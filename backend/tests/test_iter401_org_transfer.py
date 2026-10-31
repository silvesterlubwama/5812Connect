# iter401: server-to-server organisation transfer (/api/organizations/{id}/transfer-key,
# /api/transfer/*, /api/organizations/pull). The source and the target are the same
# deployment here, which is the harder case: ids collide unless `id` is unique per
# organisation rather than globally.
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
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} missing from {path}")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
db = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]

L_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
OWNER = ("qa-owner-iter401@test.local", "QaOwner@401!")
L_ADMIN = ("admin@lubwamas.org", "Lubwama@2026")
COPY_SLUG = "qa-transfer-copy"


def _login(creds):
    for _ in range(3):
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


def _purge_copy():
    org = db.organizations.find_one({"slug": COPY_SLUG})
    if not org:
        return
    for c in db.list_collection_names():
        db[c].delete_many({"organization_id": org["id"]})
    db.organizations.delete_one({"id": org["id"]})

@pytest.fixture(scope="module")
def otok():
    if not db.users.find_one({"email": OWNER[0]}):
        subprocess.run(
            [sys.executable, "scripts/create_super_admin.py",
             "--email", OWNER[0], "--name", "QA Owner", "--password", OWNER[1]],
            cwd="/app/backend", check=True, capture_output=True,
        )
    tok = _login(OWNER)
    yield tok
    _purge_copy()
    # Scoped to what this suite made: a blanket delete would wipe a real open key.
    owner = db.users.find_one({"email": OWNER[0]}, {"id": 1})
    if owner:
        for g in db.org_transfer_grants.find({"created_by": owner["id"]}, {"id": 1}):
            db.org_transfer_files.delete_many({"grant_id": g["id"]})
        db.org_transfer_grants.delete_many({"created_by": owner["id"]})
        db.org_transfer_jobs.delete_many({"started_by": owner["id"]})
    db.users.delete_many({"email": OWNER[0]})


