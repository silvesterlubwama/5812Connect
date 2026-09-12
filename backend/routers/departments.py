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
    # iter-dept-guard: bypass the "has live references" 409. Only pass true
    # after the admin has explicitly confirmed via the warning dialog.
    force: Optional[bool] = None


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
    await _audit(current_user["id"], "create", "department", dept["id"], details={"name": data.name, "location_id": data.location_id})
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
    # iter-dept-guard: refuse a silent deactivation when live references
    # exist; caller must call /reassign first or force=true via a separate
    # explicit param. Keeps admins from stranding salaries + expenses.
    if update.get("active") is False and existing.get("active") is not False:
        users_tagged = await db.users.count_documents({"department_ids": dept_id})
        active_salaries = await db.hr_salaries.count_documents({"department_ids": dept_id, "status": "active"})
        unpaid_expenses = await db.expenses.count_documents({"department_id": dept_id, "status": {"$ne": "paid"}})
        blocking = users_tagged + active_salaries + unpaid_expenses
        if blocking and (data.model_dump().get("force") is not True):
            raise HTTPException(status_code=409, detail={
                "message": "Department has live references",
                "users_tagged": users_tagged,
                "active_salaries": active_salaries,
                "unpaid_expenses": unpaid_expenses,
            })
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.departments.update_one({"id": dept_id}, {"$set": update})
    doc = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    await _audit(current_user["id"], "update", "department", dept_id, details=update)
    return doc


@router.get("/{dept_id}/usage")
async def department_usage(dept_id: str, current_user: dict = Depends(require_manager)):
    """Return counts of live references to a department. Used by the frontend
    Deactivate/Delete flow to warn admins before pulling the rug."""
    dept = await db.departments.find_one({"id": dept_id}, {"_id": 0, "id": 1, "name": 1})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    users_tagged = await db.users.count_documents({"department_ids": dept_id})
    active_salaries = await db.hr_salaries.count_documents({"department_ids": dept_id, "status": "active"})
    unpaid_expenses = await db.expenses.count_documents({"department_id": dept_id, "status": {"$ne": "paid"}})
    return {
        "department": dept,
        "users_tagged": users_tagged,
        "active_salaries": active_salaries,
        "unpaid_expenses": unpaid_expenses,
        "safe_to_deactivate": (users_tagged + active_salaries + unpaid_expenses) == 0,
    }


@router.post("/{dept_id}/reassign")
async def reassign_department(dept_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Move all live references from `dept_id` to `target_id`. Runs before a
    deactivation when the admin picks a replacement in the warning dialog."""
    target = (data or {}).get("target_id")
    if not target:
        raise HTTPException(status_code=400, detail="target_id required")
    if target == dept_id:
        raise HTTPException(status_code=400, detail="target must differ")
    src = await db.departments.find_one({"id": dept_id}, {"_id": 0, "id": 1})
    tgt = await db.departments.find_one({"id": target, "active": {"$ne": False}}, {"_id": 0, "id": 1})
    if not src or not tgt:
        raise HTTPException(status_code=404, detail="Source or target department not found / inactive")
    # Users: swap the id inside the array without duplicating
    async for u in db.users.find({"department_ids": dept_id}, {"_id": 0, "id": 1, "department_ids": 1}):
        new_ids = [target if x == dept_id else x for x in (u.get("department_ids") or [])]
        new_ids = list(dict.fromkeys(new_ids))
        await db.users.update_one({"id": u["id"]}, {"$set": {"department_ids": new_ids}})
    # Salaries: swap in department_ids + department_splits
    async for s in db.hr_salaries.find({"department_ids": dept_id}, {"_id": 0, "id": 1, "department_ids": 1, "department_splits": 1}):
        new_ids = list(dict.fromkeys([target if x == dept_id else x for x in (s.get("department_ids") or [])]))
        new_splits = [{**sp, "department_id": target if sp.get("department_id") == dept_id else sp.get("department_id")} for sp in (s.get("department_splits") or [])]
        await db.hr_salaries.update_one({"id": s["id"]}, {"$set": {"department_ids": new_ids, "department_splits": new_splits}})
    # Expenses: swap direct department_id
    await db.expenses.update_many({"department_id": dept_id}, {"$set": {"department_id": target}})
    await db.expense_allocations.update_many({"department_id": dept_id}, {"$set": {"department_id": target}})
    await _audit(current_user["id"], "reassign", "department", dept_id, details={"to": target})
    return {"ok": True}


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
    await _audit(current_user["id"], "delete", "department", dept_id, details={"hard": hard})
    return {"ok": True}


# ── legacy migration ─────────────────────────────────────────────
# Before departments became real records, staff/members/expenses carried a
# free-text `department` string typed by hand ("Food ", "food", "Kitchen").
# Those rows are invisible to department P&L and staffing reports. This pair
# of endpoints surfaces them and folds them into proper department records.

_LEGACY_SOURCES = [
    # collection, legacy text field, target field, is_array
    ("users", "department", "department_ids", True),
    ("members", "department", "department_id", False),
    ("expenses", "department", "department_id", False),
    ("assets", "department", "department_id", False),
    ("purchase_orders", "department", "department_id", False),
]


async def _legacy_rows(coll: str, text_field: str, target_field: str):
    q = {
        text_field: {"$nin": [None, ""]},
        "$or": [{target_field: {"$in": [None, "", []]}}, {target_field: {"$exists": False}}],
    }
    return await db[coll].find(
        q, {"_id": 0, "id": 1, text_field: 1, "location_id": 1, "location_ids": 1, "name": 1}
    ).to_list(2000)


@router.get("/legacy-scan")
async def scan_legacy_departments(current_user: dict = Depends(require_admin)):
    """Group hand-typed department names that aren't linked to a real record."""
    existing = await db.departments.find({}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "active": 1}).to_list(500)
    by_key = {(d["location_id"], (d.get("name") or "").strip().lower()): d for d in existing}
    groups: dict = {}
    for coll, text_field, target_field, _arr in _LEGACY_SOURCES:
        for row in await _legacy_rows(coll, text_field, target_field):
            raw = str(row.get(text_field) or "").strip()
            if not raw:
                continue
            key = raw.lower()
            g = groups.setdefault(key, {
                "legacy_name": raw, "clean_name": raw, "count": 0,
                "collections": {}, "location_ids": [], "samples": [],
                "matches_existing": None,
            })
            g["count"] += 1
            g["collections"][coll] = g["collections"].get(coll, 0) + 1
            loc = row.get("location_id") or (row.get("location_ids") or [None])[0]
            if loc and loc not in g["location_ids"]:
                g["location_ids"].append(loc)
            if row.get("name") and len(g["samples"]) < 3:
                g["samples"].append(row["name"])
            if g["matches_existing"] is None and loc:
                hit = by_key.get((loc, key))
                if hit:
                    g["matches_existing"] = {"id": hit["id"], "name": hit["name"]}
    return {
        "groups": sorted(groups.values(), key=lambda x: -x["count"]),
        "total_records": sum(g["count"] for g in groups.values()),
        "existing_departments": len(existing),
    }


