# iter405: password sign-in binds to the org web name (X-Org-Slug); Google bogus session -> 401
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LUB_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"


def _login(ident, pw, slug):
    h = {"Content-Type": "application/json"}
    if slug:
        h["X-Org-Slug"] = slug
    return requests.post(f"{BASE_URL}/api/auth/login",
                         json={"identifier": ident, "password": pw}, headers=h, timeout=30)


# Password sign-in: Lubwamas admin on its own address
def test_lubwamas_admin_on_lubwamas():
    r = _login("admin@lubwamas.org", "Lubwama@2026", "lubwamas")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["organization_id"] == LUB_ORG
    assert isinstance(d.get("token"), str) and d["token"]
    assert "password_hash" not in d["user"]


# Password sign-in: Lubwamas admin refused on 58:12 Global address
def test_lubwamas_admin_refused_on_5812global():
    r = _login("admin@lubwamas.org", "Lubwama@2026", "5812global")
    assert r.status_code in (401, 403), f"{r.status_code} {r.text}"
    time.sleep(3)


# Password sign-in: 58:12 Global admin on its own address
def test_global_admin_on_5812global():
    r = _login("admin@5812global.org", "Admin@1234", "5812global")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["organization_id"] == GLOBAL_ORG


# Google session exchange with a bogus id -> 401 not 500
def test_google_bogus_session():
    r = requests.post(f"{BASE_URL}/api/auth/google-session", json={"session_id": "bogus-xyz"},
                      headers={"X-Org-Slug": "lubwamas"}, timeout=30)
    assert r.status_code == 401, r.text
    assert "Invalid Google session" in r.json().get("detail", "")


# Google session exchange with no session id -> 400
def test_google_missing_session():
    r = requests.post(f"{BASE_URL}/api/auth/google-session", json={}, timeout=30)
    assert r.status_code == 400, r.text


# Token from lubwamas login works on /auth/me
def test_me_after_login():
    r = _login("admin@lubwamas.org", "Lubwama@2026", "lubwamas")
    assert r.status_code == 200
    tok = r.json()["token"]
    me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {tok}",
                                                          "X-Org-Slug": "lubwamas"}, timeout=30)
    assert me.status_code == 200, me.text
    assert me.json().get("email") == "admin@lubwamas.org" or me.json().get("user", {}).get("email") == "admin@lubwamas.org"
