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


class TestPruneOverPledged:
    def test_prune_trims_and_logs(self, shipment, headers):
        sid = shipment["id"]
        # Create an item with qty_needed=2 then push qty_acquired to 5 directly
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                          headers=headers, json={
                              "name": "Overflow Books",
                              "isbn": "8881118880001",
                              "container_type": "container",
                              "qty_needed": 2, "qty_acquired": 5,
                          }, timeout=10)
        assert r.status_code == 200
        item = r.json()
        assert item["over_pledged"] is True

        # Add a non-overpledged item — must NOT be trimmed
        requests.post(f"{BASE_URL}/api/shipments/{sid}/items",
                      headers=headers, json={
                          "name": "Right-sized item", "qty_needed": 3, "qty_acquired": 1,
                      }, timeout=10)

        # Prune
        pr = requests.post(f"{BASE_URL}/api/shipments/{sid}/prune-over-pledged",
                           headers=headers, timeout=10)
        assert pr.status_code == 200
        body = pr.json()
        assert len(body["trimmed"]) == 1
        assert body["trimmed"][0]["surplus"] == 3
        assert body["total_surplus"] == 3

        # Verify item now at exactly qty_needed and surplus logged
        items = _list_items(sid, headers)
        trimmed_item = next(i for i in items if i.get("isbn") == "8881118880001")
        assert trimmed_item["qty_acquired"] == 2
        assert len(trimmed_item.get("surplus_redistributed") or []) == 1
        assert trimmed_item["surplus_redistributed"][0]["qty"] == 3

        # Idempotent: pruning again is a no-op
        pr2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/prune-over-pledged",
                            headers=headers, timeout=10)
        assert pr2.json()["trimmed"] == []
        assert pr2.json()["total_surplus"] == 0

    def test_prune_requires_admin(self, shipment):
        # No auth header
        r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/prune-over-pledged",
                          timeout=10)
        assert r.status_code in (401, 403)


class TestAutoStack:
    def test_auto_assigns_lightest_pallet(self, shipment, headers):
        sid = shipment["id"]
        # Create two pallets
        p1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "Heavy"}, timeout=10).json()
        p2 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "Light"}, timeout=10).json()
        # Load p1 with a heavy item
        requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Cement bags", "container_type": "pallet", "pallet_id": p1["id"],
            "weight_kg": 25, "qty_acquired": 10,
        }, timeout=10)
        # Add new pallet-bound item without specifying pallet → should land on p2 (lighter)
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Toolkit", "container_type": "pallet", "weight_kg": 5,
        }, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["pallet_id"] == p2["id"]
        assert body.get("auto_placed") is True

    def test_loose_container_items_not_auto_placed(self, shipment, headers):
        sid = shipment["id"]
        requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                      headers=headers, json={"label": "Solo"}, timeout=10)
        # container_type='container' means loose on floor — must NOT be re-assigned
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Floor crate", "container_type": "container", "weight_kg": 50,
        }, timeout=10)
        body = r.json()
        assert body["pallet_id"] is None
        assert body.get("auto_placed") is not True

    def test_auto_stacks_lighter_item_on_heavier(self, shipment, headers):
        sid = shipment["id"]
        p1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "Stack"}, timeout=10).json()
        # Heavy bottom item
        bottom = requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Toolbox", "container_type": "pallet", "pallet_id": p1["id"],
            "weight_kg": 20, "dims_cm": {"length": 60, "width": 40, "height": 25},
        }, timeout=10).json()
        # Light item on the same pallet — should auto-stack on top of toolbox
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Stationery box", "container_type": "pallet", "pallet_id": p1["id"],
            "weight_kg": 2, "dims_cm": {"length": 30, "width": 20, "height": 10},
        }, timeout=10)
        body = r.json()
        assert body["parent_id"] == bottom["id"]
        assert body.get("auto_stacked") is True
        assert body["z_cm"] == 25  # height of bottom item

    def test_similar_weight_items_dont_stack(self, shipment, headers):
        sid = shipment["id"]
        p1 = requests.post(f"{BASE_URL}/api/shipments/{sid}/pallets",
                           headers=headers, json={"label": "Side"}, timeout=10).json()
        requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Cement A", "container_type": "pallet", "pallet_id": p1["id"],
            "weight_kg": 25,
        }, timeout=10)
        # Second similar-weight item — within 10% — should stay side-by-side
        r = requests.post(f"{BASE_URL}/api/shipments/{sid}/items", headers=headers, json={
            "name": "Cement B", "container_type": "pallet", "pallet_id": p1["id"],
            "weight_kg": 24,
        }, timeout=10)
        assert r.json().get("parent_id") is None
        assert r.json().get("auto_stacked") is not True


class TestEditTokenTTL:
    def test_default_ttl_is_12h(self, shipment):
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "7777"}, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["ttl_hours"] == 12

    def test_long_session_24h(self, shipment):
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "7777", "ttl_hours": 24}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ttl_hours"] == 24

    def test_ttl_capped_at_24h(self, shipment):
        # Sneaky caller asks for a week — must be clamped to 24h.
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "7777", "ttl_hours": 999}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ttl_hours"] == 24
