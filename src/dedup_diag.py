"""
Диагностика дедупликации и воронки экспорта (UI /api/diag).
Переиспользует deduplicator и export без дублирования логики.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .config import load_suppliers_config
from .deduplicator import deduplicate, group_duplicates, select_best_from_group
from .export import compute_export_dedup_stats, get_export_products
from .models import Product
from .storage import Storage

# Статусы позиции в цепочке «БД → дедуп → price/qty → экспорт»
STATUS_INACTIVE_SUPPLIER = "inactive_supplier"
STATUS_EXPORT_WINNER = "export_winner"
STATUS_DEDUP_LOSER = "dedup_loser"
STATUS_DEDUP_GROUP_DROPPED = "dedup_group_dropped"
STATUS_PRICE_QTY_FILTER = "price_qty_filter"
STATUS_UNIQUE_IN_EXPORT = "unique_in_export"

EXPORT_STATUSES = (
    STATUS_INACTIVE_SUPPLIER,
    STATUS_EXPORT_WINNER,
    STATUS_DEDUP_LOSER,
    STATUS_DEDUP_GROUP_DROPPED,
    STATUS_PRICE_QTY_FILTER,
    STATUS_UNIQUE_IN_EXPORT,
)

STATUS_LABELS_RU: dict[str, str] = {
    STATUS_INACTIVE_SUPPLIER: "Поставщик неактивен",
    STATUS_EXPORT_WINNER: "Победитель дедупа (в экспорте)",
    STATUS_DEDUP_LOSER: "Проиграл дедуп (в БД, нет в экспорте)",
    STATUS_DEDUP_GROUP_DROPPED: "Группа без остатка",
    STATUS_PRICE_QTY_FILTER: "Отсечён по цене/остатку",
    STATUS_UNIQUE_IN_EXPORT: "Единственный в группе (в экспорте)",
}


def status_label_ru(status: str) -> str:
    """Человекочитаемая подпись статуса для UI."""
    return STATUS_LABELS_RU.get(status, status)


def scoped_group_key(category: str, raw_key: str) -> str:
    """Ключ группы с префиксом категории (tires:g:0), без коллизий tires/wheels."""
    return f"{category}:{raw_key}"


def active_supplier_ids_from_config(config: Optional[dict] = None) -> list[str]:
    """Id поставщиков с active: true из config/suppliers.yaml."""
    cfg = config or load_suppliers_config()
    return [s["id"] for s in cfg.get("suppliers", []) if s.get("active", True)]


def _passes_price_qty(p: Product) -> bool:
    return p.price > 0 and p.quantity > 0


def build_export_pipeline_context(
    storage: Storage,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> dict[str, Any]:
    """
    Предрасчёт групп дедупа и победителей для classify / group / funnel.
    Ключ product_id → статус и метаданные группы.
    """
    cfg_active = active_supplier_ids
    if cfg_active is None:
        cfg_active = active_supplier_ids_from_config()
    active_set = set(cfg_active)

    all_products = storage.get_all_products(active_supplier_ids=None)
    by_id: dict[int, Product] = {
        int(p.id): p for p in all_products if p.id is not None
    }

    product_status: dict[int, str] = {}
    product_group_key: dict[int, str] = {}
    groups_by_key: dict[str, list[Product]] = {}

    for category in ("tires", "wheels"):
        cat_all = [p for p in all_products if p.category == category]
        grouped = group_duplicates(cat_all, category)
        for gkey, group in grouped.items():
            scoped_key = scoped_group_key(category, gkey)
            for p in group:
                if p.id is not None:
                    product_group_key[int(p.id)] = scoped_key
            groups_by_key[scoped_key] = group

            inactive_members = [p for p in group if p.supplier_id not in active_set]
            active_members = [p for p in group if p.supplier_id in active_set]

            for p in inactive_members:
                if p.id is not None:
                    product_status[int(p.id)] = STATUS_INACTIVE_SUPPLIER

            if not active_members:
                continue

            best = select_best_from_group(active_members, require_stock=require_stock)
            multi = len(active_members) > 1

            if best is None:
                for p in active_members:
                    if p.id is not None and int(p.id) not in product_status:
                        product_status[int(p.id)] = STATUS_DEDUP_GROUP_DROPPED
                continue

            best_id = int(best.id) if best.id is not None else None
            for p in active_members:
                pid = int(p.id) if p.id is not None else None
                if pid is None or pid in product_status:
                    continue
                if pid != best_id:
                    product_status[pid] = STATUS_DEDUP_LOSER
                    continue
                if not _passes_price_qty(p):
                    product_status[pid] = STATUS_PRICE_QTY_FILTER
                elif multi:
                    product_status[pid] = STATUS_EXPORT_WINNER
                else:
                    product_status[pid] = STATUS_UNIQUE_IN_EXPORT

    export_ids = {
        int(p.id)
        for p in get_export_products(
            storage,
            active_supplier_ids=cfg_active,
            require_stock=require_stock,
        )
        if p.id is not None
    }

    return {
        "active_supplier_ids": list(cfg_active),
        "by_id": by_id,
        "product_status": product_status,
        "product_group_key": product_group_key,
        "groups_by_key": groups_by_key,
        "export_ids": export_ids,
    }


def classify_product_in_export_pipeline(
    product: Product,
    storage: Storage,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
    context: Optional[dict[str, Any]] = None,
) -> str:
    """Статус одной позиции в цепочке экспорта (см. EXPORT_STATUSES)."""
    ctx = context or build_export_pipeline_context(
        storage,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )
    if product.id is None:
        if product.supplier_id not in set(ctx["active_supplier_ids"]):
            return STATUS_INACTIVE_SUPPLIER
        return STATUS_UNIQUE_IN_EXPORT
    pid = int(product.id)
    return ctx["product_status"].get(pid, STATUS_UNIQUE_IN_EXPORT)


def product_to_diag_dict(product: Product, status: str) -> dict[str, Any]:
    """Сериализация товара для JSON API."""
    d = product.to_dict()
    d["id"] = product.id
    d["export_status"] = status
    d["export_status_label"] = status_label_ru(status)
    model = (
        product.MODEL_AVTOSHINY
        if product.category == "tires"
        else product.MODEL_DISKA
    )
    d["display_model"] = model or product.NAME or product.CML2_ARTICLE
    return d


def get_product_diag(
    storage: Storage,
    product_id: int,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> Optional[dict[str, Any]]:
    """Деталь одной позиции или None."""
    product = storage.get_product_by_id(product_id)
    if product is None:
        return None
    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )
    status = classify_product_in_export_pipeline(
        product, storage, active_supplier_ids, require_stock, context=ctx
    )
    gkey = ctx["product_group_key"].get(product_id)
    in_export = product_id in ctx["export_ids"]
    return {
        **product_to_diag_dict(product, status),
        "group_key": gkey,
        "in_export": in_export,
        "group_size": len(ctx["groups_by_key"].get(gkey, [product])),
    }


def get_group_diag(
    storage: Storage,
    product_id: int,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> Optional[dict[str, Any]]:
    """Группа дублей, содержащая product_id."""
    product = storage.get_product_by_id(product_id)
    if product is None:
        return None
    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )
    gkey = ctx["product_group_key"].get(product_id)
    if not gkey:
        grouped = group_duplicates(
            [p for p in storage.get_all_products() if p.category == product.category],
            product.category,
        )
        for key, grp in grouped.items():
            if any(p.id == product_id for p in grp):
                gkey = scoped_group_key(product.category, key)
                members = grp
                break
        else:
            members = [product]
            gkey = scoped_group_key(product.category, "g:single")
    else:
        members = ctx["groups_by_key"].get(gkey, [product])

    best = select_best_from_group(
        [p for p in members if p.supplier_id in set(ctx["active_supplier_ids"])],
        require_stock=require_stock,
    )
    best_id = int(best.id) if best and best.id is not None else None

    items = []
    export_winner_item: Optional[dict[str, Any]] = None
    for p in members:
        pid = int(p.id) if p.id is not None else None
        st = ctx["product_status"].get(pid, STATUS_UNIQUE_IN_EXPORT) if pid else STATUS_UNIQUE_IN_EXPORT
        in_export = pid in ctx["export_ids"] if pid else False
        item = {
            **product_to_diag_dict(p, st),
            "is_group_best": pid == best_id,
            "in_export": in_export,
            "is_export_winner": in_export,
        }
        if in_export and export_winner_item is None:
            export_winner_item = item
        items.append(item)
    items.sort(key=lambda x: (not x.get("is_export_winner"), not x.get("is_group_best"), x.get("price", 0)))

    return {
        "group_key": gkey,
        "category": product.category,
        "size": len(members),
        "best_product_id": best_id,
        "export_winner": export_winner_item,
        "export_winner_in_xml": export_winner_item is not None,
        "members": items,
    }


def lookup_by_article(
    storage: Storage,
    article: str,
    category: Optional[str] = None,
    supplier_id: Optional[str] = None,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
) -> dict[str, Any]:
    """
    Поиск по артикулу: для каждой группы дедупа — победитель экспорта и все схлопнувшиеся позиции.
    """
    article = (article or "").strip()
    if not article:
        return {"found": False, "article": "", "groups": []}

    matches = storage.find_by_article(article, category=category, supplier_id=supplier_id)
    if not matches:
        return {"found": False, "article": article, "groups": []}

    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=active_supplier_ids,
        require_stock=require_stock,
    )

    groups_out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for p in matches:
        if p.id is None:
            continue
        pid = int(p.id)
        gkey = ctx["product_group_key"].get(pid)
        if not gkey or gkey in seen_keys:
            continue
        seen_keys.add(gkey)

        group_data = get_group_diag(
            storage,
            pid,
            active_supplier_ids=active_supplier_ids,
            require_stock=require_stock,
        )
        if group_data is None:
            continue

        queried_ids = {
            int(m.id)
            for m in matches
            if m.id is not None and ctx["product_group_key"].get(int(m.id)) == gkey
        }
        members = []
        for m in group_data["members"]:
            row = dict(m)
            row["is_queried_article"] = row.get("id") in queried_ids
            members.append(row)

        queried_products = [
            product_to_diag_dict(
                m,
                ctx["product_status"].get(int(m.id), STATUS_UNIQUE_IN_EXPORT),
            )
            for m in matches
            if m.id is not None and int(m.id) in queried_ids
        ]

        groups_out.append(
            {
                "group_key": group_data["group_key"],
                "category": group_data["category"],
                "size": group_data["size"],
                "export_winner": group_data.get("export_winner"),
                "export_winner_in_xml": group_data.get("export_winner_in_xml", False),
                "queried_products": queried_products,
                "members": members,
            }
        )

    return {
        "found": bool(groups_out),
        "article": article,
        "groups": groups_out,
    }


def get_sync_category_ingestion(
    supplier_id: str,
    category: str,
    sync_state_path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """
    Статистика последней загрузки из data/sync_state.json (сырой фид → БД).
    Ключ категории: «supplier_3|tires».
    """
    if sync_state_path is None:
        return None
    path = Path(sync_state_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get("categories", {}).get(f"{supplier_id}|{category}")
    if not entry:
        return None
    raw = int(entry.get("raw_items") or 0)
    accepted = int(entry.get("accepted") or 0)
    filtered = int(entry.get("filtered_out") or 0)
    saved = int(entry.get("products_saved") or accepted)
    return {
        "outcome": entry.get("outcome"),
        "detail": entry.get("detail") or "",
        "raw_items_in_feed": raw,
        "accepted_by_adapter": accepted,
        "filtered_out_at_load": filtered,
        "products_saved_to_db": saved,
        "sync_updated_at": data.get("updated_at"),
    }


def list_supplier_products_by_status(
    storage: Storage,
    supplier_id: str,
    category: str,
    status: Optional[str] = None,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Список позиций поставщика с фильтром по статусу (для просмотра dedup_loser и т.д.)."""
    if category not in ("tires", "wheels"):
        raise ValueError("category must be tires or wheels")
    if status is not None and status not in EXPORT_STATUSES:
        raise ValueError(f"status must be one of {EXPORT_STATUSES}")

    cfg_active = active_supplier_ids
    if cfg_active is None:
        cfg_active = active_supplier_ids_from_config()

    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=cfg_active,
        require_stock=require_stock,
    )

    supplier_products = [
        p
        for p in storage.get_all_products()
        if p.supplier_id == supplier_id and p.category == category and p.id is not None
    ]

    items: list[dict[str, Any]] = []
    for p in supplier_products:
        st = ctx["product_status"].get(int(p.id), STATUS_UNIQUE_IN_EXPORT)
        if status is not None and st != status:
            continue
        pid = int(p.id)
        items.append(
            {
                **product_to_diag_dict(p, st),
                "in_export": pid in ctx["export_ids"],
                "group_size": len(
                    ctx["groups_by_key"].get(
                        ctx["product_group_key"].get(pid, ""), [p]
                    )
                ),
            }
        )

    items.sort(key=lambda x: (x.get("export_status", ""), x.get("price", 0)))
    total = len(items)
    page = items[offset : offset + limit]

    return {
        "supplier_id": supplier_id,
        "category": category,
        "status_filter": status,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": page,
    }


