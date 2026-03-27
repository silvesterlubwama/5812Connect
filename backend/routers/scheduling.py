"""Volunteer scheduling endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from deps import get_current_user, db, get_campus_filter
from typing import Optional
import uuid

router = APIRouter(prefix="/api")


@router.get("/volunteer/shifts")
async def list_shifts(event_id: Optional[str] = None, location_id: Optional[str] = None, date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if event_id:
        query["event_id"] = event_id
    if location_id:
        query["location_id"] = location_id
    if date:
        query["date"] = date
    shifts = await db.volunteer_shifts.find(query, {"_id": 0}).sort("date", 1).to_list(200)
    return shifts


@router.post("/volunteer/shifts")
async def create_shift(data: dict, current_user: dict = Depends(get_current_user)):
    shift_id = f"shift_{str(uuid.uuid4())[:8]}"
    doc = {
        "id": shift_id,
        "title": data.get("title", "Volunteer Shift"),
        "event_id": data.get("event_id"),
        "location_id": data.get("location_id"),
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
