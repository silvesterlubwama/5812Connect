"""Iteration 160 — Telemetry & License Management.

Covers the desktop / HQ telemetry + license CRUD flow:
  • POST /api/telemetry/heartbeat                (no auth)
  • POST /api/telemetry/heartbeat               (rate-limit: 8h dedup)
  • GET  /api/license/self                       (no auth)
  • POST /api/license/configure                  (admin only)
  • POST /api/admin/licenses                     (admin only)
  • GET  /api/admin/licenses                     (admin only)
  • PUT  /api/admin/licenses/{id}                (block / unblock)
  • DELETE /api/admin/licenses/{id}              (admin only)
  • GET  /api/admin/telemetry/installs           (admin only)
  • License status: valid / unlicensed / invalid / expired / blocked
"""
import os
import requests
import pytest
import uuid


def _load_backend_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.strip().startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    if not u:
        raise RuntimeError("REACT_APP_BACKEND_URL not configured")
    return u.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def install_id():
    return str(uuid.uuid4())


# ============================================================
# HEARTBEAT (no auth)
# ============================================================

def test_heartbeat_unlicensed_install(install_id):
    """A heartbeat with no license_key returns 'unlicensed' status."""
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": install_id,
        "license_key": "",
        "version": "0.1.0",
        "user_count": 5,
        "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["license_status"] == "unlicensed"
    assert "server_time" in j


def test_heartbeat_invalid_key(install_id):
    """A heartbeat with a bogus license_key returns 'invalid'."""
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": install_id,
        "license_key": "definitely-not-a-real-key-xyz",
        "version": "0.1.0",
        "user_count": 1,
        "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200
    assert r.json()["license_status"] == "invalid"


def test_heartbeat_requires_install_id():
    """Empty install_id → 400."""
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": "",
        "version": "0.1.0",
        "user_count": 0,
    }, timeout=15)
    assert r.status_code == 400


def test_heartbeat_dedup_within_8h(install_id):
    """Two heartbeats within 8 h from the same install_id → 2nd is rate-limited."""
    payload = {"install_id": install_id, "license_key": "", "version": "0.1.0", "user_count": 1, "env": "desktop"}
    r1 = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json=payload, timeout=15)
    assert r1.status_code == 200
    assert not r1.json().get("ratelimited")
    r2 = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json=payload, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("ratelimited") is True


# ============================================================
# LICENSE CRUD (admin only)
# ============================================================

def test_issue_license_requires_org_name(auth_headers):
    r = requests.post(f"{BASE_URL}/api/admin/licenses", headers=auth_headers, json={"plan": "trial"}, timeout=15)
    assert r.status_code == 400


def test_issue_list_block_delete_license_roundtrip(auth_headers, install_id):
    org_name = f"TEST_LIC_{uuid.uuid4().hex[:6]}"
    # Issue
    r = requests.post(f"{BASE_URL}/api/admin/licenses", headers=auth_headers,
                      json={"org_name": org_name, "plan": "standard"}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    issued = r.json()
    assert issued["org_name"] == org_name
    assert issued["plan"] == "standard"
    assert isinstance(issued["key"], str) and len(issued["key"]) >= 24
    license_id = issued["id"]
    license_key = issued["key"]

    # Heartbeat with the new key returns 'valid'
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": install_id, "license_key": license_key,
        "version": "0.1.0", "user_count": 3, "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200
    assert r.json()["license_status"] == "valid"

    # List
    r = requests.get(f"{BASE_URL}/api/admin/licenses", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    rows = r.json()
    assert any(L["id"] == license_id for L in rows)

    # Block
    r = requests.put(f"{BASE_URL}/api/admin/licenses/{license_id}", headers=auth_headers,
                     json={"blocked": True, "blocked_reason": "test revoke"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["blocked"] is True

    # Heartbeat after block → blocked (use new install_id to bypass 8h dedup)
    iid2 = str(uuid.uuid4())
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": iid2, "license_key": license_key,
        "version": "0.1.0", "user_count": 3, "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200
    assert r.json()["license_status"] == "blocked"

    # Unblock
    r = requests.put(f"{BASE_URL}/api/admin/licenses/{license_id}", headers=auth_headers,
                     json={"blocked": False}, timeout=15)
    assert r.status_code == 200
    assert r.json()["blocked"] is False

    # Delete
    r = requests.delete(f"{BASE_URL}/api/admin/licenses/{license_id}", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Heartbeat after delete → invalid (key no longer exists; bypass dedup again)
    iid3 = str(uuid.uuid4())
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": iid3, "license_key": license_key,
        "version": "0.1.0", "user_count": 3, "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200
    assert r.json()["license_status"] == "invalid"


def test_expired_license_returns_expired_status(auth_headers):
    """A license whose expires_at is past → 'expired'."""
    org_name = f"TEST_EXPIRED_{uuid.uuid4().hex[:6]}"
    # Issue with a past expiry
    r = requests.post(f"{BASE_URL}/api/admin/licenses", headers=auth_headers,
                      json={"org_name": org_name, "expires_at": "2020-01-01T00:00:00Z"}, timeout=15)
    assert r.status_code == 200
    issued = r.json()
    iid = str(uuid.uuid4())
    r = requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json={
        "install_id": iid, "license_key": issued["key"],
        "version": "0.1.0", "user_count": 1, "env": "desktop",
    }, timeout=15)
    assert r.status_code == 200
    assert r.json()["license_status"] == "expired"
    # Cleanup
    requests.delete(f"{BASE_URL}/api/admin/licenses/{issued['id']}", headers=auth_headers, timeout=15)


def test_admin_endpoints_require_admin():
    """Admin telemetry / license endpoints reject unauth requests."""
    r = requests.get(f"{BASE_URL}/api/admin/licenses", timeout=15)
    assert r.status_code in (401, 403)
    r = requests.get(f"{BASE_URL}/api/admin/telemetry/installs", timeout=15)
    assert r.status_code in (401, 403)
    r = requests.post(f"{BASE_URL}/api/admin/licenses", json={"org_name": "X"}, timeout=15)
    assert r.status_code in (401, 403)


def test_install_roster_includes_recent(auth_headers, install_id):
    """After a heartbeat, /api/admin/telemetry/installs reflects it."""
    payload = {"install_id": install_id, "license_key": "", "version": "0.1.0", "user_count": 7, "env": "desktop"}
    requests.post(f"{BASE_URL}/api/telemetry/heartbeat", json=payload, timeout=15)
    r = requests.get(f"{BASE_URL}/api/admin/telemetry/installs", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "installs" in data and "total" in data
    found = next((x for x in data["installs"] if x["install_id"] == install_id), None)
    assert found is not None
    assert found["user_count"] == 7
    assert "license_status_obj" in found


def test_license_self_endpoint_works():
    """GET /api/license/self does not require auth and returns a structured response."""
    r = requests.get(f"{BASE_URL}/api/license/self", timeout=15)
    assert r.status_code == 200
    j = r.json()
    # Either configured (with install_id + license_status) or default
    assert "license_status" in j


def test_license_configure_requires_admin():
    """POST /api/license/configure rejects unauth."""
    r = requests.post(f"{BASE_URL}/api/license/configure", json={"license_key": "test"}, timeout=15)
    assert r.status_code in (401, 403)
