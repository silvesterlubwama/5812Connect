"""Iteration 80 — backend tests for receipt overhaul, expense workflow, draft sales,
sheet import, financial_accounts auto-creation, restricted-locations filter, and
product variants update.

Run:
    pytest /app/backend/tests/test_iteration80_features.py -v --tb=short \
        --junitxml=/app/test_reports/pytest/pytest_iter80.xml
"""
import os
import re
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


# ========== Fixtures ==========

@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Auth failed: {r.status_code} {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def admin_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def campus_id(admin_headers):
    """First main/campus location id."""
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    locs = r.json()
    for loc in locs:
        if loc.get("type") in ("main", "campus"):
            return loc["id"]
    return locs[0]["id"] if locs else "loc_001"


# ========== BUG 1: financial_accounts ==========

class TestFinancialAccounts:
    def test_accounts_have_id_starting_balance_currency(self, admin_headers, campus_id):
        r = requests.get(
            f"{BASE_URL}/api/financial/accounts",
            headers=admin_headers, params={"campus_id": campus_id}, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        accounts = data.get("accounts") if isinstance(data, dict) else data
        assert isinstance(accounts, list) and len(accounts) > 0, f"No accounts returned: {data}"
        for acct in accounts:
            assert "id" in acct, f"missing id: {acct}"
            assert acct["id"].startswith("acct_"), f"id format wrong: {acct['id']}"
            assert "starting_balance" in acct
            assert "currency" in acct


# ========== BUG 2/3: Expense workflow ==========

class TestExpenseWorkflow:
    def test_create_expense_pending_then_approve(self, admin_headers, campus_id):
        # Get baseline summary
        r0 = requests.get(f"{BASE_URL}/api/financial/summary",
                          headers=admin_headers, params={"location_id": campus_id}, timeout=20)
        assert r0.status_code == 200
        s0 = r0.json()
        base_pending = s0.get("pending_expenses_total", 0)
        base_expenses = s0.get("monthly_expenses", 0)

        # Create expense — use TODAY's date so it counts in monthly_expenses
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        payload = {"title": "TEST_iter80_expense", "amount": 12345,
                   "currency": "UGX", "category": "general",
                   "date": today, "location_id": campus_id}
        r = requests.post(f"{BASE_URL}/api/financial/expenses",
                          headers=admin_headers, json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        exp = r.json()
        exp_id = exp.get("id")
        assert exp_id
        assert exp.get("status") == "pending", f"new expense should be pending: {exp}"

        # Summary should include pending counters and NOT include in monthly_expenses yet
        r1 = requests.get(f"{BASE_URL}/api/financial/summary",
                          headers=admin_headers, params={"location_id": campus_id}, timeout=20)
        s1 = r1.json()
        assert s1.get("pending_expenses_total", 0) >= base_pending + 12345 - 1
        assert "pending_expenses_count" in s1
        assert s1.get("monthly_expenses", 0) <= base_expenses + 1, "pending should NOT be in monthly_expenses"

        # Approve
        ra = requests.put(f"{BASE_URL}/api/financial/expenses/{exp_id}/approve",
                         headers=admin_headers, json={"comment": "ok"}, timeout=20)
        assert ra.status_code == 200, ra.text

        # After approve, monthly_expenses should grow
        r2 = requests.get(f"{BASE_URL}/api/financial/summary",
                          headers=admin_headers, params={"location_id": campus_id}, timeout=20)
        s2 = r2.json()
        assert s2.get("monthly_expenses", 0) >= base_expenses + 12345 - 1, \
            f"approved expense missing from totals: base={base_expenses} after={s2.get('monthly_expenses')}"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}",
                       headers=admin_headers, timeout=10)

    def test_reject_expense(self, admin_headers, campus_id):
        payload = {"title": "TEST_iter80_reject", "amount": 999,
                   "currency": "UGX", "category": "general",
                   "date": "2026-01-15", "location_id": campus_id}
        r = requests.post(f"{BASE_URL}/api/financial/expenses",
                          headers=admin_headers, json=payload, timeout=20)
        assert r.status_code in (200, 201)
        exp_id = r.json()["id"]

        rj = requests.put(f"{BASE_URL}/api/financial/expenses/{exp_id}/reject",
                         headers=admin_headers, json={"comment": "duplicate"}, timeout=20)
        assert rj.status_code == 200, rj.text

        # Cleanup
        requests.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}",
                       headers=admin_headers, timeout=10)


