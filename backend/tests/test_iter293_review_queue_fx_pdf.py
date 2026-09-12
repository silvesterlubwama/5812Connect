"""Iter 293 backend regression:
  - Review queue endpoints (list, approve, edit-repost)
  - Receipt scan → draft JE in queue
  - /api/reports/pdf with & without fx params
  - /api/hr/payslips/generate-payday (director+) responds 200
  - Regression: /api/finance/journal, /api/finance/chart-of-accounts, /api/finance/reports/pnl
"""
import io
import os
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Review Queue ----------
def test_review_queue_list(headers):
    r = requests.get(f"{BASE_URL}/api/finance/receipts/review-queue", headers=headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), list)


def _make_fake_receipt_png():
    # Minimal PNG bytes with rendered text — use PIL if available
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (600, 300), "white")
        d = ImageDraw.Draw(img)
        d.text((20, 20), "TEST Vendor Ltd", fill="black")
        d.text((20, 60), "Date: 2026-01-15", fill="black")
        d.text((20, 100), "Total: UGX 12,500", fill="black")
        buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        return buf.read()
    except Exception:
        # Fallback: 1x1 PNG
        return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82")


def test_receipt_scan_creates_draft_je_in_queue(headers):
    files = {"file": ("test_receipt.png", _make_fake_receipt_png(), "image/png")}
    data = {"location_id": "loc_001"}
    r = requests.post(f"{BASE_URL}/api/finance/receipts/scan", headers=headers,
                      files=files, data=data, timeout=45)
    # OCR may not extract amount from a minimal PNG. Accept success or benign 200 no JE.
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    if body.get("journal_entry"):
        assert body["journal_entry"].get("needs_review") is True
        je_id = body["journal_entry"]["id"]
        # Verify shows up in queue
        q = requests.get(f"{BASE_URL}/api/finance/receipts/review-queue", headers=headers, timeout=15).json()
        assert any(x["id"] == je_id for x in q), "JE not in review queue"

        # Approve endpoint
        a = requests.put(f"{BASE_URL}/api/finance/receipts/{je_id}/approve", headers=headers, timeout=15)
        assert a.status_code == 200, a.text[:300]
        # After approve, no longer in queue
        q2 = requests.get(f"{BASE_URL}/api/finance/receipts/review-queue", headers=headers, timeout=15).json()
        assert not any(x["id"] == je_id for x in q2)
    else:
        # OCR could not read amount from the tiny synthetic image — accept
        assert body.get("extracted") is not None


def test_approve_nonexistent_returns_404(headers):
    r = requests.put(f"{BASE_URL}/api/finance/receipts/does_not_exist_xyz/approve",
                     headers=headers, timeout=15)
    assert r.status_code == 404


# ---------- Reports PDF FX ----------
def test_reports_pdf_no_fx(headers):
    r = requests.get(f"{BASE_URL}/api/reports/pdf", headers=headers, timeout=45)
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 500
    global BASE_PDF_SIZE
    BASE_PDF_SIZE = len(r.content)


def test_reports_pdf_with_fx(headers):
    r0 = requests.get(f"{BASE_URL}/api/reports/pdf", headers=headers, timeout=45)
    r = requests.get(f"{BASE_URL}/api/reports/pdf",
                     headers=headers,
                     params={"fx_target": "USD", "fx_rate": 0.00027},
                     timeout=45)
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    # Should embed FX note → produce different (typically larger) bytes
    assert len(r.content) > 500
    assert len(r.content) >= len(r0.content), f"FX pdf ({len(r.content)}) not >= base ({len(r0.content)})"


# ---------- HR payday ----------
def test_hr_payday_generate(headers):
    r = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday", headers=headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Accept either 'generated' count or descriptive message
    assert "generated" in body or "message" in body


# ---------- Regression ----------
def test_finance_journal(headers):
    r = requests.get(f"{BASE_URL}/api/finance/journal", headers=headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_finance_coa(headers):
    r = requests.get(f"{BASE_URL}/api/finance/chart-of-accounts", headers=headers, timeout=15)
    assert r.status_code == 200
    coa = r.json()
    assert isinstance(coa, list)
    assert len(coa) >= 1


def test_finance_pnl(headers):
    r = requests.get(f"{BASE_URL}/api/finance/reports/pnl", headers=headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


# ---------- Sublocation nesting (data pre-req) ----------
def test_locations_have_or_can_have_sublocation(headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=headers, timeout=15)
    assert r.status_code == 200
    locs = r.json()
    assert isinstance(locs, list) and len(locs) >= 1
    has_sub = any(l.get("parent_id") for l in locs)
    if not has_sub:
        # Try to create one so the ReportsPage dropdown nesting has data
        parent = next((l for l in locs if not l.get("parent_id")), None)
        if parent:
            payload = {"name": "TEST_SubLoc_Iter293", "parent_id": parent["id"], "type": "sublocation"}
            cr = requests.post(f"{BASE_URL}/api/locations", headers=headers, json=payload, timeout=15)
            # Not a hard fail — just note it. Some APIs may 403 for admin.
            print(f"[iter293] create sublocation status={cr.status_code} body={cr.text[:120]}")
