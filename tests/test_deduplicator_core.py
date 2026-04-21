"""Группировка дублей и выбор cheapest в deduplicator."""
from __future__ import annotations

from src.deduplicator import deduplicate
from tests.conftest import make_tire_product, make_wheel_product


def test_cheapest_with_stock_wins_same_specs():
    """Две шины с одинаковыми характеристиками — остаётся более дешёвая с остатком."""
    low = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="L",
        price=100,
        quantity=2,
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
    )
    high = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="H",
        price=500,
        quantity=5,
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
    )
    out = deduplicate([low, high], active_supplier_ids=["s1"])
    assert len(out) == 1
    assert out[0].price == 100


def test_require_stock_false_when_all_zero_qty_picks_lowest_price():
    """При отсутствии остатков у всех позиций выбирается минимальная цена."""
    p1 = make_tire_product(price=50, quantity=0, CML2_ARTICLE="a")
    p2 = make_tire_product(price=100, quantity=0, CML2_ARTICLE="b")
    for p in (p1, p2):
        p.PROIZVODITEL = "X"
        p.MODEL_AVTOSHINY = "Y"
        p.SEZONNOST = "Летняя"
        p.SHIRINA_PROFILYA = "205"
        p.VYSOTA_PROFILYA = "55"
        p.POSADOCHNYY_DIAMETR = "16"

    out = deduplicate([p1, p2], require_stock=False)
    assert len(out) == 1
    assert out[0].price == 50


def test_wheel_duplicate_group():
    w1 = make_wheel_product(
        supplier_id="s1",
        price=300,
        quantity=2,
        PROIZVODITEL="W",
        MODEL_DISKA="Z",
        SHIRINA_DISKA="7",
        POSADOCHNYY_DIAMETR_DISKA="17",
        COUNT_OTVERSTIY="5",
        MEZHBOLTOVOE_RASSTOYANIE="112",
        VYLET_DISKA="40",
        DIAMETR_STUPITSY="60",
        WHEEL_TYPE="литой",
        CML2_ARTICLE="w1",
    )
    w2 = make_wheel_product(
        supplier_id="s1",
        price=150,
        quantity=1,
        PROIZVODITEL="W",
        MODEL_DISKA="Z",
        SHIRINA_DISKA="7",
        POSADOCHNYY_DIAMETR_DISKA="17",
        COUNT_OTVERSTIY="5",
        MEZHBOLTOVOE_RASSTOYANIE="112",
        VYLET_DISKA="40",
        DIAMETR_STUPITSY="60",
        WHEEL_TYPE="литой",
        CML2_ARTICLE="w2",
    )
    out = deduplicate([w1, w2])
    assert len(out) == 1
    assert out[0].price == 150
