"""Backend tests for social_review_forms.py — iteration 164."""
import os
import io
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def test_child(auth_headers):
    """Create a TEST_ child for the duration of this run."""
    name = f"TEST_Review_Child_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/children",
        json={"name": name, "age": 10, "gender": "male"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code in (200, 201), f"child create failed: {r.status_code} {r.text[:300]}"
    cid = r.json()["id"]
    yield cid
    try:
        requests.delete(f"{BASE_URL}/api/children/{cid}", headers=auth_headers, timeout=15)
    except Exception:
        pass


# ===== TEMPLATES =====
def test_school_template_pdf(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/school_progress.pdf", headers=auth_headers, timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert "application/pdf" in r.headers.get("content-type", "").lower(), r.headers.get("content-type")
    assert r.content[:4] == b"%PDF", "not a PDF magic"
    assert len(r.content) > 5000


def test_welfare_template_pdf(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/welfare_visit.pdf", headers=auth_headers, timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "").lower()
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000


def test_template_invalid_kind(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/bogus.pdf", headers=auth_headers, timeout=30)
    assert r.status_code == 400


def test_template_requires_auth():
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/school_progress.pdf", timeout=30)
    assert r.status_code in (401, 403)


# ===== CREATE + AUTO-SYNC =====
def test_create_school_review_and_auto_sync(auth_headers, test_child):
    payload = {
        "kind": "school_progress",
        "review_date": "2026-01-15",
        "term": "Term 1",
        "fields": {
            "school": "TEST School Of Champions",
            "class_grade": "P5",
            "term": "Term 1 2026",
            "academic_performance": {"overall": "Good", "math": "Good"},
            "attendance_discipline": {"attends_regularly": "Yes"},
            "social_emotional": {"peers": "Good"},
            "strengths": "Diligent reader",
            "areas_requiring_support": "Math word problems",
        },
        "action_plan": [{"no": 1, "concern": "Math", "action": "Tutoring", "responsible": "Teacher", "timeline": "1 mo"}],
        "overall_assessment": "Good Progress",
    }
    r = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}", json=payload, headers=auth_headers, timeout=30)
    assert r.status_code in (200, 201), r.text[:400]
    body = r.json()
    assert body["id"].startswith("rev_")
    assert body["kind"] == "school_progress"
    assert body["overall_assessment"] == "Good Progress"
    assert body["review_date"] == "2026-01-15"
    rid = body["id"]

    # auto-sync into child
    cr = requests.get(f"{BASE_URL}/api/children/{test_child}/full-profile", headers=auth_headers, timeout=30)
    assert cr.status_code == 200, cr.text[:300]
    child = cr.json().get("child") or cr.json()
    edu = child.get("education") or {}
    assert edu.get("school_name") == "TEST School Of Champions", edu
    assert edu.get("grade") == "P5"
    assert edu.get("current_term") == "Term 1 2026"
    lr = edu.get("latest_review") or {}
    assert lr.get("review_id") == rid
    assert lr.get("overall") == "Good Progress"
    assert lr.get("strengths") == "Diligent reader"

    # cleanup
    requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)


def test_create_welfare_with_protection_flags(auth_headers, test_child):
    payload = {
        "kind": "welfare_visit",
        "review_date": "2026-01-16",
        "fields": {
            "caregiver_name": "TEST_Caregiver Jane",
            "caregiver_relationship": "Aunt",
            "village_parish": "TEST Village",
            "district": "Wakiso",
            "welfare_indicators": {"physical_health": "Good", "nutrition": "Fair"},
            "education_checks": {"enrolled": True},
            "health_nutrition": {"healthy": True},
            "protection_concerns": {"neglect": True, "child_labour": True, "physical_abuse": False},
            "protection_details": "Long working hours at home",
            "household": {"caregiver_child_rel": "Good"},
            "child_voice": {"going_well": "School friends", "challenges": "Late meals", "support": "Books"},
            "strengths": "Resilient",
            "challenges": "Food insecurity",
        },
        "action_plan": [{"no": 1, "need": "Food", "action": "Referral", "responsible": "SW", "timeline": "2w"}],
        "overall_assessment": "Requires additional support services",
        "next_visit_date": "2026-02-10",
    }
    r = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}", json=payload, headers=auth_headers, timeout=30)
    assert r.status_code in (200, 201), r.text[:400]
    rid = r.json()["id"]

    cr = requests.get(f"{BASE_URL}/api/children/{test_child}/full-profile", headers=auth_headers, timeout=30)
    child = cr.json().get("child") or cr.json()
    fam = child.get("family") or {}
    assert fam.get("primary_caregiver") == "TEST_Caregiver Jane"
    assert fam.get("caregiver_relationship") == "Aunt"
    assert fam.get("village_parish") == "TEST Village"
    assert fam.get("district") == "Wakiso"

    prot = child.get("protection") or {}
    assert prot.get("has_active_concern") is True
    flags = prot.get("flags") or {}
    assert flags.get("neglect") is True
    assert flags.get("child_labour") is True
    assert flags.get("physical_abuse") is False

    welf = child.get("welfare") or {}
    lr = welf.get("latest_review") or {}
    assert lr.get("review_id") == rid
    assert lr.get("overall") == "Requires additional support services"

    requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)


