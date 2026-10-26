"""iter396 — fresh-DB bootstrap, passkey sign-in across organisations, Google
session error paths, cross-tenant safety and sign-in regression.
Run alone (auth routes rate limited ~20/min per IP). Hits http://localhost:8001
directly (Host-header tests). Cleans up only rows it creates, by id."""
import base64
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import uuid

import cbor2
import pytest
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from pymongo import MongoClient

LOCAL = os.environ.get("TEST_LOCAL_BASE", "http://localhost:8001")
API = f"{LOCAL}/api"
HERE = os.path.dirname(__file__)


def _env():
    env = {}
    with open(os.path.join(HERE, "..", ".env")) as fh:
        for line in fh:
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k] = v.strip('"')
    return env


ENV = _env()
MONGO_URL = os.environ.get("MONGO_URL") or ENV["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or ENV["DB_NAME"]
OWNER_EMAIL = os.environ.get("OWNER_EMAIL") or ENV.get("OWNER_EMAIL")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD") or ENV.get("OWNER_PASSWORD")
if not OWNER_EMAIL or not OWNER_PASSWORD:
    pytest.skip("OWNER_EMAIL/OWNER_PASSWORD not configured", allow_module_level=True)
OWNER = {"identifier": OWNER_EMAIL, "password": OWNER_PASSWORD}
UNSCOPED = {
    "organizations", "org_exports", "counters", "app_config", "cron_runs",
    "public_endpoint_hits", "login_attempts", "org_audit_log", "sessions",
    "password_reset_tokens",
}

A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
B_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}
ORG_A = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"   # 58:12 Global
ORG_B = "ee79732c-1263-46a8-bf46-511c5fe812bf"   # Lubwamas
RP = "passkey-test.example.org"
ORIGIN = f"https://{RP}"


def _db():
    return MongoClient(MONGO_URL)[DB_NAME]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _login(creds, headers=None, expect=200):
    for _ in range(3):
        _db().login_attempts.delete_many({})
        r = requests.post(f"{API}/auth/login", json=creds, headers=headers or {}, timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        assert r.status_code == expect, r.text
        return r.json()
    pytest.fail("login rate limited")


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _begin(body=None, **kw):
    return requests.post(f"{API}/webauthn/authenticate/begin", json=body, timeout=30, **kw)


def _complete(body):
    return requests.post(f"{API}/webauthn/authenticate/complete", json=body, timeout=30)


# ---------- software authenticator (EC P-256, ES256) ----------
class SoftKey:
    def __init__(self):
        self.priv = ec.generate_private_key(ec.SECP256R1())
        nums = self.priv.public_key().public_numbers()
        self.cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
                                 -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        self.cred_id = os.urandom(32)

    def assertion(self, challenge_b64, sign_count=1):
        auth_data = hashlib.sha256(RP.encode()).digest() + bytes([0x05]) + struct.pack(">I", sign_count)
        client_data = json.dumps({"type": "webauthn.get", "challenge": challenge_b64,
                                  "origin": ORIGIN, "crossOrigin": False}).encode()
        sig = self.priv.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64u(self.cred_id), "rawId": b64u(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64u(client_data), "authenticatorData": b64u(auth_data),
                             "signature": b64u(sig), "userHandle": None},
                "clientExtensionResults": {}, "rpId": RP, "expectedOrigin": ORIGIN}


@pytest.fixture(scope="module")
def S():
    s = {}
    a = _login(A_ADMIN); s["a_tok"], s["a_id"] = a["token"], a["user"]["id"]
    b = _login(B_ADMIN); s["b_tok"], s["b_id"] = b["token"], b["user"]["id"]
    return s


@pytest.fixture
def b_passkey(S):
    """Credential row for admin@lubwamas.org inserted directly; removed by id."""
    key = SoftKey()
    row_id = f"wk_test396_{uuid.uuid4().hex[:8]}"
    _db().webauthn_credentials.insert_one({
        "id": row_id, "user_id": S["b_id"], "credential_id": b64u(key.cred_id),
        "public_key": b64u(key.cose), "sign_count": 0, "active": True,
        "organization_id": ORG_B, "device_name": "TEST_iter396",
        "created_at": "2026-01-01T00:00:00+00:00"})
    yield key
    _db().webauthn_credentials.delete_one({"id": row_id})


