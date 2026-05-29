"""Admin user management: edit all users, password reset, bulk operations, audit"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, require_director, require_manager, require_staff, hash_password, _audit, logger, is_system_admin, get_campus_filter, generate_title, resolve_parent_campus
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import secrets

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ========== USER MANAGEMENT ==========

@router.get("/users/directory")
async def user_directory(include_all: bool = False, current_user: dict = Depends(get_current_user)) -> list:
    """Lightweight user list for cross-referencing in boards, tasks, etc.
    Scoped to current user's campus; returns active staff-capable users only.
    Admins can pass include_all=true to bypass filters."""
    STAFF_ROLES = ["admin", "system_admin", "Executive Director", "Adviser", "Director",
                   "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"]
    if include_all and is_system_admin(current_user):
        query = {"status": {"$ne": "deleted"}}
    else:
        campus = await get_campus_filter(current_user)
        base = {"status": "active", "role": {"$in": STAFF_ROLES}}
        query = {"$and": [base, campus]} if campus else base
    users = await db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "role": 1, "photo_url": 1, "location_id": 1, "location_ids": 1, "email": 1}
    ).sort("name", 1).to_list(1000)
    return users


@router.get("/users")
async def list_all_users(search: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(require_admin)) -> list:
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
async def create_user(data: dict, current_user: dict = Depends(require_admin)) -> dict:
    """Create a new user account. Optionally also creates a linked member record."""
    # Guard: only system admins can grant admin-tier roles
    ADMIN_TIER = {"admin", "system_admin", "Executive Director"}
    new_role = data.get("role", "Staff")
    if new_role in ADMIN_TIER and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail=f"Only system admins can assign the '{new_role}' role")
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    password = data.get("password") or "Test@5812!"
    user_id = str(uuid.uuid4())
    # Support multi-campus: accept location_ids array + expand with parent campuses
    primary_loc = data.get("location_id", "") or ""
    loc_ids = list(data.get("location_ids") or [])
    if primary_loc and primary_loc not in loc_ids:
        loc_ids.append(primary_loc)
    expanded_locs = list(set(loc_ids))
    for lid in list(expanded_locs):
        parent = await resolve_parent_campus(lid)
        if parent and parent not in expanded_locs:
            expanded_locs.append(parent)
    user = {
        "id": user_id,
        "name": name,
        "email": email,
        "phone": data.get("phone", ""),
        "role": data.get("role", "Staff"),
        "status": data.get("status", "active"),
        "department": data.get("department", ""),
        "location_id": primary_loc,
        "location_ids": expanded_locs,
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
            "status": "active", "location_id": primary_loc,
            "location_ids": expanded_locs,
            "department": data.get("department", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        user_out["member_id"] = member_id
        user_out["has_member_profile"] = True

    # Auto-mark staff as guest for their campus
    staff_roles = {"Executive Director", "Adviser", "Director", "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"}
    if user.get("role") in staff_roles and user.get("location_id"):
        existing_guest = await db.guests.find_one({"$or": [{"email": email}, {"user_id": user_id}]})
        if not existing_guest:
            await db.guests.insert_one({
                "id": f"gst_{uuid.uuid4().hex[:8]}", "name": name, "email": email,
                "phone": data.get("phone", ""), "user_id": user_id,
                "is_parent": False, "is_staff_guest": True,
                "location_id": user["location_id"],
                "notes": f"Auto-linked staff guest for {user['role']}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Link existing guest to this user
            if not existing_guest.get("user_id"):
                await db.guests.update_one({"id": existing_guest["id"]}, {"$set": {"user_id": user_id, "is_staff_guest": True}})

    await _audit(current_user["id"], "create", "user", user_id, {"name": name, "role": user["role"]})
    return user_out


@router.post("/users/import")
async def import_users(data: dict, current_user: dict = Depends(require_admin)) -> dict:
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
async def get_user(user_id: str, current_user: dict = Depends(require_admin)) -> dict:
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}/profile")
async def get_user_full_profile(user_id: str, current_user: dict = Depends(require_admin)) -> dict:
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
async def admin_update_user(user_id: str, data: dict, current_user: dict = Depends(require_admin)) -> dict:
    # Guard: only system admins can grant admin-tier roles
    ADMIN_TIER = {"admin", "system_admin", "Executive Director"}
    if data.get("role") in ADMIN_TIER and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail=f"Only system admins can assign the '{data['role']}' role")
    ACCOUNT_FIELDS = {"name", "email", "phone", "national_id", "role", "status",
                      "address", "emergency_contact", "department", "departments", "notes",
                      "secondary_roles", "is_parent", "is_customer", "is_donor", "is_guest", "is_medical", "is_resident", "has_restricted_access", "resident_location_id", "pin",
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
    # Auto-add to restricted residents if is_resident + resident_location_id set
    if update.get("is_resident") and update.get("resident_location_id"):
        existing_res = await db.residents.find_one({"member_id": user_id, "location_id": update["resident_location_id"], "status": "active"})
        if not existing_res:
            await db.residents.insert_one({
                "id": f"res_{uuid.uuid4().hex[:8]}", "member_id": user_id,
                "member_name": user.get("name", ""), "source": "flag_toggle",
                "location_id": update["resident_location_id"], "tags": [], "status": "active",
                "assigned_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
            })
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
async def admin_reset_password(user_id: str, data: dict, current_user: dict = Depends(require_director)) -> dict:
    new_password = data.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    # Resolve: if user_id is actually a member_id, find the linked user
    user_exists = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1})
    if not user_exists:
        # Try member → user_id lookup
        member = await db.members.find_one({"id": user_id}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
        if member:
            if member.get("user_id"):
                user_id = member["user_id"]
            elif member.get("email"):
                # Fallback: find user by email
                user_by_email = await db.users.find_one({"email": member["email"]}, {"_id": 0, "id": 1})
                if user_by_email:
                    user_id = user_by_email["id"]
                    # Fix the broken link while we're at it
                    await db.members.update_one({"id": member.get("id", user_id)}, {"$set": {"user_id": user_id}})
                else:
                    raise HTTPException(status_code=404, detail=f"No user account found for {member.get('name', 'this member')}. Create a user account first.")
            else:
                raise HTTPException(status_code=404, detail="Member has no linked user account or email to look up")
        else:
            raise HTTPException(status_code=404, detail="User not found")
    result = await db.users.update_one({"id": user_id}, {"$set": {
        "password_hash": hash_password(new_password),
        "status": "active",
        "password_reset_at": datetime.now(timezone.utc).isoformat(),
        "password_reset_by": current_user["id"],
    }})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await _audit(current_user["id"], "update", "password_reset", user_id)
    # Send email notification to user about password reset
    email_sent = False
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1})
    if user and user.get("email"):
        try:
            from email_helpers import send_notification_email
            email_sent = await send_notification_email(
                user["email"],
                "58:12 Global — Your Password Has Been Reset",
                f"""<h2 style="color:#1a1a2e">Password Reset</h2>
                <p>Hi {user.get('name', '')},</p>
                <p>Your password has been reset by an administrator.</p>
                <div style="background:#f8f9fa;border-left:4px solid #fbbf24;padding:12px 16px;margin:16px 0;border-radius:4px">
                  <p style="font-size:14px;font-weight:600;margin:0">Your new password: <code>{new_password}</code></p>
                </div>
                <p style="font-size:13px;color:#666">Please log in and change your password immediately.</p>
                <p style="margin-top:16px">
                  <a href="https://5812-global.org" style="background:#1a1a2e;color:#fbbf24;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-block">Log In Now</a>
                </p>"""
            )
        except Exception as e:
            logger.warning(f"Password reset email failed: {e}")
    return {"message": "Password reset successfully", "email_sent": email_sent, "new_password": new_password}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: str, current_user: dict = Depends(require_admin)) -> dict:
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
    # Cascade: clean up references
    await db.tasks.update_many({"assignees": user_id}, {"$pull": {"assignees": user_id}})
    await db.boards.update_many({"tagged_members": user_id}, {"$pull": {"tagged_members": user_id}})
    await db.members.update_many({"user_id": user_id}, {"$unset": {"user_id": ""}})
    await db.guests.update_many({"user_id": user_id}, {"$unset": {"user_id": ""}})
    await _audit(current_user["id"], "delete", "user", user_id, {"name": user.get("name")})
    return {"message": "User deleted"}


# ========== BULK OPERATIONS ==========

@router.post("/users/bulk-update")
async def bulk_update_users(data: dict, current_user: dict = Depends(require_admin)) -> dict:
    """Bulk update multiple users. Expects: { "user_ids": [...], "updates": { "role": "...", "status": "..." } }"""
    user_ids = data.get("user_ids", [])
    updates = data.get("updates", {})
    if not user_ids:
        raise HTTPException(status_code=400, detail="No user_ids provided")
    # Guard: only system admins can bulk-grant admin-tier roles
    ADMIN_TIER = {"admin", "system_admin", "Executive Director"}
    if updates.get("role") in ADMIN_TIER and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail=f"Only system admins can assign the '{updates['role']}' role")
    allowed = {"role", "status", "department", "notes", "secondary_roles", "is_parent", "is_customer", "is_donor"}
    clean_updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not clean_updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    clean_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.users.update_many({"id": {"$in": user_ids}}, {"$set": clean_updates})
    await _audit(current_user["id"], "bulk_update", "users", None, {"count": result.modified_count, "fields": list(clean_updates.keys())})
    return {"updated": result.modified_count}


@router.post("/users/bulk-delete")
async def bulk_delete_users(data: dict, current_user: dict = Depends(require_admin)) -> dict:
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
async def list_audit(skip: int = 0, limit: int = 100, current_user: dict = Depends(require_admin)) -> dict:
    logs = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.audit_log.count_documents({})
    # Backfill user_name for older log rows that don't have it stored.
    missing_user_ids = list({l.get("user_id") for l in logs if l.get("user_id") and not l.get("user_name")})
    if missing_user_ids:
        users = await db.users.find(
            {"id": {"$in": missing_user_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(len(missing_user_ids))
        name_map = {u["id"]: u.get("name", "") for u in users}
        for log in logs:
            if not log.get("user_name") and log.get("user_id"):
                log["user_name"] = name_map.get(log["user_id"], "")
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



@router.post("/cleanup-orphans")
async def cleanup_orphaned_references(current_user: dict = Depends(require_admin)) -> dict:
    """Scan and remove orphaned references to deleted profiles across all collections."""
    cleaned = {}

    # Get all valid IDs
    valid_user_ids = set()
    async for u in db.users.find({}, {"_id": 0, "id": 1}):
        valid_user_ids.add(u["id"])
    valid_member_ids = set()
    async for m in db.members.find({}, {"_id": 0, "id": 1}):
        valid_member_ids.add(m["id"])
    valid_guest_ids = set()
    async for g in db.guests.find({}, {"_id": 0, "id": 1}):
        valid_guest_ids.add(g["id"])
    valid_child_ids = set()
    async for c in db.children.find({}, {"_id": 0, "id": 1}):
        valid_child_ids.add(c["id"])
    all_valid = valid_user_ids | valid_member_ids | valid_guest_ids | valid_child_ids

    # Clean tasks: remove invalid assignees
    tasks_cleaned = 0
    async for task in db.tasks.find({"assignees": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "assignees": 1}):
        invalid = [a for a in (task.get("assignees") or []) if a not in all_valid]
        if invalid:
            await db.tasks.update_one({"id": task["id"]}, {"$pull": {"assignees": {"$in": invalid}}})
            tasks_cleaned += len(invalid)
    if tasks_cleaned: cleaned["tasks_assignees"] = tasks_cleaned

    # Clean boards: remove invalid tagged_members
    boards_cleaned = 0
    async for board in db.boards.find({"tagged_members": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "tagged_members": 1}):
        invalid = [m for m in (board.get("tagged_members") or []) if m not in all_valid]
        if invalid:
            await db.boards.update_one({"id": board["id"]}, {"$pull": {"tagged_members": {"$in": invalid}}})
            boards_cleaned += len(invalid)
    if boards_cleaned: cleaned["boards_tagged_members"] = boards_cleaned

    # Clean children: remove invalid parent_ids
    children_cleaned = 0
    async for child in db.children.find({"parent_ids": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "parent_ids": 1}):
        invalid = [p for p in (child.get("parent_ids") or []) if p not in all_valid]
        if invalid:
            await db.children.update_one({"id": child["id"]}, {"$pull": {"parent_ids": {"$in": invalid}}})
            children_cleaned += len(invalid)
    if children_cleaned: cleaned["children_parent_ids"] = children_cleaned

    # Clean conversations: remove invalid participants
    convs_cleaned = 0
    async for conv in db.conversations.find({"participants": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "participants": 1}):
        invalid = [p for p in (conv.get("participants") or []) if p not in valid_user_ids]
        if invalid:
            await db.conversations.update_one({"id": conv["id"]}, {"$pull": {"participants": {"$in": invalid}}})
            convs_cleaned += len(invalid)
    if convs_cleaned: cleaned["conversations_participants"] = convs_cleaned

    # Clean residents: remove entries for deleted people
    residents_cleaned = 0
    async for res in db.residents.find({"status": "active"}, {"_id": 0, "id": 1, "member_id": 1}):
        if res.get("member_id") not in all_valid:
            await db.residents.update_one({"id": res["id"]}, {"$set": {"status": "orphaned"}})
            residents_cleaned += 1
    if residents_cleaned: cleaned["residents"] = residents_cleaned

    # Clean members with invalid user_id
    members_cleaned = 0
    async for mem in db.members.find({"user_id": {"$exists": True, "$ne": ""}}, {"_id": 0, "id": 1, "user_id": 1}):
        if mem.get("user_id") and mem["user_id"] not in valid_user_ids:
            await db.members.update_one({"id": mem["id"]}, {"$unset": {"user_id": ""}})
            members_cleaned += 1
    if members_cleaned: cleaned["members_user_ids"] = members_cleaned

    await _audit(current_user["id"], "maintenance", "cleanup_orphans", "system", cleaned)
    return {"cleaned": cleaned, "total_orphans_removed": sum(cleaned.values())}



# ========== BULK REASSIGN LOCATION-SPECIFIC DATA ==========

REASSIGNABLE_COLLECTIONS = {
    "events": "Events",
    "tasks": "Tasks",
    "boards": "Kanban Boards",
    "members": "Members",
    "users": "Users",
    "financial": "Financial entries (donations/expenses)",
    "sales": "Sales / POS transactions",
    "products": "Products",
    "resources": "Resources / Assets",
    "hr_salaries": "HR — Salaries",
    "hr_payslips": "HR — Payslips",
    "hr_contracts": "HR — Contracts",
}


@router.get("/reassign/preview")
async def reassign_preview(from_location_id: str, current_user: dict = Depends(require_admin)) -> dict:
    """Count records keyed to a given location_id across all reassignable collections.
    Use this to preview impact before calling /reassign/run."""
    if not from_location_id:
        raise HTTPException(status_code=400, detail="from_location_id required")
    counts = {}
    for coll, _label in REASSIGNABLE_COLLECTIONS.items():
        try:
            counts[coll] = await db[coll].count_documents({"location_id": from_location_id})
        except Exception as e:
            logger.error(f"reassign_preview count failed for {coll}: {e}")
            counts[coll] = 0
    return {"from_location_id": from_location_id, "counts": counts, "total": sum(counts.values())}


@router.post("/reassign/run")
async def reassign_run(data: dict, current_user: dict = Depends(require_admin)) -> dict:
    """Bulk-reassign location-keyed records from one campus to another.
    Body: { from_location_id, to_location_id, collections: [...] (default = all reassignable) }
    Idempotent; only touches records whose location_id == from_location_id."""
    from_id = data.get("from_location_id")
    to_id = data.get("to_location_id")
    collections = data.get("collections") or list(REASSIGNABLE_COLLECTIONS.keys())
    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_location_id and to_location_id required")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="from and to must differ")
    # Verify target campus exists
    target = await db.locations.find_one({"id": to_id}, {"_id": 0, "id": 1, "name": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Target campus not found")
    moved = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for coll in collections:
        if coll not in REASSIGNABLE_COLLECTIONS:
            continue
        try:
            res = await db[coll].update_many(
                {"location_id": from_id},
                {"$set": {"location_id": to_id, "reassigned_from": from_id, "reassigned_at": now_iso}},
            )
            moved[coll] = res.modified_count
        except Exception as e:
            logger.error(f"reassign {coll}: {e}")
            moved[coll] = 0
    # Users/members carry an array `location_ids` too — patch those when caller asks.
    if data.get("patch_location_arrays", True):
        for coll in ("users", "members"):
            try:
                # Replace the from_id occurrence inside location_ids
                cursor = db[coll].find({"location_ids": from_id}, {"_id": 0, "id": 1, "location_ids": 1})
                arr_patched = 0
                async for doc in cursor:
                    new_arr = [to_id if x == from_id else x for x in (doc.get("location_ids") or [])]
                    # de-dup while preserving order
                    seen = set(); deduped = []
                    for x in new_arr:
                        if x not in seen:
                            seen.add(x); deduped.append(x)
                    await db[coll].update_one({"id": doc["id"]}, {"$set": {"location_ids": deduped}})
                    arr_patched += 1
                if arr_patched:
                    moved[f"{coll}_location_ids_array"] = arr_patched
            except Exception as e:
                logger.error(f"reassign array-patch {coll}: {e}")
    await _audit(current_user["id"], "reassign", "location_data", from_id, {
        "to_location_id": to_id, "moved": moved,
    })
    return {"from_location_id": from_id, "to_location_id": to_id, "target_name": target.get("name"), "moved": moved, "total": sum(moved.values())}


# ========== FINANCE ACCESS MANAGEMENT ==========

@router.get("/finance-access/users")
async def list_finance_access_users(current_user: dict = Depends(require_admin)):
    """List all users + their finance-access status. Useful for the admin
    panel that grants/revokes financial visibility."""
    from deps import FINANCE_PRIVILEGED_ROLES
    users = await db.users.find(
        {"status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "finance_access": 1,
         "finance_access_expires_at": 1, "location_id": 1, "department": 1},
    ).sort("name", 1).to_list(2000)
    now_iso = datetime.now(timezone.utc).isoformat()
    for u in users:
        role = u.get("role") or ""
        u["finance_access_implicit"] = role in FINANCE_PRIVILEGED_ROLES
        # Effective access takes expiry into account
        explicit_active = bool(u.get("finance_access"))
        if explicit_active and u.get("finance_access_expires_at"):
            if str(u["finance_access_expires_at"]) <= now_iso:
                explicit_active = False
                u["finance_access_expired"] = True
        u["finance_access_effective"] = u["finance_access_implicit"] or explicit_active
    return users


@router.put("/finance-access/users/{user_id}")
async def set_finance_access(user_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Grant or revoke explicit finance access for a non-Director user.
    Body: { finance_access: bool, expires_at?: 'YYYY-MM-DD', ttl_days?: int, reason? }
    `ttl_days` (if positive) overrides `expires_at` and sets expiry that many days out.
    Omitting both = permanent grant."""
    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "finance_access": 1},
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_state = bool(data.get("finance_access"))
    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "finance_access": new_state,
        "finance_access_changed_at": now_iso,
        "finance_access_changed_by": current_user["id"],
    }
    # Compute expiry: ttl_days > expires_at > permanent (clear)
    if new_state:
        ttl_days = data.get("ttl_days")
        expires_at = data.get("expires_at")
        if ttl_days and int(ttl_days) > 0:
            from datetime import timedelta
            update["finance_access_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(days=int(ttl_days))
            ).strftime("%Y-%m-%dT23:59:59+00:00")
        elif expires_at:
            update["finance_access_expires_at"] = str(expires_at)[:10] + "T23:59:59+00:00"
        else:
            # Permanent grant — explicitly clear any previous expiry
            update["finance_access_expires_at"] = None
    else:
        # Revoke — also clear expiry
        update["finance_access_expires_at"] = None
    await db.users.update_one({"id": user_id}, {"$set": update})
    await _audit(
        current_user["id"],
        "grant" if new_state else "revoke",
        "finance_access",
        user_id,
        {"target_name": target.get("name"), "reason": data.get("reason", ""),
         "expires_at": update.get("finance_access_expires_at")},
    )
    return {"updated": True, "user_id": user_id, "finance_access": new_state,
            "expires_at": update.get("finance_access_expires_at")}



