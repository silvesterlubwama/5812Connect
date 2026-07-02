"""Iteration 206 — Reversal line-status fix, repair/bulk-reverse endpoints,
HR timesheets + payslips (days_worked_override, use_timesheets), payroll
expense auto-tag from store_settings.default_cash_account_id, and self-service
/payslips/mine.

Public URL under REACT_APP_BACKEND_URL. All endpoints under /api.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_IDENT = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
LOC = "loc_001"


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": identifier, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {identifier}: {r.status_code} {r.text}"
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    assert tok, f"no token: {d}"
    return tok, d


@pytest.fixture(scope="session")
def admin_token():
    tok, _ = _login(ADMIN_IDENT, ADMIN_PASS)
    return tok


@pytest.fixture(scope="session")
def admin(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def staff_user(admin):
    """Create a non-admin staff user for cross-user isolation tests."""
    email = f"test_iter206_staff_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": "TEST Iter206 Staff",
        "email": email,
        "password": "Test@5812!",
        "role": "staff",
        "location_id": LOC,
        "also_create_member": False,
    }
    r = admin.post(f"{BASE_URL}/api/admin/users", json=payload, timeout=20)
    assert r.status_code == 200, f"create staff failed: {r.status_code} {r.text}"
    u = r.json()
    yield u
    # cleanup
    try:
        admin.delete(f"{BASE_URL}/api/admin/users/{u['id']}", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="session")
def staff_session(staff_user):
    tok, _ = _login(staff_user["email"], "Test@5812!")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def orig_store_settings(admin):
    r = admin.get(f"{BASE_URL}/api/store-settings/{LOC}", timeout=15)
    if r.status_code == 200:
        return r.json()
    return {}


@pytest.fixture(scope="session", autouse=True)
def _restore_store_settings(admin, orig_store_settings):
    yield
    restore = {"default_cash_account_id": orig_store_settings.get("default_cash_account_id", "")}
    try:
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json=restore, timeout=15)
    except Exception:
        pass


# ===================================================================
# Helpers for accounting
# ===================================================================
def _mk_account(admin, code, name, acc_type):
    body = {"code": code, "name": name, "type": acc_type, "location_id": LOC, "currency": "UGX"}
    r = admin.post(f"{BASE_URL}/api/accounting/accounts", json=body, timeout=20)
    assert r.status_code == 200, f"create acct failed: {r.status_code} {r.text}"
    return r.json()


def _ensure_journal(admin):
    lst = admin.get(f"{BASE_URL}/api/accounting/journals", timeout=15).json()
    for j in lst:
        if j.get("location_id") == LOC and j.get("kind") in ("miscellaneous", "cash"):
            return j
    body = {"code": f"MSC{uuid.uuid4().hex[:3].upper()}", "name": "TEST_Iter206_Misc", "kind": "miscellaneous", "location_id": LOC}
    r = admin.post(f"{BASE_URL}/api/accounting/journals", json=body, timeout=15)
    assert r.status_code == 200, f"journal create failed: {r.status_code} {r.text}"
    return r.json()


def _create_and_post_entry(admin, journal_id, debit_acc, credit_acc, amount=500.0, date=None):
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = {
        "journal_id": journal_id,
        "date": date,
        "narration": "TEST_Iter206 entry",
        "location_id": LOC,
        "lines": [
            {"account_id": debit_acc, "debit": amount, "credit": 0, "description": "Dr"},
            {"account_id": credit_acc, "debit": 0, "credit": amount, "description": "Cr"},
        ],
    }
    r = admin.post(f"{BASE_URL}/api/accounting/entries", json=body, timeout=20)
    assert r.status_code == 200, f"entry create failed: {r.status_code} {r.text}"
    eid = r.json()["id"]
    p = admin.post(f"{BASE_URL}/api/accounting/entries/{eid}/post", timeout=15)
    assert p.status_code == 200, f"post failed: {p.status_code} {p.text}"
    return eid


# ===================================================================
# REVERSAL FIX + REPAIR + BULK-REVERSE
# ===================================================================
class TestReversalFix:
    def test_reversal_flips_line_status_and_tb_nets_to_zero(self, admin):
        journal = _ensure_journal(admin)
        cash = _mk_account(admin, f"1{uuid.uuid4().hex[:3]}", "TEST_Iter206_Cash", "asset_cash")
        income = _mk_account(admin, f"4{uuid.uuid4().hex[:3]}", "TEST_Iter206_Income", "income")
        # Dr cash 500 / Cr income 500 → income Cr=500
        eid = _create_and_post_entry(admin, journal["id"], cash["id"], income["id"], 500.0)

        # TB shows income credit=500
        tb1 = admin.get(f"{BASE_URL}/api/accounting/reports/trial-balance?location_id={LOC}", timeout=15).json()
        row = next((r for r in tb1["rows"] if r["account_id"] == income["id"]), None)
        assert row is not None, f"income row missing in TB pre-reverse: {tb1}"
        assert row["credit"] == 500.0
        assert row["debit"] == 0

        # Reverse
        rr = admin.post(f"{BASE_URL}/api/accounting/entries/{eid}/reverse", json={}, timeout=15)
        assert rr.status_code == 200, f"reverse failed: {rr.status_code} {rr.text}"
        reversal = rr.json()
        assert reversal.get("status") == "posted"
        assert reversal.get("reverses") == eid

        # Original marked reversed
        oe = admin.get(f"{BASE_URL}/api/accounting/entries/{eid}", timeout=15).json()
        assert oe.get("is_reversed") is True
        assert oe.get("reversed_by") == reversal["id"]

        # Reversal lines all status=posted (this is THE bug fix)
        re_full = admin.get(f"{BASE_URL}/api/accounting/entries/{reversal['id']}", timeout=15).json()
        assert re_full.get("status") == "posted"
        for ln in re_full["lines"]:
            assert ln.get("status") == "posted", f"reversal line not posted: {ln}"

        # TB now nets income to zero
        tb2 = admin.get(f"{BASE_URL}/api/accounting/reports/trial-balance?location_id={LOC}", timeout=15).json()
        row2 = next((r for r in tb2["rows"] if r["account_id"] == income["id"]), None)
        if row2 is not None:
            # Some builds drop zero rows, but if present must net to 0
            net = round(row2["credit"] - row2["debit"], 2)
            assert net == 0.0, f"income didn't net to 0 after reverse: {row2}"

        # Cleanup accounts (they now have txn — delete may archive; ignore result)
        admin.delete(f"{BASE_URL}/api/accounting/accounts/{income['id']}", timeout=15)
        admin.delete(f"{BASE_URL}/api/accounting/accounts/{cash['id']}", timeout=15)


class TestRepairEndpoint:
    def test_repair_reversal_lines(self, admin):
        journal = _ensure_journal(admin)
        cash = _mk_account(admin, f"1{uuid.uuid4().hex[:3]}", "TEST_Iter206_Cash_R", "asset_cash")
        inc = _mk_account(admin, f"4{uuid.uuid4().hex[:3]}", "TEST_Iter206_Inc_R", "income")
        eid = _create_and_post_entry(admin, journal["id"], cash["id"], inc["id"], 100.0)

        # We can't directly poke Mongo from outside; simulate legacy state by
        # calling reverse-then-mutating via a NEW entry that we reverse, then
        # verify repair leaves the already-posted lines untouched. This still
        # exercises the endpoint contract shape ({fixed_entries, entry_ids}).
        rr = admin.post(f"{BASE_URL}/api/accounting/entries/{eid}/reverse", json={}, timeout=15)
        assert rr.status_code == 200
        reversal_id = rr.json()["id"]

        rep = admin.post(f"{BASE_URL}/api/accounting/entries/repair-reversal-lines", json={}, timeout=30)
        assert rep.status_code == 200, f"repair failed: {rep.status_code} {rep.text}"
        body = rep.json()
        assert "fixed_entries" in body and "entry_ids" in body
        assert isinstance(body["fixed_entries"], int)
        assert isinstance(body["entry_ids"], list)

        # After repair, the reversal's lines must all be posted (double-check)
        rd = admin.get(f"{BASE_URL}/api/accounting/entries/{reversal_id}", timeout=15).json()
        for ln in rd["lines"]:
            assert ln.get("status") == "posted"

        admin.delete(f"{BASE_URL}/api/accounting/accounts/{inc['id']}", timeout=15)
        admin.delete(f"{BASE_URL}/api/accounting/accounts/{cash['id']}", timeout=15)


class TestBulkReverse:
    def test_bulk_reverse_mixed(self, admin):
        journal = _ensure_journal(admin)
        cash = _mk_account(admin, f"1{uuid.uuid4().hex[:3]}", "TEST_Iter206_CashB", "asset_cash")
        inc = _mk_account(admin, f"4{uuid.uuid4().hex[:3]}", "TEST_Iter206_IncB", "income")

        # 2 posted entries
        p1 = _create_and_post_entry(admin, journal["id"], cash["id"], inc["id"], 50.0)
        p2 = _create_and_post_entry(admin, journal["id"], cash["id"], inc["id"], 60.0)
        # 1 draft
        r = admin.post(f"{BASE_URL}/api/accounting/entries", json={
            "journal_id": journal["id"],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "narration": "draft",
            "location_id": LOC,
            "lines": [
                {"account_id": cash["id"], "debit": 10, "credit": 0},
                {"account_id": inc["id"], "debit": 0, "credit": 10},
            ],
        }, timeout=15)
        assert r.status_code == 200
        draft_id = r.json()["id"]
        # 1 already-reversed
        already_id = _create_and_post_entry(admin, journal["id"], cash["id"], inc["id"], 30.0)
        rr = admin.post(f"{BASE_URL}/api/accounting/entries/{already_id}/reverse", json={}, timeout=15)
        assert rr.status_code == 200

        # Empty ids → 400
        er = admin.post(f"{BASE_URL}/api/accounting/entries/bulk-reverse", json={"ids": []}, timeout=15)
        assert er.status_code == 400

        # Mixed batch
        payload = {"ids": [p1, p2, draft_id, already_id, "bogus_id_xxx"]}
        br = admin.post(f"{BASE_URL}/api/accounting/entries/bulk-reverse", json=payload, timeout=30)
        assert br.status_code == 200, f"bulk-reverse failed: {br.status_code} {br.text}"
        body = br.json()
        assert body["reversed"] == 2, f"expected reversed=2 got {body}"
        assert body["skipped_already_reversed"] == 1, body
        assert body["skipped_not_posted"] == 1, body
        errs = body.get("errors") or []
        assert any(e.get("id") == "bogus_id_xxx" for e in errs), f"bogus not in errors: {errs}"

        admin.delete(f"{BASE_URL}/api/accounting/accounts/{inc['id']}", timeout=15)
        admin.delete(f"{BASE_URL}/api/accounting/accounts/{cash['id']}", timeout=15)


# ===================================================================
# HR TIMESHEETS + PAYSLIPS
# ===================================================================
class TestTimesheets:
    def test_submit_resubmit_approve_reject_delete(self, admin, staff_session, staff_user):
        period = "2026-02"
        # submit as staff
        r = staff_session.post(f"{BASE_URL}/api/hr/timesheets", json={"period": period, "days_worked": 18, "pto_days": 2, "notes": "test"}, timeout=15)
        assert r.status_code == 200, f"submit ts failed: {r.status_code} {r.text}"
        ts = r.json()
        assert ts["status"] == "submitted"
        assert ts["days_worked"] == 18
        assert ts["pto_days"] == 2
        ts_id = ts["id"]

        # resubmit same period → same id (no duplicate)
        r2 = staff_session.post(f"{BASE_URL}/api/hr/timesheets", json={"period": period, "days_worked": 19, "pto_days": 1}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["id"] == ts_id, "resubmit created duplicate"
        assert r2.json()["days_worked"] == 19

        # GET as staff — only own
        mine = staff_session.get(f"{BASE_URL}/api/hr/timesheets", timeout=15).json()
        assert isinstance(mine, list)
        for x in mine:
            assert x["staff_id"] == staff_user["id"]

        # approve as admin
        ap = admin.put(f"{BASE_URL}/api/hr/timesheets/{ts_id}/approve", json={"notes": "ok"}, timeout=15)
        assert ap.status_code == 200
        assert ap.json()["status"] == "approved"

        # DELETE approved as staff → 400 or 403
        d1 = staff_session.delete(f"{BASE_URL}/api/hr/timesheets/{ts_id}", timeout=15)
        assert d1.status_code in (400, 403), f"expected reject, got {d1.status_code} {d1.text}"

        # Fresh timesheet to test reject flow (different period)
        r3 = staff_session.post(f"{BASE_URL}/api/hr/timesheets", json={"period": "2026-04", "days_worked": 10}, timeout=15)
        assert r3.status_code == 200
        ts2 = r3.json()["id"]
        rj = admin.put(f"{BASE_URL}/api/hr/timesheets/{ts2}/reject", json={"reason": "Please revise"}, timeout=15)
        assert rj.status_code == 200
        rjb = rj.json()
        assert rjb["status"] == "rejected"
        assert "Please revise" in (rjb.get("review_notes") or "")

        # DELETE rejected as staff → ok
        d2 = staff_session.delete(f"{BASE_URL}/api/hr/timesheets/{ts2}", timeout=15)
        assert d2.status_code == 200


class TestGeneratePayslips:
    @pytest.fixture(scope="class")
    def salary_setup(self, admin, staff_user):
        # Create active salary for staff
        r = admin.post(f"{BASE_URL}/api/hr/salaries", json={
            "staff_id": staff_user["id"],
            "base_salary": 1000000,
            "pay_frequency": "monthly",
            "location_id": LOC,
        }, timeout=15)
        assert r.status_code == 200, f"salary create: {r.status_code} {r.text}"
        sal = r.json()
        yield sal
        try:
            admin.delete(f"{BASE_URL}/api/hr/salaries/{sal['id']}", timeout=15)
        except Exception:
            pass

    def test_generate_uses_approved_timesheet(self, admin, staff_session, staff_user, salary_setup):
        period = "2026-03"
        # Submit + approve
        s = staff_session.post(f"{BASE_URL}/api/hr/timesheets", json={"period": period, "days_worked": 15}, timeout=15)
        assert s.status_code == 200
        ts_id = s.json()["id"]
        admin.put(f"{BASE_URL}/api/hr/timesheets/{ts_id}/approve", json={}, timeout=15)

        # Clean any existing payslip for this staff+period
        # (no admin endpoint; ignore and trust idempotency in generator)
        r = admin.post(f"{BASE_URL}/api/hr/payslips/generate", json={"period": period, "location_id": LOC, "use_timesheets": True}, timeout=30)
        assert r.status_code == 200, f"generate: {r.status_code} {r.text}"
        # Fetch payslips for period and locate this staff's
        pl = admin.get(f"{BASE_URL}/api/hr/payslips?period={period}&location_id={LOC}", timeout=15).json()
        mine = [p for p in pl if p.get("staff_id") == staff_user["id"]]
        assert mine, f"no payslip for staff after generate: {pl}"
        p = mine[0]
        assert p["days_worked"] == 15, f"expected days_worked=15, got {p['days_worked']}"
        adj_items = [i for i in (p.get("line_items") or []) if i.get("name") == "Days-worked adjustment"]
        assert adj_items, f"no Days-worked adjustment line: {p}"
        adj = adj_items[0]
        assert adj["type"] == "deduction"
        assert adj["calculated_amount"] > 0
        # Net should equal base - adjustment (no other items)
        assert round(p["net_salary"], 2) == round(1000000 - adj["calculated_amount"], 2), f"net mismatch: {p}"

    def test_explicit_override_beats_timesheet(self, admin, staff_user, salary_setup):
        period = "2026-05"
        # No timesheet submitted for this period; override to 20
        r = admin.post(f"{BASE_URL}/api/hr/payslips/generate", json={
            "period": period, "location_id": LOC,
            "days_worked_override": {staff_user["id"]: 20},
            "use_timesheets": True,
        }, timeout=30)
        assert r.status_code == 200
        pl = admin.get(f"{BASE_URL}/api/hr/payslips?period={period}&location_id={LOC}", timeout=15).json()
        mine = [p for p in pl if p.get("staff_id") == staff_user["id"]]
        assert mine
        assert mine[0]["days_worked"] == 20


class TestManualPayslipUnchanged:
    def test_manual_still_works(self, admin, staff_user):
        r = admin.post(f"{BASE_URL}/api/hr/payslips/manual", json={
            "staff_id": staff_user["id"],
            "staff_name": staff_user.get("name", ""),
            "period": "2026-06",
            "gross_salary": 500000,
            "deductions": [{"name": "Tax", "amount": 50000}],
            "allowances": [{"name": "Transport", "amount": 20000}],
            "currency": "UGX",
            "location_id": LOC,
        }, timeout=15)
        assert r.status_code in (200, 201), f"manual payslip failed: {r.status_code} {r.text}"


# ===================================================================
# PAYROLL EXPENSE AUTO-TAG paid_from_account_id
# ===================================================================
class TestPayrollAutoTag:
    @pytest.fixture(scope="class")
    def cash_account(self, admin):
        body = {"name": f"TEST_Iter206_CashAcct_{uuid.uuid4().hex[:4]}", "kind": "cash", "currency": "UGX", "starting_balance": 500000.0, "location_id": LOC}
        r = admin.post(f"{BASE_URL}/api/financial/chart-accounts", json=body, timeout=15)
        assert r.status_code == 200, f"create cha: {r.status_code} {r.text}"
        acc = r.json()
        # Set default_cash_account_id
        pr = admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": acc["id"]}, timeout=15)
        assert pr.status_code == 200
        # Clean up any pre-existing daily aggregated payroll expense so
        # our test starts fresh — otherwise the "preserve paid_from" logic
        # would carry over a stale account id from previous test runs.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        exp_id = f"payroll_{LOC}_{today}"
        try:
            admin.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}", timeout=10)
        except Exception:
            pass
        yield acc
        try:
            admin.delete(f"{BASE_URL}/api/financial/chart-accounts/{acc['id']}", timeout=15)
        except Exception:
            pass

    @pytest.fixture(scope="class")
    def payslip_A(self, admin, staff_user):
        # Ensure salary exists for staff so we can generate; else create manual payslip
        r = admin.post(f"{BASE_URL}/api/hr/payslips/manual", json={
            "staff_id": staff_user["id"],
            "staff_name": staff_user.get("name", ""),
            "period": "2026-07",
            "gross_salary": 200000, "deductions": [], "allowances": [],
            "currency": "UGX", "location_id": LOC,
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        return r.json()

    @pytest.fixture(scope="class")
    def payslip_B(self, admin, staff_user):
        r = admin.post(f"{BASE_URL}/api/hr/payslips/manual", json={
            "staff_id": staff_user["id"],
            "staff_name": staff_user.get("name", ""),
            "period": "2026-08",
            "gross_salary": 150000, "deductions": [], "allowances": [],
            "currency": "UGX", "location_id": LOC,
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_mark_paid_creates_expense_with_paid_from(self, admin, cash_account, payslip_A):
        # Mark paid
        r = admin.put(f"{BASE_URL}/api/hr/payslips/{payslip_A['id']}", json={"status": "paid"}, timeout=20)
        assert r.status_code == 200, f"mark paid: {r.status_code} {r.text}"
        # Locate the daily aggregated expense
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        exp_id = f"payroll_{LOC}_{today}"
        # Find via HR expenses list or generic expenses endpoint
        el = admin.get(f"{BASE_URL}/api/financial/expenses?location_id={LOC}&limit=500", timeout=15)
        assert el.status_code == 200
        rows = el.json()
        exp = next((e for e in rows if e.get("id") == exp_id), None)
        assert exp is not None, f"payroll expense not found among {[e.get('id') for e in rows][:20]}"
        assert exp.get("paid_from_account_id") == cash_account["id"], f"paid_from mismatch: {exp}"
        assert float(exp.get("amount") or 0) >= 200000

    def test_second_paid_aggregates_and_preserves_paid_from(self, admin, cash_account, payslip_A, payslip_B):
        # payslip_A already paid; mark B paid
        r = admin.put(f"{BASE_URL}/api/hr/payslips/{payslip_B['id']}", json={"status": "paid"}, timeout=20)
        assert r.status_code == 200
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        exp_id = f"payroll_{LOC}_{today}"
        el = admin.get(f"{BASE_URL}/api/financial/expenses?location_id={LOC}&limit=500", timeout=15).json()
        exp = next((e for e in el if e.get("id") == exp_id), None)
        assert exp is not None
        assert exp["payroll_count"] >= 2
        assert exp["amount"] >= 350000
        assert exp["paid_from_account_id"] == cash_account["id"], f"paid_from was overwritten: {exp}"


# ===================================================================
# SELF-SERVICE /payslips/mine
# ===================================================================
class TestSelfServicePayslips:
    def test_mine_returns_only_own(self, staff_session, staff_user):
        r = staff_session.get(f"{BASE_URL}/api/hr/payslips/mine", timeout=15)
        assert r.status_code == 200
        for p in r.json():
            assert p["staff_id"] == staff_user["id"], f"leaked payslip: {p}"

    def test_mine_by_id_owner_ok_cross_user_blocked(self, admin, staff_session, staff_user):
        # Ensure staff has at least one payslip (from earlier tests)
        pl = staff_session.get(f"{BASE_URL}/api/hr/payslips/mine", timeout=15).json()
        if not pl:
            pytest.skip("no payslip to check")
        pid = pl[0]["id"]
        r = staff_session.get(f"{BASE_URL}/api/hr/payslips/{pid}/mine", timeout=15)
        assert r.status_code == 200
        # Cross-user: create a second staff and try to access first's payslip
        email = f"test_iter206_other_{uuid.uuid4().hex[:5]}@example.com"
        cu = admin.post(f"{BASE_URL}/api/admin/users", json={"name": "Other Staff", "email": email, "password": "Test@5812!", "role": "staff", "location_id": LOC, "also_create_member": False}, timeout=15)
        assert cu.status_code == 200
        other_id = cu.json()["id"]
        tok, _ = _login(email, "Test@5812!")
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {tok}"})
        r2 = s.get(f"{BASE_URL}/api/hr/payslips/{pid}/mine", timeout=15)
        assert r2.status_code == 404, f"cross-user access not blocked: {r2.status_code}"
        try:
            admin.delete(f"{BASE_URL}/api/admin/users/{other_id}", timeout=10)
        except Exception:
            pass


# ===================================================================
# REGRESSION
# ===================================================================
class TestRegression:
    def test_profit_loss_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/accounting/reports/profit-loss?location_id={LOC}", timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert "income" in b and "expense" in b and "totals" in b
        assert "net_profit" in b["totals"]

    def test_balance_sheet_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/accounting/reports/balance-sheet?location_id={LOC}", timeout=15)
        assert r.status_code == 200
        b = r.json()
        assert "assets" in b and "liabilities" in b and "equity" in b
        assert "balanced" in b["totals"]

    def test_attendance_summary(self, admin):
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        r = admin.get(f"{BASE_URL}/api/hr/attendance/summary?period={period}", timeout=15)
        assert r.status_code == 200