# ========== BUG 4: Product variants update ==========

class TestProductVariants:
    def test_put_product_with_variants_recomputes_stock(self, admin_headers, campus_id):
        # Create product
        r = requests.post(f"{BASE_URL}/api/products",
                          headers=admin_headers,
                          json={"name": "TEST_iter80_prod", "price": 100,
                                "stock": 0, "location_id": campus_id}, timeout=20)
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        try:
            # Update with variants
            up = {
                "has_variants": True,
                "variants": [
                    {"id": "v1", "name": "Small", "price": 100, "stock": 5},
                    {"id": "v2", "name": "Large", "price": 150, "stock": 7},
                ],
            }
            r2 = requests.put(f"{BASE_URL}/api/products/{pid}",
                              headers=admin_headers, json=up, timeout=20)
            assert r2.status_code == 200, r2.text
            updated = r2.json()
            assert updated.get("has_variants") is True
            assert len(updated.get("variants") or []) == 2
            # Stock should be auto-computed = 5 + 7 = 12
            assert updated.get("stock") == 12, f"stock should be sum of variants: {updated.get('stock')}"
        finally:
            requests.delete(f"{BASE_URL}/api/products/{pid}",
                            headers=admin_headers, timeout=10)


# ========== BUG 6: locations filtering (admin-only test) ==========

