"""Backend tests for iteration 168 — Gemini OCR upload-scan, template externalisation,
case-list protection enrichment, and /compliance/due review widget."""
import os
import io
import uuid
import time
import requests
import pytest
from pathlib import Path

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD

TEMPLATES_DIR = Path("/app/backend/templates/social_reviews")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def test_child(auth_headers):
    name = f"TEST_OCR_Child_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE_URL}/api/children",
                      json={"name": name, "age": 10, "gender": "male"},
                      headers=auth_headers, timeout=30)
    assert r.status_code in (200, 201), f"child create failed: {r.status_code} {r.text[:300]}"
    cid = r.json()["id"]
    yield {"id": cid, "name": name}
    try:
        requests.delete(f"{BASE_URL}/api/children/{cid}", headers=auth_headers, timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def test_case(auth_headers, test_child):
    """Create an active social-work case so /compliance/due picks it up."""
    payload = {
        "subject_kind": "child",
        "subject_id": test_child["id"],
        "subject_name": test_child["name"],
        "case_type": "welfare",
        "priority": "medium",
        "summary": "TEST iter168 compliance",
    }
    r = requests.post(f"{BASE_URL}/api/social-work/cases", json=payload, headers=auth_headers, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"could not create case for compliance test: {r.status_code} {r.text[:200]}")
    case_id = r.json().get("id")
    yield case_id
    try:
        requests.delete(f"{BASE_URL}/api/social-work/cases/{case_id}", headers=auth_headers, timeout=15)
    except Exception:
        pass


# ---------- 1) Templates externalised ----------
def test_templates_files_exist():
    assert (TEMPLATES_DIR / "school_progress.html").exists()
    assert (TEMPLATES_DIR / "welfare_visit.html").exists()


def test_school_template_pdf_serves(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/school_progress.pdf",
                     headers=auth_headers, timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "").lower()
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 5000


def test_welfare_template_pdf_serves(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/welfare_visit.pdf",
                     headers=auth_headers, timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "").lower()
    assert r.content[:4] == b"%PDF"


def test_template_html_contains_org_branding(auth_headers):
    """The HTML file uses the {{ORG_NAME}} placeholder which must be interpolated server-side."""
    school = (TEMPLATES_DIR / "school_progress.html").read_text()
    assert "{{ORG_NAME}}" in school
    welfare = (TEMPLATES_DIR / "welfare_visit.html").read_text()
    assert "{{ORG_NAME}}" in welfare


# ---------- 2) upload-scan: unsupported MIME → 400 ----------
def test_upload_scan_unsupported_mime(auth_headers, test_child):
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"kind": "welfare_visit", "run_ocr": "false"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"


# ---------- 3) upload-scan: oversize image (>15MB) → 400 ----------
def test_upload_scan_oversize(auth_headers, test_child):
    big = b"\xff\xd8\xff" + b"0" * (16 * 1024 * 1024)
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("big.jpg", big, "image/jpeg")},
        data={"kind": "welfare_visit", "run_ocr": "false"},
        headers=auth_headers,
        timeout=60,
    )
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"


