"""iter363 — people type-ahead, linked household members, kiosk household check-in."""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
TAG = "iter363"


@pytest.fixture(scope="module")
def hdr():
    r = requests.post(f"{API}/auth/login", json={"identifier": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def household(hdr):
    tag = uuid.uuid4().hex[:5]
    phone = f"07{uuid.uuid4().int % 10_000_000:07d}"
    fam = requests.post(f"{API}/families", headers=hdr, timeout=30, json={
        "family_name": f"{TAG} Okello {tag}", "primary_contact_name": f"{TAG} Dad {tag}",
        "primary_contact_phone": "0770000111",
    })
    assert fam.status_code == 200, fam.text
    family = fam.json()
    spouse = requests.post(f"{API}/members", headers=hdr, timeout=30, json={
        "name": f"{TAG} Mary {tag}", "phone": phone, "email": f"mary{tag}@example.test",
        "gender": "female", "role": "Member",
    })
    assert spouse.status_code == 200, spouse.text
    return {"family": family, "spouse": spouse.json(), "tag": tag, "phone": phone}


def test_people_suggest(hdr, household):
    r = requests.get(f"{API}/people/suggest", headers=hdr, timeout=30, params={"q": "a"})
    assert r.status_code == 200 and r.json()["people"] == [], "one letter is too short to search"

    name = household["spouse"]["name"]
    r = requests.get(f"{API}/people/suggest", headers=hdr, timeout=30, params={"q": name[:12]})
    assert r.status_code == 200, r.text
    hit = next((p for p in r.json()["people"] if p["id"] == household["spouse"]["id"]), None)
    assert hit, f"the new member should be findable by name: {r.json()}"
    assert hit["type"] == "member" and hit["phone"] == household["phone"]

    # phone and email find them too
    for term in (household["phone"], household["spouse"]["email"]):
        r = requests.get(f"{API}/people/suggest", headers=hdr, timeout=30, params={"q": term})
        assert any(p["id"] == household["spouse"]["id"] for p in r.json()["people"]), term

    # kind filter and a regex-unsafe term
    r = requests.get(f"{API}/people/suggest", headers=hdr, timeout=30,
                     params={"q": name[:12], "kinds": "child"})
    assert all(p["type"] == "child" for p in r.json()["people"])
    assert requests.get(f"{API}/people/suggest", headers=hdr, timeout=30,
                        params={"q": "("}).status_code == 200

    assert requests.get(f"{API}/people/suggest", timeout=30, params={"q": "mary"}).status_code == 401


def test_portal_suggest_is_thin(hdr, household):
    r = requests.get(f"{API}/portal/people/suggest", headers=hdr, timeout=30, params={"q": "ma"})
    assert r.status_code == 200 and r.json()["people"] == [], "portal needs 3 characters"
    r = requests.get(f"{API}/portal/people/suggest", headers=hdr, timeout=30,
                     params={"q": household["spouse"]["name"][:12]})
    assert r.status_code == 200, r.text
    for p in r.json()["people"]:
        assert set(p) == {"id", "name", "type", "photo_url", "hint"}, "no PII may leak to a member"


def test_linking_a_spouse(hdr, household):
    fam_id = household["family"]["id"]
    r = requests.post(f"{API}/families/{fam_id}/guardians", headers=hdr, timeout=30, json={
        "person_id": household["spouse"]["id"], "person_type": "member", "relationship": "Spouse",
    })
    assert r.status_code == 200, r.text
    guardian = r.json()
    assert guardian["person_id"] == household["spouse"]["id"]
    assert guardian["name"] == household["spouse"]["name"], "the name comes from the linked profile"
    assert guardian["phone"] == household["phone"]

    # the profile now belongs to the household
    member = requests.get(f"{API}/members/{household['spouse']['id']}", headers=hdr, timeout=30).json()
    assert member["family_id"] == fam_id

    # a bad link is refused, and a nameless loose entry too
    assert requests.post(f"{API}/families/{fam_id}/guardians", headers=hdr, timeout=30,
                         json={"person_id": "nope", "person_type": "member"}).status_code == 404
    assert requests.post(f"{API}/families/{fam_id}/guardians", headers=hdr, timeout=30,
                         json={"relationship": "Spouse"}).status_code == 400
    pytest.guardian_id = guardian["id"]


def test_family_detail_exposes_one_household(hdr, household):
    r = requests.get(f"{API}/families/{household['family']['id']}", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json()["household"]
    assert any(h["name"] == household["spouse"]["name"] and h["relationship"] == "Spouse" for h in rows)
    assert all({"id", "name", "type", "relationship"} <= set(h) for h in rows)


def test_add_a_brand_new_person(hdr, household):
    fam_id = household["family"]["id"]
    r = requests.post(f"{API}/families/{fam_id}/people", headers=hdr, timeout=30, json={
        "name": f"{TAG} Grace {household['tag']}", "relationship": "Grandparent",
        "phone": "0770000333", "email": f"grace{household['tag']}@example.test",
        "gender": "female", "date_of_birth": "1960-04-02", "national_id": "CF1234567",
        "address": "Plot 4, Entebbe",
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "member"
    assert out["person"]["family_id"] == fam_id
    assert out["person"]["national_id"] == "CF1234567"
    assert out["guardian"]["person_id"] == out["person"]["id"]

    # they are now findable by the same type-ahead, so nobody re-types them
    found = requests.get(f"{API}/people/suggest", headers=hdr, timeout=30,
                         params={"q": f"{TAG} Grace"}).json()["people"]
    assert any(p["id"] == out["person"]["id"] for p in found)

    # a child goes to the children collection instead
    r = requests.post(f"{API}/families/{fam_id}/people", headers=hdr, timeout=30, json={
        "name": f"{TAG} Junior {household['tag']}", "relationship": "Child",
        "date_of_birth": "2018-06-01", "gender": "male",
    })
    assert r.status_code == 200 and r.json()["kind"] == "child"
    assert r.json()["person"]["id"].startswith("chd_")

    assert requests.post(f"{API}/families/{fam_id}/people", headers=hdr, timeout=30,
                         json={"name": "x"}).status_code == 400
    assert requests.post(f"{API}/families/nope/people", headers=hdr, timeout=30,
                         json={"name": "Someone Real"}).status_code == 404


def test_members_can_be_grouped_by_family(hdr, household):
    r = requests.get(f"{API}/members", headers=hdr, timeout=30,
                     params={"family_id": household["family"]["id"], "limit": 50})
    assert r.status_code == 200, r.text
    rows = r.json()["members"]
    assert rows and all(m["family_id"] == household["family"]["id"] for m in rows)
    assert all(m.get("family_name") == household["family"]["family_name"] for m in rows)


def test_kiosk_offers_the_whole_household(hdr, household):
    """The person at the keypad plus their spouse, guardians and children."""
    r = requests.get(f"{API}/kiosk/lookup", timeout=30, params={"identifier": household["phone"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == household["spouse"]["name"]
    rows = body["household"]
    assert rows[0]["type"] == "self"
    names = {h["name"] for h in rows}
    assert any(f"{TAG} Grace" in n for n in names), f"the guardian should be offered: {names}"
    assert any(f"{TAG} Junior" in n for n in names), f"the child should be offered: {names}"
    assert all("checked_in_today" in h for h in rows)
    # Nothing beyond what the screen shows
    for h in rows:
        assert not ({"phone", "email", "date_of_birth", "national_id", "address"} & set(h))
    assert body["children"], "the old children-only field is still returned"


def test_kiosk_checks_in_the_people_tapped(hdr, household):
    look = requests.get(f"{API}/kiosk/lookup", timeout=30, params={"identifier": household["phone"]}).json()
    rows = look["household"]
    grace = next(h for h in rows if f"{TAG} Grace" in h["name"])
    junior = next(h for h in rows if f"{TAG} Junior" in h["name"])

    r = requests.post(f"{API}/kiosk/pin-checkin", timeout=30, json={
        "pin": household["phone"][-4:], "action": "checkin", "include_self": False,
        "member_ids": [grace["id"]], "child_ids": [junior["id"]],
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checked_in_count"] >= 2
    filed = " ".join(out["checked_in_names"])
    assert f"{TAG} Grace" in filed and f"{TAG} Junior" in filed
    assert f"{TAG} Mary" not in filed, "the adult at the keypad was not tapped, so must not be checked in"

    # tapping nobody is still refused
    r = requests.post(f"{API}/kiosk/pin-checkin", timeout=30, json={
        "pin": household["phone"][-4:], "action": "checkin", "include_self": False, "member_ids": [], "child_ids": [],
    })
    assert r.status_code == 400

    # and the next lookup shows who is already in
    again = requests.get(f"{API}/kiosk/lookup", timeout=30, params={"identifier": household["phone"]}).json()
    done = {h["name"] for h in again["household"] if h.get("checked_in_today")}
    assert any(f"{TAG} Grace" in n for n in done), f"already-checked-in should be flagged: {done}"


def test_portal_suggest_matches_name_only(hdr, household):
    """A member must not be able to probe the directory with a phone or email."""
    by_name = requests.get(f"{API}/portal/people/suggest", headers=hdr, timeout=30,
                           params={"q": household["spouse"]["name"][:12]}).json()["people"]
    assert any(p["id"] == household["spouse"]["id"] for p in by_name)
    for term in (household["phone"], household["spouse"]["email"]):
        found = requests.get(f"{API}/portal/people/suggest", headers=hdr, timeout=30,
                             params={"q": term}).json()["people"]
        assert not any(p["id"] == household["spouse"]["id"] for p in found), term
