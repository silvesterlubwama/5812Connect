"""Backend tests for the Security Checkpoint Kiosk (iteration 91)."""
import os
import io
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend/.env file
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=20,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def some_location(admin_headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    locs = r.json()
    if isinstance(locs, dict):
        locs = locs.get("locations") or locs.get("items") or []
    assert isinstance(locs, list) and locs, "no locations available"
    return locs[0]


@pytest.fixture(scope="module")
def admin_user_id(admin_token):
    # decode-less: hit /api/auth/me
    r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return r.json().get("id") or r.json().get("user", {}).get("id")


@pytest.fixture(scope="module")
def checkpoint(admin_headers, some_location):
    body = {
        "name": "TEST_Checkpoint_Iter91",
        "location_id": some_location["id"],
        "description": "iter91 test",
        "requires_id_for_one_time": True,
    }
    r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
    assert r.status_code == 200, f"create checkpoint: {r.status_code} {r.text[:300]}"
    cp = r.json()
    assert cp.get("id", "").startswith("cpk_")
    assert len(cp["pairing_pin"]) == 6 and cp["pairing_pin"].isdigit()
    assert cp["location_name"]
    yield cp
    # cleanup
    requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ---------- Admin CRUD ----------
class TestCheckpointAdmin:
    def test_list_contains_created(self, admin_headers, checkpoint):
        r = requests.get(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert checkpoint["id"] in ids

    def test_update_description(self, admin_headers, checkpoint):
        r = requests.put(
            f"{BASE_URL}/api/security/checkpoints/{checkpoint['id']}",
            headers=admin_headers,
            json={"description": "updated"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["description"] == "updated"

    def test_update_rejects_empty(self, admin_headers, checkpoint):
        r = requests.put(
            f"{BASE_URL}/api/security/checkpoints/{checkpoint['id']}",
            headers=admin_headers,
            json={"hacker_field": "x"},
            timeout=20,
        )
        assert r.status_code == 400


# ---------- Pair ----------
class TestPair:
    def test_pair_bad_pin_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": "000000", "mode": "guest"}, timeout=20)
        assert r.status_code == 401

    def test_pair_bad_pin_format(self):
        r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": "abc", "mode": "guest"}, timeout=20)
        assert r.status_code == 400

    def test_pair_guest_and_security(self, checkpoint):
        pin = checkpoint["pairing_pin"]
        r1 = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": pin, "mode": "guest"}, timeout=20)
        assert r1.status_code == 200, r1.text[:200]
        g = r1.json()
        assert g["mode"] == "guest"
        assert g["session_token"]
        assert g["checkpoint"]["id"] == checkpoint["id"]
        assert "pairing_pin" not in g["checkpoint"], "pairing_pin must NOT be leaked"

        r2 = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": pin, "mode": "security"}, timeout=20)
        assert r2.status_code == 200
        s = r2.json()
        assert s["mode"] == "security"
        assert s["session_token"] != g["session_token"]


@pytest.fixture(scope="module")
def guest_session(checkpoint):
    r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": checkpoint["pairing_pin"], "mode": "guest"}, timeout=20)
    assert r.status_code == 200
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def security_session(checkpoint):
    r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": checkpoint["pairing_pin"], "mode": "security"}, timeout=20)
    assert r.status_code == 200
    return r.json()["session_token"]


# ---------- Scan ----------
class TestScan:
    def test_scan_missing_session_401(self):
        r = requests.post(f"{BASE_URL}/api/security/checkpoint/scan", json={"scan_type": "qr", "payload": "x"}, timeout=20)
        assert r.status_code == 401

    def test_scan_bad_session_401(self):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": "bogus"},
            json={"scan_type": "qr", "payload": "x"},
            timeout=20,
        )
        assert r.status_code == 401

    def test_scan_admin_uuid_approved(self, security_session, admin_user_id):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": security_session},
            json={"scan_type": "qr", "payload": admin_user_id},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        ev = r.json()
        assert ev["decision"] == "approved", ev
        assert ev["subject"]["kind"] in {"user", "member"}
        assert ev["kind"] == "entry_scan"
        assert ev["clear_at"] > ev["created_at"]

    def test_scan_unknown_payload_denied(self, security_session):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": security_session},
            json={"scan_type": "qr", "payload": "definitely-not-a-real-id-1234567890"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["decision"] == "denied"


# ---------- State / Finish ----------
class TestStateAndFinish:
    def test_state_security_has_history(self, security_session, checkpoint):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoint/state",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "security"
        assert body["checkpoint"]["id"] == checkpoint["id"]
        assert isinstance(body["history"], list)
        assert len(body["history"]) >= 1  # we already scanned

    def test_state_guest_history_empty(self, guest_session):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoint/state",
            headers={"X-Checkpoint-Session": guest_session},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "guest"
        assert body["history"] == []

    def test_finish_clears_current(self, security_session, admin_user_id):
        # generate fresh event
        requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": security_session},
            json={"scan_type": "qr", "payload": admin_user_id},
            timeout=20,
        )
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/finish",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["cleared"] >= 1
        # state.current should now be None
        r2 = requests.get(
            f"{BASE_URL}/api/security/checkpoint/state",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        )
        assert r2.json()["current"] is None


# ---------- One-time grant ----------
class TestOneTimeGrant:
    def test_grant_requires_security(self, guest_session):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/grant-one-time",
            headers={"X-Checkpoint-Session": guest_session},
            data={"name": "TEST_Visitor", "phone": "123", "reason": "test"},
            timeout=20,
        )
        assert r.status_code == 403

    def test_grant_requires_id_image_when_set(self, security_session):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/grant-one-time",
            headers={"X-Checkpoint-Session": security_session},
            data={"name": "TEST_NoID", "phone": "0", "reason": "no id"},
            timeout=20,
        )
        assert r.status_code == 400

    def test_grant_with_image_succeeds(self, security_session):
        files = {"id_image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fakejpg"), "image/jpeg")}
        data = {"name": "TEST_Visitor", "phone": "+256700", "reason": "iter91"}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/grant-one-time",
            headers={"X-Checkpoint-Session": security_session},
            data=data,
            files=files,
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["grant"]["id_image_url"]
        assert body["event"]["decision"] == "approved"
        assert body["event"]["kind"] == "one_time_grant"

    def test_one_time_open_list(self, security_session):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoint/one-time/open",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        )
        assert r.status_code == 200
        assert any(g.get("name") == "TEST_Visitor" for g in r.json())

    def test_one_time_open_guest_forbidden(self, guest_session):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoint/one-time/open",
            headers={"X-Checkpoint-Session": guest_session},
            timeout=20,
        )
        assert r.status_code == 403

    def test_return_id_marks_returned(self, security_session):
        # find an open grant
        listing = requests.get(
            f"{BASE_URL}/api/security/checkpoint/one-time/open",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        ).json()
        assert listing
        gid = listing[0]["id"]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/one-time/{gid}/return-id",
            headers={"X-Checkpoint-Session": security_session},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["id_returned"] is True


