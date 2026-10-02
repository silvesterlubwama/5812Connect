"""iter374 — branded report letterhead + expenditure accountability.

Reports used to print "58:12 Connect" with no logo, and every financial report
stopped at the account total, so "Education 6,934,800" could not be defended in
an audit. Now:
  • `/api/reports/pdf` and the new `/api/finance/reports/expenditure.pdf` carry
    the organisation's own logo + name from Settings → Branding, plus the
    period, campus, prepared-by and printed-on lines, and a branded filename;
  • `/api/finance/reports/expenditure` lists each payment (paid to,
    description, category, campus, paid by, recorded by, receipt) with
    subtotals by category and then campus, including staff-portal expenses that
    never reached the ledger;
  • an expense records `payee` / `receipt_number`.

iter376 — `purpose` was dropped: it said the same thing as the ledger's own
`description`, so there is now exactly one field for WHY money was spent.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER374_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    """Reverse the probe expense so the ledger is left exactly as found."""
    h = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/login', json=ADMIN, timeout=30).json()['token']}"}
    if state.get("je"):
        requests.post(f"{BASE}/finance/journal/{state['je']}/reverse", headers=h, timeout=30,
                      json={"reason": "iter374 test cleanup"})


def _campus(head):
    rows = requests.get(f"{BASE}/locations", headers=head, timeout=30).json()
    rows = rows if isinstance(rows, list) else rows.get("locations", [])
    return next(l for l in rows if not l.get("parent_id"))


def _expense_account(head):
    coa = requests.get(f"{BASE}/finance/chart-of-accounts", headers=head, timeout=30).json()
    rows = coa if isinstance(coa, list) else coa.get("accounts", [])
    return next(a for a in rows if a["type"] == "expense")


def test_an_expense_records_who_was_paid_and_why(head):
    acct = _expense_account(head)
    state["account_code"] = acct["code"]
    r = requests.post(f"{BASE}/finance/transactions/expense", headers=head, timeout=30, json={
        "amount": 123456,
        "expense_account_code": acct["code"],
        "paid_from_code": "1000",
        "location_id": _campus(head)["id"],
        "description": "Roofing sheets for the shelter dormitory",
        "payee": f"{TAG} Hardware Ltd",
        "receipt_number": "RCT-374",
    })
    assert r.status_code in (200, 201), r.text
    je = r.json()
    state["je"] = je["id"]
    assert je["payee"] == f"{TAG} Hardware Ltd"
    assert je["description"] == "Roofing sheets for the shelter dormitory"
    assert je["receipt_number"] == "RCT-374"
    assert "purpose" not in je          # one field for "why", not two


def test_the_expenditure_report_shows_that_payment_in_full(head):
    r = requests.get(f"{BASE}/finance/reports/expenditure", headers=head, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    mine = next((x for x in data["rows"] if x["id"] == state["je"]), None)
    assert mine, "the probe expense is missing from the detail report"
    assert mine["payee"] == f"{TAG} Hardware Ltd"
    assert mine["description"] == "Roofing sheets for the shelter dormitory"
    assert "purpose" not in mine
    assert mine["reference"] == "RCT-374"
    assert mine["recorded_by"] == "Admin"
    assert mine["location_name"] and mine["category"]
    assert mine["status"] == "posted"


def test_it_subtotals_by_category_then_campus(head):
    data = requests.get(f"{BASE}/finance/reports/expenditure", headers=head, timeout=60).json()
    assert data["by_category"], "no subtotals"
    for cat in data["by_category"]:
        assert cat["campuses"]
        assert round(sum(c["total"] for c in cat["campuses"]), 2) == cat["total"]
        assert cat["count"] == sum(c["count"] for c in cat["campuses"])
    assert round(sum(c["total"] for c in data["by_category"]), 2) == data["total"]
    assert round(data["total_posted"] + data["total_pending"], 2) == data["total"]


def test_portal_expenses_are_included_and_flagged_pending(head):
    with_portal = requests.get(f"{BASE}/finance/reports/expenditure", headers=head, timeout=60).json()
    ledger_only = requests.get(f"{BASE}/finance/reports/expenditure", headers=head, timeout=60,
                               params={"include_portal": "false"}).json()
    assert with_portal["count"] >= ledger_only["count"]
    portal = [r for r in with_portal["rows"] if r["source"] == "portal"]
    assert portal, "the staff-portal expenses should be visible here"
    assert all(r["status"] != "posted" or r["source"] == "ledger" for r in portal)
    assert all(r["source"] == "ledger" for r in ledger_only["rows"])


def test_a_category_drill_down_returns_only_that_account(head):
    data = requests.get(f"{BASE}/finance/reports/expenditure", headers=head, timeout=60,
                        params={"account_code": state["account_code"]}).json()
    assert data["rows"], "drill-down is empty"
    assert {r["category_code"] for r in data["rows"]} == {state["account_code"]}
    # a drill-down is about the ledger account, so portal rows stay out
    assert all(r["source"] == "ledger" for r in data["rows"])


def test_the_expenditure_pdf_is_branded_and_downloads(head):
    r = requests.get(f"{BASE}/finance/reports/expenditure.pdf", headers=head, timeout=120)
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000
    disp = r.headers.get("content-disposition", "")
    assert "5812" not in disp.replace("58-12", "")      # no hardcoded 5812_report_
    assert "expenditure" in disp


def test_the_summary_pdf_uses_the_org_name_not_ours(head):
    settings = requests.get(f"{BASE}/admin/system-settings/public", timeout=30).json()
    org = (settings.get("branding") or {}).get("app_name") or "58:12 Connect"
    r = requests.get(f"{BASE}/reports/pdf", headers=head, timeout=120)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    slug = "".join(c if c.isalnum() else "-" for c in org.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    assert slug in r.headers.get("content-disposition", "")
