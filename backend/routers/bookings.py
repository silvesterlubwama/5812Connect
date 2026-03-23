"""Booking system with 1-hour buffer enforcement"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
from deps import db, get_current_user, _audit

router = APIRouter(prefix="/api", tags=["bookings"])

BUFFER_HOURS = 1

class BookingCreate(BaseModel):
    resource_id: Optional[str] = None
    location_id: Optional[str] = None
    title: str
    date: str
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    booked_by_name: Optional[str] = None
    notes: Optional[str] = None

class BookingUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


def time_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def minutes_to_time(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


async def check_booking_conflict(resource_id: str, location_id: str, date: str, start_time: str, end_time: str, exclude_id: str = None):
    """Check for conflicts with 1-hour buffer"""
    start_mins = time_to_minutes(start_time)
    end_mins = time_to_minutes(end_time)
    # Add 1-hour buffer on each side
    buffered_start = start_mins - (BUFFER_HOURS * 60)
    buffered_end = end_mins + (BUFFER_HOURS * 60)

    query = {"date": date, "status": {"$ne": "cancelled"}}
    if resource_id:
        query["resource_id"] = resource_id
    elif location_id:
        query["location_id"] = location_id
    else:
        return None  # No conflict check needed

    if exclude_id:
        query["id"] = {"$ne": exclude_id}

    existing = await db.bookings.find(query, {"_id": 0}).to_list(100)
    for b in existing:
        b_start = time_to_minutes(b["start_time"])
        b_end = time_to_minutes(b["end_time"])
        # Check overlap with buffer
        if buffered_start < b_end and buffered_end > b_start:
            return b
    return None


@router.get("/bookings")
async def list_bookings(
    resource_id: Optional[str] = None,
    location_id: Optional[str] = None,
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {}
    if resource_id:
        query["resource_id"] = resource_id
    if location_id:
        query["location_id"] = location_id
    if date:
        query["date"] = date
    elif date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    if status:
        query["status"] = status
    bookings = await db.bookings.find(query, {"_id": 0}).sort("date", 1).to_list(200)
    return bookings


@router.post("/bookings")
async def create_booking(data: BookingCreate, current_user: dict = Depends(get_current_user)):
    # Validate times
    start_mins = time_to_minutes(data.start_time)
    end_mins = time_to_minutes(data.end_time)
    if end_mins <= start_mins:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    # Check staff-only resources
    if data.resource_id:
        resource = await db.resources.find_one({"id": data.resource_id}, {"_id": 0})
        if resource:
            if not resource.get("is_bookable", True):
                raise HTTPException(status_code=400, detail="This resource is not bookable")
            if resource.get("staff_only") and current_user.get("role") in ["Parent", "Customer"]:
                raise HTTPException(status_code=403, detail="This resource is staff-only")

    # Check sub-location bookability
    if data.location_id:
        loc = await db.locations.find_one({"id": data.location_id}, {"_id": 0})
        if loc and not loc.get("is_bookable", False):
            raise HTTPException(status_code=400, detail="This location is not bookable")

    # Check for conflicts (with 1-hour buffer)
    conflict = await check_booking_conflict(
        data.resource_id, data.location_id, data.date, data.start_time, data.end_time
    )
    if conflict:
        buffer_msg = f"There's a booking from {conflict['start_time']} to {conflict['end_time']}. A 1-hour buffer is required between bookings."
        raise HTTPException(status_code=409, detail=buffer_msg)

    # If booking a sub-location, mark its venues as unavailable for that period
    if data.location_id:
        loc = await db.locations.find_one({"id": data.location_id}, {"_id": 0})
        if loc and loc.get("is_bookable"):
            child_venues = await db.locations.find(
                {"parent_id": data.location_id, "is_venue": True}, {"_id": 0, "id": 1}
            ).to_list(50)
            for venue in child_venues:
                venue_conflict = await check_booking_conflict(
                    None, venue["id"], data.date, data.start_time, data.end_time
                )
                if venue_conflict:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Venue within this location already has a booking ({venue_conflict['start_time']}-{venue_conflict['end_time']}). Cancel that first."
                    )

    booking = {
        "id": f"bk_{str(uuid.uuid4())[:8]}",
        "resource_id": data.resource_id,
        "location_id": data.location_id,
        "title": data.title,
        "date": data.date,
        "start_time": data.start_time,
        "end_time": data.end_time,
        "booked_by": current_user["id"],
        "booked_by_name": data.booked_by_name or current_user.get("name"),
        "notes": data.notes,
        "status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bookings.insert_one(booking)
    booking.pop("_id", None)
    await _audit(current_user["id"], "create", "booking", booking["id"])
    return booking


@router.put("/bookings/{booking_id}")
async def update_booking(booking_id: str, data: BookingUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Booking not found")

    update = {k: v for k, v in data.model_dump().items() if v is not None}

    # If time changed, check conflicts again
    new_date = update.get("date", existing["date"])
    new_start = update.get("start_time", existing["start_time"])
    new_end = update.get("end_time", existing["end_time"])
    if "date" in update or "start_time" in update or "end_time" in update:
        conflict = await check_booking_conflict(
            existing.get("resource_id"), existing.get("location_id"),
            new_date, new_start, new_end, exclude_id=booking_id
        )
        if conflict:
            raise HTTPException(status_code=409, detail=f"Conflict with booking {conflict['start_time']}-{conflict['end_time']}. 1-hour buffer required.")

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.bookings.update_one({"id": booking_id}, {"$set": update})
    return await db.bookings.find_one({"id": booking_id}, {"_id": 0})


@router.delete("/bookings/{booking_id}")
async def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.bookings.update_one(
        {"id": booking_id}, {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    await _audit(current_user["id"], "delete", "booking", booking_id)
    return {"message": "Booking cancelled"}
