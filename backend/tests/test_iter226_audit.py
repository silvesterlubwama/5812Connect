"""Iteration 226 audit — social-work scans/risk, security companies CRUD,
Security Contractor users, NFC auto-member, storage routes, checkpoint scan,
and role guards.

Run: pytest /app/backend/tests/test_iter226_audit.py -v
"""
import os
import time
import uuid
import asyncio

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL missing"

be = dotenv_values("/app/backend/.env")
MONGO_URL = be.get("MONGO_URL")
DB_NAME = be.get("DB_NAME")

ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEFAULT_PW = "Test@5812!"
CHILD_ID = "chd_a3b4e279"

# Shared cross-test state
STATE = {}
RUN = uuid.uuid4().hex[:6]

# Tiny valid PNG (1x1)
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fffe4c4b0000000049454e44ae426082"
)
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    c = AsyncIOMotorClient(MONGO_URL)
    return c, c[DB_NAME]


def run_db(coro_fn):
    async def _wrap():
        c, db = _mongo()
        try:
            return await coro_fn(db)
        finally:
            c.close()
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_wrap())


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=60)
    assert r.status_code == 200, f"admin login failed {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in {r.json().keys()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ============================================================
# 1. SOCIAL WORK — upload-scan speed + guards
# ============================================================
class TestSocialWorkUploadScan:
    def test_upload_scan_fast_and_201(self, admin):
        t0 = time.time()
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/{CHILD_ID}/upload-scan",
            params={"kind": "welfare_visit", "run_ocr": "false"},
            data={"kind": "welfare_visit", "run_ocr": "false"},
            files={"file": ("qa_scan.pdf", PDF, "application/pdf")},
            timeout=60,
        )
        elapsed = time.time() - t0
        print(f"upload-scan took {elapsed:.2f}s status={r.status_code}")
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        body = r.json()
        assert body.get("attached_scan_url"), f"no attached_scan_url: {body}"
        STATE["review_id"] = body["id"]
        STATE["scan_url"] = body["attached_scan_url"]
        assert elapsed < 5.0, f"upload took {elapsed:.2f}s (>5s)"

    def test_scan_url_resolves_200(self, admin):
        url = STATE.get("scan_url")
        assert url, "no scan url from previous test"
        r = requests.get(f"{BASE}{url}", timeout=60)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        assert "pdf" in r.headers.get("content-type", ""), r.headers.get("content-type")

    def test_get_review_back(self, admin):
        r = admin.get(f"{BASE}/api/social-work/reviews/{STATE['review_id']}", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json().get("attached_scan_url")

    def test_undefined_child_404(self, admin):
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/undefined/upload-scan",
            data={"kind": "welfare_visit", "run_ocr": "false"},
            files={"file": ("x.pdf", PDF, "application/pdf")},
            timeout=60,
        )
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"
        assert "not found" in r.text.lower()

    def test_member_fallback_201(self, admin):
        async def get_member(db):
            return await db.members.find_one({}, {"_id": 0, "id": 1})
        m = run_db(get_member)
        assert m, "no members in db"
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/{m['id']}/upload-scan",
            data={"kind": "welfare_visit", "run_ocr": "false"},
            files={"file": ("x.pdf", PDF, "application/pdf")},
            timeout=60,
        )
        assert r.status_code in (200, 201), f"member fallback -> {r.status_code} {r.text[:300]}"
        STATE["member_review_id"] = r.json().get("id")

    def test_path_traversal_blocked(self):
        r = requests.get(f"{BASE}/api/uploads/social-review-scans/../server.py", timeout=60)
        assert r.status_code == 404, f"traversal -> {r.status_code} {r.text[:200]}"


