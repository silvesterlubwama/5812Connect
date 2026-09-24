"""iter369 — children follow a cleared parent, and guest stays can span days.

User reports:
  • "allow issuing access badges to certain children but automatically to staff
     children to follow them to restricted locations if they are under 18 —
     so if a staff/parent has access, their child does as well"
  • "children transition to members/guests at 18, still need badge issuance"
  • "guest requests may have extended stay periods instead of just single day,
     search for existing guests/members first before adding new guest"
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
TAG = f"ITER369_{uuid.uuid4().hex[:6]}"
state = {}
TODAY = date.today()


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    for cid in (state.get("minor"), state.get("adult_child")):
        if cid:
            requests.delete(f"{BASE}/children/{cid}", headers=h, timeout=30)
    if state.get("family"):
        requests.delete(f"{BASE}/families/{state['family']}", headers=h, timeout=30)
    if state.get("staff_pass"):
        requests.delete(f"{BASE}/access/staff-passes/{state['staff_pass']}", headers=h, timeout=30)


def test_setup(head):
    # a restricted location to guard
    r = requests.get(f"{BASE}/locations", headers=head, timeout=30)
    restricted = [l for l in r.json() if l.get("is_restricted")]
    assert restricted, "need at least one restricted location in the system"
    state["loc"] = restricted[0]["id"]
    state["loc_name"] = restricted[0].get("name")

    r = requests.post(f"{BASE}/families", headers=head, timeout=30, json={
        "family_name": f"{TAG} Staff Household", "primary_contact_name": "Iter369 Parent"})
    state["family"] = r.json()["id"]

    # a minor and a grown-up "child" record
    minor_dob = TODAY.replace(year=TODAY.year - 9, day=min(TODAY.day, 28)).isoformat()
    adult_dob = TODAY.replace(year=TODAY.year - 21, day=min(TODAY.day, 28)).isoformat()
    for key, dob in (("minor", minor_dob), ("adult_child", adult_dob)):
        r = requests.post(f"{BASE}/children", headers=head, timeout=30, json={
            "name": f"{TAG} {key}", "date_of_birth": dob, "family_id": state["family"]})
        assert r.status_code == 200, r.text
        state[key] = r.json()["id"]

    # the caregiver, added through the unified family-members endpoint
    r = requests.post(f"{BASE}/children/{state['minor']}/family-members", headers=head, timeout=30,
                      json={"name": f"{TAG} Cleared Parent", "role": "Father"})
    assert r.status_code == 200, r.text
    state["parent"] = r.json()["member"]["person_id"]


def test_child_has_no_access_before_the_parent_does(head):
    r = requests.get(f"{BASE}/access/child-access/{state['minor']}", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eligible"] is False
    assert body["age"] == 9, body
    assert body["expires_on"].startswith(str(TODAY.year + 9)), body


def test_child_inherits_the_parents_staff_pass(head):
    r = requests.post(f"{BASE}/access/staff-passes", headers=head, timeout=30,
                      json={"staff_id": state["parent"], "location_id": state["loc"]})
    assert r.status_code == 200, r.text
    state["staff_pass"] = r.json()["id"]

    r = requests.get(f"{BASE}/access/child-access/{state['minor']}", headers=head, timeout=30)
    body = r.json()
    assert body["eligible"] is True, body
    assert state["loc"] in [l["location_id"] for l in body["locations"]], body
    assert body["locations"][0]["via_kind"] == "staff_pass"

    # the gate lets them in, and says who they are following
    r = requests.post(f"{BASE}/access/validate", headers=head, timeout=30,
                      json={"member_id": state["minor"], "location_id": state["loc"]})
    assert r.status_code == 200, r.text
    assert r.json()["allowed"] is True, r.text
    assert r.json()["access_type"] == "inherited_child", r.text


def test_badge_issue_now_allowed_and_carries_expiry(head):
    r = requests.post(f"{BASE}/children/{state['minor']}/wallet-badge", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    badge = r.json()
    assert badge["access_expires_on"], badge
    assert state["loc"] in badge["inherited_location_ids"], badge


def test_over_18_inherits_nothing(head):
    r = requests.get(f"{BASE}/access/child-access/{state['adult_child']}", headers=head, timeout=30)
    body = r.json()
    assert body["aged_out"] is True and body["eligible"] is False, body
    assert "18" in body["reason"], body
    r = requests.post(f"{BASE}/children/{state['adult_child']}/wallet-badge", headers=head, timeout=30)
    assert r.status_code == 403, "an 18-year-old must not inherit a badge"


def test_explicit_block_beats_inheritance(head):
    r = requests.put(f"{BASE}/access/child-access/{state['minor']}/override", headers=head, timeout=30,
                     json={"mode": "block", "reason": "court order"})
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/access/validate", headers=head, timeout=30,
                      json={"member_id": state["minor"], "location_id": state["loc"]})
    assert r.json()["allowed"] is False, r.text
    # and back to following the family
    r = requests.put(f"{BASE}/access/child-access/{state['minor']}/override", headers=head, timeout=30,
                     json={"mode": "auto"})
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/access/validate", headers=head, timeout=30,
                      json={"member_id": state["minor"], "location_id": state["loc"]})
    assert r.json()["allowed"] is True, r.text


def test_explicit_grant_without_family_access(head):
    r = requests.put(f"{BASE}/access/child-access/{state['adult_child']}/override", headers=head, timeout=30,
                     json={"mode": "grant", "location_ids": [state["loc"]], "reason": "one-off"})
    assert r.status_code == 200, r.text
    assert state["loc"] in [l["location_id"] for l in r.json()["locations"]], r.text
    r = requests.post(f"{BASE}/access/validate", headers=head, timeout=30,
                      json={"member_id": state["adult_child"], "location_id": state["loc"]})
    assert r.json()["allowed"] is True, r.text


def test_revoking_the_parent_revokes_the_child(head):
    r = requests.delete(f"{BASE}/access/staff-passes/{state['staff_pass']}", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    state["staff_pass"] = None
    r = requests.post(f"{BASE}/access/validate", headers=head, timeout=30,
                      json={"member_id": state["minor"], "location_id": state["loc"]})
    assert r.json()["allowed"] is False, "child access must die with the parent's pass"
    # the nightly re-check cleans the stored badge and reports it
    r = requests.post(f"{BASE}/access/child-access/sync-all", headers=head, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["refreshed"] >= 1, r.text


# ---------- guest requests: extended stays + search-first ----------

def test_guest_request_extended_stay(head):
    start = (TODAY + timedelta(days=2)).isoformat()
    end = (TODAY + timedelta(days=9)).isoformat()
    r = requests.post(f"{BASE}/access/guest-requests", headers=head, timeout=30, json={
        "guest_name": f"{TAG} Visitor", "guest_phone": "0770369369",
        "location_id": state["loc"], "purpose": "Extended stay",
        "visit_from": start, "visit_to": end, "visit_time": "08:00", "visit_until_time": "20:00",
    })
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["days"] == 8, req
    assert req["visit_date"] == start, "single-day clients still get visit_date"
    state["req"] = req["id"]

    r = requests.put(f"{BASE}/access/guest-requests/{req['id']}/approve", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE}/access/guest-passes", headers=head,
                     params={"location_id": state["loc"]}, timeout=30)
    passes = r.json() if isinstance(r.json(), list) else r.json().get("passes", [])
    ours = next((p for p in passes if p.get("guest_request_id") == req["id"]), None)
    assert ours, f"no pass minted for the stay: {passes[:2]}"
    assert ours["valid_from"] == start and ours["valid_until"] == end, ours
    assert ours["valid_from_time"] == "08:00" and ours["valid_until_time"] == "20:00", ours


def test_guest_request_backwards_compatible_single_day(head):
    day = (TODAY + timedelta(days=1)).isoformat()
    r = requests.post(f"{BASE}/access/guest-requests", headers=head, timeout=30, json={
        "guest_name": f"{TAG} One Day", "location_id": state["loc"], "visit_date": day})
    assert r.status_code == 200, r.text
    assert r.json()["visit_from"] == day and r.json()["visit_to"] == day
    assert r.json()["days"] == 1


def test_guest_request_rejects_backwards_range(head):
    r = requests.post(f"{BASE}/access/guest-requests", headers=head, timeout=30, json={
        "guest_name": f"{TAG} Bad Range", "location_id": state["loc"],
        "visit_from": (TODAY + timedelta(days=5)).isoformat(), "visit_to": TODAY.isoformat()})
    assert r.status_code == 400, r.text


def test_guest_request_links_an_existing_profile(head):
    r = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30,
                     params={"q": "adm", "kinds": "user,member,guest"})
    people = r.json()["people"]
    assert people, "need somebody to link to"
    p = people[0]
    r = requests.post(f"{BASE}/access/guest-requests", headers=head, timeout=30, json={
        "person_id": p["id"], "person_type": p["type"], "location_id": state["loc"],
        "visit_from": TODAY.isoformat(), "visit_to": TODAY.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["person_id"] == p["id"] and body["guest_name"] == p["name"], body

    r = requests.put(f"{BASE}/access/guest-requests/{body['id']}/approve", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE}/access/guest-passes", headers=head,
                     params={"location_id": state["loc"]}, timeout=30)
    passes = r.json() if isinstance(r.json(), list) else r.json().get("passes", [])
    ours = next((x for x in passes if x.get("guest_request_id") == body["id"]), None)
    assert ours and ours["existing_member_id"] == p["id"], ours


def test_guest_request_needs_a_name(head):
    r = requests.post(f"{BASE}/access/guest-requests", headers=head, timeout=30, json={
        "location_id": state["loc"], "visit_from": TODAY.isoformat()})
    assert r.status_code == 400, r.text
