"""Iteration 141 — Security Checkpoint unification with Check-in.

Tests:
- kind (strict/hybrid/check_in_only) + device_mode (dual_device/single_device) CRUD
- Single-device + guest mode pair rejection
- Event ticket (TKT-XXXX) scan resolution and hybrid/strict decision branches
- Hybrid event-ticket scan inserts db.checkins row
- Entry/exit pairing via find_one_and_update + exit_event_id
- Visitor-log device + admin endpoints
- Household lookup
- Batch check-in
- check_in_only mode approves any active subject
"""
import os
import time
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
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


# ----- shared fixtures -----
@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def location_id(admin_headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    locs = r.json()
    if isinstance(locs, dict):
        locs = locs.get("locations") or locs.get("items") or []
    assert locs
    return locs[0]["id"]


def _create_checkpoint(admin_headers, location_id, kind="strict", device_mode="dual_device", name=None):
    body = {
        "name": name or f"TEST_Iter141_{kind}_{device_mode}_{uuid.uuid4().hex[:6]}",
        "location_id": location_id,
        "kind": kind,
        "device_mode": device_mode,
    }
    r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _pair(pin, mode="security"):
    r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair", json={"pin": pin, "mode": mode}, timeout=20)
    return r


# ============================================================
# 1. kind + device_mode CRUD
# ============================================================
class TestCheckpointKindAndDeviceMode:
    def test_create_with_kind_and_device_mode(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id, "hybrid", "single_device")
        assert cp["kind"] == "hybrid"
        assert cp["device_mode"] == "single_device"
        # cleanup
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_create_defaults_when_omitted(self, admin_headers, location_id):
        body = {"name": f"TEST_Iter141_defaults_{uuid.uuid4().hex[:6]}", "location_id": location_id}
        r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
        assert r.status_code == 200
        cp = r.json()
        assert cp["kind"] == "strict"
        assert cp["device_mode"] == "dual_device"
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_create_invalid_kind_400(self, admin_headers, location_id):
        body = {"name": "TEST_Iter141_badkind", "location_id": location_id, "kind": "lenient"}
        r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
        assert r.status_code == 400

    def test_create_invalid_device_mode_400(self, admin_headers, location_id):
        body = {"name": "TEST_Iter141_baddm", "location_id": location_id, "device_mode": "triple_device"}
        r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
        assert r.status_code == 400

    def test_put_updates_kind_and_device_mode(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id, "strict", "dual_device")
        r = requests.put(
            f"{BASE_URL}/api/security/checkpoints/{cp['id']}",
            headers=admin_headers,
            json={"kind": "check_in_only", "device_mode": "single_device"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        upd = r.json()
        assert upd["kind"] == "check_in_only"
        assert upd["device_mode"] == "single_device"
        # bad update value
        bad = requests.put(
            f"{BASE_URL}/api/security/checkpoints/{cp['id']}",
            headers=admin_headers,
            json={"kind": "bogus"},
            timeout=20,
        )
        assert bad.status_code == 400
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 2. Single-device pair restriction
# ============================================================
class TestSingleDevicePair:
    def test_single_device_guest_mode_rejected(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id, "hybrid", "single_device")
        r = _pair(cp["pairing_pin"], mode="guest")
        assert r.status_code == 400
        assert "single-device" in r.json().get("detail", "").lower()
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_single_device_security_mode_ok(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id, "hybrid", "single_device")
        r = _pair(cp["pairing_pin"], mode="security")
        assert r.status_code == 200, r.text[:200]
        assert "session_token" in r.json()
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_dual_device_guest_mode_ok(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id, "strict", "dual_device")
        r = _pair(cp["pairing_pin"], mode="guest")
        assert r.status_code == 200, r.text[:200]
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 3. Event ticket scan (TKT-XXXX)
# ============================================================
@pytest.fixture(scope="module")
def event_with_ticket(admin_headers):
    """Create an event and a public booking → returns (event_id, ticket_id)."""
    ev_payload = {
        "title": f"TEST_Iter141_Event_{uuid.uuid4().hex[:6]}",
        "type": "service",
        "date": "2026-12-31",
        "time": "10:00",
        "location": "Test Hall",
        "capacity": 100,
        "is_public": True,
        "is_free": True,
    }
    r = requests.post(f"{BASE_URL}/api/events", headers=admin_headers, json=ev_payload, timeout=20)
    if r.status_code not in (200, 201):
        pytest.skip(f"Cannot create event: {r.status_code} {r.text[:200]}")
    ev = r.json()
    event_id = ev.get("id") or ev.get("event_id")
    # Try public booking endpoints
    name = f"TEST_Iter141_Guest_{uuid.uuid4().hex[:6]}"
    booking_payload = {
        "event_id": event_id,
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@test.example",
        "phone": f"+25670{int(time.time()) % 10000000:07d}",
        "num_tickets": 1,
        "agreed_to_terms": True,
    }
    ticket_id = None
    for url in [
        f"{BASE_URL}/api/public/bookings/event",
    ]:
        rr = requests.post(url, json=booking_payload, timeout=20)
        if rr.status_code in (200, 201):
            data = rr.json()
            tids = data.get("ticket_ids") or (data.get("booking") or {}).get("ticket_ids") or []
            if tids:
                ticket_id = tids[0]
                break
    if not ticket_id:
        pytest.skip("Could not create a public booking with ticket_ids for ticket scan tests")
    yield {"event_id": event_id, "ticket_id": ticket_id, "title": ev_payload["title"]}


class TestEventTicketScan:
    def test_hybrid_ticket_scan_approved_and_creates_checkin(self, admin_headers, location_id, event_with_ticket):
        cp = _create_checkpoint(admin_headers, location_id, "hybrid", "dual_device")
        pair = _pair(cp["pairing_pin"], mode="security")
        assert pair.status_code == 200
        sess = pair.json()["session_token"]
        # scan
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": sess},
            json={"scan_type": "qr", "payload": event_with_ticket["ticket_id"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        ev = r.json()
        assert ev["subject"]["kind"] == "event_ticket"
        assert ev["subject"].get("event_id") == event_with_ticket["event_id"]
        assert ev["decision"] == "approved"
        # Verify a db.checkins row exists on /api/check-ins or check-ins
        time.sleep(0.4)
        chk_url = None
        for u in [f"{BASE_URL}/api/check-ins", f"{BASE_URL}/api/checkins"]:
            cr = requests.get(u, headers=admin_headers, timeout=20)
            if cr.status_code == 200:
                chk_url = u
                rows = cr.json()
                if isinstance(rows, dict):
                    rows = rows.get("checkins") or rows.get("items") or []
                matched = [x for x in rows if x.get("ticket_id") == event_with_ticket["ticket_id"]]
                assert matched, f"No checkin row for ticket {event_with_ticket['ticket_id']} via {u}"
                assert matched[0].get("method") == "security_checkpoint"
                assert matched[0].get("type") == "event_ticket"
                break
        assert chk_url, "Neither /api/check-ins nor /api/checkins returned 200"
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_strict_ticket_scan_denied(self, admin_headers, location_id, event_with_ticket):
        cp = _create_checkpoint(admin_headers, location_id, "strict", "dual_device")
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": sess},
            json={"scan_type": "qr", "payload": event_with_ticket["ticket_id"]},
            timeout=20,
        )
        assert r.status_code == 200
        ev = r.json()
        assert ev["subject"]["kind"] == "event_ticket"
        assert ev["decision"] == "denied"
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 4. Entry/exit pairing
# ============================================================
@pytest.fixture(scope="module")
def test_member(admin_headers):
    body = {
        "name": f"TEST_Iter141_Mem_{uuid.uuid4().hex[:6]}",
        "phone": f"+25670{int(time.time()) % 10000000:07d}",
        "email": f"iter141_{uuid.uuid4().hex[:8]}@test.example",
        "role": "Director",  # privileged so passes _decide
    }
    r = requests.post(f"{BASE_URL}/api/members", headers=admin_headers, json=body, timeout=20)
    assert r.status_code in (200, 201), r.text[:200]
    m = r.json()
    yield m
    requests.delete(f"{BASE_URL}/api/members/{m['id']}", headers=admin_headers, timeout=20)


class TestEntryExitPairing:
    def test_double_scan_creates_entry_then_exit(self, admin_headers, location_id, test_member):
        cp = _create_checkpoint(admin_headers, location_id, "check_in_only", "single_device")
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        headers = {"X-Checkpoint-Session": sess}
        # 1st scan = entry
        r1 = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers=headers,
            json={"scan_type": "qr", "payload": test_member["id"]},
            timeout=20,
        )
        assert r1.status_code == 200
        entry = r1.json()
        assert entry["direction"] == "entry"
        assert entry["decision"] == "approved", f"entry denied: {entry.get('reason')} subject={entry.get('subject')}"
        # 2nd scan = exit
        time.sleep(0.5)
        r2 = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers=headers,
            json={"scan_type": "qr", "payload": test_member["id"]},
            timeout=20,
        )
        assert r2.status_code == 200
        exit_ev = r2.json()
        assert exit_ev["direction"] == "exit"
        # Now check visitor-log: entry row should have exit_at + exit_event_id set + still_inside False
        time.sleep(0.3)
        vl = requests.get(
            f"{BASE_URL}/api/security/checkpoint/visitor-log",
            headers=headers,
            timeout=20,
        )
        assert vl.status_code == 200
        # New shape (iter 145): {date, rows, counts, include_residents}
        envelope = vl.json()
        rows = envelope.get("rows") if isinstance(envelope, dict) else envelope
        # Test member doesn't have is_resident set → should appear in default visitor view
        match = [x for x in rows if x.get("subject_id") == test_member["id"]]
        if not match:
            # Or via the include_residents=true view if the test seeded a resident
            vl2 = requests.get(
                f"{BASE_URL}/api/security/checkpoint/visitor-log?include_residents=true",
                headers=headers, timeout=20,
            )
            assert vl2.status_code == 200
            env2 = vl2.json()
            rows = env2.get("rows") if isinstance(env2, dict) else env2
            match = [x for x in rows if x.get("subject_id") == test_member["id"]]
        assert match, "no visitor-log row for test member"
        row = match[-1]
        assert row.get("exit_event_id") == exit_ev["id"], f"exit_event_id mismatch: {row}"
        assert row.get("exit_at"), "exit_at not set on entry row"
        assert row.get("still_inside") is False
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 5. Visitor-log endpoints
# ============================================================
class TestVisitorLog:
    def test_device_visitor_log_unauth(self):
        r = requests.get(f"{BASE_URL}/api/security/checkpoint/visitor-log", timeout=20)
        assert r.status_code == 401

    def test_admin_visitor_log_shape(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id)
        r = requests.get(
            f"{BASE_URL}/api/security/checkpoints/{cp['id']}/visitor-log",
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200
        # New shape (iter 145): envelope {date, rows, counts, include_residents}
        body = r.json()
        assert isinstance(body, dict)
        assert "rows" in body and "counts" in body
        # with date param
        r2 = requests.get(
            f"{BASE_URL}/api/security/checkpoints/{cp['id']}/visitor-log?date=2026-01-01",
            headers=admin_headers,
            timeout=20,
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert isinstance(body2, dict)
        assert "rows" in body2
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 6. Lookup
# ============================================================
class TestLookup:
    def test_lookup_requires_session(self):
        r = requests.post(f"{BASE_URL}/api/security/checkpoint/lookup", json={"q": "ab"}, timeout=20)
        assert r.status_code == 401

    def test_lookup_short_query_400(self, admin_headers, location_id):
        cp = _create_checkpoint(admin_headers, location_id)
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/lookup",
            headers={"X-Checkpoint-Session": sess},
            json={"q": "a"},
            timeout=20,
        )
        assert r.status_code == 400
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)

    def test_lookup_returns_members_with_household(self, admin_headers, location_id, test_member):
        cp = _create_checkpoint(admin_headers, location_id)
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        # search by part of name
        q = test_member["name"][:8]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/lookup",
            headers={"X-Checkpoint-Session": sess},
            json={"q": q},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "results" in data
        assert data["count"] >= 1
        # each result has household array
        found = [x for x in data["results"] if x["id"] == test_member["id"]]
        assert found, "test member not in lookup results"
        assert "household" in found[0]
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 7. Batch check-in
# ============================================================
class TestBatchCheckIn:
    def test_batch_check_in_writes_events_and_checkins(self, admin_headers, location_id, test_member):
        cp = _create_checkpoint(admin_headers, location_id, "check_in_only", "single_device")
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/check-in-batch",
            headers={"X-Checkpoint-Session": sess},
            json={"members": [{"kind": "member", "id": test_member["id"]}]},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data["checked_in"] == 1
        assert len(data["events"]) == 1
        ev = data["events"][0]
        assert ev["scan_type"] == "manual_household"
        assert ev["decision"] == "approved"
        # missing/empty members → 400
        r2 = requests.post(
            f"{BASE_URL}/api/security/checkpoint/check-in-batch",
            headers={"X-Checkpoint-Session": sess},
            json={"members": []},
            timeout=20,
        )
        assert r2.status_code == 400
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


# ============================================================
# 8. check_in_only mode approves active subjects
# ============================================================
class TestCheckInOnlyMode:
    def test_active_member_approved_without_location_check(self, admin_headers, location_id, test_member):
        # Create a check_in_only checkpoint at a DIFFERENT location-less context (location_id still set,
        # but kind=check_in_only should bypass the restricted-loc gate)
        cp = _create_checkpoint(admin_headers, location_id, "check_in_only", "dual_device")
        sess = _pair(cp["pairing_pin"], "security").json()["session_token"]
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan",
            headers={"X-Checkpoint-Session": sess},
            json={"scan_type": "qr", "payload": test_member["id"]},
            timeout=20,
        )
        assert r.status_code == 200
        ev = r.json()
        assert ev["decision"] == "approved", f"denied: {ev.get('reason')} subj={ev.get('subject')}"
        assert "check-in only" in ev["reason"].lower() or "no access restriction" in ev["reason"].lower()
        requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)
