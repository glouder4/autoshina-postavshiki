from src.product_filters import _is_outlet_clearance_product
from tests.conftest import make_tire_product


def test_outlet_clearance_detects_compact_marker_in_name():
    product = make_tire_product(NAME="РаспродажаУценка", PROIZVODITEL="Нормальный бренд")
    assert _is_outlet_clearance_product(product) is True


def test_outlet_clearance_detects_spaced_marker_in_name():
    product = make_tire_product(NAME="Распродажа Уценка", PROIZVODITEL="Нормальный бренд")
    assert _is_outlet_clearance_product(product) is True


def test_outlet_clearance_does_not_trigger_for_regular_brand():
    product = make_tire_product(NAME="Обычный товар", PROIZVODITEL="Michelin")
    assert _is_outlet_clearance_product(product) is False
