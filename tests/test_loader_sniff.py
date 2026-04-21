"""Тест сниффинга формата без чтения всего файла."""
from pathlib import Path

from src.loader import FORMAT_SNIFF_BYTES, parse_file_by_content


def test_sniff_reads_small_prefix_only(tmp_path: Path) -> None:
    huge = tmp_path / "big.xml"
    body = "<root>" + ("x" * (FORMAT_SNIFF_BYTES + 5000)) + "</root>"
    huge.write_text(body, encoding="utf-8")
    root, fmt = parse_file_by_content(huge)
    assert fmt == "xml"
    assert root is not None


def test_sniff_json(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    p.write_text('[{"a": 1}]', encoding="utf-8")
    data, fmt = parse_file_by_content(p)
    assert fmt == "json"
    assert isinstance(data, list)
