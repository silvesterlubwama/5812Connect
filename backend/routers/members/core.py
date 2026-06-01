"""Members core CRUD + approve/reject + listing helpers."""
from fastapi import APIRouter, Depends, HTTPException
from deps import (
    db, get_current_user, _audit, require_coordinator,
    normalize_gender, resolve_department, logger, is_system_admin, get_campus_filter,
)
from models import MemberCreate, MemberUpdate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/members")
async def list_members(
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    location_id: Optional[str] = None,
    staff_only: Optional[bool] = None,
    welfare_category: Optional[str] = None,  # sponsored|restricted_location|welfare_support|multiple|any
    kind: Optional[str] = None,  # member|guest|parent|any — empty = legacy "member-or-unspecified"
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
    if kind and kind != "any":
        # Match the explicit kind. For "member" also match historical rows that
        # have no kind at all (they were members before the unification).
        if kind == "member":
            conditions.append({"$or": [{"kind": "member"}, {"kind": {"$exists": False}}]})
        else:
            conditions.append({"kind": kind})
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
    # Welfare-category filter: restrict to members who have an active social_work case
    if welfare_category and welfare_category != "all":
        case_query = {"subject_kind": "member", "status": "active"}
        if welfare_category != "any":
            case_query["category"] = welfare_category
        active_subjects = await db.social_cases.find(
            case_query, {"_id": 0, "subject_id": 1}
        ).to_list(5000)
        ids = list({c["subject_id"] for c in active_subjects if c.get("subject_id")})
        if not ids:
            return {"members": [], "total": 0, "welfare_filtered": True}
        conditions.append({"id": {"$in": ids}})
    if conditions:
        query["$and"] = conditions
    total = await db.members.count_documents(query)
    members = await db.members.find(query, {"_id": 0}).skip(skip).limit(limit).sort("name", 1).to_list(limit)
    # Enrich with location names AND welfare category if any active case exists
    loc_cache = {}
    member_ids = [m["id"] for m in members if m.get("id")]
    welfare_map = {}
    if member_ids:
        async for c in db.social_cases.find(
            {"subject_kind": "member", "subject_id": {"$in": member_ids}, "status": "active"},
            {"_id": 0, "subject_id": 1, "category": 1, "risk_level": 1},
        ):
            welfare_map[c["subject_id"]] = {"category": c.get("category"), "risk_level": c.get("risk_level")}
    for m in members:
        lid = m.get("location_id")
        if lid and lid not in loc_cache:
            loc = await db.locations.find_one({"id": lid}, {"_id": 0, "name": 1})
            loc_cache[lid] = loc.get("name") if loc else ""
        if lid:
            m["location_name"] = loc_cache.get(lid, "")
        if m["id"] in welfare_map:
            m["welfare_case"] = welfare_map[m["id"]]
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
    member["_deleted_from"] = "members"
    member["deleted_at"] = datetime.now(timezone.utc).isoformat()
    member["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(member)
    await db.members.delete_one({"id": member_id})
    # Cascade: remove from task assignees, board tagged_members
    await db.tasks.update_many({"assignees": member_id}, {"$pull": {"assignees": member_id}})
    await db.boards.update_many({"tagged_members": member_id}, {"$pull": {"tagged_members": member_id}})
    # Cascade: unlink from linked user
    if member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$unset": {"member_id": ""}})
    await _audit(current_user["id"], "delete", "member", member_id, {"name": member.get("name")})
    return {"message": "Member deleted"}


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
