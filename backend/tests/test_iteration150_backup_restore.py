"""Iteration 150 — Backup & Restore (admin only)

Covers:
- GET /api/admin/backup/preview (admin only; 403 for non-admin)
- POST /api/admin/backup/export (admin only; .tar.gz with manifest + collections + uploads)
- POST /api/admin/backup/import (password gate, dry-run, merge, replace, error cases)
- GET /api/admin/backup/snapshots, GET /snapshots/{f}/download
"""
import io
import os
import json
import tarfile
import time
import uuid
import requests
import pytest

def _load_backend_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.strip().startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    if not u:
        raise RuntimeError("REACT_APP_BACKEND_URL not configured")
    return u.rstrip("/")

BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
NEW_USER_PASS = "Test@5812!"


def _login(identifier, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": identifier, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASS)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def staff_headers(admin_headers):
    """Create a non-admin user via /api/auth/register and login."""
    email = f"test_iter150_nonadmin_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Iter150 NonAdmin", "email": email, "password": NEW_USER_PASS,
    }, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"Cannot register non-admin user ({r.status_code} {r.text[:120]})")
    j = r.json()
    token = j.get("token") or j.get("access_token")
    user_id = (j.get("user") or {}).get("id")
    if not token:
        pytest.skip("register returned no token")
    yield {"Authorization": f"Bearer {token}", "_email": email, "_id": user_id}
    # teardown
    try:
        if user_id:
            requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=admin_headers, timeout=15)
    except Exception:
        pass


# ----- preview ---------------------------------------------------------------
class TestPreview:
    def test_preview_admin_ok(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        for k in ("collections", "total_collections", "total_docs", "uploads_files", "uploads_bytes", "version", "now"):
            assert k in data, f"missing field {k}"
        assert isinstance(data["collections"], list)
        assert data["version"] == 1
        # Excluded sentinel collections should NOT be present.
        names = {c["collection"] for c in data["collections"]}
        for forbidden in ("sessions", "push_subscriptions", "notifications", "security_pair_attempts", "fingerprint_data"):
            assert forbidden not in names, f"{forbidden} must be excluded by _NEVER_BACKUP"
        # fs.* must not appear
        assert not any(n.startswith("fs.") for n in names), "fs.* must be excluded"

    def test_preview_non_admin_forbidden(self, staff_headers):
        r = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers={"Authorization": staff_headers["Authorization"]}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:150]}"


# ----- export ---------------------------------------------------------------
class TestExport:
    def test_export_returns_tarball(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/admin/backup/export",
                          data={"include_audit": "false"}, headers=admin_headers, timeout=180)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "gzip" in ct, f"unexpected content-type: {ct}"
        body = r.content
        assert len(body) > 100, "export body too small"
        # Validate tarball + manifest shape
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
            names = tar.getnames()
            assert "manifest.json" in names
            mf = tar.extractfile("manifest.json")
            manifest = json.loads(mf.read())
            assert manifest["version"] == 1
            for k in ("exported_at", "exported_by_id", "exported_by_name", "include_audit",
                      "source_db", "collections", "uploads_files", "uploads_bytes"):
                assert k in manifest, f"manifest missing {k}"
            # At least one collections/<n>.jsonl
            jsonl = [n for n in names if n.startswith("collections/") and n.endswith(".jsonl")]
            assert len(jsonl) > 0
            # Sentinel exclusions
            for forbidden in ("sessions", "push_subscriptions", "notifications"):
                assert f"collections/{forbidden}.jsonl" not in names, f"{forbidden} must NOT be exported"
        # stash for the next class
        TestExport._cached = body

    def test_export_non_admin_forbidden(self, staff_headers):
        r = requests.post(f"{BASE_URL}/api/admin/backup/export",
                          data={"include_audit": "false"},
                          headers={"Authorization": staff_headers["Authorization"]}, timeout=30)
        assert r.status_code == 403