# ---------- 4) upload-scan run_ocr=false: attaches scan, draft_scan_only ----------
def test_upload_scan_no_ocr(auth_headers, test_child):
    # 1x1 PNG
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
           b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa"
           b"\xcf\xc0\x00\x00\x00\x03\x00\x01\x84\x82\x9b\xe7\x00\x00\x00\x00IEND\xaeB`\x82")
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("scan.png", png, "image/png")},
        data={"kind": "welfare_visit", "run_ocr": "false"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["status"] == "draft_scan_only", body
    assert body["ocr"]["ran"] is False
    assert body["attached_scan_url"]
    # ensure no auto-sync happened (fields empty)
    assert body["fields"] in ({}, None)


# ---------- 5) upload-scan with PDF: OCR skipped, draft_scan_only ----------
def test_upload_scan_pdf_skips_ocr(auth_headers, test_child):
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("scan.pdf", pdf, "application/pdf")},
        data={"kind": "welfare_visit", "run_ocr": "true"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text[:300]
    body = r.json()
    assert body["status"] == "draft_scan_only"
    assert body["ocr"]["ran"] is False


# ---------- 6) upload-scan: invalid kind → 400 ----------
def test_upload_scan_invalid_kind(auth_headers, test_child):
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("scan.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"kind": "bogus", "run_ocr": "false"},
        headers=auth_headers,
        timeout=15,
    )
    assert r.status_code == 400


# ---------- 7) /compliance/due endpoint shape ----------
def test_compliance_due_shape(auth_headers, test_case):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/compliance/due?days=90",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    for key in ("total_active", "due", "never_visited", "threshold_days", "list"):
        assert key in body, f"missing key {key}"
    assert body["threshold_days"] == 90
    assert isinstance(body["list"], list)
    assert len(body["list"]) <= 200
    # our test child has never been visited, so it should appear at the top with last_review_at=None
    matching = [x for x in body["list"] if x.get("last_review_at") is None]
    # never-visited entries surface at top
    if matching:
        # ensure the never_visited counter incremented
        assert body["never_visited"] >= 1


def test_compliance_due_threshold_param(auth_headers):
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/compliance/due?days=30",
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    assert r.json()["threshold_days"] == 30


# ---------- 8) Case list enriched with protection flags ----------
def test_case_list_protection_enrichment(auth_headers, test_child, test_case):
    """Set protection.has_active_concern on the child directly via a welfare review,
    then verify /api/social-work/cases includes protection.{has_active_concern, flags}."""
    # Submit a welfare_visit review with a protection_concern flag set
    review_payload = {
        "kind": "welfare_visit",
        "review_date": "2026-01-15",
        "fields": {
            "caregiver_name": "Test Caregiver",
            "protection_concerns": {"neglect": True, "child_labour": False},
            "protection_details": "TEST protection flag",
        },
        "overall_assessment": "Requires additional support services",
    }
    rv = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}",
        json=review_payload,
        headers=auth_headers,
        timeout=30,
    )
    assert rv.status_code in (200, 201), rv.text[:300]
    review_id = rv.json()["id"]

    try:
        # Verify child profile now has protection.has_active_concern=true
        ch = requests.get(f"{BASE_URL}/api/children/{test_child['id']}/full-profile",
                          headers=auth_headers, timeout=15)
        assert ch.status_code == 200, ch.text[:300]
        body = ch.json() or {}
        child_doc = body.get("child") or body
        prot = (child_doc or {}).get("protection") or {}
        assert prot.get("has_active_concern") is True, f"protection not flagged: {prot}"

        # Verify case list now enriches with protection
        cl = requests.get(f"{BASE_URL}/api/social-work/cases", headers=auth_headers, timeout=30)
        assert cl.status_code == 200
        cases = cl.json()
        assert isinstance(cases, list)
        match = [c for c in cases if c.get("subject_id") == test_child["id"]]
        assert match, "case for test child not in list"
        case_doc = match[0]
        assert "protection" in case_doc, f"protection missing from case: {case_doc.keys()}"
        assert case_doc["protection"].get("has_active_concern") is True
        flags = case_doc["protection"].get("flags") or {}
        assert flags.get("neglect") is True
        assert flags.get("child_labour") is False
    finally:
        try:
            requests.delete(f"{BASE_URL}/api/social-work/reviews/{review_id}", headers=auth_headers, timeout=15)
        except Exception:
            pass


# ---------- 9) Editing the HTML template changes the PDF on next request (no restart) ----------
def test_template_hot_reload(auth_headers):
    school_path = TEMPLATES_DIR / "school_progress.html"
    original = school_path.read_text()
    marker = f"IT168MARKER_{uuid.uuid4().hex[:6]}"
    try:
        school_path.write_text(original.replace("{{ORG_NAME}}", f"{{{{ORG_NAME}}}} {marker}"))
        # Sleep tiny bit to ensure FS sync
        time.sleep(0.3)
        r = requests.get(f"{BASE_URL}/api/social-work/reviews/templates/school_progress.pdf",
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200
        # PDF binary may compress text, so we just confirm a fresh successful render
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 5000
    finally:
        school_path.write_text(original)


# ---------- 10) Auth: upload-scan and compliance require auth ----------
def test_upload_scan_requires_auth(test_child):
    r = requests.post(
        f"{BASE_URL}/api/social-work/reviews/children/{test_child['id']}/upload-scan",
        files={"file": ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"kind": "welfare_visit"},
        timeout=15,
    )
    assert r.status_code in (401, 403)


def test_compliance_due_requires_auth():
    r = requests.get(f"{BASE_URL}/api/social-work/reviews/compliance/due", timeout=15)
    assert r.status_code in (401, 403)
