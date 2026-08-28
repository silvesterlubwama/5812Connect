"""Security Checkpoint Kiosk — gate access control for restricted locations.

Package layout (iter 146 refactor):
  - `_common.py`            helpers (session resolver, subject/decision/log builders, broadcast)
  - `ocr.py`                OCR endpoints (uses shared helper from this file)
  - `__init__.py` (this)    endpoint definitions + router/ocr_router exports
"""
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect
from deps import db, get_current_user, require_admin, require_director, _audit, logger, has_module_access
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets  # still used by pair_device for raw_token generation

# Shared primitives — see _common.py for the bodies.
from .ocr import _ocr_id_image  # noqa: F401 — exposed for the ocr_router below
from . import logbook_lookup as _logbook_lookup
from ._common import (  # noqa: F401
    CHECKPOINT_SESSION_TTL_HOURS, SCAN_RESET_SECONDS, ROLES_ALLOWED_TO_SCAN_FROM_SECURITY,
    _checkpoint_rooms,
    _hash, _gen_pin, _resolve_session, _broadcast_to_checkpoint,
    _resolve_subject, _hydrate_subject, _shape_subject, _decide, _build_visitor_log,
)

router = APIRouter(prefix="/api/security", tags=["security_checkpoint"])

# A second router exposing the same shared OCR helper at `/api/ocr/id` for any
# authenticated staff workflow (member profile pre-fill, document upload, etc.).
ocr_router = APIRouter(prefix="/api/ocr", tags=["ocr"])

# Attach endpoint groups that live in dedicated modules to keep this __init__ readable.
_logbook_lookup.register(router)


# ============================================================
# ADMIN: create / list / manage checkpoints
# ============================================================

