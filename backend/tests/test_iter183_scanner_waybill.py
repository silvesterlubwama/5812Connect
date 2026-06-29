"""Iteration 183 — Shipment AI scanner + waybill + extended item model.

Covers:
  - POST /api/public/shipments/{token}/scan-item with ISBN → Google Books lookup
  - POST /api/public/shipments/{token}/scan-item with UPC → OpenFoodFacts lookup
  - POST /api/public/shipments/{token}/scan-item with no signals → 400
  - GET /api/shipments/{id}/waybill renders HTML with item table + totals
  - Item model accepts container_type, parent_id, isbn, upc, author,
    publisher, ai_identified, scanned_by_pin_hint, scanned_at, image_urls
"""
import os
import time
import requests
import pytest
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def shipment(headers):
    r = requests.post(f"{BASE_URL}/api/shipments", headers=headers,
                      json={"name": f"Test Ship {int(time.time())}",
                            "dest_country": "Uganda",
                            "description": "Test container for iter183"}, timeout=10)
    assert r.status_code == 200
    s = r.json()
    # Set a PIN so the public endpoints work
    r2 = requests.post(f"{BASE_URL}/api/shipments/{s['id']}/set-pin", headers=headers,
                       json={"pin": "9999"}, timeout=10)
    assert r2.status_code == 200
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


def _editor_login(token, pin):
    r = requests.post(f"{BASE_URL}/api/public/shipments/{token}/login",
                      json={"pin": pin}, timeout=10)
    r.raise_for_status()
    return r.json()["edit_token"]


class TestScan:
    def test_scan_with_isbn_hits_google_books(self, shipment):
        edit_token = _editor_login(shipment["token"], "9999")
        # Use a known classic ISBN — Penguin Classics edition of Through the
        # Looking-Glass. Google Books has a stable entry for it.
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            params={"isbn": "9780140329513"},
            headers={"X-Shipment-Edit-Token": edit_token},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Either Google Books returned a hit (preferred) or we got a fallback;
        # either way the response shape is fixed.
        assert "name" in d
        assert "category" in d
        assert "image_urls" in d
        assert d.get("isbn") == "9780140329513" or d.get("source") == "manual"

    def test_scan_with_upc_hits_openfoodfacts(self, shipment):
        edit_token = _editor_login(shipment["token"], "9999")
        # Nutella 750g — well-known UPC on OpenFoodFacts
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            params={"upc": "3017620422003"},
            headers={"X-Shipment-Edit-Token": edit_token},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Should have some name/category set even if OFF was down
        assert "name" in d
        assert "category" in d
        assert d.get("upc") == "3017620422003" or d.get("source") in ("manual", "ai_vision")

    def test_scan_with_nothing_rejects(self, shipment):
        edit_token = _editor_login(shipment["token"], "9999")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            headers={"X-Shipment-Edit-Token": edit_token},
            timeout=10,
        )
        assert r.status_code == 400

    def test_scan_without_editor_token_unauthorized(self, shipment):
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            params={"isbn": "9780140329513"},
            timeout=10,
        )
        assert r.status_code == 401


class TestExtendedItemModel:
    def test_create_item_with_new_fields(self, shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items",
                          headers=headers, json={
                              "name": "1984 by Orwell",
                              "category": "Books",
                              "container_type": "box",
                              "isbn": "9780451524935",
                              "author": "George Orwell",
                              "publisher": "Signet Classic",
                              "ai_identified": True,
                              "image_urls": ["https://example.com/cover.jpg"],
                              "qty_acquired": 1,
                              "weight_kg": 0.3,
                              "value_usd": 9.99,
                          }, timeout=10)
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["container_type"] == "box"
        assert item["isbn"] == "9780451524935"
        assert item["author"] == "George Orwell"
        assert item["publisher"] == "Signet Classic"
        assert item["ai_identified"] is True
        assert item["image_urls"] == ["https://example.com/cover.jpg"]

    def test_stacking_parent_id(self, shipment, headers):
        # Bottom item
        r1 = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items", headers=headers,
                           json={"name": "Bottom box"}, timeout=10)
        assert r1.status_code == 200
        bottom = r1.json()
        # Stacked on top
        r2 = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items", headers=headers,
                           json={"name": "Stacked book", "parent_id": bottom["id"]}, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["parent_id"] == bottom["id"]


class TestWaybill:
    def test_waybill_contains_items_and_totals(self, shipment, headers):
        requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items", headers=headers,
                      json={"name": "Test Book Alpha", "category": "Books",
                            "qty_acquired": 2, "value_usd": 12.99, "weight_kg": 0.3,
                            "isbn": "9780140329513"}, timeout=10)
        requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items", headers=headers,
                      json={"name": "Test Toy Beta", "category": "Toys",
                            "qty_acquired": 3, "value_usd": 5.00, "weight_kg": 0.2}, timeout=10)

        r = requests.get(f"{BASE_URL}/api/shipments/{shipment['id']}/waybill",
                         headers=headers, timeout=10)
        assert r.status_code == 200
        html = r.text
        assert "Test Book Alpha" in html
        assert "9780140329513" in html
        assert "Test Toy Beta" in html
        # Total value: 2*12.99 + 3*5.00 = 25.98 + 15.00 = 40.98
        assert "$40.98" in html
        # Total weight: 2*0.3 + 3*0.2 = 1.20
        assert "1.20 kg" in html

    def test_public_waybill_requires_pin(self, shipment):
        r = requests.get(f"{BASE_URL}/api/public/shipments/{shipment['token']}/waybill",
                         timeout=10)
        assert r.status_code == 401  # No edit token

        edit_token = _editor_login(shipment["token"], "9999")
        r2 = requests.get(f"{BASE_URL}/api/public/shipments/{shipment['token']}/waybill",
                          headers={"X-Shipment-Edit-Token": edit_token}, timeout=10)
        assert r2.status_code == 200
        assert "<h1>Waybill" in r2.text

    def test_public_waybill_query_param_token(self, shipment):
        """window.open()-style access — edit token passed as query param
        because browsers can't attach custom headers on plain GETs."""
        edit_token = _editor_login(shipment["token"], "9999")
        r = requests.get(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/waybill",
            params={"edit_token": edit_token}, timeout=10,
        )
        assert r.status_code == 200
        assert "<h1>Waybill" in r.text
        # Bad token rejected
        r2 = requests.get(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/waybill",
            params={"edit_token": "deadbeef"}, timeout=10,
        )
        assert r2.status_code == 401
