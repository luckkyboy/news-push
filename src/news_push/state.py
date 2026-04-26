from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
from threading import RLock
import time
from typing import Any


class StateStore:
    def __init__(self, path: Path, pending_claim_ttl_seconds: int = 3600) -> None:
        self.path = path
        self.pending_claim_ttl_seconds = pending_claim_ttl_seconds
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
        now = self._now()
        expired_before = now - self.pending_claim_ttl_seconds
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sends (channel, day, status, metadata, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                ON CONFLICT(channel, day) DO UPDATE SET
                    status = 'pending',
                    metadata = '{}',
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                WHERE sends.status = 'pending'
                    AND sends.updated_at < ?
                """,
                (channel, day, "{}", now, now, expired_before),
            )
            connection.commit()
            return cursor.rowcount > 0

    def release_claim(self, channel: str, day: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM sends WHERE channel = ? AND day = ? AND status = 'pending'",
                (channel, day),
            )
            connection.commit()

    def complete_send(self, channel: str, day: str, metadata: dict[str, Any]) -> None:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        now = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sends (channel, day, status, metadata, created_at, updated_at)
                VALUES (?, ?, 'sent', ?, ?, ?)
                ON CONFLICT(channel, day) DO UPDATE SET
                    status = 'sent',
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (channel, day, payload, now, now),
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
                    created_at INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (channel, day)
                )
                """
            )
            self._migrate_schema(connection)
            connection.commit()

            if legacy_payload:
                now = self._now()
                for channel, days in legacy_payload.items():
                    for day, metadata in days.items():
                        connection.execute(
                            """
                            INSERT INTO sends (channel, day, status, metadata, created_at, updated_at)
                            VALUES (?, ?, 'sent', ?, ?, ?)
                            ON CONFLICT(channel, day) DO UPDATE SET
                                status = 'sent',
                                metadata = excluded.metadata,
                                updated_at = excluded.updated_at
                            """,
                            (
                                channel,
                                day,
                                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                                now,
                                now,
                            ),
                        )
                connection.commit()

    def _migrate_schema(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sends)").fetchall()
        }
        if "created_at" not in columns:
            connection.execute("ALTER TABLE sends ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
        if "updated_at" not in columns:
            connection.execute("ALTER TABLE sends ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _now(self) -> int:
        return int(time.time())

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
