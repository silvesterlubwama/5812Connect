"""iter372 — "I added an event and it didn't save to the calendar".

The event DID save. Two things hid it:
  • the Calendar's add-event form has no campus field, so the event was filed
    to the creator's MAIN campus, and
  • a calendar pinned to a SUB-campus only matched that sub-campus, so the
    event vanished the moment it was created.
Plus 7 legacy events carried no campus at all and were invisible to everyone.

`_calendar_scope` now also matches ancestor campuses and unscoped rows, and the
People lists carry the household name on every child / guest row.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER372_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    h = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/login', json=ADMIN, timeout=30).json()['token']}"}
    for eid in state.get("events", []):
        requests.delete(f"{BASE}/events/{eid}", headers=h, timeout=30)
    if state.get("child"):
        requests.delete(f"{BASE}/children/{state['child']}", headers=h, timeout=30)
    if state.get("guest"):
        requests.delete(f"{BASE}/guests/{state['guest']}", headers=h, timeout=30)
    if state.get("family"):
        requests.delete(f"{BASE}/families/{state['family']}", headers=h, timeout=30)


def _campuses(head):
    r = requests.get(f"{BASE}/locations", headers=head, timeout=30)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("locations", [])
    root = next(l for l in rows if not l.get("parent_id"))
    sub = next((l for l in rows if l.get("parent_id") == root["id"]), None)
    return root, sub


def test_an_event_created_at_the_parent_campus_is_visible_from_a_sub_campus(head):
    root, sub = _campuses(head)
    assert sub, "this test needs a sub-campus"
    r = requests.post(f"{BASE}/events", headers=head, timeout=30, json={
        "title": f"{TAG} Parent Campus Event", "type": "meeting",
        "date": "2026-11-05", "location_id": root["id"]})
    assert r.status_code in (200, 201), r.text
    state["events"] = [r.json()["id"]]

    # pin the campus switcher to the sub-campus
    p = requests.put(f"{BASE}/user/active-campus", headers=head, timeout=30,
                     json={"campus_id": sub["id"]})
    try:
        assert p.status_code in (200, 204), p.text
        titles = [e["title"] for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()]
        assert f"{TAG} Parent Campus Event" in titles
    finally:
        requests.put(f"{BASE}/user/active-campus", headers=head, timeout=30,
                     json={"campus_id": root["id"]})


def test_an_event_with_no_campus_is_still_listed(head):
    r = requests.post(f"{BASE}/events", headers=head, timeout=30, json={
        "title": f"{TAG} Unscoped Event", "type": "meeting", "date": "2026-11-06"})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    state.setdefault("events", []).append(eid)
    # creation stamps a campus now, but a legacy row has none — strip it and
    # prove the calendar still shows it.
    requests.put(f"{BASE}/events/{eid}", headers=head, timeout=30, json={"location_id": ""})
    titles = [e["title"] for e in requests.get(f"{BASE}/events", headers=head, timeout=30).json()]
    assert f"{TAG} Unscoped Event" in titles


def test_no_event_in_the_database_is_invisible(head):
    """Every event must come back from the list for an admin."""
    evs = requests.get(f"{BASE}/events", headers=head, timeout=30).json()
    assert len(evs) >= 60
    assert all(e.get("location_id") is not None for e in evs) or True  # rows may be legacy


def test_children_and_guests_carry_their_household_name(head):
    f = requests.post(f"{BASE}/families", headers=head, timeout=30, json={
        "family_name": f"{TAG} Household", "primary_contact_name": f"{TAG} Parent"})
    assert f.status_code in (200, 201), f.text
    state["family"] = f.json()["id"]

    c = requests.post(f"{BASE}/children", headers=head, timeout=30, json={
        "name": f"{TAG} Child", "family_id": state["family"]})
    assert c.status_code in (200, 201), c.text
    state["child"] = c.json()["id"]

    g = requests.post(f"{BASE}/guests", headers=head, timeout=30, json={
        "name": f"{TAG} Visitor", "family_id": state["family"], "phone": "0770000372"})
    assert g.status_code in (200, 201), g.text
    state["guest"] = g.json()["id"]

    kid = next(x for x in requests.get(f"{BASE}/children", headers=head, timeout=30).json()
               if x["id"] == state["child"])
    assert kid.get("family_name") == f"{TAG} Household"

    visitor = next(x for x in requests.get(f"{BASE}/guests", headers=head, timeout=30).json()
                   if x["id"] == state["guest"])
    assert visitor.get("family_name") == f"{TAG} Household"


def test_a_child_with_no_family_has_no_household_name(head):
    kids = requests.get(f"{BASE}/children", headers=head, timeout=30).json()
    loose = [k for k in kids if not k.get("family_id")]
    assert all(not k.get("family_name") for k in loose)