def _key(otok, org_id=L_ORG):
    r = requests.post(f"{BASE_URL}/api/organizations/{org_id}/transfer-key", headers=_h(otok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- the key ----------
class TestTransferKey:
    def test_only_the_owner_can_mint_one(self, otok):
        ladmin = _login(L_ADMIN)
        r = requests.post(f"{BASE_URL}/api/organizations/{L_ORG}/transfer-key", headers=_h(ladmin), timeout=30)
        assert r.status_code in (401, 403), r.text
        r2 = requests.post(f"{BASE_URL}/api/organizations/{L_ORG}/transfer-key", timeout=30)
        assert r2.status_code in (401, 403)

    def test_key_is_not_stored_in_the_clear(self, otok):
        issued = _key(otok)
        secret = issued["transfer_key"].split(".", 1)[1]
        grant = db.org_transfer_grants.find_one({"id": issued["grant_id"]})
        assert grant and secret not in str(grant), "the secret itself is in the database"
        assert grant["key_hash"] != secret

    def test_unknown_and_malformed_keys_are_refused(self, otok):
        for bad in ("", "nonsense", "abcdef.not-a-real-secret"):
            r = requests.get(f"{BASE_URL}/api/transfer/manifest",
                             headers={"X-Transfer-Key": bad} if bad else {}, timeout=30)
            assert r.status_code == 401, f"{bad!r} -> {r.status_code}"

    def test_revoked_key_stops_working(self, otok):
        issued = _key(otok)
        rd = requests.delete(f"{BASE_URL}/api/organizations/transfer-keys/{issued['grant_id']}",
                             headers=_h(otok), timeout=30)
        assert rd.status_code == 200
        r = requests.get(f"{BASE_URL}/api/transfer/manifest",
                         headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=30)
        assert r.status_code == 401


# ---------- what the key can read ----------
class TestTransferReads:
    def test_manifest_is_one_organisation_only(self, otok):
        issued = _key(otok)
        r = requests.get(f"{BASE_URL}/api/transfer/manifest",
                         headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["format"] == "5812-org-transfer/v1"
        assert d["organization"]["name"] == "Lubwamas"
        # Addresses must not travel: two servers cannot both claim one hostname.
        assert "hostnames" not in d["organization"]
        truth = db.members.count_documents({"organization_id": L_ORG})
        assert d["collection_counts"].get("members", 0) == truth
        assert d["document_count"] > 0
        assert isinstance(d["files"], list)

    def test_rows_are_scoped_and_platform_tables_refused(self, otok):
        key = _key(otok)["transfer_key"]
        h = {"X-Transfer-Key": key}
        r = requests.get(f"{BASE_URL}/api/transfer/rows",
                         params={"collection": "members", "skip": 0, "limit": 100},
                         headers=h, timeout=60)
        assert r.status_code == 200
        rows = r.json()["rows"]
        ids = {x["id"] for x in rows if "id" in x}
        for i in ids:
            assert db.members.find_one({"id": i})["organization_id"] == L_ORG
        for forbidden in ("organizations", "sessions", "org_audit_log"):
            rf = requests.get(f"{BASE_URL}/api/transfer/rows",
                              params={"collection": forbidden, "skip": 0, "limit": 5},
                              headers=h, timeout=30)
            assert rf.status_code == 400, f"{forbidden} -> {rf.status_code}"

    def test_file_path_traversal_refused(self, otok):
        key = _key(otok)["transfer_key"]
        for bad in ("../../etc/passwd", "/etc/passwd"):
            r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": bad},
                             headers={"X-Transfer-Key": key}, timeout=30)
            assert r.status_code in (400, 404), f"{bad} -> {r.status_code}"

    def test_cannot_fetch_another_organisations_file(self, otok):
        # A path belonging to 58:12 Global, named by a key issued for Lubwamas.
        other = db.members.find_one(
            {"organization_id": "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf",
             "photo_url": {"$regex": "/api/(storage|uploads)/"}},
            {"_id": 0, "photo_url": 1},
        )
        if not other:
            pytest.skip("no 58:12 Global file to probe with")
        path = other["photo_url"].split("/api/", 1)[1].split("/", 1)[1]
        issued = _key(otok)
        h = {"X-Transfer-Key": issued["transfer_key"]}
        requests.get(f"{BASE_URL}/api/transfer/manifest", headers=h, timeout=60)
        r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": path}, headers=h, timeout=60)
        assert r.status_code == 404, f"another organisation's file was served ({len(r.content)} bytes)"

    def test_own_file_is_served(self, otok):
        issued = _key(otok)
        h = {"X-Transfer-Key": issued["transfer_key"]}
        files = requests.get(f"{BASE_URL}/api/transfer/manifest", headers=h, timeout=60).json()["files"]
        if not files:
            pytest.skip("Lubwamas has no files")
        r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": files[0]}, headers=h, timeout=60)
        assert r.status_code == 200 and r.content

    def test_file_refused_before_the_manifest_is_asked_for(self, otok):
        issued = _key(otok)
        # no manifest call: nothing is allowed yet
        r = requests.get(f"{BASE_URL}/api/transfer/file", params={"path": "branding/x/logo.png"},
                         headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=30)
        assert r.status_code == 404


# ---------- the pull ----------
class TestPull:
    def test_full_transfer_round_trip(self, otok):
        _purge_copy()
        issued = _key(otok)
        manifest = requests.get(f"{BASE_URL}/api/transfer/manifest",
                                headers={"X-Transfer-Key": issued["transfer_key"]}, timeout=60).json()
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json={
            "source_url": BASE_URL,
            "transfer_key": issued["transfer_key"],
            "name": "QA Transfer Copy",
            "slug": COPY_SLUG,
        })
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        new_org = r.json()["organization_id"]
        state = {}
        for _ in range(60):
            time.sleep(2)
            state = requests.get(f"{BASE_URL}/api/organizations/pull/{job_id}", headers=_h(otok), timeout=30).json()
            if state["status"] != "running":
                break
        assert state["status"] == "done", state
        assert state["problem_count"] == 0, state.get("problems")
        assert state["rows_done"] == manifest["document_count"]
        assert state["files_done"] == len(manifest["files"])

        # the rows really landed, under the NEW organisation
        assert db.members.count_documents({"organization_id": new_org}) == \
            db.members.count_documents({"organization_id": L_ORG})
        # ids are preserved, so references inside the data still line up
        src = db.members.find_one({"organization_id": L_ORG}, {"_id": 0, "id": 1})
        assert db.members.find_one({"organization_id": new_org, "id": src["id"]})
        # branding came with it
        copy_settings = db.system_settings.find_one({"organization_id": new_org})
        src_settings = db.system_settings.find_one({"organization_id": L_ORG})
        if src_settings and src_settings.get("branding"):
            assert copy_settings["branding"].get("app_name") == src_settings["branding"].get("app_name")
        # and the new organisation claims no web address
        org_row = db.organizations.find_one({"id": new_org})
        assert not org_row.get("hostnames") and not org_row.get("is_default")

    def test_key_is_burnt_after_the_pull(self, otok):
        # the previous test consumed its key; a fresh pull with it must fail
        grant = db.org_transfer_grants.find_one({"status": "used"})
        assert grant, "the key was never marked used"

    def test_bad_source_is_reported_not_swallowed(self, otok):
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json={
            "source_url": "not-a-url", "transfer_key": "abc.def", "slug": "qa-bad-source",
        })
        assert r.status_code == 400, r.text
        # 400, not 502: the ingress replaces a 502 body with its own HTML page and
        # the reason never reaches the UI.
        r3 = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=180, json={
            "source_url": "https://example.com", "transfer_key": "abcdef.secret", "slug": "qa-not-connect",
        })
        assert r3.status_code == 400, r3.text
        assert r3.headers.get("content-type", "").startswith("application/json")
        assert r3.json().get("detail")
        r2 = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json={
            "source_url": BASE_URL, "transfer_key": "abcdef.wrong-secret", "slug": "qa-bad-key",
        })
        assert r2.status_code in (401, 403), r2.text
        assert not db.organizations.find_one({"slug": "qa-bad-key"}), "an organisation was created for a refused key"
        for s in ("qa-bad-source", "qa-not-connect"):
            assert not db.organizations.find_one({"slug": s})

    def test_non_owner_cannot_start_a_pull(self, otok):
        ladmin = _login(L_ADMIN)
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(ladmin), timeout=60, json={
            "source_url": BASE_URL, "transfer_key": "abc.def", "slug": "qa-nope",
        })
        assert r.status_code in (401, 403)


