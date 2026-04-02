import logging
from datetime import date

import httpx

from news_push.news_image import DailyImageJob, ImageFetcher


class DummyFetcher:
    def __init__(self, exists: bool, content: bytes | None = None) -> None:
        self.exists = exists
        self.content = content or b"image-bytes"
        self.checked_urls: list[str] = []

    def fetch_if_exists(self, url: str) -> bytes | None:
        self.checked_urls.append(url)
        return self.content if self.exists else None


class DummyBot:
    def __init__(self) -> None:
        self.images: list[bytes] = []

    def send_image(self, image_bytes: bytes) -> None:
        self.images.append(image_bytes)


class DummyStore:
    def __init__(self, sent: bool = False) -> None:
        self.sent = sent
        self.marked: list[tuple[str, str, dict[str, str]]] = []

    def has_sent(self, channel: str, day: str) -> bool:
        return self.sent

    def mark_sent(self, channel: str, day: str, metadata: dict[str, str]) -> None:
        self.marked.append((channel, day, metadata))
        self.sent = True


def test_run_sends_image_when_available() -> None:
    fetcher = DummyFetcher(exists=True, content=b"news-image")
    bot = DummyBot()
    store = DummyStore()
    job = DailyImageJob(
        image_base_url="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images",
        fetcher=fetcher,
        bot=bot,
        state_store=store,
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is True
    assert result.reason == "sent"
    assert bot.images == [b"news-image"]
    assert fetcher.checked_urls == [
        "https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images/2026-03-30.png"
    ]
    assert store.marked == [
        (
            "news_image",
            "2026-03-30",
            {"url": "https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images/2026-03-30.png"},
        )
    ]


def test_run_skips_when_already_sent() -> None:
    fetcher = DummyFetcher(exists=True)
    bot = DummyBot()
    store = DummyStore(sent=True)
    job = DailyImageJob(
        image_base_url="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images",
        fetcher=fetcher,
        bot=bot,
        state_store=store,
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "already_sent"
    assert bot.images == []
    assert fetcher.checked_urls == []


def test_run_skips_when_image_missing() -> None:
    fetcher = DummyFetcher(exists=False)
    bot = DummyBot()
    store = DummyStore()
    job = DailyImageJob(
        image_base_url="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images",
        fetcher=fetcher,
        bot=bot,
        state_store=store,
    )

    result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "image_missing"
    assert bot.images == []
    assert store.marked == []


def test_fetch_if_exists_retries_after_transient_request_error(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: float) -> httpx.Response:
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("temporary failure")
        return httpx.Response(200, content=b"news-image", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    fetcher = ImageFetcher(timeout=1.0)

    content = fetcher.fetch_if_exists("https://example.com/2026-03-30.png")

    assert content == b"news-image"
    assert calls == [
        "https://example.com/2026-03-30.png",
        "https://example.com/2026-03-30.png",
    ]


def test_run_logs_skip_reason_when_image_missing(caplog) -> None:
    fetcher = DummyFetcher(exists=False)
    bot = DummyBot()
    store = DummyStore()
    job = DailyImageJob(
        image_base_url="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images",
        fetcher=fetcher,
        bot=bot,
        state_store=store,
    )

    with caplog.at_level(logging.INFO):
        result = job.run(today=date(2026, 3, 30))

    assert result.sent is False
    assert result.reason == "image_missing"
    assert "news image skipped: image_missing" in caplog.text
