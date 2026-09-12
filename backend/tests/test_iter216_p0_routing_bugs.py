"""
iter216 P0 routing/filtering bug fixes verification:
 1. Task assignee directory search returns STAFF_ROLES only
 2. Multi-campus switcher works for non-admin users (get_campus_filter honors active_campus_id)
 3. Chat /users excludes non-active users and non-staff roles
 4. Presence online-users drops entries for non-active DB users
 5. Restricted sub-location data not visible to non-assigned users
 6. Active-campus PUT: 200 when campus_id is in user's locs, 403 otherwise
 7. Admin directory regressions
"""
import os
import uuid
import pytest
import requests
from pathlib import Path

import creds  # env-backed logins, see tests/creds.py

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_base_url()
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD
DEFAULT_PW = creds.NEW_USER_PASSWORD

STAFF_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
               "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"}
NON_STAFF_ROLES = {"Member", "Parent", "Customer", "Guest"}

TAG = f"TEST_iter216_{uuid.uuid4().hex[:6]}"


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def two_campuses(admin_headers):
    """Return two existing campus IDs (parent-type locations)."""
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    locs = r.json()
    campuses = [l for l in locs if not l.get("parent_id")]
    assert len(campuses) >= 2, f"Need >=2 top-level campuses; got {len(campuses)}"
    return campuses[0]["id"], campuses[1]["id"]


@pytest.fixture(scope="module")
def restricted_sublocation(admin_headers, two_campuses):
    """Create a restricted sub-location under the first campus."""
    parent_id, _ = two_campuses
    payload = {
        "name": f"{TAG}_restricted",
        "type": "sub-location",
        "parent_id": parent_id,
        "is_restricted": True,
    }
    r = requests.post(f"{BASE_URL}/api/locations", headers=admin_headers, json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    loc = r.json()
    return loc.get("id") or loc.get("location", {}).get("id"), parent_id


# ---------- helpers ----------

def _login(email, password=DEFAULT_PW):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": email, "password": password}, timeout=15)
    return r


def _create_user(admin_headers, name, email, role, location_ids, extras=None):
    body = {"name": name, "email": email, "role": role,
            "location_ids": location_ids, "location_id": location_ids[0],
            "password": DEFAULT_PW, "status": "active"}
    if extras:
        body.update(extras)
    r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers,
                      json=body, timeout=15)
    assert r.status_code in (200, 201), f"create user {email} -> {r.status_code}: {r.text}"
    return r.json()


