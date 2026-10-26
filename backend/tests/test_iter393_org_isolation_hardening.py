"""iter393 — the holes an adversarial pass found around the organisation wall.

The scoped db proxy held; everything here sits OUTSIDE it: role assignment,
unauthenticated routers, forged tokens, process-global socket state and the one
pre-auth identity lookup. Each test below is a reproduction of a real finding.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient
from passlib.context import CryptContext

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"

# The platform owner's credentials live in backend/.env (gitignored), never in
# a test file — this suite would otherwise publish the key to every organisation.
def _owner_creds():
    env = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", ".env")) as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v
    except OSError:
        pass
    email = os.environ.get("OWNER_EMAIL") or env.get("OWNER_EMAIL")
    password = os.environ.get("OWNER_PASSWORD") or env.get("OWNER_PASSWORD")
    if not email or not password:
        import pytest as _pytest
        _pytest.skip("OWNER_EMAIL/OWNER_PASSWORD not configured", allow_module_level=True)
    return {"identifier": email, "password": password}


SUPER = _owner_creds()
ORG_A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
ORG_B_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _db():
    return MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "5812global")
    ]


@pytest.fixture(autouse=True)
def _clear_login_throttle():
    _db().login_attempts.delete_many({})
    yield


def _token(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _h(creds):
    return {"Authorization": f"Bearer {_token(creds)}"}


# ------------------------------------------------- privilege escalation

def test_org_admin_cannot_mint_a_platform_owner():
    """The worst finding: an organisation's own admin could create a
    super_admin, sign in as it and walk into every other organisation."""
    h = _h(ORG_B_ADMIN)
    r = requests.post(f"{API}/admin/users", headers=h, timeout=30, json={
        "name": "TEST_iter393 escalate",
        "email": f"esc{uuid.uuid4().hex[:6]}@example.test",
        "role": "super_admin",
        "password": "Escalate@2026",
    })
    assert r.status_code == 403, r.text
    assert "platform owner" in r.text.lower()


def test_org_admin_cannot_promote_anyone_to_platform_owner():
    h = _h(ORG_B_ADMIN)
    rows = requests.get(f"{API}/admin/users", headers=h, timeout=30).json()
    users = rows if isinstance(rows, list) else rows.get("users", [])
    assert users, "need at least one user in the tenant"
    r = requests.put(f"{API}/admin/users/{users[0]['id']}", headers=h, timeout=30,
                     json={"role": "super_admin"})
    assert r.status_code == 403, r.text


def test_org_admin_cannot_delete_the_platform_owner():
    owner = _db().users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1})
    assert owner, "super admin must exist"
    h = _h(ORG_A_ADMIN)
    r = requests.delete(f"{API}/admin/users/{owner['id']}", headers=h, timeout=30)
    assert r.status_code in (403, 404), r.text
    assert _db().users.find_one({"id": owner["id"]}), "platform owner was deleted"


# ------------------------------------------------- forged / unauthenticated

def test_forged_google_token_is_refused():
    """The old /auth/google base64-decoded the token payload without checking
    its signature, so this forged payload minted an admin session."""
    import base64
    import json
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": "admin@5812uganda.org", "name": "Forged"}).encode()
    ).decode().rstrip("=")
    r = requests.post(f"{API}/auth/google", timeout=30,
                      json={"token": f"header.{payload}.signature"})
    assert r.status_code == 404, f"the unverified route is back: {r.status_code}"


def test_seed_routes_require_the_platform_owner():
    """Unauthenticated seeding inserted a known admin account into whichever
    organisation was pinned — anonymous takeover of a fresh tenant."""
    for path in ("/seed", "/seed-extended", "/seed-locations", "/seed-all"):
        r = requests.post(f"{API}{path}", timeout=30)
        assert r.status_code in (401, 403), f"{path} -> {r.status_code}"
        r2 = requests.post(f"{API}{path}", headers=_h(ORG_B_ADMIN), timeout=30)
        assert r2.status_code == 403, f"{path} as org admin -> {r2.status_code}"


def test_calling_and_presence_require_authentication():
    """These routers had no auth, so an anonymous caller inherited the default
    organisation and could read a tenant's staff directory."""
    for path in ("/calling/extensions", "/calling/contacts", "/conferences",
                 "/presence/online-users", "/reactions/quick"):
        r = requests.get(f"{API}{path}", timeout=30)
        assert r.status_code in (401, 403), f"{path} exposed anonymously: {r.status_code}"


