"""
Генерация объединённого XML из товаров после дедупликации.
Конвертация значений поставщиков под наши требования при экспорте.
"""
from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from .deduplicator import deduplicate
from .models import Product
from .storage import Storage
from .sync import load_suppliers_config

# Конвертация значений при экспорте (шины)
EXPORT_TRANSFORMS_TIRES: dict[str, dict[str, str]] = {
    "SEZONNOST": {
        "Летняя": "summer",
        "Зимняя": "winter",
        "Всесезонная": "allseason",
    },
    # SHIPY: поиск без учёта регистра
    "SHIPY": {
        "0": "no_ship", "1": "ship",
        "да": "ship", "нет": "no_ship",
        "шип": "ship", "нешип": "no_ship",
        "шипы": "ship", "шипованная": "ship", "шипованные": "ship",
        "нешипованная": "no_ship", "нешипованные": "no_ship",
        "без шипов": "no_ship", "без шипа": "no_ship",
        "yes": "ship", "no": "no_ship",
        "_": "no_ship",
        "ш.": "ship", "ш": "ship",
    },
}

# Поля с поиском без учёта регистра (normalize для lookup)
EXPORT_TRANSFORMS_NORMALIZE: set[str] = {"SHIPY"}


def _transform_export_value(field: str, value: str, category: str) -> str:
    """Применить конвертацию значения при экспорте."""
    transforms = EXPORT_TRANSFORMS_TIRES if category == "tires" else {}
    mapping = transforms.get(field, {})
    if not mapping:
        return value
    lookup = value.lower().strip() if field in EXPORT_TRANSFORMS_NORMALIZE else value.strip()
    return mapping.get(lookup, value)


def _product_to_xml(parent: Element, p: Product) -> None:
    """Добавить товар как дочерний элемент. Свойства — в тегах param."""
    item = SubElement(parent, "product")
    item.set("category", p.category)
    if p.OS_ARTICLE_ID:
        item.set("OS_ARTICLE_ID", p.OS_ARTICLE_ID)
    SubElement(item, "supplier").text = p.OS_SUPPLIER_TEXT or p.supplier
    SubElement(item, "price").text = str(p.price)
    SubElement(item, "quantity").text = str(p.quantity)

    def add_param(name: str) -> None:
        val = getattr(p, name, "")
        if val:
            val_str = str(val).strip()
            val_str = _transform_export_value(name, val_str, p.category)
            param = SubElement(item, "param")
            param.set("name", name)
            param.text = val_str

    if p.category == "tires":
        for attr in [
            "SHIRINA_PROFILYA", "VYSOTA_PROFILYA", "POSADOCHNYY_DIAMETR",
            "PROIZVODITEL", "SEZONNOST", "SHIPY", "MORE_PHOTO",
            "INDEKS_NAGRUZKI", "INDEKS_SKOROSTI", "CML2_ARTICLE",
            "MODEL_AVTOSHINY", "HOMOLOGATION",
        ]:
            add_param(attr)
    else:
        for attr in [
            "SHIRINA_DISKA", "POSADOCHNYY_DIAMETR_DISKA", "COUNT_OTVERSTIY",
            "MEZHBOLTOVOE_RASSTOYANIE", "VYLET_DISKA", "DIAMETR_STUPITSY",
            "MORE_PHOTO", "CML2_ARTICLE", "WHEEL_TYPE", "MODEL_DISKA",
            "PROIZVODITEL", "DISK_COLOR",
        ]:
            add_param(attr)


def build_export_xml(
    products: list[Product],
    category_filter: Optional[str] = None,
) -> bytes:
    """Собрать XML из списка товаров. category_filter: только tires или wheels."""
    root = Element("catalog")
    root.set("xmlns", "http://autoshina-postavshiki/export/1.0")

    if category_filter and category_filter != "tires":
        tires = None
    else:
        tires = SubElement(root, "tires")
    if category_filter and category_filter != "wheels":
        wheels = None
    else:
        wheels = SubElement(root, "wheels")

    for p in products:
        if category_filter and p.category != category_filter:
            continue
        parent = tires if p.category == "tires" else wheels
        if parent is not None:
            _product_to_xml(parent, p)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        root, encoding="unicode", method="xml"
    ).encode("utf-8")


def get_export_products(
    storage: Storage,
    active_suppliers: Optional[list[str]] = None,
    require_stock: bool = True,
) -> list[Product]:
    """Получить товары для выгрузки (после дедупликации, cheapest available)."""
    products = storage.get_all_products(active_suppliers=active_suppliers)
    return deduplicate(
        products,
        active_suppliers=active_suppliers,
        require_stock=require_stock,
    )


def generate_export_xml(
    db_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    require_stock: bool = True,
    category: Optional[str] = None,
) -> bytes:
    """
    Сгенерировать объединённый XML. Только активные поставщики.
    category: None — оба, "tires" или "wheels" — только указанная категория.
    """
    cfg = load_suppliers_config(config_path)
    suppliers = cfg.get("suppliers", [])
    active = [s["name"] for s in suppliers if s.get("active", True)]

    storage = Storage(db_path or "data/products.db")
    products = get_export_products(
        storage,
        active_suppliers=active,
        require_stock=require_stock,
    )
    return build_export_xml(products, category_filter=category)
