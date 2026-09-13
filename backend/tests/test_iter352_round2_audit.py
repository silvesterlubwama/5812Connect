"""iter352 — round-2 security-audit remediation regression suite.

Round-1 verified at iter351. This suite covers the 4 HIGH + 1 MEDIUM
follow-up findings + regression checks:

  R2-1  cross-campus by-id reads now 404 for social-work notes/payments,
        review get/put/delete, member profile-pdf
  R2-2  privilege escalation via /admin/users/{id}/reset-password blocked
        for callers below level 10
  R2-3  active-campus pin no longer leaks sibling campuses to non-switchers
  R2-4  kiosk/pin-checkin lookup — no child DOB + per-IP throttle +
        per-socket safety net against X-Forwarded-For spoofing
  R2-5  kiosk unlock: unknown identifier vs real+wrong-password return the
        identical 401 body AND comparable time (dummy bcrypt burn)
  Payslip PDF cross-campus scoping (owner always allowed)
"""
import os
import time
import uuid
import statistics
import pytest
import requests
from pymongo import MongoClient

import creds

BASE = creds.BASE_URL
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "5812global")
_mc = MongoClient(MONGO_URL)
db = _mc[DB_NAME]

CASE_A_ID = "sc_140b496b"          # seeded case at loc_001 (Central)
DIR_PASSWORD = "TestDir@5812!"
MEMBER_RESET_PASSWORD = "MemberReset@5812!"


# ---------- helpers ----------

def _login(email, password):
    return requests.post(f"{BASE}/api/auth/login",
                         json={"identifier": email, "password": password}, timeout=15)


def _clear_public_hits(action=None):
    q = {"action": action} if action else {}
    db.public_endpoint_hits.delete_many(q)


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============================================================
# R2-1  Cross-campus by-id 404 + own-campus 200
# ============================================================

