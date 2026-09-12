"""Backend tests for iteration 138:
   1) Gemini OCR endpoint /api/security/checkpoint/ocr-id
   2) Product is_exit_restricted flag + sale enrichment
   3) Receipt exit-scan denies departures for flagged items
   4) WebSocket /api/security/checkpoint/ws push events
"""
import os
import io
import json
import asyncio
import pytest
import requests
from urllib.parse import urlparse
import websockets
from PIL import Image, ImageDraw, ImageFont

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


# --------- shared fixtures ---------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def some_location(admin_headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    locs = r.json()
    if isinstance(locs, dict):
        locs = locs.get("locations") or locs.get("items") or []
    assert isinstance(locs, list) and locs
    return locs[0]


@pytest.fixture(scope="module")
def checkpoint(admin_headers, some_location):
    body = {"name": "TEST_Iter138_CP", "location_id": some_location["id"],
            "description": "iter138", "requires_id_for_one_time": False}
    r = requests.post(f"{BASE_URL}/api/security/checkpoints", headers=admin_headers, json=body, timeout=20)
    assert r.status_code == 200, r.text[:300]
    cp = r.json()
    yield cp
    requests.delete(f"{BASE_URL}/api/security/checkpoints/{cp['id']}", headers=admin_headers, timeout=20)


@pytest.fixture(scope="module")
def security_session(checkpoint):
    r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair",
                      json={"pin": checkpoint["pairing_pin"], "mode": "security"}, timeout=20)
    assert r.status_code == 200
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def guest_session(checkpoint):
    r = requests.post(f"{BASE_URL}/api/security/checkpoint/pair",
                      json={"pin": checkpoint["pairing_pin"], "mode": "guest"}, timeout=20)
    assert r.status_code == 200
    return r.json()["session_token"]


