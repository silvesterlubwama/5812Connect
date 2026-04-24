"""Admin user management: edit all users, password reset, bulk operations, audit"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, require_director, require_manager, require_staff, hash_password, _audit, logger, is_system_admin, get_campus_filter, generate_title, resolve_parent_campus
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import secrets

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ========== USER MANAGEMENT ==========

@router.get("/users")
async def list_all_users(search: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(require_admin)):
    campus = await get_campus_filter(current_user)
    query = {}
    conditions = []
    if campus:
        conditions.append(campus)
    if search:
        conditions.append({"$or": [{"name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]})
    if role and role != "all": query["role"] = role
    if status and status != "all": query["status"] = status
    if conditions:
        query["$and"] = conditions
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(500)
    # Enrich with member profile existence and location name
    loc_cache = {}
    for u in users:
        member = await db.members.find_one(
            {"$or": [{"user_id": u["id"]}, {"email": u.get("email", "__none__")}]},
            {"_id": 0, "id": 1}
        )
        u["has_member_profile"] = bool(member)
        if member:
            u["member_id"] = member["id"]
        # Resolve location name
        lid = u.get("location_id")
        if lid:
            if lid not in loc_cache:
                loc = await db.locations.find_one({"id": lid}, {"_id": 0, "name": 1})
                loc_cache[lid] = loc.get("name") if loc else ""
            u["location_name"] = loc_cache[lid]
    return users


@router.post("/users")
async def create_user(data: dict, current_user: dict = Depends(require_admin)):
    """Create a new user account. Optionally also creates a linked member record."""
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    password = data.get("password") or "User@58:12"
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "name": name,
        "email": email,
        "phone": data.get("phone", ""),
        "role": data.get("role", "Staff"),
        "status": data.get("status", "active"),
        "department": data.get("department", ""),
        "location_id": data.get("location_id", ""),
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.users.insert_one(user)
    user.pop("_id", None)
    user_out = {k: v for k, v in user.items() if k != "password_hash"}
    user_out["temp_password"] = password  # show once so admin can share

    if data.get("also_create_member", True):
        member_id = str(uuid.uuid4())
        await db.members.insert_one({
            "id": member_id, "user_id": user_id,
            "name": name, "email": email, "phone": data.get("phone", ""),
            "role": "member", "membership_type": data.get("role", "Staff").lower(),
            "status": "active", "location_id": data.get("location_id", ""),
            "department": data.get("department", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        user_out["member_id"] = member_id
        user_out["has_member_profile"] = True
    await _audit(current_user["id"], "create", "user", user_id, {"name": name, "role": user["role"]})
    return user_out


@router.post("/users/import")
async def import_users(data: dict, current_user: dict = Depends(require_admin)):
    """Bulk import users from a JSON array or CSV-parsed data."""
    users_data = data.get("users", [])
    if not users_data:
        raise HTTPException(status_code=400, detail="No users provided")
    created = 0
    skipped = 0
    error_list = []
    for row in users_data:
        name = (row.get("name") or row.get("Name") or "").strip()
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        if not name or not email:
            error_list.append(f"Missing name/email: {row}")
            skipped += 1
            continue
        if await db.users.find_one({"email": email}):
            skipped += 1
            continue
        password = row.get("password") or secrets.token_urlsafe(10)
        user_id = str(uuid.uuid4())
        role = row.get("role") or row.get("Role") or "Staff"
        loc_id = row.get("location_id") or row.get("location") or ""
        dept = row.get("department") or row.get("Department") or ""
        phone = row.get("phone") or row.get("Phone") or ""
        user = {
            "id": user_id, "name": name, "email": email, "phone": phone,
            "role": role, "status": "active", "department": dept,
            "location_id": loc_id, "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
        }
        await db.users.insert_one(user)
        # Always create member record on import
        await db.members.insert_one({
            "id": str(uuid.uuid4()), "user_id": user_id,
            "name": name, "email": email, "phone": phone,
            "role": "member", "membership_type": role.lower(),
            "status": "active", "location_id": loc_id, "department": dept,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        created += 1
    await _audit(current_user["id"], "create", "bulk_import_users", f"{created}_users")
    return {"created": created, "skipped": skipped, "errors": error_list[:10]}




@router.get("/users/{user_id}")
async def get_user(user_id: str, current_user: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}/profile")
async def get_user_full_profile(user_id: str, current_user: dict = Depends(require_admin)):
    """Return merged user + member profile for admin full-edit"""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    # Merge with member record
    member = await db.members.find_one(
        {"$or": [{"user_id": user_id}, {"id": user_id}, {"email": user.get("email", "__none__")}]},
        {"_id": 0}
    )
    if member:
        # member data takes precedence for profile fields; user for account fields
        merged = {**member, **{k: v for k, v in user.items() if k in {"id", "email", "role", "status", "pin"}}}
        merged["member_id"] = member.get("id")
        return merged
    return user


@router.put("/users/{user_id}")
async def admin_update_user(user_id: str, data: dict, current_user: dict = Depends(require_admin)):
    ACCOUNT_FIELDS = {"name", "email", "phone", "national_id", "role", "status",
                      "address", "emergency_contact", "department", "departments", "notes",
                      "secondary_roles", "is_parent", "is_customer", "is_donor", "is_guest", "pin",
                      "location_id", "location_ids", "title", "extension", "forward_to",
                      "gender", "date_of_birth", "group", "program"}
    update = {k: v for k, v in data.items() if k in ACCOUNT_FIELDS}
    if not update: raise HTTPException(status_code=400, detail="No valid fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    loc_id, expanded = await _expand_user_locations(update, data)

    if "title" not in data or not data.get("title"):
        role = update.get("role") or (await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1}) or {}).get("role", "")
        dept = update.get("department") or ""
        update["title"] = await generate_title(role, expanded or ([loc_id] if loc_id else []), dept)

    user_update = {k: v for k, v in update.items() if k in ACCOUNT_FIELDS}
    if user_update:
        await db.users.update_one({"id": user_id}, {"$set": user_update})
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})

    await _sync_member_profile(user_id, user, update, ACCOUNT_FIELDS, loc_id, expanded)
    await _audit(current_user["id"], "update", "user", user_id, {"fields": list(update.keys())})
    return user


async def _expand_user_locations(update: dict, data: dict) -> tuple:
    """Expand location_ids with parent campuses. Returns (loc_id, expanded)."""
    loc_ids = update.get("location_ids") or data.get("location_ids") or []
    loc_id = update.get("location_id") or data.get("location_id") or ""
    if loc_id and loc_id not in loc_ids:
        loc_ids.append(loc_id)
    expanded = list(set(loc_ids))
    for lid in list(expanded):
        parent = await resolve_parent_campus(lid)
        if parent and parent not in expanded:
            expanded.append(parent)
    if expanded:
        update["location_ids"] = expanded
    if loc_id:
        update["location_id"] = loc_id
    return loc_id, expanded


async def _sync_member_profile(user_id: str, user: dict, update: dict, account_fields: set, loc_id: str, expanded: list):
    """Sync user update to linked member profile, creating if missing."""
    if not user or not user.get("email"):
        return
    member_update = {k: v for k, v in update.items() if k in account_fields}
    if not member_update:
        return
    member_exists = await db.members.find_one(
        {"$or": [{"user_id": user_id}, {"email": user["email"]}]},
        {"_id": 0, "id": 1}
    )
    if member_exists:
        await db.members.update_one(
            {"$or": [{"user_id": user_id}, {"email": user["email"]}]},
            {"$set": member_update}
        )
    else:
        member_id = str(uuid.uuid4())
        await db.members.insert_one({
            "id": member_id, "user_id": user_id,
            "name": user.get("name", ""), "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "role": "member", "membership_type": (user.get("role") or "Staff").lower(),
            "status": "active",
            "location_id": loc_id, "location_ids": expanded,
            "department": user.get("department", ""),
            "departments": update.get("departments", []),
            "title": update.get("title", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in member_update.items() if k in account_fields},
        })


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, data: dict, current_user: dict = Depends(require_director)):
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
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Soft-delete: move to deleted_items
    user.pop("password_hash", None)
    user["_deleted_from"] = "users"
    user["deleted_at"] = datetime.now(timezone.utc).isoformat()
    user["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(user)
    await db.users.delete_one({"id": user_id})
    await _audit(current_user["id"], "delete", "user", user_id, {"name": user.get("name")})
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


@router.post("/members/bulk-export")
async def bulk_export_members(data: dict, current_user: dict = Depends(get_current_user)):
    """Export selected members as JSON. Body: {ids: []} or empty for all."""
    ids = data.get("ids") or data.get("member_ids")
    query = {"id": {"$in": ids}} if ids else {}
    members = await db.members.find(query, {"_id": 0}).sort("name", 1).to_list(1000)
    return members




# ========== AUDIT LOG ==========

@router.get("/audit")
async def list_audit(skip: int = 0, limit: int = 100, current_user: dict = Depends(require_admin)):
    logs = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.audit_log.count_documents({})
    return {"logs": logs, "total": total}


# ========== DELETED ITEMS (Recycle Bin / Restore) ==========

@router.get("/deleted-items")
async def list_deleted_items(collection: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """List items deleted in the last 30 days, optionally filtered by collection."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    query = {"deleted_at": {"$gte": cutoff}}
    if collection:
        query["_deleted_from"] = collection
    items = await db.deleted_items.find(query, {"_id": 0}).sort("deleted_at", -1).to_list(500)
    return items


