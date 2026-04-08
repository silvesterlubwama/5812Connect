"""Events, Check-ins, Venues, Event Types, Public Events routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_staff, require_manager, require_admin, _audit, logger, is_system_admin, get_campus_filter
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
    campus = await get_campus_filter(current_user)
    query = {}
    if campus:
        # Non-admin: see campus events + public events
        query["$or"] = [{**campus}, {"is_public": True}]
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
    return filtered


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
async def public_events(country: Optional[str] = None):
    query = {"is_public": True, "status": "upcoming"}
    if country:
        query["$or"] = [{"country": country}, {"country": {"$exists": False}}, {"country": ""}]
    # Only show events up to 1 year ahead
    from datetime import timedelta
    max_date = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
    query["date"] = {"$lte": max_date}
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(100)
    return events


@router.get("/public/venues")
async def public_venues():
    venues = await db.venues.find({"available": True, "is_bookable": {"$ne": False}}, {"_id": 0}).to_list(50)
    return venues


@router.post("/public/bookings/event")
async def public_book_event(data: PublicBookingCreate):
    event = await db.events.find_one({"id": data.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("registered", 0) >= event.get("capacity", 0):
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
            except: pass
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
    """Return unified organizational policies."""
    return {
        "privacy_policy": {
            "title": "Privacy Policy",
            "content": "58:12 Global (\"we\", \"us\") is committed to protecting your personal data. We collect and process personal information in accordance with the EU General Data Protection Regulation (GDPR), the US Privacy Act, Uganda's Data Protection and Privacy Act 2019, Kenya's Data Protection Act 2019, Thailand's Personal Data Protection Act (PDPA), Haiti's applicable privacy provisions, and Mexico's Federal Law on Protection of Personal Data (LFPDPPP). We collect only data necessary for event registration, volunteer management, and ministry operations. You have the right to access, correct, delete, and port your data. Contact privacy@5812global.org for requests.",
        },
        "terms_of_service": {
            "title": "Terms of Service",
            "content": "By using 58:12 Connect services, you agree to these terms. 58:12 Global is a Christ-centered nonprofit organization bringing hope and healing to the most vulnerable. Our services include event management, volunteer coordination, and community programs across the USA, Uganda, Kenya, Thailand, Haiti, and Mexico. Users must be at least 13 years old. Parents/guardians must consent for minors. We reserve the right to modify services and these terms with notice.",
        },
        "refund_policy": {
            "title": "Refund & Cancellation Policy",
            "content": "Free events: No payment required, cancellations accepted anytime. Paid events: Full refund if cancelled 7+ days before event. 50% refund if cancelled 3-7 days before. No refund within 3 days of event. Cash payments must be received within the agreed deadline or booking is automatically cancelled. Mobile money and card payments are processed immediately.",
        },
        "employee_onboarding": {
            "title": "Employee & Volunteer Onboarding Policy",
            "content": "All new staff and volunteers undergo a background check process compliant with US, EU, and local laws. New accounts start as Members and require admin approval before system access is granted. Volunteers must complete orientation training. Staff must sign confidentiality agreements, undergo safeguarding training, and comply with our Code of Conduct. All personnel working with children must pass enhanced background checks per local jurisdiction requirements.",
        },
        "data_retention": {
            "title": "Data Retention Policy",
            "content": "Personal data is retained for the duration of your relationship with 58:12 Global plus 3 years for legal compliance. Financial records are retained for 7 years per US IRS requirements. Check-in data is retained for 2 years. You may request data deletion at any time, subject to legal retention requirements. Anonymization is available as an alternative to deletion.",
        },
        "cookie_policy": {
            "title": "Cookie & Tracking Policy",
            "content": "We use essential cookies for authentication and session management. We use location data only with your consent to show relevant local events. You may disable cookies in your browser settings. We do not sell personal data to third parties.",
        },
    }


# ========== CALENDAR IMPORT/EXPORT ==========

@router.get("/events/export/ical")
async def export_calendar_ical(current_user: dict = Depends(get_current_user)):
    """Export user's events as iCal (.ics) format for calendar apps."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    events = await db.events.find(query, {"_id": 0}).to_list(500)

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//58:12 Global Connect//CRM//EN"]
    for ev in events:
        uid = ev.get("id") or ""
        dtstart = (ev.get("date") or "").replace("-", "")
        time_str = (ev.get("time") or "0900").replace(":", "")
        summary = ev.get("title") or ""
        desc = (ev.get("description") or "").replace("\n", "\\n")
        location = ev.get("location") or ""
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}@5812global",
            f"DTSTART:{dtstart}T{time_str}00",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{location}",
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
                try: event_date = datetime.fromisoformat(custom_dates[i])
                except: continue
            else: break

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
