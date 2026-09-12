"""Iter-172 backend regression for Container Shipments (visualizer, photo upload,
AI URL estimate, CSV bulk-import, public endpoint pallets field)."""
import io
import os
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PWD = creds.ADMIN_PASSWORD


# ─── Shared fixtures ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"identifier": ADMIN_EMAIL, "password": ADMIN_PWD},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok, "no token from login"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def shipment_id(session):
    """Create a fresh shipment for the test class. Cleaned up at end."""
    r = session.post(f"{BASE_URL}/api/shipments", json={
        "name": "TEST_iter172 Container",
        "dest_country": "Uganda",
        "description": "Iter-172 regression run",
        "target_ship_date": "2026-06-01",
    }, timeout=10)
    assert r.status_code in (200, 201), r.text
    sid = r.json().get("id")
    assert sid
    yield sid
    # Teardown
    try:
        session.delete(f"{BASE_URL}/api/shipments/{sid}", timeout=10)
    except Exception:
        pass


# ─── Shipment CRUD smoke ─────────────────────────────────────────
class TestShipmentSmoke:
    def test_list_shipments(self, session):
        r = session.get(f"{BASE_URL}/api/shipments", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_shipment(self, session, shipment_id):
        r = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("id") == shipment_id
        assert body.get("token"), "shipment must have public token"


# ─── Items CRUD ──────────────────────────────────────────────────
class TestItems:
    def test_add_item_normalises(self, session, shipment_id):
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_school-bag",
            "category": "Supplies",
            "qty_needed": 5,
            "weight_kg": 0.7,
            "dims_cm": {"length": 40, "width": 30, "height": 15},
            "value_usd": 12.5,
            "priority": "high",
        }, timeout=10)
        assert r.status_code == 200, r.text
        item = r.json()
        assert item.get("name") == "TEST_school-bag"
        assert item.get("priority") == "high"
        assert item.get("qty_needed") == 5
        assert item.get("dims_cm", {}).get("length") == 40
        # Verify persistence
        g = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10).json()
        ids = [i["id"] for i in g.get("items", [])]
        assert item["id"] in ids


# ─── CSV bulk-import ─────────────────────────────────────────────
class TestBulkImport:
    def test_bulk_import_skips_empty_names(self, session, shipment_id):
        payload = {"items": [
            {"name": "TEST_bulk-A", "qty_needed": 2, "weight_kg": 0.3, "priority": "urgent",
             "dims_cm": {"length": 20, "width": 10, "height": 5}, "value_usd": 4},
            {"name": "TEST_bulk-B", "qty_needed": 1, "weight_kg": 0.1},
            {"name": "", "qty_needed": 99},   # should be skipped
        ]}
        r = session.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/bulk-import",
            json=payload, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("imported") == 2

    def test_bulk_import_invalid_items_type(self, session, shipment_id):
        r = session.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/bulk-import",
            json={"items": "notalist"}, timeout=10,
        )
        assert r.status_code == 400


# ─── Photo upload ────────────────────────────────────────────────
class TestPhotoUpload:
    def test_upload_item_photo(self, session, shipment_id):
        # First create an item
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                         json={"name": "TEST_photo-item", "qty_needed": 1},
                         timeout=10)
        item_id = r.json()["id"]
        # Minimal 1x1 PNG
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000000500010d0a2db40000000049454e44"
            "ae426082"
        )
        files = {"file": ("tiny.png", io.BytesIO(png), "image/png")}
        # Don't send Content-Type from session headers (it'd override multipart)
        headers = {k: v for k, v in session.headers.items() if k.lower() != "content-type"}
        r = requests.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item_id}/photo",
            files=files, headers=headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        photo_url = r.json().get("photo_url")
        assert photo_url, "expected photo_url in response"
        # Verify it's saved on the item
        g = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10).json()
        item = next(i for i in g["items"] if i["id"] == item_id)
        assert item.get("photo_url") == photo_url

    def test_upload_rejects_non_image(self, session, shipment_id):
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                         json={"name": "TEST_photo-bad", "qty_needed": 1},
                         timeout=10)
        item_id = r.json()["id"]
        files = {"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")}
        headers = {k: v for k, v in session.headers.items() if k.lower() != "content-type"}
        r = requests.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item_id}/photo",
            files=files, headers=headers, timeout=15,
        )
        assert r.status_code == 400


# ─── AI estimate from product URL ────────────────────────────────
class TestEstimateFromLink:
    def test_estimate_graceful(self, session, shipment_id):
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                         json={"name": "TEST_link-item", "qty_needed": 1},
                         timeout=10)
        item_id = r.json()["id"]
        r = session.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item_id}/estimate-from-link",
            json={"url": "https://www.example.com/dp/B000FAKE"},
            timeout=40,
        )
        # Endpoint must either succeed OR return a clean 4xx/5xx — never 500 with traceback
        assert r.status_code in (200, 400, 422, 502, 503), (
            f"unexpected status {r.status_code}: {r.text[:300]}"
        )
        if r.status_code == 200:
            body = r.json()
            assert "weight_kg" in body or "estimate" in body or "dims_cm" in body, body


# ─── Public endpoint ─────────────────────────────────────────────
class TestPublicEndpoint:
    def test_public_payload_includes_pallets(self, session, shipment_id):
        # Get token (admin view)
        s = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10).json()
        token = s.get("token")
        assert token
        # No auth — public
        r = requests.get(f"{BASE_URL}/api/public/shipments/{token}", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Iter-172 contract: public must include `pallets` and `container_dims_cm`
        assert "pallets" in body, "public endpoint must include 'pallets' field"
        assert isinstance(body["pallets"], list)
        assert "container_dims_cm" in body
        assert "still_needed" in body
        assert "already_acquired" in body

    def test_public_donate_increments_acquired(self, session, shipment_id):
        # Add a needable item
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                         json={"name": "TEST_donate-target", "qty_needed": 3},
                         timeout=10)
        item_id = r.json()["id"]
        s = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10).json()
        token = s.get("token")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{token}/items/{item_id}/donate",
            json={"qty": 2, "donor_name": "TEST_donor"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("qty_recorded") == 2
        # Verify persisted
        g = session.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=10).json()
        item = next(i for i in g["items"] if i["id"] == item_id)
        assert item.get("qty_acquired") == 2


# ─── AI packing scenario regression ──────────────────────────────
class TestAiPacking:
    def test_ai_packing_graceful(self, session, shipment_id):
        r = session.post(f"{BASE_URL}/api/shipments/{shipment_id}/ai-packing", timeout=40)
        # Must not 500-traceback. 200 if LLM works, 503/502 if not configured
        assert r.status_code in (200, 502, 503), (
            f"unexpected status {r.status_code}: {r.text[:200]}"
        )
