"""Iteration 202 — Finance bulk delete on all pages, expense paid_from_account_id,
accounting reversal correctness + hide-by-default + bulk delete of entries.

Runs against REACT_APP_BACKEND_URL. Admin login uses `identifier` field.
"""
import os
import time
import uuid
import requests
import pytest
from datetime import date
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
LOCATION_ID = "loc_001"


# ---------------------- fixtures ---------------------- #
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def journal_and_accounts(H):
    """Journal + 2 accounts. Seed if none exist."""
    journals = requests.get(f"{BASE_URL}/api/accounting/journals", headers=H, timeout=15).json()
    accts = requests.get(f"{BASE_URL}/api/accounting/accounts", headers=H, timeout=15).json()
    if not journals or len(accts) < 2:
        requests.post(
            f"{BASE_URL}/api/accounting/seed",
            headers=H,
            json={"location_id": LOCATION_ID, "currency": "UGX"},
            timeout=30,
        )
        journals = requests.get(f"{BASE_URL}/api/accounting/journals", headers=H, timeout=15).json()
        accts = requests.get(f"{BASE_URL}/api/accounting/accounts", headers=H, timeout=15).json()
    if not journals or len(accts) < 2:
        pytest.skip("Journals/accounts not available even after seed")
    return journals[0], accts[0], accts[1]


def _create_and_post_entry(H, journal, a1, a2, narration="iter202 test"):
    ref = f"TEST-{uuid.uuid4().hex[:8]}"
    e = requests.post(
        f"{BASE_URL}/api/accounting/entries",
        headers=H,
        json={
            "journal_id": journal["id"],
            "date": date.today().isoformat(),
            "ref": ref,
            "narration": narration,
            "location_id": LOCATION_ID,
            "lines": [
                {"account_id": a1["id"], "debit": 100, "credit": 0, "description": "dr"},
                {"account_id": a2["id"], "debit": 0, "credit": 100, "description": "cr"},
            ],
        },
        timeout=15,
    )
    assert e.status_code in (200, 201), f"create entry failed: {e.status_code} {e.text}"
    entry = e.json()
    p = requests.post(
        f"{BASE_URL}/api/accounting/entries/{entry['id']}/post",
        headers=H,
        timeout=15,
    )
    assert p.status_code == 200, f"post entry failed: {p.status_code} {p.text}"
    return entry


# ---------------------- 1) ACCOUNTING REVERSAL ---------------------- #
class TestAccountingReversal:
    def test_reverse_marks_original_and_returns_reversal(self, H, journal_and_accounts):
        j, a1, a2 = journal_and_accounts
        entry = _create_and_post_entry(H, j, a1, a2, "reverse-mark test")
        r = requests.post(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}/reverse",
            headers=H,
            json={},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        rev = r.json()
        assert rev.get("reverses") == entry["id"]
        assert rev.get("status") == "posted"

        one = requests.get(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}", headers=H, timeout=15
        ).json()
        assert one.get("is_reversed") is True
        assert one.get("reversed_by") == rev["id"]
        assert one.get("reversed_at")

    def test_reverse_is_idempotent(self, H, journal_and_accounts):
        j, a1, a2 = journal_and_accounts
        entry = _create_and_post_entry(H, j, a1, a2, "idempotent test")
        r1 = requests.post(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}/reverse",
            headers=H, json={}, timeout=15,
        )
        r2 = requests.post(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}/reverse",
            headers=H, json={}, timeout=15,
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"], "duplicate reversal created"

    def test_default_list_hides_reversed_pairs(self, H, journal_and_accounts):
        j, a1, a2 = journal_and_accounts
        entry = _create_and_post_entry(H, j, a1, a2, "hide test")
        rev = requests.post(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}/reverse",
            headers=H, json={}, timeout=15,
        ).json()

        entries = requests.get(
            f"{BASE_URL}/api/accounting/entries?limit=1000", headers=H, timeout=20
        ).json()
        ids = {e["id"] for e in entries}
        assert entry["id"] not in ids, "reversed original still showing"
        assert rev["id"] not in ids, "reversal entry still showing by default"

    def test_include_reversed_shows_both(self, H, journal_and_accounts):
        j, a1, a2 = journal_and_accounts
        entry = _create_and_post_entry(H, j, a1, a2, "include test")
        rev = requests.post(
            f"{BASE_URL}/api/accounting/entries/{entry['id']}/reverse",
            headers=H, json={}, timeout=15,
        ).json()

        entries = requests.get(
            f"{BASE_URL}/api/accounting/entries?include_reversed=true&limit=1000",
            headers=H, timeout=20,
        ).json()
        ids = {e["id"] for e in entries}
        assert entry["id"] in ids and rev["id"] in ids, (
            f"include_reversed=true missing entries. orig_in={entry['id'] in ids}, rev_in={rev['id'] in ids}"
        )


