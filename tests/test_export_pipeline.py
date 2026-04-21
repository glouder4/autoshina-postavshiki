"""Интеграция export.get_export_products с storage и deduplicate."""
from __future__ import annotations

from src.export import compute_export_dedup_stats, get_export_products
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


def test_compute_export_dedup_stats_merged_two_suppliers(tmp_db_path):
    """Две одинаковые по ключу шины от разных поставщиков → merged_duplicate_rows.total == 1."""
    st = Storage(tmp_db_path)
    a = make_tire_product(supplier_id="s1", CML2_ARTICLE="A1", price=90.0)
    b = make_tire_product(supplier_id="s2", CML2_ARTICLE="B1", price=100.0)
    st.upsert_products([a], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([b], supplier="S2", supplier_id="s2", category="tires")
    stats = compute_export_dedup_stats(st, active_supplier_ids=["s1", "s2"])
    assert stats["before_deduplicate_rows"]["total"] == 2
    assert stats["after_deduplicate_rows"]["total"] == 1
    assert stats["merged_duplicate_rows"]["total"] == 1