# ------------------------------------------------- identity collisions

def test_same_email_in_two_organisations_can_both_sign_in():
    """The pre-auth lookup took whichever row Mongo returned first, so only one
    of two same-email people could ever sign in on a shared hostname."""
    db = _db()
    orgs = {o["slug"]: o["id"] for o in db.organizations.find({}, {"_id": 0, "slug": 1, "id": 1})}
    email = f"dup{uuid.uuid4().hex[:6]}@example.test"
    created = []
    try:
        for slug, password in (("5812global", "AlphaPass@1"), ("lubwamas", "BetaPass@2")):
            if slug not in orgs:
                pytest.skip(f"organisation {slug} not present")
            loc = db.locations.find_one({"organization_id": orgs[slug]}, {"_id": 0, "id": 1})
            uid = str(uuid.uuid4())
            created.append(uid)
            db.users.insert_one({
                "id": uid, "name": f"TEST_iter393 {slug}", "email": email,
                "password_hash": pwd_context.hash(password),
                "role": "Staff", "status": "active",
                "location_id": (loc or {}).get("id", ""),
                "location_ids": [(loc or {}).get("id", "")],
                "organization_id": orgs[slug],
                "created_at": "2026-10-21T00:00:00+00:00",
            })
        for slug, password in (("5812global", "AlphaPass@1"), ("lubwamas", "BetaPass@2")):
            r = requests.post(f"{API}/auth/login", timeout=30,
                              json={"identifier": email, "password": password})
            assert r.status_code == 200, f"{slug}: {r.text}"
            assert r.json()["user"]["organization_id"] == orgs[slug], \
                f"{slug} password signed into the wrong organisation"
    finally:
        for uid in created:
            db.users.delete_one({"id": uid})


def test_wrong_password_still_fails_for_a_duplicated_email():
    db = _db()
    org = db.organizations.find_one({"slug": "5812global"}, {"_id": 0, "id": 1})
    email = f"dup{uuid.uuid4().hex[:6]}@example.test"
    uid = str(uuid.uuid4())
    db.users.insert_one({
        "id": uid, "name": "TEST_iter393 wrongpw", "email": email,
        "password_hash": pwd_context.hash("RightPass@1"),
        "role": "Staff", "status": "active", "organization_id": org["id"],
        "created_at": "2026-10-21T00:00:00+00:00",
    })
    try:
        r = requests.post(f"{API}/auth/login", timeout=30,
                          json={"identifier": email, "password": "WrongPass@9"})
        assert r.status_code == 401, r.text
    finally:
        db.users.delete_one({"id": uid})


# ------------------------------------------------- smaller corrections

def test_foreign_location_id_returns_404_not_200():
    db = _db()
    other = db.organizations.find_one({"slug": "lubwamas"}, {"_id": 0, "id": 1})
    if not other:
        pytest.skip("second organisation not present")
    foreign = db.locations.find_one({"organization_id": other["id"]}, {"_id": 0, "id": 1})
    if not foreign:
        pytest.skip("second organisation has no campus")
    h = _h(ORG_A_ADMIN)
    r = requests.put(f"{API}/locations/{foreign['id']}", headers=h, timeout=30,
                     json={"name": "TEST_iter393 hijack"})
    assert r.status_code == 404, f"PUT -> {r.status_code} {r.text[:200]}"
    d = requests.delete(f"{API}/locations/{foreign['id']}", headers=h, timeout=30)
    assert d.status_code == 404, f"DELETE -> {d.status_code}"
    assert db.locations.find_one({"id": foreign["id"]}), "foreign campus was deleted"


def test_only_one_default_organisation_exists():
    """is_default decides who answers public pages on an unclaimed hostname, so
    an imported copy must never inherit it."""
    assert _db().organizations.count_documents({"is_default": True}) == 1