# ---------------------- 2) EXPENSE PAID FROM ---------------------- #
class TestExpensePaidFrom:
    def test_create_expense_with_paid_from_persists(self, H):
        payload = {
            "title": "TEST_iter202 paid_from",
            "amount": 12.5,
            "currency": "UGX",
            "category": "general",
            "notes": "unit test",
            "location_id": LOCATION_ID,
            "paid_from_account_id": "acct_xyz",
        }
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses", headers=H, json=payload, timeout=15
        )
        assert r.status_code in (200, 201), r.text
        created = r.json()
        assert created.get("paid_from_account_id") == "acct_xyz"
        assert "id" in created
        exp_id = created["id"]

        # Verify persistence via GET list
        listing = requests.get(
            f"{BASE_URL}/api/financial/expenses?location_id={LOCATION_ID}&limit=200",
            headers=H, timeout=15,
        ).json()
        match = next((e for e in listing if e["id"] == exp_id), None)
        assert match is not None, "expense not found in list after create"
        assert match.get("paid_from_account_id") == "acct_xyz"

        # cleanup
        requests.post(
            f"{BASE_URL}/api/financial/expenses/bulk-delete",
            headers=H, json={"ids": [exp_id]}, timeout=15,
        )


# ---------------------- 3) BULK DELETE — DONATIONS ---------------------- #
class TestBulkDeleteDonations:
    def _create(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/donations",
            headers=H,
            json={
                "donor_name": f"TEST_don_{uuid.uuid4().hex[:6]}",
                "amount": 5.0,
                "currency": "UGX",
                "type": "cash",
                "notes": "iter202",
                "location_id": LOCATION_ID,
            },
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_bulk_delete_donations_ok(self, H):
        ids = [self._create(H) for _ in range(2)]
        r = requests.post(
            f"{BASE_URL}/api/financial/donations/bulk-delete",
            headers=H, json={"ids": ids}, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") == 2

        listing = requests.get(
            f"{BASE_URL}/api/financial/donations?location_id={LOCATION_ID}&limit=500",
            headers=H, timeout=15,
        ).json()
        got = {d["id"] for d in listing}
        for did in ids:
            assert did not in got, f"donation {did} still present after bulk delete"

    def test_bulk_delete_donations_empty_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/donations/bulk-delete",
            headers=H, json={"ids": []}, timeout=15,
        )
        assert r.status_code == 400, r.text


# ---------------------- 4) BULK DELETE — EXPENSES ---------------------- #
class TestBulkDeleteExpenses:
    def _create(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses",
            headers=H,
            json={
                "title": f"TEST_exp_{uuid.uuid4().hex[:6]}",
                "amount": 3.0,
                "currency": "UGX",
                "category": "general",
                "notes": "iter202",
                "location_id": LOCATION_ID,
            },
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_bulk_delete_expenses_ok(self, H):
        ids = [self._create(H) for _ in range(2)]
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses/bulk-delete",
            headers=H, json={"ids": ids}, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") == 2

    def test_bulk_delete_expenses_empty_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/expenses/bulk-delete",
            headers=H, json={"ids": []}, timeout=15,
        )
        assert r.status_code == 400


# ---------------------- 5) BULK DELETE — ASSETS ---------------------- #
class TestBulkDeleteAssets:
    def _create(self, H):
        payload = {
            "name": f"TEST_asset_{uuid.uuid4().hex[:6]}",
            "category": "equipment",
            "value": 100,
            "currency": "UGX",
            "location_id": LOCATION_ID,
        }
        r = requests.post(
            f"{BASE_URL}/api/financial/assets", headers=H, json=payload, timeout=15
        )
        if r.status_code not in (200, 201):
            pytest.skip(f"asset create not available: {r.status_code} {r.text[:150]}")
        return r.json().get("id")

    def test_bulk_delete_assets_ok(self, H):
        ids = [self._create(H) for _ in range(2)]
        ids = [i for i in ids if i]
        if len(ids) < 2:
            pytest.skip("Could not create assets to bulk-delete")
        r = requests.post(
            f"{BASE_URL}/api/financial/assets/bulk-delete",
            headers=H, json={"ids": ids}, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") == len(ids)

    def test_bulk_delete_assets_empty_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/assets/bulk-delete",
            headers=H, json={"ids": []}, timeout=15,
        )
        assert r.status_code == 400


# ---------------------- 6) BULK DELETE — BUDGETS ---------------------- #
class TestBulkDeleteBudgets:
    def _create(self, H):
        payload = {
            "name": f"TEST_budget_{uuid.uuid4().hex[:6]}",
            "amount": 1000,
            "currency": "UGX",
            "period": "monthly",
            "category": "general",
            "location_id": LOCATION_ID,
        }
        r = requests.post(
            f"{BASE_URL}/api/financial/budgets", headers=H, json=payload, timeout=15
        )
        if r.status_code not in (200, 201):
            pytest.skip(f"budget create not available: {r.status_code} {r.text[:150]}")
        return r.json().get("id")

    def test_bulk_delete_budgets_ok(self, H):
        ids = [self._create(H) for _ in range(2)]
        ids = [i for i in ids if i]
        if len(ids) < 2:
            pytest.skip("Could not create budgets")
        r = requests.post(
            f"{BASE_URL}/api/financial/budgets/bulk-delete",
            headers=H, json={"ids": ids}, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") == len(ids)

    def test_bulk_delete_budgets_empty_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/financial/budgets/bulk-delete",
            headers=H, json={"ids": []}, timeout=15,
        )
        assert r.status_code == 400


# ---------------------- 7) BULK DELETE — ACCOUNTING ENTRIES ---------------------- #
class TestBulkDeleteAccountingEntries:
    def test_bulk_delete_drafts_but_skips_posted(self, H, journal_and_accounts):
        j, a1, a2 = journal_and_accounts

        # Two drafts (not posted)
        draft_ids = []
        for i in range(2):
            r = requests.post(
                f"{BASE_URL}/api/accounting/entries",
                headers=H,
                json={
                    "journal_id": j["id"],
                    "date": date.today().isoformat(),
                    "ref": f"TEST-DRAFT-{uuid.uuid4().hex[:6]}",
                    "narration": "iter202 draft",
                    "location_id": LOCATION_ID,
                    "lines": [
                        {"account_id": a1["id"], "debit": 10, "credit": 0},
                        {"account_id": a2["id"], "debit": 0, "credit": 10},
                    ],
                },
                timeout=15,
            )
            assert r.status_code in (200, 201), r.text
            draft_ids.append(r.json()["id"])

        # One posted (should be skipped)
        posted = _create_and_post_entry(H, j, a1, a2, "iter202 posted")

        # One non-existent id — should be ignored (not counted as skipped_posted)
        fake_id = f"jent_{uuid.uuid4().hex[:8]}"

        ids = draft_ids + [posted["id"], fake_id]
        r = requests.post(
            f"{BASE_URL}/api/accounting/entries/bulk-delete",
            headers=H, json={"ids": ids}, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("deleted") == 2, f"expected 2 deleted, got {body}"
        assert body.get("skipped_posted") == 1, f"expected 1 skipped_posted, got {body}"

        # Verify drafts are gone
        for did in draft_ids:
            g = requests.get(
                f"{BASE_URL}/api/accounting/entries/{did}", headers=H, timeout=15
            )
            assert g.status_code == 404, f"draft {did} still exists: {g.status_code}"

        # Verify posted still exists
        g = requests.get(
            f"{BASE_URL}/api/accounting/entries/{posted['id']}?include_reversed=true",
            headers=H, timeout=15,
        )
        # (single GET usually doesn't need include_reversed but include for safety)
        assert g.status_code == 200, f"posted entry got removed! {g.status_code} {g.text}"

    def test_bulk_delete_entries_empty_400(self, H):
        r = requests.post(
            f"{BASE_URL}/api/accounting/entries/bulk-delete",
            headers=H, json={"ids": []}, timeout=15,
        )
        assert r.status_code == 400
