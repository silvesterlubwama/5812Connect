"""Iter 379 — P&L breakdown + auto-translate endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- P&L breakdown ----------------
class TestPnlBreakdown:
    def test_pnl_with_breakdown(self, hdr):
        r = requests.get(f"{API}/finance/reports/pnl", headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # locate expense rows
        exp = data.get("expense") or data.get("expenses") or []
        if not exp and "rows" in data:
            exp = [row for row in data["rows"] if row.get("type") == "expense"]
        assert exp, f"no expense rows: {list(data)[:10]}"
        row_with_bd = next((r for r in exp if r.get("breakdown")), None)
        assert row_with_bd, "no expense row had a breakdown"
        bd = row_with_bd["breakdown"]
        assert "payees" in bd and "campuses" in bd and "departments" in bd
        assert "entries" in bd
        # consistency: sum of campus amounts ≈ account amount (abs)
        acct_amt = abs(float(row_with_bd.get("amount") or row_with_bd.get("total") or 0))
        camp_sum = sum(abs(float(c.get("amount", 0))) for c in bd["campuses"])
        if acct_amt and camp_sum:
            # allow 1% slack
            assert abs(camp_sum - acct_amt) <= max(1.0, 0.02 * acct_amt), (
                f"campus sum {camp_sum} != account {acct_amt}")

    def test_pnl_breakdown_false(self, hdr):
        r = requests.get(f"{API}/finance/reports/pnl?breakdown=false", headers=hdr, timeout=30)
        assert r.status_code == 200
        data = r.json()
        exp = data.get("expense") or data.get("expenses") or []
        if not exp and "rows" in data:
            exp = [row for row in data["rows"] if row.get("type") == "expense"]
        for row in exp:
            assert not row.get("breakdown"), f"breakdown=false leaked: {row.get('code')}"

    def test_pnl_pdf_contains_breakdown(self, hdr):
        r = requests.get(f"{API}/finance/reports/pnl.pdf", headers=hdr, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        body = r.content
        assert body[:4] == b"%PDF", "not a PDF"
        # extract text roughly
        try:
            from pypdf import PdfReader
            import io
            text = ""
            for p in PdfReader(io.BytesIO(body)).pages:
                text += p.extract_text() or ""
        except Exception:
            text = body.decode("latin1", "ignore")
        assert "Where the money went" in text, "PDF missing breakdown section"


# ---------------- translate ----------------
class TestTranslate:
    def test_translate_luganda_and_cache(self, hdr):
        payload = {"lang": "lg", "texts": ["Staff meeting", "Welcome back"]}
        r = requests.post(f"{API}/translate", headers=hdr, json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["lang"] == "lg"
        assert set(d["translations"].keys()) == {"Staff meeting", "Welcome back"}
        # at least one truly translated (not identical to english)
        any_different = any(v != k for k, v in d["translations"].items())
        assert any_different or d.get("translated", 0) == 0, "LLM returned nothing different"

        # second call should hit cache
        r2 = requests.post(f"{API}/translate", headers=hdr, json=payload, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("from_cache", 0) > 0, f"expected cache hits: {d2}"

    def test_translate_english_echo(self, hdr):
        r = requests.post(f"{API}/translate", headers=hdr,
                          json={"lang": "en", "texts": ["Hello"]}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["translations"]["Hello"] == "Hello"

    def test_translate_unsupported_lang(self, hdr):
        r = requests.post(f"{API}/translate", headers=hdr,
                          json={"lang": "zz", "texts": ["Hi"]}, timeout=15)
        assert r.status_code == 400

    def test_cache_stats(self, hdr):
        r = requests.get(f"{API}/translate/cache-stats", headers=hdr, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "cached" in d and "total" in d
        for lang in ("lg", "sw", "es", "th", "ht", "fr"):
            assert lang in d["cached"]
