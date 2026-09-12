"""Badges + wallet badges + auto-issue + list + invalidate / reactivate."""
from fastapi import APIRouter, Depends, HTTPException, Query
from deps import db, get_current_user, _audit, require_staff, require_admin, is_system_admin, get_campus_filter, logger
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["members"])


# ========== BADGES (badge templates) ==========

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


# ========== WALLET BADGES ==========

@router.post("/members/{member_id}/wallet-badge")
async def create_wallet_badge(member_id: str, current_user: dict = Depends(require_staff)) -> dict:
    """Generate a shareable badge URL with a unique token for mobile wallet/home screen."""
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "password_hash": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    token = uuid.uuid4().hex[:16]
    # Resolve location country
    loc = await db.locations.find_one({"id": member.get("location_id", "")}, {"_id": 0, "name": 1, "country": 1, "country_code": 1}) if member.get("location_id") else None
    badge_data = {
        "id": f"wbadge_{token}",
        "token": token,
        "member_id": member_id,
        "name": member.get("name", ""),
        "role": member.get("role", member.get("membership_type", "")),
        "title": member.get("title", ""),
        "department": member.get("department", ""),
        "photo_url": member.get("photo_url", ""),
        "location_name": loc.get("name") if loc else "",
        "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
        "qr_data": member_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.wallet_badges.update_one({"member_id": member_id}, {"$set": badge_data}, upsert=True)
    return badge_data


@router.post("/children/{child_id}/wallet-badge")
async def create_child_wallet_badge(child_id: str, current_user: dict = Depends(require_staff)) -> dict:
    """Generate a wallet badge for a child. Verifies parent has staff access if child is not at a restricted location."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    # Check if child is at restricted location OR has a staff parent
    loc = await db.locations.find_one({"id": child.get("location_id", "")}, {"_id": 0}) if child.get("location_id") else None
    is_restricted = child.get("is_resident") or (loc and loc.get("is_restricted"))
    if not is_restricted:
        # Check if any parent is staff with access
        parent_ids = child.get("parent_ids", [])
        has_staff_parent = False
        for pid in parent_ids:
            parent_user = await db.users.find_one({"id": pid, "status": "active"}, {"_id": 0, "role": 1})
            if not parent_user:
                parent_member = await db.members.find_one({"id": pid}, {"_id": 0, "user_id": 1})
                if parent_member and parent_member.get("user_id"):
                    parent_user = await db.users.find_one({"id": parent_member["user_id"], "status": "active"}, {"_id": 0, "role": 1})
            if parent_user and parent_user.get("role") in ("Staff", "Director", "Manager", "Coordinator", "Leader", "HR", "Volunteer", "admin", "system_admin", "Executive Director", "Adviser"):
                has_staff_parent = True
                break
        if not has_staff_parent:
            raise HTTPException(status_code=403, detail="Child's parent must be staff with access to issue a badge")
    # Get parent details for badge
    parents = []
    for pid in (child.get("parent_ids") or []):
        p = await db.guests.find_one({"id": pid}, {"_id": 0, "name": 1, "phone": 1})
        if not p:
            p = await db.users.find_one({"id": pid}, {"_id": 0, "name": 1, "phone": 1})
        if p:
            parents.append(p)
    token = uuid.uuid4().hex[:16]
    badge_data = {
        "id": f"wbadge_{token}", "token": token,
        "member_id": child_id, "name": child.get("name", ""), "role": "Child",
        "photo_url": child.get("photo_url", ""),
        "location_name": loc.get("name") if loc else "", "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
        "qr_data": child_id, "parents": parents,
        "campus_phone": loc.get("contact_phone") if loc else "",
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    }
    await db.wallet_badges.update_one({"member_id": child_id}, {"$set": badge_data}, upsert=True)
    return badge_data


@router.get("/wallet-badge/{token}")
async def get_wallet_badge(token: str):
    """Public endpoint to view a wallet badge (no auth required)."""
    badge = await db.wallet_badges.find_one({"token": token}, {"_id": 0})
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    if badge.get("status") == "invalidated":
        raise HTTPException(status_code=403, detail="This badge has been invalidated")
    # iter345 — carry the holder's live event passes on the badge payload so a
    # kiosk/checkpoint scanning the badge alone can see they're ticketed.
    try:
        from routers.event_tickets import ticket_flags_for
        badge["event_tickets"] = await ticket_flags_for(
            [badge.get("member_id"), badge.get("subject_id"), badge.get("id")],
            badge.get("email") or "",
        )
    except Exception:
        badge["event_tickets"] = []
    return badge


# ============================================================
# AUTO-ISSUE BADGE — unified helper used by Check-in Kiosk + Security Checkpoint
# ============================================================

@router.post("/badges/auto-issue")
async def auto_issue_badge(data: dict, current_user: dict = Depends(require_staff)) -> dict:
    """Idempotent: returns an existing wallet_badge for the subject OR creates one.
    Body: { subject_kind: 'member'|'child'|'guest'|'user', subject_id }
    Returns the full badge document plus a `was_created` flag so the frontend
    can decide whether to spool the printer."""
    subject_kind = (data.get("subject_kind") or "").lower()
    subject_id = (data.get("subject_id") or "").strip()
    if not subject_kind or not subject_id:
        raise HTTPException(status_code=400, detail="subject_kind and subject_id are required")
    if subject_kind not in {"member", "child", "guest", "user"}:
        raise HTTPException(status_code=400, detail="Unsupported subject_kind")
    # Try existing badge first
    existing = await db.wallet_badges.find_one({"member_id": subject_id}, {"_id": 0})
    if existing and existing.get("status") != "invalidated":
        return {**existing, "was_created": False}
    # Resolve the subject record
    if subject_kind == "child":
        subj = await db.children.find_one({"id": subject_id}, {"_id": 0})
        role = "Child"
    elif subject_kind == "guest":
        subj = await db.guests.find_one({"id": subject_id}, {"_id": 0})
        if not subj:
            subj = await db.members.find_one({"id": subject_id, "kind": {"$in": ["guest", "parent"]}}, {"_id": 0})
        role = (subj or {}).get("role") or "Guest"
    elif subject_kind == "user":
        subj = await db.users.find_one({"id": subject_id}, {"_id": 0, "password_hash": 0, "pin_hash": 0})
        role = (subj or {}).get("role") or "Staff"
    else:
        subj = await db.members.find_one({"id": subject_id}, {"_id": 0})
        role = (subj or {}).get("role") or (subj or {}).get("membership_type") or "Member"
    if not subj:
        raise HTTPException(status_code=404, detail=f"{subject_kind} not found")
    loc_id = subj.get("location_id") or (subj.get("location_ids") or [None])[0]
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0, "name": 1, "country": 1, "country_code": 1, "contact_phone": 1}) if loc_id else None
    # Resident flag — embed on the badge payload so a checkpoint that doesn't know the
    # member can still recognise them as "lives here" via the badge itself.
    is_resident = bool(subj.get("is_resident"))
    resident_location_id = subj.get("resident_location_id") if is_resident else None
    resident_location_name = None
    if resident_location_id and resident_location_id != loc_id:
        rloc = await db.locations.find_one({"id": resident_location_id}, {"_id": 0, "name": 1})
        resident_location_name = (rloc or {}).get("name")
    elif resident_location_id and loc:
        resident_location_name = loc.get("name")
    token = uuid.uuid4().hex[:16]
    badge = {
        "id": f"wbadge_{token}",
        "token": token,
        "qr_token": token,
        "member_id": subject_id,
        "subject_kind": subject_kind,
        "name": subj.get("name") or subj.get("full_name") or "",
        "role": role,
        "title": subj.get("title", ""),
        "department": subj.get("department", ""),
        "photo_url": subj.get("photo_url", ""),
        "location_id": loc_id,
        "location_name": loc.get("name") if loc else "",
        "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
        "campus_phone": loc.get("contact_phone") if loc else "",
        "qr_data": subject_id,
        "is_resident": is_resident,
        "resident_location_id": resident_location_id,
        "resident_location_name": resident_location_name,
        "status": "active",
        "issued_via": "auto_kiosk",
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wallet_badges.update_one(
        {"member_id": subject_id},
        {"$set": badge},
        upsert=True,
    )
    await _audit(current_user["id"], "auto_issue_badge", subject_kind, subject_id, {"badge_id": badge["id"]})
    return {**badge, "was_created": True}


@router.post("/badges/auto-issue/residents")
async def auto_issue_resident_badges(data: dict, current_user: dict = Depends(require_staff)) -> dict:
    """Bulk auto-issue wallet badges for every resident of a restricted location.
    Body: { location_id }. Pass `location_id='all'` to sweep EVERY restricted location
    in the org. Includes both adult `members` AND `children` whose `resident_location_id`
    matches. Idempotent — already-badged subjects come back as `existing`."""
    location_id = (data.get("location_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id required")
    # Resolve the set of target locations
    if location_id == "all":
        loc_docs = await db.locations.find(
            {"is_restricted": True, "active": {"$ne": False}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        if not loc_docs:
            raise HTTPException(status_code=404, detail="No restricted locations found")
        target_loc_ids = [L["id"] for L in loc_docs]
        loc_name_map = {L["id"]: L.get("name") for L in loc_docs}
        loc_label = f"all {len(loc_docs)} restricted location(s)"
    else:
        loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "id": 1, "name": 1})
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found")
        target_loc_ids = [loc["id"]]
        loc_name_map = {loc["id"]: loc.get("name")}
        loc_label = loc.get("name") or location_id

    members = await db.members.find(
        {"is_resident": True, "resident_location_id": {"$in": target_loc_ids}, "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "resident_location_id": 1},
    ).to_list(20000)
    children = await db.children.find(
        {"resident_location_id": {"$in": target_loc_ids}},
        {"_id": 0, "id": 1, "resident_location_id": 1},
    ).to_list(20000)
    targets = (
        [("member", m["id"], m.get("resident_location_id")) for m in members]
        + [("child", c["id"], c.get("resident_location_id")) for c in children]
    )
    created = 0
    existing = 0
    errors = 0
    for kind, sid, rloc_id in targets:
        try:
            badge_existing = await db.wallet_badges.find_one({"member_id": sid}, {"_id": 0, "status": 1})
            if badge_existing and badge_existing.get("status") != "invalidated":
                existing += 1
                continue
            if kind == "child":
                subj = await db.children.find_one({"id": sid}, {"_id": 0})
                role = "Child"
            else:
                subj = await db.members.find_one({"id": sid}, {"_id": 0})
                role = (subj or {}).get("role") or (subj or {}).get("membership_type") or "Member"
            if not subj:
                continue
            token = uuid.uuid4().hex[:16]
            loc_name = loc_name_map.get(rloc_id) or ""
            badge = {
                "id": f"wbadge_{token}",
                "token": token,
                "qr_token": token,
                "member_id": sid,
                "subject_kind": kind,
                "name": subj.get("name") or subj.get("full_name") or "",
                "role": role,
                "photo_url": subj.get("photo_url", ""),
                "location_id": rloc_id,
                "location_name": loc_name,
                "qr_data": sid,
                "is_resident": True,
                "resident_location_id": rloc_id,
                "resident_location_name": loc_name,
                "status": "active",
                "issued_via": "bulk_resident_issue",
                "issued_by": current_user["id"],
                "issued_by_name": current_user.get("name", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.wallet_badges.update_one(
                {"member_id": sid}, {"$set": badge}, upsert=True,
            )
            created += 1
        except Exception as e:
            logger.warning(f"bulk badge issue failed for {kind} {sid}: {e}")
            errors += 1
    await _audit(
        current_user["id"], "bulk_auto_issue_badges", "location", location_id,
        {"created": created, "existing": existing, "errors": errors,
         "total_residents": len(targets), "scope": loc_label},
    )
    return {
        "location_id": location_id,
        "location_name": loc_label,
        "total_residents": len(targets),
        "created": created,
        "existing": existing,
        "errors": errors,
    }


# ========== BADGE INVALIDATION ==========

@router.post("/badges/{badge_id}/invalidate")
async def invalidate_badge(badge_id: str, current_user: dict = Depends(require_admin)) -> dict:
    """Invalidate a badge so it no longer works for access."""
    # Check wallet_badges
    badge = await db.wallet_badges.find_one({"$or": [{"id": badge_id}, {"token": badge_id}]}, {"_id": 0})
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    await db.wallet_badges.update_one(
        {"$or": [{"id": badge_id}, {"token": badge_id}]},
        {"$set": {"status": "invalidated", "invalidated_at": datetime.now(timezone.utc).isoformat(), "invalidated_by": current_user["id"]}}
    )
    await _audit(current_user["id"], "update", "badge_invalidate", badge_id)
    return {"message": "Badge invalidated", "badge_id": badge.get("id"), "member_id": badge.get("member_id")}


@router.post("/badges/{badge_id}/reactivate")
async def reactivate_badge(badge_id: str, current_user: dict = Depends(require_admin)) -> dict:
    """Reactivate a previously invalidated badge."""
    await db.wallet_badges.update_one(
        {"$or": [{"id": badge_id}, {"token": badge_id}]},
        {"$set": {"status": "active", "reactivated_at": datetime.now(timezone.utc).isoformat(), "reactivated_by": current_user["id"]}}
    )
    return {"message": "Badge reactivated"}


@router.get("/badges/list")
async def list_wallet_badges(current_user: dict = Depends(require_staff)) -> list:
    """List all issued wallet badges (different from /badges which lists badge types).
    Campus filter accepts EITHER location_id (issued-at) OR resident_location_id
    (the badge holder's home location) — needed so bulk-issued resident badges
    show up regardless of where the admin happens to be sitting today."""
    # Admin-tier sees everything; non-admin staff sees their campus + adjacent.
    if is_system_admin(current_user):
        return await db.wallet_badges.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    loc_filter = await get_campus_filter(current_user, field="location_id")
    res_filter = await get_campus_filter(current_user, field="resident_location_id")
    # Both filters are dicts like {"location_id": {"$in": [...]}}; OR them.
    if loc_filter and res_filter:
        query = {"$or": [loc_filter, res_filter]}
    else:
        query = loc_filter or res_filter or {}
    return await db.wallet_badges.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
