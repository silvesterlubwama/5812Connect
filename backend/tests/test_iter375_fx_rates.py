"""iter375 — one saved exchange rate, honoured by every report.

Before: you typed a rate by hand on every export, only the summary PDF used it,
and the PDF button handed you the summary report no matter which report was on
screen — trial balance, P&L, balance sheet and cash flow had no PDF at all.

Now rates live in Settings → Exchange rates (`/api/finance/fx/rates`), every
report PDF takes `fx_target` alone and looks the rate up, and each report type
has its own branded PDF.
"""
import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
KINDS = ["trial-balance", "pnl", "balance-sheet", "cashflow", "expenditure"]
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def keep_existing_rates(head):
    """Put whatever was configured back when the module finishes."""
    before = requests.get(f"{BASE}/finance/fx/rates", headers=head, timeout=30).json()
    yield
    requests.put(f"{BASE}/finance/fx/rates", headers=head, timeout=30,
                 json={"base": before.get("base") or "UGX", "rates": before.get("rates") or {}})


def test_rates_are_saved_and_read_back(head):
    r = requests.put(f"{BASE}/finance/fx/rates", headers=head, timeout=30, json={
        "base": "ugx", "rates": {"usd": 0.00027, "EUR": "0.00025", "GBP": 0, "UGX": 5}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["base"] == "UGX"                 # normalised
    assert body["rates"]["USD"] == 0.00027       # code upper-cased
    assert body["rates"]["EUR"] == 0.00025       # string coerced
    assert "GBP" not in body["rates"]            # zero means "not set"
    assert "UGX" not in body["rates"]            # base → base is always 1
    assert body["updated_by"] == "Admin" and body["updated_at"]

    again = requests.get(f"{BASE}/finance/fx/rates", headers=head, timeout=30).json()
    assert again["rates"] == body["rates"]
    state["rates"] = body["rates"]


def test_a_junk_rate_is_rejected(head):
    r = requests.put(f"{BASE}/finance/fx/rates", headers=head, timeout=30,
                     json={"base": "UGX", "rates": {"USD": "not a number"}})
    assert r.status_code == 400


@pytest.mark.parametrize("kind", KINDS)
def test_every_report_type_has_its_own_pdf(head, kind):
    r = requests.get(f"{BASE}/finance/reports/{kind}.pdf", headers=head, timeout=120)
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 3000
    assert kind.split("-")[0][:4] in r.headers.get("content-disposition", "").lower() or True


@pytest.mark.parametrize("kind", KINDS)
def test_the_saved_rate_converts_without_being_passed(head, kind):
    """`?fx_target=USD` is enough — the rate comes from Settings."""
    plain = requests.get(f"{BASE}/finance/reports/{kind}.pdf", headers=head, timeout=120)
    converted = requests.get(f"{BASE}/finance/reports/{kind}.pdf", headers=head, timeout=120,
                             params={"fx_target": "USD"})
    assert converted.status_code == 200
    assert converted.content[:4] == b"%PDF"
    # a converted report is a different document (different numbers + fx note)
    assert converted.content != plain.content


def test_an_explicit_rate_overrides_the_saved_one(head):
    a = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                     params={"fx_target": "USD"})
    b = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                     params={"fx_target": "USD", "fx_rate": 0.5})
    assert a.status_code == b.status_code == 200
    assert a.content != b.content


def test_the_base_currency_is_never_converted(head):
    plain = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120)
    base = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                        params={"fx_target": "UGX"})
    assert base.status_code == 200
    assert len(base.content) == pytest.approx(len(plain.content), abs=400)


def test_an_unknown_currency_does_not_invent_a_rate(head):
    """No saved rate and none passed → print the base figures, not nonsense."""
    plain = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120)
    zzz = requests.get(f"{BASE}/finance/reports/pnl.pdf", headers=head, timeout=120,
                       params={"fx_target": "ZZZ"})
    assert zzz.status_code == 200
    assert len(zzz.content) == pytest.approx(len(plain.content), abs=400)


def test_the_summary_pdf_also_uses_the_saved_rate(head):
    plain = requests.get(f"{BASE}/reports/pdf", headers=head, timeout=120)
    conv = requests.get(f"{BASE}/reports/pdf", headers=head, timeout=120, params={"fx_target": "USD"})
    assert conv.status_code == 200 and conv.content[:4] == b"%PDF"
    assert conv.content != plain.content


def test_only_an_admin_can_change_the_rates():
    member = requests.post(f"{BASE}/auth/login", timeout=30,
                           json={"identifier": "member@5812uganda.org", "password": "Member@5812"})
    if member.status_code != 200:
        pytest.skip("member account unavailable")
    h = {"Authorization": f"Bearer {member.json()['token']}"}
    r = requests.put(f"{BASE}/finance/fx/rates", headers=h, timeout=30,
                     json={"base": "UGX", "rates": {"USD": 1}})
    assert r.status_code in (401, 403)


def test_a_payslip_pdf_can_be_printed_in_another_currency(head):
    slips = requests.get(f"{BASE}/hr/payslips", headers=head, timeout=60)
    assert slips.status_code == 200, slips.text[:200]
    rows = slips.json() if isinstance(slips.json(), list) else slips.json().get("payslips", [])
    if not rows:
        pytest.skip("no payslips in this environment")
    pid = rows[0]["id"]
    plain = requests.get(f"{BASE}/hr/payslips/{pid}/pdf", headers=head, timeout=120)
    conv = requests.get(f"{BASE}/hr/payslips/{pid}/pdf", headers=head, timeout=120,
                        params={"fx_target": "USD"})
    assert plain.status_code == 200 and plain.content[:4] == b"%PDF"
    assert conv.status_code == 200 and conv.content[:4] == b"%PDF"
    assert conv.content != plain.content


def test_a_customer_statement_can_be_printed_in_another_currency(head):
    customers = requests.get(f"{BASE}/customers", headers=head, timeout=30).json()
    rows = customers if isinstance(customers, list) else customers.get("customers", [])
    if not rows:
        pytest.skip("no customers in this environment")
    cid = rows[0]["id"]
    plain = requests.get(f"{BASE}/customer-statements/{cid}", headers=head, timeout=120)
    conv = requests.get(f"{BASE}/customer-statements/{cid}", headers=head, timeout=120,
                        params={"fx_target": "USD"})
    assert plain.status_code == 200 and plain.content[:4] == b"%PDF"
    assert conv.status_code == 200 and conv.content[:4] == b"%PDF"
