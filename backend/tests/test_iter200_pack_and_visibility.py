"""Iteration 200 — Pack action + public wishlist vs manifest split.

Verifies:
  - New qty_packed / transport_mode fields on items
  - POST /shipments/{id}/items/{item_id}/pack increments qty_packed
  - Independent counters — acquired stays untouched after packing
  - Public GET WITHOUT edit_token returns stripped fields only
  - Public GET WITH edit_token returns full manifest
"""
import os
import time
import requests
import pytest
from dotenv import load_dotenv

import creds  # env-backed logins, see tests/creds.py
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD

SENSITIVE_FIELDS = {"weight_kg", "dims_cm", "pallet_id", "parent_id",
                    "qty_packed", "transport_mode", "x_cm", "y_cm", "z_cm",
                    "image_urls", "isbn", "upc", "container_type"}


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
                      json={"name": f"PackTest {int(time.time())}"}, timeout=10)
    s = r.json()
    requests.post(f"{BASE_URL}/api/shipments/{s['id']}/set-pin", headers=headers,
                  json={"pin": "3333"}, timeout=10)
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


@pytest.fixture
def item(shipment, headers):
    r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items",
                      headers=headers, json={
                          "name": "Solar lantern",
                          "category": "Electronics",
                          "qty_needed": 20, "qty_acquired": 15,
                          "weight_kg": 0.8,
                          "isbn": "", "upc": "1234567890128",
                      }, timeout=10)
    return r.json()


class TestPackAction:
    def test_pack_increments_qty_packed(self, shipment, item, headers):
        r = requests.post(
            f"{BASE_URL}/api/shipments/{shipment['id']}/items/{item['id']}/pack",
            headers=headers, json={"qty": 10, "mode": "container"}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["qty_packed"] == 10
        assert r.json()["qty_acquired"] == 15  # untouched (independent counter)
        assert r.json()["transport_mode"] == "container"
        assert r.json()["over_packed"] is False

    def test_pack_flags_over_packed(self, shipment, item, headers):
        # Pack 20 units when only 15 acquired → over_packed True
        r = requests.post(
            f"{BASE_URL}/api/shipments/{shipment['id']}/items/{item['id']}/pack",
            headers=headers, json={"qty": 20, "mode": "suitcase"}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["qty_packed"] == 20
        assert r.json()["over_packed"] is True
        assert r.json()["transport_mode"] == "suitcase"

    def test_pack_rejects_bad_mode(self, shipment, item, headers):
        r = requests.post(
            f"{BASE_URL}/api/shipments/{shipment['id']}/items/{item['id']}/pack",
            headers=headers, json={"qty": 5, "mode": "spaceship"}, timeout=10,
        )
        assert r.status_code == 400


class TestPublicWishlistView:
    def _fetch(self, token, edit_token=None):
        url = f"{BASE_URL}/api/public/shipments/{token}"
        if edit_token:
            url += f"?edit_token={edit_token}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()

    def test_anonymous_public_view_strips_sensitive_fields(self, shipment, item):
        body = self._fetch(shipment["token"])
        assert body["unlocked"] is False
        items = body["still_needed"] + body["already_acquired"]
        assert len(items) > 0
        for i in items:
            for field in SENSITIVE_FIELDS:
                assert field not in i, f"Public view leaked {field}: {i}"
            # These should ALWAYS be visible so donors know what's needed
            assert "name" in i
            assert "qty_needed" in i
            assert "qty_acquired" in i

    def test_anonymous_view_hides_container_dims_and_pallets(self, shipment, item):
        body = self._fetch(shipment["token"])
        assert body.get("container_dims_cm") is None
        assert body.get("pallets") == []
        assert body.get("ai_packing_text") == ""

    def test_unlocked_view_shows_everything(self, shipment, item, headers):
        # First unlock
        login = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "3333"}, timeout=10,
        )
        edit_token = login.json()["edit_token"]
        body = self._fetch(shipment["token"], edit_token)
        assert body["unlocked"] is True
        assert body["container_dims_cm"] is not None
        items = body["still_needed"] + body["already_acquired"]
        # Full item shape — should include weight_kg + qty_packed keys
        assert any("weight_kg" in i for i in items)
        assert any("qty_packed" in i for i in items)


class TestNewItemDefaults:
    def test_new_item_has_default_pack_state(self, shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items",
                          headers=headers, json={"name": "Default"}, timeout=10)
        it = r.json()
        assert it["qty_packed"] == 0
        assert it["transport_mode"] == "container"

    def test_can_create_item_as_suitcase(self, shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items",
                          headers=headers, json={
                              "name": "Hand-carry meds",
                              "transport_mode": "suitcase",
                          }, timeout=10)
        assert r.json()["transport_mode"] == "suitcase"

    def test_invalid_mode_falls_back_to_container(self, shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{shipment['id']}/items",
                          headers=headers, json={
                              "name": "Bad mode",
                              "transport_mode": "hovercraft",
                          }, timeout=10)
        assert r.json()["transport_mode"] == "container"
