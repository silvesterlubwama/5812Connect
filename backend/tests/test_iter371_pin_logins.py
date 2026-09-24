"""iter371 — the two POS PIN logins were left behind by the iter353 PIN hashing.

`/auth/sales-portal-login` and `/auth/pin-login` both still queried the
cleartext `users.pin` field that the hashing migration deletes, so nobody could
sign in to a POS terminal at all. Both now look the person up by the HMAC
digest, confirm it in constant time, escape the last-name regex and are
throttled like every other public PIN surface.

The admin account carries POS PIN 4917 (see /app/memory/test_credentials.md).
"""
import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
POS = {"last_name": "Admin", "pin": "4917"}


@pytest.fixture(scope="module", autouse=True)
def clear_throttle():
    """The endpoint allows 10 attempts / 10 min per IP — clear the bucket so the
    suite can be re-run straight away."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")

    async def wipe():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.public_endpoint_hits.delete_many(
            {"action": {"$in": ["sales_portal_login", "pin_login"]}})

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(wipe())


def test_sales_portal_login_accepts_a_hashed_pin():
    r = requests.post(f"{BASE}/auth/sales-portal-login", json=POS, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token") and body.get("name") == "Admin"


def test_pin_login_accepts_a_hashed_pin():
    r = requests.post(f"{BASE}/auth/pin-login", json={"pin": POS["pin"]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("token")


def test_the_token_actually_works():
    tok = requests.post(f"{BASE}/auth/sales-portal-login", json=POS, timeout=30).json()["token"]
    me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert me.status_code == 200
    # the POS needs the people picker, which is staff-only
    s = requests.get(f"{BASE}/people/suggest", timeout=30,
                     headers={"Authorization": f"Bearer {tok}"},
                     params={"q": "ad", "kinds": "customer,member,user,guest"})
    assert s.status_code == 200


@pytest.mark.parametrize("payload", [
    {"last_name": "Admin", "pin": "0000"},
    {"last_name": "NobodyHere", "pin": "4917"},
])
def test_wrong_credentials_give_one_uniform_401(payload):
    r = requests.post(f"{BASE}/auth/sales-portal-login", json=payload, timeout=30)
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid last name or PIN"


def test_a_regex_in_the_last_name_cannot_crash_the_lookup():
    r = requests.post(f"{BASE}/auth/sales-portal-login",
                      json={"last_name": "Ad(min", "pin": "4917"}, timeout=30)
    assert r.status_code == 401


def test_missing_fields_are_a_400():
    r = requests.post(f"{BASE}/auth/sales-portal-login", json={"last_name": "Admin"}, timeout=30)
    assert r.status_code == 400
