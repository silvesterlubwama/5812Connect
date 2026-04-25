"""Members, Families, Children, Guests, Badges, Approvals routes"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from deps import (
    db, get_current_user, _audit, require_staff, require_manager, require_coordinator, require_admin, require_director,
    normalize_gender, resolve_department, logger, is_system_admin, get_campus_filter
)
from models import MemberCreate, MemberUpdate, FamilyCreate, ChildCreate, GuestCreate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["members"])


# ========== MEMBERS CRUD ==========

@router.get("/members")
async def list_members(
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    location_id: Optional[str] = None,
    staff_only: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
) -> dict:
    STAFF_ROLES = {"Executive Director", "Adviser", "Director", "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer", "admin", "system_admin"}
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus:
        conditions.append(campus)
    if staff_only:
        query["role"] = {"$in": list(STAFF_ROLES)}
    if search:
        conditions.append({"$or": [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"national_id": {"$regex": search, "$options": "i"}},
        ]})
    if group and group != "all":
        query["group"] = group
    if status and status != "all":
        query["status"] = status
    if role and role != "all":
        query["role"] = role
    if location_id and location_id != "all":
        query["location_id"] = location_id
    if conditions:
        query["$and"] = conditions
    total = await db.members.count_documents(query)
    members = await db.members.find(query, {"_id": 0}).skip(skip).limit(limit).sort("name", 1).to_list(limit)
    # Enrich with location names
    loc_cache = {}
    for m in members:
        lid = m.get("location_id")
        if lid and lid not in loc_cache:
            loc = await db.locations.find_one({"id": lid}, {"_id": 0, "name": 1})
            loc_cache[lid] = loc.get("name") if loc else ""
        if lid:
            m["location_name"] = loc_cache.get(lid, "")
    return {"members": members, "total": total}


@router.post("/members")
async def create_member(data: MemberCreate, current_user: dict = Depends(get_current_user)) -> dict:
    payload = data.model_dump()
    payload["gender"] = normalize_gender(payload.get("gender"))
    payload["department"] = await resolve_department(payload.get("location_id"), payload.get("department"))
    # Duplicate check by email, phone, or national_id
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone") or "").strip()
    national_id = (payload.get("national_id") or "").strip()
    dedup_or = []
    if email:
        dedup_or.append({"email": {"$regex": f"^{email}$", "$options": "i"}})
    if phone:
        dedup_or.append({"phone": phone})
    if national_id:
        dedup_or.append({"national_id": national_id})
    if dedup_or:
        existing = await db.members.find_one({"$or": dedup_or}, {"_id": 0, "name": 1, "email": 1})
        if existing:
            raise HTTPException(status_code=409, detail=f"Duplicate: a member with this email/phone/ID already exists ({existing.get('name', '')})")
    member_id = f"mem_{str(uuid.uuid4())[:8]}"
    member = {
        "id": member_id,
        **payload,
        "status": "active",
        "join_date": datetime.now(timezone.utc).isoformat().split("T")[0],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.members.insert_one(member)
    member.pop("_id", None)
    return member


@router.get("/members/pending")
async def list_pending_members(current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user), "status": "pending"}
    members = await db.members.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"members": members, "total": len(members)}


@router.get("/members/{member_id}")
async def get_member(member_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    checkins = await db.checkins.find({"member_id": member_id}, {"_id": 0}).sort("check_in_time", -1).limit(20).to_list(20)
    member["checkin_history"] = checkins
    return member


@router.put("/members/{member_id}")
async def update_member(member_id: str, data: MemberUpdate, current_user: dict = Depends(get_current_user)) -> dict:
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    # Coordinators can edit only same-location, non-restricted members
    role_level = {"admin": 10, "system_admin": 10, "Executive Director": 9, "Adviser": 8.5, "Director": 8, "Manager": 7, "Coordinator": 6}.get(current_user.get("role"), 0)
    if role_level < 7 and not is_system_admin(current_user):
        # Coordinator-level check
        if role_level < 6:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        user_locs = current_user.get("location_ids") or [current_user.get("location_id")]
        member_loc = member.get("location_id", "")
        if member_loc and member_loc not in user_locs:
            raise HTTPException(status_code=403, detail="Cannot edit members outside your campus")
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "gender" in update_data:
        update_data["gender"] = normalize_gender(update_data["gender"])
    if "department" in update_data or "location_id" in update_data:
        location_id = update_data.get("location_id", member.get("location_id"))
        department = update_data.get("department", member.get("department"))
        update_data["department"] = await resolve_department(location_id, department)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.members.update_one({"id": member_id}, {"$set": update_data})
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    return member


@router.delete("/members/{member_id}")
async def delete_member(member_id: str, current_user: dict = Depends(require_coordinator)) -> dict:
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    # Soft-delete: move to deleted_items collection
    member["_deleted_from"] = "members"
    member["deleted_at"] = datetime.now(timezone.utc).isoformat()
    member["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(member)
    await db.members.delete_one({"id": member_id})
    await _audit(current_user["id"], "delete", "member", member_id, {"name": member.get("name")})
    return {"message": "Member deleted"}


# ========== FAMILIES ==========

@router.get("/families")
async def list_families(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    if search:
        query["$or"] = [
            {"family_name": {"$regex": search, "$options": "i"}},
            {"primary_contact_name": {"$regex": search, "$options": "i"}},
        ]
    families = await db.families.find(query, {"_id": 0}).sort("family_name", 1).to_list(500)
    return families


@router.post("/families")
async def create_family(data: FamilyCreate, current_user: dict = Depends(get_current_user)):
    # Duplicate check by family_name
    existing = await db.families.find_one({"family_name": {"$regex": f"^{data.family_name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail=f"A family named '{data.family_name}' already exists")
    doc = {
        "id": f"fam_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.families.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/families/bulk-update")
async def bulk_update_families(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk update families. Body: {ids: [], updates: {location_id, primary_contact_name, primary_contact_phone}}"""
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates: return {"updated": 0}
    allowed = {"location_id", "primary_contact_name", "primary_contact_phone", "primary_contact_email", "address"}
    clean = {k: v for k, v in updates.items() if k in allowed and v}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.families.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/families/bulk-delete")
