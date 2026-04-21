"""Общие фикстуры и фабрики для тестов."""
from __future__ import annotations

import pytest

from src.models import Product


def make_tire_product(
    *,
    supplier_id: str = "supplier_1",
    supplier: str = "TestSupplier",
    article: str = "ART001",
    price: float = 100.0,
    quantity: int = 5,
    **kwargs: object,
) -> Product:
    """Шина с полями, проходящими фильтр loader и export (price>0, имя/бренд, фото URL)."""
    return Product(
        supplier_id=supplier_id,
        supplier=supplier,
        category="tires",
        price=price,
        quantity=quantity,
        NAME=kwargs.get("NAME", "Test Tire"),
        CML2_ARTICLE=str(kwargs.get("CML2_ARTICLE", article)),
        MORE_PHOTO=kwargs.get("MORE_PHOTO", "https://example.com/p.jpg"),
        PROIZVODITEL=kwargs.get("PROIZVODITEL", "BrandX"),
        MODEL_AVTOSHINY=kwargs.get("MODEL_AVTOSHINY", "ModelY"),
        SHIRINA_PROFILYA=kwargs.get("SHIRINA_PROFILYA", "205"),
        VYSOTA_PROFILYA=kwargs.get("VYSOTA_PROFILYA", "55"),
        POSADOCHNYY_DIAMETR=kwargs.get("POSADOCHNYY_DIAMETR", "16"),
    )


def make_wheel_product(
    *,
    supplier_id: str = "supplier_1",
    supplier: str = "TestSupplier",
    article: str = "W001",
    price: float = 200.0,
    quantity: int = 3,
    **kwargs: object,
) -> Product:
    return Product(
        supplier_id=supplier_id,
        supplier=supplier,
        category="wheels",
        price=price,
        quantity=quantity,
        NAME=kwargs.get("NAME", "Wheel Z"),
        CML2_ARTICLE=str(kwargs.get("CML2_ARTICLE", article)),
        MORE_PHOTO=kwargs.get("MORE_PHOTO", "https://example.com/w.jpg"),
        PROIZVODITEL=kwargs.get("PROIZVODITEL", "WheelCo"),
        MODEL_DISKA=kwargs.get("MODEL_DISKA", "R1"),
        SHIRINA_DISKA=kwargs.get("SHIRINA_DISKA", "7.5"),
        POSADOCHNYY_DIAMETR_DISKA=kwargs.get("POSADOCHNYY_DIAMETR_DISKA", "17"),
    )


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "test.db"
