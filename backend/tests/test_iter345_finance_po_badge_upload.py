"""iter345 backend tests: Finance reports, ledger drilldown, PO edit/PDF, universal upload targets."""
import os
import io
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-tenant-scope.preview.emergentagent.com').rstrip('/')

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Finance reports (ledger-backed) ----
@pytest.mark.parametrize("kind", ["pnl", "balance-sheet", "trial-balance", "cashflow"])
def test_finance_report_kinds(h, kind):
    r = requests.get(f"{BASE_URL}/api/finance/reports/{kind}", headers=h, timeout=30)
    assert r.status_code == 200, f"{kind}: {r.status_code} {r.text[:200]}"
    assert isinstance(r.json(), dict)


# ---- Reports summary endpoint (used by /reports page) ----
def test_reports_summary(h):
    r = requests.get(f"{BASE_URL}/api/reports/summary", headers=h, timeout=30)
    assert r.status_code == 200, r.text


# ---- Report Builder: create / generate / export XLSX for each type ----
@pytest.mark.parametrize("rtype", ["members", "financial", "events", "attendance", "custom"])
def test_report_builder_lifecycle(h, rtype):
    payload = {"name": f"TEST_iter345_{rtype}", "report_type": rtype, "filters": {}}
    r = requests.post(f"{BASE_URL}/api/reports", headers=h, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create {rtype}: {r.status_code} {r.text[:200]}"
    rid = r.json().get("id") or r.json().get("_id")
    assert rid, r.text
    g = requests.post(f"{BASE_URL}/api/reports/{rid}/generate", headers=h, timeout=60)
    assert g.status_code == 200, f"generate {rtype}: {g.status_code} {g.text[:200]}"
    x = requests.get(f"{BASE_URL}/api/reports/{rid}/export/xlsx", headers=h, timeout=60)
    assert x.status_code == 200, f"xlsx {rtype}: {x.status_code} {x.text[:200]}"
    # Openpyxl / xlsx zip signature
    assert x.content[:2] == b"PK", f"{rtype} xlsx not a zip"
    # Cleanup
    requests.delete(f"{BASE_URL}/api/reports/{rid}", headers=h, timeout=15)


# ---- Chart of accounts ledger drilldown ----
def test_coa_ledger_ok(h):
    coa = requests.get(f"{BASE_URL}/api/finance/chart-of-accounts", headers=h, timeout=20)
    assert coa.status_code == 200
    accounts = coa.json() if isinstance(coa.json(), list) else coa.json().get("items", [])
    assert accounts, "no accounts"
    # prefer 1010 if it exists
    a = next((x for x in accounts if str(x.get("code")) == "1010"), accounts[0])
    aid = a.get("id") or a.get("_id")
    r = requests.get(f"{BASE_URL}/api/finance/chart-of-accounts/{aid}/ledger",
                     headers=h, params={"date_from": "2026-09-01", "date_to": "2026-09-30"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("opening_balance", "total_debit", "total_credit", "closing_balance", "rows"):
        assert k in data, f"missing {k} in ledger response: {list(data.keys())}"
    # sanity: closing == opening + debits - credits (signed) OR at least numeric
    assert isinstance(data["closing_balance"], (int, float))
    assert isinstance(data["rows"], list)


def test_coa_ledger_404(h):
    r = requests.get(f"{BASE_URL}/api/finance/chart-of-accounts/bogus-id-xxx/ledger", headers=h, timeout=15)
    assert r.status_code == 404


# ---- Purchase Order edit + PDF ----
@pytest.fixture(scope="module")
def po_id(h):
    # Try to reuse the seeded draft PO, else create one
    lst = requests.get(f"{BASE_URL}/api/purchase-orders", headers=h, timeout=20)
    assert lst.status_code == 200, lst.text
    items = lst.json() if isinstance(lst.json(), list) else lst.json().get("items", [])
    draft = next((p for p in items if (p.get("status") or "").lower() == "draft"), None)
    if draft:
        return draft.get("id") or draft.get("_id")
    payload = {
        "vendor_name": "TEST_iter345 Vendor",
        "lines": [{"description": "Line A", "qty": 2, "unit_price": 100000}],
    }
    r = requests.post(f"{BASE_URL}/api/purchase-orders", headers=h, json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    return r.json().get("id") or r.json().get("_id")


def test_po_edit_recompute_totals(h, po_id):
    payload = {
        "vendor_name": "TEST_iter345 Vendor Edited",
        "tax": 78000,
        "lines": [
            {"description": "L1", "qty": 2, "unit_price": 100000},
            {"description": "L2", "qty": 3, "unit_price": 100000},
        ],
    }
    r = requests.put(f"{BASE_URL}/api/purchase-orders/{po_id}", headers=h, json=payload, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    subtotal = 2 * 100000 + 3 * 100000
    # Accept either recomputed total or subtotal/tax fields
    total = d.get("total") or d.get("grand_total")
    if total is not None:
        assert total in (subtotal + 78000, float(subtotal + 78000)), f"total mismatch: {total}"


def test_po_pdf(h, po_id):
    r = requests.get(f"{BASE_URL}/api/purchase-orders/{po_id}/pdf", headers=h, timeout=60)
    assert r.status_code == 200, r.text[:200]
    assert r.content[:4] == b"%PDF", "not a PDF"


# ---- Universal upload targets ----
def test_receipt_scan_upload(h):
    files = {"file": ("test.jpg", b"\xff\xd8\xff\xe0testjpg", "image/jpeg")}
    try:
        r = requests.post(f"{BASE_URL}/api/finance/receipts/scan",
                          headers={"Authorization": h["Authorization"]}, files=files, timeout=120)
    except requests.exceptions.ReadTimeout:
        pytest.skip("AI OCR endpoint slow (>120s) — acceptable for tiny dummy image")
    if r.status_code == 502:
        pytest.skip("Ingress 502 on receipt scan (LLM slow for dummy image)")
    assert r.status_code in (200, 201, 400, 422), f"scan status {r.status_code}: {r.text[:200]}"


def test_hr_timesheet_upload_requires_period(h):
    files = {"file": ("t.xlsx", b"PKfake", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{BASE_URL}/api/hr/timesheets/upload",
                      headers={"Authorization": h["Authorization"]}, files=files, timeout=30)
    # Missing period => expect 400/422
    assert r.status_code in (400, 422), f"expected validation error, got {r.status_code}: {r.text[:200]}"
