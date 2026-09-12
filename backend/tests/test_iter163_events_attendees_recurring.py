"""Iteration 163 tests:
1) GET /api/events/{id} attendees merging from db.public_bookings + db.event_registrations.
2) POST /api/events/generate-recurring producing correct counts (was bugging at 1).
"""
import os
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.strip().startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL not configured"
    return v.rstrip("/")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok, f"no token in login response: {body}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_event(headers):
    """Create a test event for attendee tests."""
    payload = {
        "title": f"TEST_iter163_event_{uuid.uuid4().hex[:6]}",
        "type": "service",
        "date": "2030-06-15",
        "time": "10:00",
        "end_time": "12:00",
        "location": "Test Hall",
        "capacity": 100,
        "is_public": True,
        "is_free": True,
        "visibility": "external",
        "description": "Test event for iter163",
    }
    r = requests.post(f"{BASE_URL}/api/events", json=payload, headers=headers, timeout=30)
    assert r.status_code in (200, 201), f"create event failed: {r.status_code} {r.text}"
    ev = r.json()
    assert ev.get("id"), ev
    yield ev
    # teardown — delete event
    try:
        requests.delete(f"{BASE_URL}/api/events/{ev['id']}", headers=headers, timeout=15)
    except Exception:
        pass


# ============ Bug 1: Attendees visibility from public_bookings =============

class TestAttendeesVisibility:
    def test_public_booking_appears_in_attendees(self, headers, created_event):
        eid = created_event["id"]
        booking_payload = {
            "event_id": eid,
            "name": "Iter163 Tester One",
            "email": "iter163_one@e2e.test",
            "phone": "+256700000001",
            "num_tickets": 2,
        }
        r = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking_payload, timeout=30)
        assert r.status_code == 200, f"public booking failed: {r.status_code} {r.text}"
        booking = r.json()
        assert booking.get("status") == "confirmed", booking
        # Now fetch the event and check attendees array
        r2 = requests.get(f"{BASE_URL}/api/events/{eid}", headers=headers, timeout=30)
        assert r2.status_code == 200, r2.text
        ev = r2.json()
        assert "attendees" in ev, "attendees key missing"
        assert ev.get("attendee_count", 0) >= 1, f"attendee_count not updated: {ev.get('attendee_count')}"
        # Find our attendee
        ours = [a for a in ev["attendees"] if a.get("email") == "iter163_one@e2e.test"]
        assert len(ours) == 1, f"attendee not present once: {ours}"
        a = ours[0]
        # Shape verification
        for field in ("name", "email", "phone", "status", "num_tickets", "created_at", "source"):
            assert field in a, f"field '{field}' missing in attendee row {a}"
        assert a["source"] == "public_booking"
        assert a["num_tickets"] == 2
        assert a["status"] == "confirmed"
        # registered counter auto-sync
        assert ev.get("registered", 0) >= 2, f"registered counter not synced: {ev.get('registered')}"

    def test_cancelled_booking_excluded(self, headers, created_event):
        eid = created_event["id"]
        # Create another booking
        bp = {
            "event_id": eid,
            "name": "Iter163 Cancelled",
            "email": "iter163_cancel@e2e.test",
            "phone": "+256700000002",
            "num_tickets": 1,
        }
        r = requests.post(f"{BASE_URL}/api/public/bookings/event", json=bp, timeout=30)
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        # Manually mark it cancelled via direct DB query path —
        # Use admin update endpoint if available; else use Mongo via a helper.
        # We'll try the bookings admin endpoint:
        update = requests.put(
            f"{BASE_URL}/api/public-bookings/{bid}",
            json={"status": "cancelled"}, headers=headers, timeout=15,
        )
        # Fallback: try alternate endpoint paths if 404
        if update.status_code == 404:
            update = requests.put(
                f"{BASE_URL}/api/bookings/{bid}",
                json={"status": "cancelled"}, headers=headers, timeout=15,
            )
        # If neither works, we use direct DB via a helper endpoint or skip
        if update.status_code not in (200, 204):
            pytest.skip(f"No public endpoint to cancel a booking ({update.status_code}); skipping cancel-exclude check")
        r2 = requests.get(f"{BASE_URL}/api/events/{eid}", headers=headers, timeout=30)
        ev = r2.json()
        cancelled_visible = [a for a in ev["attendees"] if a.get("email") == "iter163_cancel@e2e.test"]
        assert len(cancelled_visible) == 0, "cancelled booking should not be in attendees"


# ============ Bug 2: generate-recurring producing correct counts =============

class TestGenerateRecurring:
    created_ids = []

    @classmethod
    def teardown_class(cls):
        # Best-effort cleanup of TEST_iter163_recur events via list+delete
        try:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=20)
            tok = r.json().get("token") or r.json().get("access_token")
            h = {"Authorization": f"Bearer {tok}"}
            for eid in cls.created_ids:
                requests.delete(f"{BASE_URL}/api/events/{eid}", headers=h, timeout=10)
        except Exception:
            pass

    def _gen(self, headers, **kwargs):
        payload = {
            "title": f"TEST_iter163_recur_{uuid.uuid4().hex[:6]}",
            "type": "service",
            "time": "10:00",
            "capacity": 50,
            "is_public": True,
            **kwargs,
        }
        r = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=headers, timeout=60)
        assert r.status_code == 200, f"generate failed: {r.status_code} {r.text}"
        body = r.json()
        for ev in body.get("events", []):
            self.created_ids.append(ev["id"])
        return body

    def test_weekly_10_no_enddate(self, headers):
        body = self._gen(headers, pattern="weekly", occurrences=10, start_date="2030-01-06")
        assert body["created"] == 10, f"expected 10 weekly events, got {body['created']}"

    def test_monthly_6_with_5month_enddate(self, headers):
        # start 2030-02-01, end 2030-07-15 → 6 monthly events (Feb, Mar, Apr, May, Jun, Jul)
        body = self._gen(headers, pattern="monthly", occurrences=6,
                         start_date="2030-02-01", end_date="2030-07-15")
        assert body["created"] == 6, f"expected 6 monthly events, got {body['created']}"

    def test_enddate_before_startdate_returns_zero(self, headers):
        body = self._gen(headers, pattern="weekly", occurrences=10,
                         start_date="2030-06-01", end_date="2030-05-01")
        assert body["created"] == 0, f"expected 0 events when end<start, got {body['created']}"

    def test_daily_5_regression(self, headers):
        body = self._gen(headers, pattern="daily", occurrences=5, start_date="2030-03-01")
        assert body["created"] == 5, f"expected 5 daily events, got {body['created']}"

    def test_monthly_too_close_returns_one_bug_fingerprint(self, headers):
        # start=2030-04-01, end=2030-04-15 (less than a month) → only 1 event
        body = self._gen(headers, pattern="monthly", occurrences=12,
                         start_date="2030-04-01", end_date="2030-04-15")
        assert body["created"] == 1, f"expected 1 event (end too close), got {body['created']}"