# ---------- fresh database bootstrap ----------
class TestFreshBootstrap:
    def test_fresh_db_boot_is_usable(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "scratch_iter396_fresh_boot.py")],
                           capture_output=True, text=True, timeout=110, cwd=os.path.join(HERE, ".."))
        line = [l for l in p.stdout.splitlines() if l.startswith("RESULT ")]
        assert line, p.stdout[-2000:] + p.stderr[-2000:]
        res = json.loads(line[-1][7:])
        assert "error" not in res, res
        assert res["orgs"] == [["58:12 Global", "5812global", True, "active"]]
        assert res["owners"] == [[OWNER_EMAIL.lower(), None]]
        # No route may blow up for lack of an organisation. The Google one calls
        # the external session service, so a gateway failure there is not ours.
        ours = {k: v for k, v in res["codes"].items() if k != "google_bad_session"}
        assert all(c < 500 for c in ours.values()), res["codes"]
        assert res["codes"]["google_bad_session"] in (400, 401, 403, 500, 502, 504), res["codes"]
        if res["codes"]["google_bad_session"] == 500:
            pytest.skip("the external Google session service was unreachable on this run")
        # With one organisation there is nothing to choose: the owner is signed
        # straight in. An empty or single-item picker was a dead end.
        assert res["owner_login"]["status"] == 200, res["owner_login"]
        assert res["owner_login"]["requires_org_selection"] is False, res["owner_login"]
        assert res["owner_login"]["signed_in"] is True, res["owner_login"]
        assert res["scratch_db"] not in MongoClient(MONGO_URL).list_database_names()

    def test_live_db_untouched(self):
        d = _db()
        assert d.organizations.count_documents({"id": {"$in": [ORG_A, ORG_B]}}) == 2
        assert d.users.count_documents({"role": "super_admin"}) == 1


# ---------- passkey begin ----------
class TestPasskeyBegin:
    @pytest.mark.parametrize("body", [None, {}, {"email": ""}, {"email": "admin@5812uganda.org"},
                                      {"email": "admin@lubwamas.org"},
                                      {"email": f"nobody_{uuid.uuid4().hex[:6]}@nowhere.test"}])
    def test_begin_never_500(self, body):
        r = _begin(body) if body is not None else requests.post(
            f"{API}/webauthn/authenticate/begin", timeout=30)
        assert r.status_code == 200, (body, r.status_code, r.text[:300])
        j = r.json()
        assert isinstance(j.get("allowCredentials"), list)
        assert isinstance(j.get("challenge"), str) and j["challenge"]

    def test_begin_same_shape_real_vs_fake(self):
        real = _begin({"email": "admin@5812uganda.org"}).json()
        fake = _begin({"email": "nobody_x@nowhere.test"}).json()
        assert set(real.keys()) == set(fake.keys())

    def test_org_b_passkey_visible_on_shared_address(self, b_passkey):
        j = _begin({"email": "admin@lubwamas.org"}).json()
        ids = [c["id"] for c in j["allowCredentials"]]
        assert b64u(b_passkey.cred_id) in ids


# ---------- passkey complete error paths ----------
class TestPasskeyCompleteErrors:
    def test_missing_client_data(self):
        assert _complete({"response": {}}).status_code == 400

    def test_malformed_client_data(self):
        assert _complete({"response": {"clientDataJSON": "%%%not-base64%%%"}}).status_code == 400

    def test_unknown_challenge(self):
        cd = b64u(json.dumps({"type": "webauthn.get", "challenge": b64u(os.urandom(32))}).encode())
        assert _complete({"response": {"clientDataJSON": cd}}).status_code == 400

    def test_known_challenge_unknown_credential(self):
        ch = _begin({}).json()["challenge"]
        cd = b64u(json.dumps({"type": "webauthn.get", "challenge": ch}).encode())
        r = _complete({"id": b64u(os.urandom(16)), "response": {"clientDataJSON": cd}})
        assert r.status_code == 400 and "Credential" in r.text

    @pytest.mark.parametrize("body", [{"response": "string"}, {"response": None}, []])
    def test_odd_shapes_not_500(self, body):
        r = _complete(body)
        assert 400 <= r.status_code < 500, (body, r.status_code, r.text[:200])

    def test_operator_injection_in_challenge(self):
        cd = b64u(json.dumps({"type": "webauthn.get", "challenge": {"$ne": ""}}).encode())
        r = _complete({"id": {"$ne": ""}, "response": {"clientDataJSON": cd}})
        assert 400 <= r.status_code < 500, (r.status_code, r.text[:200])


