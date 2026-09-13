"""iter351 — security-audit fixes regression suite.

Covers:
  SEC-001  kiosk lookup PII removal + exact match + throttle
  SEC-002  social-work case cross-campus 404
  SEC-003  kiosk unlock uniform 401 + throttle + valid unlock
  School-portal login throttle
  Auth CORS preflight allowlist
  Regression — badgeless checkpoint scan by phone (iter350 shared helper)
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

import creds

BASE = creds.BASE_URL
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD

# Direct DB for setup / cleanup
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "5812global")
_mc = MongoClient(MONGO_URL)
db = _mc[DB_NAME]


PII_FORBIDDEN = {
    "phone", "email", "date_of_birth", "dob",
    "national_id", "nin", "passport", "passport_number",
    "address", "notes", "pin", "password_hash",
}


# ---------- helpers ----------

def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"identifier": email, "password": password}, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def admin_user_phone():
    """Ensure the admin has a full phone so kiosk lookup has something to hit.
    Returns the phone string (unchanged if already set)."""
    u = db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "id": 1, "phone": 1})
    if not u:
        pytest.skip("admin user not found in DB")
    phone = (u.get("phone") or "").strip()
    if not phone or not phone.startswith("+"):
        phone = "+256772123456"
        db.users.update_one({"id": u["id"]}, {"$set": {"phone": phone}})
    return phone


def _clear_public_hits(action=None):
    q = {"action": action} if action else {}
    db.public_endpoint_hits.delete_many(q)


# ============================================================
# SEC-001 — kiosk lookup
# ============================================================

class TestKioskLookupPII:

    def test_lookup_returns_minimal_projection_no_pii(self, admin_user_phone):
        _clear_public_hits("kiosk_lookup")
        r = requests.get(f"{BASE}/api/kiosk/lookup",
                         params={"identifier": admin_user_phone},
                         headers={"X-Forwarded-For": "10.0.0.1"}, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        allowed = {"id", "name", "role", "photo_url", "location_id", "children"}
        extras = set(body.keys()) - allowed
        assert not extras, f"unexpected keys leaked from kiosk lookup: {extras}"
        # Explicit PII check
        for k in PII_FORBIDDEN:
            assert k not in body, f"PII field '{k}' leaked in kiosk lookup"
        # children are also minimal
        for c in body.get("children", []):
            cextras = set(c.keys()) - {"id", "name", "photo_url"}
            assert not cextras, f"children leaked keys: {cextras}"

    def test_suffix_phone_now_404(self, admin_user_phone):
        _clear_public_hits("kiosk_lookup")
        suffix = admin_user_phone[-9:]  # 9-digit tail
        r = requests.get(f"{BASE}/api/kiosk/lookup",
                         params={"identifier": suffix},
                         headers={"X-Forwarded-For": "10.0.0.2"}, timeout=15)
        assert r.status_code == 404, f"suffix should not match anymore, got {r.status_code} {r.text}"

    def test_short_identifier_400(self):
        _clear_public_hits("kiosk_lookup")
        r = requests.get(f"{BASE}/api/kiosk/lookup",
                         params={"identifier": "abc"},
                         headers={"X-Forwarded-For": "10.0.0.3"}, timeout=15)
        assert r.status_code == 400

    def test_rate_limit_kicks_in_around_15(self, admin_user_phone):
        _clear_public_hits("kiosk_lookup")
        ip = "10.9.9.9"
        codes = []
        for _ in range(20):
            r = requests.get(f"{BASE}/api/kiosk/lookup",
                             params={"identifier": admin_user_phone},
                             headers={"X-Forwarded-For": ip}, timeout=15)
            codes.append(r.status_code)
        assert 429 in codes, f"expected 429 in codes, got {codes}"
        first_429 = codes.index(429) + 1
        assert 14 <= first_429 <= 16, f"429 should hit ~15th call, actually {first_429}"
        # friendly message
        last_body = requests.get(f"{BASE}/api/kiosk/lookup",
                                 params={"identifier": admin_user_phone},
                                 headers={"X-Forwarded-For": ip}, timeout=15).json()
        assert "wait" in str(last_body).lower() or "attempts" in str(last_body).lower()

    def test_rate_limit_is_per_ip(self, admin_user_phone):
        # Fresh IP after previous saturation
        _clear_public_hits("kiosk_lookup")
        r = requests.get(f"{BASE}/api/kiosk/lookup",
                         params={"identifier": admin_user_phone},
                         headers={"X-Forwarded-For": "10.7.7.7"}, timeout=15)
        assert r.status_code == 200


# ============================================================
# SEC-003 — kiosk unlock oracle removed
# ============================================================

class TestKioskUnlockOracle:

    def _post(self, body, ip="10.20.20.1"):
        return requests.post(f"{BASE}/api/kiosk/unlock",
                             json=body, headers={"X-Forwarded-For": ip}, timeout=15)

    def test_unknown_identifier_returns_uniform_401(self):
        _clear_public_hits("kiosk_unlock")
        r = self._post({"identifier": f"nobody+{uuid.uuid4().hex}@nope.io", "password": "whatever"})
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid credentials"}

    def test_real_admin_wrong_password_returns_uniform_401(self):
        _clear_public_hits("kiosk_unlock")
        r = self._post({"identifier": ADMIN_EMAIL, "password": "totally-wrong-password"})
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid credentials"}

    def test_random_pin_returns_uniform_401(self):
        _clear_public_hits("kiosk_unlock")
        r = self._post({"pin": "987321"})
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid credentials"}

    def test_missing_both_returns_400(self):
        _clear_public_hits("kiosk_unlock")
        r = self._post({})
        assert r.status_code == 400

    def test_valid_unlock_still_works_and_role_returned(self):
        _clear_public_hits("kiosk_unlock")
        # Set a PIN on admin
        pin = "246813"
        u = db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "id": 1, "pin": 1})
        prev_pin = u.get("pin")
        db.users.update_one({"id": u["id"]}, {"$set": {"pin": pin}})
        try:
            r = self._post({"pin": pin}, ip="10.20.20.2")
            assert r.status_code == 200, f"{r.status_code} {r.text}"
            body = r.json()
            assert body.get("unlocked") is True
            assert body.get("user_role", "").lower() in ("admin", "system_admin")
        finally:
            if prev_pin is None:
                db.users.update_one({"id": u["id"]}, {"$unset": {"pin": ""}})
            else:
                db.users.update_one({"id": u["id"]}, {"$set": {"pin": prev_pin}})

    def test_unlock_throttles_around_8(self):
        _clear_public_hits("kiosk_unlock")
        ip = "10.20.20.99"
        codes = []
        for _ in range(12):
            r = self._post({"pin": "111111"}, ip=ip)
            codes.append(r.status_code)
        assert 429 in codes, f"unlock should throttle, got {codes}"
        first_429 = codes.index(429) + 1
        assert 7 <= first_429 <= 9, f"unlock 429 should hit ~8th, got {first_429}"


# ============================================================
# SEC-002 — cross-campus case scoping
# ============================================================

class TestSocialWorkCampusScoping:
    """Create a second campus + Director whose scope excludes campus A, then
    verify every by-id social-work endpoint 404s for a campus-A case."""

    CASE_A_ID = "sc_140b496b"

    @pytest.fixture(scope="class")
    def setup(self, admin_headers):
        # Verify the seeded case exists
        r = requests.get(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}",
                         headers=admin_headers, timeout=15)
        if r.status_code != 200:
            pytest.skip("seeded case sc_140b496b missing — cannot run cross-campus test")
        case_a = r.json()
        campus_a_id = case_a.get("location_id")
        assert campus_a_id, "case has no location_id"

        # Create campus B via /api/locations
        loc_body = {"name": f"TEST_Campus_B_{uuid.uuid4().hex[:6]}", "type": "campus"}
        rl = requests.post(f"{BASE}/api/locations", json=loc_body,
                           headers=admin_headers, timeout=15)
        assert rl.status_code in (200, 201), f"create loc failed: {rl.status_code} {rl.text}"
        campus_b = rl.json()
        campus_b_id = campus_b.get("id") or campus_b.get("_id")

        # Create Director user in campus B
        director_email = f"test.director.{uuid.uuid4().hex[:6]}@test.local"
        director_password = "TestDir@5812!"
        user_body = {
            "email": director_email,
            "name": "TEST Campus B Director",
            "password": director_password,
            "role": "Director",
            "location_id": campus_b_id,
            "location_ids": [campus_b_id],
        }
        ru = requests.post(f"{BASE}/api/admin/users", json=user_body,
                           headers=admin_headers, timeout=15)
        assert ru.status_code in (200, 201), f"create user failed: {ru.status_code} {ru.text}"
        user = ru.json()
        user_id = user.get("id")

        # login as director
        rlogin = _login(director_email, director_password)
        assert rlogin.status_code == 200, f"director login failed: {rlogin.text}"
        dir_token = rlogin.json()["token"]

        # Create a Case in campus B directly in the DB (bypasses subject-existence checks).
        case_b_id = f"sc_TEST_{uuid.uuid4().hex[:8]}"
        db.social_cases.insert_one({
            "id": case_b_id,
            "subject_kind": "child",
            "subject_id": f"test_child_{uuid.uuid4().hex[:6]}",
            "subject_name": "TEST Child B",
            "category": "child_development",
            "status": "active",
            "location_id": campus_b_id,
            "opened_by": user_id,
            "opened_at": "2026-01-01T00:00:00Z",
        })

        yield {
            "campus_a": campus_a_id,
            "campus_b": campus_b_id,
            "dir_headers": {"Authorization": f"Bearer {dir_token}"},
            "dir_user_id": user_id,
            "case_b_id": case_b_id,
        }

        # ---- cleanup ----
        try:
            if case_b_id:
                db.social_cases.delete_one({"id": case_b_id})
                db.social_case_notes.delete_many({"case_id": case_b_id})
                db.social_child_payments.delete_many({"case_id": case_b_id})
            requests.delete(f"{BASE}/api/admin/users/{user_id}", headers=admin_headers, timeout=10)
        except Exception:
            pass
        try:
            db.locations.delete_one({"id": campus_b_id})
        except Exception:
            pass

    def test_admin_can_read_campus_a_case(self, admin_headers):
        r = requests.get(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_admin_bogus_id_404(self, admin_headers):
        r = requests.get(f"{BASE}/api/social-work/cases/sc_does_not_exist",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 404

    def test_campusB_director_get_case_A_404(self, setup):
        r = requests.get(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}",
                         headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 404, f"cross-campus read leaked: {r.status_code} {r.text[:200]}"

    def test_campusB_director_report_case_A_404(self, setup):
        r = requests.get(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}/report",
                         headers=setup["dir_headers"], timeout=20)
        assert r.status_code == 404

    def test_campusB_director_update_case_A_404(self, setup):
        r = requests.put(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}",
                         json={"subject_name": "hacked"},
                         headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_campusB_director_add_note_case_A_404(self, setup):
        r = requests.post(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}/notes",
                          json={"body": "cross campus note", "note_type": "general"},
                          headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_campusB_director_add_payment_case_A_404(self, setup):
        r = requests.post(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}/payments",
                          json={"amount": 10, "currency": "USD", "date": "2026-01-01"},
                          headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_campusB_director_sponsor_story_case_A_404(self, setup):
        r = requests.post(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}/sponsor-story",
                          json={"body": "malicious", "tone": "warm"},
                          headers=setup["dir_headers"], timeout=30)
        assert r.status_code == 404

    def test_campusB_director_delete_case_A_404(self, setup):
        r = requests.delete(f"{BASE}/api/social-work/cases/{self.CASE_A_ID}",
                            headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_campusB_director_can_read_own_case_b(self, setup):
        if not setup["case_b_id"]:
            pytest.skip("case B was not created (director may lack create permission)")
        r = requests.get(f"{BASE}/api/social-work/cases/{setup['case_b_id']}",
                         headers=setup["dir_headers"], timeout=15)
        assert r.status_code == 200


# ============================================================
# School portal login throttle
# ============================================================

class TestSchoolPortalThrottle:

    def test_bogus_login_throttles(self):
        _clear_public_hits("school_portal_login")
        ip = "10.42.42.1"
        codes = []
        for _ in range(12):
            r = requests.post(f"{BASE}/api/school-portal/login",
                              json={"portal_token": "does-not-exist", "password": "x"},
                              headers={"X-Forwarded-For": ip}, timeout=15)
            codes.append(r.status_code)
        # First ~10 return 404 or 401, then 429
        assert 429 in codes, f"expected 429, got {codes}"
        first_429 = codes.index(429) + 1
        assert 9 <= first_429 <= 11, f"429 should hit ~10th, got {first_429}"


# ============================================================
# CORS allowlist
# ============================================================

class TestCORSAllowlist:

    def test_allowed_origin_preflight(self):
        # Use the public base URL for the preflight
        r = requests.options(f"{BASE}/api/kiosk/unlock",
                             headers={
                                 "Origin": "https://multi-tenant-scope.preview.emergentagent.com",
                                 "Access-Control-Request-Method": "POST",
                                 "Access-Control-Request-Headers": "content-type",
                             }, timeout=15)
        # CORS middleware returns 200 with the header
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "https://multi-tenant-scope.preview.emergentagent.com", f"got '{acao}'"

    def test_disallowed_origin_no_header(self):
        r = requests.options(f"{BASE}/api/kiosk/unlock",
                             headers={
                                 "Origin": "https://evil.example.com",
                                 "Access-Control-Request-Method": "POST",
                                 "Access-Control-Request-Headers": "content-type",
                             }, timeout=15)
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "", f"evil origin should not be echoed, got '{acao}'"


# ============================================================
# Regression — badge-less checkpoint scan (iter350 helper)
# ============================================================

class TestCheckpointBadgelessRegression:

    def test_checkpoint_scan_by_phone(self, admin_headers, admin_user_phone):
        # Create a temporary checkpoint, pair as security, scan admin's phone
        loc = db.locations.find_one({}, {"_id": 0, "id": 1})
        if not loc:
            pytest.skip("no locations in DB")
        body = {"name": f"TEST_cp_{uuid.uuid4().hex[:6]}", "location_id": loc["id"], "device_mode": "single_device"}
        cp = requests.post(f"{BASE}/api/security/checkpoints", headers=admin_headers, json=body, timeout=15)
        if cp.status_code not in (200, 201):
            pytest.skip(f"can't create checkpoint: {cp.status_code}")
        checkpoint = cp.json()
        pin = checkpoint.get("pairing_pin")
        try:
            pr = requests.post(f"{BASE}/api/security/checkpoint/pair",
                               json={"pin": pin, "mode": "security"}, timeout=15)
            assert pr.status_code == 200, f"pair {pr.status_code} {pr.text}"
            token = pr.json()["session_token"]
            r = requests.post(f"{BASE}/api/security/checkpoint/scan",
                              headers={"X-Checkpoint-Session": token},
                              json={"scan_type": "manual", "payload": admin_user_phone},
                              timeout=15)
            assert r.status_code == 200, f"scan {r.status_code} {r.text}"
            body_r = r.json()
            assert body_r.get("badgeless") is True
            assert body_r.get("matched_by") == "phone"
        finally:
            requests.delete(f"{BASE}/api/security/checkpoints/{checkpoint['id']}",
                            headers=admin_headers, timeout=15)
