"""Backup + restore for one organisation — admin-only.

Before multi-organisation this dumped the whole database and the whole uploads
directory, and `replace` mode dropped entire collections. On a shared backend
that is both a leak and a weapon: an administrator of one organisation would
have taken everyone's rows and files with them, and a restore would have wiped
the other organisations' data out of the same collections.

So every read is filtered to the administrator's own organisation, the archive
carries only the files that organisation's rows point at, and a restore only
ever touches rows carrying its organisation id.

Export: a single .tar.gz holding each collection as JSONL, the uploaded files
those rows reference, and a manifest.
Import: the same archive, in `merge` (upsert by id) or `replace` (clear this
organisation's rows first) mode. A pre-restore snapshot is always saved so the
operator can roll back, and the admin password is re-asked.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from deps import raw_db, require_admin, _audit, logger, verify_password
from org_context import UNSCOPED_COLLECTIONS, org_bypass
from storage import get_object, put_object
from datetime import datetime, timezone
from typing import Optional
import asyncio
import io
import os
import re
import json
import mimetypes
import tarfile

router = APIRouter(prefix="/api/admin/backup", tags=["backup"])

UPLOADS_DIR = "/app/backend/uploads"
BACKUPS_DIR = "/app/backend/backups"
BACKUP_VERSION = 2  # v2 = one organisation per archive
ORG_FIELD = "organization_id"
FILE_URL_RE = re.compile(r"/api/(?:storage|uploads)/([A-Za-z0-9._\-/]+)")
# How much of the organisation's media one download may carry. A reply has to
# finish inside the proxy's time limit, and hundreds of megabytes of photos does
# not — past the cap the remaining paths are listed in the manifest so the
# operator knows exactly what is still to copy.
MAX_FILE_BYTES = int(os.environ.get("BACKUP_MAX_FILE_BYTES", 200 * 1024 * 1024))

# Collections we ALWAYS skip — runtime/ephemeral state that doesn't need to travel.
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
_AUDIT_COLLECTIONS = {"audits", "audit_log", "task_overdue_emails", "checkin_logs"}


def _org_of(user: dict) -> str:
    org = user.get(ORG_FIELD)
    if not org:
        raise HTTPException(
            status_code=400,
            detail="Open an organisation before backing up or restoring its data",
        )
    return org


async def _backup_collection_names() -> list:
    """Every collection that holds this organisation's own rows.

    Platform plumbing (the organisation registry, sessions, rate limits) is left
    out: it is not any one organisation's data and restoring it would reach
    across tenants."""
    try:
        with org_bypass():
            names = await raw_db.list_collection_names()
    except Exception as e:
        logger.error(f"list_collection_names failed: {e}")
        names = []
    return [
        n for n in names
        if not n.startswith("system.")
        and n not in _NEVER_BACKUP
        and n not in UNSCOPED_COLLECTIONS
    ]


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


def _walk_file_paths(value, seen: set, out: list):
    """Collect every uploaded-file path the rows point at."""
    if isinstance(value, str):
        for m in FILE_URL_RE.finditer(value):
            p = m.group(1)
            if p not in seen:
                seen.add(p)
                out.append(p)
    elif isinstance(value, dict):
        for v in value.values():
            _walk_file_paths(v, seen, out)
    elif isinstance(value, list):
        for v in value:
            _walk_file_paths(v, seen, out)


async def _read_file(path: str) -> Optional[tuple]:
    try:
        return await asyncio.to_thread(get_object, path)
    except Exception:
        local = os.path.join(UPLOADS_DIR, path)
        if os.path.isfile(local):
            try:
                with open(local, "rb") as fh:
                    return fh.read(), "application/octet-stream"
            except OSError:
                return None
    return None


@router.get("/preview")
async def preview_backup(current_user: dict = Depends(require_admin)) -> dict:
    """Each collection name + this organisation's row count, so the admin can
    size the export and decide whether to opt out of the audit collections."""
    org_id = _org_of(current_user)
    names = await _backup_collection_names()
    out = []
    paths: list = []
    seen: set = set()
    audit_paths: list = []
    audit_seen: set = set()
    audit_docs = 0
    with org_bypass():
        for n in names:
            try:
                count = await raw_db[n].count_documents({ORG_FIELD: org_id})
            except Exception:
                count = -1
            if count == 0:
                continue
            is_audit = n in _AUDIT_COLLECTIONS
            out.append({
                "collection": n,
                "doc_count": count,
                "is_audit": is_audit,
            })
            if is_audit:
                audit_docs += max(count, 0)
            async for doc in raw_db[n].find({ORG_FIELD: org_id}, {"_id": 0}).batch_size(2000):
                if is_audit:
                    _walk_file_paths(doc, audit_seen, audit_paths)
                else:
                    _walk_file_paths(doc, seen, paths)
    audit_only_files = len([p for p in audit_paths if p not in seen])
    return {
        "version": BACKUP_VERSION,
        "organization_id": org_id,
        "collections": out,
        # What the default options actually export, and what ticking "include
        # audit" adds — the two used to be reported as one number, so the
        # download never matched the summary.
        "uploads_files": len(paths),
        "uploads_files_with_audit": len(paths) + audit_only_files,
        "max_file_bytes": MAX_FILE_BYTES,
        "total_collections": len([c for c in out if not c["is_audit"]]),
        "total_docs": sum(x["doc_count"] for x in out if x["doc_count"] > 0 and not x["is_audit"]),
        "audit_docs": audit_docs,
        "audit_collections": len([c for c in out if c["is_audit"]]),
        "now": datetime.now(timezone.utc).isoformat(),
    }


class _TarBuffer:
    """Catches what tarfile writes so it can be handed out as it is produced."""

    def __init__(self):
        self._parts = []

    def write(self, data):
        self._parts.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def drain(self) -> bytes:
        out = b"".join(self._parts)
        self._parts.clear()
        return out


async def _stream_tarball(org_id: str, include_audit: bool, current_user: dict,
                          include_files: bool = True):
    """Produce the archive in pieces.

    A whole organisation's photos and scans ran to hundreds of megabytes, and
    building that in one go took longer than the proxy allows for a reply: the
    download arrived as a gateway error page instead of a file. Now bytes start
    flowing within a second and keep flowing, so nothing times out and nothing
    has to fit in memory.
    """
    buf = _TarBuffer()
    tar = tarfile.open(fileobj=buf, mode="w|gz")
    now = int(datetime.now(timezone.utc).timestamp())

    def _add(name: str, data: bytes):
        tinfo = tarfile.TarInfo(name=name)
        tinfo.size = len(data)
        tinfo.mtime = now
        tar.addfile(tinfo, io.BytesIO(data))

    with org_bypass():
        org = await raw_db.organizations.find_one(
            {"id": org_id}, {"_id": 0, "id": 1, "name": 1, "slug": 1}
        ) or {"id": org_id}
    manifest = {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by_id": current_user["id"],
        "exported_by_name": current_user.get("name") or current_user.get("email"),
        "include_audit": include_audit,
        "organization": org,
        "source_db": os.environ.get("DB_NAME", ""),
        "collections": [],
    }
    collection_names = await _backup_collection_names()
    if not include_audit:
        collection_names = [c for c in collection_names if c not in _AUDIT_COLLECTIONS]
    file_paths: list = []
    seen: set = set()
    for cname in sorted(collection_names):
        with org_bypass():
            expected = await raw_db[cname].count_documents({ORG_FIELD: org_id})
        if not expected:
            continue
        jsonl_chunks = []
        doc_count = 0
        with org_bypass():
            cursor = raw_db[cname].find({ORG_FIELD: org_id}, {"_id": 0}).batch_size(2000)
            async for doc in cursor:
                _walk_file_paths(doc, seen, file_paths)
                doc.pop(ORG_FIELD, None)  # re-stamped on restore
                jsonl_chunks.append(json.dumps(doc, default=_safe_json_default))
                doc_count += 1
        if doc_count != expected:
            logger.warning("Backup %s: read %s of %s rows in %s",
                           org_id, doc_count, expected, cname)
        data = ("\n".join(jsonl_chunks)).encode("utf-8")
        _add(f"collections/{cname}.jsonl", data)
        manifest["collections"].append(
            {"name": cname, "doc_count": doc_count, "expected": expected, "bytes": len(data)}
        )
        yield buf.drain()

    # ----- only the files these rows point at, a handful at a time -----
    uploads_added = 0
    uploads_bytes = 0
    missing: list = []
    if not include_files:
        missing = list(file_paths)
    else:
        for i in range(0, len(file_paths), 8):
            if uploads_bytes >= MAX_FILE_BYTES:
                missing.extend(file_paths[i:])
                break
            batch = file_paths[i:i + 8]
            for path, got in zip(batch, await asyncio.gather(*[_read_file(p) for p in batch])):
                if not got or not got[0]:
                    missing.append(path)
                    continue
                blob = got[0]
                _add(f"uploads/{path}", blob)
                uploads_added += 1
                uploads_bytes += len(blob)
            yield buf.drain()

    manifest["uploads_files"] = uploads_added
    manifest["uploads_bytes"] = uploads_bytes
    manifest["uploads_missing"] = missing
    manifest["include_files"] = include_files
    _add("manifest.json", json.dumps(manifest, indent=2, default=_safe_json_default).encode("utf-8"))
    tar.close()
    yield buf.drain()
    logger.info("Backup export for %s: %s collections, %s files, %s bytes of uploads",
                org_id, len(manifest["collections"]), uploads_added, uploads_bytes)


@router.post("/export")
async def export_backup(
    include_audit: bool = Form(False),
    include_files: bool = Form(True),
    current_user: dict = Depends(require_admin),
):
    """Streams this organisation's backup as a single application/gzip download."""
    org_id = _org_of(current_user)
    logger.info(f"Backup export for {org_id} by {current_user.get('email')}")
    fname = f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.tar.gz"
    await _audit(current_user["id"], "backup_export", "system", org_id, {
        "include_audit": include_audit, "include_files": include_files,
    })
    return StreamingResponse(
        _stream_tarball(org_id, include_audit, current_user, include_files=include_files),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Backup-Version": str(BACKUP_VERSION),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Backup-Version",
        },
    )


