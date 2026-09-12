"""
Iteration 81 — Verify backend split (financial.py → sales.py / products.py / sheet_import.py)
Tests all previously-in-financial endpoints still respond + regressions from iter80.
"""
import os
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD},
        timeout=30,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    token = resp.json().get("token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------- PRODUCTS router (NEW) ----------

class TestProductsRouter:
    def test_get_products(self, session):
        r = session.get(f"{BASE_URL}/api/products", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_product_crud_and_variants(self, session):
        # CREATE
        payload = {"name": f"TEST_prod_{uuid.uuid4().hex[:6]}", "price": 100, "stock": 5}
        r = session.post(f"{BASE_URL}/api/products", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        prod = r.json()
        pid = prod["id"]
        assert prod["name"] == payload["name"]

        try:
            # UPDATE
            r = session.put(f"{BASE_URL}/api/products/{pid}", json={"price": 150}, timeout=30)
            assert r.status_code == 200
            assert r.json()["price"] == 150

            # ADD VARIANT
            r = session.post(
                f"{BASE_URL}/api/products/{pid}/variants",
                json={"name": "Red-L", "type": "color-size", "value": "Red/Large", "price": 150, "stock": 3},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            variant = r.json()
            vid = variant["id"]
            assert variant.get("barcode")

            # UPDATE VARIANT
            r = session.put(
                f"{BASE_URL}/api/products/{pid}/variants/{vid}",
                json={"price": 175, "stock": 4},
                timeout=30,
            )
            assert r.status_code == 200
            assert r.json()["price"] == 175
            assert r.json()["stock"] == 4

            # DELETE VARIANT
            r = session.delete(f"{BASE_URL}/api/products/{pid}/variants/{vid}", timeout=30)
            assert r.status_code == 200

        finally:
            # CLEANUP — DELETE PRODUCT
            r = session.delete(f"{BASE_URL}/api/products/{pid}", timeout=30)
            assert r.status_code == 200


# ---------- SALES router (NEW) ----------

class TestSalesRouter:
    def test_get_sales(self, session):
        r = session.get(f"{BASE_URL}/api/sales", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_sale_receipt_format(self, session):
        payload = {
            "items": [{"name": "TEST_item", "qty": 1, "unit_price": 1000}],
            "customer_name": "TEST_customer_iter81",
            "total": 1000,
            "payment_method": "cash",
        }
        r = session.post(f"{BASE_URL}/api/sales", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        sale = r.json()
        rn = sale.get("receipt_number", "")
        # INV-YYYYMMDD-NNNN
        import re
        assert re.match(r"^INV-\d{8}-\d{4}$", rn), f"Receipt number format wrong: {rn}"
        assert sale.get("id") == rn
        pytest.sale_receipt = rn
        pytest.sale_id = sale["id"]

    def test_drafts_crud(self, session):
        # CREATE
        r = session.post(
            f"{BASE_URL}/api/sales/drafts",
            json={"items": [{"name": "x", "qty": 1, "unit_price": 5}], "total": 5},
            timeout=30,
        )
        assert r.status_code == 200
        draft = r.json()
        did = draft["id"]
        assert draft.get("status") == "draft"

        # LIST
        r = session.get(f"{BASE_URL}/api/sales/drafts", timeout=30)
        assert r.status_code == 200
        assert any(d["id"] == did for d in r.json())

        # DELETE
        r = session.delete(f"{BASE_URL}/api/sales/drafts/{did}", timeout=30)
        assert r.status_code == 200

    def test_public_receipt_lookup_no_auth(self):
        # Use a fresh session WITHOUT auth header
        rn = getattr(pytest, "sale_receipt", None)
        if not rn:
            pytest.skip("No receipt from prior test")
        r = requests.get(f"{BASE_URL}/api/sales/by-receipt/{rn}", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["receipt_number"] == rn
        # sensitive fields should be absent
        assert "created_by" not in data
        assert "cashier_id" not in data


# ---------- SHEET IMPORT router (NEW) ----------

class TestSheetImportRouter:
    def test_import_sheet_expense(self, session):
        payload = {
            "type": "expense",
            "rows": [
                {"date": "15/01/26", "vendor": "TEST_vendor", "purpose": "TEST_iter81 import", "amount": "UGX480,000"},
            ],
        }
        r = session.post(f"{BASE_URL}/api/financial/import-sheet", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 1
        assert data["type"] == "expense"


# ---------- FINANCIAL router (REGRESSION from iter80) ----------

class TestFinancialRegressions:
    def test_financial_summary(self, session):
        r = session.get(f"{BASE_URL}/api/financial/summary", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "monthly_expenses" in data
        assert "pending_expenses_total" in data

    def test_financial_expenses_list(self, session):
        r = session.get(f"{BASE_URL}/api/financial/expenses", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_financial_accounts(self, session):
        r = session.get(f"{BASE_URL}/api/financial/accounts", timeout=30)
        assert r.status_code == 200

    def test_expense_approve_reject_workflow(self, session):
        # Create an expense
        payload = {
            "title": "TEST_iter81_workflow",
            "amount": 500,
            "category": "test",
            "date": "2026-01-15",
            "status": "pending",
        }
        r = session.post(f"{BASE_URL}/api/financial/expenses", json=payload, timeout=30)
        assert r.status_code == 200
        exp = r.json()
        eid = exp["id"]
        assert exp.get("status") == "pending"

        # Approve (PUT)
        r = session.put(f"{BASE_URL}/api/financial/expenses/{eid}/approve", timeout=30)
        assert r.status_code == 200, r.text

        # Reject (create second one)
        r = session.post(f"{BASE_URL}/api/financial/expenses", json=payload, timeout=30)
        eid2 = r.json()["id"]
        r = session.put(
            f"{BASE_URL}/api/financial/expenses/{eid2}/reject",
            json={"comment": "not justified"},
            timeout=30,
        )
        assert r.status_code == 200, r.text


# ---------- CUSTOMERS (regression) ----------

class TestCustomers:
    def test_list_customers(self, session):
        r = session.get(f"{BASE_URL}/api/customers", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_customer_purchases_endpoint(self, session):
        r = session.get(f"{BASE_URL}/api/customers", timeout=30)
        items = r.json()
        if not items:
            pytest.skip("No customers")
        cid = items[0]["id"]
        r1 = session.get(f"{BASE_URL}/api/customers/{cid}", timeout=30)
        assert r1.status_code == 200
        r2 = session.get(f"{BASE_URL}/api/customers/{cid}/purchases", timeout=30)
        assert r2.status_code == 200
