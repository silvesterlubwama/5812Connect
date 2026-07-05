"""iter215 backend tests — Payroll pro-ration from approved timesheets.

Covers:
- POST /api/hr/payslips/generate with use_timesheets=true: approved timesheet's
  days_worked pro-rates the payslip (net < gross, Days-worked adjustment line).
- use_timesheets=false: timesheets ignored, full-month pay.
- days_worked_override wins over approved timesheet.
- pto_days from timesheet merged if no explicit override.
- Regression tag: iter214 suite still passes.
"""
import os
import uuid
import calendar
import pytest
import requests
from datetime import date


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE = _base()
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEFAULT_PW = "Test@5812!"
TAG = f"iter215_{uuid.uuid4().hex[:6]}"


def _working_days(period: str) -> int:
    y, m = map(int, period.split("-"))
    last = calendar.monthrange(y, m)[1]
    n = 0
    for d in range(1, last + 1):
        if date(y, m, d).weekday() < 5:
            n += 1
    return n


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:400]
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def campus(admin_h):
    r = requests.get(f"{BASE}/api/locations", headers=admin_h, timeout=20)
    assert r.status_code == 200
    locs = [l for l in r.json() if l.get("type") in ("campus", "main") and not l.get("is_restricted")]
    assert locs, "no campus locations"
    return locs[0]["id"]


@pytest.fixture(scope="module")
def staff(admin_h, campus):
    """Create a fresh staff user and an active salary of 100000/mo."""
    email = f"TEST_{TAG}_staff_{uuid.uuid4().hex[:4]}@iter215.test"
    body = {
        "name": f"TEST_{TAG}_staff",
        "email": email,
        "role": "Staff",
        "password": DEFAULT_PW,
        "location_ids": [campus],
        "location_id": campus,
        "also_create_member": False,
    }
    r = requests.post(f"{BASE}/api/admin/users", json=body, headers=admin_h, timeout=20)
    assert r.status_code in (200, 201), r.text[:400]
    user = r.json()
    # Create salary
    sal_body = {
        "staff_id": user["id"],
        "location_id": campus,
        "base_salary": 100000,
        "currency": "UGX",
        "pay_frequency": "monthly",
    }
    s = requests.post(f"{BASE}/api/hr/salaries", json=sal_body, headers=admin_h, timeout=20)
    assert s.status_code == 200, s.text[:400]
    return {"user": user, "salary": s.json(), "location_id": campus}


def _submit_and_approve_ts(admin_h, staff_id, location_id, period, days_worked, pto_days=0):
    body = {
        "period": period,
        "days_worked": days_worked,
        "pto_days": pto_days,
        "staff_id": staff_id,
        "location_id": location_id,
    }
    r = requests.post(f"{BASE}/api/hr/timesheets", json=body, headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text[:400]
    ts = r.json()
    a = requests.put(f"{BASE}/api/hr/timesheets/{ts['id']}/approve", json={}, headers=admin_h, timeout=20)
    assert a.status_code == 200, a.text[:400]
    assert a.json()["status"] == "approved"
    return a.json()


def _generate(admin_h, period, location_id, use_timesheets=True, days_override=None, pto_override=None):
    body = {"period": period, "location_id": location_id, "use_timesheets": use_timesheets}
    if days_override is not None:
        body["days_worked_override"] = days_override
    if pto_override is not None:
        body["pto_days_override"] = pto_override
    r = requests.post(f"{BASE}/api/hr/payslips/generate", json=body, headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text[:600]
    return r.json()


def _find_payslip_for(gen_resp, staff_id):
    for ps in gen_resp.get("payslips", []):
        if ps.get("staff_id") == staff_id:
            return ps
    return None


class TestPayrollTimesheetProration:
    """Iter215 P2: payslip pro-ration from approved timesheets."""

    def test_use_timesheets_true_prorates(self, admin_h, staff):
        """Approved timesheet with days_worked=15 pro-rates the payslip."""
        period = "2027-03"  # future / clean period
        _submit_and_approve_ts(admin_h, staff["user"]["id"], staff["location_id"], period, days_worked=15, pto_days=2)
        resp = _generate(admin_h, period, staff["location_id"], use_timesheets=True)
        ps = _find_payslip_for(resp, staff["user"]["id"])
        assert ps is not None, f"payslip not generated for our staff: {resp}"
        wd = _working_days(period)
        assert ps["working_days"] == wd
        assert ps["days_worked"] == 15
        assert ps["pto_days"] == 2
        assert ps["gross_salary"] == 100000
        assert ps["net_salary"] < ps["gross_salary"], "should be prorated"
        # Days-worked adjustment line present
        adj = [li for li in ps.get("line_items", []) if li.get("name") == "Days-worked adjustment"]
        assert adj, f"expected Days-worked adjustment line item: {ps.get('line_items')}"
        expected_short = round(100000 * ((wd - 15) / wd), 2)
        assert abs(adj[0]["calculated_amount"] - expected_short) < 1.0

    def test_use_timesheets_false_ignores_timesheet(self, admin_h, staff):
        """With use_timesheets=false the approved timesheet is ignored → full pay."""
        period = "2027-04"
        _submit_and_approve_ts(admin_h, staff["user"]["id"], staff["location_id"], period, days_worked=15, pto_days=2)
        resp = _generate(admin_h, period, staff["location_id"], use_timesheets=False)
        ps = _find_payslip_for(resp, staff["user"]["id"])
        assert ps is not None
        wd = _working_days(period)
        assert ps["days_worked"] == wd, f"expected full month {wd}, got {ps['days_worked']}"
        assert ps["pto_days"] == 0
        assert ps["net_salary"] == ps["gross_salary"] == 100000
        adj = [li for li in ps.get("line_items", []) if li.get("name") == "Days-worked adjustment"]
        assert not adj, "should have no days-worked adjustment when ignoring timesheets"

    def test_days_worked_override_beats_timesheet(self, admin_h, staff):
        """Explicit days_worked_override wins over approved timesheet."""
        period = "2027-05"
        _submit_and_approve_ts(admin_h, staff["user"]["id"], staff["location_id"], period, days_worked=10, pto_days=4)
        override = {staff["user"]["id"]: 20}
        resp = _generate(admin_h, period, staff["location_id"], use_timesheets=True, days_override=override)
        ps = _find_payslip_for(resp, staff["user"]["id"])
        assert ps is not None
        assert ps["days_worked"] == 20, f"override should win: got {ps['days_worked']}"
        # pto_days from timesheet still merged since no pto_override
        assert ps["pto_days"] == 4

    def test_pto_override_wins_over_timesheet(self, admin_h, staff):
        """Explicit pto_days_override wins over approved timesheet's pto_days."""
        period = "2027-06"
        _submit_and_approve_ts(admin_h, staff["user"]["id"], staff["location_id"], period, days_worked=18, pto_days=3)
        pto_override = {staff["user"]["id"]: 7}
        resp = _generate(admin_h, period, staff["location_id"], use_timesheets=True, pto_override=pto_override)
        ps = _find_payslip_for(resp, staff["user"]["id"])
        assert ps is not None
        assert ps["pto_days"] == 7, f"pto override should win: got {ps['pto_days']}"
        # days_worked from timesheet merged since no days override
        assert ps["days_worked"] == 18
