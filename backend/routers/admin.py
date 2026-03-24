"""Admin user management: edit all users, password reset, bulk operations, audit"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, require_manager, require_staff, hash_password, _audit, logger
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ========== USER MANAGEMENT ==========

@router.get("/users")
async def list_all_users(search: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(require_admin)):
    query = {}
    if search:
        query["$or"] = [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]
    if role and role != "all": query["role"] = role
    if status and status != "all": query["status"] = status
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(500)
    return users


@router.get("/users/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}")
async def admin_update_user(user_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "email", "phone", "national_id", "role", "status", "address", "emergency_contact", "department", "notes", "secondary_roles", "is_parent", "is_customer", "is_donor", "pin"}
    update = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not update: raise HTTPException(status_code=400, detail="No valid fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user_id}, {"$set": update})
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if user and user.get("email"):
        member_update = {k: v for k, v in update.items() if k in {"name", "phone", "email", "role", "status", "address", "emergency_contact", "department", "notes", "secondary_roles", "is_parent", "is_customer", "is_donor", "pin"}}
        if member_update:
            await db.members.update_one({"email": user["email"]}, {"$set": member_update})
    await _audit(current_user["id"], "update", "user", user_id, {"fields": list(update.keys())})
    return user


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, data: dict, current_user: dict = Depends(require_admin)):
    new_password = data.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await db.users.update_one({"id": user_id}, {"$set": {
        "password_hash": hash_password(new_password),
        "password_reset_at": datetime.now(timezone.utc).isoformat(),
        "password_reset_by": current_user["id"],
    }})
    await _audit(current_user["id"], "update", "password_reset", user_id)
    return {"message": "Password reset successfully"}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: str, current_user: dict = Depends(require_admin)):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await _audit(current_user["id"], "delete", "user", user_id)
    return {"message": "User deleted"}


# ========== BULK OPERATIONS ==========

@router.post("/users/bulk-update")
async def bulk_update_users(data: dict, current_user: dict = Depends(require_admin)):
    """Bulk update multiple users. Expects: { "user_ids": [...], "updates": { "role": "...", "status": "..." } }"""
    user_ids = data.get("user_ids", [])
    updates = data.get("updates", {})
    if not user_ids:
        raise HTTPException(status_code=400, detail="No user_ids provided")
    allowed = {"role", "status", "department", "notes", "secondary_roles", "is_parent", "is_customer", "is_donor"}
    clean_updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not clean_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    clean_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_many({"id": {"$in": user_ids}}, {"$set": clean_updates})
    await _audit(current_user["id"], "bulk_update", "users", None, {"count": result.modified_count, "fields": list(clean_updates.keys())})
    return {"updated": result.modified_count}


@router.post("/users/bulk-delete")
async def bulk_delete_users(data: dict, current_user: dict = Depends(require_admin)):
    """Bulk delete multiple users. Expects: { "user_ids": [...] }"""
    user_ids = data.get("user_ids", [])
    if not user_ids:
        raise HTTPException(status_code=400, detail="No user_ids provided")
    if current_user["id"] in user_ids:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_many({"id": {"$in": user_ids}})
    await _audit(current_user["id"], "bulk_delete", "users", None, {"count": result.deleted_count})
    return {"deleted": result.deleted_count}


# ========== MEMBERS BULK OPERATIONS ==========

@router.post("/members/bulk-update")
async def bulk_update_members(data: dict, current_user: dict = Depends(require_manager)):
    member_ids = data.get("member_ids", [])
    updates = data.get("updates", {})
    if not member_ids:
        raise HTTPException(status_code=400, detail="No member_ids provided")
    allowed = {"role", "status", "group", "location_id", "department", "is_parent", "is_customer", "is_donor", "secondary_roles"}
    clean_updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not clean_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    clean_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.members.update_many({"id": {"$in": member_ids}}, {"$set": clean_updates})
    await _audit(current_user["id"], "bulk_update", "members", None, {"count": result.modified_count})
    return {"updated": result.modified_count}


@router.post("/members/bulk-delete")
async def bulk_delete_members(data: dict, current_user: dict = Depends(require_admin)):
    member_ids = data.get("member_ids", [])
    if not member_ids:
        raise HTTPException(status_code=400, detail="No member_ids provided")
    result = await db.members.delete_many({"id": {"$in": member_ids}})
    await _audit(current_user["id"], "bulk_delete", "members", None, {"count": result.deleted_count})
    return {"deleted": result.deleted_count}


# ========== AUDIT LOG ==========

@router.get("/audit")
async def list_audit(skip: int = 0, limit: int = 100, current_user: dict = Depends(require_admin)):
    logs = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.audit_log.count_documents({})
    return {"logs": logs, "total": total}
