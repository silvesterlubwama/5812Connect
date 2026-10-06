"""iter380 — vendors must auto-populate on financial entries.

Covers the three reasons the "Paid to" type-ahead looked empty:
  1. ledger expenses stored `payee` but never created a vendor profile,
  2. the suggest query dropped vendors that carry campus_id (or neither tag),
  3. ledger activity wasn't counted, so real vendors looked stale.
Plus the new manual POST /api/vendors used by the Vendors page.
"""
import os
import uuid

import requests

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


def _headers():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _campus(h):
    r = requests.get(f"{BASE}/api/locations", headers=h, timeout=20)
    r.raise_for_status()
    return next(l["id"] for l in r.json() if not l.get("parent_id"))


def test_manual_vendor_create_then_suggest():
    h = _headers()
    name = f"ITER380 Hardware {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/api/vendors", json={"name": name, "category": "supplier",
                                                   "phone": "0772000111"}, headers=h, timeout=20)
    assert r.status_code == 200, r.text
    s = requests.get(f"{BASE}/api/vendors/suggest", params={"q": name.split()[1]}, headers=h, timeout=20)
    assert s.status_code == 200
    assert any(v["name"] == name for v in s.json()), s.text


def test_duplicate_manual_create_is_reactivated_not_duplicated():
    h = _headers()
    name = f"ITER380 Dup {uuid.uuid4().hex[:6]}"
    requests.post(f"{BASE}/api/vendors", json={"name": name}, headers=h, timeout=20)
    r = requests.post(f"{BASE}/api/vendors", json={"name": name}, headers=h, timeout=20)
    assert r.status_code == 200
    assert "reactivated" in r.json().get("message", "").lower()
    rows = requests.get(f"{BASE}/api/vendors", params={"search": name}, headers=h, timeout=20).json()
    assert len([v for v in rows if v["name"] == name]) == 1


def test_ledger_expense_creates_vendor_and_counts_activity():
    h = _headers()
    loc = _campus(h)
    name = f"ITER380 Fuel {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/api/finance/transactions/expense", json={
        "amount": 45000, "expense_account_code": "5000", "paid_from_code": "1000",
        "location_id": loc, "description": "Diesel for the farm truck",
        "vendor": name, "date": "2026-06-10",
    }, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    je = r.json()
    assert je["payee"] == name
    assert je.get("vendor_id"), "expense did not link a vendor profile"

    s = requests.get(f"{BASE}/api/vendors/suggest", params={"q": name.split()[1]}, headers=h, timeout=20).json()
    assert any(v["name"] == name for v in s)

    rows = requests.get(f"{BASE}/api/vendors", params={"search": name}, headers=h, timeout=30).json()
    row = next(v for v in rows if v["name"] == name)
    assert row["total_expenses"] >= 45000, row
    assert row["expense_count"] >= 1
    assert row.get("is_stale") is not True, "ledger activity not counted — vendor would be archived"


def test_split_journal_entry_keeps_payee():
    h = _headers()
    loc = _campus(h)
    accounts = requests.get(f"{BASE}/api/finance/chart-of-accounts", headers=h, timeout=20).json()
    rows = accounts if isinstance(accounts, list) else accounts.get("accounts", [])
    exp = next(a for a in rows if a["type"] == "expense")
    cash = next(a for a in rows if a["type"] == "asset")
    name = f"ITER380 Split {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/api/finance/journal", json={
        "date": "2026-06-11", "description": "Split expense", "location_id": loc,
        "vendor": name,
        "lines": [
            {"account_id": exp["id"], "account_code": exp["code"], "account_name": exp["name"],
             "debit": 1000, "credit": 0},
            {"account_id": cash["id"], "account_code": cash["code"], "account_name": cash["name"],
             "debit": 0, "credit": 1000},
        ],
    }, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("payee") == name
    s = requests.get(f"{BASE}/api/vendors/suggest", params={"q": "ITER380 Split"}, headers=h, timeout=20).json()
    assert any(v["name"] == name for v in s)


def test_tasks_still_listable():
    """The board-scope widening must not break the plain task list."""
    h = _headers()
    r = requests.get(f"{BASE}/api/tasks", headers=h, timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
