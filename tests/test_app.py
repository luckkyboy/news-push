from dataclasses import dataclass
from datetime import date
import json
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

    def claim_send(self, channel: str, day: str) -> bool:
        return True

    def complete_send(self, channel: str, day: str, metadata: dict) -> None:
        self.data.setdefault(channel, {})[day] = metadata

    def release_claim(self, channel: str, day: str) -> None:
        return None

    def snapshot(self) -> dict:
        return self.data


@dataclass
class FakeImageJob:
    image_base_url: str
    fetcher: object
    bot: object
    state_store: object
    clock: object

    def run(self) -> NewsJobResult:
        return NewsJobResult(sent=True, reason="sent")


@dataclass
class FakeOilJob:
    source: object
    bot: object
    state_store: object
    clock: object
    calendar: object

    def run(self) -> NewsJobResult:
        return NewsJobResult(sent=False, reason="listing_missing")


class FakeBot:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url


class FixedClock:
    def __init__(self, today: date) -> None:
        self.today_value = today

    def today(self) -> date:
        return self.today_value


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
        oil_calendar_data_dir=tmp_path / "oil-calendar",
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
        oil_calendar_data_dir=tmp_path / "oil-calendar",
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
        oil_calendar_data_dir=tmp_path / "oil-calendar",
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


def test_ensure_oil_calendar_generates_missing_current_year(monkeypatch, tmp_path: Path) -> None:
    generated: list[int] = []

    class FakeOilCalendarGenerator:
        def __init__(self, data_dir: Path, today: date, anchor_data_dirs: list[object]) -> None:
            self.data_dir = data_dir
            self.today = today

        def generate(self, year: int) -> dict[str, object]:
            generated.append(year)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "year": year,
                "adjustment_dates": [f"{year}-01-05"],
            }
            (self.data_dir / f"oil_calendar_{year}.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            return payload

    monkeypatch.setattr(app_module, "OilCalendarGenerator", FakeOilCalendarGenerator)
    settings = Settings(
        wecom_webhook_url="",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        oil_calendar_data_dir=tmp_path / "oil-calendar",
        timezone="Asia/Shanghai",
    )

    calendar = app_module.ensure_oil_calendar(settings, FixedClock(date(2027, 1, 1)))

    assert generated == [2027]
    assert calendar.is_adjustment_day(date(2027, 1, 5)) is True


def test_ensure_oil_calendar_uses_existing_current_year(tmp_path: Path) -> None:
    oil_calendar_data_dir = tmp_path / "oil-calendar"
    oil_calendar_data_dir.mkdir()
    (oil_calendar_data_dir / "oil_calendar_2027.json").write_text(
        json.dumps({"year": 2027, "adjustment_dates": ["2027-01-05"]}),
        encoding="utf-8",
    )
    settings = Settings(
        wecom_webhook_url="",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        oil_calendar_data_dir=oil_calendar_data_dir,
        timezone="Asia/Shanghai",
    )

    calendar = app_module.ensure_oil_calendar(settings, FixedClock(date(2027, 1, 1)))

    assert calendar.is_adjustment_day(date(2027, 1, 5)) is True


def test_oil_calendar_generates_new_year_while_process_keeps_running(monkeypatch, tmp_path: Path) -> None:
    generated: list[int] = []

    class FakeOilCalendarGenerator:
        def __init__(self, data_dir: Path, today: date, anchor_data_dirs: list[object]) -> None:
            self.data_dir = data_dir

        def generate(self, year: int) -> dict[str, object]:
            generated.append(year)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "year": year,
                "adjustment_dates": [f"{year}-01-05"],
            }
            (self.data_dir / f"oil_calendar_{year}.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            return payload

    monkeypatch.setattr(app_module, "OilCalendarGenerator", FakeOilCalendarGenerator)
    settings = Settings(
        wecom_webhook_url="",
        image_base_url="https://example.com/images",
        state_file=tmp_path / "state.json",
        oil_calendar_data_dir=tmp_path / "oil-calendar",
        timezone="Asia/Shanghai",
    )

    calendar = app_module.ensure_oil_calendar(settings, FixedClock(date(2026, 12, 31)))

    assert generated == []
    assert calendar.is_adjustment_day(date(2027, 1, 5)) is True
    assert generated == [2027]
