"""Iteration 203 — Chart Accounts backend tests.

Covers:
  1. Chart account CRUD (create/update/assignees/delete soft+hard).
  2. Listing + scoping (admin vs non-admin, /mine endpoint).
  3. Balance computation (donations in, pending vs approved expenses, sales).
  4. Access control on expenses/donations without/with account assignment.
  5. Access control on GET account / transactions.
  6. Transfers between accounts + validation.
  7. Sales deposit_to_account_id integration.
  8. Regressions on expenses/donations without account, balance-sheet.
"""
import os
import time
import uuid

import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD
STAFF_PW = creds.NEW_USER_PASSWORD
LOC_ID = "loc_001"


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=30,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def staff_user(admin_headers):
    """Create a fresh non-admin staff user; grant finance access so they hit the
    account-assignment check (not the module gate). Returns dict with user_id/email/token."""
    email = f"test_iter203_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        f"{BASE_URL}/api/admin/users",
        headers=admin_headers,
        json={
            "name": "TEST Iter203 Staff",
            "email": email,
            "role": "staff",
            "password": STAFF_PW,
            "also_create_member": False,
        },
        timeout=30,
    )
    assert r.status_code in (200, 201), f"create staff failed: {r.status_code} {r.text[:200]}"
    user = r.json()
    user_id = user["id"]

    # Grant finance access so require_finance_view passes.
    g = requests.put(
        f"{BASE_URL}/api/admin/finance-access/users/{user_id}",
        headers=admin_headers,
        json={"finance_access": True},
        timeout=30,
    )
    assert g.status_code == 200, f"finance grant failed: {g.status_code} {g.text[:200]}"

    # Login as staff
    login = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": email, "password": STAFF_PW},
        timeout=30,
    )
    assert login.status_code == 200, f"staff login failed: {login.status_code} {login.text[:200]}"
    token = login.json()["token"]

    yield {"id": user_id, "email": email, "token": token,
           "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}}

    # Cleanup
    try:
        requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers, timeout=10)
    except Exception:
        pass


@pytest.fixture
def make_account(admin_headers):
    """Factory to create + track chart accounts for cleanup."""
    created = []

    def _make(**overrides):
        payload = {
            "name": overrides.pop("name", f"TEST_Iter203_Cash_{uuid.uuid4().hex[:6]}"),
            "kind": "cash",
            "currency": "UGX",
            "starting_balance": 0,
            "location_id": LOC_ID,
            "assigned_user_ids": [],
        }
        payload.update(overrides)
        r = requests.post(
            f"{BASE_URL}/api/financial/chart-accounts",
            headers=admin_headers, json=payload, timeout=30,
        )
        assert r.status_code == 200, f"create account failed: {r.status_code} {r.text[:200]}"
        acct = r.json()
        created.append(acct["id"])
        return acct

    yield _make

    # Cleanup — soft or hard delete
    for aid in created:
        try:
            requests.delete(f"{BASE_URL}/api/financial/chart-accounts/{aid}",
                            headers=admin_headers, timeout=15)
        except Exception:
            pass


# ---------- 1. CHART ACCOUNT CRUD ----------

