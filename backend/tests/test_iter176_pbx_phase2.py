"""PBX Phase 2 — AMI bridge + softphone helper endpoints (iter 176).

Verifies graceful degradation when AMI_SECRET is unset (preview env):
  - /api/pbx/apply → 200 {applied:false, ami_response:{...skipped...}}
  - /api/pbx/registrations → 200 {live:false, reason:'AMI not configured'}
  - /api/pbx/originate → 503 AMI_SECRET unset / 404 / 400
  - /api/pbx/me/softphone → 204 (no ext) / 200 (wss ext) with full payload
  - /api/pbx/me/click-to-call-config → 204 / 200
  - RBAC: /apply, /registrations, /originate require admin
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_id(headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def staff_token(headers):
    """Create a fresh non-admin user via /auth/register, return their bearer token."""
    import uuid
    email = f"test_pbxstaff_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"name": "TEST Staff", "email": email, "password": "Test@5812!", "role": "Guest"}
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"could not register staff user: {r.status_code} {r.text[:200]}")
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    uid = (body.get("user") or {}).get("id")
    if not tok:
        # try login (pending users may not get a token)
        lr = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"identifier": email, "password": "Test@5812!"}, timeout=10)
        if lr.status_code == 200:
            tok = lr.json().get("token") or lr.json().get("access_token")
    if not tok:
        pytest.skip(f"no token for staff user (status may be 'pending')")
    yield {"token": tok, "id": uid, "email": email}
    # cleanup
    if uid:
        requests.delete(f"{BASE_URL}/api/users/{uid}", headers=headers, timeout=10)


# ── /apply ─────────────────────────────────────────────────────
class TestApply:
    def test_apply_returns_200_when_ami_unset(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/apply", headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["applied"] is False
        assert data["ami_response"]["reloaded"] is False
        assert "skipped" in data["ami_response"] or "error" in data["ami_response"]
        assert "config_urls" in data
        for k in ("pjsip", "extensions", "voicemail"):
            assert k in data["config_urls"]

    def test_apply_requires_admin(self, staff_token):
        h = {"Authorization": f"Bearer {staff_token['token']}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/api/pbx/apply", headers=h, timeout=10)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


# ── /registrations ─────────────────────────────────────────────
class TestRegistrations:
    def test_registrations_graceful_when_ami_unset(self, headers):
        r = requests.get(f"{BASE_URL}/api/pbx/registrations", headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["live"] is False
        assert "AMI not configured" in data["reason"]
        assert isinstance(data["extensions"], list)
        assert isinstance(data["trunks"], list)
        for e in data["extensions"]:
            for k in ("id", "number", "display_name", "registered", "user_agent", "contact_uri", "roundtrip_ms"):
                assert k in e, f"missing {k} in extension entry"
            assert e["registered"] is False
            assert e["user_agent"] == ""
            assert e["contact_uri"] == ""
            assert e["roundtrip_ms"] is None

    def test_registrations_requires_admin(self, staff_token):
        h = {"Authorization": f"Bearer {staff_token['token']}"}
        r = requests.get(f"{BASE_URL}/api/pbx/registrations", headers=h, timeout=10)
        assert r.status_code == 403


# ── /originate ─────────────────────────────────────────────────
class TestOriginate:
    def test_originate_missing_fields_400(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/originate", headers=headers, json={}, timeout=10)
        assert r.status_code == 400, r.text
        r2 = requests.post(f"{BASE_URL}/api/pbx/originate", headers=headers,
                           json={"from_extension": "101"}, timeout=10)
        assert r2.status_code == 400
        r3 = requests.post(f"{BASE_URL}/api/pbx/originate", headers=headers,
                           json={"to_number": "+15551234567"}, timeout=10)
        assert r3.status_code == 400

    def test_originate_unknown_extension_404(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/originate", headers=headers,
                          json={"from_extension": "99987", "to_number": "+15551234567"},
                          timeout=10)
        assert r.status_code == 404, r.text
        assert "99987" in r.text or "not found" in r.text.lower()

    def test_originate_503_when_ami_unset(self, headers):
        # Create a real extension first
        ext_payload = {"number": "778", "display_name": "TEST_orig", "transport": "transport-udp"}
        cr = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json=ext_payload, timeout=10)
        if cr.status_code != 200:
            pytest.skip(f"could not create ext: {cr.text}")
        ext = cr.json()
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/originate", headers=headers,
                              json={"from_extension": "778", "to_number": "+15551234567"},
                              timeout=10)
            assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
            assert "AMI_SECRET" in r.text or "AMI" in r.text or "unset" in r.text.lower()
        finally:
            requests.delete(f"{BASE_URL}/api/pbx/extensions/{ext['id']}", headers=headers, timeout=10)

    def test_originate_requires_admin(self, staff_token):
        h = {"Authorization": f"Bearer {staff_token['token']}", "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/api/pbx/originate", headers=h,
                          json={"from_extension": "101", "to_number": "+15551234567"},
                          timeout=10)
        assert r.status_code == 403


# ── /me/softphone ──────────────────────────────────────────────
class TestSoftphoneMe:
    def test_softphone_204_when_no_extension(self, headers, admin_id):
        # ensure no wss ext on admin
        r = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
        for e in r.json():
            if e.get("user_id") == admin_id and e.get("transport") == "transport-wss":
                # detach
                requests.put(f"{BASE_URL}/api/pbx/extensions/{e['id']}", headers=headers,
                             json={"user_id": None}, timeout=10)
        r = requests.get(f"{BASE_URL}/api/pbx/me/softphone", headers=headers, timeout=10)
        assert r.status_code == 204, r.text

    def test_softphone_returns_creds_when_wss_assigned(self, headers, admin_id):
        # Create a wss extension assigned to admin
        ep = {"number": "881", "display_name": "TEST_softphone",
              "transport": "transport-wss", "user_id": admin_id}
        cr = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json=ep, timeout=10)
        assert cr.status_code == 200, cr.text
        ext = cr.json()
        try:
            r = requests.get(f"{BASE_URL}/api/pbx/me/softphone", headers=headers, timeout=10)
            assert r.status_code == 200, r.text
            data = r.json()
            for k in ("extension", "secret", "ws_url", "sip_uri", "sip_domain", "stun_url", "allowed_codecs"):
                assert k in data, f"missing key {k}"
            assert data["extension"] == "881"
            assert data["sip_uri"].startswith("sip:881@")
            assert "stun:" in data["stun_url"]
        finally:
            requests.delete(f"{BASE_URL}/api/pbx/extensions/{ext['id']}", headers=headers, timeout=10)

    def test_softphone_accessible_by_non_admin(self, staff_token):
        h = {"Authorization": f"Bearer {staff_token['token']}"}
        r = requests.get(f"{BASE_URL}/api/pbx/me/softphone", headers=h, timeout=10)
        # No ext for fresh staff → 204; not 403/401
        assert r.status_code in (200, 204), f"got {r.status_code}: {r.text}"


# ── /me/click-to-call-config ───────────────────────────────────
class TestClickToCallConfig:
    def test_click_to_call_204_when_no_ext(self, staff_token):
        h = {"Authorization": f"Bearer {staff_token['token']}"}
        r = requests.get(f"{BASE_URL}/api/pbx/me/click-to-call-config", headers=h, timeout=10)
        assert r.status_code == 204

    def test_click_to_call_200_with_udp_ext(self, headers, admin_id):
        # Detach any existing
        list_r = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
        for e in list_r.json():
            if e.get("user_id") == admin_id:
                requests.put(f"{BASE_URL}/api/pbx/extensions/{e['id']}", headers=headers,
                             json={"user_id": None}, timeout=10)
        ep = {"number": "882", "display_name": "TEST_udp",
              "transport": "transport-udp", "user_id": admin_id}
        cr = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json=ep, timeout=10)
        assert cr.status_code == 200, cr.text
        ext = cr.json()
        try:
            r = requests.get(f"{BASE_URL}/api/pbx/me/click-to-call-config", headers=headers, timeout=10)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["extension"] == "882"
            assert data["is_softphone"] is False
        finally:
            requests.delete(f"{BASE_URL}/api/pbx/extensions/{ext['id']}", headers=headers, timeout=10)

    def test_click_to_call_softphone_flag_true_for_wss(self, headers, admin_id):
        ep = {"number": "883", "display_name": "TEST_wss_cfg",
              "transport": "transport-wss", "user_id": admin_id}
        cr = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json=ep, timeout=10)
        assert cr.status_code == 200, cr.text
        ext = cr.json()
        try:
            r = requests.get(f"{BASE_URL}/api/pbx/me/click-to-call-config", headers=headers, timeout=10)
            assert r.status_code == 200
            assert r.json()["is_softphone"] is True
        finally:
            requests.delete(f"{BASE_URL}/api/pbx/extensions/{ext['id']}", headers=headers, timeout=10)


# ── Trunk render regression (register=true + no username should 400) ───
class TestTrunkRegisterValidation:
    def test_trunk_register_requires_username(self, headers):
        payload = {"name": "TEST_badreg", "host": "sip.example.com",
                   "register": True, "username": ""}
        r = requests.post(f"{BASE_URL}/api/pbx/trunks", headers=headers, json=payload, timeout=10)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