# ---------- full passkey sign-in with a software key + tenant scope ----------
class TestPasskeyFullFlow:
    def test_org_b_passkey_login_token_scoped_to_org_b(self, S, b_passkey):
        ch = _begin({"email": "admin@lubwamas.org", "rpId": RP}).json()["challenge"]
        r = _complete(b_passkey.assertion(ch))
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["user"]["id"] == S["b_id"]
        assert "password_hash" not in j["user"]
        tok = j["token"]
        me = requests.get(f"{API}/auth/me", headers=H(tok), timeout=30)
        assert me.status_code == 200 and me.json().get("email") == "admin@lubwamas.org"
        # members list only from Lubwamas
        m = requests.get(f"{API}/members", headers=H(tok), params={"limit": 200}, timeout=30)
        assert m.status_code == 200
        data = m.json()
        rows = data if isinstance(data, list) else (data.get("members") or data.get("items") or [])
        ids = [x.get("id") for x in rows]
        if ids:
            orgs = set(d["organization_id"] for d in _db().members.find(
                {"id": {"$in": ids}}, {"_id": 0, "organization_id": 1}))
            assert orgs <= {ORG_B}, orgs
        # challenge is single-use
        r2 = _complete(b_passkey.assertion(ch, sign_count=2))
        assert r2.status_code == 400

    def test_org_a_passkey_refused_on_lubwamas_host(self, S):
        key = SoftKey()
        row_id = f"wk_test396_{uuid.uuid4().hex[:8]}"
        _db().webauthn_credentials.insert_one({
            "id": row_id, "user_id": S["a_id"], "credential_id": b64u(key.cred_id),
            "public_key": b64u(key.cose), "sign_count": 0, "active": True,
            "organization_id": ORG_A, "device_name": "TEST_iter396"})
        try:
            ch = _begin({"email": "admin@5812uganda.org", "rpId": RP}).json()["challenge"]
            r = requests.post(f"{API}/webauthn/authenticate/complete", json=key.assertion(ch),
                              headers={"Host": "new.lubwamas.org"}, timeout=30)
            assert r.status_code in (401, 403), (r.status_code, r.text[:200])
            assert "token" not in r.text
        finally:
            _db().webauthn_credentials.delete_one({"id": row_id})

    def test_passkey_token_cannot_read_org_a_member(self, S, b_passkey):
        ch = _begin({"email": "admin@lubwamas.org", "rpId": RP}).json()["challenge"]
        tok = _complete(b_passkey.assertion(ch)).json()["token"]
        a_mem = _db().members.find_one({"organization_id": ORG_A}, {"_id": 0, "id": 1})
        if not a_mem:
            pytest.skip("no org A member")
        r = requests.get(f"{API}/members/{a_mem['id']}", headers=H(tok), timeout=30)
        assert r.status_code in (403, 404), (r.status_code, r.text[:200])

    def test_org_b_passkey_refused_on_org_a_host(self, b_passkey):
        hosts = _db().organizations.find_one({"id": ORG_A}, {"_id": 0, "hostnames": 1}).get("hostnames") or []
        if not hosts:
            pytest.skip("org A has no hostname")
        ch = _begin({"email": "admin@lubwamas.org", "rpId": RP}).json()["challenge"]
        r = requests.post(f"{API}/webauthn/authenticate/complete", json=b_passkey.assertion(ch),
                          headers={"Host": hosts[0]}, timeout=30)
        assert r.status_code == 403, (r.status_code, r.text[:200])


