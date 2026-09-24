"""iter371 — search-first on the last free-text person fields.

Phase 4 of "change most editing lines to first allow type searching before
adding new data": the Add Person / Add Child / Record Guest / Add Family forms
now look a person up before creating one, and the POS customer box uses the
same shared picker — which means `/people/suggest` must also be able to return
existing CUSTOMER accounts (opt-in, so the family pickers stay people-only).
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER371{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    h = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/login', json=ADMIN, timeout=30).json()['token']}"}
    for guest in state.get("guests", []):
        requests.delete(f"{BASE}/guests/{guest}", headers=h, timeout=30)
    if state.get("family"):
        requests.delete(f"{BASE}/families/{state['family']}", headers=h, timeout=30)


def test_seed_a_guest_and_a_customer(head):
    g = requests.post(f"{BASE}/guests", headers=head, timeout=30, json={
        "name": f"{TAG} Visitor", "phone": "0770000371", "email": f"{TAG.lower()}@ex.org"})
    assert g.status_code in (200, 201), g.text
    state["guests"] = [g.json()["id"]]
    state["guest_name"] = g.json()["name"]

    c = requests.post(f"{BASE}/customers", headers=head, timeout=30,
                      json={"name": f"{TAG} Shopper", "phone": "0770000372"})
    assert c.status_code in (200, 201), c.text
    state["customer"] = c.json()["id"]


def test_suggest_finds_the_guest(head):
    r = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30,
                     params={"q": TAG, "kinds": "guest,member,user"})
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["people"]}
    assert state["guest_name"] in names


def test_customers_are_not_returned_unless_asked_for(head):
    r = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30,
                     params={"q": TAG, "kinds": "guest,member,user,child"})
    assert r.status_code == 200
    assert not [p for p in r.json()["people"] if p["type"] == "customer"]


def test_customer_kind_is_opt_in_and_works(head):
    r = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30,
                     params={"q": TAG, "kinds": "customer,member,user,guest"})
    assert r.status_code == 200
    rows = r.json()["people"]
    customer = [p for p in rows if p["type"] == "customer"]
    assert customer and customer[0]["name"] == f"{TAG} Shopper"
    # the visitor is still in the same single list (a guest is mirrored into
    # `members`, so either type is a correct hit for the same human)
    assert any(p["name"] == state["guest_name"] for p in rows)


def test_two_character_minimum_still_holds(head):
    r = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30, params={"q": "a"})
    assert r.status_code == 200 and r.json()["people"] == []


def test_family_contact_picked_from_the_directory_is_linked(head):
    r = requests.post(f"{BASE}/families", headers=head, timeout=30, json={
        "family_name": f"{TAG} Household",
        "primary_contact_name": state["guest_name"],
        "primary_contact_person_id": state["guests"][0],
        "primary_contact_person_type": "guest",
    })
    assert r.status_code in (200, 201), r.text
    state["family"] = r.json()["id"]
    assert r.json()["primary_contact_person_id"] == state["guests"][0]

    # the guest's own profile now points at the household
    g = requests.get(f"{BASE}/people/suggest", headers=head, timeout=30,
                     params={"q": TAG, "kinds": "guest"})
    assert g.status_code == 200
    mine = [x for x in g.json()["people"] if x["id"] == state["guests"][0]]
    assert mine and mine[0].get("family_id") == state["family"]


def test_family_without_a_picked_contact_still_creates(head):
    r = requests.post(f"{BASE}/families", headers=head, timeout=30, json={
        "family_name": f"{TAG} Freetext", "primary_contact_name": "Typed By Hand"})
    assert r.status_code in (200, 201), r.text
    fid = r.json()["id"]
    assert not r.json().get("primary_contact_person_id")
    requests.delete(f"{BASE}/families/{fid}", headers=head, timeout=30)
