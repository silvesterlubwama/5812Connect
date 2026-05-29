"""
Test iteration 90: Module Access generalization (Finance, HR, Sales, Banking, Accounting, Social Work, Restricted)
- Validates new /admin/module-access/* endpoints
- Validates legacy /admin/finance-access/* shim still works
- Validates Manager no longer auto-gets finance access (must be explicitly granted)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"
DEFAULT_NEW_PASSWORD = "Test@5812!"

EXPECTED_MODULES = {"finance", "hr", "sales", "banking", "accounting", "social_work", "restricted"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def manager_user(admin_headers):
    """Create a TEST manager user; return user dict + login token."""
    suffix = str(int(time.time()))[-6:]
    email = f"TEST_mgr_{suffix}@example.com"
    payload = {
        "email": email,
        "name": f"TEST Manager {suffix}",
        "role": "Manager",
        "password": DEFAULT_NEW_PASSWORD,
    }
    # Try the users endpoint
    r = requests.post(f"{BASE_URL}/api/users", json=payload, headers=admin_headers, timeout=20)
    if r.status_code not in (200, 201):
        # Try alternate seed endpoint
        r2 = requests.post(f"{BASE_URL}/api/admin/users", json=payload, headers=admin_headers, timeout=20)
        assert r2.status_code in (200, 201), f"could not create manager: {r.status_code}/{r.text[:200]} | {r2.status_code}/{r2.text[:200]}"
        user = r2.json()
    else:
        user = r.json()
    user_id = user.get("id") or user.get("_id") or user.get("user_id")
    assert user_id, f"no id in created user: {user}"

    # Login as manager
    lg = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"identifier": email, "password": DEFAULT_NEW_PASSWORD},
                       timeout=20)
    mtoken = None
    if lg.status_code == 200:
        mtoken = lg.json().get("token") or lg.json().get("access_token")

    yield {"id": user_id, "email": email, "token": mtoken}

    # Teardown: try to delete
    try:
        requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers, timeout=10)
    except Exception:
        pass


# --- 1. /admin/module-access/modules lists 7 modules ---
def test_modules_list(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/module-access/modules", headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    assert isinstance(data, list)
    keys = {m.get("key") for m in data}
    assert keys == EXPECTED_MODULES, f"expected {EXPECTED_MODULES}, got {keys}"
    for m in data:
        assert "key" in m and "label" in m


# --- 2. /admin/module-access/users?module=hr returns enriched users ---
@pytest.mark.parametrize("module", sorted(EXPECTED_MODULES))
def test_users_per_module(admin_headers, module):
    r = requests.get(f"{BASE_URL}/api/admin/module-access/users?module={module}",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200, f"module={module} -> {r.status_code} {r.text[:200]}"
    users = r.json()
    assert isinstance(users, list)
    assert len(users) > 0, f"no users for module={module}"
    sample = users[0]
    # Required enriched fields (access_expired is optional; only set when grant exists & expired)
    for k in ("access_implicit", "access_effective"):
        assert k in sample, f"module={module} sample missing {k}: keys={list(sample.keys())}"


# --- 3. Grant + Revoke HR access for the manager user ---
def test_grant_and_revoke_hr_access(admin_headers, manager_user):
    uid = manager_user["id"]
    # Grant HR with TTL=30
    r = requests.put(f"{BASE_URL}/api/admin/module-access/users/{uid}",
                     json={"module": "hr", "granted": True, "ttl_days": 30},
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"grant: {r.status_code} {r.text[:200]}"
    body = r.json()
    # Should reflect hr_access=true and an expiry timestamp
    assert body.get("hr_access") is True or body.get("access_effective") is True

    # Re-list and find the user
    r2 = requests.get(f"{BASE_URL}/api/admin/module-access/users?module=hr",
                      headers=admin_headers, timeout=15)
    assert r2.status_code == 200
    rows = r2.json()
    found = [u for u in rows if (u.get("id") or u.get("_id") or u.get("user_id")) == uid]
    assert found, f"manager {uid} not found in hr list"
    assert found[0].get("access_effective") is True, f"access_effective not true: {found[0]}"

    # Revoke
    rv = requests.put(f"{BASE_URL}/api/admin/module-access/users/{uid}",
                      json={"module": "hr", "granted": False},
                      headers=admin_headers, timeout=15)
    assert rv.status_code == 200, f"revoke: {rv.status_code} {rv.text[:200]}"

    r3 = requests.get(f"{BASE_URL}/api/admin/module-access/users?module=hr",
                      headers=admin_headers, timeout=15)
    rows3 = r3.json()
    found3 = [u for u in rows3 if (u.get("id") or u.get("_id") or u.get("user_id")) == uid]
    assert found3
    assert found3[0].get("access_effective") in (False, None), f"access still effective after revoke: {found3[0]}"


# --- 4. Legacy /admin/finance-access/* still works ---
def test_legacy_finance_access_users(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/finance-access/users", headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    users = r.json()
    assert isinstance(users, list) and len(users) > 0
    sample = users[0]
    # Must keep original keys
    assert "finance_access_implicit" in sample, f"missing legacy key, keys={list(sample.keys())}"
    assert "finance_access_effective" in sample, f"missing legacy key, keys={list(sample.keys())}"


def test_legacy_finance_access_put(admin_headers, manager_user):
    uid = manager_user["id"]
    r = requests.put(f"{BASE_URL}/api/admin/finance-access/users/{uid}",
                     json={"finance_access": True, "ttl_days": 30},
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    # Cleanup
    requests.put(f"{BASE_URL}/api/admin/finance-access/users/{uid}",
                 json={"finance_access": False}, headers=admin_headers, timeout=10)


# --- 5. CRITICAL behavior change: Manager no longer auto-gets finance access ---
def test_manager_excluded_from_implicit_finance(admin_headers, manager_user):
    if not manager_user["token"]:
        pytest.skip("manager login failed; cannot test 403 path")
    mheaders = {"Authorization": f"Bearer {manager_user['token']}"}

    # Before grant: should be 403 on a finance-protected route
    r1 = requests.get(f"{BASE_URL}/api/financial/donations", headers=mheaders, timeout=15)
    assert r1.status_code in (401, 403), f"expected 403 for manager without grant, got {r1.status_code} {r1.text[:200]}"

    # Grant finance access via new endpoint
    g = requests.put(f"{BASE_URL}/api/admin/module-access/users/{manager_user['id']}",
                     json={"module": "finance", "granted": True},
                     headers=admin_headers, timeout=15)
    assert g.status_code == 200, f"grant failed: {g.status_code} {g.text[:200]}"

    # After grant: should be 200
    r2 = requests.get(f"{BASE_URL}/api/financial/donations", headers=mheaders, timeout=15)
    assert r2.status_code == 200, f"expected 200 after grant, got {r2.status_code} {r2.text[:200]}"

    # Cleanup grant
    requests.put(f"{BASE_URL}/api/admin/module-access/users/{manager_user['id']}",
                 json={"module": "finance", "granted": False},
                 headers=admin_headers, timeout=10)
