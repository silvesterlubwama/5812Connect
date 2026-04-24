"""Programmes (Outreach), Programme Categories, Recurring Events"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, _audit, logger, get_campus_filter
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import calendar

router = APIRouter(prefix="/api", tags=["programmes"])


class ProgrammeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "community"
    status: str = "active"
    location: Optional[str] = None
    location_id: Optional[str] = None
    start_date: Optional[str] = None
    target: Optional[int] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_day: Optional[int] = None
    recurrence_time: Optional[str] = None
    recurrence_end_time: Optional[str] = None


class SessionCreate(BaseModel):
    program_id: str
    date: str
    time: Optional[str] = None
    location: Optional[str] = None
    attendees: int = 0
    notes: Optional[str] = None
    led_by: Optional[str] = None


# ========== PROGRAMME CATEGORIES ==========

@router.get("/programme-categories")
async def list_programme_categories(current_user: dict = Depends(get_current_user)):
    cats = await db.programme_categories.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    if not cats:
        defaults = [
            {"id": "pcat_community", "name": "community", "label": "Community", "color": "#10b981"},
            {"id": "pcat_health", "name": "health", "label": "Health", "color": "#ef4444"},
            {"id": "pcat_education", "name": "education", "label": "Education", "color": "#3b82f6"},
            {"id": "pcat_welfare", "name": "welfare", "label": "Welfare", "color": "#f59e0b"},
            {"id": "pcat_sports", "name": "sports", "label": "Sports", "color": "#8b5cf6"},
            {"id": "pcat_ministry", "name": "ministry", "label": "Ministry", "color": "#6366f1"},
        ]
        await db.programme_categories.insert_many(defaults)
        for d in defaults:
            d.pop("_id", None)
        return defaults
    return cats


@router.post("/programme-categories")
async def create_programme_category(data: dict, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"pcat_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", "").lower().replace(" ", "_"),
        "label": data.get("label", data.get("name", "")),
        "color": data.get("color", "#6366f1"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.programme_categories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/programme-categories/{cat_id}")
async def update_programme_category(cat_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    update = {k: v for k, v in data.items() if k in ("name", "label", "color") and v is not None}
    if update.get("name"):
        update["name"] = update["name"].lower().replace(" ", "_")
    await db.programme_categories.update_one({"id": cat_id}, {"$set": update})
    return await db.programme_categories.find_one({"id": cat_id}, {"_id": 0})


@router.delete("/programme-categories/{cat_id}")
async def delete_programme_category(cat_id: str, current_user: dict = Depends(get_current_user)):
    await db.programme_categories.delete_one({"id": cat_id})
    return {"message": "Category deleted"}


# ========== PROGRAMMES ==========

@router.get("/outreach/programs")
async def list_outreach_programs(category: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus: conditions.append(campus)
    if category and category != "all": query["category"] = category
    if status and status != "all": query["status"] = status
    if conditions:
        if query: conditions.append(query)
        final_query = {"$and": conditions}
    else:
        final_query = query
    programs = await db.outreach_programs.find(final_query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return programs


@router.post("/outreach/programs")
async def create_outreach_program(data: ProgrammeCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"op_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "sessions_count": 0, "total_reached": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.outreach_programs.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "outreach_program", doc["id"])

    # Auto-generate calendar events if recurring
    if data.is_recurring and data.recurrence_pattern:
        try:
            await _auto_generate_outreach_events(doc, current_user["id"], months_ahead=3)
        except Exception as e:
            logger.warning(f"Auto-generate events for outreach failed: {e}")

    return doc


@router.get("/outreach/programs/{prog_id}")
async def get_programme(prog_id: str, current_user: dict = Depends(get_current_user)):
    prog = await db.outreach_programs.find_one({"id": prog_id}, {"_id": 0})
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")
    return prog


@router.put("/outreach/programs/{prog_id}")
async def update_outreach_program(prog_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "description", "category", "status", "location", "location_id", "start_date", "target", "is_recurring", "recurrence_pattern", "recurrence_day", "recurrence_time", "recurrence_end_time"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.outreach_programs.update_one({"id": prog_id}, {"$set": update})
    prog = await db.outreach_programs.find_one({"id": prog_id}, {"_id": 0})
    # Sync event changes when outreach name/location/time changes
    event_update = {}
    if "name" in data: event_update["title"] = data["name"]
    if "location" in data: event_update["location"] = data["location"]
    if "location_id" in data: event_update["location_id"] = data["location_id"]
    if "recurrence_time" in data: event_update["time"] = data["recurrence_time"]
    if event_update:
        event_update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.events.update_many({"outreach_program_id": prog_id}, {"$set": event_update})
    # Auto-regenerate events if recurrence changed
    if prog and prog.get("is_recurring") and any(k in data for k in ("recurrence_pattern", "recurrence_day", "recurrence_time", "start_date")):
        try:
            await db.events.delete_many({"outreach_program_id": prog_id, "is_auto_generated": True})
            await _auto_generate_outreach_events(prog, current_user["id"], months_ahead=3)
        except Exception as e:
            logger.warning(f"Auto-regenerate outreach events failed: {e}")
    return prog


@router.delete("/outreach/programs/{prog_id}")
async def delete_outreach_program(prog_id: str, current_user: dict = Depends(get_current_user)):
    # Auto-delete associated events
    await db.events.delete_many({"outreach_program_id": prog_id, "is_auto_generated": True})
    await db.outreach_programs.delete_one({"id": prog_id})
    return {"message": "Deleted"}


@router.post("/outreach/programs/{prog_id}/duplicate")
async def duplicate_programme(prog_id: str, current_user: dict = Depends(get_current_user)):
    prog = await db.outreach_programs.find_one({"id": prog_id}, {"_id": 0})
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")
    new_id = f"op_{str(uuid.uuid4())[:8]}"
    new_prog = {
        **prog, "id": new_id,
        "name": f"{prog['name']} (Copy)",
        "sessions_count": 0, "total_reached": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.outreach_programs.insert_one(new_prog)
    new_prog.pop("_id", None)
    return new_prog


@router.post("/outreach/programs/{prog_id}/generate-events")
async def generate_recurring_events(prog_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Generate recurring events for a programme.
    data: { "months_ahead": 3, "nth_day": 2, "day_of_week": "saturday" }
    nth_day: 1=first, 2=second, 3=third, 4=fourth, -1=last
    day_of_week: monday=0, ..., sunday=6 or name
    """
    prog = await db.outreach_programs.find_one({"id": prog_id}, {"_id": 0})
    if not prog:
        raise HTTPException(status_code=404, detail="Programme not found")

    months_ahead = data.get("months_ahead", 3)
    nth_day = data.get("nth_day", prog.get("recurrence_day", 1))
    day_name = data.get("day_of_week", data.get("recurrence_pattern", "saturday"))
    time_str = data.get("time", prog.get("recurrence_time", "09:00"))
    end_time_str = data.get("end_time", prog.get("recurrence_end_time", "12:00"))

    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    target_weekday = day_map.get(str(day_name).lower(), 5)

    now = datetime.now(timezone.utc)
    events_created = []

    for m_offset in range(months_ahead):
        month = now.month + m_offset
        year = now.year
        while month > 12:
            month -= 12
            year += 1

        cal = calendar.monthcalendar(year, month)
        matching_days = []
        for week in cal:
            if week[target_weekday] != 0:
                matching_days.append(week[target_weekday])

        if not matching_days:
            continue

        if nth_day == -1:
            day = matching_days[-1]
        elif 1 <= nth_day <= len(matching_days):
            day = matching_days[nth_day - 1]
        else:
            continue

        date_str = f"{year}-{month:02d}-{day:02d}"
        event_id = f"evt_{str(uuid.uuid4())[:8]}"
        event = {
            "id": event_id,
            "title": prog.get("name", "Programme Event"),
            "type": "outreach",
            "date": date_str,
            "time": time_str,
            "end_time": end_time_str,
            "location": prog.get("location", ""),
            "location_id": prog.get("location_id"),
            "capacity": prog.get("target", 100),
            "description": prog.get("description", ""),
            "is_public": False,
            "is_free": True,
            "visibility": "internal",
            "is_recurring": True,
            "programme_id": prog_id,
            "registered": 0,
            "status": "upcoming",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.events.insert_one(event)
        event.pop("_id", None)
        events_created.append(event)

    return {"created": len(events_created), "events": events_created}


# ========== HELPER: Auto-generate outreach events ==========

async def _auto_generate_outreach_events(prog: dict, user_id: str, months_ahead: int = 3):
    """Auto-create calendar events for a recurring outreach programme."""
    day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    target_weekday = day_map.get(str(prog.get("recurrence_pattern", "saturday")).lower(), 5)
    nth_day = prog.get("recurrence_day", 1) or 1
    time_str = prog.get("recurrence_time", "09:00")
    end_time_str = prog.get("recurrence_end_time", "12:00")
    now = datetime.now(timezone.utc)
    events_created = []

    for m_offset in range(months_ahead):
        month = now.month + m_offset
        year = now.year
        while month > 12:
            month -= 12
            year += 1
        cal = calendar.monthcalendar(year, month)
        matching_days = [week[target_weekday] for week in cal if week[target_weekday] != 0]
        if not matching_days:
            continue
        if nth_day == -1:
            day = matching_days[-1]
        elif 1 <= nth_day <= len(matching_days):
            day = matching_days[nth_day - 1]
        else:
            continue
        date_str = f"{year}-{month:02d}-{day:02d}"
        # Check if event already exists for this programme on this date
        existing = await db.events.find_one({"programme_id": prog["id"], "date": date_str})
        if existing:
            continue
        event_id = f"evt_{str(uuid.uuid4())[:8]}"
        event = {
            "id": event_id, "title": prog.get("name", "Outreach Event"),
            "type": "outreach", "date": date_str, "time": time_str, "end_time": end_time_str,
            "location": prog.get("location", ""), "location_id": prog.get("location_id"),
            "capacity": prog.get("target", 100), "description": prog.get("description", ""),
            "is_public": False, "is_free": True, "visibility": "internal",
            "is_recurring": True, "programme_id": prog["id"],
            "registered": 0, "status": "upcoming",
            "created_at": datetime.now(timezone.utc).isoformat(), "created_by": user_id,
        }
        await db.events.insert_one(event)
        event.pop("_id", None)
        events_created.append(event)
    return events_created


# ========== SESSIONS ==========

@router.get("/outreach/sessions")
async def list_outreach_sessions(program_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus: conditions.append(campus)
    if program_id: query["program_id"] = program_id
    if conditions:
        if query: conditions.append(query)
        final_query = {"$and": conditions}
    else:
        final_query = query
    sessions = await db.outreach_sessions.find(final_query, {"_id": 0}).sort("date", -1).to_list(500)
    return sessions


@router.post("/outreach/sessions")
async def create_outreach_session(data: SessionCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"os_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.outreach_sessions.insert_one(doc)
    doc.pop("_id", None)
    await db.outreach_programs.update_one(
        {"id": data.program_id},
        {"$inc": {"sessions_count": 1, "total_reached": data.attendees}}
    )

    # Auto-create a calendar event for this session
    prog = await db.outreach_programs.find_one({"id": data.program_id}, {"_id": 0})
    if prog:
        event_id = f"evt_{str(uuid.uuid4())[:8]}"
        event = {
            "id": event_id,
            "title": f"{prog.get('name', 'Outreach')} - Session",
            "type": "outreach",
            "date": data.date,
            "time": data.time or prog.get("recurrence_time", "09:00"),
            "end_time": prog.get("recurrence_end_time", ""),
            "location": data.location or prog.get("location", ""),
            "location_id": prog.get("location_id"),
            "capacity": prog.get("target", 100),
            "description": f"Outreach session: {data.notes or prog.get('description', '')}",
            "is_public": False, "is_free": True, "visibility": "internal",
            "programme_id": data.program_id,
            "session_id": doc["id"],
            "registered": data.attendees,
            "status": "upcoming" if data.date >= datetime.now(timezone.utc).isoformat()[:10] else "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.events.insert_one(event)
        event.pop("_id", None)
        doc["calendar_event_id"] = event_id

    return doc
