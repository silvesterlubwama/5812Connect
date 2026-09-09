"""Families CRUD + guardians + portal/family endpoints + family-members linking."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit
from models import FamilyCreate, ChildCreate
from datetime import datetime, timezone
from typing import Optional
import uuid

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
    return {"decided": "rejected", "family_id": family_id, "guardian_id": guardian_id}


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

async def _resolve_my_family_id(current_user: dict) -> Optional[str]:
    """Find the logged-in parent's family_id via guests table or family record."""
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    parent_guest = await db.guests.find_one(
        {"$or": [{"email": email}, {"name": {"$regex": f"^{name}$", "$options": "i"}}], "is_parent": True},
        {"_id": 0}
    )
    if parent_guest and parent_guest.get("family_id"):
        return parent_guest["family_id"]
    family = await db.families.find_one(
        {"$or": [{"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}}, {"parent_ids": current_user["id"]}]},
        {"_id": 0}
    )
    if family:
        return family["id"]
    return None


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
    # Also include staff users marked as parents linked to this family
    staff_parents = await db.users.find(
        {"is_parent": True, "$or": [
            {"family_id": family["id"]},
            {"email": {"$in": [p.get("email") for p in parents if p.get("email")]}},
        ]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "role": 1, "location_id": 1}
    ).to_list(20)
    for sp in staff_parents:
        if not any(p.get("email") == sp.get("email") for p in parents):
            parents.append({**sp, "is_parent": True, "is_staff": True})
    return {"family": family, "children": children, "parents": parents}


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
    """Update which children and parents/guardians belong to a family"""
    child_ids = data.get("child_ids", [])
    parent_ids = data.get("parent_ids", [])
    guardian_ids = data.get("guardian_ids", [])

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

    return {"message": "Family members updated", "children": len(child_ids), "parents": len(parent_ids), "guardians": len(guardian_ids)}
