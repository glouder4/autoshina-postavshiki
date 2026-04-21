"""
а) Выявление дублей.
б) Объединённый набор из 2+ поставщиков (как после совместной выгрузки в БД).
в) Дедупликация после скрещивания: один победитель на группу, уникальные позиции сохраняются.

Без сети: фабрики Product + локальный SQLite для интеграции с export pipeline.
"""
from __future__ import annotations

from src.deduplicator import deduplicate, group_duplicates
from src.export import get_export_products
from src.storage import Storage
from tests.conftest import make_tire_product, make_wheel_product


def _tire_same_specs_template(**overrides):
    """Одинаковые характеристики для ключа дедупликации шин."""
    base = dict(
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        PROIZVODITEL="Bridgestone",
        MODEL_AVTOSHINY="T001",
        SEZONNOST="Летняя",
        MORE_PHOTO="https://example.com/a.jpg",
    )
    base.update(overrides)
    return make_tire_product(**base)


# --- (а) выявление дублей среди одного объединённого списка ---


def test_duplicate_two_suppliers_same_specs_cheapest_with_stock_wins():
    """Два поставщика, одинаковые dedup-поля: остаётся более дешёвая позиция с остатком."""
    cheap = _tire_same_specs_template(
        supplier_id="sup_a",
        CML2_ARTICLE="A1",
        price=90,
        quantity=3,
    )
    costly = _tire_same_specs_template(
        supplier_id="sup_b",
        CML2_ARTICLE="B1",
        price=200,
        quantity=5,
    )
    merged = [cheap, costly]
    out = deduplicate(merged, active_supplier_ids=["sup_a", "sup_b"])
    assert len(out) == 1
    assert out[0].supplier_id == "sup_a"
    assert out[0].price == 90


def test_no_false_duplicate_different_sizes():
    """Разные размеры — разные группы, обе позиции остаются."""
    a = _tire_same_specs_template(
        supplier_id="s1",
        CML2_ARTICLE="a",
        SHIRINA_PROFILYA="195",
    )
    b = _tire_same_specs_template(
        supplier_id="s2",
        CML2_ARTICLE="b",
        SHIRINA_PROFILYA="205",
    )
    out = deduplicate([a, b], active_supplier_ids=["s1", "s2"])
    assert len(out) == 2


def test_name_fallback_duplicate_when_char_key_invalid():
    """Пустые поля характеристик — fallback по модели/CML2_ARTICLE; дубли схлопываются."""
    p1 = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="ONLYKEY",
        price=10,
        quantity=1,
        PROIZVODITEL="",
        MODEL_AVTOSHINY="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        SEZONNOST="",
    )
    p2 = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="ONLYKEY",
        price=99,
        quantity=2,
        PROIZVODITEL="",
        MODEL_AVTOSHINY="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        SEZONNOST="",
    )
    out = deduplicate([p1, p2], active_supplier_ids=["s1", "s2"])
    assert len(out) == 1
    assert out[0].price == 10


def test_group_duplicates_mixed_suppliers_one_group():
    """group_duplicates объединяет позиции разных supplier_id в одну группу."""
    a = _tire_same_specs_template(supplier_id="a", CML2_ARTICLE="x")
    b = _tire_same_specs_template(supplier_id="b", CML2_ARTICLE="y")
    groups = group_duplicates([a, b], "tires")
    assert len(groups) == 1
    assert len(next(iter(groups.values()))) == 2


# --- (б) скрещивание 2+ поставщиков: все уникальные остаются ---


def test_merge_three_suppliers_unique_products_three_rows():
    """Три разных товара от трёх поставщиков — три строки после дедупа."""
    products = [
        _tire_same_specs_template(
            supplier_id="s1",
            CML2_ARTICLE="u1",
            MODEL_AVTOSHINY="M1",
        ),
        _tire_same_specs_template(
            supplier_id="s2",
            CML2_ARTICLE="u2",
            MODEL_AVTOSHINY="M2",
            SHIRINA_PROFILYA="195",
        ),
        _tire_same_specs_template(
            supplier_id="s3",
            CML2_ARTICLE="u3",
            MODEL_AVTOSHINY="M3",
            SHIRINA_PROFILYA="215",
        ),
    ]
    out = deduplicate(products, active_supplier_ids=["s1", "s2", "s3"])
    assert len(out) == 3


