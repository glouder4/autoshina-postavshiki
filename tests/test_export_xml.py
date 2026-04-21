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
