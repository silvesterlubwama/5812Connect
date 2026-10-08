"""iter383 — event types CRUD, multi-day events, ticket price enforcement +
finance posting, capacity defaults, imported calendars (webcal/URL) with
per-user visibility and sharing.
"""
import os
import uuid

import requests

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:ITER383 Imported One
DTSTART:20260701T090000
DTEND:20260703T100000
LOCATION:Kampala
END:VEVENT
BEGIN:VEVENT
SUMMARY:ITER383 Imported Two
DTSTART:20260705T140000
END:VEVENT
END:VCALENDAR
"""


def _h():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _campus(h):
    return next(l["id"] for l in requests.get(f"{BASE}/api/locations", headers=h, timeout=20).json()
                if not l.get("parent_id"))


def test_event_types_crud():
    h = _h()
    label = f"ITER383 Camp {uuid.uuid4().hex[:4]}"
    made = requests.post(f"{BASE}/api/event-types", json={"name": label, "label": label, "color": "#123456"},
                         headers=h, timeout=20)
    assert made.status_code == 200, made.text
    tid = made.json()["id"]
    assert made.json()["color"] == "#123456"

    listed = requests.get(f"{BASE}/api/event-types", headers=h, timeout=20).json()
    assert any(t["id"] == tid for t in listed)

    upd = requests.put(f"{BASE}/api/event-types/{tid}", json={"label": label + " Renamed", "color": "#abcdef"},
                       headers=h, timeout=20)
    assert upd.status_code == 200 and upd.json()["color"] == "#abcdef"

    assert requests.delete(f"{BASE}/api/event-types/{tid}", headers=h, timeout=20).status_code == 200
    listed = requests.get(f"{BASE}/api/event-types", headers=h, timeout=20).json()
    assert all(t["id"] != tid for t in listed)


def test_multi_day_event_and_bad_range():
    h = _h()
    loc = _campus(h)
    ok = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER383 Conference {uuid.uuid4().hex[:4]}", "type": "conference",
        "date": "2026-07-10", "end_date": "2026-07-13", "location_id": loc,
    }, headers=h, timeout=30)
    assert ok.status_code == 200, ok.text
    ev = ok.json()
    assert ev["end_date"] == "2026-07-13"

    bad = requests.post(f"{BASE}/api/events", json={
        "title": "ITER383 Backwards", "date": "2026-07-10", "end_date": "2026-07-01", "location_id": loc,
    }, headers=h, timeout=30)
    assert bad.status_code == 400
    assert "end date" in bad.json()["detail"].lower()

    requests.delete(f"{BASE}/api/events/{ev['id']}", headers=h, timeout=20)


def test_paid_event_requires_a_price():
    h = _h()
    loc = _campus(h)
    r = requests.post(f"{BASE}/api/events", json={
        "title": "ITER383 Paid no price", "date": "2026-07-20", "location_id": loc, "is_free": False,
    }, headers=h, timeout=30)
    assert r.status_code == 400
    assert "ticket price" in r.json()["detail"].lower()

    tiered = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER383 Gala {uuid.uuid4().hex[:4]}", "date": "2026-07-21", "location_id": loc,
        "is_free": False, "ticket_tiers": [{"id": "t1", "name": "Standard", "price": 25000, "capacity": 50}],
    }, headers=h, timeout=30)
    assert tiered.status_code == 200, tiered.text
    requests.delete(f"{BASE}/api/events/{tiered.json()['id']}", headers=h, timeout=20)


def test_default_capacity_is_five_and_venue_wins():
    h = _h()
    loc = _campus(h)
    plain = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER383 Small {uuid.uuid4().hex[:4]}", "date": "2026-07-22", "location_id": loc,
    }, headers=h, timeout=30).json()
    assert plain["capacity"] == 5

    venue = requests.post(f"{BASE}/api/venues", json={
        "name": f"ITER383 Hall {uuid.uuid4().hex[:4]}", "capacity": 42, "location_id": loc,
    }, headers=h, timeout=20)
    if venue.status_code == 200:
        vid = venue.json()["id"]
        with_venue = requests.post(f"{BASE}/api/events", json={
            "title": f"ITER383 At hall {uuid.uuid4().hex[:4]}", "date": "2026-07-23",
            "location_id": loc, "venue_id": vid, "capacity": 0,
        }, headers=h, timeout=30).json()
        assert with_venue["capacity"] == 42, with_venue
        requests.delete(f"{BASE}/api/events/{with_venue['id']}", headers=h, timeout=20)
        requests.delete(f"{BASE}/api/venues/{vid}", headers=h, timeout=20)
    requests.delete(f"{BASE}/api/events/{plain['id']}", headers=h, timeout=20)


def test_ticket_sale_posts_income_to_finance():
    h = _h()
    loc = _campus(h)
    ev = requests.post(f"{BASE}/api/events", json={
        "title": f"ITER383 Ticketed {uuid.uuid4().hex[:4]}", "date": "2026-07-25", "location_id": loc,
        "is_free": False, "price": 30000, "capacity": 100, "is_public": True,
    }, headers=h, timeout=30).json()

    booking = requests.post(f"{BASE}/api/public/bookings/event", json={
        "event_id": ev["id"], "name": "ITER383 Guest", "email": "iter383@example.com",
        "phone": "0770000000", "num_tickets": 2, "payment_method": "card",
    }, timeout=30)
    assert booking.status_code == 200, booking.text
    b = booking.json()
    assert b["total"] == 60000, b

    paid = requests.put(f"{BASE}/api/public/bookings/{b['id']}/mark-paid",
                        json={"transaction_ref": "ITER383-REF"}, headers=h, timeout=60)
    assert paid.status_code == 200, paid.text
    assert paid.json()["finance_posted"] is True, paid.json().get("finance_post_error")

    entries = requests.get(f"{BASE}/api/finance/journal", params={"source": "event_ticket", "limit": 50},
                           headers=h, timeout=30).json()
    rows = entries if isinstance(entries, list) else entries.get("entries", [])
    mine = next((j for j in rows if j.get("reference") == b["id"]), None)
    assert mine, "ticket sale did not reach the ledger"
    assert round(sum(l["debit"] for l in mine["lines"]), 2) == 60000
    assert any(l["account_code"] == "4100" and l["credit"] == 60000 for l in mine["lines"])
    assert mine.get("location_id") == loc, "ticket income must book to the event's campus"

    requests.delete(f"{BASE}/api/events/{ev['id']}", headers=h, timeout=20)


def test_imported_calendar_import_share_prefs_and_delete():
    h = _h()
    name = f"ITER383 Cal {uuid.uuid4().hex[:4]}"
    imp = requests.post(f"{BASE}/api/events/import/ical",
                        json={"ical_content": ICS, "name": name}, headers=h, timeout=40)
    assert imp.status_code == 200, imp.text
    assert imp.json()["imported"] == 2
    cal = imp.json()["calendar"]
    assert cal["name"] == name

    cals = requests.get(f"{BASE}/api/events/imported-calendars", headers=h, timeout=20).json()["calendars"]
    mine = next(c for c in cals if c["id"] == cal["id"])
    assert mine["is_owner"] is True and mine["event_count"] == 2

    # multi-day DTEND is kept so an imported trip spans its days
    evs = requests.get(f"{BASE}/api/events", params={"search": "ITER383 Imported One"}, headers=h, timeout=30).json()
    assert evs and evs[0]["end_date"] == "2026-07-03"
    assert evs[0]["calendar_id"] == cal["id"]

    loc = _campus(h)
    shared = requests.put(f"{BASE}/api/events/imported-calendars/{cal['id']}/share",
                          json={"user_ids": [], "location_ids": [loc]}, headers=h, timeout=20)
    assert shared.status_code == 200
    assert shared.json()["visible_to_locations"] == [loc]

    prefs = requests.put(f"{BASE}/api/events/calendar-prefs",
                         json={"hidden_calendar_ids": [cal["id"]], "show_holidays": False},
                         headers=h, timeout=20)
    assert prefs.status_code == 200
    assert cal["id"] in prefs.json()["hidden_calendar_ids"]
    assert prefs.json()["show_holidays"] is False
    # prefs are a per-user view switch, they must not delete anything
    assert requests.get(f"{BASE}/api/events/imported-calendars", headers=h, timeout=20).json()["calendars"]
    requests.put(f"{BASE}/api/events/calendar-prefs",
                 json={"hidden_calendar_ids": [], "show_holidays": True}, headers=h, timeout=20)

    gone = requests.delete(f"{BASE}/api/events/imported-calendars/{cal['id']}", headers=h, timeout=30)
    assert gone.status_code == 200 and "2 events" in gone.json()["message"]
    left = requests.get(f"{BASE}/api/events", params={"search": "ITER383 Imported"}, headers=h, timeout=30).json()
    assert not left


def test_webcal_url_import_rejects_rubbish_links():
    h = _h()
    bad = requests.post(f"{BASE}/api/events/import/ical-url", json={"url": "not-a-link"}, headers=h, timeout=30)
    assert bad.status_code == 400
    assert "webcal" in bad.json()["detail"].lower()

    missing = requests.post(f"{BASE}/api/events/import/ical-url", json={}, headers=h, timeout=30)
    assert missing.status_code == 400
