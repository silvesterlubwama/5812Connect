"""Departments — a functional cost-centre dimension that lives INSIDE a
campus (and optionally inside a sub-location). Distinct from `locations`
because a department isn't a physical place; it's a grouping used for
budgeting, HR staffing, and cross-charging (Option B in the design chat).

Model:
    id, name, description
    location_id            # required: which campus owns this department
    sublocation_id?        # optional: nested inside a specific sub-location
    color?, budget?        # cosmetic + budget cap
    active                 # soft-disabled without deleting

Scope rules:
    - list is filtered via get_campus_filter (same as expenses/users)
    - create/update/delete is admin+director. system_admin bypasses.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

from deps import (
    db, get_current_user, require_manager, require_admin,
    get_campus_filter, is_system_admin, _audit,
)

router = APIRouter(prefix="/api/departments", tags=["departments"])


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location_id: str
    sublocation_id: Optional[str] = None
    color: Optional[str] = None
    budget: Optional[float] = None
    active: bool = True


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location_id: Optional[str] = None
    sublocation_id: Optional[str] = None
    color: Optional[str] = None
    budget: Optional[float] = None
    active: Optional[bool] = None


@router.get("")
async def list_departments(
    location_id: Optional[str] = None,
    include_inactive: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """List departments visible to the current user (campus-scoped)."""
    scope = await get_campus_filter(current_user)
    q: dict = {**scope}
    if location_id:
        q["location_id"] = location_id
    if not include_inactive:
        q["active"] = {"$ne": False}
    rows = await db.departments.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    return rows


@router.post("")
async def create_department(data: DepartmentCreate, current_user: dict = Depends(require_manager)):
    """Create a department. Managers+ inside the target campus, admins anywhere."""
    # Validate location exists
    loc = await db.locations.find_one({"id": data.location_id}, {"_id": 0, "id": 1, "name": 1})
    if not loc:
        raise HTTPException(status_code=400, detail="location_id does not match a campus")
    # Enforce location membership for non-admins
    if not is_system_admin(current_user):
        user_locs = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            user_locs.add(current_user["location_id"])
        if data.location_id not in user_locs:
            raise HTTPException(status_code=403, detail="You can only create departments in your own campuses")

    dept = {
        "id": f"dept_{uuid.uuid4().hex[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    # Optional: block same-name duplicates within a campus
    dupe = await db.departments.find_one(
        {"location_id": data.location_id, "name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}, "active": {"$ne": False}},
        {"_id": 0, "id": 1},
    )
    if dupe:
        raise HTTPException(status_code=409, detail=f"A department named '{data.name}' already exists in this campus")
    await db.departments.insert_one(dept)
    dept.pop("_id", None)
    await _audit(current_user["id"], "create", "department", dept["id"], data={"name": data.name, "location_id": data.location_id})
    return dept


@router.put("/{dept_id}")
async def update_department(dept_id: str, data: DepartmentUpdate, current_user: dict = Depends(require_manager)):
    existing = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    # Enforce campus membership for non-admins
    if not is_system_admin(current_user):
        user_locs = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            user_locs.add(current_user["location_id"])
        if existing.get("location_id") not in user_locs:
            raise HTTPException(status_code=403, detail="You can only edit departments in your own campuses")

    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.departments.update_one({"id": dept_id}, {"$set": update})
    doc = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    await _audit(current_user["id"], "update", "department", dept_id, data=update)
    return doc


@router.delete("/{dept_id}")
async def delete_department(dept_id: str, hard: bool = False, current_user: dict = Depends(require_admin)):
    """Soft-delete by default (mark inactive). `hard=true` removes the record."""
    existing = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    # Refuse hard delete when anyone is still tagged
    if hard:
        in_use = await db.users.count_documents({"department_ids": dept_id})
        if in_use:
            raise HTTPException(status_code=409, detail=f"Cannot hard-delete: {in_use} user(s) are still tagged")
        await db.departments.delete_one({"id": dept_id})
    else:
        await db.departments.update_one({"id": dept_id}, {"$set": {"active": False, "deactivated_at": datetime.now(timezone.utc).isoformat()}})
    await _audit(current_user["id"], "delete", "department", dept_id, data={"hard": hard})
    return {"ok": True}
