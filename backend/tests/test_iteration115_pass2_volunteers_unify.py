"""Iteration 115 — Pass 2 features:
 1. Volunteer scheduling auto-populate from public events
    - GET /api/volunteer/role-defaults (with & without event_type)
    - POST /api/volunteer/shifts/generate-from-event (happy, idempotent, replace, errors)
 2. Migration of Guests + Parents → unified `members` collection (kind=guest|parent)
    - /api/admin/migrate/guests-to-members/preview + /run idempotency
    - /api/members?kind=guest|parent listing
    - Dual-write on POST/PUT/DELETE /api/guests
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = (os.environ.get("TEST_API_URL") or os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")).rstrip("/")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _members(token, kind):
    """Wrapper around GET /api/members that returns the inner list regardless
    of whether the endpoint envelopes the response as {members,total} or returns
    a bare list."""
    r = requests.get(f"{BASE_URL}/api/members",
                     headers=_hdr(token), params={"kind": kind}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    if isinstance(body, dict) and "members" in body:
        return body["members"]
    return body


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def primary_location(token):
    r = requests.get(f"{BASE_URL}/api/locations", headers=_hdr(token), timeout=10)
    assert r.status_code == 200
    locs = r.json()
    assert locs, "no locations"
    return locs[0]["id"]


# ----------------------------------------------------------------------------
# 1. VOLUNTEER ROLE DEFAULTS
# ----------------------------------------------------------------------------
class TestRoleDefaults:
    def test_role_defaults_without_event_type(self, token):
        r = requests.get(f"{BASE_URL}/api/volunteer/role-defaults",
                         headers=_hdr(token), timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("roles"), list) and len(body["roles"]) > 0
        # Generic fallback should include Greeter & Usher
        names = {x["role"] for x in body["roles"]}
        assert "Greeter" in names and "Usher" in names
        assert isinstance(body.get("all_role_options"), list)
        assert "Children Ministry" in body["all_role_options"]

    def test_role_defaults_with_known_event_type(self, token):
        # try a known type from the map — service/worship are common
        for et in ("service", "worship", "kids", "outreach", "conference"):
            r = requests.get(f"{BASE_URL}/api/volunteer/role-defaults",
                             headers=_hdr(token), params={"event_type": et}, timeout=10)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["event_type"] == et
            assert isinstance(body["roles"], list) and len(body["roles"]) > 0
            for it in body["roles"]:
                assert "role" in it and "slots" in it
                assert isinstance(it["slots"], int) and it["slots"] >= 1


# ----------------------------------------------------------------------------
# 2. GENERATE SHIFTS FROM EVENT
# ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def temp_event(token, primary_location):
    """Create a small event we can attach shifts to, then nuke it."""
    future = (date.today() + timedelta(days=14)).isoformat()
    payload = {
        "title": f"CI-PASS2-EVT-{uuid.uuid4().hex[:6]}",
        "type": "service",
        "date": future,
        "time": "09:00",
        "end_time": "11:00",
        "location_id": primary_location,
        "description": "ci pass2 event",
        "is_public": True,
    }
    r = requests.post(f"{BASE_URL}/api/events", headers=_hdr(token), json=payload, timeout=10)
    assert r.status_code == 200, r.text
    ev = r.json()
    yield ev
    # cleanup any shifts spawned for this event + the event itself
    try:
        shifts = requests.get(f"{BASE_URL}/api/volunteer/shifts",
                              headers=_hdr(token), timeout=10).json()
        for s in shifts:
            if s.get("event_id") == ev["id"]:
                requests.delete(f"{BASE_URL}/api/volunteer/shifts/{s['id']}",
                                headers=_hdr(token), timeout=10)
    except Exception:
        pass
    try:
        requests.delete(f"{BASE_URL}/api/events/{ev['id']}", headers=_hdr(token), timeout=10)
    except Exception:
        pass


class TestGenerateFromEvent:
    def test_missing_event_id_returns_400(self, token):
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"roles": [{"role": "Greeter", "slots": 2}]}, timeout=10)
        assert r.status_code == 400

    def test_unknown_event_id_returns_404(self, token):
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"event_id": "non-existent-xxx",
                                "roles": [{"role": "Greeter", "slots": 2}]},
                          timeout=10)
        assert r.status_code == 404

    def test_happy_path_creates_shifts(self, token, temp_event):
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"event_id": temp_event["id"],
                                "roles": [
                                    {"role": "Greeter", "slots": 2},
                                    {"role": "Usher", "slots": 4},
                                ]},
                          timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_created"] == 2
        assert body["total_skipped"] == 0
        assert body["event_id"] == temp_event["id"]
        # each created shift must inherit date / start_time from the event
        for s in body["created"]:
            assert s["date"] == temp_event["date"]
            assert s["start_time"] == temp_event.get("time", "09:00")
            assert s["auto_generated_from_event"] is True
            assert s["location_id"] == temp_event.get("location_id")

    def test_idempotent_rerun_skips_duplicates(self, token, temp_event):
        # rerunning same roles must skip (no duplicates)
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"event_id": temp_event["id"],
                                "roles": [
                                    {"role": "Greeter", "slots": 2},
                                    {"role": "Usher", "slots": 4},
                                ]},
                          timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_created"] == 0
        assert body["total_skipped"] == 2
        assert body["total_updated"] == 0

    def test_replace_true_updates_existing(self, token, temp_event):
        # change slot counts using replace=True
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"event_id": temp_event["id"],
                                "replace": True,
                                "roles": [{"role": "Greeter", "slots": 7,
                                           "start_time": "08:30", "end_time": "10:30"}]},
                          timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_updated"] == 1
        upd = body["updated"][0]
        assert upd["slots"] == 7
        assert upd["start_time"] == "08:30"
        assert upd["end_time"] == "10:30"

    def test_empty_roles_returns_400(self, token, temp_event):
        r = requests.post(f"{BASE_URL}/api/volunteer/shifts/generate-from-event",
                          headers=_hdr(token),
                          json={"event_id": temp_event["id"], "roles": []}, timeout=10)
        assert r.status_code == 400


# ----------------------------------------------------------------------------
# 3. GUESTS → MEMBERS MIGRATION
# ----------------------------------------------------------------------------
class TestGuestMigration:
    def test_preview_endpoint_shape(self, token):
        r = requests.get(f"{BASE_URL}/api/admin/migrate/guests-to-members/preview",
                         headers=_hdr(token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("total_guests", "already_mirrored_in_members", "pending_to_migrate"):
            assert k in body
            assert isinstance(body[k], int)
        assert body["total_guests"] >= 0

    def test_run_then_rerun_is_idempotent(self, token):
        r1 = requests.post(f"{BASE_URL}/api/admin/migrate/guests-to-members/run",
                           headers=_hdr(token), json={}, timeout=30)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert "migrated" in b1 and "errors" in b1
        assert b1["errors"] == 0

        # 2nd run — must NOT produce duplicates. After run #1 every guest is
        # already mirrored, so subsequent runs upsert in place (no new rows).
        r2 = requests.post(f"{BASE_URL}/api/admin/migrate/guests-to-members/run",
                           headers=_hdr(token), json={}, timeout=30)
        assert r2.status_code == 200, r2.text

        # Verify by checking preview after second run: pending_to_migrate == 0
        prev = requests.get(f"{BASE_URL}/api/admin/migrate/guests-to-members/preview",
                            headers=_hdr(token), timeout=15).json()
        assert prev["pending_to_migrate"] == 0, (
            f"expected 0 pending after run, got {prev['pending_to_migrate']}"
        )


class TestMembersKindFilter:
    def test_kind_guest_returns_guest_mirrors(self, token):
        members = _members(token, "guest")
        assert isinstance(members, list)
        for m in members:
            assert m.get("kind") == "guest", f"expected kind=guest, got {m.get('kind')} on {m.get('id')}"

    def test_kind_parent_returns_parent_mirrors(self, token):
        members = _members(token, "parent")
        assert isinstance(members, list)
        for m in members:
            assert m.get("kind") == "parent"


# ----------------------------------------------------------------------------
# 4. GUEST DUAL-WRITE (create / update / delete)
# ----------------------------------------------------------------------------
class TestGuestDualWrite:
    @pytest.fixture
    def guest_id(self, token, primary_location):
        """Create a single throwaway guest, yield its id, then delete it."""
        name = f"CI-DUAL-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/guests", headers=_hdr(token),
                          json={"name": name, "email": f"{name.lower()}@ci.test",
                                "phone": "+256700000000",
                                "location_id": primary_location}, timeout=10)
        assert r.status_code == 200, r.text
        gid = r.json()["id"]
        yield gid, name
        # best-effort cleanup (test_delete will already wipe)
        requests.delete(f"{BASE_URL}/api/guests/{gid}", headers=_hdr(token), timeout=10)

    def test_create_guest_mirrors_to_members(self, token, guest_id):
        gid, _name = guest_id
        ids = {m["id"] for m in _members(token, "guest")}
        assert gid in ids, f"new guest {gid} did not appear in members?kind=guest"

    def test_update_guest_updates_mirror(self, token, guest_id, primary_location):
        gid, name = guest_id
        # Update phone + name on the guest
        new_name = f"{name}-UPD"
        r = requests.put(f"{BASE_URL}/api/guests/{gid}", headers=_hdr(token),
                         json={"name": new_name, "email": f"{name.lower()}@ci.test",
                               "phone": "+256711111111",
                               "location_id": primary_location}, timeout=10)
        assert r.status_code == 200, r.text
        # Verify mirror is updated
        match = next((m for m in _members(token, "guest") if m["id"] == gid), None)
        assert match is not None, "mirror row missing after update"
        assert match.get("name") == new_name, (
            f"mirror name not updated: expected {new_name}, got {match.get('name')}"
        )
        assert match.get("phone") == "+256711111111"

    def test_delete_guest_removes_mirror(self, token, primary_location):
        # Independent guest so the fixture teardown doesn't double-delete
        name = f"CI-DEL-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/guests", headers=_hdr(token),
                          json={"name": name, "email": f"{name.lower()}@ci.test",
                                "location_id": primary_location}, timeout=10)
        assert r.status_code == 200
        gid = r.json()["id"]

        # Mirror must exist first
        m1 = _members(token, "guest")
        assert any(m["id"] == gid for m in m1)

        # Delete
        d = requests.delete(f"{BASE_URL}/api/guests/{gid}", headers=_hdr(token), timeout=10)
        assert d.status_code == 200

        # Mirror must be gone
        m2 = _members(token, "guest")
        assert all(m["id"] != gid for m in m2), (
            f"mirror row {gid} should have been removed after guest delete"
        )
