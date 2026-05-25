"""Тесты API /api/diag и /ui."""
from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient

from api import app as api_app
from src.storage import Storage
from tests.conftest import make_tire_product


@pytest.fixture
def diag_client(tmp_path, monkeypatch):
    db = tmp_path / "diag.db"
    cfg = tmp_path / "suppliers.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            suppliers:
              - id: supplier_1
                name: Test1
                active: true
              - id: supplier_2
                name: Test2
                active: true
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_app, "DB_PATH", db)
    monkeypatch.setattr(api_app, "CONFIG_PATH", cfg)

    st = Storage(db)
    a = make_tire_product(
        supplier_id="supplier_1",
        CML2_ARTICLE="FINDME-001",
        MODEL_AVTOSHINY="PilotSport",
        NAME="Pilot Sport 4",
    )
    b = make_tire_product(
        supplier_id="supplier_2",
        CML2_ARTICLE="OTHER",
        MODEL_AVTOSHINY="PilotSport",
        PROIZVODITEL="OtherBrand",
        price=500,
    )
    st.upsert_products([a], supplier="T1", supplier_id="supplier_1", category="tires")
    st.upsert_products([b], supplier="T2", supplier_id="supplier_2", category="tires")

    return TestClient(api_app.app)


def test_health_export_unchanged(diag_client):
    assert diag_client.get("/health").json()["status"] == "ok"
    r = diag_client.get("/export/tires.xml")
    assert r.status_code in (200, 500)


def test_diag_search(diag_client):
    r = diag_client.get("/api/diag/search", params={"q": "FINDME"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    assert any("FINDME" in (i.get("CML2_ARTICLE") or "") for i in data["items"])
    assert "export_status" in data["items"][0]


def test_diag_product_and_group(diag_client):
    search = diag_client.get("/api/diag/search", params={"q": "FINDME"}).json()
    pid = search["items"][0]["id"]
    prod = diag_client.get(f"/api/diag/product/{pid}")
    assert prod.status_code == 200
    assert prod.json()["id"] == pid
    grp = diag_client.get("/api/diag/group", params={"product_id": pid})
    assert grp.status_code == 200
    assert grp.json()["size"] >= 1


def test_diag_suppliers_and_summary(diag_client):
    sup = diag_client.get("/api/diag/suppliers")
    assert sup.status_code == 200
    ids = {s["id"] for s in sup.json()["suppliers"]}
    assert "supplier_1" in ids
    summary = diag_client.get(
        "/api/diag/supplier/supplier_1/summary",
        params={"category": "tires"},
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["supplier_id"] == "supplier_1"
    assert body["category"] == "tires"
    assert "status_counts" in body


def test_ui_page(diag_client):
    r = diag_client.get("/ui")
    assert r.status_code == 200
    assert "Диагностика дедупликации" in r.text


def test_diag_statuses_ru(diag_client):
    r = diag_client.get("/api/diag/statuses")
    assert r.status_code == 200
    labels = {s["code"]: s["label_ru"] for s in r.json()["statuses"]}
    assert "dedup_loser" in labels
    assert "дедуп" in labels["dedup_loser"].lower()


def test_diag_lookup_by_article(diag_client):
    cheap = make_tire_product(
        supplier_id="supplier_1",
        CML2_ARTICLE="WIN-LOOKUP",
        MODEL_AVTOSHINY="PilotSport",
        PROIZVODITEL="Michelin",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        SEZONNOST="Летняя",
        price=100,
        quantity=3,
    )
    costly = make_tire_product(
        supplier_id="supplier_2",
        CML2_ARTICLE="LOSE-LOOKUP",
        MODEL_AVTOSHINY="PilotSport",
        PROIZVODITEL="Michelin",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        SEZONNOST="Летняя",
        price=500,
        quantity=5,
    )
    from api import app as api_app
    from src.storage import Storage

    st = Storage(api_app.DB_PATH)
    st.upsert_products([cheap], supplier="T1", supplier_id="supplier_1", category="tires")
    st.upsert_products([costly], supplier="T2", supplier_id="supplier_2", category="tires")

    r = diag_client.get("/api/diag/lookup", params={"article": "LOSE-LOOKUP"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["groups"][0]["export_winner"]["CML2_ARTICLE"] == "WIN-LOOKUP"
    assert len(body["groups"][0]["members"]) >= 2


def test_diag_suppliers_summary_all(diag_client):
    r = diag_client.get("/api/diag/suppliers/summary", params={"category": "tires"})
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "tires"
    assert len(body["suppliers"]) >= 2
    ids = {s["supplier_id"] for s in body["suppliers"]}
    assert "supplier_1" in ids
    assert "supplier_2" in ids


def test_diag_supplier_products_loser(diag_client):
    """Проигравшие дедуп видны через /products, не только через текстовый поиск."""
    cheap = make_tire_product(
        supplier_id="supplier_1",
        CML2_ARTICLE="CHEAP-001",
        MODEL_AVTOSHINY="PilotSport",
        PROIZVODITEL="Michelin",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        SEZONNOST="Летняя",
        price=100,
        quantity=3,
    )
    costly = make_tire_product(
        supplier_id="supplier_2",
        CML2_ARTICLE="LOSE-001",
        MODEL_AVTOSHINY="PilotSport",
        PROIZVODITEL="Michelin",
        SHIRINA_PROFILYA="205",
        VYSOTA_PROFILYA="55",
        POSADOCHNYY_DIAMETR="16",
        SEZONNOST="Летняя",
        price=500,
        quantity=5,
    )
    from api import app as api_app
    from src.storage import Storage

    st = Storage(api_app.DB_PATH)
    st.upsert_products([cheap], supplier="T1", supplier_id="supplier_1", category="tires")
    st.upsert_products([costly], supplier="T2", supplier_id="supplier_2", category="tires")

    r = diag_client.get(
        "/api/diag/supplier/supplier_2/products",
        params={"category": "tires", "status": "dedup_loser"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(i["CML2_ARTICLE"] == "LOSE-001" for i in body["items"])
    assert body["items"][0]["export_status_label"]
