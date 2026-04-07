from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from datetime import date
from importlib import resources

import httpx
from bs4 import BeautifulSoup
from docx import Document

from news_push.http import retry_http_call

SC_FGW_HOME_URL = "https://fgw.sc.gov.cn"
SC_FGW_NEWS_LIST_URL = f"{SC_FGW_HOME_URL}/sfgw/tzgg/olist.shtml"
KEYWORD_OIL_PRICE = "成品油价格"

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    sent: bool
    reason: str


@dataclass
class OilListingItem:
    title: str
    date_text: str
    page_url: str


@dataclass
class OilAttachment:
    href: str
    attachment_url: str


class OilAdjustmentCalendar:
    def __init__(self, adjustment_dates_by_year: dict[int, set[str]] | None = None) -> None:
        self.adjustment_dates_by_year = adjustment_dates_by_year or self._load_adjustment_dates_by_year()

    def is_adjustment_day(self, target_day: date) -> bool:
        year_dates = self.adjustment_dates_by_year.get(target_day.year)
        if year_dates is None:
            return False
        return target_day.isoformat() in year_dates

    def _load_adjustment_dates_by_year(self) -> dict[int, set[str]]:
        data_dir = resources.files("news_push").joinpath("data")
        adjustment_dates_by_year: dict[int, set[str]] = {}
        for item in data_dir.iterdir():
            if not item.name.startswith("oil_calendar_") or item.suffix != ".json":
                continue
            payload = json.loads(item.read_text(encoding="utf-8"))
            year = int(payload["year"])
            adjustment_dates_by_year[year] = set(payload.get("adjustment_dates", []))
        return adjustment_dates_by_year


def build_attachment_url(page_url: str, href: str) -> str | None:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return f"{SC_FGW_HOME_URL}{href}"
    last_slash = page_url.rfind("/")
    if last_slash == -1:
        return None
    return f"{page_url[:last_slash]}/{href}"


class SichuanOilSource:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def get_today_listing(self, today: date) -> OilListingItem | None:
        response = retry_http_call(
            lambda: _get_with_status_check(SC_FGW_NEWS_LIST_URL, timeout=self.timeout),
            operation=f"fetch oil listing {SC_FGW_NEWS_LIST_URL}",
        )
        soup = BeautifulSoup(response.text, "html.parser")
        for item in soup.select("ul.list > li"):
            anchor = item.select_one("a")
            date_span = item.select_one("span")
            if anchor is None or date_span is None:
                continue
            title = anchor.get_text(strip=True)
            date_text = date_span.get_text(strip=True)
            if KEYWORD_OIL_PRICE not in title or date_text != today.isoformat():
                continue
            href = anchor.get("href", "").strip()
            if not href:
                continue
            return OilListingItem(
                title=title,
                date_text=date_text,
                page_url=f"{SC_FGW_HOME_URL}{href}",
            )
        return None

    def get_attachment(self, page_url: str) -> OilAttachment | None:
        response = retry_http_call(
            lambda: _get_with_status_check(page_url, timeout=self.timeout),
            operation=f"fetch oil detail {page_url}",
        )
        soup = BeautifulSoup(response.text, "html.parser")
        link = soup.select_one("div#NewsContent a[href$='.docx']") or soup.select_one("a[href$='.docx']")
        if link is None:
            return None
        href = link.get("href", "").strip()
        if not href:
            return None
        attachment_url = build_attachment_url(page_url, href)
        if attachment_url is None:
            return None
        return OilAttachment(href=href, attachment_url=attachment_url)

    def parse_docx_prices(self, attachment_url: str) -> list[str]:
        response = retry_http_call(
            lambda: _get_with_status_check(attachment_url, timeout=self.timeout),
            operation=f"download oil attachment {attachment_url}",
        )
        document = Document(io.BytesIO(response.content))
        lines: list[str] = []
        for table in document.tables:
            rows = table.rows
            for row in rows[3:-1]:
                cells = row.cells
                if len(cells) < 4:
                    continue
                title = cells[0].text.strip()
                price = cells[3].text.strip()
                if title and price:
                    lines.append(f"{title} -- {price}")
        return lines


@dataclass
class OilPriceJob:
    source: object
    bot: object
    state_store: object
    calendar: object | None = None

    def run(self, today: date | None = None) -> JobResult:
        target_day = today or date.today()
        day_text = target_day.isoformat()
        if not self.state_store.claim_send("oil_price", day_text):
            logger.info("oil price skipped: already_sent")
            return JobResult(sent=False, reason="already_sent")

        try:
            calendar = self.calendar or OilAdjustmentCalendar()
            if not calendar.is_adjustment_day(target_day):
                logger.info("oil price skipped: not_adjustment_day")
                self.state_store.release_claim("oil_price", day_text)
                return JobResult(sent=False, reason="not_adjustment_day")

            listing = self.source.get_today_listing(target_day)
            if listing is None:
                logger.info("oil price skipped: listing_missing")
                self.state_store.release_claim("oil_price", day_text)
                return JobResult(sent=False, reason="listing_missing")

            attachment = self.source.get_attachment(listing.page_url)
            if attachment is None:
                logger.info("oil price skipped: attachment_missing")
                self.state_store.release_claim("oil_price", day_text)
                return JobResult(sent=False, reason="attachment_missing")

            price_lines = self.source.parse_docx_prices(attachment.attachment_url)
            if not price_lines:
                logger.info("oil price skipped: price_missing")
                self.state_store.release_claim("oil_price", day_text)
                return JobResult(sent=False, reason="price_missing")

            content = "\n".join([listing.title, ""] + price_lines)
            self.bot.send_text(content)
            self.state_store.complete_send(
                "oil_price",
                day_text,
                {
                    "content": content,
                    "title": listing.title,
                    "page_url": listing.page_url,
                },
            )
            logger.info("oil price sent: %s", listing.page_url)
            return JobResult(sent=True, reason="sent")
        except Exception:
            self.state_store.release_claim("oil_price", day_text)
            raise


def _get_with_status_check(url: str, *, timeout: float) -> httpx.Response:
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response
