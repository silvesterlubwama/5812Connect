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

PERSON_COLLECTIONS = {"member": "members", "user": "users", "guest": "guests", "child": "children"}
SPOUSE_WORDS = {"spouse", "husband", "wife", "partner"}
# Relationships that ARE a parent by definition — the toggle is locked on.
PARENT_WORDS = SPOUSE_WORDS | {"guardian", "parent", "mother", "father", "mum", "mom", "dad",
                               "step-parent", "step parent", "foster parent"}
NEW_PERSON_FIELDS = ("phone", "email", "gender", "date_of_birth", "national_id",
                     "address", "photo_url", "notes", "occupation")


def parent_flags(relationship: str, data: dict) -> dict:
    """One role + one pickup permission for every household adult.

    The old parent-vs-pickup-only split is gone: everybody recorded on a family
    is a family member, and the only question left is whether they may collect
    the children (see routers/members/family_members.py).
    """
    from routers.members.family_members import role_flags
    return role_flags(relationship, data)


async def _build_guardian(data: dict, actor: dict, pending: bool) -> dict:
    """A household adult row. When `person_id` is supplied (the type-ahead was
    used) the row carries the link, so the kiosk and every other surface can
    resolve the same profile instead of a re-typed name."""
    name = (data.get("name") or "").strip()
    person_id = (data.get("person_id") or "").strip()
    person_type = (data.get("person_type") or "").strip()
    linked = None
    if person_id and person_type in PERSON_COLLECTIONS:
        linked = await db[PERSON_COLLECTIONS[person_type]].find_one(
            {"id": person_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "photo_url": 1})
        if not linked:
            raise HTTPException(status_code=404, detail="That person could not be found any more")
        name = name or linked.get("name") or ""
    if not name:
        raise HTTPException(status_code=400, detail="Give their name, or pick them from the search")
    guardian = {
        "id": f"gdn_{str(uuid.uuid4())[:8]}",
        "name": name[:160],
        "phone": (data.get("phone") or (linked or {}).get("phone") or "")[:40],
        "email": (data.get("email") or (linked or {}).get("email") or "")[:160],
        "person_id": person_id if linked else "",
        "person_type": person_type if linked else "",
        "photo_url": data.get("photo_url") or (linked or {}).get("photo_url") or "",
        **parent_flags(data.get("role") or data.get("relationship") or "Guardian", data),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": actor.get("id"),
        "added_by_name": actor.get("name", ""),
    }
    if pending:
        guardian["approval_status"] = "pending"
        guardian["submitted_by_parent"] = True
    return guardian


async def _link_person_to_family(guardian: dict, family_id: str, actor: dict):
    """Point the linked profile at this household, and pair spouses both ways.

    The spouse link is only written when neither side already has a different
    one — a correction made by the other person or an admin is never undone by
    someone else re-adding them.
    """
    pid, ptype = guardian.get("person_id"), guardian.get("person_type")
    if not pid or ptype not in PERSON_COLLECTIONS:
        return
    coll = PERSON_COLLECTIONS[ptype]
    await db[coll].update_one({"id": pid}, {"$set": {"family_id": family_id}})
    if (guardian.get("relationship") or "").strip().lower() not in SPOUSE_WORDS:
        return
    me = actor.get("id")
    if not me or me == pid:
        return
    for a, b in ((me, pid), (pid, me)):
        for c in ("users", "members", "guests"):
            row = await db[c].find_one({"id": a}, {"_id": 0, "spouse_id": 1})
            if row is None:
                continue
            if row.get("spouse_id") and row["spouse_id"] != b:
                continue        # somebody already set a different spouse — leave it
            await db[c].update_one({"id": a}, {"$set": {
                "spouse_id": b, "spouse_linked_by": actor.get("id"),
                "spouse_linked_at": datetime.now(timezone.utc).isoformat(),
            }})


