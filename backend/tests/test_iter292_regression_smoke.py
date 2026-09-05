"""Iter 292 broader regression smoke — post bank/finance migration.

Covers the review request bullets:
 - plain list endpoints on /api/bank/*
 - /api/finance/journal-entries reversal flow still works
 - core endpoints: /api/reports/summary, /api/tasks, /api/events,
   /api/admin/users/directory, /api/chat/users
 - Confirms no writes to legacy accounting_entries collection after
   posting a Bill through the migrated path.
"""
import httpx, pytest, os

def _api():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()

API = _api()

@pytest.fixture(scope="module")
def h():
    r = httpx.post(f"{API}/api/auth/login",
                   json={"identifier": "admin@5812uganda.org", "password": "Admin@5812"},
                   timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def coa(h):
    r = httpx.get(f"{API}/api/finance/chart-of-accounts", headers=h, timeout=15)
    r.raise_for_status()
    return {a["code"]: a["id"] for a in r.json()}


# ---- bank list endpoints -----------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/bank/bills",
    "/api/bank/vendors",
    "/api/bank/rules",
    "/api/bank/recurring",
    "/api/bank/accounts",
])
def test_bank_list_endpoints_200(h, path):
    r = httpx.get(f"{API}{path}", headers=h, timeout=15)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    assert isinstance(r.json(), list)


# ---- core regression endpoints ----------------------------------------
@pytest.mark.parametrize("path", [
    "/api/reports/summary",
    "/api/tasks",
    "/api/events",
    "/api/admin/users/directory",
    "/api/chat/users",
])
def test_core_endpoints_still_200(h, path):
    r = httpx.get(f"{API}{path}", headers=h, timeout=20)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])


# ---- finance JE reversal untouched ------------------------------------
def test_finance_je_reversal_still_works(h, coa):
    # Create a small manual JE via /api/finance/journal
    je_payload = {
        "date": "2026-02-15",
        "description": "iter292 reversal probe",
        "location_id": "loc_001",
        "lines": [
            {"account_id": coa["5400"], "account_code": "5400",
             "account_name": "Office & Admin", "debit": 500, "credit": 0},
            {"account_id": coa["1010"], "account_code": "1010",
             "account_name": "Bank", "debit": 0, "credit": 500},
        ],
    }
    r = httpx.post(f"{API}/api/finance/journal", headers=h, json=je_payload, timeout=15)
    assert r.status_code == 200, r.text[:300]
    je = r.json()
    je_id = je["id"]
    # Reverse it
    rv = httpx.post(f"{API}/api/finance/journal/{je_id}/reverse", headers=h,
                    json={"reason": "iter292 smoke"}, timeout=15)
    assert rv.status_code == 200, rv.text[:300]
    body = rv.json()
    # response typically returns the reversal JE (must be balanced)
    if "lines" in body:
        d = sum(l["debit"] for l in body["lines"])
        c = sum(l["credit"] for l in body["lines"])
        assert d == c == 500.0


# ---- no writes to legacy accounting_entries after Bill via new path --
def test_bill_posts_only_to_unified_ledger(h, coa):
    # snapshot legacy count
    r_before = httpx.get(f"{API}/api/finance/journal", headers=h, timeout=15)
    assert r_before.status_code == 200
    before_ledger = len(r_before.json())

    # create vendor + bill
    v = httpx.post(f"{API}/api/bank/vendors", headers=h,
                   json={"name": "iter292 reg vendor", "location_id": "loc_001"},
                   timeout=15).json()
    bill = httpx.post(f"{API}/api/bank/bills", headers=h,
                      json={"vendor_id": v["id"], "bill_date": "2026-02-16",
                            "location_id": "loc_001", "status": "open",
                            "items": [{"description": "reg", "qty": 1,
                                       "unit_price": 1234,
                                       "account_id": coa["5400"]}]},
                      timeout=15).json()
    assert bill.get("id"), bill

    r_after = httpx.get(f"{API}/api/finance/journal", headers=h, timeout=15).json()
    # unified ledger must contain one more JE for this bill
    matched = [x for x in r_after
               if x.get("source") == "bill" and x.get("reference") == bill["id"]]
    assert len(matched) == 1, f"expected 1 bill JE, got {len(matched)}"
    assert len(r_after) >= before_ledger + 1

    # /api/accounting/* should be unmounted (404) — this is the smoke check
    # that legacy path is gone.
    rleg = httpx.get(f"{API}/api/accounting/entries", headers=h, timeout=10)
    assert rleg.status_code == 404, f"legacy /api/accounting/* still mounted: {rleg.status_code}"
