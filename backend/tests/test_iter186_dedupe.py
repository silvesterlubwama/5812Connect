"""Iteration 186 — Shipment inventory deduplication + over-pledge warning.

Covers:
  - Same ISBN on the same pallet/container_type merges (qty_acquired += 1)
    instead of inserting a duplicate row.
  - Same UPC on the same pallet merges the same way.
  - Same ISBN but DIFFERENT pallet_id stays as two separate rows.
  - over_pledged flag is true when qty_acquired exceeds qty_needed.
  - Public PIN endpoint also dedupes (same code path).
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
                      json={"name": f"Dedupe Ship {int(time.time())}",
                            "dest_country": "Uganda"}, timeout=10)
    assert r.status_code == 200
    s = r.json()
    requests.post(f"{BASE_URL}/api/shipments/{s['id']}/set-pin", headers=headers,
                  json={"pin": "7777"}, timeout=10)
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


def _editor_login(token, pin="7777"):
    r = requests.post(f"{BASE_URL}/api/public/shipments/{token}/login",
                      json={"pin": pin}, timeout=10)
    r.raise_for_status()
    return r.json()["edit_token"]


def _list_items(shipment_id, headers):
    r = requests.get(f"{BASE_URL}/api/shipments/{shipment_id}", headers=headers, timeout=10)
    r.raise_for_status()
    return r.json().get("items") or []


class TestDedupe:
    def test_same_isbn_same_pallet_merges(self, shipment, headers):
        sid = shipment["id"]
        payload = {"name": "Dune", "isbn": "9780441172719",
                   "container_type": "container",
                   "qty_needed": 5, "qty_acquired": 1}
        r1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers, json=payload, timeout=10)
        assert r1.status_code == 200
        assert r1.json().get("merged") is not True

        r2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers, json=payload, timeout=10)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2.get("merged") is True
        assert body2.get("qty_acquired") == 2
        assert body2.get("over_pledged") is False

        items = [i for i in _list_items(sid, headers) if i.get("isbn") == payload["isbn"]]
        assert len(items) == 1, f"Expected 1 merged row, got {len(items)}"
        assert items[0]["qty_acquired"] == 2

    def test_same_upc_same_pallet_merges(self, shipment, headers):
        sid = shipment["id"]
        payload = {"name": "Nutella 750g", "upc": "3017620422003",
                   "container_type": "container",
                   "qty_needed": 3, "qty_acquired": 1}
        requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                      headers=headers, json=payload, timeout=10)
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                          headers=headers, json=payload, timeout=10)
        assert r.json()["merged"] is True
        assert r.json()["qty_acquired"] == 2

    def test_over_pledge_warning_flag(self, shipment, headers):
        sid = shipment["id"]
        # qty_needed=1, then add 2 → second insert should flag over_pledged.
        payload = {"name": "Limited item", "isbn": "9990000000001",
                   "container_type": "container",
                   "qty_needed": 1, "qty_acquired": 1}
        r1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers, json=payload, timeout=10)
        assert r1.json().get("over_pledged") is False  # exactly at pledge
        r2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers, json=payload, timeout=10)
        body2 = r2.json()
        assert body2["merged"] is True
        assert body2["qty_acquired"] == 2
        assert body2["over_pledged"] is True

    def test_different_pallet_stays_separate(self, shipment, headers):
        sid = shipment["id"]
        # Create two pallets
        p1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "A"}, timeout=10).json()
        p2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "B"}, timeout=10).json()
        payload = {"name": "Hobbit", "isbn": "9780547928227",
                   "container_type": "pallet", "qty_acquired": 1}
        r1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers,
                           json={**payload, "pallet_id": p1["id"]}, timeout=10)
        r2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                           headers=headers,
                           json={**payload, "pallet_id": p2["id"]}, timeout=10)
        assert r1.status_code == 200 and r2.status_code == 200
        # Different pallets → no merge
        assert r2.json().get("merged") is not True
        rows = [i for i in _list_items(sid, headers) if i.get("isbn") == payload["isbn"]]
        assert len(rows) == 2

    def test_public_endpoint_also_dedupes(self, shipment, headers):
        sid = shipment["id"]
        edit_token = _editor_login(shipment["token"])
        payload = {"name": "Public scan", "upc": "0123456789012",
                   "container_type": "container",
                   "qty_needed": 5, "qty_acquired": 1}
        requests.post(f"{BASE_URL}/api/public/shipments/{shipment['token']}/items",
                      headers={"X-Shipment-Edit-Token": edit_token},
                      json=payload, timeout=10)
        r = requests.post(f"{BASE_URL}/api/public/shipments/{shipment['token']}/items",
                          headers={"X-Shipment-Edit-Token": edit_token},
                          json=payload, timeout=10)
        assert r.status_code == 200
        assert r.json()["merged"] is True
        assert r.json()["qty_acquired"] == 2
