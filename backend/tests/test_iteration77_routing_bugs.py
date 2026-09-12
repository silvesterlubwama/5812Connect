"""Iteration 77: Test 6 routing/filtering bugs + admin-tier guard.
- Bug 1: /api/admin/users/directory scoping to staff roles + campus
- Bug 2: Restricted sub-location data leak (members/tasks/financial)
- Bug 4: PUT /api/user/active-campus multi-campus switcher
- Bonus: admin-tier role guard on POST/PUT /api/admin/users
"""
import os
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_IDENT = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD
DEFAULT_USER_PASS = creds.NEW_USER_PASSWORD

STAFF_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
               "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"}
NON_STAFF_ROLES = {"Parent", "Customer", "Guest", "Member"}


# ========== Fixtures ==========

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_IDENT, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_user(admin_headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def parent_campus(admin_headers, admin_user):
    """Pick a parent campus location to work with."""
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    locs = r.json()
    # Prefer a campus (type parent/campus/main)
    for loc in locs:
        if loc.get("type") in ("campus", "parent", None) and not loc.get("parent_id"):
            return loc
    # Fallback
    assert locs, "No locations found"
    return locs[0]


# ========== Bug 1: Directory scoping ==========

class TestDirectoryScoping:
    def test_directory_returns_only_staff_roles(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # Admin (campus-scoped by default unless include_all)
        for u in users:
            role = u.get("role", "")
            assert role in STAFF_ROLES, f"Found non-staff role in directory: {role} user={u.get('name')}"
            assert role not in NON_STAFF_ROLES

    def test_directory_include_all_for_sysadmin(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/directory?include_all=true",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # include_all bypasses scoping for system admins (no role restriction)


# ========== Bonus: Admin-tier role guard ==========

class TestAdminTierGuard:
    def test_admin_can_create_admin_role(self, admin_headers):
        email = f"TEST_tieradmin_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                          json={"name": "TEST Tier Admin", "email": email, "role": "admin",
                                "password": DEFAULT_USER_PASS}, timeout=10)
        assert r.status_code in (200, 201), f"Admin create admin-tier failed: {r.status_code} {r.text}"
        uid = r.json().get("id")
        if uid:
            requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers, timeout=10)

    def test_non_admin_cannot_call_create(self):
        """A non-admin should get 403 from /api/admin/users (require_admin guard)."""
        # Create a Manager via admin then try to use its token
        adm = requests.post(f"{BASE_URL}/api/auth/login",
                            json={"identifier": ADMIN_IDENT, "password": ADMIN_PASS}).json()
        headers = {"Authorization": f"Bearer {adm['token']}", "Content-Type": "application/json"}
        email = f"TEST_mgrguard_{uuid.uuid4().hex[:6]}@example.com"
        rc = requests.post(f"{BASE_URL}/api/admin/users", headers=headers,
                           json={"name": "TEST Mgr Guard", "email": email, "role": "Manager",
                                 "password": DEFAULT_USER_PASS}, timeout=10)
        assert rc.status_code in (200, 201), f"Manager create failed: {rc.text}"
        mgr_id = rc.json().get("id")
        # Login as this Manager
        lg = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"identifier": email, "password": DEFAULT_USER_PASS}, timeout=10)
        if lg.status_code != 200:
            pytest.skip(f"Manager login failed {lg.status_code}")
        mgr_headers = {"Authorization": f"Bearer {lg.json()['token']}", "Content-Type": "application/json"}
        # Try to create a user → must be 403
        r = requests.post(f"{BASE_URL}/api/admin/users", headers=mgr_headers,
                          json={"name": "TEST x", "email": f"TEST_x_{uuid.uuid4().hex[:6]}@ex.com",
                                "role": "Staff", "password": DEFAULT_USER_PASS}, timeout=10)
        assert r.status_code == 403, f"Expected 403 for non-admin create, got {r.status_code}"
        # Cleanup
        if mgr_id:
            requests.delete(f"{BASE_URL}/api/admin/users/{mgr_id}", headers=headers, timeout=10)


# ========== Bug 4: Multi-campus switcher ==========