class TestChartAccountCRUD:
    def test_create_account_returns_full_shape(self, admin_headers, make_account):
        acct = make_account(
            name=f"TEST_Iter203_CashA_{uuid.uuid4().hex[:6]}",
            kind="cash", currency="UGX", starting_balance=50000,
            assigned_user_ids=[], notes="test",
        )
        assert acct["id"].startswith("cha_")
        assert acct["kind"] == "cash"
        assert acct["currency"] == "UGX"
        assert acct["starting_balance"] == 50000
        assert acct["assigned_user_ids"] == []
        assert acct["active"] is True
        assert acct["balance"] == 50000  # freshly created → equals starting

    def test_create_invalid_kind_400(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/financial/chart-accounts",
            headers=admin_headers,
            json={"name": "TEST_Iter203_Bad", "kind": "bogus_kind"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "kind" in r.text.lower()

    def test_update_account_fields(self, admin_headers, make_account):
        acct = make_account(starting_balance=1000)
        r = requests.put(
            f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}",
            headers=admin_headers,
            json={"name": acct["name"] + "_upd", "notes": "changed"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["name"].endswith("_upd")

    def test_set_assignees(self, admin_headers, make_account, staff_user):
        acct = make_account()
        r = requests.put(
            f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}/assignees",
            headers=admin_headers,
            json={"user_ids": [staff_user["id"]]},
            timeout=15,
        )
        assert r.status_code == 200
        assert staff_user["id"] in r.json()["assigned_user_ids"]

    def test_delete_no_txns_hard_deletes(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/financial/chart-accounts",
            headers=admin_headers,
            json={"name": f"TEST_Iter203_Del_{uuid.uuid4().hex[:6]}",
                  "kind": "cash", "location_id": LOC_ID},
            timeout=15,
        )
        aid = r.json()["id"]
        d = requests.delete(f"{BASE_URL}/api/financial/chart-accounts/{aid}",
                            headers=admin_headers, timeout=15)
        assert d.status_code == 200
        body = d.json()
        assert body.get("deleted") is True, f"expected hard delete, got {body}"

    def test_delete_with_txns_archives(self, admin_headers, make_account):
        acct = make_account(starting_balance=10000)
        # Post a donation referencing it
        don = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=admin_headers,
            json={"donor_name": "TEST Iter203 Donor", "amount": 500, "currency": "UGX",
                  "date": "2026-01-01", "location_id": LOC_ID,
                  "deposit_to_account_id": acct["id"]},
            timeout=15,
        )
        assert don.status_code == 200, don.text[:200]
        d = requests.delete(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}",
                            headers=admin_headers, timeout=15)
        assert d.status_code == 200
        body = d.json()
        assert body.get("archived") is True
        assert body.get("referenced_txns", 0) >= 1
        # cleanup donation
        try:
            requests.delete(f"{BASE_URL}/api/financial/donations/{don.json()['id']}",
                            headers=admin_headers, timeout=10)
        except Exception:
            pass


# ---------- 2. LIST + SCOPING ----------

class TestListAndScoping:
    def test_admin_sees_all(self, admin_headers, make_account):
        a1 = make_account()
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert a1["id"] in ids
        # every returned row has balance field
        assert all("balance" in x for x in r.json())

    def test_nonadmin_sees_only_assigned(self, admin_headers, make_account, staff_user):
        # Two accounts, staff assigned to one only.
        unassigned = make_account()
        assigned = make_account(assigned_user_ids=[staff_user["id"]])
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                         headers=staff_user["headers"], timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert assigned["id"] in ids
        assert unassigned["id"] not in ids

    def test_mine_returns_assigned(self, admin_headers, make_account, staff_user):
        assigned = make_account(assigned_user_ids=[staff_user["id"]])
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/mine",
                         headers=staff_user["headers"], timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert assigned["id"] in ids

    def test_mine_admin_bypasses(self, admin_headers, make_account):
        acct = make_account()  # empty assigned list
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/mine",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert acct["id"] in ids  # admin sees it even though not assigned


# ---------- 3. BALANCE COMPUTATION ----------

class TestBalanceComputation:
    def test_pending_expense_does_not_affect_balance_then_approve_deducts(
        self, admin_headers, make_account,
    ):
        acct = make_account(starting_balance=50000)
        aid = acct["id"]

        # Pending expense (created via /financial/expenses defaults to status=pending)
        exp = requests.post(
            f"{BASE_URL}/api/financial/expenses",
            headers=admin_headers,
            json={"title": "TEST Iter203 Exp", "amount": 8000, "currency": "UGX",
                  "date": "2026-01-05", "category": "office", "location_id": LOC_ID,
                  "paid_from_account_id": aid},
            timeout=15,
        )
        assert exp.status_code == 200, exp.text[:200]
        exp_id = exp.json()["id"]

        # Balance still 50000
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{aid}",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["balance"] == 50000, f"pending expense should not affect balance: got {r.json()['balance']}"

        # Approve it
        ap = requests.put(
            f"{BASE_URL}/api/financial/expenses/{exp_id}/approve",
            headers=admin_headers, json={"comment": "test"}, timeout=15,
        )
        assert ap.status_code == 200, ap.text[:200]

        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{aid}",
                         headers=admin_headers, timeout=15)
        assert r.json()["balance"] == 42000, f"after approve should be 42000, got {r.json()['balance']}"

        # Donation +20000 → 62000
        don = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=admin_headers,
            json={"donor_name": "TEST Iter203 Donor", "amount": 20000, "currency": "UGX",
                  "date": "2026-01-06", "location_id": LOC_ID,
                  "deposit_to_account_id": aid},
            timeout=15,
        )
        assert don.status_code == 200
        don_id = don.json()["id"]

        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{aid}",
                         headers=admin_headers, timeout=15)
        assert r.json()["balance"] == 62000

        # /transactions ledger
        t = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{aid}/transactions",
                         headers=admin_headers, timeout=15)
        assert t.status_code == 200
        body = t.json()
        assert body["balance"] == 62000
        assert body["starting_balance"] == 50000
        types = {(x["type"], x["direction"]) for x in body["transactions"]}
        assert ("expense", "out") in types
        assert ("donation", "in") in types

        # cleanup created txns
        requests.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}",
                        headers=admin_headers, timeout=10)
        requests.delete(f"{BASE_URL}/api/financial/donations/{don_id}",
                        headers=admin_headers, timeout=10)


