"""Members, Families, Children, Guests, Badges, Approvals routes"""
from fastapi import APIRouter, Depends, HTTPException, Query
from deps import (
    db, get_current_user, _audit, require_coordinator, require_manager,
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
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    query = {**get_campus_filter(current_user)}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"national_id": {"$regex": search, "$options": "i"}},
        ]
    if group and group != "all":
        query["group"] = group
    if status and status != "all":
        query["status"] = status
    if role and role != "all":
        query["role"] = role
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
async def create_member(data: MemberCreate, current_user: dict = Depends(get_current_user)):
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
    query = {**get_campus_filter(current_user), "status": "pending"}
    members = await db.members.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"members": members, "total": len(members)}


@router.get("/members/{member_id}")
async def get_member(member_id: str, current_user: dict = Depends(get_current_user)):
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    checkins = await db.checkins.find({"member_id": member_id}, {"_id": 0}).sort("check_in_time", -1).limit(20).to_list(20)
    member["checkin_history"] = checkins
    return member


@router.put("/members/{member_id}")
async def update_member(member_id: str, data: MemberUpdate, current_user: dict = Depends(get_current_user)):
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
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
async def delete_member(member_id: str, current_user: dict = Depends(require_coordinator)):
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
    query = {**get_campus_filter(current_user)}
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
    query = {**get_campus_filter(current_user)}
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


@router.put("/children/{child_id}")
async def update_child(child_id: str, data: ChildCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.children.update_one({"id": child_id}, {"$set": update})
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


# ========== GUESTS ==========

@router.get("/guests")
async def list_guests(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**get_campus_filter(current_user)}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    guests = await db.guests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
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
