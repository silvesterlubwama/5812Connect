"""Move one organisation from another deployment, server to server.

An organisation with years of photos and scans runs to hundreds of megabytes or
more. Pushing that through a browser as one archive cannot work: the reply has
to finish inside the proxy's time limit, and a single upload that size is one
dropped connection away from starting again.

So the two servers talk to each other instead. The old deployment issues a
one-time transfer key for one organisation and serves it in pages — rows a few
thousand at a time, files one at a time. The new deployment pulls those pages in
the background and writes them straight into a fresh organisation. Nothing is
ever assembled into a single file, so there is no size limit and nothing to
clean up afterwards; the key is destroyed the moment the pull reports finished.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import Response
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import asyncio
import hashlib
import hmac
import secrets
import uuid

import httpx

from deps import raw_db, require_super_admin, org_bypass, logger
from org_context import UNSCOPED_COLLECTIONS
from storage import get_object, put_object
from routers.organizations import _audit, SLUG_RE, _stats

router = APIRouter(prefix="/api")

GRANTS = "org_transfer_grants"
GRANT_FILES = "org_transfer_files"
JOBS = "org_transfer_jobs"
ROW_PAGE = 2000          # rows per request
FILE_CONCURRENCY = 8     # files fetched at once
WRITE_BATCH = 1000       # rows per insert_many
GRANT_TTL_HOURS = 48


def _hash_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# SOURCE SIDE — issuing and serving a transfer key
# ============================================================

@router.post("/organizations/{org_id}/transfer-key")
async def create_transfer_key(
    org_id: str, current_user: dict = Depends(require_super_admin)
) -> dict:
    """Mint a one-time key that lets another deployment read this organisation.

    The key is shown once and only its hash is kept, so a leaked database gives
    nobody a way back in."""
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "name": 1, "slug": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    grant_id = uuid.uuid4().hex[:12]
    secret = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=GRANT_TTL_HOURS)
    with org_bypass():
        await raw_db[GRANTS].insert_one({
            "id": grant_id,
            "organization_id": org_id,
            "organization_name": org.get("name"),
            "key_hash": _hash_key(secret),
            "created_at": _now(),
            "created_by": current_user.get("id"),
            "expires_at": expires.isoformat(),
            "status": "open",
            "rows_served": 0,
            "files_served": 0,
        })
    await _audit(current_user.get("id"), "transfer_key_created", "organization", org_id,
                 {"grant": grant_id, "expires_at": expires.isoformat()})
    return {
        "grant_id": grant_id,
        # Shown once. Everything the other server needs is in this one string.
        "transfer_key": f"{grant_id}.{secret}",
        "organization": org,
        "expires_at": expires.isoformat(),
    }


@router.get("/organizations/{org_id}/transfer-keys")
async def list_transfer_keys(
    org_id: str, current_user: dict = Depends(require_super_admin)
) -> dict:
    with org_bypass():
        rows = await raw_db[GRANTS].find(
            {"organization_id": org_id}, {"_id": 0, "key_hash": 0}
        ).sort("created_at", -1).to_list(50)
    return {"keys": rows}


@router.delete("/organizations/transfer-keys/{grant_id}")
async def revoke_transfer_key(
    grant_id: str, current_user: dict = Depends(require_super_admin)
) -> dict:
    with org_bypass():
        res = await raw_db[GRANTS].delete_one({"id": grant_id})
        await raw_db[GRANT_FILES].delete_many({"grant_id": grant_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Transfer key not found")
    await _audit(current_user.get("id"), "transfer_key_revoked", "organization", None, {"grant": grant_id})
    return {"revoked": grant_id}


async def _grant_from_key(key: Optional[str]) -> dict:
    """Resolve the key the other deployment presents. The only way into the
    endpoints below — they take no session and belong to no logged-in user."""
    if not key or "." not in key:
        raise HTTPException(status_code=401, detail="Transfer key required")
    grant_id, _, secret = key.partition(".")
    with org_bypass():
        grant = await raw_db[GRANTS].find_one({"id": grant_id}, {"_id": 0})
    if not grant or not hmac.compare_digest(grant.get("key_hash", ""), _hash_key(secret)):
        raise HTTPException(status_code=401, detail="Transfer key not accepted")
    if grant.get("status") != "open":
        raise HTTPException(status_code=403, detail="This transfer key has already been used")
    if grant.get("expires_at", "") < _now():
        raise HTTPException(status_code=401, detail="This transfer key has expired")
    return grant


async def _transfer_collections() -> list:
    with org_bypass():
        names = await raw_db.list_collection_names()
    return sorted(n for n in names if not n.startswith("system.") and n not in UNSCOPED_COLLECTIONS)


@router.get("/transfer/manifest")
async def transfer_manifest(x_transfer_key: str = Header(None)) -> dict:
    """What the other side is about to pull: the organisation, every collection
    with its row count, and every file its rows point at."""
    grant = await _grant_from_key(x_transfer_key)
    org_id = grant["organization_id"]
    from routers.backup import _walk_file_paths
    counts = {}
    paths: list = []
    seen: set = set()
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0})
        for name in await _transfer_collections():
            n = await raw_db[name].count_documents({"organization_id": org_id})
            if not n:
                continue
            counts[name] = n
            async for doc in raw_db[name].find({"organization_id": org_id}, {"_id": 0}).batch_size(2000):
                _walk_file_paths(doc, seen, paths)
        # The key may read exactly these files and nothing else. Storage is one
        # shared bucket whose paths carry no organisation, so without this list
        # a key for one organisation could name another's photo and get it.
        await raw_db[GRANT_FILES].delete_many({"grant_id": grant["id"]})
        for i in range(0, len(paths), 1000):
            await raw_db[GRANT_FILES].insert_many(
                [{"grant_id": grant["id"], "path": p} for p in paths[i:i + 1000]],
                ordered=False,
            )
        await raw_db[GRANTS].update_one(
            {"id": grant["id"]}, {"$set": {"files_listed": len(paths), "manifest_at": _now()}}
        )
    return {
        "format": "5812-org-transfer/v1",
        "organization": {k: v for k, v in (org or {}).items() if k not in {"hostnames", "is_default"}},
        "collection_counts": counts,
        "document_count": sum(counts.values()),
        "files": paths,
        "row_page": ROW_PAGE,
        "served_at": _now(),
    }


@router.get("/transfer/rows")
async def transfer_rows(
    collection: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(ROW_PAGE, ge=1, le=5000),
    x_transfer_key: str = Header(None),
) -> dict:
    """One page of one collection — only ever this organisation's rows."""
    grant = await _grant_from_key(x_transfer_key)
    if collection.startswith("system.") or collection in UNSCOPED_COLLECTIONS:
        raise HTTPException(status_code=400, detail="That collection is not part of an organisation")
    org_id = grant["organization_id"]
    with org_bypass():
        rows = await raw_db[collection].find(
            {"organization_id": org_id}, {"_id": 0}
        ).sort("_id", 1).skip(skip).limit(limit).to_list(limit)
        await raw_db[GRANTS].update_one({"id": grant["id"]}, {"$inc": {"rows_served": len(rows)}})
    for r in rows:
        r.pop("organization_id", None)
    return {"collection": collection, "skip": skip, "rows": rows}


