"""iter362 — RBAC on new template + PDF + email-run-sheet endpoints."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
LP = f"{API}/lesson-planning"
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"
MEMBER_EMAIL = "member@5812uganda.org"
MEMBER_PASSWORD = "Member@5812"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"identifier": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_hdr():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def member_hdr():
    return _login(MEMBER_EMAIL, MEMBER_PASSWORD)


@pytest.fixture(scope="module")
def volunteer_hdr(admin_hdr):
    """Create a Volunteer user for this run and clean up after."""
    email = f"vol_{uuid.uuid4().hex[:8]}@example.test"
    r = requests.post(f"{API}/admin/users", headers=admin_hdr, timeout=30, json={
        "email": email, "name": "Vol Tester", "role": "Volunteer",
    })
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    hdr = _login(email, "Test@5812!")
    yield hdr
    requests.delete(f"{API}/admin/users/{uid}", headers=admin_hdr, timeout=30)


@pytest.fixture(scope="module")
def a_plan(admin_hdr):
    date = (datetime.now(timezone.utc) + timedelta(days=8)).date().isoformat()
    ev = requests.post(f"{API}/events", headers=admin_hdr, timeout=30, json={
        "title": f"RBAC ev {uuid.uuid4().hex[:5]}", "type": "outreach", "date": date,
        "time": "09:00", "end_time": "11:00", "description": "iter362 rbac",
    }).json()
    plan = requests.post(f"{LP}/plans", headers=admin_hdr, timeout=30, json={"event_id": ev["id"]}).json()
    return plan


def test_templates_list_auth_matrix(admin_hdr, volunteer_hdr, member_hdr):
    assert requests.get(f"{LP}/templates", timeout=30).status_code == 401
    assert requests.get(f"{LP}/templates", headers=member_hdr, timeout=30).status_code == 403
    assert requests.get(f"{LP}/templates", headers=volunteer_hdr, timeout=30).status_code == 200
    assert requests.get(f"{LP}/templates", headers=admin_hdr, timeout=30).status_code == 200


def test_run_sheet_pdf_auth_matrix(admin_hdr, volunteer_hdr, member_hdr, a_plan):
    url = f"{LP}/plans/{a_plan['id']}/run-sheet.pdf"
    assert requests.get(url, timeout=30).status_code == 401
    assert requests.get(url, headers=member_hdr, timeout=30).status_code == 403
    r = requests.get(url, headers=volunteer_hdr, timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_email_run_sheet_auth_matrix(admin_hdr, volunteer_hdr, member_hdr, a_plan):
    url = f"{LP}/plans/{a_plan['id']}/email-run-sheet"
    assert requests.post(url, json={}, timeout=30).status_code == 401
    assert requests.post(url, headers=member_hdr, json={}, timeout=30).status_code == 403
    # volunteer allowed to invoke but plan has no leaders -> 400
    r = requests.post(url, headers=volunteer_hdr, json={}, timeout=30)
    assert r.status_code == 400
    assert "leader" in r.json()["detail"].lower()


def test_volunteer_can_save_template(volunteer_hdr, a_plan):
    name = f"vol tpl {uuid.uuid4().hex[:5]}"
    r = requests.post(f"{LP}/templates", headers=volunteer_hdr, timeout=30,
                      json={"plan_id": a_plan["id"], "name": name})
    assert r.status_code == 200, r.text
    tpl_id = r.json()["id"]
    # cleanup
    requests.delete(f"{LP}/templates/{tpl_id}", headers=volunteer_hdr, timeout=30)
