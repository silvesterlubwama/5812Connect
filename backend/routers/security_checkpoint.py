"""Security Checkpoint Kiosk — gate access control for restricted locations.

Architecture:
  • An admin creates a `SecurityCheckpoint` for a restricted location and receives
    a 6-digit pairing PIN. Two devices (guest-facing + security-contractor-facing)
    enter the same PIN and pick their mode → a checkpoint session is created.
  • Scans on either device hit POST /scan → backend resolves the subject, checks
    permissions, and writes a `CheckpointEvent`. Both devices poll
    /checkpoints/{id}/state every 1.5s to see the latest event.
  • Auto-resets 15s after a scan (server-side `clear_at`).
  • Security can grant ONE-TIME entry with name+phone+ID photo evidence.
  • Receipt exit-scan: look up sale → list items, flag any `is_exit_restricted`.

Auth model:
  • Admin endpoints (create/list/rotate) require admin/Director.
  • Device-pair endpoints (/pair, /scan, /state, /grant-one-time, /finish) require
    the device's session token returned by /pair.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from deps import db, get_current_user, require_admin, require_director, _audit, logger, has_module_access
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets
import hashlib

router = APIRouter(prefix="/api/security", tags=["security_checkpoint"])

CHECKPOINT_SESSION_TTL_HOURS = 12
SCAN_RESET_SECONDS = 15
ROLES_ALLOWED_TO_SCAN_FROM_SECURITY = {
    "admin", "system_admin", "Executive Director", "Adviser", "Director",
    "Security Contractor",
}


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _gen_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


async def _resolve_session(session_token: Optional[str]) -> dict:
    """Verify the X-Checkpoint-Session header and return the session document."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing checkpoint session token")
    token_hash = _hash(session_token)
    sess = await db.security_checkpoint_sessions.find_one({"token_hash": token_hash}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid checkpoint session")
    if sess.get("expires_at", "") <= datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=401, detail="Checkpoint session expired — pair the device again")
    if sess.get("revoked"):
        raise HTTPException(status_code=401, detail="Session revoked")
    return sess


# ============================================================
# ADMIN: create / list / manage checkpoints
# ============================================================

