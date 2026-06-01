"""Full-app backup + restore — admin-only.

Export: streams a single .tar.gz that contains every Mongo collection (as JSONL),
every file under /app/backend/uploads/, and a manifest. Designed for cross-environment
data migration (preview → prod → self-hosted Tauri build).

Import: accepts that same .tar.gz, validates the manifest, and writes the data back
in either `merge` (upsert per doc id) or `replace` (drop collections first) mode.
Always saves a pre-restore snapshot to /app/backend/backups/ so the operator can
roll back. Re-asks for the admin password as a safety guard.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from deps import db, require_admin, _audit, logger, verify_password
from datetime import datetime, timezone
from typing import Optional
import io
import os
import json
import tarfile
import tempfile
import shutil
import uuid

router = APIRouter(prefix="/api/admin/backup", tags=["backup"])

UPLOADS_DIR = "/app/backend/uploads"
BACKUPS_DIR = "/app/backend/backups"
BACKUP_VERSION = 1

# Collections we ALWAYS skip — runtime/ephemeral state that doesn't need to travel.
# These either bind to device-specific resources or have non-`id` unique keys that
# our generic upsert logic can't reason about.
_NEVER_BACKUP = {
    "system.indexes",
    "fs.chunks",
    "fs.files",
    "sessions",                # JWT sessions — jti-keyed, ephemeral
    "push_subscriptions",      # browser endpoints, device-bound
    "notifications",           # transient inbox state
    "security_pair_attempts",  # rate-limit log — recreated naturally
    "fingerprint_data",        # device-bound biometric blobs
}
# Collections we OFFER as opt-out (operator can untick before exporting).
_AUDIT_COLLECTIONS = {"audits", "task_overdue_emails", "checkin_logs"}


async def _list_collection_names() -> list:
    """Return all user collections (not system.*)."""
    try:
        names = await db.list_collection_names()
    except Exception as e:
        logger.error(f"list_collection_names failed: {e}")
        names = []
    return [n for n in names if not n.startswith("system.") and n not in _NEVER_BACKUP]


def _safe_json_default(o):
    """JSON encoder fallback for datetime / ObjectId / bytes — keep the data movable."""
    if isinstance(o, datetime):
        return o.isoformat()
    try:
        from bson import ObjectId
        if isinstance(o, ObjectId):
            return str(o)
    except Exception:
        pass
    if isinstance(o, bytes):
        return o.decode("utf-8", errors="replace")
    return str(o)


@router.get("/preview")
async def preview_backup(current_user: dict = Depends(require_admin)) -> dict:
    """Returns each collection name + doc count so the admin can size the export
    + decide whether to opt out of the noisy audit collections."""
    names = await _list_collection_names()
    out = []
    for n in names:
        try:
            count = await db[n].count_documents({})
        except Exception:
            count = -1
        out.append({
            "collection": n,
            "doc_count": count,
            "is_audit": n in _AUDIT_COLLECTIONS,
        })
    uploads = 0
    uploads_bytes = 0
    if os.path.isdir(UPLOADS_DIR):
        for root, _dirs, files in os.walk(UPLOADS_DIR):
            for fn in files:
                try:
                    uploads += 1
                    uploads_bytes += os.path.getsize(os.path.join(root, fn))
                except Exception:
                    pass
    return {
        "version": BACKUP_VERSION,
        "collections": out,
        "uploads_files": uploads,
        "uploads_bytes": uploads_bytes,
        "total_collections": len(out),
        "total_docs": sum(x["doc_count"] for x in out if x["doc_count"] > 0),
        "now": datetime.now(timezone.utc).isoformat(),
    }


async def _build_tarball(include_audit: bool, current_user: dict) -> bytes:
    """Build the .tar.gz entirely in memory — for ~10MB-1GB exports this is fine.
    Streams to disk via a NamedTemporaryFile for safety on huge data sets."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    tmp_path = tmp.name
    tmp.close()
    try:
        with tarfile.open(tmp_path, "w:gz", compresslevel=6) as tar:
            # ----- manifest.json -----
            manifest = {
                "version": BACKUP_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "exported_by_id": current_user["id"],
                "exported_by_name": current_user.get("name") or current_user.get("email"),
                "include_audit": include_audit,
                "source_db": os.environ.get("DB_NAME", ""),
                "source_host": os.environ.get("PREVIEW_PROXY_URL", os.environ.get("REACT_APP_BACKEND_URL", "")),
                "collections": [],
            }
            collection_names = await _list_collection_names()
            if not include_audit:
                collection_names = [c for c in collection_names if c not in _AUDIT_COLLECTIONS]
            # ----- collections (jsonl) -----
            for cname in sorted(collection_names):
                jsonl_chunks = []
                doc_count = 0
                async for doc in db[cname].find({}, {"_id": 0}):
                    jsonl_chunks.append(json.dumps(doc, default=_safe_json_default))
                    doc_count += 1
                data = ("\n".join(jsonl_chunks)).encode("utf-8")
                tinfo = tarfile.TarInfo(name=f"collections/{cname}.jsonl")
                tinfo.size = len(data)
                tinfo.mtime = int(datetime.now(timezone.utc).timestamp())
                tar.addfile(tinfo, io.BytesIO(data))
                manifest["collections"].append({"name": cname, "doc_count": doc_count, "bytes": len(data)})
            # ----- uploads dir -----
            uploads_added = 0
            uploads_bytes = 0
            if os.path.isdir(UPLOADS_DIR):
                for root, _dirs, files in os.walk(UPLOADS_DIR):
                    for fn in files:
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, UPLOADS_DIR)
                        try:
                            tar.add(full, arcname=f"uploads/{rel}")
                            uploads_added += 1
                            uploads_bytes += os.path.getsize(full)
                        except Exception as e:
                            logger.warning(f"backup: skipped {full}: {e}")
            manifest["uploads_files"] = uploads_added
            manifest["uploads_bytes"] = uploads_bytes
            # ----- manifest as the LAST entry so readers can find it after the data -----
            mb = json.dumps(manifest, indent=2, default=_safe_json_default).encode("utf-8")
            mi = tarfile.TarInfo(name="manifest.json")
            mi.size = len(mb)
            mi.mtime = int(datetime.now(timezone.utc).timestamp())
            tar.addfile(mi, io.BytesIO(mb))
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/export")
async def export_backup(
    include_audit: bool = Form(False),
    current_user: dict = Depends(require_admin),
):
    """Streams the full backup as a single application/gzip download."""
    logger.info(f"Starting backup export (include_audit={include_audit}) by {current_user.get('email')}")
    blob = await _build_tarball(include_audit=include_audit, current_user=current_user)
    fname = f"5812connect-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.tar.gz"
    await _audit(current_user["id"], "backup_export", "system", "all", {
        "include_audit": include_audit, "size_bytes": len(blob),
    })
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Backup-Version": str(BACKUP_VERSION)},
    )


