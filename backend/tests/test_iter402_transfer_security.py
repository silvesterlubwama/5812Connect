# iter402: adversarial checks on the server-to-server organisation transfer —
# key lifecycle, cross-tenant reads via a key, pull failure modes, and tenant
# isolation after a same-deployment pull. Cleans up ONLY what it creates.
import os
import subprocess
import sys
import time

import pytest
import requests
from pymongo import MongoClient


def _env(path, key):
    with open(path) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"{key} missing from {path}")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
db = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]

L_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
G_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
OWNER = ("qa-owner-iter401@test.local", "QaOwner@401!")
L_ADMIN = ("admin@lubwamas.org", "Lubwama@2026")
G_ADMIN = ("admin@5812global.org", "Admin@1234")
COPY_SLUG = "qa-iter402-copy"
CREATED = {"grants": set(), "orgs": set()}
PROTECTED = {"admin@5812global.org", "admin@lubwamas.org", "silvesterlubwama@icloud.com"}


def _login(creds):
    for _ in range(4):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"identifier": creds[0], "password": creds[1]}, timeout=30)
        if r.status_code == 429:
            time.sleep(20)
            continue
        assert r.status_code == 200, r.text
        return r.json()["token"]
    pytest.skip("login rate limited")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _purge_org(org_id):
    assert org_id not in (L_ORG, G_ORG)
    for c in db.list_collection_names():
        if c == "users":
            # never touch protected real accounts' ORIGINAL rows; copy rows are keyed by org id
            db[c].delete_many({"organization_id": org_id})
        else:
            db[c].delete_many({"organization_id": org_id})
    db.organizations.delete_one({"id": org_id})


@pytest.fixture(scope="module")
def otok():
    created_owner = False
    if not db.users.find_one({"email": OWNER[0]}):
        subprocess.run([sys.executable, "scripts/create_super_admin.py", "--email", OWNER[0],
                        "--name", "QA Owner", "--password", OWNER[1]],
                       cwd="/app/backend", check=True, capture_output=True)
        created_owner = True
    tok = _login(OWNER)
    yield tok
    org = db.organizations.find_one({"slug": COPY_SLUG})
    if org:
        CREATED["orgs"].add(org["id"])
    for oid in CREATED["orgs"]:
        _purge_org(oid)
        db.org_transfer_jobs.delete_many({"organization_id": oid})
    for gid in CREATED["grants"]:
        db.org_transfer_grants.delete_one({"id": gid})
    if created_owner:
        db.users.delete_one({"email": OWNER[0]})


def _key(otok, org_id=L_ORG):
    r = requests.post(f"{BASE_URL}/api/organizations/{org_id}/transfer-key", headers=_h(otok), timeout=30)
    assert r.status_code == 200, r.text
    CREATED["grants"].add(r.json()["grant_id"])
    return r.json()


def _counts(org_id):
    out = {}
    for c in db.list_collection_names():
        if c in ("org_transfer_grants", "org_transfer_jobs", "org_audit_log"):
            continue
        n = db[c].count_documents({"organization_id": org_id})
        if n:
            out[c] = n
    return out


# ---------- who may manage keys ----------
class TestKeyAccess:
    def test_list_and_revoke_refused_for_admin_and_anon(self, otok):
        issued = _key(otok)
        ladmin = _login(L_ADMIN)
        for hdrs in ({}, _h(ladmin)):
            r = requests.get(f"{BASE_URL}/api/organizations/{L_ORG}/transfer-keys", headers=hdrs, timeout=30)
            assert r.status_code in (401, 403), r.text
            r = requests.delete(f"{BASE_URL}/api/organizations/transfer-keys/{issued['grant_id']}", headers=hdrs, timeout=30)
            assert r.status_code in (401, 403), r.text
            r = requests.get(f"{BASE_URL}/api/organizations/pulls", headers=hdrs, timeout=30)
            assert r.status_code in (401, 403), r.text
        # owner list shows it, without the hash
        r = requests.get(f"{BASE_URL}/api/organizations/{L_ORG}/transfer-keys", headers=_h(otok), timeout=30)
        assert r.status_code == 200
        keys = r.json()["keys"]
        assert any(k["id"] == issued["grant_id"] for k in keys)
        assert all("key_hash" not in k for k in keys)

    def test_unknown_org_404(self, otok):
        r = requests.post(f"{BASE_URL}/api/organizations/does-not-exist/transfer-key", headers=_h(otok), timeout=30)
        assert r.status_code == 404


