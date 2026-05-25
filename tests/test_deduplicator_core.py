"""Группировка дублей и выбор cheapest в deduplicator."""
from __future__ import annotations

from src.deduplicator import deduplicate
from tests.conftest import make_tire_product, make_wheel_product


def test_cheapest_with_stock_wins_same_specs():
    """Две шины с одинаковыми характеристиками — остаётся более дешёвая с остатком."""
    low = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="",
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
        CML2_ARTICLE="",
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
    p1 = make_tire_product(price=50, quantity=0, CML2_ARTICLE="")
    p2 = make_tire_product(price=100, quantity=0, CML2_ARTICLE="")
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
        CML2_ARTICLE="",
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
        CML2_ARTICLE="",
    )
    out = deduplicate([w1, w2])
    assert len(out) == 1
    assert out[0].price == 150


def test_wheels_different_disk_color_do_not_merge():
    """Разный цвет диска — это разные SKU, даже при одинаковых остальных характеристиках."""
    rich_stock = make_wheel_product(
        supplier_id="supplier_2",
        CML2_ARTICLE="9320085",
        price=9200,
        quantity=19,
        PROIZVODITEL="Replay",
        MODEL_DISKA="TY120",
        SHIRINA_DISKA="7.0",
        POSADOCHNYY_DIAMETR_DISKA="17",
    )
    low_stock = make_wheel_product(
        supplier_id="supplier_2",
        CML2_ARTICLE="9331139",
        price=8730,
        quantity=2,
        PROIZVODITEL="Replay",
        MODEL_DISKA="TY120",
        SHIRINA_DISKA="7.0",
        POSADOCHNYY_DIAMETR_DISKA="17",
    )
    for p in (rich_stock, low_stock):
        p.COUNT_OTVERSTIY = "5"
        p.MEZHBOLTOVOE_RASSTOYANIE = "114.3"
        p.VYLET_DISKA = "45"
        p.DIAMETR_STUPITSY = "60.1"
        p.WHEEL_TYPE = "литой"
    rich_stock.DISK_COLOR = "S"
    low_stock.DISK_COLOR = "BKF"

    out = deduplicate([rich_stock, low_stock])
    assert len(out) == 2
    assert {p.CML2_ARTICLE for p in out} == {"9320085", "9331139"}
    assert sorted(p.quantity for p in out) == [2, 19]


def test_same_article_deduplicates_despite_name_brand_and_case_differences():
    """Одинаковый валидный артикул в категории схлопывается в одну запись."""
    p1 = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="  ART-777  ",
        NAME="Название один",
        PROIZVODITEL="Brand One",
        MODEL_AVTOSHINY="Model One",
        price=250,
        quantity=2,
    )
    p2 = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="art-777",
        NAME="другое название",
        PROIZVODITEL="BRAND TWO",
        MODEL_AVTOSHINY="Another Model",
        price=120,
        quantity=1,
    )

    out = deduplicate([p1, p2])
    assert len(out) == 1
    assert out[0].price == 120


def test_empty_article_uses_legacy_chars_then_name_fallback():
    """Пустой артикул не ломает прежний fallback: chars key -> name key."""
    first = make_tire_product(
        CML2_ARTICLE="   ",
        PROIZVODITEL="",
        MODEL_AVTOSHINY="",
        SEZONNOST="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        NAME="  fallback name  ",
        price=300,
        quantity=1,
    )
    second = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="",
        MODEL_AVTOSHINY="",
        SEZONNOST="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        NAME="FALLBACK   NAME",
        price=180,
        quantity=1,
    )

    out = deduplicate([first, second])
    assert len(out) == 1
    assert out[0].price == 180


def test_brand_alias_pirelli_and_bfg_merge_by_chars_key():
    p1 = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="",
        PROIZVODITEL="Pirelli",
        MODEL_AVTOSHINY="Scorpion",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="235",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="19",
        price=200,
        quantity=1,
    )
    p2 = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="",
        PROIZVODITEL="Пирелли",
        MODEL_AVTOSHINY="Scorpion",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="235",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="19",
        price=180,
        quantity=1,
    )
    p3 = make_tire_product(
        supplier_id="s3",
        CML2_ARTICLE="",
        PROIZVODITEL="BFGoodrich",
        MODEL_AVTOSHINY="All-Terrain",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="245",
        VYSOTA_PROFILYA="70",
        POSADOCHNYY_DIAMETR="16",
        price=300,
        quantity=1,
    )
    p4 = make_tire_product(
        supplier_id="s4",
        CML2_ARTICLE="",
        PROIZVODITEL="BFG",
        MODEL_AVTOSHINY="All-Terrain",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="245",
        VYSOTA_PROFILYA="70",
        POSADOCHNYY_DIAMETR="16",
        price=250,
        quantity=1,
    )

    out = deduplicate([p1, p2, p3, p4])
    prices = sorted([p.price for p in out])
    assert prices == [180, 250]


