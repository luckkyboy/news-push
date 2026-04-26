from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    wecom_webhook_url: str
    image_base_url: str
    state_file: Path
    oil_calendar_data_dir: Path
    timezone: str

    @classmethod
    def from_env(cls) -> "Settings":
        state_file = Path(os.environ.get("STATE_FILE", "/tmp/news-push/state.db"))
        return cls(
            wecom_webhook_url=os.environ.get("WECOM_WEBHOOK_URL", ""),
            image_base_url=os.environ.get(
                "NEWS_IMAGE_BASE_URL",
                "https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images",
            ),
            state_file=state_file,
            oil_calendar_data_dir=Path(
                os.environ.get("OIL_CALENDAR_DATA_DIR", str(state_file.parent / "oil-calendar"))
            ),
            timezone=os.environ.get("TZ", "Asia/Shanghai"),
        )
