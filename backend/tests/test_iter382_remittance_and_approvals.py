"""iter382 — remittance payments clear the liability, dual approval gates
payment, payslip email on payday, and finance-changed refresh plumbing.
"""
import os
import uuid

import requests

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


def _h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _campus(h):
    return next(l["id"] for l in requests.get(f"{BASE}/api/locations", headers=h, timeout=20).json()
                if not l.get("parent_id"))


def _cash_account(h):
    accts = requests.get(f"{BASE}/api/finance/chart-of-accounts", headers=h, timeout=20).json()
    rows = accts if isinstance(accts, list) else accts.get("accounts", [])
    return next(a for a in rows if a["type"] == "asset" and a["code"].startswith("10"))


def _staff_id(h):
    users = requests.get(f"{BASE}/api/admin/users", headers=h, timeout=30).json()
    users = users if isinstance(users, list) else users.get("users", [])
    return users[0]["id"]


def _manual_payslip(h, loc, gross=600000):
    r = requests.post(f"{BASE}/api/hr/payslips/manual", json={
        "staff_id": _staff_id(h), "period": f"2026-02-iter382-{uuid.uuid4().hex[:5]}",
        "gross_salary": gross, "currency": "UGX", "location_id": loc,
    }, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_dual_approval_blocks_payment_until_two_people_sign():
    h = _h()
    loc = _campus(h)
    requests.put(f"{BASE}/api/hr/settings/{loc}", json={"dual_approval": True, "email_payslips": False},
                 headers=h, timeout=20).raise_for_status()
    slip = _manual_payslip(h, loc)

    first = requests.put(f"{BASE}/api/hr/payslips/{slip['id']}", json={"status": "approved"}, headers=h, timeout=30)
    assert first.status_code == 200, first.text
    assert len(first.json()["approvals"]) == 1

    # Same person approving again must not count as a second signature.
    again = requests.put(f"{BASE}/api/hr/payslips/{slip['id']}", json={"status": "approved"}, headers=h, timeout=30)
    assert len(again.json()["approvals"]) == 1

    blocked = requests.put(f"{BASE}/api/hr/payslips/{slip['id']}",
                           json={"status": "paid", "payroll_location_id": loc}, headers=h, timeout=30)
    assert blocked.status_code == 400
    assert "second approval" in blocked.json()["detail"].lower()

    # Switching the control off lets the same admin pay it.
    requests.put(f"{BASE}/api/hr/settings/{loc}", json={"dual_approval": False}, headers=h, timeout=20)
    paid = requests.put(f"{BASE}/api/hr/payslips/{slip['id']}",
                        json={"status": "paid", "payroll_location_id": loc}, headers=h, timeout=60)
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json().get("finance_posted") is True, paid.json().get("finance_post_error")
    requests.put(f"{BASE}/api/hr/settings/{loc}", json={"dual_approval": True}, headers=h, timeout=20)


def test_remittance_payment_clears_the_liability():
    h = _h()
    loc = _campus(h)
    acct = _cash_account(h)

    before = requests.get(f"{BASE}/api/hr/payroll/remittance",
                          params={"location_id": loc, "status": "paid"}, headers=h, timeout=60).json()
    assert before["total_outstanding"] > 0, "need some accrued statutory amounts to remit"
    target = next(l["name"] for l in before["lines"] if l["outstanding"] > 0)
    target_amount = next(l["outstanding"] for l in before["lines"] if l["name"] == target)

    pay = requests.post(f"{BASE}/api/hr/payroll/remittance/pay", json={
        "location_id": loc, "status": "paid", "lines": [target],
        "paid_from_account_id": acct["id"], "payee": "URA",
        "reference": f"PRN-{uuid.uuid4().hex[:6]}", "notes": "iter382 test filing",
    }, headers=h, timeout=60)
    assert pay.status_code == 200, pay.text
    body = pay.json()
    assert round(body["total"], 2) == round(target_amount, 2)
    assert body["je_id"], "remittance must post a journal entry"

    je = requests.get(f"{BASE}/api/finance/journal/{body['je_id']}", headers=h, timeout=20).json()
    debits = {l["account_code"]: l["debit"] for l in je["lines"] if l["debit"]}
    credits = {l["account_code"]: l["credit"] for l in je["lines"] if l["credit"]}
    assert "2200" in debits, "the liability must be debited (cleared)"
    assert acct["code"] in credits, "the chosen bank/cash account must be credited"
    assert round(sum(debits.values()), 2) == round(sum(credits.values()), 2)

    after = requests.get(f"{BASE}/api/hr/payroll/remittance",
                         params={"location_id": loc, "status": "paid"}, headers=h, timeout=60).json()
    line_after = next(l for l in after["lines"] if l["name"] == target)
    assert line_after["remitted"] >= target_amount
    assert line_after["outstanding"] <= 0.01, "line should now read as settled"
    assert after["total_outstanding"] < before["total_outstanding"]

    hist = requests.get(f"{BASE}/api/hr/payroll/remittance/payments",
                        params={"location_id": loc}, headers=h, timeout=30).json()
    assert any(p["id"] == body["id"] for p in hist["payments"])


def test_remittance_pay_requires_an_account_and_rejects_nothing_due():
    h = _h()
    loc = _campus(h)
    no_acct = requests.post(f"{BASE}/api/hr/payroll/remittance/pay",
                            json={"location_id": loc}, headers=h, timeout=30)
    assert no_acct.status_code == 400
    assert "account" in no_acct.json()["detail"].lower()

    acct = _cash_account(h)
    nothing = requests.post(f"{BASE}/api/hr/payroll/remittance/pay", json={
        "location_id": loc, "paid_from_account_id": acct["id"], "lines": ["No Such Statutory Line"],
    }, headers=h, timeout=30)
    assert nothing.status_code == 400
    assert "outstanding" in nothing.json()["detail"].lower()


def test_remittance_report_exposes_remitted_and_outstanding():
    h = _h()
    rep = requests.get(f"{BASE}/api/hr/payroll/remittance", params={"status": "all"}, headers=h, timeout=60).json()
    assert "total_remitted" in rep and "total_outstanding" in rep
    for l in rep["lines"]:
        assert round(l["remitted"] + l["outstanding"], 2) == round(l["total"], 2)
    pdf = requests.get(f"{BASE}/api/hr/payroll/remittance.pdf", params={"status": "all"}, headers=h, timeout=90)
    assert pdf.status_code == 200 and len(pdf.content) > 500