def test_model_separator_normalization_x_ice_merge():
    p1 = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="Michelin",
        MODEL_AVTOSHINY="X-Ice Snow",
        SEZONNOST="Зимняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        price=220,
        quantity=1,
    )
    p2 = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="Michelin",
        MODEL_AVTOSHINY="X Ice Snow",
        SEZONNOST="Зимняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        price=190,
        quantity=1,
    )
    out = deduplicate([p1, p2])
    assert len(out) == 1
    assert out[0].price == 190


def test_alias_does_not_overmerge_with_different_model():
    first = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="Pirelli",
        MODEL_AVTOSHINY="Cinturato P7",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="225",
        VYSOTA_PROFILYA="45",
        POSADOCHNYY_DIAMETR="17",
    )
    second = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="Пирелли",
        MODEL_AVTOSHINY="Scorpion Verde",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="225",
        VYSOTA_PROFILYA="45",
        POSADOCHNYY_DIAMETR="17",
    )
    out = deduplicate([first, second])
    assert len(out) == 2


def test_name_key_separator_normalization_does_not_break_article_fallback():
    first = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="",
        MODEL_AVTOSHINY="X-Ice 3",
        SEZONNOST="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        price=210,
    )
    second = make_tire_product(
        CML2_ARTICLE="",
        PROIZVODITEL="",
        MODEL_AVTOSHINY="x ice 3",
        SEZONNOST="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="",
        price=180,
    )
    out = deduplicate([first, second])
    assert len(out) == 1
    assert out[0].price == 180


def test_tire_16_vs_r16_merges():
    """16 и R16 после нормализации дают один ключ дедупликации."""
    a = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        price=200,
        quantity=1,
    )
    b = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="R16",
        price=150,
        quantity=1,
    )
    out = deduplicate([a, b])
    assert len(out) == 1
    assert out[0].price == 150


def test_tire_zr17_vs_17_merges():
    """zr17 и 17 после нормализации дают один ключ дедупликации."""
    a = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="zr17",
        price=200,
        quantity=1,
    )
    b = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="M",
        SEZONNOST="Летняя",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="17",
        price=150,
        quantity=1,
    )
    out = deduplicate([a, b])
    assert len(out) == 1
    assert out[0].price == 150


def test_tire_zr_vs_r_in_posadochnyy_diametr_merges():
    """R и ZR в полном размере шины считаем одним ключом дедупликации."""
    a = make_tire_product(
        supplier_id="s1",
        CML2_ARTICLE="",
        PROIZVODITEL="Michelin",
        MODEL_AVTOSHINY="X",
        SEZONNOST="Зимняя",
        SHIRINA_PROFILYA="225",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="225/55R17",
        price=200,
        quantity=1,
    )
    b = make_tire_product(
        supplier_id="s2",
        CML2_ARTICLE="",
        PROIZVODITEL="Michelin",
        MODEL_AVTOSHINY="X",
        SEZONNOST="Зимняя",
        SHIRINA_PROFILYA="225",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="225/55ZR17",
        price=150,
        quantity=1,
    )
    out = deduplicate([a, b])
    assert len(out) == 1
    assert out[0].price == 150


def test_wheel_rim_slash_width_vs_diameter_only_merges():
    """«16 / 7j» и «16» в ширине/диаметре диска дают один ключ по ведущему дюйму."""
    w1 = make_wheel_product(
        supplier_id="s1",
        CML2_ARTICLE="",
        PROIZVODITEL="X",
        MODEL_DISKA="Z",
        SHIRINA_DISKA="16 / 7j",
        POSADOCHNYY_DIAMETR_DISKA="",
        COUNT_OTVERSTIY="5",
        MEZHBOLTOVOE_RASSTOYANIE="112",
        VYLET_DISKA="40",
        DIAMETR_STUPITSY="60",
        WHEEL_TYPE="литой",
        price=200,
        quantity=1,
    )
    w2 = make_wheel_product(
        supplier_id="s2",
        CML2_ARTICLE="",
        PROIZVODITEL="X",
        MODEL_DISKA="Z",
        SHIRINA_DISKA="16",
        POSADOCHNYY_DIAMETR_DISKA="",
        COUNT_OTVERSTIY="5",
        MEZHBOLTOVOE_RASSTOYANIE="112",
        VYLET_DISKA="40",
        DIAMETR_STUPITSY="60",
        WHEEL_TYPE="литой",
        price=180,
        quantity=1,
    )
    out = deduplicate([w1, w2])
    assert len(out) == 1
    assert out[0].price == 180
