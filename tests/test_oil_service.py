import io
import logging
from datetime import date

import httpx
import pytest
from docx import Document

from news_push.oil import (
    OilAdjustmentCalendar,
    OilAttachment,
    OilListingItem,
    OilPriceJob,
    SichuanOilSource,
    build_attachment_url,
)


def test_build_attachment_url_supports_relative_and_absolute_paths() -> None:
    page_url = "https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/abcd.shtml"

    assert (
        build_attachment_url(page_url, "file.docx")
        == "https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/file.docx"
    )
    assert (
        build_attachment_url(page_url, "/upload/file.docx")
        == "https://fgw.sc.gov.cn/upload/file.docx"
    )
    assert (
        build_attachment_url(page_url, "https://cdn.example.com/file.docx")
        == "https://cdn.example.com/file.docx"
    )


class DummyOilSource:
    def __init__(self, listing: OilListingItem | None, attachment: OilAttachment | None) -> None:
        self.listing = listing
        self.attachment = attachment
        self.calls = {"listing": 0, "attachment": 0, "prices": 0}

    def get_today_listing(self, today: date) -> OilListingItem | None:
        self.calls["listing"] += 1
        return self.listing

    def get_attachment(self, page_url: str) -> OilAttachment | None:
        self.calls["attachment"] += 1
        return self.attachment

    def parse_docx_prices(self, attachment_url: str) -> list[str]:
        self.calls["prices"] += 1
        return ["92号汽油 -- 7.12", "95号汽油 -- 7.61"]


class DummyCalendar:
    def __init__(self, is_adjustment_day: bool) -> None:
        self.is_adjustment_day_value = is_adjustment_day

    def is_adjustment_day(self, target_day: date) -> bool:
        return self.is_adjustment_day_value


class DummyClock:
    def __init__(self, today: date) -> None:
        self.today_value = today

    def today(self) -> date:
        return self.today_value


class DummyBot:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_text(self, content: str) -> None:
        self.messages.append(content)


class DummyStore:
    def __init__(self, sent: bool = False) -> None:
        self.sent = sent
        self.marked: list[tuple[str, str, dict[str, str]]] = []
        self.claimed: set[tuple[str, str]] = set()
        self.released: list[tuple[str, str]] = []

    def has_sent(self, channel: str, day: str) -> bool:
        return self.sent

    def claim_send(self, channel: str, day: str) -> bool:
        key = (channel, day)
        if self.sent or key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def release_claim(self, channel: str, day: str) -> None:
        key = (channel, day)
        self.claimed.discard(key)
        self.released.append(key)

    def mark_sent(self, channel: str, day: str, metadata: dict[str, str]) -> None:
        self.marked.append((channel, day, metadata))
        self.sent = True

    def complete_send(self, channel: str, day: str, metadata: dict[str, str]) -> None:
        self.mark_sent(channel, day, metadata)


