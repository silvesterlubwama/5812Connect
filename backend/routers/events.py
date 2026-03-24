"""Events, Check-ins, Venues routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger
from models import EventCreate, EventUpdate, CheckInCreate, VenueCreate, VenueUpdate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def list_events(search: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None, is_public: Optional[bool] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    if type and type != "all":
        query["type"] = type
    if status and status != "all":
        query["status"] = status
    if is_public is not None:
        query["is_public"] = is_public
    events = await db.events.find(query, {"_id": 0}).sort("date", -1).to_list(200)
    return events


@router.post("/events")
async def create_event(data: EventCreate, current_user: dict = Depends(get_current_user)):
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    event = {"id": event_id, **data.model_dump(), "registered": 0, "status": "upcoming", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.events.insert_one(event)
    event.pop("_id", None)
    try:
        from routers.notifications import send_bulk_notifications
        recipients = await db.users.find({"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}, "email": {"$exists": True, "$ne": ""}}, {"_id": 0, "email": 1, "name": 1}).to_list(200)
        if recipients:
            await send_bulk_notifications({"recipients": recipients, "type": "event_reminder", "data": {"event_title": event.get("title"), "date": event.get("date"), "time": event.get("time"), "location": event.get("location")}})
    except Exception as e:
        logger.warning(f"Event notify failed: {e}")
    return event


@router.get("/events/{event_id}")
async def get_event(event_id: str, current_user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    attendees = await db.event_registrations.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    event["attendees"] = attendees
    checkins = await db.checkins.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    event["checkins"] = checkins
    return event


@router.put("/events/{event_id}")
async def update_event(event_id: str, data: EventUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.events.update_one({"id": event_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return await db.events.find_one({"id": event_id}, {"_id": 0})


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event deleted"}


# ========== CHECK-INS ==========

@router.get("/checkins")
async def list_checkins(event_id: Optional[str] = None, member_id: Optional[str] = None, type: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if event_id: query["event_id"] = event_id
    if member_id: query["member_id"] = member_id
    if type and type != "all": query["type"] = type
    if search: query["member_name"] = {"$regex": search, "$options": "i"}
    checkins = await db.checkins.find(query, {"_id": 0}).sort("check_in_time", -1).to_list(1000)
    return checkins


@router.post("/checkins")
async def create_checkin(data: CheckInCreate, current_user: dict = Depends(get_current_user)):
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {"id": ci_id, **data.model_dump(), "check_in_time": datetime.now(timezone.utc).isoformat(), "checked_in_by": current_user["id"]}
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return checkin


@router.get("/checkins/stats")
async def get_checkin_stats(current_user: dict = Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    return {
        "total": await db.checkins.count_documents({}),
        "today": await db.checkins.count_documents({"check_in_time": {"$gte": today_start}}),
        "members": await db.checkins.count_documents({"type": "member"}),
        "visitors": await db.checkins.count_documents({"type": "visitor"}),
        "staff": await db.checkins.count_documents({"type": "staff"}),
    }


# ========== VENUES ==========

@router.get("/venues")
async def list_venues(current_user: dict = Depends(get_current_user)):
    return await db.venues.find({}, {"_id": 0}).to_list(100)


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
