"""iter373 — a repeating event is one series, not a pile of look-alikes.

The generator already existed (Calendar → More → Recurring events) but every
occurrence was a standalone row with nothing tying it to the others, so the run
could not be edited or removed except one date at a time.

Now `POST /events/generate-recurring` stamps a shared `series_id`, and
`PUT/DELETE /events/{id}` take `scope=single|future|series`.
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER373_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    h = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/login', json=ADMIN, timeout=30).json()['token']}"}
    for eid in state.get("ids", []):
        requests.delete(f"{BASE}/events/{eid}", headers=h, timeout=30)


def _start():
    return (date.today() + timedelta(days=3)).isoformat()


def test_a_weekly_run_shares_one_series_id(head):
    r = requests.post(f"{BASE}/events/generate-recurring", headers=head, timeout=60, json={
        "title": f"{TAG} Weekly Club", "type": "outreach", "pattern": "weekly",
        "start_date": _start(), "occurrences": 5, "time": "14:00", "end_time": "16:00",
        "location": "Magoggo",
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["created"] == 5
    assert body["series_id"].startswith("ser_")
    state["series"] = body["series_id"]
    state["ids"] = [e["id"] for e in body["events"]]
    assert {e["series_id"] for e in body["events"]} == {body["series_id"]}
    # a week apart, in order, never in the past
    dates = sorted(e["date"] for e in body["events"])
    assert dates[0] >= date.today().isoformat()
    for a, b in zip(dates, dates[1:]):
        assert (date.fromisoformat(b) - date.fromisoformat(a)).days == 7


def test_editing_one_date_leaves_the_rest_alone(head):
    first = sorted(state["ids"], key=lambda i: i)
    target = state["ids"][0]
    r = requests.put(f"{BASE}/events/{target}", headers=head, timeout=30, json={"time": "09:00"})
    assert r.status_code == 200, r.text
    assert r.json()["time"] == "09:00"
    others = [e for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()
              if e.get("series_id") == state["series"] and e["id"] != target]
    assert others and all(e["time"] == "14:00" for e in others)
    assert first  # keeps the linter honest about the unused sort


def test_this_and_all_later_dates_travel_together(head):
    rows = sorted([e for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()
                   if e.get("series_id") == state["series"]], key=lambda e: e["date"])
    third = rows[2]
    r = requests.put(f"{BASE}/events/{third['id']}?scope=future", headers=head, timeout=30,
                     json={"time": "18:30", "location": "New Hall"})
    assert r.status_code == 200, r.text
    assert r.json()["series_updated"] == 3          # the 3rd, 4th and 5th

    after = sorted([e for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()
                    if e.get("series_id") == state["series"]], key=lambda e: e["date"])
    assert [e["time"] for e in after[2:]] == ["18:30", "18:30", "18:30"]
    assert after[1]["time"] == "14:00"              # an earlier date is untouched
    # each occurrence keeps its OWN date
    assert len({e["date"] for e in after}) == len(after)


def test_deleting_this_and_all_later_dates(head):
    rows = sorted([e for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()
                   if e.get("series_id") == state["series"]], key=lambda e: e["date"])
    r = requests.delete(f"{BASE}/events/{rows[3]['id']}?scope=future", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    left = [e for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()
            if e.get("series_id") == state["series"]]
    assert len(left) == 3
    state["ids"] = [e["id"] for e in left]


def test_a_lone_event_is_unaffected_by_the_scope_param(head):
    r = requests.post(f"{BASE}/events", headers=head, timeout=30, json={
        "title": f"{TAG} One Off", "type": "meeting", "date": _start()})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    assert not r.json().get("series_id")
    u = requests.put(f"{BASE}/events/{eid}?scope=future", headers=head, timeout=30, json={"time": "11:00"})
    assert u.status_code == 200 and u.json()["series_updated"] == 1
    d = requests.delete(f"{BASE}/events/{eid}?scope=future", headers=head, timeout=30)
    assert d.status_code == 200 and d.json()["deleted"] == 1


def test_a_bad_scope_is_rejected(head):
    r = requests.delete(f"{BASE}/events/{state['ids'][0]}?scope=everything", headers=head, timeout=30)
    assert r.status_code == 422


# iter378 — the Repeats form now exposes the richer patterns the generator
# always supported: yearly, every 2/3 months, the Nth weekday of a month, a set
# day each month, and certain days each week.
@pytest.mark.parametrize("pattern,extra,expect", [
    ("yearly", {}, ["2027-10-05", "2028-10-05"]),
    ("nth_month", {"day_of_month": 15}, ["2026-10-15", "2026-11-15"]),
    ("quarterly", {}, ["2027-01-05", "2027-04-05"]),
])
def test_the_richer_patterns_land_on_the_right_dates(head, pattern, extra, expect):
    r = requests.post(f"{BASE}/events/generate-recurring", headers=head, timeout=60, json={
        "title": f"{TAG} {pattern}", "type": "meeting", "pattern": pattern,
        "start_date": "2026-10-05", "occurrences": 4, **extra})
    assert r.status_code in (200, 201), r.text
    dates = [e["date"] for e in r.json()["events"]]
    state.setdefault("ids", []).extend(e["id"] for e in r.json()["events"])
    for d in expect:
        assert d in dates, f"{pattern} produced {dates}"


def test_nth_weekday_of_the_month(head):
    """Second Wednesday, month after month."""
    r = requests.post(f"{BASE}/events/generate-recurring", headers=head, timeout=60, json={
        "title": f"{TAG} nth_week", "type": "meeting", "pattern": "nth_week",
        "start_date": "2026-10-05", "occurrences": 3, "day_of_week": 2, "nth_week": 2})
    assert r.status_code in (200, 201), r.text
    rows = r.json()["events"]
    state.setdefault("ids", []).extend(e["id"] for e in rows)
    from datetime import date as _date
    for e in rows:
        d = _date.fromisoformat(e["date"])
        assert d.weekday() == 2, f"{e['date']} is not a Wednesday"
        assert 8 <= d.day <= 14, f"{e['date']} is not the SECOND Wednesday"


def test_certain_days_each_week(head):
    r = requests.post(f"{BASE}/events/generate-recurring", headers=head, timeout=60, json={
        "title": f"{TAG} custom_weekly", "type": "meeting", "pattern": "custom_weekly",
        "start_date": "2026-10-05", "occurrences": 4, "days_of_week": [0, 3]})
    assert r.status_code in (200, 201), r.text
    rows = r.json()["events"]
    state.setdefault("ids", []).extend(e["id"] for e in rows)
    from datetime import date as _date
    assert {_date.fromisoformat(e["date"]).weekday() for e in rows} == {0, 3}
    # one series, so the whole run can still be removed in one go
    assert len({e["series_id"] for e in rows}) == 1
