"""One list of family members — the parents-vs-guardians split is gone.

Every adult in a household is a *family member* with a role (Mother, Father,
Guardian, Grandparent, Aunt, Uncle, Sibling, Step-Parent, Other) and a single
permission: can they collect the children. Storage stays on
`families.guardians[]` so the kiosk, the approvals queue and badge issuing keep
reading the same place; legacy people who were only linked through
`families.parent_ids` or a bare `family_id` on their profile are adopted into
that array the first time a household is read, so nothing is lost.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user, require_staff

router = APIRouter(prefix="/api", tags=["members"])

FAMILY_ROLES = ["Mother", "Father", "Guardian", "Grandparent", "Aunt", "Uncle",
                "Sibling", "Step-Parent", "Other"]
# Pickup is on by default for the people who raise the child.
PICKUP_BY_DEFAULT = {"mother", "father", "guardian"}
# Roles that also make somebody a parent/caregiver of the household's children.
CAREGIVER_ROLES = {"mother", "father", "guardian", "step-parent"}
MAX_FAMILY_MEMBERS = 6

PERSON_COLLECTIONS = {"member": "members", "user": "users", "guest": "guests"}

_ROLE_ALIASES = {
    "mother": "Mother", "mum": "Mother", "mom": "Mother", "mama": "Mother",
    "father": "Father", "dad": "Father", "papa": "Father",
    "guardian": "Guardian", "parent": "Guardian", "spouse": "Guardian",
    "husband": "Guardian", "wife": "Guardian", "partner": "Guardian",
    "foster parent": "Guardian", "caregiver": "Guardian", "primary contact": "Guardian",
    "household member": "Guardian",
    "step-parent": "Step-Parent", "step parent": "Step-Parent",
    "stepfather": "Step-Parent", "stepmother": "Step-Parent",
    "grandparent": "Grandparent", "grandmother": "Grandparent", "grandfather": "Grandparent",
    "granny": "Grandparent", "grandma": "Grandparent", "grandpa": "Grandparent",
    "aunt": "Aunt", "auntie": "Aunt",
    "uncle": "Uncle",
    "sibling": "Sibling", "brother": "Sibling", "sister": "Sibling",
    "aunt/uncle": "Aunt",
}


def _norm(v) -> str:
    return (v or "").strip().lower()


def normalise_role(raw: Optional[str]) -> str:
    """Map anything ever typed into a relationship box onto one role."""
    r = _norm(raw)
    if not r:
        return "Guardian"
    for role in FAMILY_ROLES:
        if r == role.lower():
            return role
    return _ROLE_ALIASES.get(r, "Other")


def role_flags(role: str, data: Optional[dict] = None) -> dict:
    """Role + pickup permission. Pickup defaults on for mum/dad/guardian."""
    role = normalise_role(role)
    given = (data or {}).get("can_pickup")
    can_pickup = bool(given) if given is not None else (role.lower() in PICKUP_BY_DEFAULT)
    return {
        "role": role,
        # `relationship` is what every older surface (kiosk, badges, PDFs) reads.
        "relationship": role,
        # Everybody on this list is a member of the family now — the old
        # is_parent flag stays true so existing filters keep finding them.
        "is_parent": True,
        "can_pickup": can_pickup,
    }


async def find_person(person_id: str, person_type: str = "") -> Optional[dict]:
    """Resolve a profile from any of the people collections."""
    order = [PERSON_COLLECTIONS[person_type]] if person_type in PERSON_COLLECTIONS \
        else ["members", "users", "guests"]
    kinds = {v: k for k, v in PERSON_COLLECTIONS.items()}
    for coll in order:
        doc = await db[coll].find_one(
            {"id": person_id},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "photo_url": 1,
             "relationship": 1, "family_id": 1},
        )
        if doc:
            return {**doc, "person_type": kinds[coll], "collection": coll}
    return None


def _row(name: str, person_id: str, person_type: str, role: str, data: dict,
         actor: dict, pending: bool, photo_url: str = "") -> dict:
    return {
        "id": f"fmb_{uuid.uuid4().hex[:10]}",
        "name": name[:160],
        "phone": (data.get("phone") or "")[:40],
        "email": (data.get("email") or "")[:160],
        "person_id": person_id or "",
        "person_type": person_type or "",
        "photo_url": photo_url or data.get("photo_url") or "",
        **role_flags(role, data),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": (actor or {}).get("id"),
        "added_by_name": (actor or {}).get("name", ""),
        **({"approval_status": "pending", "submitted_by_parent": True} if pending else {}),
    }


async def ensure_member_rows(family_id: str) -> Optional[dict]:
    """Adopt legacy household adults into `guardians[]` and give every row a role.

    Idempotent: people already represented (same profile id or same name) are
    skipped, so calling this on every read is safe.
    """
    family = await db.families.find_one(
        {"id": family_id}, {"_id": 0, "id": 1, "guardians": 1, "parent_ids": 1})
    if not family:
        return None
    rows = list(family.get("guardians") or [])
    have_pid = {g.get("person_id") for g in rows if g.get("person_id")}
    have_name = {_norm(g.get("name")) for g in rows}
    new_rows = []

    async def adopt(p: dict, kind: str):
        if p.get("id") in have_pid or _norm(p.get("name")) in have_name or not (p.get("name") or "").strip():
            return
        have_pid.add(p["id"])
        have_name.add(_norm(p.get("name")))
        new_rows.append(_row(p.get("name") or "", p["id"], kind,
                             p.get("relationship") or "Guardian", p, {}, False,
                             p.get("photo_url") or ""))

    for coll, kind in (("guests", "guest"), ("members", "member"), ("users", "user")):
        async for p in db[coll].find(
            {"family_id": family_id},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "photo_url": 1, "relationship": 1},
        ):
            await adopt(p, kind)
    for pid in (family.get("parent_ids") or []):
        if pid in have_pid:
            continue
        found = await find_person(pid)
        if found:
            await adopt(found, found["person_type"])

    if new_rows:
        await db.families.update_one({"id": family_id}, {"$push": {"guardians": {"$each": new_rows}}})

    # Backfill a role on rows written before the roles existed.
    for g in rows:
        if g.get("role") in FAMILY_ROLES:
            continue
        flags = role_flags(g.get("role") or g.get("relationship"),
                           {"can_pickup": g.get("can_pickup")})
        await db.families.update_one(
            {"id": family_id, "guardians.id": g.get("id")},
            {"$set": {f"guardians.$.{k}": v for k, v in flags.items()}})
    return await db.families.find_one({"id": family_id}, {"_id": 0})


def _public(g: dict) -> dict:
    return {
        "id": g.get("id"),
        "person_id": g.get("person_id") or "",
        "person_type": g.get("person_type") or "",
        "name": g.get("name") or "",
        "phone": g.get("phone") or "",
        "email": g.get("email") or "",
        "photo_url": g.get("photo_url") or "",
        "role": normalise_role(g.get("role") or g.get("relationship")),
        "can_pickup": g.get("can_pickup") is not False,
        "approval_status": g.get("approval_status") or "approved",
        "added_by_name": g.get("added_by_name") or "",
    }


async def member_rows(family_id: str, include_pending: bool = True) -> list:
    """Every adult in the household, roles normalised."""
    family = await ensure_member_rows(family_id)
    if not family:
        return []
    return [_public(g) for g in (family.get("guardians") or [])
            if include_pending or (g.get("approval_status") or "approved") != "pending"]


async def _link_child_parents(person_id: str, family_id: str, role: str, child_id: Optional[str]):
    """Point the child's parent link at this adult.

    An explicit add from a child's profile always links that child; an add at
    household level only links the caregivers (mum, dad, guardian, step-parent).
    """
    if not person_id:
        return
    if child_id:
        await db.children.update_one({"id": child_id}, {"$addToSet": {"parent_ids": person_id}})
        return
    if not family_id or normalise_role(role).lower() not in CAREGIVER_ROLES:
        return
    await db.children.update_many({"family_id": family_id}, {"$addToSet": {"parent_ids": person_id}})


async def _create_profile(data: dict, family_id: str, actor: dict, pending: bool) -> dict:
    """Nobody matched the search — record the new adult as a member profile."""
    doc = {
        "id": f"mem_{uuid.uuid4().hex[:8]}",
        "name": (data.get("name") or "").strip()[:160],
        "kind": "member",
        "role": "Member",
        "status": "pending" if pending else "active",
        "family_id": family_id or "",
        "relationship": normalise_role(data.get("role") or data.get("relationship")),
        "location_id": (actor or {}).get("location_id") or (actor or {}).get("active_campus_id") or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": (actor or {}).get("id"),
        "created_from": "family_member_form",
        **{k: (str(data.get(k) or "").strip()[:300]) for k in
           ("phone", "email", "gender", "date_of_birth", "national_id", "address", "photo_url")},
    }
    if pending:
        doc.update({"approval_status": "pending", "submitted_by_parent": True})
    await db.members.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def add_family_member(family_id: Optional[str], data: dict, actor: dict,
                            pending: bool = False, child_id: Optional[str] = None) -> dict:
    """Add or link one adult — profile, household row and child link in one go."""
    role = normalise_role(data.get("role") or data.get("relationship"))
    person_id = (data.get("person_id") or "").strip()
    person_type = (data.get("person_type") or "").strip()
    name = (data.get("name") or "").strip()
    photo_url = ""

    if person_id:
        found = await find_person(person_id, person_type)
        if not found:
            raise HTTPException(status_code=404, detail="That person could not be found any more")
        name = (found.get("name") or name).strip()
        person_type = found["person_type"]
        photo_url = found.get("photo_url") or ""
        data = {**data, "phone": data.get("phone") or found.get("phone") or "",
                "email": data.get("email") or found.get("email") or ""}
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Enter their full name")

    if family_id:
        family = await ensure_member_rows(family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")
        rows = family.get("guardians") or []
        existing = next(
            (g for g in rows if (person_id and g.get("person_id") == person_id)
             or (not person_id and _norm(g.get("name")) == _norm(name))), None)
        if existing:
            flags = role_flags(role, data)
            await db.families.update_one(
                {"id": family_id, "guardians.id": existing["id"]},
                {"$set": {f"guardians.$.{k}": v for k, v in flags.items()}})
            if person_id:
                await _link_child_parents(person_id, family_id, role, child_id)
            return {"member": _public({**existing, **flags}), "created_profile": None,
                    "already_linked": True}
        if len(rows) >= MAX_FAMILY_MEMBERS:
            raise HTTPException(
                status_code=400,
                detail=f"A family can have at most {MAX_FAMILY_MEMBERS} family members. "
                       "Remove somebody before adding another.")

    created = None
    if not person_id:
        created = await _create_profile({**data, "name": name}, family_id or "", actor, pending)
        person_id, person_type = created["id"], "member"
        photo_url = created.get("photo_url") or ""

    row = _row(name, person_id, person_type, role, data, actor, pending, photo_url)

    if family_id:
        await db.families.update_one({"id": family_id}, {"$push": {"guardians": row}})
    if not pending:
        coll = PERSON_COLLECTIONS.get(person_type)
        if coll and family_id:
            await db[coll].update_one({"id": person_id}, {"$set": {"family_id": family_id}})
        if family_id and normalise_role(role).lower() in CAREGIVER_ROLES:
            await db.families.update_one({"id": family_id}, {"$addToSet": {"parent_ids": person_id}})
        await _link_child_parents(person_id, family_id or "", role, child_id)

    try:
        from routers.members.families import _log_family_event
        await _log_family_event(family_id, "family_member_submitted" if pending else "family_member_added",
                                actor, {"member_id": row["id"], "name": name, "role": role,
                                        "created_profile": created["id"] if created else None})
    except Exception:
        pass
    return {"member": _public(row), "created_profile": created, "already_linked": False}


async def remove_family_member(family_id: str, member_id: str) -> dict:
    family = await db.families.find_one({"id": family_id}, {"_id": 0, "guardians": 1})
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    row = next((g for g in (family.get("guardians") or []) if g.get("id") == member_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Family member not found")
    await db.families.update_one({"id": family_id}, {"$pull": {"guardians": {"id": member_id}}})
    pid = row.get("person_id")
    if pid:
        coll = PERSON_COLLECTIONS.get(row.get("person_type") or "")
        if coll:
            await db[coll].update_one({"id": pid, "family_id": family_id}, {"$unset": {"family_id": ""}})
        await db.families.update_one({"id": family_id}, {"$pull": {"parent_ids": pid}})
        await db.children.update_many({"family_id": family_id}, {"$pull": {"parent_ids": pid}})
    return {"removed": member_id}


# ========== STAFF ROUTES ==========

@router.get("/families/{family_id}/members")
async def list_family_members(family_id: str, current_user: dict = Depends(get_current_user)):
    """Everyone in the household — adults with roles, plus the children."""
    if not await db.families.find_one({"id": family_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Family not found")
    members = await member_rows(family_id)
    children = await db.children.find(
        {"family_id": family_id},
        {"_id": 0, "id": 1, "name": 1, "date_of_birth": 1, "gender": 1, "class_group": 1,
         "photo_url": 1, "approval_status": 1, "parent_ids": 1},
    ).sort("name", 1).to_list(100)
    return {"members": members, "children": children,
            "roles": FAMILY_ROLES, "max": MAX_FAMILY_MEMBERS}


@router.post("/families/{family_id}/members")
async def add_member_to_family(family_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Link an existing person (or create a new profile) as a family member."""
    return await add_family_member(family_id, data, current_user, pending=False,
                                   child_id=(data.get("child_id") or None))