# ============================================================
# IMPORT
# ============================================================

async def _snapshot_for_rollback(label: str, current_user: dict) -> Optional[str]:
    """Save a pre-restore snapshot to disk so the operator can roll back."""
    try:
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        blob = await _build_tarball(include_audit=True, current_user=current_user)
        path = os.path.join(BACKUPS_DIR, f"prerestore-{label}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.tar.gz")
        with open(path, "wb") as f:
            f.write(blob)
        return path
    except Exception as e:
        logger.error(f"pre-restore snapshot failed: {e}")
        return None


@router.post("/import")
async def import_backup(
    file: UploadFile = File(...),
    mode: str = Form("merge"),
    admin_password: str = Form(...),
    include_audit: bool = Form(False),
    dry_run: bool = Form(False),
    current_user: dict = Depends(require_admin),
):
    """Restore a backup archive.

    Body (multipart):
      • file              - the .tar.gz produced by /export
      • mode              - 'merge' (upsert per id) | 'replace' (drop target collections first)
      • admin_password    - re-enter password for safety (must match current_user.password_hash)
      • include_audit     - restore the audit collections too
      • dry_run           - parse + report counts but write nothing
    """
    if mode not in {"merge", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    # Re-verify admin password — guards against stolen-token misuse
    full_user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "password_hash": 1, "email": 1})
    if not full_user or not full_user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Cannot re-verify admin — contact system admin")
    if not verify_password(admin_password, full_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Admin password incorrect")

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(body) > 1024 * 1024 * 1024:  # 1 GB hard cap
        raise HTTPException(status_code=400, detail="Backup file too large (>1 GB)")

    # ---- Parse the tarball ----
    snapshot_path = None
    if not dry_run:
        snapshot_path = await _snapshot_for_rollback(label=mode, current_user=current_user)
    report = {
        "mode": mode,
        "dry_run": dry_run,
        "manifest": None,
        "collections": {},
        "uploads_restored": 0,
        "snapshot_path": snapshot_path,
        "errors": [],
    }
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
            # Find manifest first
            try:
                mf = tar.extractfile("manifest.json")
                manifest = json.loads(mf.read().decode("utf-8")) if mf else {}
            except Exception:
                manifest = {}
            if manifest.get("version") and manifest["version"] > BACKUP_VERSION:
                raise HTTPException(status_code=400, detail=f"Backup version {manifest['version']} is newer than this server supports ({BACKUP_VERSION})")
            report["manifest"] = manifest
            # ---- Collections ----
            for member in tar.getmembers():
                if not member.name.startswith("collections/") or not member.name.endswith(".jsonl"):
                    continue
                cname = member.name[len("collections/"):-len(".jsonl")]
                if cname in _AUDIT_COLLECTIONS and not include_audit:
                    report["collections"][cname] = {"skipped": "audit collection opted out"}
                    continue
                stats = {"read": 0, "inserted": 0, "updated": 0, "errors": 0}
                if mode == "replace" and not dry_run:
                    try:
                        await db[cname].drop()
                    except Exception as e:
                        logger.warning(f"drop {cname} failed: {e}")
                f = tar.extractfile(member)
                if not f:
                    continue
                for raw in f.read().decode("utf-8").splitlines():
                    if not raw.strip():
                        continue
                    stats["read"] += 1
                    try:
                        doc = json.loads(raw)
                    except Exception as e:
                        stats["errors"] += 1
                        report["errors"].append(f"{cname}: json parse: {e}")
                        continue
                    if dry_run:
                        continue
                    try:
                        if "id" in doc:
                            res = await db[cname].update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
                            if res.upserted_id is not None:
                                stats["inserted"] += 1
                            else:
                                stats["updated"] += 1
                        else:
                            await db[cname].insert_one(doc)
                            stats["inserted"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        report["errors"].append(f"{cname}: write: {e}")
                report["collections"][cname] = stats
            # ---- Uploads ----
            if not dry_run:
                os.makedirs(UPLOADS_DIR, exist_ok=True)
                for member in tar.getmembers():
                    if not member.name.startswith("uploads/") or member.isdir():
                        continue
                    rel = member.name[len("uploads/"):]
                    if not rel or ".." in rel:
                        continue
                    target = os.path.join(UPLOADS_DIR, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    try:
                        src = tar.extractfile(member)
                        if src:
                            with open(target, "wb") as out:
                                shutil.copyfileobj(src, out)
                            report["uploads_restored"] += 1
                    except Exception as e:
                        report["errors"].append(f"upload {rel}: {e}")
    except tarfile.ReadError as e:
        raise HTTPException(status_code=400, detail=f"Not a valid .tar.gz: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"import_backup error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")

    await _audit(current_user["id"], "backup_import", "system", "all", {
        "mode": mode, "dry_run": dry_run,
        "collections_imported": len([k for k, v in report["collections"].items() if isinstance(v, dict) and v.get("read")]),
        "uploads_restored": report["uploads_restored"],
        "snapshot_path": snapshot_path,
    })
    return report


@router.get("/snapshots")
async def list_snapshots(current_user: dict = Depends(require_admin)):
    """List pre-restore auto-snapshots available on disk."""
    if not os.path.isdir(BACKUPS_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(BACKUPS_DIR), reverse=True):
        if not fn.endswith(".tar.gz"):
            continue
        full = os.path.join(BACKUPS_DIR, fn)
        try:
            st = os.stat(full)
            out.append({
                "filename": fn,
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        except Exception:
            pass
    return out


@router.get("/snapshots/{filename}/download")
async def download_snapshot(filename: str, current_user: dict = Depends(require_admin)):
    """Download a pre-restore snapshot so the operator can run an /import on it
    after a botched restore. Same .tar.gz format as a fresh /export."""
    if "/" in filename or ".." in filename or not filename.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Bad filename")
    full = os.path.join(BACKUPS_DIR, filename)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    with open(full, "rb") as f:
        blob = f.read()
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