@router.post("/checkpoints")
async def create_checkpoint(data: dict, current_user: dict = Depends(require_director)):
    """Body: { name, location_id, requires_id_for_one_time?: true, description?,
              kind?: 'strict'|'hybrid'|'check_in_only', device_mode?: 'dual_device'|'single_device',
              auto_check_in_event_id?: str }"""
    name = (data.get("name") or "").strip()
    location_id = (data.get("location_id") or "").strip()
    if not name or not location_id:
        raise HTTPException(status_code=400, detail="name and location_id are required")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "id": 1, "name": 1})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    kind = (data.get("kind") or "strict").lower()
    if kind not in {"strict", "hybrid", "check_in_only"}:
        raise HTTPException(status_code=400, detail="kind must be strict | hybrid | check_in_only")
    device_mode = (data.get("device_mode") or "dual_device").lower()
    if device_mode not in {"dual_device", "single_device"}:
        raise HTTPException(status_code=400, detail="device_mode must be dual_device | single_device")
    pin = _gen_pin()
    doc = {
        "id": f"cpk_{uuid.uuid4().hex[:10]}",
        "name": name,
        "description": data.get("description", ""),
        "location_id": location_id,
        "location_name": loc.get("name"),
        "pairing_pin": pin,  # cleartext intentionally — admin sees + can rotate
        "active": True,
        "kind": kind,                # strict = restricted-loc gate, hybrid = also accepts event tickets, check_in_only = no gating just log
        "device_mode": device_mode,  # dual_device = guest tablet + security console pair, single_device = operator-only
        "auto_check_in_event_id": (data.get("auto_check_in_event_id") or "").strip(),
        "requires_id_for_one_time": bool(data.get("requires_id_for_one_time", True)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.security_checkpoints.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "security_checkpoint", doc["id"], {"location": loc.get("name"), "kind": kind, "device_mode": device_mode})
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
    allowed = {"name", "description", "active", "requires_id_for_one_time", "kind", "device_mode", "auto_check_in_event_id"}
    update = {k: v for k, v in (data or {}).items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    if "kind" in update and update["kind"] not in {"strict", "hybrid", "check_in_only"}:
        raise HTTPException(status_code=400, detail="kind must be strict | hybrid | check_in_only")
    if "device_mode" in update and update["device_mode"] not in {"dual_device", "single_device"}:
        raise HTTPException(status_code=400, detail="device_mode must be dual_device | single_device")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.security_checkpoints.update_one({"id": checkpoint_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    await _audit(current_user["id"], "update", "security_checkpoint", checkpoint_id, {"changes": list(update.keys())})
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
    await _audit(current_user["id"], "rotate_pin", "security_checkpoint", checkpoint_id)
    return {"checkpoint_id": checkpoint_id, "pairing_pin": pin}


# ============================================================
# PUBLIC-ish: device pairing
# ============================================================

@router.post("/checkpoint/pair")
async def pair_device(data: dict, request: Request):
    """Body: { pin, mode: 'guest'|'security', device_label? }
    Returns: { session_token, checkpoint, expires_at }
    Anyone with the PIN can pair — that's by design (private security contractor).

    Brute-force mitigation: a per-IP counter in `security_pair_attempts` enforces a
    short cooldown after 5 bad PINs in 60s. Combined with the 1,000,000-PIN space,
    this caps brute-forcing well below feasibility.
    """
    import asyncio
    pin = (data.get("pin") or "").strip()
    mode = (data.get("mode") or "").strip().lower()
    if not pin or len(pin) != 6 or not pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be 6 digits")
    if mode not in {"guest", "security"}:
        raise HTTPException(status_code=400, detail="mode must be 'guest' or 'security'")
    # Identify the client (best-effort)
    client_ip = "anon"
    try:
        if request is not None:
            client_ip = (request.client.host if request.client else "") or request.headers.get("x-forwarded-for", "anon").split(",")[0].strip()
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(seconds=60)).isoformat()
    recent_bad = await db.security_pair_attempts.count_documents(
        {"ip": client_ip, "ok": False, "at": {"$gte": cutoff_iso}},
    )
    if recent_bad >= 5:
        # Hard back-off; force operator to wait.
        raise HTTPException(status_code=429, detail="Too many failed pairing attempts — wait a minute and try again")
    cp = await db.security_checkpoints.find_one({"pairing_pin": pin, "active": True}, {"_id": 0})
    if not cp:
        await db.security_pair_attempts.insert_one({"ip": client_ip, "at": now.isoformat(), "ok": False})
        await asyncio.sleep(0.4)  # tarpit
        raise HTTPException(status_code=401, detail="Invalid PIN")
    # Single-device checkpoints only allow `security` mode — guest tablet is not used.
    if cp.get("device_mode") == "single_device" and mode == "guest":
        raise HTTPException(status_code=400, detail="This checkpoint is single-device — pair as 'security' instead")
    await db.security_pair_attempts.insert_one({"ip": client_ip, "at": now.isoformat(), "ok": True, "checkpoint_id": cp["id"]})
    raw_token = secrets.token_urlsafe(32)
    expires_at = (now + timedelta(hours=CHECKPOINT_SESSION_TTL_HOURS)).isoformat()
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
    # Classify the subject as `resident` of this checkpoint's location vs `visitor`.
    # Residents (and resident children) scan in/out of their own premises constantly —
    # they belong in the audit log but should NOT clutter the daily visitor count.
    cp_loc = cp.get("location_id")
    is_resident_here = bool(
        subject.get("is_resident")
        and subject.get("resident_location_id") == cp_loc
        and cp_loc
    )
    subject_type = "resident" if is_resident_here else "visitor"
    # STRAY-resident detection: a resident OF SOMEWHERE ELSE scanning at THIS checkpoint.
    # Surface their home location so security knows where they belong.
    stray_home = None
    if (
        not is_resident_here
        and subject.get("is_resident")
        and subject.get("resident_location_id")
        and subject.get("resident_location_id") != cp_loc
    ):
        home = await db.locations.find_one(
            {"id": subject["resident_location_id"]},
            {"_id": 0, "id": 1, "name": 1, "is_restricted": 1},
        )
        if home:
            stray_home = {
                "id": home["id"],
                "name": home.get("name"),
                "is_restricted": bool(home.get("is_restricted")),
            }
    # Detect entry vs exit by checking today's open entries — if the same person already
    # has an "entry" today without an exit, this scan is recorded as their exit.
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    direction = "entry"
    if subject.get("id"):
        # An "entry" event is the most recent today-entry for this subject that has NO matching exit yet.
        prior = await db.security_checkpoint_events.find_one(
            {
                "checkpoint_id": cp["id"],
                "created_at": {"$gte": today_iso},
                "subject.id": subject["id"],
                "direction": "entry",
                "exit_event_id": {"$exists": False},
                "decision": "approved",
            },
            sort=[("created_at", -1)],
        )
        if prior:
            direction = "exit"
    now = datetime.now(timezone.utc)
    clear_at = (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
    event = {
        "id": f"cev_{uuid.uuid4().hex[:10]}",
        "checkpoint_id": cp["id"],
        "location_id": cp.get("location_id"),
        "kind": "entry_scan",
        "direction": direction,
        "subject_type": subject_type,
        "stray_home": stray_home,
        "scan_type": scan_type,
        "payload": payload,
        "subject": subject,
        "decision": decision,
        "reason": reason if not is_resident_here else f"{reason} (resident)",
        "from_session_id": sess["id"],
        "from_mode": sess.get("mode"),
        "created_at": now.isoformat(),
        "clear_at": clear_at,
    }
    await db.security_checkpoint_events.insert_one(event)
    # If this is an exit scan, link it back to the matching entry so logbook can render the pair
    if direction == "exit" and subject.get("id"):
        try:
            # motor's update_one does NOT accept a `sort` arg — use find_one_and_update.
            await db.security_checkpoint_events.find_one_and_update(
                {
                    "checkpoint_id": cp["id"],
                    "created_at": {"$gte": today_iso},
                    "subject.id": subject["id"],
                    "direction": "entry",
                    "exit_event_id": {"$exists": False},
                    "decision": "approved",
                },
                {"$set": {"exit_event_id": event["id"], "exit_at": now.isoformat()}},
                sort=[("created_at", -1)],
            )
        except Exception as _e:
            logger.warning(f"exit linking failed: {_e}")
    # Hybrid: auto-mark event check-in on db.checkins so Events page shows it
    if subject.get("kind") == "event_ticket" and decision == "approved" and direction == "entry":
        try:
            await db.checkins.insert_one({
                "id": f"chk_{uuid.uuid4().hex[:10]}",
                "member_name": subject.get("name"),
                "member_email": subject.get("email"),
                "member_phone": subject.get("phone"),
                "type": "event_ticket",
                "method": "security_checkpoint",
                "event_id": subject.get("event_id"),
                "event_title": subject.get("event_title"),
                "ticket_id": subject.get("id"),
                "booking_id": subject.get("booking_id"),
                "location_id": cp.get("location_id"),
                "checkpoint_id": cp["id"],
                "checked_in_at": now.isoformat(),
            })
        except Exception as e:
            logger.warning(f"event ticket auto-checkin failed: {e}")
    event.pop("_id", None)
    await _broadcast_to_checkpoint(cp["id"], {"type": "event", "event": event})
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
    # Live "still inside" tile — quick counts that the operator wants up top.
    today_iso = now_iso[:10]
    pipeline = [
        {"$match": {
            "checkpoint_id": cp["id"],
            "created_at": {"$gte": today_iso},
            "decision": "approved",
            "kind": "entry_scan",
            "direction": "entry",
            "exit_event_id": {"$exists": False},
        }},
        {"$group": {"_id": "$subject_type", "n": {"$sum": 1}}},
    ]
    cur_counts = {"visitors_inside": 0, "residents_inside": 0}
    async for row in db.security_checkpoint_events.aggregate(pipeline):
        if row["_id"] == "resident":
            cur_counts["residents_inside"] = row["n"]
        else:
            cur_counts["visitors_inside"] = row["n"]
    cp.pop("pairing_pin", None)
    return {
        "checkpoint": cp,
        "mode": sess.get("mode"),
        "current": current,
        "history": history,
        "counts": cur_counts,
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
    await _broadcast_to_checkpoint(cp_id, {"type": "clear", "by": sess.get("mode")})
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
            from upload_helper import save_upload_sync
            id_url = save_upload_sync("checkpoint-ids", fname, data_bytes, id_image.content_type or "image/jpeg")
        except Exception as e:
            logger.warning(f"checkpoint id upload failed: {e}")
            id_url = None
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
    await _broadcast_to_checkpoint(cp["id"], {"type": "event", "event": event})
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
    await _broadcast_to_checkpoint(sess["checkpoint_id"], {"type": "event", "event": event})
    return event


# ============================================================
# WEBSOCKET — real-time push to paired devices (polling stays as fallback)
# ============================================================

@router.websocket("/checkpoint/ws")
async def checkpoint_ws(websocket: WebSocket, session: Optional[str] = None):
    """Connect via `wss://.../api/security/checkpoint/ws?session=<token>`.
    Pushes `{type:'event'|'clear'}` messages to the device whenever the
    checkpoint state changes — eliminates the 1.5s poll latency."""
    if not session:
        await websocket.close(code=4401)
        return
    sess_doc = await db.security_checkpoint_sessions.find_one({"token_hash": _hash(session)}, {"_id": 0})
    if not sess_doc or sess_doc.get("revoked") or sess_doc.get("expires_at", "") <= datetime.now(timezone.utc).isoformat():
        await websocket.close(code=4401)
        return
    cp_id = sess_doc["checkpoint_id"]
    await websocket.accept()
    room = _checkpoint_rooms.setdefault(cp_id, set())
    room.add(websocket)
    try:
        await websocket.send_json({"type": "joined", "checkpoint_id": cp_id, "mode": sess_doc.get("mode")})
        # Keep the socket alive — we don't expect inbound messages but tolerate pings.
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        room.discard(websocket)

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


# ============================================================
# OCR — best-effort ID extraction via Gemini vision
# ============================================================

# Optional language hint → injected into the OCR system prompt so the model knows
# what script to expect (Arabic, Cyrillic, CJK, etc.). Defaults to English/Latin.
@router.post("/checkpoint/ocr-id")
async def ocr_id_photo(
    image: UploadFile = File(...),
    language: Optional[str] = Form(None),
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Extract Name / Date of Birth / ID Number from a captured ID photo.
    Returns: { name, date_of_birth, id_number, raw_text, confidence, language_hint }.
    Security-device only. Best-effort — operator should always confirm before saving.
    Optional `language` hint (en|fr|es|pt|sw|lg|ar|ru|zh|ja|ko|th|hi|am) helps Gemini
    pick the right script — defaults to English/Latin."""
    sess = await _resolve_session(session_token)
    if sess.get("mode") != "security":
        raise HTTPException(status_code=403, detail="OCR is security-device only")
    return await _ocr_id_image(image, language, sess["id"])


# ============================================================
# STAFF-AUTH WRAPPER — same OCR pipeline for any authenticated workflow
# ============================================================

@ocr_router.post("/id")
async def ocr_id_staff(
    image: UploadFile = File(...),
    language: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Staff-auth wrapper around the same OCR pipeline used by the security
    checkpoint. Used by `/people` profile edit to pre-fill name + DOB + national_id
    when an admin uploads a member's ID photo. Returns the same shape."""
    return await _ocr_id_image(image, language, f"staff_{current_user['id']}")


# ============================================================
# RECEIPT-DENIAL SUPERVISOR OVERRIDE
# ============================================================

@router.post("/checkpoint/receipt-override")
async def receipt_override(
    data: dict,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Supervisor override for a denied exit-scan. Body: { event_id, supervisor_pin, reason? }.
    The supervisor PIN must match an active user with role in
    {admin, system_admin, Executive Director, Adviser, Director, Manager} AND
    the user must have a non-empty `pin` set. Flips the event decision from
    'denied' → 'approved' and writes a supervisor_override audit trail on the event."""
    sess = await _resolve_session(session_token)
    if sess.get("mode") != "security":
        raise HTTPException(status_code=403, detail="Only the security console can override")
    event_id = (data.get("event_id") or "").strip()
    supervisor_pin = (data.get("supervisor_pin") or "").strip()
    reason = (data.get("reason") or "").strip()
    if not event_id or not supervisor_pin:
        raise HTTPException(status_code=400, detail="event_id and supervisor_pin are required")
    if len(supervisor_pin) < 4:
        raise HTTPException(status_code=400, detail="Supervisor PIN must be at least 4 digits")
    event = await db.security_checkpoint_events.find_one(
        {"id": event_id, "checkpoint_id": sess["checkpoint_id"]},
        {"_id": 0},
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("kind") not in {"exit_scan", "entry_scan"}:
        raise HTTPException(status_code=400, detail="Only exit/entry scans can be overridden")
    if event.get("decision") != "denied":
        raise HTTPException(status_code=400, detail="Event is not in a denied state")
    SUPERVISOR_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director", "Manager"}
    supervisor = await db.users.find_one(
        {"pin": supervisor_pin, "status": "active", "role": {"$in": list(SUPERVISOR_ROLES)}},
        {"_id": 0, "id": 1, "name": 1, "role": 1},
    )
    if not supervisor:
        raise HTTPException(status_code=401, detail="Invalid supervisor PIN — must belong to a Manager+ active user")
    now_iso = datetime.now(timezone.utc).isoformat()
    new_clear = (datetime.now(timezone.utc) + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
    update = {
        "decision": "approved",
        "reason": f"Supervisor override by {supervisor['name']} ({supervisor['role']})" + (f" — {reason}" if reason else ""),
        "supervisor_override": {
            "supervisor_id": supervisor["id"],
            "supervisor_name": supervisor["name"],
            "supervisor_role": supervisor["role"],
            "reason": reason,
            "at": now_iso,
            "original_decision": "denied",
            "original_reason": event.get("reason"),
        },
        "clear_at": new_clear,
    }
    await db.security_checkpoint_events.update_one({"id": event_id}, {"$set": update})
    fresh = await db.security_checkpoint_events.find_one({"id": event_id}, {"_id": 0})
    await _broadcast_to_checkpoint(sess["checkpoint_id"], {"type": "event", "event": fresh})
    await _audit(
        supervisor["id"], "override", "checkpoint_event", event_id,
        {"checkpoint_id": sess["checkpoint_id"], "reason": reason or "exit denied — supervisor cleared"},
    )
    return fresh


# ============================================================
# DASHBOARD WIDGET — live checkpoint situational awareness
# ============================================================

@router.get("/dashboard/checkpoints")
async def dashboard_checkpoints(current_user: dict = Depends(require_director)):
    """Returns the active checkpoints in the org with last-5 events + paired-device counts.
    Used by the Dashboard 'Live Checkpoint Map' widget."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cps = await db.security_checkpoints.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
    # Strip the cleartext PIN so dashboard viewers can't memorise it
    for c in cps:
        c.pop("pairing_pin", None)
        c["paired_devices"] = await db.security_checkpoint_sessions.count_documents(
            {"checkpoint_id": c["id"], "expires_at": {"$gt": now_iso}, "revoked": {"$ne": True}}
        )
        c["recent_events"] = await db.security_checkpoint_events.find(
            {"checkpoint_id": c["id"]}, {"_id": 0},
        ).sort("created_at", -1).limit(5).to_list(5)
        # Today's totals for the at-a-glance counters
        today_iso = now_iso[:10]
        c["today_approved"] = await db.security_checkpoint_events.count_documents(
            {"checkpoint_id": c["id"], "decision": "approved", "created_at": {"$gte": today_iso}},
        )
        c["today_denied"] = await db.security_checkpoint_events.count_documents(
            {"checkpoint_id": c["id"], "decision": "denied", "created_at": {"$gte": today_iso}},
        )
        c["holding_ids"] = await db.security_one_time_entries.count_documents(
            {"checkpoint_id": c["id"], "id_returned": False},
        )
    return cps

