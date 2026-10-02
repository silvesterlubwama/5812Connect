"""iter377 — printing an account ledger produced a blank page.

The dialog's Print button was a bare `window.print()`, and the app's print
stylesheet hides everything outside `.print-area` — which this dialog never
had. So the sheet came out empty every time. It now prints a branded PDF from
the backend, and both the screen and the print carry the FULL transaction
detail (paid to / from, contra account, reference, who handled it, who recorded
it, source) rather than just a description and an amount.
"""
import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
WINDOW = {"date_from": "2026-01-01", "date_to": "2026-12-31"}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def account(head):
    """An account that actually has movement, so the test proves something."""
    rows = requests.get(f"{BASE}/finance/chart-of-accounts", headers=head, timeout=30).json()
    rows = rows if isinstance(rows, list) else rows.get("accounts", [])
    for a in rows:
        led = requests.get(f"{BASE}/finance/chart-of-accounts/{a['id']}/ledger",
                           headers=head, timeout=30, params=WINDOW).json()
        if led.get("count"):
            return a
    pytest.skip("no account with postings in this environment")


def test_each_ledger_row_explains_itself(head, account):
    led = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger",
                       headers=head, timeout=30, params=WINDOW).json()
    assert led["count"] > 0
    for r in led["rows"]:
        # every detail a printed ledger needs is on the row itself
        for field in ("date", "description", "payee", "paid_by", "recorded_by",
                      "reference", "source", "counterparts", "debit", "credit", "balance", "je_id"):
            assert field in r, f"{field} missing from the ledger row"
    # at least one row names the person who keyed it in
    assert any(r["recorded_by"] for r in led["rows"])
    # the contra account is named, not just coded
    assert any(c.get("name") for r in led["rows"] for c in r["counterparts"])


def test_the_running_balance_still_reconciles(head, account):
    led = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger",
                       headers=head, timeout=30, params=WINDOW).json()
    assert led["rows"][-1]["balance"] == led["closing_balance"]
    expected = round(led["opening_balance"] + sum(r["change"] for r in led["rows"]), 2)
    assert expected == led["closing_balance"]


def test_the_ledger_prints_a_real_document(head, account):
    r = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger.pdf",
                     headers=head, timeout=120, params=WINDOW)
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000, "a blank page is exactly the bug being fixed"
    assert "ledger" in r.headers.get("content-disposition", "").lower()


def test_an_empty_period_still_prints_a_sheet(head, account):
    """An account with no movement should print a letterhead, not fail."""
    r = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger.pdf",
                     headers=head, timeout=120,
                     params={"date_from": "1990-01-01", "date_to": "1990-01-31"})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_the_printed_ledger_can_be_converted(head, account):
    plain = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger.pdf",
                         headers=head, timeout=120, params=WINDOW)
    conv = requests.get(f"{BASE}/finance/chart-of-accounts/{account['id']}/ledger.pdf",
                        headers=head, timeout=120, params={**WINDOW, "fx_target": "USD"})
    assert conv.status_code == 200 and conv.content[:4] == b"%PDF"
    assert conv.content != plain.content


def test_an_unknown_account_is_a_404(head):
    r = requests.get(f"{BASE}/finance/chart-of-accounts/acc_does_not_exist/ledger.pdf",
                     headers=head, timeout=60)
    assert r.status_code == 404
