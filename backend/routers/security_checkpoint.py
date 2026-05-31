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
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect
from deps import db, get_current_user, require_admin, require_director, _audit, logger, has_module_access
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets
import hashlib

router = APIRouter(prefix="/api/security", tags=["security_checkpoint"])

# A second router exposing the same shared OCR helper at `/api/ocr/id` for any
# authenticated staff workflow (member profile pre-fill, document upload, etc.).
ocr_router = APIRouter(prefix="/api/ocr", tags=["ocr"])

CHECKPOINT_SESSION_TTL_HOURS = 12
SCAN_RESET_SECONDS = 15
ROLES_ALLOWED_TO_SCAN_FROM_SECURITY = {
    "admin", "system_admin", "Executive Director", "Adviser", "Director",
    "Security Contractor",
}

# Per-checkpoint live socket rooms — keyed by checkpoint_id, value is a set of
# active WebSocket connections. Updates posted by scan/grant/finish are pushed
# instantly to every device joined to the room (HTTP polling stays as fallback).
_checkpoint_rooms: dict = {}


async def _broadcast_to_checkpoint(checkpoint_id: str, payload: dict):
    """Best-effort push to every WebSocket joined to a checkpoint room."""
    sockets = list(_checkpoint_rooms.get(checkpoint_id) or [])
    dead = []
    for ws in sockets:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    if dead:
        room = _checkpoint_rooms.get(checkpoint_id) or set()
        for ws in dead:
            room.discard(ws)


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

async def _resolve_subject(scan_type: str, payload: str) -> dict:
    """Best-effort lookup of the subject the scan represents.
    Returns: { kind, id, name, role?, email?, photo_url?, has_restricted_access?, ... }
    or { kind: 'unknown', payload } if we can't resolve."""
    payload = (payload or "").strip()
    if not payload:
        return {"kind": "unknown", "payload": ""}
    # Event ticket QR — format `TKT-XXXX` (issued by /events/.../register). Match early so
    # hybrid checkpoints can auto-check-in.
    if payload.startswith("TKT-") or payload.startswith("TKT_"):
        booking = await db.public_bookings.find_one(
            {"ticket_ids": payload}, {"_id": 0},
        )
        if booking:
            event = await db.events.find_one({"id": booking.get("event_id")}, {"_id": 0, "id": 1, "title": 1, "date": 1})
            return {
                "kind": "event_ticket",
                "id": payload,
                "name": booking.get("name") or "Ticket holder",
                "email": booking.get("email"),
                "phone": booking.get("phone"),
                "event_id": booking.get("event_id"),
                "event_title": (event or {}).get("title"),
                "event_date": (event or {}).get("date"),
                "booking_id": booking.get("id"),
                "num_tickets": booking.get("num_tickets") or 1,
            }
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
    # Event ticket — always approved on hybrid checkpoints, denied on strict-only ones
    if subject.get("kind") == "event_ticket":
        if (checkpoint.get("kind") or "strict") in {"hybrid", "check_in_only"}:
            return "approved", f"Event ticket: {subject.get('event_title') or subject.get('event_id')}"
        return "denied", "Event tickets are not accepted at this checkpoint"
    # check_in_only checkpoints log everyone without restricted-location gating
    if (checkpoint.get("kind") or "strict") == "check_in_only":
        if (subject.get("status") or "active") != "active":
            return "denied", f"Profile is {subject.get('status') or 'inactive'}"
        return "approved", "Check-in only — no access restriction"
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
# VISITOR LOGBOOK — paired entry/exit times per person per day
# ============================================================

async def _build_visitor_log(checkpoint_id: str, date_iso: str) -> list:
    """Collapse all approved entry/exit events for a checkpoint on a single day
    into one row per (subject, entry). Each row carries first-entry time + last-exit time
    so the operator sees who is still inside."""
    if not date_iso:
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_start = date_iso
    day_end = (datetime.fromisoformat(date_iso) + timedelta(days=1)).strftime("%Y-%m-%d")
    events = await db.security_checkpoint_events.find(
        {
            "checkpoint_id": checkpoint_id,
            "created_at": {"$gte": day_start, "$lt": day_end},
            "decision": "approved",
            "kind": "entry_scan",
        },
        {"_id": 0},
    ).sort("created_at", 1).to_list(5000)
    rows = []
    for ev in events:
        subj = ev.get("subject") or {}
        if ev.get("direction") == "exit":
            continue  # exit data is attached via exit_event_id on the entry row
        rows.append({
            "entry_event_id": ev["id"],
            "entry_at": ev.get("created_at"),
            "subject_kind": subj.get("kind"),
            "subject_id": subj.get("id"),
            "name": subj.get("name") or "Unknown",
            "role": subj.get("role"),
            "phone": subj.get("phone"),
            "email": subj.get("email"),
            "photo_url": subj.get("photo_url"),
            "scan_type": ev.get("scan_type"),
            "event_id": subj.get("event_id"),
            "event_title": subj.get("event_title"),
            "exit_event_id": ev.get("exit_event_id"),
            "exit_at": ev.get("exit_at"),
            "still_inside": not bool(ev.get("exit_event_id")),
            "reason": ev.get("reason"),
        })
    return rows


