"""Telemetry & License Management — for self-hosted desktop installs.

Two roles:
  • HQ deployment (e.g. https://hq.5812-global.org) — receives heartbeats from
    every desktop install, surfaces a roster on /admin/telemetry, lets system
    admins issue / revoke license keys.
  • Desktop install — reads its persisted install_id + license_key, POSTs a
    daily heartbeat to the configured HQ endpoint, surfaces the license-status
    banner if blocked / expired.

Design choices:
  • SOFT enforcement — invalid / expired license shows an amber banner but
    never crashes the desktop app. Partner orgs, not paying customers.
  • Heartbeat is anonymous: only install_id + license_key + org_id + version +
    user_count are sent. NO PII. No member names, no document content.
  • license_key is a 32-char URL-safe token. install_id is a UUID4.
  • Rate-limited: the same install_id can heartbeat at most once every 8 hours.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from deps import db, require_admin, _audit, logger
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets

router = APIRouter(prefix="/api", tags=["telemetry"])


# ============================================================
# PUBLIC: heartbeat from desktop installs (no auth)
# ============================================================

@router.post("/telemetry/heartbeat")
async def post_heartbeat(data: dict, request: Request):
    """Public endpoint — desktop installs POST here every 24 h.

    Body: {
        install_id: str (UUID4 — generated on first run),
        license_key: str | "",
        org_id: str | "",
        version: str,
        user_count: int,
        env: "desktop" | "cloud" | str,
    }
    Returns: { license_status: 'valid'|'expired'|'invalid'|'unlicensed',
               license_expires_at: iso | null,
               server_time: iso, message?: str }
    """
    install_id = (data.get("install_id") or "").strip()
    if not install_id or len(install_id) > 64:
        raise HTTPException(status_code=400, detail="install_id required")
    license_key = (data.get("license_key") or "").strip()
    org_id = (data.get("org_id") or "").strip()
    version = (data.get("version") or "").strip()[:32]
    user_count = int(data.get("user_count") or 0)
    env = (data.get("env") or "desktop").strip()[:16]

    # Soft rate-limit: deduplicate same-install heartbeats within 8 hours
    cutoff_8h = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    last = await db.telemetry_heartbeats.find_one(
        {"install_id": install_id, "received_at": {"$gt": cutoff_8h}},
        {"_id": 0, "id": 1},
    )
    if last:
        # Acknowledge but skip the write — keeps the dataset clean
        license_status = await _validate_license_status(license_key)
        return {**license_status, "server_time": datetime.now(timezone.utc).isoformat(), "ratelimited": True}

    # Persist
    ip = request.client.host if request.client else ""
    doc = {
        "id": f"hb_{uuid.uuid4().hex[:10]}",
        "install_id": install_id,
        "license_key": license_key,
        "org_id": org_id,
        "version": version,
        "user_count": user_count,
        "env": env,
        "ip": ip,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.telemetry_heartbeats.insert_one(doc)
    # Upsert the install roster row so /admin/telemetry doesn't have to aggregate
    await db.telemetry_installs.update_one(
        {"install_id": install_id},
        {"$set": {
            "install_id": install_id,
            "license_key": license_key,
            "org_id": org_id,
            "version": version,
            "user_count": user_count,
            "env": env,
            "last_seen_at": doc["received_at"],
            "last_seen_ip": ip,
        }, "$setOnInsert": {
            "first_seen_at": doc["received_at"],
        }},
        upsert=True,
    )
    license_status = await _validate_license_status(license_key)
    return {**license_status, "server_time": doc["received_at"]}


async def _validate_license_status(license_key: str) -> dict:
    """Look up license_key in db.licenses → return one of:
      • {license_status:'unlicensed'} when blank
      • {license_status:'invalid'}  when not found
      • {license_status:'expired', license_expires_at: iso} when past expiry
      • {license_status:'blocked'} when manually revoked
      • {license_status:'valid', license_expires_at: iso|null}
    """
    if not license_key:
        return {"license_status": "unlicensed"}
    lic = await db.licenses.find_one({"key": license_key}, {"_id": 0})
    if not lic:
        return {"license_status": "invalid"}
    if lic.get("blocked"):
        return {"license_status": "blocked", "message": lic.get("blocked_reason", "License revoked")}
    expires_at = lic.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                return {"license_status": "expired", "license_expires_at": expires_at}
        except Exception:
            pass
    return {"license_status": "valid", "license_expires_at": expires_at, "plan": lic.get("plan", "standard")}


# ============================================================
# ADMIN: install roster on HQ deployment
# ============================================================

@router.get("/admin/telemetry/installs")
async def list_installs(current_user: dict = Depends(require_admin)):
    """Return every install that has heartbeat'd. Sorted by last_seen desc."""
    installs = await db.telemetry_installs.find({}, {"_id": 0}).sort("last_seen_at", -1).to_list(2000)
    # Annotate each install with its license status
    for inst in installs:
        inst["license_status_obj"] = await _validate_license_status(inst.get("license_key", ""))
        # Days since last seen
        try:
            last = datetime.fromisoformat(inst["last_seen_at"].replace("Z", "+00:00"))
            inst["days_since_last_seen"] = (datetime.now(timezone.utc) - last).days
        except Exception:
            inst["days_since_last_seen"] = None
    return {"installs": installs, "total": len(installs)}