class TestLocationsFilter:
    def test_admin_sees_all_locations(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        locs = r.json()
        assert isinstance(locs, list)
        assert len(locs) >= 1


# ========== Receipt overhaul: INV-YYYYMMDD-NNNN, drafts, by-receipt ==========

class TestReceiptAndDrafts:
    @pytest.fixture
    def created_sale(self, admin_headers, campus_id):
        payload = {
            "items": [{"name": "TEST item", "qty": 1, "unit_price": 500}],
            "total": 500,
            "payment_method": "cash",
            "customer_name": "Walk-in",
            "location_id": campus_id,
        }
        r = requests.post(f"{BASE_URL}/api/sales", headers=admin_headers,
                          json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        sale = r.json()
        yield sale

    def test_sale_returns_inv_receipt_number(self, created_sale):
        rn = created_sale.get("receipt_number")
        assert rn, f"missing receipt_number: {created_sale}"
        assert re.match(r"^INV-\d{8}-\d{4}$", rn), f"bad receipt format: {rn}"
        assert created_sale.get("id") == rn  # id == receipt_number

    def test_public_lookup_by_receipt_no_auth(self, created_sale):
        rn = created_sale["receipt_number"]
        # NO auth header → must be public
        r = requests.get(f"{BASE_URL}/api/sales/by-receipt/{rn}", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("receipt_number") == rn
        assert body.get("total") == 500
        assert "items" in body
        assert "cashier" in body

    def test_public_lookup_404(self):
        r = requests.get(f"{BASE_URL}/api/sales/by-receipt/INV-99991231-9999", timeout=20)
        assert r.status_code == 404

    def test_park_and_list_and_delete_draft(self, admin_headers, campus_id):
        # Park
        payload = {
            "items": [{"name": "Parked item", "qty": 2, "unit_price": 100}],
            "total": 200, "customer_name": "Walk-in",
            "payment_method": "cash", "location_id": campus_id,
        }
        r = requests.post(f"{BASE_URL}/api/sales/drafts",
                          headers=admin_headers, json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        draft = r.json()
        assert draft.get("id", "").startswith("draft_")
        assert draft.get("status") == "draft"

        # List
        rl = requests.get(f"{BASE_URL}/api/sales/drafts",
                         headers=admin_headers, timeout=20)
        assert rl.status_code == 200
        drafts = rl.json()
        assert any(d["id"] == draft["id"] for d in drafts), \
            f"created draft not in list: {[d['id'] for d in drafts]}"

        # Delete
        rd = requests.delete(f"{BASE_URL}/api/sales/drafts/{draft['id']}",
                            headers=admin_headers, timeout=20)
        assert rd.status_code == 200

        # Verify removal
        rl2 = requests.get(f"{BASE_URL}/api/sales/drafts",
                          headers=admin_headers, timeout=20)
        drafts2 = rl2.json()
        assert not any(d["id"] == draft["id"] for d in drafts2)


# ========== Sheet import ==========

class TestSheetImport:
    def test_import_expense_rows_with_messy_amounts_and_dates(self, admin_headers, campus_id):
        rows = [
            {"Date": "15/01/26", "Vendor": "TEST_VendorA",
             "Purpose/Beneficiary/Notes": "TEST_iter80_sheet purchase",
             "Reff./Receipt#": "RX-001", "ACCOUNT": "CASH DRAWER",
             "Department": "FARM", "Budget": "supplies",
             "TOTAL UGX": "UGX480,000", "USD": "$130.50"},
            {"Date": "16/01", "Vendor": "TEST_VendorB",
             "Purpose/Beneficiary/Notes": "Another row",
             "Reff./Receipt#": "RX-002", "ACCOUNT": "MTN MOMO",
             "Department": "OUTREACH", "Budget": "transport",
             "TOTAL UGX": "120,000", "USD": ""},
            # Empty / invalid row → should be skipped (amount=0)
            {"Date": "", "Vendor": "", "TOTAL UGX": "0"},
        ]
        body = {"type": "expense", "rows": rows,
                "default_status": "pending", "location_id": campus_id}
        r = requests.post(f"{BASE_URL}/api/financial/import-sheet",
                          headers=admin_headers, json=body, timeout=30)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result.get("created") == 2, f"expected 2 created, got {result}"
        assert result.get("skipped") >= 1

        # Spot-check that the created docs have the new fields persisted
        re_list = requests.get(f"{BASE_URL}/api/financial/expenses",
                               headers=admin_headers, timeout=20)
        assert re_list.status_code == 200
        items = re_list.json()
        if isinstance(items, dict):
            items = items.get("expenses") or items.get("items") or []
        imported = [e for e in items if (e.get("source") == "sheet_import"
                                          and e.get("vendor", "").startswith("TEST_Vendor"))]
        assert len(imported) >= 2, f"imported docs not found in /expenses: {len(imported)}"
        sample = imported[0]
        for f in ("vendor", "receipt_number", "account", "department",
                  "budget_category"):
            assert f in sample, f"missing field {f} in imported expense"
        # Date normalization: 15/01/26 → 2026-01-15
        d_match = next((e for e in imported if e.get("vendor") == "TEST_VendorA"), None)
        if d_match:
            assert d_match.get("date") == "2026-01-15", f"date norm failed: {d_match.get('date')}"
            assert d_match.get("amount") == 480000.0
            assert d_match.get("usd_equivalent") == 130.5

        # Cleanup
        for e in imported:
            requests.delete(f"{BASE_URL}/api/financial/expenses/{e['id']}",
                           headers=admin_headers, timeout=10)

    def test_import_donation_rows(self, admin_headers, campus_id):
        rows = [{"Date": "10/01/2026", "Vendor": "TEST_DonorX",
                 "TOTAL UGX": "250,000", "Department": "GENERAL",
                 "Budget": "tithe"}]
        r = requests.post(f"{BASE_URL}/api/financial/import-sheet",
                          headers=admin_headers,
                          json={"type": "donation", "rows": rows,
                                "location_id": campus_id}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("created") == 1

        # Cleanup
        rdon = requests.get(f"{BASE_URL}/api/financial/donations",
                            headers=admin_headers, timeout=20)
        if rdon.status_code == 200:
            dlist = rdon.json()
            if isinstance(dlist, dict):
                dlist = dlist.get("donations") or dlist.get("items") or []
            for d in dlist:
                if d.get("source") == "sheet_import" and d.get("donor_name") == "TEST_DonorX":
                    requests.delete(f"{BASE_URL}/api/financial/donations/{d['id']}",
                                   headers=admin_headers, timeout=10)

    def test_import_empty_rows_returns_400(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/financial/import-sheet",
                          headers=admin_headers,
                          json={"type": "expense", "rows": []}, timeout=20)
        assert r.status_code == 400
