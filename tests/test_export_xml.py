"""Базовый контракт XML экспорта."""
from __future__ import annotations

import pytest
from xml.etree import ElementTree as ET

from src.export import _build_sync_comment, build_export_xml
from src.sync_state import SyncState, save_sync_state
from tests.conftest import make_tire_product, make_wheel_product


def _extract_root(xml_bytes: bytes) -> ET.Element:
    text = xml_bytes.decode("utf-8")
    start = text.find("<catalog")
    assert start != -1
    return ET.fromstring(text[start:])


def test_export_xml_structure_and_os_article():
    tires = [
        make_tire_product(CML2_ARTICLE="T1"),
    ]
    tires[0].OS_ARTICLE_ID = "os_article_supplier_1_T1"
    wheels = [
        make_wheel_product(CML2_ARTICLE="W1"),
    ]
    wheels[0].OS_ARTICLE_ID = "os_article_supplier_1_W1"
    xml_bytes = build_export_xml(tires + wheels)
    root = _extract_root(xml_bytes)
    assert root.tag == "catalog"
    tire_elems = root.find("tires").findall("product")
    wheel_elems = root.find("wheels").findall("product")
    assert len(tire_elems) == 1
    assert tire_elems[0].get("OS_ARTICLE_ID") == "os_article_supplier_1_T1"
    assert len(wheel_elems) == 1


def test_export_category_filter_tires_only():
    p = make_tire_product(CML2_ARTICLE="only")
    p.OS_ARTICLE_ID = "id1"
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    assert root.find("wheels") is None
    assert root.find("tires") is not None


def test_export_price_markup_7_percent_from_integer_is_107_not_108():
    p = make_tire_product(price=100.0, CML2_ARTICLE="price-int")
    xml_bytes = build_export_xml([p], markup_percent=7)
    root = _extract_root(xml_bytes)
    price = root.find("tires").find("product").find("price").text
    assert price == "107"


def test_export_price_markup_7_percent_from_fractional_rounds_up():
    p = make_tire_product(price=100.01, CML2_ARTICLE="price-frac")
    xml_bytes = build_export_xml([p], markup_percent=7)
    root = _extract_root(xml_bytes)
    price = root.find("tires").find("product").find("price").text
    assert price == "108"


def test_export_price_without_markup_for_integer_and_fractional():
    integer = make_tire_product(price=100.0, CML2_ARTICLE="no-markup-int")
    fractional = make_tire_product(price=100.01, CML2_ARTICLE="no-markup-frac")
    xml_bytes = build_export_xml([integer, fractional], markup_percent=0)
    root = _extract_root(xml_bytes)
    prices = [item.find("price").text for item in root.find("tires").findall("product")]
    assert prices == ["100", "101"]


def test_export_filters_clearance_products_from_legacy_data():
    bad = make_tire_product(NAME="Распродажа Уценка", CML2_ARTICLE="bad")
    good = make_tire_product(NAME="Обычный товар", CML2_ARTICLE="good")
    xml_bytes = build_export_xml([bad, good], category_filter="tires")
    root = _extract_root(xml_bytes)
    articles = [
        item.find("CML2_ARTICLE").text
        for item in root.find("tires").findall("product")
    ]
    assert articles == ["good"]


def test_export_tires_posadochnyy_diametr_zr_to_r():
    p = make_tire_product(POSADOCHNYY_DIAMETR="zr17", CML2_ARTICLE="zr")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == "R17"


def test_export_tires_posadochnyy_diametr_r_keeps_value():
    p = make_tire_product(POSADOCHNYY_DIAMETR="R17", CML2_ARTICLE="r17")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == "R17"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20", "R20"),
        ("16.5", "R16.5"),
        ("12C", "R12C"),
        ("533", "533"),
        ("x100", "x100"),
        ("225/55R17", "225/55R17"),
    ],
)
def test_export_tires_posadochnyy_diametr_normalizes_bare_diameter(raw, expected):
    p = make_tire_product(POSADOCHNYY_DIAMETR=raw, CML2_ARTICLE=f"pdd-{raw}")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == expected


def test_export_tires_posadochnyy_diametr_16_and_r16_both_normalize_to_r16():
    for article, raw in (("bare-16", "16"), ("prefixed-r16", "R16")):
        p = make_tire_product(POSADOCHNYY_DIAMETR=raw, CML2_ARTICLE=article)
        xml_bytes = build_export_xml([p], category_filter="tires")
        root = _extract_root(xml_bytes)
        assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == "R16"


