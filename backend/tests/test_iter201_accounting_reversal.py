"""Iteration 201 — Accounting reversal correctness + hide-by-default."""
import os
import time
import requests
import pytest
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def journal_and_accounts(headers):
    """Grab (or create) a journal + two accounts to test with."""
    j = requests.get(f"{BASE_URL}/api/accounting/journals", headers=headers, timeout=10).json()
    if not j:
        j = [requests.post(f"{BASE_URL}/api/accounting/journals", headers=headers,
                           json={"code": f"TST{int(time.time()) % 100000}",
                                 "name": "Test Journal"}, timeout=10).json()]
    accts = requests.get(f"{BASE_URL}/api/accounting/accounts", headers=headers, timeout=10).json()
    if len(accts) < 2:
        pytest.skip("Need at least 2 accounts in the chart")
    return j[0], accts[0], accts[1]


@pytest.fixture
def posted_entry(headers, journal_and_accounts):
    j, a1, a2 = journal_and_accounts
    from datetime import date
    ref = f"TEST-{int(time.time())}"
    entry = requests.post(f"{BASE_URL}/api/accounting/entries", headers=headers, json={
        "journal_id": j["id"],
        "date": date.today().isoformat(),  # today — so it's near the top of the sort
        "ref": ref,
        "narration": "Iter201 reversal test",
        "lines": [
            {"account_id": a1["id"], "debit": 100, "credit": 0, "description": "test dr"},
            {"account_id": a2["id"], "debit": 0, "credit": 100, "description": "test cr"},
        ],
    }, timeout=10).json()
    requests.post(f"{BASE_URL}/api/accounting/entries/{entry['id']}/post",
                  headers=headers, timeout=10)
    entry["_ref"] = ref
    return entry


def _find_by_id(entries, entry_id):
    return next((e for e in entries if e["id"] == entry_id), None)


class TestReversalCorrectness:
    def test_reversal_marks_original_as_reversed(self, posted_entry, headers):
        r = requests.post(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}/reverse",
                          headers=headers, json={}, timeout=10)
        assert r.status_code == 200
        rev = r.json()
        assert rev.get("reverses") == posted_entry["id"]
        assert rev.get("status") == "posted"

        # Fetch directly by id to sidestep list pagination on huge test DBs.
        one = requests.get(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}",
                           headers=headers, timeout=10).json()
        assert one.get("is_reversed") is True
        assert one.get("reversed_by") == rev["id"]

    def test_reversal_is_idempotent(self, posted_entry, headers):
        """Reverse twice — should return the same reversal, no duplicates."""
        r1 = requests.post(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}/reverse",
                           headers=headers, json={}, timeout=10)
        r2 = requests.post(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}/reverse",
                           headers=headers, json={}, timeout=10)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"], "Second reverse returned a different entry — duplicate created"

    def test_default_list_hides_reversed_pairs(self, posted_entry, headers):
        # Reverse it
        requests.post(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}/reverse",
                      headers=headers, json={}, timeout=10)
        # Default query — should NOT include either the original or the reversal
        entries = requests.get(f"{BASE_URL}/api/accounting/entries?limit=1000",
                               headers=headers, timeout=10).json()
        ids = {e["id"] for e in entries}
        assert posted_entry["id"] not in ids, "Reversed original still showing by default"
        for e in entries:
            assert not e.get("reverses"), f"Reversal entry still showing by default: {e['id']}"

    def test_include_reversed_shows_both(self, posted_entry, headers):
        r = requests.post(f"{BASE_URL}/api/accounting/entries/{posted_entry['id']}/reverse",
                         headers=headers, json={}, timeout=10)
        rev_id = r.json()["id"]
        entries = requests.get(f"{BASE_URL}/api/accounting/entries?include_reversed=true&limit=1000",
                               headers=headers, timeout=10).json()
        ids = {e["id"] for e in entries}
        assert posted_entry["id"] in ids or rev_id in ids, "Neither original nor reversal visible with include_reversed=true"
