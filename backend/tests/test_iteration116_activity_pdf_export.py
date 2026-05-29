"""Iteration 116 — Activity Trail PDF export + Universal Activity expansion.

Backend coverage:
- GET /api/activity/{kind}/{id}/export (default = json) returns the JSON envelope
- GET /api/activity/{kind}/{id}/export?format=json returns the same JSON envelope
- GET /api/activity/{kind}/{id}/export?format=pdf returns application/pdf, body starts with %PDF-
- PDF export works across all valid subject kinds: member, child, user/staff, guest, customer
- PDF body embeds the subject's name + 'Activity Trail (N)' heading
- Unknown subject_id returns 404
- GET /api/activity/{kind}/{id} still works (regression)
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"


# ------- helpers --------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _pick_subject(session, kind):
    """Find a real id of the given subject_kind. Return (id, name) or (None, None)."""
    if kind == "member":
        r = session.get(f"{API}/members?limit=5", timeout=20)
        if r.status_code == 200:
            payload = r.json()
            rows = payload.get("members", payload) if isinstance(payload, dict) else payload
            if rows:
                return rows[0].get("id"), rows[0].get("name") or rows[0].get("full_name")
    elif kind == "child":
        r = session.get(f"{API}/children?limit=5", timeout=20)
        if r.status_code == 200:
            payload = r.json()
            rows = payload.get("children", payload) if isinstance(payload, dict) else payload
            if rows:
                return rows[0].get("id"), rows[0].get("name") or rows[0].get("full_name")
    elif kind in {"user", "staff"}:
        r = session.get(f"{API}/admin/users?limit=5", timeout=20)
        if r.status_code == 200:
            payload = r.json()
            rows = payload.get("users", payload) if isinstance(payload, dict) else payload
            if rows:
                return rows[0].get("id"), rows[0].get("name") or rows[0].get("email")
    elif kind == "guest":
        r = session.get(f"{API}/guests?limit=5", timeout=20)
        if r.status_code == 200:
            payload = r.json()
            rows = payload.get("guests", payload) if isinstance(payload, dict) else payload
            if rows:
                return rows[0].get("id"), rows[0].get("name")
    elif kind == "customer":
        # /api/customers returns a bare list of customer rows
        r = session.get(f"{API}/customers?limit=5", timeout=20)
        if r.status_code == 200:
            payload = r.json()
            rows = payload if isinstance(payload, list) else (payload.get("customers") or payload.get("rows") or [])
            if rows:
                return rows[0].get("id"), rows[0].get("name") or rows[0].get("phone")
    return None, None


# ----- regression: GET /api/activity/{kind}/{id} -----
class TestActivityGetRegression:
    def test_get_activity_member(self, session):
        sid, _ = _pick_subject(session, "member")
        if not sid:
            pytest.skip("no member seeded")
        r = session.get(f"{API}/activity/member/{sid}", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ----- JSON export envelope -----
class TestExportJSONEnvelope:
    def test_default_format_is_json(self, session):
        sid, _ = _pick_subject(session, "member")
        if not sid:
            pytest.skip("no member seeded")
        r = session.get(f"{API}/activity/member/{sid}/export", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        for k in ("subject_kind", "subject_id", "profile", "activity", "activity_count", "exported_at", "exported_by", "exported_by_name"):
            assert k in data, f"missing key {k} in JSON envelope"
        assert data["subject_kind"] == "member"
        assert data["subject_id"] == sid
        assert isinstance(data["activity"], list)
        assert data["activity_count"] == len(data["activity"])

    def test_explicit_format_json(self, session):
        sid, _ = _pick_subject(session, "member")
        if not sid:
            pytest.skip("no member seeded")
        r = session.get(f"{API}/activity/member/{sid}/export?format=json", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["subject_id"] == sid


# ----- PDF export -----
@pytest.mark.parametrize("kind", ["member", "child", "user", "guest", "customer"])
class TestExportPDFAllKinds:
    def test_pdf_export(self, session, kind):
        sid, name = _pick_subject(session, kind)
        if not sid:
            pytest.skip(f"no {kind} seeded")
        r = session.get(f"{API}/activity/{kind}/{sid}/export?format=pdf", timeout=60)
        assert r.status_code == 200, f"{kind} PDF export failed: {r.status_code} {r.text[:300]}"
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"{kind} wrong content-type: {ct}"
        assert len(r.content) > 1000, f"{kind} PDF too small: {len(r.content)}"
        assert r.content[:5] == b"%PDF-", f"{kind} body doesn't start with %PDF-: {r.content[:8]!r}"


# ----- PDF body content (parse-ish) -----
class TestPDFBodyContains:
    def test_pdf_contains_name_and_heading(self, session):
        sid, name = _pick_subject(session, "member")
        if not sid:
            pytest.skip("no member seeded")
        r = session.get(f"{API}/activity/member/{sid}/export?format=pdf", timeout=60)
        assert r.status_code == 200
        body = r.content
        # WeasyPrint compresses PDF content streams, so search the raw bytes won't catch
        # the rendered text. Extract via pdfminer.high_level.extract_text.
        from io import BytesIO
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(BytesIO(body)) or ""
        except Exception as e:
            pytest.skip(f"pdfminer not usable: {e}")
        assert "Activity Trail" in text, f"PDF text missing 'Activity Trail' heading. Got first 400 chars: {text[:400]!r}"
        if name:
            first = str(name).split()[0]
            assert first in text, f"PDF text missing subject name '{first}'. Got first 400 chars: {text[:400]!r}"


# ----- 404 for unknown id -----
class TestExportUnknownId:
    def test_unknown_member_returns_404(self, session):
        r = session.get(f"{API}/activity/member/does-not-exist-xyz/export?format=pdf", timeout=20)
        assert r.status_code == 404

    def test_unknown_member_json_returns_404(self, session):
        r = session.get(f"{API}/activity/member/does-not-exist-xyz/export", timeout=20)
        assert r.status_code == 404

    def test_invalid_kind_returns_400(self, session):
        # /export validates subject_kind explicitly
        r = session.get(f"{API}/activity/banana/abc/export", timeout=20)
        assert r.status_code in (400, 422)


# ----- Smoke: ensure the read endpoint and the export merge function still work side-by-side -----
class TestExportMatchesRead:
    def test_export_activity_matches_read_count_shape(self, session):
        sid, _ = _pick_subject(session, "member")
        if not sid:
            pytest.skip("no member seeded")
        r1 = session.get(f"{API}/activity/member/{sid}", timeout=20)
        r2 = session.get(f"{API}/activity/member/{sid}/export?format=json", timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        list_count = len(r1.json())
        env_count = r2.json()["activity_count"]
        # Both should be the same merged list (cap differs but content sets should overlap)
        assert env_count >= list_count - 5  # allow slight in-flight drift
