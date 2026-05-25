"""
Хранение товаров в SQLite.
"""
import hashlib
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
    PRICE_ROZN REAL DEFAULT 0,
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_supplier_cat_article ON products(supplier_id, category, CML2_ARTICLE);
"""

SURROGATE_ARTICLE_PREFIX = "___det_"


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
            conn.execute("DROP INDEX IF EXISTS idx_products_supplier_article")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "idx_products_supplier_cat_article "
                "ON products(supplier_id, category, CML2_ARTICLE)"
            )
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
            try:
                conn.execute("SELECT PRICE_ROZN FROM products LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(
                    "ALTER TABLE products ADD COLUMN PRICE_ROZN REAL DEFAULT 0"
                )

    def stable_surrogate_article(self, product: Product) -> str:
        """
        Детерминированный surrogate-артикул для позиций без CML2_ARTICLE.
        Не включает price/quantity, чтобы ключ был стабилен между синками.
        """
        parts = [
            product.supplier_id,
            product.category,
            product.PROIZVODITEL,
            product.MODEL_AVTOSHINY,
            product.MODEL_DISKA,
            product.SHIRINA_PROFILYA,
            product.VYSOTA_PROFILYA,
            product.POSADOCHNYY_DIAMETR,
            product.SEZONNOST,
            product.SHIPY,
            product.INDEKS_NAGRUZKI,
            product.INDEKS_SKOROSTI,
            product.HOMOLOGATION,
            product.SHIRINA_DISKA,
            product.POSADOCHNYY_DIAMETR_DISKA,
            product.COUNT_OTVERSTIY,
            product.MEZHBOLTOVOE_RASSTOYANIE,
            product.VYLET_DISKA,
            product.DIAMETR_STUPITSY,
            product.WHEEL_TYPE,
            product.DISK_COLOR,
        ]
        payload = "|".join(str(part or "").strip().lower() for part in parts)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{SURROGATE_ARTICLE_PREFIX}{digest[:16]}"

    def upsert_products(
        self,
        products: list[Product],
        supplier: str,
        supplier_id: str,
        category: str,
    ) -> None:
        """
        Обновить товары поставщика по (supplier_id, category, CML2_ARTICLE).
        Артикулы разных поставщиков могут совпадать — это разные товары, храним оба.
        OS_ARTICLE_ID = os_article_{supplier_id}_{article} — стабильный ID для 1С.
        Удаляются товары, которых больше нет в выгрузке поставщика в рамках категории.
        """
        if not products:
            return
        normalized_rows: list[tuple[dict, str]] = []
        new_articles: set[str] = set()

        for p in products:
            if p.category != category:
                raise ValueError(
                    f"upsert_products expects category={category}, got {p.category}"
                )
            d = p.to_dict()
            article = (p.CML2_ARTICLE or "").strip() or self.stable_surrogate_article(p)
            d["CML2_ARTICLE"] = article
            d["supplier"] = supplier
            d["supplier_id"] = supplier_id
            d["OS_SUPPLIER_TEXT"] = supplier
            d["category"] = category
            d.pop("id", None)
            d["OS_ARTICLE_ID"] = f"os_article_{supplier_id}_{article}"
            normalized_rows.append((d, article))
            new_articles.add(article)

        with self._get_conn() as conn:
            placeholders = ", ".join("?" * len(new_articles))
            conn.execute(
                "DELETE FROM products WHERE supplier_id = ? AND category = ? "
                "AND CML2_ARTICLE NOT IN ("
                + placeholders
                + ")",
                [supplier_id, category] + list(new_articles),
            )
            for d, _article in normalized_rows:
                cols = ", ".join(d.keys())
                ph = ", ".join("?" * len(d))
                conn.execute(
                    f"INSERT OR REPLACE INTO products ({cols}) VALUES ({ph})",
                    list(d.values()),
                )

    def get_all_products(
        self, active_supplier_ids: Optional[list[str]] = None
    ) -> list[Product]:
        """Получить все товары. Если active_supplier_ids задан — только от этих поставщиков."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            if active_supplier_ids is not None:
                if not active_supplier_ids:
                    return []
                placeholders = ", ".join("?" * len(active_supplier_ids))
                rows = conn.execute(
                    f"SELECT * FROM products WHERE supplier_id IN ({placeholders})",
                    active_supplier_ids,
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

    def get_product_by_id(self, product_id: int) -> Optional[Product]:
        """Одна позиция по id или None."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if row is None:
                return None
            return Product.from_dict(dict(row))

    def search_products(
        self,
        q: str,
        category: Optional[str] = None,
        supplier_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Product]:
        """
        Поиск по подстроке (LIKE, без учёта регистра) в CML2_ARTICLE, NAME,
        MODEL_AVTOSHINY, MODEL_DISKA.
        """
        q = (q or "").strip()
        if not q:
            return []
        limit = max(1, min(int(limit), 200))
        pattern = f"%{q}%"
        sql = (
            "SELECT * FROM products WHERE ("
            "LOWER(CML2_ARTICLE) LIKE LOWER(?) OR "
            "LOWER(NAME) LIKE LOWER(?) OR "
            "LOWER(MODEL_AVTOSHINY) LIKE LOWER(?) OR "
            "LOWER(MODEL_DISKA) LIKE LOWER(?)"
            ")"
        )
        params: list[object] = [pattern, pattern, pattern, pattern]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if supplier_id:
            sql += " AND supplier_id = ?"
            params.append(supplier_id)
        sql += " ORDER BY price ASC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            return [Product.from_dict(dict(r)) for r in rows]

    def find_by_article(
        self,
        article: str,
        category: Optional[str] = None,
        supplier_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[Product]:
        """
        Поиск по артикулу: сначала точное совпадение CML2_ARTICLE, затем подстрока.
        """
        article = (article or "").strip()
        if not article:
            return []
        limit = max(1, min(int(limit), 50))

        def _query(extra_sql: str, extra_params: list[object]) -> list[Product]:
            sql = "SELECT * FROM products WHERE " + extra_sql
            params = list(extra_params)
            if category:
                sql += " AND category = ?"
                params.append(category)
            if supplier_id:
                sql += " AND supplier_id = ?"
                params.append(supplier_id)
            sql += " ORDER BY price ASC LIMIT ?"
            params.append(limit)
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, params).fetchall()
                return [Product.from_dict(dict(r)) for r in rows]

        exact = _query("LOWER(CML2_ARTICLE) = LOWER(?)", [article])
        if exact:
            return exact
        pattern = f"%{article}%"
        return _query("LOWER(CML2_ARTICLE) LIKE LOWER(?)", [pattern])