def test_export_tire_name_uses_normalized_diameter_when_name_empty():
    p = make_tire_product(
        NAME="",
        PROIZVODITEL="",
        MODEL_AVTOSHINY="",
        SHIRINA_PROFILYA="",
        VYSOTA_PROFILYA="",
        POSADOCHNYY_DIAMETR="zr17",
        CML2_ARTICLE="name-zr17",
    )
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    name_text = root.find("tires").find("product").find("name").text
    assert "RZR17" not in name_text
    assert name_text == "R17"


def test_export_wheels_shirina_diska_extracts_leading_number():
    p = make_wheel_product(SHIRINA_DISKA="16 / 7J", CML2_ARTICLE="w-width")
    xml_bytes = build_export_xml([p], category_filter="wheels")
    root = _extract_root(xml_bytes)
    assert root.find("wheels").find("product").find("SHIRINA_DISKA").text == "16"


def test_export_wheels_posadochnyy_diametr_diska_extracts_leading_number():
    p = make_wheel_product(POSADOCHNYY_DIAMETR_DISKA="16 / 7J", CML2_ARTICLE="w-pdd")
    xml_bytes = build_export_xml([p], category_filter="wheels")
    root = _extract_root(xml_bytes)
    assert root.find("wheels").find("product").find("POSADOCHNYY_DIAMETR_DISKA").text == "16"


def test_export_tires_shipy_n_sh_maps_to_neshipovannye():
    p = make_tire_product(SHIPY="\u043d/\u0448.", CML2_ARTICLE="t-shipy")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = _extract_root(xml_bytes)
    assert root.find("tires").find("product").find("SHIPY").text == (
        "\u041d\u0435\u0448\u0438\u043f\u043e\u0432\u0430\u043d\u043d\u044b\u0435"
    )


def test_export_wheel_name_empty_uses_normalized_width_x_diameter():
    p = make_wheel_product(
        NAME="",
        SHIRINA_DISKA="8.5 / 9J",
        POSADOCHNYY_DIAMETR_DISKA="18 / 7J",
        CML2_ARTICLE="w-name-norm",
    )
    xml_bytes = build_export_xml([p], category_filter="wheels")
    root = _extract_root(xml_bytes)
    prod = root.find("wheels").find("product")
    assert prod.find("SHIRINA_DISKA").text == "8.5"
    assert prod.find("POSADOCHNYY_DIAMETR_DISKA").text == "18"
    name_text = prod.find("name").text
    assert "8.5x18" in name_text
    assert "8.5 /" not in name_text
    assert "18 /" not in name_text


def test_export_xml_includes_meta_comment_at_top():
    p = make_tire_product(CML2_ARTICLE="top-comment")
    xml_text = build_export_xml(
        [p],
        category_filter="tires",
        meta_comment="Дата последнего обновления: 2026-04-30T12:00:00+00:00",
    ).decode("utf-8")
    assert xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!--\n')
    assert "Дата последнего обновления: 2026-04-30T12:00:00+00:00" in xml_text
    assert "<catalog>" in xml_text


def test_build_sync_comment_filters_only_requested_category(tmp_path):
    st = SyncState(
        updated_at="2026-04-30T12:00:00+00:00",
        categories={
            "supplier_1|tires": {"outcome": "success", "accepted": 120, "products_saved": 118},
            "supplier_2|wheels": {"outcome": "success", "accepted": 20, "products_saved": 19},
            "supplier_3|tires": {"outcome": "fetch_error", "detail": "timeout", "accepted": 0},
        },
    )
    sync_state_path = tmp_path / "sync_state.json"
    save_sync_state(st, sync_state_path)

    tires_comment = _build_sync_comment("tires", sync_state_path=sync_state_path)
    assert "Дата последнего обновления: 2026-04-30T12:00:00+00:00" in tires_comment
    assert "supplier_1 - SUCCESS, accepted=120, saved=118" in tires_comment
    assert "supplier_3 - FETCH_ERROR, accepted=0, saved=0, detail=timeout" in tires_comment
    assert "supplier_2 - SUCCESS" not in tires_comment

    wheels_comment = _build_sync_comment("wheels", sync_state_path=sync_state_path)
    assert "supplier_2 - SUCCESS, accepted=20, saved=19" in wheels_comment
    assert "supplier_1 - SUCCESS" not in wheels_comment


def test_build_sync_comment_fallback_when_state_missing(tmp_path):
    comment = _build_sync_comment("tires", sync_state_path=tmp_path / "missing.json")
    assert "Дата последнего обновления: неизвестно" in comment
    assert "sync_state недоступен или поврежден" in comment
