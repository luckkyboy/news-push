from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
import logging
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from threading import RLock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from news_push.clock import LocalClock
from news_push.config import Settings
from news_push.news_image import DailyImageJob, ImageFetcher
from news_push.oil import OilAdjustmentCalendar, OilPriceJob, SichuanOilSource
from news_push.oil_calendar import OilCalendarGenerator
from news_push.state import StateStore
from news_push.wecom import WeComBotClient

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    clock = LocalClock(settings.timezone)
    oil_calendar = ensure_oil_calendar(settings, clock)
    state_store = StateStore(settings.state_file)
    bot = WeComBotClient(settings.wecom_webhook_url) if settings.wecom_webhook_url else None
    image_job = DailyImageJob(
        image_base_url=settings.image_base_url,
        fetcher=ImageFetcher(),
        bot=bot,
        state_store=state_store,
        clock=clock,
    )
    oil_job = OilPriceJob(
        source=SichuanOilSource(),
        bot=bot,
        state_store=state_store,
        clock=clock,
        calendar=oil_calendar,
    )
    scheduler = BackgroundScheduler(timezone=settings.timezone)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if bot is not None:
            scheduler.add_job(
                image_job.run,
                CronTrigger(minute="*/10", hour="0-10", timezone=settings.timezone),
                id="news_image_push",
                replace_existing=True,
            )
            scheduler.add_job(
                oil_job.run,
                CronTrigger(minute="0/30", hour="17-20", timezone=settings.timezone),
                id="oil_price_push",
                replace_existing=True,
            )
        scheduler.start()
        yield
        if scheduler.running:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="news-push", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    def status() -> dict[str, object]:
        return {
            "jobs": [job.id for job in scheduler.get_jobs()],
            "state": state_store.snapshot(),
            "webhookConfigured": bot is not None,
        }

    @app.post("/jobs/news-image/run")
    def run_news_image() -> dict[str, object]:
        if bot is None:
            return {"sent": False, "reason": "missing_webhook"}
        result = image_job.run()
        return {"sent": result.sent, "reason": result.reason}

    @app.post("/jobs/oil/run")
    def run_oil() -> dict[str, object]:
        if bot is None:
            return {"sent": False, "reason": "missing_webhook"}
        result = oil_job.run()
        return {"sent": result.sent, "reason": result.reason}

    return app


class AutoGeneratingOilCalendar:
    def __init__(
        self,
        runtime_data_dir: Path,
        anchor_data_dirs: list[Traversable],
    ) -> None:
        self.runtime_data_dir = runtime_data_dir
        self.anchor_data_dirs = anchor_data_dirs
        self._lock = RLock()
        self._calendar = self._load_calendar()

    def is_adjustment_day(self, target_day: date) -> bool:
        self.ensure_year(target_day)
        return self._calendar.is_adjustment_day(target_day)

    def ensure_year(self, target_day: date) -> None:
        target_year = target_day.year
        if self._calendar.has_year(target_year):
            return

        with self._lock:
            if self._calendar.has_year(target_year):
                return
            logger.info(
                "oil calendar missing for %s, generating into %s",
                target_year,
                self.runtime_data_dir,
            )
            OilCalendarGenerator(
                data_dir=self.runtime_data_dir,
                today=target_day,
                anchor_data_dirs=self.anchor_data_dirs,
            ).generate(target_year)
            self._calendar = self._load_calendar()

    def _load_calendar(self) -> OilAdjustmentCalendar:
        return OilAdjustmentCalendar(data_dirs=[self.runtime_data_dir])


def ensure_oil_calendar(settings: Settings, clock: LocalClock) -> AutoGeneratingOilCalendar:
    calendar = AutoGeneratingOilCalendar(
        runtime_data_dir=settings.oil_calendar_data_dir,
        anchor_data_dirs=[resources.files("news_push").joinpath("data")],
    )
    calendar.ensure_year(clock.today())
    return calendar


app = create_app()
