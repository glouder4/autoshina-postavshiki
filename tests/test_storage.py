"""Тесты Storage: category-scoped upsert, surrogate, фильтр поставщиков."""
from __future__ import annotations

import pytest

from src.models import Product
from src.storage import Storage
from tests.conftest import make_tire_product, make_wheel_product


def test_upsert_does_not_touch_other_category_same_supplier(tmp_db_path):
    """Обновление tires не удаляет wheels того же supplier_id."""
    st = Storage(tmp_db_path)
    tires = [
        make_tire_product(CML2_ARTICLE="T1"),
        make_tire_product(CML2_ARTICLE="T2"),
    ]
    wheels = [make_wheel_product(CML2_ARTICLE="W1")]
    st.upsert_products(tires, supplier="S", supplier_id="sup_a", category="tires")
    st.upsert_products(wheels, supplier="S", supplier_id="sup_a", category="wheels")

    st.upsert_products([make_tire_product(CML2_ARTICLE="T1")], supplier="S", supplier_id="sup_a", category="tires")

    ids = [p.CML2_ARTICLE for p in st.get_all_products()]
    assert "W1" in ids
    assert ids.count("T2") == 0
    assert "T1" in ids


def test_upsert_same_article_different_suppliers(tmp_db_path):
    """Одинаковый артикул у двух поставщиков — две строки."""
    st = Storage(tmp_db_path)
    st.upsert_products(
        [make_tire_product(supplier_id="a", CML2_ARTICLE="X")],
        supplier="A",
        supplier_id="a",
        category="tires",
    )
    st.upsert_products(
        [make_tire_product(supplier_id="b", supplier="B", CML2_ARTICLE="X")],
        supplier="B",
        supplier_id="b",
        category="tires",
    )
    rows = st.get_all_products()
    assert len(rows) == 2
    assert {p.supplier_id for p in rows} == {"a", "b"}


def test_stable_surrogate_ignores_price_quantity(tmp_db_path):
    st = Storage(tmp_db_path)
    p1 = make_tire_product(CML2_ARTICLE="", price=100, quantity=1)
    p2 = make_tire_product(CML2_ARTICLE="", price=999, quantity=99)
    assert st.stable_surrogate_article(p1) == st.stable_surrogate_article(p2)


def test_surrogate_changes_when_model_changes(tmp_db_path):
    st = Storage(tmp_db_path)
    p1 = make_tire_product(CML2_ARTICLE="", MODEL_AVTOSHINY="M1")
    p2 = make_tire_product(CML2_ARTICLE="", MODEL_AVTOSHINY="M2")
    assert st.stable_surrogate_article(p1) != st.stable_surrogate_article(p2)


def test_os_article_id_uses_supplier_id_and_article(tmp_db_path):
    st = Storage(tmp_db_path)
    p = make_tire_product(CML2_ARTICLE="ZZ")
    st.upsert_products([p], supplier="DisplayName", supplier_id="sid_x", category="tires")
    loaded = st.get_all_products(active_supplier_ids=["sid_x"])[0]
    assert loaded.OS_ARTICLE_ID == "os_article_sid_x_ZZ"


def test_upsert_aligns_os_supplier_text_with_config_supplier(tmp_db_path):
    """OS_SUPPLIER_TEXT в БД совпадает с supplier из конфига, а не с текстом из фида."""
    st = Storage(tmp_db_path)
    p = make_tire_product(
        supplier="stale",
        OS_SUPPLIER_TEXT="Feed supplier label",
    )
    st.upsert_products([p], supplier="Canonical Name", supplier_id="sid_x", category="tires")
    loaded = st.get_all_products(active_supplier_ids=["sid_x"])[0]
    assert loaded.supplier == "Canonical Name"
    assert loaded.OS_SUPPLIER_TEXT == "Canonical Name"


def test_get_all_products_none_vs_empty_list(tmp_db_path):
    st = Storage(tmp_db_path)
    st.upsert_products([make_tire_product()], supplier="S", supplier_id="s1", category="tires")
    assert len(st.get_all_products(None)) == 1
    assert st.get_all_products([]) == []
    assert len(st.get_all_products(["s1"])) == 1


def test_wrong_category_in_batch_raises(tmp_db_path):
    st = Storage(tmp_db_path)
    with pytest.raises(ValueError, match="expects category=wheels"):
        st.upsert_products(
            [make_tire_product()],
            supplier="S",
            supplier_id="x",
            category="wheels",
        )


def test_empty_upsert_list_noop(tmp_db_path):
    """Пустой список не вызывает удаление существующих строк."""
    st = Storage(tmp_db_path)
    st.upsert_products([make_tire_product(CML2_ARTICLE="A")], supplier="S", supplier_id="x", category="tires")
    st.upsert_products([], supplier="S", supplier_id="x", category="tires")
    assert len(st.get_all_products()) == 1


def test_get_product_by_id(tmp_db_path):
    st = Storage(tmp_db_path)
    st.upsert_products([make_tire_product(CML2_ARTICLE="Z9")], supplier="S", supplier_id="x", category="tires")
    loaded = st.get_all_products()[0]
    assert loaded.id is not None
    found = st.get_product_by_id(loaded.id)
    assert found is not None
    assert found.CML2_ARTICLE == "Z9"
    assert st.get_product_by_id(99999) is None


def test_search_products_by_article_and_model(tmp_db_path):
    st = Storage(tmp_db_path)
    st.upsert_products(
        [
            make_tire_product(CML2_ARTICLE="ABC-123", MODEL_AVTOSHINY="WinterContact"),
            make_tire_product(CML2_ARTICLE="ZZ", MODEL_AVTOSHINY="Other"),
        ],
        supplier="S",
        supplier_id="x",
        category="tires",
    )
    by_art = st.search_products("abc")
    assert len(by_art) == 1
    assert by_art[0].CML2_ARTICLE == "ABC-123"
    by_model = st.search_products("winter")
    assert len(by_model) == 1
    assert by_model[0].MODEL_AVTOSHINY == "WinterContact"


def test_search_products_filter_category_supplier(tmp_db_path):
    st = Storage(tmp_db_path)
    st.upsert_products(
        [make_tire_product(supplier_id="a", CML2_ARTICLE="T-A")],
        supplier="A",
        supplier_id="a",
        category="tires",
    )
    st.upsert_products(
        [make_wheel_product(supplier_id="b", CML2_ARTICLE="W-B", MODEL_DISKA="RimX")],
        supplier="B",
        supplier_id="b",
        category="wheels",
    )
    assert len(st.search_products("T-A", category="tires")) == 1
    assert len(st.search_products("T-A", category="wheels")) == 0
    assert len(st.search_products("Rim", supplier_id="b")) == 1
    assert st.search_products("") == []


def test_find_by_article_exact_before_partial(tmp_db_path):
    st = Storage(tmp_db_path)
    st.upsert_products(
        [
            make_tire_product(CML2_ARTICLE="12345", MODEL_AVTOSHINY="A"),
            make_tire_product(CML2_ARTICLE="123456", MODEL_AVTOSHINY="B"),
        ],
        supplier="S",
        supplier_id="x",
        category="tires",
    )
    exact = st.find_by_article("12345")
    assert len(exact) == 1
    assert exact[0].CML2_ARTICLE == "12345"
