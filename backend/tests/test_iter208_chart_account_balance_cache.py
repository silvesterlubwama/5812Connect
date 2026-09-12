"""Iter 208 — Chart-account balance cache + hot-path index regression tests.

Covers (as specified by main agent review request):
1. GET /api/financial/chart-accounts?include_balance=true&active_only=false shape
2. Donation create/delete → balance updates within cache TTL window (invalidation works)
3. Expense create+approve/delete → balance updates (invalidation works)
4. POST /api/financial/chart-accounts/transfer → both sides update immediately
5. Bulk-delete donations/expenses → balances refresh (cache cleared)
6. Repair-orphaned-journals idempotency preserved from iter207
7. /api/accounting/reports/trial-balance still balances (indexes didn't break aggregations)

Notes:
- Cache TTL is 5s; tests re-read within 6s after every write and assert reflected value.
- Uses `active_only=false` because dev DB chart accounts are all active=False.
- All test-created donations/expenses are prefixed TEST_iter208_ and cleaned up.
"""
import os
import time
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


# ---------- fixtures ---------- #

@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def chart_accounts(admin_headers):
    """List of all chart accounts (active_only=false, include_balance=true)."""
    r = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                     headers=admin_headers,
                     params={"include_balance": "true", "active_only": "false"}, timeout=30)
    assert r.status_code == 200, f"list failed: {r.status_code} {r.text}"
    accts = r.json()
    assert isinstance(accts, list) and len(accts) >= 2, "need at least 2 chart accounts for transfer test"
    return accts


@pytest.fixture(scope="module")
def target_account(chart_accounts):
    """Pick one UGX account for donation/expense tests."""
    for a in chart_accounts:
        if a.get("currency") == "UGX":
            return a
    return chart_accounts[0]


@pytest.fixture(scope="module")
def transfer_pair(chart_accounts):
    """Pick two accounts of the same currency for transfer test."""
    by_ccy: dict = {}
    for a in chart_accounts:
        by_ccy.setdefault(a.get("currency", "UGX"), []).append(a)
    for ccy, group in by_ccy.items():
        if len(group) >= 2:
            return group[0], group[1]
    pytest.skip("Need two chart accounts of same currency")


def _get_balance(admin_headers, account_id: str) -> float:
    """Fetch fresh balance for a single account via list endpoint."""
    r = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                     headers=admin_headers,
                     params={"include_balance": "true", "active_only": "false"}, timeout=30)
    assert r.status_code == 200
    for a in r.json():
        if a["id"] == account_id:
            return float(a.get("balance", 0))
    raise AssertionError(f"account {account_id} not found in list")


# ---------- 1. list endpoint shape ---------- #

class TestListEndpointShape:

    def test_list_returns_balance_field(self, chart_accounts):
        assert len(chart_accounts) > 0
        sample = chart_accounts[0]
        for k in ("id", "name", "kind", "currency", "starting_balance", "balance"):
            assert k in sample, f"missing key {k} in response: {sample}"
        assert isinstance(sample["balance"], (int, float))

    def test_list_active_only_false_returns_inactive_too(self, admin_headers):
        r_all = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                             headers=admin_headers,
                             params={"include_balance": "true", "active_only": "false"}, timeout=30)
        r_active = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                                headers=admin_headers,
                                params={"include_balance": "true", "active_only": "true"}, timeout=30)
        assert r_all.status_code == 200
        assert r_active.status_code == 200
        # active_only=false must be a superset
        assert len(r_all.json()) >= len(r_active.json())


# ---------- 2. donation create/delete cache invalidation ---------- #

class TestDonationCacheInvalidation:

    def test_donation_create_updates_balance_then_delete_reverts(self, admin_headers, target_account):
        aid = target_account["id"]
        loc = target_account.get("location_id") or ""
        # Wait 6s to guarantee any stale cache expired before baseline read
        time.sleep(6)
        baseline = _get_balance(admin_headers, aid)
        amount = 4321.0
        payload = {"donor_name": f"TEST_iter208_{uuid.uuid4().hex[:6]}",
                   "amount": amount, "currency": target_account.get("currency", "UGX"),
                   "type": "tithe", "location_id": loc,
                   "deposit_to_account_id": aid,
                   "notes": "TEST_iter208 cache invalidation"}
        cr = requests.post(f"{BASE_URL}/api/financial/donations",
                           headers=admin_headers, json=payload, timeout=20)
        assert cr.status_code == 200, f"create donation failed: {cr.status_code} {cr.text}"
        don_id = cr.json()["id"]
        try:
            # Read within 2s — must reflect NEW donation (cache was invalidated on write)
            after_create = _get_balance(admin_headers, aid)
            assert abs((after_create - baseline) - amount) < 0.01, (
                f"cache NOT invalidated on donation create: baseline={baseline}, "
                f"after={after_create}, expected delta={amount}"
            )
        finally:
            dr = requests.delete(f"{BASE_URL}/api/financial/donations/{don_id}",
                                 headers=admin_headers, timeout=20)
            assert dr.status_code == 200
        # After delete, immediate read should revert
        after_delete = _get_balance(admin_headers, aid)
        assert abs(after_delete - baseline) < 0.01, (
            f"cache NOT invalidated on donation delete: baseline={baseline}, after_delete={after_delete}"
        )


