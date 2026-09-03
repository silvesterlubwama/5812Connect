"""Events, Check-ins, Venues, Event Types, Public Events routes"""
from fastapi import APIRouter, Depends, HTTPException, Query
from deps import db, get_current_user, require_staff, require_manager, require_admin, _audit, logger, is_system_admin, get_campus_filter, verify_password
from models import EventCreate, EventUpdate, CheckInCreate, VenueCreate, VenueUpdate, PublicBookingCreate, SpaceBookingCreate
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import copy

router = APIRouter(prefix="/api", tags=["events"])


# ========== VENUE AVAILABILITY (double-booking prevention) ==========

def _times_overlap(a_start: Optional[str], a_end: Optional[str],
                   b_start: Optional[str], b_end: Optional[str]) -> bool:
    """Two time ranges overlap when start_a < end_b AND start_b < end_a.
    A missing start on either side is treated as an all-day booking → always overlaps."""
    if not a_start or not b_start:
        return True
    a_e = a_end or "23:59"
    b_e = b_end or "23:59"
    return a_start < b_e and b_start < a_e


async def _find_venue_conflict(venue_id: Optional[str], date: Optional[str],
                               end_date: Optional[str], time: Optional[str],
                               end_time: Optional[str],
                               exclude_event_id: Optional[str] = None,
                               exclude_booking_id: Optional[str] = None) -> Optional[dict]:
    """Return the first existing event/space-booking that clashes with the given
    venue + date/time window, or None if the slot is free."""
    if not venue_id or not date:
        return None
    d_end = end_date or date
    # 1) Check events on the same venue whose date range intersects [date, d_end]
    q: dict = {
        "venue_id": venue_id,
        "status": {"$ne": "cancelled"},
        "date": {"$lte": d_end},
    }
    if exclude_event_id:
        q["id"] = {"$ne": exclude_event_id}
    for ev in await db.events.find(q, {"_id": 0}).to_list(500):
        ev_end = ev.get("end_date") or ev.get("date")
        if not ev_end or ev_end < date:
            continue
        if _times_overlap(time, end_time, ev.get("time"), ev.get("end_time")):
            return {
                "source": "event",
                "id": ev.get("id"),
                "title": ev.get("title"),
                "date": ev.get("date"),
                "end_date": ev.get("end_date"),
                "time": ev.get("time"),
                "end_time": ev.get("end_time"),
            }
    # 2) Check public space bookings (single-day) — booking_date must fall in window
    sb_q: dict = {
        "venue_id": venue_id,
        "type": "space",
        "booking_date": {"$gte": date, "$lte": d_end},
        "status": {"$nin": ["cancelled", "rejected"]},
    }
    if exclude_booking_id:
        sb_q["id"] = {"$ne": exclude_booking_id}
    for b in await db.public_bookings.find(sb_q, {"_id": 0}).to_list(500):
        if _times_overlap(time, end_time, b.get("start_time"), b.get("end_time")):
            return {
                "source": "space_booking",
                "id": b.get("id"),
                "title": b.get("purpose") or f"Booking by {b.get('name', 'guest')}",
                "date": b.get("booking_date"),
                "time": b.get("start_time"),
                "end_time": b.get("end_time"),
                "booked_by": b.get("name"),
            }
    return None


def _can_override_conflict(user: dict) -> bool:
    """system_admin, admin, and Manager+ can override a venue conflict."""
    if is_system_admin(user):
        return True
    role = (user.get("role") or "").lower()
    return role in {"admin", "manager", "director", "executive director"}


# ========== EVENT TYPES ==========

@router.get("/event-types")
async def list_event_types(current_user: dict = Depends(get_current_user)) -> list:
    types = await db.event_types.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    if not types:
        defaults = [
            {"id": "etype_service", "name": "service", "label": "Service", "color": "#6366f1"},
            {"id": "etype_conference", "name": "conference", "label": "Conference", "color": "#f59e0b"},
            {"id": "etype_meeting", "name": "meeting", "label": "Meeting", "color": "#3b82f6"},
            {"id": "etype_community", "name": "community", "label": "Community", "color": "#10b981"},
            {"id": "etype_workshop", "name": "workshop", "label": "Workshop", "color": "#8b5cf6"},
            {"id": "etype_outreach", "name": "outreach", "label": "Outreach", "color": "#ec4899"},
            {"id": "etype_training", "name": "training", "label": "Training", "color": "#14b8a6"},
            {"id": "etype_social", "name": "social", "label": "Social", "color": "#f97316"},
        ]
        await db.event_types.insert_many(defaults)
        for d in defaults:
            d.pop("_id", None)
        return defaults
    return types


