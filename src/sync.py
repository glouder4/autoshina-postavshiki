"""
Оркестрация синхронизации: загрузка от всех активных поставщиков и сохранение в БД.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from .loader import load_products_from_url
from .storage import Storage

logger = logging.getLogger(__name__)


def load_suppliers_config(config_path: Optional[Path] = None) -> dict:
    """Загрузить config/suppliers.yaml."""
    path = config_path or Path(__file__).resolve().parent.parent / "config" / "suppliers.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_sync(
    config_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
    config_dir: Optional[Path] = None,
) -> None:
    """
    Загрузить XML от всех активных поставщиков и обновить БД.
    Неактивные поставщики: не загружаем, удаляем их товары из БД.
    """
    cfg = load_suppliers_config(config_path)
    suppliers = cfg.get("suppliers", [])
    timeout = cfg.get("request_timeout_seconds", 60)
    config_dir = config_dir or Path(__file__).resolve().parent.parent / "config"
    project_root = Path(__file__).resolve().parent.parent
    cache_dir = Path(cfg.get("cache_dir", "data/cache"))
    if not cache_dir.is_absolute():
        cache_dir = project_root / cache_dir

    storage = Storage(db_path or "data/products.db")
    active_ids: list[str] = []

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

        active_ids.append(name)
        all_products: list = []
        tires_url = s.get("tires_url")
        wheels_url = s.get("wheels_url")
        combined = tires_url and tires_url == wheels_url
        cache_combined = cache_dir / f"{sid}.xml" if combined else None

        for category, url in [("tires", tires_url), ("wheels", wheels_url)]:
            if not url:
                continue
            products = load_products_from_url(
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
            all_products.extend(products)

        if all_products:
            storage.upsert_products(all_products, supplier=name, supplier_id=sid)
            logger.info("Обновлено %d товаров от %s", len(all_products), name)
        else:
            logger.warning("Нет товаров от %s (возможно ошибка загрузки)", name)

    logger.info("Синхронизация завершена. Активных поставщиков: %d", len(active_ids))