def _supplier_funnel_from_context(
    ctx: dict[str, Any],
    storage: Storage,
    supplier_id: str,
    category: str,
    supplier_active: bool,
    sync_state_path: Optional[Path] = None,
    global_stats: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Воронка одного поставщика по уже построенному контексту дедупа."""
    supplier_products = [
        p
        for p in storage.get_all_products()
        if p.supplier_id == supplier_id and p.category == category and p.id is not None
    ]

    counts = {s: 0 for s in EXPORT_STATUSES}
    counts_ru: dict[str, int] = {}
    for p in supplier_products:
        st = ctx["product_status"].get(int(p.id), STATUS_UNIQUE_IN_EXPORT)
        counts[st] = counts.get(st, 0) + 1
    for code, n in counts.items():
        if n:
            counts_ru[status_label_ru(code)] = n

    in_export = sum(
        1 for p in supplier_products if int(p.id) in ctx["export_ids"]
    )
    ingestion = get_sync_category_ingestion(supplier_id, category, sync_state_path)

    result: dict[str, Any] = {
        "supplier_id": supplier_id,
        "category": category,
        "supplier_active": supplier_active,
        "rows_in_db": len(supplier_products),
        "status_counts": counts,
        "status_counts_ru": counts_ru,
        "in_export": in_export,
        "dedup_losers": counts.get(STATUS_DEDUP_LOSER, 0),
        "ingestion": ingestion,
    }
    if global_stats is not None:
        result["export_dedup_stats"] = global_stats
        result["status_labels_ru"] = STATUS_LABELS_RU
    return result


def compute_supplier_funnel(
    storage: Storage,
    supplier_id: str,
    category: str,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
    sync_state_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Воронка по одному поставщику и категории: счётчики по статусам + общая статистика дедупа.
    """
    if category not in ("tires", "wheels"):
        raise ValueError("category must be tires or wheels")

    cfg_active = active_supplier_ids
    if cfg_active is None:
        cfg_active = active_supplier_ids_from_config()
    supplier_active = supplier_id in set(cfg_active)

    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=cfg_active,
        require_stock=require_stock,
    )

    global_stats = compute_export_dedup_stats(
        storage,
        active_supplier_ids=cfg_active,
        require_stock=require_stock,
    )

    return _supplier_funnel_from_context(
        ctx,
        storage,
        supplier_id,
        category,
        supplier_active,
        sync_state_path,
        global_stats=global_stats,
    )


