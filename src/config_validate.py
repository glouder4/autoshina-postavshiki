"""
Валидация suppliers.yaml и YAML адаптеров до загрузки фидов.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

REQUIRED_SUPPLIER_KEYS = ("id", "name")


class ConfigValidationError(ValueError):
    """Ошибка валидации конфигурации с понятным сообщением."""

    pass


def validate_suppliers_config(cfg: dict[str, Any], *, config_dir: Path) -> None:
    """
    Проверить структуру сводного конфига и наличие адаптеров для активных поставщиков.
    """
    if not isinstance(cfg, dict):
        raise ConfigValidationError("Корень suppliers.yaml должен быть объектом YAML")

    suppliers = cfg.get("suppliers")
    if suppliers is None:
        raise ConfigValidationError("Отсутствует ключ suppliers")
    if not isinstance(suppliers, list):
        raise ConfigValidationError("suppliers должен быть списком")

    for i, s in enumerate(suppliers):
        if not isinstance(s, dict):
            raise ConfigValidationError(f"suppliers[{i}] должен быть объектом")
        for key in REQUIRED_SUPPLIER_KEYS:
            if key not in s or not str(s.get(key, "")).strip():
                raise ConfigValidationError(
                    f"Поставщик #{i}: обязательное поле '{key}' пустое или отсутствует"
                )
        sid = str(s["id"]).strip()
        active = bool(s.get("active", True))
        if not active:
            continue

        adapter_path = _adapter_yaml_path(config_dir, sid)
        if not adapter_path.exists():
            raise ConfigValidationError(
                f"Активный поставщик {sid}: не найден файл адаптера {adapter_path.name}"
            )
        raw = _load_yaml_file(adapter_path)
        _validate_adapter_structure(sid, raw, s)


def _adapter_yaml_path(config_dir: Path, supplier_id: str) -> Path:
    adapters = config_dir / "adapters"
    if not adapters.is_dir():
        adapters = config_dir
    return adapters / f"{supplier_id}.yaml"


def _load_yaml_file(path: Path) -> dict[str, Any]:
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigValidationError(f"{path.name}: ожидается объект YAML в корне")
    return data


def _validate_adapter_structure(
    supplier_id: str,
    raw: dict[str, Any],
    supplier_entry: dict[str, Any],
) -> None:
    cfg_sid = str(raw.get("supplier_id", "")).strip()
    if cfg_sid and cfg_sid != supplier_id:
        logger.warning(
            "supplier_id в YAML (%s) не совпадает с id в suppliers.yaml (%s)",
            cfg_sid,
            supplier_id,
        )

    for cat in ("tires", "wheels"):
        url_key = f"{cat}_url"
        url = supplier_entry.get(url_key)
        if not url:
            continue
        section = raw.get(cat)
        if not isinstance(section, dict):
            raise ConfigValidationError(
                f"{supplier_id}: для URL {cat} нужна секция '{cat}' в YAML адаптера"
            )
        fm = section.get("field_mapping")
        if not isinstance(fm, dict) or not fm:
            raise ConfigValidationError(
                f"{supplier_id}: секция {cat}.field_mapping должна быть непустым объектом"
            )

    xpath_tires = raw.get("item_xpath_tires")
    xpath_wheels = raw.get("item_xpath_wheels")
    if supplier_entry.get("tires_url") and not (
        isinstance(xpath_tires, str) and xpath_tires.strip()
    ):
        raise ConfigValidationError(
            f"{supplier_id}: задан tires_url, но не задан непустой item_xpath_tires"
        )
    if supplier_entry.get("wheels_url") and not (
        isinstance(xpath_wheels, str) and xpath_wheels.strip()
    ):
        raise ConfigValidationError(
            f"{supplier_id}: задан wheels_url, но не задан непустой item_xpath_wheels"
        )


def validate_all_configs(
    config_path: Optional[Path] = None,
) -> Path:
    """
    Загрузить suppliers.yaml и выполнить полную валидацию.
    Возвращает путь к каталогу config/.
    """
    from .config import load_suppliers_config

    path = config_path or Path(__file__).resolve().parent.parent / "config" / "suppliers.yaml"
    cfg = load_suppliers_config(path)
    config_dir = path.parent
    validate_suppliers_config(cfg, config_dir=config_dir)
    return config_dir
