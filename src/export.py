"""
Генерация объединённого XML из товаров после дедупликации.
Конвертация значений поставщиков под наши требования при экспорте.
"""
import re
from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from .config import load_suppliers_config
from .deduplicator import deduplicate
from .models import Product
from .storage import Storage

# Конвертация значений при экспорте (шины)
EXPORT_TRANSFORMS_TIRES: dict[str, dict[str, str]] = {
    # SEZONNOST: различные входящие значения → Летняя / Зимняя / Всесезонная
    "SEZONNOST": {
        "Летняя": "Летняя", "summer": "Летняя", "s": "Летняя",
        "Зимняя": "Зимняя", "winter": "Зимняя", "w": "Зимняя",
        "Всесезонная": "Всесезонная", "allseason": "Всесезонная", "all": "Всесезонная", "u": "Всесезонная", "a": "Всесезонная",
        "Грузовые": "Грузовые", "cargo": "Грузовые",
    },
    # SHIPY: поиск без учёта регистра → Шипованные / Нешипованные
    "SHIPY": {
        "0": "Нешипованные", "1": "Шипованные",
        "да": "Шипованные", "нет": "Нешипованные",
        "шип": "Шипованные", "нешип": "Нешипованные",
        "шипы": "Шипованные", "шипованная": "Шипованные", "шипованные": "Шипованные",
        "нешипованная": "Нешипованные", "нешипованные": "Нешипованные",
        "без шипов": "Нешипованные", "без шипа": "Нешипованные",
        "yes": "Шипованные", "no": "Нешипованные",
        "ship": "Шипованные", "no_ship": "Нешипованные",
        "_": "Нешипованные",
        "ш.": "Шипованные", "ш": "Шипованные",
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


def _build_product_name(p: Product) -> str:
    """Собрать название товара из полей."""
    parts = []
    if p.category == "tires":
        if p.PROIZVODITEL:
            parts.append(p.PROIZVODITEL)
        if p.MODEL_AVTOSHINY:
            parts.append(p.MODEL_AVTOSHINY)
        w, h, d = p.SHIRINA_PROFILYA, p.VYSOTA_PROFILYA, str(p.POSADOCHNYY_DIAMETR).strip()
        if w and h:
            dim = f"{w}/{h}"
            if d:
                dim += f"R{d}" if not d.upper().startswith("R") else d
            parts.append(dim)
        elif w:
            parts.append(w)
        elif d:
            parts.append(f"R{d}" if not d.upper().startswith("R") else d)
        if p.INDEKS_NAGRUZKI or p.INDEKS_SKOROSTI:
            parts.append(f"{p.INDEKS_NAGRUZKI or ''}{p.INDEKS_SKOROSTI or ''}".strip())
    else:
        if p.PROIZVODITEL:
            parts.append(p.PROIZVODITEL)
        if p.MODEL_DISKA:
            parts.append(p.MODEL_DISKA)
        if p.SHIRINA_DISKA and p.POSADOCHNYY_DIAMETR_DISKA:
            parts.append(f"{p.SHIRINA_DISKA}x{p.POSADOCHNYY_DIAMETR_DISKA}")
        elif p.SHIRINA_DISKA:
            parts.append(p.SHIRINA_DISKA)
        elif p.POSADOCHNYY_DIAMETR_DISKA:
            parts.append(p.POSADOCHNYY_DIAMETR_DISKA)
        if p.COUNT_OTVERSTIY and p.MEZHBOLTOVOE_RASSTOYANIE:
            parts.append(f"{p.COUNT_OTVERSTIY}x{p.MEZHBOLTOVOE_RASSTOYANIE}")
    return " ".join(p.strip() for p in parts if p and str(p).strip())


def _first_photo_url(more_photo: str) -> str:
    """Извлечь первую ссылку из MORE_PHOTO (разделители: запятая, пробел, перевод строки)."""
    if not more_photo or not more_photo.strip():
        return ""
    for part in re.split(r"[\s,;\n]+", more_photo.strip()):
        s = part.strip()
        if s and (s.startswith("http://") or s.startswith("https://")):
            return s
    return more_photo.strip()


def _product_to_xml(parent: Element, p: Product) -> None:
    """Добавить товар. Свойства — как отдельные дочерние элементы (плагины/предпросмотр лучше их видят)."""
    item = SubElement(parent, "product")
    item.set("category", p.category)
    if p.OS_ARTICLE_ID:
        item.set("OS_ARTICLE_ID", p.OS_ARTICLE_ID)
    SubElement(item, "supplier").text = p.OS_SUPPLIER_TEXT or p.supplier
    SubElement(item, "price").text = str(p.price)
    SubElement(item, "quantity").text = str(p.quantity)
    if p.PROIZVODITEL:
        SubElement(item, "brand").text = p.PROIZVODITEL.strip()
    name_val = (p.NAME or "").strip() or _build_product_name(p)
    if name_val:
        SubElement(item, "name").text = name_val
    picture = _first_photo_url(p.MORE_PHOTO)
    if picture:
        SubElement(item, "picture").text = picture

    def add_field(name: str) -> None:
        val = getattr(p, name, "")
        if val:
            val_str = str(val).strip()
            val_str = _transform_export_value(name, val_str, p.category)
            child = SubElement(item, name)
            child.text = val_str

    if p.category == "tires":
        for attr in [
            "SHIRINA_PROFILYA", "VYSOTA_PROFILYA", "POSADOCHNYY_DIAMETR",
            "PROIZVODITEL", "SEZONNOST", "SHIPY", "MORE_PHOTO",
            "INDEKS_NAGRUZKI", "INDEKS_SKOROSTI", "CML2_ARTICLE",
            "MODEL_AVTOSHINY", "HOMOLOGATION",
        ]:
            add_field(attr)
    else:
        for attr in [
            "SHIRINA_DISKA", "POSADOCHNYY_DIAMETR_DISKA", "COUNT_OTVERSTIY",
            "MEZHBOLTOVOE_RASSTOYANIE", "VYLET_DISKA", "DIAMETR_STUPITSY",
            "MORE_PHOTO", "CML2_ARTICLE", "WHEEL_TYPE", "MODEL_DISKA",
            "PROIZVODITEL", "DISK_COLOR",
        ]:
            add_field(attr)


def build_export_xml(
    products: list[Product],
    category_filter: Optional[str] = None,
) -> bytes:
    """Собрать XML из списка товаров. category_filter: только tires или wheels."""
    root = Element("catalog")

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