def test_invalid_kind_rejected(auth_headers, test_child):
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child}",
        json={"kind": "bogus_kind", "fields": {}},
        headers=auth_headers, timeout=15,
    )
    assert r.status_code == 400


def test_invalid_child_rejected(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/no_such_child",
        json={"kind": "school_progress", "fields": {}},
        headers=auth_headers, timeout=15,
    )
    assert r.status_code == 404


# ===== LIST / FILTER =====
def test_list_filter_by_kind(auth_headers, test_child):
    # seed one of each
    rid1 = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}",
        json={"kind": "school_progress", "fields": {"school": "S"}, "overall_assessment": "Good Progress"},
        headers=auth_headers, timeout=20).json()["id"]
    rid2 = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}",
        json={"kind": "welfare_visit", "fields": {}, "overall_assessment": "Requires routine monitoring"},
        headers=auth_headers, timeout=20).json()["id"]

    r_all = requests.get(f"{BASE_URL}/api/social-work/reviews/children/{test_child}", headers=auth_headers, timeout=20)
    assert r_all.status_code == 200
    all_ids = [x["id"] for x in r_all.json()]
    assert rid1 in all_ids and rid2 in all_ids

    r_sch = requests.get(f"{BASE_URL}/api/social-work/reviews/children/{test_child}?kind=school_progress", headers=auth_headers, timeout=20)
    assert r_sch.status_code == 200
    kinds = {x["kind"] for x in r_sch.json()}
    assert kinds == {"school_progress"}

    r_bad = requests.get(f"{BASE_URL}/api/social-work/reviews/children/{test_child}?kind=bogus", headers=auth_headers, timeout=20)
    assert r_bad.status_code == 400

    for rid in (rid1, rid2):
        requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)


# ===== UPDATE re-applies sync =====
def test_update_reapplies_sync(auth_headers, test_child):
    rid = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}",
        json={"kind": "school_progress", "fields": {"school": "Old"}, "overall_assessment": "Good Progress"},
        headers=auth_headers, timeout=20).json()["id"]
    upd = requests.put(f"{BASE_URL}/api/social-work/reviews/{rid}",
        json={"fields": {"school": "NewSchool", "class_grade": "P6"}, "overall_assessment": "Excellent Progress"},
        headers=auth_headers, timeout=20)
    assert upd.status_code == 200
    cr = requests.get(f"{BASE_URL}/api/children/{test_child}/full-profile", headers=auth_headers, timeout=20)
    child = cr.json().get("child") or cr.json()
    assert (child.get("education") or {}).get("school_name") == "NewSchool"
    assert (child.get("education") or {}).get("grade") == "P6"
    assert (child.get("education") or {}).get("latest_review", {}).get("overall") == "Excellent Progress"
    requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)


# ===== DELETE soft-deletes =====
def test_delete_soft(auth_headers, test_child):
    rid = requests.post(f"{BASE_URL}/api/social-work/reviews/children/{test_child}",
        json={"kind": "welfare_visit", "fields": {}, "overall_assessment": "x"},
        headers=auth_headers, timeout=20).json()["id"]
    d = requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)
    assert d.status_code == 200
    g = requests.get(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)
    assert g.status_code == 404


# ===== UPLOAD SCAN =====
def test_upload_scan_pdf(auth_headers, test_child):
    fake_pdf = b"%PDF-1.4\n%fake\n%%EOF"
    files = {"file": ("TEST_scan.pdf", fake_pdf, "application/pdf")}
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child}/upload-scan?kind=welfare_visit",
        files=files, headers=auth_headers, timeout=30,
    )
    assert r.status_code in (200, 201), r.text[:400]
    body = r.json()
    assert body["status"] == "draft_scan_only"
    assert body["kind"] == "welfare_visit"
    assert body["attached_scan_url"]
    rid = body["id"]

    # mirrored as child_extra (best-effort — check it shows in extras gallery if API exists)
    # cleanup
    requests.delete(f"{BASE_URL}/api/social-work/reviews/{rid}", headers=auth_headers, timeout=15)


def test_upload_scan_wrong_mime(auth_headers, test_child):
    files = {"file": ("evil.txt", b"hello", "text/plain")}
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child}/upload-scan?kind=welfare_visit",
        files=files, headers=auth_headers, timeout=30,
    )
    assert r.status_code == 400


def test_upload_scan_invalid_kind(auth_headers, test_child):
    files = {"file": ("x.pdf", b"%PDF-1.4\n", "application/pdf")}
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child}/upload-scan?kind=bogus",
        files=files, headers=auth_headers, timeout=30,
    )
    assert r.status_code == 400
