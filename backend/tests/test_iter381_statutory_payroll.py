"""iter381 — statutory payroll: campus lines applied automatically, per-employee
overrides, employer contributions, ledger posting and the remittance report.
"""
import os
import uuid

import requests

from routers.payroll_engine import apply_statutory_lines, line_key

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
LINES = [
    {"name": "PAYE", "type": "deduction", "is_percentage": True, "amount": 0,
     "bands": [{"up_to": 235000, "rate": 0}, {"up_to": 335000, "rate": 10},
               {"up_to": 410000, "rate": 20}, {"up_to": 10000000, "rate": 30},
               {"up_to": None, "rate": 40}]},
    {"name": "NSSF Employee", "type": "deduction", "is_percentage": True, "amount": 5},
    {"name": "NSSF Employer", "type": "employer_contribution", "mode": "employer_cost",
     "is_percentage": True, "amount": 10, "account_code": "5002"},
    {"name": "Transport top-up", "type": "employer_contribution", "mode": "add_to_pay",
     "is_percentage": False, "amount": 50000},
]


def _h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _campus(h):
    r = requests.get(f"{BASE}/api/locations", headers=h, timeout=20)
    return next(l["id"] for l in r.json() if not l.get("parent_id"))


# ---------- engine (pure) ----------

def test_progressive_bands_match_ura_table():
    paye = [LINES[0]]
    assert apply_statutory_lines(paye, {}, 200000)["employee_deductions"] == 0
    assert apply_statutory_lines(paye, {}, 410000)["employee_deductions"] == 25000
    assert apply_statutory_lines(paye, {}, 400000)["employee_deductions"] == 23000


def test_employer_modes_split_pay_from_cost():
    r = apply_statutory_lines(LINES, {}, 1000000)
    assert r["employer_cost"] == 100000          # NSSF employer — not paid to staff
    assert r["pay_additions"] == 50000           # transport — paid with salary
    assert r["employee_deductions"] == 50000 + apply_statutory_lines([LINES[0]], {}, 1000000)["employee_deductions"]
    assert r["withheld_liability"] == r["employee_deductions"]


def test_per_employee_override_and_optout():
    salary = {"statutory_overrides": {
        "nssf_employee": {"amount": 7, "is_percentage": True},
        "nssf_employer": {"enabled": False},
    }}
    r = apply_statutory_lines(LINES, salary, 1000000)
    nssf = next(i for i in r["items"] if i["name"] == "NSSF Employee")
    assert nssf["calculated_amount"] == 70000
    assert "per-employee rate" in nssf["details"]
    assert all(i["name"] != "NSSF Employer" for i in r["items"])
    assert r["employer_cost"] == 0


def test_line_key_is_slug():
    assert line_key({"name": "NSSF Employer"}) == "nssf_employer"
    assert line_key({"name": "x", "key": "custom"}) == "custom"


# ---------- API ----------

def test_payslip_applies_campus_lines_and_posts_split_journal():
    h = _h()
    loc = _campus(h)
    settings = requests.get(f"{BASE}/api/hr/settings/{loc}", headers=h, timeout=20).json()
    original = settings.get("compliance_lines") or []
    try:
        requests.put(f"{BASE}/api/hr/settings/{loc}",
                     json={"compliance_lines": LINES[:3], "country": "Uganda", "hr_enabled": True,
                           # iter382 added a second-signature gate; this test is about the
                           # statutory maths, so pay straight through.
                           "dual_approval": False, "email_payslips": False},
                     headers=h, timeout=20).raise_for_status()

        users = requests.get(f"{BASE}/api/admin/users", headers=h, timeout=30).json()
        users = users if isinstance(users, list) else users.get("users", [])
        staff_id = users[0]["id"]
        sal = requests.post(f"{BASE}/api/hr/salaries", json={
            "staff_id": staff_id, "base_salary": 1000000, "currency": "UGX",
            "location_id": loc, "wage_type": "salary", "pay_frequency": "monthly",
            "statutory_overrides": {"nssf_employee": {"enabled": True, "amount": 7, "is_percentage": True}},
        }, headers=h, timeout=20).json()
        assert sal["statutory_overrides"]["nssf_employee"]["amount"] == 7

        period = f"2026-0{uuid.uuid4().int % 8 + 1}"
        ps = requests.post(f"{BASE}/api/hr/payslips/manual", json={
            "staff_id": staff_id, "period": f"{period}-iter381-{uuid.uuid4().hex[:4]}",
            "gross_salary": 1000000, "currency": "UGX", "location_id": loc,
        }, headers=h, timeout=30)
        assert ps.status_code == 200, ps.text
        slip = ps.json()
        names = [li["name"] for li in slip["line_items"]]
        assert "PAYE" in names and "NSSF Employee" in names and "NSSF Employer" in names
        assert slip["employer_contributions"] == 100000
        assert slip["total_cost"] == round(slip["gross_salary"] + slip["allowances"] + 100000, 2)
        assert slip["net_salary"] == round(slip["gross_salary"] - slip["deductions"], 2)

        paid = requests.put(f"{BASE}/api/hr/payslips/{slip['id']}",
                            json={"status": "paid", "payroll_location_id": loc}, headers=h, timeout=60)
        assert paid.status_code == 200, paid.text
        body = paid.json()
        assert body.get("finance_posted") is True, body.get("finance_post_error")
        je = requests.get(f"{BASE}/api/finance/journal/{body['finance_je_id']}", headers=h, timeout=20).json()
        codes = {l["account_code"] for l in je["lines"]}
        assert "2200" in codes, "withheld deductions were not credited to a liability account"
        debits = round(sum(l["debit"] for l in je["lines"]), 2)
        credits = round(sum(l["credit"] for l in je["lines"]), 2)
        assert debits == credits
        # employer contribution is a real cost on top of gross
        assert debits >= round(slip["gross_salary"] + 100000, 2)

        rem = requests.get(f"{BASE}/api/hr/payroll/remittance",
                           params={"location_id": loc, "status": "paid"}, headers=h, timeout=60).json()
        assert rem["total"] >= rem["total_employee"] > 0
        assert any(l["name"] == "NSSF Employer" and l["employer_contribution"] > 0 for l in rem["lines"])
        assert all("staff" in l for l in rem["lines"]), "remittance must name who it was withheld from"

        for ext, ctype in (("csv", "text/csv"), ("pdf", "application/pdf")):
            r = requests.get(f"{BASE}/api/hr/payroll/remittance.{ext}",
                             params={"location_id": loc, "status": "paid"}, headers=h, timeout=90)
            assert r.status_code == 200 and len(r.content) > 300
            assert ctype in r.headers.get("content-type", "")

        pdf = requests.get(f"{BASE}/api/hr/payslips/{slip['id']}/pdf", headers=h, timeout=60)
        assert pdf.status_code == 200 and len(pdf.content) > 1000

        requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=h, timeout=20)
    finally:
        requests.put(f"{BASE}/api/hr/settings/{loc}",
                     json={"compliance_lines": original, "dual_approval": True, "email_payslips": True},
                     headers=h, timeout=20)
