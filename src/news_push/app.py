from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from news_push.config import Settings
from news_push.news_image import DailyImageJob, ImageFetcher
from news_push.oil import OilPriceJob, SichuanOilSource
from news_push.state import StateStore
from news_push.wecom import WeComBotClient


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    state_store = StateStore(settings.state_file)
    bot = WeComBotClient(settings.wecom_webhook_url) if settings.wecom_webhook_url else None
    image_job = DailyImageJob(
        image_base_url=settings.image_base_url,
        fetcher=ImageFetcher(),
        bot=bot,
        state_store=state_store,
    )
    oil_job = OilPriceJob(
        source=SichuanOilSource(),
        bot=bot,
        state_store=state_store,
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


app = create_app()