@router.get("/transfer/file")
async def transfer_file(path: str = Query(...), x_transfer_key: str = Header(None)):
    """One uploaded file, raw. Streamed straight through — never base64, never
    held in an archive.

    Only files this organisation's own rows point at: storage is one shared
    bucket and its paths carry no organisation, so the allowed list recorded
    when the manifest was built is the whole of the isolation here.
    """
    grant = await _grant_from_key(x_transfer_key)
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Bad path")
    with org_bypass():
        allowed = await raw_db[GRANT_FILES].find_one(
            {"grant_id": grant["id"], "path": path}, {"_id": 1}
        )
    if not allowed:
        raise HTTPException(
            status_code=404,
            detail="That file does not belong to this organisation",
        )
    try:
        blob, content_type = await asyncio.to_thread(get_object, path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    with org_bypass():
        await raw_db[GRANTS].update_one({"id": grant["id"]}, {"$inc": {"files_served": 1}})
    return Response(content=blob, media_type=content_type or "application/octet-stream")


@router.post("/transfer/complete")
async def transfer_complete(x_transfer_key: str = Header(None)) -> dict:
    """The other side reports it has everything: burn the key."""
    grant = await _grant_from_key(x_transfer_key)
    with org_bypass():
        await raw_db[GRANTS].update_one(
            {"id": grant["id"]},
            {"$set": {"status": "used", "used_at": _now()}},
        )
        # The read list dies with the key.
        await raw_db[GRANT_FILES].delete_many({"grant_id": grant["id"]})
    logger.info("Transfer key %s consumed for %s", grant["id"], grant["organization_id"])
    return {"ok": True}


# ============================================================
# TARGET SIDE — pulling an organisation in
# ============================================================

class PullIn(BaseModel):
    source_url: str
    transfer_key: str
    name: Optional[str] = None
    slug: Optional[str] = None
    # Overwrite an organisation already on this server instead of creating one.
    target_org_id: Optional[str] = None
    overwrite: bool = False


async def _job_update(job_id: str, **fields):
    fields["updated_at"] = _now()
    with org_bypass():
        await raw_db[JOBS].update_one({"id": job_id}, {"$set": fields})


async def _get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    """GET with backoff. The other deployment may still be running older code
    whose rate limiter counts these as ordinary anonymous traffic, and a pull is
    hundreds of requests — a 429 means wait, not fail."""
    delay = 2.0
    for attempt in range(6):
        r = await client.get(url, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == 5:
                return r
            wait = delay
            try:
                wait = max(wait, float(r.headers.get("retry-after", 0)))
            except (TypeError, ValueError):
                pass
            await asyncio.sleep(min(wait, 60))
            delay = min(delay * 2, 30)
            continue
        return r
    return r


async def _wipe_org(org_id: str) -> int:
    """Everything this organisation holds, before an overwrite puts the other
    server's copy in its place. The organisation row itself stays: its web
    addresses and its place on this server belong here, not to the source."""
    removed = 0
    with org_bypass():
        for name in await _transfer_collections():
            res = await raw_db[name].delete_many({"organization_id": org_id})
            removed += res.deleted_count
    return removed


async def _run_pull(job_id: str, base: str, key: str, org_id: str, manifest: dict,
                    overwrite: bool = False):
    """Pull every row and every file. Runs in the background: the browser only
    polls for progress, so nothing depends on one long request staying up."""
    headers = {"X-Transfer-Key": key}
    counts = manifest.get("collection_counts", {})
    files = manifest.get("files", [])
    rows_total = sum(counts.values())
    rows_done = 0
    files_done = 0
    bytes_done = 0
    problems: list = []
    try:
        if overwrite:
            await _job_update(job_id, current="clearing what is here now")
            cleared = await _wipe_org(org_id)
            await _job_update(job_id, cleared=cleared)
            logger.info("Pull %s cleared %s existing rows from %s", job_id, cleared, org_id)
        timeout = httpx.Timeout(120.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for name, total in counts.items():
                skip = 0
                while skip < total:
                    r = await _get(
                        client,
                        f"{base}/api/transfer/rows",
                        params={"collection": name, "skip": skip, "limit": ROW_PAGE},
                        headers=headers,
                    )
                    r.raise_for_status()
                    rows = r.json().get("rows", [])
                    if not rows:
                        break
                    for i in range(0, len(rows), WRITE_BATCH):
                        batch = [
                            {**row, "organization_id": org_id}
                            for row in rows[i:i + WRITE_BATCH]
                        ]
                        try:
                            with org_bypass():
                                await raw_db[name].insert_many(batch, ordered=False)
                        except Exception as e:
                            # A duplicate id on a re-run is not worth losing the
                            # rest of the collection over.
                            problems.append(f"{name}: {str(e)[:160]}")
                    skip += len(rows)
                    rows_done += len(rows)
                    await _job_update(job_id, rows_done=rows_done, current=name)

            # ---- files, a handful at a time ----
            sem = asyncio.Semaphore(FILE_CONCURRENCY)

            async def _one(path: str):
                async with sem:
                    try:
                        rf = await _get(
                            client, f"{base}/api/transfer/file",
                            params={"path": path}, headers=headers,
                        )
                        if rf.status_code != 200:
                            return path, None, None
                        return (path, rf.content,
                                rf.headers.get("content-type", "application/octet-stream"))
                    except Exception:
                        return path, None, None

            for i in range(0, len(files), FILE_CONCURRENCY * 2):
                chunk = files[i:i + FILE_CONCURRENCY * 2]
                for path, blob, ctype in await asyncio.gather(*[_one(p) for p in chunk]):
                    if blob is None:
                        problems.append(f"file missing: {path}")
                        continue
                    try:
                        # Same path as on the old server, so every link in the
                        # rows keeps working with nothing rewritten.
                        await asyncio.to_thread(put_object, path, blob, ctype)
                        files_done += 1
                        bytes_done += len(blob)
                    except Exception as e:
                        problems.append(f"file {path}: {str(e)[:160]}")
                await _job_update(job_id, files_done=files_done, bytes_done=bytes_done)

            try:
                await client.post(f"{base}/api/transfer/complete", headers=headers)
            except Exception:
                pass
        with org_bypass():
            await raw_db.organizations.update_one(
                {"id": org_id}, {"$set": {"last_activity_at": _now()}}
            )
        await _job_update(
            job_id, status="done", finished_at=_now(),
            rows_done=rows_done, files_done=files_done, bytes_done=bytes_done,
            problems=problems[:50], problem_count=len(problems),
        )
        logger.info("Pull %s finished: %s/%s rows, %s/%s files",
                    job_id, rows_done, rows_total, files_done, len(files))
    except Exception as e:
        logger.error(f"Pull {job_id} failed: {e}")
        # Half an organisation must not sit there looking live. Suspended, with
        # the reason on it, so the owner can retry or delete it from the console.
        with org_bypass():
            await raw_db.organizations.update_one(
                {"id": org_id},
                {"$set": {"status": "suspended",
                          "suspend_reason": f"Transfer from {base} did not finish: {str(e)[:160]}"}},
            )
        await _job_update(
            job_id, status="failed", error=str(e)[:400], finished_at=_now(),
            rows_done=rows_done, files_done=files_done, bytes_done=bytes_done,
            problems=problems[:50], problem_count=len(problems),
        )


@router.post("/organizations/pull")
async def start_pull(data: PullIn, current_user: dict = Depends(require_super_admin)) -> dict:
    """Start pulling an organisation from another deployment into this one."""
    base = data.source_url.strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        raise HTTPException(status_code=400, detail="Address must start with http:// or https://")
    key = data.transfer_key.strip()
    if "." not in key:
        raise HTTPException(status_code=400, detail="That does not look like a transfer key")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0),
                                     follow_redirects=True) as client:
            r = await client.get(f"{base}/api/transfer/manifest", headers={"X-Transfer-Key": key})
    except Exception as e:
        # Deliberately 400, not 502: the ingress replaces a 502 body with its own
        # HTML page, so the reason never reaches the person who typed the address.
        raise HTTPException(status_code=400, detail=f"Could not reach {base}: {str(e)[:200]}")
    if r.status_code in (401, 403):
        raise HTTPException(status_code=r.status_code,
                            detail=r.json().get("detail", "Transfer key not accepted")
                            if r.headers.get("content-type", "").startswith("application/json")
                            else "Transfer key not accepted")
    if r.status_code != 200:
        raise HTTPException(status_code=400,
                            detail=f"{base} answered {r.status_code} — check the address")
    try:
        manifest = r.json()
    except Exception:
        raise HTTPException(status_code=400, detail="That address is not a Connect server")
    if manifest.get("format") != "5812-org-transfer/v1":
        raise HTTPException(status_code=400, detail="Unexpected answer from the other server")

    src_org = manifest.get("organization") or {}
    name = (data.name or src_org.get("name") or "Imported organisation").strip()

    if data.target_org_id:
        # Overwrite an organisation that is already here — a second run of the
        # same move, or a rehearsal being replaced by the real thing.
        if not data.overwrite:
            raise HTTPException(
                status_code=400,
                detail="Overwriting an existing organisation has to be confirmed",
            )
        with org_bypass():
            target = await raw_db.organizations.find_one({"id": data.target_org_id}, {"_id": 0})
        if not target:
            raise HTTPException(status_code=404, detail="That organisation is not on this server")
        org_id = target["id"]
        name = (data.name or target.get("name") or name).strip()
        with org_bypass():
            await raw_db.organizations.update_one(
                {"id": org_id},
                {"$set": {
                    # Branding and settings arrive with the data; the addresses,
                    # the slug and the default flag belong to this server.
                    "name": name,
                    "status": "active",
                    "last_activity_at": _now(),
                    "pulled_from": base,
                    "overwritten_at": _now(),
                }, "$unset": {"suspend_reason": ""}},
            )
    else:
        slug = (data.slug or src_org.get("slug") or "").strip().lower()
        if not SLUG_RE.match(slug or ""):
            raise HTTPException(status_code=400, detail="Give the organisation a web name (slug)")
        with org_bypass():
            clash = await raw_db.organizations.find_one({"slug": slug}, {"_id": 0, "id": 1, "name": 1})
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"'{clash['name']}' already uses the web name '{slug}' here — "
                       "choose another, or overwrite that organisation",
            )
        org_id = str(uuid.uuid4())
        with org_bypass():
            # The addresses and the default flag stay behind: two servers must not
            # both claim the same hostname.
            await raw_db.organizations.insert_one({
                **{k: v for k, v in src_org.items()
                   if k not in {"id", "slug", "hostnames", "is_default", "_id"}},
                "id": org_id,
                "name": name,
                "slug": slug,
                "status": "active",
                "created_at": _now(),
                "created_by": current_user.get("id"),
                "last_activity_at": _now(),
                "pulled_from": base,
            })
    job_id = str(uuid.uuid4())
    with org_bypass():
        await raw_db[JOBS].insert_one({
            "id": job_id,
            "organization_id": org_id,
            "organization_name": name,
            "source_url": base,
            "status": "running",
            "overwrite": bool(data.target_org_id),
            "started_at": _now(),
            "started_by": current_user.get("id"),
            "rows_total": manifest.get("document_count", 0),
            "files_total": len(manifest.get("files", [])),
            "rows_done": 0,
            "files_done": 0,
            "bytes_done": 0,
            "cleared": 0,
        })
    asyncio.create_task(
        _run_pull(job_id, base, key, org_id, manifest, overwrite=bool(data.target_org_id))
    )
    await _audit(current_user.get("id"),
                 "pull_overwrite_started" if data.target_org_id else "pull_started",
                 "organization", org_id,
                 {"source": base, "rows": manifest.get("document_count"),
                  "files": len(manifest.get("files", []))})
    return {
        "job_id": job_id,
        "organization_id": org_id,
        "organization_name": name,
        "overwrite": bool(data.target_org_id),
        "rows_total": manifest.get("document_count", 0),
        "files_total": len(manifest.get("files", [])),
    }


@router.get("/organizations/pull/{job_id}")
async def pull_status(job_id: str, current_user: dict = Depends(require_super_admin)) -> dict:
    with org_bypass():
        job = await raw_db[JOBS].find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if job.get("status") == "done":
        job["stats"] = await _stats(job["organization_id"])
    return job


@router.get("/organizations/pulls")
async def list_pulls(current_user: dict = Depends(require_super_admin)) -> dict:
    with org_bypass():
        jobs = await raw_db[JOBS].find({}, {"_id": 0}).sort("started_at", -1).to_list(25)
    return {"transfers": jobs}
