"""iter347 backlog tests: rejected access-requests, missed calls, legacy dept migration."""
import os
import time
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if not url:
        # Fall back to reading frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().rstrip("/")
                        break
        except Exception:
            pass
    return url

BASE_URL = _load_backend_url()
ADMIN = {"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


def _visitor_headers(ip: str = "") -> dict:
    """A unique X-Forwarded-For per test = a unique rate-limit bucket.

    The public endpoint keys its limiter on the real visitor IP (leftmost
    X-Forwarded-For), so tests that deliberately trip the limiter no longer
    poison the ones that follow.
    """
    return {"X-Forwarded-For": ip or f"203.0.113.{uuid.uuid4().int % 250 + 1}"}


# ─── Rejected access-requests ──────────────────────────────
class TestRejectedAccessRequests:
    def test_rejection_flow_and_admin_endpoints(self, admin_session):
        # Clear existing so counts are predictable
        admin_session.delete(f"{BASE_URL}/api/access/rejected-requests")
        visitor = _visitor_headers()

        # Create a guest link with max_uses=1
        link_res = admin_session.post(f"{BASE_URL}/api/access/guest-links",
                                      json={"space_name": "TEST_iter347", "max_uses": 1})
        assert link_res.status_code == 200, link_res.text
        link = link_res.json()
        token = link["token"]

        # (a) bogus token → 404 invalid_link
        r = requests.post(f"{BASE_URL}/api/public/access-request/does_not_exist_xyz",
                          json={"name": "Someone", "email": "a@b.co"}, headers=visitor)
        assert r.status_code == 404

        # iter348: blocked attempts now count toward the 5-per-IP/10-min
        # window, so the link-lifecycle cases run BEFORE the validation ones —
        # otherwise the 5th call trips the limiter and masks what we're testing.
        # (b) valid submission → 200, not logged as a rejection
        r = requests.post(f"{BASE_URL}/api/public/access-request/{token}",
                          headers=visitor, json={"name": "Valid Guest", "email": f"g{uuid.uuid4().hex[:6]}@t.co"})
        assert r.status_code == 200, r.text

        # (c) second submit on max_uses=1 link → 400 max_uses
        r = requests.post(f"{BASE_URL}/api/public/access-request/{token}",
                          headers=visitor, json={"name": "Second Guest", "email": f"g{uuid.uuid4().hex[:6]}@t.co"})
        assert r.status_code == 400

        # (d) name too short → validation 400
        r = requests.post(f"{BASE_URL}/api/public/access-request/{token}",
                          headers=visitor, json={"name": "X"})
        assert r.status_code == 400

        # Check the admin GET /rejected-requests
        rej = admin_session.get(f"{BASE_URL}/api/access/rejected-requests")
        assert rej.status_code == 200
        body = rej.json()
        assert "rejections" in body and "by_reason" in body and "top_ips" in body
        reasons = {r["reason"] for r in body["rejections"]}
        # Expect at least invalid_link, validation, max_uses
        assert "invalid_link" in reasons, reasons
        assert "validation" in reasons, reasons
        assert "max_uses" in reasons, reasons
        # No _id leaked
        for row in body["rejections"]:
            assert "_id" not in row

    def test_rate_limit_after_5_hits(self, admin_session):
        # Fresh link with unlimited uses
        link_res = admin_session.post(f"{BASE_URL}/api/access/guest-links",
                                      json={"space_name": "TEST_iter347_rl", "max_uses": 0})
        token = link_res.json()["token"]

        visitor = _visitor_headers()
        codes = []
        for i in range(7):
            r = requests.post(f"{BASE_URL}/api/public/access-request/{token}",
                              headers=visitor,
                              json={"name": f"Rate Test {i}",
                                    "email": f"rl{uuid.uuid4().hex[:6]}@t.co"})
            codes.append(r.status_code)
        # Should see a 429 after 5 hits in the window
        assert 429 in codes, f"expected 429 in {codes}"

        # iter348: junk payloads count too — previously only successful
        # submissions did, so an attacker could brute-force tokens forever by
        # always sending invalid input.
        admin_session.delete(f"{BASE_URL}/api/access/rejected-requests")
        link2 = admin_session.post(f"{BASE_URL}/api/access/guest-links",
                                   json={"space_name": "TEST_iter348_rl_invalid", "max_uses": 0})
        token2 = link2.json()["token"]
        junk_visitor = _visitor_headers()
        junk_codes = [
            requests.post(f"{BASE_URL}/api/public/access-request/{token2}",
                          headers=junk_visitor, json={"name": "X"}).status_code
            for _ in range(8)
        ]
        assert 429 in junk_codes, f"invalid payloads must count toward the limit: {junk_codes}"

        rej = admin_session.get(f"{BASE_URL}/api/access/rejected-requests?reason=rate_limited")
        assert rej.status_code == 200
        assert any(r["reason"] == "rate_limited" for r in rej.json()["rejections"])

    def test_clear_all_requires_admin(self, admin_session):
        r = admin_session.delete(f"{BASE_URL}/api/access/rejected-requests")
        assert r.status_code == 200
        assert "deleted" in r.json()
        # after clear list should be empty
        r2 = admin_session.get(f"{BASE_URL}/api/access/rejected-requests")
        assert r2.json()["total"] == 0


# ─── Missed calls ───────────────────────────────────────────
class TestMissedCalls:
    def test_post_get_dedupe_handled(self, admin_session):
        peer = f"070{uuid.uuid4().hex[:7]}"
        r = admin_session.post(f"{BASE_URL}/api/voip/me/missed-calls",
                               json={"peer": peer, "caller_name": "Test Caller", "reason": "no_answer"})
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc.get("id")
        assert not doc.get("duplicate")
        call_id = doc["id"]

        # de-dupe within 90s
        r2 = admin_session.post(f"{BASE_URL}/api/voip/me/missed-calls",
                                json={"peer": peer, "caller_name": "Test Caller"})
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

        # GET should list it
        lst = admin_session.get(f"{BASE_URL}/api/voip/me/missed-calls")
        assert lst.status_code == 200
        assert any(m["id"] == call_id for m in lst.json())

        # Verify notification was created with proper link
        nots = admin_session.get(f"{BASE_URL}/api/notifications?limit=20")
        assert nots.status_code == 200
        matching = [n for n in nots.json() if peer in (n.get("link") or "")]
        assert matching, "expected a notification linking /comms?room=phone&call="
        assert "/comms?room=phone&call=" in matching[0]["link"]

        # mark handled
        h = admin_session.put(f"{BASE_URL}/api/voip/me/missed-calls/{call_id}/handled")
        assert h.status_code == 200

        # gone from default list
        lst2 = admin_session.get(f"{BASE_URL}/api/voip/me/missed-calls")
        assert not any(m["id"] == call_id for m in lst2.json())


# ─── Legacy department migration ────────────────────────────
class TestLegacyDeptMigration:
    def test_scan_returns_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/departments/legacy-scan")
        assert r.status_code == 200
        body = r.json()
        assert "groups" in body and "total_records" in body and "existing_departments" in body

    def test_dry_run_no_creation(self, admin_session):
        before = admin_session.get(f"{BASE_URL}/api/departments").json()
        before_ids = {d["id"] for d in before}
        r = admin_session.post(f"{BASE_URL}/api/departments/migrate-legacy",
                               json={"dry_run": True})
        assert r.status_code == 200
        after = admin_session.get(f"{BASE_URL}/api/departments").json()
        after_ids = {d["id"] for d in after}
        # dry_run must NOT create new deps
        assert before_ids == after_ids
