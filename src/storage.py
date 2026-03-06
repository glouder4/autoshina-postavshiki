"""
Хранение товаров в SQLite.
"""
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from .models import Product

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id TEXT NOT NULL,
    supplier TEXT NOT NULL,
    OS_ARTICLE_ID TEXT DEFAULT '',
    NAME TEXT DEFAULT '',
    category TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    CML2_ARTICLE TEXT DEFAULT '',
    MORE_PHOTO TEXT DEFAULT '',
    PROIZVODITEL TEXT DEFAULT '',
    OS_SUPPLIER_TEXT TEXT DEFAULT '',
    -- Шины
    SHIRINA_PROFILYA TEXT DEFAULT '',
    VYSOTA_PROFILYA TEXT DEFAULT '',
    POSADOCHNYY_DIAMETR TEXT DEFAULT '',
    SEZONNOST TEXT DEFAULT '',
    SHIPY TEXT DEFAULT '',
    INDEKS_NAGRUZKI TEXT DEFAULT '',
    INDEKS_SKOROSTI TEXT DEFAULT '',
    MODEL_AVTOSHINY TEXT DEFAULT '',
    HOMOLOGATION TEXT DEFAULT '',
    -- Диски
    SHIRINA_DISKA TEXT DEFAULT '',
    POSADOCHNYY_DIAMETR_DISKA TEXT DEFAULT '',
    COUNT_OTVERSTIY TEXT DEFAULT '',
    MEZHBOLTOVOE_RASSTOYANIE TEXT DEFAULT '',
    VYLET_DISKA TEXT DEFAULT '',
    DIAMETR_STUPITSY TEXT DEFAULT '',
    WHEEL_TYPE TEXT DEFAULT '',
    MODEL_DISKA TEXT DEFAULT '',
    DISK_COLOR TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_supplier_article ON products(supplier_id, CML2_ARTICLE);
"""


class Storage:
    """Работа с SQLite."""

    def __init__(self, db_path: str | Path = "data/products.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)
        # Миграция: добавить supplier_id если нет (старые БД)
        with self._get_conn() as conn:
            try:
                conn.execute("SELECT supplier_id FROM products LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN supplier_id TEXT DEFAULT ''"
                )
                conn.execute(
                    "UPDATE products SET supplier_id = 'supplier_1' "
                    "WHERE supplier IN ('Поставщик 1', '4tochki')"
                )
                conn.execute(
                    "UPDATE products SET supplier_id = supplier "
                    "WHERE supplier_id = '' OR supplier_id IS NULL"
                )
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_products_supplier_id "
                    "ON products(supplier_id)"
                )
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("SELECT OS_ARTICLE_ID FROM products LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN OS_ARTICLE_ID TEXT DEFAULT ''"
                )
            try:
                conn.execute("SELECT NAME FROM products LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN NAME TEXT DEFAULT ''"
                )

    def upsert_products(
        self, products: list[Product], supplier: str, supplier_id: str
    ) -> None:
        """
        Обновить товары поставщика по (supplier_id, CML2_ARTICLE).
        Артикулы разных поставщиков могут совпадать — это разные товары, храним оба.
        OS_ARTICLE_ID = os_article_{id} — значение поля id в нашей системе.
        """
        if not products:
            return
        import uuid

        new_articles = set()
        for p in products:
            a = p.CML2_ARTICLE
            if not a:
                a = f"___{uuid.uuid4().hex[:8]}"
            new_articles.add(a)

        with self._get_conn() as conn:
            placeholders = ", ".join("?" * len(new_articles))
            conn.execute(
                "DELETE FROM products WHERE supplier_id = ? AND CML2_ARTICLE NOT IN ("
                + placeholders
                + ")",
                [supplier_id] + list(new_articles),
            )
            for p in products:
                d = p.to_dict()
                article = p.CML2_ARTICLE
                if not article:
                    article = f"___{uuid.uuid4().hex[:8]}"
                    d["CML2_ARTICLE"] = article
                d.pop("OS_ARTICLE_ID", None)
                d.pop("id", None)
                cols = ", ".join(d.keys())
                ph = ", ".join("?" * len(d))
                conn.execute(
                    f"INSERT OR REPLACE INTO products ({cols}) VALUES ({ph})",
                    list(d.values()),
                )
                rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "UPDATE products SET OS_ARTICLE_ID = ? WHERE id = ?",
                    (f"os_article_{rid}", rid),
                )

    def get_all_products(
        self, active_suppliers: Optional[list[str]] = None
    ) -> list[Product]:
        """Получить все товары. Если active_suppliers задан — только от этих поставщиков."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            if active_suppliers:
                placeholders = ", ".join("?" * len(active_suppliers))
                rows = conn.execute(
                    f"SELECT * FROM products WHERE supplier IN ({placeholders})",
                    active_suppliers,
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM products").fetchall()
            return [Product.from_dict(dict(r)) for r in rows]

    def delete_supplier_products(self, supplier_id: str) -> None:
        """Удалить все товары поставщика (при отключении)."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM products WHERE supplier_id = ?", (supplier_id,)
            )
        logger.info("Удалены товары поставщика %s", supplier_id)
