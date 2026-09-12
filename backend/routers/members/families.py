"""Families CRUD + guardians + portal/family endpoints + family-members linking."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit
from models import FamilyCreate, ChildCreate
from datetime import datetime, timezone
from typing import Optional
import uuid


async def _log_family_event(family_id: Optional[str], action: str, actor: dict, meta: Optional[dict] = None):
    """Append a family-scoped audit record. Powers the timeline shown on
    the admin Family Approvals tab and per-family review dialog."""
    if not family_id:
        return
    try:
        doc = {
            "id": f"fah_{uuid.uuid4().hex[:10]}",
            "family_id": family_id,
            "action": action,
            "actor_id": actor.get("id"),
            "actor_name": actor.get("name", ""),
            "actor_role": actor.get("role", ""),
            "at": datetime.now(timezone.utc).isoformat(),
            "meta": meta or {},
        }
        await db.family_audit.insert_one(doc)
    except Exception:
        # audit failures never block user-facing actions
        pass


router = APIRouter(prefix="/api", tags=["members"])


@router.get("/families")
async def list_families(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    from deps import get_campus_filter
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
    if not ids or not updates:
        return {"updated": 0}
    allowed = {"location_id", "primary_contact_name", "primary_contact_phone", "primary_contact_email", "address"}
    clean = {k: v for k, v in updates.items() if k in allowed and v}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.families.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/families/bulk-delete")
async def bulk_delete_families(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    result = await db.families.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.put("/guests/bulk-update")
async def bulk_update_guests(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates:
        return {"updated": 0}
    allowed = {"location_id", "is_parent", "family_id", "status"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.guests.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/guests/bulk-delete")
async def bulk_delete_guests(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    result = await db.guests.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.get("/families/pending-approvals")
async def list_pending_family_approvals(current_user: dict = Depends(get_current_user)):
    """List parent-submitted family changes (children + guardians) that
    are awaiting admin review. Restricted to admin/director/manager roles."""
    role = (current_user.get("role") or "")
    if role not in {"admin", "system_admin", "Executive Director", "Adviser", "Director",
                    "Regional Director", "Manager", "Coordinator", "HR"}:
        raise HTTPException(status_code=403, detail="Not authorized")
    # Scope to caller's locations (admins see all)
    from deps import get_campus_filter
    campus = {} if role in {"admin", "system_admin", "Executive Director", "Adviser"} else await get_campus_filter(current_user)
    pending_children = await db.children.find(
        {"approval_status": "pending", **campus}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    # Guardians live inside families.guardians[] — pull all families that
    # have at least one pending guardian, then flatten.
    families_with_pg = await db.families.find(
        {"guardians.approval_status": "pending", **campus}, {"_id": 0}
    ).to_list(200)
    pending_guardians = []
    for fam in families_with_pg:
        for g in (fam.get("guardians") or []):
            if g.get("approval_status") == "pending":
                pending_guardians.append({
                    **g, "family_id": fam["id"], "family_name": fam.get("family_name"),
                    "location_id": fam.get("location_id"),
                })
    # Enrich children with family name for readability
    fam_ids = list({c.get("family_id") for c in pending_children if c.get("family_id")})
    fam_names = {}
    if fam_ids:
        async for f in db.families.find({"id": {"$in": fam_ids}}, {"_id": 0, "id": 1, "family_name": 1}):
            fam_names[f["id"]] = f.get("family_name", "")
    for c in pending_children:
        c["family_name"] = fam_names.get(c.get("family_id"), "")
    return {"children": pending_children, "guardians": pending_guardians}


@router.post("/families/pending-approvals/child/{child_id}/decide")
async def decide_pending_child(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Approve or reject a parent-submitted child record.
    Body: { action: 'approve' | 'reject', reason?: str }
    Approve → clears the pending flag so badges/check-ins unlock.
    Reject  → moves the record to `deleted_items` for audit."""
    role = (current_user.get("role") or "")
    if role not in {"admin", "system_admin", "Executive Director", "Adviser", "Director",
                    "Regional Director", "Manager", "Coordinator", "HR"}:
        raise HTTPException(status_code=403, detail="Not authorized")
    action = (data.get("action") or "").lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    if (child.get("approval_status") or "") != "pending":
        raise HTTPException(status_code=400, detail="Already decided")
    now = datetime.now(timezone.utc).isoformat()
    if action == "approve":
        await db.children.update_one({"id": child_id}, {"$set": {
            "approval_status": "approved",
            "approved_at": now, "approved_by": current_user["id"],
            "approved_by_name": current_user.get("name", ""),
        }})
        try:
            from routers.notifications import create_notification
            if child.get("created_by"):
                await create_notification(
                    "Family change approved",
                    f"Your addition of {child.get('name','')} has been approved.",
                    child["created_by"], "success", "/portal/family",
                )
        except Exception:
            pass
        await _audit(current_user["id"], "approve", "child", child_id, {"name": child.get("name")})
        await _log_family_event(child.get("family_id"), "child_approved", current_user, {
            "child_id": child_id, "child_name": child.get("name"),
        })
        return {"decided": "approved", "child_id": child_id}
    # Reject → soft-delete
    child["_deleted_from"] = "children"
    child["deleted_at"] = now
    child["deleted_by"] = current_user["id"]
    child["reject_reason"] = (data.get("reason") or "")[:300]
    await db.deleted_items.insert_one(child)
    await db.children.delete_one({"id": child_id})
    try:
        from routers.notifications import create_notification
        if child.get("created_by"):
            await create_notification(
                "Family change rejected",
                f"The addition of {child.get('name','')} was rejected"
                + (f": {child['reject_reason']}" if child.get("reject_reason") else "."),
                child["created_by"], "warning", "/portal/family",
            )
    except Exception:
        pass
    await _audit(current_user["id"], "reject", "child", child_id, {"name": child.get("name"), "reason": child.get("reject_reason")})
    await _log_family_event(child.get("family_id"), "child_rejected", current_user, {
        "child_id": child_id, "child_name": child.get("name"), "reason": child.get("reject_reason"),
    })
    return {"decided": "rejected", "child_id": child_id}


