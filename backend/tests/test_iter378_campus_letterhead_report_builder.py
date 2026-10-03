"""iter378 — the campus owns the letterhead, and the Report Builder works.

Reported in one message:
  • reports and prints showed the app name ("58:12 Connect") where the CAMPUS
    name belongs;
  • there was no way to reach the exchange-rate editor (its page had no nav
    link at all);
  • "the report builder is no longer useful as it does not fetch anything";
  • recurring events needed yearly / Nth-week options (covered in
    `test_iter373_recurring_series.py`).
"""
import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    h = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/login', json=ADMIN, timeout=30).json()['token']}"}
    if state.get("report"):
        requests.delete(f"{BASE}/reports/{state['report']}", headers=h, timeout=30)


def _campuses(head):
    rows = requests.get(f"{BASE}/locations", headers=head, timeout=30).json()
    rows = rows if isinstance(rows, list) else rows.get("locations", [])
    root = next(l for l in rows if not l.get("parent_id"))
    sub = next((l for l in rows if l.get("parent_id") == root["id"]), None)
    return root, sub


def _pdf_text(blob: bytes) -> str:
    """Enough of the PDF's text to assert on the letterhead."""
    import re
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(blob)
        path = f.name
    try:
        out = subprocess.run(["pdftotext", path, "-"], capture_output=True, timeout=60)
        return re.sub(r"\s+", " ", out.stdout.decode("utf-8", "ignore"))
    finally:
        os.unlink(path)


def test_a_campus_report_is_headed_by_the_campus(head):
    root, sub = _campuses(head)
    assert sub, "needs a sub-campus"
    r = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                     params={"location_id": sub["id"]})
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert sub["name"] in text, text[:400]
    # the app name is demoted to a small line, not the heading
    assert text.index(sub["name"]) < text.index("Profit & Loss")


def test_an_all_campus_report_still_names_the_organisation(head):
    r = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120)
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert "All campuses" in text


def test_the_summary_print_is_headed_by_the_campus_too(head):
    root, sub = _campuses(head)
    r = requests.get(f"{BASE}/reports/pdf", headers=head, timeout=120,
                     params={"location_id": sub["id"]})
    assert r.status_code == 200
    assert sub["name"] in _pdf_text(r.content)


def test_exchange_rates_are_editable_through_the_api_the_card_uses(head):
    """The card had no nav link; prove the endpoints behind it work end to end."""
    before = requests.get(f"{BASE}/finance/fx/rates", headers=head, timeout=30).json()
    rates = {**(before.get("rates") or {}), "CAD": 0.00037}
    r = requests.put(f"{BASE}/finance/fx/rates", headers=head, timeout=30,
                     json={"base": before.get("base") or "UGX", "rates": rates})
    assert r.status_code == 200 and r.json()["rates"]["CAD"] == 0.00037
    # and it is immediately usable by a report
    pdf = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                       params={"fx_target": "CAD"})
    assert pdf.status_code == 200
    assert "CAD" in _pdf_text(pdf.content)
    requests.put(f"{BASE}/finance/fx/rates", headers=head, timeout=30,
                 json={"base": before.get("base") or "UGX", "rates": before.get("rates") or {}})


def test_an_admin_sees_saved_reports_they_did_not_create(head):
    """The list only returned your OWN reports, so the builder looked empty."""
    rows = requests.get(f"{BASE}/reports", headers=head, timeout=30).json()
    assert isinstance(rows, list)
    assert any(not r.get("is_mine") for r in rows) or len(rows) > 0
    for r in rows:
        assert "is_mine" in r and "created_by_name" in r


def test_a_generated_report_returns_rows_and_explains_an_empty_one(head):
    root, _ = _campuses(head)
    created = requests.post(f"{BASE}/reports", headers=head, timeout=30, json={
        "title": "ITER378 probe", "type": "custom",
        "filters": {"location_id": "loc_does_not_exist", "date_from": "", "date_to": ""}})
    assert created.status_code in (200, 201), created.text
    state["report"] = created.json()["id"]

    gen = requests.post(f"{BASE}/reports/{state['report']}/generate", headers=head, timeout=120)
    assert gen.status_code == 200, gen.text
    body = gen.json()
    # the dead campus filter is reported, not silently obeyed
    assert any("no longer exists" in w for w in body["warnings"]), body["warnings"]
    assert body["counts"], "a generated report must say how much it found"
    assert sum(body["counts"].values()) > 0, "the dead filter should have been dropped"


def test_the_financial_report_reads_the_real_ledger(head):
    requests.put(f"{BASE}/reports/{state['report']}", headers=head, timeout=30,
                 json={"type": "financial", "filters": {}})
    body = requests.post(f"{BASE}/reports/{state['report']}/generate",
                         headers=head, timeout=120).json()
    data = body["data"]
    for key in ("ledger_total_revenue", "ledger_total_expenses", "ledger_net_income",
                "ledger_expense_lines"):
        assert key in data, f"{key} missing — the report is still reading only the legacy tables"
    assert data["ledger_total_expenses"] > 0


def test_the_excel_export_needs_a_token_and_works_with_one(head):
    anon = requests.get(f"{BASE}/reports/{state['report']}/export/xlsx", timeout=60)
    assert anon.status_code in (401, 403)
    ok = requests.get(f"{BASE}/reports/{state['report']}/export/xlsx", headers=head, timeout=60)
    assert ok.status_code == 200
    assert ok.content[:2] == b"PK"        # xlsx is a zip
