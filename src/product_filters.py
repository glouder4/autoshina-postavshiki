from __future__ import annotations

import re
import unicodedata

from .models import Product

_OUTLET_CLEARANCE_MARKER = "распродажауценка"


def _normalize_text(value: object) -> str:
    text = str(value or "")
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    # Align with requirement: trim, lowercase and collapse spaces,
    # then check compact marker to catch both with/without spaces.
    collapsed = re.sub(r"\s+", " ", normalized)
    return collapsed.replace(" ", "")


def _is_outlet_clearance_product(product: Product) -> bool:
    for candidate in (
        getattr(product, "PROIZVODITEL", ""),
        getattr(product, "NAME", ""),
    ):
        if _OUTLET_CLEARANCE_MARKER in _normalize_text(candidate):
            return True
    return False

