"""Locations, exchange-rate, and location-related endpoints — extracted from server.py"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, _audit, is_system_admin
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["locations"])


class LocationCreate(BaseModel):
    name: str
    code: Optional[str] = None
    type: str = "campus"
    parent_id: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    currency: str = "USD"
    timezone: Optional[str] = "Africa/Kampala"
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    director_id: Optional[str] = None
    is_venue: bool = False
    is_bookable: bool = False
    is_restricted: bool = False
    allows_residents: bool = True
    departments: Optional[List[str]] = []
    payment_apis: Optional[List[dict]] = []


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    director_id: Optional[str] = None
    is_venue: Optional[bool] = None
    is_bookable: Optional[bool] = None
    is_restricted: Optional[bool] = None
    allows_residents: Optional[bool] = None
    departments: Optional[List[str]] = None
    payment_apis: Optional[List[dict]] = None
    active: Optional[bool] = None
    financial_enabled: Optional[bool] = None
    marketplace_enabled: Optional[bool] = None
    financial_apis_enabled: Optional[bool] = None


@router.get("/locations")
async def list_locations(current_user: dict = Depends(get_current_user)) -> list:
    """List locations. Non-admins see only their campuses + non-restricted sub-locations + restricted ones they're explicitly assigned to."""
    all_locs = await db.locations.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    if is_system_admin(current_user):
        return all_locs
    user_loc_ids = set(current_user.get("location_ids") or [])
    if current_user.get("location_id"):
        user_loc_ids.add(current_user["location_id"])
    # Include parent campuses of any assigned sub-location
    for loc in all_locs:
        if loc.get("id") in user_loc_ids and loc.get("parent_id"):
            user_loc_ids.add(loc["parent_id"])
    visible = []
    for loc in all_locs:
        loc_id = loc.get("id")
        # User's own assigned locations (including sub-locations) are always visible
        if loc_id in user_loc_ids:
            visible.append(loc)
            continue
        # Top-level campus that user belongs to — visible
        if loc.get("type") in ("main", "campus") and loc_id in user_loc_ids:
            visible.append(loc)
            continue
        # Sub-locations of user's campuses — visible only if NOT restricted
        if loc.get("parent_id") in user_loc_ids:
            if not loc.get("is_restricted"):
                visible.append(loc)
            # Restricted sub-locations are hidden unless explicitly assigned (already handled above)
    return visible


@router.post("/locations")
async def create_location(data: LocationCreate, current_user: dict = Depends(require_admin)) -> dict:
    doc = {"id": f"loc_{str(uuid.uuid4())[:8]}", **data.model_dump(), "active": True, "member_count": 0, "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.locations.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "location", doc["id"])
    return doc


@router.put("/locations/{loc_id}")
async def update_location(loc_id: str, data: LocationUpdate, current_user: dict = Depends(require_admin)):
    # Use exclude_unset=True so we keep fields the caller explicitly set to null
    # (e.g. promoting a sub-location to a main campus by clearing parent_id).
    update_data = data.model_dump(exclude_unset=True)
    if "parent_id" in update_data and not update_data["parent_id"]:
        # Treat empty string / null both as "no parent" — promote to main campus
        update_data["parent_id"] = None
        # Also flip the type from sub-location to campus if currently nested
        existing = await db.locations.find_one({"id": loc_id}, {"_id": 0, "type": 1})
        if existing and existing.get("type") == "sub-location" and "type" not in update_data:
            update_data["type"] = "campus"
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.locations.update_one({"id": loc_id}, {"$set": update_data})
    return await db.locations.find_one({"id": loc_id}, {"_id": 0})


@router.get("/locations/{loc_id}/staff")
async def get_location_staff(loc_id: str, current_user: dict = Depends(get_current_user)):
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    staff_ids = loc.get("staff_ids", [])
    if not staff_ids:
        return []
    return await db.members.find({"id": {"$in": staff_ids}}, {"_id": 0}).to_list(100)


@router.put("/locations/{loc_id}/assign-staff")
async def assign_staff_to_location(loc_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    await db.locations.update_one({"id": loc_id}, {"$set": {"staff_ids": data.get("staff_ids", [])}})
    return {"message": "Staff assigned"}


@router.put("/locations/{loc_id}/director")
async def set_location_director(loc_id: str, data: dict, current_user: dict = Depends(require_admin)):
    await db.locations.update_one({"id": loc_id}, {"$set": {"director_id": data.get("director_id")}})
    return await db.locations.find_one({"id": loc_id}, {"_id": 0})


@router.get("/exchange-rate")
async def get_exchange_rate(from_currency: str = "UGX", to_currency: str = "USD"):
    rates_to_usd = {"USD": 1.0, "UGX": 0.00027, "KES": 0.0077, "TZS": 0.00039, "RWF": 0.00074, "GBP": 1.27, "EUR": 1.09, "ZAR": 0.055, "NGN": 0.00065, "GHS": 0.063, "ETB": 0.008}
    from_rate = rates_to_usd.get(from_currency.upper(), 1.0)
    to_rate = rates_to_usd.get(to_currency.upper(), 1.0)
    return {"from": from_currency, "to": to_currency, "rate": round(from_rate / to_rate if to_rate else 1.0, 6)}


@router.delete("/locations/{loc_id}")
async def delete_location(loc_id: str, current_user: dict = Depends(require_admin)):
    await db.locations.delete_one({"id": loc_id})
    return {"message": "Location deleted"}


@router.get("/locations/{loc_id}/venues")
async def get_location_venues(loc_id: str, current_user: dict = Depends(get_current_user)):
    """Get venues/sublocations within a location + external venues for event location picker"""
    venues = await db.venues.find({"location_id": loc_id}, {"_id": 0}).to_list(100)
    sublocations = await db.locations.find({"parent_id": loc_id, "is_venue": True}, {"_id": 0}).to_list(100)
    # Also include external venues (not tied to any specific location)
    external = await db.venues.find({"$or": [{"is_external": True}, {"location_id": {"$in": [None, ""]}}]}, {"_id": 0}).to_list(100)
    # Deduplicate
    venue_ids = {v["id"] for v in venues}
    for ev in external:
        if ev["id"] not in venue_ids:
            venues.append(ev)
    return {"venues": venues, "sublocations": sublocations}
