from dataclasses import dataclass
from pathlib import Path

import news_push.app as app_module
from anyio import run
from news_push.config import Settings
from news_push.news_image import JobResult as NewsJobResult


class FakeScheduler:
    def __init__(self, timezone: str) -> None:
        self.timezone = timezone
        self.jobs: list[object] = []
        self.running = False

    def add_job(self, func, trigger, id: str, replace_existing: bool) -> None:
        self.jobs.append(type("Job", (), {"id": id})())

    def get_jobs(self) -> list[object]:
        return self.jobs

    def start(self) -> None:
        self.running = True

    def shutdown(self, wait: bool = False) -> None:
        self.running = False


class FakeCronTrigger:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class DummyStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = {"news_image": {"2026-03-30": {"url": "https://example.com/news.png"}}}

    def snapshot(self) -> dict:
        return self.data


@dataclass
class FakeImageJob:
    image_base_url: str
    fetcher: object
    bot: object
    state_store: object

    def run(self) -> NewsJobResult:
        return NewsJobResult(sent=True, reason="sent")


@dataclass
class FakeOilJob:
    source: object
    bot: object
    state_store: object

    def run(self) -> NewsJobResult:
        return NewsJobResult(sent=False, reason="listing_missing")


class FakeBot:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url


def test_status_reports_jobs_and_webhook_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(app_module, "CronTrigger", FakeCronTrigger)
    monkeypatch.setattr(app_module, "StateStore", DummyStateStore)
    monkeypatch.setattr(app_module, "DailyImageJob", FakeImageJob)
    monkeypatch.setattr(app_module, "OilPriceJob", FakeOilJob)
    monkeypatch.setattr(app_module, "WeComBotClient", FakeBot)

    settings = Settings(
        wecom_webhook_url="https://example.com/webhook",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        timezone="Asia/Shanghai",
    )

    app = app_module.create_app(settings)
    async def exercise() -> dict:
        async with app.router.lifespan_context(app):
            for route in app.routes:
                if getattr(route, "path", None) == "/status":
                    return route.endpoint()
            raise AssertionError("route not found: GET /status")

    assert run(exercise) == {
        "jobs": ["news_image_push", "oil_price_push"],
        "state": {"news_image": {"2026-03-30": {"url": "https://example.com/news.png"}}},
        "webhookConfigured": True,
    }


def test_manual_job_run_returns_missing_webhook_when_not_configured(tmp_path: Path) -> None:
    settings = Settings(
        wecom_webhook_url="",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        timezone="Asia/Shanghai",
    )

    app = app_module.create_app(settings)
    def exercise() -> dict:
        for route in app.routes:
            if getattr(route, "path", None) == "/jobs/news-image/run":
                return route.endpoint()
        raise AssertionError("route not found: POST /jobs/news-image/run")

    assert exercise() == {"sent": False, "reason": "missing_webhook"}


def test_manual_job_run_returns_job_result_when_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(app_module, "CronTrigger", FakeCronTrigger)
    monkeypatch.setattr(app_module, "StateStore", DummyStateStore)
    monkeypatch.setattr(app_module, "DailyImageJob", FakeImageJob)
    monkeypatch.setattr(app_module, "OilPriceJob", FakeOilJob)
    monkeypatch.setattr(app_module, "WeComBotClient", FakeBot)

    settings = Settings(
        wecom_webhook_url="https://example.com/webhook",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        timezone="Asia/Shanghai",
    )

    app = app_module.create_app(settings)
    async def exercise() -> dict:
        async with app.router.lifespan_context(app):
            for route in app.routes:
                if getattr(route, "path", None) == "/jobs/news-image/run":
                    return route.endpoint()
            raise AssertionError("route not found: POST /jobs/news-image/run")

    assert run(exercise) == {"sent": True, "reason": "sent"}
