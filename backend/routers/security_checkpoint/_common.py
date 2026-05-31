"""Shared helpers + constants for the security_checkpoint package.

The package is split into endpoint-group modules (admin, pairing, scan, grants,
logbook, lookup, dashboard, ocr) — they all import their primitives from here.

Routers themselves live on the package's `__init__.py` so every sub-module
imports the same instance and attaches its endpoints.
"""
from fastapi import HTTPException
from datetime import datetime, timezone
from typing import Optional
import hashlib
import secrets
import uuid  # re-exported for sub-modules

from deps import db, logger  # noqa: F401 — re-exported

# ====== CONSTANTS ======
CHECKPOINT_SESSION_TTL_HOURS = 12
SCAN_RESET_SECONDS = 15
ROLES_ALLOWED_TO_SCAN_FROM_SECURITY = {
    "admin", "system_admin", "Executive Director", "Adviser", "Director",
    "Security Contractor",
}

# Per-checkpoint live socket rooms — populated by the WebSocket endpoint, drained
# by `_broadcast_to_checkpoint`. Lives at module scope so every sub-module can broadcast.
_checkpoint_rooms: dict = {}


# ====== CRYPTO + PIN HELPERS ======

def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _gen_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


# ====== SESSION RESOLVER ======

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


# ====== BROADCAST ======

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


# ====== SUBJECT RESOLUTION + SHAPING ======

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


async def _resolve_subject(scan_type: str, payload: str) -> dict:
    """Best-effort lookup of the subject the scan represents."""
    payload = (payload or "").strip()
    if not payload:
        return {"kind": "unknown", "payload": ""}
    # Event ticket QR
    if payload.startswith("TKT-") or payload.startswith("TKT_"):
        booking = await db.public_bookings.find_one({"ticket_ids": payload}, {"_id": 0})
        if booking:
            event = await db.events.find_one(
                {"id": booking.get("event_id")},
                {"_id": 0, "id": 1, "title": 1, "date": 1},
            )
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
        badge = await db.wallet_badges.find_one(
            {"$or": [{"token": payload}, {"qr_token": payload}]}, {"_id": 0},
        )
        if badge:
            owner_id = badge.get("member_id") or badge.get("user_id") or badge.get("child_id")
            owner_kind = badge.get("subject_kind") or ("child" if badge.get("child_id") else "member")
            if owner_id:
                return await _hydrate_subject(owner_kind, owner_id)
    if scan_type == "qr":
        badge = await db.wallet_badges.find_one(
            {"$or": [{"qr_token": payload}, {"token": payload}]}, {"_id": 0},
        )
        if badge:
            owner_id = badge.get("member_id") or badge.get("user_id") or badge.get("child_id")
            owner_kind = badge.get("subject_kind") or ("child" if badge.get("child_id") else "member")
            if owner_id:
                return await _hydrate_subject(owner_kind, owner_id)
        if payload.startswith("mem_") or payload.startswith("gst_"):
            return await _hydrate_subject("member", payload)
        if payload.startswith("chd_"):
            return await _hydrate_subject("child", payload)
        for kind, coll in (("user", db.users), ("member", db.members), ("child", db.children)):
            proj = {"_id": 0, "password_hash": 0, "pin_hash": 0} if kind == "user" else {"_id": 0}
            doc = await coll.find_one({"id": payload}, proj)
            if doc:
                return _shape_subject(kind, doc)
    # Fallback by phone / email / national_id
    m = await db.members.find_one(
        {"$or": [{"national_id": payload}, {"phone": payload}, {"email": payload.lower()}]},
        {"_id": 0},
    )
    if m:
        return _shape_subject("member", m)
    return {"kind": "unknown", "payload": payload}


# ====== ACCESS DECISION ======

def _decide(checkpoint: dict, subject: dict) -> tuple:
    """Decide whether the subject is approved for entry at this checkpoint."""
    if subject.get("kind") == "unknown":
        return "denied", "Could not identify this badge/QR"
    if subject.get("kind") == "event_ticket":
        if (checkpoint.get("kind") or "strict") in {"hybrid", "check_in_only"}:
            return "approved", f"Event ticket: {subject.get('event_title') or subject.get('event_id')}"
        return "denied", "Event tickets are not accepted at this checkpoint"
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
    if subject.get("is_resident") and subject.get("resident_location_id") == loc_id:
        return "approved", "Resident of this location"
    if loc_id in user_locs:
        return "approved", "Assigned to this location"
    role = subject.get("role") or ""
    if role in {"admin", "system_admin", "Executive Director", "Adviser", "Director"}:
        return "approved", f"{role} — privileged access"
    if subject.get("has_restricted_access"):
        return "approved", "Granted restricted-access privilege"
    return "denied", "Not assigned to this restricted location"


# ====== VISITOR LOG BUILDER ======

async def _build_visitor_log(checkpoint_id: str, date_iso: str, include_residents: bool = False, residents_only: bool = False) -> dict:
    """Collapse approved entry/exit events for a checkpoint on one day into rows.
    Filters:
      - residents_only=True → only resident rows.
      - include_residents=False (default) → only visitor rows.
      - include_residents=True → both visitors + residents.
    `counts` is ALWAYS the full picture so dashboards can use either endpoint.
    """
    from datetime import timedelta
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
    counts = {
        "visitors_entered": 0, "visitors_inside": 0,
        "residents_entered": 0, "residents_inside": 0,
    }
    for ev in events:
        subj = ev.get("subject") or {}
        if ev.get("direction") == "exit":
            continue
        stype = ev.get("subject_type") or "visitor"
        still_in = not bool(ev.get("exit_event_id"))
        if stype == "resident":
            counts["residents_entered"] += 1
            if still_in:
                counts["residents_inside"] += 1
            if not include_residents and not residents_only:
                continue
        else:
            counts["visitors_entered"] += 1
            if still_in:
                counts["visitors_inside"] += 1
            if residents_only:
                continue
        rows.append({
            "entry_event_id": ev["id"],
            "entry_at": ev.get("created_at"),
            "subject_kind": subj.get("kind"),
            "subject_id": subj.get("id"),
            "subject_type": stype,
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
            "still_inside": still_in,
            "reason": ev.get("reason"),
        })
    return {"date": date_iso, "rows": rows, "counts": counts, "include_residents": include_residents}
