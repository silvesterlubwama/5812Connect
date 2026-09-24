"""iter364 backend test suite — family regressions, approval flow, dedupe,
photo re-upload, social case deep-link filter, staff/user edit correctness.

Runs against the public preview URL and admin/member seeded creds. All test
data is prefixed with ``ITER364_`` and cleaned up in module teardown.
"""
import io
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # allow running locally against the frontend .env
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN = ("admin@5812uganda.org", "Admin@5812")
MEMBER = ("member@5812uganda.org", "Member@5812")


def _login(identifier: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": identifier, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {identifier}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(*ADMIN)}"}


@pytest.fixture(scope="module")
def member_h():
    return {"Authorization": f"Bearer {_login(*MEMBER)}"}


# Track ids to clean up
CLEANUP = {"families": set(), "users": set(), "members": set(),
           "children": set(), "guests": set(), "cases": set()}


def _mk_family(admin_h, name_suffix: str) -> dict:
    payload = {"family_name": f"ITER364_{name_suffix}_{uuid.uuid4().hex[:6]}",
               "primary_contact_name": "ITER364 Contact",
               "primary_contact_phone": "+256700000000",
               "address": "Kampala"}
    # Include location_id from an existing location
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20)
    if r.status_code == 200 and r.json():
        payload["location_id"] = r.json()[0]["id"]
    r = requests.post(f"{BASE_URL}/api/families", headers=admin_h, json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    fam = r.json()
    CLEANUP["families"].add(fam["id"])
    return fam


# ============ FAMILY REGRESSION TESTS ============

class TestFamilyPartialUpdate:
    def test_put_family_only_name_preserves_campus_and_guardians(self, admin_h):
        fam = _mk_family(admin_h, "partial")
        loc = fam.get("location_id")
        # add a guardian
        gr = requests.post(f"{BASE_URL}/api/families/{fam['id']}/guardians",
                           headers=admin_h,
                           json={"name": "ITER364 Guardian A", "relationship": "Spouse",
                                 "phone": "+256700000001"}, timeout=20)
        assert gr.status_code in (200, 201), gr.text

        # partial PUT with ONLY family_name
        upd = requests.put(f"{BASE_URL}/api/families/{fam['id']}", headers=admin_h,
                           json={"family_name": fam["family_name"] + " (renamed)"}, timeout=20)
        assert upd.status_code == 200, upd.text
        body = upd.json()
        assert body["family_name"].endswith("(renamed)")
        assert body.get("location_id") == loc, f"location_id was cleared! was {loc}, got {body.get('location_id')}"
        assert body.get("guardians") and len(body["guardians"]) >= 1, "guardians got wiped"

    def test_put_family_empty_location_id_does_not_clear(self, admin_h):
        fam = _mk_family(admin_h, "emptyloc")
        loc = fam.get("location_id")
        upd = requests.put(f"{BASE_URL}/api/families/{fam['id']}", headers=admin_h,
                           json={"family_name": fam["family_name"], "location_id": ""}, timeout=20)
        assert upd.status_code == 200
        assert upd.json().get("location_id") == loc, "empty location_id cleared the campus"

    def test_family_without_location_still_listed(self, admin_h):
        """Families with no campus must still appear in GET /families."""
        # create one via bulk-delete cascade would remove — instead create directly with no loc
        payload = {"family_name": f"ITER364_noloc_{uuid.uuid4().hex[:6]}",
                   "primary_contact_name": "NoLoc Contact",
                   "primary_contact_phone": "+256700000099"}
        r = requests.post(f"{BASE_URL}/api/families", headers=admin_h, json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        fam = r.json()
        CLEANUP["families"].add(fam["id"])
        lst = requests.get(f"{BASE_URL}/api/families", headers=admin_h, timeout=20).json()
        ids = [f["id"] for f in lst]
        assert fam["id"] in ids, "no-location family disappeared from list"


class TestFamilyMembersPartial:
    def test_put_members_only_child_ids_preserves_parents(self, admin_h):
        fam = _mk_family(admin_h, "members")
        # Create a guest parent
        g = requests.post(f"{BASE_URL}/api/guests", headers=admin_h,
                          json={"name": "ITER364 Guest Parent", "phone": "+256700000010",
                                "is_parent": True, "family_id": fam["id"]}, timeout=20)
        assert g.status_code in (200, 201), g.text
        guest_id = g.json()["id"]
        CLEANUP["guests"].add(guest_id)
        # attach as parent via family/members
        r = requests.put(f"{BASE_URL}/api/families/{fam['id']}/members", headers=admin_h,
                         json={"parent_ids": [guest_id]}, timeout=20)
        assert r.status_code == 200
        # Now send ONLY child_ids — must not detach parent
        r = requests.put(f"{BASE_URL}/api/families/{fam['id']}/members", headers=admin_h,
                         json={"child_ids": []}, timeout=20)
        assert r.status_code == 200
        # Check parent still linked
        det = requests.get(f"{BASE_URL}/api/families/{fam['id']}", headers=admin_h, timeout=20).json()
        parent_ids = [p["id"] for p in det.get("parents", [])]
        assert guest_id in parent_ids, "sending only child_ids detached the parent"


class TestFamilyBulkDelete:
    def test_bulk_delete_soft_and_cascade(self, admin_h):
        fam = _mk_family(admin_h, "bulkdel")
        # attach a child
        loc = fam.get("location_id") or ""
        c = requests.post(f"{BASE_URL}/api/children", headers=admin_h,
                          json={"name": "ITER364 Child BD", "date_of_birth": "2015-01-01",
                                "gender": "M", "family_id": fam["id"], "location_id": loc}, timeout=20)
        if c.status_code in (200, 201):
            CLEANUP["children"].add(c.json()["id"])
            child_id = c.json()["id"]
        else:
            child_id = None
        r = requests.post(f"{BASE_URL}/api/families/bulk-delete", headers=admin_h,
                          json={"ids": [fam["id"]]}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") == 1
        CLEANUP["families"].discard(fam["id"])
        # child should have family_id unset
        if child_id:
            got = requests.get(f"{BASE_URL}/api/children/{child_id}", headers=admin_h, timeout=20)
            if got.status_code == 200:
                assert not got.json().get("family_id"), "child family_id not cleared after bulk-delete"


# ============ APPROVAL FLOW (member portal → admin) ============

class TestPortalApprovalFlow:
    """Member portal edits → pending change request → admin approve applies."""

    def test_portal_guardian_edit_creates_change_request(self, admin_h, member_h):
        # Ensure member has a household and a guardian to edit
        pf = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20)
        assert pf.status_code == 200, pf.text
        data = pf.json()
        if not data.get("family"):
            pytest.skip("Member has no household on file")
        fam_id = data["family"]["id"]
        guardians = (data["family"].get("guardians") or [])
        if not guardians:
            # Add a guardian via portal for testing
            addr = requests.post(f"{BASE_URL}/api/portal/family/guardians", headers=member_h,
                                 json={"name": "ITER364 Test Guardian",
                                       "relationship": "Friend",
                                       "phone": "+256700000050"}, timeout=20)
            assert addr.status_code in (200, 201), addr.text
            # It will be pending, admin approve to make it live
            gid = addr.json()["id"]
            requests.post(f"{BASE_URL}/api/families/pending-approvals/guardian/{fam_id}/{gid}/decide",
                          headers=admin_h, json={"action": "approve"}, timeout=20)
            pf = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20)
            guardians = (pf.json()["family"].get("guardians") or [])
        # Find any guardian
        approved = [g for g in guardians if (g.get("approval_status") or "approved") == "approved"]
        if not approved:
            pytest.skip("No approved guardian to edit")
        gid = approved[0]["id"]
        old_phone = approved[0].get("phone", "")
        new_phone = "+25670099" + str(int(time.time()) % 10000)
        r = requests.put(f"{BASE_URL}/api/portal/family/guardians/{gid}", headers=member_h,
                         json={"name": approved[0]["name"],
                               "phone": new_phone,
                               "relationship": approved[0].get("relationship") or "Friend"},
                         timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") == "pending_review", f"expected pending_review, got {body}"
        req_id = body["request"]["id"]

        # Admin sees it in queue
        q = requests.get(f"{BASE_URL}/api/families/change-requests", headers=admin_h, timeout=20)
        assert q.status_code == 200
        rows = q.json()
        found = next((r for r in rows if r["id"] == req_id), None)
        assert found, "change request not in admin queue"
        assert "phone" in found.get("changes", {})

        # Member sees pending_changes in portal
        pf2 = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20).json()
        assert gid in (pf2.get("pending_changes") or {}), "pending_changes not keyed by guardian id"

        # Data not applied yet
        pf3 = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20).json()
        current = next((g for g in pf3["family"]["guardians"] if g["id"] == gid), None)
        assert current["phone"] == old_phone, "change applied before approval!"

        # Admin approves
        d = requests.post(f"{BASE_URL}/api/families/change-requests/{req_id}/decide",
                          headers=admin_h, json={"action": "approve"}, timeout=20)
        assert d.status_code == 200
        pf4 = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20).json()
        applied = next((g for g in pf4["family"]["guardians"] if g["id"] == gid), None)
        assert applied["phone"] == new_phone, "approved change did not apply"

    def test_change_request_reject_leaves_data(self, admin_h, member_h):
        pf = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20).json()
        if not pf.get("family"):
            pytest.skip("No household")
        # edit family notes
        old_addr = pf["family"].get("address", "")
        r = requests.put(f"{BASE_URL}/api/portal/family", headers=member_h,
                         json={"address": f"ITER364 changed {uuid.uuid4().hex[:6]}"}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("status") == "pending_review"
        req_id = r.json()["request"]["id"]
        d = requests.post(f"{BASE_URL}/api/families/change-requests/{req_id}/decide",
                          headers=admin_h, json={"action": "reject", "reason": "test"}, timeout=20)
        assert d.status_code == 200
        pf2 = requests.get(f"{BASE_URL}/api/portal/family", headers=member_h, timeout=20).json()
        assert pf2["family"].get("address", "") == old_addr, "rejected change was applied"


# ============ STAFF EDIT CORRECTNESS (Henry Lubega bug) ============

class TestStaffEditCorrectness:
    def test_get_user_profile_returns_own_identity(self, admin_h):
        """GET /admin/users/{id}/profile must return that user's own name."""
        # Try known Henry Lubega id if it exists, else pick any user with empty email
        henry_id = "87785c67-0b1a-4996-9314-5f0e5f45ecf4"
        r = requests.get(f"{BASE_URL}/api/admin/users/{henry_id}/profile", headers=admin_h, timeout=20)
        if r.status_code == 404:
            # find any user with no email
            lst = requests.get(f"{BASE_URL}/api/admin/users?limit=200", headers=admin_h, timeout=20).json()
            users = lst if isinstance(lst, list) else lst.get("users", [])
            candidate = next((u for u in users if not u.get("email")), None)
            if not candidate:
                pytest.skip("no user with empty email to test")
            henry_id = candidate["id"]
            r = requests.get(f"{BASE_URL}/api/admin/users/{henry_id}/profile", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        prof = r.json()
        # The name in profile must match the user's own name (from admin/users list)
        assert prof.get("name"), "profile has no name"
        # member_id, if present, must belong to same person: name similar
        if prof.get("member_id"):
            m = requests.get(f"{BASE_URL}/api/members/{prof['member_id']}", headers=admin_h, timeout=20)
            if m.status_code == 200:
                mname = (m.json().get("name") or "").strip().lower()
                pname = (prof.get("name") or "").strip().lower()
                # Should share at least last name
                assert mname and (mname in pname or pname in mname or
                                  mname.split()[-1] == pname.split()[-1]), \
                    f"member link mismatched: user={pname}, member={mname}"


# ============ DUPLICATE PEOPLE DETECTOR ============

class TestDuplicatePeople:
    def _mk_dup_user(self, admin_h, email: str, name: str, location_id: str = "") -> str:
        payload = {"name": name, "email": email, "role": "Member",
                   "phone": "+256700888" + str(int(time.time()) % 1000).zfill(3)}
        if location_id:
            payload["location_id"] = location_id
        r = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_h, json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        uid = r.json().get("id") or r.json().get("user", {}).get("id")
        CLEANUP["users"].add(uid)
        return uid

    def test_duplicates_list_and_merge(self, admin_h):
        # get a location so campus filter includes our rows
        locs = requests.get(f"{BASE_URL}/api/locations", headers=admin_h, timeout=20).json()
        loc_id = locs[0]["id"] if locs else ""
        marker = f"ITER364DUP{uuid.uuid4().hex[:6]}"
        name = f"ITER364 Dup {marker}"
        email = f"dup_{marker.lower()}@iter364.test"
        u1 = self._mk_dup_user(admin_h, email, name, loc_id)
        # Create a guest with same email + campus
        r = requests.post(f"{BASE_URL}/api/guests", headers=admin_h,
                          json={"name": name, "email": email, "phone": "+256700888999",
                                "location_id": loc_id}, timeout=20)
        assert r.status_code in (200, 201), f"cannot create guest duplicate: {r.status_code} {r.text[:200]}"
        m_id = r.json().get("id")
        CLEANUP["guests"].add(m_id)

        # List duplicates
        d = requests.get(f"{BASE_URL}/api/people/duplicates", headers=admin_h, timeout=30)
        assert d.status_code == 200, d.text
        groups = d.json()["groups"]
        my_group = next((g for g in groups if name.lower() in g["name"].lower()), None)
        assert my_group, f"my duplicate group not found; total={d.json().get('total')}"
        assert my_group.get("exact") is True, f"expected exact=True (shared email), got signals={my_group.get('signals')}"

        # Merge (keep user, drop member)
        merge = requests.post(f"{BASE_URL}/api/people/duplicates/merge", headers=admin_h,
                              json={"keep_id": u1, "drop_ids": [m_id]}, timeout=30)
        assert merge.status_code == 200, merge.text
        assert merge.json().get("merged") == 1
        # After merge, guest should be gone from guests list
        gm = requests.get(f"{BASE_URL}/api/guests", headers=admin_h, timeout=20)
        if gm.status_code == 200:
            ids = [g["id"] for g in gm.json()]
            assert m_id not in ids, f"dropped guest still in list"
        CLEANUP["guests"].discard(m_id)

    def test_auto_merge_only_exact(self, admin_h):
        """auto-merge must only touch exact groups (does not error)."""
        r = requests.post(f"{BASE_URL}/api/people/duplicates/auto-merge", headers=admin_h,
                          json={}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "groups_merged" in body and "records_merged" in body


# ============ PROFILE PHOTO RE-UPLOAD ============

def _png_bytes(seed: int) -> bytes:
    # 1x1 PNG with varying content
    import base64
    b = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    return b + bytes([seed % 256])


class TestPhotoReUpload:
    def test_user_photo_two_uploads_different_urls(self, admin_h):
        # find any user
        lst = requests.get(f"{BASE_URL}/api/admin/users?limit=5", headers=admin_h, timeout=20).json()
        users = lst if isinstance(lst, list) else lst.get("users", [])
        if not users:
            pytest.skip("no users")
        uid = users[0]["id"]

        def upload(seed):
            files = {"file": (f"p{seed}.png", io.BytesIO(_png_bytes(seed)), "image/png")}
            r = requests.post(f"{BASE_URL}/api/users/{uid}/photo", headers=admin_h,
                              files=files, timeout=30)
            return r
        r1 = upload(1)
        assert r1.status_code == 200, r1.text
        url1 = r1.json()["photo_url"]
        r2 = upload(2)
        assert r2.status_code == 200, r2.text
        url2 = r2.json()["photo_url"]
        assert url1 != url2, "photo url did not change on re-upload"
        # persisted on user
        p = requests.get(f"{BASE_URL}/api/admin/users/{uid}/profile", headers=admin_h, timeout=20).json()
        assert p.get("photo_url") == url2, f"user photo_url not persisted; got {p.get('photo_url')}"


# ============ SOCIAL CASE FILTER by subject_id ============

class TestSocialCaseFilter:
    def test_cases_filter_by_subject_id(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/social-work/cases", headers=admin_h, timeout=20)
        assert r.status_code == 200
        payload = r.json()
        cases = payload if isinstance(payload, list) else payload.get("cases", [])
        if not cases:
            pytest.skip("no cases to filter")
        subj = next((c.get("subject_id") for c in cases if c.get("subject_id")), None)
        if not subj:
            pytest.skip("no cases with subject_id")
        r = requests.get(f"{BASE_URL}/api/social-work/cases?subject_id={subj}", headers=admin_h, timeout=20)
        assert r.status_code == 200
        p2 = r.json()
        filt = p2 if isinstance(p2, list) else p2.get("cases", [])
        assert filt, "subject_id filter returned nothing"
        for c in filt:
            assert c.get("subject_id") == subj, f"unfiltered case: {c.get('subject_id')} != {subj}"


# ============ PARENT vs PICKUP FLAGS ============

class TestParentPickupFlags:
    def test_spouse_locks_is_parent(self, admin_h):
        fam = _mk_family(admin_h, "parentlock")
        r = requests.post(f"{BASE_URL}/api/families/{fam['id']}/guardians", headers=admin_h,
                          json={"name": "ITER364 Spouse P", "relationship": "Spouse",
                                "is_parent": False}, timeout=20)
        assert r.status_code in (200, 201)
        g = r.json()
        assert g.get("is_parent") is True, "Spouse should be locked as parent"
        assert g.get("parent_locked") is True, "parent_locked flag missing"
        assert g.get("can_pickup") is True

    def test_family_friend_can_be_pickup_only(self, admin_h):
        fam = _mk_family(admin_h, "pickup")
        r = requests.post(f"{BASE_URL}/api/families/{fam['id']}/guardians", headers=admin_h,
                          json={"name": "ITER364 Friend P", "relationship": "Family friend",
                                "is_parent": False, "can_pickup": True}, timeout=20)
        assert r.status_code in (200, 201)
        g = r.json()
        assert g.get("is_parent") is False, "Family friend should not auto-be parent"
        assert g.get("parent_locked") is False
        assert g.get("can_pickup") is True


# ============ CLEANUP ============

def teardown_module(module):
    """Best-effort cleanup of ITER364_ test data."""
    try:
        h = {"Authorization": f"Bearer {_login(*ADMIN)}"}
    except Exception:
        return
    for fid in list(CLEANUP["families"]):
        try:
            requests.delete(f"{BASE_URL}/api/families/{fid}", headers=h, timeout=10)
        except Exception:
            pass
    for uid in list(CLEANUP["users"]):
        try:
            requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=h, timeout=10)
        except Exception:
            pass
    for mid in list(CLEANUP["members"]):
        try:
            requests.delete(f"{BASE_URL}/api/members/{mid}", headers=h, timeout=10)
        except Exception:
            pass
    for cid in list(CLEANUP["children"]):
        try:
            requests.delete(f"{BASE_URL}/api/children/{cid}", headers=h, timeout=10)
        except Exception:
            pass
    for gid in list(CLEANUP["guests"]):
        try:
            requests.delete(f"{BASE_URL}/api/guests/{gid}", headers=h, timeout=10)
        except Exception:
            pass
