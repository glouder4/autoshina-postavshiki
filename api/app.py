"""
FastAPI приложение: экспорт XML, health/ready, диагностика дедупликации (/api/diag, /ui).

Запуск из корня проекта: uvicorn api.app:app — каталог текущего процесса должен содержать пакеты api/ и src/.
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from src.config import load_suppliers_config
from src.dedup_diag import (
    EXPORT_STATUSES,
    active_supplier_ids_from_config,
    build_export_pipeline_context,
    classify_product_in_export_pipeline,
    compute_all_suppliers_funnel,
    compute_supplier_funnel,
    get_group_diag,
    get_product_diag,
    list_supplier_products_by_status,
    lookup_by_article,
    product_to_diag_dict,
    status_label_ru,
)
from src.export import generate_export_xml
from src.storage import Storage
from src.sync_state import default_sync_state_path, load_sync_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Autoshina Postavshiki", version="0.1.0")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "suppliers.yaml"
DB_PATH = PROJECT_ROOT / "data" / "products.db"
SYNC_STATE_PATH = default_sync_state_path(PROJECT_ROOT)
DIAG_UI_PATH = Path(__file__).resolve().parent / "static" / "diag_ui.html"


def _storage() -> Storage:
    return Storage(DB_PATH)


def _active_supplier_ids() -> list[str]:
    return active_supplier_ids_from_config(load_suppliers_config(CONFIG_PATH))


@app.get("/health")
def health():
    """Liveness: процесс отвечает."""
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    """
    Readiness: конфиг валиден и последний цикл синка завершился без фатальной ошибки.
    До первого успешного run_sync файл sync_state может отсутствовать — сервис не готов.
    """
    st = load_sync_state(SYNC_STATE_PATH)
    if st is None:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "reason": "sync_state отсутствует — синхронизация ещё не выполнялась",
            },
        )
    if not st.config_valid:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "reason": "конфигурация не прошла валидацию",
                "detail": st.config_error,
            },
        )
    if not st.sync_finished_ok:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "reason": "последняя синхронизация неуспешна (исключение или ошибка загрузки категории)",
                "detail": st.sync_error,
                "had_category_load_errors": st.had_category_load_errors,
            },
        )
    return {
        "ready": True,
        "updated_at": st.updated_at,
        "categories": st.categories,
    }


@app.get("/export/tires.xml")
def get_tires_xml():
    """XML только шины."""
    try:
        xml_bytes = generate_export_xml(
            db_path=DB_PATH,
            config_path=CONFIG_PATH,
            require_stock=True,
            category="tires",
        )
        return Response(
            content=xml_bytes,
            media_type="application/xml",
            headers={"Content-Disposition": "inline; filename=tires.xml"},
        )
    except Exception as e:
        logger.exception("Ошибка генерации tires.xml: %s", e)
        return Response(content=f"Error: {e}".encode(), status_code=500)


@app.get("/export/wheels.xml")
def get_wheels_xml():
    """XML только диски."""
    try:
        xml_bytes = generate_export_xml(
            db_path=DB_PATH,
            config_path=CONFIG_PATH,
            require_stock=True,
            category="wheels",
        )
        return Response(
            content=xml_bytes,
            media_type="application/xml",
            headers={"Content-Disposition": "inline; filename=wheels.xml"},
        )
    except Exception as e:
        logger.exception("Ошибка генерации wheels.xml: %s", e)
        return Response(content=f"Error: {e}".encode(), status_code=500)


# --- Диагностика дедупликации (без аутентификации — только локальная отладка) ---


@app.get("/ui")
def diag_ui():
    """HTML-интерфейс отладки дедупликации."""
    if not DIAG_UI_PATH.is_file():
        raise HTTPException(status_code=404, detail="diag_ui.html не найден")
    return FileResponse(DIAG_UI_PATH, media_type="text/html; charset=utf-8")


@app.get("/api/diag/lookup")
def diag_lookup(
    article: str = Query(..., min_length=1),
    category: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
):
    """
    Поиск по артикулу: основной товар в экспорте + все позиции группы дедупа.
    """
    return lookup_by_article(
        _storage(),
        article,
        category=category,
        supplier_id=supplier_id,
        active_supplier_ids=_active_supplier_ids(),
    )


@app.get("/api/diag/search")
def diag_search(
    q: str = Query("", min_length=0),
    category: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Поиск товаров с классификацией статуса в цепочке экспорта."""
    if status is not None and status not in EXPORT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status: одно из {list(EXPORT_STATUSES)}",
        )
    storage = _storage()
    active = _active_supplier_ids()
    ctx = build_export_pipeline_context(storage, active_supplier_ids=active)

    if not (q or "").strip():
        if supplier_id and status:
            data = list_supplier_products_by_status(
                storage,
                supplier_id,
                category or "tires",
                status=status,
                active_supplier_ids=active,
                limit=limit,
            )
            return {
                "q": "",
                "count": len(data["items"]),
                "total": data["total"],
                "items": data["items"],
            }
        raise HTTPException(
            status_code=400,
            detail="укажите q или пару supplier_id + status",
        )

    products = storage.search_products(q, category=category, supplier_id=supplier_id, limit=limit)
    items = []
    for p in products:
        st = classify_product_in_export_pipeline(
            p, storage, active_supplier_ids=active, context=ctx
        )
        if status is not None and st != status:
            continue
        items.append(product_to_diag_dict(p, st))
    return {"q": q, "count": len(items), "items": items}


