"""
Планировщик периодического обновления выгрузки.
"""
import logging
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .sync import run_sync

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def run_sync_job(
    config_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Задача для планировщика: выполнить синхронизацию."""
    try:
        run_sync(config_path=config_path, db_path=db_path)
    except Exception as e:
        logger.exception("Ошибка синхронизации: %s", e)


def start_scheduler(
    interval_minutes: int = 60,
    config_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> BackgroundScheduler:
    """Запустить планировщик обновления."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_sync_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="sync_suppliers",
        kwargs={"config_path": config_path, "db_path": db_path},
    )
    _scheduler.start()
    logger.info("Планировщик запущен, интервал %d мин", interval_minutes)
    return _scheduler


def stop_scheduler() -> None:
    """Остановить планировщик."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Планировщик остановлен")
