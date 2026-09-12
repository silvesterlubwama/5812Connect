"""iter319 review — public shop, sale-payment-status JE lifecycle, customers/statements/resources/payment-reminders repairs, campus-reports removed."""
import os
import time
import pytest
import requests

from dotenv import load_dotenv

import creds  # env-backed logins, see tests/creds.py
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD

# Known tenant fixtures (per review request)
GALA_PRODUCT_ID = "prod_1543e921"  # 25,000 UGX, stock 97, sell_online false
GALA_INITIAL_STOCK = 97
GALA_PRICE = 25000
RESOURCE_ID = "res_43eda24a"


# ------- fixtures -------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def anon():
    """No auth session for public endpoints."""
    return requests.Session()


# Track things to clean up
CREATED = {"sales": [], "customers": [], "journal_entries": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(h):
    yield
    # Delete sales FIRST (each restores stock)
    for sid in CREATED["sales"]:
        try:
            requests.delete(f"{BASE_URL}/api/sales/{sid}", headers=h, timeout=20)
        except Exception:
            pass
    # THEN reset product to original state
    try:
        requests.put(f"{BASE_URL}/api/products/{GALA_PRODUCT_ID}",
                     json={"sell_online": False, "stock": GALA_INITIAL_STOCK}, headers=h, timeout=20)
    except Exception as e:
        print(f"cleanup product failed: {e}")
    for cid in CREATED["customers"]:
        try:
            requests.delete(f"{BASE_URL}/api/customers/{cid}", headers=h, timeout=20)
        except Exception:
            pass


# ============= 1. PUBLIC SHOP: opt-in required =============
class TestPublicShopOptIn:
    def test_public_products_unauth_no_optin(self, anon, h):
        # Ensure gala is opted-out
        r = requests.put(f"{BASE_URL}/api/products/{GALA_PRODUCT_ID}",
                         json={"sell_online": False}, headers=h, timeout=20)
        assert r.status_code == 200, r.text
        r = anon.get(f"{BASE_URL}/api/public/products", timeout=20)
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert GALA_PRODUCT_ID not in ids, "Product must not be public until sell_online=true"

    def test_publish_product_appears(self, anon, h):
        r = requests.put(f"{BASE_URL}/api/products/{GALA_PRODUCT_ID}",
                         json={"sell_online": True}, headers=h, timeout=20)
        assert r.status_code == 200
        r = anon.get(f"{BASE_URL}/api/public/products", timeout=20)
        assert r.status_code == 200
        products = r.json()
        gala = next((p for p in products if p["id"] == GALA_PRODUCT_ID), None)
        assert gala is not None, "Published product should appear"
        # Fields required
        for f in ("name", "price", "currency", "stock", "country"):
            assert f in gala, f"missing {f} in public product"
        assert float(gala["price"]) == GALA_PRICE

    def test_country_filter_ug(self, anon):
        r = anon.get(f"{BASE_URL}/api/public/products?country=UG", timeout=20)
        assert r.status_code == 200
        for p in r.json():
            assert p["country"] in ("UG", ""), f"non-UG leaked: {p}"


# ============= 2. PUBLIC SHOP: ordering + security =============
class TestPublicShopOrdering:
    def test_missing_name(self, anon):
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"email": "x@y.com", "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 1}]}, timeout=20)
        assert r.status_code == 400

    def test_missing_email(self, anon):
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"name": "Test", "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 1}]}, timeout=20)
        assert r.status_code == 400

    def test_empty_basket(self, anon):
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"name": "Test", "email": "x@y.com", "items": []}, timeout=20)
        assert r.status_code == 400

    def test_over_stock_rejected(self, anon):
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"name": "Test", "email": "x@y.com",
                            "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 9999}]}, timeout=20)
        assert r.status_code in (400, 409)

    def test_price_tampering_ignored(self, anon, h):
        """CRITICAL SECURITY: fake price=1 must be ignored, real price charged."""
        payload = {
            "name": "TEST_PriceTamper",
            "email": "tamper_test@example.com",
            "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 1, "price": 1}],
        }
        r = anon.post(f"{BASE_URL}/api/public/orders", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert float(data["total"]) == GALA_PRICE, f"tampered price not rejected: got total {data['total']}"
        sale_id = data["id"]
        CREATED["sales"].append(sale_id)
        # Verify server-side sale
        r2 = requests.get(f"{BASE_URL}/api/sales/by-receipt/{sale_id}", timeout=20)
        assert r2.status_code == 200
        assert float(r2.json()["total"]) == GALA_PRICE

    def test_non_sell_online_rejected(self, anon, h):
        # Find a product not opted-in
        r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=20)
        assert r.status_code == 200
        other = next((p for p in r.json() if p["id"] != GALA_PRODUCT_ID and not p.get("sell_online")), None)
        if not other:
            pytest.skip("no non-published product available")
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"name": "T", "email": "x@y.com",
                            "items": [{"product_id": other["id"], "quantity": 1}]}, timeout=20)
        assert r.status_code == 400