# ----- import: validation gates --------------------------------------------
class TestImportGates:
    @classmethod
    def _get_backup_blob(cls, admin_headers):
        if getattr(TestExport, "_cached", None):
            return TestExport._cached
        r = requests.post(f"{BASE_URL}/api/admin/backup/export",
                          data={"include_audit": "false"}, headers=admin_headers, timeout=180)
        assert r.status_code == 200
        return r.content

    def test_import_missing_password_422(self, admin_headers):
        blob = self._get_backup_blob(admin_headers)
        files = {"file": ("b.tar.gz", blob, "application/gzip")}
        # no admin_password field
        data = {"mode": "merge", "dry_run": "true", "include_audit": "false"}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=120)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_import_wrong_password_401(self, admin_headers):
        blob = self._get_backup_blob(admin_headers)
        files = {"file": ("b.tar.gz", blob, "application/gzip")}
        data = {"mode": "merge", "dry_run": "true", "include_audit": "false",
                "admin_password": "definitely_wrong_password"}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=120)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_import_corrupted_file_400(self, admin_headers):
        files = {"file": ("bad.tar.gz", b"not-a-real-tarball-just-some-bytes", "application/gzip")}
        data = {"mode": "merge", "dry_run": "false", "include_audit": "false", "admin_password": ADMIN_PASS}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=60)
        assert r.status_code == 400

    def test_import_future_version_400(self, admin_headers):
        """Rebuild the tarball with manifest.version = 999 to force the 'newer' rejection path."""
        blob = self._get_backup_blob(admin_headers)
        out = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as src, \
                tarfile.open(fileobj=out, mode="w:gz") as dst:
            for m in src.getmembers():
                if m.name == "manifest.json":
                    mf = src.extractfile(m)
                    mj = json.loads(mf.read())
                    mj["version"] = 999
                    nb = json.dumps(mj).encode()
                    ni = tarfile.TarInfo(name="manifest.json"); ni.size = len(nb)
                    dst.addfile(ni, io.BytesIO(nb))
                else:
                    f = src.extractfile(m)
                    if f is None:
                        dst.addfile(m)
                    else:
                        dst.addfile(m, f)
        files = {"file": ("future.tar.gz", out.getvalue(), "application/gzip")}
        data = {"mode": "merge", "dry_run": "true", "include_audit": "false", "admin_password": ADMIN_PASS}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=120)
        assert r.status_code == 400, f"expected 400 for future version, got {r.status_code}: {r.text[:200]}"


# ----- import: behavior (dry-run, merge) -----------------------------------
class TestImportBehavior:
    def test_dry_run_does_not_write(self, admin_headers):
        # preview before
        before = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers=admin_headers, timeout=30).json()
        before_docs = before["total_docs"]
        # export then dry-run-import
        blob = TestImportGates._get_backup_blob(admin_headers)
        files = {"file": ("b.tar.gz", blob, "application/gzip")}
        data = {"mode": "merge", "dry_run": "true", "include_audit": "false", "admin_password": ADMIN_PASS}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=180)
        assert r.status_code == 200, r.text[:200]
        report = r.json()
        assert report["dry_run"] is True
        # Snapshot path is None for dry-run.
        assert report.get("snapshot_path") in (None, ""), f"dry-run should not create snapshot, got {report.get('snapshot_path')}"
        # docs total should not grow
        after = requests.get(f"{BASE_URL}/api/admin/backup/preview", headers=admin_headers, timeout=30).json()
        # allow small audit/log natural growth between two requests (<= 100 docs)
        assert after["total_docs"] - before_docs <= 100, f"dry-run wrote data: before={before_docs}, after={after['total_docs']}"

    def test_merge_import_round_trip(self, admin_headers):
        blob = TestImportGates._get_backup_blob(admin_headers)
        files = {"file": ("b.tar.gz", blob, "application/gzip")}
        data = {"mode": "merge", "dry_run": "false", "include_audit": "false", "admin_password": ADMIN_PASS}
        r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                          headers=admin_headers, timeout=600)
        assert r.status_code == 200, r.text[:200]
        report = r.json()
        assert report["dry_run"] is False
        assert report["mode"] == "merge"
        assert "collections" in report and isinstance(report["collections"], dict)
        # Aggregate totals
        agg = {"read": 0, "inserted": 0, "updated": 0, "errors": 0}
        for v in report["collections"].values():
            if isinstance(v, dict):
                for k in agg:
                    agg[k] += v.get(k, 0) or 0
        assert agg["read"] > 0, "expected non-zero docs read"
        # On a same-instance round trip after iter150 fix:
        # errors should be 0 and updated should dominate.
        assert agg["errors"] == 0, f"unexpected errors: first 5 = {report.get('errors', [])[:5]}"
        assert agg["updated"] > agg["inserted"], f"updated({agg['updated']}) should dominate inserted({agg['inserted']})"
        # Snapshot path must be created (non-dry-run)
        assert report.get("snapshot_path"), "snapshot_path should be set after a real import"


