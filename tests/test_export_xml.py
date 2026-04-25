"""Базовый контракт XML экспорта."""
from __future__ import annotations

from xml.etree import ElementTree as ET

from src.export import build_export_xml
from tests.conftest import make_tire_product, make_wheel_product


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
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
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
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    assert root.find("wheels") is None
    assert root.find("tires") is not None


def test_export_price_markup_7_percent_from_integer_is_107_not_108():
    p = make_tire_product(price=100.0, CML2_ARTICLE="price-int")
    xml_bytes = build_export_xml([p], markup_percent=7)
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    price = root.find("tires").find("product").find("price").text
    assert price == "107"


def test_export_price_markup_7_percent_from_fractional_rounds_up():
    p = make_tire_product(price=100.01, CML2_ARTICLE="price-frac")
    xml_bytes = build_export_xml([p], markup_percent=7)
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    price = root.find("tires").find("product").find("price").text
    assert price == "108"


def test_export_price_without_markup_for_integer_and_fractional():
    integer = make_tire_product(price=100.0, CML2_ARTICLE="no-markup-int")
    fractional = make_tire_product(price=100.01, CML2_ARTICLE="no-markup-frac")
    xml_bytes = build_export_xml([integer, fractional], markup_percent=0)
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    prices = [item.find("price").text for item in root.find("tires").findall("product")]
    assert prices == ["100", "101"]


def test_export_filters_clearance_products_from_legacy_data():
    bad = make_tire_product(NAME="Распродажа Уценка", CML2_ARTICLE="bad")
    good = make_tire_product(NAME="Обычный товар", CML2_ARTICLE="good")
    xml_bytes = build_export_xml([bad, good], category_filter="tires")
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    articles = [
        item.find("CML2_ARTICLE").text
        for item in root.find("tires").findall("product")
    ]
    assert articles == ["good"]


def test_export_tires_posadochnyy_diametr_zr_to_r():
    p = make_tire_product(POSADOCHNYY_DIAMETR="zr17", CML2_ARTICLE="zr")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == "R17"


def test_export_tires_posadochnyy_diametr_r_keeps_value():
    p = make_tire_product(POSADOCHNYY_DIAMETR="R17", CML2_ARTICLE="r17")
    xml_bytes = build_export_xml([p], category_filter="tires")
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    assert root.find("tires").find("product").find("POSADOCHNYY_DIAMETR").text == "R17"


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
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    name_text = root.find("tires").find("product").find("name").text
    assert "RZR17" not in name_text
    assert name_text == "R17"


def test_export_wheels_shirina_diska_extracts_leading_number():
    p = make_wheel_product(SHIRINA_DISKA="16 / 7J", CML2_ARTICLE="w-width")
    xml_bytes = build_export_xml([p], category_filter="wheels")
    root = ET.fromstring(xml_bytes.decode("utf-8").split("\n", 1)[1])
    assert root.find("wheels").find("product").find("SHIRINA_DISKA").text == "16"
