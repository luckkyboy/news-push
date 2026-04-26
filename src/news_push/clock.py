from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def today(self) -> date:
        raise NotImplementedError


@dataclass(frozen=True)
class LocalClock:
    timezone: str

    def today(self) -> date:
        return datetime.now(ZoneInfo(self.timezone)).date()