def test_logout_releases_the_entered_organisation():
    first = requests.post(f"{API}/auth/login", json=SUPER, timeout=30).json()
    token = first["token"]
    h = {"Authorization": f"Bearer {token}"}
    if first.get("requires_org_selection"):
        org = next(o for o in first["organizations"] if o["slug"] == "5812global")
        token = requests.post(f"{API}/organizations/{org['id']}/enter",
                              headers=h, timeout=30).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
    assert requests.get(f"{API}/auth/me", headers=h, timeout=30).status_code == 200

    requests.post(f"{API}/auth/logout", headers=h, timeout=30)
    owner = _db().users.find_one({"role": "super_admin"}, {"_id": 0, "active_organization_id": 1})
    assert not owner.get("active_organization_id"), "still holding an organisation after logout"

    again = requests.post(f"{API}/auth/login", json=SUPER, timeout=30).json()
    # Signing in again on the main address opens the default organisation — the
    # point here is that logout released the previous one, not that a picker
    # appears.
    assert again.get("user", {}).get("organization_id"), "did not land in an organisation"


# ------------------------------------------------- iter394 second pass

def test_a_token_signed_with_the_published_placeholder_key_is_rejected():
    """SECRET_KEY shipped as '5812global_secret_key_change_in_production', which
    was also hard-coded as a fallback in three places in auth.py — anyone
    reading the source could mint a session for any user id."""
    from jose import jwt
    forged = jwt.encode(
        {"sub": "anyone", "exp": 9999999999},
        "5812global_secret_key_change_in_production",
        algorithm="HS256",
    )
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {forged}"}, timeout=30)
    assert r.status_code == 401, r.text


def test_user_import_cannot_smuggle_in_a_platform_owner():
    """users/import had no role guard at all, which walked straight past the
    per-route checks."""
    r = requests.post(f"{API}/admin/users/import", headers=_h(ORG_B_ADMIN), timeout=30, json={
        "users": [{"name": "TEST_iter394 import", "email": f"imp{uuid.uuid4().hex[:6]}@example.test",
                   "role": "super_admin"}]
    })
    assert r.status_code == 403, r.text
    assert not _db().users.find_one({"name": "TEST_iter394 import"})


def test_guest_promotion_cannot_mint_a_platform_owner():
    """guests/move-to-staff took the role verbatim from the request body."""
    h = _h(ORG_B_ADMIN)
    created = requests.post(f"{API}/guests", headers=h, timeout=30, json={
        "name": "TEST_iter394 guest", "email": f"g{uuid.uuid4().hex[:6]}@example.test",
    })
    if created.status_code not in (200, 201):
        pytest.skip(f"could not create a guest: {created.status_code}")
    gid = created.json()["id"]
    try:
        r = requests.post(f"{API}/guests/{gid}/move-to-staff", headers=h, timeout=30,
                          json={"role": "super_admin", "password": "Pwned@2026"})
        assert r.status_code == 403, r.text
    finally:
        requests.delete(f"{API}/guests/{gid}", headers=h, timeout=30)
        _db().users.delete_many({"name": "TEST_iter394 guest"})


def test_presence_writes_apply_to_the_caller_not_a_supplied_user_id():
    """Any signed-in user could set another user's presence — including one in
    another organisation — because user_id came from the query string."""
    h = _h(ORG_B_ADMIN)
    me = requests.get(f"{API}/auth/me", headers=h, timeout=30).json()
    victim = _db().users.find_one(
        {"email": "admin@5812uganda.org"}, {"_id": 0, "id": 1}
    )
    assert victim, "the 58:12 admin must exist"
    requests.put(f"{API}/presence/status?user_id={victim['id']}&status=dnd", headers=h, timeout=30)
    mine = requests.get(f"{API}/presence/status/{me['id']}", headers=h, timeout=30)
    assert mine.status_code == 200 and mine.json()["status"] == "dnd", \
        "the caller's own status should have changed"
    # and the other tenant's user is untouched + not even readable
    foreign = requests.get(f"{API}/presence/status/{victim['id']}", headers=h, timeout=30)
    assert foreign.status_code == 404, foreign.text
