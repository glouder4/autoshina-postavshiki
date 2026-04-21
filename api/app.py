"""
FastAPI приложение: GET /export/tires.xml, GET /export/wheels.xml, GET /health, GET /ready.

Запуск из корня проекта: uvicorn api.app:app — каталог текущего процесса должен содержать пакеты api/ и src/.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from src.export import generate_export_xml
from src.sync_state import default_sync_state_path, load_sync_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Autoshina Postavshiki", version="0.1.0")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "suppliers.yaml"
DB_PATH = PROJECT_ROOT / "data" / "products.db"
SYNC_STATE_PATH = default_sync_state_path(PROJECT_ROOT)


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
