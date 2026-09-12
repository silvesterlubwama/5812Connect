"""Iteration 197 — Shipment units feature end-to-end.

Verifies the per-shipment units toggle works AND that imperial inputs like
'2'9"' and '5lb 8oz' are correctly parsed into canonical cm/kg storage."""
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
def imperial_shipment(headers):
    r = requests.post(f"{BASE_URL}/api/shipments", headers=headers,
                      json={"name": f"Imperial Ship {int(time.time())}",
                            "dest_country": "Liberia",
                            "units": "imperial"}, timeout=10)
    s = r.json()
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


@pytest.fixture
def metric_shipment(headers):
    r = requests.post(f"{BASE_URL}/api/shipments", headers=headers,
                      json={"name": f"Metric Ship {int(time.time())}",
                            "dest_country": "Uganda"}, timeout=10)
    s = r.json()
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


class TestUnitsField:
    def test_create_defaults_to_metric(self, metric_shipment):
        assert metric_shipment["units"] == "metric"

    def test_create_imperial(self, imperial_shipment):
        assert imperial_shipment["units"] == "imperial"

    def test_can_flip_units(self, metric_shipment, headers):
        r = requests.put(f"{BASE_URL}/api/shipments/{metric_shipment['id']}",
                         headers=headers, json={"units": "imperial"}, timeout=10)
        assert r.status_code == 200
        check = requests.get(f"{BASE_URL}/api/shipments/{metric_shipment['id']}",
                             headers=headers, timeout=10).json()
        assert check["units"] == "imperial"

    def test_invalid_unit_rejected(self, metric_shipment, headers):
        r = requests.put(f"{BASE_URL}/api/shipments/{metric_shipment['id']}",
                         headers=headers, json={"units": "furlongs"}, timeout=10)
        assert r.status_code == 400


class TestImperialItemInput:
    def test_feet_inches_string_parsed_to_cm(self, imperial_shipment, headers):
        """The hero example: 2'9" must arrive on disk as 83.82 cm."""
        r = requests.post(f"{BASE_URL}/api/shipments/{imperial_shipment['id']}/items",
                          headers=headers, json={
                              "name": "Imperial dim test",
                              "dims_cm": {"length": "2'9\"", "width": "1'", "height": "6in"},
                          }, timeout=10)
        assert r.status_code == 200
        item = r.json()
        assert abs(item["dims_cm"]["length"] - 83.82) < 0.01
        assert abs(item["dims_cm"]["width"] - 30.48) < 0.01
        assert abs(item["dims_cm"]["height"] - 15.24) < 0.01

    def test_lb_oz_string_parsed_to_kg(self, imperial_shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{imperial_shipment['id']}/items",
                          headers=headers, json={
                              "name": "Imperial weight test",
                              "weight_kg": "5lb 8oz",
                          }, timeout=10)
        assert r.status_code == 200
        # 5lb 8oz = 2.494 kg
        assert abs(r.json()["weight_kg"] - 2.494) < 0.01

    def test_bare_number_on_imperial_shipment_treats_as_inches(self, imperial_shipment, headers):
        """User typed 33 (no suffix) on an imperial shipment — must arrive as 83.82 cm."""
        r = requests.post(f"{BASE_URL}/api/shipments/{imperial_shipment['id']}/items",
                          headers=headers, json={
                              "name": "Bare imperial",
                              "dims_cm": {"length": 33, "width": 0, "height": 0},
                          }, timeout=10)
        assert abs(r.json()["dims_cm"]["length"] - 83.82) < 0.01

    def test_metric_shipment_preserves_cm_numbers(self, metric_shipment, headers):
        r = requests.post(f"{BASE_URL}/api/shipments/{metric_shipment['id']}/items",
                          headers=headers, json={
                              "name": "Bare metric",
                              "dims_cm": {"length": 84, "width": 0, "height": 0},
                          }, timeout=10)
        assert r.json()["dims_cm"]["length"] == 84.0

    def test_cm_suffix_works_in_imperial_mode_too(self, imperial_shipment, headers):
        """Explicit `84cm` must always mean cm, regardless of shipment units."""
        r = requests.post(f"{BASE_URL}/api/shipments/{imperial_shipment['id']}/items",
                          headers=headers, json={
                              "name": "Mixed-mode item",
                              "dims_cm": {"length": "84cm", "width": "200mm", "height": "0.5m"},
                          }, timeout=10)
        item = r.json()
        assert item["dims_cm"]["length"] == 84.0
        assert abs(item["dims_cm"]["width"] - 20.0) < 0.01
        assert abs(item["dims_cm"]["height"] - 50.0) < 0.01
