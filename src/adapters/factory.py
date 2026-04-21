"""
Фабрика адаптеров по конфигу YAML.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from .base import BaseAdapter

logger = logging.getLogger(__name__)

def _adapters_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "adapters"


def load_adapter_config(
    supplier_id: str, config_dir: Optional[Path] = None
) -> Optional[dict]:
    """Загрузить конфиг адаптера из YAML. config_dir — путь к config/ или к config/adapters/."""
    if config_dir:
        adapters = config_dir / "adapters" if (config_dir / "adapters").is_dir() else config_dir
    else:
        adapters = _adapters_dir()
    path = adapters / f"{supplier_id}.yaml"
    if not path.exists():
        logger.error("Конфиг адаптера не найден: %s", path)
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_adapter(
    supplier_id: str,
    category: str,
    config_dir: Optional[Path] = None,
) -> Optional[BaseAdapter]:
    """
    Создать адаптер для поставщика и категории.
    category: "tires" | "wheels"
    """
    cfg = load_adapter_config(supplier_id, config_dir)
    if not cfg:
        return None
    section = cfg.get(category)
    if not section:
        logger.error("Секция %s не найдена в адаптере %s", category, supplier_id)
        return None
    mapping = section.get("field_mapping", {})
    transforms = section.get("value_transforms", {})
    quantity_sum_fields = section.get("quantity_sum_fields")
    price_min_fields = section.get("price_min_fields")
    price_max_rozn_from_quantity = section.get("price_max_rozn_from_quantity", False)
    return BaseAdapter(
        supplier_id=cfg.get("supplier_id", supplier_id),
        supplier_name=cfg.get("supplier_name", supplier_id),
        field_mapping=mapping,
        value_transforms=transforms,
        quantity_sum_fields=quantity_sum_fields,
        price_min_fields=price_min_fields,
        price_max_rozn_from_quantity=price_max_rozn_from_quantity,
    )