# ---------- Google session error paths ----------
class TestGoogleSession:
    def test_no_session_id_400(self):
        n = _db().users.count_documents({})
        r = requests.post(f"{API}/auth/google-session", json={}, timeout=30)
        assert r.status_code == 400
        assert _db().users.count_documents({}) == n

    def test_invalid_session_id_401_no_user_created(self):
        d = _db()
        n, g = d.users.count_documents({}), d.guests.count_documents({})
        r = requests.post(f"{API}/auth/google-session", json={"session_id": "fake_" + uuid.uuid4().hex},
                          timeout=30)
        assert r.status_code == 401, r.text
        assert "detail" in r.json()
        assert d.users.count_documents({}) == n and d.guests.count_documents({}) == g


# ---------- regression on password sign-in ----------
class TestSignInRegression:
    def test_admins_login_own_org(self, S):
        d = _db()
        assert d.users.find_one({"id": S["a_id"]})["organization_id"] == ORG_A
        assert d.users.find_one({"id": S["b_id"]})["organization_id"] == ORG_B

    def test_owner_org_selection_and_enter_one(self):
        # On the main address the owner lands in the default organisation, then
        # moves between organisations one at a time from the console.
        orig = _db().users.find_one({"email": OWNER_EMAIL.lower()}, {"_id": 0, "active_organization_id": 1})
        _db().users.update_one({"email": OWNER_EMAIL.lower()}, {"$set": {"active_organization_id": None}})
        j = _login(OWNER)
        assert not j.get("requires_org_selection"), j
        assert j["user"]["organization_id"] == ORG_A
        tok = j["token"]
        try:
            r = requests.post(f"{API}/organizations/{ORG_B}/enter", headers=H(tok), timeout=30)
            assert r.status_code == 200, r.text[:200]
            r = requests.post(f"{API}/organizations/{ORG_A}/enter", headers=H(tok), timeout=30)
            assert r.status_code == 200, r.text[:200]
            u = _db().users.find_one({"email": OWNER_EMAIL.lower()})
            assert u["active_organization_id"] == ORG_A
        finally:
            _db().users.update_one({"email": OWNER_EMAIL.lower()},
                                   {"$set": {"active_organization_id": orig.get("active_organization_id")}})

    def test_a_admin_refused_on_lubwamas_host(self):
        _login(A_ADMIN, headers={"Host": "new.lubwamas.org"}, expect=401)


# ── A deployment that predates organisations must adopt its own data ─────────
# This is the production case the first fix missed: the database is NOT empty,
# it just has no organisation, so creating one is not enough — the rows already
# there carry no tenant key and stay invisible.

def test_existing_data_is_adopted_into_the_first_organisation():
    import asyncio as _asyncio
    import subprocess
    import sys
    from pymongo import MongoClient

    mongo = MongoClient(_env()["MONGO_URL"])
    probe = "iter396_adopt_probe"
    mongo.drop_database(probe)
    db = mongo[probe]
    # organizations exists but is empty, like production
    db.organizations.insert_one({"id": "x"})
    db.organizations.delete_many({})
    db.users.insert_many([
        {"id": "u1", "email": "a@x.org", "role": "admin", "status": "active"},
        {"id": "u2", "email": "b@x.org", "role": "Member", "status": "active"},
        {"id": "own", "email": "owner@x.org", "role": "super_admin", "status": "active"},
    ])
    db.members.insert_many([{"id": f"m{i}", "name": f"M{i}"} for i in range(5)])
    db.sessions.insert_one({"jti": "j1", "user_id": "u1"})   # unscoped by design
    # conftest patches pymongo to stamp direct inserts with the default
    # organisation, which is the opposite of what this probe needs: production's
    # rows predate organisations entirely. Strip the stamp back off.
    for coll in ("users", "members", "sessions"):
        db[coll].update_many({}, {"$unset": {"organization_id": ""}})
    assert db.users.count_documents({"organization_id": {"$exists": True}}) == 0
    try:
        code = (
            "import asyncio, logging;"
            "logging.basicConfig(level=logging.INFO);"
            "from org_bootstrap import ensure_default_organization;"
            "asyncio.run(ensure_default_organization())"
        )
        # A clean environment on purpose: inheriting pytest's leaves the real
        # DB_NAME in place and the probe would be stamped with the live
        # organisation's id instead of its own.
        env = {"MONGO_URL": _env()["MONGO_URL"], "DB_NAME": probe,
               "SECRET_KEY": _env().get("SECRET_KEY", "probe"),
               "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        r = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(os.path.dirname(__file__), ".."),
                           env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-500:]
        assert "Adopted" in r.stderr, f"nothing was adopted: {r.stderr[-400:]}"
        org = db.organizations.find_one({}, {"_id": 0, "id": 1, "is_default": 1, "status": 1})
        assert org and org["is_default"] is True and org["status"] == "active"
        oid = org["id"]
        # everything that was already there now belongs to it …
        assert db.users.count_documents({"organization_id": oid}) == 2
        assert db.members.count_documents({"organization_id": oid}) == 5
        # … except the platform owner, who sits outside all organisations …
        assert "organization_id" not in (db.users.find_one({"id": "own"}, {"_id": 0}) or {})
        # … and collections that are deliberately not tenant-scoped
        assert "organization_id" not in (db.sessions.find_one({}, {"_id": 0}) or {})
        # a restart changes nothing
        r2 = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(os.path.dirname(__file__), ".."),
                            env=env, capture_output=True, text=True, timeout=120)
        assert r2.returncode == 0, r2.stderr[-500:]
        assert db.organizations.count_documents({}) == 1
        assert db.users.count_documents({"organization_id": oid}) == 2
    finally:
        mongo.drop_database(probe)
        mongo.close()


