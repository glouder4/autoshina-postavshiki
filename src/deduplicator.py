"""
Дедупликация товаров: по косвенным признакам и по названию.
Группировка выполняется отдельно по категории (tires/wheels).
"""
import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import Optional

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
    "DISK_COLOR",
]


def _canonicalize_base(value: str) -> str:
    """Базовая канонизация: unicode normalize, lowercase, унификация разделителей."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value)).lower().strip()
    # Приводим типовые разделители/пунктуацию к пробелу, чтобы "x-ice" == "x ice".
    value = re.sub(r"[-_/\\.,;:+()]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def canonicalize_brand(value: str) -> str:
    """Канонизация бренда с ограниченным набором alias/translit."""
    norm = _canonicalize_base(value)
    aliases = {
        "пирелли": "pirelli",
        "bfg": "bfgoodrich",
        "bf goodrich": "bfgoodrich",
    }
    return aliases.get(norm, norm)


def canonicalize_model(value: str) -> str:
    """Канонизация модели (унификация разделителей/пунктуации)."""
    return _canonicalize_base(value)


def canonicalize_name(value: str) -> str:
    """Канонизация name/model ключа для fallback-дедупликации."""
    return _canonicalize_base(value)


def canonicalize_tire_posadochnyy_diametr(raw: str) -> str:
    """
    Для ключа дедупликации: та же нормализация, что при экспорте (16/R16/zr17),
    плюс ZR→R в полном размере (55zr17 -> 55r17). Сырые данные Product не меняет.
    """
    from .export import _normalize_tire_diameter

    s = unicodedata.normalize("NFKC", str(raw or "")).strip()
    s = re.sub(r"\s+", "", s)
    s = _normalize_tire_diameter(s).lower()
    if "/" in s:
        s = re.sub(r"zr(\d{1,2}\b)", r"r\1", s)
    return s


def canonicalize_wheel_rim_size(raw: str) -> str:
    """
    Ведущий целой дюйм обода: «16 / 7j» и «16» -> «16». Только для ключа дедупликации.
    """
    s = unicodedata.normalize("NFKC", str(raw or "")).strip().lower()
    s = re.sub(r"\s+", " ", s)
    m = re.match(r"^(\d{1,2})\s*/", s)
    if m:
        return m.group(1)
    m2 = re.match(r"^(\d{1,2})\s*$", s)
    if m2:
        return m2.group(1)
    m3 = re.match(r"^(\d{1,2})\s*j\b", s)
    if m3:
        return m3.group(1)
    return re.sub(r"\s+", "", s)


def _name_key(product: Product) -> str:
    """Ключ по названию (модель)."""
    name = ""
    if product.category == "tires":
        name = product.MODEL_AVTOSHINY or product.CML2_ARTICLE
    else:
        name = product.MODEL_DISKA or product.CML2_ARTICLE
    return hashlib.md5(canonicalize_name(name).encode()).hexdigest()


def _chars_key(product: Product, fields: list[str]) -> str:
    """Ключ по набору характеристик."""
    parts = []
    for f in fields:
        val = getattr(product, f, "")
        raw = str(val or "")
        if f == "PROIZVODITEL":
            parts.append(canonicalize_brand(raw))
        elif f in ("MODEL_AVTOSHINY", "MODEL_DISKA"):
            parts.append(canonicalize_model(raw))
        elif f == "POSADOCHNYY_DIAMETR":
            parts.append(canonicalize_tire_posadochnyy_diametr(raw))
        elif f in ("SHIRINA_DISKA", "POSADOCHNYY_DIAMETR_DISKA"):
            parts.append(canonicalize_wheel_rim_size(raw))
        else:
            parts.append(raw.strip().lower())
    return "|".join(parts)


def _normalized_article(product: Product) -> str:
    """Нормализованный артикул для приоритетной дедупликации."""
    return str(product.CML2_ARTICLE or "").strip().lower()


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
    OR-семантика ключей:
    - legacy ключ: характеристики (если валидны), иначе название;
    - дополнительный ключ: валидный CML2_ARTICLE.
    Позиции объединяются в одну группу, если совпал любой ключ.
    """
    fields = DEDUP_FIELDS_TIRES if category == "tires" else DEDUP_FIELDS_WHEELS
    cat_products = [p for p in products if p.category == category]
    if not cat_products:
        return {}

    parent = list(range(len(cat_products)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    key_to_first_idx: dict[str, int] = {}
    for idx, p in enumerate(cat_products):
        keys: list[str] = []
        ckey = _chars_key(p, fields)
        if _is_char_key_valid(ckey, len(fields)):
            keys.append(f"c:{ckey}")
        else:
            keys.append(f"n:{_name_key(p)}")

        article = _normalized_article(p)
        if article:
            keys.append(f"a:{article}")

        for key in keys:
            first_idx = key_to_first_idx.get(key)
            if first_idx is None:
                key_to_first_idx[key] = idx
            else:
                union(idx, first_idx)

    groups: dict[int, list[Product]] = defaultdict(list)
    for idx, p in enumerate(cat_products):
        groups[find(idx)].append(p)

    # Стабильные текстовые ключи групп для совместимого внешнего контракта.
    return {f"g:{i}": group for i, group in enumerate(groups.values())}


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
