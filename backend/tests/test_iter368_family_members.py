"""iter368 — one "family members" list, and adding a parent actually saves.

User reports:
  • "adding parents in family or via child is not saving"
  • "I don't think we should have two fields for parents and guardians …
     should be one corresponding field across the board"
  • "unable to search all available parents when editing child profile"

The parents / guardians split is gone: every adult is a family member with a
role (Mother, Father, Guardian, …) and one permission — can they collect the
children. Max 6 per family.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER368_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    if state.get("child"):
        requests.delete(f"{BASE}/children/{state['child']}", headers=h, timeout=30)
    if state.get("family"):
        requests.delete(f"{BASE}/families/{state['family']}", headers=h, timeout=30)


def test_setup_family_and_child(head):
    r = requests.post(f"{BASE}/families", headers=head, timeout=30, json={
        "family_name": f"{TAG} Household", "primary_contact_name": "Iter368 Dad",
        "primary_contact_phone": "0770368368",
    })
    assert r.status_code == 200, r.text
    state["family"] = r.json()["id"]

    r = requests.post(f"{BASE}/children", headers=head, timeout=30, json={
        "name": f"{TAG} Kid", "date_of_birth": "2016-04-01", "family_id": state["family"],
    })
    assert r.status_code == 200, r.text
    state["child"] = r.json()["id"]


def test_add_new_family_member_persists(head):
    """A brand-new adult is created, attached to the household AND linked to
    the children in ONE call — this is what used to silently not save."""
    r = requests.post(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30,
                      json={"name": f"{TAG} Mother", "role": "Mother", "phone": "0771111111"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["member"]["role"] == "Mother"
    assert body["member"]["can_pickup"] is True, "mum can collect by default"
    assert body["created_profile"], "a profile should have been created"
    state["mother_member_id"] = body["member"]["id"]
    state["mother_person_id"] = body["member"]["person_id"]

    # it is there on the next read (the actual bug: it wasn't)
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    names = [m["name"] for m in r.json()["members"]]
    assert f"{TAG} Mother" in names, names

    # and the child now has her as a parent
    r = requests.get(f"{BASE}/children/{state['child']}/family-members", headers=head, timeout=30)
    rows = r.json()["members"]
    mum = next((m for m in rows if m["person_id"] == state["mother_person_id"]), None)
    assert mum and mum["linked_to_child"], rows


def test_pickup_default_off_for_non_caregivers(head):
    r = requests.post(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30,
                      json={"name": f"{TAG} Auntie", "role": "Aunt"})
    assert r.status_code == 200, r.text
    assert r.json()["member"]["can_pickup"] is False, "an aunt is off by default"
    state["aunt_member_id"] = r.json()["member"]["id"]

    # explicit override wins
    r = requests.put(f"{BASE}/families/{state['family']}/members/{state['aunt_member_id']}",
                     headers=head, timeout=30,
                     json={"name": f"{TAG} Auntie", "role": "Aunt", "can_pickup": True})
    assert r.status_code == 200, r.text
    assert r.json()["member"]["can_pickup"] is True


def test_legacy_relationships_normalise_to_one_role_set(head):
    """Anything typed in the old free-text box maps onto the one role list."""
    r = requests.post(f"{BASE}/families/{state['family']}/guardians", headers=head, timeout=30,
                      json={"name": f"{TAG} Spouse", "relationship": "Spouse"})
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    row = next(m for m in r.json()["members"] if m["name"] == f"{TAG} Spouse")
    assert row["role"] == "Guardian", row
    assert set(r.json()["roles"]) == {"Mother", "Father", "Guardian", "Grandparent",
                                      "Aunt", "Uncle", "Sibling", "Step-Parent", "Other"}


def test_add_from_child_profile_links_both_ways(head):
    """Adding from the child's profile writes the profile, the household row
    and the child's parent link in one go."""
    r = requests.post(f"{BASE}/children/{state['child']}/family-members", headers=head, timeout=30,
                      json={"name": f"{TAG} Grandma", "role": "Grandparent"})
    assert r.status_code == 200, r.text
    pid = r.json()["member"]["person_id"]
    r = requests.get(f"{BASE}/children/{state['child']}", headers=head, timeout=30)
    assert pid in (r.json().get("parent_ids") or []), "child parent link missing"
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    assert pid in [m["person_id"] for m in r.json()["members"]], "household row missing"


def test_search_finds_existing_people_for_child(head):
    """The child editor searches the whole directory, not a local page of rows."""
    r = requests.get(f"{BASE}/people/suggest", headers=head,
                     params={"q": f"{TAG} Grandma"[:12], "kinds": "guest,member,user"}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 1, r.text


def test_linking_the_same_person_twice_is_idempotent(head):
    r = requests.post(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30,
                      json={"name": f"{TAG} Mother", "person_id": state["mother_person_id"],
                            "person_type": "member", "role": "Mother"})
    assert r.status_code == 200, r.text
    assert r.json()["already_linked"] is True
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    assert len([m for m in r.json()["members"] if m["name"] == f"{TAG} Mother"]) == 1


def test_cap_of_six_family_members(head):
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    have = len(r.json()["members"])
    assert r.json()["max"] == 6
    codes = []
    for i in range(7 - have + 1):
        rr = requests.post(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30,
                           json={"name": f"{TAG} Filler {i}", "role": "Other"})
        codes.append(rr.status_code)
    assert 400 in codes, f"the 7th member must be refused, got {codes}"


def test_remove_family_member_unlinks_everywhere(head):
    r = requests.delete(f"{BASE}/families/{state['family']}/members/{state['mother_member_id']}",
                        headers=head, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.get(f"{BASE}/families/{state['family']}/members", headers=head, timeout=30)
    assert state["mother_person_id"] not in [m["person_id"] for m in r.json()["members"]]
    r = requests.get(f"{BASE}/children/{state['child']}", headers=head, timeout=30)
    assert state["mother_person_id"] not in (r.json().get("parent_ids") or [])


def test_family_detail_and_list_show_everyone(head):
    r = requests.get(f"{BASE}/families/{state['family']}", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    assert isinstance(r.json().get("family_members"), list) and r.json()["family_members"]
    r = requests.get(f"{BASE}/families", headers=head, params={"search": f"{TAG}"}, timeout=30)
    fam = next(f for f in r.json() if f["id"] == state["family"])
    assert fam.get("family_members"), "the card preview must list the household"