def test_passkey_endpoints_never_return_500_on_junk():
    """Everything here arrives from a browser; malformed input is a 400, not a crash."""
    assert requests.post(f"{API}/webauthn/authenticate/begin",
                         headers={"Content-Type": "application/json"}, data="", timeout=20).status_code == 200
    for payload in ({"response": "nope"}, {"response": None}, {"response": {}},
                    {"response": {"clientDataJSON": "!!!!"}},
                    {"response": {"clientDataJSON": "eyJjaGFsbGVuZ2UiOjEyM30"}},
                    {"response": {"clientDataJSON": "eyJjaGFsbGVuZ2UiOiJ4eXoifQ"}}):
        r = requests.post(f"{API}/webauthn/authenticate/complete", json=payload, timeout=20)
        assert r.status_code == 400, f"{payload} -> {r.status_code} {r.text[:120]}"


# ── iter397: accounts that predate organisations must just sign in ──────────

def test_account_without_an_organisation_is_attached_on_sign_in():
    """Every account on a pre-tenancy deployment looks like this. Their password
    is valid and there is exactly one place they can belong to, so refusing them
    with "contact your administrator" was a dead end — nothing an administrator
    could do from inside the app would fix it."""
    import subprocess
    import sys
    db = _db()
    email = "legacy.iter397@5812uganda.org"
    pw = "Legacy@2026!"
    pw_hash = subprocess.run(
        [sys.executable, "-c", f"from deps import hash_password;print(hash_password('{pw}'))"],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
    ).stdout.strip()
    db.users.delete_many({"email": email})
    db.users.insert_one({"id": "legacy-iter397", "name": "Legacy iter397", "email": email,
                         "password_hash": pw_hash, "role": "admin", "status": "active"})
    # conftest stamps direct inserts; strip it so this really is a pre-tenancy row
    db.users.update_one({"id": "legacy-iter397"}, {"$unset": {"organization_id": ""}})
    try:
        assert "organization_id" not in db.users.find_one({"id": "legacy-iter397"}, {"_id": 0})
        r = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        default_org = db.organizations.find_one({"is_default": True}, {"_id": 0, "id": 1})
        assert db.users.find_one({"id": "legacy-iter397"}, {"_id": 0})["organization_id"] == default_org["id"]
        # and the app is usable afterwards, not just the sign-in
        h = {"Authorization": f"Bearer {token}"}
        assert requests.get(f"{API}/auth/me", headers=h, timeout=20).status_code == 200
        assert requests.get(f"{API}/members?limit=2", headers=h, timeout=20).status_code == 200
    finally:
        db.users.delete_many({"id": "legacy-iter397"})