@router.post("/families/pending-approvals/guardian/{family_id}/{guardian_id}/decide")
async def decide_pending_guardian(family_id: str, guardian_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Approve or reject a parent-submitted guardian on a family.
    Body: { action: 'approve' | 'reject', reason?: str }"""
    role = (current_user.get("role") or "")
    if role not in {"admin", "system_admin", "Executive Director", "Adviser", "Director",
                    "Regional Director", "Manager", "Coordinator", "HR"}:
        raise HTTPException(status_code=403, detail="Not authorized")
    action = (data.get("action") or "").lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")
    family = await db.families.find_one({"id": family_id}, {"_id": 0})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    guardian = next((g for g in (family.get("guardians") or []) if g.get("id") == guardian_id), None)
    if not guardian:
        raise HTTPException(status_code=404, detail="Guardian not found")
    if (guardian.get("approval_status") or "") != "pending":
        raise HTTPException(status_code=400, detail="Already decided")
    now = datetime.now(timezone.utc).isoformat()
    if action == "approve":
        await db.families.update_one(
            {"id": family_id, "guardians.id": guardian_id},
            {"$set": {
                "guardians.$.approval_status": "approved",
                "guardians.$.approved_at": now,
                "guardians.$.approved_by": current_user["id"],
                "guardians.$.approved_by_name": current_user.get("name", ""),
            }},
        )
        try:
            from routers.notifications import create_notification
            if guardian.get("added_by"):
                await create_notification(
                    "Family change approved",
                    f"Guardian {guardian.get('name','')} has been approved.",
                    guardian["added_by"], "success", "/portal/family",
                )
        except Exception:
            pass
        await _log_family_event(family_id, "guardian_approved", current_user, {
            "guardian_id": guardian_id, "guardian_name": guardian.get("name"),
        })
        return {"decided": "approved", "family_id": family_id, "guardian_id": guardian_id}
    # Reject → pull guardian off the array
    await db.families.update_one({"id": family_id}, {"$pull": {"guardians": {"id": guardian_id}}})
    try:
        from routers.notifications import create_notification
        if guardian.get("added_by"):
            await create_notification(
                "Family change rejected",
                f"Guardian {guardian.get('name','')} was rejected"
                + (f": {data.get('reason')[:200]}" if data.get("reason") else "."),
                guardian["added_by"], "warning", "/portal/family",
            )
    except Exception:
        pass
    await _log_family_event(family_id, "guardian_rejected", current_user, {
        "guardian_id": guardian_id, "guardian_name": guardian.get("name"),
        "reason": (data.get("reason") or "")[:200],
    })
    return {"decided": "rejected", "family_id": family_id, "guardian_id": guardian_id}


@router.get("/families/{family_id}/audit")
async def get_family_audit(family_id: str, current_user: dict = Depends(get_current_user)):
    """Chronological audit trail for a family — every submission,
    approval, rejection, plus who did it and when. Powers the History
    modal on the admin Family Approvals tab.
    Restricted to staff+ so parents can't scrape other families."""
    role = (current_user.get("role") or "")
    if role in {"Guest", "guest", "Visitor", "visitor"}:
        raise HTTPException(status_code=403, detail="Not authorized")
    rows = await db.family_audit.find(
        {"family_id": family_id}, {"_id": 0}
    ).sort("at", -1).to_list(500)
    return rows


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
    # Cascade: unlink children and guests from this family
    await db.children.update_many({"family_id": family_id}, {"$unset": {"family_id": ""}})
    await db.guests.update_many({"family_id": family_id}, {"$unset": {"family_id": ""}})
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

def _esc(v: str) -> str:
    import re as _re
    return _re.escape(v or "")


async def _resolve_my_family_id(current_user: dict) -> Optional[str]:
    """Find the caller's own family.

    iter345 — this used to only look at `guests` rows flagged `is_parent`,
    so staff and plain members were told "no family found" even when one
    existed. Now every identity surface is checked: the user record itself,
    the guests row (parent flag optional), the members row, and the family
    document (primary contact / parent_ids / guardian email).
    """
    uid = current_user.get("id") or ""
    email = (current_user.get("email") or "").strip()
    name = (current_user.get("name") or "").strip()

    if current_user.get("family_id"):
        return current_user["family_id"]

    ident: list = [{"id": uid}, {"user_id": uid}] if uid else []
    if email:
        ident.append({"email": {"$regex": f"^{_esc(email)}$", "$options": "i"}})
    if name:
        ident.append({"name": {"$regex": f"^{_esc(name)}$", "$options": "i"}})

    # the live user doc may carry family_id even if the JWT payload doesn't
    if uid:
        u = await db.users.find_one({"id": uid}, {"_id": 0, "family_id": 1})
        if u and u.get("family_id"):
            return u["family_id"]

    if ident:
        for coll in (db.guests, db.members):
            row = await coll.find_one({"$or": ident, "family_id": {"$nin": [None, ""]}}, {"_id": 0, "family_id": 1})
            if row and row.get("family_id"):
                return row["family_id"]

    fam_or: list = [{"parent_ids": uid}] if uid else []
    if email:
        fam_or += [
            {"primary_contact_email": {"$regex": f"^{_esc(email)}$", "$options": "i"}},
            {"guardians.email": {"$regex": f"^{_esc(email)}$", "$options": "i"}},
        ]
    if fam_or:
        family = await db.families.find_one({"$or": fam_or}, {"_id": 0, "id": 1})
        if family:
            return family["id"]

    # Last resort: a child lists me as a parent. Households created from the
    # child's record don't always back-fill `families.parent_ids`, which left
    # parents staring at "no household on file" (iter349).
    child_or: list = [{"parent_ids": uid}] if uid else []
    member_ids = []
    if ident:
        async for row in db.members.find({"$or": ident}, {"_id": 0, "id": 1}):
            member_ids.append(row["id"])
        async for row in db.guests.find({"$or": ident}, {"_id": 0, "id": 1}):
            member_ids.append(row["id"])
    if member_ids:
        child_or.append({"parent_ids": {"$in": member_ids}})
    if child_or:
        child = await db.children.find_one(
            {"$or": child_or, "family_id": {"$nin": [None, ""]}}, {"_id": 0, "family_id": 1})
        if child:
            return child["family_id"]
    return None


@router.get("/portal/family")
async def get_my_family(current_user: dict = Depends(get_current_user)):
    """The caller's own household — works for staff, members and parents."""
    family_id = await _resolve_my_family_id(current_user)
    family = await db.families.find_one({"id": family_id}, {"_id": 0}) if family_id else None
    if not family:
        return {
            "family": None, "children": [], "parents": [],
            "can_create": (current_user.get("status") or "").lower() != "pending",
            "message": "No household on file yet — create yours to add your spouse, children and guardians.",
        }
    children = await db.children.find({"family_id": family["id"]}, {"_id": 0}).to_list(50)
    parents = await db.guests.find({"family_id": family["id"], "is_parent": True}, {"_id": 0}).to_list(20)
    # Staff/member accounts attached to the same household
    linked_users = await db.users.find(
        {"$or": [{"family_id": family["id"]}, {"id": {"$in": family.get("parent_ids") or []}}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "role": 1, "location_id": 1},
    ).to_list(20)
    for sp in linked_users:
        if not any((p.get("email") or "").lower() == (sp.get("email") or "").lower() for p in parents):
            parents.append({**sp, "is_parent": True, "is_staff": True})
    return {"family": family, "children": children, "parents": parents, "can_create": False}


@router.post("/portal/family")
async def create_my_family(data: dict, current_user: dict = Depends(get_current_user)):
    """Self-service household creation. A staff member or member who has no
    family on file can start one; they become the primary contact and are
    linked back onto their own user record so every surface resolves it."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — household setup unlocks once an admin approves you.")
    existing = await _resolve_my_family_id(current_user)
    if existing:
        return await db.families.find_one({"id": existing}, {"_id": 0})
    name = (current_user.get("name") or "").strip()
    default_name = f"{name.split(' ')[-1]} Family" if name else "My Family"
    family = {
        "id": f"fam_{str(uuid.uuid4())[:8]}",
        "family_name": (data.get("family_name") or default_name).strip()[:120],
        "primary_contact_name": name,
        "primary_contact_email": current_user.get("email", ""),
        "primary_contact_phone": (data.get("primary_contact_phone") or current_user.get("phone") or ""),
        "address": (data.get("address") or "").strip()[:300],
        "notes": "",
        "guardians": [],
        "parent_ids": [current_user["id"]],
        "location_id": current_user.get("location_id") or current_user.get("active_campus_id") or "",
        "created_by": current_user["id"],
        "created_by_self": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.families.insert_one(family)
    family.pop("_id", None)
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"family_id": family["id"]}})
    await _log_family_event(family["id"], "family_created_self", current_user, {"family_name": family["family_name"]})
    return family


@router.put("/portal/family/guardians/{guardian_id}")
async def portal_update_guardian(guardian_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Edit a household member on your OWN family only."""
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household found")
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    update = {
        f"guardians.$.{k}": (str(v or "").strip()[:160])
        for k, v in data.items() if k in {"name", "phone", "email", "relationship"}
    }
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    res = await db.families.update_one({"id": family_id, "guardians.id": guardian_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Household member not found")
    await _log_family_event(family_id, "guardian_updated", current_user, {"guardian_id": guardian_id})
    return await db.families.find_one({"id": family_id}, {"_id": 0})


@router.delete("/portal/family/guardians/{guardian_id}")
async def portal_remove_guardian(guardian_id: str, current_user: dict = Depends(get_current_user)):
    """Remove a household member from your OWN family only."""
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household found")
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    await db.families.update_one({"id": family_id}, {"$pull": {"guardians": {"id": guardian_id}}})
    await _log_family_event(family_id, "guardian_removed", current_user, {"guardian_id": guardian_id})
    return {"message": "Removed"}


@router.put("/portal/family")
async def update_my_family(data: dict, current_user: dict = Depends(get_current_user)):
    """Parent updates their own family details."""
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found")
    allowed_fields = {"family_name", "address", "notes", "primary_contact_phone"}
    update = {k: v for k, v in data.items() if k in allowed_fields}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.families.update_one({"id": family_id}, {"$set": update})
    return await db.families.find_one({"id": family_id}, {"_id": 0})


@router.post("/portal/family/children")
async def parent_add_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
    """Approved parent adds a child to their own family. New additions land
    in a pending-approval state so admins vet them before badges/access are
    granted (per iter343 guest-portal security lockdown)."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found. Contact admin.")
    child_data = data.model_dump()
    child_data["family_id"] = family_id
    doc = {
        "id": f"chd_{str(uuid.uuid4())[:8]}",
        **child_data,
        "approval_status": "pending",
        "submitted_by_parent": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.children.insert_one(doc)
    doc.pop("_id", None)
    await _log_family_event(family_id, "child_submitted", current_user, {
        "child_id": doc["id"], "child_name": doc.get("name"),
    })
    # Notify admins so they can approve the new child record
    try:
        from routers.notifications import create_notification
        admins = await db.users.find(
            {"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}},
            {"_id": 0, "id": 1},
        ).to_list(50)
        for a in admins:
            try:
                await create_notification(
                    "Family change pending review",
                    f"{current_user.get('name', 'A parent')} added child {doc.get('name','')} — needs approval",
                    a["id"], "warning", f"/people?tab=children&child={doc['id']}",
                )
            except Exception:
                pass
    except Exception:
        pass
    return doc


@router.post("/portal/family/guardians")
async def parent_add_guardian(data: dict, current_user: dict = Depends(get_current_user)):
    """Approved parent adds a guardian to their family. Guardians are
    pending-approval by default (must be vetted before pickup/access)."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found. Contact admin.")
    guardian = {
        "id": f"gdn_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "relationship": data.get("relationship", "Guardian"),
        "approval_status": "pending",
        "submitted_by_parent": True,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": current_user["id"],
    }
    await db.families.update_one({"id": family_id}, {"$push": {"guardians": guardian}})
    await _log_family_event(family_id, "guardian_submitted", current_user, {
        "guardian_id": guardian["id"], "guardian_name": guardian["name"], "relationship": guardian.get("relationship"),
    })
    try:
        from routers.notifications import create_notification
        admins = await db.users.find(
            {"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}},
            {"_id": 0, "id": 1},
        ).to_list(50)
        for a in admins:
            try:
                await create_notification(
                    "New guardian pending review",
                    f"{current_user.get('name', 'A parent')} added guardian {guardian['name']} — needs approval",
                    a["id"], "warning", f"/people?family={family_id}",
                )
            except Exception:
                pass
    except Exception:
        pass
    return guardian


# ========== FAMILY MEMBERS LINKING ==========

@router.put("/families/{family_id}/members")
async def update_family_members(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update which children and parents/guardians belong to a family.
    iter344f — enforce hard caps: max 2 parents (mum+dad) and max 6
    guardians (siblings, grandparents, emergency contacts). Refuses if
    caps are exceeded so bad data can't creep in from the FE."""
    child_ids = data.get("child_ids", [])
    parent_ids = data.get("parent_ids", [])
    guardian_ids = data.get("guardian_ids", [])
    if len(parent_ids) > 2:
        raise HTTPException(status_code=400, detail="A family can have at most 2 parents. Remove one before adding another.")
    if len(guardian_ids) > 6:
        raise HTTPException(status_code=400, detail="A family can have at most 6 guardians.")

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

    # Auto-link spouses when exactly 2 parents are set so the guest profile
    # can render the "married to" chip immediately.
    if len(parent_ids) == 2:
        await db.guests.update_one({"id": parent_ids[0]}, {"$set": {"spouse_id": parent_ids[1]}})
        await db.guests.update_one({"id": parent_ids[1]}, {"$set": {"spouse_id": parent_ids[0]}})
    return {"message": "Family members updated", "children": len(child_ids), "parents": len(parent_ids), "guardians": len(guardian_ids)}