# ---------- Receipt exit-scan ----------
class TestReceiptScan:
    def test_receipt_not_found(self, security_session):
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan/receipt",
            headers={"X-Checkpoint-Session": security_session},
            json={"receipt_number": "NOT_A_RECEIPT_XYZ_42"},
            timeout=20,
        )
        assert r.status_code == 404


# ---------- Admin audit ----------
class TestAdminAudit:
    def test_admin_can_list_events(self, admin_headers, checkpoint):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoints/{checkpoint['id']}/events",
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_can_list_one_time(self, admin_headers, checkpoint):
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoints/{checkpoint['id']}/one-time",
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Rotate PIN revokes ----------
class TestRotatePin:
    def test_rotate_revokes_sessions(self, admin_headers, some_location):
        # create a fresh checkpoint specifically for rotate test
        c = requests.post(
            f"{BASE_URL}/api/security/checkpoints",
            headers=admin_headers,
            json={"name": "TEST_Rotate", "location_id": some_location["id"]},
            timeout=20,
        ).json()
        try:
            r1 = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": c["pairing_pin"], "mode": "guest"}, timeout=20)
            old_token = r1.json()["session_token"]
            r2 = requests.post(f"{BASE_URL}/api/security/checkpoints/{c['id']}/rotate-pin", headers=admin_headers, timeout=20)
            assert r2.status_code == 200
            new_pin = r2.json()["pairing_pin"]
            assert new_pin != c["pairing_pin"] and len(new_pin) == 6
            # old token should be revoked
            r3 = requests.get(
                f"{BASE_URL}/api/security/checkpoint/state",
                headers={"X-Checkpoint-Session": old_token},
                timeout=20,
            )
            assert r3.status_code == 401
        finally:
            requests.delete(f"{BASE_URL}/api/security/checkpoints/{c['id']}", headers=admin_headers, timeout=20)
