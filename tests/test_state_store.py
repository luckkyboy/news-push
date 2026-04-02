from pathlib import Path

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


def test_mark_sent_preserves_existing_state_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    store.mark_sent("news_image", "2026-03-30", {"url": "https://example.com/a.png"})

    def fail_replace(self: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError):
        store.mark_sent("oil_price", "2026-03-30", {"title": "油价调整"})

    reloaded = StateStore(state_file)
    assert reloaded.snapshot() == {
        "news_image": {
            "2026-03-30": {"url": "https://example.com/a.png"},
        }
    }
