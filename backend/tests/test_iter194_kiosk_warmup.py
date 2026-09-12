"""Iteration 194 — Kiosk offline-cache warmup endpoint."""
import os
import time
import requests
import pytest
from dotenv import load_dotenv

import creds  # env-backed logins, see tests/creds.py
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestKioskWarmup:
    def test_warmup_returns_directory_shape(self, headers):
        r = requests.get(f"{BASE_URL}/api/checkins/kiosk-warmup", headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Always present + well-shaped, even when no parents are registered yet
        assert "count" in body
        assert "entries" in body
        assert isinstance(body["entries"], list)
        # Each entry must surface a parent + children list
        for e in body["entries"][:5]:
            assert "parent" in e
            assert "children" in e
            assert isinstance(e["children"], list)
            # Parent must carry at least one of (id, phone, email) so the
            # frontend has SOMETHING to key the cache by — otherwise warming
            # this row is meaningless.
            p = e["parent"]
            assert any(p.get(k) for k in ("id", "phone", "email", "name")), p

    def test_warmup_respects_limit(self, headers):
        r = requests.get(f"{BASE_URL}/api/checkins/kiosk-warmup?limit=50",
                         headers=headers, timeout=10)
        assert r.status_code == 200
        assert len(r.json()["entries"]) <= 50

    def test_warmup_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/checkins/kiosk-warmup", timeout=10)
        assert r.status_code in (401, 403)
