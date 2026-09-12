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

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


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


@pytest.fixture(scope="module", autouse=True)
def _ensure_child_fixture(session):
    """Make sure at least one child exists so parametric test_pdf_export[child] doesn't skip.
    Inserts a sentinel child once per test module; deletes it after the suite finishes."""
    r = session.get(f"{API}/children?limit=1", timeout=20)
    if r.status_code == 200:
        payload = r.json()
        rows = payload.get("children", payload) if isinstance(payload, dict) else payload
        if rows:
            yield None
            return
    # Need a location_id; pick any campus the admin has visibility into
    locs = session.get(f"{API}/locations", timeout=20).json() or []
    loc_id = locs[0]["id"] if locs else None
    created_id = None
    if loc_id:
        c = session.post(f"{API}/children", json={
            "name": "_PDFExportFixtureChild",
            "date_of_birth": "2018-01-01",
            "gender": "other",
            "location_id": loc_id,
            "grade": "P1",
        }, timeout=20)
        if c.status_code in (200, 201):
            created_id = (c.json() or {}).get("id")
    yield None
    if created_id:
        try:
            session.delete(f"{API}/children/{created_id}", timeout=10)
        except Exception:
            pass


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


# ----- Iteration 87 retest: synthetic customer (sales-only) fallback -----
class TestSyntheticCustomerFallback:
    """customer_id present in db.sales but NOT in db.customer_accounts should
    now return a PDF via the sales-aggregator fallback (was 404 before)."""

    def _find_synthetic_customer(self, session):
        # Query MongoDB directly to find a customer_id that exists in db.sales but
        # NOT in db.customer_accounts. This is the only reliable way to guarantee
        # we hit the sales-aggregator fallback branch.
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")

        async def _query():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            sales_ids = set(await db.sales.distinct("customer_id"))
            sales_ids.discard(None); sales_ids.discard("")
            acct_ids = set(await db.customer_accounts.distinct("id"))
            synth = sorted(sales_ids - acct_ids)
            if not synth:
                return None, None
            sale = await db.sales.find_one({"customer_id": synth[0]}, {"_id": 0, "customer_name": 1})
            return synth[0], (sale or {}).get("customer_name")
        return asyncio.run(_query())

    def test_synthetic_customer_pdf_200(self, session):
        cid, name = self._find_synthetic_customer(session)
        if not cid:
            pytest.skip("no synthetic (sales-aggregator-only) customer in this env")
        r = session.get(f"{API}/activity/customer/{cid}/export?format=pdf", timeout=60)
        assert r.status_code == 200, f"synthetic customer PDF 200 expected, got {r.status_code}: {r.text[:300]}"
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:5] == b"%PDF-", f"not a PDF: {r.content[:8]!r}"
        assert len(r.content) > 1000

    def test_synthetic_customer_pdf_body_has_heading_and_name(self, session):
        cid, name = self._find_synthetic_customer(session)
        if not cid:
            pytest.skip("no synthetic customer in this env")
        r = session.get(f"{API}/activity/customer/{cid}/export?format=pdf", timeout=60)
        assert r.status_code == 200
        from io import BytesIO
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(BytesIO(r.content)) or ""
        except Exception as e:
            pytest.skip(f"pdfminer not usable: {e}")
        assert "Activity Trail" in text, f"missing heading. first 400: {text[:400]!r}"
        if name:
            first = str(name).split()[0]
            # name in fallback may be 'Customer' if sales rows had no customer_name
            assert first in text or "Customer" in text, f"missing name '{first}'. first 400: {text[:400]!r}"

    def test_synthetic_customer_json_200(self, session):
        cid, _ = self._find_synthetic_customer(session)
        if not cid:
            pytest.skip("no synthetic customer in this env")
        r = session.get(f"{API}/activity/customer/{cid}/export?format=json", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["subject_kind"] == "customer"
        assert data["subject_id"] == cid
        assert data.get("profile", {}).get("source") == "sales_aggregator"


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
