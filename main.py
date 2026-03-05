"""
Точка входа: запуск API и планировщика синхронизации.
"""
import logging
import sys
from pathlib import Path

# Корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.sync import run_sync
from src.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = PROJECT_ROOT / "config" / "suppliers.yaml"
DB_PATH = PROJECT_ROOT / "data" / "products.db"


def load_interval() -> int:
    """Интервал обновления из конфига."""
    import yaml
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return int(cfg.get("update_interval_minutes", 60))
    return 60


if __name__ == "__main__":
    logger.info("Запуск первичной синхронизации...")
    try:
        run_sync(config_path=CONFIG_PATH, db_path=DB_PATH)
    except Exception as e:
        logger.warning("Первичная синхронизация не удалась: %s (запускаем API)", e)

    interval = load_interval()
    start_scheduler(
        interval_minutes=interval,
        config_path=CONFIG_PATH,
        db_path=DB_PATH,
    )

    import uvicorn
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
