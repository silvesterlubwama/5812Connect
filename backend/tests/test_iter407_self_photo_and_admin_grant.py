# iter407: self profile photo (any role) + "others need manager+" guard, over the public URL.
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_ID = "9e76c0f3-4709-40c7-88f2-846963742632"

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cf000000030101005c2b5e0a0000000049454e44ae426082"
)


def _login(ident, pw):
    r = requests.post(f"{API}/auth/login", json={"identifier": ident, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed for {ident}: {r.status_code}")
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d["user"]


@pytest.fixture(scope="module")
def member():
    return _login("member@5812uganda.org", "Member@5812")


# Self photo upload as non-staff Member
def test_member_can_set_own_photo_and_it_mirrors_to_member(member):
    h, u = member
    r = requests.post(f"{API}/users/{u['id']}/photo", headers=h,
                      files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, timeout=20)
    assert r.status_code == 200, r.text
    url = r.json()["photo_url"]
    assert url.startswith("/api/storage/profile-photos/")
    p = requests.get(f"{API}/portal/profile", headers=h, timeout=20).json()
    assert p["user"]["photo_url"] == url
    assert p["member"]["photo_url"] == url
    img = requests.get(f"{BASE_URL}{url}", timeout=20)
    assert img.status_code == 200


# Changing someone else's photo is refused below manager
def test_member_cannot_set_someone_elses_photo(member):
    h, _ = member
    r = requests.post(f"{API}/users/{ADMIN_ID}/photo", headers=h,
                      files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, timeout=20)
    assert r.status_code == 403


# Non-image uploads are rejected
def test_non_image_rejected(member):
    h, u = member
    r = requests.post(f"{API}/users/{u['id']}/photo", headers=h,
                      files={"file": ("t.txt", io.BytesIO(b"hello"), "text/plain")}, timeout=20)
    assert r.status_code in (400, 415, 422), r.status_code


# Unauthenticated upload refused
def test_unauthenticated_refused():
    r = requests.post(f"{API}/users/{ADMIN_ID}/photo",
                      files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, timeout=20)
    assert r.status_code in (401, 403)
