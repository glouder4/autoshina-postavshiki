"""Загрузка конфигурации."""
from pathlib import Path
from typing import Optional

import yaml


def load_suppliers_config(config_path: Optional[Path] = None) -> dict:
    """Загрузить config/suppliers.yaml."""
    path = config_path or Path(__file__).resolve().parent.parent / "config" / "suppliers.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
