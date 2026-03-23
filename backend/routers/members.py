"""Members, Families, Children, Guests, Badges, Approvals routes"""
from fastapi import APIRouter, Depends, HTTPException, Query
from deps import (
    db, get_current_user, _audit, require_coordinator, require_manager,
    normalize_gender, resolve_department, logger
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
    query = {}
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
    return {"members": members, "total": total}


@router.post("/members")
async def create_member(data: MemberCreate, current_user: dict = Depends(get_current_user)):
    payload = data.model_dump()
    payload["gender"] = normalize_gender(payload.get("gender"))
    payload["department"] = await resolve_department(payload.get("location_id"), payload.get("department"))
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
    members = await db.members.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
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
    result = await db.members.delete_one({"id": member_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"message": "Member deleted"}


# ========== FAMILIES ==========

@router.get("/families")
async def list_families(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["$or"] = [
            {"family_name": {"$regex": search, "$options": "i"}},
            {"primary_contact_name": {"$regex": search, "$options": "i"}},
        ]
    families = await db.families.find(query, {"_id": 0}).sort("family_name", 1).to_list(500)
    return families


@router.post("/families")
async def create_family(data: FamilyCreate, current_user: dict = Depends(get_current_user)):
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
    await db.families.delete_one({"id": family_id})
    return {"message": "Family deleted"}


# ========== CHILDREN ==========

@router.get("/children")
async def list_children(family_id: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if family_id:
        query["family_id"] = family_id
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    children = await db.children.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return children


@router.post("/children")
async def create_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
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
    await db.children.delete_one({"id": child_id})
    return {"message": "Child deleted"}


# ========== GUESTS ==========

@router.get("/guests")
async def list_guests(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    guests = await db.guests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return guests


@router.post("/guests")
async def create_guest(data: GuestCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"gst_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "visit_date": data.visit_date or datetime.now(timezone.utc).isoformat()[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/guests/{guest_id}")
async def delete_guest(guest_id: str, current_user: dict = Depends(get_current_user)):
    await db.guests.delete_one({"id": guest_id})
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
