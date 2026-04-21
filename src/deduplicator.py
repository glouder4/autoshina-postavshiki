"""
Дедупликация товаров: по косвенным признакам и по названию.
Группировка выполняется отдельно по категории (tires/wheels).
"""
import hashlib
import re
from collections import defaultdict
from typing import Callable, Optional

from .models import Product

# Поля для ключа дедупликации по характеристикам
DEDUP_FIELDS_TIRES = [
    "SHIRINA_PROFILYA",
    "VYSOTA_PROFILYA",
    "POSADOCHNYY_DIAMETR",
    "PROIZVODITEL",
    "MODEL_AVTOSHINY",
    "SEZONNOST",
]
DEDUP_FIELDS_WHEELS = [
    "SHIRINA_DISKA",
    "POSADOCHNYY_DIAMETR_DISKA",
    "COUNT_OTVERSTIY",
    "MEZHBOLTOVOE_RASSTOYANIE",
    "VYLET_DISKA",
    "DIAMETR_STUPITSY",
    "PROIZVODITEL",
    "MODEL_DISKA",
    "WHEEL_TYPE",
]


def normalize_name(s: str) -> str:
    """Нормализация строки: lowercase, trim, сжатие пробелов."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _name_key(product: Product) -> str:
    """Ключ по названию (модель)."""
    name = ""
    if product.category == "tires":
        name = product.MODEL_AVTOSHINY or product.CML2_ARTICLE
    else:
        name = product.MODEL_DISKA or product.CML2_ARTICLE
    return hashlib.md5(normalize_name(name).encode()).hexdigest()


def _chars_key(product: Product, fields: list[str]) -> str:
    """Ключ по набору характеристик."""
    parts = []
    for f in fields:
        val = getattr(product, f, "")
        parts.append(str(val or "").strip().lower())
    return "|".join(parts)


def _is_char_key_valid(ckey: str, num_fields: int) -> bool:
    """Ключ по характеристикам считается валидным, если не пустой."""
    empty = "|" * (num_fields - 1) if num_fields > 1 else ""
    return bool(ckey and ckey != empty and not all(c in "| " for c in ckey))


def group_duplicates(
    products: list[Product],
    category: str,
) -> dict[str, list[Product]]:
    """
    Сгруппировать товары-дубликаты по категории.
    Сначала ключ по характеристикам (б), при отсутствии — по названию (а).
    """
    fields = DEDUP_FIELDS_TIRES if category == "tires" else DEDUP_FIELDS_WHEELS
    groups: dict[str, list[Product]] = defaultdict(list)

    for p in products:
        if p.category != category:
            continue
        ckey = _chars_key(p, fields)
        if _is_char_key_valid(ckey, len(fields)):
            groups[f"c:{ckey}"].append(p)
        else:
            nkey = _name_key(p)
            groups[f"n:{nkey}"].append(p)

    return dict(groups)


def select_best_from_group(
    products: list[Product],
    require_stock: bool = True,
) -> Optional[Product]:
    """
    Из группы дублей выбрать один: самая дешёвая с остатком.
    В <price> — цена этого товара (минимальная среди доступных).
    Если require_stock и все без остатка — не включать (return None).
    """
    if not products:
        return None
    sorted_by_price = sorted(products, key=lambda x: x.price)
    for p in sorted_by_price:
        if p.quantity > 0:
            return p
    if require_stock:
        return None
    return sorted_by_price[0]


def deduplicate(
    products: list[Product],
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> list[Product]:
    """
    Дедупликация: оставить по одному товару из каждой группы дублей.
    Только товары от active_supplier_ids. Cheapest available.
    """
    if active_supplier_ids is not None:
        if not active_supplier_ids:
            return []
        products = [p for p in products if p.supplier_id in active_supplier_ids]

    result: list[Product] = []
    for category in ("tires", "wheels"):
        cat_products = [p for p in products if p.category == category]
        groups = group_duplicates(cat_products, category)
        for group in groups.values():
            best = select_best_from_group(group, require_stock=require_stock)
            if best:
                result.append(best)

    return result