class TestOverwrite:
    """Pulling the same organisation again, over the copy already here."""

    def _pull(self, otok, **extra):
        issued = _key(otok)
        body = {"source_url": BASE_URL, "transfer_key": issued["transfer_key"], **extra}
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(otok), timeout=120, json=body)
        return r

    def _wait(self, otok, job_id):
        for _ in range(60):
            time.sleep(2)
            s = requests.get(f"{BASE_URL}/api/organizations/pull/{job_id}", headers=_h(otok), timeout=30).json()
            if s["status"] != "running":
                return s
        return s

    def test_same_web_name_is_refused_with_a_way_out(self, otok):
        _purge_copy()
        first = self._pull(otok, name="QA Transfer Copy", slug=COPY_SLUG)
        assert first.status_code == 200, first.text
        assert self._wait(otok, first.json()["job_id"])["status"] == "done"
        again = self._pull(otok, slug=COPY_SLUG)
        assert again.status_code == 409
        assert "overwrite" in again.json()["detail"].lower(), again.text

    def test_overwrite_needs_confirming(self, otok):
        org = db.organizations.find_one({"slug": COPY_SLUG})
        assert org, "the first pull did not land"
        r = self._pull(otok, target_org_id=org["id"])
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower()

    def test_unknown_target_is_refused(self, otok):
        r = self._pull(otok, target_org_id="no-such-organisation", overwrite=True)
        assert r.status_code == 404

    def test_overwrite_replaces_data_but_keeps_the_address(self, otok):
        org = db.organizations.find_one({"slug": COPY_SLUG})
        oid = org["id"]
        # something stale that must not survive, and an address that must
        db.members.insert_one({"id": "QA-STALE-OVERWRITE", "organization_id": oid, "name": "Stale"})
        db.organizations.update_one({"id": oid}, {"$set": {"hostnames": ["qa-overwrite.example.org"]}})
        before = db.members.count_documents({"organization_id": oid})
        source_before = db.members.count_documents({"organization_id": L_ORG})

        r = self._pull(otok, target_org_id=oid, overwrite=True)
        assert r.status_code == 200, r.text
        assert r.json()["organization_id"] == oid, "an overwrite created a second organisation"
        state = self._wait(otok, r.json()["job_id"])
        assert state["status"] == "done", state
        assert state["cleared"] >= before, state
        assert state["problem_count"] == 0, state.get("problems")

        assert db.members.find_one({"id": "QA-STALE-OVERWRITE"}) is None, "stale row survived the overwrite"
        assert db.members.count_documents({"organization_id": oid}) == source_before, "rows duplicated"
        row = db.organizations.find_one({"id": oid})
        assert row["hostnames"] == ["qa-overwrite.example.org"], "the address was taken from the source"
        assert row["slug"] == COPY_SLUG
        assert row["status"] == "active"
        # and the organisation it came from is untouched
        assert db.members.count_documents({"organization_id": L_ORG}) == source_before

    def test_overwrite_cannot_be_started_by_a_non_owner(self, otok):
        org = db.organizations.find_one({"slug": COPY_SLUG})
        ladmin = _login(L_ADMIN)
        r = requests.post(f"{BASE_URL}/api/organizations/pull", headers=_h(ladmin), timeout=60, json={
            "source_url": BASE_URL, "transfer_key": "abc.def",
            "target_org_id": org["id"], "overwrite": True,
        })
        assert r.status_code in (401, 403)
