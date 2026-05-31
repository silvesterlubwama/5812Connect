"""Iteration 146 — Residents Log + stray_home + org-wide bulk resident badges.

Coverage:
- /api/security/checkpoint/residents-log (device session): envelope shape; resident rows only
- /api/security/checkpoints/{id}/residents-log (admin auth) parity
- /checkpoint/scan stamps stray_home for residents scanning at non-home checkpoints
- /badges/auto-issue/residents body {location_id:'all'} sweep
- wallet_badges payload persists is_resident + resident_location_id + resident_location_name
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


# ------------------------------ fixtures ------------------------------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={
        "identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    }, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def two_restricted_locations(admin_headers):
    """Create two restricted locations (HOME_A, HOME_B). Yields (a, b)."""
    created = []
    for label in ("HOMEA", "HOMEB"):
        payload = {
            "name": f"TEST_Iter146_{label}_{uuid.uuid4().hex[:6]}",
            "is_restricted": True,
        }
        r = requests.post(f"{API}/locations", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code in (200, 201), f"loc create failed: {r.status_code} {r.text}"
        created.append(r.json())
    yield created[0], created[1]
    # cleanup
    for L in created:
        try:
            requests.delete(f"{API}/locations/{L['id']}", headers=admin_headers, timeout=10)
        except Exception:
            pass


@pytest.fixture(scope="module")
def resident_member_at_A(admin_headers, two_restricted_locations):
    a, _ = two_restricted_locations
    payload = {
        "name": f"TEST_Iter146 Resident {uuid.uuid4().hex[:5]}",
        "phone": f"+1555{uuid.uuid4().hex[:7]}",
        "email": f"test_iter146_{uuid.uuid4().hex[:5]}@test.local",
        "role": "Member",
        "is_resident": True,
        "resident_location_id": a["id"],
    }
    r = requests.post(f"{API}/members", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code in (200, 201), f"member create failed: {r.status_code} {r.text}"
    m = r.json()
    yield m
    try:
        requests.delete(f"{API}/members/{m['id']}", headers=admin_headers, timeout=10)
        requests.delete_one = None  # noqa
    except Exception:
        pass


@pytest.fixture(scope="module")
def checkpoint_at_B(admin_headers, two_restricted_locations):
    _, b = two_restricted_locations
    payload = {
        "name": f"TEST_Iter146 CP_B {uuid.uuid4().hex[:5]}",
        "location_id": b["id"],
        "kind": "strict",
        "device_mode": "single_device",
    }
    r = requests.post(f"{API}/security/checkpoints", json=payload,
                      headers=admin_headers, timeout=15)
    assert r.status_code in (200, 201), f"cp create failed: {r.status_code} {r.text}"
    cp = r.json()
    yield cp
    try:
        requests.delete(f"{API}/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="module")
def checkpoint_at_A(admin_headers, two_restricted_locations):
    a, _ = two_restricted_locations
    payload = {
        "name": f"TEST_Iter146 CP_A {uuid.uuid4().hex[:5]}",
        "location_id": a["id"],
        "kind": "strict",
        "device_mode": "single_device",
    }
    r = requests.post(f"{API}/security/checkpoints", json=payload,
                      headers=admin_headers, timeout=15)
    assert r.status_code in (200, 201)
    cp = r.json()
    yield cp
    try:
        requests.delete(f"{API}/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=10)
    except Exception:
        pass


def _pair_session(admin_headers, cp):
    """Pair a device session at the given checkpoint and return X-Checkpoint-Session token."""
    # Get or rotate the PIN
    pin = cp.get("pairing_pin")
    if not pin:
        r = requests.post(f"{API}/security/checkpoints/{cp['id']}/rotate-pin",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200, f"rotate-pin failed: {r.status_code} {r.text}"
        pin = r.json().get("pairing_pin")
    assert pin
    # Device claims the PIN (must include mode)
    r = requests.post(f"{API}/security/checkpoint/pair",
                      json={"pin": pin, "mode": "security"}, timeout=10)
    assert r.status_code == 200, f"pair failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


# ------------------------------ tests ------------------------------

class TestStrayHomeDetection:
    """checkpoint_scan must stamp stray_home for residents away-from-home."""

    def test_resident_at_foreign_checkpoint_gets_stray_home(
        self, admin_headers, resident_member_at_A, checkpoint_at_B, two_restricted_locations,
    ):
        a, _ = two_restricted_locations
        tok = _pair_session(admin_headers, checkpoint_at_B)
        # scan resident's id at CP_B (home is A)
        r = requests.post(
            f"{API}/security/checkpoint/scan",
            json={"scan_type": "qr", "payload": resident_member_at_A["id"]},
            headers={"X-Checkpoint-Session": tok}, timeout=15,
        )
        assert r.status_code == 200, f"scan failed: {r.status_code} {r.text}"
        body = r.json()
        # The scan response includes the event under several possible keys; tolerate.
        event = body.get("event") or body
        assert event.get("stray_home"), f"stray_home missing: {body}"
        sh = event["stray_home"]
        assert sh.get("id") == a["id"]
        assert sh.get("name") == a["name"]
        assert sh.get("is_restricted") is True

    def test_resident_at_own_checkpoint_no_stray_home(
        self, admin_headers, resident_member_at_A, checkpoint_at_A,
    ):
        tok = _pair_session(admin_headers, checkpoint_at_A)
        r = requests.post(
            f"{API}/security/checkpoint/scan",
            json={"scan_type": "qr", "payload": resident_member_at_A["id"]},
            headers={"X-Checkpoint-Session": tok}, timeout=15,
        )
        assert r.status_code == 200
        event = r.json().get("event") or r.json()
        assert event.get("stray_home") in (None, {}), f"unexpected stray_home: {event.get('stray_home')}"
        assert event.get("subject_type") == "resident", f"expected subject_type=resident, got {event.get('subject_type')}"


class TestResidentsLogEndpoints:
    """Both device-session and admin-auth residents-log return the envelope shape."""

    def test_device_residents_log_envelope(self, admin_headers, checkpoint_at_A, resident_member_at_A):
        tok = _pair_session(admin_headers, checkpoint_at_A)
        # ensure at least one resident scan exists (idempotent — TestStrayHome runs first usually)
        requests.post(
            f"{API}/security/checkpoint/scan",
            json={"scan_type": "qr", "payload": resident_member_at_A["id"]},
            headers={"X-Checkpoint-Session": tok}, timeout=15,
        )
        r = requests.get(f"{API}/security/checkpoint/residents-log",
                         headers={"X-Checkpoint-Session": tok}, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert "date" in body
        assert "rows" in body and isinstance(body["rows"], list)
        assert "counts" in body
        counts = body["counts"]
        assert "visitors_entered" in counts
        assert "residents_entered" in counts
        # include_residents flag should be False on this dedicated endpoint
        assert body.get("include_residents") is False
        # every row must be a resident-typed row
        for row in body["rows"]:
            assert row.get("subject_type") == "resident", f"non-resident row leaked: {row}"

    def test_admin_residents_log_endpoint(self, admin_headers, checkpoint_at_A):
        r = requests.get(
            f"{API}/security/checkpoints/{checkpoint_at_A['id']}/residents-log",
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert "rows" in body and "counts" in body
        assert body.get("include_residents") is False
        for row in body["rows"]:
            assert row.get("subject_type") == "resident"

    def test_admin_residents_log_requires_auth(self, checkpoint_at_A):
        r = requests.get(
            f"{API}/security/checkpoints/{checkpoint_at_A['id']}/residents-log",
            timeout=10,
        )
        assert r.status_code in (401, 403)


class TestBulkResidentBadgesAll:
    """POST /badges/auto-issue/residents with location_id='all'."""

    def test_org_wide_sweep(self, admin_headers, resident_member_at_A, two_restricted_locations):
        # reset any preexisting badge for our test member so we observe 'created'
        # (the API is idempotent; we just want to see the counts include our subject)
        r = requests.post(
            f"{API}/badges/auto-issue/residents",
            json={"location_id": "all"},
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert "total_residents" in body
        assert "created" in body and "existing" in body
        assert isinstance(body["total_residents"], int)
        assert body["total_residents"] >= 1
        # second call: same residents already exist
        r2 = requests.post(
            f"{API}/badges/auto-issue/residents",
            json={"location_id": "all"},
            headers=admin_headers, timeout=30,
        )
        assert r2.status_code == 200
        b2 = r2.json()
        # second sweep: everything should be 'existing', nothing new
        assert b2.get("created", 0) == 0, f"second sweep created badges: {b2}"
        assert b2.get("existing", 0) >= 1


class TestWalletBadgeIsResident:
    """wallet_badges issued for residents must persist is_resident + resident_location_id/name."""

    def test_wallet_badge_payload_has_resident_flags(self, admin_headers, resident_member_at_A,
                                                      two_restricted_locations):
        a, _ = two_restricted_locations
        # ensure bulk has issued the badge
        requests.post(
            f"{API}/badges/auto-issue/residents",
            json={"location_id": "all"},
            headers=admin_headers, timeout=30,
        )
        # verify directly in DB (the public listing applies a campus filter that excludes
        # bulk-issued resident badges; the spec is about what is persisted)
        import asyncio
        import sys
        if "/app/backend" not in sys.path:
            sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from motor.motor_asyncio import AsyncIOMotorClient

        async def fetch():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            return await db.wallet_badges.find_one(
                {"member_id": resident_member_at_A["id"]}, {"_id": 0},
            )

        b = asyncio.get_event_loop().run_until_complete(fetch()) \
            if asyncio.get_event_loop().is_running() is False \
            else asyncio.new_event_loop().run_until_complete(fetch())
        assert b is not None, "wallet_badge not found for resident member"
        assert b.get("is_resident") is True, f"is_resident missing in badge: {b}"
        assert b.get("resident_location_id") == a["id"], f"resident_location_id mismatch: {b}"
        assert b.get("resident_location_name") == a["name"], f"resident_location_name mismatch: {b}"


class TestSecurityCheckpointRefactorImports:
    """Refactor sanity: package + ocr_router import path must be unchanged."""

    def test_package_imports(self):
        import sys
        if "/app/backend" not in sys.path:
            sys.path.insert(0, "/app/backend")
        from routers.security_checkpoint import router, ocr_router  # noqa: F401
        from routers.security_checkpoint._common import (  # noqa: F401
            _resolve_subject, _decide, _build_visitor_log,
            _resolve_session, _hash, _broadcast_to_checkpoint, _checkpoint_rooms,
        )
        from routers.security_checkpoint.ocr import _ocr_id_image  # noqa: F401

    def test_init_under_target_size(self):
        """__init__.py was 1304 → expected ~949 after split."""
        path = "/app/backend/routers/security_checkpoint/__init__.py"
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) < 1000, f"__init__.py is {len(lines)} lines (expected <1000 after refactor)"