# ---------- 4. ACCESS CONTROL on expense/donation creation ----------

class TestAccountAccessControl:
    def test_unassigned_nonadmin_expense_403(self, admin_headers, make_account, staff_user):
        acct = make_account(assigned_user_ids=[])  # nobody assigned
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses",
            headers=staff_user["headers"],
            json={"title": "TEST Iter203 Denied", "amount": 100, "currency": "UGX",
                  "date": "2026-01-07", "category": "office", "location_id": LOC_ID,
                  "paid_from_account_id": acct["id"]},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
        assert "not assigned" in r.text.lower()

    def test_unassigned_nonadmin_donation_403(self, admin_headers, make_account, staff_user):
        acct = make_account(assigned_user_ids=[])
        r = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=staff_user["headers"],
            json={"donor_name": "TEST", "amount": 100, "currency": "UGX",
                  "date": "2026-01-07", "location_id": LOC_ID,
                  "deposit_to_account_id": acct["id"]},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
        assert "not assigned" in r.text.lower()

    def test_assigned_nonadmin_can_use(self, admin_headers, make_account, staff_user):
        acct = make_account(assigned_user_ids=[staff_user["id"]])
        # expense
        exp = requests.post(
            f"{BASE_URL}/api/financial/expenses",
            headers=staff_user["headers"],
            json={"title": "TEST Iter203 Allowed", "amount": 50, "currency": "UGX",
                  "date": "2026-01-08", "category": "office", "location_id": LOC_ID,
                  "paid_from_account_id": acct["id"]},
            timeout=15,
        )
        assert exp.status_code == 200, exp.text[:200]
        # donation
        don = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=staff_user["headers"],
            json={"donor_name": "TEST", "amount": 500, "currency": "UGX",
                  "date": "2026-01-08", "location_id": LOC_ID,
                  "deposit_to_account_id": acct["id"]},
            timeout=15,
        )
        assert don.status_code == 200, don.text[:200]
        # cleanup
        requests.delete(f"{BASE_URL}/api/financial/expenses/{exp.json()['id']}",
                        headers=admin_headers, timeout=10)
        requests.delete(f"{BASE_URL}/api/financial/donations/{don.json()['id']}",
                        headers=admin_headers, timeout=10)

    def test_get_account_unassigned_nonadmin_403(self, admin_headers, make_account, staff_user):
        acct = make_account(assigned_user_ids=[])
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}",
                         headers=staff_user["headers"], timeout=15)
        assert r.status_code == 403

        t = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}/transactions",
                         headers=staff_user["headers"], timeout=15)
        assert t.status_code == 403

    def test_get_account_assigned_nonadmin_200(self, admin_headers, make_account, staff_user):
        acct = make_account(assigned_user_ids=[staff_user["id"]])
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}",
                         headers=staff_user["headers"], timeout=15)
        assert r.status_code == 200
        t = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}/transactions",
                         headers=staff_user["headers"], timeout=15)
        assert t.status_code == 200


# ---------- 5. TRANSFERS ----------

