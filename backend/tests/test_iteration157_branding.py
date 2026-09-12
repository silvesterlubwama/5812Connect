"""Iteration 157 — Branding & Navigation customisation.

Covers:
- GET /api/admin/system-settings/public exposes branding subset (no auth)
- PUT /api/admin/system-settings persists branding overrides
- Roundtrip: write app_name + nav_overrides + section_overrides + primary_color
- Non-admin cannot mutate system settings (403)
"""
import os
import requests
import pytest

import creds  # env-backed logins, see tests/creds.py


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
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": identifier, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASS)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(autouse=True, scope="module")
def _restore_branding(admin_token):
    """Reset branding to defaults after this module runs so we don't leak test
    overrides into other suites or the live app."""
    yield
    requests.put(
        f"{BASE_URL}/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"branding": {"app_name": "58:12 Connect", "tagline": "", "logo_url": "", "primary_color": "", "nav_overrides": {}, "section_overrides": {}}},
        timeout=15,
    )


def test_public_endpoint_no_auth_exposes_branding():
    r = requests.get(f"{BASE_URL}/api/admin/system-settings/public", timeout=15)
    assert r.status_code == 200, f"public settings failed: {r.status_code}"
    j = r.json()
    assert "branding" in j, "branding missing from public payload"
    b = j["branding"]
    for k in ("app_name", "tagline", "logo_url", "primary_color", "nav_overrides", "section_overrides"):
        assert k in b, f"branding.{k} missing"


def test_admin_writes_branding_and_public_reflects_it(admin_token):
    payload = {
        "branding": {
            "app_name": "Acme Field Ops",
            "tagline": "Test tagline",
            "logo_url": "https://example.com/logo.png",
            "primary_color": "#10b981",
            "nav_overrides": {
                "/dashboard": {"label": "Home Base", "order": 0},
                "/tasks": {"hidden": True},
            },
            "section_overrides": {
                "Operations": {"label": "Field Ops"},
                "Finance": {"hidden": True},
            },
        },
    }
    r = requests.put(
        f"{BASE_URL}/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
        timeout=15,
    )
    assert r.status_code == 200, f"write failed: {r.status_code} {r.text[:200]}"
    written = r.json().get("branding") or {}
    assert written.get("app_name") == "Acme Field Ops"
    assert written.get("primary_color") == "#10b981"
    assert (written.get("nav_overrides") or {}).get("/dashboard", {}).get("label") == "Home Base"
    assert (written.get("section_overrides") or {}).get("Finance", {}).get("hidden") is True

    # Public endpoint reflects it without auth
    r = requests.get(f"{BASE_URL}/api/admin/system-settings/public", timeout=15)
    assert r.status_code == 200
    pub = (r.json() or {}).get("branding") or {}
    assert pub.get("app_name") == "Acme Field Ops"
    assert pub.get("logo_url") == "https://example.com/logo.png"
    assert (pub.get("nav_overrides") or {}).get("/tasks", {}).get("hidden") is True
    assert (pub.get("section_overrides") or {}).get("Operations", {}).get("label") == "Field Ops"


def test_non_admin_cannot_write_branding(admin_token):
    # Try with no auth → should be 401/403
    r = requests.put(
        f"{BASE_URL}/api/admin/system-settings",
        json={"branding": {"app_name": "Hax"}},
        timeout=15,
    )
    assert r.status_code in (401, 403), f"unauth write should be rejected, got {r.status_code}"


def test_partial_update_preserves_other_branding_fields(admin_token):
    # Set everything
    requests.put(
        f"{BASE_URL}/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"branding": {"app_name": "Full", "tagline": "Keep me", "primary_color": "#ff00ff"}},
        timeout=15,
    )
    # Update only app_name
    r = requests.put(
        f"{BASE_URL}/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"branding": {"app_name": "Renamed"}},
        timeout=15,
    )
    assert r.status_code == 200
    b = r.json().get("branding") or {}
    assert b.get("app_name") == "Renamed"
    assert b.get("tagline") == "Keep me", "partial update should preserve untouched fields"
    assert b.get("primary_color") == "#ff00ff", "partial update should preserve untouched fields"
