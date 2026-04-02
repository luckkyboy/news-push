#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from news_push.oil_calendar import OilCalendarGenerator


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "src" / "news_push" / "data"
    payload = OilCalendarGenerator(data_dir=data_dir).generate()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
