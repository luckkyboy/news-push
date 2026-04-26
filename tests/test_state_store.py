from pathlib import Path
import sqlite3

import pytest

from news_push.state import StateStore


def test_mark_and_check_sent_date(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)

    assert store.has_sent("news_image", "2026-03-30") is False

    store.mark_sent("news_image", "2026-03-30", {"url": "https://example.com/a.png"})

    assert store.has_sent("news_image", "2026-03-30") is True

    reloaded = StateStore(state_file)
    assert reloaded.has_sent("news_image", "2026-03-30") is True


def test_get_snapshot_includes_metadata(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.mark_sent("oil_price", "2026-03-30", {"title": "油价调整"})

    snapshot = store.snapshot()

    assert snapshot["oil_price"]["2026-03-30"]["title"] == "油价调整"


def test_legacy_json_state_is_migrated_to_sqlite_on_init(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        '{"news_image":{"2026-03-30":{"url":"https://example.com/a.png"}}}',
        encoding="utf-8",
    )

    store = StateStore(state_file)

    reloaded = StateStore(state_file)
    assert reloaded.snapshot() == {
        "news_image": {
            "2026-03-30": {"url": "https://example.com/a.png"},
        }
    }
    assert state_file.with_name("state.json.legacy.json.bak").exists() is True


def test_claim_send_prevents_duplicate_claims_until_released(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")

    first_claim = store.claim_send("news_image", "2026-03-30")
    second_claim = store.claim_send("news_image", "2026-03-30")

    assert first_claim is True
    assert second_claim is False

    store.release_claim("news_image", "2026-03-30")

    assert store.claim_send("news_image", "2026-03-30") is True


def test_expired_pending_claim_can_be_reclaimed(monkeypatch, tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db", pending_claim_ttl_seconds=60)
    now = 1_000
    monkeypatch.setattr(store, "_now", lambda: now)

    assert store.claim_send("news_image", "2026-03-30") is True
    assert store.claim_send("news_image", "2026-03-30") is False

    now = 1_061

    assert store.claim_send("news_image", "2026-03-30") is True


def test_existing_sqlite_state_gets_timestamp_columns(tmp_path: Path) -> None:
    state_file = tmp_path / "state.db"
    with sqlite3.connect(state_file) as connection:
        connection.execute(
            """
            CREATE TABLE sends (
                channel TEXT NOT NULL,
                day TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (channel, day)
            )
            """
        )
        connection.execute(
            "INSERT INTO sends (channel, day, status, metadata) VALUES (?, ?, 'sent', ?)",
            ("news_image", "2026-03-30", '{"url":"https://example.com/a.png"}'),
        )

    store = StateStore(state_file)

    assert store.has_sent("news_image", "2026-03-30") is True
    with sqlite3.connect(state_file) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sends)").fetchall()}

    assert {"created_at", "updated_at"} <= columns


def test_complete_send_persists_metadata_in_sqlite_store(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")

    assert store.claim_send("oil_price", "2026-03-30") is True

    store.complete_send(
        "oil_price",
        "2026-03-30",
        {
            "content": "成品油价格按机制上调\n\n92号汽油 -- 7.12",
            "title": "油价调整",
            "page_url": "https://example.com/post",
        },
    )

    assert store.has_sent("oil_price", "2026-03-30") is True
    assert store.snapshot() == {
        "oil_price": {
            "2026-03-30": {
                "content": "成品油价格按机制上调\n\n92号汽油 -- 7.12",
                "title": "油价调整",
                "page_url": "https://example.com/post",
            }
        }
    }