@router.get("/checkpoint/visitor-log")
async def checkpoint_visitor_log_device(
    date: Optional[str] = None,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Device-session-authed visitor log — used by the security console tab."""
    sess = await _resolve_session(session_token)
    return await _build_visitor_log(sess["checkpoint_id"], date or "")


@router.get("/checkpoints/{checkpoint_id}/visitor-log")
async def checkpoint_visitor_log_admin(
    checkpoint_id: str,
    date: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Admin-authed visitor log — same shape as the device endpoint. Used by the
    Admin → Security Checkpoints → View Logbook flow."""
    return await _build_visitor_log(checkpoint_id, date or "")


# ============================================================
# HOUSEHOLD LOOKUP — phone / first-name search → member + family members
# ============================================================

@router.post("/checkpoint/lookup")
async def checkpoint_household_lookup(
    data: dict,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Body: { q }. Searches members + children and returns each match alongside
    its household siblings. Security operator picks the right person and ticks the
    family members actually present."""
    await _resolve_session(session_token)
    q = (data.get("q") or "").strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Search needs at least 2 characters")
    rx = {"$regex": q, "$options": "i"}
    member_matches = await db.members.find(
        {"$or": [{"name": rx}, {"phone": rx}, {"email": rx}, {"national_id": rx}]},
        {"_id": 0, "password_hash": 0, "pin_hash": 0},
    ).limit(20).to_list(20)
    child_matches = await db.children.find(
        {"$or": [{"name": rx}, {"phone": rx}]},
        {"_id": 0},
    ).limit(20).to_list(20)
    family_ids = list({m.get("family_id") for m in member_matches if m.get("family_id")})
    family_ids += list({c.get("family_id") for c in child_matches if c.get("family_id")})
    families = {}
    if family_ids:
        async for fam in db.families.find({"id": {"$in": list(set(family_ids))}}, {"_id": 0}):
            families[fam["id"]] = fam
    out = []
    seen = set()
    member_ids = {m.get("id") for m in member_matches}
    for who in member_matches + child_matches:
        wid = who.get("id")
        if not wid or wid in seen:
            continue
        seen.add(wid)
        fam_id = who.get("family_id")
        family_members = []
        if fam_id:
            siblings_m = await db.members.find(
                {"family_id": fam_id, "id": {"$ne": wid}},
                {"_id": 0, "id": 1, "name": 1, "phone": 1, "role": 1, "photo_url": 1},
            ).to_list(20)
            siblings_c = await db.children.find(
                {"family_id": fam_id, "id": {"$ne": wid}},
                {"_id": 0, "id": 1, "name": 1, "date_of_birth": 1, "photo_url": 1, "grade": 1},
            ).to_list(20)
            for s in siblings_m:
                family_members.append({**s, "kind": "member"})
            for s in siblings_c:
                family_members.append({**s, "kind": "child"})
        kind = "member" if wid in member_ids else "child"
        out.append({
            "kind": kind,
            "id": wid,
            "name": who.get("name"),
            "phone": who.get("phone"),
            "email": who.get("email"),
            "role": who.get("role"),
            "photo_url": who.get("photo_url"),
            "family_id": fam_id,
            "family_name": (families.get(fam_id) or {}).get("name") if fam_id else None,
            "household": family_members,
        })
    return {"q": q, "results": out, "count": len(out)}


@router.post("/checkpoint/check-in-batch")
async def checkpoint_check_in_batch(
    data: dict,
    session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
):
    """Body: { members: [{kind, id}, ...] }
    Manually check in a batch of selected household members. Writes one checkpoint event
    per person + a checkins row per person so they show on /check-ins."""
    sess = await _resolve_session(session_token)
    cp = await db.security_checkpoints.find_one({"id": sess["checkpoint_id"]}, {"_id": 0})
    if not cp:
        raise HTTPException(status_code=404, detail="Checkpoint missing")
    members = data.get("members") or []
    if not isinstance(members, list) or not members:
        raise HTTPException(status_code=400, detail="members[] required")
    now = datetime.now(timezone.utc)
    clear_at = (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
    created = []
    for m in members:
        subject = await _hydrate_subject(m.get("kind") or "member", m.get("id") or "")
        if subject.get("kind") == "unknown":
            continue
        decision, reason = _decide(cp, subject)
        event = {
            "id": f"cev_{uuid.uuid4().hex[:10]}",
            "checkpoint_id": cp["id"],
            "location_id": cp.get("location_id"),
            "kind": "entry_scan",
            "direction": "entry",
            "scan_type": "manual_household",
            "payload": subject.get("id"),
            "subject": subject,
            "decision": decision,
            "reason": reason + " (household batch check-in)",
            "from_session_id": sess["id"],
            "from_mode": sess.get("mode"),
            "created_at": now.isoformat(),
            "clear_at": clear_at,
        }
        await db.security_checkpoint_events.insert_one(event)
        event.pop("_id", None)
        if decision == "approved":
            try:
                await db.checkins.insert_one({
                    "id": f"chk_{uuid.uuid4().hex[:10]}",
                    "member_id": subject.get("id"),
                    "member_name": subject.get("name"),
                    "type": subject.get("kind"),
                    "method": "checkpoint_household",
                    "location_id": cp.get("location_id"),
                    "checkpoint_id": cp["id"],
                    "checked_in_at": now.isoformat(),
                })
            except Exception as e:
                logger.warning(f"household checkin mirror failed: {e}")
        created.append(event)
    if created:
        await _broadcast_to_checkpoint(cp["id"], {"type": "event", "event": created[-1]})
    return {"checked_in": len(created), "events": created}



# ============================================================
# OCR — best-effort ID extraction via Gemini vision
# ============================================================

# Optional language hint → injected into the OCR system prompt so the model knows
# what script to expect (Arabic, Cyrillic, CJK, etc.). Defaults to English/Latin.
_OCR_LANG_HINTS = {
    "en": "English / Latin script",
    "fr": "French / Latin script",
    "es": "Spanish / Latin script",
    "pt": "Portuguese / Latin script",
    "sw": "Swahili / Latin script",
    "lg": "Luganda / Latin script",
    "ar": "Arabic script (right-to-left)",
    "ru": "Cyrillic / Russian script",
    "uk": "Cyrillic / Ukrainian script",
    "zh": "Simplified Chinese (Hanzi)",
    "ja": "Japanese (Kanji + Kana)",
    "ko": "Korean (Hangul)",
    "th": "Thai script",
    "hi": "Devanagari / Hindi script",
    "am": "Amharic / Ge'ez script",
}


async def _ocr_id_image(image: UploadFile, language: Optional[str], session_id_for_log: str) -> dict:
    """Shared OCR pipeline. Used by both /security/checkpoint/ocr-id (device session)
    and the staff-auth wrapper at /ocr/id (admin auth).
    Returns the same {name, date_of_birth, id_number, raw_text, confidence} shape."""
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 8MB")
    # Validate MIME (Gemini accepts jpeg/png/webp)
    mime = (image.content_type or "").lower()
    if mime not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        if data[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WEBP")
    import os as _os
    import json as _json
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix="." + mime.split("/")[-1])
    try:
        with _os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"OCR unavailable: {e}")
        api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="OCR not configured (no LLM key)")
        lang_hint = _OCR_LANG_HINTS.get((language or "en").strip().lower(), "")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"ocr_{session_id_for_log}_{uuid.uuid4().hex[:6]}",
            system_message=(
                "You are an OCR assistant for government-issued ID cards (passports, national IDs, drivers licenses). "
                f"{f'The document is most likely in {lang_hint}. ' if lang_hint else ''}"
                "Transliterate non-Latin names into Latin script if the latin transliteration is printed on the document, "
                "otherwise return the name in its original script.\n"
                "Extract ONLY the following fields and return STRICT JSON — no prose, no markdown:\n"
                "{\"name\": str, \"date_of_birth\": \"YYYY-MM-DD\" or empty, \"id_number\": str, \"raw_text\": str (everything legible), \"confidence\": \"high\"|\"medium\"|\"low\"}\n"
                "If a field is unreadable or absent, return empty string for that field."
            ),
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text=(
                "Extract the holder's full name, date of birth, and primary ID/document number from this ID card. "
                "Return strict JSON as instructed. If the image is not an ID card, set confidence='low' and all fields empty."
            ),
            file_contents=[FileContentWithMimeType(file_path=tmp_path, mime_type=mime)],
        )
        raw = await chat.send_message(msg)
        s = (raw or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:].strip()
        first = s.find("{")
        last = s.rfind("}")
        if first >= 0 and last > first:
            s = s[first:last + 1]
        try:
            parsed = _json.loads(s)
        except Exception:
            parsed = {"name": "", "date_of_birth": "", "id_number": "", "raw_text": (raw or "")[:500], "confidence": "low"}
        out = {
            "name": str(parsed.get("name") or "").strip()[:120],
            "date_of_birth": str(parsed.get("date_of_birth") or "").strip()[:10],
            "id_number": str(parsed.get("id_number") or "").strip()[:60],
            "raw_text": str(parsed.get("raw_text") or "")[:2000],
            "confidence": str(parsed.get("confidence") or "low").lower() if parsed.get("confidence") else "low",
            "language_hint": (language or "en").lower(),
        }
        if out["confidence"] not in {"high", "medium", "low"}:
            out["confidence"] = "low"
        return out
    finally:
        try: _os.remove(tmp_path)
        except Exception: pass


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