# ---------- what one key can reach ----------
class TestKeyScope:
    def test_forged_secret_on_real_grant_refused(self, otok):
        issued = _key(otok)
        forged = issued["grant_id"] + ".AAAAforgedsecretAAAA"
        r = requests.get(f"{BASE_URL}/api/transfer/manifest", headers={"X-Transfer-Key": forged}, timeout=30)
        assert r.status_code == 401

    def test_expired_key_refused(self, otok):
        issued = _key(otok)
        db.org_transfer_grants.update_one({"id": issued["grant_id"]}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}})
        r = requests.get(f"{BASE_URL}/api/transfer/manifest", headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=30)
        assert r.status_code in (401, 403), r.status_code
        print("expired key status:", r.status_code)

    def test_more_platform_collections_refused(self, otok):
        h = {"X-Transfer-Key": _key(otok)["transfer_key"]}
        for c in ("org_transfer_grants", "org_transfer_jobs", "password_reset_tokens", "login_attempts",
                  "counters", "app_config", "system.users"):
            r = requests.get(f"{BASE_URL}/api/transfer/rows", params={"collection": c}, headers=h, timeout=30)
            assert r.status_code == 400, f"{c} -> {r.status_code}"

    def test_rows_never_include_other_org(self, otok):
        h = {"X-Transfer-Key": _key(otok)["transfer_key"]}
        g_ids = {d["id"] for d in db.members.find({"organization_id": G_ORG}, {"id": 1}).limit(5000) if "id" in d}
        r = requests.get(f"{BASE_URL}/api/transfer/rows", params={"collection": "members", "limit": 5000}, headers=h, timeout=60)
        assert r.status_code == 200
        l_ids = {d["id"] for d in db.members.find({"organization_id": L_ORG}, {"id": 1})}
        got = {x.get("id") for x in r.json()["rows"]}
        assert got <= l_ids
        assert len(got) == len(l_ids)

    def test_file_of_another_org_refused(self, otok):
        """A Lubwamas key must not read a 58:12 Global file by guessing its path."""
        h = {"X-Transfer-Key": _key(otok)["transfer_key"]}
        from_manifest = set(requests.get(f"{BASE_URL}/api/transfer/manifest", headers=h, timeout=60).json()["files"])
        sys.path.insert(0, "/app/backend")
        from routers.backup import _walk_file_paths
        seen, paths = set(), []
        for d in db.members.find({"organization_id": G_ORG}, {"_id": 0}).limit(300):
            _walk_file_paths(d, seen, paths)
        foreign = [p for p in paths if p not in from_manifest]
        assert foreign, "no 58:12 file path found to probe with"
        r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": foreign[0]}, headers=h, timeout=60)
        print("foreign file probe:", foreign[0], r.status_code, len(r.content))
        assert r.status_code in (400, 403, 404), \
            f"Lubwamas key served a 58:12 Global file ({foreign[0]}, {len(r.content)} bytes)"

    def test_encoded_traversal_refused(self, otok):
        h = {"X-Transfer-Key": _key(otok)["transfer_key"]}
        for bad in ("profile-photos/../../etc/passwd", "%2e%2e/%2e%2e/etc/passwd", "....//etc/passwd"):
            r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": bad}, headers=h, timeout=30)
            assert r.status_code in (400, 404), f"{bad} -> {r.status_code}"


