"""Volunteer scheduling endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from deps import get_current_user, db, get_campus_filter, default_creation_location
from typing import Optional
import uuid

router = APIRouter(prefix="/api")


@router.get("/volunteer/shifts")
async def list_shifts(event_id: Optional[str] = None, location_id: Optional[str] = None, date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    # Always scope by the caller's active campus so a regional director in one
    # location doesn't see (or accidentally staff) shifts from another.
    campus = await get_campus_filter(current_user) or {}
    query = dict(campus)
    if event_id:
        query["event_id"] = event_id
    if location_id:
        # Explicit filter narrows further — but only within the scoped campus.
        query["location_id"] = location_id
    if date:
        query["date"] = date
    shifts = await db.volunteer_shifts.find(query, {"_id": 0}).sort("date", 1).to_list(200)
    return shifts


@router.get("/volunteer/available-staff")
async def available_staff(current_user: dict = Depends(get_current_user)):
    """Return the pool of staff/volunteers assignable to a shift, scoped to
    the caller's active campus. Used by the FE assign-volunteer picker so it
    doesn't offer global (or out-of-scope) users."""
    campus = await get_campus_filter(current_user) or {}
    q: dict = {"status": {"$ne": "archived"}}
    q.update(campus)
    rows = []
    async for u in db.users.find(q, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1, "location_ids": 1}):
        rows.append({
            "id": u["id"], "name": u.get("name") or u.get("email"),
            "role": u.get("role") or "",
        })
    rows.sort(key=lambda r: (r.get("name") or "").lower())
    return rows