async def bulk_delete_families(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids: return {"deleted": 0}
    result = await db.families.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.put("/guests/bulk-update")
async def bulk_update_guests(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates: return {"updated": 0}
    allowed = {"location_id", "is_parent", "family_id", "status"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.guests.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/guests/bulk-delete")
async def bulk_delete_guests(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids: return {"deleted": 0}
    result = await db.guests.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}



@router.put("/families/{family_id}")
async def update_family(family_id: str, data: FamilyCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.families.update_one({"id": family_id}, {"$set": update})
    return await db.families.find_one({"id": family_id}, {"_id": 0})


@router.delete("/families/{family_id}")
async def delete_family(family_id: str, current_user: dict = Depends(get_current_user)):
    family = await db.families.find_one({"id": family_id}, {"_id": 0})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    family["_deleted_from"] = "families"
    family["deleted_at"] = datetime.now(timezone.utc).isoformat()
    family["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(family)
    await db.families.delete_one({"id": family_id})
    await _audit(current_user["id"], "delete", "family", family_id, {"name": family.get("family_name")})
    return {"message": "Family deleted"}


@router.get("/families/{family_id}")
async def get_family_detail(family_id: str, current_user: dict = Depends(get_current_user)):
    """Get family with all members: parents (guests), children, guardians."""
    family = await db.families.find_one({"id": family_id}, {"_id": 0})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    # Get children for this family
    family_children = await db.children.find({"family_id": family_id}, {"_id": 0}).to_list(50)
    # Get parents (guests with is_parent=True and this family_id)
    parents = await db.guests.find({"family_id": family_id, "is_parent": True}, {"_id": 0}).to_list(20)
    family["children"] = family_children
    family["parents"] = parents
    return family


@router.post("/families/{family_id}/guardians")
async def add_guardian(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a guardian to a family."""
    family = await db.families.find_one({"id": family_id})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    guardian = {
        "id": f"gdn_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "relationship": data.get("relationship", "Guardian"),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.families.update_one({"id": family_id}, {"$push": {"guardians": guardian}})
    return guardian


@router.put("/families/{family_id}/guardians/{guardian_id}")
async def update_guardian(family_id: str, guardian_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a guardian in a family."""
    await db.families.update_one(
        {"id": family_id, "guardians.id": guardian_id},
        {"$set": {
            "guardians.$.name": data.get("name", ""),
            "guardians.$.phone": data.get("phone", ""),
            "guardians.$.email": data.get("email", ""),
            "guardians.$.relationship": data.get("relationship", "Guardian"),
        }}
    )
    return {"message": "Guardian updated"}


@router.delete("/families/{family_id}/guardians/{guardian_id}")
async def remove_guardian(family_id: str, guardian_id: str, current_user: dict = Depends(get_current_user)):
    """Remove a guardian from a family."""
    await db.families.update_one({"id": family_id}, {"$pull": {"guardians": {"id": guardian_id}}})
    return {"message": "Guardian removed"}


# ========== PORTAL: PARENT FAMILY MANAGEMENT ==========

@router.get("/portal/family")
async def get_my_family(current_user: dict = Depends(get_current_user)):
    """Get the logged-in parent's family. Searches by user email in guests/parents."""
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    # Find parent guest record linked to a family
    parent_guest = await db.guests.find_one(
        {"$or": [{"email": email}, {"name": {"$regex": f"^{name}$", "$options": "i"}}], "is_parent": True},
        {"_id": 0}
    )
    family = None
    if parent_guest and parent_guest.get("family_id"):
        family = await db.families.find_one({"id": parent_guest["family_id"]}, {"_id": 0})
    if not family:
        # Also check if user has a family directly
        family = await db.families.find_one(
            {"$or": [
                {"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}},
                {"parent_ids": current_user["id"]},
            ]},
            {"_id": 0}
        )
    if not family:
        return {"family": None, "children": [], "parents": [], "message": "No family found. Contact admin to link your account."}
    children = await db.children.find({"family_id": family["id"]}, {"_id": 0}).to_list(50)
    parents = await db.guests.find({"family_id": family["id"], "is_parent": True}, {"_id": 0}).to_list(20)
    # Also include staff users marked as parents linked to this family
    staff_parents = await db.users.find(
        {"is_parent": True, "$or": [
            {"family_id": family["id"]},
            {"email": {"$in": [p.get("email") for p in parents if p.get("email")]}},
        ]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "role": 1, "location_id": 1}
    ).to_list(20)
    for sp in staff_parents:
        if not any(p.get("email") == sp.get("email") for p in parents):
            parents.append({**sp, "is_parent": True, "is_staff": True})
    return {"family": family, "children": children, "parents": parents}


@router.put("/portal/family")
async def update_my_family(data: dict, current_user: dict = Depends(get_current_user)):
    """Parent updates their own family details."""
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    parent_guest = await db.guests.find_one(
        {"$or": [{"email": email}, {"name": {"$regex": f"^{name}$", "$options": "i"}}], "is_parent": True},
        {"_id": 0}
    )
    family_id = None
    if parent_guest and parent_guest.get("family_id"):
        family_id = parent_guest["family_id"]
    if not family_id:
        family = await db.families.find_one(
            {"$or": [{"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}}, {"parent_ids": current_user["id"]}]},
            {"_id": 0}
        )
        if family:
            family_id = family["id"]
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found")
    allowed_fields = {"family_name", "address", "notes", "primary_contact_phone"}
    update = {k: v for k, v in data.items() if k in allowed_fields}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.families.update_one({"id": family_id}, {"$set": update})
    return await db.families.find_one({"id": family_id}, {"_id": 0})


@router.post("/portal/family/children")
async def parent_add_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
    """Parent adds a child to their own family."""
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    parent_guest = await db.guests.find_one(
        {"$or": [{"email": email}, {"name": {"$regex": f"^{name}$", "$options": "i"}}], "is_parent": True},
        {"_id": 0}
    )
    family_id = None
    if parent_guest and parent_guest.get("family_id"):
        family_id = parent_guest["family_id"]
    if not family_id:
        family = await db.families.find_one(
            {"$or": [{"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}}, {"parent_ids": current_user["id"]}]},
            {"_id": 0}
        )
        if family:
            family_id = family["id"]
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found. Contact admin.")
    child_data = data.model_dump()
    child_data["family_id"] = family_id
    doc = {
        "id": f"chd_{str(uuid.uuid4())[:8]}",
        **child_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.children.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/portal/family/guardians")
async def parent_add_guardian(data: dict, current_user: dict = Depends(get_current_user)):
    """Parent adds a guardian to their family."""
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    parent_guest = await db.guests.find_one(
        {"$or": [{"email": email}, {"name": {"$regex": f"^{name}$", "$options": "i"}}], "is_parent": True},
        {"_id": 0}
    )
    family_id = None
    if parent_guest and parent_guest.get("family_id"):
        family_id = parent_guest["family_id"]
    if not family_id:
        family = await db.families.find_one(
            {"$or": [{"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}}, {"parent_ids": current_user["id"]}]},
            {"_id": 0}
        )
        if family:
            family_id = family["id"]
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found. Contact admin.")
    guardian = {
        "id": f"gdn_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "relationship": data.get("relationship", "Guardian"),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.families.update_one({"id": family_id}, {"$push": {"guardians": guardian}})
    return guardian


# ========== CHILDREN ==========

@router.get("/children")
async def list_children(family_id: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    if family_id:
        query["family_id"] = family_id
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    # Children in restricted sub-locations: only visible to staff assigned to that exact location
    if not is_system_admin(current_user):
        user_loc = current_user.get("location_id")
        # Get restricted sub-location IDs
        restricted_locs = await db.locations.find(
            {"type": "sub-location", "is_restricted": True},
            {"_id": 0, "id": 1}
        ).to_list(100)
        restricted_ids = [r["id"] for r in restricted_locs]
        if restricted_ids:
            # Exclude children in restricted locations that aren't the user's location
            other_restricted = [rid for rid in restricted_ids if rid != user_loc]
            if other_restricted:
                query["location_id"] = {"$nin": other_restricted}
    children = await db.children.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return children


@router.post("/children")
async def create_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
    # Duplicate check by name + family_id
    name = data.name.strip()
    dedup_q = {"name": {"$regex": f"^{name}$", "$options": "i"}}
    if data.family_id:
        dedup_q["family_id"] = data.family_id
    existing = await db.children.find_one(dedup_q)
    if existing:
        raise HTTPException(status_code=409, detail=f"A child named '{name}' already exists in this family")
    doc = {
        "id": f"chd_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.children.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ========== BULK OPERATIONS FOR CHILDREN, FAMILIES, GUESTS ==========

@router.put("/children/bulk-update")
async def bulk_update_children(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk update children. Body: {ids: [], updates: {family_id, location_id, class_group, gender}}"""
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates: return {"updated": 0}
    allowed = {"family_id", "location_id", "class_group", "gender", "grade", "medical_info", "allergies"}
    clean = {k: v for k, v in updates.items() if k in allowed and v}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.children.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/children/bulk-delete")
async def bulk_delete_children(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids: return {"deleted": 0}
    result = await db.children.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}



@router.put("/children/{child_id}")
async def update_child(child_id: str, data: ChildCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    # Get old child to check residency changes
    old_child = await db.children.find_one({"id": child_id}, {"_id": 0})
    await db.children.update_one({"id": child_id}, {"$set": update})
    # Sync residency if changed
    new_resident = update.get("is_resident", False)
    new_loc = update.get("resident_location_id", "")
    old_loc = old_child.get("resident_location_id", "") if old_child else ""
    if new_resident and new_loc:
        await db.locations.update_one({"id": new_loc}, {"$addToSet": {"resident_ids": child_id}})
        if old_loc and old_loc != new_loc:
            await db.locations.update_one({"id": old_loc}, {"$pull": {"resident_ids": child_id}})
    elif not new_resident and old_loc:
        await db.locations.update_one({"id": old_loc}, {"$pull": {"resident_ids": child_id}})
    return await db.children.find_one({"id": child_id}, {"_id": 0})


@router.delete("/children/{child_id}")
async def delete_child(child_id: str, current_user: dict = Depends(get_current_user)):
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    child["_deleted_from"] = "children"
    child["deleted_at"] = datetime.now(timezone.utc).isoformat()
    child["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(child)
    await db.children.delete_one({"id": child_id})
    await _audit(current_user["id"], "delete", "child", child_id, {"name": child.get("name")})
    return {"message": "Child deleted"}



# ========== CHILD EDUCATION & PROFILE INFO ==========

@router.put("/children/{child_id}/education")
async def update_child_education(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update child's school, grade, report cards — staff or parent can update"""
    allowed = {"school", "grade", "class_group", "report_cards", "achievements", "special_needs", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.children.update_one({"id": child_id}, {"$set": update})
    return await db.children.find_one({"id": child_id}, {"_id": 0})


@router.post("/children/{child_id}/report-card")
async def add_report_card(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a report card entry to a child's profile"""
    entry = {
        "id": f"rc_{str(uuid.uuid4())[:8]}",
        "term": data.get("term", ""),
        "year": data.get("year", ""),
        "school": data.get("school", ""),
        "grade": data.get("grade", ""),
        "gpa": data.get("gpa", ""),
        "notes": data.get("notes", ""),
        "document_id": data.get("document_id"),
        "added_by": current_user["id"],
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.children.update_one({"id": child_id}, {"$push": {"report_cards": entry}})
    return entry


@router.put("/children/{child_id}/residency")
async def set_child_residency(child_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Set a child as a resident of a restricted location"""
    resident_loc = data.get("resident_location_id", "")
    is_resident = data.get("is_resident", True)
    update = {"is_resident": is_resident, "resident_location_id": resident_loc if is_resident else None, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.children.update_one({"id": child_id}, {"$set": update})
    # Also add to location's resident_ids
    if is_resident and resident_loc:
        await db.locations.update_one({"id": resident_loc}, {"$addToSet": {"resident_ids": child_id}})
    elif not is_resident and resident_loc:
        await db.locations.update_one({"id": resident_loc}, {"$pull": {"resident_ids": child_id}})
    return {"message": "Residency updated"}


@router.get("/children/{child_id}/full-profile")
async def get_child_full_profile(child_id: str, current_user: dict = Depends(get_current_user)):
    """Get full child profile — restricted info hidden based on access level"""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    user_role = (current_user.get("role") or "").lower()
    is_authorized = user_role in {"admin", "system_admin", "executive director"}

    # Check if user is director/manager/staff of child's location
    if not is_authorized:
        user_locs = current_user.get("location_ids") or []
        user_loc = current_user.get("location_id", "")
        if user_loc and user_loc not in user_locs: user_locs.append(user_loc)
        child_loc = child.get("location_id") or child.get("resident_location_id") or ""
        if child_loc:
            # Check if child's location is user's location or sub-location
            loc = await db.locations.find_one({"id": child_loc}, {"_id": 0, "parent_id": 1})
            if child_loc in user_locs or (loc and loc.get("parent_id") in user_locs):
                if user_role in {"director", "manager", "coordinator", "staff"}:
                    is_authorized = True
        # Check if user is a parent of this child
        if current_user["id"] in (child.get("parent_ids") or []):
            is_authorized = True

    # Get documents
    docs = await db.member_documents.find({"member_id": child_id}, {"_id": 0}).to_list(50)

    result = {**child, "documents": docs}

    # Hide restricted info if not authorized
    if not is_authorized and child.get("is_resident"):
        result.pop("resident_location_id", None)
        result.pop("sponsor_first_name", None)
        result.pop("sponsor_id", None)

    return result



# ========== GUESTS ==========

@router.get("/guests")
async def list_guests(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus: conditions.append(campus)
    if search:
        conditions.append({"$or": [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]})
    if conditions: query["$and"] = conditions
    guests = await db.guests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    # Also include staff/users tagged as parents or guests
    staff_query = {"$or": [{"is_parent": True}, {"is_guest": True}]}
    if campus:
        staff_conditions = [campus, staff_query]
        if search: staff_conditions.append({"$or": [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]})
        staff_parents = await db.users.find({"$and": staff_conditions}, {"_id": 0, "password_hash": 0, "totp_secret": 0}).to_list(200)
    else:
        sq = {**staff_query}
        if search: sq["$and"] = [{"$or": [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]}]
        staff_parents = await db.users.find(sq, {"_id": 0, "password_hash": 0, "totp_secret": 0}).to_list(200)
    
    # Merge without duplicates (by email)
    guest_emails = {g.get("email", "").lower() for g in guests if g.get("email")}
    for sp in staff_parents:
        sp_email = (sp.get("email") or "").lower()
        if sp_email and sp_email in guest_emails: continue
        guests.append({**sp, "is_staff": True, "source": "staff"})
    
    return guests


@router.post("/guests")
async def create_guest(data: GuestCreate, current_user: dict = Depends(get_current_user)):
    # Duplicate check by name + email or phone
    name = data.name.strip()
    dedup_or = [{"name": {"$regex": f"^{name}$", "$options": "i"}, "email": (data.email or "").strip().lower()}]
    if data.phone:
        dedup_or.append({"name": {"$regex": f"^{name}$", "$options": "i"}, "phone": data.phone.strip()})
    existing = await db.guests.find_one({"$or": dedup_or})
    if existing:
        raise HTTPException(status_code=409, detail=f"Guest '{name}' already recorded")
    doc = {
        "id": f"gst_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "visit_date": data.visit_date or datetime.now(timezone.utc).isoformat()[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/guests/{guest_id}")
async def update_guest(guest_id: str, data: GuestCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.guests.update_one({"id": guest_id}, {"$set": update})
    return await db.guests.find_one({"id": guest_id}, {"_id": 0})



@router.delete("/guests/{guest_id}")
async def delete_guest(guest_id: str, current_user: dict = Depends(get_current_user)):
    guest = await db.guests.find_one({"id": guest_id}, {"_id": 0})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    guest["_deleted_from"] = "guests"
    guest["deleted_at"] = datetime.now(timezone.utc).isoformat()
    guest["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(guest)
    await db.guests.delete_one({"id": guest_id})
    await _audit(current_user["id"], "delete", "guest", guest_id, {"name": guest.get("name")})
    return {"message": "Guest deleted"}


# ========== BADGES ==========

@router.get("/badges")
async def list_badges(current_user: dict = Depends(get_current_user)):
    badges = await db.badges.find({}, {"_id": 0}).to_list(100)
    return badges


@router.post("/badges")
async def create_badge(data: dict, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"badge_{str(uuid.uuid4())[:8]}", "name": data.get("name", ""), "color": data.get("color", "#6366f1"), "description": data.get("description", ""), "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.badges.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/badges/{badge_id}")
async def delete_badge(badge_id: str, current_user: dict = Depends(get_current_user)):
    await db.badges.delete_one({"id": badge_id})
    return {"message": "Deleted"}


@router.post("/members/{member_id}/issue-badge")
async def issue_badge_to_member(member_id: str, badge_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    badge = await db.badges.find_one({"id": badge_id}, {"_id": 0})
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    issued = {"badge_id": badge_id, "badge_name": badge["name"], "badge_color": badge.get("color", "#6366f1"), "issued_at": datetime.now(timezone.utc).isoformat(), "issued_by": current_user["id"]}
    await db.members.update_one({"id": member_id}, {"$push": {"badges": issued}})
    await db.badges.update_one({"id": badge_id}, {"$inc": {"issued_count": 1}})
    await _audit(current_user["id"], "create", "badge_issue", f"{member_id}:{badge_id}")
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    return member


@router.get("/members/{member_id}/badges")
async def get_member_badges(member_id: str, current_user: dict = Depends(get_current_user)):
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member.get("badges", [])


# ========== MEMBER APPROVALS ==========

@router.put("/members/{member_id}/approve")
async def approve_member(member_id: str, current_user: dict = Depends(get_current_user)):
    await db.members.update_one({"id": member_id}, {"$set": {"status": "active", "approved_at": datetime.now(timezone.utc).isoformat(), "approved_by": current_user["id"]}})
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    await _audit(current_user["id"], "update", "member_approval", member_id)
    try:
        from routers.notifications import send_notification, NotifyRequest
        if member and member.get("email"):
            await send_notification(NotifyRequest(
                type="approval_status",
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                data={"member_name": member.get("name", ""), "status": "approved"},
            ))
    except Exception as e:
        logger.warning(f"Member approval notify failed: {e}")
    return member


@router.put("/members/{member_id}/reject")
async def reject_member(member_id: str, current_user: dict = Depends(get_current_user)):
    await db.members.update_one({"id": member_id}, {"$set": {"status": "rejected", "rejected_at": datetime.now(timezone.utc).isoformat(), "rejected_by": current_user["id"]}})
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    await _audit(current_user["id"], "update", "member_rejection", member_id)
    try:
        from routers.notifications import send_notification, NotifyRequest
        if member and member.get("email"):
            await send_notification(NotifyRequest(
                type="approval_status",
                recipient_email=member["email"],
                recipient_name=member.get("name", ""),
                data={"member_name": member.get("name", ""), "status": "rejected"},
            ))
    except Exception as e:
        logger.warning(f"Member rejection notify failed: {e}")
    return member


# ========== BULK IMPORT (JSON) ==========

@router.post("/members/bulk-import")
async def bulk_import_members(file: str = None, members_data: list = None, current_user: dict = Depends(get_current_user)):
    if not members_data:
        return {"imported": 0, "errors": []}
    imported = 0
    errors = []
    for i, row in enumerate(members_data):
        try:
            if not row.get("name"):
                errors.append(f"Row {i+1}: Name is required")
                continue
            existing = await db.members.find_one({"email": row.get("email", "")})
            if existing and row.get("email"):
                errors.append(f"Row {i+1}: Email {row['email']} already exists")
                continue
            doc = {"id": f"m_{str(uuid.uuid4())[:8]}", "name": row.get("name", ""), "email": row.get("email", ""), "phone": row.get("phone", ""), "national_id": row.get("national_id", ""), "role": row.get("role", "Member"), "group": row.get("group", "General"), "gender": row.get("gender", ""), "status": "active", "join_date": datetime.now(timezone.utc).date().isoformat(), "location_id": row.get("location_id"), "created_at": datetime.now(timezone.utc).isoformat()}
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "bulk_import", f"{imported}_members")
    return {"imported": imported, "errors": errors, "total": len(members_data)}


# ========== CHILDREN IMPORT (with auto-parent/family creation) ==========

@router.post("/children/bulk-import")
async def bulk_import_children(request_data: dict, current_user: dict = Depends(get_current_user)):
    """Import children with auto-creation of parents and families. 
    Prevents duplicates; updates existing records with new info.
    Parents are created even without email addresses.
    Campus/location_id is auto-resolved from campus name if provided.
    Body: {"children": [{name, age, gender, family_name, parent_name, parent_phone, parent_email, campus, location_id}]}"""
    data = request_data.get("children", request_data.get("data", []))
    if not data:
        return {"imported": 0, "updated": 0, "parents_created": 0, "errors": ["No children data provided"], "total": 0}
    imported = 0
    updated = 0
    parents_created = 0
    errors = []
    family_cache = {}
    campus_cache = {}
    parent_cache = {}  # Track created parents by name+phone to skip repeated info

    for i, row in enumerate(data):
        try:
            child_name = (row.get("name") or "").strip()
            if not child_name:
                errors.append(f"Row {i+1}: Name required"); continue
            
            family_name = (row.get("family_name") or "").strip()
            parent_name = (row.get("parent_name") or row.get("father_name") or row.get("mother_name") or "").strip()
            parent_phone = (row.get("parent_phone") or row.get("father_phone") or row.get("mother_phone") or "").strip()
            parent_email = (row.get("parent_email") or row.get("father_email") or row.get("mother_email") or "").strip().lower()
            campus_name = (row.get("campus") or "").strip()
            location_id = row.get("location_id", "")

            # Auto-resolve campus name to location_id; fall back to admin's active campus
            if campus_name and not location_id:
                if campus_name in campus_cache:
                    location_id = campus_cache[campus_name]
                else:
                    loc = await db.locations.find_one({"name": {"$regex": f"^{campus_name}$", "$options": "i"}}, {"_id": 0, "id": 1})
                    location_id = loc["id"] if loc else ""
                    campus_cache[campus_name] = location_id
            if not location_id:
                location_id = current_user.get("active_campus_id") or current_user.get("location_id") or ""

            # 1. Find or create family
            family_id = None
            if family_name:
                if family_name in family_cache:
                    family_id = family_cache[family_name]
                else:
                    existing_fam = await db.families.find_one({"family_name": {"$regex": f"^{family_name}$", "$options": "i"}})
                    if existing_fam:
                        family_id = existing_fam["id"]
                        merge_fields = {}
                        if location_id and not existing_fam.get("location_id"):
                            merge_fields["location_id"] = location_id
                        if parent_phone and not existing_fam.get("primary_contact_phone"):
                            merge_fields["primary_contact_phone"] = parent_phone
                        if parent_name and not existing_fam.get("primary_contact_name"):
                            merge_fields["primary_contact_name"] = parent_name
                        if merge_fields:
                            await db.families.update_one({"id": family_id}, {"$set": merge_fields})
                    else:
                        family_id = f"fam_{str(uuid.uuid4())[:8]}"
                        await db.families.insert_one({
                            "id": family_id, "family_name": family_name,
                            "primary_contact_name": parent_name, "primary_contact_phone": parent_phone,
                            "primary_contact_email": parent_email, "location_id": location_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                    family_cache[family_name] = family_id

            # 2. Find or create parent (even without email) — skip if already handled in this batch
            if parent_name:
                parent_key = f"{parent_name.lower()}|{parent_phone}"
                if parent_key not in parent_cache:
                    parent_q_conditions = [{"name": {"$regex": f"^{parent_name}$", "$options": "i"}, "is_parent": True}]
                    if parent_phone:
                        parent_q_conditions.append({"phone": parent_phone, "is_parent": True})
                    existing_parent = await db.guests.find_one({"$or": parent_q_conditions})
                    if not existing_parent:
                        staff_parent = await db.users.find_one({"name": {"$regex": f"^{parent_name}$", "$options": "i"}, "is_parent": True})
                        if not staff_parent:
                            await db.guests.insert_one({
                                "id": f"gst_{str(uuid.uuid4())[:8]}", "name": parent_name,
                                "email": parent_email, "phone": parent_phone,
                                "is_parent": True, "family_id": family_id, "location_id": location_id,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            })
                            parents_created += 1
                    else:
                        merge = {}
                        if family_id and not existing_parent.get("family_id"):
                            merge["family_id"] = family_id
                        if parent_phone and not existing_parent.get("phone"):
                            merge["phone"] = parent_phone
                        if location_id and not existing_parent.get("location_id"):
                            merge["location_id"] = location_id
                        if merge:
                            await db.guests.update_one({"id": existing_parent["id"]}, {"$set": merge})
                    parent_cache[parent_key] = True

            # Also handle second parent (father/mother) if both provided — skip if already in cache
            father_name = (row.get("father_name") or "").strip()
            mother_name = (row.get("mother_name") or "").strip()
            for pname, pphone, pemail in [
                (father_name, (row.get("father_phone") or "").strip(), (row.get("father_email") or "").strip().lower()),
                (mother_name, (row.get("mother_phone") or "").strip(), (row.get("mother_email") or "").strip().lower()),
            ]:
                if pname and pname != parent_name:
                    p_key = f"{pname.lower()}|{pphone}"
                    if p_key in parent_cache:
                        continue
                    p_conditions = [{"name": {"$regex": f"^{pname}$", "$options": "i"}, "is_parent": True}]
                    if pphone:
                        p_conditions.append({"phone": pphone, "is_parent": True})
                    existing_p = await db.guests.find_one({"$or": p_conditions})
                    if not existing_p:
                        await db.guests.insert_one({
                            "id": f"gst_{str(uuid.uuid4())[:8]}", "name": pname,
                            "email": pemail, "phone": pphone,
                            "is_parent": True, "family_id": family_id, "location_id": location_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        parents_created += 1
                    parent_cache[p_key] = True

            # 3. Find or create/update child
            child_q = {"name": {"$regex": f"^{child_name}$", "$options": "i"}}
            if family_id: child_q["family_id"] = family_id
            existing_child = await db.children.find_one(child_q)
            if existing_child:
                update_fields = {}
                for k in ("age", "gender", "date_of_birth", "medical_info", "allergies", "grade", "class_group"):
                    if row.get(k) and row[k] != existing_child.get(k):
                        update_fields[k] = row[k]
                if location_id and location_id != existing_child.get("location_id"):
                    update_fields["location_id"] = location_id
                if family_id and not existing_child.get("family_id"):
                    update_fields["family_id"] = family_id
                if update_fields:
                    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await db.children.update_one({"id": existing_child["id"]}, {"$set": update_fields})
                    updated += 1
            else:
                await db.children.insert_one({
                    "id": f"chd_{str(uuid.uuid4())[:8]}", "name": child_name,
                    "age": row.get("age"), "gender": row.get("gender", ""),
                    "date_of_birth": row.get("date_of_birth", ""),
                    "family_id": family_id, "location_id": location_id,
                    "medical_info": row.get("medical_info", ""), "allergies": row.get("allergies", ""),
                    "grade": row.get("grade", ""), "class_group": row.get("class_group", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    return {"imported": imported, "updated": updated, "parents_created": parents_created, "errors": errors, "total": len(data)}


# ========== FAMILY EDITING (children + parents) ==========

@router.put("/families/{family_id}/members")
async def update_family_members(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update which children and parents/guardians belong to a family"""
    child_ids = data.get("child_ids", [])
    parent_ids = data.get("parent_ids", [])
    guardian_ids = data.get("guardian_ids", [])

    # Unlink old children from this family
    await db.children.update_many({"family_id": family_id}, {"$unset": {"family_id": ""}})
    # Link specified children
    if child_ids:
        await db.children.update_many({"id": {"$in": child_ids}}, {"$set": {"family_id": family_id}})

    # Unlink old parents
    await db.guests.update_many({"family_id": family_id, "is_parent": True}, {"$unset": {"family_id": ""}})
    # Link specified parents
    if parent_ids:
        await db.guests.update_many({"id": {"$in": parent_ids}}, {"$set": {"family_id": family_id, "is_parent": True}})

    # Store guardian links
    await db.families.update_one({"id": family_id}, {"$set": {
        "guardian_ids": guardian_ids,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})

    return {"message": "Family members updated", "children": len(child_ids), "parents": len(parent_ids), "guardians": len(guardian_ids)}


# ========== NFC TAG MANAGEMENT ==========

@router.get("/members/{member_id}/nfc-tags")
async def get_member_nfc_tags(member_id: str, current_user: dict = Depends(get_current_user)) -> list:
    """Get NFC tags associated with a member."""
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "nfc_tags": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member.get("nfc_tags", [])


@router.post("/members/{member_id}/nfc-tags")
async def add_nfc_tag(member_id: str, data: dict, current_user: dict = Depends(require_staff)) -> dict:
    """Add an NFC tag to a member profile. Body: { serial_number, label? }"""
    serial = (data.get("serial_number") or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="NFC serial_number is required")
    # Check if tag is already assigned to another member
    existing = await db.members.find_one(
        {"nfc_tags.serial_number": serial, "id": {"$ne": member_id}},
        {"_id": 0, "id": 1, "name": 1}
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"This NFC tag is already assigned to {existing.get('name', 'another member')}")
    tag = {
        "id": f"nfc_{uuid.uuid4().hex[:8]}",
        "serial_number": serial,
        "label": data.get("label", ""),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": current_user["id"],
    }
    await db.members.update_one({"id": member_id}, {"$push": {"nfc_tags": tag}})
    # Also store on user record if linked
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$push": {"nfc_tags": tag}})
    await _audit(current_user["id"], "create", "nfc_tag", member_id, {"serial": serial})
    return tag


@router.delete("/members/{member_id}/nfc-tags/{tag_id}")
async def remove_nfc_tag(member_id: str, tag_id: str, current_user: dict = Depends(require_staff)) -> dict:
    """Remove an NFC tag from a member profile."""
    result = await db.members.update_one(
        {"id": member_id},
        {"$pull": {"nfc_tags": {"id": tag_id}}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="NFC tag not found")
    # Also remove from user record
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$pull": {"nfc_tags": {"id": tag_id}}})
    await _audit(current_user["id"], "delete", "nfc_tag", member_id, {"tag_id": tag_id})
    return {"message": "NFC tag removed"}


@router.post("/members/{member_id}/nfc-write")
async def write_nfc_tag(member_id: str, data: dict, current_user: dict = Depends(require_director)) -> dict:
    """Record that an NFC tag was written with this member's data. Director+ only.
    Body: { serial_number, written_data?, label? }
    This also adds the tag to the member's profile if not already present."""
    serial = (data.get("serial_number") or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="NFC serial_number is required")
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "id": 1, "name": 1, "user_id": 1, "nfc_tags": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    # Check duplicate on other members
    existing = await db.members.find_one(
        {"nfc_tags.serial_number": serial, "id": {"$ne": member_id}},
        {"_id": 0, "id": 1, "name": 1}
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"NFC tag already assigned to {existing.get('name', 'another member')}")
    # Add tag if not already present on this member
    current_tags = member.get("nfc_tags") or []
    already_has = any(t.get("serial_number") == serial for t in current_tags)
    tag = None
    if not already_has:
        tag = {
            "id": f"nfc_{uuid.uuid4().hex[:8]}",
            "serial_number": serial,
            "label": data.get("label", ""),
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_by": current_user["id"],
            "written": True,
        }
        await db.members.update_one({"id": member_id}, {"$push": {"nfc_tags": tag}})
        if member.get("user_id"):
            await db.users.update_one({"id": member["user_id"]}, {"$push": {"nfc_tags": tag}})
    else:
        # Mark existing tag as written
        await db.members.update_one(
            {"id": member_id, "nfc_tags.serial_number": serial},
            {"$set": {"nfc_tags.$.written": True, "nfc_tags.$.written_at": datetime.now(timezone.utc).isoformat(), "nfc_tags.$.written_by": current_user["id"]}}
        )
        tag = next((t for t in current_tags if t.get("serial_number") == serial), None)
    # Log the write event
    await db.nfc_write_log.insert_one({
        "id": str(uuid.uuid4()),
        "member_id": member_id,
        "member_name": member.get("name", ""),
        "serial_number": serial,
        "written_data": data.get("written_data", member_id),
        "written_by": current_user["id"],
        "written_at": datetime.now(timezone.utc).isoformat(),
    })
    await _audit(current_user["id"], "create", "nfc_write", member_id, {"serial": serial})
    return {"message": "NFC tag written and linked", "tag": tag, "member_id": member_id, "member_name": member.get("name", "")}


# ========== PROFILE PHOTOS ==========

@router.post("/members/{member_id}/photo")
async def upload_member_photo(member_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_staff)) -> dict:
    """Upload a profile photo for a member. Stores in object storage."""
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    ext = file.filename.rsplit('.', 1)[-1] if '.' in (file.filename or '') else 'jpg'
    path = f"profile-photos/{member_id}.{ext}"
    try:
        from storage import put_object
        result = put_object(path, data, file.content_type)
        photo_url = result.get("url", f"/api/storage/{path}")
    except Exception as e:
        logger.warning(f"Storage upload failed, saving locally: {e}")
        import os
        os.makedirs("/app/backend/uploads/photos", exist_ok=True)
        local_path = f"/app/backend/uploads/photos/{member_id}.{ext}"
        with open(local_path, "wb") as f:
            f.write(data)
        photo_url = f"/api/uploads/photos/{member_id}.{ext}"
    await db.members.update_one({"id": member_id}, {"$set": {"photo_url": photo_url}})
    # Also update user record if linked
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$set": {"photo_url": photo_url}})
    return {"photo_url": photo_url}


@router.post("/children/{child_id}/photo")
async def upload_child_photo(child_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_staff)) -> dict:
    """Upload a profile photo for a child."""
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    ext = file.filename.rsplit('.', 1)[-1] if '.' in (file.filename or '') else 'jpg'
    path = f"profile-photos/child-{child_id}.{ext}"
    try:
        from storage import put_object
        result = put_object(path, data, file.content_type)
        photo_url = result.get("url", f"/api/storage/{path}")
    except Exception as e:
        logger.warning(f"Storage upload failed, saving locally: {e}")
        import os
        os.makedirs("/app/backend/uploads/photos", exist_ok=True)
        local_path = f"/app/backend/uploads/photos/child-{child_id}.{ext}"
        with open(local_path, "wb") as f:
            f.write(data)
        photo_url = f"/api/uploads/photos/child-{child_id}.{ext}"
    await db.children.update_one({"id": child_id}, {"$set": {"photo_url": photo_url}})
    return {"photo_url": photo_url}