# ============================================================
# IMPORT
# ============================================================

async def _snapshot_for_rollback(org_id: str, label: str, current_user: dict) -> Optional[str]:
    """Save a pre-restore snapshot to disk so the operator can roll back."""
    try:
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(BACKUPS_DIR, f"prerestore-{org_id}-{label}-{stamp}.tar.gz")
        with open(path, "wb") as f:
            async for chunk in _stream_tarball(org_id, True, current_user, include_files=False):
                f.write(chunk)
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
    """Restore an archive into this organisation.

    Body (multipart):
      • file              - the .tar.gz produced by /export
      • mode              - 'merge' (upsert per id) | 'replace' (clear this
                            organisation's rows in those collections first)
      • admin_password    - re-enter password for safety
      • include_audit     - restore the audit collections too
      • dry_run           - parse + report counts but write nothing
    """
    org_id = _org_of(current_user)
    if mode not in {"merge", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    with org_bypass():
        full_user = await raw_db.users.find_one(
            {"id": current_user["id"]}, {"_id": 0}
        )
    if not full_user or not full_user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Cannot re-verify admin — contact system admin")
    if not verify_password(admin_password, full_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Admin password incorrect")

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(body) > 1024 * 1024 * 1024:  # 1 GB hard cap
        raise HTTPException(status_code=400, detail="Backup file too large (>1 GB)")

    snapshot_path = None
    if not dry_run:
        snapshot_path = await _snapshot_for_rollback(org_id, mode, current_user)
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
            try:
                mf = tar.extractfile("manifest.json")
                manifest = json.loads(mf.read().decode("utf-8")) if mf else {}
            except Exception:
                manifest = {}
            if manifest.get("version") and manifest["version"] > BACKUP_VERSION:
                raise HTTPException(
                    status_code=400,
                    detail=f"Backup version {manifest['version']} is newer than this server supports ({BACKUP_VERSION})",
                )
            report["manifest"] = manifest
            # Which uploaded files this archive's own rows actually point at.
            # Anything else in uploads/ is not restored: an archive could
            # otherwise name another organisation's logo or scans and overwrite
            # them on the way in.
            referenced_paths: list = []
            seen_paths: set = set()
            # ---- Collections ----
            for member in tar.getmembers():
                if not member.name.startswith("collections/") or not member.name.endswith(".jsonl"):
                    continue
                cname = member.name[len("collections/"):-len(".jsonl")]
                if cname in UNSCOPED_COLLECTIONS or cname in _NEVER_BACKUP or cname.startswith("system."):
                    report["collections"][cname] = {"skipped": "platform collection, not organisation data"}
                    continue
                if cname in _AUDIT_COLLECTIONS and not include_audit:
                    report["collections"][cname] = {"skipped": "audit collection opted out"}
                    continue
                stats = {"read": 0, "inserted": 0, "updated": 0, "errors": 0}
                if mode == "replace" and not dry_run:
                    # Only this organisation's rows — dropping the collection
                    # would have deleted every other organisation's data too.
                    try:
                        with org_bypass():
                            await raw_db[cname].delete_many({ORG_FIELD: org_id})
                    except Exception as e:
                        logger.warning(f"clearing {cname} for {org_id} failed: {e}")
                        report["errors"].append(f"{cname}: clear: {e}")
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
                    _walk_file_paths(doc, seen_paths, referenced_paths)
                    if dry_run:
                        continue
                    doc.pop("_id", None)
                    doc[ORG_FIELD] = org_id  # never trust the archive's own tenant key
                    try:
                        with org_bypass():
                            if cname == "users" and doc.get("email"):
                                # Email is unique per organisation; keep the id the
                                # rest of the data already points at.
                                existing = await raw_db.users.find_one(
                                    {"email": doc["email"], ORG_FIELD: org_id}, {"_id": 0, "id": 1}
                                )
                                if existing:
                                    doc["id"] = existing.get("id", doc.get("id"))
                                    await raw_db.users.update_one(
                                        {"id": doc["id"], ORG_FIELD: org_id}, {"$set": doc}
                                    )
                                    stats["updated"] += 1
                                    continue
                            if "id" in doc:
                                res = await raw_db[cname].update_one(
                                    {"id": doc["id"], ORG_FIELD: org_id}, {"$set": doc}, upsert=True
                                )
                                if res.upserted_id is not None:
                                    stats["inserted"] += 1
                                else:
                                    stats["updated"] += 1
                            else:
                                await raw_db[cname].insert_one(doc)
                                stats["inserted"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        report["errors"].append(f"{cname}: write: {str(e)[:200]}")
                report["collections"][cname] = stats
            # ---- Uploaded files ----
            if not dry_run:
                os.makedirs(UPLOADS_DIR, exist_ok=True)
                for member in tar.getmembers():
                    if not member.name.startswith("uploads/") or member.isdir():
                        continue
                    rel = member.name[len("uploads/"):]
                    if not rel or ".." in rel:
                        continue
                    if rel not in seen_paths:
                        report["errors"].append(
                            f"upload {rel}: skipped — no imported record points at it"
                        )
                        continue
                    src = tar.extractfile(member)
                    if not src:
                        continue
                    blob = src.read()
                    content_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
                    restored = False
                    try:
                        # Back to the same path, so every link in the data keeps
                        # working without rewriting a single row.
                        await asyncio.to_thread(put_object, rel, blob, content_type)
                        restored = True
                    except Exception as e:
                        logger.warning(f"restore {rel} to storage failed: {e}")
                    if not restored:
                        target = os.path.join(UPLOADS_DIR, rel)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        try:
                            with open(target, "wb") as out:
                                out.write(blob)
                            restored = True
                        except Exception as e:
                            report["errors"].append(f"upload {rel}: {e}")
                    if restored:
                        report["uploads_restored"] += 1
    except tarfile.ReadError as e:
        raise HTTPException(status_code=400, detail=f"Not a valid .tar.gz: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"import_backup error: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")

    if not dry_run:
        # A replace that cleared `users` without the importing admin in the
        # archive would have locked them out of their own organisation.
        with org_bypass():
            still_there = await raw_db.users.find_one(
                {"id": current_user["id"]}, {"_id": 0, "id": 1}
            )
            if not still_there:
                await raw_db.users.insert_one({**full_user, ORG_FIELD: org_id})
                report["errors"].append(
                    "your own account was not in the archive and has been kept as it was"
                )

    await _audit(current_user["id"], "backup_import", "system", org_id, {
        "mode": mode, "dry_run": dry_run,
        "collections_imported": len([k for k, v in report["collections"].items()
                                     if isinstance(v, dict) and v.get("read")]),
        "uploads_restored": report["uploads_restored"],
        "snapshot_path": snapshot_path,
    })
    return report


@router.get("/snapshots")
async def list_snapshots(current_user: dict = Depends(require_admin)):
    """Pre-restore auto-snapshots belonging to this organisation."""
    org_id = _org_of(current_user)
    if not os.path.isdir(BACKUPS_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(BACKUPS_DIR), reverse=True):
        if not fn.endswith(".tar.gz") or org_id not in fn:
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
    org_id = _org_of(current_user)
    if "/" in filename or ".." in filename or not filename.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Bad filename")
    if org_id not in filename:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    full = os.path.join(BACKUPS_DIR, filename)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    with open(full, "rb") as f:
        blob = f.read()
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