async def _create_household_person(data: dict, family_id: str, actor: dict, pending: bool) -> dict:
    """"Add new" from a household form: build the profile the app was missing.

    An adult becomes a real `members` row (so they can be searched, badged and
    checked in later); a child goes to `children`, which is where the rest of
    the app expects them.
    """
    name = (data.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Enter their full name")
    relationship = (data.get("relationship") or "Guardian").strip()
    is_child = bool(data.get("is_child")) or relationship.lower() in {"child", "son", "daughter"}
    base = {k: (str(data.get(k) or "").strip()[:300]) for k in NEW_PERSON_FIELDS}
    doc = {
        "id": f"{'chd' if is_child else 'mem'}_{str(uuid.uuid4())[:8]}",
        "name": name[:160],
        **base,
        "relationship": relationship[:60],
        "family_id": family_id,
        "location_id": actor.get("location_id") or actor.get("active_campus_id") or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": actor.get("id"),
        "created_from": "household_form",
    }
    if pending:
        doc["approval_status"] = "pending"
        doc["submitted_by_parent"] = True
    if is_child:
        doc["parent_ids"] = [actor["id"]] if actor.get("id") else []
        await db.children.insert_one(dict(doc))
        await _log_family_event(family_id, "child_submitted" if pending else "child_added", actor,
                                {"child_id": doc["id"], "child_name": doc["name"]})
        return {"person": doc, "kind": "child", "guardian": None}
    doc.update({"kind": "member", "role": "Member", "status": "pending" if pending else "active"})
    await db.members.insert_one(dict(doc))
    guardian = await _build_guardian({
        "name": doc["name"], "relationship": relationship, "phone": doc.get("phone"),
        "email": doc.get("email"), "photo_url": doc.get("photo_url"),
        "is_parent": data.get("is_parent"), "can_pickup": data.get("can_pickup"),
        "person_id": doc["id"], "person_type": "member",
    }, actor, pending=pending)
    await db.families.update_one({"id": family_id}, {"$push": {"guardians": guardian}})
    if not pending:
        await _link_person_to_family(guardian, family_id, actor)
    await _log_family_event(family_id, "guardian_submitted" if pending else "guardian_added", actor,
                            {"guardian_id": guardian["id"], "guardian_name": guardian["name"],
                             "relationship": relationship, "created_profile": doc["id"]})
    return {"person": doc, "kind": "member", "guardian": guardian}


async def _notify_admins_of_family_change(title: str, body: str, link: str):
    try:
        from routers.notifications import create_notification
        admins = await db.users.find(
            {"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}},
            {"_id": 0, "id": 1},
        ).to_list(50)
        for a in admins:
            try:
                await create_notification(title, body, a["id"], "warning", link)
            except Exception:
                pass
    except Exception:
        pass


@router.get("/families")
async def list_families(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    from deps import get_campus_filter
    conditions = []
    campus = await get_campus_filter(current_user)
    if campus:
        # A household with no campus on file must still be visible — otherwise
        # it silently vanishes from the Families tab (and looks deleted).
        conditions.append({"$or": [campus, {"location_id": {"$in": [None, ""]}},
                                   {"location_id": {"$exists": False}}]})
    if search:
        conditions.append({"$or": [
            {"family_name": {"$regex": search, "$options": "i"}},
            {"primary_contact_name": {"$regex": search, "$options": "i"}},
        ]})
    query = {"$and": conditions} if conditions else {}
    families = await db.families.find(query, {"_id": 0}).sort("family_name", 1).to_list(500)
    # Card preview: every adult in the household, however they were linked —
    # guardians[] rows plus any profile that simply carries the family_id.
    ids = [f["id"] for f in families]
    if ids:
        from routers.members.family_members import normalise_role
        extra = {fid: [] for fid in ids}
        for coll, kind in (("guests", "guest"), ("members", "member"), ("users", "user")):
            async for p in db[coll].find(
                {"family_id": {"$in": ids}},
                {"_id": 0, "id": 1, "name": 1, "family_id": 1, "relationship": 1, "phone": 1},
            ):
                extra[p["family_id"]].append(p)
        for f in families:
            rows, seen = [], set()
            for g in (f.get("guardians") or []):
                key = (g.get("person_id") or "") or (g.get("name") or "").strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"id": g.get("person_id") or g.get("id"), "name": g.get("name") or "",
                             "role": normalise_role(g.get("role") or g.get("relationship")),
                             "can_pickup": g.get("can_pickup") is not False,
                             "approval_status": g.get("approval_status") or "approved"})
            for p in extra.get(f["id"], []):
                key = p["id"] if p["id"] not in seen else (p.get("name") or "").strip().lower()
                if p["id"] in seen or key in seen or not (p.get("name") or "").strip():
                    continue
                seen.add(p["id"])
                rows.append({"id": p["id"], "name": p.get("name") or "",
                             "role": normalise_role(p.get("relationship")),
                             "can_pickup": True, "approval_status": "approved"})
            f["family_members"] = rows
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
    # The contact was chosen from the people picker — point their profile here
    # so the household resolves from either side.
    if data.primary_contact_person_id:
        await _link_person_to_family(
            {"person_id": data.primary_contact_person_id,
             "person_type": data.primary_contact_person_type},
            doc["id"], current_user)
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
    """Delete several households. Same soft-delete + unlink cascade as the
    single delete — without it, children/guests/members kept a dangling
    `family_id` and disappeared from every household view."""
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    deleted = 0
    for fid in ids:
        family = await db.families.find_one({"id": fid}, {"_id": 0})
        if not family:
            continue
        family["_deleted_from"] = "families"
        family["deleted_at"] = datetime.now(timezone.utc).isoformat()
        family["deleted_by"] = current_user["id"]
        await db.deleted_items.insert_one(family)
        await db.families.delete_one({"id": fid})
        for coll in (db.children, db.guests, db.users, db.members):
            await coll.update_many({"family_id": fid}, {"$unset": {"family_id": ""}})
        await _audit(current_user["id"], "delete", "family", fid, {"name": family.get("family_name")})
        deleted += 1
    return {"deleted": deleted}


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
        # Only now does the link go live: the profile joins the household and,
        # for a spouse, the pairing is written both ways.
        submitter = await db.users.find_one({"id": guardian.get("added_by")}, {"_id": 0, "id": 1, "name": 1}) \
            if guardian.get("added_by") else None
        await _link_person_to_family(guardian, family_id, submitter or current_user)
        if guardian.get("person_type") == "member" and guardian.get("person_id"):
            await db.members.update_one({"id": guardian["person_id"]},
                                        {"$set": {"status": "active", "approval_status": "approved"}})
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
    # A profile created purely by that submission goes with it.
    if guardian.get("person_type") == "member" and guardian.get("person_id"):
        created = await db.members.find_one({"id": guardian["person_id"]}, {"_id": 0})
        if created and created.get("created_from") == "household_form":
            created.update({"_deleted_from": "members", "deleted_at": datetime.now(timezone.utc).isoformat(),
                            "deleted_by": current_user["id"], "delete_reason": "household submission rejected"})
            await db.deleted_items.insert_one(created)
            await db.members.delete_one({"id": guardian["person_id"]})
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
async def update_family(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Partial update of the household record.

    Only the scalar fields the caller actually sent are written. The old
    version replaced the whole document from a `FamilyCreate` payload, which
    blanked `location_id` (so the family dropped out of the campus-scoped
    Families list and looked deleted) and wiped `guardians` / `parent_ids`.
    Membership is changed through the dedicated guardian/member endpoints.
    """
    allowed = {"family_name", "primary_contact_name", "primary_contact_email",
               "primary_contact_phone", "address", "notes", "location_id"}
    update = {k: v for k, v in data.items() if k in allowed and v not in (None,)}
    if not update.get("location_id"):
        update.pop("location_id", None)   # never clear the campus
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.families.update_one({"id": family_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Family not found")
    await _log_family_event(family_id, "family_updated", current_user, {"fields": list(update.keys())})
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
    # users and members carry the same pointer (iter363) — a dangling one used
    # to leave the person unable to create a new household.
    await db.users.update_many({"family_id": family_id}, {"$unset": {"family_id": ""}})
    await db.members.update_many({"family_id": family_id}, {"$unset": {"family_id": ""}})
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
    # One unified list of household adults (roles + pickup permission).
    from routers.members.family_members import member_rows
    family["family_members"] = await member_rows(family_id)
    fresh = await db.families.find_one({"id": family_id}, {"_id": 0, "guardians": 1, "parent_ids": 1})
    family["guardians"] = (fresh or {}).get("guardians") or []
    family["parent_ids"] = (fresh or {}).get("parent_ids") or []
    # One household definition for every surface (admin, portal, kiosk).
    from routers.members.household import household_members
    anchor = (parents[0] if parents else {"id": (family.get("parent_ids") or [None])[0],
                                          "name": family.get("primary_contact_name") or "",
                                          "email": family.get("primary_contact_email") or ""})
    family["household"] = await household_members({**anchor, "family_id": family_id}, include_pending=True)
    return family


@router.post("/families/{family_id}/guardians")
async def add_guardian(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a spouse/guardian to a family — linked to their profile when picked
    from the people search, or a loose contact when typed in by hand."""
    family = await db.families.find_one({"id": family_id})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    guardian = await _build_guardian(data, current_user, pending=False)
    await db.families.update_one({"id": family_id}, {"$push": {"guardians": guardian}})
    await _link_person_to_family(guardian, family_id, current_user)
    await _log_family_event(family_id, "guardian_added", current_user, {
        "guardian_id": guardian["id"], "guardian_name": guardian["name"],
        "relationship": guardian.get("relationship"), "linked": bool(guardian.get("person_id")),
    })
    return guardian


@router.post("/families/{family_id}/people")
async def admin_add_household_person(family_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """"Add new" on the admin household form — creates the profile and attaches it."""
    if not await db.families.find_one({"id": family_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Family not found")
    return await _create_household_person(data, family_id, current_user, pending=False)


@router.post("/portal/family/people")
async def portal_add_household_person(data: dict, current_user: dict = Depends(get_current_user)):
    """A member adds a brand-new spouse / guardian / child to their own household.
    Same approval queue as children — an admin vets it before it goes live."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household on file yet — create yours first")
    out = await _create_household_person(data, family_id, current_user, pending=True)
    await _notify_admins_of_family_change(
        "Family change pending review",
        f"{current_user.get('name', 'A member')} added {out['person']['name']} "
        f"({out['person'].get('relationship')}) — needs approval",
        f"/people?family={family_id}",
    )
    return out


@router.put("/families/{family_id}/guardians/{guardian_id}")
async def update_guardian(family_id: str, guardian_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a household adult — including whether they count as a parent or
    are only authorised to collect the children."""
    relationship = data.get("role") or data.get("relationship") or "Guardian"
    flags = parent_flags(relationship, data)
    await db.families.update_one(
        {"id": family_id, "guardians.id": guardian_id},
        {"$set": {
            "guardians.$.name": data.get("name", ""),
            "guardians.$.phone": data.get("phone", ""),
            "guardians.$.email": data.get("email", ""),
            **{f"guardians.$.{k}": v for k, v in flags.items()},
        }}
    )
    await _log_family_event(family_id, "guardian_updated", current_user, {"guardian_id": guardian_id})
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
    from routers.members.household import household_members
    household = await household_members({**current_user, "family_id": family["id"]}, include_pending=True)
    from routers.members.family_approvals import pending_change_map
    pending_changes = await pending_change_map(family["id"])
    # One unified family-member list — same shape the staff side gets.
    from routers.members.family_members import member_rows
    family_members = await member_rows(family["id"])
    return {"family": family, "children": children, "parents": parents,
            "family_members": family_members,
            "household": household, "pending_changes": pending_changes, "can_create": False}


@router.post("/portal/family")
async def create_my_family(data: dict, current_user: dict = Depends(get_current_user)):
    """Self-service household creation. A staff member or member who has no
    family on file can start one; they become the primary contact and are
    linked back onto their own user record so every surface resolves it."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — household setup unlocks once an admin approves you.")
    existing = await _resolve_my_family_id(current_user)
    if existing:
        family = await db.families.find_one({"id": existing}, {"_id": 0})
        if family:
            return family
        # The household was deleted but the pointer on the user survived —
        # clear it rather than handing back null and blocking setup forever.
        await db.users.update_one({"id": current_user["id"]}, {"$unset": {"family_id": ""}})
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
    """Propose an edit to a household adult on your OWN family.

    Member-side edits are reviewed before they go live (iter364) — the request
    is queued and an admin approves or rejects it.
    """
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household found")
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    family = await db.families.find_one({"id": family_id}, {"_id": 0, "guardians": 1})
    guardian = next((g for g in (family or {}).get("guardians") or [] if g.get("id") == guardian_id), None)
    if not guardian:
        raise HTTPException(status_code=404, detail="Household member not found")
    relationship = data.get("role") or data.get("relationship") or guardian.get("role") or guardian.get("relationship") or "Guardian"
    proposed = {k: (str(v or "").strip()[:160]) for k, v in data.items()
                if k in {"name", "phone", "email"}}
    flags = parent_flags(relationship, data)
    proposed.update({"role": flags["role"], "relationship": flags["relationship"],
                     "can_pickup": flags["can_pickup"]})
    from routers.members.family_approvals import create_change_request
    req = await create_change_request(family_id, "guardian", guardian_id,
                                      guardian.get("name") or "", guardian, proposed, current_user)
    if req.get("status") == "unchanged":
        return {"status": "unchanged", "message": "Nothing changed"}
    return {"status": "pending_review", "request": req,
            "message": "Sent for review — an admin approves it before it goes live"}


@router.put("/portal/family/children/{child_id}")
async def portal_update_child(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Propose an edit to one of your own children. Reviewed before it applies."""
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household found")
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval — family edits unlock once an admin approves you.")
    child = await db.children.find_one({"id": child_id, "family_id": family_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found in your household")
    allowed = {"name", "date_of_birth", "gender", "class_group", "medical_notes", "allergies"}
    proposed = {k: (str(v or "").strip()[:300]) for k, v in data.items() if k in allowed}
    from routers.members.family_approvals import create_change_request
    req = await create_change_request(family_id, "child", child_id, child.get("name") or "",
                                      child, proposed, current_user)
    if req.get("status") == "unchanged":
        return {"status": "unchanged", "message": "Nothing changed"}
    return {"status": "pending_review", "request": req,
            "message": "Sent for review — an admin approves it before it goes live"}


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
    """Member proposes an update to their own family details — reviewed first."""
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No family found")
    family = await db.families.find_one({"id": family_id}, {"_id": 0})
    allowed_fields = {"family_name", "address", "notes", "primary_contact_phone"}
    proposed = {k: v for k, v in data.items() if k in allowed_fields}
    from routers.members.family_approvals import create_change_request
    req = await create_change_request(family_id, "family", family_id,
                                      family.get("family_name") or "", family, proposed, current_user)
    if req.get("status") == "unchanged":
        return {"status": "unchanged", "message": "Nothing changed"}
    return {"status": "pending_review", "request": req,
            "message": "Sent for review — an admin approves it before it goes live"}


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
    guardian = await _build_guardian(data, current_user, pending=True)
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
    caps are exceeded so bad data can't creep in from the FE.

    Only the dimensions actually present in the body are touched. Sending
    just `child_ids` used to detach every parent from the household because
    the missing key was read as "empty list".
    """
    child_ids = data.get("child_ids")
    parent_ids = data.get("parent_ids")
    guardian_ids = data.get("guardian_ids")
    from routers.members.family_members import MAX_FAMILY_MEMBERS
    if parent_ids is not None and len(parent_ids) > MAX_FAMILY_MEMBERS:
        raise HTTPException(status_code=400, detail=f"A family can have at most {MAX_FAMILY_MEMBERS} family members. Remove somebody before adding another.")
    if guardian_ids is not None and len(guardian_ids) > MAX_FAMILY_MEMBERS:
        raise HTTPException(status_code=400, detail=f"A family can have at most {MAX_FAMILY_MEMBERS} family members.")

    if child_ids is not None:
        # Unlink only the children that are no longer on the list
        await db.children.update_many(
            {"family_id": family_id, "id": {"$nin": child_ids}}, {"$unset": {"family_id": ""}})
        if child_ids:
            await db.children.update_many({"id": {"$in": child_ids}}, {"$set": {"family_id": family_id}})

    if parent_ids is not None:
        await db.guests.update_many(
            {"family_id": family_id, "is_parent": True, "id": {"$nin": parent_ids}},
            {"$unset": {"family_id": ""}})
        if parent_ids:
            await db.guests.update_many({"id": {"$in": parent_ids}}, {"$set": {"family_id": family_id, "is_parent": True}})
            # A picked person is just as often a members/users row — writing
            # only to `guests` was why the link silently never saved.
            for coll in (db.members, db.users):
                await coll.update_many({"id": {"$in": parent_ids}}, {"$set": {"family_id": family_id}})
            await db.families.update_one({"id": family_id}, {"$set": {"parent_ids": parent_ids}})

    if guardian_ids is not None:
        await db.families.update_one({"id": family_id}, {"$set": {
            "guardian_ids": guardian_ids,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})

    # Auto-link spouses when exactly 2 parents are set so the guest profile
    # can render the "married to" chip immediately.
    if parent_ids and len(parent_ids) == 2:
        await db.guests.update_one({"id": parent_ids[0]}, {"$set": {"spouse_id": parent_ids[1]}})
        await db.guests.update_one({"id": parent_ids[1]}, {"$set": {"spouse_id": parent_ids[0]}})
    await _log_family_event(family_id, "membership_updated", current_user, {
        "children": len(child_ids or []), "parents": len(parent_ids or []),
        "guardians": len(guardian_ids or []),
    })
    return {"message": "Family members updated", "children": len(child_ids or []),
            "parents": len(parent_ids or []), "guardians": len(guardian_ids or [])}
