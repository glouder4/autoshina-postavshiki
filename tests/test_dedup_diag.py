"""Тесты src/dedup_diag: классификация и воронка."""
from __future__ import annotations

from src.dedup_diag import (
    STATUS_DEDUP_GROUP_DROPPED,
    STATUS_DEDUP_LOSER,
    STATUS_EXPORT_WINNER,
    STATUS_INACTIVE_SUPPLIER,
    STATUS_PRICE_QTY_FILTER,
    STATUS_UNIQUE_IN_EXPORT,
    build_export_pipeline_context,
    classify_product_in_export_pipeline,
    compute_supplier_funnel,
    get_group_diag,
    get_product_diag,
    get_sync_category_ingestion,
    list_supplier_products_by_status,
    lookup_by_article,
    status_label_ru,
)
from src.deduplicator import deduplicate
from src.export import get_export_products
from src.storage import Storage
from tests.conftest import make_tire_product, make_wheel_product


def _same_specs(**kw):
    base = dict(
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        PROIZVODITEL="Bridgestone",
        MODEL_AVTOSHINY="T001",
        SEZONNOST="Летняя",
    )
    base.update(kw)
    return make_tire_product(**base)


def test_classify_export_winner_and_loser(tmp_db_path):
    st = Storage(tmp_db_path)
    cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="A1", price=90, quantity=2)
    costly = _same_specs(supplier_id="s2", CML2_ARTICLE="B1", price=200, quantity=5)
    st.upsert_products([cheap], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([costly], supplier="S2", supplier_id="s2", category="tires")
    all_p = st.get_all_products()
    by_art = {p.CML2_ARTICLE: p for p in all_p}
    active = ["s1", "s2"]
    assert classify_product_in_export_pipeline(by_art["A1"], st, active) == STATUS_EXPORT_WINNER
    assert classify_product_in_export_pipeline(by_art["B1"], st, active) == STATUS_DEDUP_LOSER


def test_classify_unique_in_export(tmp_db_path):
    st = Storage(tmp_db_path)
    p = _same_specs(
        supplier_id="s1",
        CML2_ARTICLE="SOLO",
        SHIRINA_PROFILYA="195",
    )
    st.upsert_products([p], supplier="S", supplier_id="s1", category="tires")
    loaded = st.get_all_products()[0]
    assert classify_product_in_export_pipeline(loaded, st, ["s1"]) == STATUS_UNIQUE_IN_EXPORT


def test_classify_inactive_supplier(tmp_db_path):
    st = Storage(tmp_db_path)
    p = _same_specs(supplier_id="off", CML2_ARTICLE="X")
    st.upsert_products([p], supplier="Off", supplier_id="off", category="tires")
    loaded = st.get_all_products()[0]
    assert classify_product_in_export_pipeline(loaded, st, ["s1"]) == STATUS_INACTIVE_SUPPLIER


def test_classify_dedup_group_dropped_no_stock(tmp_db_path):
    st = Storage(tmp_db_path)
    a = _same_specs(supplier_id="s1", CML2_ARTICLE="A", quantity=0, price=50)
    b = _same_specs(supplier_id="s2", CML2_ARTICLE="B", quantity=0, price=99)
    st.upsert_products([a], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([b], supplier="S2", supplier_id="s2", category="tires")
    for p in st.get_all_products():
        assert classify_product_in_export_pipeline(p, st, ["s1", "s2"]) == STATUS_DEDUP_GROUP_DROPPED


def test_classify_price_qty_filter_winner_zero_price(tmp_db_path):
    """Победитель дедупа с остатком, но price<=0 — отсекается на финальном фильтре."""
    st = Storage(tmp_db_path)
    ok = _same_specs(supplier_id="s1", CML2_ARTICLE="OK", quantity=5, price=0)
    st.upsert_products([ok], supplier="S", supplier_id="s1", category="tires")
    loaded = st.get_all_products()[0]
    assert classify_product_in_export_pipeline(loaded, st, ["s1"]) == STATUS_PRICE_QTY_FILTER


def _wheel_dup_specs(**kw):
    base = dict(
        PROIZVODITEL="X",
        MODEL_DISKA="Z",
        SHIRINA_DISKA="7.5",
        POSADOCHNYY_DIAMETR_DISKA="17",
        COUNT_OTVERSTIY="5",
        MEZHBOLTOVOE_RASSTOYANIE="112",
        VYLET_DISKA="40",
        DIAMETR_STUPITSY="60",
        WHEEL_TYPE="литой",
    )
    base.update(kw)
    return make_wheel_product(**base)


def test_group_diag_no_cross_category_collision(tmp_db_path):
    """tires:g:0 и wheels:g:0 не перезаписывают друг друга в groups_by_key."""
    st = Storage(tmp_db_path)
    tire_cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="T1", price=90, quantity=2)
    tire_costly = _same_specs(supplier_id="s2", CML2_ARTICLE="T2", price=200, quantity=5)
    wheel_cheap = _wheel_dup_specs(supplier_id="s1", CML2_ARTICLE="W1", price=100, quantity=2)
    wheel_costly = _wheel_dup_specs(supplier_id="s2", CML2_ARTICLE="W2", price=250, quantity=1)
    st.upsert_products([tire_cheap], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([tire_costly], supplier="S2", supplier_id="s2", category="tires")
    st.upsert_products([wheel_cheap], supplier="S1", supplier_id="s1", category="wheels")
    st.upsert_products([wheel_costly], supplier="S2", supplier_id="s2", category="wheels")

    ctx = build_export_pipeline_context(st, active_supplier_ids=["s1", "s2"])
    assert "tires:g:0" in ctx["groups_by_key"]
    assert "wheels:g:0" in ctx["groups_by_key"]
    assert len(ctx["groups_by_key"]["tires:g:0"]) == 2
    assert len(ctx["groups_by_key"]["wheels:g:0"]) == 2

    by_cat = {}
    for p in st.get_all_products():
        by_cat.setdefault(p.category, []).append(p)
    tire_id = next(p.id for p in by_cat["tires"] if p.CML2_ARTICLE == "T1")
    wheel_id = next(p.id for p in by_cat["wheels"] if p.CML2_ARTICLE == "W1")

    assert ctx["product_group_key"][tire_id] == "tires:g:0"
    assert ctx["product_group_key"][wheel_id] == "wheels:g:0"

    tire_grp = get_group_diag(st, tire_id, active_supplier_ids=["s1", "s2"])
    wheel_grp = get_group_diag(st, wheel_id, active_supplier_ids=["s1", "s2"])
    assert tire_grp["group_key"] == "tires:g:0"
    assert wheel_grp["group_key"] == "wheels:g:0"
    assert tire_grp["size"] == 2
    assert wheel_grp["size"] == 2


def test_diag_winner_in_export_matches_deduplicate(tmp_db_path):
    """Победитель diag in_export совпадает с deduplicate/get_export_products."""
    st = Storage(tmp_db_path)
    cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="A1", price=90, quantity=2)
    costly = _same_specs(supplier_id="s2", CML2_ARTICLE="B1", price=200, quantity=5)
    st.upsert_products([cheap, costly], supplier="S", supplier_id="s1", category="tires")
    active = ["s1", "s2"]
    by_art = {p.CML2_ARTICLE: p for p in st.get_all_products()}

    export_ids = {int(p.id) for p in get_export_products(st, active_supplier_ids=active)}
    dedup_ids = {int(p.id) for p in deduplicate(st.get_all_products(), active_supplier_ids=active)}
    assert export_ids == dedup_ids

    winner_diag = get_product_diag(st, int(by_art["A1"].id), active_supplier_ids=active)
    loser_diag = get_product_diag(st, int(by_art["B1"].id), active_supplier_ids=active)
    assert winner_diag["in_export"] is True
    assert loser_diag["in_export"] is False
    assert winner_diag["export_status"] == STATUS_EXPORT_WINNER
    assert loser_diag["export_status"] == STATUS_DEDUP_LOSER


def test_supplier_funnel_counts(tmp_db_path):
    st = Storage(tmp_db_path)
    cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="A1", price=90, quantity=2)
    costly = _same_specs(supplier_id="s2", CML2_ARTICLE="B1", price=200, quantity=5)
    solo = _same_specs(
        supplier_id="s1",
        CML2_ARTICLE="Solo",
        SHIRINA_PROFILYA="195",
        price=80,
        quantity=1,
    )
    st.upsert_products([cheap, solo], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([costly], supplier="S2", supplier_id="s2", category="tires")
    funnel = compute_supplier_funnel(st, "s1", "tires", active_supplier_ids=["s1", "s2"])
    assert funnel["rows_in_db"] == 2
    assert funnel["status_counts"][STATUS_EXPORT_WINNER] == 1
    assert funnel["status_counts"][STATUS_UNIQUE_IN_EXPORT] == 1
    assert funnel["in_export"] == 2
    assert "export_dedup_stats" in funnel


def test_status_label_ru():
    assert "дедуп" in status_label_ru(STATUS_DEDUP_LOSER).lower()
    assert status_label_ru(STATUS_EXPORT_WINNER)


def test_list_supplier_products_by_status_loser(tmp_db_path):
    st = Storage(tmp_db_path)
    cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="A1", price=90, quantity=2)
    costly = _same_specs(supplier_id="s2", CML2_ARTICLE="B1", price=200, quantity=5)
    st.upsert_products([cheap], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([costly], supplier="S2", supplier_id="s2", category="tires")
    losers = list_supplier_products_by_status(
        st, "s2", "tires", status=STATUS_DEDUP_LOSER, active_supplier_ids=["s1", "s2"]
    )
    assert losers["total"] == 1
    assert losers["items"][0]["export_status"] == STATUS_DEDUP_LOSER
    assert losers["items"][0]["export_status_label"]


def test_get_sync_category_ingestion(tmp_path):
    sync_file = tmp_path / "sync_state.json"
    sync_file.write_text(
        '{"updated_at":"2026-01-01","categories":{"supplier_3|tires":'
        '{"outcome":"success","raw_items":65543,"accepted":100,"filtered_out":65443,'
        '"products_saved":100}}}',
        encoding="utf-8",
    )
    ing = get_sync_category_ingestion("supplier_3", "tires", sync_file)
    assert ing["raw_items_in_feed"] == 65543
    assert ing["filtered_out_at_load"] == 65443


def test_lookup_by_article_shows_export_winner_and_group(tmp_db_path):
    st = Storage(tmp_db_path)
    cheap = _same_specs(supplier_id="s1", CML2_ARTICLE="WIN-001", price=90, quantity=2)
    costly = _same_specs(supplier_id="s2", CML2_ARTICLE="LOSE-001", price=200, quantity=5)
    st.upsert_products([cheap], supplier="S1", supplier_id="s1", category="tires")
    st.upsert_products([costly], supplier="S2", supplier_id="s2", category="tires")

    data = lookup_by_article(st, "LOSE-001", active_supplier_ids=["s1", "s2"])
    assert data["found"] is True
    assert len(data["groups"]) == 1
    grp = data["groups"][0]
    assert grp["export_winner"]["CML2_ARTICLE"] == "WIN-001"
    assert grp["export_winner"]["supplier_id"] == "s1"
    assert len(grp["members"]) == 2
    loser = next(m for m in grp["members"] if m["CML2_ARTICLE"] == "LOSE-001")
    assert loser["is_queried_article"] is True
    assert loser["export_status"] == STATUS_DEDUP_LOSER
