"""Iteration 79 tests:
(a) MongoDB indexes audit — sessions.jti unique index
(p) server.py router split — dashboard/i18n/seed/webcal endpoints respond
(l) Session manager — login returns jti, /auth/sessions, revoke, revoke-others, logout revokes
(i) Birthday/anniversary code path exists (static verification)
(h) Push subscribe/unsubscribe/vapid-key
(regression) iter77 directory + active-campus, iter78 payday + multi-campus user
"""
import os
import re
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- (p) Router split — endpoints respond ----------
class TestRouterSplit:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_dashboard_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_dashboard_action_items(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_people_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/people/stats", headers=auth_headers, timeout=15)
        assert r.status_code in (200, 403)

    def test_parent_dashboard(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/parent/dashboard", headers=auth_headers, timeout=15)
        assert r.status_code in (200, 403, 404)

    def test_i18n_default(self):
        r = requests.get(f"{BASE_URL}/api/i18n", timeout=10)
        assert r.status_code == 200

    def test_i18n_en(self):
        r = requests.get(f"{BASE_URL}/api/i18n/en", timeout=10)
        assert r.status_code == 200

    def test_webcal_ics(self, auth_headers):
        # Need a user_id; use current user
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10).json()
        uid = me["id"]
        r = requests.get(f"{BASE_URL}/api/webcal/{uid}.ics", timeout=10)
        # Should return ics file (200 or requires no auth)
        assert r.status_code in (200, 401, 403), f"{r.status_code} {r.text[:200]}"


# ---------- (l) Session manager ----------
class TestSessionManager:
    def test_login_jwt_includes_jti(self, admin_token):
        import base64, json as _json
        parts = admin_token.split(".")
        assert len(parts) == 3
        payload = _json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        assert "jti" in payload, "JWT must include jti claim"
        assert "sub" in payload

    def test_list_sessions(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/sessions", headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "sessions" in data and "current_jti" in data
        assert isinstance(data["sessions"], list)
        # at least one session, current flagged
        assert any(s.get("is_current") for s in data["sessions"])
        assert data["current_jti"] is not None

    def test_revoke_other_sessions(self, auth_headers):
        # Create a second session (2nd login)
        r2 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        assert r2.status_code == 200
        other_token = r2.json()["token"]

        # Revoke others from the primary session
        r = requests.post(f"{BASE_URL}/api/auth/sessions/revoke-others", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("revoked") >= 1

        # Other token should now be 401 with 'Session revoked'
        r3 = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {other_token}"},
            timeout=10,
        )
        assert r3.status_code == 401
        assert "revoked" in r3.text.lower()

    def test_revoke_specific_session_and_logout(self):
        """Fresh login, then revoke via DELETE, verify 401. Then test logout revokes."""
        # First session to remain active
        r1 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        primary_token = r1.json()["token"]

        # Second session (target for revoke)
        r2 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        target_token = r2.json()["token"]

        import base64, json as _json
        target_jti = _json.loads(base64.urlsafe_b64decode(target_token.split(".")[1] + "=="))["jti"]

        # Revoke target from primary
        r = requests.delete(
            f"{BASE_URL}/api/auth/sessions/{target_jti}",
            headers={"Authorization": f"Bearer {primary_token}"},
            timeout=10,
        )
        assert r.status_code == 200

        # Target should now 401
        r3 = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {target_token}"}, timeout=10)
        assert r3.status_code == 401

        # Now logout primary → token revoked
        rl = requests.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {primary_token}"}, timeout=10)
        assert rl.status_code == 200

        r4 = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {primary_token}"}, timeout=10)
        assert r4.status_code == 401, f"Expected 401 after logout; got {r4.status_code}"


# ---------- (h) Push notifications ----------
class TestPush:
    def test_vapid_key(self):
        r = requests.get(f"{BASE_URL}/api/push/vapid-key", timeout=10)
        assert r.status_code == 200
        assert "publicKey" in r.json()

    def test_push_subscribe_and_unsubscribe(self, auth_headers):
        sub = {
            "subscription": {
                "endpoint": f"https://fcm.googleapis.com/fcm/send/TEST_iter79_{os.urandom(4).hex()}",
                "keys": {"p256dh": "TEST_p256dh", "auth": "TEST_auth"},
            }
        }
        r = requests.post(f"{BASE_URL}/api/push/subscribe", headers=auth_headers, json=sub, timeout=10)
        assert r.status_code == 200
        r2 = requests.delete(f"{BASE_URL}/api/push/subscribe", headers=auth_headers, timeout=10)
        assert r2.status_code == 200


# ---------- (i) Birthday/anniversary — static code verification ----------
class TestBirthdayAnniversary:
    def test_fire_birthday_function_exists(self):
        # iter302 — extracted to scheduler.py; server.py still re-exports the symbol.
        server_src = Path("/app/backend/server.py").read_text()
        sched_src = Path("/app/backend/scheduler.py").read_text()
        assert "_fire_birthday_anniversary_notifications" in server_src
        assert 'kind": "birthday"' in sched_src or "'kind': 'birthday'" in sched_src or '"kind": "birthday"' in sched_src
        assert 'kind": "anniversary"' in sched_src or '"kind": "anniversary"' in sched_src
        # Regex on date_of_birth
        assert "date_of_birth" in sched_src and "regex" in sched_src.lower()


# ---------- (a) Indexes — sessions.jti unique ----------
class TestIndexes:
    def test_sessions_jti_index_created_via_login(self, admin_token):
        """The login flow inserts a session with jti. Duplicate jti would fail at insert.
        Indirectly verifies the unique index is NOT blocking normal operation
        (if duplicate-key error occurred, login would fail)."""
        # Already verified implicitly. Just ensure /api/auth/sessions works.
        r = requests.get(f"{BASE_URL}/api/auth/sessions",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200

    def test_server_logs_indexes_ensured(self):
        log = Path("/var/log/supervisor/backend.err.log")
        if log.exists():
            content = log.read_text()[-50000:]
            assert "Indexes ensured" in content, "Expected 'Indexes ensured (idempotent)' log entry"


# ---------- Regression: iter77 + iter78 ----------
class TestRegression:
    def test_admin_directory_staff_only(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # staff-only filter: no Guest role
        non_staff = [u for u in users if (u.get("role") or "").lower() in {"guest", "customer"}]
        assert len(non_staff) == 0, f"Directory should not include guest/customer: {non_staff[:3]}"

    def test_active_campus_requires_campus_id(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/user/active-campus", headers=auth_headers, json={}, timeout=10)
        assert r.status_code == 400

    def test_hr_payslips_generate_payday_endpoint_exists(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday", headers=auth_headers, timeout=15)
        # Endpoint must exist; may return 200 (generated) or 200 with generated:0
        assert r.status_code in (200, 403), f"{r.status_code} {r.text[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