def compute_all_suppliers_funnel(
    storage: Storage,
    category: str,
    active_supplier_ids: Optional[list[str]] = None,
    require_stock: bool = True,
    sync_state_path: Optional[Path] = None,
    config: Optional[dict] = None,
) -> dict[str, Any]:
    """Сводная воронка по всем поставщикам из конфига для одной категории."""
    if category not in ("tires", "wheels"):
        raise ValueError("category must be tires or wheels")

    cfg = config or load_suppliers_config()
    suppliers_cfg = cfg.get("suppliers", [])
    cfg_active = active_supplier_ids
    if cfg_active is None:
        cfg_active = active_supplier_ids_from_config(cfg)
    active_set = set(cfg_active)

    ctx = build_export_pipeline_context(
        storage,
        active_supplier_ids=cfg_active,
        require_stock=require_stock,
    )
    global_stats = compute_export_dedup_stats(
        storage,
        active_supplier_ids=cfg_active,
        require_stock=require_stock,
    )

    rows: list[dict[str, Any]] = []
    for s in suppliers_cfg:
        sid = s["id"]
        row = _supplier_funnel_from_context(
            ctx,
            storage,
            sid,
            category,
            sid in active_set,
            sync_state_path,
        )
        row["supplier_name"] = s.get("name", sid)
        rows.append(row)

    return {
        "category": category,
        "suppliers": rows,
        "export_dedup_stats": global_stats,
        "status_labels_ru": STATUS_LABELS_RU,
    }
