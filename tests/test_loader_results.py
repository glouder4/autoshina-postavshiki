"""Ветки LoadResult без сети (моки)."""
from __future__ import annotations

import requests

from src.loader import LoadOutcome, load_products_from_url
from tests.conftest import make_tire_product


class StubAdapter:
    def parse_product(self, elem, category):
        return make_tire_product(CML2_ARTICLE="stub")


def test_load_config_error_no_adapter(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: None)
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=tmp_path,
        config_dir=tmp_path,
    )
    assert r.outcome == LoadOutcome.CONFIG_ERROR


def test_load_fetch_error(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: StubAdapter())

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr("src.loader.fetch_xml_to_file", boom)
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=tmp_path,
        config_dir=tmp_path,
    )
    assert r.outcome == LoadOutcome.FETCH_ERROR


def test_load_parse_error_bad_xml(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: StubAdapter())
    cache_dir = tmp_path
    cache_file = cache_dir / "sid_tires.xml"
    cache_file.write_text("not xml at all <<<", encoding="utf-8")
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.PARSE_ERROR


def test_load_process_error_xpath(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: StubAdapter())
    monkeypatch.setattr(
        "src.loader.get_adapter_config",
        lambda *a, **k: {"item_xpath_tires": "//bad["},
    )
    cache_dir = tmp_path
    p = cache_dir / "sid_tires.xml"
    p.write_bytes(b'<?xml version="1.0"?><root><offer/></root>')
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.PROCESS_ERROR


def test_load_empty_all_filtered(monkeypatch, tmp_path):
    class BadAdapter:
        def parse_product(self, elem, category):
            return make_tire_product(price=0)

    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: BadAdapter())
    monkeypatch.setattr(
        "src.loader.get_adapter_config",
        lambda *a, **k: {"item_xpath_tires": "//offer"},
    )
    cache_dir = tmp_path
    p = cache_dir / "sid_tires.xml"
    p.write_bytes(b'<?xml version="1.0"?><root><offer/><offer/></root>')
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.EMPTY
    assert r.raw_items == 2
    assert r.filtered_out == 2
    assert r.accepted == 0


def test_load_success(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: StubAdapter())
    monkeypatch.setattr(
        "src.loader.get_adapter_config",
        lambda *a, **k: {"item_xpath_tires": "//offer"},
    )
    cache_dir = tmp_path
    p = cache_dir / "sid_tires.xml"
    p.write_bytes(b'<?xml version="1.0"?><root><offer id="1"/></root>')
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.SUCCESS
    assert len(r.products) == 1
    assert r.accepted == 1


class _ClearanceThenGoodAdapter:
    def __init__(self) -> None:
        self._n = 0

    def parse_product(self, elem, category):
        self._n += 1
        if self._n == 1:
            return make_tire_product(PROIZVODITEL="  Распродажа   Уценка ", CML2_ARTICLE="bad")
        return make_tire_product(NAME="Нормальное название", CML2_ARTICLE="good")


def test_clearance_placeholder_name_filtered(monkeypatch, tmp_path):
    monkeypatch.setattr("src.loader.get_adapter", lambda *a, **k: _ClearanceThenGoodAdapter())
    monkeypatch.setattr(
        "src.loader.get_adapter_config",
        lambda *a, **k: {"item_xpath_tires": "//offer"},
    )
    cache_dir = tmp_path
    p = cache_dir / "sid_tires.xml"
    p.write_bytes(
        b'<?xml version="1.0"?><root><offer id="1"/><offer id="2"/></root>'
    )
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.SUCCESS
    assert r.raw_items == 2
    assert r.filtered_out == 1
    assert r.accepted == 1
    assert r.products[0].CML2_ARTICLE == "good"


class _ManufacturerClearanceAdapter:
    def __init__(self) -> None:
        self._n = 0

    def parse_product(self, elem, category):
        self._n += 1
        if self._n == 1:
            return make_tire_product(
                NAME="Нормальное название",
                PROIZVODITEL="РаспродажаУценка",
                CML2_ARTICLE="bad-manufacturer",
            )
        return make_tire_product(NAME="Нормальное название", CML2_ARTICLE="good-manufacturer")


def test_clearance_placeholder_manufacturer_filtered(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.loader.get_adapter",
        lambda *a, **k: _ManufacturerClearanceAdapter(),
    )
    monkeypatch.setattr(
        "src.loader.get_adapter_config",
        lambda *a, **k: {"item_xpath_tires": "//offer"},
    )
    cache_dir = tmp_path
    p = cache_dir / "sid_tires.xml"
    p.write_bytes(
        b'<?xml version="1.0"?><root><offer id="1"/><offer id="2"/></root>'
    )
    r = load_products_from_url(
        "http://example.com/x.xml",
        "sid",
        "Name",
        "tires",
        cache_dir=cache_dir,
        config_dir=tmp_path,
        skip_fetch=True,
    )
    assert r.outcome == LoadOutcome.SUCCESS
    assert r.raw_items == 2
    assert r.filtered_out == 1
    assert r.accepted == 1
    assert r.products[0].CML2_ARTICLE == "good-manufacturer"