@app.get("/api/diag/product/{product_id}")
def diag_product(product_id: int):
    """Деталь позиции и статус в экспортной цепочке."""
    data = get_product_diag(
        _storage(),
        product_id,
        active_supplier_ids=_active_supplier_ids(),
    )
    if data is None:
        raise HTTPException(status_code=404, detail="товар не найден")
    return data


@app.get("/api/diag/group")
def diag_group(product_id: int = Query(..., ge=1)):
    """Группа дублей для product_id."""
    data = get_group_diag(
        _storage(),
        product_id,
        active_supplier_ids=_active_supplier_ids(),
    )
    if data is None:
        raise HTTPException(status_code=404, detail="товар не найден")
    return data


@app.get("/api/diag/suppliers")
def diag_suppliers():
    """Список поставщиков из конфига."""
    cfg = load_suppliers_config(CONFIG_PATH)
    suppliers = [
        {
            "id": s["id"],
            "name": s.get("name", s["id"]),
            "active": s.get("active", True),
        }
        for s in cfg.get("suppliers", [])
    ]
    return {"suppliers": suppliers, "active_ids": _active_supplier_ids()}


@app.get("/api/diag/suppliers/summary")
def diag_all_suppliers_summary(
    category: str = Query("tires"),
):
    """Сводная воронка по всем поставщикам для категории."""
    if category not in ("tires", "wheels"):
        raise HTTPException(status_code=400, detail="category: tires или wheels")
    try:
        return compute_all_suppliers_funnel(
            _storage(),
            category,
            active_supplier_ids=_active_supplier_ids(),
            sync_state_path=SYNC_STATE_PATH,
            config=load_suppliers_config(CONFIG_PATH),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/diag/supplier/{supplier_id}/summary")
def diag_supplier_summary(
    supplier_id: str,
    category: str = Query("tires"),
):
    """Воронка поставщика по категории."""
    if category not in ("tires", "wheels"):
        raise HTTPException(status_code=400, detail="category: tires или wheels")
    try:
        return compute_supplier_funnel(
            _storage(),
            supplier_id,
            category,
            active_supplier_ids=_active_supplier_ids(),
            sync_state_path=SYNC_STATE_PATH,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/diag/supplier/{supplier_id}/products")
def diag_supplier_products(
    supplier_id: str,
    category: str = Query("tires"),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список позиций поставщика с фильтром по статусу (например dedup_loser)."""
    if category not in ("tires", "wheels"):
        raise HTTPException(status_code=400, detail="category: tires или wheels")
    if status is not None and status not in EXPORT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status: одно из {list(EXPORT_STATUSES)}",
        )
    try:
        return list_supplier_products_by_status(
            _storage(),
            supplier_id,
            category,
            status=status,
            active_supplier_ids=_active_supplier_ids(),
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/diag/statuses")
def diag_statuses():
    """Справочник кодов статусов и русских подписей."""
    return {
        "statuses": [
            {"code": code, "label_ru": status_label_ru(code)} for code in EXPORT_STATUSES
        ]
    }
