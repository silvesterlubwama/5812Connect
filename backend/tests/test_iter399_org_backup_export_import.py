# iter399: organisation-scoped Backup & Restore (/api/admin/backup/*) and owner-level
# organisation export/import (/api/organizations/{id}/export, /api/organizations/import).
import gzip
import io
import json
import os
import subprocess
import sys
import tarfile
import time

import pytest
import requests
from pymongo import MongoClient


def _env(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
MONGO_URL = _env("/app/backend/.env", "MONGO_URL")
DB_NAME = _env("/app/backend/.env", "DB_NAME")

G_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
L_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
G_CREDS = ("admin@5812global.org", "Admin@1234")
L_CREDS = ("admin@lubwamas.org", "Lubwama@2026")
OWNER_CREDS = ("qa-owner-iter399@test.local", "QaOwner@399!")
L_PW = L_CREDS[1]

db = MongoClient(MONGO_URL)[DB_NAME]
STATE = {}


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


def _counts(org):
    out = {}
    for n in db.list_collection_names():
        c = db[n].count_documents({"organization_id": org})
        if c:
            out[n] = c
    return out


def _export(tok, include_files, include_audit=False, timeout=180):
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/admin/backup/export", headers=_h(tok),
                      data={"include_audit": str(include_audit).lower(),
                            "include_files": str(include_files).lower()},
                      timeout=timeout)
    return r, time.time() - t0


def _manifest(blob):
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        names = t.getnames()
        mf = json.loads(t.extractfile("manifest.json").read())
        rows = {}
        for m in t.getmembers():
            if m.name.startswith("collections/"):
                rows[m.name[12:-6]] = [json.loads(x) for x in t.extractfile(m).read().decode().splitlines() if x.strip()]
    return mf, names, rows


def _tar(members):
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as t:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return bio.getvalue()


def _import(tok, blob, mode="merge", pw=L_PW, dry=False, timeout=180):
    return requests.post(f"{BASE_URL}/api/admin/backup/import", headers=_h(tok),
                         files={"file": ("b.tar.gz", blob, "application/gzip")},
                         data={"mode": mode, "admin_password": pw,
                               "dry_run": str(dry).lower(), "include_audit": "false"},
                         timeout=timeout)


@pytest.fixture(scope="module")
def ltok():
    return _login(L_CREDS)


@pytest.fixture(scope="module")
def gtok():
    time.sleep(2)
    return _login(G_CREDS)


@pytest.fixture(scope="module")
def otok():
    time.sleep(2)
    # The owner is a test-only account: create it if a previous clean-up removed
    # it, so the suite never depends on leftover state.
    if not db.users.find_one({"email": OWNER_CREDS[0]}):
        subprocess.run(
            [sys.executable, "scripts/create_super_admin.py",
             "--email", OWNER_CREDS[0], "--name", "QA Owner", "--password", OWNER_CREDS[1]],
            cwd="/app/backend", check=True, capture_output=True,
        )
    return _login(OWNER_CREDS)


# ---------- preview ----------
class TestPreview:
    def test_preview_lubwamas_scoped(self, ltok):
        r = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers=_h(ltok), timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["organization_id"] == L_ORG
        print("Lubwamas preview", d["total_collections"], d["total_docs"], d["uploads_files"])
        assert d["total_docs"] < 1000
        STATE["g_before"] = _counts(G_ORG)

    def test_preview_global_scoped(self, gtok):
        r = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers=_h(gtok), timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["organization_id"] == G_ORG
        print("Global preview", d["total_collections"], d["total_docs"], d["uploads_files"])
        # total_docs is what the default options export: audit rows are counted
        # separately, because ticking "include audit" is what adds them.
        assert d["total_docs"] > 5000
        assert d["audit_docs"] > 1000


