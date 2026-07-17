"""iter224 — PIN editor_name audit, QR labels PDF, AI-suggest packing, apply-suggested.

Covers:
  • POST /api/public/shipments/{token}/login — editor_name required, ≥2 chars
  • Edit-token payload carries editor_name; legacy 3-part tokens still verify
  • GET /api/shipments/{sid}/labels.pdf — application/pdf, error paths
  • POST /api/shipments/{sid}/ai-suggest-packing — 400 empty items
  • POST /api/shipments/{sid}/apply-suggested-packing — persists units, 400 empty
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"


@pytest.fixture(scope="module")
def client():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def shipment(client):
    """Create a shipment WITH a PIN set + a public token."""
    tag = uuid.uuid4().hex[:6]
    r = client.post(f"{BASE_URL}/api/shipments", json={
        "name": f"TEST_iter224_{tag}",
        "dest_country": "Uganda",
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    # Set an access PIN via admin endpoint
    rp = client.post(f"{BASE_URL}/api/shipments/{sid}/set-pin", json={"pin": "9911"}, timeout=10)
    ship = client.get(f"{BASE_URL}/api/shipments/{sid}").json()
    token = ship.get("token")
    yield {"id": sid, "token": token, "pin_set_ok": rp.status_code in (200, 201)}
    client.delete(f"{BASE_URL}/api/shipments/{sid}")


# ─── PIN Login with editor_name ────────────────────────────────
class TestPinLoginEditorName:
    def test_missing_name_400(self, shipment):
        if not shipment["token"]:
            pytest.skip("No token available")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "9911"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "name is required" in r.text.lower()

    def test_short_name_400(self, shipment):
        if not shipment["token"]:
            pytest.skip("No token available")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "9911", "editor_name": "A"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_valid_login_returns_editor_name(self, shipment):
        if not shipment["token"]:
            pytest.skip("No token available")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "9911", "editor_name": "TEST_Jane Volunteer"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "edit_token" in data
        assert data.get("editor_name") == "TEST_Jane Volunteer"
        assert data.get("shipment_id") == shipment["id"]
        assert data.get("ttl_hours")

    def test_bad_pin_401(self, shipment):
        if not shipment["token"]:
            pytest.skip("No token available")
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/login",
            json={"pin": "0000", "editor_name": "TEST_Someone"},
            timeout=10,
        )
        assert r.status_code == 401


# ─── Edit-token payload (unit-level) ─────────────────────────────
class TestEditTokenPayload:
    def test_verify_new_format_carries_editor_name(self):
        # Direct unit test of shipment_security helpers
        import sys
        sys.path.insert(0, "/app/backend")
        from shipment_security import make_edit_token, verify_edit_token
        tok = make_edit_token("ship-xyz", ttl_hours=1, editor_name="TEST_Alice")
        v = verify_edit_token(tok)
        assert v is not None
        assert v["shipment_id"] == "ship-xyz"
        assert v["editor_name"] == "TEST_Alice"

    def test_legacy_3part_token_still_verifies(self):
        import sys, hmac, hashlib, base64
        from datetime import datetime, timezone, timedelta
        sys.path.insert(0, "/app/backend")
        from shipment_security import verify_edit_token, _PIN_SECRET
        # Handcraft legacy: shipment_id|expires|sig
        sid = "legacy-ship"
        exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        payload = f"{sid}|{exp}"
        sig = hmac.new(_PIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
        tok = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode().rstrip("=")
        v = verify_edit_token(tok)
        assert v is not None
        assert v["shipment_id"] == sid
        assert v["editor_name"] == ""

    def test_bad_token_returns_none(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from shipment_security import verify_edit_token
        assert verify_edit_token("garbage!!!") is None


# ─── QR Labels PDF ────────────────────────────────────────────
class TestLabelsPDF:
    def test_no_units_400(self, client, shipment):
        r = client.get(f"{BASE_URL}/api/shipments/{shipment['id']}/labels.pdf", timeout=30)
        assert r.status_code == 400
        assert "no packing units" in r.text.lower() or "no packing" in r.text.lower()

    def test_pdf_returned_after_units_added(self, client, shipment):
        # add 2 units
        client.post(f"{BASE_URL}/api/shipments/{shipment['id']}/packing-units",
                    json={"type": "pallet", "preset_key": "eur_pallet", "name": "TEST_p1"})
        client.post(f"{BASE_URL}/api/shipments/{shipment['id']}/packing-units",
                    json={"type": "box", "preset_key": "large_box", "name": "TEST_b1"})
        r = client.get(f"{BASE_URL}/api/shipments/{shipment['id']}/labels.pdf", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1000
        assert r.content[:4] == b"%PDF"

    def test_404_for_missing_shipment(self, client):
        r = client.get(f"{BASE_URL}/api/shipments/no-such-ship/labels.pdf", timeout=10)
        assert r.status_code == 404


# ─── AI Suggest Packing ───────────────────────────────────────
class TestAISuggestPacking:
    def test_empty_items_400(self, client):
        # Fresh shipment with no items
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter224_empty_{uuid.uuid4().hex[:5]}",
            "dest_country": "Uganda",
        }).json()
        sid = r["id"]
        try:
            resp = client.post(f"{BASE_URL}/api/shipments/{sid}/ai-suggest-packing", timeout=15)
            # 400 (no items) or 503 (no LLM key) — both acceptable if items absent
            assert resp.status_code in (400, 503)
            if resp.status_code == 400:
                assert "no items" in resp.text.lower()
        finally:
            client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def test_missing_shipment_404_or_503(self, client):
        r = client.post(f"{BASE_URL}/api/shipments/nonexistent-xxx/ai-suggest-packing", timeout=15)
        # 404 if LLM key configured; 503 if not (503 fires before shipment lookup)
        assert r.status_code in (404, 503)

    def test_suggest_and_apply_flow(self, client):
        # Create shipment + a few items
        sid = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter224_ai_{uuid.uuid4().hex[:5]}",
            "dest_country": "Uganda",
        }).json()["id"]
        try:
            for name in ("TEST_shirts", "TEST_shoes", "TEST_books"):
                client.post(f"{BASE_URL}/api/shipments/{sid}/items",
                            json={"name": name, "qty_acquired": 10, "weight_kg": 0.5,
                                  "category": "clothing", "condition": "used"})
            r = client.post(f"{BASE_URL}/api/shipments/{sid}/ai-suggest-packing", timeout=90)
            # 200 if LLM present; 503 if key missing; 502 if malformed AI JSON
            assert r.status_code in (200, 502, 503), r.text[:200]
            if r.status_code == 200:
                data = r.json()
                assert "strategy" in data
                assert len(data.get("strategy", "")) <= 250
                assert "units" in data and isinstance(data["units"], list)
                assert data.get("items_analysed", 0) >= 1
                # Apply proposals
                if data["units"]:
                    ra = client.post(
                        f"{BASE_URL}/api/shipments/{sid}/apply-suggested-packing",
                        json={"units": data["units"]},
                        timeout=15,
                    )
                    assert ra.status_code == 200, ra.text
                    aj = ra.json()
                    assert aj["created"] == len(data["units"])
                    # verify persisted
                    g = client.get(f"{BASE_URL}/api/shipments/{sid}").json()
                    assert len(g.get("packing_units") or []) == len(data["units"])
                    # each unit has floor position set
                    for u in g["packing_units"]:
                        assert "floor_x_cm" in u and "floor_y_cm" in u
        finally:
            client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def test_apply_empty_units_400(self, client, shipment):
        r = client.post(
            f"{BASE_URL}/api/shipments/{shipment['id']}/apply-suggested-packing",
            json={"units": []},
            timeout=10,
        )
        assert r.status_code == 400

    def test_apply_missing_units_key_400(self, client, shipment):
        r = client.post(
            f"{BASE_URL}/api/shipments/{shipment['id']}/apply-suggested-packing",
            json={},
            timeout=10,
        )
        assert r.status_code == 400
