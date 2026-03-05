"""
FastAPI приложение: GET /export/tires.xml, GET /export/wheels.xml, GET /health.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response

# Добавляем корень проекта в path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.export import generate_export_xml
from src.storage import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Autoshina Postavshiki", version="0.1.0")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "suppliers.yaml"
DB_PATH = PROJECT_ROOT / "data" / "products.db"


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


@app.get("/health")
def health():
    """Проверка работы сервиса."""
    return {"status": "ok"}
