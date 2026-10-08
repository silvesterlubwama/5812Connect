"""iter384 — platform crons: event reminders the day before, subscribed
calendar sync, plus the opportunistic sync the calendar page calls on open.
"""
import datetime
import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")


def _h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cron_headers(run_id):
    return {"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
            "X-Webhook-Id": run_id}


def test_cron_endpoints_reject_bad_auth():
    for path in ("event-reminders", "calendar-sync"):
        assert requests.post(f"{BASE}/api/cron/{path}", json={}, timeout=20).status_code == 401
        bad = requests.post(f"{BASE}/api/cron/{path}", json={},
                            headers={"Authorization": "Bearer nope"}, timeout=20)
        assert bad.status_code == 401


def test_cron_delivery_is_idempotent():
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    first = requests.post(f"{BASE}/api/cron/calendar-sync", headers=_cron_headers(run_id),
                          json={"run_id": run_id}, timeout=30)
    assert first.status_code == 200 and first.json()["accepted"] is True
    assert not first.json().get("duplicate")
    again = requests.post(f"{BASE}/api/cron/calendar-sync", headers=_cron_headers(run_id),
                          json={"run_id": run_id}, timeout=30)
    assert again.json().get("duplicate") is True


def test_reminder_goes_to_ticket_holders_once():
    import time
    h = _h()
    loc = next(l["id"] for l in requests.get(f"{BASE}/api/locations", headers=h, timeout=20).json()
               if not l.get("parent_id"))
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    ev = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER384 Reminder Gala {uuid.uuid4().hex[:4]}", "date": tomorrow, "time": "18:00",
        "location_id": loc, "is_public": True, "is_free": False, "price": 10000, "capacity": 50,
    }, headers=h, timeout=30).json()
    booking = requests.post(f"{BASE}/api/public/bookings/event", json={
        "event_id": ev["id"], "name": "ITER384 Guest", "email": "admin@5812uganda.org",
        "phone": "0770000003", "num_tickets": 2, "payment_method": "card",
    }, timeout=30).json()
    try:
        assert booking.get("id")

        run_id = f"run_{uuid.uuid4().hex[:10]}"
        r = requests.post(f"{BASE}/api/cron/event-reminders", headers=_cron_headers(run_id),
                          json={"run_id": run_id}, timeout=30)
        assert r.status_code == 200 and r.json()["accepted"] is True

        sent_at = None
        for _ in range(12):
            time.sleep(2)
            rows = requests.get(f"{BASE}/api/public/bookings/status",
                                params={"booking_id": booking["id"]}, timeout=30).json()
            row = rows[0] if rows else None
            if row and row.get("reminder_sent_at"):
                sent_at = row["reminder_sent_at"]
                break
        assert sent_at, "ticket holder never got flagged as reminded"

        # A second run must not pester the same person again.
        run2 = f"run_{uuid.uuid4().hex[:10]}"
        requests.post(f"{BASE}/api/cron/event-reminders", headers=_cron_headers(run2),
                      json={"run_id": run2}, timeout=30)
        time.sleep(6)
        row = requests.get(f"{BASE}/api/public/bookings/status",
                           params={"booking_id": booking["id"]}, timeout=30).json()[0]
        assert row["reminder_sent_at"] == sent_at, "reminder was sent twice"
    finally:
        # Always tear the event down, even when an assert above fails, so the
        # customer's calendar doesn't collect QA galas.
        requests.delete(f"{BASE}/api/events/{ev['id']}", headers=h, timeout=20)


def test_opportunistic_sync_endpoint_is_safe_when_nothing_is_stale():
    h = _h()
    r = requests.post(f"{BASE}/api/events/imported-calendars/sync-stale", headers=h, timeout=90)
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"refreshed", "events", "errors"}


def test_drag_move_keeps_duration_and_rejects_bad_resize():
    """What the drag-and-drop writes: a moved run keeps its length, and the
    right-edge drag can never end before the start."""
    h = _h()
    loc = next(l["id"] for l in requests.get(f"{BASE}/api/locations", headers=h, timeout=20).json()
               if not l.get("parent_id"))
    ev = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER384 Drag {uuid.uuid4().hex[:4]}", "date": "2026-09-07",
        "end_date": "2026-09-09", "location_id": loc,
    }, headers=h, timeout=30).json()

    moved = requests.put(f"{BASE}/api/events/{ev['id']}",
                         json={"date": "2026-09-14", "end_date": "2026-09-16"}, headers=h, timeout=30)
    assert moved.status_code == 200, moved.text
    assert moved.json()["date"] == "2026-09-14" and moved.json()["end_date"] == "2026-09-16"

    stretched = requests.put(f"{BASE}/api/events/{ev['id']}", json={"end_date": "2026-09-20"},
                             headers=h, timeout=30)
    assert stretched.status_code == 200 and stretched.json()["end_date"] == "2026-09-20"

    bad = requests.put(f"{BASE}/api/events/{ev['id']}", json={"end_date": "2026-09-01"},
                       headers=h, timeout=30)
    assert bad.status_code == 400
    assert "end date" in bad.json()["detail"].lower()

    requests.delete(f"{BASE}/api/events/{ev['id']}", headers=h, timeout=20)
