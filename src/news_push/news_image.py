from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import httpx

from news_push.http import retry_http_call

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    sent: bool
    reason: str


@dataclass
class ImageFetcher:
    timeout: float = 10.0

    def fetch_if_exists(self, url: str) -> bytes | None:
        response = retry_http_call(
            lambda: httpx.get(url, timeout=self.timeout),
            operation=f"fetch image {url}",
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content


@dataclass
class DailyImageJob:
    image_base_url: str
    fetcher: ImageFetcher
    bot: object
    state_store: object

    def run(self, today: date | None = None) -> JobResult:
        target_day = today or date.today()
        day_text = target_day.isoformat()
        if self.state_store.has_sent("news_image", day_text):
            logger.info("news image skipped: already_sent")
            return JobResult(sent=False, reason="already_sent")

        image_url = f"{self.image_base_url.rstrip('/')}/{day_text}.png"
        image_bytes = self.fetcher.fetch_if_exists(image_url)
        if image_bytes is None:
            logger.info("news image skipped: image_missing")
            return JobResult(sent=False, reason="image_missing")

        self.bot.send_image(image_bytes)
        self.state_store.mark_sent("news_image", day_text, {"url": image_url})
        logger.info("news image sent: %s", image_url)
        return JobResult(sent=True, reason="sent")
