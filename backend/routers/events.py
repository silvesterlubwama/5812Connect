"""Events, Check-ins, Venues, Event Types, Public Events routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_staff, require_manager, require_admin, _audit, logger
from models import EventCreate, EventUpdate, CheckInCreate, VenueCreate, VenueUpdate, PublicBookingCreate, SpaceBookingCreate
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import copy

router = APIRouter(prefix="/api", tags=["events"])


# ========== EVENT TYPES ==========

@router.get("/event-types")
async def list_event_types(current_user: dict = Depends(get_current_user)):
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
async def create_event_type(data: dict, current_user: dict = Depends(require_manager)):
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
async def list_events(search: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None, is_public: Optional[bool] = None, visibility: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
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
    events = await db.events.find(query, {"_id": 0}).sort("date", -1).to_list(200)
    return events


@router.post("/events")
async def create_event(data: EventCreate, current_user: dict = Depends(get_current_user)):
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    event = {
        "id": event_id,
        **data.model_dump(),
        "registered": 0,
        "status": "upcoming",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
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


# ========== CHECK-INS ==========

@router.get("/checkins")
async def list_checkins(event_id: Optional[str] = None, member_id: Optional[str] = None, type: Optional[str] = None, search: Optional[str] = None, location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
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
    checkin = {
        "id": ci_id, **data.model_dump(),
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
        }
        await db.checkins.insert_one(checkin)
        checkin.pop("_id", None)
        checked_in.append(checkin)

    return {"parent": parent, "children": children, "checked_in": checked_in}


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


# ========== KIOSK ==========

@router.post("/kiosk/checkin")
async def kiosk_checkin(data: CheckInCreate):
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, **data.model_dump(),
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
    """Kiosk PIN-based check-in/out (no auth required)"""
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
        last_ci = await db.checkins.find_one(
            {"member_id": member["id"], "check_out_time": None},
            {"_id": 0}, sort=[("check_in_time", -1)]
        )
        if last_ci:
            await db.checkins.update_one({"id": last_ci["id"]}, {"$set": {"check_out_time": datetime.now(timezone.utc).isoformat()}})
            return {"message": "Checked out", "member_name": member.get("name")}
        return {"message": "No active check-in", "member_name": member.get("name")}
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id, "member_id": member["id"], "member_name": member.get("name", ""),
        "type": member.get("role", "member").lower(), "event_id": event_id, "event_name": event_name,
        "method": "pin", "check_in_time": datetime.now(timezone.utc).isoformat(), "source": "kiosk",
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return {"message": "Checked in", "member_name": member.get("name"), "checkin": checkin}


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


# ========== PUBLIC ENDPOINTS ==========

@router.get("/public/events")
async def public_events():
    events = await db.events.find(
        {"is_public": True, "status": "upcoming"},
        {"_id": 0}
    ).sort("date", 1).to_list(50)
    return events


@router.get("/public/venues")
async def public_venues():
    venues = await db.venues.find({"available": True}, {"_id": 0}).to_list(50)
    return venues


@router.post("/public/bookings/event")
async def public_book_event(data: PublicBookingCreate):
    event = await db.events.find_one({"id": data.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("registered", 0) >= event.get("capacity", 0):
        raise HTTPException(status_code=400, detail="Event is fully booked")
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id, **data.model_dump(),
        "event_title": event.get("title", ""),
        "is_free": event.get("is_free", True),
        "price": event.get("price", 0),
        "status": "confirmed" if event.get("is_free", True) else "pending_payment",
        "ticket_ids": [f"TKT-{str(uuid.uuid4())[:4].upper()}" for _ in range(data.num_tickets)],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    await db.events.update_one({"id": data.event_id}, {"$inc": {"registered": data.num_tickets}})
    booking.pop("_id", None)
    return booking


@router.post("/public/bookings/space")
async def public_book_space(data: SpaceBookingCreate):
    venue = await db.venues.find_one({"id": data.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id, **data.model_dump(),
        "type": "space", "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
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