@router.get("/admin/telemetry/heartbeats/{install_id}")
async def install_heartbeat_history(install_id: str, current_user: dict = Depends(require_admin)):
    """Last 60 heartbeats for one install — for the detail drawer."""
    rows = await db.telemetry_heartbeats.find(
        {"install_id": install_id}, {"_id": 0}
    ).sort("received_at", -1).limit(60).to_list(60)
    return rows


# ============================================================
# ADMIN: license CRUD on HQ deployment
# ============================================================

@router.get("/admin/licenses")
async def list_licenses(current_user: dict = Depends(require_admin)):
    licenses = await db.licenses.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Annotate each with current usage (count of installs using it)
    for lic in licenses:
        usage = await db.telemetry_installs.count_documents({"license_key": lic["key"]})
        lic["installs_using"] = usage
    return licenses


@router.post("/admin/licenses")
async def issue_license(data: dict, current_user: dict = Depends(require_admin)):
    """Body: { org_name, org_id?, expires_at?: iso, plan?: 'standard'|'extended' }"""
    org_name = (data.get("org_name") or "").strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="org_name is required")
    key = secrets.token_urlsafe(24)  # 32-char URL-safe token
    doc = {
        "id": f"lic_{uuid.uuid4().hex[:10]}",
        "key": key,
        "org_name": org_name,
        "org_id": (data.get("org_id") or "").strip(),
        "plan": data.get("plan", "standard"),
        "expires_at": data.get("expires_at") or None,
        "blocked": False,
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.licenses.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "license", doc["id"], {"org_name": org_name, "plan": doc["plan"]})
    return doc


@router.put("/admin/licenses/{license_id}")
async def update_license(license_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Update org_name / expires_at / plan / blocked / blocked_reason."""
    allowed = {"org_name", "org_id", "expires_at", "plan", "blocked", "blocked_reason"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    res = await db.licenses.update_one({"id": license_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="License not found")
    await _audit(current_user["id"], "update", "license", license_id, update)
    return await db.licenses.find_one({"id": license_id}, {"_id": 0})


@router.delete("/admin/licenses/{license_id}")
async def delete_license(license_id: str, current_user: dict = Depends(require_admin)):
    lic = await db.licenses.find_one({"id": license_id}, {"_id": 0})
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    await db.licenses.delete_one({"id": license_id})
    await _audit(current_user["id"], "delete", "license", license_id, {"key_prefix": lic.get("key", "")[:6]})
    return {"deleted": True}


# ============================================================
# DESKTOP CLIENT-SIDE LICENSE STORAGE (per-install)
# Each install also exposes a tiny self-status endpoint via FastAPI so the
# Tauri shell + the React layout can read its own license status from the
# local backend (no round-trip to HQ for every page load).
# ============================================================

@router.get("/license/self")
async def license_self_status():
    """Returns this install's own license + last-known status.

    Stored under db.local_install (single doc, id='install') — written by the
    desktop's /api/license/configure endpoint."""
    doc = await db.local_install.find_one({"id": "install"}, {"_id": 0})
    if not doc:
        return {"install_id": None, "license_key": "", "license_status": "unlicensed", "configured": False}
    return doc


@router.post("/license/configure")
async def license_configure(data: dict, current_user: dict = Depends(require_admin)):
    """Admin pastes their license key + (optionally) the HQ heartbeat URL.

    Body: { license_key, hq_url?, telemetry_enabled?: bool }
    """
    update = {
        "id": "install",
        "license_key": (data.get("license_key") or "").strip(),
        "hq_url": (data.get("hq_url") or "https://hq.5812-global.org").strip(),
        "telemetry_enabled": bool(data.get("telemetry_enabled", True)),
        "configured": True,
        "configured_by": current_user["id"],
        "configured_by_name": current_user.get("name", ""),
        "configured_at": datetime.now(timezone.utc).isoformat(),
    }
    # Auto-generate install_id if missing (first config)
    existing = await db.local_install.find_one({"id": "install"}, {"_id": 0, "install_id": 1})
    if existing and existing.get("install_id"):
        update["install_id"] = existing["install_id"]
    else:
        update["install_id"] = str(uuid.uuid4())
    await db.local_install.update_one({"id": "install"}, {"$set": update}, upsert=True)
    await _audit(current_user["id"], "update", "license_config", "install", {"telemetry_enabled": update["telemetry_enabled"]})
    return await db.local_install.find_one({"id": "install"}, {"_id": 0})
