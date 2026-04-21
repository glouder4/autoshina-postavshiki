"""Тесты дедупликации и фильтра active_supplier_ids."""
from __future__ import annotations

from src.deduplicator import deduplicate
from tests.conftest import make_tire_product


def test_active_supplier_ids_empty_returns_empty():
    p = make_tire_product()
    assert deduplicate([p], active_supplier_ids=[]) == []


def test_inactive_supplier_excluded_even_if_cheaper():
    cheap = make_tire_product(
        supplier_id="inactive",
        price=10,
        CML2_ARTICLE="D1",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="Same",
        SEZONNOST="Летняя",
    )
    expensive = make_tire_product(
        supplier_id="active",
        price=9999,
        CML2_ARTICLE="D2",
        PROIZVODITEL="B",
        MODEL_AVTOSHINY="Same",
        SEZONNOST="Летняя",
    )

    result = deduplicate([cheap, expensive], active_supplier_ids=["active"])
    assert len(result) == 1
    assert result[0].supplier_id == "active"


def test_none_active_filter_passes_all():
    a = make_tire_product(supplier_id="s1", CML2_ARTICLE="A1")
    b = make_tire_product(supplier_id="s2", CML2_ARTICLE="A2", MODEL_AVTOSHINY="Other")
    out = deduplicate([a, b], active_supplier_ids=None)
    assert len(out) == 2