@pytest.fixture(scope="module")
def scoping_env(admin_headers):
    """Create campus B + Director scoped only to campus B, plus own review + own member."""
    r = requests.get(f"{BASE}/api/social-work/cases/{CASE_A_ID}",
                     headers=admin_headers, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"seed case {CASE_A_ID} missing")
    case_a = r.json()
    campus_a = case_a.get("location_id")

    # Ensure a note + payment + review + member exist in campus A (seed via db).
    note_a = f"note_TEST_A_{uuid.uuid4().hex[:6]}"
    db.social_case_notes.insert_one({
        "id": note_a, "case_id": CASE_A_ID, "body": "campus A note",
        "note_type": "general", "author_id": "seed", "author_name": "seed",
        "created_at": "2026-01-01T00:00:00Z", "location_id": campus_a,
    })
    pay_a = f"pay_TEST_A_{uuid.uuid4().hex[:6]}"
    db.social_child_payments.insert_one({
        "id": pay_a, "case_id": CASE_A_ID, "amount": 10, "currency": "USD",
        "date": "2026-01-01", "location_id": campus_a,
    })
    review_a = f"rev_TEST_A_{uuid.uuid4().hex[:8]}"
    db.social_review_forms.insert_one({
        "id": review_a, "child_id": "test_child_A", "child_name": "Test Child A",
        "kind": "welfare_visit", "review_date": "2026-01-01",
        "fields": {}, "action_plan": [], "location_id": campus_a,
        "created_at": "2026-01-01T00:00:00Z",
    })
    member_a = f"mem_TEST_A_{uuid.uuid4().hex[:6]}"
    db.members.insert_one({
        "id": member_a, "name": "TEST Member A", "email": f"{member_a}@test.local",
        "phone": "+256700000001", "role": "member",
        "location_id": campus_a, "location_ids": [campus_a],
        "status": "active", "created_at": "2026-01-01T00:00:00Z",
    })

    # Campus B
    lb = requests.post(f"{BASE}/api/locations",
                       json={"name": f"TEST_R2_Campus_B_{uuid.uuid4().hex[:6]}",
                             "type": "campus"},
                       headers=admin_headers, timeout=15)
    assert lb.status_code in (200, 201), lb.text
    campus_b = lb.json().get("id") or lb.json().get("_id")

    dir_email = f"test.r2.dir.{uuid.uuid4().hex[:6]}@test.local"
    ru = requests.post(f"{BASE}/api/admin/users", json={
        "email": dir_email, "name": "TEST R2 Director",
        "password": DIR_PASSWORD, "role": "Director",
        "location_id": campus_b, "location_ids": [campus_b],
    }, headers=admin_headers, timeout=15)
    assert ru.status_code in (200, 201), ru.text
    dir_user = ru.json()
    dir_id = dir_user["id"]

    tok = _login(dir_email, DIR_PASSWORD).json()["token"]
    dir_headers = {"Authorization": f"Bearer {tok}"}

    # Own campus-B artifacts (seed directly to bypass subject-existence rules)
    case_b = f"sc_TEST_B_{uuid.uuid4().hex[:8]}"
    db.social_cases.insert_one({
        "id": case_b, "subject_kind": "child",
        "subject_id": f"test_child_B_{uuid.uuid4().hex[:6]}",
        "subject_name": "TEST Child B", "category": "child_development",
        "status": "active", "location_id": campus_b, "opened_by": dir_id,
        "opened_at": "2026-01-01T00:00:00Z",
    })
    note_b = f"note_TEST_B_{uuid.uuid4().hex[:6]}"
    db.social_case_notes.insert_one({
        "id": note_b, "case_id": case_b, "body": "campus B note",
        "note_type": "general", "author_id": dir_id, "author_name": "TEST R2 Director",
        "created_at": "2026-01-01T00:00:00Z", "location_id": campus_b,
    })
    review_b = f"rev_TEST_B_{uuid.uuid4().hex[:8]}"
    db.social_review_forms.insert_one({
        "id": review_b, "child_id": "test_child_B", "child_name": "TEST Child B",
        "kind": "welfare_visit", "review_date": "2026-01-01",
        "fields": {}, "action_plan": [], "location_id": campus_b,
        "created_at": "2026-01-01T00:00:00Z",
    })
    member_b = f"mem_TEST_B_{uuid.uuid4().hex[:6]}"
    db.members.insert_one({
        "id": member_b, "name": "TEST Member B", "email": f"{member_b}@test.local",
        "phone": "+256700000002", "role": "member",
        "location_id": campus_b, "location_ids": [campus_b],
        "status": "active", "created_at": "2026-01-01T00:00:00Z",
    })

    yield {
        "campus_a": campus_a, "campus_b": campus_b,
        "dir_headers": dir_headers, "dir_id": dir_id, "dir_email": dir_email,
        "note_a": note_a, "pay_a": pay_a, "review_a": review_a, "member_a": member_a,
        "case_b": case_b, "note_b": note_b, "review_b": review_b, "member_b": member_b,
    }

    # ---- cleanup ----
    try:
        db.social_case_notes.delete_many({"id": {"$in": [note_a, note_b]}})
        db.social_child_payments.delete_one({"id": pay_a})
        db.social_review_forms.delete_many({"id": {"$in": [review_a, review_b]}})
        db.members.delete_many({"id": {"$in": [member_a, member_b]}})
        db.social_cases.delete_one({"id": case_b})
        requests.delete(f"{BASE}/api/admin/users/{dir_id}", headers=admin_headers, timeout=10)
        db.locations.delete_one({"id": campus_b})
    except Exception:
        pass