class TestTransfers:
    def test_transfer_success(self, admin_headers, make_account):
        src = make_account(starting_balance=10000)
        dst = make_account(starting_balance=0)
        r = requests.post(
            f"{BASE_URL}/api/financial/chart-accounts/transfer",
            headers=admin_headers,
            json={"from_account_id": src["id"], "to_account_id": dst["id"],
                  "amount": 3000, "notes": "TEST_Iter203_xfer"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        # verify balances
        s = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{src['id']}",
                        headers=admin_headers, timeout=10)
        d = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{dst['id']}",
                        headers=admin_headers, timeout=10)
        assert s.json()["balance"] == 7000
        assert d.json()["balance"] == 3000
        # transfers/list
        lst = requests.get(f"{BASE_URL}/api/financial/chart-accounts/transfers/list",
                          headers=admin_headers, timeout=15)
        assert lst.status_code == 200
        assert any(t.get("from_account_id") == src["id"] and t.get("to_account_id") == dst["id"]
                   for t in lst.json())

    def test_transfer_invalid_amounts(self, admin_headers, make_account):
        a1 = make_account(starting_balance=1000)
        a2 = make_account(starting_balance=0)

        # amount <= 0
        r = requests.post(f"{BASE_URL}/api/financial/chart-accounts/transfer",
                          headers=admin_headers,
                          json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 0},
                          timeout=10)
        assert r.status_code == 400

        # same src+dst
        r = requests.post(f"{BASE_URL}/api/financial/chart-accounts/transfer",
                          headers=admin_headers,
                          json={"from_account_id": a1["id"], "to_account_id": a1["id"], "amount": 5},
                          timeout=10)
        assert r.status_code == 400

        # missing to
        r = requests.post(f"{BASE_URL}/api/financial/chart-accounts/transfer",
                          headers=admin_headers,
                          json={"from_account_id": a1["id"], "amount": 5},
                          timeout=10)
        assert r.status_code == 400

        # insufficient
        r = requests.post(f"{BASE_URL}/api/financial/chart-accounts/transfer",
                          headers=admin_headers,
                          json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 999999},
                          timeout=10)
        assert r.status_code == 400
        assert "balance" in r.text.lower() or "insufficient" in r.text.lower()


# ---------- 6. SALES deposit_to_account_id ----------

class TestSalesDeposit:
    def test_sale_deposit_updates_balance(self, admin_headers, make_account):
        acct = make_account(starting_balance=0)
        sale = requests.post(
            f"{BASE_URL}/api/sales",
            headers=admin_headers,
            json={"items": [{"name": "TEST_Iter203_Item", "qty": 1, "price": 1500}],
                  "total": 1500, "payment_method": "cash",
                  "location_id": LOC_ID,
                  "deposit_to_account_id": acct["id"]},
            timeout=20,
        )
        assert sale.status_code == 200, sale.text[:200]
        body = sale.json()
        assert body.get("deposit_to_account_id") == acct["id"], f"deposit_to_account_id missing in response: {body}"

        # balance now 1500
        r = requests.get(f"{BASE_URL}/api/financial/chart-accounts/{acct['id']}",
                         headers=admin_headers, timeout=10)
        assert r.json()["balance"] == 1500

        # cleanup sale
        sid = body.get("id")
        if sid:
            requests.delete(f"{BASE_URL}/api/sales/{sid}", headers=admin_headers, timeout=10)


# ---------- 7. REGRESSION ----------

class TestRegression:
    def test_expense_without_account(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses",
            headers=admin_headers,
            json={"title": "TEST_Iter203_NoAcct", "amount": 10, "currency": "UGX",
                  "date": "2026-01-09", "category": "office", "location_id": LOC_ID},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        eid = r.json()["id"]
        requests.delete(f"{BASE_URL}/api/financial/expenses/{eid}",
                        headers=admin_headers, timeout=10)

    def test_donation_without_account(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=admin_headers,
            json={"donor_name": "TEST_Iter203", "amount": 20, "currency": "UGX",
                  "date": "2026-01-09", "location_id": LOC_ID},
            timeout=15,
        )
        assert r.status_code == 200
        did = r.json()["id"]
        requests.delete(f"{BASE_URL}/api/financial/donations/{did}",
                        headers=admin_headers, timeout=10)

    def test_list_endpoints_ok(self, admin_headers):
        for path in ["/api/financial/expenses", "/api/financial/donations",
                     "/api/financial/balance-sheet"]:
            r = requests.get(f"{BASE_URL}{path}", headers=admin_headers, timeout=15)
            assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"
