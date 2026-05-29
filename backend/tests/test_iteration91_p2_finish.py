"""P2 finish tests (iter 132–134): router-gating, task snooze, expiring-soon banner."""
import os
import uuid
import requests
import pytest
from datetime import datetime, timezone

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.strip().split("=", 1)[1]
                        break
        except Exception:
            pass
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return v.rstrip("/")


BASE_URL = _load_base_url()
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
DEFAULT_NEW_PASS = "Test@5812!"


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": identifier, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {identifier}: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def staff_user(admin_token):
    """Create a fresh non-privileged Staff user for module-gate tests."""
    h = {"Authorization": f"Bearer {admin_token}"}
    email = f"TEST_staff_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/admin/users",
                      headers=h,
                      json={"name": "TEST P2 Staff", "email": email, "role": "Staff",
                            "password": DEFAULT_NEW_PASS, "also_create_member": False},
                      timeout=30)
    assert r.status_code in (200, 201), f"create user failed: {r.status_code} {r.text}"
    user = r.json()
    yield {"id": user["id"], "email": email, "token": _login(email, DEFAULT_NEW_PASS)}
    # Cleanup
    try:
        requests.delete(f"{BASE_URL}/api/admin/users/{user['id']}", headers=h, timeout=30)
    except Exception:
        pass


# ============== Router-level gating ==============

def test_social_work_blocked_for_staff(staff_user):
    h = {"Authorization": f"Bearer {staff_user['token']}"}
    r = requests.get(f"{BASE_URL}/api/social-work/cases", headers=h, timeout=30)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"
    detail = (r.json().get("detail") or "")
    assert "Social Work" in detail or "social" in detail.lower(), f"detail missing: {detail}"


def test_social_work_allowed_for_admin(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/social-work/cases", headers=h, timeout=30)
    assert r.status_code == 200, f"Admin should access social work: {r.status_code} {r.text[:200]}"
    assert isinstance(r.json(), (list, dict))


def test_products_blocked_for_staff(staff_user):
    h = {"Authorization": f"Bearer {staff_user['token']}"}
    r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=30)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"


def test_products_allowed_for_admin(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/products", headers=h, timeout=30)
    assert r.status_code == 200, f"Admin should access products: {r.status_code} {r.text[:200]}"


def test_social_work_unlocked_after_grant(staff_user, admin_token):
    """After admin grants social_work module, staff can list cases."""
    h_admin = {"Authorization": f"Bearer {admin_token}"}
    r = requests.put(f"{BASE_URL}/api/admin/module-access/users/{staff_user['id']}",
                     headers=h_admin,
                     json={"module": "social_work", "granted": True, "ttl_days": 5,
                           "reason": "P2 test"},
                     timeout=30)
    assert r.status_code == 200, f"grant failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("social_work_access") is True
    assert body.get("social_work_access_expires_at"), "Expected expires_at to be set"

    # Re-login the staff user — JWT may not carry new flag; backend reads from DB on each req.
    h_staff = {"Authorization": f"Bearer {staff_user['token']}"}
    r2 = requests.get(f"{BASE_URL}/api/social-work/cases", headers=h_staff, timeout=30)
    assert r2.status_code == 200, f"After grant expected 200, got {r2.status_code}: {r2.text[:200]}"


# ============== Expiring-soon endpoint ==============

def test_expiring_soon_shape_and_includes_user(staff_user, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/api/admin/module-access/expiring-soon?days=7",
                     headers=h, timeout=30)
    assert r.status_code == 200, f"expiring-soon failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert "count" in body and "days" in body and "rows" in body
    assert body["days"] == 7
    assert isinstance(body["rows"], list)
    # The previous test granted social_work with ttl=5 to staff_user → it must be present.
    matches = [row for row in body["rows"]
               if row.get("user_id") == staff_user["id"] and row.get("module") == "social_work"]
    assert matches, f"Expected staff_user social_work grant in expiring-soon; got rows={body['rows'][:5]}"
    row = matches[0]
    for k in ("user_id", "name", "role", "module", "module_label", "expires_at"):
        assert k in row, f"Missing key {k} in row {row}"


# ============== Task snooze ==============

@pytest.fixture(scope="module")
def admin_task(admin_token):
    """Create a temporary task owned by admin for snooze tests."""
    h = {"Authorization": f"Bearer {admin_token}"}
    # First find a board the admin can post on
    boards = requests.get(f"{BASE_URL}/api/boards", headers=h, timeout=30).json()
    if not boards:
        pytest.skip("No boards available for task creation")
    bid = boards[0]["id"]
    lists_resp = requests.get(f"{BASE_URL}/api/boards/{bid}/lists", headers=h, timeout=30).json()
    if isinstance(lists_resp, dict):
        lists_resp = lists_resp.get("lists") or lists_resp.get("data") or []
    lid = (lists_resp[0]["id"] if lists_resp else None)
    payload = {"title": f"TEST snooze {uuid.uuid4().hex[:6]}", "status": "todo",
               "priority": "medium", "board_id": bid, "list_id": lid}
    r = requests.post(f"{BASE_URL}/api/tasks", headers=h, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"task create failed: {r.text[:200]}"
    task = r.json()
    yield task
    requests.delete(f"{BASE_URL}/api/tasks/{task['id']}", headers=h, timeout=30)


def test_snooze_sets_date(admin_task, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.post(f"{BASE_URL}/api/tasks/{admin_task['id']}/snooze",
                      headers=h, json={"days": 7}, timeout=30)
    assert r.status_code == 200, f"snooze failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("snoozed") is True
    assert body.get("snooze_until"), "snooze_until missing"
    # Validate ~7 days out (parse YYYY-MM-DD)
    from datetime import date, timedelta
    expected = (date.today() + timedelta(days=7)).isoformat()
    assert body["snooze_until"][:10] == expected, f"expected {expected}, got {body['snooze_until']}"

    # Verify on the task record via list
    tasks = requests.get(f"{BASE_URL}/api/tasks?board_id={admin_task.get('board_id', '')}",
                         headers=h, timeout=30).json()
    match = [t for t in tasks if t["id"] == admin_task["id"]]
    assert match and match[0].get("snooze_until"), "task snooze_until not persisted"


def test_snooze_clear(admin_task, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.post(f"{BASE_URL}/api/tasks/{admin_task['id']}/snooze",
                      headers=h, json={"clear": True}, timeout=30)
    assert r.status_code == 200, f"clear failed: {r.status_code} {r.text[:200]}"
    assert r.json().get("snoozed") is False
    tasks = requests.get(f"{BASE_URL}/api/tasks?board_id={admin_task.get('board_id', '')}",
                         headers=h, timeout=30).json()
    match = [t for t in tasks if t["id"] == admin_task["id"]]
    assert match
    assert not match[0].get("snooze_until"), "snooze_until should be cleared"


def test_snooze_forbidden_for_non_assignee(admin_task, staff_user):
    """staff_user is neither assignee nor manager → 403."""
    h = {"Authorization": f"Bearer {staff_user['token']}"}
    r = requests.post(f"{BASE_URL}/api/tasks/{admin_task['id']}/snooze",
                      headers=h, json={"days": 3}, timeout=30)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"
