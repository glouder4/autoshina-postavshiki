"""
Оркестрация синхронизации: загрузка от всех активных поставщиков и сохранение в БД.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .config import load_suppliers_config
from .config_validate import ConfigValidationError, validate_suppliers_config
from .loader import LoadOutcome, LoadResult, load_products_from_url
from .storage import Storage
from .sync_state import SyncState, default_sync_state_path, save_sync_state

logger = logging.getLogger(__name__)


def _category_key(supplier_id: str, category: str) -> str:
    return f"{supplier_id}|{category}"


def run_sync(
    config_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
    config_dir: Optional[Path] = None,
    sync_state_path: Optional[Path] = None,
) -> None:
    """
    Загрузить XML от всех активных поставщиков и обновить БД.
    Неактивные поставщики: не загружаем, удаляем их товары из БД.

    При ошибках загрузки/парсинга категории предыдущее состояние категории в БД сохраняется.
    Upsert выполняется только при outcome SUCCESS (есть принятые товары).
    """
    cfg_path = config_path or Path(__file__).resolve().parent.parent / "config" / "suppliers.yaml"
    sync_state_path = sync_state_path or default_sync_state_path(
        Path(__file__).resolve().parent.parent
    )

    state = SyncState(config_valid=False, sync_finished_ok=False)

    try:
        cfg = load_suppliers_config(cfg_path)
        config_dir = config_dir or cfg_path.parent
        validate_suppliers_config(cfg, config_dir=config_dir)
        state.config_valid = True
        state.config_error = ""
    except ConfigValidationError as e:
        state.config_valid = False
        state.config_error = str(e)
        state.sync_error = str(e)
        save_sync_state(state, sync_state_path)
        logger.error("Ошибка валидации конфигурации: %s", e)
        raise
    except Exception as e:
        state.config_valid = False
        state.config_error = str(e)
        state.sync_error = str(e)
        save_sync_state(state, sync_state_path)
        logger.exception("Не удалось загрузить или проверить конфиг: %s", e)
        raise

    suppliers = cfg.get("suppliers", [])
    timeout = cfg.get("request_timeout_seconds", 60)
    project_root = Path(__file__).resolve().parent.parent
    cache_dir = Path(cfg.get("cache_dir", "data/cache"))
    if not cache_dir.is_absolute():
        cache_dir = project_root / cache_dir

    storage = Storage(db_path or "data/products.db")
    active_ids: list[str] = []
    state.had_category_load_errors = False

    _ERR_OUTCOMES = frozenset(
        {
            LoadOutcome.FETCH_ERROR,
            LoadOutcome.PARSE_ERROR,
            LoadOutcome.CONFIG_ERROR,
            LoadOutcome.PROCESS_ERROR,
        }
    )

    try:
        for s in suppliers:
            sid = s.get("id", "")
            name = s.get("name", sid)
            active = s.get("active", True)
            tires_url = s.get("tires_url")
            wheels_url = s.get("wheels_url")

            if not active:
                storage.delete_supplier_products(sid)
                logger.info("Поставщик %s отключён, товары удалены", name)
                continue

            active_ids.append(sid)
            combined = tires_url and tires_url == wheels_url
            cache_combined = cache_dir / f"{sid}.xml" if combined else None

            for category, url in [("tires", tires_url), ("wheels", wheels_url)]:
                ck = _category_key(sid, category)
                if not url:
                    logger.info(
                        "У поставщика %s отсутствует URL для категории %s, пропускаем",
                        name,
                        category,
                    )
                    state.categories[ck] = {
                        "outcome": "skipped_no_url",
                        "detail": "URL не задан",
                    }
                    continue

                result = load_products_from_url(
                    url=url,
                    supplier_id=sid,
                    supplier_name=name,
                    category=category,
                    timeout=timeout,
                    config_dir=config_dir,
                    cache_dir=cache_dir,
                    cache_file_override=cache_combined,
                    skip_fetch=combined and category == "wheels",
                )

                _record_load_result(state, ck, result)

                if result.outcome in _ERR_OUTCOMES:
                    state.had_category_load_errors = True

                if result.outcome == LoadOutcome.SUCCESS:
                    storage.upsert_products(
                        result.products,
                        supplier=name,
                        supplier_id=sid,
                        category=category,
                    )
                    logger.info(
                        "Обновлено %d товаров категории %s от %s",
                        len(result.products),
                        category,
                        name,
                    )
                elif result.outcome == LoadOutcome.EMPTY:
                    logger.warning(
                        "Категория %s у %s: %s — БД не меняем",
                        category,
                        name,
                        result.detail,
                    )
                else:
                    logger.error(
                        "Категория %s у %s: ошибка %s — %s — БД не меняем",
                        category,
                        name,
                        result.outcome.value,
                        result.detail,
                    )

        state.sync_finished_ok = not state.had_category_load_errors
        logger.info(
            "Синхронизация завершена. Активных поставщиков: %d",
            len(active_ids),
        )
    except Exception as e:
        state.sync_finished_ok = False
        state.sync_error = str(e)
        logger.exception("Синхронизация прервана: %s", e)
        raise
    finally:
        save_sync_state(state, sync_state_path)


def _record_load_result(state: SyncState, ck: str, result: LoadResult) -> None:
    entry = {
        "outcome": result.outcome.value,
        "detail": result.detail,
        "raw_items": result.raw_items,
        "accepted": result.accepted,
        "filtered_out": result.filtered_out,
    }
    if result.outcome == LoadOutcome.SUCCESS:
        entry["products_saved"] = len(result.products)
    state.categories[ck] = entry
