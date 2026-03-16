"""
Загрузка XML/JSON по URL с обработкой ошибок, retry, таймаутом.
Файлы сначала сохраняются в кэш, затем парсятся — экономия памяти на больших выгрузках.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Union

import requests
from lxml import etree
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .adapters import get_adapter
from .models import Product


def _product_has_required_fields(p: Product) -> bool:
    """Обязательные поля при импорте: Название, Картинка, Цена > 0."""
    if not p or p.price <= 0:
        return False
    name_ok = bool((p.NAME or "").strip())
    if not name_ok:
        name_ok = bool(
            (p.PROIZVODITEL or "").strip()
            or (p.MODEL_AVTOSHINY or "").strip()
            or (p.MODEL_DISKA or "").strip()
        )
    if not name_ok:
        return False
    photo = (p.MORE_PHOTO or "").strip()
    photo_ok = "http://" in photo or "https://" in photo
    return photo_ok

logger = logging.getLogger(__name__)

# Временные ошибки для retry
RETRY_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout,
)


@retry(
    retry=retry_if_exception_type(RETRY_EXCEPTIONS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_xml_to_file(url: str, filepath: Path, timeout: int = 60) -> bool:
    """
    Загрузить XML по URL в локальный файл (stream — для больших файлов).
    Retry при временных сетевым ошибках.
    Возвращает True при успехе, False при ошибке.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return True


def parse_xml_from_file(filepath: Path) -> Optional[etree._Element]:
    """Распарсить XML из файла. Возвращает корневой элемент или None при ошибке."""
    try:
        tree = etree.parse(str(filepath))
        return tree.getroot()
    except etree.XMLSyntaxError as e:
        logger.error("Ошибка парсинга XML %s: %s", filepath, e)
        return None


def parse_json_from_file(filepath: Path):
    """Распарсить JSON из файла. Возвращает данные или None при ошибке."""
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Ошибка парсинга JSON %s: %s", filepath, e)
        return None


def parse_file_by_content(filepath: Path) -> tuple[Optional[Union[etree._Element, list]], str]:
    """
    Определить формат по содержимому и распарсить.
    Возвращает (root/elements, "xml"|"json") или (None, "") при ошибке.
    """
    try:
        first_bytes = filepath.read_bytes()[:50]
        first_chars = first_bytes.decode("utf-8", errors="ignore").lstrip()
        if first_chars.startswith("[") or first_chars.startswith("{"):
            data = parse_json_from_file(filepath)
            if data is not None:
                items = data if isinstance(data, list) else []
                return (items, "json")
        # XML
        root = parse_xml_from_file(filepath)
        return (root, "xml") if root is not None else (None, "")
    except Exception as e:
        logger.error("Ошибка чтения %s: %s", filepath, e)
        return (None, "")


def load_products_from_url(
    url: str,
    supplier_id: str,
    supplier_name: str,
    category: str,
    timeout: int = 60,
    config_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    cache_file_override: Optional[Path] = None,
    skip_fetch: bool = False,
) -> list[Product]:
    """
    Скачать XML по URL в кэш, распарсить через адаптер, вернуть список Product.
    cache_file_override: использовать этот файл вместо supplier_id_category.xml
    skip_fetch: не скачивать, только парсить (для объединённой выгрузки).
    """
    adapter = get_adapter(supplier_id, category, config_dir)
    if not adapter:
        logger.error("Адаптер не найден для %s/%s", supplier_id, category)
        return []

    cache_base = cache_dir or Path("data/cache")
    cache_file = cache_file_override or (cache_base / f"{supplier_id}_{category}.xml")

    if not skip_fetch:
        try:
            fetch_xml_to_file(url, cache_file, timeout=timeout)
        except requests.exceptions.RequestException as e:
            logger.error(
                "Ошибка загрузки %s (поставщик %s): %s", url, supplier_id, e
            )
            return []
        except Exception as e:
            logger.exception("Неожиданная ошибка загрузки %s: %s", url, e)
            return []

    parsed, fmt = parse_file_by_content(cache_file)
    if parsed is None:
        return []

    if fmt == "json":
        items = parsed if isinstance(parsed, list) else []
    else:
        cfg = get_adapter_config(supplier_id, config_dir)
        item_xpath = cfg.get(f"item_xpath_{category}", "//offer") if cfg else "//offer"
        try:
            items = parsed.xpath(item_xpath)
        except Exception as e:
            logger.error("Ошибка XPath %s: %s", item_xpath, e)
            return []

    products: list[Product] = []
    for elem in items:
        if fmt == "json":
            if not isinstance(elem, dict):
                continue
        elif not hasattr(elem, "tag"):
            continue
        p = adapter.parse_product(elem, category)
        if p and _product_has_required_fields(p):
            products.append(p)

    logger.info(
        "Загружено %d товаров с %s (%s)",
        len(products),
        supplier_id,
        category,
    )
    return products


def get_adapter_config(
    supplier_id: str,
    config_dir: Optional[Path] = None,
) -> Optional[dict]:
    """Загрузить сырой конфиг адаптера."""
    from .adapters.factory import load_adapter_config

    return load_adapter_config(supplier_id, config_dir)
