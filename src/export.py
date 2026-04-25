"""
Генерация объединённого XML из товаров после дедупликации.
Конвертация значений поставщиков под наши требования при экспорте.
"""
import re
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from .config import load_suppliers_config
from .deduplicator import deduplicate
from .models import Product
from .product_filters import _is_outlet_clearance_product
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
        w = p.SHIRINA_PROFILYA
        h = p.VYSOTA_PROFILYA
        d = _normalize_tire_diameter(str(p.POSADOCHNYY_DIAMETR))
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
    """Извлечь первую полную ссылку из MORE_PHOTO. URL может содержать запятые в пути."""
    if not more_photo or not more_photo.strip():
        return ""
    m = re.search(r"https?://[^\s]+", more_photo.strip())
    return m.group(0) if m else more_photo.strip()


def _normalize_tire_diameter(value: str) -> str:
    raw = (value or "").strip()
    m = re.match(r"^ZR(\d+)$", raw, flags=re.IGNORECASE)
    if m:
        return f"R{m.group(1)}"
    return raw


def _normalize_wheel_width(value: str) -> str:
    raw = (value or "").strip()
    first_part = raw.split("/", 1)[0].strip()
    m = re.match(r"^(\d+(?:\.\d+)?)", first_part)
    if m:
        return m.group(1)
    return first_part


def _product_to_xml(parent: Element, p: Product, markup_percent: float = 0) -> None:
    """Добавить товар. Свойства — как отдельные дочерние элементы (плагины/предпросмотр лучше их видят)."""
    item = SubElement(parent, "product")
    item.set("category", p.category)
    if p.OS_ARTICLE_ID:
        item.set("OS_ARTICLE_ID", p.OS_ARTICLE_ID)
    SubElement(item, "supplier").text = p.OS_SUPPLIER_TEXT or p.supplier
    base_price = Decimal(str(p.price))
    if markup_percent:
        markup_multiplier = Decimal("1") + (Decimal(str(markup_percent)) / Decimal("100"))
        raw_price = base_price * markup_multiplier
    else:
        raw_price = base_price
    price_val = int(raw_price.to_integral_value(rounding=ROUND_CEILING))
    SubElement(item, "price").text = str(price_val)
    SubElement(item, "quantity").text = str(p.quantity)
    brand_val = (p.PROIZVODITEL or "").strip()
    if brand_val:
        SubElement(item, "brand").text = brand_val
    name_val = (p.NAME or "").strip() or _build_product_name(p)
    if name_val and brand_val and not name_val.lower().startswith(brand_val.lower()):
        name_val = f"{brand_val} {name_val}"
    if name_val:
        SubElement(item, "name").text = name_val
    picture = _first_photo_url(p.MORE_PHOTO)
    if picture:
        SubElement(item, "picture").text = picture

    def add_field(name: str) -> None:
        val = getattr(p, name, "")
        if val:
            val_str = str(val).strip()
            if p.category == "tires" and name == "POSADOCHNYY_DIAMETR":
                val_str = _normalize_tire_diameter(val_str)
            elif p.category == "wheels" and name == "SHIRINA_DISKA":
                val_str = _normalize_wheel_width(val_str)
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
    markup_percent: float = 0,
) -> bytes:
    """Собрать XML из списка товаров. category_filter: только tires или wheels. markup_percent: накрутка на цены."""
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
        if _is_outlet_clearance_product(p):
            continue
        if category_filter and p.category != category_filter:
            continue
        parent = tires if p.category == "tires" else wheels
        if parent is not None:
            _product_to_xml(parent, p, markup_percent=markup_percent)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        root, encoding="unicode", method="xml"
    ).encode("utf-8")


def get_export_products(
    storage: Storage,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> list[Product]:
    """Получить товары для выгрузки (после дедупликации, cheapest available)."""
    products = storage.get_all_products(active_supplier_ids=active_supplier_ids)
    products = deduplicate(
        products,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )
    return [p for p in products if p.price > 0 and p.quantity > 0]


def compute_export_dedup_stats(
    storage: Storage,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> dict[str, Any]:
    """
    Счётчики до/после дедупликации (та же цепочка, что у get_export_products).
    merged_duplicate_rows = before − after дедупликатора: слияние дублей и пропуск групп
    без валидного кандидата при require_stock; не смешивать с filtered_out на загрузке.
    """
    all_p = storage.get_all_products(active_supplier_ids=active_supplier_ids)

    def _count_cat(products: list[Product], cat: str) -> int:
        return sum(1 for p in products if p.category == cat)

    before = {
        "tires": _count_cat(all_p, "tires"),
        "wheels": _count_cat(all_p, "wheels"),
    }
    before["total"] = before["tires"] + before["wheels"]

    deduped = deduplicate(
        all_p,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )
    after_dedup = {
        "tires": _count_cat(deduped, "tires"),
        "wheels": _count_cat(deduped, "wheels"),
    }
    after_dedup["total"] = after_dedup["tires"] + after_dedup["wheels"]

    merged = {
        "tires": before["tires"] - after_dedup["tires"],
        "wheels": before["wheels"] - after_dedup["wheels"],
        "total": before["total"] - after_dedup["total"],
    }

    kept_price_qty = [p for p in deduped if p.price > 0 and p.quantity > 0]
    after_filter = {
        "tires": _count_cat(kept_price_qty, "tires"),
        "wheels": _count_cat(kept_price_qty, "wheels"),
    }
    after_filter["total"] = after_filter["tires"] + after_filter["wheels"]

    return {
        "before_deduplicate_rows": before,
        "after_deduplicate_rows": after_dedup,
        "merged_duplicate_rows": merged,
        "after_price_quantity_filter_rows": after_filter,
    }


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
    active = [s["id"] for s in suppliers if s.get("active", True)]

    storage = Storage(db_path or "data/products.db")
    products = get_export_products(
        storage,
        active_supplier_ids=active,
        require_stock=require_stock,
    )
    markup = float(cfg.get("markup_percent", 0) or 0)
    return build_export_xml(products, category_filter=category, markup_percent=markup)