@router.post("/checkpoints")
async def create_checkpoint(data: dict, current_user: dict = Depends(require_director)):
    """Body: { name, location_id, requires_id_for_one_time?: true, description? }"""
    name = (data.get("name") or "").strip()
    location_id = (data.get("location_id") or "").strip()
    if not name or not location_id:
        raise HTTPException(status_code=400, detail="name and location_id are required")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "id": 1, "name": 1})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    pin = _gen_pin()
    doc = {
        "id": f"cpk_{uuid.uuid4().hex[:10]}",
        "name": name,
        "description": data.get("description", ""),
        "location_id": location_id,
        "location_name": loc.get("name"),
        "pairing_pin": pin,  # cleartext intentionally — admin sees + can rotate
        "active": True,
        "requires_id_for_one_time": bool(data.get("requires_id_for_one_time", True)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.security_checkpoints.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "security_checkpoint", doc["id"], {"location": loc.get("name")})
    return doc


@router.get("/checkpoints")
async def list_checkpoints(current_user: dict = Depends(require_director)):
    """List all checkpoints with their pairing PIN visible to admins."""
    rows = await db.security_checkpoints.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Attach live session counts
    for r in rows:
        r["paired_devices"] = await db.security_checkpoint_sessions.count_documents(
            {"checkpoint_id": r["id"], "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}, "revoked": {"$ne": True}}
        )
    return rows


@router.put("/checkpoints/{checkpoint_id}")
async def update_checkpoint(checkpoint_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "description", "active", "requires_id_for_one_time"}
    update = {k: v for k, v in (data or {}).items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.security_checkpoints.update_one({"id": checkpoint_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return await db.security_checkpoints.find_one({"id": checkpoint_id}, {"_id": 0})


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(checkpoint_id: str, current_user: dict = Depends(require_admin)):
    """Delete a checkpoint and revoke all its sessions."""
    cp = await db.security_checkpoints.find_one({"id": checkpoint_id}, {"_id": 0})
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    await db.security_checkpoint_sessions.update_many({"checkpoint_id": checkpoint_id}, {"$set": {"revoked": True}})
    await db.security_checkpoints.delete_one({"id": checkpoint_id})
    await _audit(current_user["id"], "delete", "security_checkpoint", checkpoint_id)
    return {"deleted": True}


@router.post("/checkpoints/{checkpoint_id}/rotate-pin")
async def rotate_pin(checkpoint_id: str, current_user: dict = Depends(require_director)):
    """Regenerate the pairing PIN AND revoke every currently-paired device."""
    pin = _gen_pin()
    res = await db.security_checkpoints.update_one(
        {"id": checkpoint_id},
        {"$set": {"pairing_pin": pin, "pin_rotated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    await db.security_checkpoint_sessions.update_many({"checkpoint_id": checkpoint_id}, {"$set": {"revoked": True}})
    return {"checkpoint_id": checkpoint_id, "pairing_pin": pin}


# ============================================================
# PUBLIC-ish: device pairing
# ============================================================

@router.post("/checkpoint/pair")
async def pair_device(data: dict):
    """Body: { pin, mode: 'guest'|'security', device_label? }
    Returns: { session_token, checkpoint, expires_at }
    Anyone with the PIN can pair — that's by design (private security contractor).
    """
    pin = (data.get("pin") or "").strip()
    mode = (data.get("mode") or "").strip().lower()
    if not pin or len(pin) != 6 or not pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be 6 digits")
    if mode not in {"guest", "security"}:
        raise HTTPException(status_code=400, detail="mode must be 'guest' or 'security'")
    cp = await db.security_checkpoints.find_one({"pairing_pin": pin, "active": True}, {"_id": 0})
    if not cp:
        raise HTTPException(status_code=401, detail="Invalid PIN")
    raw_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=CHECKPOINT_SESSION_TTL_HOURS)).isoformat()
    sess = {
        "id": f"cps_{uuid.uuid4().hex[:10]}",
        "checkpoint_id": cp["id"],
        "token_hash": _hash(raw_token),
        "mode": mode,
        "device_label": (data.get("device_label") or f"{mode}-device")[:80],
        "expires_at": expires_at,
        "revoked": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.security_checkpoint_sessions.insert_one(sess)
    cp.pop("pairing_pin", None)  # never leak PIN back to a paired device
    return {
        "session_token": raw_token,
        "checkpoint": cp,
        "mode": mode,
        "expires_at": expires_at,
        "ttl_hours": CHECKPOINT_SESSION_TTL_HOURS,
    }


@router.post("/checkpoint/unpair")
async def unpair_device(authorization: Optional[str] = Header(None, alias="X-Checkpoint-Session")):
    if not authorization:
        return {"unpaired": True}
    await db.security_checkpoint_sessions.update_one(
        {"token_hash": _hash(authorization)}, {"$set": {"revoked": True}},
    )
    return {"unpaired": True}


# ============================================================
# DEVICE: scan, state, grant, finish
# ============================================================

async def _resolve_subject(scan_type: str, payload: str) -> dict:
    """Best-effort lookup of the subject the scan represents.
    Returns: { kind, id, name, role?, email?, photo_url?, has_restricted_access?, ... }
    or { kind: 'unknown', payload } if we can't resolve."""
    payload = (payload or "").strip()
    if not payload:
        return {"kind": "unknown", "payload": ""}
    if scan_type == "nfc":
        # Existing badge issuance writes the wallet_badges.token as the NFC payload.
        badge = await db.wallet_badges.find_one({"$or": [{"token": payload}, {"qr_token": payload}]}, {"_id": 0})
        if badge:
            owner_id = badge.get("member_id") or badge.get("user_id") or badge.get("child_id")
            owner_kind = badge.get("subject_kind") or ("child" if badge.get("child_id") else "member")
            if owner_id:
                return await _hydrate_subject(owner_kind, owner_id)
    if scan_type == "qr":
        # Try wallet_badges first (token / qr_token), then a raw `mem_*/chd_*/user-uuid` lookup
        badge = await db.wallet_badges.find_one({"$or": [{"qr_token": payload}, {"token": payload}]}, {"_id": 0})
        if badge:
            owner_id = badge.get("member_id") or badge.get("user_id") or badge.get("child_id")
            owner_kind = badge.get("subject_kind") or ("child" if badge.get("child_id") else "member")
            if owner_id:
                return await _hydrate_subject(owner_kind, owner_id)
        # Direct id sniffing by prefix
        if payload.startswith("mem_") or payload.startswith("gst_"):
            return await _hydrate_subject("member", payload)
        if payload.startswith("chd_"):
            return await _hydrate_subject("child", payload)
        # Bare UUID / unknown-prefix string — try every collection in order
        for kind, coll in (("user", db.users), ("member", db.members), ("child", db.children)):
            doc = await coll.find_one({"id": payload}, {"_id": 0, "password_hash": 0, "pin_hash": 0} if kind == "user" else {"_id": 0})
            if doc:
                return _shape_subject(kind, doc)
    # Fallback: try searching by national_id / phone / email
    m = await db.members.find_one(
        {"$or": [{"national_id": payload}, {"phone": payload}, {"email": payload.lower()}]},
        {"_id": 0},
    )
    if m:
        return _shape_subject("member", m)
    return {"kind": "unknown", "payload": payload}


async def _hydrate_subject(kind: str, sid: str) -> dict:
    if kind == "member":
        doc = await db.members.find_one({"id": sid}, {"_id": 0})
    elif kind == "child":
        doc = await db.children.find_one({"id": sid}, {"_id": 0})
    elif kind in {"user", "staff"}:
        doc = await db.users.find_one({"id": sid}, {"_id": 0, "password_hash": 0, "pin_hash": 0})
    else:
        doc = None
    if not doc:
        return {"kind": "unknown", "id": sid}
    return _shape_subject(kind, doc)


def _shape_subject(kind: str, doc: dict) -> dict:
    return {
        "kind": kind,
        "id": doc.get("id"),
        "name": doc.get("name") or doc.get("full_name"),
        "photo_url": doc.get("photo_url"),
        "role": doc.get("role"),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "status": doc.get("status"),
        "location_id": doc.get("location_id"),
        "location_ids": doc.get("location_ids"),
        "has_restricted_access": bool(doc.get("has_restricted_access")),
        "is_resident": bool(doc.get("is_resident")),
        "resident_location_id": doc.get("resident_location_id"),
    }


def _decide(checkpoint: dict, subject: dict) -> tuple:
    """Decide whether the subject is approved for entry at this checkpoint.
    Returns (decision, reason). decision ∈ {approved, denied, unknown}."""
    if subject.get("kind") == "unknown":
        return "denied", "Could not identify this badge/QR"
    if (subject.get("status") or "active") != "active":
        return "denied", f"Profile is {subject.get('status') or 'inactive'}"
    loc_id = checkpoint.get("location_id")
    if not loc_id:
        return "approved", "No restriction set on this checkpoint"
    user_locs = set(subject.get("location_ids") or [])
    if subject.get("location_id"):
        user_locs.add(subject["location_id"])
    # Resident: explicit assignment to this restricted location
    if subject.get("is_resident") and subject.get("resident_location_id") == loc_id:
        return "approved", "Resident of this location"
    # Explicit assignment
    if loc_id in user_locs:
        return "approved", "Assigned to this location"
    # Director+ override regardless of location
    role = subject.get("role") or ""
    if role in {"admin", "system_admin", "Executive Director", "Adviser", "Director"}:
        return "approved", f"{role} — privileged access"
    # Restricted-access explicit flag
    if subject.get("has_restricted_access"):
        return "approved", "Granted restricted-access privilege"
    return "denied", "Not assigned to this restricted location"


@router.post("/checkpoint/scan")
async def checkpoint_scan(
    data: dict,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Body: { scan_type: 'nfc'|'qr'|'manual', payload }
    Auth: device session token. Persists a CheckpointEvent and returns it."""
    sess = await _resolve_session(session_token)
    cp = await db.security_checkpoints.find_one({"id": sess["checkpoint_id"]}, {"_id": 0})
    if not cp or not cp.get("active"):
        raise HTTPException(status_code=403, detail="Checkpoint inactive or removed")
    scan_type = (data.get("scan_type") or "qr").lower()
    if scan_type not in {"nfc", "qr", "manual"}:
        raise HTTPException(status_code=400, detail="Invalid scan_type")
    payload = (data.get("payload") or "").strip()
    if not payload:
        raise HTTPException(status_code=400, detail="payload required")
    subject = await _resolve_subject(scan_type, payload)
    decision, reason = _decide(cp, subject)
    now = datetime.now(timezone.utc)
    clear_at = (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
    event = {
        "id": f"cev_{uuid.uuid4().hex[:10]}",
        "checkpoint_id": cp["id"],
        "location_id": cp.get("location_id"),
        "kind": "entry_scan",
        "scan_type": scan_type,
        "payload": payload,
        "subject": subject,
        "decision": decision,
        "reason": reason,
        "from_session_id": sess["id"],
        "from_mode": sess.get("mode"),
        "created_at": now.isoformat(),
        "clear_at": clear_at,
    }
    await db.security_checkpoint_events.insert_one(event)
    event.pop("_id", None)
    return event


@router.get("/checkpoint/state")
async def checkpoint_state(
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Live state for both paired devices to poll every ~1.5s.
    Returns the most-recent un-cleared event, plus the last 20 events for the security console."""
    sess = await _resolve_session(session_token)
    cp = await db.security_checkpoints.find_one({"id": sess["checkpoint_id"]}, {"_id": 0})
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint missing")
    now_iso = datetime.now(timezone.utc).isoformat()
    # Active = the most recent event whose clear_at > now
    current = await db.security_checkpoint_events.find_one(
        {"checkpoint_id": cp["id"], "clear_at": {"$gt": now_iso}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    history = []
    if sess.get("mode") == "security":
        history = await db.security_checkpoint_events.find(
            {"checkpoint_id": cp["id"]}, {"_id": 0},
        ).sort("created_at", -1).to_list(20)
    cp.pop("pairing_pin", None)
    return {
        "checkpoint": cp,
        "mode": sess.get("mode"),
        "current": current,
        "history": history,
        "now": now_iso,
    }


@router.post("/checkpoint/finish")
async def checkpoint_finish(
    data: Optional[dict] = None,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Manually clear the current event (tap-to-finish before the 15s auto-reset)."""
    sess = await _resolve_session(session_token)
    cp_id = sess["checkpoint_id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.security_checkpoint_events.update_many(
        {"checkpoint_id": cp_id, "clear_at": {"$gt": now_iso}},
        {"$set": {"clear_at": now_iso, "finished_early": True, "finished_by_mode": sess.get("mode")}},
    )
    return {"cleared": res.modified_count}


@router.post("/checkpoint/grant-one-time")
async def grant_one_time_entry(
    name: str = Form(...),
    phone: str = Form(""),
    reason: str = Form(""),
    id_image: Optional[UploadFile] = File(None),
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Security-only — grants a one-time entry. Stores name/phone/reason + optional ID image
    so the contractor can hand the physical ID back when the guest leaves."""
    sess = await _resolve_session(session_token)
    if sess.get("mode") != "security":
        raise HTTPException(status_code=403, detail="Only the security device can grant one-time entries")
    cp = await db.security_checkpoints.find_one({"id": sess["checkpoint_id"]}, {"_id": 0})
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint missing")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Guest name is required")
    if cp.get("requires_id_for_one_time", True) and not id_image:
        raise HTTPException(status_code=400, detail="An ID photo is required for one-time entry at this checkpoint")
    id_url = None
    if id_image and id_image.filename:
        data_bytes = await id_image.read()
        if len(data_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="ID image must be under 8MB")
        ext = id_image.filename.rsplit(".", 1)[-1] if "." in id_image.filename else "jpg"
        fname = f"{cp['id']}_{uuid.uuid4().hex[:10]}.{ext}"
        # Try cloud storage first; fall back to local uploads dir.
        try:
            from storage import put_object
            result = put_object(f"checkpoint-ids/{fname}", data_bytes, id_image.content_type or "image/jpeg")
            id_url = result.get("url", f"/api/storage/checkpoint-ids/{fname}")
        except Exception as e:
            logger.warning(f"checkpoint id cloud put failed, using local: {e}")
            import os as _os
            _os.makedirs("/app/backend/uploads/checkpoint-ids", exist_ok=True)
            with open(f"/app/backend/uploads/checkpoint-ids/{fname}", "wb") as fh:
                fh.write(data_bytes)
            id_url = f"/api/uploads/checkpoint-ids/{fname}"
    now = datetime.now(timezone.utc)
    grant_id = f"otg_{uuid.uuid4().hex[:10]}"
    grant_doc = {
        "id": grant_id,
        "checkpoint_id": cp["id"],
        "location_id": cp.get("location_id"),
        "name": name.strip(),
        "phone": phone.strip(),
        "reason": reason.strip(),
        "id_image_url": id_url,
        "id_returned": False,
        "granted_at": now.isoformat(),
        "granted_by_session_id": sess["id"],
        # ocr_extracted_* fields kept blank for now — OCR is a Phase 2 plug-in.
        "ocr_pending": bool(id_url),
    }
    await db.security_one_time_entries.insert_one(grant_doc)
    # Mirror an event so the guest device flips to "Approved — One-Time Entry"
    clear_at = (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
    event = {
        "id": f"cev_{uuid.uuid4().hex[:10]}",
        "checkpoint_id": cp["id"],
        "location_id": cp.get("location_id"),
        "kind": "one_time_grant",
        "subject": {"kind": "one_time", "name": name.strip(), "phone": phone.strip(), "photo_url": id_url},
        "decision": "approved",
        "reason": f"One-time entry: {reason.strip()[:120] or 'security override'}",
        "one_time_grant_id": grant_id,
        "from_session_id": sess["id"],
        "from_mode": sess.get("mode"),
        "created_at": now.isoformat(),
        "clear_at": clear_at,
    }
    await db.security_checkpoint_events.insert_one(event)
    event.pop("_id", None)
    grant_doc.pop("_id", None)
    return {"grant": grant_doc, "event": event}


@router.post("/checkpoint/one-time/{grant_id}/return-id")
async def mark_id_returned(grant_id: str, session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session")):
    """Security marks the physical ID as handed back to the guest on exit."""
    sess = await _resolve_session(session_token)
    if sess.get("mode") != "security":
        raise HTTPException(status_code=403, detail="Only the security device can mark IDs returned")
    res = await db.security_one_time_entries.update_one(
        {"id": grant_id, "checkpoint_id": sess["checkpoint_id"]},
        {"$set": {"id_returned": True, "id_returned_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Grant not found")
    return {"id_returned": True}


@router.get("/checkpoint/one-time/open")
async def list_open_one_time_entries(session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session")):
    """List one-time entries whose physical ID is still being held by security."""
    sess = await _resolve_session(session_token)
    if sess.get("mode") != "security":
        raise HTTPException(status_code=403, detail="Security device only")
    rows = await db.security_one_time_entries.find(
        {"checkpoint_id": sess["checkpoint_id"], "id_returned": False},
        {"_id": 0},
    ).sort("granted_at", -1).to_list(100)
    return rows


@router.post("/checkpoint/scan/receipt")
async def receipt_exit_scan(
    data: dict,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Exit-scan stub (Phase 1): look up sale by receipt number and return line items.
    Phase 2 will fold in per-item `is_exit_restricted` policy + bulk approval/deny."""
    sess = await _resolve_session(session_token)
    receipt = (data.get("receipt_number") or data.get("payload") or "").strip()
    if not receipt:
        raise HTTPException(status_code=400, detail="receipt_number required")
    sale = await db.sales.find_one(
        {"$or": [{"receipt_number": receipt}, {"id": receipt}]},
        {"_id": 0},
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Receipt not found")
    now = datetime.now(timezone.utc)
    items = [
        {
            "name": it.get("name"), "qty": it.get("qty"),
            "unit_price": it.get("unit_price"),
            "is_exit_restricted": bool(it.get("is_exit_restricted")),
        }
        for it in (sale.get("items") or [])
    ]
    flagged = any(i["is_exit_restricted"] for i in items)
    decision = "denied" if flagged else "approved"
    reason = "Item flagged as exit-restricted" if flagged else "All items cleared for exit"
    event = {
        "id": f"cev_{uuid.uuid4().hex[:10]}",
        "checkpoint_id": sess["checkpoint_id"],
        "kind": "exit_scan",
        "scan_type": "receipt",
        "payload": receipt,
        "subject": {
            "kind": "receipt",
            "name": f"Receipt {sale.get('receipt_number') or sale.get('id')}",
            "customer_name": sale.get("customer_name"),
            "total": sale.get("total"),
            "currency": sale.get("currency"),
            "items": items,
        },
        "decision": decision,
        "reason": reason,
        "from_session_id": sess["id"],
        "from_mode": sess.get("mode"),
        "created_at": now.isoformat(),
        "clear_at": (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat(),
    }
    await db.security_checkpoint_events.insert_one(event)
    event.pop("_id", None)
    return event


# ============================================================
# ADMIN: read-only audit access
# ============================================================

@router.get("/checkpoints/{checkpoint_id}/events")
async def list_checkpoint_events(checkpoint_id: str, limit: int = 200, current_user: dict = Depends(require_director)):
    rows = await db.security_checkpoint_events.find(
        {"checkpoint_id": checkpoint_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(min(limit, 2000))
    return rows


@router.get("/checkpoints/{checkpoint_id}/one-time")
async def list_one_time_entries_admin(checkpoint_id: str, current_user: dict = Depends(require_director)):
    rows = await db.security_one_time_entries.find(
        {"checkpoint_id": checkpoint_id}, {"_id": 0},
    ).sort("granted_at", -1).to_list(500)
    return rows