@router.post("/event-types")
async def create_event_type(data: dict, current_user: dict = Depends(require_manager)) -> dict:
    doc = {
        "id": f"etype_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", "").lower().replace(" ", "_"),
        "label": data.get("label", data.get("name", "")),
        "color": data.get("color", "#6366f1"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.event_types.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/event-types/{type_id}")
async def update_event_type(type_id: str, data: dict, current_user: dict = Depends(require_manager)):
    update = {k: v for k, v in data.items() if k in ("name", "label", "color") and v is not None}
    if update.get("name"):
        update["name"] = update["name"].lower().replace(" ", "_")
    await db.event_types.update_one({"id": type_id}, {"$set": update})
    return await db.event_types.find_one({"id": type_id}, {"_id": 0})


@router.delete("/event-types/{type_id}")
async def delete_event_type(type_id: str, current_user: dict = Depends(require_admin)):
    await db.event_types.delete_one({"id": type_id})
    return {"message": "Event type deleted"}


# ========== EVENTS ==========

@router.get("/events")
async def list_events(search: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None, is_public: Optional[bool] = None, visibility: Optional[str] = None, current_user: dict = Depends(get_current_user)) -> list:
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    # NOTE: is_public events used to bypass campus filter — that caused public events
    # from one campus to leak into another. is_public now controls public-page visibility
    # only, NOT cross-campus visibility. Use /public/events for the truly-public endpoint.
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    if type and type != "all":
        query["type"] = type
    if status and status != "all":
        query["status"] = status
    if is_public is not None:
        query["is_public"] = is_public
    if visibility and visibility != "all":
        query["visibility"] = visibility
    events = await db.events.find(query, {"_id": 0}).sort([("date", 1)]).to_list(200)
    # Auto-update status for past events still marked as upcoming
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for ev in events:
        if ev.get("status") == "upcoming" and ev.get("date") and ev["date"] < today:
            ev["status"] = "completed"
            await db.events.update_one({"id": ev["id"]}, {"$set": {"status": "completed"}})
    # Sort: upcoming first, then by date
    status_order = {"upcoming": 0, "ongoing": 1, "completed": 2, "cancelled": 3}
    events.sort(key=lambda e: (status_order.get(e.get("status", ""), 9), e.get("date", "")))
    # Filter imported events: only show to importer or invited users
    uid = current_user["id"]
    filtered = []
    for ev in events:
        if ev.get("type") == "imported" and ev.get("imported_by"):
            if ev["imported_by"] == uid or uid in (ev.get("visible_to") or []):
                filtered.append(ev)
            elif is_system_admin(current_user):
                filtered.append(ev)
        else:
            filtered.append(ev)
    # iter 265 — resolve venue_name for every event so the events list card
    # can show the venue / sub-location without a second round-trip.
    venue_ids = list({e.get("venue_id") for e in filtered if e.get("venue_id")})
    if venue_ids:
        venue_docs = await db.venues.find({"id": {"$in": venue_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        subloc_docs = await db.locations.find({"id": {"$in": venue_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        name_map = {v["id"]: v.get("name") for v in venue_docs}
        for s in subloc_docs:
            name_map.setdefault(s["id"], s.get("name"))
        for ev in filtered:
            if ev.get("venue_id") and name_map.get(ev["venue_id"]):
                ev["venue_name"] = name_map[ev["venue_id"]]
    return filtered


@router.post("/events")
async def create_event(data: EventCreate, force: bool = Query(False), current_user: dict = Depends(get_current_user)) -> dict:
    # Venue availability check — block double-booking unless a privileged user forces
    if data.venue_id:
        conflict = await _find_venue_conflict(
            data.venue_id, data.date, data.end_date, data.time, data.end_time,
        )
        if conflict and not (force and _can_override_conflict(current_user)):
            raise HTTPException(status_code=409, detail={
                "message": "Venue already booked for that time",
                "conflict": conflict,
                "can_override": _can_override_conflict(current_user),
            })
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    event = {
        "id": event_id,
        **data.model_dump(),
        "registered": 0,
        "status": "upcoming",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    # Auto-set country from location if not provided
    if not event.get("country") and event.get("location_id"):
        loc = await db.locations.find_one({"id": event["location_id"]}, {"_id": 0, "country": 1})
        if loc and loc.get("country"):
            event["country"] = loc["country"]
    await db.events.insert_one(event)
    event.pop("_id", None)
    try:
        from routers.notifications import send_bulk_notifications
        recipients = await db.users.find(
            {"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1, "name": 1}
        ).to_list(200)
        if recipients:
            await send_bulk_notifications({
                "recipients": recipients, "type": "event_reminder",
                "data": {"event_title": event.get("title"), "date": event.get("date"), "time": event.get("time"), "location": event.get("location")},
            })
    except Exception as e:
        logger.warning(f"Event notify failed: {e}")
    return event


# ========== BULK EVENT OPERATIONS (must be before parameterized routes) ==========

@router.put("/events/bulk-update")
async def bulk_update_events(data: dict, current_user: dict = Depends(require_staff)):
    """Bulk update events. Body: {ids: [], updates: {status, type, location_id, is_public, country}}"""
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates:
        return {"updated": 0}
    allowed = {"status", "type", "location_id", "is_public", "country", "visibility", "capacity", "ticket_tiers", "waitlist_enabled"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.events.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/events/bulk-delete")
async def bulk_delete_events(data: dict, current_user: dict = Depends(require_staff)):
    """Bulk delete events. Body: {ids: []}"""
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    result = await db.events.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.post("/events/bulk-export")
async def bulk_export_events(data: dict, current_user: dict = Depends(get_current_user)):
    """Export selected events as JSON (for CSV conversion on frontend). Body: {ids: []} or empty for all."""
    ids = data.get("ids")
    query = {"id": {"$in": ids}} if ids else {}
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(500)
    return events


# ========== SINGLE EVENT OPERATIONS ==========

# ========== CALENDAR IMPORT/EXPORT ==========

@router.get("/events/export/ical")
async def export_calendar_ical(current_user: dict = Depends(get_current_user)):
    """Export user's events as iCal (.ics) format for calendar apps."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    events = await db.events.find(query, {"_id": 0}).to_list(500)

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//58:12 Global Connect//CRM//EN", "X-WR-CALNAME:58:12 Connect", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for ev in events:
        uid = ev.get("id") or ""
        dtstart = (ev.get("date") or "").replace("-", "")
        time_str = (ev.get("time") or "0900").replace(":", "")
        end_time = (ev.get("end_time") or "").replace(":", "")
        summary = ev.get("title") or ""
        desc = (ev.get("description") or "").replace("\n", "\\n")
        location = ev.get("location") or ""
        status_map = {"upcoming": "CONFIRMED", "completed": "CONFIRMED", "cancelled": "CANCELLED"}
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}@5812connect",
            f"DTSTART:{dtstart}T{time_str}00",
            f"DTEND:{dtstart}T{end_time or time_str}00" if end_time else f"DTEND:{dtstart}T{time_str}00",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{location}",
            f"STATUS:{status_map.get(ev.get('status'), 'CONFIRMED')}",
            f"LAST-MODIFIED:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")

    from fastapi.responses import Response
    ical_text = "\r\n".join(lines)
    return Response(
        content=ical_text,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=5812_calendar.ics"}
    )


@router.get("/events/webcal-subscribe")
async def get_webcal_link(current_user: dict = Depends(get_current_user)):
    """Get a subscribable webcal:// link for live calendar sync"""
    import secrets as sec
    user_id = current_user["id"]
    existing = await db.webcal_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if existing:
        return {"token": existing["token"], "webcal_url": f"/api/events/webcal/{existing['token']}"}
    token = sec.token_urlsafe(32)
    await db.webcal_tokens.insert_one({"user_id": user_id, "token": token, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"token": token, "webcal_url": f"/api/events/webcal/{token}"}


@router.get("/events/webcal/{token}")
async def webcal_feed(token: str):
    """Public webcal feed — no auth required, uses token"""
    token_doc = await db.webcal_tokens.find_one({"token": token}, {"_id": 0})
    if not token_doc:
        raise HTTPException(status_code=404, detail="Invalid calendar link")
    user = await db.users.find_one({"id": token_doc["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    campus = await get_campus_filter(user)
    query = {**campus} if campus else {}
    events = await db.events.find(query, {"_id": 0}).to_list(500)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//58:12 Connect//CRM//EN", "X-WR-CALNAME:58:12 Connect", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for ev in events:
        uid = ev.get("id", "")
        dtstart = (ev.get("date") or "").replace("-", "")
        time_str = (ev.get("time") or "0900").replace(":", "")
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}@5812connect", f"DTSTART:{dtstart}T{time_str}00", f"SUMMARY:{ev.get('title','')}", f"LOCATION:{ev.get('location','')}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    from fastapi.responses import Response
    return Response(content="\r\n".join(lines), media_type="text/calendar")


# ─── PUBLIC SHAREABLE CALENDAR (global + per-location, JSON + iCal) ─────────
# Users can share a stable, unauth link that renders only public events
# (`is_public=True`) and never leaks tasks. Tokens are HMAC-signed so no db
# lookup is required to validate the link — rotate SECRET_KEY to invalidate.

import hmac as _hmac, hashlib as _hashlib
from deps import SECRET_KEY as _SECRET_KEY


def _calendar_token(scope: str, ident: str = "") -> str:
    """Deterministic 12-char signature so the same scope always yields the
    same URL. Rotating SECRET_KEY invalidates every existing link."""
    msg = f"cal:{scope}:{ident}".encode("utf-8")
    return _hmac.new(_SECRET_KEY.encode(), msg, _hashlib.sha256).hexdigest()[:16]


def _verify_calendar_token(token: str, scope: str, ident: str = "") -> bool:
    return _hmac.compare_digest(token, _calendar_token(scope, ident))


def _ical_escape(s: str) -> str:
    """RFC 5545: escape commas, semicolons, backslashes, and newlines."""
    if not s:
        return ""
    return (s.replace("\\", "\\\\").replace(",", "\\,")
             .replace(";", "\\;").replace("\n", "\\n").replace("\r", ""))


def _events_to_ical(events: list, cal_name: str) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//58:12 Global Connect//CRM//EN",
        f"X-WR-CALNAME:{_ical_escape(cal_name)}",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    ]
    status_map = {"upcoming": "CONFIRMED", "completed": "CONFIRMED", "cancelled": "CANCELLED"}
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        uid = ev.get("id") or ""
        dt = (ev.get("date") or "").replace("-", "")
        if not dt:
            continue
        start_t = (ev.get("time") or "").replace(":", "")
        end_t = (ev.get("end_time") or "").replace(":", "")
        end_d = (ev.get("end_date") or ev.get("date") or "").replace("-", "")
        if not start_t:
            # All-day event
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}@5812connect",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{dt}",
                f"DTEND;VALUE=DATE:{end_d}",
                f"SUMMARY:{_ical_escape(ev.get('title', ''))}",
                f"DESCRIPTION:{_ical_escape(ev.get('description', ''))}",
                f"LOCATION:{_ical_escape(ev.get('location', ''))}",
                f"STATUS:{status_map.get(ev.get('status'), 'CONFIRMED')}",
                "END:VEVENT",
            ])
        else:
            end_t = end_t or start_t
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}@5812connect",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{dt}T{start_t}00",
                f"DTEND:{end_d}T{end_t}00",
                f"SUMMARY:{_ical_escape(ev.get('title', ''))}",
                f"DESCRIPTION:{_ical_escape(ev.get('description', ''))}",
                f"LOCATION:{_ical_escape(ev.get('location', ''))}",
                f"STATUS:{status_map.get(ev.get('status'), 'CONFIRMED')}",
                "END:VEVENT",
            ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


@router.get("/calendar/share-links")
async def get_calendar_share_links(current_user: dict = Depends(get_current_user)):
    """Return the shareable public calendar URLs for this user — one global feed
    plus one per campus they can access. Tokens are stable across calls."""
    global_token = _calendar_token("global")
    user_loc_ids = set(current_user.get("location_ids") or [])
    if current_user.get("location_id"):
        user_loc_ids.add(current_user["location_id"])
    active = current_user.get("active_campus_id")
    if active:
        user_loc_ids.add(active)
    per_loc = []
    if user_loc_ids:
        locs = await db.locations.find(
            {"id": {"$in": list(user_loc_ids)}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(50)
        for loc in locs:
            per_loc.append({
                "location_id": loc["id"],
                "location_name": loc.get("name") or loc["id"],
                "token": _calendar_token("location", loc["id"]),
            })
    return {"global": {"token": global_token}, "locations": per_loc}


async def _fetch_public_events(location_id: Optional[str] = None) -> list:
    q: dict = {"is_public": True, "status": {"$ne": "cancelled"}}
    if location_id:
        q["location_id"] = location_id
    return await db.events.find(q, {"_id": 0}).sort("date", 1).to_list(1000)


@router.get("/public/calendar/global.ics")
async def public_calendar_global_ical(token: str):
    if not _verify_calendar_token(token, "global"):
        raise HTTPException(status_code=404, detail="Invalid calendar link")
    events = await _fetch_public_events()
    ical = _events_to_ical(events, "58:12 Public Events")
    from fastapi.responses import Response
    return Response(content=ical, media_type="text/calendar",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/public/calendar/global")
async def public_calendar_global_json(token: str):
    if not _verify_calendar_token(token, "global"):
        raise HTTPException(status_code=404, detail="Invalid calendar link")
    events = await _fetch_public_events()
    return {"scope": "global", "events": events, "count": len(events)}


@router.get("/public/calendar/location/{location_id}.ics")
async def public_calendar_location_ical(location_id: str, token: str):
    if not _verify_calendar_token(token, "location", location_id):
        raise HTTPException(status_code=404, detail="Invalid calendar link")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1})
    events = await _fetch_public_events(location_id)
    ical = _events_to_ical(events, f"58:12 · {loc.get('name') if loc else location_id}")
    from fastapi.responses import Response
    return Response(content=ical, media_type="text/calendar",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/public/calendar/location/{location_id}")
async def public_calendar_location_json(location_id: str, token: str):
    if not _verify_calendar_token(token, "location", location_id):
        raise HTTPException(status_code=404, detail="Invalid calendar link")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1, "city": 1, "country": 1})
    events = await _fetch_public_events(location_id)
    return {"scope": "location", "location": loc or {"id": location_id}, "events": events, "count": len(events)}


@router.post("/events/import/ical")
async def import_calendar_ical(data: dict, current_user: dict = Depends(get_current_user)):
    """Import events from iCal text content."""
    ical_text = data.get("ical_content", "")
    if not ical_text:
        raise HTTPException(status_code=400, detail="No iCal content provided")

    imported = 0
    events = []
    current_event = {}
    for line in ical_text.split("\n"):
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current_event = {}
        elif line == "END:VEVENT":
            if current_event.get("title"):
                event_id = f"evt_{str(uuid.uuid4())[:8]}"
                event_doc = {
                    "id": event_id,
                    "title": current_event.get("title", "Imported Event"),
                    "date": current_event.get("date", ""),
                    "time": current_event.get("time", ""),
                    "description": current_event.get("description", ""),
                    "location": current_event.get("location", ""),
                    "location_id": current_user.get("location_id", ""),
                    "type": "imported",
                    "status": "upcoming",
                    "is_public": False,
                    "imported_by": current_user["id"],
                    "visible_to": [],
                    "created_by": current_user["id"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                events.append(event_doc)
                imported += 1
            current_event = {}
        elif line.startswith("SUMMARY:"):
            current_event["title"] = line[8:]
        elif line.startswith("DTSTART:"):
            dt = line[8:].replace("T", " ")[:15]
            if len(dt) >= 8:
                current_event["date"] = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
                if len(dt) >= 12:
                    current_event["time"] = f"{dt[9:11]}:{dt[11:13]}"
        elif line.startswith("DESCRIPTION:"):
            current_event["description"] = line[12:].replace("\\n", "\n")
        elif line.startswith("LOCATION:"):
            current_event["location"] = line[9:]

    if events:
        await db.events.insert_many(events)

    return {"imported": imported, "message": f"Imported {imported} events"}




@router.get("/events/{event_id}")
async def get_event(event_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Public signups land in db.public_bookings (see POST /api/public/bookings/event).
    # Legacy / internal registrations may live in db.event_registrations. Merge both
    # so the staff "Registrations" tab shows everyone regardless of entry path.
    public_bookings = await db.public_bookings.find(
        {"event_id": event_id, "status": {"$ne": "cancelled"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(2000)
    legacy_regs = await db.event_registrations.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    # Normalise into the shape the frontend already expects: {name, email, phone, status, num_tickets, ...}
    attendees = []
    seen = set()
    for b in public_bookings:
        key = (b.get("email") or "").lower() + "|" + str(b.get("phone") or "")
        if key in seen:
            continue
        seen.add(key)
        attendees.append({
            "id": b.get("id"),
            "name": b.get("name") or b.get("guest_name") or "Anonymous",
            "email": b.get("email", ""),
            "phone": b.get("phone", ""),
            "status": b.get("status", "confirmed"),
            "payment_status": b.get("payment_status"),
            "num_tickets": b.get("num_tickets", 1),
            "tier_name": b.get("tier_name"),
            "total": b.get("total"),
            "created_at": b.get("created_at"),
            "source": "public_booking",
        })
    for r in legacy_regs:
        key = (r.get("email") or "").lower() + "|" + str(r.get("phone") or "")
        if key in seen:
            continue
        seen.add(key)
        attendees.append({**r, "source": "registration"})
    event["attendees"] = attendees
    event["attendee_count"] = len(attendees)
    # Keep the legacy "registered" counter in sync with the actual booking total —
    # this is what shows on event cards.
    real_count = sum(b.get("num_tickets", 1) for b in public_bookings) + len(legacy_regs)
    if event.get("registered") != real_count:
        try:
            await db.events.update_one({"id": event_id}, {"$set": {"registered": real_count}})
            event["registered"] = real_count
        except Exception:
            pass
    checkins = await db.checkins.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    event["checkins"] = checkins
    return event


@router.put("/events/{event_id}")
async def update_event(event_id: str, data: EventUpdate, force: bool = Query(False), current_user: dict = Depends(get_current_user)) -> dict:
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Venue availability re-check when venue or timing changes
    existing = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    venue_id = update_data.get("venue_id", existing.get("venue_id"))
    if venue_id and any(k in update_data for k in ("venue_id", "date", "end_date", "time", "end_time")):
        conflict = await _find_venue_conflict(
            venue_id,
            update_data.get("date", existing.get("date")),
            update_data.get("end_date", existing.get("end_date")),
            update_data.get("time", existing.get("time")),
            update_data.get("end_time", existing.get("end_time")),
            exclude_event_id=event_id,
        )
        if conflict and not (force and _can_override_conflict(current_user)):
            raise HTTPException(status_code=409, detail={
                "message": "Venue already booked for that time",
                "conflict": conflict,
                "can_override": _can_override_conflict(current_user),
            })
    result = await db.events.update_one({"id": event_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return await db.events.find_one({"id": event_id}, {"_id": 0})


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event deleted"}




@router.post("/events/{event_id}/duplicate")
async def duplicate_event(event_id: str, current_user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    new_id = f"evt_{str(uuid.uuid4())[:8]}"
    new_event = {**event, "id": new_id, "title": f"{event['title']} (Copy)", "registered": 0, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.events.insert_one(new_event)
    new_event.pop("_id", None)
    return new_event


@router.put("/events/{event_id}/share")
async def share_imported_event(event_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Share an imported calendar event with other users."""
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("imported_by") != current_user["id"] and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail="Only the importer can share this event")
    user_ids = data.get("user_ids", [])
    await db.events.update_one({"id": event_id}, {"$addToSet": {"visible_to": {"$each": user_ids}}})
    return {"message": f"Event shared with {len(user_ids)} users"}




# ========== CHECK-INS ==========

@router.get("/checkins")
async def list_checkins(event_id: Optional[str] = None, member_id: Optional[str] = None, type: Optional[str] = None, search: Optional[str] = None, location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    if event_id: query["event_id"] = event_id
    if member_id: query["member_id"] = member_id
    if type and type != "all": query["type"] = type
    if search: query["member_name"] = {"$regex": search, "$options": "i"}
    if location_id: query["location_id"] = location_id
    checkins = await db.checkins.find(query, {"_id": 0}).sort("check_in_time", -1).to_list(1000)
    return checkins


@router.post("/checkins")
async def create_checkin(data: CheckInCreate, current_user: dict = Depends(get_current_user)):
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    payload = data.model_dump()
    # If the caller didn't specify a location_id, infer it (event → user) so the
    # row is visible under campus-scoped queries.
    if not payload.get("location_id"):
        ev_id = payload.get("event_id")
        if ev_id:
            ev = await db.events.find_one({"id": ev_id}, {"_id": 0, "location_id": 1})
            if ev:
                payload["location_id"] = ev.get("location_id")
        if not payload.get("location_id"):
            payload["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    checkin = {
        "id": ci_id, **payload,
        "check_in_time": datetime.now(timezone.utc).isoformat(),
        "checked_in_by": current_user["id"],
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return checkin


@router.post("/checkins/pin")
async def pin_checkin(data: dict, current_user: dict = Depends(get_current_user)):
    """Check in/out a member using their PIN code"""
    pin = data.get("pin", "").strip()
    event_id = data.get("event_id")
    event_name = data.get("event_name", "")
    action = data.get("action", "checkin")
    if not pin:
        raise HTTPException(status_code=400, detail="PIN required")
    member = await db.members.find_one({"pin": pin}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Invalid PIN")
    if action == "checkout":
        last_checkin = await db.checkins.find_one(
            {"member_id": member["id"], "check_out_time": None},
            {"_id": 0}, sort=[("check_in_time", -1)]
        )
        if last_checkin:
            await db.checkins.update_one(
                {"id": last_checkin["id"]},
                {"$set": {"check_out_time": datetime.now(timezone.utc).isoformat(), "checked_out_by": current_user["id"]}}
            )
            return {"message": "Checked out", "member": member, "checkin_id": last_checkin["id"]}
        return {"message": "No active check-in found", "member": member}
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, "member_id": member["id"], "member_name": member.get("name", ""),
        "type": member.get("role", "member").lower(), "event_id": event_id, "event_name": event_name,
        "method": "pin", "check_in_time": datetime.now(timezone.utc).isoformat(),
        "checked_in_by": current_user["id"],
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return {"message": "Checked in", "member": member, "checkin": checkin}


@router.post("/checkins/{checkin_id}/checkout")
async def checkout_person(checkin_id: str, current_user: dict = Depends(require_staff)):
    """Admin/manager can check out a person from the backend"""
    checkin = await db.checkins.find_one({"id": checkin_id}, {"_id": 0})
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.get("check_out_time"):
        raise HTTPException(status_code=400, detail="Already checked out")
    await db.checkins.update_one(
        {"id": checkin_id},
        {"$set": {"check_out_time": datetime.now(timezone.utc).isoformat(), "checked_out_by": current_user["id"]}}
    )
    return {"message": "Checked out successfully"}


@router.post("/checkins/visitor")
async def visitor_checkin(data: dict, current_user: dict = Depends(get_current_user)):
    """Full visitor check-in flow: lookup/create guest, check blocked status, issue badge, tag under-18 guests"""
    phone = (data.get("phone") or "").strip()
    name = (data.get("name") or "").strip()
    event_id = data.get("event_id", "")
    event_name = data.get("event_name", "")
    location_id = data.get("location_id", "")
    additional_guests = data.get("additional_guests", [])  # [{name, age}] for under-18s
    id_data = data.get("id_data")  # Extracted ID info: {first_name, last_name, dob, id_number, id_type, photo_url}

    if not phone and not name:
        raise HTTPException(status_code=400, detail="Phone number or name required")

    # 1. Look up existing guest profile
    guest = None
    if phone:
        guest = await db.guests.find_one({"phone": phone}, {"_id": 0})
    if not guest and name:
        guest = await db.guests.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0})

    needs_profile = not guest

    # 2. Check if guest is blocked
    if guest and guest.get("is_blocked"):
        return {"status": "blocked", "message": f"This guest has been blocked from checking in. Reason: {guest.get('block_reason', 'Contact administration')}",
                "guest": {"name": guest.get("name"), "id": guest.get("id")}}

    # 3. Create new guest profile if needed
    if needs_profile:
        if not name:
            return {"status": "needs_info", "message": "Guest not found. Please provide full name, date of birth, and ID."}
        guest_id = f"gst_{str(uuid.uuid4())[:8]}"
        guest = {
            "id": guest_id, "name": name, "phone": phone,
            "email": data.get("email", ""), "date_of_birth": data.get("date_of_birth", ""),
            "location_id": location_id, "is_parent": False,
            "id_type": id_data.get("id_type", "") if id_data else "",
            "id_number": id_data.get("id_number", "") if id_data else "",
            "photo_url": id_data.get("photo_url", "") if id_data else "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if id_data:
            if id_data.get("first_name"): guest["name"] = f"{id_data['first_name']} {id_data.get('last_name', '')}".strip()
            if id_data.get("dob"): guest["date_of_birth"] = id_data["dob"]
        await db.guests.insert_one(guest)
        guest.pop("_id", None)

    # 4. Create check-in record
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, "member_id": guest["id"], "member_name": guest.get("name", name),
        "type": "visitor", "event_id": event_id, "event_name": event_name,
        "method": "visitor_kiosk", "location_id": location_id,
        "check_in_time": datetime.now(timezone.utc).isoformat(),
        "checked_in_by": current_user["id"],
    }
    await db.checkins.insert_one(checkin); checkin.pop("_id", None)

    # 5. Handle additional under-18 guests (up to 3)
    additional_badges = []
    for i, ag in enumerate(additional_guests[:3]):
        ag_name = (ag.get("name") or "").strip()
        if not ag_name: continue
        ag_ci_id = f"ci_{str(uuid.uuid4())[:8]}"
        ag_checkin = {
            "id": ag_ci_id, "member_id": guest["id"], "member_name": ag_name,
            "type": "minor_guest", "event_id": event_id, "event_name": event_name,
            "method": "tagged_guest", "location_id": location_id,
            "tagged_to": guest["id"], "tagged_to_name": guest.get("name", ""),
            "age": ag.get("age"), "check_in_time": datetime.now(timezone.utc).isoformat(),
            "checked_in_by": current_user["id"],
        }
        await db.checkins.insert_one(ag_checkin); ag_checkin.pop("_id", None)
        additional_badges.append({"name": ag_name, "checkin_id": ag_ci_id, "tagged_to": guest.get("name", "")})

    # 6. Generate badge data
    badge = {
        "guest_id": guest["id"], "name": guest.get("name", name),
        "first_name": guest.get("name", "").split(" ")[0] if guest.get("name") else name.split(" ")[0],
        "last_name": " ".join(guest.get("name", "").split(" ")[1:]) if guest.get("name") else "",
        "qr_data": guest["id"], "checkin_id": ci_id,
        "is_new_profile": needs_profile,
    }

    return {
        "status": "success", "message": f"{'New profile created. ' if needs_profile else ''}Checked in!",
        "guest": guest, "checkin": checkin, "badge": badge,
        "additional_guests": additional_badges, "is_new_profile": needs_profile,
    }


@router.put("/guests/{guest_id}/block")
async def block_guest(guest_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Block/unblock a guest from checking in"""
    await db.guests.update_one({"id": guest_id}, {"$set": {
        "is_blocked": data.get("blocked", True),
        "block_reason": data.get("reason", ""),
        "blocked_by": current_user["id"],
        "blocked_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"message": "Guest blocked" if data.get("blocked", True) else "Guest unblocked"}


@router.post("/checkins/restricted-alert")
async def restricted_area_alert(data: dict, current_user: dict = Depends(get_current_user)):
    """Send alert for unauthorized check-in at restricted location"""
    location_id = data.get("location_id", "")
    person_name = data.get("person_name", "Unknown")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    campus_id = loc.get("parent_id") or location_id if loc else location_id
    # Find director and security staff
    director = await db.users.find_one({"location_id": campus_id, "role": {"$in": ["Director", "Executive Director"]}}, {"_id": 0, "id": 1, "name": 1})
    loc_manager = await db.users.find_one({"location_id": location_id, "role": {"$in": ["Manager", "Coordinator"]}}, {"_id": 0, "id": 1, "name": 1})
    # Create notification
    notif = {
        "id": f"notif_{str(uuid.uuid4())[:8]}", "type": "warning",
        "title": f"UNAUTHORIZED ACCESS: {person_name}",
        "message": f"Unauthorized check-in attempt at {loc.get('name', location_id) if loc else location_id}",
        "link": "/access", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    targets = [t["id"] for t in [director, loc_manager] if t]
    for uid in targets:
        await db.notifications.insert_one({**notif, "id": f"notif_{str(uuid.uuid4())[:8]}", "user_id": uid, "read": False})
    return {"alerted": len(targets), "targets": targets}


@router.post("/checkins/qr-scan")
async def qr_code_checkin(data: dict, current_user: dict = Depends(get_current_user)):
    """Check in by scanning a member's QR code (containing member ID or national ID)."""
    qr_data = (data.get("qr_data") or "").strip()
    event_id = data.get("event_id", "")
    event_name = data.get("event_name", "")
    if not qr_data:
        raise HTTPException(status_code=400, detail="QR data required")
    # Try to find member by ID, national_id, or email
    member = await db.members.find_one(
        {"$or": [{"id": qr_data}, {"national_id": qr_data}, {"email": qr_data}, {"pin": qr_data}]},
        {"_id": 0}
    )
    if not member:
        # Try users table
        user = await db.users.find_one(
            {"$or": [{"id": qr_data}, {"national_id": qr_data}, {"email": qr_data}]},
            {"_id": 0, "password_hash": 0}
        )
        if user:
            member = {"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "member")}
    if not member:
        raise HTTPException(status_code=404, detail="No member found for this QR code")
    # Create check-in
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, "member_id": member["id"], "member_name": member.get("name", ""),
        "type": member.get("role", "member").lower(), "event_id": event_id, "event_name": event_name,
        "method": "qr", "check_in_time": datetime.now(timezone.utc).isoformat(),
        "checked_in_by": current_user["id"],
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return {"message": "Checked in via QR", "member": member, "checkin": checkin}


async def _notify_parent_checkin(parent, checked_in, event_name=""):
    """Send email to parent when their children are checked in."""
    email = parent.get("email", "")
    if not email or not checked_in:
        return False
    try:
        from email_helpers import notify_checkin
        names = ", ".join(c.get("member_name", "") for c in checked_in)
        await notify_checkin(email, parent.get("name", ""), names, event_name)
        return True
    except Exception as e:
        logger.warning(f"Parent checkin notification failed: {e}")
        return False



@router.get("/checkins/kiosk-warmup")
async def kiosk_warmup(event_id: str = "", limit: int = 500, current_user: dict = Depends(get_current_user)):
    """Return a thin directory of parent lookup keys for a kiosk to pre-seed
    its offline cache when the host opens check-in for an event. We hand
    back ONLY the minimum each cached entry will key off — id, name, phone,
    email, and the child list — so the payload stays small even on big
    family rolls."""
    cap = max(50, min(1000, int(limit or 500)))
    # Anchor to the event's campus when available; otherwise fall back to
    # the operator's active campus so we don't leak cross-campus data.
    location_id = None
    if event_id:
        ev = await db.events.find_one({"id": event_id}, {"_id": 0, "location_id": 1})
        if ev:
            location_id = ev.get("location_id")
    if not location_id:
        location_id = current_user.get("active_campus_id") or current_user.get("location_id")

    base_filter: dict = {"is_parent": True}
    if location_id:
        base_filter["location_id"] = location_id

    parents = await db.guests.find(
        base_filter,
        {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1, "family_id": 1, "location_id": 1},
    ).to_list(cap)

    # Pull children scoped to the parents we found
    family_ids = [p["family_id"] for p in parents if p.get("family_id")]
    parent_ids = [p["id"] for p in parents if p.get("id")]
    child_filter = {"$or": []}
    if family_ids:
        child_filter["$or"].append({"family_id": {"$in": family_ids}})
    if parent_ids:
        child_filter["$or"].append({"parent_ids": {"$in": parent_ids}})
    if not child_filter["$or"]:
        children_by_parent: dict = {}
    else:
        kids = await db.children.find(
            child_filter,
            {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "family_id": 1, "parent_ids": 1},
        ).to_list(cap * 4)
        children_by_parent = {}
        for k in kids:
            for pid in (k.get("parent_ids") or []):
                children_by_parent.setdefault(pid, []).append(k)
            if k.get("family_id"):
                children_by_parent.setdefault(f"family:{k['family_id']}", []).append(k)

    entries = []
    for p in parents:
        kids = []
        if p.get("id") and p["id"] in children_by_parent:
            kids = children_by_parent[p["id"]]
        elif p.get("family_id"):
            kids = children_by_parent.get(f"family:{p['family_id']}", [])
        entries.append({"parent": p, "children": kids})
    return {"event_id": event_id, "location_id": location_id, "count": len(entries), "entries": entries}



@router.post("/checkins/parent-lookup")
async def parent_lookup_checkin(data: dict, current_user: dict = Depends(get_current_user)):
    """Look up children by parent phone, ID, email, or QR code and optionally check them in.
    Returns list of children linked to the parent.
    If 'checkin' is true, creates check-in records for selected children."""
    lookup = (data.get("lookup", "") or "").strip()
    event_id = data.get("event_id", "")
    event_name = data.get("event_name", "")
    do_checkin = data.get("checkin", False)
    child_ids = data.get("child_ids", [])  # specific children to check in

    if not lookup:
        raise HTTPException(status_code=400, detail="Parent phone, email, or ID required")

    # Search for parent in guests (parents) by phone, email, or id
    import re
    safe_lookup = re.escape(lookup)
    parent_or = [
        {"phone": {"$regex": safe_lookup, "$options": "i"}},
        {"email": {"$regex": f"^{safe_lookup}$", "$options": "i"}},
        {"id": lookup},
        {"name": {"$regex": safe_lookup, "$options": "i"}},
    ]
    parent = await db.guests.find_one({"$or": parent_or, "is_parent": True}, {"_id": 0})
    if not parent:
        # Fallback: search guests without is_parent filter (may have been created without the flag)
        parent = await db.guests.find_one({"$or": parent_or}, {"_id": 0})
    if not parent:
        # Also check members/users with parent flag or phone
        parent = await db.members.find_one({"$or": parent_or}, {"_id": 0})
    if not parent:
        raise HTTPException(status_code=404, detail="Parent not found. Check the phone number or ID.")

    # Find children linked to this parent
    children_query = {"$or": []}
    if parent.get("family_id"):
        children_query["$or"].append({"family_id": parent["family_id"]})
    if parent.get("id"):
        children_query["$or"].append({"parent_ids": parent["id"]})
    if not children_query["$or"]:
        return {"parent": parent, "children": [], "checked_in": []}

    children = await db.children.find(children_query, {"_id": 0}).to_list(50)

    if not do_checkin:
        return {"parent": parent, "children": children, "checked_in": []}

    # Check in specified children (or all if no child_ids provided)
    # Resolve the location_id so staff can see these rows under their campus filter.
    resolved_location = (data.get("location_id") or "").strip() or None
    if not resolved_location and event_id:
        ev = await db.events.find_one({"id": event_id}, {"_id": 0, "location_id": 1})
        if ev:
            resolved_location = ev.get("location_id")
    if not resolved_location:
        resolved_location = parent.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    checked_in = []
    targets = children if not child_ids else [c for c in children if c["id"] in child_ids]
    for child in targets:
        ci_id = f"ci_{str(uuid.uuid4())[:8]}"
        checkin = {
            "id": ci_id,
            "member_name": child["name"],
            "member_id": child["id"],
            "type": "child",
            "event_id": event_id,
            "event_name": event_name,
            "method": "parent_id",
            "check_in_time": datetime.now(timezone.utc).isoformat(),
            "checked_in_by": current_user["id"],
            "parent_id": parent["id"],
            "parent_name": parent.get("name", ""),
            "location_id": resolved_location or child.get("location_id") or "",
        }
        await db.checkins.insert_one(checkin)
        checkin.pop("_id", None)
        checked_in.append(checkin)

    return {"parent": parent, "children": children, "checked_in": checked_in,
            "email_sent": await _notify_parent_checkin(parent, checked_in, event_name)}


@router.get("/checkins/stats")
async def get_checkin_stats(current_user: dict = Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    return {
        "total": await db.checkins.count_documents({}),
        "today": await db.checkins.count_documents({"check_in_time": {"$gte": today_start}}),
        "members": await db.checkins.count_documents({"type": "member"}),
        "visitors": await db.checkins.count_documents({"type": "visitor"}),
        "staff": await db.checkins.count_documents({"type": "staff"}),
        "children": await db.checkins.count_documents({"type": "child"}),
    }



# ========== KIOSK DEVICE MANAGEMENT ==========

@router.post("/kiosk/devices")
async def register_kiosk_device(data: dict, current_user: dict = Depends(require_admin)):
    """Admin registers a new kiosk device with location, type, and peripheral config"""
    device_id = f"kiosk_{str(uuid.uuid4())[:8]}"
    doc = {
        "id": device_id,
        "name": data.get("name", "Kiosk"),
        "location_id": data.get("location_id", ""),
        "location_name": data.get("location_name", ""),
        "type": data.get("type", "regular"),  # regular, restricted, venue
        "venue_id": data.get("venue_id"),
        "is_restricted": data.get("is_restricted", False),
        "peripherals": data.get("peripherals", {}),  # {nfc: true, fingerprint: true, camera: true, qr_scanner: true}
        "auto_lock": data.get("auto_lock", True),
        "lock_password": data.get("lock_password", ""),
        "check_in_types": data.get("check_in_types", ["staff", "parent", "guest", "child_self"]),
        "active": True,
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.kiosk_devices.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/kiosk/devices")
async def list_kiosk_devices(current_user: dict = Depends(require_staff)):
    return await db.kiosk_devices.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.put("/kiosk/devices/{device_id}")
async def update_kiosk_device(device_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "location_id", "location_name", "type", "venue_id", "is_restricted", "peripherals", "auto_lock", "lock_password", "check_in_types", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.kiosk_devices.update_one({"id": device_id}, {"$set": update})
    return await db.kiosk_devices.find_one({"id": device_id}, {"_id": 0})


@router.delete("/kiosk/devices/{device_id}")
async def delete_kiosk_device(device_id: str, current_user: dict = Depends(require_admin)):
    await db.kiosk_devices.delete_one({"id": device_id})
    return {"message": "Device removed"}


@router.post("/kiosk/devices/{device_id}/unlock")
async def unlock_kiosk(device_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Manager+ unlocks a kiosk with password"""
    device = await db.kiosk_devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    stored_pw = device.get("lock_password", "")
    if stored_pw and data.get("password") != stored_pw:
        # Also try user's actual password
        user = await db.users.find_one({"id": current_user["id"]})
        from deps import verify_password
        if not verify_password(data.get("password", ""), user.get("password_hash", "")):
            raise HTTPException(status_code=403, detail="Invalid password")
    return {"unlocked": True}



# ========== KIOSK ==========

@router.post("/kiosk/unlock")
async def kiosk_unlock(data: dict):
    """Public endpoint to unlock a kiosk. Accepts ANY of:
      - { pin: "1234" } → matches a user/member with that pin AND an admin/manager+ role
      - { identifier, password } → standard auth flow (any admin/manager+)
    Returns { unlocked: true, user_name, user_role } on success."""
    PRIVILEGED_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director", "Manager"}
    pin = (data.get("pin") or "").strip()
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    # ---- PIN flow ----
    if pin:
        # Check users collection first (admin/manager PINs)
        u = await db.users.find_one(
            {"pin": pin, "status": {"$ne": "inactive"}},
            {"_id": 0, "password_hash": 0, "pin_hash": 0},
        )
        # Fall back to members collection (PIN might be stored there for some installs)
        if not u:
            u = await db.members.find_one({"pin": pin}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=401, detail="Invalid PIN")
        role = u.get("role") or ""
        if role not in PRIVILEGED_ROLES:
            raise HTTPException(status_code=403, detail=f"PIN belongs to '{role or 'unknown'}', not an admin/manager")
        return {"unlocked": True, "user_name": u.get("name", ""), "user_role": role, "method": "pin"}

    # ---- password flow ----
    if identifier and password:
        # Locate user by email/username/phone
        ident = identifier.lower()
        u = await db.users.find_one(
            {"$or": [
                {"email": ident},
                {"username": identifier},
                {"phone": identifier},
            ], "status": {"$ne": "inactive"}},
            {"_id": 0},
        )
        if not u or not u.get("password_hash"):
            raise HTTPException(status_code=401, detail="Unknown identifier")
        if not verify_password(password, u["password_hash"]):
            raise HTTPException(status_code=401, detail="Wrong password")
        role = u.get("role") or ""
        if role not in PRIVILEGED_ROLES:
            raise HTTPException(status_code=403, detail=f"User '{role or 'unknown'}' is not an admin/manager")
        return {"unlocked": True, "user_name": u.get("name", ""), "user_role": role, "method": "password"}

    raise HTTPException(status_code=400, detail="Provide either {pin} or {identifier, password}")


@router.post("/kiosk/checkin")
async def kiosk_checkin(data: CheckInCreate):
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    payload = data.model_dump()
    # Infer location_id from event if not provided so staff list_checkins
    # (campus-scoped) can see this row.
    if not payload.get("location_id") and payload.get("event_id"):
        ev = await db.events.find_one({"id": payload["event_id"]}, {"_id": 0, "location_id": 1})
        if ev:
            payload["location_id"] = ev.get("location_id") or ""
    checkin = {
        "id": ci_id, **payload,
        "check_in_time": datetime.now(timezone.utc).isoformat(),
        "source": "kiosk",
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return checkin


@router.get("/kiosk/lookup")
async def kiosk_lookup(identifier: str):
    member = await db.members.find_one(
        {"$or": [{"national_id": identifier}, {"phone": identifier}, {"email": identifier.lower()}]},
        {"_id": 0, "password_hash": 0}
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.post("/kiosk/pin-checkin")
async def kiosk_pin_checkin(data: dict):
    """Kiosk PIN or phone-last-4 based check-in/out (no auth required)"""
    pin = data.get("pin", "").strip()
    event_id = data.get("event_id")
    event_name = data.get("event_name", "")
    action = data.get("action", "checkin")
    # Resolve a location_id so that staff list_checkins (campus-filtered) can see this row.
    # Priority: explicit caller value → event's location → matched person's location.
    caller_location_id = (data.get("location_id") or "").strip() or None
    if not pin:
        raise HTTPException(status_code=400, detail="PIN or phone digits required")
    # Try PIN match first, then phone-last-4
    member = await db.members.find_one({"pin": pin}, {"_id": 0})
    if not member and len(pin) >= 4:
        # Try matching last 4 digits of phone
        phone_regex = f"{pin}$"
        member = await db.members.find_one({"phone": {"$regex": phone_regex}}, {"_id": 0})
        if not member:
            # Also check users collection
            user = await db.users.find_one({"phone": {"$regex": phone_regex}, "status": "active"}, {"_id": 0, "password_hash": 0})
            if user:
                member = await db.members.find_one({"user_id": user["id"]}, {"_id": 0})
                if not member:
                    # Create a temporary member entry for check-in
                    member = {"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "Guest"), "phone": user.get("phone", "")}
            if not member:
                # Check guests
                guest = await db.guests.find_one({"phone": {"$regex": phone_regex}}, {"_id": 0})
                if guest:
                    member = {"id": guest["id"], "name": guest.get("name", ""), "role": "guest", "phone": guest.get("phone", "")}
    if not member:
        raise HTTPException(status_code=404, detail="No match found for this PIN or phone number")
    # Resolve the location_id (kiosk → event → member → guest). Without this, the
    # checkin row won't be visible to staff via the campus-scoped /checkins list.
    resolved_location = caller_location_id
    if not resolved_location and event_id:
        ev = await db.events.find_one({"id": event_id}, {"_id": 0, "location_id": 1})
        if ev:
            resolved_location = ev.get("location_id")
    if not resolved_location:
        resolved_location = member.get("location_id") or member.get("active_campus_id") or ""
    # If this person is/could be a parent, also surface their children so the kiosk
    # can offer them as check-in options (kiosk is unauthenticated — staff-only
    # parent-lookup endpoint won't work for an external parent at a kiosk).
    children = []
    try:
        child_or = []
        if member.get("family_id"):
            child_or.append({"family_id": member["family_id"]})
        if member.get("id"):
            child_or.append({"parent_ids": member["id"]})
        if child_or:
            children = await db.children.find(
                {"$or": child_or},
                {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "date_of_birth": 1, "family_id": 1},
            ).to_list(20)
    except Exception as e:
        logger.warning(f"Kiosk children lookup failed: {e}")
        children = []
    if action == "lookup":
        return {
            "member_name": member.get("name"),
            "member_id": member.get("id"),
            "role": member.get("role", ""),
            "type": member.get("role", "member"),
            "children": children,
        }
    if action == "checkout":
        last_ci = await db.checkins.find_one(
            {"member_id": member["id"], "check_out_time": None},
            {"_id": 0}, sort=[("check_in_time", -1)]
        )
        if last_ci:
            await db.checkins.update_one({"id": last_ci["id"]}, {"$set": {"check_out_time": datetime.now(timezone.utc).isoformat()}})
            return {"message": "Checked out", "member_name": member.get("name")}
        return {"message": "No active check-in", "member_name": member.get("name")}
    # ---- check in (parent + optional children) ----
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, "member_id": member["id"], "member_name": member.get("name", ""),
        "type": member.get("role", "member").lower(), "event_id": event_id, "event_name": event_name,
        "method": "pin", "check_in_time": datetime.now(timezone.utc).isoformat(), "source": "kiosk",
        "location_id": resolved_location,
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    # Optionally check in the parent's children too
    selected_child_ids = data.get("child_ids") or []
    child_checkins = []
    if selected_child_ids and children:
        for child in children:
            if child["id"] not in selected_child_ids:
                continue
            cci_id = f"ci_{str(uuid.uuid4())[:8]}"
            cci = {
                "id": cci_id, "member_id": child["id"], "member_name": child.get("name", ""),
                "type": "child", "event_id": event_id, "event_name": event_name,
                "method": "parent_phone", "check_in_time": datetime.now(timezone.utc).isoformat(), "source": "kiosk",
                "parent_id": member["id"], "parent_name": member.get("name", ""),
                "location_id": resolved_location or child.get("location_id") or "",
            }
            await db.checkins.insert_one(cci)
            cci.pop("_id", None)
            child_checkins.append(cci)
    return {
        "message": "Checked in",
        "member_name": member.get("name"),
        "checkin": checkin,
        "child_checkins": child_checkins,
    }


# ========== VENUES ==========

@router.get("/venues")
async def list_venues(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    return await db.venues.find(query, {"_id": 0}).sort("name", 1).to_list(100)


@router.post("/venues")
async def create_venue(data: VenueCreate, current_user: dict = Depends(get_current_user)):
    venue = {"id": f"ven_{str(uuid.uuid4())[:8]}", **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.venues.insert_one(venue)
    venue.pop("_id", None)
    return venue


@router.put("/venues/{venue_id}")
async def update_venue(venue_id: str, data: VenueUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.venues.update_one({"id": venue_id}, {"$set": update_data})
    return await db.venues.find_one({"id": venue_id}, {"_id": 0})


@router.delete("/venues/{venue_id}")
async def delete_venue(venue_id: str, current_user: dict = Depends(get_current_user)):
    await db.venues.delete_one({"id": venue_id})
    return {"message": "Venue deleted"}


@router.get("/venues/{venue_id}/availability")
async def venue_availability(
    venue_id: str,
    date: str,
    end_date: Optional[str] = None,
    time: Optional[str] = None,
    end_time: Optional[str] = None,
    exclude_event_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return existing bookings on this venue in the given window and a computed
    conflict payload the UI can render inline before submit."""
    d_end = end_date or date
    events = await db.events.find(
        {"venue_id": venue_id, "status": {"$ne": "cancelled"}, "date": {"$lte": d_end}},
        {"_id": 0, "id": 1, "title": 1, "date": 1, "end_date": 1, "time": 1, "end_time": 1, "status": 1},
    ).to_list(500)
    events = [e for e in events if (e.get("end_date") or e.get("date")) >= date and e.get("id") != exclude_event_id]
    bookings = await db.public_bookings.find(
        {"venue_id": venue_id, "type": "space", "booking_date": {"$gte": date, "$lte": d_end}, "status": {"$nin": ["cancelled", "rejected"]}},
        {"_id": 0, "id": 1, "name": 1, "purpose": 1, "booking_date": 1, "start_time": 1, "end_time": 1, "status": 1},
    ).to_list(500)
    conflict = await _find_venue_conflict(venue_id, date, end_date, time, end_time, exclude_event_id=exclude_event_id)
    return {
        "venue_id": venue_id,
        "events": events,
        "space_bookings": bookings,
        "conflict": conflict,
        "can_override": _can_override_conflict(current_user),
    }


# ========== PUBLIC ENDPOINTS ==========

def _normalize_country_code(value: str) -> str:
    """Map freeform country names ('Uganda', 'USA', 'Haiti') to ISO-ish codes
    used by the public booking page filter ('UG', 'US', 'HT', 'KE', 'TH').
    Returns empty string for unrecognised input — callers should treat empty as
    'no country' (excluded from any specific filter)."""
    if not value:
        return ""
    s = str(value).strip().lower()
    table = {
        "uganda": "UG", "ug": "UG", "uga": "UG",
        "usa": "US", "us": "US", "united states": "US", "united states of america": "US", "america": "US",
        "kenya": "KE", "ke": "KE", "ken": "KE",
        "haiti": "HT", "haïti": "HT", "ht": "HT", "hti": "HT",
        "thailand": "TH", "th": "TH", "tha": "TH",
    }
    if s in table:
        return table[s]
    if len(s) == 2 and s.upper() in {"UG", "US", "KE", "HT", "TH"}:
        return s.upper()
    return ""


@router.get("/public/events")
async def public_events(country: Optional[str] = None):
    query = {"is_public": True, "status": "upcoming"}
    from datetime import timedelta
    max_date = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
    query["date"] = {"$lte": max_date}
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(200)

    # Resolve country code for every event. Priority:
    #   1. event.country (already stored)
    #   2. event's location.country
    #   3. walk up parent_id chain (sub-locations may not have country set)
    # Normalize to ISO code so freeform "Uganda" matches frontend's "UG".
    if events:
        loc_ids = list({e.get("location_id") for e in events if e.get("location_id")})
        loc_map = {}
        if loc_ids:
            locs = await db.locations.find(
                {"id": {"$in": loc_ids}},
                {"_id": 0, "id": 1, "country": 1, "parent_id": 1},
            ).to_list(500)
            for L in locs:
                loc_map[L["id"]] = L
            # Resolve parents for sub-locations without country
            parent_ids_needed = [L.get("parent_id") for L in locs if L.get("parent_id") and not L.get("country")]
            parent_ids_needed = list({p for p in parent_ids_needed if p})
            if parent_ids_needed:
                parents = await db.locations.find(
                    {"id": {"$in": parent_ids_needed}},
                    {"_id": 0, "id": 1, "country": 1},
                ).to_list(500)
                for p in parents:
                    loc_map[p["id"]] = p
        for ev in events:
            resolved = _normalize_country_code(ev.get("country"))
            if not resolved and ev.get("location_id"):
                loc = loc_map.get(ev["location_id"]) or {}
                resolved = _normalize_country_code(loc.get("country"))
                if not resolved and loc.get("parent_id"):
                    parent = loc_map.get(loc["parent_id"]) or {}
                    resolved = _normalize_country_code(parent.get("country"))
            ev["country_code"] = resolved
            # Keep `country` field present for backwards compat with existing UI
            if not ev.get("country"):
                ev["country"] = resolved or ""

    # iter 265 — Same venue_name resolution as list_events / public_events so
    # the events list card shows the venue without a second round-trip.
    if events:
        venue_ids = list({e.get("venue_id") for e in events if e.get("venue_id")})
        if venue_ids:
            venue_docs = await db.venues.find({"id": {"$in": venue_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
            subloc_docs = await db.locations.find({"id": {"$in": venue_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
            name_map = {v["id"]: v.get("name") for v in venue_docs}
            for s in subloc_docs:
                name_map.setdefault(s["id"], s.get("name"))
            for ev in events:
                if ev.get("venue_id") and name_map.get(ev["venue_id"]):
                    ev["venue_name"] = name_map[ev["venue_id"]]

    # iter 265 — Country filter. Events with an unresolved country_code
    # (no location country, unmapped freeform value, or intentionally
    # global) are treated as "global" and stay visible for ANY country
    # filter — otherwise a public event with no location would never
    # show up because the frontend always sends the visitor's country.
    if country and country != 'ALL':
        target = _normalize_country_code(country) or country.upper()
        events = [e for e in events if (not e.get("country_code")) or e.get("country_code") == target]

    return events


@router.get("/public/venues")
async def public_venues(country: Optional[str] = None):
    """Public-bookable venues, optionally filtered by country."""
    venues = await db.venues.find({"available": True, "is_bookable": {"$ne": False}}, {"_id": 0}).to_list(200)
    if not country or country == 'ALL':
        return venues
    target = _normalize_country_code(country) or country.upper()
    # Resolve country via location for venues that don't carry one
    loc_ids = list({v.get("location_id") for v in venues if v.get("location_id")})
    loc_map = {}
    if loc_ids:
        locs = await db.locations.find(
            {"id": {"$in": loc_ids}},
            {"_id": 0, "id": 1, "country": 1, "parent_id": 1},
        ).to_list(500)
        for L in locs:
            loc_map[L["id"]] = L
        parent_ids = [L.get("parent_id") for L in locs if L.get("parent_id") and not L.get("country")]
        parent_ids = list({p for p in parent_ids if p})
        if parent_ids:
            parents = await db.locations.find({"id": {"$in": parent_ids}}, {"_id": 0, "id": 1, "country": 1}).to_list(500)
            for p in parents:
                loc_map[p["id"]] = p
    out = []
    for v in venues:
        code = _normalize_country_code(v.get("country"))
        if not code and v.get("location_id"):
            loc = loc_map.get(v["location_id"]) or {}
            code = _normalize_country_code(loc.get("country"))
            if not code and loc.get("parent_id"):
                code = _normalize_country_code((loc_map.get(loc["parent_id"]) or {}).get("country"))
        v["country_code"] = code
        if code == target:
            out.append(v)
    return out


@router.post("/public/bookings/event")
async def public_book_event(data: PublicBookingCreate):
    event = await db.events.find_one({"id": data.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Resolve ticket tier (Odoo-style: multi-tier pricing)
    tiers = event.get("ticket_tiers") or []
    tier = None
    tier_id = getattr(data, "tier_id", None) or (data.model_dump().get("tier_id"))
    if tiers:
        if tier_id:
            tier = next((t for t in tiers if t.get("id") == tier_id), None)
            if not tier:
                raise HTTPException(status_code=400, detail="Invalid ticket tier")
        else:
            tier = tiers[0]  # backwards-compat: default to first tier
        tier_capacity = int(tier.get("capacity") or 0)
        tier_sold = int(tier.get("sold") or 0)
        if tier_capacity and tier_sold + data.num_tickets > tier_capacity:
            # Offer waitlist if enabled, else 400
            if event.get("waitlist_enabled", True):
                raise HTTPException(status_code=409, detail=f"Tier '{tier.get('name')}' is sold out. Use the waitlist endpoint.")
            raise HTTPException(status_code=400, detail=f"Tier '{tier.get('name')}' is sold out")
        is_free = float(tier.get("price") or 0) == 0
        price = float(tier.get("price") or 0)
    else:
        if event.get("registered", 0) >= event.get("capacity", 0):
            if event.get("waitlist_enabled", True):
                raise HTTPException(status_code=409, detail="Event is fully booked. Use the waitlist endpoint.")
            raise HTTPException(status_code=400, detail="Event is fully booked")
        is_free = event.get("is_free", True)
        price = event.get("price", 0)
    payment_method = data.payment_method if hasattr(data, 'payment_method') else None
    # Payment rules for paid events
    if not is_free and price > 0:
        method = payment_method or "card"
        event_date = event.get("date", "")
        days_until = 999
        if event_date:
            try:
                from datetime import date as dt_date
                ed = dt_date.fromisoformat(event_date)
                days_until = (ed - dt_date.today()).days
            except Exception:
                pass
        if method == "cash":
            if days_until <= 3:
                raise HTTPException(status_code=400, detail="Cash payments not accepted within 3 days of event. Please use card or mobile money.")
            payment_deadline = 2 if days_until <= 7 else 7
        else:
            payment_deadline = None
    else:
        payment_deadline = None
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id, **data.model_dump(),
        "event_title": event.get("title", ""),
        "is_free": is_free,
        "price": price,
        "total": price * (data.num_tickets or 1) if not is_free else 0,
        "payment_method": payment_method,
        "payment_status": "paid" if is_free else "pending",
        "payment_deadline_days": payment_deadline,
        "status": "confirmed" if is_free else "pending_payment",
        "ticket_ids": [f"TKT-{str(uuid.uuid4())[:4].upper()}" for _ in range(data.num_tickets)],
        "tier_id": tier.get("id") if tier else None,
        "tier_name": tier.get("name") if tier else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    # Update counts
    if tier:
        await db.events.update_one(
            {"id": data.event_id, "ticket_tiers.id": tier["id"]},
            {"$inc": {"registered": data.num_tickets, "ticket_tiers.$.sold": data.num_tickets}},
        )
    else:
        await db.events.update_one({"id": data.event_id}, {"$inc": {"registered": data.num_tickets}})
    booking.pop("_id", None)
    return booking


# ========== EVENT WAITLIST (Odoo-style auto-promote) ==========

@router.post("/public/events/{event_id}/waitlist")
async def join_event_waitlist(event_id: str, data: dict):
    """Add someone to the waitlist when an event/tier is sold out.
    Body: { name, email, phone?, num_tickets?, tier_id? }"""
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.get("waitlist_enabled", True):
        raise HTTPException(status_code=400, detail="Waitlist disabled for this event")
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name or not email:
        raise HTTPException(status_code=400, detail="name and email required")
    # De-dup: same email + tier
    existing = await db.event_waitlist.find_one({
        "event_id": event_id,
        "email": email,
        "tier_id": data.get("tier_id"),
        "status": "waiting",
    })
    if existing:
        raise HTTPException(status_code=400, detail="You are already on the waitlist for this tier")
    doc = {
        "id": f"wl_{uuid.uuid4().hex[:10]}",
        "event_id": event_id,
        "event_title": event.get("title"),
        "name": name,
        "email": email,
        "phone": (data.get("phone") or "").strip(),
        "num_tickets": int(data.get("num_tickets") or 1),
        "tier_id": data.get("tier_id"),
        "status": "waiting",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.event_waitlist.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/events/{event_id}/waitlist")
async def list_event_waitlist(event_id: str, current_user: dict = Depends(require_staff)):
    return await db.event_waitlist.find({"event_id": event_id}, {"_id": 0}).sort("created_at", 1).to_list(500)


@router.post("/events/{event_id}/waitlist/{wl_id}/promote")
async def promote_waitlist_entry(event_id: str, wl_id: str, current_user: dict = Depends(require_staff)):
    """Manually convert a waitlist entry into a confirmed booking (free; admin chases payment after)."""
    entry = await db.event_waitlist.find_one({"id": wl_id, "event_id": event_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    if entry.get("status") != "waiting":
        raise HTTPException(status_code=400, detail="Entry already processed")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    booking_id = f"book_{uuid.uuid4().hex[:12]}"
    tier = None
    if entry.get("tier_id") and event.get("ticket_tiers"):
        tier = next((t for t in event["ticket_tiers"] if t.get("id") == entry["tier_id"]), None)
    price = float(tier.get("price") or 0) if tier else float(event.get("price") or 0)
    is_free = price == 0
    booking = {
        "id": booking_id,
        "event_id": event_id,
        "event_title": event.get("title"),
        "name": entry["name"],
        "email": entry["email"],
        "phone": entry.get("phone"),
        "num_tickets": entry["num_tickets"],
        "is_free": is_free,
        "price": price,
        "total": price * entry["num_tickets"] if not is_free else 0,
        "payment_status": "paid" if is_free else "pending",
        "status": "confirmed" if is_free else "pending_payment",
        "ticket_ids": [f"TKT-{str(uuid.uuid4())[:4].upper()}" for _ in range(entry["num_tickets"])],
        "tier_id": entry.get("tier_id"),
        "tier_name": tier.get("name") if tier else None,
        "promoted_from_waitlist": wl_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    if tier:
        await db.events.update_one(
            {"id": event_id, "ticket_tiers.id": tier["id"]},
            {"$inc": {"registered": entry["num_tickets"], "ticket_tiers.$.sold": entry["num_tickets"]}},
        )
    else:
        await db.events.update_one({"id": event_id}, {"$inc": {"registered": entry["num_tickets"]}})
    await db.event_waitlist.update_one(
        {"id": wl_id},
        {"$set": {"status": "promoted", "promoted_at": booking["created_at"], "booking_id": booking_id}},
    )
    booking.pop("_id", None)
    return booking


@router.delete("/events/{event_id}/waitlist/{wl_id}")
async def cancel_waitlist_entry(event_id: str, wl_id: str, current_user: dict = Depends(require_staff)):
    res = await db.event_waitlist.update_one(
        {"id": wl_id, "event_id": event_id, "status": "waiting"},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Not found or already processed")
    return {"cancelled": 1}


@router.get("/events/{event_id}/attendees/export")
async def export_event_attendees(event_id: str, current_user: dict = Depends(require_staff)):
    """Export confirmed attendees as CSV."""
    from starlette.responses import StreamingResponse
    import io
    import csv
    event = await db.events.find_one({"id": event_id}, {"_id": 0, "title": 1})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    bookings = await db.public_bookings.find({"event_id": event_id}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Booking ID", "Name", "Email", "Phone", "Tickets", "Tier", "Status", "Payment Status", "Total", "Created At", "Ticket IDs"])
    for b in bookings:
        writer.writerow([
            b.get("id", ""),
            b.get("name", ""),
            b.get("email", ""),
            b.get("phone", ""),
            b.get("num_tickets", 1),
            b.get("tier_name") or "—",
            b.get("status", ""),
            b.get("payment_status", ""),
            b.get("total", 0),
            b.get("created_at", ""),
            "; ".join(b.get("ticket_ids") or []),
        ])
    buf.seek(0)
    safe = (event.get("title") or "event").replace(" ", "_")[:40]
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="attendees-{safe}-{event_id}.csv"'},
    )


@router.post("/public/bookings/space")
async def public_book_space(data: SpaceBookingCreate):
    venue = await db.venues.find_one({"id": data.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    # Prevent double-booking a venue on the public flow (no override for guests)
    conflict = await _find_venue_conflict(
        data.venue_id, data.booking_date, None, data.start_time, data.end_time,
    )
    if conflict:
        raise HTTPException(status_code=409, detail={
            "message": "Venue already booked for that time",
            "conflict": conflict,
            "can_override": False,
        })
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id, **data.model_dump(),
        "type": "space", "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    booking.pop("_id", None)
    return booking


# ========== PUBLIC RESOURCE (ASSET) BOOKING ==========
# Mirrors the /public/venues flow but for the resources/assets collection.
# Only resources flagged `is_bookable=True` AND `staff_only != True` AND `available=True` are exposed.

@router.get("/public/resources")
async def public_resources(country: Optional[str] = None):
    """Return resources that are publicly bookable. Excludes consumables, staff-only items,
    and resources currently marked unavailable. Country filter mirrors /public/venues."""
    query = {
        "is_bookable": True,
        "available": {"$ne": False},
        "$and": [
            {"$or": [{"staff_only": {"$exists": False}}, {"staff_only": False}, {"staff_only": None}]},
            {"$or": [{"is_consumable": {"$exists": False}}, {"is_consumable": False}, {"is_consumable": None}]},
        ],
    }
    resources = await db.resources.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    if not country or country == "ALL":
        return resources
    target = _normalize_country_code(country) or country.upper()
    # Walk location chain to resolve country (same pattern as venues)
    loc_ids = list({r.get("location_id") for r in resources if r.get("location_id")})
    loc_map = {}
    if loc_ids:
        locs = await db.locations.find(
            {"id": {"$in": loc_ids}},
            {"_id": 0, "id": 1, "country": 1, "parent_id": 1},
        ).to_list(500)
        for L in locs:
            loc_map[L["id"]] = L
        parent_ids = list({L.get("parent_id") for L in locs if L.get("parent_id") and not L.get("country")})
        if parent_ids:
            parents = await db.locations.find({"id": {"$in": parent_ids}}, {"_id": 0, "id": 1, "country": 1}).to_list(500)
            for p in parents:
                loc_map[p["id"]] = p
    out = []
    for r in resources:
        code = _normalize_country_code(r.get("country"))
        if not code and r.get("location_id"):
            loc = loc_map.get(r["location_id"]) or {}
            code = _normalize_country_code(loc.get("country"))
            if not code and loc.get("parent_id"):
                code = _normalize_country_code((loc_map.get(loc["parent_id"]) or {}).get("country"))
        r["country_code"] = code
        if code == target:
            out.append(r)
    return out


@router.post("/public/bookings/resource")
async def public_book_resource(data: dict):
    """Public resource booking. Body: { name, email, phone?, resource_id, booking_date, start_time, end_time, purpose? }.
    Validates the resource exists AND is_bookable. Creates a `public_bookings` row with type='resource' (status=pending)
    and a mirror entry in `resource_bookings` so staff see the hold immediately on /resources."""
    required = ("name", "email", "resource_id", "booking_date", "start_time", "end_time")
    missing = [k for k in required if not (data or {}).get(k)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required field(s): {', '.join(missing)}")
    resource = await db.resources.find_one({"id": data["resource_id"]}, {"_id": 0})
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not resource.get("is_bookable"):
        raise HTTPException(status_code=400, detail="This resource is not publicly bookable")
    if resource.get("staff_only"):
        raise HTTPException(status_code=403, detail="This resource is reserved for staff use")
    if resource.get("available") is False:
        raise HTTPException(status_code=400, detail="This resource is currently unavailable")
    if data["end_time"] <= data["start_time"]:
        raise HTTPException(status_code=400, detail="End time must be after start time")
    # Conflict check — overlapping confirmed/pending bookings on the same resource/date
    overlap = await db.resource_bookings.find_one({
        "resource_id": data["resource_id"],
        "date": data["booking_date"],
        "status": {"$ne": "cancelled"},
        "start_time": {"$lt": data["end_time"]},
        "end_time": {"$gt": data["start_time"]},
    })
    if overlap:
        raise HTTPException(status_code=409, detail="That time slot is already booked. Please pick a different time.")
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    booking = {
        "id": booking_id,
        "name": data.get("name", "").strip(),
        "email": (data.get("email") or "").strip().lower(),
        "phone": data.get("phone", "").strip(),
        "resource_id": data["resource_id"],
        "resource_name": resource.get("name"),
        "booking_date": data["booking_date"],
        "start_time": data["start_time"],
        "end_time": data["end_time"],
        "purpose": (data.get("purpose") or "").strip(),
        "type": "resource",
        "status": "pending",
        "location_id": resource.get("location_id"),
        "created_at": now_iso,
    }
    await db.public_bookings.insert_one(booking)
    # Mirror to internal resource_bookings so staff /resources sees the hold immediately
    await db.resource_bookings.insert_one({
        "id": f"rb_{str(uuid.uuid4())[:8]}",
        "resource_id": data["resource_id"],
        "resource_name": resource.get("name"),
        "booked_by": booking["name"],
        "booker_email": booking["email"],
        "booker_phone": booking["phone"],
        "date": data["booking_date"],
        "start_time": data["start_time"],
        "end_time": data["end_time"],
        "notes": booking["purpose"],
        "status": "pending",
        "source": "public",
        "public_booking_id": booking_id,
        "location_id": resource.get("location_id"),
        "created_at": now_iso,
    })
    booking.pop("_id", None)
    return booking


@router.get("/public/bookings/status")
async def check_booking_status(booking_id: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None):
    query = {}
    if booking_id:
        query["id"] = booking_id
    elif email:
        query["email"] = email.lower()
    elif phone:
        query["phone"] = phone
    else:
        raise HTTPException(status_code=400, detail="Provide booking_id, email, or phone")
    bookings = await db.public_bookings.find(query, {"_id": 0}).to_list(20)
    return bookings


@router.put("/public/bookings/{booking_id}/mark-paid")
async def mark_booking_paid(booking_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Mark a booking/ticket as paid. Staff+ only. Requires transaction reference."""
    booking = await db.public_bookings.find_one({"id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    await db.public_bookings.update_one({"id": booking_id}, {"$set": {
        "payment_status": "paid", "status": "confirmed",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "paid_by": current_user["id"],
        "transaction_ref": data.get("transaction_ref", ""),
        "payment_notes": data.get("notes", ""),
    }})
    return {"message": "Booking marked as paid"}


@router.get("/public/bookings/pending-payments")
async def list_pending_payments(current_user: dict = Depends(require_staff)):
    """List bookings with pending payments."""
    bookings = await db.public_bookings.find(
        {"payment_status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return bookings


# ========== POLICIES ==========

@router.get("/public/policies")
async def get_policies():
    """Return organizational policies. Admin-editable via PUT, falls back to defaults."""
    stored = await db.legal_policies.find_one({"_key": "policies"}, {"_id": 0})
    if stored and stored.get("policies"):
        return stored["policies"]
    return _default_policies()


@router.put("/policies")
async def update_policies(data: dict, current_user: dict = Depends(require_admin)):
    """Admin edits policies. Body: {policies: {privacy_policy: {title, content}, ...}}"""
    policies = data.get("policies", data)
    policies_clean = {}
    for key, val in policies.items():
        if isinstance(val, dict) and "title" in val and "content" in val:
            policies_clean[key] = {"title": val["title"], "content": val["content"], "last_updated": datetime.now(timezone.utc).isoformat()}
    await db.legal_policies.update_one({"_key": "policies"}, {"$set": {"_key": "policies", "policies": policies_clean, "updated_by": current_user["id"], "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return policies_clean


@router.get("/policies")
async def get_policies_admin(current_user: dict = Depends(get_current_user)):
    """Get policies for admin editing"""
    stored = await db.legal_policies.find_one({"_key": "policies"}, {"_id": 0})
    if stored and stored.get("policies"):
        return stored["policies"]
    return _default_policies()


def _default_policies():
    return {
        "privacy_policy": {
            "title": "Privacy Policy",
            "content": """58:12 Global, Inc. ("we," "us," "our") is a Christ-centered nonprofit organization (EIN pending) headquartered in Holmes County, Ohio, USA, with operations in Uganda, Kenya, Thailand, and Haiti. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use 58:12 Connect ("the Platform") and our services.

INFORMATION WE COLLECT
Personal Information: Name, email address, phone number, date of birth, gender, mailing address, national identification documents (ID number, passport), photographs, and emergency contact details.
Children's Information: Name, date of birth, grade/class, medical information, allergies, guardian/parent associations. We comply with COPPA (Children's Online Privacy Protection Act) for users under 13 in the United States.
Financial Information: Donation records, payment method details (processed through third-party payment processors — we do not store full credit card numbers), expense receipts, and transaction history.
Check-in Data: Attendance records, timestamps, location data, device identifiers, and biometric scan data (fingerprint, facial recognition) where enabled with explicit consent.
Technical Data: IP address, browser type, device information, cookies, and usage analytics.
Communication Data: Chat messages, announcements, AI assistant interactions, and call metadata.

LEGAL BASIS FOR PROCESSING
We process personal data under the following legal bases, as applicable across our jurisdictions:
- Consent (GDPR Art. 6(1)(a), PDPA Section 19, Uganda DPA Section 7)
- Performance of a contract or service
- Legitimate interests of the organization (ministry operations, safeguarding)
- Legal obligations (financial record keeping, child protection reporting)

YOUR RIGHTS
Under applicable data protection laws (EU GDPR, Uganda Data Protection Act 2019, Kenya Data Protection Act 2019, Thailand PDPA, US state privacy laws), you have the right to:
- Access your personal data
- Correct inaccurate data
- Request deletion ("right to be forgotten")
- Data portability (receive your data in machine-readable format)
- Object to processing
- Withdraw consent at any time
- Lodge a complaint with a supervisory authority

To exercise these rights, use the "My Privacy" section in the Platform or contact us at privacy@5812global.org.

DATA RETENTION
- Active member data: Duration of relationship plus 3 years
- Financial records: 7 years (US IRS requirements, applicable tax laws)
- Check-in/attendance data: 2 years
- Children's data: Until child reaches 18 or relationship ends, whichever is later
- Communication data: 1 year for chat messages, 90 days for AI interactions

DATA TRANSFERS
As an international organization, we transfer data between our locations in the USA, Uganda, Kenya, Thailand, and Haiti. Transfers are protected through:
- Standard Contractual Clauses (EU GDPR Chapter V)
- Organizational security policies and encryption
- Access controls limiting data to authorized personnel in each jurisdiction

SECURITY MEASURES
We implement industry-standard security measures including encryption in transit (TLS/SSL), role-based access control (RBAC), session management with secure storage, two-factor authentication (2FA), and regular access audits.

COOKIES AND TRACKING
We use essential cookies for authentication and session management. Location data is used only with consent to display relevant local events. We do not sell personal data to third parties. We do not use third-party advertising trackers.

CHILDREN'S PRIVACY
We take children's privacy seriously. Children's data is collected only with parental/guardian consent and is used solely for ministry program management, attendance tracking, and safeguarding purposes. Parents may review, modify, or request deletion of their children's data at any time.

CONTACT
58:12 Global, Inc.
Holmes County, Ohio, USA
Phone: 330-521-1948
Email: privacy@5812global.org
Website: www.5812-global.org

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
        "terms_of_service": {
            "title": "Terms of Service",
            "content": """These Terms of Service ("Terms") govern your use of 58:12 Connect ("the Platform"), operated by 58:12 Global, Inc. ("we," "us," "our"), a Christ-centered nonprofit organization.

ACCEPTANCE OF TERMS
By accessing or using the Platform, you agree to be bound by these Terms. If you do not agree, do not use the Platform. If you are using the Platform on behalf of an organization, you represent that you have authority to bind that organization.

ELIGIBILITY
You must be at least 13 years old to create an account. Users under 18 require parental or guardian consent. Parents/guardians are responsible for their children's use of the Platform.

ACCOUNT REGISTRATION
- New accounts start as "Member" status and require administrator approval before full access is granted
- You are responsible for maintaining the confidentiality of your login credentials
- Default passwords must be changed upon first login
- You must provide accurate and complete information
- You must notify us immediately of any unauthorized use of your account

ACCEPTABLE USE
You agree NOT to:
- Use the Platform for any unlawful purpose
- Attempt to gain unauthorized access to restricted areas or other users' accounts
- Upload malicious software, viruses, or harmful content
- Harass, threaten, or discriminate against any person
- Share login credentials with unauthorized persons
- Use the Platform to collect personal information about others without their consent
- Circumvent access controls or security measures

OUR SERVICES
58:12 Connect provides tools for nonprofit ministry management including:
- Member and family management
- Event planning and registration
- Check-in and attendance tracking
- Financial tracking (donations, expenses)
- Internal communications and calling
- Volunteer coordination
- Resource management
- Access control for physical locations

SERVICE AVAILABILITY
We strive for continuous availability but do not guarantee uninterrupted service. We may perform maintenance, updates, or modifications at any time. We are not liable for any service interruptions.

INTELLECTUAL PROPERTY
The Platform, its design, features, and content are owned by 58:12 Global, Inc. User-generated content (messages, uploads, etc.) remains the property of the user, but you grant us a license to store, display, and process it as necessary to provide the service.

PAYMENTS AND REFUNDS
- Free events require no payment
- Paid events: Full refund if cancelled 7+ days before event; 50% refund if cancelled 3-7 days before; no refund within 3 days
- Cash bookings must be fulfilled within the agreed deadline or are automatically cancelled
- All payment processing is handled by third-party providers; we do not store full payment card details

LIMITATION OF LIABILITY
To the maximum extent permitted by law, 58:12 Global shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of the Platform. Our total liability shall not exceed the amount you paid us in the 12 months preceding the claim.

TERMINATION
We may suspend or terminate your account at any time for violation of these Terms or for any other reason at our discretion. Upon termination, your right to use the Platform ceases immediately. You may request export of your data before termination.

GOVERNING LAW
These Terms are governed by the laws of the State of Ohio, United States, without regard to conflict of law principles. For users in other jurisdictions, applicable local consumer protection laws may also apply.

CHANGES TO TERMS
We reserve the right to modify these Terms at any time. Changes will be posted on the Platform with the updated date. Continued use after changes constitutes acceptance.

CONTACT
58:12 Global, Inc.
Holmes County, Ohio, USA
Phone: 330-521-1948
Email: legal@5812global.org
Website: www.5812-global.org

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
        "refund_policy": {
            "title": "Refund & Cancellation Policy",
            "content": """This policy applies to all bookings, event registrations, and purchases made through 58:12 Connect.

EVENT REGISTRATIONS
- Free events: No payment required. Cancellations accepted at any time
- Paid events: Full refund if cancelled 7 or more days before the event date. 50% refund if cancelled 3-7 days before the event. No refund for cancellations within 3 days of the event
- Event cancellation by organizer: Full refund will be issued regardless of timing

PAYMENT METHODS AND DEADLINES
- Credit/Debit Card: Payment processed immediately at time of booking
- MTN Mobile Money: Payment processed immediately
- Airtel Money: Payment processed immediately
- Venmo: Payment must be sent within 7 days of booking (2 days if event is within 7 days)
- Cash: Payment must be received in person within 7 days of booking (2 days if event is within 7 days). Cash bookings are not accepted within 3 days of the event

UNPAID BOOKINGS
Bookings with pending payment status will be automatically cancelled if payment is not received by the deadline. A notification will be sent before cancellation.

SPACE/VENUE BOOKINGS
Venue booking cancellations follow the same refund schedule as events. Damage deposits (if applicable) are returned within 14 days after the event, subject to inspection.

PRODUCT PURCHASES
- Physical goods: Returns accepted within 30 days of purchase in original condition. Buyer pays return shipping
- Digital goods: No refunds after delivery

DISPUTE RESOLUTION
For refund disputes, contact us at finance@5812global.org. We aim to resolve all disputes within 14 business days.

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
        "employee_onboarding": {
            "title": "Employee & Volunteer Onboarding Policy",
            "content": """This policy applies to all staff, volunteers, interns, and contractors of 58:12 Global across all locations.

ACCOUNT CREATION AND APPROVAL
- All new accounts start as "Member" status with pending approval
- Administrative approval is required before system access is granted
- New staff accounts are assigned a default password which must be changed at first login
- Two-factor authentication (2FA) is recommended for all staff accounts

BACKGROUND CHECKS
All personnel undergo background checks compliant with applicable laws:
- USA: FBI fingerprint check, state criminal history, sex offender registry
- Uganda: Police clearance certificate, reference checks per Employment Act 2006
- Kenya: Certificate of Good Conduct per Kenya Police Service, DCI clearance
- Thailand: Criminal record check per local law enforcement
- Haiti: Background verification through local authorities

CHILD SAFEGUARDING
All personnel working directly with children or vulnerable persons must:
- Complete safeguarding training within 30 days of onboarding
- Pass enhanced background checks (above standard requirements)
- Sign the 58:12 Global Child Protection Policy acknowledgment
- Report any safeguarding concerns immediately to designated safeguarding officers
- Comply with mandatory reporting laws in their jurisdiction

CONFIDENTIALITY
All staff and volunteers must sign a confidentiality agreement covering:
- Member and beneficiary personal information
- Financial data and donation records
- Internal communications
- Medical and sensitive personal data
- Organizational strategic information

CODE OF CONDUCT
Personnel must comply with the 58:12 Global Code of Conduct which includes:
- Professional behavior in all interactions
- Respect for cultural diversity across all locations
- Zero tolerance for abuse, harassment, or discrimination
- Responsible use of organizational resources and technology
- Compliance with local laws in all jurisdictions of operation

TRAINING REQUIREMENTS
- Safeguarding training (mandatory, within 30 days)
- Data protection and privacy (within 60 days)
- Platform usage training (within 14 days)
- Location-specific orientation
- Annual refresher training

TERMINATION OF ACCESS
Upon departure, all system access is immediately revoked. Former personnel may request export of their personal data within 30 days of departure.

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
        "data_retention": {
            "title": "Data Retention Policy",
            "content": """This policy defines how long 58:12 Global retains different categories of data across all jurisdictions.

RETENTION SCHEDULES
- Active member/user profiles: Duration of relationship plus 3 years
- Inactive member profiles: 3 years after last activity, then anonymized
- Financial records (donations, expenses, transfers): 7 years (US IRS, Uganda URA, Kenya KRA requirements)
- Check-in/attendance data: 2 years
- Chat messages and communications: 1 year
- AI assistant interaction logs: 90 days
- Call recordings and metadata: 6 months
- Event registrations and bookings: 3 years
- Children's records: Until child reaches 18 or relationship ends, plus 3 years
- Access control logs (restricted areas): 1 year
- Audit trail/activity logs: 5 years
- Documents and ID scans: Duration of relationship plus 1 year, or until document expiry

DELETION AND ANONYMIZATION
- Users may request data deletion at any time via the "My Privacy" section
- Deletion requests are processed within 30 days
- Some data may be retained for legal compliance despite deletion request (financial records, safeguarding records)
- Anonymization is available as an alternative to deletion — personal identifiers are replaced with anonymous values while aggregate data is preserved

AUTOMATED RETENTION
The system automatically:
- Archives inactive accounts after 2 years of inactivity
- Flags expired documents for renewal
- Removes temporary guest check-in data after the retention period
- Purges AI interaction logs after 90 days

CROSS-BORDER CONSIDERATIONS
Data retention may be extended where required by local law (e.g., Uganda's mandatory data retention requirements, Kenya's financial record keeping requirements). The longest applicable retention period across jurisdictions applies.

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
        "cookie_policy": {
            "title": "Cookie & Tracking Policy",
            "content": """This policy explains how 58:12 Connect uses cookies and similar technologies.

ESSENTIAL COOKIES
We use strictly necessary cookies for:
- User authentication and session management (session token)
- Security (CSRF protection)
- User preference storage (dark mode, language, campus selection)
These cookies cannot be disabled as they are required for the Platform to function.

FUNCTIONAL COOKIES
With your consent, we use:
- Location detection (to show relevant local events)
- Calendar preferences
- Kiosk mode settings
These can be managed in your browser settings.

WE DO NOT USE
- Third-party advertising cookies
- Social media tracking pixels
- Cross-site tracking technologies
- We do not sell, share, or monetize any user data

LOCATION DATA
We may request access to your device location solely to:
- Auto-detect your country for event filtering on the public marketplace
- Determine the nearest campus for check-in
Location data is processed locally and not stored on our servers unless you explicitly check in.

MANAGING COOKIES
You can control cookies through your browser settings. Blocking essential cookies may prevent the Platform from functioning correctly.

COMPLIANCE
This cookie policy complies with:
- EU ePrivacy Directive (Cookie Law)
- GDPR cookie consent requirements
- Thailand PDPA cookie provisions
- California Consumer Privacy Act (CCPA) disclosure requirements

Last Updated: {date}""".replace("{date}", datetime.now(timezone.utc).strftime("%B %d, %Y")),
        },
    }


# ========== RECURRING EVENT GENERATION ==========

@router.post("/events/generate-recurring")
async def generate_recurring_events(data: dict, current_user: dict = Depends(get_current_user)):
    """Generate recurring events from a pattern specification.
    Supports: daily, weekly, biweekly, monthly, yearly, nth_week, nth_month patterns."""
    import calendar as cal_module

    pattern = data.get("pattern", "weekly")  # daily, weekly, biweekly, monthly, bimonthly, quarterly, yearly, nth_week, nth_month, custom
    title = data.get("title", "Recurring Event")
    event_type = data.get("type", "service")
    location = data.get("location", "")
    location_id = data.get("location_id", "")
    time_str = data.get("time", "09:00")
    end_time = data.get("end_time", "")
    start_date = data.get("start_date", datetime.now(timezone.utc).isoformat()[:10])
    occurrences = min(int(data.get("occurrences", 12)), 104)
    interval = max(int(data.get("interval", 1)), 1)
    capacity = int(data.get("capacity", 100))
    is_public = data.get("is_public", True)
    day_of_week = int(data.get("day_of_week", 0))
    nth_week = int(data.get("nth_week", 1))
    day_of_month = int(data.get("day_of_month", 1))
    end_date = data.get("end_date")
    custom_dates = data.get("custom_dates", [])  # For custom pattern: list of date strings
    days_of_week = data.get("days_of_week", [])  # For custom: multiple days per week

    from datetime import timedelta
    start = datetime.fromisoformat(start_date)
    created = []

    for i in range(occurrences):
        event_date = None

        if pattern == "daily":
            event_date = start + timedelta(days=i * interval)

        elif pattern == "weekly":
            event_date = start + timedelta(weeks=i * interval)

        elif pattern == "biweekly":
            event_date = start + timedelta(weeks=i * 2)

        elif pattern == "monthly":
            month = start.month + i * interval - 1
            year = start.year + month // 12
            month = month % 12 + 1
            day = min(start.day, cal_module.monthrange(year, month)[1])
            event_date = start.replace(year=year, month=month, day=day)

        elif pattern == "bimonthly":
            month = start.month + i * 2 - 1
            year = start.year + month // 12
            month = month % 12 + 1
            day = min(start.day, cal_module.monthrange(year, month)[1])
            event_date = start.replace(year=year, month=month, day=day)

        elif pattern == "quarterly":
            month = start.month + i * 3 - 1
            year = start.year + month // 12
            month = month % 12 + 1
            day = min(start.day, cal_module.monthrange(year, month)[1])
            event_date = start.replace(year=year, month=month, day=day)

        elif pattern == "custom" and custom_dates:
            if i < len(custom_dates):
                try:
                    event_date = datetime.fromisoformat(custom_dates[i])
                except Exception:
                    continue
            else:
                break

        elif pattern == "custom_weekly" and days_of_week:
            # Multiple days per week (e.g., Mon+Wed+Fri)
            week_num = i // len(days_of_week)
            day_idx = i % len(days_of_week)
            target_dow = days_of_week[day_idx]
            base = start + timedelta(weeks=week_num * interval)
            days_ahead = (target_dow - base.weekday()) % 7
            event_date = base + timedelta(days=days_ahead)

        elif pattern == "yearly":
            try:
                event_date = start.replace(year=start.year + i * interval)
            except ValueError:
                # Feb 29 on non-leap year
                event_date = start.replace(year=start.year + i * interval, day=28)

        elif pattern == "nth_week":
            month = start.month + i * interval - 1
            year = start.year + month // 12
            month = month % 12 + 1
            weeks = cal_module.monthcalendar(year, month)
            matching = [w[day_of_week] for w in weeks if w[day_of_week] != 0]
            if nth_week == -1 and matching:
                day = matching[-1]
            elif 1 <= nth_week <= len(matching):
                day = matching[nth_week - 1]
            else:
                continue
            event_date = datetime(year, month, day)

        elif pattern == "nth_month":
            month = start.month + i * interval - 1
            year = start.year + month // 12
            month = month % 12 + 1
            max_day = cal_module.monthrange(year, month)[1]
            day = min(day_of_month, max_day)
            event_date = datetime(year, month, day)

        if event_date is None:
            continue

        date_str = event_date.strftime("%Y-%m-%d")
        if end_date and date_str > end_date:
            break

        event_id = f"evt_{str(uuid.uuid4())[:8]}"
        doc = {
            "id": event_id, "title": title, "type": event_type,
            "date": date_str, "time": time_str, "end_time": end_time,
            "location": location, "location_id": location_id,
            "capacity": capacity, "registered": 0, "status": "upcoming",
            "is_public": is_public, "is_free": True, "visibility": "external",
            "is_recurring": True, "recurrence_pattern": pattern,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.events.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)

    return {"created": len(created), "events": created}
