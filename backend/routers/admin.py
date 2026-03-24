"""Admin user management: edit all users, password reset"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, hash_password, _audit, logger
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
    allowed = {"name", "email", "phone", "national_id", "role", "status", "address", "emergency_contact", "department", "notes"}
    update = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not update: raise HTTPException(status_code=400, detail="No valid fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user_id}, {"$set": update})
    # Also update linked member record if email matches
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if user and user.get("email"):
        member_update = {k: v for k, v in update.items() if k in {"name", "phone", "email", "role", "status", "address", "emergency_contact", "department", "notes"}}
        if member_update:
            await db.members.update_one({"email": user["email"]}, {"$set": member_update})
    await _audit(current_user["id"], "update", "user", user_id, {"fields": list(update.keys())})
    return user


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, data: dict, current_user: dict = Depends(require_admin)):
    new_password = data.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await db.users.update_one({"id": user_id}, {"$set": {"password_hash": hash_password(new_password), "password_reset_at": datetime.now(timezone.utc).isoformat(), "password_reset_by": current_user["id"]}})
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