# --- (в) дубли среди скрещенной выгрузки 2+ поставщиков ---


def test_merged_catalog_two_pairs_duplicate_plus_unique():
    """
    Поставщики A,B дают дубль (одна группа), C — уникум.
    После дедупа: 2 позиции (победитель дубля + уникум).
    """
    dup_a = _tire_same_specs_template(
        supplier_id="sup_a",
        CML2_ARTICLE="da",
        price=50,
        quantity=1,
    )
    dup_b = _tire_same_specs_template(
        supplier_id="sup_b",
        CML2_ARTICLE="db",
        price=999,
        quantity=1,
    )
    unique_c = _tire_same_specs_template(
        supplier_id="sup_c",
        CML2_ARTICLE="uniq",
        MODEL_AVTOSHINY="OTHER",
        SHIRINA_PROFILYA="225",
        price=300,
        quantity=2,
    )
    merged = [dup_a, dup_b, unique_c]
    out = deduplicate(merged, active_supplier_ids=["sup_a", "sup_b", "sup_c"])
    assert len(out) == 2
    articles = {p.CML2_ARTICLE for p in out}
    assert "uniq" in articles
    assert "da" in articles and "db" not in articles


def test_cheapest_no_stock_loses_to_more_expensive_with_stock():
    """Дешевле без остатка не побеждает дороже с остатком при require_stock=True."""
    no_stock = _tire_same_specs_template(
        supplier_id="s1",
        CML2_ARTICLE="n",
        price=1,
        quantity=0,
    )
    has_stock = _tire_same_specs_template(
        supplier_id="s2",
        CML2_ARTICLE="h",
        price=500,
        quantity=4,
    )
    out = deduplicate([no_stock, has_stock], require_stock=True)
    assert len(out) == 1
    assert out[0].supplier_id == "s2"


def test_wheels_two_suppliers_duplicate_merge():
    """Диски: два поставщика, одинаковые dedup-поля — один победитель."""
    w1 = make_wheel_product(
        supplier_id="wa",
        CML2_ARTICLE="w1",
        price=100,
        quantity=2,
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
    w2 = make_wheel_product(
        supplier_id="wb",
        CML2_ARTICLE="w2",
        price=250,
        quantity=1,
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
    out = deduplicate([w1, w2], active_supplier_ids=["wa", "wb"])
    assert len(out) == 1
    assert out[0].supplier_id == "wa"


# --- Интеграция storage -> get_export_products (скрещивание как в проде) ---


def test_export_pipeline_two_suppliers_merged_then_deduped(tmp_db_path):
    """Два поставщика в БД + один дубль между ними -> export отдаёт 2 строки (уникум + победитель)."""
    st = Storage(tmp_db_path)
    u1 = _tire_same_specs_template(
        supplier_id="p1",
        supplier="P1",
        CML2_ARTICLE="only",
        MODEL_AVTOSHINY="SOLO",
        SHIRINA_PROFILYA="265",
    )
    d1 = _tire_same_specs_template(
        supplier_id="p1",
        supplier="P1",
        CML2_ARTICLE="d1",
        price=100,
        quantity=2,
    )
    d2 = _tire_same_specs_template(
        supplier_id="p2",
        supplier="P2",
        CML2_ARTICLE="d2",
        price=300,
        quantity=1,
    )
    st.upsert_products([u1, d1], supplier="P1", supplier_id="p1", category="tires")
    st.upsert_products([d2], supplier="P2", supplier_id="p2", category="tires")

    out = get_export_products(
        st,
        active_supplier_ids=["p1", "p2"],
        require_stock=True,
    )
    articles = {p.CML2_ARTICLE for p in out}
    assert articles == {"only", "d1"}
    assert len(out) == 2