# ---------- pull failure modes leave nothing behind ----------
class TestPullFailures:
    def test_taken_slug_409_and_nothing_created(self, otok):
        issued = _key(otok)
        orgs_before = db.organizations.count_documents({})
        jobs_before = db.org_transfer_jobs.count_documents({})
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json={
            "source_url": BASE_URL, "transfer_key": issued["transfer_key"], "slug": "lubwamas"})
        assert r.status_code == 409, r.text
        detail = r.json()["detail"].lower()
        assert "lubwamas" in detail and "overwrite" in detail, r.text
        assert db.organizations.count_documents({}) == orgs_before
        assert db.org_transfer_jobs.count_documents({}) == jobs_before
        # key not burnt by a refused pull
        assert db.org_transfer_grants.find_one({"id": issued["grant_id"]})["status"] == "open"

    def test_unreachable_and_non_server_address(self, otok):
        orgs_before = db.organizations.count_documents({})
        for url in ("https://no-such-host-iter402.invalid", "https://example.com"):
            r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=150, json={
                "source_url": url, "transfer_key": "abc.def", "slug": "qa-iter402-bad"})
            print("bad source:", url, r.status_code, r.headers.get("content-type"), r.text[:200])
            assert r.status_code in (400, 502), f"{url} -> {r.status_code} {r.text}"
            assert "json" in r.headers.get("content-type", ""), f"{url}: non-JSON error body"
            assert r.json().get("detail")
        assert db.organizations.count_documents({}) == orgs_before

    def test_pull_status_refused_for_admin(self, otok):
        ladmin = _login(L_ADMIN)
        r = requests.get(f"{BASE_URL}/api/organizations/pull/anything", headers=_h(ladmin), timeout=30)
        assert r.status_code in (401, 403)
        r = requests.get(f"{BASE_URL}/api/organizations/pull/nope", headers=_h(otok), timeout=30)
        assert r.status_code == 404


# ---------- full pull + isolation afterwards ----------
class TestPullIsolation:
    def test_pull_then_isolation(self, otok):
        src_before = _counts(L_ORG)
        g_before = _counts(G_ORG)
        issued = _key(otok)
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json={
            "source_url": BASE_URL + "/", "transfer_key": issued["transfer_key"],
            "name": "QA iter402 Copy", "slug": COPY_SLUG})
        assert r.status_code == 200, r.text
        job, new_org = r.json()["job_id"], r.json()["organization_id"]
        CREATED["orgs"].add(new_org)
        st = {}
        for _ in range(90):
            time.sleep(2)
            st = requests.get(f"{BASE_URL}/api/organizations/pull/{job}", headers=_h(otok), timeout=30).json()
            if st["status"] != "running":
                break
        assert st["status"] == "done", st
        assert st["problem_count"] == 0, st.get("problems")
        assert st["files_done"] == st["files_total"]

        # key burnt -> reuse is 403
        rr = requests.get(f"{BASE_URL}/api/transfer/manifest", headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=30)
        assert rr.status_code == 403, rr.status_code

        # copy matches source per collection; source and 58:12 untouched
        copy = _counts(new_org)
        assert _counts(L_ORG) == src_before
        assert _counts(G_ORG) == g_before
        diff = {c: (src_before.get(c), copy.get(c)) for c in set(src_before) | set(copy)
                if src_before.get(c) != copy.get(c)}
        assert not diff, f"per-collection mismatch: {diff}"

        org_row = db.organizations.find_one({"id": new_org})
        assert not org_row.get("hostnames") and not org_row.get("is_default")
        assert org_row["slug"] == COPY_SLUG and org_row["name"] == "QA iter402 Copy"

        # the real Lubwamas admin still lands in the REAL Lubwamas
        ltok = _login(L_ADMIN)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(ltok), timeout=30).json()
        print("lubwamas admin org after pull:", me.get("organization_id"))
        assert me.get("organization_id") == L_ORG, f"real admin now signs into {me.get('organization_id')}"

        # 58:12 admin cannot see the copy's members
        gtok = _login(G_ADMIN)
        rm = requests.get(f"{BASE_URL}/api/members", headers={**_h(gtok), "X-Organization-Id": new_org},
                          params={"limit": 500}, timeout=60)
        if rm.status_code == 200:
            body = rm.json()
            items = body if isinstance(body, list) else body.get("members") or body.get("items") or []
            copy_ids = {d["id"] for d in db.members.find({"organization_id": new_org}, {"id": 1})}
            g_ids = {d["id"] for d in db.members.find({"organization_id": G_ORG}, {"id": 1})}
            leaked = {m.get("id") for m in items} & (copy_ids - g_ids)
            assert not leaked, f"58:12 admin sees {len(leaked)} copied members"
