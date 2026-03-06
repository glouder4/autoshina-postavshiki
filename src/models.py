"""
Единая модель товара для шин и дисков.
Адаптеры маппят поля поставщика в эти имена.
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Product:
    """Товар после нормализации (шина или диск)."""

    # Обязательные поля
    supplier_id: str  # стабильный ключ (supplier_1), для удаления при обновлении
    supplier: str  # отображаемое имя (4tochki)
    category: str  # "tires" | "wheels"
    price: float
    quantity: int

    # Общие
    NAME: str = ""  # Название товара (от поставщика или сформированное)
    CML2_ARTICLE: str = ""
    OS_ARTICLE_ID: str = ""  # наш ID: os_article_{supplier_id}_{article}
    MORE_PHOTO: str = ""
    PROIZVODITEL: str = ""
    OS_SUPPLIER_TEXT: str = ""

    # Шины
    SHIRINA_PROFILYA: str = ""
    VYSOTA_PROFILYA: str = ""
    POSADOCHNYY_DIAMETR: str = ""
    SEZONNOST: str = ""
    SHIPY: str = ""
    INDEKS_NAGRUZKI: str = ""
    INDEKS_SKOROSTI: str = ""
    MODEL_AVTOSHINY: str = ""
    HOMOLOGATION: str = ""

    # Диски
    SHIRINA_DISKA: str = ""
    POSADOCHNYY_DIAMETR_DISKA: str = ""
    COUNT_OTVERSTIY: str = ""
    MEZHBOLTOVOE_RASSTOYANIE: str = ""
    VYLET_DISKA: str = ""
    DIAMETR_STUPITSY: str = ""
    WHEEL_TYPE: str = ""
    MODEL_DISKA: str = ""
    DISK_COLOR: str = ""

    # Внутренний ID (генерируется при сохранении)
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Преобразование в словарь для SQLite."""
        d: dict[str, Any] = {
            "supplier_id": self.supplier_id,
            "supplier": self.supplier,
            "category": self.category,
            "price": self.price,
            "quantity": self.quantity,
            "NAME": self.NAME,
            "CML2_ARTICLE": self.CML2_ARTICLE,
            "OS_ARTICLE_ID": self.OS_ARTICLE_ID,
            "MORE_PHOTO": self.MORE_PHOTO,
            "PROIZVODITEL": self.PROIZVODITEL,
            "OS_SUPPLIER_TEXT": self.OS_SUPPLIER_TEXT,
        }
        if self.category == "tires":
            d.update(
                {
                    "SHIRINA_PROFILYA": self.SHIRINA_PROFILYA,
                    "VYSOTA_PROFILYA": self.VYSOTA_PROFILYA,
                    "POSADOCHNYY_DIAMETR": self.POSADOCHNYY_DIAMETR,
                    "SEZONNOST": self.SEZONNOST,
                    "SHIPY": self.SHIPY,
                    "INDEKS_NAGRUZKI": self.INDEKS_NAGRUZKI,
                    "INDEKS_SKOROSTI": self.INDEKS_SKOROSTI,
                    "MODEL_AVTOSHINY": self.MODEL_AVTOSHINY,
                    "HOMOLOGATION": self.HOMOLOGATION,
                }
            )
        else:
            d.update(
                {
                    "SHIRINA_DISKA": self.SHIRINA_DISKA,
                    "POSADOCHNYY_DIAMETR_DISKA": self.POSADOCHNYY_DIAMETR_DISKA,
                    "COUNT_OTVERSTIY": self.COUNT_OTVERSTIY,
                    "MEZHBOLTOVOE_RASSTOYANIE": self.MEZHBOLTOVOE_RASSTOYANIE,
                    "VYLET_DISKA": self.VYLET_DISKA,
                    "DIAMETR_STUPITSY": self.DIAMETR_STUPITSY,
                    "WHEEL_TYPE": self.WHEEL_TYPE,
                    "MODEL_DISKA": self.MODEL_DISKA,
                    "DISK_COLOR": self.DISK_COLOR,
                }
            )
        if self.id is not None:
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Product":
        """Создание из словаря (из SQLite)."""
        p = cls(
            supplier_id=d.get("supplier_id", d.get("supplier", "")),
            supplier=d["supplier"],
            category=d["category"],
            price=float(d["price"]),
            quantity=int(d["quantity"]),
            NAME=d.get("NAME", ""),
            CML2_ARTICLE=d.get("CML2_ARTICLE", ""),
            OS_ARTICLE_ID=d.get("OS_ARTICLE_ID", ""),
            MORE_PHOTO=d.get("MORE_PHOTO", ""),
            PROIZVODITEL=d.get("PROIZVODITEL", ""),
            OS_SUPPLIER_TEXT=d.get("OS_SUPPLIER_TEXT", ""),
        )
        if d.get("id"):
            p.id = int(d["id"])
        if p.category == "tires":
            p.SHIRINA_PROFILYA = d.get("SHIRINA_PROFILYA", "")
            p.VYSOTA_PROFILYA = d.get("VYSOTA_PROFILYA", "")
            p.POSADOCHNYY_DIAMETR = d.get("POSADOCHNYY_DIAMETR", "")
            p.SEZONNOST = d.get("SEZONNOST", "")
            p.SHIPY = d.get("SHIPY", "")
            p.INDEKS_NAGRUZKI = d.get("INDEKS_NAGRUZKI", "")
            p.INDEKS_SKOROSTI = d.get("INDEKS_SKOROSTI", "")
            p.MODEL_AVTOSHINY = d.get("MODEL_AVTOSHINY", "")
            p.HOMOLOGATION = d.get("HOMOLOGATION", "")
        else:
            p.SHIRINA_DISKA = d.get("SHIRINA_DISKA", "")
            p.POSADOCHNYY_DIAMETR_DISKA = d.get("POSADOCHNYY_DIAMETR_DISKA", "")
            p.COUNT_OTVERSTIY = d.get("COUNT_OTVERSTIY", "")
            p.MEZHBOLTOVOE_RASSTOYANIE = d.get("MEZHBOLTOVOE_RASSTOYANIE", "")
            p.VYLET_DISKA = d.get("VYLET_DISKA", "")
            p.DIAMETR_STUPITSY = d.get("DIAMETR_STUPITSY", "")
            p.WHEEL_TYPE = d.get("WHEEL_TYPE", "")
            p.MODEL_DISKA = d.get("MODEL_DISKA", "")
            p.DISK_COLOR = d.get("DISK_COLOR", "")
        return p