@router.post("/volunteer/shifts")
async def create_shift(data: dict, current_user: dict = Depends(get_current_user)):
    shift_id = f"shift_{str(uuid.uuid4())[:8]}"
    # iter-main-loc: default to the caller's MAIN campus (not switched active
    # campus) so shifts created without an explicit location don't scatter
    # across whichever campus they've switched to via the campus switcher.
    location_id = default_creation_location(current_user, data.get("location_id"))
    doc = {
        "id": shift_id,
        "title": data.get("title", "Volunteer Shift"),
        "event_id": data.get("event_id"),
        "location_id": location_id,
        "date": data.get("date"),
        "start_time": data.get("start_time", "09:00"),
        "end_time": data.get("end_time", "17:00"),
        "role": data.get("role", "General"),
        "slots": int(data.get("slots", 5)),
        "assigned": [],
        "notes": data.get("notes", ""),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.volunteer_shifts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/volunteer/shifts/{shift_id}")
async def update_shift(shift_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    data.pop("_id", None)
    data.pop("id", None)
    await db.volunteer_shifts.update_one({"id": shift_id}, {"$set": data})
    return {"id": shift_id, **data}


@router.delete("/volunteer/shifts/{shift_id}")
async def delete_shift(shift_id: str, current_user: dict = Depends(get_current_user)):
    await db.volunteer_shifts.delete_one({"id": shift_id})
    return {"message": "Shift deleted"}


@router.post("/volunteer/shifts/{shift_id}/assign")
async def assign_volunteer(shift_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    member_id = data.get("member_id")
    name = data.get("name", "")
    shift = await db.volunteer_shifts.find_one({"id": shift_id}, {"_id": 0})
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    if len(shift.get("assigned", [])) >= shift.get("slots", 5):
        raise HTTPException(status_code=400, detail="Shift is full")
    await db.volunteer_shifts.update_one(
        {"id": shift_id},
        {"$addToSet": {"assigned": {"member_id": member_id, "name": name, "assigned_at": datetime.now(timezone.utc).isoformat()}}},
    )
    return {"message": f"{name or member_id} assigned to shift"}


@router.delete("/volunteer/shifts/{shift_id}/assign/{member_id}")
async def unassign_volunteer(shift_id: str, member_id: str, current_user: dict = Depends(get_current_user)):
    await db.volunteer_shifts.update_one({"id": shift_id}, {"$pull": {"assigned": {"member_id": member_id}}})
    return {"message": "Volunteer removed from shift"}


@router.get("/volunteer/my-shifts")
async def my_shifts(current_user: dict = Depends(get_current_user)):
    shifts = await db.volunteer_shifts.find({"assigned.member_id": current_user["id"]}, {"_id": 0}).sort("date", 1).to_list(50)
    return shifts


# ============================================================
# Auto-populate shifts from a public event
# ============================================================

# Sensible default volunteer roles per event type — staff can override per generation.
DEFAULT_ROLES_BY_EVENT_TYPE = {
    "service": [
        {"role": "Greeter", "slots": 4},
        {"role": "Usher", "slots": 6},
        {"role": "Worship", "slots": 4},
        {"role": "Children Ministry", "slots": 6},
        {"role": "Media/Tech", "slots": 3},
        {"role": "Hospitality", "slots": 3},
        {"role": "Security", "slots": 2},
        {"role": "Parking", "slots": 3},
    ],
    "conference": [
        {"role": "Greeter", "slots": 4},
        {"role": "Usher", "slots": 6},
        {"role": "Media/Tech", "slots": 4},
        {"role": "Hospitality", "slots": 5},
        {"role": "Security", "slots": 3},
    ],
    "outreach": [
        {"role": "General", "slots": 10},
        {"role": "Hospitality", "slots": 4},
        {"role": "Children Ministry", "slots": 4},
    ],
    "workshop": [
        {"role": "Greeter", "slots": 2},
        {"role": "Media/Tech", "slots": 2},
        {"role": "Hospitality", "slots": 3},
    ],
    "training": [
        {"role": "Greeter", "slots": 2},
        {"role": "Media/Tech", "slots": 2},
        {"role": "Hospitality", "slots": 3},
    ],
    "community": [
        {"role": "General", "slots": 6},
        {"role": "Hospitality", "slots": 4},
        {"role": "Children Ministry", "slots": 4},
    ],
    "meeting": [
        {"role": "Greeter", "slots": 1},
        {"role": "Hospitality", "slots": 2},
    ],
    "social": [
        {"role": "Hospitality", "slots": 5},
        {"role": "Greeter", "slots": 2},
        {"role": "Children Ministry", "slots": 3},
    ],
}

GENERIC_DEFAULTS = [
    {"role": "Greeter", "slots": 2},
    {"role": "Usher", "slots": 4},
    {"role": "Hospitality", "slots": 3},
    {"role": "Media/Tech", "slots": 2},
]


@router.get("/volunteer/role-defaults")
async def volunteer_role_defaults(event_type: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Return the suggested set of roles + slot counts to pre-populate the
    auto-generate dialog. Picks by event.type, falling back to a generic
    template so any event can still be auto-populated."""
    et = (event_type or "").strip().lower()
    return {
        "event_type": et,
        "roles": DEFAULT_ROLES_BY_EVENT_TYPE.get(et) or GENERIC_DEFAULTS,
        "all_role_options": [
            "General", "Greeter", "Usher", "Worship", "Children Ministry",
            "Media/Tech", "Security", "Hospitality", "Parking",
        ],
    }


@router.post("/volunteer/shifts/generate-from-event")
async def generate_shifts_from_event(data: dict, current_user: dict = Depends(get_current_user)):
    """Create a batch of volunteer shifts for a given event in one call.
    Body:
      { event_id, roles: [{role, slots, start_time?, end_time?}], replace?: false }
    Returns: { created: [...], skipped: [...] }
    - Idempotent per (event_id, role): existing shift for the same pair is skipped
      unless `replace=True`, in which case the existing shift's slot count and
      time fields are updated in place.
    - Pulls date / start_time / end_time / location_id from the event itself.
    """
    event_id = (data.get("event_id") or "").strip()
    roles = data.get("roles") or []
    replace = bool(data.get("replace"))
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id required")
    if not isinstance(roles, list) or not roles:
        raise HTTPException(status_code=400, detail="roles[] required (each: {role, slots})")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Per the previous Pass 1 fix, public events are no longer required to be
    # tagged is_public — any event can spawn shifts. We do enforce the user has
    # access (i.e. it's in their campus scope).
    date = event.get("date")
    start_default = event.get("time") or "09:00"
    end_default = event.get("end_time") or "12:00"
    location_id = event.get("location_id")
    if not date:
        raise HTTPException(status_code=400, detail="Event has no date — set it before generating shifts")
    now_iso = datetime.now(timezone.utc).isoformat()
    created, skipped, updated = [], [], []
    for r in roles:
        role_name = (r.get("role") or "").strip()
        if not role_name:
            continue
        slots = max(1, min(int(r.get("slots") or 1), 200))
        start_time = (r.get("start_time") or start_default)
        end_time = (r.get("end_time") or end_default)
        existing = await db.volunteer_shifts.find_one(
            {"event_id": event_id, "role": role_name},
            {"_id": 0},
        )
        if existing:
            if replace:
                await db.volunteer_shifts.update_one(
                    {"id": existing["id"]},
                    {"$set": {
                        "slots": slots,
                        "start_time": start_time,
                        "end_time": end_time,
                        "date": date,
                        "location_id": location_id,
                        "updated_at": now_iso,
                        "updated_by": current_user["id"],
                    }},
                )
                fresh = await db.volunteer_shifts.find_one({"id": existing["id"]}, {"_id": 0})
                updated.append(fresh)
            else:
                skipped.append({"role": role_name, "shift_id": existing["id"]})
            continue
        shift_id = f"shift_{str(uuid.uuid4())[:8]}"
        doc = {
            "id": shift_id,
            "title": f"{event.get('title') or 'Event'} — {role_name}",
            "event_id": event_id,
            "location_id": location_id,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "role": role_name,
            "slots": slots,
            "assigned": [],
            "notes": "",
            "auto_generated_from_event": True,
            "created_by": current_user["id"],
            "created_at": now_iso,
        }
        await db.volunteer_shifts.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
    return {
        "event_id": event_id,
        "event_title": event.get("title"),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_created": len(created),
        "total_updated": len(updated),
        "total_skipped": len(skipped),
    }