@router.put("/families/{family_id}/members/{member_id}")
async def update_member_of_family(family_id: str, member_id: str, data: dict,
                                  current_user: dict = Depends(require_staff)):
    family = await db.families.find_one({"id": family_id}, {"_id": 0, "guardians": 1})
    row = next((g for g in (family or {}).get("guardians") or [] if g.get("id") == member_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Family member not found")
    name = (data.get("name") or row.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Enter their full name")
    update = {
        "name": name[:160],
        "phone": (data.get("phone") if data.get("phone") is not None else row.get("phone") or "")[:40],
        "email": (data.get("email") if data.get("email") is not None else row.get("email") or "")[:160],
        **role_flags(data.get("role") or data.get("relationship") or row.get("role"), data),
    }
    await db.families.update_one(
        {"id": family_id, "guardians.id": member_id},
        {"$set": {f"guardians.$.{k}": v for k, v in update.items()}})
    if row.get("person_id") and normalise_role(update["role"]).lower() in CAREGIVER_ROLES:
        await db.families.update_one({"id": family_id},
                                     {"$addToSet": {"parent_ids": row["person_id"]}})
    return {"member": _public({**row, **update})}


@router.delete("/families/{family_id}/members/{member_id}")
async def delete_member_of_family(family_id: str, member_id: str,
                                  current_user: dict = Depends(require_staff)):
    return await remove_family_member(family_id, member_id)


# ========== CHILD-SIDE ROUTES ==========

@router.get("/children/{child_id}/family-members")
async def list_child_family_members(child_id: str, current_user: dict = Depends(get_current_user)):
    """The child's family members — household adults plus anyone linked only
    through `parent_ids` (so a child with no household still shows them)."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "family_id": 1, "parent_ids": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    linked = list(child.get("parent_ids") or [])
    rows = await member_rows(child["family_id"]) if child.get("family_id") else []
    seen = {r["person_id"] for r in rows if r["person_id"]}
    for pid in linked:
        if pid in seen:
            continue
        found = await find_person(pid)
        if not found:
            continue
        seen.add(pid)
        rows.append({**_public({**found, "person_id": pid,
                                "person_type": found["person_type"],
                                "role": found.get("relationship") or "Guardian"}),
                     "id": "", "outside_household": True})
    for r in rows:
        r["linked_to_child"] = bool(r["person_id"]) and r["person_id"] in linked
    return {"members": rows, "family_id": child.get("family_id") or "",
            "roles": FAMILY_ROLES, "max": MAX_FAMILY_MEMBERS}


@router.post("/children/{child_id}/family-members")
async def add_child_family_member(child_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Add a family member from the child's profile — one call writes the
    profile, the household row and the child's parent link."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "family_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return await add_family_member(child.get("family_id") or None, data, current_user,
                                   pending=False, child_id=child_id)


@router.delete("/children/{child_id}/family-members/{person_id}")
async def unlink_child_family_member(child_id: str, person_id: str,
                                     current_user: dict = Depends(require_staff)):
    """Unlink an adult from this child. They stay in the household."""
    res = await db.children.update_one({"id": child_id}, {"$pull": {"parent_ids": person_id}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"unlinked": person_id}


# ========== PORTAL ROUTES (member self-service, needs approval) ==========

@router.get("/portal/family/members")
async def list_my_family_members(current_user: dict = Depends(get_current_user)):
    from routers.members.families import _resolve_my_family_id
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        return {"members": [], "roles": FAMILY_ROLES, "max": MAX_FAMILY_MEMBERS}
    return {"members": await member_rows(family_id), "roles": FAMILY_ROLES,
            "max": MAX_FAMILY_MEMBERS}


@router.post("/portal/family/members")
async def add_my_family_member(data: dict, current_user: dict = Depends(get_current_user)):
    """A member adds someone to their own household — queued for staff approval."""
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403,
                            detail="Your account is pending approval — family edits unlock once an admin approves you.")
    from routers.members.families import _resolve_my_family_id, _notify_admins_of_family_change
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        raise HTTPException(status_code=404, detail="No household on file yet — create yours first")
    out = await add_family_member(family_id, data, current_user, pending=True)
    await _notify_admins_of_family_change(
        "Family change pending review",
        f"{current_user.get('name', 'A member')} added {out['member']['name']} "
        f"({out['member']['role']}) — needs approval",
        f"/people?family={family_id}",
    )
    return out
