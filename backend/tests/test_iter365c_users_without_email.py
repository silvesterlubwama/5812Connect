"""iter365b — accounts without an email address.

The `users.email` unique index treated every email-less account as `email: ""`,
so creating a second volunteer / kiosk-only user without an email raised a
duplicate-key error and the request hung for 60s before the gateway gave up.
The index is now unique only for accounts that actually have an email.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER365C_{uuid.uuid4().hex[:6]}"
created = []


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    for uid in created:
        requests.delete(f"{BASE}/admin/users/{uid}", headers=h, timeout=30)


def _create(head, **extra):
    payload = {"name": f"{TAG} {extra.pop('label', 'user')}", "role": "Member", **extra}
    r = requests.post(f"{BASE}/admin/users", json=payload, headers=head, timeout=45)
    if r.status_code == 200:
        created.append(r.json()["id"])
    return r


def test_two_users_without_email_can_be_created(head):
    a = _create(head, label="noemail-a")
    assert a.status_code == 200, a.text
    b = _create(head, label="noemail-b")
    assert b.status_code == 200, b.text
    assert a.json()["id"] != b.json()["id"]


def test_blank_email_update_is_fast_and_ok(head):
    r = _create(head, label="blank-update", email=f"{TAG.lower()}@example.org")
    assert r.status_code == 200
    uid = r.json()["id"]
    upd = requests.put(f"{BASE}/admin/users/{uid}", json={"email": "", "phone": "0700000111"},
                       headers=head, timeout=30)
    assert upd.status_code == 200, upd.text
    assert upd.json().get("phone") == "0700000111"


def test_duplicate_real_email_is_rejected_cleanly(head):
    r = _create(head, label="dup", email="admin@5812uganda.org")
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()
