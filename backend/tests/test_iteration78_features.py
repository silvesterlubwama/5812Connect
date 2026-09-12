"""Iteration 78 — payday payslip endpoint + multi-campus user creation"""
import os
import requests
import pytest
from datetime import datetime, timezone

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN = {"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def first_campus(headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=headers, timeout=30)
    assert r.status_code == 200
    locs = r.json()
    assert len(locs) >= 1
    return locs[0]["id"]


# ---------- HR PAYDAY ENDPOINT ----------
class TestHRPayday:
    def test_payday_endpoint_no_match(self, headers):
        # When no campus has pay_day matching today, it should return generated:0 with message
        r = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday", headers=headers, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert "generated" in data
        assert "period" in data
        # period must be YYYY-MM
        today = datetime.now(timezone.utc)
        expected_period = f"{today.year:04d}-{today.month:02d}"
        assert data["period"] == expected_period

    def test_payday_endpoint_with_match_idempotent(self, headers, first_campus):
        today = datetime.now(timezone.utc)
        # 1) Configure HR settings on first campus with pay_day = today.day
        sett_r = requests.put(
            f"{BASE_URL}/api/hr/settings/{first_campus}",
            headers=headers,
            json={"hr_enabled": True, "pay_day": today.day, "currency": "UGX", "pay_frequency": "monthly"},
            timeout=30,
        )
        assert sett_r.status_code == 200, f"{sett_r.status_code} {sett_r.text}"

        # 2) Find an admin/staff user to attach a salary to (use admin user)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=30).json()
        admin_user_id = me["id"]

        # 3) Create a salary
        sal_r = requests.post(
            f"{BASE_URL}/api/hr/salaries",
            headers=headers,
            json={
                "staff_id": admin_user_id,
                "base_salary": 1000000,
                "currency": "UGX",
                "location_id": first_campus,
                "pay_frequency": "monthly",
            },
            timeout=30,
        )
        assert sal_r.status_code == 200, f"{sal_r.status_code} {sal_r.text}"
        sal_id = sal_r.json()["id"]

        try:
            # 4) Trigger payday
            r1 = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday", headers=headers, timeout=30)
            assert r1.status_code == 200
            d1 = r1.json()
            assert d1["generated"] >= 1, f"Expected >=1 generated, got {d1}"
            assert d1.get("day_of_month") == today.day
            assert first_campus in (d1.get("campuses_matched") or [])

            # 5) Idempotent — second call should generate 0 new
            r2 = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday", headers=headers, timeout=30)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["generated"] == 0, f"Expected 0 on second call, got {d2}"

            # Cleanup payslips for this period & salary
            ps_list = requests.get(
                f"{BASE_URL}/api/hr/payslips",
                headers=headers,
                params={"period": d1["period"]},
                timeout=30,
            ).json()
            for ps in ps_list:
                if ps.get("salary_id") == sal_id:
                    # No DELETE endpoint for payslip — leave; test_payday_endpoint_no_match teardown handled
                    pass
        finally:
            # Clean up: delete the test salary
            requests.delete(f"{BASE_URL}/api/hr/salaries/{sal_id}", headers=headers, timeout=30)
            # Reset pay_day to a safe value (e.g., 28)
            requests.put(
                f"{BASE_URL}/api/hr/settings/{first_campus}",
                headers=headers,
                json={"hr_enabled": True, "pay_day": 28},
                timeout=30,
            )


# ---------- MULTI-CAMPUS USER CREATION ----------
class TestMultiCampusUserCreate:
    def test_create_user_with_location_ids(self, headers):
        # Get 2 campuses
        locs = requests.get(f"{BASE_URL}/api/locations", headers=headers, timeout=30).json()
        if len(locs) < 2:
            pytest.skip("Need at least 2 campuses")
        loc_a, loc_b = locs[0]["id"], locs[1]["id"]

        email = f"TEST_multicampus_{datetime.now().timestamp():.0f}@example.com"
        payload = {
            "name": "TEST Multi Campus User",
            "email": email,
            "role": "Staff",
            "location_id": loc_a,
            "location_ids": [loc_a, loc_b],
        }
        r = requests.post(f"{BASE_URL}/api/admin/users", headers=headers, json=payload, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        created = r.json()
        user_id = created["id"]
        try:
            assert created.get("location_id") == loc_a
            lids = created.get("location_ids") or []
            assert loc_a in lids and loc_b in lids, f"location_ids missing campuses: {lids}"

            # Verify GET
            g = requests.get(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers, timeout=30)
            assert g.status_code == 200
            gd = g.json()
            gids = gd.get("location_ids") or []
            assert loc_a in gids and loc_b in gids

            # Verify member record was created with same location_ids (search members)
            ms = requests.get(f"{BASE_URL}/api/members", headers=headers, params={"search": email}, timeout=30)
            assert ms.status_code == 200
            members = ms.json() if isinstance(ms.json(), list) else ms.json().get("items", [])
            mem = next((m for m in members if m.get("email") == email), None)
            if mem:
                mids = mem.get("location_ids") or []
                assert loc_a in mids and loc_b in mids
        finally:
            requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers, timeout=30)


# ---------- ITER-77 REGRESSION ----------
class TestIter77Regression:
    def test_directory_staff_only(self, headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=headers, timeout=30)
        assert r.status_code == 200
        users = r.json()
        STAFF = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
                 "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"}
        for u in users:
            assert u.get("role") in STAFF, f"Non-staff role leaked: {u.get('role')}"

    def test_active_campus_missing_id(self, headers):
        r = requests.put(f"{BASE_URL}/api/user/active-campus", headers=headers, json={}, timeout=30)
        assert r.status_code == 400