# ============================================================
# 1. Admin directory search returns staff roles only
# ============================================================
class TestUserDirectorySearch:
    def test_directory_no_search(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/directory",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list)
        # Every user must be STAFF and active
        for u in users:
            assert u.get("role") in STAFF_ROLES, f"non-staff role in directory: {u}"

    def test_directory_with_search_still_staff_only(self, admin_headers):
        # First create a non-staff (Member) user with a distinctive name
        member_email = f"{TAG}_member@test.local"
        _create_user(admin_headers, f"{TAG}_Member_User", member_email,
                     "Member", ["home"], extras={"also_create_member": False})

        # Search for TAG — should NOT include the Member
        r = requests.get(f"{BASE_URL}/api/admin/users/directory",
                         headers=admin_headers,
                         params={"search": TAG, "include_all": "true"},
                         timeout=15)
        assert r.status_code == 200, r.text
        users = r.json()
        names = [u.get("name") for u in users]
        roles = {u.get("role") for u in users}
        # Every returned user must be staff role
        for u in users:
            assert u.get("role") in STAFF_ROLES, f"non-staff leaked into search: {u}"
        # Member must not appear
        assert not any(u.get("email") == member_email for u in users), \
            f"Member user leaked into directory search: {names}"

    def test_directory_excludes_deleted_users(self, admin_headers, two_campuses):
        c1, _ = two_campuses
        # Create staff user
        email = f"{TAG}_delstaff@test.local"
        u = _create_user(admin_headers, f"{TAG}_DelStaff", email, "Staff", [c1])
        uid = u["id"]
        # Mark as deleted status
        requests.put(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers,
                     json={"status": "deleted"}, timeout=15)
        r = requests.get(f"{BASE_URL}/api/admin/users/directory",
                         headers=admin_headers,
                         params={"search": TAG, "include_all": "true"},
                         timeout=15)
        assert r.status_code == 200
        assert not any(x.get("id") == uid for x in r.json()), \
            "deleted user leaked into directory"


# ============================================================
# 2. Multi-campus switcher for non-admin
# ============================================================
class TestMultiCampusSwitcher:
    def test_multi_campus_user_can_switch_and_filter(self, admin_headers, two_campuses):
        c1, c2 = two_campuses
        email = f"{TAG}_mgr@test.local"
        u = _create_user(admin_headers, f"{TAG}_MultiMgr", email,
                         "Manager", [c1, c2])
        r = _login(email)
        assert r.status_code == 200, r.text
        hdr = {"Authorization": f"Bearer {r.json()['token']}"}

        # Set active_campus to c1
        r = requests.put(f"{BASE_URL}/api/user/active-campus",
                         headers=hdr, json={"campus_id": c1}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("active_campus_id") == c1

        # Switch to c2
        r = requests.put(f"{BASE_URL}/api/user/active-campus",
                         headers=hdr, json={"campus_id": c2}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("active_campus_id") == c2

    def test_switch_to_unassigned_campus_403(self, admin_headers, two_campuses):
        c1, c2 = two_campuses
        email = f"{TAG}_mgr2@test.local"
        _create_user(admin_headers, f"{TAG}_SingleMgr", email, "Manager", [c1])
        r = _login(email)
        hdr = {"Authorization": f"Bearer {r.json()['token']}"}
        r = requests.put(f"{BASE_URL}/api/user/active-campus",
                         headers=hdr, json={"campus_id": c2}, timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_admin_can_switch_to_any_campus(self, admin_headers, two_campuses):
        _, c2 = two_campuses
        r = requests.put(f"{BASE_URL}/api/user/active-campus",
                         headers=admin_headers, json={"campus_id": c2}, timeout=15)
        assert r.status_code == 200, r.text
        # Cleanup
        requests.put(f"{BASE_URL}/api/user/active-campus/clear",
                     headers=admin_headers, timeout=15)


# ============================================================
# 3. Chat users excludes ghost/non-staff
# ============================================================
class TestChatUsers:
    def test_chat_users_are_staff_active(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/chat/users",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        users = r.json()
        allowed = STAFF_ROLES | {"Security Contractor"}
        for u in users:
            assert u.get("role") in allowed, f"non-staff in chat users: {u}"

    def test_chat_excludes_deleted_and_member(self, admin_headers, two_campuses):
        c1, _ = two_campuses
        # Create Member (non-staff)
        m_email = f"{TAG}_chatmember@test.local"
        m = _create_user(admin_headers, f"{TAG}_ChatMember", m_email, "Member", [c1],
                         extras={"also_create_member": False})
        # Create deleted staff
        d_email = f"{TAG}_chatdel@test.local"
        d = _create_user(admin_headers, f"{TAG}_ChatDel", d_email, "Staff", [c1])
        requests.put(f"{BASE_URL}/api/admin/users/{d['id']}", headers=admin_headers,
                     json={"status": "deleted"}, timeout=15)

        r = requests.get(f"{BASE_URL}/api/chat/users",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids = {u["id"] for u in r.json()}
        assert m["id"] not in ids, "Member user in /chat/users"
        assert d["id"] not in ids, "deleted-status user in /chat/users"


# ============================================================
# 4. Presence online-users drops non-active
# ============================================================
class TestPresenceGhosts:
    def test_fake_user_dropped_from_online(self, admin_headers):
        fake_id = f"ghost_{uuid.uuid4().hex[:8]}"
        r = requests.put(f"{BASE_URL}/api/presence/heartbeat",
                         params={"user_id": fake_id}, timeout=15)
        assert r.status_code == 200
        # Mark connected
        requests.put(f"{BASE_URL}/api/presence/connect",
                     params={"user_id": fake_id}, timeout=15)
        r = requests.get(f"{BASE_URL}/api/presence/online-users",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ids = {u["user_id"] for u in r.json()}
        assert fake_id not in ids, "ghost user_id appears in online-users"

    def test_deleted_status_user_dropped(self, admin_headers, two_campuses):
        c1, _ = two_campuses
        email = f"{TAG}_presdel@test.local"
        u = _create_user(admin_headers, f"{TAG}_PresDel", email, "Staff", [c1])
        uid = u["id"]
        # Send heartbeat & connect for this user
        requests.put(f"{BASE_URL}/api/presence/heartbeat",
                     params={"user_id": uid}, timeout=15)
        requests.put(f"{BASE_URL}/api/presence/connect",
                     params={"user_id": uid}, timeout=15)
        # Confirm they're online first
        r = requests.get(f"{BASE_URL}/api/presence/online-users",
                         headers=admin_headers, timeout=15)
        ids = {u["user_id"] for u in r.json()}
        assert uid in ids, "user not appearing as online before deletion"
        # Mark deleted
        requests.put(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers,
                     json={"status": "deleted"}, timeout=15)
        r = requests.get(f"{BASE_URL}/api/presence/online-users",
                         headers=admin_headers, timeout=15)
        ids = {u["user_id"] for u in r.json()}
        assert uid not in ids, "deleted-status user still appears in online-users"


# ============================================================
# 5. Restricted sub-location data leakage
# ============================================================
class TestRestrictedLocations:
    def test_regular_user_cannot_see_restricted_expense(self, admin_headers,
                                                       restricted_sublocation,
                                                       two_campuses):
        restricted_id, parent_id = restricted_sublocation
        # Create a Director in the parent campus (has finance access) but NOT in restricted sub
        email = f"{TAG}_dir@test.local"
        _create_user(admin_headers, f"{TAG}_ParentDir", email, "Director", [parent_id])
        r = _login(email)
        assert r.status_code == 200
        hdr = {"Authorization": f"Bearer {r.json()['token']}"}

        # Admin creates an expense inside the restricted sub-location
        exp_payload = {
            "title": f"{TAG}_restricted_exp",
            "amount": 42.0,
            "location_id": restricted_id,
            "category": "general",
        }
        r = requests.post(f"{BASE_URL}/api/financial/expenses",
                          headers=admin_headers, json=exp_payload, timeout=15)
        assert r.status_code in (200, 201), r.text

        # Director in parent campus fetches expenses — should NOT include the restricted one
        r = requests.get(f"{BASE_URL}/api/financial/expenses",
                         headers=hdr, timeout=15)
        assert r.status_code == 200, r.text
        titles = [e.get("title") for e in r.json()]
        assert f"{TAG}_restricted_exp" not in titles, \
            f"restricted expense leaked to non-assigned Director: {titles}"

    def test_assigned_user_can_see_restricted(self, admin_headers,
                                              restricted_sublocation):
        restricted_id, parent_id = restricted_sublocation
        # Create Director explicitly assigned to the restricted sub
        email = f"{TAG}_resdir@test.local"
        _create_user(admin_headers, f"{TAG}_ResDir", email, "Director",
                     [restricted_id, parent_id])
        r = _login(email)
        hdr = {"Authorization": f"Bearer {r.json()['token']}"}
        r = requests.get(f"{BASE_URL}/api/financial/expenses",
                         headers=hdr, timeout=15)
        assert r.status_code == 200
        titles = [e.get("title") for e in r.json()]
        assert f"{TAG}_restricted_exp" in titles, \
            "assigned user cannot see restricted-loc expense (over-filtering)"


# ============================================================
# 6. Regression: single-campus user without active_campus_id
# ============================================================
class TestSingleCampusRegression:
    def test_single_campus_user_sees_only_their_campus(self, admin_headers, two_campuses):
        c1, c2 = two_campuses
        email = f"{TAG}_singleuser@test.local"
        u = _create_user(admin_headers, f"{TAG}_Single", email, "Director", [c1])
        r = _login(email)
        hdr = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create an expense in c2 (as admin)
        r = requests.post(f"{BASE_URL}/api/financial/expenses",
                          headers=admin_headers,
                          json={"title": f"{TAG}_c2_exp", "amount": 10.0,
                                "location_id": c2, "category": "general"},
                          timeout=15)
        assert r.status_code in (200, 201)

        # User in c1 should NOT see the c2 expense
        r = requests.get(f"{BASE_URL}/api/financial/expenses",
                         headers=hdr, timeout=15)
        assert r.status_code == 200
        titles = [e.get("title") for e in r.json()]
        assert f"{TAG}_c2_exp" not in titles, \
            f"single-campus user sees other campus data: {titles}"
