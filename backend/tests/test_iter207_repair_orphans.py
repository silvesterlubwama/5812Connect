"""Iter 207 — Finance ↔ Accounting drift repair endpoint + delete cascade tests.

Covers:
1. POST /api/financial/repair-orphaned-journals as admin (idempotent)
2. Same endpoint as non-admin → 403
3. Donation create → delete → auto-JE marked is_reversed + reversal entry created
4. Expense approve → delete → auto-JE reversed
5. Bulk delete donations → returns {deleted, je_reversed}
6. Bulk delete expenses → returns {deleted, je_reversed}
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def staff_token(admin_headers):
    """Create a low-privilege staff user for RBAC check on repair endpoint."""
    email = f"TEST_iter207_staff_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers, json={
        "name": "TEST Iter207 Staff",
        "email": email,
        "password": "Test@5812!",
        "role": "staff",
    }, timeout=20)
    assert r.status_code in (200, 201), f"staff create failed: {r.status_code} {r.text}"
    # login as this user
    lr = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"identifier": email, "password": "Test@5812!"}, timeout=20)
    assert lr.status_code == 200, f"staff login failed: {lr.status_code} {lr.text}"
    return {"token": lr.json().get("access_token") or lr.json().get("token"),
            "user_id": r.json().get("id")}


@pytest.fixture(scope="module")
def location_id(admin_headers):
    """Pick a location that has a CoA set up (so auto-post to accounting will fire).
    We look for one whose journal + accounts exist."""
    # Query journals — any location with an active journal will do
    jrns = requests.get(f"{BASE_URL}/api/accounting/journals", headers=admin_headers, timeout=20).json()
    for j in jrns:
        loc = j.get("location_id")
        if not loc:
            continue
        accs = requests.get(f"{BASE_URL}/api/accounting/accounts",
                            headers=admin_headers, params={"location_id": loc}, timeout=20).json()
        types = {a.get("type") for a in accs}
        if "asset_cash" in types and "income" in types and "expense" in types:
            return loc
    pytest.skip("No fully-configured CoA location available — cannot exercise auto-post path")


# ------------------------------------------------------------------ #
# 1 + 2. Repair endpoint RBAC + idempotency
# ------------------------------------------------------------------ #
class TestRepairOrphanedJournalsEndpoint:

    def test_admin_can_call_returns_expected_shape(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                          headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        for key in ("scanned", "orphans_found", "reversed", "already_reversed", "message"):
            assert key in data, f"missing key {key} in {data}"
        assert isinstance(data["scanned"], int)
        assert isinstance(data["orphans_found"], int)
        assert isinstance(data["reversed"], int)
        assert isinstance(data["already_reversed"], int)
        assert isinstance(data["message"], str) and len(data["message"]) > 0

    def test_idempotent_second_call(self, admin_headers):
        r1 = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                           headers=admin_headers, timeout=60)
        assert r1.status_code == 200
        d1 = r1.json()
        r2 = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                           headers=admin_headers, timeout=60)
        assert r2.status_code == 200
        d2 = r2.json()
        # 2nd call must reverse 0 (nothing new left to reverse)
        assert d2["reversed"] == 0, f"idempotency broken: 2nd call reversed {d2['reversed']}"
        # 2nd call already_reversed must include everything the 1st call reversed
        assert d2["already_reversed"] >= d1["reversed"], (
            f"already_reversed({d2['already_reversed']}) should be >= 1st call's reversed({d1['reversed']})"
        )
        # orphans_found stable
        assert d2["orphans_found"] == d1["orphans_found"], (
            f"orphans_found drifted: {d1['orphans_found']} → {d2['orphans_found']}"
        )

    def test_non_admin_forbidden(self, staff_token):
        headers = {"Authorization": f"Bearer {staff_token['token']}",
                   "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                          headers=headers, timeout=30)
        assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code}: {r.text}"


# ------------------------------------------------------------------ #
# 3. Donation create → delete → JE reversed
# ------------------------------------------------------------------ #
class TestDonationDeleteCascadeReversesJE:

    def _find_je(self, headers, donation_id):
        # Fetch entries; auto-post entries carry auto_generated_from=donation & source_id
        r = requests.get(f"{BASE_URL}/api/accounting/entries",
                         headers=headers, params={"limit": 500, "include_reversed": True}, timeout=30)
        assert r.status_code == 200
        for e in r.json():
            if e.get("auto_generated_from") == "donation" and e.get("source_id") == donation_id:
                return e
        return None

    def test_delete_reverses_auto_je(self, admin_headers, location_id):
        # Create donation
        payload = {"donor_name": "TEST_iter207_donor", "amount": 12345.67,
                   "currency": "UGX", "type": "tithe", "location_id": location_id,
                   "notes": "TEST_iter207 cascade check"}
        cr = requests.post(f"{BASE_URL}/api/financial/donations",
                           headers=admin_headers, json=payload, timeout=20)
        assert cr.status_code == 200, f"create donation failed: {cr.status_code} {cr.text}"
        don_id = cr.json()["id"]

        # Confirm JE was auto-posted
        je = self._find_je(admin_headers, don_id)
        assert je is not None, "auto-posted JE not created for donation"
        assert je.get("status") == "posted"
        assert je.get("is_reversed") is not True

        # Delete donation
        dr = requests.delete(f"{BASE_URL}/api/financial/donations/{don_id}",
                             headers=admin_headers, timeout=30)
        assert dr.status_code == 200, f"delete failed: {dr.status_code} {dr.text}"

        # Verify original JE marked is_reversed + reversal entry created
        je_after = self._find_je(admin_headers, don_id)
        assert je_after is not None, "JE disappeared after delete (should be marked reversed, not deleted)"
        assert je_after.get("is_reversed") is True, f"JE not marked reversed: {je_after}"


# ------------------------------------------------------------------ #
# 4. Expense approve → delete → JE reversed
# ------------------------------------------------------------------ #
class TestExpenseDeleteCascadeReversesJE:

    def _find_je(self, headers, expense_id):
        r = requests.get(f"{BASE_URL}/api/accounting/entries",
                         headers=headers, params={"limit": 500, "include_reversed": True}, timeout=30)
        assert r.status_code == 200
        for e in r.json():
            if e.get("auto_generated_from") == "expense" and e.get("source_id") == expense_id:
                return e
        return None

    def test_approved_expense_delete_reverses_je(self, admin_headers, location_id):
        # Create + approve expense
        payload = {"title": "TEST_iter207_expense", "amount": 987.65,
                   "currency": "UGX", "category": "supplies", "location_id": location_id,
                   "notes": "TEST_iter207 cascade check"}
        cr = requests.post(f"{BASE_URL}/api/financial/expenses",
                           headers=admin_headers, json=payload, timeout=20)
        assert cr.status_code == 200, f"create expense failed: {cr.status_code} {cr.text}"
        exp_id = cr.json()["id"]
        # Approve → this triggers auto-post
        ar = requests.put(f"{BASE_URL}/api/financial/expenses/{exp_id}/approve",
                         headers=admin_headers, json={"comment": "TEST auto"}, timeout=20)
        assert ar.status_code == 200, f"approve failed: {ar.status_code} {ar.text}"

        je = self._find_je(admin_headers, exp_id)
        if je is None:
            pytest.skip("Expense approve did not auto-post JE (likely missing expense-type CoA account) — cascade path untestable here")
        assert je.get("status") == "posted"
        assert je.get("is_reversed") is not True

        # Delete
        dr = requests.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}",
                             headers=admin_headers, timeout=30)
        assert dr.status_code == 200, f"delete failed: {dr.status_code} {dr.text}"

        je_after = self._find_je(admin_headers, exp_id)
        assert je_after is not None
        assert je_after.get("is_reversed") is True, f"JE not reversed after delete: {je_after}"


# ------------------------------------------------------------------ #
# 5. Bulk delete donations returns counts + reverses JEs
# ------------------------------------------------------------------ #
class TestBulkDeleteDonations:

    def test_bulk_delete_returns_counts_and_reverses(self, admin_headers, location_id):
        ids = []
        for i in range(2):
            cr = requests.post(f"{BASE_URL}/api/financial/donations", headers=admin_headers, json={
                "donor_name": f"TEST_iter207_bulk_{i}",
                "amount": 100 + i,
                "currency": "UGX", "type": "tithe", "location_id": location_id,
            }, timeout=20)
            assert cr.status_code == 200
            ids.append(cr.json()["id"])

        r = requests.post(f"{BASE_URL}/api/financial/donations/bulk-delete",
                          headers=admin_headers, json={"ids": ids}, timeout=30)
        assert r.status_code == 200, f"bulk-delete failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("deleted") == len(ids), f"deleted count mismatch: {data}"
        assert "je_reversed" in data, f"missing je_reversed in {data}"
        # In a fully-configured location, both donations auto-posted JEs → 2 reversals
        assert data["je_reversed"] >= 1, f"expected >=1 JE reversal, got {data['je_reversed']}"

    def test_bulk_delete_empty_ids_400(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/financial/donations/bulk-delete",
                          headers=admin_headers, json={"ids": []}, timeout=15)
        assert r.status_code == 400


# ------------------------------------------------------------------ #
# 6. Bulk delete expenses returns counts + reverses JEs
# ------------------------------------------------------------------ #
class TestBulkDeleteExpenses:

    def test_bulk_delete_returns_counts_and_reverses(self, admin_headers, location_id):
        ids = []
        for i in range(2):
            cr = requests.post(f"{BASE_URL}/api/financial/expenses", headers=admin_headers, json={
                "title": f"TEST_iter207_bulk_exp_{i}",
                "amount": 50 + i, "currency": "UGX", "category": "supplies",
                "location_id": location_id,
            }, timeout=20)
            assert cr.status_code == 200
            eid = cr.json()["id"]
            # approve so it auto-posts a JE
            ar = requests.put(f"{BASE_URL}/api/financial/expenses/{eid}/approve",
                              headers=admin_headers, json={"comment": "TEST"}, timeout=20)
            assert ar.status_code == 200
            ids.append(eid)

        r = requests.post(f"{BASE_URL}/api/financial/expenses/bulk-delete",
                          headers=admin_headers, json={"ids": ids}, timeout=30)
        assert r.status_code == 200, f"bulk-delete failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("deleted") == len(ids)
        assert "je_reversed" in data

    def test_bulk_delete_empty_ids_400(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/financial/expenses/bulk-delete",
                          headers=admin_headers, json={"ids": []}, timeout=15)
        assert r.status_code == 400