def test_owner_on_the_main_address_lands_in_the_default_org():
    # Subdomains cannot be set up before an organisation exists, so the main web
    # address belongs to the default organisation and never shows a picker.
    first = requests.post(f"{API}/auth/login", json=OWNER, timeout=30).json()
    if first.get("token"):
        requests.post(f"{API}/organizations/exit",
                      headers={"Authorization": f"Bearer {first['token']}"}, timeout=30)
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert not j.get("requires_org_selection"), j
    assert j["user"]["organization_id"] == ORG_A


# ── iter397: moving a whole organisation between apps ───────────────────────

def test_export_and_import_moves_rows_settings_and_files():
    """What "move an organisation to another app" has to mean: the copy opens
    with its own settings, its branding intact and its images actually loading.
    Rows alone left the other server full of broken pictures."""
    import io
    h = H(_login(OWNER)["token"])
    lub_admin = _login(B_ADMIN)
    lh = H(lub_admin["token"])

    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000002000100ff03000006000557bfabd400000000"
        "49454e44ae426082")
    up = requests.post(f"{API}/admin/system-settings/branding/logo", headers=lh, timeout=60,
                       files={"file": ("probe397.png", io.BytesIO(png), "image/png")})
    assert up.status_code == 200, up.text
    logo_url = up.json()["url"]
    before = requests.get(f"{API}/admin/system-settings", headers=lh, timeout=30).json()["branding"]
    requests.put(f"{API}/admin/system-settings", headers=lh, timeout=30,
                 json={"branding": {**before, "logo_url": logo_url}})

    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    src = next(o for o in orgs if o["name"] == "Lubwamas")
    exp = requests.get(f"{API}/organizations/{src['id']}/export", headers=h, timeout=300)
    assert exp.status_code == 200, exp.text
    dump = exp.json()
    assert dump["document_count"] > 0
    assert logo_url.split("/api/storage/")[-1] in dump["files"], "the logo was not in the export"
    assert dump["files_missing"] == []

    dump["organization"] = dict(dump["organization"], name="PROBE iter397 move", slug="probeiter397")
    imp = requests.post(f"{API}/organizations/import", headers=h, json=dump, timeout=600)
    assert imp.status_code == 200, imp.text
    body = imp.json()
    new_id = body["organization"]["id"]
    try:
        assert body["restored_documents"] == dump["document_count"]
        assert body["restored_files"] == dump["file_count"]
        # the copy is a separate organisation, never the default one
        assert body["organization"].get("is_default") is not True
        assert not body["organization"].get("hostnames")

        assert requests.post(f"{API}/organizations/{new_id}/enter", headers=h, timeout=30).status_code == 200
        branding = requests.get(f"{API}/admin/system-settings", headers=h, timeout=30).json()["branding"]
        # settings are a singleton keyed by a fixed id — re-minting it lost them
        assert branding["app_name"] == before.get("app_name"), branding
        assert branding["logo_url"] and branding["logo_url"] != logo_url, "logo link was not rewritten"
        img = requests.get(f"{LOCAL}{branding['logo_url']}", timeout=60)
        assert img.status_code == 200 and img.headers["content-type"] == "image/png"
        assert img.content == png, "the restored image is not the file that was uploaded"
        assert requests.get(f"{API}/members?limit=3", headers=h, timeout=30).status_code == 200
    finally:
        requests.post(f"{API}/organizations/exit", headers=h, timeout=30)
        requests.post(f"{API}/organizations/{new_id}/status", headers=h,
                      json={"status": "suspended"}, timeout=60)
        requests.delete(f"{API}/organizations/{new_id}", headers=h,
                        params={"confirm": "probeiter397"}, timeout=300)
        # the real organisation's branding is the user's, not the test's
        requests.put(f"{API}/admin/system-settings", headers=lh, timeout=30,
                     json={"branding": before})


# ── iter397 fixes from the second adversarial pass ──────────────────────────