def _make_jpeg_bytes(text="NATIONAL ID\nJOHN DOE\n1990-01-01\nCM90010112345"):
    img = Image.new("RGB", (640, 400), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    # add varied content so it's not blank
    draw.rectangle([10, 10, 630, 390], outline=(20, 20, 20), width=3)
    draw.rectangle([20, 20, 200, 200], fill=(180, 180, 220))  # photo placeholder
    y = 30
    for line in text.split("\n"):
        draw.text((220, y), line, fill=(10, 10, 10))
        y += 30
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ====================================================================
# 1) OCR endpoint
# ====================================================================
class TestOcrIdEndpoint:
    def test_missing_session_401(self):
        files = {"image": ("a.jpg", _make_jpeg_bytes(), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/api/security/checkpoint/ocr-id", files=files, timeout=30)
        assert r.status_code == 401, r.text[:200]

    def test_guest_session_403(self, guest_session):
        files = {"image": ("a.jpg", _make_jpeg_bytes(), "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": guest_session},
            files=files, timeout=30,
        )
        assert r.status_code == 403, r.text[:200]

    def test_bad_mime_400(self, security_session):
        # send a small bytes payload with text/plain — should 400 (and magic bytes don't match)
        files = {"image": ("a.txt", b"hello world", "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": security_session},
            files=files, timeout=30,
        )
        assert r.status_code == 400, r.text[:200]

    def test_empty_image_400(self, security_session):
        files = {"image": ("a.jpg", b"", "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": security_session},
            files=files, timeout=30,
        )
        assert r.status_code == 400

    def test_huge_image_400(self, security_session):
        # 9MB > 8MB limit
        big = b"\xff\xd8\xff\xe0" + (b"A" * (9 * 1024 * 1024))
        files = {"image": ("big.jpg", big, "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": security_session},
            files=files, timeout=60,
        )
        assert r.status_code == 400

    def test_octet_stream_with_jpeg_magic_bytes_works(self, security_session):
        files = {"image": ("a.bin", _make_jpeg_bytes(), "application/octet-stream")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": security_session},
            files=files, timeout=60,
        )
        # Either 200 (Gemini ran) or 503 (no key); must NOT be 400
        assert r.status_code in (200, 503), r.text[:300]

    def test_happy_path_extracts_fields(self, security_session):
        files = {"image": ("id.jpg", _make_jpeg_bytes(), "image/jpeg")}
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/ocr-id",
            headers={"X-Checkpoint-Session": security_session},
            files=files, timeout=90,
        )
        if r.status_code == 503:
            pytest.skip(f"OCR unavailable: {r.text[:200]}")
        assert r.status_code == 200, r.text[:400]
        body = r.json()
        for k in ("name", "date_of_birth", "id_number", "raw_text", "confidence"):
            assert k in body, f"missing key {k}: {body}"
        assert body["confidence"] in {"high", "medium", "low"}


# ====================================================================
# 2 + 3) Product is_exit_restricted + sale enrichment + receipt scan
# ====================================================================
class TestExitRestrictedFlag:
    @pytest.fixture(scope="class")
    def flagged_product(self, admin_headers, some_location):
        body = {
            "name": "TEST_Iter138_RestrictedItem",
            "price": 1000, "stock": 50,
            "location_id": some_location["id"],
            "is_exit_restricted": True,
        }
        r = requests.post(f"{BASE_URL}/api/products", headers=admin_headers, json=body, timeout=20)
        assert r.status_code == 200, r.text[:300]
        prod = r.json()
        assert prod.get("is_exit_restricted") is True
        yield prod
        requests.delete(f"{BASE_URL}/api/products/{prod['id']}", headers=admin_headers, timeout=20)

    @pytest.fixture(scope="class")
    def normal_product(self, admin_headers, some_location):
        body = {
            "name": "TEST_Iter138_NormalItem", "price": 500, "stock": 50,
            "location_id": some_location["id"],
        }
        r = requests.post(f"{BASE_URL}/api/products", headers=admin_headers, json=body, timeout=20)
        assert r.status_code == 200
        prod = r.json()
        assert prod.get("is_exit_restricted") is False
        yield prod
        requests.delete(f"{BASE_URL}/api/products/{prod['id']}", headers=admin_headers, timeout=20)

    def test_create_flag_persisted(self, admin_headers, flagged_product):
        # GET /api/products returns it
        r = requests.get(f"{BASE_URL}/api/products", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        found = next((p for p in r.json() if p["id"] == flagged_product["id"]), None)
        assert found is not None
        assert found["is_exit_restricted"] is True

    def test_update_can_clear_flag(self, admin_headers, normal_product):
        r = requests.put(f"{BASE_URL}/api/products/{normal_product['id']}",
                         headers=admin_headers, json={"is_exit_restricted": True}, timeout=20)
        assert r.status_code == 200
        assert r.json()["is_exit_restricted"] is True
        # flip back
        r2 = requests.put(f"{BASE_URL}/api/products/{normal_product['id']}",
                          headers=admin_headers, json={"is_exit_restricted": False}, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["is_exit_restricted"] is False

    def test_sale_enriches_items_with_flag(self, admin_headers, flagged_product, normal_product):
        sale_body = {
            "items": [
                {"product_id": flagged_product["id"], "name": flagged_product["name"], "qty": 1, "price": 1000},
                {"product_id": normal_product["id"], "name": normal_product["name"], "qty": 1, "price": 500},
            ],
            "total": 1500, "payment_method": "cash",
            "customer_name": "TEST_Buyer",
        }
        r = requests.post(f"{BASE_URL}/api/sales", headers=admin_headers, json=sale_body, timeout=20)
        assert r.status_code == 200, r.text[:300]
        sale = r.json()
        items = sale["items"]
        flagged = next(i for i in items if i["product_id"] == flagged_product["id"])
        plain = next(i for i in items if i["product_id"] == normal_product["id"])
        assert flagged.get("is_exit_restricted") is True, flagged
        assert not plain.get("is_exit_restricted"), plain
        # store for next test
        TestExitRestrictedFlag._receipt_no = sale["receipt_number"]

    def test_receipt_exit_scan_denies_flagged(self, security_session):
        rn = getattr(TestExitRestrictedFlag, "_receipt_no", None)
        assert rn, "previous sale test must have run"
        r = requests.post(
            f"{BASE_URL}/api/security/checkpoint/scan/receipt",
            headers={"X-Checkpoint-Session": security_session},
            json={"receipt_number": rn}, timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # decision can be returned at top level or nested under "event"
        decision = body.get("decision") or (body.get("event") or {}).get("decision")
        assert decision == "denied", f"expected denied for flagged item, got {body}"


# ====================================================================
# 4) WebSocket /checkpoint/ws
# ====================================================================
def _ws_url(token):
    parsed = urlparse(BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/security/checkpoint/ws?session={token}"


class TestWebSocket:
    def test_missing_session_rejected(self):
        async def run():
            url = _ws_url("")
            url = url.replace("?session=", "")  # drop param entirely
            try:
                async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                return None
            except websockets.exceptions.InvalidStatus as e:
                return ("status", e.response.status_code)
            except websockets.exceptions.ConnectionClosed as e:
                return ("close", e.code)
            except Exception as e:
                return ("err", str(e))
        res = asyncio.run(run())
        # Either rejected at handshake or closed with 4401
        assert res is not None
        kind, val = res
        if kind == "close":
            assert val == 4401, res
        else:
            # handshake error is acceptable too (FastAPI may reject)
            assert kind in ("status", "err", "close"), res

    def test_invalid_session_rejected(self):
        """An invalid session must be rejected — either by close(4401) (if the
        framework lets that bubble) or by an HTTP 403 handshake rejection
        (Starlette converts close-before-accept into 403). Either is valid auth denial."""
        async def run():
            url = _ws_url("bogus-token")
            try:
                async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    return ("accepted", msg)
            except websockets.exceptions.ConnectionClosed as e:
                return ("close", e.code)
            except websockets.exceptions.InvalidStatus as e:
                return ("status", e.response.status_code)
            except Exception as e:
                return ("err", str(e))
        kind, val = asyncio.run(run())
        assert kind != "accepted", f"WS should NOT accept invalid token, got {val}"
        if kind == "close":
            assert val == 4401, f"expected close 4401, got {val}"
        elif kind == "status":
            assert val in (401, 403), f"expected 401/403 handshake reject, got {val}"
        else:
            # err string — must contain auth/forbidden marker
            assert any(s in val.lower() for s in ("403", "401", "forbidden", "unauth")), val

    def test_valid_session_joined_and_event(self, security_session, admin_headers):
        async def run():
            url = _ws_url(security_session)
            async with websockets.connect(url, open_timeout=15, close_timeout=5) as ws:
                joined_raw = await asyncio.wait_for(ws.recv(), timeout=10)
                joined = json.loads(joined_raw)
                assert joined.get("type") == "joined", joined
                # Trigger a scan and expect an 'event' broadcast
                me = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=10).json()
                uid = me.get("id") or me.get("user", {}).get("id")
                requests.post(
                    f"{BASE_URL}/api/security/checkpoint/scan",
                    headers={"X-Checkpoint-Session": security_session},
                    json={"scan_type": "qr", "payload": uid}, timeout=15,
                )
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(msg_raw)
                assert msg.get("type") == "event", msg
                assert "event" in msg
                # Now finish -> expect clear
                requests.post(
                    f"{BASE_URL}/api/security/checkpoint/finish",
                    headers={"X-Checkpoint-Session": security_session},
                    timeout=15,
                )
                clear_raw = await asyncio.wait_for(ws.recv(), timeout=10)
                clear = json.loads(clear_raw)
                assert clear.get("type") == "clear", clear
                return True
        ok = asyncio.run(run())
        assert ok
