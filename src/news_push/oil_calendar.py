from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from importlib.resources.abc import Traversable
from pathlib import Path

import httpx

from news_push.http import retry_http_call

HOLIDAY_DATA_URL_TEMPLATE = "https://raw.githubusercontent.com/bastengao/chinese-holidays-data/master/data/{year}.json"
BOOTSTRAP_ANCHORS = {
    2026: "2025-12-22",
}


def _expand_range(raw_range: list[str]) -> list[date]:
    if len(raw_range) == 1:
        return [date.fromisoformat(raw_range[0])]
    start = date.fromisoformat(raw_range[0])
    end = date.fromisoformat(raw_range[1])
    result: list[date] = []
    current = start
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def _is_workday(target_day: date, holidays: set[date], working_days: set[date]) -> bool:
    if target_day in working_days:
        return True
    if target_day in holidays:
        return False
    return target_day.weekday() < 5


class ChinaHolidaySource:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def get_year_calendar(self, year: int) -> tuple[set[date], set[date]]:
        url = HOLIDAY_DATA_URL_TEMPLATE.format(year=year)
        response = retry_http_call(
            lambda: _get_with_status_check(url, timeout=self.timeout),
            operation=f"fetch holiday calendar {url}",
        )
        payload = response.json()
        holidays: set[date] = set()
        working_days: set[date] = set()
        for item in payload:
            target_set = working_days if item["type"] == "workingday" else holidays
            target_set.update(_expand_range(item["range"]))
        return holidays, working_days


@dataclass
class OilCalendarGenerator:
    data_dir: Path
    holiday_source: object | None = None
    today: date | None = None
    anchor_data_dirs: list[Path | Traversable] | None = None

    def generate(self, year: int | None = None) -> dict[str, object]:
        target_year = year or (self.today or date.today()).year
        holidays, working_days = self._holiday_source().get_year_calendar(target_year)
        anchor_previous_adjustment_date = self._resolve_anchor_previous_adjustment_date(target_year)
        adjustment_dates = self._derive_adjustment_dates(
            target_year=target_year,
            anchor_previous_adjustment_date=date.fromisoformat(anchor_previous_adjustment_date),
            holidays=holidays,
            working_days=working_days,
        )
        payload = {
            "calendar_name": "cn_refined_oil_adjustment_days",
            "timezone": "Asia/Shanghai",
            "generated_at": (self.today or date.today()).isoformat(),
            "description": (
                "Domestic refined oil adjustment window dates derived from the 10-working-day "
                "NDRC rule and the China holiday/workday calendar."
            ),
            "sources": [
                {
                    "name": "国家发展改革委关于进一步完善成品油价格形成机制的通知",
                    "url": "https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=19805",
                },
                {
                    "name": f"{target_year} holiday and working-day data",
                    "url": HOLIDAY_DATA_URL_TEMPLATE.format(year=target_year),
                },
            ],
            "year": target_year,
            "anchor_previous_adjustment_date": anchor_previous_adjustment_date,
            "adjustment_dates": adjustment_dates,
        }
        output_path = self.data_dir / f"oil_calendar_{target_year}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _holiday_source(self) -> object:
        return self.holiday_source or ChinaHolidaySource()

    def _resolve_anchor_previous_adjustment_date(self, year: int) -> str:
        for data_dir in [self.data_dir] + list(self.anchor_data_dirs or []):
            previous_path = data_dir / f"oil_calendar_{year - 1}.json"
            if previous_path.exists():
                payload = json.loads(previous_path.read_text(encoding="utf-8"))
                adjustment_dates = payload.get("adjustment_dates", [])
                if adjustment_dates:
                    return adjustment_dates[-1]
        bootstrap_anchor = BOOTSTRAP_ANCHORS.get(year)
        if bootstrap_anchor is None:
            raise ValueError(f"missing previous-year oil calendar and bootstrap anchor for {year}")
        return bootstrap_anchor

    def _derive_adjustment_dates(
        self,
        target_year: int,
        anchor_previous_adjustment_date: date,
        holidays: set[date],
        working_days: set[date],
    ) -> list[str]:
        current = anchor_previous_adjustment_date
        adjustment_dates: list[str] = []
        while True:
            current = self._next_adjustment_day(current, holidays, working_days)
            if current.year > target_year:
                break
            if current.year == target_year:
                adjustment_dates.append(current.isoformat())
        return adjustment_dates

    def _next_adjustment_day(
        self,
        current: date,
        holidays: set[date],
        working_days: set[date],
    ) -> date:
        counted = 0
        target = current
        while counted < 10:
            target += timedelta(days=1)
            if _is_workday(target, holidays, working_days):
                counted += 1
        return target


def _get_with_status_check(url: str, *, timeout: float) -> httpx.Response:
    response = httpx.get(url, timeout=timeout)
    response.raise_for_status()
    return response