@router.post("/deleted-items/{item_id}/restore")
async def restore_deleted_item(item_id: str, current_user: dict = Depends(require_admin)):
    """Restore a soft-deleted item back to its original collection."""
    item = await db.deleted_items.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Deleted item not found")
    collection_name = item.pop("_deleted_from", None)
    if not collection_name:
        raise HTTPException(status_code=400, detail="Cannot determine original collection")
    item.pop("deleted_at", None)
    item.pop("deleted_by", None)
    target = db[collection_name]
    # Check if item with same id already exists (shouldn't, but be safe)
    existing = await target.find_one({"id": item_id})
    if existing:
        raise HTTPException(status_code=409, detail="An item with this ID already exists in the collection")
    await target.insert_one(item)
    await db.deleted_items.delete_one({"id": item_id})
    await _audit(current_user["id"], "restore", collection_name, item_id, {"name": item.get("name") or item.get("family_name", "")})
    # Clean _id from response
    item.pop("_id", None)
    return {"message": f"Restored to {collection_name}", "item": item}


@router.delete("/deleted-items/{item_id}")
async def permanently_delete_item(item_id: str, current_user: dict = Depends(require_admin)):
    """Permanently delete an item from the recycle bin."""
    result = await db.deleted_items.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await _audit(current_user["id"], "permanent_delete", "deleted_items", item_id)
    return {"message": "Permanently deleted"}


@router.post("/deleted-items/bulk-delete")
async def bulk_delete_items(data: dict, current_user: dict = Depends(require_admin)):
    """Permanently delete multiple items from recycle bin."""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    result = await db.deleted_items.delete_many({"id": {"$in": ids}})
    await _audit(current_user["id"], "bulk_permanent_delete", "deleted_items", ",".join(ids[:5]))
    return {"message": f"Permanently deleted {result.deleted_count} items"}


@router.post("/deleted-items/bulk-restore")
async def bulk_restore_items(data: dict, current_user: dict = Depends(require_admin)):
    """Restore multiple items from recycle bin."""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    restored = 0
    for item_id in ids:
        item = await db.deleted_items.find_one({"id": item_id}, {"_id": 0})
        if not item:
            continue
        collection_name = item.pop("_deleted_from", None)
        if not collection_name:
            continue
        item.pop("deleted_at", None)
        item.pop("deleted_by", None)
        existing = await db[collection_name].find_one({"id": item_id})
        if existing:
            continue
        await db[collection_name].insert_one(item)
        await db.deleted_items.delete_one({"id": item_id})
        restored += 1
    return {"message": f"Restored {restored} items"}