def test_oil_job_sends_today_listing() -> None:
    source = DummyOilSource(
        listing=OilListingItem(
            title="成品油价格按机制上调",
            date_text="2026-03-30",
            page_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/abcd.shtml",
        ),
        attachment=OilAttachment(
            href="file.docx",
            attachment_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/file.docx",
        ),
    )
    bot = DummyBot()
    store = DummyStore()
    job = OilPriceJob(
        source=source,
        bot=bot,
        state_store=store,
        calendar=DummyCalendar(True),
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is True
    assert result.reason == "sent"
    assert "成品油价格按机制上调" in bot.messages[0]
    assert "92号汽油 -- 7.12" in bot.messages[0]
    assert store.marked == [
        (
            "oil_price",
            "2026-03-30",
            {
                "content": "成品油价格按机制上调\n\n92号汽油 -- 7.12\n95号汽油 -- 7.61",
                "title": "成品油价格按机制上调",
                "page_url": "https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/abcd.shtml",
            },
        )
    ]


def test_oil_job_uses_clock_when_today_is_not_provided() -> None:
    source = DummyOilSource(
        listing=OilListingItem(
            title="成品油价格按机制上调",
            date_text="2026-04-26",
            page_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/4/26/abcd.shtml",
        ),
        attachment=OilAttachment(
            href="file.docx",
            attachment_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/4/26/file.docx",
        ),
    )
    store = DummyStore()
    job = OilPriceJob(
        source=source,
        bot=DummyBot(),
        state_store=store,
        calendar=DummyCalendar(True),
        clock=DummyClock(date(2026, 4, 26)),
    )

    result = job.run()

    assert result.sent is True
    assert store.marked[0][1] == "2026-04-26"
    assert source.calls == {"listing": 1, "attachment": 1, "prices": 1}


def test_oil_job_skips_when_no_listing_found() -> None:
    job = OilPriceJob(
        source=DummyOilSource(None, None),
        bot=DummyBot(),
        state_store=DummyStore(),
        calendar=DummyCalendar(True),
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "listing_missing"


def test_adjustment_calendar_recognizes_known_2026_dates() -> None:
    calendar = OilAdjustmentCalendar()

    assert calendar.is_adjustment_day(date(2026, 1, 6)) is True
    assert calendar.is_adjustment_day(date(2026, 3, 9)) is True
    assert calendar.is_adjustment_day(date(2026, 1, 7)) is False
    assert calendar.is_adjustment_day(date(2027, 1, 6)) is False


def test_oil_job_skips_when_today_is_not_adjustment_day() -> None:
    source = DummyOilSource(None, None)
    job = OilPriceJob(
        source=source,
        bot=DummyBot(),
        state_store=DummyStore(),
        calendar=DummyCalendar(False),
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "not_adjustment_day"
    assert source.calls == {"listing": 0, "attachment": 0, "prices": 0}


def test_oil_job_skips_when_send_claim_is_already_held() -> None:
    source = DummyOilSource(None, None)
    store = DummyStore()
    assert store.claim_send("oil_price", "2026-03-30") is True
    job = OilPriceJob(
        source=source,
        bot=DummyBot(),
        state_store=store,
        calendar=DummyCalendar(True),
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "already_sent"
    assert source.calls == {"listing": 0, "attachment": 0, "prices": 0}


def test_parse_docx_prices_retries_after_transient_request_error(monkeypatch) -> None:
    calls = 0
    document = Document()
    table = document.add_table(rows=5, cols=4)
    table.rows[3].cells[0].text = "92号汽油"
    table.rows[3].cells[3].text = "7.12"
    buffer = io.BytesIO()
    document.save(buffer)

    def fake_get(url: str, timeout: float) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return httpx.Response(
            200,
            content=buffer.getvalue(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    source = SichuanOilSource(timeout=1.0)

    parsed = source.parse_docx_prices("https://example.com/file.docx")

    assert parsed == ["92号汽油 -- 7.12"]
    assert calls == 2


def test_oil_job_logs_skip_reason_when_listing_missing(caplog) -> None:
    job = OilPriceJob(
        source=DummyOilSource(None, None),
        bot=DummyBot(),
        state_store=DummyStore(),
        calendar=DummyCalendar(True),
    )

    with caplog.at_level(logging.INFO):
        result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "listing_missing"
    assert "oil price skipped: listing_missing" in caplog.text


def test_oil_job_releases_claim_when_send_fails() -> None:
    class FailingBot:
        def send_text(self, content: str) -> None:
            raise RuntimeError("boom")

    source = DummyOilSource(
        listing=OilListingItem(
            title="成品油价格按机制上调",
            date_text="2026-03-30",
            page_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/abcd.shtml",
        ),
        attachment=OilAttachment(
            href="file.docx",
            attachment_url="https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/file.docx",
        ),
    )
    store = DummyStore()
    job = OilPriceJob(
        source=source,
        bot=FailingBot(),
        state_store=store,
        calendar=DummyCalendar(True),
    )

    with pytest.raises(RuntimeError, match="boom"):
        job.run(today=date(2026, 3, 30))

    assert store.released == [("oil_price", "2026-03-30")]
    assert store.marked == []