# ============= 3. PUBLIC SHOP knock-on effects =============
class TestPublicShopSideEffects:
    def test_order_effects(self, anon, h):
        # Fetch stock before
        r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=20)
        gala = next(p for p in r.json() if p["id"] == GALA_PRODUCT_ID)
        stock_before = float(gala["stock"])

        payload = {"name": "TEST_SideEffects", "email": "se@example.com",
                   "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 2}]}
        r = anon.post(f"{BASE_URL}/api/public/orders", json=payload, timeout=30)
        assert r.status_code == 200
        sale_id = r.json()["id"]
        CREATED["sales"].append(sale_id)
        assert r.json()["payment_status"] == "pending"

        # Stock decremented
        r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=20)
        gala = next(p for p in r.json() if p["id"] == GALA_PRODUCT_ID)
        assert float(gala["stock"]) == stock_before - 2

        # Sale in staff Sales list with channel='online'
        r = requests.get(f"{BASE_URL}/api/sales?limit=50", headers=h, timeout=20)
        assert r.status_code == 200
        found = next((s for s in r.json() if s["id"] == sale_id), None)
        assert found, "online sale not visible to staff"
        assert found.get("channel") == "online"
        assert found.get("cashier") == "Website order"
        assert found.get("payment_status") == "pending"

        # No journal entry for pending online sale
        r = requests.get(f"{BASE_URL}/api/finance/journal?limit=200", headers=h, timeout=20)
        assert r.status_code == 200
        entries = r.json() if isinstance(r.json(), list) else r.json().get("entries", [])
        matching = [e for e in entries if e.get("idempotency_key") == f"sale:{sale_id}" and not e.get("reversed")]
        assert not matching, f"Online pending sale should NOT have JE yet: {matching}"


# ============= 4. Accounting: payment-status → JE lifecycle =============
class TestPaymentStatusJournalEntry:
    def _get_je(self, h, sale_id):
        r = requests.get(f"{BASE_URL}/api/finance/journal?limit=500", headers=h, timeout=20)
        assert r.status_code == 200
        entries = r.json() if isinstance(r.json(), list) else r.json().get("entries", [])
        return [e for e in entries if e.get("idempotency_key") == f"sale:{sale_id}"]

    def test_paid_posts_reverse_and_no_double_post(self, anon, h):
        # Create a pending sale via public shop
        r = anon.post(f"{BASE_URL}/api/public/orders",
                      json={"name": "TEST_JELifecycle", "email": "je@example.com",
                            "items": [{"product_id": GALA_PRODUCT_ID, "quantity": 1}]}, timeout=30)
        assert r.status_code == 200
        sale_id = r.json()["id"]
        CREATED["sales"].append(sale_id)

        # Mark paid → should post balanced JE
        r = requests.put(f"{BASE_URL}/api/sales/{sale_id}/payment-status",
                         json={"payment_status": "paid"}, headers=h, timeout=20)
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        entries = self._get_je(h, sale_id)
        live = [e for e in entries if not e.get("reversed")]
        assert len(live) == 1, f"expected 1 live JE after paid, got {len(live)}: {entries}"
        je = live[0]
        # Balanced check
        debits = sum(float(l.get("debit") or 0) for l in je.get("lines", []))
        credits = sum(float(l.get("credit") or 0) for l in je.get("lines", []))
        assert abs(debits - credits) < 0.01, f"JE unbalanced: D={debits} C={credits}"
        assert abs(debits - GALA_PRICE) < 0.01
        codes = {l.get("account_code") for l in je.get("lines", [])}
        assert "4100" in codes, f"expected revenue 4100, got {codes}"

        # Mark paid again → NO double post
        r = requests.put(f"{BASE_URL}/api/sales/{sale_id}/payment-status",
                         json={"payment_status": "paid"}, headers=h, timeout=20)
        assert r.status_code == 200
        time.sleep(0.5)
        entries = self._get_je(h, sale_id)
        live = [e for e in entries if not e.get("reversed")]
        assert len(live) == 1, f"double-post detected: {len(live)} live JEs"

        # Mark pending → JE reversed
        r = requests.put(f"{BASE_URL}/api/sales/{sale_id}/payment-status",
                         json={"payment_status": "pending"}, headers=h, timeout=20)
        assert r.status_code == 200
        time.sleep(0.5)
        entries = self._get_je(h, sale_id)
        live = [e for e in entries if not e.get("reversed")]
        assert len(live) == 0, f"expected 0 live JE after un-pay, got {len(live)}"


