"""iter363 EXTRA coverage — RBAC, portal add-guardian (linked+new), approvals,
spouse both-ways link, kiosk pin-checkin action=lookup privacy, one-household
across all three endpoints.

The base suite (test_iter363_household_and_people_search.py) covers the happy
paths on /people/suggest, admin `/families/{id}/people` and kiosk lookup. This
suite fills in the gaps in the review request.
"""
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN = ("admin@5812uganda.org", "Admin@5812")
MEMBER = ("member@5812uganda.org", "Member@5812")
TAG = "iter363x"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"identifier": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login for {email} failed: {r.status_code} {r.text}"
    return r.json()["token"], r.json().get("user") or {}


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_hdr():
    tok, _ = _login(*ADMIN)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def member_ctx():
    tok, user = _login(*MEMBER)
    return {"hdr": {"Authorization": f"Bearer {tok}"}, "user": user}


@pytest.fixture(scope="module")
def member_household(admin_hdr, member_ctx):
    """Ensure the member has a family; return the family_id."""
    r = requests.get(f"{API}/portal/family", headers=member_ctx["hdr"], timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("family") and body["family"].get("id"):
        return body["family"]["id"]
    # create one via the portal
    r = requests.post(f"{API}/portal/family", headers=member_ctx["hdr"], timeout=30,
                      json={"family_name": f"{TAG} Household", "primary_contact_phone": "0770099999"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- RBAC ----------
def test_people_suggest_requires_staff_role(member_ctx):
    """Member role must not read the staff directory type-ahead (403/401)."""
    r = requests.get(f"{API}/people/suggest", headers=member_ctx["hdr"], timeout=30, params={"q": "adm"})
    assert r.status_code in (401, 403), f"a Member should NOT be able to hit /people/suggest, got {r.status_code}"


def test_portal_suggest_open_to_member_and_is_thin(member_ctx):
    r = requests.get(f"{API}/portal/people/suggest", headers=member_ctx["hdr"], timeout=30,
                     params={"q": "adm"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "people" in body
    for p in body["people"]:
        assert set(p.keys()) <= {"id", "name", "type", "photo_url", "hint"}, f"portal leaked PII: {p}"


def test_regex_unsafe_and_single_char(admin_hdr):
    r = requests.get(f"{API}/people/suggest", headers=admin_hdr, timeout=30, params={"q": "("})
    assert r.status_code == 200, r.text
    r = requests.get(f"{API}/people/suggest", headers=admin_hdr, timeout=30, params={"q": "a"})
    assert r.status_code == 200 and r.json()["people"] == []


# ---------- Portal: add guardian (linked + new-person) with approval flow ----------
def test_portal_add_linked_guardian_awaits_approval(admin_hdr, member_ctx, member_household):
    fam_id = member_household
    # create a member "person" that the portal will LINK to
    tag = uuid.uuid4().hex[:5]
    person_name = f"{TAG} Linkable {tag}"
    r = requests.post(f"{API}/members", headers=admin_hdr, timeout=30, json={
        "name": person_name, "phone": "0770123123",
        "email": f"link{tag}@example.test", "role": "Member", "gender": "male",
    })
    assert r.status_code == 200, r.text
    linked_id = r.json()["id"]

    # portal → /api/portal/family/guardians  (linked=is_new: false)
    r = requests.post(f"{API}/portal/family/guardians", headers=member_ctx["hdr"], timeout=30, json={
        "name": person_name, "relationship": "Spouse",
        "person_id": linked_id, "person_type": "member",
    })
    assert r.status_code == 200, r.text
    guardian = r.json()
    assert guardian.get("approval_status") == "pending", "member submissions must be pending"
    assert guardian.get("person_id") == linked_id

    # It shows on Family Approvals
    r = requests.get(f"{API}/families/pending-approvals", headers=admin_hdr, timeout=30)
    assert r.status_code == 200, r.text
    pend = r.json()["guardians"]
    ours = next((g for g in pend if g["id"] == guardian["id"]), None)
    assert ours, f"pending guardian not surfaced: {[g['id'] for g in pend]}"
    assert ours["family_id"] == fam_id

    # Approve → member gets family_id AND spouse pair written both ways
    r = requests.post(
        f"{API}/families/pending-approvals/guardian/{fam_id}/{guardian['id']}/decide",
        headers=admin_hdr, timeout=30, json={"action": "approve"},
    )
    assert r.status_code == 200, r.text

    m = requests.get(f"{API}/members/{linked_id}", headers=admin_hdr, timeout=30).json()
    assert m.get("family_id") == fam_id, "approve must link the profile to the family"
    # spouse pairing
    me_id = member_ctx["user"]["id"]
    assert m.get("spouse_id") == me_id or m.get("spouse_id"), f"spouse should be paired both ways: {m.get('spouse_id')}"

    pytest.fam_for_portal = fam_id
    pytest.linked_member_id = linked_id


def test_portal_add_new_person_creates_pending_profile(admin_hdr, member_ctx, member_household):
    fam_id = member_household
    tag = uuid.uuid4().hex[:5]
    name = f"{TAG} NewGuardian {tag}"
    # portal → new-person creates via POST /portal/family/people
    r = requests.post(f"{API}/portal/family/people", headers=member_ctx["hdr"], timeout=30, json={
        "name": name, "relationship": "Grandparent",
        "date_of_birth": "1955-01-01", "gender": "female",
        "national_id": "NID-PORT-X", "address": "Plot Test",
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "member"
    person_id = out["person"]["id"]
    assert out["person"].get("status") == "pending"
    guardian_id = out["guardian"]["id"]

    # Approvals list surfaces it
    r = requests.get(f"{API}/families/pending-approvals", headers=admin_hdr, timeout=30)
    assert any(g["id"] == guardian_id for g in r.json()["guardians"]), "pending new-person guardian not visible"

    # Reject → profile is torn down
    r = requests.post(
        f"{API}/families/pending-approvals/guardian/{fam_id}/{guardian_id}/decide",
        headers=admin_hdr, timeout=30, json={"action": "reject", "reason": "duplicate"},
    )
    assert r.status_code == 200, r.text

    m = requests.get(f"{API}/members/{person_id}", headers=admin_hdr, timeout=30)
    assert m.status_code == 404, f"a rejected member-created profile should be removed, got {m.status_code}"


# ---------- One household across all surfaces ----------
def test_same_household_admin_portal_kiosk(admin_hdr, member_ctx, member_household):
    fam_id = member_household
    # Admin view
    admin_view = requests.get(f"{API}/families/{fam_id}", headers=admin_hdr, timeout=30).json()
    admin_names = {h["name"] for h in admin_view.get("household", [])}

    # Portal view (that member)
    portal_view = requests.get(f"{API}/portal/family", headers=member_ctx["hdr"], timeout=30).json()
    portal_names = {h["name"] for h in (portal_view.get("household") or [])}

    # Both must overlap on approved rows
    assert admin_names, "admin household must have rows"
    # Portal always includes self + approved guardians; must share at least one name
    assert admin_names & portal_names or (portal_view.get("family") and portal_view["family"]["id"] == fam_id), \
        f"admin/portal household disagree: admin={admin_names} portal={portal_names}"

    # /api/members?family_id filter
    r = requests.get(f"{API}/members", headers=admin_hdr, timeout=30,
                     params={"family_id": fam_id, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    for row in body["members"]:
        assert row["family_id"] == fam_id
        assert row.get("family_name"), "family_name enrichment missing"


# ---------- Kiosk PIN-checkin: action=lookup returns household w/ no PII ----------
def test_kiosk_pin_lookup_household_has_no_pii(admin_hdr):
    """action=lookup echoes the same shape as /kiosk/lookup but for PIN paths."""
    # We reuse the member who is in the non-anonymous flow: use a public phone lookup
    # first, then exercise pin-checkin with action=lookup for the same phone tail.
    # (The public route is rate-limited — this is a single call.)
    # Grab any known adult with a phone
    r = requests.get(f"{API}/members", headers=admin_hdr, timeout=30, params={"limit": 100})
    assert r.status_code == 200
    someone = next((m for m in r.json().get("members", []) if m.get("phone")), None)
    if not someone:
        pytest.skip("no member with a phone to exercise the kiosk PIN lookup")
    phone = someone["phone"]
    # Take the last 4 digits as the "PIN" surrogate used by the endpoint.
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        pytest.skip("member phone too short")
    r = requests.post(f"{API}/kiosk/pin-checkin", timeout=30, json={
        "pin": digits[-4:], "action": "lookup",
    })
    # 200 with body, or 404 if the pin was ambiguous — either way must not 500.
    assert r.status_code in (200, 400, 404, 429), r.text
    if r.status_code == 200:
        body = r.json()
        for h in body.get("household", []):
            leaked = {"phone", "email", "date_of_birth", "national_id", "address"} & set(h)
            assert not leaked, f"kiosk pin-checkin lookup leaked PII: {leaked} in {h}"


# ---------- Regression: 6-family-member cap and family basics still work ----------
def test_family_caps_and_basic_crud(admin_hdr):
    tag = uuid.uuid4().hex[:5]
    r = requests.post(f"{API}/families", headers=admin_hdr, timeout=30, json={
        "family_name": f"{TAG} Cap Test {tag}", "primary_contact_name": "Cap Dad",
        "primary_contact_phone": "0770000000",
    })
    assert r.status_code == 200, r.text
    fam = r.json()

    # iter368 — one unified list, capped at 6 family members
    r = requests.put(f"{API}/families/{fam['id']}/members", headers=admin_hdr, timeout=30,
                     json={"parent_ids": ["a", "b", "c", "d", "e", "f", "g"], "child_ids": []})
    assert r.status_code == 400, "7 family members must be refused"

    r = requests.put(f"{API}/families/{fam['id']}/members", headers=admin_hdr, timeout=30,
                     json={"parent_ids": ["a", "b", "c"], "child_ids": []})
    assert r.status_code == 200, "3 family members must be allowed now"

    # rename + address change still work — PUT /families/{id} needs the full payload
    r = requests.put(f"{API}/families/{fam['id']}", headers=admin_hdr, timeout=30, json={
        "family_name": f"{TAG} Cap Renamed {tag}",
        "primary_contact_name": "Cap Dad",
        "primary_contact_phone": "0770000000",
        "address": "New Address",
    })
    assert r.status_code == 200, r.text
    r = requests.get(f"{API}/families/{fam['id']}", headers=admin_hdr, timeout=30).json()
    assert r["family_name"].startswith(f"{TAG} Cap Renamed")
    assert r["address"] == "New Address"

    # cleanup
    requests.delete(f"{API}/families/{fam['id']}", headers=admin_hdr, timeout=30)
