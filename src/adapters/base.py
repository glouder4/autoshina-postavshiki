"""
Базовый адаптер для преобразования XML поставщика в единую модель Product.
"""
import re
import logging
from typing import Any, Optional

from lxml import etree

# Опечатка «—» (em dash) в полях с положительными числами. —10 → 10
LEADING_DASH_CLEAN_RE = re.compile(r"^[—–−\-]+(.*)$")

# Поля, где ожидается положительное число — убираем ошибочный минус в начале
NUMERIC_FIELDS = frozenset({
    "SHIRINA_PROFILYA", "VYSOTA_PROFILYA", "POSADOCHNYY_DIAMETR",
    "INDEKS_NAGRUZKI", "INDEKS_SKOROSTI",
    "SHIRINA_DISKA", "POSADOCHNYY_DIAMETR_DISKA",
    "COUNT_OTVERSTIY", "MEZHBOLTOVOE_RASSTOYANIE", "VYLET_DISKA", "DIAMETR_STUPITSY",
})

from ..models import Product

logger = logging.getLogger(__name__)


class BaseAdapter:
    """Адаптер для преобразования XML в Product."""

    def __init__(
        self,
        supplier_id: str,
        supplier_name: str,
        field_mapping: dict[str, str],
        value_transforms: Optional[dict[str, dict[str, str]]] = None,
        quantity_sum_fields: Optional[list[str]] = None,
        price_min_fields: Optional[list[str]] = None,
    ):
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self.field_mapping = field_mapping
        self.value_transforms = value_transforms or {}
        self.quantity_sum_fields = quantity_sum_fields or []
        self.price_min_fields = price_min_fields or []

    def _get_text(self, elem, tag: str) -> str:
        """Получить текст дочернего элемента, атрибута или ключа dict. Поддержка fallback: "field1|field2"."""
        for t in tag.split("|"):
            t = t.strip()
            if not t:
                continue
            if isinstance(elem, dict):
                val = elem.get(t)
                if val is not None and str(val).strip():
                    return str(val).strip()
                continue
            child = elem.find(t)
            if child is not None and child.text:
                return child.text.strip()
            val = elem.get(t)
            if val and val.strip():
                return val.strip()
        return ""

    def _apply_transform(self, field: str, value: str) -> str:
        """Применить value_transforms если есть."""
        if field in NUMERIC_FIELDS:
            m = LEADING_DASH_CLEAN_RE.match(value.strip())
            if m:
                value = m.group(1).strip() or value
        transforms = self.value_transforms.get(field)
        if transforms and value in transforms:
            return transforms[value]
        return value

    def _parse_product_element(self, elem) -> dict[str, Any]:
        """Извлечь данные из XML-элемента по маппингу."""
        result: dict[str, Any] = {}
        for our_field, supplier_field in self.field_mapping.items():
            raw = self._get_text(elem, supplier_field)
            if raw:
                result[our_field] = self._apply_transform(our_field, raw)
            else:
                result[our_field] = ""
        return result

    def _parse_price(self, elem) -> float:
        """Взять минимальную цену по полям price_min_fields (самая дешёвая по складам)."""
        if not self.price_min_fields:
            raw = self._get_text(
                elem,
                self.field_mapping.get("price", ""),
            )
            try:
                return float(raw) if raw else 0.0
            except ValueError:
                return 0.0
        prices: list[float] = []
        for tag in self.price_min_fields:
            raw = self._get_text(elem, tag)
            if raw:
                try:
                    p = float(raw)
                    if p > 0:
                        prices.append(p)
                except ValueError:
                    pass
        return min(prices) if prices else 0.0

    def _parse_quantity(self, elem) -> int:
        """Суммировать остатки по полям quantity_sum_fields. «более 40» → 40."""
        if not self.quantity_sum_fields:
            raw = self._get_text(
                elem,
                self.field_mapping.get("quantity", ""),
            )
            raw = self._apply_transform("quantity", raw) if raw else ""
            try:
                return int(raw) if raw else 0
            except ValueError:
                return 0
        total = 0
        transforms = self.value_transforms.get("quantity", {})
        for tag in self.quantity_sum_fields:
            raw = self._get_text(elem, tag)
            if raw:
                raw = transforms.get(raw, raw)
            try:
                total += int(raw) if raw else 0
            except ValueError:
                pass
        return total

    def parse_product(self, elem, category: str) -> Optional[Product]:
        """
        Преобразовать XML-элемент в Product.
        Возвращает None при ошибке (логируем и пропускаем).
        """
        try:
            data = self._parse_product_element(elem)
            price = self._parse_price(elem)
            quantity = self._parse_quantity(elem)
            supplier = data.get("OS_SUPPLIER_TEXT") or self.supplier_name

            p = Product(
                supplier_id=self.supplier_id,
                supplier=supplier,
                category=category,
                price=price,
                quantity=quantity,
                OS_SUPPLIER_TEXT=supplier,
            )
            for k, v in data.items():
                if k in ("price", "quantity", "supplier", "OS_SUPPLIER_TEXT"):
                    continue
                if hasattr(p, k):
                    setattr(p, k, str(v) if v else "")
            return p
        except Exception as e:
            logger.warning(
                "Ошибка парсинга товара у %s: %s", self.supplier_id, e, exc_info=True
            )
            return None
