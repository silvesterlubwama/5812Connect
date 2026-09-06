"""Sub-location budget CRUD — admins can set a hard cap that overrides
the auto-rolled-up department sum shown on the Department P&L report.

Sub-locations live in the `sublocations` collection alongside the
existing Finance sub-location editor. This router just exposes the
`budget` field so it can be edited from the UI without touching the
larger financial.py file.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Optional
import uuid

from deps import db, require_manager, get_campus_filter, is_system_admin, _audit

router = APIRouter(prefix="/api/sublocations", tags=["sublocations"])


@router.get("")
async def list_sublocations(location_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    """Lightweight sub-location list — id, name, location_id, budget."""
    scope = await get_campus_filter(current_user)
    q: dict = {**scope}
    if location_id:
        q["location_id"] = location_id
    rows = await db.sublocations.find(q, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "budget": 1}).sort("name", 1).to_list(200)
    return rows


@router.put("/{subloc_id}/budget")
async def set_sublocation_budget(subloc_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Override the auto-rolled-up budget with a hard cap.

    Body: {budget: number | null}. Pass null to clear the override and
    fall back to the department-sum rollup on Department P&L.
    """
    existing = await db.sublocations.find_one({"id": subloc_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Sub-location not found")
    if not is_system_admin(current_user):
        user_locs = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            user_locs.add(current_user["location_id"])
        if existing.get("location_id") not in user_locs:
            raise HTTPException(status_code=403, detail="You can only edit sub-locations in your own campuses")
    budget = data.get("budget")
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if budget is None:
        update["budget"] = None
    else:
        try:
            update["budget"] = float(budget)
        except Exception:
            raise HTTPException(status_code=400, detail="budget must be a number or null")
    await db.sublocations.update_one({"id": subloc_id}, {"$set": update})
    await _audit(current_user["id"], "update", "sublocation-budget", subloc_id, data={"budget": update["budget"]})
    doc = await db.sublocations.find_one({"id": subloc_id}, {"_id": 0})
    return doc
