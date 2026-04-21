"""Интеграционные тесты run_sync с моками загрузчика."""
from __future__ import annotations

from pathlib import Path

from src.loader import LoadOutcome, LoadResult
from src.sync import run_sync
from src.storage import Storage
from tests.conftest import make_tire_product, make_wheel_product


def test_fetch_error_preserves_existing_category_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ошибка загрузки категории не удаляет уже сохранённые строки этой категории."""
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    (adapters / "s1.yaml").write_text(
        """
supplier_id: s1
supplier_name: S
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
    cfg_path = cfg_dir / "suppliers.yaml"
    cfg_path.write_text(
        """
suppliers:
  - id: s1
    name: Shop
    active: true
    tires_url: "http://example.com/t.xml"
    wheels_url: "http://example.com/w.xml"
""",
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite"

    st = Storage(db_path)
    existing = make_tire_product(supplier_id="s1", CML2_ARTICLE="KEEP")
    st.upsert_products([existing], supplier="Shop", supplier_id="s1", category="tires")

    def fake_load(**kwargs):
        category = kwargs["category"]
        if category == "tires":
            return LoadResult(outcome=LoadOutcome.FETCH_ERROR, detail="offline")
        return LoadResult(
            outcome=LoadOutcome.SUCCESS,
            products=[make_wheel_product(CML2_ARTICLE="W1")],
            accepted=1,
            raw_items=1,
        )

    monkeypatch.setattr("src.sync.load_products_from_url", fake_load)

    run_sync(config_path=cfg_path, db_path=db_path, config_dir=cfg_dir)

    rows = Storage(db_path).get_all_products()
    tires = [p for p in rows if p.category == "tires"]
    wheels = [p for p in rows if p.category == "wheels"]
    assert len(tires) == 1 and tires[0].CML2_ARTICLE == "KEEP"
    assert len(wheels) == 1


def test_active_false_deletes_supplier_products(monkeypatch, tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    adapters = cfg_dir / "adapters"
    adapters.mkdir(parents=True)
    for sid in ("keep", "gone"):
        (adapters / f"{sid}.yaml").write_text(
            f"""
supplier_id: {sid}
supplier_name: {sid}
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
    cfg_path = cfg_dir / "suppliers.yaml"
    cfg_path.write_text(
        """
suppliers:
  - id: gone
    name: Off
    active: false
  - id: keep
    name: On
    active: true
    tires_url: "http://example.com/t.xml"
""",
        encoding="utf-8",
    )
    db_path = tmp_path / "db2.sqlite"
    st = Storage(db_path)
    st.upsert_products(
        [make_tire_product(supplier_id="gone", CML2_ARTICLE="G")],
        supplier="Off",
        supplier_id="gone",
        category="tires",
    )
    st.upsert_products(
        [make_tire_product(supplier_id="keep", CML2_ARTICLE="K")],
        supplier="On",
        supplier_id="keep",
        category="tires",
    )

    monkeypatch.setattr(
        "src.sync.load_products_from_url",
        lambda **kw: LoadResult(
            outcome=LoadOutcome.SUCCESS,
            products=[make_tire_product(supplier_id="keep", CML2_ARTICLE="K2")],
            accepted=1,
            raw_items=1,
        ),
    )

    run_sync(config_path=cfg_path, db_path=db_path, config_dir=cfg_dir)

    ids = {p.supplier_id for p in Storage(db_path).get_all_products()}
    assert "gone" not in ids
    assert "keep" in ids
