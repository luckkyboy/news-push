import json
from datetime import date
from pathlib import Path

from news_push.oil_calendar import BOOTSTRAP_ANCHORS, OilCalendarGenerator


class FakeHolidaySource:
    def __init__(self, holidays: set[date] | None = None, working_days: set[date] | None = None) -> None:
        self.holidays = holidays or set()
        self.working_days = working_days or set()
        self.calls: list[int] = []

    def get_year_calendar(self, year: int) -> tuple[set[date], set[date]]:
        self.calls.append(year)
        return self.holidays, self.working_days


def test_generator_overwrites_existing_current_year_file(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target_file = data_dir / "oil_calendar_2026.json"
    target_file.write_text('{"old":"data"}', encoding="utf-8")

    generator = OilCalendarGenerator(
        data_dir=data_dir,
        holiday_source=FakeHolidaySource(),
        today=date(2026, 4, 1),
    )

    payload = generator.generate()

    assert payload["year"] == 2026
    assert payload["adjustment_dates"][0] == "2026-01-05"
    assert json.loads(target_file.read_text(encoding="utf-8")) == payload


def test_generator_uses_previous_year_file_as_anchor_when_available(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    previous_file = data_dir / "oil_calendar_2026.json"
    previous_file.write_text(
        json.dumps(
            {
                "year": 2026,
                "adjustment_dates": ["2026-12-10", "2026-12-24"],
            }
        ),
        encoding="utf-8",
    )
    generator = OilCalendarGenerator(
        data_dir=data_dir,
        holiday_source=FakeHolidaySource(),
        today=date(2027, 1, 3),
    )

    payload = generator.generate()

    assert payload["anchor_previous_adjustment_date"] == "2026-12-24"
    assert payload["adjustment_dates"][0] == "2027-01-07"


def test_bootstrap_anchor_covers_2026_generation() -> None:
    assert BOOTSTRAP_ANCHORS[2026] == "2025-12-22"
