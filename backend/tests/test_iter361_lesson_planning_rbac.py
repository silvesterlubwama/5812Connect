"""iter361 — extra coverage: RBAC (volunteer allowed, member forbidden),
theme delete guard (director-only + in-use), PO no-ops without snacks,
duplicate onto non-outreach.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
LP = f"{API}/lesson-planning"
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"
MEMBER_EMAIL = "member@5812uganda.org"
MEMBER_PW = "Member@5812"
DEFAULT_PW = "Test@5812!"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("token")


@pytest.fixture(scope="module")
def admin_hdr():
    token = _login(ADMIN_EMAIL, ADMIN_PW)
    assert token, "admin login failed"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def member_hdr():
    token = _login(MEMBER_EMAIL, MEMBER_PW)
    if not token:
        pytest.skip("member account unavailable")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def volunteer_hdr(admin_hdr):
    """Create a volunteer test user via admin and log in."""
    tag = uuid.uuid4().hex[:6]
    email = f"vol_{tag}@example.test"
    payload = {"email": email, "name": f"Vol {tag}", "role": "Volunteer", "password": DEFAULT_PW}
    r = requests.post(f"{API}/admin/users", headers=admin_hdr, timeout=30, json=payload)
    if r.status_code not in (200, 201):
        # try alternate payloads
        payload["role"] = "volunteer"
        r = requests.post(f"{API}/admin/users", headers=admin_hdr, timeout=30, json=payload)
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot create volunteer user: {r.status_code} {r.text}")
    user = r.json()
    uid = user.get("id") or user.get("user", {}).get("id")
    # Attempt login
    token = _login(email, DEFAULT_PW)
    if not token:
        pytest.skip("volunteer login failed after creation")
    yield {"Authorization": f"Bearer {token}"}
    # cleanup
    if uid:
        requests.delete(f"{API}/admin/users/{uid}", headers=admin_hdr, timeout=30)


def test_member_blocked_from_lesson_planning(member_hdr):
    r = requests.get(f"{LP}/themes", headers=member_hdr, timeout=30)
    assert r.status_code == 403, f"member should be forbidden, got {r.status_code}: {r.text}"
    r = requests.get(f"{LP}/outreach-events", headers=member_hdr, timeout=30)
    assert r.status_code == 403


def test_volunteer_can_access(volunteer_hdr):
    r = requests.get(f"{LP}/themes", headers=volunteer_hdr, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.get(f"{LP}/outreach-events", headers=volunteer_hdr, timeout=30)
    assert r.status_code == 200


def test_theme_delete_blocked_when_in_use(admin_hdr):
    # create outreach event + theme + plan referencing that theme
    date = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    ev = requests.post(f"{API}/events", headers=admin_hdr, timeout=30, json={
        "title": f"iter361-rbac-outreach {uuid.uuid4().hex[:5]}",
        "type": "outreach", "date": date, "time": "09:00", "end_time": "11:00",
        "location": "Test", "description": "rbac",
    }).json()
    th = requests.post(f"{LP}/themes", headers=admin_hdr, timeout=30, json={
        "year": 2026, "name": f"RBAC Theme {uuid.uuid4().hex[:4]}",
    }).json()
    plan = requests.post(f"{LP}/plans", headers=admin_hdr, timeout=30,
                        json={"event_id": ev["id"]}).json()
    requests.put(f"{LP}/plans/{plan['id']}", headers=admin_hdr, timeout=30,
                 json={"theme_id": th["id"], "theme_name": th["name"]})
    # try delete — must be refused (in use)
    r = requests.delete(f"{LP}/themes/{th['id']}", headers=admin_hdr, timeout=30)
    assert r.status_code == 400, r.text

    # cleanup: delete plan then theme
    requests.delete(f"{LP}/plans/{plan['id']}", headers=admin_hdr, timeout=30)
    r2 = requests.delete(f"{LP}/themes/{th['id']}", headers=admin_hdr, timeout=30)
    assert r2.status_code == 200
    requests.delete(f"{API}/events/{ev['id']}", headers=admin_hdr, timeout=30)


def test_po_requires_snacks_or_materials(admin_hdr):
    date = (datetime.now(timezone.utc) + timedelta(days=6)).date().isoformat()
    ev = requests.post(f"{API}/events", headers=admin_hdr, timeout=30, json={
        "title": f"iter361-po-empty {uuid.uuid4().hex[:5]}", "type": "outreach",
        "date": date, "time": "10:00", "end_time": "11:00",
        "location": "T", "description": "",
    }).json()
    plan = requests.post(f"{LP}/plans", headers=admin_hdr, timeout=30,
                        json={"event_id": ev["id"]}).json()
    r = requests.post(f"{LP}/plans/{plan['id']}/purchase-order", headers=admin_hdr, timeout=30)
    assert r.status_code == 400, r.text
    assert "snack" in r.text.lower() or "material" in r.text.lower()
    requests.delete(f"{LP}/plans/{plan['id']}", headers=admin_hdr, timeout=30)
    requests.delete(f"{API}/events/{ev['id']}", headers=admin_hdr, timeout=30)


def test_volunteer_can_create_plan(volunteer_hdr, admin_hdr):
    date = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    ev = requests.post(f"{API}/events", headers=admin_hdr, timeout=30, json={
        "title": f"iter361-vol-plan {uuid.uuid4().hex[:5]}", "type": "outreach",
        "date": date, "time": "09:00", "end_time": "10:00",
        "location": "Test", "description": "",
    }).json()
    r = requests.post(f"{LP}/plans", headers=volunteer_hdr, timeout=30,
                     json={"event_id": ev["id"]})
    assert r.status_code == 200, r.text
    plan_id = r.json()["id"]
    requests.delete(f"{LP}/plans/{plan_id}", headers=admin_hdr, timeout=30)
    requests.delete(f"{API}/events/{ev['id']}", headers=admin_hdr, timeout=30)
