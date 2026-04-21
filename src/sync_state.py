"""
Сохранение состояния последней синхронизации для health/readiness и диагностики.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SyncState:
    updated_at: str = ""
    config_valid: bool = True
    config_error: str = ""
    sync_finished_ok: bool = False
    sync_error: str = ""
    # had_category_load_errors: True — была FETCH/PARSE/CONFIG/PROCESS по категории
    had_category_load_errors: bool = False
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Сводка загрузки и дедупликации для выгрузки (после успешного прохода по БД)
    export_stats: dict[str, Any] = field(default_factory=dict)
    # Поставщики с active: true на момент этого run_sync
    active_supplier_ids: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "config_valid": self.config_valid,
            "config_error": self.config_error,
            "sync_finished_ok": self.sync_finished_ok,
            "sync_error": self.sync_error,
            "had_category_load_errors": self.had_category_load_errors,
            "categories": self.categories,
            "export_stats": self.export_stats,
            "active_supplier_ids": self.active_supplier_ids,
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> SyncState:
        raw_ids = d.get("active_supplier_ids")
        if isinstance(raw_ids, (list, tuple)):
            active_ids = [str(x) for x in raw_ids]
        else:
            active_ids = []
        return cls(
            updated_at=d.get("updated_at", ""),
            config_valid=bool(d.get("config_valid", True)),
            config_error=d.get("config_error", ""),
            sync_finished_ok=bool(d.get("sync_finished_ok", False)),
            sync_error=d.get("sync_error", ""),
            had_category_load_errors=bool(d.get("had_category_load_errors", False)),
            categories=dict(d.get("categories") or {}),
            export_stats=dict(d.get("export_stats") or {}),
            active_supplier_ids=active_ids,
        )


def default_sync_state_path(project_root: Optional[Path] = None) -> Path:
    root = project_root or Path(__file__).resolve().parent.parent
    return root / "data" / "sync_state.json"


def load_sync_state(path: Optional[Path] = None) -> Optional[SyncState]:
    p = path or default_sync_state_path()
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return SyncState.from_json_dict(json.load(f))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Не удалось прочитать sync_state %s: %s", p, e)
        return None


def save_sync_state(
    state: SyncState,
    path: Optional[Path] = None,
) -> None:
    p = path or default_sync_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = state.updated_at or _utc_now_iso()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state.to_json_dict(), f, ensure_ascii=False, indent=2)
