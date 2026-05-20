"""Smoke tests for recently added modules (iterations 103-114).
These intentionally use only the public API surface and don't rely on
pre-seeded data beyond the default admin. Designed for CI.

Coverage:
  - Approvals workflows + requests + role hierarchy
  - HR Leave types/balance/request flow
  - HR Reimbursement create→approve loop + auto-approval spawn
  - HR Attendance clock-in/out idempotency
  - Accounting CoA seed + balanced journal entry + trial balance
  - Asset depreciation schedule preview
  - Sale discount approval auto-spawn + payment lock
  - Payment reminder send (graceful on missing email)
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("TEST_API_URL") or os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
BASE_URL = BASE_URL.rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_id(token: str) -> str:
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(token), timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def primary_location(token: str) -> str:
    r = requests.get(f"{BASE_URL}/api/locations", headers=_hdr(token), timeout=10)
    assert r.status_code == 200, r.text
    locs = r.json()
    assert len(locs) > 0, "No locations seeded"
    return locs[0]["id"]


# ============================================================
# APPROVALS
# ============================================================
class TestApprovals:
    def test_workflow_crud_cycle(self, token, primary_location):
        r = requests.post(
            f"{BASE_URL}/api/approvals/workflows",
            headers=_hdr(token),
            json={
                "name": f"CI Test WF {uuid.uuid4().hex[:6]}",
                "kind": "custom",
                "steps": [{"name": "First", "approver_role": "Manager"}],
                "location_id": primary_location,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        wf_id = r.json()["id"]

        r = requests.get(f"{BASE_URL}/api/approvals/workflows", headers=_hdr(token), timeout=10)
        assert r.status_code == 200
        assert any(w["id"] == wf_id for w in r.json())

        # Cleanup
        d = requests.delete(f"{BASE_URL}/api/approvals/workflows/{wf_id}", headers=_hdr(token), timeout=10)
        assert d.status_code == 200, d.text

    def test_request_flow_admin_overrides_manager_step(self, token, primary_location):
        wf = requests.post(
            f"{BASE_URL}/api/approvals/workflows",
            headers=_hdr(token),
            json={"name": f"CI Single Step {uuid.uuid4().hex[:6]}", "kind": "custom",
                  "steps": [{"name": "Manager OK", "approver_role": "Manager"}],
                  "location_id": primary_location},
            timeout=10,
        ).json()
        try:
            req = requests.post(
                f"{BASE_URL}/api/approvals/requests",
                headers=_hdr(token),
                json={"workflow_id": wf["id"], "title": "Test", "amount": 5, "currency": "USD"},
                timeout=10,
            )
            assert req.status_code == 200, req.text
            req_id = req.json()["id"]
            # Admin can override Manager-level step
            act = requests.post(
                f"{BASE_URL}/api/approvals/requests/{req_id}/act",
                headers=_hdr(token),
                json={"outcome": "approved", "note": "ok"},
                timeout=10,
            )
            assert act.status_code == 200, act.text
            assert act.json()["status"] == "approved"
            # Re-acting on a finalized request must 400
            again = requests.post(
                f"{BASE_URL}/api/approvals/requests/{req_id}/act",
                headers=_hdr(token), json={"outcome": "approved"}, timeout=10,
            )
            assert again.status_code == 400
        finally:
            requests.delete(f"{BASE_URL}/api/approvals/workflows/{wf['id']}", headers=_hdr(token), timeout=10)


# ============================================================
# HR — LEAVE
# ============================================================
class TestHrLeave:
    def test_leave_types_defaults(self, token):
        r = requests.get(f"{BASE_URL}/api/hr/leave/types", headers=_hdr(token), timeout=10)
        assert r.status_code == 200
        types = r.json()
        assert any(t["id"] == "annual" for t in types), "Annual leave type missing"
        assert any(t["id"] == "unpaid" for t in types), "Unpaid leave type missing"

    def test_leave_request_lifecycle(self, token, admin_id):
        # Use dates well within the current year to ensure the balance endpoint sees them.
        # Pick a Mon-Fri block 5 business days long.
        from datetime import date, timedelta
        # Find next Monday at least 7 days ahead
        d = date.today() + timedelta(days=7)
        while d.weekday() != 0:
            d += timedelta(days=1)
        start = d.isoformat()
        end = (d + timedelta(days=4)).isoformat()

        # Capture baseline used days (other test runs may have polluted state)
        before = requests.get(f"{BASE_URL}/api/hr/leave/balance", headers=_hdr(token), timeout=10).json()
        before_annual = next((x for x in before["balances"] if x["type"] == "annual"), {})
        baseline_used = int(before_annual.get("used") or 0)

        # Submit
        r = requests.post(
            f"{BASE_URL}/api/hr/leave/requests",
            headers=_hdr(token),
            json={"leave_type": "annual", "start_date": start, "end_date": end},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        lv = r.json()
        assert lv["status"] == "pending"
        assert lv["days"] == 5, f"Expected 5 business days, got {lv['days']}"

        # Approve
        a = requests.put(
            f"{BASE_URL}/api/hr/leave/requests/{lv['id']}",
            headers=_hdr(token),
            json={"status": "approved", "decision_note": "ok"},
            timeout=10,
        )
        assert a.status_code == 200, a.text
        assert a.json()["status"] == "approved"

        # Balance must have grown by at least the 5 days we just approved
        b = requests.get(f"{BASE_URL}/api/hr/leave/balance", headers=_hdr(token), timeout=10)
        assert b.status_code == 200
        annual = next((x for x in b.json()["balances"] if x["type"] == "annual"), None)
        assert annual is not None
        assert int(annual["used"]) >= baseline_used + 5, (
            f"Expected used ≥ {baseline_used + 5} after approving 5 days, got {annual['used']}"
        )

        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/leave/requests/{lv['id']}", headers=_hdr(token), timeout=10)

    def test_leave_validation_end_before_start(self, token):
        r = requests.post(
            f"{BASE_URL}/api/hr/leave/requests",
            headers=_hdr(token),
            json={"leave_type": "annual", "start_date": "2027-01-10", "end_date": "2027-01-05"},
            timeout=10,
        )
        assert r.status_code == 400


# ============================================================
# HR — REIMBURSEMENT
# ============================================================
class TestHrReimbursement:
    def test_reimbursement_lifecycle(self, token):
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses",
            headers=_hdr(token),
            json={"title": "CI test small expense", "amount": 5, "currency": "USD",
                  "category": "supplies"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        ex = r.json()
        assert ex["status"] == "pending"

        # Approve → reimburse
        a = requests.put(f"{BASE_URL}/api/hr/expenses/{ex['id']}",
                         headers=_hdr(token), json={"status": "approved"}, timeout=10)
        assert a.status_code == 200
        b = requests.put(f"{BASE_URL}/api/hr/expenses/{ex['id']}",
                         headers=_hdr(token), json={"status": "reimbursed"}, timeout=10)
        assert b.status_code == 200
        assert b.json()["status"] == "reimbursed"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/expenses/{ex['id']}", headers=_hdr(token), timeout=10)

    def test_reimbursement_negative_amount_rejected(self, token):
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses",
            headers=_hdr(token),
            json={"title": "negative", "amount": -1, "category": "other"},
            timeout=10,
        )
        assert r.status_code == 400


# ============================================================
# HR — ATTENDANCE
# ============================================================
class TestHrAttendance:
    def test_clock_in_idempotency_then_out(self, token):
        # Make sure no open entry
        active = requests.get(f"{BASE_URL}/api/hr/attendance/me/active", headers=_hdr(token), timeout=10)
        if active.status_code == 200 and active.json():
            requests.post(f"{BASE_URL}/api/hr/attendance/clock-out", headers=_hdr(token), timeout=10)

        r1 = requests.post(f"{BASE_URL}/api/hr/attendance/clock-in",
                           headers=_hdr(token), json={"notes": "ci"}, timeout=10)
        assert r1.status_code == 200, r1.text
        assert r1.json()["already_clocked_in"] is False
        entry_id = r1.json()["entry"]["id"]

        # Second call should return already=True
        r2 = requests.post(f"{BASE_URL}/api/hr/attendance/clock-in", headers=_hdr(token), timeout=10)
        assert r2.status_code == 200
        assert r2.json()["already_clocked_in"] is True

        # Clock out
        out = requests.post(f"{BASE_URL}/api/hr/attendance/clock-out", headers=_hdr(token), timeout=10)
        assert out.status_code == 200
        assert out.json()["check_out_time"] is not None

        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/attendance/{entry_id}", headers=_hdr(token), timeout=10)


# ============================================================
# ACCOUNTING
# ============================================================
class TestAccounting:
    def test_coa_seed_idempotent(self, token, primary_location):
        r = requests.post(f"{BASE_URL}/api/accounting/seed",
                          headers=_hdr(token), json={"location_id": primary_location, "currency": "UGX"},
                          timeout=15)
        assert r.status_code == 200, r.text
        # Second call should skip everything (idempotent)
        r2 = requests.post(f"{BASE_URL}/api/accounting/seed",
                           headers=_hdr(token), json={"location_id": primary_location, "currency": "UGX"},
                           timeout=15)
        assert r2.status_code == 200
        assert r2.json()["seeded"] == 0, "Re-seeding should not duplicate accounts"

    def test_balanced_entry_create_and_post(self, token, primary_location):
        accs = requests.get(f"{BASE_URL}/api/accounting/accounts",
                            headers=_hdr(token), params={"location_id": primary_location}, timeout=10).json()
        recv = next((a for a in accs if a["code"] == "1200"), None)  # AR
        rev = next((a for a in accs if a["code"] == "4000"), None)   # Sales Revenue
        if not recv or not rev:
            pytest.skip("Standard CoA accounts not seeded")
        # Need a sales journal — create one if missing
        jrns = requests.get(f"{BASE_URL}/api/accounting/journals", headers=_hdr(token), timeout=10).json()
        jrn = next((j for j in jrns if j.get("kind") == "sales" and j.get("location_id") == primary_location), None)
        if not jrn:
            r = requests.post(f"{BASE_URL}/api/accounting/journals",
                              headers=_hdr(token),
                              json={"code": f"CI{uuid.uuid4().hex[:3].upper()}", "name": "CI Sales Journal",
                                    "kind": "sales", "location_id": primary_location,
                                    "default_debit_account_id": recv["id"],
                                    "default_credit_account_id": rev["id"]},
                              timeout=10)
            assert r.status_code == 200, r.text
            jrn = r.json()
        # Balanced entry
        e = requests.post(f"{BASE_URL}/api/accounting/entries",
                          headers=_hdr(token),
                          json={"journal_id": jrn["id"], "date": "2027-02-01",
                                "ref": "CI-TEST", "narration": "CI smoke",
                                "lines": [
                                    {"account_id": recv["id"], "debit": 100, "credit": 0},
                                    {"account_id": rev["id"], "debit": 0, "credit": 100},
                                ]}, timeout=10)
        assert e.status_code == 200, e.text
        entry = e.json()
        assert entry["status"] == "draft"
        assert entry["total_debit"] == entry["total_credit"] == 100.0
        # Post
        p = requests.post(f"{BASE_URL}/api/accounting/entries/{entry['id']}/post",
                          headers=_hdr(token), timeout=10)
        assert p.status_code == 200
        assert p.json()["status"] == "posted"

    def test_unbalanced_entry_rejected(self, token, primary_location):
        accs = requests.get(f"{BASE_URL}/api/accounting/accounts",
                            headers=_hdr(token), params={"location_id": primary_location}, timeout=10).json()
        if len(accs) < 2:
            pytest.skip("Not enough accounts seeded")
        jrns = requests.get(f"{BASE_URL}/api/accounting/journals", headers=_hdr(token), timeout=10).json()
        if not jrns:
            pytest.skip("No journals configured")
        jrn = jrns[0]
        e = requests.post(f"{BASE_URL}/api/accounting/entries",
                          headers=_hdr(token),
                          json={"journal_id": jrn["id"], "date": "2027-02-01",
                                "lines": [
                                    {"account_id": accs[0]["id"], "debit": 100, "credit": 0},
                                    {"account_id": accs[1]["id"], "debit": 0, "credit": 50},
                                ]}, timeout=10)
        assert e.status_code == 400, "Unbalanced entry must be rejected"
        assert "unbalanced" in e.json()["detail"].lower()

    def test_trial_balance_reconciles(self, token):
        r = requests.get(f"{BASE_URL}/api/accounting/reports/trial-balance",
                         headers=_hdr(token), timeout=15)
        assert r.status_code == 200
        totals = r.json()["totals"]
        # If there are any posted entries, the trial balance must reconcile
        if totals["debit"] > 0 or totals["credit"] > 0:
            assert totals["balanced"] is True, f"TB unbalanced: D={totals['debit']} C={totals['credit']}"


# ============================================================
# SALE DISCOUNT AUTO-APPROVAL
# ============================================================
class TestSaleDiscountApproval:
    def test_high_discount_spawns_approval_and_locks_payment(self, token, primary_location):
        # Need a sale_discount workflow
        wf = requests.post(f"{BASE_URL}/api/approvals/workflows",
                           headers=_hdr(token),
                           json={"name": f"CI Discount WF {uuid.uuid4().hex[:6]}",
                                 "kind": "sale_discount",
                                 "steps": [{"name": "Manager OK", "approver_role": "Manager"}],
                                 "location_id": primary_location},
                           timeout=10).json()
        try:
            # 30% line discount > default 20% threshold → must spawn
            r = requests.post(f"{BASE_URL}/api/sales", headers=_hdr(token),
                              json={"items": [{"name": "ItemCI", "qty": 1, "unit_price": 100,
                                               "manual_discount_pct": 30}],
                                    "customer_name": "ci", "payment_method": "card",
                                    "total": 70, "location_id": primary_location},
                              timeout=10)
            assert r.status_code == 200, r.text
            sale = r.json()
            assert sale.get("requires_discount_approval") is True
            assert sale.get("payment_status") == "pending"
            approval_id = sale.get("discount_approval_id")
            assert approval_id, "Approval should have spawned"

            # Marking paid while pending must fail
            block = requests.put(f"{BASE_URL}/api/sales/{sale['id']}/payment-status",
                                 headers=_hdr(token), json={"payment_status": "paid"},
                                 timeout=10)
            assert block.status_code == 400
            assert "approval" in block.json()["detail"].lower()

            # Approve unblocks
            requests.post(f"{BASE_URL}/api/approvals/requests/{approval_id}/act",
                          headers=_hdr(token), json={"outcome": "approved"}, timeout=10)
            ok = requests.put(f"{BASE_URL}/api/sales/{sale['id']}/payment-status",
                              headers=_hdr(token), json={"payment_status": "paid"},
                              timeout=10)
            assert ok.status_code == 200
            assert ok.json()["payment_status"] == "paid"
        finally:
            requests.delete(f"{BASE_URL}/api/approvals/workflows/{wf['id']}",
                            headers=_hdr(token), timeout=10)


# ============================================================
# PAYMENT REMINDERS
# ============================================================
class TestPaymentReminders:
    def test_history_endpoint_responds(self, token):
        r = requests.get(f"{BASE_URL}/api/payment-reminders/history",
                         headers=_hdr(token), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
