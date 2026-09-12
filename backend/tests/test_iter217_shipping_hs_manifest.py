"""iter217 — Shipping AI HS Code classification + printable manifest PDF.

Covers:
  • POST /api/shipments/{id}/items — condition defaults to 'used', invalid coerces
  • PUT  /api/shipments/{id}/items/{item_id} — whitelist for hs_code, condition, hs_code_reason
  • POST /api/shipments/{id}/items/{item_id}/classify-hs — single-item AI
  • POST /api/shipments/{id}/classify-hs-bulk — bulk AI with force flag
  • GET  /api/shipments/{id}/manifest.pdf — empty + with items, valid PDF header
"""
import os
import re
import time
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read from frontend/.env (never hardcoded)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


# ─── fixtures ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def client(admin_token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    })
    return s


@pytest.fixture(scope="module")
def shipment_id(client):
    """Create a fresh shipment for the whole test module."""
    tag = uuid.uuid4().hex[:6]
    r = client.post(f"{BASE_URL}/api/shipments", json={
        "name": f"TEST_iter217_{tag}",
        "dest_country": "Uganda",
        "units": "metric",
    }, timeout=15)
    assert r.status_code in (200, 201), f"Create shipment failed: {r.status_code} {r.text[:200]}"
    sid = r.json()["id"]
    yield sid
    # cleanup best-effort
    client.delete(f"{BASE_URL}/api/shipments/{sid}")


# ─── item condition schema ─────────────────────────────────────
class TestItemCondition:
    def test_condition_defaults_to_used(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 default cond item",
            "qty_needed": 1,
        }, timeout=15)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("condition") == "used"

    def test_condition_new_persists(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 new item",
            "qty_needed": 1,
            "condition": "new",
        }, timeout=15)
        assert r.status_code == 200
        assert r.json().get("condition") == "new"

    def test_condition_refurbished_persists(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 refurb item",
            "qty_needed": 1,
            "condition": "refurbished",
        }, timeout=15)
        assert r.status_code == 200
        assert r.json().get("condition") == "refurbished"

    def test_condition_invalid_coerces_to_used(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 bad-cond item",
            "qty_needed": 1,
            "condition": "banana",
        }, timeout=15)
        assert r.status_code == 200
        assert r.json().get("condition") == "used"


# ─── item update whitelist ─────────────────────────────────────
class TestItemUpdate:
    def test_put_updates_hs_code_and_condition(self, client, shipment_id):
        # create
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 update target",
            "qty_needed": 1,
        }, timeout=15)
        assert r.status_code == 200
        item_id = r.json()["id"]
        # update whitelisted fields
        r2 = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item_id}",
            json={
                "hs_code": "6109.10",
                "hs_code_reason": "cotton T-shirt (manual)",
                "condition": "new",
                # This should be IGNORED (not in whitelist)
                "created_at": "1970-01-01",
            },
            timeout=15,
        )
        assert r2.status_code == 200, r2.text[:300]
        # Verify persistence via GET on shipment detail
        r3 = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15)
        assert r3.status_code == 200
        item = next((i for i in r3.json().get("items", []) if i["id"] == item_id), None)
        assert item is not None, "Item lost after update"
        assert item.get("hs_code") == "6109.10"
        assert item.get("hs_code_reason") == "cotton T-shirt (manual)"
        assert item.get("condition") == "new"
        # created_at should NOT be 1970 — whitelist blocked it
        assert not str(item.get("created_at", "")).startswith("1970")


