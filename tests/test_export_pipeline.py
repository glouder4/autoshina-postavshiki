"""Интеграция export.get_export_products с storage и deduplicate."""
from __future__ import annotations

from src.export import get_export_products
from src.storage import Storage
from tests.conftest import make_tire_product


def test_get_export_products_excludes_zero_stock(tmp_db_path):
    st = Storage(tmp_db_path)
    ok = make_tire_product(supplier_id="s1", CML2_ARTICLE="A", quantity=2)
    dead = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="B",
        quantity=0,
        MODEL_AVTOSHINY="Other",
        SHIRINA_PROFILYA="195",
    )
    st.upsert_products([ok, dead], supplier="S", supplier_id="s1", category="tires")
    out = get_export_products(st, active_supplier_ids=["s1"], require_stock=True)
    articles = {p.CML2_ARTICLE for p in out}
    assert "A" in articles
    assert "B" not in articles