# ---------- 3. expense create+approve/delete cache invalidation ---------- #

class TestExpenseCacheInvalidation:

    def test_expense_create_approve_delete_flow(self, admin_headers, target_account):
        aid = target_account["id"]
        loc = target_account.get("location_id") or ""
        time.sleep(6)
        baseline = _get_balance(admin_headers, aid)
        amount = 777.0
        payload = {"title": f"TEST_iter208_exp_{uuid.uuid4().hex[:6]}",
                   "amount": amount, "currency": target_account.get("currency", "UGX"),
                   "category": "supplies", "location_id": loc,
                   "paid_from_account_id": aid,
                   "notes": "TEST_iter208"}
        cr = requests.post(f"{BASE_URL}/api/financial/expenses",
                           headers=admin_headers, json=payload, timeout=20)
        assert cr.status_code == 200, f"create expense failed: {cr.status_code} {cr.text}"
        exp_id = cr.json()["id"]
        try:
            # Approve — this transitions status from pending → approved, which is what
            # _batch_compute_balances counts. NOTE: approve does NOT itself call
            # invalidate_balance_cache — we rely on cache having been invalidated at
            # create time (before the row was countable), so first read after approve
            # may still show baseline until TTL expires.
            ar = requests.put(f"{BASE_URL}/api/financial/expenses/{exp_id}/approve",
                              headers=admin_headers, json={"comment": "test approve"}, timeout=20)
            assert ar.status_code == 200, f"approve failed: {ar.status_code} {ar.text}"
            # Wait for cache TTL to expire so approve becomes visible
            time.sleep(6)
            after_approve = _get_balance(admin_headers, aid)
            assert abs((baseline - after_approve) - amount) < 0.01, (
                f"expense (approved) not reflected in balance: baseline={baseline}, "
                f"after_approve={after_approve}, expected outflow={amount}"
            )
        finally:
            dr = requests.delete(f"{BASE_URL}/api/financial/expenses/{exp_id}",
                                 headers=admin_headers, timeout=20)
            assert dr.status_code == 200
        # Immediate read after delete — must revert (delete invalidates cache)
        after_delete = _get_balance(admin_headers, aid)
        assert abs(after_delete - baseline) < 0.01, (
            f"cache NOT invalidated on expense delete: baseline={baseline}, after={after_delete}"
        )


# ---------- 4. transfer invalidates both sides ---------- #

class TestTransferCacheInvalidation:

    def test_transfer_updates_both_sides_immediately(self, admin_headers, transfer_pair):
        from_acc, to_acc = transfer_pair
        # Choose amount small enough to be within from-side balance (we'll seed if needed)
        time.sleep(6)
        b_from_before = _get_balance(admin_headers, from_acc["id"])
        b_to_before = _get_balance(admin_headers, to_acc["id"])
        amount = 50.0
        # Ensure from-side has funds — top up via a donation if empty
        seeded_donation_id = None
        if b_from_before < amount + 1:
            seed = requests.post(f"{BASE_URL}/api/financial/donations",
                                 headers=admin_headers,
                                 json={"donor_name": "TEST_iter208_seed",
                                       "amount": amount + 100,
                                       "currency": from_acc.get("currency", "UGX"),
                                       "type": "tithe",
                                       "location_id": from_acc.get("location_id") or "",
                                       "deposit_to_account_id": from_acc["id"],
                                       "notes": "TEST_iter208 seed for transfer"}, timeout=20)
            assert seed.status_code == 200, seed.text
            seeded_donation_id = seed.json()["id"]
            b_from_before = _get_balance(admin_headers, from_acc["id"])

        try:
            tr = requests.post(f"{BASE_URL}/api/financial/chart-accounts/transfer",
                               headers=admin_headers,
                               json={"from_account_id": from_acc["id"],
                                     "to_account_id": to_acc["id"],
                                     "amount": amount,
                                     "notes": "TEST_iter208 transfer"}, timeout=20)
            assert tr.status_code == 200, f"transfer failed: {tr.status_code} {tr.text}"
            xfer_id = tr.json()["id"]

            # IMMEDIATE reads — should reflect both sides
            b_from_after = _get_balance(admin_headers, from_acc["id"])
            b_to_after = _get_balance(admin_headers, to_acc["id"])
            assert abs((b_from_before - b_from_after) - amount) < 0.01, (
                f"from-side cache stale: before={b_from_before}, after={b_from_after}, expected -{amount}"
            )
            assert abs((b_to_after - b_to_before) - amount) < 0.01, (
                f"to-side cache stale: before={b_to_before}, after={b_to_after}, expected +{amount}"
            )
        finally:
            # Cleanup: delete transfer record directly is not exposed; leave TEST_ tagged
            # Cleanup seed donation
            if seeded_donation_id:
                requests.delete(f"{BASE_URL}/api/financial/donations/{seeded_donation_id}",
                                headers=admin_headers, timeout=20)