class TestCampusSwitcher:
    def test_missing_campus_id_returns_400(self, admin_headers):
        r = requests.put(f"{BASE_URL}/api/user/active-campus", headers=admin_headers,
                         json={}, timeout=10)
        assert r.status_code == 400

    def test_admin_can_switch_to_any_campus(self, admin_headers, parent_campus):
        r = requests.put(f"{BASE_URL}/api/user/active-campus", headers=admin_headers,
                         json={"campus_id": parent_campus["id"]}, timeout=10)
        assert r.status_code == 200
        assert r.json().get("active_campus_id") == parent_campus["id"]
        requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=admin_headers, timeout=10)

    def test_multi_campus_user_can_switch_within_assigned(self, admin_headers):
        """Create a Manager with 2 campuses, verify can switch, cannot switch to 3rd."""
        # Get at least 2 campuses + 1 extra we won't assign
        r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        campuses = [l for l in r.json() if not l.get("parent_id")]
        if len(campuses) < 2:
            pytest.skip("Need at least 2 parent campuses to test multi-campus switcher")
        c1, c2 = campuses[0]["id"], campuses[1]["id"]
        c3 = campuses[2]["id"] if len(campuses) >= 3 else None

        # Create multi-campus Manager
        email = f"TEST_multi_{uuid.uuid4().hex[:6]}@example.com"
        rc = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                           json={"name": "TEST MultiCampus", "email": email, "role": "Manager",
                                 "location_id": c1, "password": DEFAULT_USER_PASS}, timeout=10)
        assert rc.status_code in (200, 201), f"create multi user failed: {rc.text}"
        uid = rc.json().get("id")
        # Assign multiple campuses via PUT
        ru = requests.put(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers,
                          json={"location_ids": [c1, c2]}, timeout=10)
        assert ru.status_code == 200, f"Assign location_ids failed: {ru.text}"

        try:
            # Login as the multi-campus user
            lg = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"identifier": email, "password": DEFAULT_USER_PASS}, timeout=10)
            assert lg.status_code == 200, f"multi user login failed: {lg.text}"
            hdrs = {"Authorization": f"Bearer {lg.json()['token']}", "Content-Type": "application/json"}

            # Switch to c1 — should succeed
            r1 = requests.put(f"{BASE_URL}/api/user/active-campus", headers=hdrs,
                              json={"campus_id": c1}, timeout=10)
            assert r1.status_code == 200, f"Switch to c1 failed: {r1.status_code} {r1.text}"
            # Switch to c2 — should succeed
            r2 = requests.put(f"{BASE_URL}/api/user/active-campus", headers=hdrs,
                              json={"campus_id": c2}, timeout=10)
            assert r2.status_code == 200, f"Switch to c2 failed: {r2.status_code} {r2.text}"
            # Switch to c3 (not assigned) — should be 403
            if c3:
                r3 = requests.put(f"{BASE_URL}/api/user/active-campus", headers=hdrs,
                                  json={"campus_id": c3}, timeout=10)
                assert r3.status_code == 403, f"Expected 403 for unassigned campus, got {r3.status_code}"
        finally:
            if uid:
                requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers, timeout=10)


# ========== Bug 2: Restricted sub-location leak ==========

class TestRestrictedLocationLeak:
    def test_restricted_sublocation_not_visible_to_unassigned_manager(self, admin_headers, parent_campus):
        """Create restricted sub-location + a member there. Verify unassigned Manager can't see it."""
        campus_id = parent_campus["id"]

        # Create restricted sub-location
        sl_name = f"TEST_RestrictedSL_{uuid.uuid4().hex[:6]}"
        rsl = requests.post(f"{BASE_URL}/api/locations", headers=admin_headers,
                            json={"name": sl_name, "parent_id": campus_id,
                                  "type": "sub-location", "is_restricted": True}, timeout=10)
        assert rsl.status_code in (200, 201), f"Create restricted SL failed: {rsl.text}"
        sl_id = rsl.json().get("id")

        # Create a member in that restricted sub-location
        mem = requests.post(f"{BASE_URL}/api/members", headers=admin_headers,
                            json={"name": f"TEST RestrictedMem_{uuid.uuid4().hex[:6]}",
                                  "location_id": sl_id, "email": f"TEST_rm_{uuid.uuid4().hex[:6]}@ex.com"},
                            timeout=10)
        # Members endpoint signature may vary; accept 200/201
        mem_id = None
        if mem.status_code in (200, 201):
            mem_id = mem.json().get("id")

        # Create Manager NOT assigned to restricted sub-location (only parent campus)
        memail = f"TEST_unassigned_{uuid.uuid4().hex[:6]}@example.com"
        rc = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                           json={"name": "TEST Unassigned Mgr", "email": memail, "role": "Manager",
                                 "location_id": campus_id, "password": DEFAULT_USER_PASS}, timeout=10)
        assert rc.status_code in (200, 201)
        mgr_id = rc.json().get("id")
        # Ensure location_ids is exactly [campus_id] (no restricted SL)
        requests.put(f"{BASE_URL}/api/admin/users/{mgr_id}", headers=admin_headers,
                     json={"location_ids": [campus_id]}, timeout=10)

        try:
            lg = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"identifier": memail, "password": DEFAULT_USER_PASS}, timeout=10)
            assert lg.status_code == 200
            hdrs = {"Authorization": f"Bearer {lg.json()['token']}", "Content-Type": "application/json"}

            # Unassigned Manager GET /api/members → must not include our restricted member
            rm = requests.get(f"{BASE_URL}/api/members", headers=hdrs, timeout=10)
            assert rm.status_code == 200
            if mem_id:
                ids = [m.get("id") for m in rm.json() if isinstance(m, dict)]
                assert mem_id not in ids, f"LEAK: Restricted member {mem_id} visible to unassigned Manager"

            # Also check that locations the user sees don't include the restricted sub-loc data path.
            # Admin should still see it:
            radm = requests.get(f"{BASE_URL}/api/members", headers=admin_headers, timeout=10)
            assert radm.status_code == 200
            # Not asserting admin sees it (campus filtering depends on active_campus); just no crash.
        finally:
            if mgr_id:
                requests.delete(f"{BASE_URL}/api/admin/users/{mgr_id}", headers=admin_headers, timeout=10)
            if mem_id:
                requests.delete(f"{BASE_URL}/api/members/{mem_id}", headers=admin_headers, timeout=10)
            if sl_id:
                requests.delete(f"{BASE_URL}/api/locations/{sl_id}", headers=admin_headers, timeout=10)


# ========== Chat users endpoint scoping (supports Frontend Issue 3) ==========

class TestChatUsers:
    def test_chat_users_scoped_and_active(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/chat/users", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # All returned users should have id & name
        for u in users:
            assert "id" in u and "name" in u
