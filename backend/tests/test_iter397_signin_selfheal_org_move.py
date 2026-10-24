"""iter397 retest — sign-in self-heal (pre-tenancy accounts, owner picker) and
organisation export/import ("move an organisation between apps").
NEVER changes 58:12 Global / Lubwamas branding and never deletes them: only
organisations this suite imports are suspended + deleted, by their own id.
Run alone (login rate limit ~20/min)."""
import os
import subprocess
import sys
import time

import pytest
import requests
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
OWNER = {"identifier": ENV.get("OWNER_EMAIL"), "password": ENV.get("OWNER_PASSWORD")}
if not OWNER["identifier"] or not OWNER["password"]:
    pytest.skip("OWNER_EMAIL/OWNER_PASSWORD not configured", allow_module_level=True)
B_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}
A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
ORG_A = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
ORG_B = "ee79732c-1263-46a8-bf46-511c5fe812bf"
LUB_HOST = {"Host": "new.lubwamas.org"}


def _db():
    return MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def _login(creds, headers=None):
    for _ in range(3):
        _db().login_attempts.delete_many({"ok": False})
        r = requests.post(f"{API}/auth/login", json=creds, headers=headers or {}, timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        return r
    pytest.fail("login rate limited")


def _owner_token():
    j = _login(OWNER).json()
    tok = j["token"]
    if j.get("requires_org_selection"):
        tok = requests.post(f"{API}/organizations/{ORG_A}/enter", headers=H(tok), timeout=30).json()["token"]
    return tok


def _branding_snapshot():
    return {r["organization_id"]: r.get("branding")
            for r in _db().system_settings.find({"id": "default"}, {"_id": 0})}


def _drop_org(h, org_id, slug):
    requests.post(f"{API}/organizations/{org_id}/status", headers=h, json={"status": "suspended"}, timeout=60)
    return requests.delete(f"{API}/organizations/{org_id}", headers=h, params={"confirm": slug}, timeout=300)


@pytest.fixture(scope="module")
def owner():
    d = _db()
    orig = d.users.find_one({"email": OWNER["identifier"].lower()}, {"_id": 0, "active_organization_id": 1})
    before = _branding_snapshot()
    tok = _owner_token()
    yield H(tok)
    d.users.update_one({"email": OWNER["identifier"].lower()},
                       {"$set": {"active_organization_id": orig.get("active_organization_id")}})
    assert _branding_snapshot() == before, "protected organisations' branding changed!"


@pytest.fixture(scope="module")
def lub_export(owner):
    r = requests.get(f"{API}/organizations/{ORG_B}/export", headers=owner, timeout=300)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---- sign-in self-heal ----
class TestPreTenancySignIn:
    EMAIL = "legacy.t397@5812uganda.org"
    PW = "Legacy@2026!"

    def _make(self):
        pw_hash = subprocess.run([sys.executable, "-c", f"from deps import hash_password;print(hash_password('{self.PW}'))"],
                                 capture_output=True, text=True, cwd=os.path.join(HERE, "..")).stdout.strip()
        d = _db()
        d.users.delete_many({"id": "legacy-t397"})
        d.users.insert_one({"id": "legacy-t397", "name": "TEST legacy t397", "email": self.EMAIL,
                            "password_hash": pw_hash, "role": "admin", "status": "active"})
        d.users.update_one({"id": "legacy-t397"}, {"$unset": {"organization_id": ""}})

    def test_shared_address_attaches_to_default(self):
        self._make()
        try:
            r = _login({"identifier": self.EMAIL, "password": self.PW})
            assert r.status_code == 200, r.text
            assert r.json()["user"]["organization_id"] == ORG_A
            assert _db().users.find_one({"id": "legacy-t397"})["organization_id"] == ORG_A
            me = requests.get(f"{API}/auth/me", headers=H(r.json()["token"]), timeout=20)
            assert me.status_code == 200
        finally:
            _db().users.delete_many({"id": "legacy-t397"})

    def test_lubwamas_host_does_not_capture_legacy_account(self):
        """A pre-tenancy (58:12) account must not be stamped into Lubwamas just
        because its first sign-in happened on Lubwamas' address."""
        self._make()
        try:
            r = _login({"identifier": self.EMAIL, "password": self.PW}, headers=LUB_HOST)
            row = _db().users.find_one({"id": "legacy-t397"})
            print("legacy on lubwamas host ->", r.status_code, r.text[:150], row.get("organization_id"))
            assert row.get("organization_id") != ORG_B
        finally:
            _db().users.delete_many({"id": "legacy-t397"})

    def test_wrong_password_legacy_not_attached(self):
        self._make()
        try:
            r = _login({"identifier": self.EMAIL, "password": "Wrong@1234"})
            assert r.status_code == 401
            assert "organization_id" not in _db().users.find_one({"id": "legacy-t397"})
        finally:
            _db().users.delete_many({"id": "legacy-t397"})


class TestOwnerPicker:
    def test_two_orgs_no_active_shows_picker(self, owner):
        _db().users.update_one({"email": OWNER["identifier"].lower()}, {"$set": {"active_organization_id": None}})
        j = _login(OWNER).json()
        assert j.get("requires_org_selection") is True
        ids = {o["id"] for o in j["organizations"]}
        assert {ORG_A, ORG_B} <= ids

    def test_owner_with_active_org_goes_straight_in(self, owner):
        _db().users.update_one({"email": OWNER["identifier"].lower()}, {"$set": {"active_organization_id": ORG_B}})
        j = _login(OWNER).json()
        assert not j.get("requires_org_selection")
        assert j["user"]["organization_id"] == ORG_B

    def test_owner_on_lubwamas_host_enters_lubwamas(self, owner):
        # _resolve_login_org has a super-admin + host_org branch; the identity
        # query filters by organization_id first, so the owner currently gets 401
        r = _login(OWNER, headers=LUB_HOST)
        assert r.status_code == 200, r.text
        j = r.json()
        assert not j.get("requires_org_selection") and j["user"]["organization_id"] == ORG_B


# ---- export / import ----
class TestExportImport:
    def test_export_shape(self, lub_export):
        e = lub_export
        assert e["format"] == "5812-org-export/v1"
        assert e["organization"]["id"] == ORG_B
        assert e["document_count"] == sum(e["collection_counts"].values()) > 0
        assert "users" in e["collections"] and "system_settings" in e["collections"]
        assert isinstance(e["files"], dict) and isinstance(e["files_missing"], list)
        assert e["file_count"] == len(e["files"])
        for rows in e["collections"].values():
            for r in rows:
                assert "_id" not in r
                assert r["organization_id"] == ORG_B

    def test_export_requires_owner(self):
        tok = _login(A_ADMIN).json()["token"]
        assert requests.get(f"{API}/organizations/{ORG_B}/export", headers=H(tok), timeout=30).status_code in (401, 403)
        assert requests.post(f"{API}/organizations/import", headers=H(tok), json={}, timeout=30).status_code in (401, 403)

    def test_import_bad_format_400(self, owner):
        r = requests.post(f"{API}/organizations/import", headers=owner, json={"format": "nope"}, timeout=30)
        assert r.status_code == 400

    def test_two_imports_and_login_isolation(self, owner, lub_export):
        """Import the same export twice (the realistic retry case), then confirm
        the real Lubwamas admin still signs into the real Lubwamas."""
        made = []
        try:
            results = []
            for i in range(2):
                dump = dict(lub_export)
                dump["organization"] = dict(lub_export["organization"], name=f"TEST t397 copy {i}", slug="testt397copy")
                r = requests.post(f"{API}/organizations/import", headers=owner, json=dump, timeout=600)
                results.append((r.status_code, r.text[:300]))
                if r.status_code == 200:
                    made.append((r.json()["organization"]["id"], r.json()["organization"]["slug"]))
            print("import results:", results)
            assert results[0][0] == 200, results[0]
            body_ok = made[0]
            copy = _db().organizations.find_one({"id": body_ok[0]}, {"_id": 0})
            assert copy.get("is_default") is not True
            # restored singleton settings keep fixed id
            s = _db().system_settings.find_one({"organization_id": body_ok[0], "id": "default"}, {"_id": 0})
            assert s and s["branding"] == lub_export["collections"]["system_settings"][0]["branding"]
            # real admin, shared address and own host, must still land in Lubwamas
            landed = []
            for hdr in (None, None, None, LUB_HOST):
                r = _login(B_ADMIN, headers=hdr)
                assert r.status_code == 200, r.text
                landed.append((hdr is not None, r.json()["user"]["organization_id"]))
            print("admin@lubwamas.org landed in:", landed)
            assert all(o == ORG_B for _, o in landed), f"admin@lubwamas.org signed into the copy: {landed}"
            assert results[1][0] == 200, f"second import failed: {results[1]}"
        finally:
            for oid, slug in made:
                d = _drop_org(owner, oid, slug)
                print("cleanup", oid, d.status_code)
            assert _db().organizations.count_documents({"slug": {"$regex": "^testt397copy"}}) == 0

    def test_delete_guards(self, owner):
        r = requests.delete(f"{API}/organizations/{ORG_B}", headers=owner, params={"confirm": "lubwamas"}, timeout=30)
        assert r.status_code == 400  # active org cannot be deleted
        assert _db().organizations.find_one({"id": ORG_B})