class TestR21CrossCampus:

    # --- Director on campus A endpoints → 404 ---

    def test_dir_notes_case_A_404(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/cases/{CASE_A_ID}/notes",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_dir_payments_case_A_404(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/cases/{CASE_A_ID}/payments",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_dir_review_get_A_404(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/reviews/{scoping_env['review_a']}",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_dir_review_put_A_404(self, scoping_env):
        r = requests.put(f"{BASE}/api/social-work/reviews/{scoping_env['review_a']}",
                         json={"overall_assessment": "hacked"},
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_dir_review_delete_A_404(self, scoping_env):
        r = requests.delete(f"{BASE}/api/social-work/reviews/{scoping_env['review_a']}",
                            headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 404

    def test_dir_profile_pdf_A_404(self, scoping_env):
        r = requests.get(f"{BASE}/api/members/{scoping_env['member_a']}/profile-pdf",
                         headers=scoping_env["dir_headers"], timeout=20)
        assert r.status_code == 404

    # --- Director on OWN campus B → 200 ---

    def test_dir_notes_case_B_200(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/cases/{scoping_env['case_b']}/notes",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_dir_payments_case_B_200(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/cases/{scoping_env['case_b']}/payments",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 200

    def test_dir_review_get_B_200(self, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/reviews/{scoping_env['review_b']}",
                         headers=scoping_env["dir_headers"], timeout=15)
        assert r.status_code == 200

    def test_dir_profile_pdf_B_200(self, scoping_env):
        r = requests.get(f"{BASE}/api/members/{scoping_env['member_b']}/profile-pdf",
                         headers=scoping_env["dir_headers"], timeout=20)
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "").lower() or \
               "html" in r.headers.get("content-type", "").lower()

    # --- Admin on campus A → 200 ---

    def test_admin_notes_A_200(self, admin_headers):
        r = requests.get(f"{BASE}/api/social-work/cases/{CASE_A_ID}/notes",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_admin_payments_A_200(self, admin_headers):
        r = requests.get(f"{BASE}/api/social-work/cases/{CASE_A_ID}/payments",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_admin_review_A_200(self, admin_headers, scoping_env):
        r = requests.get(f"{BASE}/api/social-work/reviews/{scoping_env['review_a']}",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_admin_profile_pdf_A_200(self, admin_headers, scoping_env):
        r = requests.get(f"{BASE}/api/members/{scoping_env['member_a']}/profile-pdf",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200


# ============================================================
# R2-2  Privilege escalation via password reset
# ============================================================

class TestR22ResetPasswordEscalation:

    def test_director_cannot_reset_admin(self, admin_headers, scoping_env):
        # Find the primary admin user id
        admin_user = db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "id": 1})
        assert admin_user
        r = requests.post(
            f"{BASE}/api/admin/users/{admin_user['id']}/reset-password",
            json={"new_password": "PWNED@1234"},
            headers=scoping_env["dir_headers"], timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"
        assert "own level or above" in r.text.lower() or "cannot reset" in r.text.lower(), r.text

        # Admin login must still work with the ORIGINAL password
        rl = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert rl.status_code == 200, "admin lost their password!"

    def test_director_can_reset_member(self, admin_headers, scoping_env):
        # Create a throwaway Member in the director's campus
        email = f"test.r2.member.{uuid.uuid4().hex[:6]}@test.local"
        ru = requests.post(f"{BASE}/api/admin/users", json={
            "email": email, "name": "TEST R2 Member",
            "password": "OldMemberPass1!", "role": "Member",
            "location_id": scoping_env["campus_b"],
            "location_ids": [scoping_env["campus_b"]],
        }, headers=admin_headers, timeout=15)
        assert ru.status_code in (200, 201), ru.text
        member_id = ru.json()["id"]
        try:
            r = requests.post(
                f"{BASE}/api/admin/users/{member_id}/reset-password",
                json={"new_password": MEMBER_RESET_PASSWORD},
                headers=scoping_env["dir_headers"], timeout=15,
            )
            assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
            # Member can log in with the new password
            rl = _login(email, MEMBER_RESET_PASSWORD)
            assert rl.status_code == 200, "member login with new pw failed"
        finally:
            requests.delete(f"{BASE}/api/admin/users/{member_id}",
                            headers=admin_headers, timeout=10)

    def test_admin_can_reset_throwaway_admin(self, admin_headers):
        # Create a throwaway admin, reset via another admin (the fixture admin),
        # then log in. The target admin must NOT be one of the protected accounts.
        email = f"test.r2.admin.{uuid.uuid4().hex[:6]}@test.local"
        ru = requests.post(f"{BASE}/api/admin/users", json={
            "email": email, "name": "TEST R2 Throwaway Admin",
            "password": "OldAdminPass1!", "role": "admin",
        }, headers=admin_headers, timeout=15)
        if ru.status_code not in (200, 201):
            pytest.skip(f"cannot create throwaway admin: {ru.status_code} {ru.text[:120]}")
        target_id = ru.json()["id"]
        assert email != "admin@5812uganda.org"
        assert email != "admin@5812global.org"
        try:
            r = requests.post(
                f"{BASE}/api/admin/users/{target_id}/reset-password",
                json={"new_password": "NewThrowawayPass1!"},
                headers=admin_headers, timeout=15,
            )
            assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
            rl = _login(email, "NewThrowawayPass1!")
            assert rl.status_code == 200
        finally:
            requests.delete(f"{BASE}/api/admin/users/{target_id}",
                            headers=admin_headers, timeout=10)


# ============================================================
# R2-3  Active-campus pin must not leak siblings
# ============================================================

class TestR23ActiveCampusPin:

    @pytest.fixture(scope="class")
    def topology(self, admin_headers):
        # Region already exists as loc_001; ensure two campuses under it.
        # Build a sub-location under one of them for the non-switcher user.
        # Anchor to a true region root — a location with no parent AND
        # type != 'campus' (otherwise ephemeral test-created campuses without
        # parent_id can be picked up here and skew the child-campus count).
        region = db.locations.find_one(
            {"parent_id": {"$in": [None, ""]}, "type": {"$ne": "campus"}},
            {"_id": 0, "id": 1},
        )
        if not region:
            pytest.skip("no root region")
        region_id = region["id"]
        campuses = list(db.locations.find(
            {"parent_id": region_id, "type": "campus"},
            {"_id": 0, "id": 1, "name": 1},
        ).limit(2))
        if len(campuses) < 2:
            pytest.skip("need at least 2 child campuses under the region")
        camp_a, camp_b = campuses[0]["id"], campuses[1]["id"]

        # Sub-location under camp A
        sub_id = f"loc_TEST_sub_{uuid.uuid4().hex[:6]}"
        db.locations.insert_one({
            "id": sub_id, "name": f"TEST_Sub_of_A_{uuid.uuid4().hex[:4]}",
            "type": "sub-location", "parent_id": camp_a,
        })

        # Non-switcher user (Manager) assigned ONLY to sub_id
        email = f"test.r2.mgr.{uuid.uuid4().hex[:6]}@test.local"
        pwd = "MgrPass1!"
        ru = requests.post(f"{BASE}/api/admin/users", json={
            "email": email, "name": "TEST R2 Manager", "password": pwd,
            "role": "Manager", "location_id": sub_id, "location_ids": [sub_id],
        }, headers=admin_headers, timeout=15)
        assert ru.status_code in (200, 201), ru.text
        mgr_id = ru.json()["id"]
        mtok = _login(email, pwd).json()["token"]
        mgr_headers = {"Authorization": f"Bearer {mtok}"}

        # Seed one event in each campus so the leak (or lack of it) is observable
        ev_a = f"ev_TEST_A_{uuid.uuid4().hex[:6]}"
        db.events.insert_one({"id": ev_a, "title": "TEST event A",
                              "location_id": camp_a, "status": "upcoming",
                              "date": "2099-12-31", "type": "general",
                              "created_at": "2026-01-01T00:00:00Z"})
        ev_b = f"ev_TEST_B_{uuid.uuid4().hex[:6]}"
        db.events.insert_one({"id": ev_b, "title": "TEST event B",
                              "location_id": camp_b, "status": "upcoming",
                              "date": "2099-12-31", "type": "general",
                              "created_at": "2026-01-01T00:00:00Z"})

        yield {
            "region": region_id, "camp_a": camp_a, "camp_b": camp_b,
            "sub_id": sub_id, "mgr_id": mgr_id, "mgr_headers": mgr_headers,
            "ev_a": ev_a, "ev_b": ev_b,
        }
        # Cleanup
        db.events.delete_many({"id": {"$in": [ev_a, ev_b]}})
        db.locations.delete_one({"id": sub_id})
        requests.delete(f"{BASE}/api/admin/users/{mgr_id}",
                        headers=admin_headers, timeout=10)

    def test_manager_can_pin_parent_region(self, topology):
        r = requests.put(f"{BASE}/api/user/active-campus",
                         json={"campus_id": topology["region"]},
                         headers=topology["mgr_headers"], timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_manager_pin_region_does_not_leak_sibling_campus(self, topology):
        # After pinning the region, events list must NOT include a campus-B event
        r = requests.get(f"{BASE}/api/events",
                         headers=topology["mgr_headers"], timeout=15)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("events", [])
        ids = {t.get("id") for t in items}
        assert topology["ev_b"] not in ids, "Campus B event leaked to non-switcher pinning parent"

    def test_admin_pin_region_sees_both(self, admin_headers, topology):
        # Admin pin same region, should see BOTH campus A and B events
        r = requests.put(f"{BASE}/api/user/active-campus",
                         json={"campus_id": topology["region"]},
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        try:
            rt = requests.get(f"{BASE}/api/events", headers=admin_headers, timeout=15)
            assert rt.status_code == 200
            items = rt.json() if isinstance(rt.json(), list) else rt.json().get("events", [])
            ids = {t.get("id") for t in items}
            assert topology["ev_a"] in ids, "admin should see campus A"
            assert topology["ev_b"] in ids, "admin should see campus B"
        finally:
            requests.put(f"{BASE}/api/user/active-campus/clear",
                         headers=admin_headers, timeout=10)


# ============================================================
# R2-4  Kiosk PIN check-in — no child DOB + spoof safety net
# ============================================================

class TestR24KioskPinCheckin:

    @pytest.fixture(scope="class")
    def parent_with_child(self, admin_headers):
        """Seed a member (parent) + child sharing family_id so lookup returns children."""
        family_id = f"fam_TEST_{uuid.uuid4().hex[:6]}"
        parent_phone = f"+2567{uuid.uuid4().int % 100000000:08d}"
        parent_id = f"mem_TEST_par_{uuid.uuid4().hex[:6]}"
        db.members.insert_one({
            "id": parent_id, "name": "TEST Kiosk Parent",
            "phone": parent_phone, "email": f"{parent_id}@test.local",
            "role": "Parent", "is_parent": True,
            "family_id": family_id, "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
        })
        child_id = f"ch_TEST_{uuid.uuid4().hex[:6]}"
        db.children.insert_one({
            "id": child_id, "name": "TEST Kiosk Child",
            "family_id": family_id, "parent_ids": [parent_id],
            "date_of_birth": "2018-06-15", "photo_url": "",
            "created_at": "2026-01-01T00:00:00Z",
        })
        yield {"phone": parent_phone, "parent_id": parent_id, "child_id": child_id,
               "family_id": family_id}
        db.children.delete_one({"id": child_id})
        db.members.delete_one({"id": parent_id})

    def test_lookup_returns_no_child_dob(self, parent_with_child):
        _clear_public_hits("kiosk_pin_checkin")
        last4 = parent_with_child["phone"][-4:]
        r = requests.post(f"{BASE}/api/kiosk/pin-checkin",
                          json={"pin": last4, "action": "lookup"},
                          headers={"X-Forwarded-For": "10.11.11.1"}, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body.get("member_name")
        children = body.get("children") or []
        assert children, "expected the parent's child in response"
        for c in children:
            assert "date_of_birth" not in c, f"DOB leaked on child: {c.keys()}"
            assert "dob" not in c
            # Only these keys allowed
            extras = set(c.keys()) - {"id", "name", "photo_url", "family_id"}
            assert not extras, f"unexpected child keys leaked: {extras}"

    def test_rate_limit_per_ip_around_20(self, parent_with_child):
        _clear_public_hits("kiosk_pin_checkin")
        ip = "10.11.11.99"
        last4 = parent_with_child["phone"][-4:]
        codes = []
        for _ in range(25):
            r = requests.post(f"{BASE}/api/kiosk/pin-checkin",
                              json={"pin": last4, "action": "lookup"},
                              headers={"X-Forwarded-For": ip}, timeout=15)
            codes.append(r.status_code)
        assert 429 in codes, f"expected per-IP 429, got {codes}"
        first_429 = codes.index(429) + 1
        assert 19 <= first_429 <= 22, f"per-IP 429 should hit ~20th, actually {first_429}"

    def test_socket_spoof_safety_net(self, parent_with_child):
        """Rotate X-Forwarded-For to a fresh IP each call. After roughly 12x the
        per-IP allowance (~240 calls) the per-socket safety net must also 429.

        In the k8s preview, requests may be spread across multiple ingress pods
        so socket_ip is not always stable — we tolerate that by checking the DB
        directly for socket_ip diversity and skipping if the environment can't
        pin a single socket bucket."""
        _clear_public_hits("kiosk_pin_checkin")
        last4 = parent_with_child["phone"][-4:]
        first_429 = None
        call_count = 0
        for i in range(300):
            ip = f"172.16.{(i // 250) % 256}.{i % 250 + 1}"
            r = requests.post(f"{BASE}/api/kiosk/pin-checkin",
                              json={"pin": last4, "action": "lookup"},
                              headers={"X-Forwarded-For": ip}, timeout=15)
            call_count += 1
            if r.status_code == 429:
                first_429 = i + 1
                break
        # Check DB — how many distinct socket_ips were recorded?
        try:
            distinct_sockets = len(db.public_endpoint_hits.distinct(
                "socket_ip", {"action": "kiosk_pin_checkin"}
            ))
        except Exception:
            distinct_sockets = -1
        _clear_public_hits("kiosk_pin_checkin")
        if first_429 is None:
            if distinct_sockets != 1:
                pytest.skip(
                    f"socket safety net cannot be validated: {distinct_sockets} distinct "
                    f"socket_ips seen across {call_count} calls (multi-ingress preview env)."
                )
            pytest.fail(f"socket safety net never fired within {call_count} spoofed IPs "
                        f"despite a single socket_ip bucket")
        assert 20 < first_429 <= 280, f"socket 429 at #{first_429} (should be around 12x=240)"


# ============================================================
# R2-5  Kiosk unlock — identical body + comparable timing
# ============================================================

class TestR25KioskUnlockTiming:

    def _post_time(self, body, ip):
        t0 = time.perf_counter()
        r = requests.post(f"{BASE}/api/kiosk/unlock",
                          json=body, headers={"X-Forwarded-For": ip}, timeout=15)
        return r, (time.perf_counter() - t0)

    def test_identical_body_and_comparable_time(self):
        _clear_public_hits("kiosk_unlock")
        # Warm up (JIT / connection)
        for _ in range(2):
            self._post_time({"identifier": ADMIN_EMAIL, "password": "warmup"}, "10.30.30.0")
        _clear_public_hits("kiosk_unlock")

        # Measure unknown-identifier path
        unknown_times = []
        for i in range(5):
            _clear_public_hits("kiosk_unlock")
            r, t = self._post_time(
                {"identifier": f"nobody+{uuid.uuid4().hex[:8]}@nope.io", "password": "pw"},
                f"10.30.30.{10 + i}",
            )
            assert r.status_code == 401
            assert r.json() == {"detail": "Invalid credentials"}
            unknown_times.append(t)

        # Measure real-user + wrong-password path
        real_times = []
        for i in range(5):
            _clear_public_hits("kiosk_unlock")
            r, t = self._post_time(
                {"identifier": ADMIN_EMAIL, "password": f"totally-wrong-{i}"},
                f"10.30.31.{10 + i}",
            )
            assert r.status_code == 401
            assert r.json() == {"detail": "Invalid credentials"}
            real_times.append(t)

        u_med = statistics.median(unknown_times) * 1000
        r_med = statistics.median(real_times) * 1000
        delta_ms = abs(u_med - r_med)
        ratio = min(u_med, r_med) / max(u_med, r_med) if max(u_med, r_med) else 1
        print(f"[R2-5] unknown median={u_med:.1f}ms real median={r_med:.1f}ms "
              f"delta={delta_ms:.1f}ms ratio={ratio:.2f}")
        # Comparable: the unknown path burns a dummy bcrypt verify. Bcrypt
        # dominates the response time (~50–200ms), so the two medians should
        # be within a factor of 2 across a public link.
        assert ratio >= 0.5, (
            f"timing oracle: unknown={u_med:.1f}ms real={r_med:.1f}ms "
            f"delta={delta_ms:.1f}ms ratio={ratio:.2f}"
        )

    def test_valid_pin_unlock_still_works(self):
        _clear_public_hits("kiosk_unlock")
        pin = "351824"
        u = db.users.find_one({"email": ADMIN_EMAIL.lower()}, {"_id": 0, "id": 1, "pin": 1})
        prev = u.get("pin")
        db.users.update_one({"id": u["id"]}, {"$set": {"pin": pin}})
        try:
            r = requests.post(f"{BASE}/api/kiosk/unlock",
                              json={"pin": pin},
                              headers={"X-Forwarded-For": "10.30.32.1"}, timeout=15)
            assert r.status_code == 200, f"{r.status_code} {r.text}"
            assert r.json().get("unlocked") is True
        finally:
            if prev is None:
                db.users.update_one({"id": u["id"]}, {"$unset": {"pin": ""}})
            else:
                db.users.update_one({"id": u["id"]}, {"$set": {"pin": prev}})


# ============================================================
# Regression — payslip PDF scoping
# ============================================================

class TestPayslipPDFScoping:

    @pytest.fixture(scope="class")
    def payslip_env(self, admin_headers):
        # Find or create a staff user in loc_002 (Entebbe) with a payslip.
        campuses = list(db.locations.find(
            {"type": "campus"}, {"_id": 0, "id": 1}
        ).limit(2))
        if len(campuses) < 2:
            pytest.skip("need two campuses for payslip cross-campus test")
        camp_a, camp_b = campuses[0]["id"], campuses[1]["id"]

        # Staff in campus A
        staff_email = f"test.r2.staff.{uuid.uuid4().hex[:6]}@test.local"
        staff_pwd = "StaffPass1!"
        rs = requests.post(f"{BASE}/api/admin/users", json={
            "email": staff_email, "name": "TEST R2 Staff", "password": staff_pwd,
            "role": "Staff", "location_id": camp_a, "location_ids": [camp_a],
        }, headers=admin_headers, timeout=15)
        assert rs.status_code in (200, 201), rs.text
        staff_id = rs.json()["id"]

        # Director in campus B (different campus)
        dir_email = f"test.r2.dirB.{uuid.uuid4().hex[:6]}@test.local"
        dir_pwd = "DirBPass1!"
        rd = requests.post(f"{BASE}/api/admin/users", json={
            "email": dir_email, "name": "TEST R2 Director B", "password": dir_pwd,
            "role": "Director", "location_id": camp_b, "location_ids": [camp_b],
        }, headers=admin_headers, timeout=15)
        assert rd.status_code in (200, 201), rd.text
        dir_id = rd.json()["id"]

        # HR in campus A
        hr_email = f"test.r2.hrA.{uuid.uuid4().hex[:6]}@test.local"
        hr_pwd = "HRAPass1!"
        rh = requests.post(f"{BASE}/api/admin/users", json={
            "email": hr_email, "name": "TEST R2 HR A", "password": hr_pwd,
            "role": "HR", "location_id": camp_a, "location_ids": [camp_a],
        }, headers=admin_headers, timeout=15)
        assert rh.status_code in (200, 201), rh.text
        hr_id = rh.json()["id"]

        # Seed a payslip owned by staff, campus A
        payslip_id = f"ps_TEST_{uuid.uuid4().hex[:8]}"
        db.hr_payslips.insert_one({
            "id": payslip_id, "staff_id": staff_id, "staff_name": "TEST R2 Staff",
            "period": "2026-01", "location_id": camp_a,
            "payroll_location_id": camp_a,
            "gross": 100, "net": 90, "deductions": 10,
            "created_at": "2026-01-01T00:00:00Z",
        })

        staff_tok = _login(staff_email, staff_pwd).json()["token"]
        dir_tok = _login(dir_email, dir_pwd).json()["token"]
        hr_tok = _login(hr_email, hr_pwd).json()["token"]

        yield {
            "camp_a": camp_a, "camp_b": camp_b,
            "staff_id": staff_id, "payslip_id": payslip_id,
            "staff_headers": {"Authorization": f"Bearer {staff_tok}"},
            "dir_headers": {"Authorization": f"Bearer {dir_tok}"},
            "hr_headers": {"Authorization": f"Bearer {hr_tok}"},
        }
        db.hr_payslips.delete_one({"id": payslip_id})
        for uid in (staff_id, dir_id, hr_id):
            requests.delete(f"{BASE}/api/admin/users/{uid}", headers=admin_headers, timeout=10)

    def test_owner_can_download(self, payslip_env):
        r = requests.get(f"{BASE}/api/hr/payslips/{payslip_env['payslip_id']}/pdf",
                         headers=payslip_env["staff_headers"], timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_hr_same_campus_can_download(self, payslip_env):
        r = requests.get(f"{BASE}/api/hr/payslips/{payslip_env['payslip_id']}/pdf",
                         headers=payslip_env["hr_headers"], timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_director_other_campus_404(self, payslip_env):
        r = requests.get(f"{BASE}/api/hr/payslips/{payslip_env['payslip_id']}/pdf",
                         headers=payslip_env["dir_headers"], timeout=20)
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"

    def test_admin_can_download(self, admin_headers, payslip_env):
        r = requests.get(f"{BASE}/api/hr/payslips/{payslip_env['payslip_id']}/pdf",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200