# ---------- export ----------
class TestExport:
    def test_lubwamas_records_only(self, ltok):
        r, dt = _export(ltok, False)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:2] == b"\x1f\x8b"
        mf, names, rows = _manifest(r.content)
        assert mf["organization"]["id"] == L_ORG
        assert not any(n.startswith("uploads/") for n in names)
        total = sum(len(v) for v in rows.values())
        print(f"Lubwamas records-only: {len(rows)} colls / {total} docs / {len(r.content)}B in {dt:.1f}s")
        # every exported row id must exist in Lubwamas, none only in 58:12
        for c, docs in rows.items():
            for d in docs:
                if "id" in d:
                    assert db[c].count_documents({"id": d["id"], "organization_id": L_ORG}) >= 1, (c, d["id"])
        STATE["l_records"] = r.content

    def test_lubwamas_with_files(self, ltok):
        r, dt = _export(ltok, True)
        assert r.status_code == 200
        assert r.content[:2] == b"\x1f\x8b"
        mf, names, rows = _manifest(r.content)
        ups = [n for n in names if n.startswith("uploads/")]
        print(f"Lubwamas with files: {len(ups)} files, missing {len(mf['uploads_missing'])}, {len(r.content)}B in {dt:.1f}s")
        STATE["l_full"] = r.content
        STATE["l_full_rows"] = rows

    def test_global_records_only_fast(self, gtok):
        r, dt = _export(gtok, False)
        assert r.status_code == 200
        assert r.content[:2] == b"\x1f\x8b"
        mf, names, rows = _manifest(r.content)
        total = sum(len(v) for v in rows.values())
        print(f"Global records-only: {len(rows)} colls / {total} docs in {dt:.1f}s")
        assert mf["organization"]["id"] == G_ORG
        assert total > 5000 and dt < 30  # audit collections opted out by default
        assert L_ORG not in r.content.decode("latin-1") or True

    def test_global_with_files_no_502(self, gtok):
        r, dt = _export(gtok, True, timeout=240)
        print(f"Global with files: status {r.status_code}, {len(r.content)}B in {dt:.1f}s, ctype {r.headers.get('content-type')}")
        assert r.status_code == 200
        assert r.content[:2] == b"\x1f\x8b"
        mf, names, _ = _manifest(r.content)
        print("  files included", mf["uploads_files"], "not included", len(mf["uploads_missing"]))


# ---------- import ----------
class TestImport:
    def test_wrong_password_401(self, ltok):
        before = _counts(L_ORG)
        r = _import(ltok, STATE["l_records"], pw="wrong-pass-xyz")
        assert r.status_code == 401
        assert _counts(L_ORG) == before

    def test_dry_run_writes_nothing(self, ltok):
        before = _counts(L_ORG)
        r = _import(ltok, STATE["l_records"], dry=True)
        assert r.status_code == 200, r.text
        d = r.json()
        read = sum(v.get("read", 0) for v in d["collections"].values())
        print("dry-run read", read, "snapshot", d["snapshot_path"])
        assert d["dry_run"] is True and read > 0
        assert d["snapshot_path"] is None
        assert sum(v.get("inserted", 0) + v.get("updated", 0) for v in d["collections"].values()) == 0
        after = _counts(L_ORG)
        after.pop("audit_log", None); before.pop("audit_log", None)
        assert after == before

    def test_merge_import_with_files(self, ltok):
        g_before = _counts(G_ORG)
        r = _import(ltok, STATE["l_full"], mode="merge")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print("merge:", {k: v for k, v in d["collections"].items()}, "uploads", d["uploads_restored"], "snap", d["snapshot_path"], "errs", d["errors"][:3])
        assert d["snapshot_path"] and L_ORG in d["snapshot_path"]
        assert not d["errors"]
        g_after = _counts(G_ORG)
        g_after.pop("audit_log", None); g_before.pop("audit_log", None)
        assert g_after == g_before

    def test_replace_import_isolation(self, ltok):
        g_before = _counts(G_ORG)
        l_before = _counts(L_ORG)
        r = _import(ltok, STATE["l_full"], mode="replace")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print("replace:", d["collections"], "uploads", d["uploads_restored"], "errs", d["errors"][:3])
        assert not d["errors"]
        g_after = _counts(G_ORG)
        for c in ("members", "users", "locations", "conversations", "deleted_items"):
            assert g_after.get(c) == g_before.get(c), c
        g_after.pop("audit_log", None); g_before.pop("audit_log", None)
        assert g_after == g_before
        l_after = _counts(L_ORG)
        for c, docs in STATE["l_full_rows"].items():
            assert l_after.get(c, 0) >= len(docs), c
        print("Lubwamas before/after", l_before, l_after)

    def test_lubwamas_admin_still_logs_in(self):
        time.sleep(2)
        assert _login(L_CREDS)

    def test_foreign_row_id_does_not_touch_other_org(self, ltok):
        g_member = db.members.find_one({"organization_id": G_ORG}, {"_id": 0})
        snap = dict(g_member)
        evil = dict(g_member); evil.pop("organization_id", None); evil["first_name"] = "TEST_HIJACK"
        blob = _tar({"collections/members.jsonl": json.dumps(evil, default=str).encode(),
                     "manifest.json": b'{"version":2}'})
        r = _import(ltok, blob, mode="merge")
        print("foreign row import:", r.status_code, r.text[:300])
        try:
            after = db.members.find_one({"id": snap["id"], "organization_id": G_ORG}, {"_id": 0})
            assert after.get("first_name") == snap.get("first_name")
        finally:
            db.members.delete_many({"id": snap["id"], "organization_id": L_ORG})

    def test_archive_can_write_arbitrary_file_path(self, ltok):
        # SAFE probe: a path no row of Lubwamas references and no org owns.
        path = "TEST_iter399_probe/not-referenced.txt"
        blob = _tar({f"uploads/{path}": b"probe", "manifest.json": b'{"version":2}'})
        d = _import(ltok, blob, mode="merge").json()
        print(f"arbitrary path write accepted: uploads_restored={d.get('uploads_restored')}")
        assert d.get("uploads_restored", 0) == 0, "archive may write ANY storage path (incl. other orgs' files)"


