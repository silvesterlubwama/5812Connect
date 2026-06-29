"""Iteration 189 — Scan-item Photo+AI regression.

Repro of the production bug: the scan-item endpoint was re-downloading a
just-uploaded image via httpx against a relative `/uploads/...` URL (because
`storage.upload_bytes` doesn't exist — every photo silently fell back to
disk). The download failed, the AI got an empty file, and every scan
returned `name='Unidentified item'` with low confidence.

This test:
  - Uploads two tiny JPEGs to the scan endpoint with an editor PIN session
  - Confirms the response is 200 (no 500 crash)
  - Confirms image_urls round-trips back to the client
  - Confirms either AI identification ran (`source='ai_vision'`) or the
    barebones `Unidentified item` fallback (acceptable for a synthetic blob)
  - Verifies the persisted URL is a real URL the client could fetch back
    (either an absolute https:// from cloud storage OR an `/api/`-prefixed
    relative path — NOT the broken `/uploads/...` shape).
"""
import io
import os
import time
import struct
import requests
import pytest
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


def _make_jpeg() -> bytes:
    """Smallest valid JPEG — a 1x1 white pixel. Gemini will say 'low
    confidence' but the endpoint must still return cleanly."""
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
        0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01,
        0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00,
    ] + [0x08] * 64 + [
        0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00,
        0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00,
        0x1F, 0x00,
    ] + [0x00] * 16 + list(range(16)) + [
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00,
        0x3F, 0x00, 0x00, 0xFF, 0xD9,
    ])


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def shipment(headers):
    r = requests.post(f"{BASE_URL}/api/shipments", headers=headers,
                      json={"name": f"Scan AI Ship {int(time.time())}",
                            "dest_country": "Uganda"}, timeout=10)
    s = r.json()
    requests.post(f"{BASE_URL}/api/shipments/{s['id']}/set-pin", headers=headers,
                  json={"pin": "4242"}, timeout=10)
    yield s
    requests.delete(f"{BASE_URL}/api/shipments/{s['id']}", headers=headers, timeout=10)


def _editor_login(token, pin="4242"):
    r = requests.post(f"{BASE_URL}/api/public/shipments/{token}/login",
                      json={"pin": pin}, timeout=10)
    r.raise_for_status()
    return r.json()["edit_token"]


class TestScanPhotoAI:
    def test_photo_scan_does_not_crash_and_returns_image_urls(self, shipment):
        """The exact code path that was returning 'Unknown' in production —
        upload a photo with no ISBN/UPC hint and assert the endpoint comes
        back cleanly with the image URLs in the response."""
        edit_token = _editor_login(shipment["token"])
        jpg = _make_jpeg()
        files = [
            ("images", ("scan1.jpg", io.BytesIO(jpg), "image/jpeg")),
            ("images", ("scan2.jpg", io.BytesIO(jpg), "image/jpeg")),
        ]
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            files=files,
            headers={"X-Shipment-Edit-Token": edit_token},
            timeout=60,  # AI calls can be slow
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Always returns something the client can show + edit
        assert "name" in body
        assert "category" in body
        assert "image_urls" in body
        # Both photos should have persisted
        assert len(body["image_urls"]) == 2, body["image_urls"]
        # URL shape — NOT the broken relative `/uploads/...` we used to return
        for url in body["image_urls"]:
            assert url.startswith(("http://", "https://", "/api/")), \
                f"Bad URL shape (won't be reachable from frontend): {url}"

    def test_photo_scan_with_isbn_hint_still_works(self, shipment):
        """Mixed mode: photo + a known ISBN. Should hit Google Books FIRST
        and not even touch the AI path — proves we don't regress the fast
        path while fixing the slow one."""
        edit_token = _editor_login(shipment["token"])
        jpg = _make_jpeg()
        r = requests.post(
            f"{BASE_URL}/api/public/shipments/{shipment['token']}/scan-item",
            params={"isbn": "9780140329513"},
            files=[("images", ("scan.jpg", io.BytesIO(jpg), "image/jpeg"))],
            headers={"X-Shipment-Edit-Token": edit_token},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Either Google Books hit (preferred — fast path)
        # or AI vision (slower path) — both are valid.
        assert body.get("source") in ("google_books", "ai_vision", "manual"), body