# ─── AI HS classification (SLOW — 10-30s per item; use a dedicated
#     small shipment with exactly 2 items to keep bulk runtime bounded).
class TestHsClassification:
    @pytest.fixture(scope="class")
    def ai_shipment_id(self, client):
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter217_ai_{uuid.uuid4().hex[:6]}",
            "dest_country": "Uganda",
            "units": "metric",
        }, timeout=15)
        assert r.status_code in (200, 201)
        sid = r.json()["id"]
        # exactly 2 items so bulk runs in ~60s
        r1 = client.post(f"{BASE_URL}/api/shipments/{sid}/items", json={
            "name": "Used cotton t-shirts", "qty_needed": 10, "condition": "used",
        }, timeout=15)
        assert r1.status_code == 200
        r2 = client.post(f"{BASE_URL}/api/shipments/{sid}/items", json={
            "name": "Children books", "qty_needed": 5, "condition": "used",
        }, timeout=15)
        assert r2.status_code == 200
        yield sid, r1.json()["id"], r2.json()["id"]
        client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def test_single_item_classify_used_cotton_tshirts(self, client, ai_shipment_id):
        sid, tshirt_id, _ = ai_shipment_id
        r2 = client.post(
            f"{BASE_URL}/api/shipments/{sid}/items/{tshirt_id}/classify-hs",
            json={}, timeout=90,
        )
        if r2.status_code == 503:
            pytest.skip(f"AI unavailable: {r2.text[:120]}")
        assert r2.status_code == 200, r2.text[:300]
        data = r2.json()
        assert re.match(r"^\d{4}\.\d{2}$", data.get("hs_code", "")), f"Bad HS: {data}"
        assert data["hs_code"].startswith("6309") or data["hs_code"].startswith("6109"), (
            f"Unexpected HS for used cotton t-shirts: {data['hs_code']}"
        )

    def test_bulk_classify_only_missing(self, client, ai_shipment_id):
        sid, _, _ = ai_shipment_id
        # After previous test, t-shirt item has hs_code; only Children books left
        r2 = client.post(
            f"{BASE_URL}/api/shipments/{sid}/classify-hs-bulk",
            json={"force": False}, timeout=180,
        )
        if r2.status_code == 503:
            pytest.skip(f"AI unavailable: {r2.text[:120]}")
        assert r2.status_code == 200, r2.text[:400]
        data = r2.json()
        assert data["shipment_id"] == sid
        assert data["classified"] >= 1
        assert data["skipped_existing"] >= 1
        for row in data["results"]:
            assert "item_id" in row and "name" in row and "ok" in row
            if row["ok"]:
                assert re.match(r"^\d{4}\.\d{2}$", row["hs_code"])

    def test_bulk_classify_force_reclassifies_all(self, client, ai_shipment_id):
        sid, _, _ = ai_shipment_id
        r = client.post(
            f"{BASE_URL}/api/shipments/{sid}/classify-hs-bulk",
            json={"force": True}, timeout=240,
        )
        if r.status_code == 503:
            pytest.skip(f"AI unavailable: {r.text[:120]}")
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data["skipped_existing"] == 0
        assert data["classified"] + data["failed"] == len(data["results"])
        assert data["classified"] >= 1


# ─── manifest PDF ──────────────────────────────────────────────
class TestManifestPdf:
    def test_manifest_pdf_with_items(self, client, shipment_id):
        r = client.get(f"{BASE_URL}/api/shipments/{shipment_id}/manifest.pdf", timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-", f"Not a PDF, got: {r.content[:20]!r}"
        # Should include HS classification banner text somewhere
        assert len(r.content) > 1000

    def test_manifest_pdf_empty_shipment(self, client):
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter217_empty_{uuid.uuid4().hex[:4]}",
            "dest_country": "Uganda",
        }, timeout=15)
        assert r.status_code in (200, 201)
        sid = r.json()["id"]
        try:
            r2 = client.get(f"{BASE_URL}/api/shipments/{sid}/manifest.pdf", timeout=90)
            assert r2.status_code == 200
            assert r2.content[:5] == b"%PDF-"
        finally:
            client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def test_manifest_pdf_404_for_unknown_shipment(self, client):
        r = client.get(f"{BASE_URL}/api/shipments/does_not_exist_xyz/manifest.pdf", timeout=15)
        assert r.status_code == 404


# ─── regression: shipment/item CRUD still works ─────────────────
class TestRegression:
    def test_shipment_list_and_get(self, client, shipment_id):
        r = client.get(f"{BASE_URL}/api/shipments", timeout=15)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert shipment_id in ids
        r2 = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["id"] == shipment_id

    def test_delete_item(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items", json={
            "name": "TEST_iter217 delete-me",
            "qty_needed": 1,
        }, timeout=15)
        assert r.status_code == 200
        iid = r.json()["id"]
        r2 = client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/items/{iid}", timeout=15)
        assert r2.status_code in (200, 204)