# ============= 5. Customers CRUD =============
class TestCustomers:
    def test_list_customers(self, h):
        r = requests.get(f"{BASE_URL}/api/customers", headers=h, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_customer_crud(self, h):
        payload = {"name": "TEST_CustomerIter319", "email": "test319@example.com", "phone": "+256700000319"}
        r = requests.post(f"{BASE_URL}/api/customers", json=payload, headers=h, timeout=20)
        assert r.status_code == 200, r.text
        c = r.json()
        cid = c["id"]
        CREATED["customers"].append(cid)
        assert c["name"] == payload["name"]

        # Get by id (includes purchases)
        r = requests.get(f"{BASE_URL}/api/customers/{cid}", headers=h, timeout=20)
        assert r.status_code == 200
        assert "purchases" in r.json()

        # Update
        r = requests.put(f"{BASE_URL}/api/customers/{cid}",
                         json={"notes": "updated"}, headers=h, timeout=20)
        assert r.status_code == 200
        assert r.json().get("notes") == "updated"

        # Purchases endpoint
        r = requests.get(f"{BASE_URL}/api/customers/{cid}/purchases", headers=h, timeout=20)
        assert r.status_code == 200
        assert "purchases" in r.json()

        # Delete
        r = requests.delete(f"{BASE_URL}/api/customers/{cid}", headers=h, timeout=20)
        assert r.status_code == 200
        CREATED["customers"].remove(cid)


# ============= 6. Statements + Payment Reminders =============
class TestStatements:
    def test_statement_json(self, h):
        r = requests.get(f"{BASE_URL}/api/customer-statements/anyname?format=json", headers=h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("customer", "sales", "total_billed", "total_outstanding"):
            assert k in d

    def test_schedule_list(self, h):
        r = requests.get(f"{BASE_URL}/api/customer-statements/schedule/list", headers=h, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_schedule_save(self, h):
        # Need a customer first
        r = requests.post(f"{BASE_URL}/api/customers",
                          json={"name": "TEST_SchedCust", "email": "sc@example.com"}, headers=h, timeout=20)
        cid = r.json()["id"]
        CREATED["customers"].append(cid)
        r = requests.post(f"{BASE_URL}/api/customer-statements/schedule",
                          json={"customer_id": cid, "cadence": "monthly", "day_of_month": 1}, headers=h, timeout=20)
        assert r.status_code == 200
        assert r.json()["cadence"] == "monthly"


class TestPaymentReminders:
    def test_reminder_endpoint_exists(self, h):
        # Send with a fake customer to confirm endpoint returns a 400 (validation), not 404
        r = requests.post(f"{BASE_URL}/api/payment-reminders/send",
                          json={"customer_id_or_name": "TEST_nonexistent_reminder_iter319"}, headers=h, timeout=20)
        assert r.status_code != 404, "payment-reminders/send should not 404"
        # Expected 400 due to no outstanding sales or no email
        assert r.status_code == 400


# ============= 7. Resources single-get =============
class TestResources:
    def test_get_resource_by_id(self, h):
        r = requests.get(f"{BASE_URL}/api/resources/{RESOURCE_ID}", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("id") == RESOURCE_ID


# ============= 8. Chart-of-accounts seed (HR repair repointed) =============
class TestChartAccountsSeed:
    def test_seed_idempotent(self, h):
        r = requests.post(f"{BASE_URL}/api/finance/chart-of-accounts/seed", json={}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "inserted" in data or "count" in data or "message" in data


# ============= 9. Campus Reports removed =============
class TestCampusReportsRemoved:
    def test_backend_campus_reports_removed(self, h):
        # These endpoints must not exist
        for path in ("/api/campus-reports", "/api/reports/campus", "/api/campus_reports"):
            r = requests.get(f"{BASE_URL}{path}", headers=h, timeout=15)
            assert r.status_code in (404, 405), f"{path} still responds {r.status_code}"


# ============= 10. Regression: store-settings + POS still work =============
class TestRegression:
    def test_store_settings(self, h):
        r = requests.get(f"{BASE_URL}/api/store-settings/loc_001", headers=h, timeout=20)
        assert r.status_code == 200

    def test_pos_cash_sale_posts_je_and_decrements_stock(self, h):
        # Get stock
        r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=20)
        gala = next(p for p in r.json() if p["id"] == GALA_PRODUCT_ID)
        stock_before = float(gala["stock"])

        payload = {
            "items": [{"product_id": GALA_PRODUCT_ID, "name": "Gala Ticket",
                       "price": GALA_PRICE, "qty": 1, "units_per_pack": 1}],
            "total": GALA_PRICE, "payment_method": "cash",
            "customer_name": "TEST_POS_iter319", "location_id": "loc_001",
        }
        r = requests.post(f"{BASE_URL}/api/sales", json=payload, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        sale = r.json()
        sale_id = sale["id"]
        CREATED["sales"].append(sale_id)
        assert sale["payment_status"] == "paid"

        time.sleep(0.5)
        # Stock decremented
        r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=20)
        gala = next(p for p in r.json() if p["id"] == GALA_PRODUCT_ID)
        assert float(gala["stock"]) == stock_before - 1

        # JE posted immediately
        r = requests.get(f"{BASE_URL}/api/finance/journal?limit=500", headers=h, timeout=20)
        entries = r.json() if isinstance(r.json(), list) else r.json().get("entries", [])
        live = [e for e in entries if e.get("idempotency_key") == f"sale:{sale_id}" and not e.get("reversed")]
        assert len(live) == 1
