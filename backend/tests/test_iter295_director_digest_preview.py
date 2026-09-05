"""Iter 295 backend tests: GET /api/tasks/director-digest-preview.

Covers:
  * admin gets `{eligible:true, scope:'global', ...}`
  * non-director user gets `{eligible:false, task_count:0, tasks:[]}`
  * campus scope: director user with location_ids=['loc_002'] only sees loc_002 task
  * admin (global) sees BOTH tasks
  * days-late sort: 5d > 3d > 1d in returned rows
  * regression sanity checks (existing endpoints untouched)
"""
import os
import sys
import uuid
import asyncio
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEFAULT_USER_PW = "Test@5812!"

sys.path.insert(0, "/app/backend")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def seeded(event_loop):
    """Seed 1 volunteer user, 1 director user (loc_002), and 3 overdue tasks
    (loc_001@5d, loc_002@3d, loc_001@1d) — 5d and 1d at loc_001, 3d at loc_002.
    Actually we need scope test: 1 task at loc_001 + 1 at loc_002.
    We'll seed 3 overdue tasks total for the days-late sort test:
       t5 loc_001 5d ago
       t3 loc_002 3d ago
       t1 loc_001 1d ago
    Director (loc_002) should see only t3.
    Admin should see all 3, sorted 5→3→1.
    """
    from deps import db  # backend deps

    tag = f"TEST_iter295_{uuid.uuid4().hex[:6]}"
    today = date.today()

    from deps import hash_password

    director_id = f"user_{tag}_dir"
    volunteer_id = f"user_{tag}_vol"

    director = {
        "id": director_id,
        "email": f"{tag}_dir@test.local".lower(),
        "name": f"{tag} Director",
        "role": "director",
        "location_ids": ["loc_002"],
        "active_campus_id": "loc_002",
        "password_hash": hash_password(DEFAULT_USER_PW),
        "status": "active",
    }
    volunteer = {
        "id": volunteer_id,
        "email": f"{tag}_vol@test.local".lower(),
        "name": f"{tag} Volunteer",
        "role": "volunteer",
        "location_ids": ["loc_002"],
        "active_campus_id": "loc_002",
        "password_hash": hash_password(DEFAULT_USER_PW),
        "status": "active",
    }

    task_ids = []

    async def _setup():
        await db.users.insert_one(director)
        await db.users.insert_one(volunteer)
        for days_ago, loc in [(5, "loc_001"), (3, "loc_002"), (1, "loc_001")]:
            tid = f"task_{tag}_{days_ago}d"
            task_ids.append(tid)
            await db.tasks.insert_one({
                "id": tid,
                "title": f"{tag} overdue {days_ago}d",
                "due_date": (today - timedelta(days=days_ago)).isoformat(),
                "status": "todo",
                "is_archived": False,
                "location_id": loc,
                "priority": "high",
                "assignees": [],
            })

    async def _teardown():
        await db.users.delete_many({"id": {"$in": [director_id, volunteer_id]}})
        await db.tasks.delete_many({"id": {"$in": task_ids}})

    event_loop.run_until_complete(_setup())
    yield {
        "tag": tag,
        "director": director,
        "volunteer": volunteer,
        "task_ids": task_ids,
    }
    event_loop.run_until_complete(_teardown())


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": identifier, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {identifier}: {r.status_code} {r.text[:200]}"
    return r.json().get("token") or r.json().get("access_token")


# ---------- endpoint shape ----------
def test_admin_gets_eligible_global(admin_headers):
    r = requests.get(f"{BASE_URL}/api/tasks/director-digest-preview",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["eligible"] is True
    assert data["scope"] == "global"
    assert "task_count" in data
    assert isinstance(data["tasks"], list)
    assert "already_sent_today" in data
    assert "date" in data


def test_non_director_gets_ineligible(seeded):
    tok = _login(seeded["volunteer"]["email"], DEFAULT_USER_PW)
    r = requests.get(f"{BASE_URL}/api/tasks/director-digest-preview",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["eligible"] is False
    assert data["task_count"] == 0
    assert data["tasks"] == []


# ---------- scope test ----------
def test_director_scope_campus_only(seeded):
    tok = _login(seeded["director"]["email"], DEFAULT_USER_PW)
    r = requests.get(f"{BASE_URL}/api/tasks/director-digest-preview",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["eligible"] is True
    assert data["scope"] == "campus"
    seeded_task_ids = set(seeded["task_ids"])
    returned_ids = {t["id"] for t in data["tasks"] if t["id"] in seeded_task_ids}
    # Only the loc_002 (3d) seeded task should appear
    expected_id = f"task_{seeded['tag']}_3d"
    assert expected_id in returned_ids, f"director should see loc_002 task {expected_id}, got {returned_ids}"
    # Should NOT see loc_001 seeded tasks
    forbidden = {f"task_{seeded['tag']}_5d", f"task_{seeded['tag']}_1d"}
    assert not (forbidden & returned_ids), f"director leaked loc_001 tasks: {forbidden & returned_ids}"


def test_admin_global_sees_all_seeded(seeded, admin_headers):
    r = requests.get(f"{BASE_URL}/api/tasks/director-digest-preview",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    ids = {t["id"] for t in data["tasks"]}
    for tid in seeded["task_ids"]:
        assert tid in ids, f"admin/global missing {tid}"


# ---------- days-late sort ----------
def test_days_late_sort(seeded, admin_headers):
    r = requests.get(f"{BASE_URL}/api/tasks/director-digest-preview",
                     headers=admin_headers, timeout=30)
    data = r.json()
    # Extract the seeded tasks in returned order and verify 5d>3d>1d
    seeded_ids = set(seeded["task_ids"])
    order = [t for t in data["tasks"] if t["id"] in seeded_ids]
    days = [t["days_late"] for t in order]
    assert days == sorted(days, reverse=True), f"not sorted desc: {days}"
    # Specifically the 5d task must come before the 3d and 1d ones among seeded
    positions = {t["id"]: i for i, t in enumerate(order)}
    tag = seeded["tag"]
    assert positions[f"task_{tag}_5d"] < positions[f"task_{tag}_3d"] < positions[f"task_{tag}_1d"]


# ---------- regression: untouched endpoints still respond ----------
@pytest.mark.parametrize("path", [
    "/api/tasks",
    "/api/finance/receipts/review-queue",
    "/api/hr/payslips/generate-payday",
    "/api/bank/accounts",
    "/api/finance/journal",
])
def test_regression_endpoints_reachable(admin_headers, path):
    r = requests.get(f"{BASE_URL}{path}", headers=admin_headers, timeout=30)
    # Any non-5xx is acceptable — we just want to confirm no server error was
    # introduced by the new endpoint's router changes.
    assert r.status_code < 500, f"{path}: {r.status_code} {r.text[:200]}"


def test_regression_reports_pdf(admin_headers):
    r = requests.get(f"{BASE_URL}/api/reports/pdf?report=summary",
                     headers=admin_headers, timeout=60)
    assert r.status_code < 500, f"reports/pdf: {r.status_code} {r.text[:200]}"
