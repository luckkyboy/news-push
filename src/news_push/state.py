from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
from threading import RLock
from typing import Any


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._bootstrap()

    def has_sent(self, channel: str, day: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sends WHERE channel = ? AND day = ? AND status = 'sent'",
                (channel, day),
            ).fetchone()
        return row is not None

    def claim_send(self, channel: str, day: str) -> bool:
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO sends (channel, day, status, metadata) VALUES (?, ?, 'pending', ?)",
                    (channel, day, "{}"),
                )
                connection.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def release_claim(self, channel: str, day: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM sends WHERE channel = ? AND day = ? AND status = 'pending'",
                (channel, day),
            )
            connection.commit()

    def complete_send(self, channel: str, day: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sends (channel, day, status, metadata)
                VALUES (?, ?, 'sent', ?)
                ON CONFLICT(channel, day) DO UPDATE SET
                    status = 'sent',
                    metadata = excluded.metadata
                """,
                (channel, day, payload),
            )
            connection.commit()

    def mark_sent(self, channel: str, day: str, metadata: dict[str, Any]) -> None:
        self.complete_send(channel, day, metadata)

    def snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT channel, day, metadata
                FROM sends
                WHERE status = 'sent'
                ORDER BY channel, day
                """
            ).fetchall()

        snapshot: dict[str, dict[str, dict[str, Any]]] = {}
        for channel, day, metadata_text in rows:
            snapshot.setdefault(channel, {})[day] = json.loads(metadata_text)
        return snapshot

    def _bootstrap(self) -> None:
        legacy_payload = self._load_legacy_json_if_needed()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sends (
                    channel TEXT NOT NULL,
                    day TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (channel, day)
                )
                """
            )
            connection.commit()

            if legacy_payload:
                for channel, days in legacy_payload.items():
                    for day, metadata in days.items():
                        connection.execute(
                            """
                            INSERT INTO sends (channel, day, status, metadata)
                            VALUES (?, ?, 'sent', ?)
                            ON CONFLICT(channel, day) DO UPDATE SET
                                status = 'sent',
                                metadata = excluded.metadata
                            """,
                            (
                                channel,
                                day,
                                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                            ),
                        )
                connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _load_legacy_json_if_needed(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}

        header = self.path.read_bytes()[:16]
        if not header:
            return {}
        if header.startswith(b"SQLite format 3\x00"):
            return {}

        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            self.path.unlink()
            return {}

        payload = json.loads(raw)
        backup_path = self.path.with_name(f"{self.path.name}.legacy.json.bak")
        shutil.copyfile(self.path, backup_path)
        self.path.unlink()
        return payload
