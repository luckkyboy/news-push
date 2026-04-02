from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
import uuid
from typing import Any


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def has_sent(self, channel: str, day: str) -> bool:
        data = self._load()
        return day in data.get(channel, {})

    def mark_sent(self, channel: str, day: str, metadata: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            channel_data = data.setdefault(channel, {})
            channel_data[day] = metadata
            self._save(data)

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        return self._load()

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        with self._lock:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            return json.loads(raw)

    def _save(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