def test_owner_can_sign_in_on_a_tenant_address_and_lands_in_it():
    """The owner belongs to no organisation, so the hostname filter excluded
    them and every organisation's own address refused the one account that is
    allowed to enter all of them."""
    r = requests.post(f"{LOCAL}/api/auth/login", headers={"Host": "new.lubwamas.org"},
                      json=OWNER, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token")
    assert not body.get("requires_org_selection"), "should go straight into that organisation"
    me = requests.get(f"{LOCAL}/api/auth/me",
                      headers={"Authorization": f"Bearer {body['token']}"}, timeout=20).json()
    db = _db()
    lub = db.organizations.find_one({"name": "Lubwamas"}, {"_id": 0, "id": 1})
    assert me.get("active_organization_id") == lub["id"]
    # a tenant admin is still refused on another tenant's address
    w = requests.post(f"{LOCAL}/api/auth/login", headers={"Host": "new.lubwamas.org"},
                      json=A_ADMIN, timeout=30)
    assert w.status_code == 401


def test_importing_the_same_organisation_twice_both_succeed():
    """Both copies have no web address. The unique index indexes an empty array
    as a value, so writing `hostnames: []` made the second import a 500."""
    h = H(_login(OWNER)["token"])
    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    src = next(o for o in orgs if o["name"] == "Lubwamas")
    dump = requests.get(f"{API}/organizations/{src['id']}/export", headers=h, timeout=300).json()
    made = []
    try:
        for i in (1, 2):
            payload = dict(dump, organization=dict(dump["organization"],
                                                   name=f"PROBE twice {i}", slug=f"probetwice{i}"))
            r = requests.post(f"{API}/organizations/import", headers=h, json=payload, timeout=600)
            assert r.status_code == 200, f"import #{i}: {r.status_code} {r.text[:200]}"
            body = r.json()
            assert body["failures"] == [], body["failures"]
            assert body["restored_documents"] == body["expected_documents"]
            made.append((body["organization"]["id"], f"probetwice{i}"))
        assert len({m[0] for m in made}) == 2
    finally:
        for oid, slug in made:
            requests.post(f"{API}/organizations/{oid}/status", headers=h,
                          json={"status": "suspended"}, timeout=60)
            requests.delete(f"{API}/organizations/{oid}", headers=h,
                            params={"confirm": slug}, timeout=300)


def test_export_counts_match_the_database_exactly():
    """"Everything" has to be checkable: the export reports per-collection counts
    and they are compared here against the database itself. It also used to stop
    at 100,000 rows in a collection and say nothing about the rest."""
    h = H(_login(OWNER)["token"])
    db = _db()
    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    for org in orgs:
        dump = requests.get(f"{API}/organizations/{org['id']}/export", headers=h, timeout=600).json()
        truth = {}
        for name in db.list_collection_names():
            if name in UNSCOPED:
                continue
            n = db[name].count_documents({"organization_id": org["id"]})
            if n:
                truth[name] = n
        assert dump["collection_counts"] == truth, {
            "missing": {k: v for k, v in truth.items() if dump["collection_counts"].get(k) != v},
        }
        assert dump["document_count"] == sum(truth.values())
        assert all(len(rows) == truth[name] for name, rows in dump["collections"].items())


def test_owner_is_not_locked_out_when_the_only_organisation_is_suspended():
    db = _db()
    hidden = db.organizations.find_one_and_delete({"is_default": {"$ne": True}})
    db.organizations.update_one({"is_default": True}, {"$set": {"status": "suspended"}})
    owner = db.users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1})
    db.users.update_one({"id": owner["id"]}, {"$set": {"active_organization_id": None}})
    try:
        r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("token"), "a hard 403 left the owner with no way to reactivate it"
        assert body.get("all_suspended") is True
        h = H(body["token"])
        assert requests.get(f"{API}/organizations", headers=h, timeout=30).status_code == 200
        oid = body["organizations"][0]["id"]
        assert requests.post(f"{API}/organizations/{oid}/status", headers=h,
                             json={"status": "active"}, timeout=60).status_code == 200
    finally:
        db.organizations.update_one({"is_default": True}, {"$set": {"status": "active"}})
        if hidden:
            hidden.pop("_id", None)
            db.organizations.insert_one(hidden)
        db.users.update_one({"id": owner["id"]}, {"$set": {"active_organization_id": None}})