# ========== GUESTS → MEMBERS UNIFICATION MIGRATION ==========

@router.get("/migrate/guests-to-members/preview")
async def preview_guest_migration(current_user: dict = Depends(require_admin)) -> dict:
    """Counts pending guest→member mirror rows. Safe to call any time."""
    total_guests = await db.guests.count_documents({})
    already_mirrored = await db.members.count_documents({"mirrored_from_guests": True})
    guest_ids = await db.guests.find({}, {"_id": 0, "id": 1}).to_list(50000)
    ids = [g["id"] for g in guest_ids if g.get("id")]
    existing_member_ids = set()
    if ids:
        async for m in db.members.find({"id": {"$in": ids}}, {"_id": 0, "id": 1}):
            existing_member_ids.add(m["id"])
    pending = sum(1 for i in ids if i not in existing_member_ids)
    return {
        "total_guests": total_guests,
        "already_mirrored_in_members": already_mirrored,
        "pending_to_migrate": pending,
        "members_with_same_id_already": len(existing_member_ids - {i for i in ids if i in existing_member_ids and i not in existing_member_ids}),
    }


@router.post("/migrate/guests-to-members/run")
async def run_guest_migration(data: dict = None, current_user: dict = Depends(require_admin)) -> dict:
    """One-time migration: mirror every guest into the unified `members`
    collection with `kind` = 'parent' (if is_parent) or 'guest'. Same `id`
    is reused so all existing FKs (children.parent_ids, residents, etc.)
    keep working without rewrite.

    - Idempotent: re-running will only upsert; no duplicate inserts.
    - Pass `{ overwrite: true }` to overwrite existing member fields with
      the latest guest data (use after major guest edits if needed).
    """
    overwrite = bool((data or {}).get("overwrite"))
    migrated = 0
    skipped = 0
    errors = 0
    async for guest in db.guests.find({}, {"_id": 0}):
        gid = guest.get("id")
        if not gid:
            continue
        try:
            mirror_kind = "parent" if guest.get("is_parent") else "guest"
            existing = await db.members.find_one({"id": gid}, {"_id": 0, "id": 1, "mirrored_from_guests": 1})
            if existing and not existing.get("mirrored_from_guests") and not overwrite:
                # Conflict — a real member already owns this id. Skip rather than clobber.
                skipped += 1
                continue
            payload = {k: v for k, v in guest.items() if k not in ("_id",)}
            payload["kind"] = mirror_kind
            payload["mirrored_from_guests"] = True
            payload.setdefault("status", "active")
            await db.members.update_one({"id": gid}, {"$set": payload}, upsert=True)
            migrated += 1
        except Exception as e:
            logger.error(f"guest→member migration failed for {gid}: {e}")
            errors += 1
    await _audit(current_user["id"], "migrate", "guests_to_members", "all", {
        "migrated": migrated, "skipped": skipped, "errors": errors, "overwrite": overwrite,
    })
    return {"migrated": migrated, "skipped_conflict": skipped, "errors": errors}