# ----- snapshots -----------------------------------------------------------
class TestSnapshots:
    def test_list_snapshots(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/backup/snapshots", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # After the merge round-trip we expect at least one snapshot
        assert len(items) > 0, "expected at least one auto-saved pre-restore snapshot"
        for it in items:
            for k in ("filename", "size_bytes", "modified_at"):
                assert k in it
        TestSnapshots._latest = items[0]["filename"]

    def test_download_snapshot(self, admin_headers):
        fn = getattr(TestSnapshots, "_latest", None)
        if not fn:
            # fetch
            r = requests.get(f"{BASE_URL}/api/admin/backup/snapshots", headers=admin_headers, timeout=30)
            items = r.json()
            if not items:
                pytest.skip("no snapshots to download")
            fn = items[0]["filename"]
        r = requests.get(f"{BASE_URL}/api/admin/backup/snapshots/{fn}/download",
                         headers=admin_headers, timeout=120)
        assert r.status_code == 200
        assert "gzip" in r.headers.get("content-type", "")
        # parse the gzip to verify it's a valid tarball
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
            assert "manifest.json" in tar.getnames()


# ----- replace mode (sentinel) -------------------------------------------
class TestReplaceMode:
    SENTINEL_COLL = "audits"  # always populated — safe pick

    def test_replace_drops_then_restores(self, admin_headers):
        """Test the drop-then-restore behavior of replace mode.

        1. Insert sentinel_A → in DB
        2. Export backup (contains sentinel_A)
        3. Insert sentinel_B (NOT in backup)
        4. Replace-restore from backup
        5. sentinel_B must be GONE (collection dropped), sentinel_A must be PRESENT (re-inserted from backup).
        """
        try:
            from pymongo import MongoClient
        except Exception:
            pytest.skip("pymongo unavailable for direct mongo test")
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            try:
                with open("/app/backend/.env") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith("MONGO_URL="):
                            mongo_url = s.split("=", 1)[1].strip().strip('"').strip("'")
                        elif s.startswith("DB_NAME="):
                            db_name = s.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
        if not mongo_url or not db_name:
            pytest.skip("MONGO_URL/DB_NAME not set")
        client = MongoClient(mongo_url)
        coll = client[db_name][self.SENTINEL_COLL]
        sa = f"TEST_iter150_A_{uuid.uuid4().hex[:8]}"
        sb = f"TEST_iter150_B_{uuid.uuid4().hex[:8]}"
        try:
            # 1. Insert sentinel A
            coll.insert_one({"id": sa, "marker": "iter150_A"})
            assert coll.find_one({"id": sa}) is not None
            # 2. Export (contains A)
            exp = requests.post(f"{BASE_URL}/api/admin/backup/export",
                                data={"include_audit": "true"}, headers=admin_headers, timeout=300)
            assert exp.status_code == 200
            backup_blob = exp.content
            # 3. Insert sentinel B (after backup)
            coll.insert_one({"id": sb, "marker": "iter150_B"})
            assert coll.find_one({"id": sb}) is not None
            # 4. Replace-restore from backup
            files = {"file": ("b.tar.gz", backup_blob, "application/gzip")}
            data = {"mode": "replace", "dry_run": "false", "include_audit": "true", "admin_password": ADMIN_PASS}
            r = requests.post(f"{BASE_URL}/api/admin/backup/import", data=data, files=files,
                              headers=admin_headers, timeout=600)
            assert r.status_code == 200, r.text[:200]
            # 5. Verify
            leftover_b = coll.find_one({"id": sb})
            restored_a = coll.find_one({"id": sa})
            assert leftover_b is None, "replace mode failed to DROP collection (sentinel B still present)"
            assert restored_a is not None, "replace mode failed to RESTORE from backup (sentinel A missing)"
        finally:
            coll.delete_many({"id": {"$in": [sa, sb]}})
            client.close()