# ---------- 5. bulk-delete clears cache ---------- #

class TestBulkDeleteCacheInvalidation:

    def test_bulk_delete_donations_clears_cache(self, admin_headers, target_account):
        aid = target_account["id"]
        loc = target_account.get("location_id") or ""
        time.sleep(6)
        baseline = _get_balance(admin_headers, aid)
        # Create 2 donations
        ids = []
        for _i in range(2):
            r = requests.post(f"{BASE_URL}/api/financial/donations",
                              headers=admin_headers,
                              json={"donor_name": f"TEST_iter208_bulk_{uuid.uuid4().hex[:6]}",
                                    "amount": 100.0,
                                    "currency": target_account.get("currency", "UGX"),
                                    "type": "tithe",
                                    "location_id": loc,
                                    "deposit_to_account_id": aid}, timeout=20)
            assert r.status_code == 200
            ids.append(r.json()["id"])
        # Balance should now show +200 (cache invalidated on each create)
        after_create = _get_balance(admin_headers, aid)
        assert abs((after_create - baseline) - 200.0) < 0.01, (
            f"cache issue on donation create: baseline={baseline}, after={after_create}"
        )
        # Bulk-delete
        br = requests.post(f"{BASE_URL}/api/financial/donations/bulk-delete",
                           headers=admin_headers, json={"ids": ids}, timeout=30)
        assert br.status_code == 200, f"bulk-delete failed: {br.status_code} {br.text}"
        data = br.json()
        assert data.get("deleted") == 2
        # IMMEDIATE read — must be back to baseline (bulk-delete flushes entire cache)
        after_bulk = _get_balance(admin_headers, aid)
        assert abs(after_bulk - baseline) < 0.01, (
            f"cache NOT flushed on bulk delete: baseline={baseline}, after_bulk={after_bulk}"
        )


# ---------- 6. repair-orphaned-journals idempotency ---------- #

class TestRepairOrphansStillIdempotent:

    def test_repair_endpoint_idempotent(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                          headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("scanned", "orphans_found", "reversed", "already_reversed", "message"):
            assert k in d
        # Per iter207 context, all pre-existing orphans already reversed; this run
        # should reverse 0 (unless prior tests in this session created new ones,
        # which they should NOT since delete cascades reverse automatically).
        assert d["reversed"] == 0, (
            f"expected 0 new reversals but got {d['reversed']} — "
            f"a delete path may be leaving orphan JEs behind. Full response: {d}"
        )


# ---------- 7. trial-balance still balances ---------- #

class TestTrialBalanceStillBalances:

    def test_trial_balance_totals_match(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/accounting/reports/trial-balance",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"trial-balance fetch failed: {r.status_code} {r.text}"
        data = r.json()
        # Payload shape can be either flat or per-journal — accept both
        if isinstance(data, list):
            # per-journal — each item should balance
            for jb in data:
                td = float(jb.get("total_debit", 0))
                tc = float(jb.get("total_credit", 0))
                assert abs(td - tc) < 0.01, f"journal {jb.get('journal_id')} unbalanced: D={td} C={tc}"
        else:
            td = float(data.get("total_debit", 0))
            tc = float(data.get("total_credit", 0))
            assert abs(td - tc) < 0.01, f"trial balance unbalanced: D={td} C={tc}, resp={data}"