@router.post("/migrate-legacy")
async def migrate_legacy_departments(data: dict = None, current_user: dict = Depends(require_admin)):
    """Fold hand-typed department names into real department records.

    Body: {"dry_run": bool, "default_location_id": str?}
    Matching is case/whitespace-insensitive within the record's own campus;
    anything unmatched gets a new department created in that campus.
    """
    data = data or {}
    dry_run = bool(data.get("dry_run"))
    default_loc = data.get("default_location_id") or ""
    if not default_loc:
        main = await db.locations.find_one({"type": "main"}, {"_id": 0, "id": 1}) \
            or await db.locations.find_one({}, {"_id": 0, "id": 1})
        default_loc = (main or {}).get("id", "")

    existing = await db.departments.find({}, {"_id": 0, "id": 1, "name": 1, "location_id": 1}).to_list(500)
    index = {(d["location_id"], (d.get("name") or "").strip().lower()): d["id"] for d in existing}
    created: list = []
    updated: dict = {}
    skipped = 0

    for coll, text_field, target_field, is_array in _LEGACY_SOURCES:
        for row in await _legacy_rows(coll, text_field, target_field):
            raw = str(row.get(text_field) or "").strip()
            if not raw:
                continue
            loc = row.get("location_id") or (row.get("location_ids") or [None])[0] or default_loc
            if not loc:
                skipped += 1
                continue
            key = (loc, raw.lower())
            dept_id = index.get(key)
            if not dept_id:
                dept_id = f"dept_{uuid.uuid4().hex[:8]}"
                new_dept = {
                    "id": dept_id, "name": raw, "description": "Migrated from legacy free-text department",
                    "location_id": loc, "sublocation_id": None, "color": None, "budget": None,
                    "active": True, "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"], "migrated_from_legacy": True,
                }
                if not dry_run:
                    await db.departments.insert_one(new_dept)
                index[key] = dept_id
                created.append({"id": dept_id, "name": raw, "location_id": loc})
            if not dry_run:
                value = [dept_id] if is_array else dept_id
                await db[coll].update_one(
                    {"id": row["id"]},
                    {"$set": {target_field: value, "department": raw, "department_migrated_at": datetime.now(timezone.utc).isoformat()}},
                )
            updated[coll] = updated.get(coll, 0) + 1

    if not dry_run:
        await _audit(current_user["id"], "migrate", "departments", "legacy",
                     details={"created": len(created), "updated": updated})
    return {
        "dry_run": dry_run, "departments_created": created,
        "records_updated": updated,
        "records_total": sum(updated.values()), "skipped_no_campus": skipped,
    }