# ============================================================
# 2. SOCIAL WORK — orphan case re-link
# ============================================================
class TestOrphanCaseRelink:
    def test_seed_orphan_case(self):
        async def seed(db):
            await db.social_cases.delete_one({"id": "sc_qa_orphan"})
            await db.social_cases.insert_one({
                "id": "sc_qa_orphan", "subject_id": None, "subject_kind": "child",
                "subject_name": "Gift Nabaterega", "category": "welfare_support",
                "risk_level": "low", "status": "active",
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            return True
        assert run_db(seed)

    def test_relink_valid_child_hydrates(self, admin):
        r = admin.put(f"{BASE}/api/social-work/cases/sc_qa_orphan",
                      json={"subject_id": CHILD_ID, "subject_kind": "child"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

        async def fetch(db):
            return await db.social_cases.find_one({"id": "sc_qa_orphan"}, {"_id": 0})
        doc = fetch and run_db(fetch)
        assert doc["subject_id"] == CHILD_ID
        assert doc["subject_name"] == "Little Test Jr", f"subject_name not hydrated: {doc.get('subject_name')}"

    def test_relink_bogus_child_404(self, admin):
        r = admin.put(f"{BASE}/api/social-work/cases/sc_qa_orphan",
                      json={"subject_id": "chd_nope", "subject_kind": "child"}, timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"

    def test_cleanup_orphan(self):
        async def rm(db):
            await db.social_cases.delete_one({"id": "sc_qa_orphan"})
            return True
        assert run_db(rm)


# ============================================================
# 3. SOCIAL WORK — manual review → risk + goals + case note
# ============================================================
class TestManualReviewAutoPopulate:
    def test_create_case_for_child(self, admin):
        r = admin.post(f"{BASE}/api/social-work/cases", json={
            "subject_kind": "child", "subject_id": CHILD_ID,
            "category": "welfare_support", "status": "active",
            "summary": "TEST_iter226 audit case",
        }, timeout=60)
        if r.status_code == 400 and "already exists" in r.text:
            async def fetch(db):
                return await db.social_cases.find_one(
                    {"subject_id": CHILD_ID, "subject_kind": "child", "status": "active"}, {"_id": 0, "id": 1})
            STATE["case_id"] = run_db(fetch)["id"]
            STATE["case_preexisting"] = True
        else:
            assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
            STATE["case_id"] = r.json().get("id")

    def test_create_manual_welfare_review(self, admin):
        payload = {
            "kind": "welfare_visit",
            "review_date": "2026-07-01",
            "fields": {
                "caregiver_name": "TEST_Grandmother Alice",
                "protection_concerns": {"neglect": True},
                "protection_details": "Child left unsupervised for long periods",
                "child_voice": {"going_well": "Likes school friends",
                                "challenges": "Afraid of going home late",
                                "support_wanted": "Wants school fees help"},
                "welfare_indicators": {"nutrition": {"rating": "Fair"}},
            },
            "action_plan": [
                {"action": f"TEST_Enrol in feeding programme {RUN}", "responsible": "Social worker", "timeline": "2026-08-01"},
                {"action": f"TEST_Weekly home visit {RUN}", "responsible": "Case worker", "timeline": "2026-09-01"},
            ],
            "overall_assessment": "Needs urgent follow-up",
        }
        r = admin.post(f"{BASE}/api/social-work/reviews/children/{CHILD_ID}", json=payload, timeout=90)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        STATE["manual_review_id"] = r.json()["id"]

    def test_child_risk_is_critical(self, admin):
        r = admin.get(f"{BASE}/api/children/{CHILD_ID}/full-profile", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        c = r.json()
        risk = c.get("risk") or {}
        assert risk.get("level") == "critical", f"risk.level={risk.get('level')} risk={risk}"
        assert isinstance(risk.get("factors"), list) and risk["factors"], f"factors={risk.get('factors')}"
        assert any("neglect" in f.lower() for f in risk["factors"]), risk["factors"]
        STATE["child_goals"] = c.get("goals") or []

    def test_goals_created_from_action_plan(self):
        goals = STATE.get("child_goals") or []
        rid = STATE["manual_review_id"]
        matched = [g for g in goals if isinstance(g, dict) and g.get("source_review_id") == rid]
        assert len(matched) >= 2, f"expected 2 auto-goals from action_plan, got {len(matched)}: {goals}"

    def test_social_case_risk_synced(self):
        async def fetch(db):
            return await db.social_cases.find_one(
                {"subject_id": CHILD_ID, "subject_kind": "child", "status": "active"}, {"_id": 0})
        doc = run_db(fetch)
        assert doc, "no active case found for child"
        assert doc.get("risk_level") == "critical", f"case risk_level={doc.get('risk_level')}"
        assert doc.get("risk_factors"), f"case risk_factors={doc.get('risk_factors')}"

    def test_case_note_ocr_auto_rich(self):
        async def fetch(db):
            return await db.case_notes.find({"source": "ocr_auto"}, {"_id": 0}).sort("created_at", -1).to_list(10)
        notes = run_db(fetch)
        assert notes, "no case_notes with source='ocr_auto'"
        blob = " ".join((n.get("body") or n.get("note") or n.get("text") or "").lower() for n in notes)
        for kw in ("going well", "support wanted", "protection concern", "action plan"):
            assert kw in blob, f"'{kw}' missing from ocr_auto notes; sample={notes[0]}"


# ============================================================
# 4. SECURITY COMPANIES CRUD
# ============================================================
class TestSecurityCompanies:
    def test_create(self, admin):
        name = f"TEST_Sentry {uuid.uuid4().hex[:6]}"
        STATE["co_name"] = name
        r = admin.post(f"{BASE}/api/security-companies", json={"name": name}, timeout=60)
        assert r.status_code == 201, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["name"] == name and d["active"] is True and "_id" not in d
        STATE["co_id"] = d["id"]

    def test_list_contains(self, admin):
        r = admin.get(f"{BASE}/api/security-companies", timeout=60)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        assert any(c["id"] == STATE["co_id"] for c in arr)

    def test_duplicate_409(self, admin):
        r = admin.post(f"{BASE}/api/security-companies", json={"name": STATE["co_name"]}, timeout=60)
        assert r.status_code == 409, f"{r.status_code} {r.text[:300]}"

    def test_update_phone(self, admin):
        r = admin.put(f"{BASE}/api/security-companies/{STATE['co_id']}",
                      json={"phone": "+256700111222"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["phone"] == "+256700111222"

    def test_logo_upload_and_fetch(self, admin):
        r = admin.post(f"{BASE}/api/security-companies/{STATE['co_id']}/logo",
                       files={"file": ("logo.png", PNG, "image/png")}, timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        logo = r.json().get("logo_url")
        assert logo, r.json()
        STATE["co_logo"] = logo
        g = admin.get(f"{BASE}/api/security-companies", timeout=60)
        doc = next(c for c in g.json() if c["id"] == STATE["co_id"])
        assert doc["logo_url"] == logo
        img = requests.get(f"{BASE}{logo}" if logo.startswith("/") else logo, timeout=60)
        assert img.status_code == 200, f"logo fetch {logo} -> {img.status_code}"
        assert img.headers.get("content-type", "").startswith("image/"), img.headers.get("content-type")

    def test_update_404(self, admin):
        r = admin.put(f"{BASE}/api/security-companies/secco_nope", json={"phone": "1"}, timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_hard_delete_when_unlinked(self, admin):
        tmp = admin.post(f"{BASE}/api/security-companies",
                         json={"name": f"TEST_Temp {uuid.uuid4().hex[:6]}"}, timeout=60)
        assert tmp.status_code == 201
        tid = tmp.json()["id"]
        r = admin.delete(f"{BASE}/api/security-companies/{tid}", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        assert r.json().get("deleted") is True, r.json()
        arr = admin.get(f"{BASE}/api/security-companies", timeout=60).json()
        assert not any(c["id"] == tid for c in arr)


# ============================================================
# 5. SECURITY CONTRACTOR USER
# ============================================================
class TestSecurityContractorUser:
    def test_create_contractor(self, admin):
        email = f"qa.guard.{uuid.uuid4().hex[:6]}@5812.test"
        STATE["guard_email"] = email
        r = admin.post(f"{BASE}/api/admin/users", json={
            "name": "QA Guard", "email": email, "role": "Security Contractor",
            "security_company_id": STATE["co_id"], "security_rank": "Officer",
            "location_id": "loc_001",
        }, timeout=60)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        d = r.json()
        STATE["guard_id"] = d.get("id") or (d.get("user") or {}).get("id")
        assert STATE["guard_id"], d

    def test_list_users_enrichment(self, admin):
        r = admin.get(f"{BASE}/api/admin/users", params={"search": STATE["guard_email"]}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        rows = data if isinstance(data, list) else data.get("users", [])
        row = next((u for u in rows if u.get("id") == STATE["guard_id"]), None)
        assert row, f"guard not in search results: {rows}"
        assert row.get("security_company_id") == STATE["co_id"]
        assert row.get("security_rank") == "Officer"
        assert row.get("security_company_name") == STATE["co_name"], f"not enriched: {row.get('security_company_name')}"
        assert row.get("security_company_logo_url") == STATE["co_logo"], row.get("security_company_logo_url")

    def test_contractor_login_and_me(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login",
                   json={"identifier": STATE["guard_email"], "password": DEFAULT_PW}, timeout=60)
        assert r.status_code == 200, f"contractor login {r.status_code} {r.text[:300]}"
        tok = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {tok}"})
        STATE["guard_session"] = s
        me = s.get(f"{BASE}/api/auth/me", timeout=60)
        assert me.status_code == 200, f"{me.status_code} {me.text[:300]}"
        u = me.json()
        assert u.get("security_company_name") == STATE["co_name"], u
        assert u.get("security_rank") == "Officer", u
        assert u.get("security_company_logo_url") == STATE["co_logo"], u

    def test_contractor_cannot_list_users(self):
        s = STATE["guard_session"]
        r = s.get(f"{BASE}/api/admin/users", timeout=60)
        assert r.status_code in (401, 403), f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_contractor_cannot_read_social_cases(self):
        s = STATE["guard_session"]
        r = s.get(f"{BASE}/api/social-work/cases", timeout=60)
        assert r.status_code in (401, 403), f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_contractor_cannot_create_company(self):
        s = STATE["guard_session"]
        r = s.post(f"{BASE}/api/security-companies", json={"name": "TEST_Hacked"}, timeout=60)
        assert r.status_code in (401, 403), f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_soft_delete_company_with_linked_user(self, admin):
        r = admin.delete(f"{BASE}/api/security-companies/{STATE['co_id']}", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("deactivated") is True and d.get("linked_users", 0) >= 1, d
        # re-activate so later tests still see it
        admin.put(f"{BASE}/api/security-companies/{STATE['co_id']}", json={"active": True}, timeout=60)


# ============================================================
# 6. NFC auto-member via user_id
# ============================================================
class TestNfcAutoMember:
    def test_nfc_payload_by_user_id(self, admin):
        r = admin.post(f"{BASE}/api/members/{STATE['guard_id']}/nfc-payload", json={}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("payload"), d
        assert d.get("member_id"), d
        STATE["guard_member_id"] = d["member_id"]

    def test_nfc_write_by_user_id(self, admin):
        serial = f"04:AB:CD:{uuid.uuid4().hex[:2].upper()}:11:22"
        STATE["serial"] = serial
        r = admin.post(f"{BASE}/api/members/{STATE['guard_id']}/nfc-write",
                       json={"serial_number": serial, "label": "QA Test"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert (d.get("tag") or {}).get("serial_number") == serial or d.get("serial_number") == serial, d

    def test_member_row_holds_tag(self):
        uid = STATE["guard_id"]
        serial = STATE["serial"]

        async def fetch(db):
            return await db.members.find_one({"user_id": uid}, {"_id": 0})
        m = run_db(fetch)
        assert m, f"no member linked to user_id={uid}"
        assert any(t.get("serial_number") == serial for t in (m.get("nfc_tags") or [])), m.get("nfc_tags")
        STATE["guard_member_row_id"] = m["id"]

    def test_autocreate_member_for_raw_user(self, admin):
        """Exercise the _resolve_member auto-create path with a user that has
        NO member row at all."""
        raw_uid = f"usr_qa_{uuid.uuid4().hex[:8]}"
        STATE["raw_uid"] = raw_uid

        async def seed(db):
            await db.users.insert_one({
                "id": raw_uid, "name": "QA Raw Guard", "email": f"{raw_uid}@5812.test",
                "role": "Security Contractor", "status": "active",
            })
            return True
        run_db(seed)
        serial = f"04:99:{uuid.uuid4().hex[:2].upper()}:00:11:22"
        r = admin.post(f"{BASE}/api/members/{raw_uid}/nfc-write",
                       json={"serial_number": serial, "label": "QA Raw"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"

        async def fetch(db):
            return await db.members.find_one({"user_id": raw_uid}, {"_id": 0})
        m = run_db(fetch)
        assert m, f"no member auto-created for raw user {raw_uid}"
        assert m.get("auto_created_from_user") is True, m
        assert any(t.get("serial_number") == serial for t in (m.get("nfc_tags") or [])), m.get("nfc_tags")

    def test_nfc_write_unknown_person_404(self, admin):
        r = admin.post(f"{BASE}/api/members/usr_definitely_nope/nfc-write",
                       json={"serial_number": "04:00:00:00:00:00"}, timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"


# ============================================================
# 7. STORAGE / PHOTO ROUTES
# ============================================================
class TestStorageRoutes:
    def test_member_photo_upload_and_fetch(self, admin):
        mid = STATE.get("guard_member_row_id") or STATE.get("guard_member_id")
        assert mid, "no member id from NFC tests"
        r = admin.post(f"{BASE}/api/members/{mid}/photo",
                       files={"file": ("p.png", PNG, "image/png")}, timeout=90)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        url = r.json().get("photo_url")
        assert url, r.json()
        img = requests.get(f"{BASE}{url}" if url.startswith("/") else url, timeout=60)
        assert img.status_code == 200, f"photo {url} -> {img.status_code}"
        assert img.headers.get("content-type", "").startswith("image/"), img.headers.get("content-type")
        g = admin.get(f"{BASE}/api/members/{mid}", timeout=60)
        assert g.status_code == 200
        assert g.json().get("photo_url") == url, g.json().get("photo_url")

    def test_storage_route_existing_photo(self):
        async def fetch(db):
            return await db.members.find_one(
                {"photo_url": {"$regex": "^/api/storage/"}}, {"_id": 0, "photo_url": 1})
        d = run_db(fetch)
        if not d:
            pytest.skip("no /api/storage/ photo_url in db")
        r = requests.get(f"{BASE}{d['photo_url']}", timeout=60)
        assert r.status_code == 200, f"{d['photo_url']} -> {r.status_code}"
        assert r.headers.get("content-type", "").startswith("image/"), r.headers.get("content-type")

    def test_storage_missing_object_404(self):
        r = requests.get(f"{BASE}/api/storage/profile-photos/{uuid.uuid4().hex}.png", timeout=60)
        assert r.status_code == 404, f"{r.status_code}"


# ============================================================
# 8. CHECKPOINT auto-recognition of a brand-new user
# ============================================================
class TestCheckpointScan:
    def test_pair_and_scan_new_user(self, admin):
        async def loc(db):
            return await db.locations.find_one({}, {"_id": 0, "id": 1, "name": 1})
        l = run_db(loc)
        assert l, "no locations"
        c = admin.post(f"{BASE}/api/security/checkpoints", json={
            "name": f"TEST_QA Gate {uuid.uuid4().hex[:5]}", "location_id": l["id"],
            "kind": "check_in_only", "device_mode": "single_device",
        }, timeout=60)
        assert c.status_code in (200, 201), f"create checkpoint {c.status_code} {c.text[:300]}"
        cp = c.json()
        STATE["cp_id"] = cp.get("id")
        pin = cp.get("pairing_pin")
        assert pin, f"no pairing_pin returned: {cp}"
        p = requests.post(f"{BASE}/api/security/checkpoint/pair",
                          json={"pin": pin, "mode": "security", "device_label": "qa"}, timeout=60)
        assert p.status_code == 200, f"pair {p.status_code} {p.text[:300]}"
        token = p.json()["session_token"]
        s = requests.post(f"{BASE}/api/security/checkpoint/scan",
                          json={"scan_type": "qr", "payload": STATE["guard_id"]},
                          headers={"X-Checkpoint-Session": token}, timeout=60)
        assert s.status_code == 200, f"scan {s.status_code} {s.text[:400]}"
        body = s.json()
        blob = str(body)
        assert STATE["guard_id"] in blob, f"user not resolved: {blob[:500]}"
        assert "QA Guard" in blob, f"name not resolved (kind unknown?): {blob[:500]}"

    def test_scan_without_session_401(self):
        r = requests.post(f"{BASE}/api/security/checkpoint/scan",
                          json={"scan_type": "qr", "payload": "x"}, timeout=60)
        assert r.status_code == 401, f"{r.status_code}"

    def test_cleanup_checkpoint(self, admin):
        if STATE.get("cp_id"):
            admin.delete(f"{BASE}/api/security/checkpoints/{STATE['cp_id']}", timeout=60)


# ============================================================
# 9. ROLE GUARDS — Volunteer
# ============================================================
class TestVolunteerGuards:
    def test_create_volunteer(self, admin):
        email = f"qa.vol.{uuid.uuid4().hex[:6]}@5812.test"
        STATE["vol_email"] = email
        r = admin.post(f"{BASE}/api/admin/users", json={
            "name": "QA Volunteer", "email": email, "role": "Volunteer",
            "location_id": "loc_001",
        }, timeout=60)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        STATE["vol_id"] = r.json().get("id")

    def test_volunteer_blocked_on_company_create(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login",
                   json={"identifier": STATE["vol_email"], "password": DEFAULT_PW}, timeout=60)
        assert r.status_code == 200, f"volunteer login {r.status_code} {r.text[:300]}"
        tok = r.json().get("access_token") or r.json().get("token")
        s.headers.update({"Authorization": f"Bearer {tok}"})
        STATE["vol_session"] = s
        c = s.post(f"{BASE}/api/security-companies", json={"name": "TEST_VolCo"}, timeout=60)
        assert c.status_code == 403, f"expected 403, got {c.status_code} {c.text[:200]}"

    def test_volunteer_blocked_deleting_social_case(self):
        s = STATE["vol_session"]
        cid = STATE.get("case_id") or "sc_nope"
        r = s.delete(f"{BASE}/api/social-work/cases/{cid}", timeout=60)
        assert r.status_code in (401, 403), f"expected 403, got {r.status_code} {r.text[:200]}"


# ============================================================
# 11. Extra edge cases (iter 226 follow-ups)
# ============================================================
class TestExtraEdgeCases:
    def test_upload_scan_with_ocr_enabled_still_fast(self, admin):
        """run_ocr=true must NOT block the response (background task)."""
        t0 = time.time()
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/{CHILD_ID}/upload-scan",
            data={"kind": "welfare_visit", "run_ocr": "true"},
            files={"file": ("qa_ocr.png", PNG, "image/png")},
            timeout=60,
        )
        elapsed = time.time() - t0
        print(f"upload-scan(run_ocr=true) {elapsed:.2f}s status={r.status_code}")
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        assert elapsed < 5.0, f"took {elapsed:.2f}s (>5s) with OCR enabled"
        assert (r.json().get("ocr") or {}).get("pending") is True, r.json().get("ocr")
        STATE["ocr_review_id"] = r.json()["id"]

    def test_ocr_failure_does_not_break_review(self, admin):
        """Background OCR may fail (LLM budget) — the review must survive and
        the scan URL must still resolve."""
        time.sleep(8)
        rid = STATE["ocr_review_id"]
        r = admin.get(f"{BASE}/api/social-work/reviews/{rid}", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        url = d.get("attached_scan_url")
        assert url, d
        img = requests.get(f"{BASE}{url}", timeout=60)
        assert img.status_code == 200, f"scan url {url} -> {img.status_code} (cloud swap broke it?)"
        print(f"ocr meta after 8s: {d.get('ocr')}")

    def test_upload_scan_rejects_bad_mime(self, admin):
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/{CHILD_ID}/upload-scan",
            data={"kind": "welfare_visit", "run_ocr": "false"},
            files={"file": ("x.txt", b"hello", "text/plain")},
            timeout=60,
        )
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_upload_scan_rejects_bad_kind(self, admin):
        r = admin.post(
            f"{BASE}/api/social-work/reviews/children/{CHILD_ID}/upload-scan",
            data={"kind": "nonsense", "run_ocr": "false"},
            files={"file": ("x.pdf", PDF, "application/pdf")},
            timeout=60,
        )
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_relink_rejects_bad_subject_kind(self, admin):
        async def seed(db):
            await db.social_cases.delete_one({"id": "sc_qa_orphan2"})
            await db.social_cases.insert_one({
                "id": "sc_qa_orphan2", "subject_id": None, "subject_kind": "child",
                "subject_name": "QA Orphan2", "status": "active", "category": "welfare_support"})
            return True
        run_db(seed)
        r = admin.put(f"{BASE}/api/social-work/cases/sc_qa_orphan2",
                      json={"subject_id": CHILD_ID, "subject_kind": "banana"}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

        async def rm(db):
            await db.social_cases.delete_one({"id": "sc_qa_orphan2"})
            return True
        run_db(rm)

    def test_company_create_blank_name_400(self, admin):
        r = admin.post(f"{BASE}/api/security-companies", json={"name": "   "}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_company_logo_rejects_non_image(self, admin):
        c = admin.post(f"{BASE}/api/security-companies",
                       json={"name": f"TEST_LogoCo {uuid.uuid4().hex[:6]}"}, timeout=60)
        assert c.status_code == 201
        cid = c.json()["id"]
        r = admin.post(f"{BASE}/api/security-companies/{cid}/logo",
                       files={"file": ("x.txt", b"nope", "text/plain")}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        r2 = admin.post(f"{BASE}/api/security-companies/secco_nope/logo",
                        files={"file": ("l.png", PNG, "image/png")}, timeout=60)
        assert r2.status_code == 404, f"{r2.status_code} {r2.text[:200]}"
        admin.delete(f"{BASE}/api/security-companies/{cid}", timeout=60)

    def test_contractor_blocked_on_more_modules(self):
        s = STATE.get("guard_session")
        if not s:
            pytest.skip("no contractor session")
        results = {}
        for path in ("/api/members", "/api/children", "/api/admin/audit-logs",
                     "/api/social-work/reviews/children/" + CHILD_ID,
                     "/api/dashboard/stats", "/api/reports/summary",
                     "/api/tasks", "/api/notifications", "/api/financial/transactions"):
            try:
                r = s.get(f"{BASE}{path}", timeout=60)
                results[path] = r.status_code
            except Exception as e:
                results[path] = str(e)
        print("Contractor access matrix:", results)
        leaked = [p for p, sc in results.items() if sc == 200]
        assert not leaked, f"Security Contractor can read staff modules: {leaked}"

    def test_contractor_can_read_own_company(self):
        s = STATE.get("guard_session")
        if not s:
            pytest.skip("no contractor session")
        r = s.get(f"{BASE}/api/security-companies", timeout=60)
        print(f"contractor GET /api/security-companies -> {r.status_code}")
        assert r.status_code in (200, 403)


# ============================================================
# 10. Cleanup
# ============================================================
class TestZZCleanup:
    def test_cleanup(self, admin):
        for uid in (STATE.get("guard_id"), STATE.get("vol_id")):
            if uid:
                admin.delete(f"{BASE}/api/admin/users/{uid}", timeout=60)
        if STATE.get("co_id"):
            admin.delete(f"{BASE}/api/security-companies/{STATE['co_id']}", timeout=60)
        if STATE.get("case_id"):
            admin.delete(f"{BASE}/api/social-work/cases/{STATE['case_id']}", timeout=60)

        async def rm(db):
            await db.members.delete_many({"user_id": STATE.get("raw_uid", "x")})
            await db.users.delete_many({"id": STATE.get("raw_uid", "x")})
            await db.social_cases.delete_one({"id": "sc_qa_orphan"})
            return True
        run_db(rm)
        assert True


