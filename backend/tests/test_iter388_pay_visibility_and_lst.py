"""iter388 — pay figures restricted to HR/finance, statutory toggle audit trail,
and the Uganda LST bracket presets."""
import os
import uuid
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEFAULT_PW = "Test@5812!"


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _make_user(admin_tok, role):
    email = f"iter388_{role.lower().replace(' ', '')}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/admin/users", json={
        "name": f"Iter388 {role}", "email": email, "role": role,
    }, headers=_h(admin_tok), timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json(), email


def test_admin_can_view_pay():
    tok = _login(ADMIN)
    me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=30).json()
    assert me["can_view_pay"] is True
    assert requests.get(f"{API}/hr/salaries", headers=_h(tok), timeout=30).status_code == 200


def test_coordinator_without_hr_or_finance_cannot_see_pay():
    admin = _login(ADMIN)
    user, email = _make_user(admin, "Coordinator")
    try:
        tok = _login({"identifier": email, "password": DEFAULT_PW})
        me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=30).json()
        assert me["can_view_pay"] is False

        # Salary list and the salary audit trail are both refused.
        assert requests.get(f"{API}/hr/salaries", headers=_h(tok), timeout=30).status_code == 403
        assert requests.get(f"{API}/hr/salaries/history", headers=_h(tok), timeout=30).status_code == 403

        # Payslips still resolve, but only ever their own (they have none).
        r = requests.get(f"{API}/hr/payslips", headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        assert all(p.get("staff_id") == user["id"] for p in r.json()), "saw somebody else's payslip"
    finally:
        requests.delete(f"{API}/admin/users/{user['id']}", headers=_h(admin), timeout=30)


def test_hr_grant_restores_pay_visibility():
    admin = _login(ADMIN)
    user, email = _make_user(admin, "Coordinator")
    try:
        requests.put(f"{API}/admin/module-access/users/{user['id']}",
                     json={"module": "hr", "granted": True, "reason": "iter388 test"},
                     headers=_h(admin), timeout=30)
        tok = _login({"identifier": email, "password": DEFAULT_PW})
        me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=30).json()
        assert me["can_view_pay"] is True
        assert requests.get(f"{API}/hr/salaries", headers=_h(tok), timeout=30).status_code == 200
    finally:
        requests.delete(f"{API}/admin/users/{user['id']}", headers=_h(admin), timeout=30)


def test_statutory_toggle_is_recorded_per_line_in_salary_history():
    admin = _login(ADMIN)
    staff, email = _make_user(admin, "Staff")
    sal = requests.post(f"{API}/hr/salaries", json={
        "staff_id": staff["id"], "base_salary": 800000, "currency": "UGX",
        "pay_frequency": "monthly",
    }, headers=_h(admin), timeout=30)
    assert sal.status_code in (200, 201), sal.text
    sal = sal.json()
    try:
        # Switch one line on, leave the rest at the campus default.
        r = requests.put(f"{API}/hr/salaries/{sal['id']}", json={
            "statutory_overrides": {"nssf_employer": {"enabled": True}},
            "reason": "Enrolled in employer NSSF",
        }, headers=_h(admin), timeout=30)
        assert r.status_code == 200, r.text

        hist = requests.get(f"{API}/hr/salaries/history", params={"salary_id": sal["id"]},
                            headers=_h(admin), timeout=30).json()
        entry = hist[0]
        assert "statutory:nssf_employer" in entry["changes"], entry["changes"]
        assert entry["changes"]["statutory:nssf_employer"] == {"from": "campus default", "to": "on"}
        assert entry["changed_by_name"]
        assert entry["changed_at"]
        assert entry["reason"] == "Enrolled in employer NSSF"
        # The whole-dict blob must NOT be logged any more.
        assert "statutory_overrides" not in entry["changes"]

        # Switching it back off is logged as its own event.
        requests.put(f"{API}/hr/salaries/{sal['id']}", json={
            "statutory_overrides": {"nssf_employer": {"enabled": False}},
        }, headers=_h(admin), timeout=30)
        hist = requests.get(f"{API}/hr/salaries/history", params={"salary_id": sal["id"]},
                            headers=_h(admin), timeout=30).json()
        assert hist[0]["changes"]["statutory:nssf_employer"] == {"from": "on", "to": "off"}

        # A per-person rate shows the figure, not just the switch.
        requests.put(f"{API}/hr/salaries/{sal['id']}", json={
            "statutory_overrides": {"nssf_employer": {"enabled": True, "amount": 7, "is_percentage": True}},
        }, headers=_h(admin), timeout=30)
        hist = requests.get(f"{API}/hr/salaries/history", params={"salary_id": sal["id"]},
                            headers=_h(admin), timeout=30).json()
        assert hist[0]["changes"]["statutory:nssf_employer"]["to"] == "on, 7%"

        # An unrelated edit must not invent a statutory entry.
        requests.put(f"{API}/hr/salaries/{sal['id']}", json={"base_salary": 850000},
                     headers=_h(admin), timeout=30)
        hist = requests.get(f"{API}/hr/salaries/history", params={"salary_id": sal["id"]},
                            headers=_h(admin), timeout=30).json()
        assert list(hist[0]["changes"]) == ["base_salary"]
    finally:
        requests.delete(f"{API}/hr/salaries/{sal['id']}", headers=_h(admin), timeout=30)
        requests.delete(f"{API}/admin/users/{staff['id']}", headers=_h(admin), timeout=30)


def test_uganda_lst_bracket_presets():
    tok = _login(ADMIN)
    opts = requests.get(f"{API}/hr/compliance-options/Uganda", headers=_h(tok), timeout=30).json()["options"]
    lst = {o["name"]: o for o in opts if "LST" in o["name"]}
    assert len(lst) == 2, list(lst)
    annual = lst["LST (Local Service Tax) — annual"]
    monthly = lst["LST (Local Service Tax) — monthly instalment"]
    for o in (annual, monthly):
        assert o["band_mode"] == "bracket_amount"
        assert o["type"] == "deduction"
        assert o["is_percentage"] is False
        assert len(o["bands"]) == 11
        assert o["bands"][-1]["up_to"] is None      # "and above" catch-all
        assert o["liability_account_code"] == "2200"
    # Official schedule, and the instalment version is exactly a quarter of it.
    assert [b["amount"] for b in annual["bands"]] == [0, 5000, 10000, 20000, 30000, 40000,
                                                      60000, 70000, 80000, 90000, 100000]
    for a, m in zip(annual["bands"], monthly["bands"]):
        assert m["up_to"] == a["up_to"]
        assert m["amount"] * 4 == a["amount"]


def test_lst_preset_calculates_the_right_bracket():
    from routers.payroll_engine import apply_statutory_lines
    tok = _login(ADMIN)
    opts = requests.get(f"{API}/hr/compliance-options/Uganda", headers=_h(tok), timeout=30).json()["options"]
    annual = next(o for o in opts if o["name"].endswith("annual"))
    cases = {80_000: 0, 150_000: 5_000, 450_000: 30_000, 750_000: 70_000, 4_000_000: 100_000}
    for gross, expected in cases.items():
        out = apply_statutory_lines([annual], {}, gross)
        assert out["employee_deductions"] == expected, f"gross {gross} -> {out['employee_deductions']}"
