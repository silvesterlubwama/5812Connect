"""Iteration 86 tests — Marketplace invoices + 58:12 resource serials."""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
LOC_ID = "loc_419f5d5e"  # 58:12 Uganda


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def state():
    return {}


# ---------- INVOICES ----------

class TestInvoices:
    def test_create_invoice(self, headers, state):
        payload = {
            "customer_name": "TEST_Invoice_Customer",
            "items": [
                {"name": "TEST Item A", "qty": 2, "unit_price": 5000},
                {"name": "TEST Item B", "qty": 1, "unit_price": 3000, "discount": 500},
            ],
            "discount": 0,
            "tax_amount": 200,
            "notes": "TEST invoice",
        }
        r = requests.post(f"{BASE_URL}/api/invoices", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["status"] == "draft"
        assert inv["invoice_number"].startswith("INV-DRAFT-")
        # subtotal = 2*5000 + 1*3000 = 13000
        assert inv["subtotal"] == 13000
        # total = (2*5000 - 0) + (1*3000 - 500) - 0 + 200 = 12700
        assert inv["total"] == 12700
        state["invoice_id"] = inv["id"]
        state["invoice_number"] = inv["invoice_number"]

    def test_list_invoices_filter_draft(self, headers, state):
        r = requests.get(f"{BASE_URL}/api/invoices?status=draft", headers=headers)
        assert r.status_code == 200
        data = r.json()
        ids = [i.get("id") for i in data]
        assert state["invoice_id"] in ids

    def test_update_invoice_recomputes_total(self, headers, state):
        new_items = [{"name": "TEST Item X", "qty": 3, "unit_price": 2000}]
        r = requests.put(f"{BASE_URL}/api/invoices/{state['invoice_id']}",
                         json={"items": new_items, "discount": 100, "tax_amount": 0,
                               "notes": "Updated"}, headers=headers)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["subtotal"] == 6000
        assert inv["total"] == 5900
        assert inv["notes"] == "Updated"

    def test_convert_invoice_with_overrides(self, headers, state):
        # Use real product for stock decrement test
        pr = requests.get(f"{BASE_URL}/api/products", headers=headers)
        assert pr.status_code == 200
        products = pr.json()
        if not products:
            pytest.skip("No products available to test stock decrement")
        prod = products[0]
        state["product_id"] = prod["id"]
        state["initial_stock"] = prod.get("stock", 0)

        # Update invoice to include real product
        upd = requests.put(
            f"{BASE_URL}/api/invoices/{state['invoice_id']}",
            json={"items": [{"name": prod["name"], "qty": 1,
                             "unit_price": prod.get("price", 1000),
                             "product_id": prod["id"]}]},
            headers=headers,
        )
        assert upd.status_code == 200

        r = requests.post(
            f"{BASE_URL}/api/invoices/{state['invoice_id']}/convert",
            json={"payment_method": "cash", "customer_name": "TEST_Converted"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "receipt_number" in data
        assert data["receipt_number"].startswith("INV-")
        assert data["sale"]["from_invoice"] == state["invoice_number"]
        assert data["sale"]["payment_status"] == "paid"
        state["receipt_number"] = data["receipt_number"]

        # Verify invoice now converted
        ginv = requests.get(f"{BASE_URL}/api/invoices/{state['invoice_id']}", headers=headers)
        assert ginv.status_code == 200
        assert ginv.json()["status"] == "converted"
        assert ginv.json()["receipt_number"] == state["receipt_number"]

        # Verify stock decremented
        pr2 = requests.get(f"{BASE_URL}/api/products/{state['product_id']}", headers=headers)
        if pr2.status_code == 200:
            new_stock = pr2.json().get("stock", 0)
            assert new_stock == state["initial_stock"] - 1, f"Stock {state['initial_stock']}→{new_stock}"

    def test_convert_twice_rejected(self, headers, state):
        r = requests.post(f"{BASE_URL}/api/invoices/{state['invoice_id']}/convert",
                          json={}, headers=headers)
        assert r.status_code == 400

    def test_edit_converted_rejected(self, headers, state):
        r = requests.put(f"{BASE_URL}/api/invoices/{state['invoice_id']}",
                         json={"notes": "nope"}, headers=headers)
        assert r.status_code == 400

    def test_delete_converted_rejected(self, headers, state):
        r = requests.delete(f"{BASE_URL}/api/invoices/{state['invoice_id']}", headers=headers)
        assert r.status_code == 400

    def test_delete_draft_allowed(self, headers):
        # Create a fresh draft invoice and delete
        c = requests.post(f"{BASE_URL}/api/invoices",
                          json={"customer_name": "TEST_DeleteMe",
                                "items": [{"name": "x", "qty": 1, "unit_price": 100}]},
                          headers=headers)
        assert c.status_code == 200
        iid = c.json()["id"]
        d = requests.delete(f"{BASE_URL}/api/invoices/{iid}", headers=headers)
        assert d.status_code == 200
        g = requests.get(f"{BASE_URL}/api/invoices/{iid}", headers=headers)
        assert g.status_code == 404


# ---------- RESOURCE SERIALS ----------

class TestResourceSerials:
    def test_create_resource_auto_serial(self, headers, state):
        payload = {"name": "TEST_Resource_AutoSerial", "type": "equipment",
                   "location_id": LOC_ID, "quantity": 1}
        r = requests.post(f"{BASE_URL}/api/resources", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res.get("serial_auto_generated") is True
        sn = res.get("serial_number", "")
        assert sn.startswith("5812-"), f"Unexpected serial: {sn}"
        parts = sn.split("-")
        assert len(parts) == 4, sn
        # parts[1] should contain country + abbr (UG + 3 chars)
        assert parts[1].startswith("UG"), f"Expected UG prefix, got {parts[1]}"
        # Today DDMMYY
        expected_date = datetime.now(timezone.utc).strftime("%d%m%y")
        assert parts[2] == expected_date
        # barcode mirrors
        assert res.get("barcode") == sn
        state["auto_res_id"] = res["id"]
        state["auto_serial"] = sn

    def test_create_resource_custom_serial(self, headers, state):
        payload = {"name": "TEST_Resource_CustomSerial", "type": "equipment",
                   "location_id": LOC_ID, "serial_number": "MY-CUSTOM-123"}
        r = requests.post(f"{BASE_URL}/api/resources", json=payload, headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["serial_number"] == "MY-CUSTOM-123"
        assert res["barcode"] == "MY-CUSTOM-123"
        assert res.get("serial_auto_generated") is not True
        state["custom_res_id"] = res["id"]

    def test_regenerate_serial(self, headers, state):
        r = requests.post(
            f"{BASE_URL}/api/resources/{state['custom_res_id']}/generate-serial",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["serial_number"].startswith("5812-")
        assert data["barcode"] == data["serial_number"]

    def test_lookup_by_serial_public(self, state):
        # Public — no auth header
        r = requests.get(f"{BASE_URL}/api/resources/by-serial/{state['auto_serial']}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["serial_number"] == state["auto_serial"]
        assert data["name"] == "TEST_Resource_AutoSerial"
        assert data.get("location") is not None
        assert "name" in (data["location"] or {})

    def test_lookup_unknown_serial_404(self):
        r = requests.get(f"{BASE_URL}/api/resources/by-serial/UNKNOWN-XYZ-999")
        assert r.status_code == 404

    def test_cleanup(self, headers, state):
        for k in ("auto_res_id", "custom_res_id"):
            if state.get(k):
                requests.delete(f"{BASE_URL}/api/resources/{state[k]}", headers=headers)
