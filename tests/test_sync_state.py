"""Тесты сохранения состояния синхронизации."""
from __future__ import annotations

import json

from src.sync_state import SyncState, load_sync_state, save_sync_state


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    st = SyncState(
        config_valid=True,
        sync_finished_ok=True,
        had_category_load_errors=False,
        categories={"supplier_1|tires": {"outcome": "success", "products_saved": 3}},
        active_supplier_ids=["supplier_1", "supplier_2"],
    )
    st.updated_at = "2026-01-01T00:00:00+00:00"
    save_sync_state(st, p)
    loaded = load_sync_state(p)
    assert loaded is not None
    assert loaded.config_valid is True
    assert loaded.sync_finished_ok is True
    assert loaded.had_category_load_errors is False
    assert loaded.categories["supplier_1|tires"]["outcome"] == "success"
    assert loaded.active_supplier_ids == ["supplier_1", "supplier_2"]


def test_save_sets_updated_at_when_empty(tmp_path):
    p = tmp_path / "x.json"
    st = SyncState()
    st.updated_at = ""
    save_sync_state(st, p)
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert data["updated_at"]


def test_load_missing_returns_none(tmp_path):
    assert load_sync_state(tmp_path / "nope.json") is None


def test_load_corrupt_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_sync_state(p) is None


def test_save_preserves_explicit_updated_at(tmp_path):
    p = tmp_path / "st.json"
    st = SyncState(updated_at="2099-01-01T00:00:00+00:00")
    save_sync_state(st, p)
    loaded = load_sync_state(p)
    assert loaded.updated_at.startswith("2099-01-01")
