"""Тесты валидации конфигурации."""
from pathlib import Path

import pytest

from src.config_validate import ConfigValidationError, validate_suppliers_config


def test_validate_suppliers_minimal_ok(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "supplier_x.yaml").write_text(
        """
supplier_id: supplier_x
supplier_name: Test
item_xpath_tires: "//t"
item_xpath_wheels: "//w"
tires:
  field_mapping:
    NAME: n
wheels:
  field_mapping:
    NAME: n
""",
        encoding="utf-8",
    )
    cfg = {
        "suppliers": [
            {
                "id": "supplier_x",
                "name": "Test",
                "active": True,
                "tires_url": "http://example.com/t.xml",
                "wheels_url": "http://example.com/w.xml",
            }
        ]
    }
    validate_suppliers_config(cfg, config_dir=cfg_dir)


def test_validate_missing_adapter_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    (cfg_dir / "adapters").mkdir(parents=True)
    cfg = {
        "suppliers": [
            {
                "id": "missing",
                "name": "X",
                "active": True,
                "tires_url": "http://example.com/t.xml",
            }
        ]
    }
    with pytest.raises(ConfigValidationError):
        validate_suppliers_config(cfg, config_dir=cfg_dir)


def test_root_not_dict_raises():
    with pytest.raises(ConfigValidationError, match="объектом YAML"):
        validate_suppliers_config([], config_dir=Path("."))


def test_missing_suppliers_key_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError, match="suppliers"):
        validate_suppliers_config({}, config_dir=tmp_path)


def test_suppliers_not_list_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError, match="списком"):
        validate_suppliers_config({"suppliers": {}}, config_dir=tmp_path)


def test_supplier_entry_not_object_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError, match="объектом"):
        validate_suppliers_config({"suppliers": ["x"]}, config_dir=tmp_path)


def test_missing_id_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError, match="id"):
        validate_suppliers_config({"suppliers": [{"name": "n"}]}, config_dir=tmp_path)


def test_inactive_skips_adapter_requirement(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    validate_suppliers_config(
        {
            "suppliers": [
                {"id": "off", "name": "Off", "active": False, "tires_url": "http://x"}
            ]
        },
        config_dir=cfg_dir,
    )


def test_tires_url_without_section_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "bad.yaml").write_text(
        "supplier_id: bad\nitem_xpath_tires: '//t'\nitem_xpath_wheels: '//w'\n",
        encoding="utf-8",
    )
    cfg = {
        "suppliers": [
            {
                "id": "bad",
                "name": "B",
                "active": True,
                "tires_url": "http://example.com/t.xml",
            }
        ]
    }
    with pytest.raises(ConfigValidationError, match="секция"):
        validate_suppliers_config(cfg, config_dir=cfg_dir)


def test_empty_field_mapping_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "bad2.yaml").write_text(
        """
supplier_id: bad2
supplier_name: B
item_xpath_tires: "//t"
item_xpath_wheels: "//w"
tires:
  field_mapping: {}
wheels:
  field_mapping:
    NAME: n
""",
        encoding="utf-8",
    )
    cfg = {
        "suppliers": [
            {
                "id": "bad2",
                "name": "B",
                "active": True,
                "tires_url": "http://example.com/t.xml",
                "wheels_url": "http://example.com/w.xml",
            }
        ]
    }
    with pytest.raises(ConfigValidationError, match="field_mapping"):
        validate_suppliers_config(cfg, config_dir=cfg_dir)


def test_missing_item_xpath_tires_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "bad3.yaml").write_text(
        """
supplier_id: bad3
supplier_name: B
item_xpath_wheels: "//w"
wheels:
  field_mapping:
    NAME: n
tires:
  field_mapping:
    NAME: n
""",
        encoding="utf-8",
    )
    cfg = {
        "suppliers": [
            {
                "id": "bad3",
                "name": "B",
                "active": True,
                "tires_url": "http://example.com/t.xml",
                "wheels_url": "http://example.com/w.xml",
            }
        ]
    }
    with pytest.raises(ConfigValidationError, match="item_xpath_tires"):
        validate_suppliers_config(cfg, config_dir=cfg_dir)


def test_adapter_yaml_root_not_object_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "notobj.yaml").write_text("- x", encoding="utf-8")
    cfg = {
        "suppliers": [
            {
                "id": "notobj",
                "name": "N",
                "active": True,
                "tires_url": "http://example.com/t.xml",
                "wheels_url": "http://example.com/w.xml",
            }
        ]
    }
    with pytest.raises(ConfigValidationError, match="объект YAML"):
        validate_suppliers_config(cfg, config_dir=cfg_dir)
