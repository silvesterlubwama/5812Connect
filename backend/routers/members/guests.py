"""Guests CRUD + members-mirror helper + move-to-staff."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, require_director, logger, get_campus_filter, hash_password
from models import GuestCreate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["members"])


async def _mirror_guest_to_members(guest_doc: dict) -> None:
    """Create or update a guest's mirror row in `db.members` with kind='guest' or 'parent'.
    Same id is used in both collections so existing FKs (children.parent_ids etc.) keep working.
    Best-effort — never raises."""
    try:
        if not guest_doc or not guest_doc.get("id"):
            return
        mirror_kind = "parent" if guest_doc.get("is_parent") else "guest"
        # Build a safe payload — strip _id / system flags
        payload = {k: v for k, v in guest_doc.items() if k not in ("_id",)}
        payload["kind"] = mirror_kind
        payload["mirrored_from_guests"] = True
        payload.setdefault("status", "active")
        await db.members.update_one(
            {"id": guest_doc["id"]},
            {"$set": payload},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"mirror_guest_to_members failed for {guest_doc.get('id')}: {e}")


@router.get("/guests")
async def list_guests(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus:
        conditions.append(campus)
    if search:
        conditions.append({"$or": [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]})
    if conditions:
        query["$and"] = conditions
    guests = await db.guests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)

    # Also include staff/users tagged as parents or guests
    staff_query = {"$or": [{"is_parent": True}, {"is_guest": True}]}
    if campus:
        staff_conditions = [campus, staff_query]
        if search:
            staff_conditions.append({"$or": [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]})
        staff_parents = await db.users.find({"$and": staff_conditions}, {"_id": 0, "password_hash": 0, "totp_secret": 0}).to_list(200)
    else:
        sq = {**staff_query}
        if search:
            sq["$and"] = [{"$or": [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]}]
        staff_parents = await db.users.find(sq, {"_id": 0, "password_hash": 0, "totp_secret": 0}).to_list(200)

    # Merge without duplicates (by email)
    guest_emails = {g.get("email", "").lower() for g in guests if g.get("email")}
    for sp in staff_parents:
        sp_email = (sp.get("email") or "").lower()
        if sp_email and sp_email in guest_emails:
            continue
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
    await _mirror_guest_to_members(doc)
    return doc


@router.put("/guests/{guest_id}")
async def update_guest(guest_id: str, data: GuestCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.guests.update_one({"id": guest_id}, {"$set": update})
    # Auto-add to restricted residents if is_resident + resident_location_id set
    if update.get("is_resident") and update.get("resident_location_id"):
        existing_res = await db.residents.find_one({"member_id": guest_id, "location_id": update["resident_location_id"], "status": "active"})
        if not existing_res:
            guest = await db.guests.find_one({"id": guest_id}, {"_id": 0, "name": 1})
            await db.residents.insert_one({
                "id": f"res_{uuid.uuid4().hex[:8]}", "member_id": guest_id,
                "member_name": guest.get("name", "") if guest else "", "source": "guest_flag",
                "location_id": update["resident_location_id"], "tags": [], "status": "active",
                "assigned_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
            })
    fresh = await db.guests.find_one({"id": guest_id}, {"_id": 0})
    if fresh:
        await _mirror_guest_to_members(fresh)
    return fresh


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
    # Also remove the mirror row in members if it was added by the unification
    try:
        await db.members.delete_one({"id": guest_id, "mirrored_from_guests": True})
    except Exception as e:
        logger.warning(f"delete guest members-mirror failed: {e}")
    # Cascade: remove from children's parent_ids
    await db.children.update_many({"parent_ids": guest_id}, {"$pull": {"parent_ids": guest_id}})
    await _audit(current_user["id"], "delete", "guest", guest_id, {"name": guest.get("name")})
    return {"message": "Guest deleted"}


@router.post("/guests/{guest_id}/move-to-staff")
async def move_guest_to_staff(guest_id: str, data: dict = None, current_user: dict = Depends(require_director)) -> dict:
    """Move a guest to a staff user account. Body: {role?, department?, password?}"""
    if data is None:
        data = {}
    guest = await db.guests.find_one({"id": guest_id}, {"_id": 0})
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    # Check if user already exists with this email
    email = guest.get("email", "")
    if email:
        existing = await db.users.find_one({"email": email})
        if existing:
            raise HTTPException(status_code=409, detail="A user with this email already exists")
    user_id = str(uuid.uuid4())
    password = data.get("password", "Test@5812!")
    role = data.get("role", "Staff")
    user = {
        "id": user_id, "name": guest.get("name", ""), "email": email,
        "phone": guest.get("phone", ""), "password_hash": hash_password(password),
        "role": role, "status": "active", "department": data.get("department", ""),
        "location_id": guest.get("location_id") or current_user.get("active_campus_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(), "moved_from": "guests", "original_id": guest_id,
    }
    await db.users.insert_one(user)
    # Create member profile
    member_id = str(uuid.uuid4())
    await db.members.insert_one({
        "id": member_id, "user_id": user_id, "name": user["name"], "email": email,
        "phone": user["phone"], "role": "member", "membership_type": role.lower(),
        "status": "active", "location_id": user["location_id"], "department": user.get("department", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Link guest to user
    await db.guests.update_one({"id": guest_id}, {"$set": {"user_id": user_id, "is_staff_guest": True, "moved_to_staff": True}})
    user.pop("_id", None)
    user.pop("password_hash", None)
    await _audit(current_user["id"], "move", "guest_to_staff", guest_id, {"user_id": user_id, "role": role})
    return {"message": f"Moved {guest.get('name')} to staff as {role}", "user_id": user_id, "member_id": member_id}
