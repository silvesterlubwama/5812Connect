"""Iter221: HR repair-payslip-journals diagnostics + Finance edit whitelist expansion.

Coverage:
- POST /api/hr/repair-payslip-journals returns diagnostics block with correct DB-backed counts/sums.
- Non-admin gets 403.
- PUT /api/financial/donations/{id} accepts sublocation_id + deposit_to_account_id (persists).
- PUT /api/financial/expenses/{id} accepts vendor, receipt_number, account (persists).
- Non-whitelisted fields ignored.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


@pytest.fixture(scope="module")
def sync_db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def location_id(sync_db):
    loc = sync_db.locations.find_one({}, {"_id": 0, "id": 1})
    assert loc, "No location in DB"
    return loc["id"]


# ---------- HR repair diagnostics ----------

class TestRepairDiagnostics:
    def test_dry_run_returns_diagnostics(self, admin_headers, sync_db):
        r = requests.post(f"{BASE_URL}/api/hr/repair-payslip-journals",
                          json={"apply": False}, headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        diag = body.get("diagnostics")
        assert diag is not None, "diagnostics block missing"
        # Required keys
        for k in ("paid_payslips", "paid_payslips_total_ugx",
                  "aggregate_expenses", "aggregate_expenses_total_ugx",
                  "active_payroll_jes", "active_payroll_jes_total_ugx",
                  "in_sync"):
            assert k in diag, f"diagnostics missing key {k}"
        assert isinstance(diag["in_sync"], bool)

        # Cross-check with direct DB probes
        db_paid_count = sync_db.hr_payslips.count_documents({"status": "paid"})
        db_agg_count = sync_db.expenses.count_documents({"source": "hr_payroll_aggregate"})
        db_je_count = sync_db.accounting_entries.count_documents({
            "auto_generated_from": "payroll",
            "is_reversed": {"$ne": True},
            "status": "posted",
        })
        assert diag["paid_payslips"] == db_paid_count
        assert diag["aggregate_expenses"] == db_agg_count
        assert diag["active_payroll_jes"] == db_je_count

        # Sum crosscheck (within 0.01)
        agg_sum = list(sync_db.expenses.aggregate([
            {"$match": {"source": "hr_payroll_aggregate"}},
            {"$group": {"_id": None, "t": {"$sum": "$amount"}}},
        ]))
        exp_total = float((agg_sum or [{}])[0].get("t") or 0)
        assert abs(diag["aggregate_expenses_total_ugx"] - round(exp_total, 2)) < 0.01

        je_sum = list(sync_db.accounting_entries.aggregate([
            {"$match": {"auto_generated_from": "payroll", "is_reversed": {"$ne": True}, "status": "posted"}},
            {"$group": {"_id": None, "t": {"$sum": "$total_debit"}}},
        ]))
        je_total = float((je_sum or [{}])[0].get("t") or 0)
        assert abs(diag["active_payroll_jes_total_ugx"] - round(je_total, 2)) < 0.01

        # in_sync consistency
        expected_in_sync = abs(exp_total - je_total) < 0.01 and db_agg_count > 0
        assert diag["in_sync"] == expected_in_sync

    def test_apply_returns_diagnostics(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/hr/repair-payslip-journals",
                          json={"apply": True}, headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is False
        assert "diagnostics" in body
        assert "in_sync" in body["diagnostics"]

    def test_non_admin_forbidden(self):
        # Login without token
        r = requests.post(f"{BASE_URL}/api/hr/repair-payslip-journals",
                          json={"apply": False}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------- Finance donation edit whitelist expansion ----------

class TestDonationUpdateWhitelist:
    def _create(self, admin_headers, location_id, amount=100):
        r = requests.post(f"{BASE_URL}/api/financial/donations",
                          json={"donor_name": "TEST_iter221 donor", "amount": amount,
                                "type": "tithe", "location_id": location_id, "notes": "TEST"},
                          headers=admin_headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_update_accepts_sublocation_and_deposit_to(self, admin_headers, location_id, sync_db):
        don = self._create(admin_headers, location_id)
        # Pick any chart account (or fabricate a plausible id)
        acct = sync_db.chart_accounts.find_one({"location_id": location_id}, {"_id": 0, "id": 1}) or {}
        acct_id = acct.get("id") or "test_acct_iter221"
        payload = {
            "sublocation_id": "test_sub_iter221",
            "deposit_to_account_id": acct_id,
            "notes": "TEST updated with sublocation+deposit",
            "should_be_ignored": "yes",
        }
        r = requests.put(f"{BASE_URL}/api/financial/donations/{don['id']}",
                         json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("sublocation_id") == "test_sub_iter221"
        assert body.get("deposit_to_account_id") == acct_id
        assert "should_be_ignored" not in body
        # Verify persistence in DB
        d = sync_db.donations.find_one({"id": don["id"]}, {"_id": 0})
        assert d["sublocation_id"] == "test_sub_iter221"
        assert d["deposit_to_account_id"] == acct_id
        # cleanup
        sync_db.donations.delete_one({"id": don["id"]})


# ---------- Finance expense edit whitelist expansion ----------

class TestExpenseUpdateWhitelist:
    def _create(self, admin_headers, location_id, amount=50):
        r = requests.post(f"{BASE_URL}/api/financial/expenses",
                          json={"title": "TEST_iter221 exp", "amount": amount,
                                "category": "office", "location_id": location_id,
                                "notes": "TEST"},
                          headers=admin_headers, timeout=30)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_update_accepts_vendor_receipt_number_account(self, admin_headers, location_id, sync_db):
        exp = self._create(admin_headers, location_id)
        payload = {
            "vendor": "TEST Vendor Ltd",
            "receipt_number": "RCPT-IT221-001",
            "account": "Ledger-A",
            "sublocation_id": "test_sub_iter221",
            "budget_category": "Uganda Farm",
            "not_allowed": "ignore me",
        }
        r = requests.put(f"{BASE_URL}/api/financial/expenses/{exp['id']}",
                         json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("vendor") == "TEST Vendor Ltd"
        assert body.get("receipt_number") == "RCPT-IT221-001"
        assert body.get("account") == "Ledger-A"
        assert body.get("sublocation_id") == "test_sub_iter221"
        assert body.get("budget_category") == "Uganda Farm"
        assert "not_allowed" not in body
        # DB persistence
        d = sync_db.expenses.find_one({"id": exp["id"]}, {"_id": 0})
        assert d["vendor"] == "TEST Vendor Ltd"
        assert d["receipt_number"] == "RCPT-IT221-001"
        assert d["account"] == "Ledger-A"
        # cleanup
        sync_db.expenses.delete_one({"id": exp["id"]})