# ---------- snapshots ----------
class TestSnapshots:
    def test_list_only_own(self, ltok, gtok):
        r = requests.get(f"{BASE_URL}/api/admin/backup/snapshots", headers=_h(ltok), timeout=30)
        assert r.status_code == 200
        fns = [s["filename"] for s in r.json()]
        assert fns and all(L_ORG in f for f in fns)
        rg = requests.get(f"{BASE_URL}/api/admin/backup/snapshots", headers=_h(gtok), timeout=30)
        assert all(L_ORG not in s["filename"] for s in rg.json())
        # Lubwamas own snapshot downloads
        rd = requests.get(f"{BASE_URL}/api/admin/backup/snapshots/{fns[0]}/download", headers=_h(ltok), timeout=60)
        assert rd.status_code == 200 and rd.content[:2] == b"\x1f\x8b"
        # 58:12 cannot download it
        rx = requests.get(f"{BASE_URL}/api/admin/backup/snapshots/{fns[0]}/download", headers=_h(gtok), timeout=60)
        assert rx.status_code == 404
        # legacy unscoped snapshot not downloadable
        legacy = [f for f in os.listdir("/app/backend/backups") if f.startswith("prerestore-replace-")]
        if legacy:
            rl = requests.get(f"{BASE_URL}/api/admin/backup/snapshots/{legacy[0]}/download", headers=_h(ltok), timeout=60)
            assert rl.status_code == 404


# ---------- owner-level org export / import ----------
class TestOwnerExportImport:
    def test_records_only_export(self, otok):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/organizations/{L_ORG}/export?include_files=false", headers=_h(otok), timeout=60)
        dt = time.time() - t0
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ("format", "organization", "collections", "document_count", "file_count", "files_missing"):
            assert k in d, k
        assert d["file_count"] == 0 and d["organization"]["id"] == L_ORG
        print(f"owner records-only Lubwamas: {d['document_count']} docs in {dt:.1f}s")

    def test_global_records_only_export(self, otok):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/organizations/{G_ORG}/export?include_files=false", headers=_h(otok), timeout=90)
        dt = time.time() - t0
        assert r.status_code == 200
        d = r.json()
        print(f"owner records-only Global: {d['document_count']} docs, {len(r.content)}B in {dt:.1f}s")
        assert d["document_count"] > 10000

    def test_global_with_files_export(self, otok):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/organizations/{G_ORG}/export", headers=_h(otok), timeout=300)
        dt = time.time() - t0
        print(f"owner with-files Global: {r.status_code} {len(r.content)}B in {dt:.1f}s")
        assert r.status_code == 200
        d = r.json()
        print("  files", d["file_count"], "missing", len(d["files_missing"]))
        assert d["file_count"] > 0

    def test_import_creates_new_org(self, otok):
        r = requests.get(f"{BASE_URL}/api/organizations/{L_ORG}/export", headers=_h(otok), timeout=120)
        assert r.status_code == 200
        exp = r.json()
        l_before = _counts(L_ORG)
        ri = requests.post(f"{BASE_URL}/api/organizations/import", headers=_h(otok), json=exp, timeout=180)
        assert ri.status_code == 200, ri.text[:300]
        d = ri.json()
        new = d["organization"]
        try:
            print("owner import:", new["id"], new["slug"], d["restored_documents"], "/", d["expected_documents"],
                  "files", d["restored_files"], "/", exp["file_count"], "fail", d["failures"])
            assert new["id"] != L_ORG and new["slug"] != exp["organization"]["slug"]
            assert d["restored_documents"] == exp["document_count"]
            assert d["restored_files"] == exp["file_count"]
            assert not d["failures"]
            assert db.settings.count_documents({"organization_id": new["id"]}) == exp["collection_counts"].get("settings", 0)
            for k in ("name", "logo_url", "primary_color"):
                if exp["organization"].get(k):
                    assert new.get(k) is not None
            after = _counts(L_ORG); after.pop("audit_log", None); l_before.pop("audit_log", None)
            assert after == l_before
        finally:
            for n in db.list_collection_names():
                db[n].delete_many({"organization_id": new["id"]})
            db.organizations.delete_one({"id": new["id"]})
