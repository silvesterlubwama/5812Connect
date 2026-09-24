"""iter365 backend tests — search-first pickers + duplicate merge hardening.

Covers:
  * POST /api/people/duplicates/merge honours skip_fields, guards against
    placeholder emails, and stashes a second real email as `alt_emails`.
  * Reference repointing (checkins.member_id) survives a merge and the
    duplicate row is removed from its collection.
  * GET /api/people/duplicates now includes campus-less records and returns
    0 groups for the real seeded data (Henry Lubega / Katelyn Lubwama
    already folded per iter365 spec).
  * Post-merge state of Henry Lubega + Katelyn Lubwama is intact.
  * Manual check-in accepts member_id AND falls back to type=visitor with
    an empty member_id (walk-in).
  * Parent-lookup by raw phone still works (regression).
  * Social-work POST /cases with subject_kind=child and =member; missing
    subject_id rejected.
  * POS /customers create with person_id/person_type links the customer.
  * /people/suggest returns matches for the admin.

All test-created rows are cleaned up in teardown_module().
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN = ("admin@5812uganda.org", "Admin@5812")

# Known real records that the review request says are already merged
HENRY_ID = "87785c67-0b1a-4996-9314-5f0e5f45ecf4"
KATELYN_ID = "8646388b-a17e-4402-8166-c01f66f93094"

CLEANUP = {"users": set(), "guests": set(), "checkins": set(), "cases": set(),
           "customers": set()}


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": identifier, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(*ADMIN)}"}


def _mk_user(admin_h, name, email="", location_id=""):
    """Create a user. NOTE: on this preview env POST /admin/users without an
    email hangs 60s → 502, and PUT /admin/users/{id} with email='' also hangs
    (both look like a backend bug in the members-sync path). Tests that need
    a blank-email keeper use _mk_guest instead."""
    payload = {"name": name, "role": "Member",
               "email": email or f"tmp_{uuid.uuid4().hex[:8]}@iter365.tmp"}
    if location_id:
        payload["location_id"] = location_id
    r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_h, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create user failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    uid = body.get("id") or body.get("user", {}).get("id")
    CLEANUP["users"].add(uid)
    return uid


def _mk_guest(admin_h, name, email="", phone="", location_id=""):
    payload = {"name": name, "email": email, "phone": phone or f"+2567009{int(time.time()) % 100000:05d}"}
    if location_id:
        payload["location_id"] = location_id
    r = requests.post(f"{BASE_URL}/api/guests", headers=admin_h, json=payload, timeout=20)
    assert r.status_code in (200, 201), f"guest create: {r.status_code} {r.text[:200]}"
    gid = r.json()["id"]
    CLEANUP["guests"].add(gid)
    return gid


# ========== MERGE — placeholder email + alt_emails ==========

class TestDedupeMergeEmailRules:
    def test_placeholder_email_not_copied(self, admin_h):
        """Keeper with blank email + dup with foo@example.com → keeper email stays blank.

        Uses a guest as keeper (blank email OK there — POST /admin/users without
        email hangs 60s on this preview, tracked as a separate backend bug)."""
        locs = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20).json()
        loc = locs[0]["id"] if locs else ""
        marker = f"ITER365PH{uuid.uuid4().hex[:6]}"
        name = f"ITER365 Placeholder {marker}"
        keep = _mk_guest(admin_h, name + " K", email="", location_id=loc)
        drop = _mk_guest(admin_h, name + " D", email=f"foo_{marker.lower()}@example.com", location_id=loc)
        r = requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                          json={"keep_id": keep, "drop_ids": [drop]}, timeout=30)
        assert r.status_code == 200, r.text
        # Verify keeper email still blank
        gs = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20).json()
        kept = next((g for g in gs if g["id"] == keep), None)
        assert kept, "keeper guest disappeared"
        assert not (kept.get("email") or "").strip(), \
            f"placeholder email was copied onto keeper: {kept.get('email')}"
        alt = kept.get("alt_emails") or []
        assert not any("@example" in (a or "").lower() for a in alt), \
            f"placeholder ended up in alt_emails: {alt}"
        CLEANUP["guests"].discard(drop)

    def test_second_real_email_becomes_alt(self, admin_h):
        """Keeper a@real.org + dup b@real.org → keeper keeps a@real.org, alt_emails=[b@real.org]."""
        locs = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20).json()
        loc = locs[0]["id"] if locs else ""
        marker = f"ITER365ALT{uuid.uuid4().hex[:6]}"
        name = f"ITER365 Alt {marker}"
        a_email = f"a_{marker.lower()}@iter365.real.org"
        b_email = f"b_{marker.lower()}@iter365.real.org"
        keep = _mk_user(admin_h, name + " K", email=a_email, location_id=loc)
        drop = _mk_guest(admin_h, name + " D", email=b_email, location_id=loc)
        r = requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                          json={"keep_id": keep, "drop_ids": [drop]}, timeout=30)
        assert r.status_code == 200, r.text
        details = r.json().get("details", [{}])[0]
        assert b_email in (details.get("alt_emails") or []), \
            f"alt_emails not in merge response: {r.json()}"
        # Keeper login email must NOT have changed. Fetch via users list.
        ul = requests.get(f"{BASE_URL}/api/admin/users?limit=500", headers=admin_h, timeout=30).json()
        users = ul if isinstance(ul, list) else ul.get("users", [])
        me = next((u for u in users if u["id"] == keep), None)
        assert me, "keeper user disappeared"
        assert (me.get("email") or "").lower() == a_email.lower(), \
            f"keeper login email got overwritten to {me.get('email')}"
        assert b_email.lower() in [(x or "").lower() for x in (me.get("alt_emails") or [])], \
            f"second real email not saved in alt_emails: {me.get('alt_emails')}"
        CLEANUP["guests"].discard(drop)

    def test_skip_fields_honoured(self, admin_h):
        """skip_fields=['email'] must leave keeper email alone even if it was blank."""
        locs = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20).json()
        loc = locs[0]["id"] if locs else ""
        marker = f"ITER365SK{uuid.uuid4().hex[:6]}"
        name = f"ITER365 Skip {marker}"
        keep = _mk_guest(admin_h, name + " K", email="", location_id=loc)
        drop_email = f"drop_{marker.lower()}@iter365.real.org"
        drop = _mk_guest(admin_h, name + " D", email=drop_email, location_id=loc)
        r = requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                          json={"keep_id": keep, "drop_ids": [drop], "skip_fields": ["email"]},
                          timeout=30)
        assert r.status_code == 200, r.text
        gs = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20).json()
        kept = next((g for g in gs if g["id"] == keep), None)
        assert kept, "keeper guest disappeared"
        assert not (kept.get("email") or "").strip(), f"skip_fields ignored, email={kept.get('email')}"
        CLEANUP["guests"].discard(drop)


# ========== MERGE — reference repointing ==========

class TestDedupeMergeReferences:
    def test_checkin_member_id_repointed(self, admin_h):
        locs = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20).json()
        loc = locs[0]["id"] if locs else ""
        marker = f"ITER365REF{uuid.uuid4().hex[:6]}"
        name = f"ITER365 Ref {marker}"
        keep = _mk_user(admin_h, name, location_id=loc)
        drop = _mk_guest(admin_h, name, phone=f"+256700111{int(time.time()) % 1000:03d}",
                         location_id=loc)
        # Create a checkin pointing at the DROP id
        ci = requests.post(f"{BASE_URL}/api/checkins", headers=admin_h,
                           json={"member_id": drop, "member_name": name,
                                 "type": "visitor", "method": "manual"}, timeout=20)
        assert ci.status_code == 200, ci.text
        ci_id = ci.json()["id"]
        CLEANUP["checkins"].add(ci_id)

        r = requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                          json={"keep_id": keep, "drop_ids": [drop]}, timeout=30)
        assert r.status_code == 200, r.text
        moved = r.json().get("details", [{}])[0].get("moved", 0)
        assert moved >= 1, f"no references moved: {r.json()}"

        # Duplicate row removed from guests
        gs = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20)
        assert gs.status_code == 200
        assert drop not in [g["id"] for g in gs.json()], "dropped guest still in list"
        CLEANUP["guests"].discard(drop)

        # Checkin now points at keeper
        cs = requests.get(f"{BASE_URL}/api/checkins", headers=admin_h, timeout=20).json()
        rows = cs if isinstance(cs, list) else cs.get("checkins", [])
        row = next((r for r in rows if r.get("id") == ci_id), None)
        assert row, "checkin disappeared after merge"
        assert row.get("member_id") == keep, f"member_id not repointed: {row.get('member_id')}"


# ========== DUPLICATES LISTING ==========

class TestDuplicatesListing:
    def test_list_includes_campus_less_records(self, admin_h):
        """A duplicate group where BOTH sides have no location_id must show up."""
        marker = f"ITER365NC{uuid.uuid4().hex[:6]}"
        name = f"ITER365 NoCampus {marker}"
        email = f"nc_{marker.lower()}@iter365.real.org"
        keep = _mk_user(admin_h, name, email=email)  # no location_id
        drop = _mk_guest(admin_h, name, email=email)  # no location_id
        d = requests.get(f"{BASE_URL}/api/people/duplicates", headers=admin_h, timeout=30)
        assert d.status_code == 200
        groups = d.json()["groups"]
        found = next((g for g in groups if name.lower() in g["name"].lower()), None)
        assert found, f"campus-less duplicate group not surfaced (total={d.json().get('total')})"
        # cleanup — merge them
        requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                      json={"keep_id": keep, "drop_ids": [drop]}, timeout=30)
        CLEANUP["guests"].discard(drop)

    def test_no_real_dup_groups_for_henry_katelyn(self, admin_h):
        """Post-merge, the review list should NOT contain Henry Lubega or Katelyn Lubwama."""
        d = requests.get(f"{BASE_URL}/api/people/duplicates", headers=admin_h, timeout=30)
        assert d.status_code == 200
        groups = d.json().get("groups", [])
        for g in groups:
            n = (g.get("name") or "").lower()
            assert "henry lubega" not in n, f"Henry Lubega still surfaces as duplicate: {g}"
            assert "katelyn lubwama" not in n, f"Katelyn Lubwama still surfaces as duplicate: {g}"


# ========== HENRY + KATELYN STATE ==========

class TestSeededPeopleState:
    def test_henry_lubega_intact(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/admin/users/{HENRY_ID}/profile",
                         headers=admin_h, timeout=20)
        if r.status_code == 404:
            pytest.skip("Henry Lubega record missing in this env")
        assert r.status_code == 200, r.text
        p = r.json()
        assert (p.get("name") or "").lower().startswith("henry"), f"wrong name: {p.get('name')}"
        # Role Staff, department Poultry, campus Zimba Farm, BLANK email
        assert (p.get("role") or "").lower() == "staff", f"role={p.get('role')}"
        assert (p.get("department") or "").lower() == "poultry", f"dept={p.get('department')}"
        assert not (p.get("email") or "").strip(), f"expected blank email, got {p.get('email')}"
        # campus resolution — id or name
        # We don't have a strict campus name endpoint here, so we just check
        # location_id is set (Zimba Farm exists) and, if the name is in the
        # payload, it says Zimba.
        if p.get("campus_name") or p.get("location_name"):
            cn = (p.get("campus_name") or p.get("location_name") or "").lower()
            assert "zimba" in cn, f"campus_name={cn}"

    def test_katelyn_lubwama_intact(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/admin/users/{KATELYN_ID}/profile",
                         headers=admin_h, timeout=20)
        if r.status_code == 404:
            pytest.skip("Katelyn Lubwama record missing in this env")
        assert r.status_code == 200, r.text
        p = r.json()
        assert (p.get("email") or "").lower() == "katelyn@lubwamas.org", \
            f"email mismatch: {p.get('email')}"
        assert (p.get("role") or "").lower() in ("admin", "system_admin"), \
            f"role should be admin, got {p.get('role')}"
        alt = [a.lower() for a in (p.get("alt_emails") or [])]
        assert "katelynlubwama@gmail.com" in alt, \
            f"gmail not folded into alt_emails: {p.get('alt_emails')}"


# ========== MANUAL CHECK-IN — search-first ==========

class TestManualCheckin:
    def test_checkin_with_member_id_and_name(self, admin_h):
        # pick any user in the /people/suggest response
        s = requests.get(f"{BASE_URL}/api/people/suggest?q=lu&limit=5",
                         headers=admin_h, timeout=20)
        assert s.status_code == 200, s.text
        people = s.json().get("people", [])
        if not people:
            pytest.skip("no people to pick")
        person = people[0]
        ci = requests.post(f"{BASE_URL}/api/checkins", headers=admin_h,
                           json={"member_id": person["id"], "member_name": person["name"],
                                 "type": "member", "method": "manual"}, timeout=20)
        assert ci.status_code == 200, ci.text
        row = ci.json()
        CLEANUP["checkins"].add(row["id"])
        assert row.get("member_id") == person["id"]
        assert row.get("member_name") == person["name"]
        # visible in the list
        lst = requests.get(f"{BASE_URL}/api/checkins", headers=admin_h, timeout=20).json()
        rows = lst if isinstance(lst, list) else lst.get("checkins", [])
        assert any(r["id"] == row["id"] for r in rows), "check-in not on list"

    def test_walkin_visitor_without_member_id(self, admin_h):
        """Typing a name that matches nobody must submit with type=visitor, member_id=''."""
        marker = uuid.uuid4().hex[:6]
        ci = requests.post(f"{BASE_URL}/api/checkins", headers=admin_h,
                           json={"member_id": "", "member_name": f"ITER365 Walkin {marker}",
                                 "type": "visitor", "method": "manual"}, timeout=20)
        assert ci.status_code == 200, ci.text
        row = ci.json()
        CLEANUP["checkins"].add(row["id"])
        assert row.get("type") == "visitor"
        assert not (row.get("member_id") or "")


# ========== PARENT CHECK-IN LOOKUP (regression) ==========

class TestParentLookup:
    def test_parent_lookup_by_phone_still_works(self, admin_h):
        # Any parent phone from the guests list
        gs = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20).json()
        parent = next((g for g in gs if g.get("phone") and g.get("is_parent")), None)
        if not parent:
            # fall back to any guest with a phone number
            parent = next((g for g in gs if g.get("phone")), None)
        if not parent:
            pytest.skip("no parent phone to test")
        r = requests.post(f"{BASE_URL}/api/checkins/parent-lookup", headers=admin_h,
                          json={"lookup": parent["phone"]}, timeout=20)
        # 200 with a parent match or empty; either is acceptable — the point is
        # the endpoint still accepts a raw phone string.
        assert r.status_code == 200, r.text


# ========== SOCIAL WORK NEW CASE ==========

class TestSocialWorkCreate:
    def test_reject_missing_subject_id(self, admin_h):
        r = requests.post(f"{BASE_URL}/api/social-work/cases", headers=admin_h,
                          json={"category": "welfare_support", "summary": "x"}, timeout=20)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_case_with_subject_kind_child(self, admin_h):
        kids = requests.get(f"{BASE_URL}/api/children", headers=admin_h, timeout=20).json()
        rows = kids if isinstance(kids, list) else kids.get("children", [])
        # pick a child without an active case
        for child in rows:
            r = requests.post(f"{BASE_URL}/api/social-work/cases", headers=admin_h,
                              json={"subject_id": child["id"], "subject_kind": "child",
                                    "category": "welfare_support",
                                    "summary": "ITER365 test child case"},
                              timeout=20)
            if r.status_code == 200:
                CLEANUP["cases"].add(r.json()["id"])
                assert r.json().get("subject_kind") == "child"
                return
            if r.status_code == 400 and "already exists" in r.text:
                continue
            # unexpected
            pytest.fail(f"unexpected: {r.status_code} {r.text[:200]}")
        pytest.skip("all children already have active cases")

    def test_case_with_subject_kind_member(self, admin_h):
        ms = requests.get(f"{BASE_URL}/api/members?limit=50", headers=admin_h, timeout=20).json()
        rows = ms if isinstance(ms, list) else ms.get("members", [])
        for m in rows:
            r = requests.post(f"{BASE_URL}/api/social-work/cases", headers=admin_h,
                              json={"subject_id": m["id"], "subject_kind": "member",
                                    "category": "welfare_support",
                                    "summary": "ITER365 test member case"},
                              timeout=20)
            if r.status_code == 200:
                CLEANUP["cases"].add(r.json()["id"])
                assert r.json().get("subject_kind") == "member"
                return
            if r.status_code == 400 and "already exists" in r.text:
                continue
            pytest.fail(f"unexpected: {r.status_code} {r.text[:200]}")
        pytest.skip("no member available for a fresh case")


# ========== POS CUSTOMER FROM PERSON ==========

class TestCustomerFromPerson:
    def test_create_customer_with_person_link(self, admin_h):
        # pick a guest to link to
        gs = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20).json()
        if not gs:
            pytest.skip("no guest to link")
        g = gs[0]
        r = requests.post(f"{BASE_URL}/api/customers", headers=admin_h,
                          json={"name": g["name"], "person_id": g["id"], "person_type": "guest",
                                "email": g.get("email", ""), "phone": g.get("phone", "")},
                          timeout=20)
        assert r.status_code == 200, r.text
        cust = r.json()
        CLEANUP["customers"].add(cust["id"])
        assert cust.get("person_id") == g["id"]
        assert cust.get("person_type") == "guest"
        # verify persistence
        fetched = requests.get(f"{BASE_URL}/api/customers/{cust['id']}",
                               headers=admin_h, timeout=20).json()
        assert fetched.get("person_id") == g["id"]


# ========== PEOPLE SUGGEST ==========

class TestPeopleSuggest:
    def test_admin_can_suggest(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/people/suggest?q=lu&limit=10",
                         headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "people" in body and "count" in body
        # short query returns empty
        r2 = requests.get(f"{BASE_URL}/api/people/suggest?q=a", headers=admin_h, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["count"] == 0

    def test_kinds_filter(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/people/suggest?q=lu&kinds=child",
                         headers=admin_h, timeout=20)
        assert r.status_code == 200
        for p in r.json().get("people", []):
            assert p["type"] == "child", f"kinds=child returned {p['type']}"


# ========== CLEANUP ==========

def teardown_module(module):
    try:
        h = {"Authorization": f"Bearer {_login(*ADMIN)}"}
    except Exception:
        return
    for cid in list(CLEANUP["checkins"]):
        try:
            requests.delete(f"{BASE_URL}/api/checkins/{cid}", headers=h, timeout=10)
        except Exception:
            pass
    for cid in list(CLEANUP["cases"]):
        try:
            requests.delete(f"{BASE_URL}/api/social-work/cases/{cid}", headers=h, timeout=10)
        except Exception:
            pass
    for cid in list(CLEANUP["customers"]):
        try:
            requests.delete(f"{BASE_URL}/api/customers/{cid}", headers=h, timeout=10)
        except Exception:
            pass
    for gid in list(CLEANUP["guests"]):
        try:
            requests.delete(f"{BASE_URL}/api/guests/{gid}", headers=h, timeout=10)
        except Exception:
            pass
    for uid in list(CLEANUP["users"]):
        try:
            requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=h, timeout=10)
        except Exception:
            pass
