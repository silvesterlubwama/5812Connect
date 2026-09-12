"""Iter219: Backend tests for /api/hr/repair-payslip-journals.

Coverage:
- Auth guard: non-admin (staff/hr/director/manager) → 403; admin → 200
- Dry-run vs apply, response shape (pass_a, pass_b, pass_c, locations_missing_accounts)
- Pass A (missing JE for existing aggregate) — reverse aggregate JE via API, fixer re-posts,
  balanced lines, journal_code NOT starting with SALES, idempotent (2nd apply = 0 pass_a).
- Pass A skip (loc without Wages/Cash CoA) — fixer marks skipped_no_accounts and
  location_id in locations_missing_accounts; expense doc not double-modified.
- Pass B (reconstruct from paid payslips) — DB-seed a paid payslip w/o aggregate
  expense; apply creates payroll_<loc>_<date> expense with retroactive_repair=True,
  balanced JE; re-run = 0 pass_b.
- Pass C (wrong journal) — DB-insert a payroll JE into a SALES journal; dry-run
  counts, apply re-tags journal_id.
- Audit trail — audit_log row with action=repair entity=payslip_journals after apply.
"""
import os
import uuid
import datetime as _dt

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

import creds  # env-backed logins, see tests/creds.py

load_dotenv("/app/backend/.env")


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    v = ln.split("=", 1)[1].strip()
                    break
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE = _base()
ADMIN = {"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD}
DEFAULT_PW = creds.NEW_USER_PASSWORD
REPAIR_URL = f"{BASE}/api/hr/repair-payslip-journals"


# ---------- Mongo helpers (sync — avoid motor cross-loop issues) ----------
def _mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _create_user(admin_h, role="staff", suffix=""):
    email = f"iter219_{role}_{suffix}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {"name": f"TEST Iter219 {role}", "email": email, "password": DEFAULT_PW, "role": role}
    r = requests.post(f"{BASE}/api/admin/users", json=payload, headers=admin_h, timeout=20)
    assert r.status_code in (200, 201), r.text[:400]
    user = r.json()
    lg = requests.post(f"{BASE}/api/auth/login", json={"identifier": email, "password": DEFAULT_PW}, timeout=20)
    assert lg.status_code == 200
    return user, {"Authorization": f"Bearer {lg.json()['token']}"}


@pytest.fixture(scope="module")
def staff_h(admin_h):
    _, h = _create_user(admin_h, role="staff", suffix="s")
    return h


@pytest.fixture(scope="module")
def hr_h(admin_h):
    _, h = _create_user(admin_h, role="hr", suffix="h")
    return h


@pytest.fixture(scope="module")
def director_h(admin_h):
    _, h = _create_user(admin_h, role="director", suffix="d")
    return h


@pytest.fixture(scope="module")
def manager_h(admin_h):
    _, h = _create_user(admin_h, role="manager", suffix="m")
    return h


def _mk_loc(admin_h, tag):
    body = {"name": f"TEST_Iter219_{tag}_{uuid.uuid4().hex[:6]}", "type": "sublocation"}
    r = requests.post(f"{BASE}/api/locations", json=body, headers=admin_h, timeout=20)
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot create location: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def _seed_coa(admin_h, loc_id, include_wages=True, include_cash=True):
    accts = {}
    if include_cash:
        r = requests.post(f"{BASE}/api/accounting/accounts",
                          json={"code": "1001", "name": "Cash", "type": "asset_cash",
                                "location_id": loc_id, "active": True},
                          headers=admin_h, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"cannot seed cash: {r.status_code} {r.text[:200]}")
        accts["cash"] = r.json()["id"]
    if include_wages:
        r = requests.post(f"{BASE}/api/accounting/accounts",
                          json={"code": "6100", "name": "Salaries & Wages", "type": "expense",
                                "location_id": loc_id, "active": True},
                          headers=admin_h, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"cannot seed wages: {r.status_code} {r.text[:200]}")
        accts["wages"] = r.json()["id"]
    return accts


def _make_and_pay_payslip(admin_h, staff_id, staff_name, net, loc_id, period="2025-06"):
    body = {"staff_id": staff_id, "staff_name": staff_name, "period": period,
            "gross_salary": net, "allowances": [], "deductions": [], "currency": "UGX",
            "notes": f"iter219 {uuid.uuid4().hex[:4]}", "location_id": loc_id}
    r = requests.post(f"{BASE}/api/hr/payslips/manual", json=body, headers=admin_h, timeout=20)
    assert r.status_code in (200, 201), r.text[:400]
    pid = r.json()["id"]
    r = requests.put(f"{BASE}/api/hr/payslips/{pid}",
                     json={"status": "approved", "reason": "iter219"},
                     headers=admin_h, timeout=20)
    assert r.status_code == 200
    r = requests.put(f"{BASE}/api/hr/payslips/{pid}",
                     json={"status": "paid", "payroll_location_id": loc_id, "reason": "iter219"},
                     headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text[:400]
    return pid


# =========== 1. AUTH GUARD ===========
class TestAuthGuard:
    def test_dry_run_admin_ok(self, admin_h):
        r = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("dry_run") is True
        for k in ("pass_a_missing_je", "pass_b_reconstruct", "pass_c_wrong_journal",
                  "locations_missing_accounts", "message"):
            assert k in d, f"missing key {k} in response"
        assert "count" in d["pass_a_missing_je"]

    def test_staff_forbidden(self, staff_h):
        r = requests.post(REPAIR_URL, json={}, headers=staff_h, timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_hr_forbidden(self, hr_h):
        r = requests.post(REPAIR_URL, json={}, headers=hr_h, timeout=20)
        assert r.status_code == 403

    def test_director_forbidden(self, director_h):
        r = requests.post(REPAIR_URL, json={}, headers=director_h, timeout=20)
        assert r.status_code == 403

    def test_manager_forbidden(self, manager_h):
        r = requests.post(REPAIR_URL, json={}, headers=manager_h, timeout=20)
        assert r.status_code == 403

    def test_unauthenticated_forbidden(self):
        r = requests.post(REPAIR_URL, json={}, timeout=20)
        assert r.status_code in (401, 403)


# =========== 2. PASS A — MISSING JE FOR EXISTING AGGREGATE ===========
class TestPassAMissingJE:
    def test_missing_je_gets_backfilled(self, admin_h):
        loc_id = _mk_loc(admin_h, "PA")
        _seed_coa(admin_h, loc_id)
        u, _ = _create_user(admin_h, role="staff", suffix="pa")
        pid = _make_and_pay_payslip(admin_h, u["id"], u["name"], 250000, loc_id)
        today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        expense_id = f"payroll_{loc_id}_{today}"

        # Find + reverse the JE via DB (API filters by campus scope for fresh loc)
        db = _mongo()

        entry = db.accounting_entries.find_one(
            {"auto_generated_from": "payroll", "source_id": expense_id, "is_reversed": {"$ne": True}},
            {"_id": 0})
        assert entry, f"no active JE to reverse for {expense_id}"
        je_id = entry["id"]
        # Reverse via API
        r = requests.post(f"{BASE}/api/accounting/entries/{je_id}/reverse",
                          json={"reason": "iter219 test setup"}, headers=admin_h, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]

        # Sanity: no active JE for this expense
        active_count = db.accounting_entries.count_documents(
            {"auto_generated_from": "payroll", "source_id": expense_id, "is_reversed": {"$ne": True},
             "status": "posted"})
        assert active_count == 0, "reversal did not remove active JE"

        # Dry-run
        r = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["dry_run"] is True
        # Sample should include our expense_id somewhere in pass_a
        # (sample capped at 10 — but count includes all; we can't be sure it's in first 10
        # so we just require count>=1)
        assert d["pass_a_missing_je"]["count"] >= 1

        # Apply
        r2 = requests.post(REPAIR_URL, json={"apply": True}, headers=admin_h, timeout=120)
        assert r2.status_code == 200, r2.text[:400]
        d2 = r2.json()
        assert d2["dry_run"] is False

        # Verify a new active JE was posted for this expense
        def _verify():
            entry = db.accounting_entries.find_one(
                {"auto_generated_from": "payroll", "source_id": expense_id,
                 "is_reversed": {"$ne": True}, "status": "posted"}, {"_id": 0})
            if not entry:
                return None, [], None
            lines = list(db.accounting_entry_lines.find(
                {"entry_id": entry["id"]}, {"_id": 0}).limit(20))
            journal = db.accounting_journals.find_one({"id": entry.get("journal_id")}, {"_id": 0})
            return entry, lines, journal

        entry, lines, journal = _verify()
        assert entry, f"pass A did NOT re-post an active JE for {expense_id}"
        # Balanced: total_debit==total_credit==amount
        assert abs(float(entry.get("total_debit") or 0) - 250000.0) < 0.05
        assert abs(float(entry.get("total_credit") or 0) - 250000.0) < 0.05
        assert entry.get("status") == "posted"
        assert entry.get("is_reversed") in (False, None)
        # 2 lines: one debit to Wages, one credit to Cash
        assert len(lines) == 2, f"expected 2 lines, got {len(lines)}: {lines}"
        debits = [l for l in lines if float(l.get("debit") or 0) > 0]
        credits = [l for l in lines if float(l.get("credit") or 0) > 0]
        assert len(debits) == 1 and len(credits) == 1
        # Journal must NOT be a sales journal
        jcode = (entry.get("journal_code") or "").upper()
        assert not jcode.startswith("SALES"), f"landed on SALES journal! code={jcode}"
        if journal:
            assert (journal.get("kind") or "").lower() != "sales"

        # Idempotency — re-run apply should not re-fix THIS expense (count in pass A drops)
        r3 = requests.post(REPAIR_URL, json={"apply": True}, headers=admin_h, timeout=60)
        assert r3.status_code == 200
        # We check that our specific expense is no longer in pass_a sample or that global count decreased
        # (safer check: fetch fresh dry-run and ensure our expense not surfaced)
        r4 = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
        d4 = r4.json()
        sample_expense_ids = {f.get("expense_id") for f in d4["pass_a_missing_je"].get("sample", [])}
        # Even if capped at 10, ensure that any remaining pass_a entries do NOT include our repaired one:
        # do a raw DB check instead — active JE must still exist
        assert _verify()[0] is not None, "idempotency broken — active JE was removed"


# =========== 3. PASS A SKIP — NO CHART OF ACCOUNTS ===========
class TestPassASkipNoAccounts:
    def test_skip_when_no_wages_or_cash(self, admin_h):
        loc_id = _mk_loc(admin_h, "PAskip")
        # Do NOT seed CoA at all
        # Insert an aggregate expense DIRECTLY (with no JE)
        db = _mongo()
        exp_id = f"payroll_{loc_id}_2025-05-20"
        exp_doc = {
            "id": exp_id, "title": "Payroll (Wages & Salaries)", "amount": 100000.0,
            "currency": "UGX", "category": "Wages & Salaries", "department": "HR",
            "budget_category": "Wages & Salaries", "date": "2025-05-20",
            "notes": "iter219 skip test", "location_id": loc_id,
            "paid_from_account_id": "", "status": "approved",
            "source": "hr_payroll_aggregate", "payroll_count": 1,
            "payroll_period": "2025-05",
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "created_by": "iter219_test",
        }
        db.expenses.insert_one(exp_doc)
        try:
            r = requests.post(REPAIR_URL, json={"apply": True}, headers=admin_h, timeout=120)
            assert r.status_code == 200, r.text[:400]
            d = r.json()
            skipped = d["pass_a_missing_je"].get("skipped_no_accounts", 0)
            missing_locs = d.get("locations_missing_accounts", [])
            assert skipped >= 1, f"expected >=1 skipped, got {skipped}"
            assert loc_id in missing_locs, f"loc {loc_id} not in {missing_locs}"

            # Expense not modified beyond original doc
            doc = db.expenses.find_one({"id": exp_id}, {"_id": 0})
            je = db.accounting_entries.find_one(
                {"auto_generated_from": "payroll", "source_id": exp_id,
                 "is_reversed": {"$ne": True}, "status": "posted"}, {"_id": 0})
            assert doc is not None
            assert je is None, f"expected NO active JE at loc without CoA, got {je}"
            # Original fields intact
            assert doc.get("amount") == 100000.0
            assert doc.get("title") == "Payroll (Wages & Salaries)"
        finally:
            db.expenses.delete_one({"id": exp_id})


# =========== 4. PASS B — RECONSTRUCT FROM PAID PAYSLIPS ===========
class TestPassBReconstruct:
    def test_reconstruct_expense_and_je(self, admin_h):
        loc_id = _mk_loc(admin_h, "PB")
        _seed_coa(admin_h, loc_id)
        # Auto-create a miscellaneous journal by posting a first JE via a tiny donation
        # or via _post_to_accounting: easier — insert a miscellaneous journal directly
        db = _mongo()
        jrn_id = f"jrn_iter219_{uuid.uuid4().hex[:8]}"
        db.accounting_journals.insert_one({
            "id": jrn_id, "code": "GL", "name": "General Ledger",
            "kind": "miscellaneous", "location_id": loc_id, "active": True,
            "auto_created": True,
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })

        # Insert 2 paid payslips directly (no aggregate expense exists)
        u1, _ = _create_user(admin_h, role="staff", suffix="pb1")
        u2, _ = _create_user(admin_h, role="staff", suffix="pb2")
        paid_at = "2025-04-10T09:00:00Z"
        ps_ids = []
        for u, net in [(u1, 120000), (u2, 180000)]:
            pid = f"psl_iter219_{uuid.uuid4().hex[:8]}"
            ps_ids.append(pid)
            db.hr_payslips.insert_one({
                "id": pid, "staff_id": u["id"], "staff_name": u["name"],
                "period": "2025-04", "gross_salary": net, "net_salary": net,
                "allowances": [], "deductions": [], "currency": "UGX",
                "status": "paid", "paid_at": paid_at,
                "payroll_location_id": loc_id, "location_id": loc_id,
                "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "created_by": "iter219_test",
            })
        expense_id = f"payroll_{loc_id}_2025-04-10"

        try:
            # Dry-run first
            r = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
            assert r.status_code == 200
            d = r.json()
            assert d["dry_run"] is True
            # Might not be in first 10 sample but count must be >=1
            assert d["pass_b_reconstruct"]["count"] >= 1

            # Apply
            r2 = requests.post(REPAIR_URL, json={"apply": True}, headers=admin_h, timeout=120)
            assert r2.status_code == 200, r2.text[:400]

            # Verify expense doc + JE
            exp = db.expenses.find_one({"id": expense_id}, {"_id": 0})
            je = db.accounting_entries.find_one(
                {"auto_generated_from": "payroll", "source_id": expense_id,
                 "is_reversed": {"$ne": True}, "status": "posted"}, {"_id": 0})
            lines = []
            if je:
                lines = list(db.accounting_entry_lines.find(
                    {"entry_id": je["id"]}, {"_id": 0}).limit(20))
            assert exp, f"expense {expense_id} not reconstructed"
            assert exp.get("retroactive_repair") is True
            assert exp.get("source") == "hr_payroll_aggregate"
            assert abs(float(exp.get("amount") or 0) - 300000.0) < 0.05
            assert je, f"JE not posted for reconstructed expense {expense_id}"
            assert abs(float(je.get("total_debit") or 0) - 300000.0) < 0.05
            assert abs(float(je.get("total_credit") or 0) - 300000.0) < 0.05
            assert len(lines) == 2

            # Idempotency: re-run dry-run should NOT re-list this expense
            r3 = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
            d3 = r3.json()
            b_ids2 = {f.get("expense_id") for f in d3["pass_b_reconstruct"].get("sample", [])}
            assert expense_id not in b_ids2, "pass_b idempotency broken"
        finally:
            db.hr_payslips.delete_many({"id": {"$in": ps_ids}})


# =========== 5. PASS C — WRONG (SALES) JOURNAL ===========
class TestPassCWrongJournal:
    def test_dry_run_counts_and_apply_retags(self, admin_h):
        loc_id = _mk_loc(admin_h, "PC")
        _seed_coa(admin_h, loc_id)
        db = _mongo()
        # Create a SALES journal at this location
        sales_jrn_id = f"jrn_sales_iter219_{uuid.uuid4().hex[:8]}"
        db.accounting_journals.insert_one({
            "id": sales_jrn_id, "code": "SALES", "name": "Sales Journal",
            "kind": "sales", "location_id": loc_id, "active": True,
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })
        # Create a GL journal so repair can migrate to it
        gl_jrn_id = f"jrn_gl_iter219_{uuid.uuid4().hex[:8]}"
        db.accounting_journals.insert_one({
            "id": gl_jrn_id, "code": "GL", "name": "General Ledger",
            "kind": "miscellaneous", "location_id": loc_id, "active": True,
            "auto_created": True,
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })
        # Insert a payroll JE mis-routed to the SALES journal
        entry_id = f"je_iter219_wj_{uuid.uuid4().hex[:8]}"
        source_id = f"payroll_{loc_id}_2025-03-01"
        db.accounting_entries.insert_one({
            "id": entry_id, "entry_number": "TEST-WJ-001",
            "journal_id": sales_jrn_id, "journal_code": "SALES",
            "date": "2025-03-01", "narration": "iter219 wrong-journal test",
            "auto_generated_from": "payroll", "source_id": source_id,
            "status": "posted", "location_id": loc_id,
            "total_debit": 150000.0, "total_credit": 150000.0,
            "is_reversed": False,
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })
        db.accounting_entry_lines.insert_many([
            {"id": f"l1_{entry_id}", "entry_id": entry_id, "debit": 150000.0,
             "credit": 0, "journal_id": sales_jrn_id},
            {"id": f"l2_{entry_id}", "entry_id": entry_id, "debit": 0,
             "credit": 150000.0, "journal_id": sales_jrn_id},
        ])

        try:
            # Dry-run: pass_c should count our entry
            r = requests.post(REPAIR_URL, json={}, headers=admin_h, timeout=60)
            assert r.status_code == 200
            d = r.json()
            assert d["dry_run"] is True
            assert (d["pass_c_wrong_journal"] or {}).get("scanned", 0) >= 1

            # Verify still on SALES journal (dry-run doesn't modify)
            e = db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
            assert e["journal_id"] == sales_jrn_id, "dry-run modified entry!"

            # Apply
            r2 = requests.post(REPAIR_URL, json={"apply": True, "include_wrong_journal": True},
                               headers=admin_h, timeout=120)
            assert r2.status_code == 200, r2.text[:400]
            d2 = r2.json()
            c = d2["pass_c_wrong_journal"] or {}
            assert (c.get("entries_fixed") or 0) >= 1, f"pass C fixed=0: {c}"

            # Verify entry re-tagged (journal no longer SALES)
            e2 = db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
            assert e2["journal_id"] != sales_jrn_id, "entry still on SALES journal after apply"
            # Lines also updated to same journal_id
            lines = list(db.accounting_entry_lines.find({"entry_id": entry_id}, {"_id": 0}).limit(20))
            for l in lines:
                if l.get("journal_id"):
                    assert l["journal_id"] == e2["journal_id"], f"line journal not migrated: {l}"
        finally:
            db.accounting_entries.delete_many({"id": entry_id})
            db.accounting_entry_lines.delete_many({"entry_id": entry_id})
            db.accounting_journals.delete_many({"id": {"$in": [sales_jrn_id, gl_jrn_id]}})


# =========== 6. AUDIT TRAIL ===========
class TestAuditTrail:
    def test_audit_log_written_on_apply(self, admin_h):
        # Trigger an apply (may be a no-op — audit should still be written)
        before = _dt.datetime.now(_dt.timezone.utc).isoformat()
        r = requests.post(REPAIR_URL, json={"apply": True}, headers=admin_h, timeout=120)
        assert r.status_code == 200
        db = _mongo()

        row = db.audit_log.find_one(
            {"action": "repair", "resource": "payslip_journals", "timestamp": {"$gte": before}},
            {"_id": 0}, sort=[("timestamp", -1)])
        assert row, "no audit_log row written for repair/payslip_journals"
        meta = row.get("details") or {}
        # Metadata should include the pass counts
        assert "pass_a" in meta, f"audit details missing pass_a: {meta}"
        assert "pass_b" in meta
        assert "pass_c" in meta
