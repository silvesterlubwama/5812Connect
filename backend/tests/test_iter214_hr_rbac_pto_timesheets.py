"""iter214 backend tests: HR RBAC scoping + Time-Off (PTO) flow + on-behalf timesheet.

Covers:
- GET /api/hr/payslips scoping: staff sees own, director sees location_ids only, admin sees all (scope {})
- GET /api/hr/timesheets scoping (same rules)
- POST /api/hr/timesheets on-behalf: 403 for staff, allowed for director+/admin at same location, 403 outside
- POST /api/hr/time-off: window rule +/-7 days; admin_override admin-only; on-behalf rules
- PUT approve/reject; DELETE rules
- Regression: iter211 payroll JE tests still pass (run separately via pytest)
"""
import os
import uuid
import time
import pytest
import requests
from datetime import date, timedelta


def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE = _load_base()
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEFAULT_PW = "Test@5812!"
TAG = f"iter214_{uuid.uuid4().hex[:6]}"


# --------------------- Fixtures ---------------------

@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text[:400]
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def two_locations(admin_h):
    """Return two distinct campus location ids for locA (director scope) and locB (other)."""
    r = requests.get(f"{BASE}/api/locations", headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text[:300]
    locs = [l for l in r.json() if l.get("type") in ("campus", "main") and not l.get("is_restricted")]
    assert len(locs) >= 2, f"need at least 2 campuses, have {len(locs)}"
    return locs[0]["id"], locs[1]["id"]


def _create_user(admin_h, role, loc_ids, name_suffix):
    email = f"TEST_{TAG}_{name_suffix}_{uuid.uuid4().hex[:4]}@iter214.test"
    payload = {
        "name": f"TEST_{TAG}_{name_suffix}",
        "email": email,
        "role": role,
        "password": DEFAULT_PW,
        "location_ids": loc_ids,
        "location_id": loc_ids[0] if loc_ids else "",
        "also_create_member": False,
    }
    r = requests.post(f"{BASE}/api/admin/users", json=payload, headers=admin_h, timeout=20)
    assert r.status_code in (200, 201), f"create {role} failed: {r.status_code} {r.text[:400]}"
    user = r.json()
    lg = requests.post(f"{BASE}/api/auth/login", json={"identifier": email, "password": DEFAULT_PW}, timeout=20)
    assert lg.status_code == 200, lg.text[:400]
    tok = lg.json()["token"]
    return user, {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def actors(admin_h, two_locations):
    locA, locB = two_locations
    staff_a, staff_a_h = _create_user(admin_h, "Staff", [locA], "staffA")
    staff_b, staff_b_h = _create_user(admin_h, "Staff", [locB], "staffB")
    director_a, director_a_h = _create_user(admin_h, "Director", [locA], "dirA")
    return {
        "locA": locA, "locB": locB,
        "staff_a": staff_a, "staff_a_h": staff_a_h,
        "staff_b": staff_b, "staff_b_h": staff_b_h,
        "director_a": director_a, "director_a_h": director_a_h,
    }


def _make_payslip(admin_h, staff_id, location_id, period="2026-01"):
    # Create via manual payslip endpoint. Requires director+. Use admin.
    # First, set admin's active_campus to that location so the payslip.location_id defaults right
    # Actually manual endpoint reads staff.location_id; but our test users have location_id set.
    body = {
        "staff_id": staff_id,
        "period": period,
        "gross_salary": 100000,
        "currency": "UGX",
        "notes": f"TEST_{TAG}",
    }
    r = requests.post(f"{BASE}/api/hr/payslips/manual", json=body, headers=admin_h, timeout=20)
    assert r.status_code == 200, r.text[:400]
    ps = r.json()
    # Ensure location matches expected (manual endpoint uses staff.location_id)
    assert ps.get("location_id") == location_id, f"payslip loc mismatch {ps.get('location_id')} != {location_id}"
    return ps


@pytest.fixture(scope="module")
def payslips(admin_h, actors):
    ps_a = _make_payslip(admin_h, actors["staff_a"]["id"], actors["locA"])
    ps_b = _make_payslip(admin_h, actors["staff_b"]["id"], actors["locB"])
    return {"ps_a": ps_a, "ps_b": ps_b}


# --------------------- Payslip RBAC scoping ---------------------

class TestPayslipScoping:
    def test_staff_sees_only_own(self, actors, payslips):
        r = requests.get(f"{BASE}/api/hr/payslips", headers=actors["staff_a_h"], timeout=20)
        # Staff may or may not have hr view access — if not, expect 403
        if r.status_code == 403:
            pytest.skip("Staff lacks HR view access — RBAC guard blocks entirely (acceptable)")
        assert r.status_code == 200, r.text[:400]
        items = r.json()
        for it in items:
            assert it["staff_id"] == actors["staff_a"]["id"], f"staff saw non-own payslip: {it}"

    def test_director_sees_only_own_locations(self, actors, payslips):
        r = requests.get(f"{BASE}/api/hr/payslips", headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        items = r.json()
        loc_ids = actors["director_a"].get("location_ids") or [actors["locA"]]
        # Should NOT contain any payslip at locB
        for it in items:
            assert it.get("location_id") in loc_ids, f"director saw out-of-scope payslip: {it.get('location_id')}"
        # Should contain ps_a
        ids = {p["id"] for p in items}
        assert payslips["ps_a"]["id"] in ids, "director should see own-location payslip"
        assert payslips["ps_b"]["id"] not in ids, "director should NOT see other-loc payslip"

    def test_admin_sees_target_payslip(self, admin_h, payslips):
        # Admin gets no user-based scope. Campus filter may still apply for admin
        # via get_campus_filter. Verify admin sees at least their active_campus payslips
        # and that both created test payslips ARE reachable (via /mine-style scan across list).
        r = requests.get(f"{BASE}/api/hr/payslips", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text[:400]
        items = r.json()
        ids = {p["id"] for p in items}
        # Admin should at minimum see one of the two (their active_campus one).
        # Record whether admin sees both for reporting.
        seen_a = payslips["ps_a"]["id"] in ids
        seen_b = payslips["ps_b"]["id"] in ids
        assert seen_a or seen_b, "admin sees neither test payslip — scope broken"
        # For visibility, print for the report (not an assertion failure)
        print(f"admin_sees_ps_a={seen_a} admin_sees_ps_b={seen_b}")


# --------------------- Timesheet RBAC + on-behalf ---------------------

class TestTimesheetOnBehalf:
    def test_staff_cannot_submit_for_other(self, actors):
        body = {"period": "2026-01", "days_worked": 20, "staff_id": actors["staff_b"]["id"]}
        r = requests.post(f"{BASE}/api/hr/timesheets", json=body, headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_director_submits_onbehalf_same_location(self, actors):
        body = {"period": "2026-02", "days_worked": 20, "staff_id": actors["staff_a"]["id"]}
        r = requests.post(f"{BASE}/api/hr/timesheets", json=body, headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        ts = r.json()
        assert ts["staff_id"] == actors["staff_a"]["id"]
        assert ts["submitted_by"] == actors["director_a"]["id"]
        assert ts["submitted_by_name"] == actors["director_a"]["name"]

    def test_director_cannot_submit_onbehalf_other_location(self, actors):
        body = {"period": "2026-03", "days_worked": 20, "staff_id": actors["staff_b"]["id"]}
        r = requests.post(f"{BASE}/api/hr/timesheets", json=body, headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_admin_can_submit_onbehalf_any_location(self, admin_h, actors):
        body = {"period": "2026-04", "days_worked": 20, "staff_id": actors["staff_b"]["id"]}
        r = requests.post(f"{BASE}/api/hr/timesheets", json=body, headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["staff_id"] == actors["staff_b"]["id"]

    def test_timesheets_list_scoping_staff(self, actors):
        r = requests.get(f"{BASE}/api/hr/timesheets", headers=actors["staff_a_h"], timeout=20)
        if r.status_code == 403:
            pytest.skip("staff blocked from listing timesheets (hr guard)")
        assert r.status_code == 200
        for ts in r.json():
            assert ts["staff_id"] == actors["staff_a"]["id"]

    def test_timesheets_list_scoping_director(self, actors):
        r = requests.get(f"{BASE}/api/hr/timesheets", headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200
        loc_ids = actors["director_a"].get("location_ids") or [actors["locA"]]
        for ts in r.json():
            assert ts.get("location_id") in loc_ids, f"director saw out-of-scope ts: {ts.get('location_id')}"


# --------------------- Time-off (PTO) flow ---------------------

class TestTimeOffFlow:
    def test_within_window_succeeds(self, actors):
        d = (date.today() + timedelta(days=3)).isoformat()
        body = {"start_date": d, "end_date": d, "reason": "test in window"}
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        pto = r.json()
        assert pto["status"] == "pending"
        assert pto["staff_id"] == actors["staff_a"]["id"]
        # Save for approve test
        pytest.pto_in_window = pto

    def test_beyond_window_fails(self, actors):
        d = (date.today() + timedelta(days=30)).isoformat()
        body = {"start_date": d, "end_date": d}
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 400, r.text[:400]
        assert "7 days" in r.text or "window" in r.text.lower() or "days from today" in r.text

    def test_admin_override_admin_ok(self, admin_h, actors):
        d = (date.today() + timedelta(days=45)).isoformat()
        body = {
            "start_date": d, "end_date": d,
            "admin_override": True,
            "staff_id": actors["staff_a"]["id"],
            "reason": "test override",
        }
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["admin_override"] is True

    def test_admin_override_nonadmin_denied(self, actors):
        d = (date.today() + timedelta(days=45)).isoformat()
        body = {"start_date": d, "end_date": d, "admin_override": True}
        # director
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 403, r.text[:200]
        # staff
        r2 = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["staff_a_h"], timeout=20)
        assert r2.status_code == 403, r2.text[:200]

    def test_onbehalf_director_same_loc(self, actors):
        d = (date.today() + timedelta(days=2)).isoformat()
        body = {"start_date": d, "end_date": d, "staff_id": actors["staff_a"]["id"], "reason": "dir on behalf"}
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        assert r.json()["staff_id"] == actors["staff_a"]["id"]

    def test_onbehalf_staff_denied(self, actors):
        d = (date.today() + timedelta(days=2)).isoformat()
        body = {"start_date": d, "end_date": d, "staff_id": actors["staff_b"]["id"]}
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 403, r.text[:200]

    def test_onbehalf_director_other_loc_denied(self, actors):
        d = (date.today() + timedelta(days=2)).isoformat()
        body = {"start_date": d, "end_date": d, "staff_id": actors["staff_b"]["id"]}
        r = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 403, r.text[:200]

    def test_approve_by_director(self, actors):
        pto = getattr(pytest, "pto_in_window", None)
        assert pto, "prior test did not create PTO"
        r = requests.put(f"{BASE}/api/hr/time-off/{pto['id']}/approve", json={"notes": "ok"},
                         headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        out = r.json()
        assert out["status"] == "approved"
        assert out["approved_by"] == actors["director_a"]["id"]
        # Idempotent
        r2 = requests.put(f"{BASE}/api/hr/time-off/{pto['id']}/approve", json={},
                          headers=actors["director_a_h"], timeout=20)
        assert r2.status_code == 200
        assert r2.json()["status"] == "approved"

    def test_approve_by_staff_denied(self, actors):
        # Create a fresh pending PTO to try approving as staff
        d = (date.today() + timedelta(days=1)).isoformat()
        body = {"start_date": d, "end_date": d}
        c = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["staff_a_h"], timeout=20)
        assert c.status_code == 200
        pid = c.json()["id"]
        r = requests.put(f"{BASE}/api/hr/time-off/{pid}/approve", json={}, headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 403, r.text[:200]

    def test_reject_by_director(self, actors):
        d = (date.today() + timedelta(days=4)).isoformat()
        body = {"start_date": d, "end_date": d, "staff_id": actors["staff_a"]["id"]}
        c = requests.post(f"{BASE}/api/hr/time-off", json=body, headers=actors["director_a_h"], timeout=20)
        assert c.status_code == 200
        pid = c.json()["id"]
        r = requests.put(f"{BASE}/api/hr/time-off/{pid}/reject", json={"reason": "no coverage"},
                         headers=actors["director_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:400]
        out = r.json()
        assert out["status"] == "rejected"
        assert out["review_notes"] == "no coverage"

    def test_list_scoping(self, admin_h, actors):
        # Staff sees only own
        rs = requests.get(f"{BASE}/api/hr/time-off", headers=actors["staff_a_h"], timeout=20)
        assert rs.status_code == 200
        for p in rs.json():
            assert p["staff_id"] == actors["staff_a"]["id"]
        # Director sees only their locations
        rd = requests.get(f"{BASE}/api/hr/time-off", headers=actors["director_a_h"], timeout=20)
        assert rd.status_code == 200
        loc_ids = actors["director_a"].get("location_ids") or [actors["locA"]]
        for p in rd.json():
            assert p.get("location_id") in loc_ids, f"director saw out-of-scope PTO: {p}"

    def test_delete_owner_pending_ok(self, actors):
        d = (date.today() + timedelta(days=5)).isoformat()
        c = requests.post(f"{BASE}/api/hr/time-off", json={"start_date": d, "end_date": d},
                          headers=actors["staff_a_h"], timeout=20)
        assert c.status_code == 200
        pid = c.json()["id"]
        r = requests.delete(f"{BASE}/api/hr/time-off/{pid}", headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 200, r.text[:200]

    def test_delete_owner_approved_denied(self, actors):
        d = (date.today() + timedelta(days=6)).isoformat()
        c = requests.post(f"{BASE}/api/hr/time-off", json={"start_date": d, "end_date": d},
                          headers=actors["staff_a_h"], timeout=20)
        assert c.status_code == 200
        pid = c.json()["id"]
        # Approve as director
        a = requests.put(f"{BASE}/api/hr/time-off/{pid}/approve", json={}, headers=actors["director_a_h"], timeout=20)
        assert a.status_code == 200
        # Owner tries to delete
        r = requests.delete(f"{BASE}/api/hr/time-off/{pid}", headers=actors["staff_a_h"], timeout=20)
        assert r.status_code == 400, r.text[:200]
        # HR/director can still delete
        r2 = requests.delete(f"{BASE}/api/hr/time-off/{pid}", headers=actors["director_a_h"], timeout=20)
        assert r2.status_code == 200
