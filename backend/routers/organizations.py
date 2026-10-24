"""Organisation registry — the tenant boundary.

Only a super admin can see this. Everything else in the system is locked to a
single organisation by the scoped db proxy; these routes are the one place that
legitimately reads across the registry (never across tenant *data*).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import re
from pymongo.errors import DuplicateKeyError
import uuid

from deps import (
    raw_db,
    db,
    require_super_admin,
    create_token_with_session,
    hash_password,
    org_bypass,
    org_as,
    logger,
)
from org_context import UNSCOPED_COLLECTIONS

router = APIRouter(prefix="/api")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


async def _audit(user_id, action, resource, resource_id=None, details=None):
    """Platform-level audit. Deliberately NOT the per-tenant audit_log: these
    actions happen outside any organisation, and must survive deleting one."""
    try:
        with org_bypass():
            await raw_db.org_audit_log.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "resource_id": resource_id,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.warning(f"Org audit write failed: {e}")


class OrganizationIn(BaseModel):
    name: str
    slug: str
    hostnames: List[str] = Field(default_factory=list)
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None
    owner_password: Optional[str] = None


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    hostnames: Optional[List[str]] = None


def _clean_hostnames(hostnames):
    """Accept what people actually type: 'https://New.Lubwamas.org/' → 'new.lubwamas.org'.

    Both the bare and the www form are kept, because the request hostname is
    matched literally — someone typing www.lubwamas.org must land in the same
    organisation as lubwamas.org."""
    out = []
    for h in hostnames or []:
        h = (h or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
        h = h.split("/")[0].split(":")[0]
        if not h:
            continue
        if h not in out:
            out.append(h)
        twin = h[4:] if h.startswith("www.") else f"www.{h}"
        if twin and twin not in out:
            out.append(twin)
    return out


async def _stats(org_id: str) -> dict:
    """Row counts for the super admin's list view. Each count runs pinned to
    that organisation, so this is a per-tenant tally, never a joined view."""
    out = {}
    with org_as(org_id):
        for coll, label in (("users", "users"), ("members", "members"), ("locations", "campuses")):
            try:
                out[label] = await db[coll].count_documents({})
            except Exception:
                out[label] = 0
    return out


@router.get("/organizations")
async def list_organizations(current_user: dict = Depends(require_super_admin)) -> dict:
    with org_bypass():
        orgs = await raw_db.organizations.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    for o in orgs:
        o["stats"] = await _stats(o["id"])
    return {
        "organizations": orgs,
        "active_organization_id": current_user.get("active_organization_id"),
    }


@router.post("/organizations")
async def create_organization(
    data: OrganizationIn, current_user: dict = Depends(require_super_admin)
) -> dict:
    slug = (data.slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Slug must be 3-40 characters, lowercase letters, numbers and hyphens only.",
        )
    hostnames = _clean_hostnames(data.hostnames)
    with org_bypass():
        if await raw_db.organizations.find_one({"slug": slug}):
            raise HTTPException(status_code=409, detail=f"Slug '{slug}' is already taken")
        for h in hostnames:
            clash = await raw_db.organizations.find_one({"hostnames": h})
            if clash:
                raise HTTPException(
                    status_code=409,
                    detail=f"Hostname '{h}' already belongs to {clash.get('name')}",
                )

    org_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    org = {
        "id": org_id,
        "name": data.name.strip(),
        "slug": slug,
        "status": "active",
        "created_at": now,
        "created_by": current_user.get("id"),
        "last_activity_at": now,
    }
    if hostnames:
        # Left out entirely when empty: the unique index indexes an empty array
        # as a value, so two address-less organisations would collide.
        org["hostnames"] = hostnames
    with org_bypass():
        try:
            await raw_db.organizations.insert_one(dict(org))
        except DuplicateKeyError:
            # Two owners saving the same address at the same moment — the index
            # is what actually guarantees one hostname, one organisation.
            raise HTTPException(status_code=409, detail="That web address was just claimed by another organisation")

    # Seed the new tenant: its own campus and its own administrator. Created
    # inside org context so the proxy stamps them with the new organisation.
    seeded = {}
    with org_as(org_id):
        campus_id = str(uuid.uuid4())
        await db.locations.insert_one({
            "id": campus_id,
            "name": data.name.strip(),
            "type": "campus",
            "parent_id": None,
            "created_at": now,
        })
        seeded["campus_id"] = campus_id
        if data.owner_email and data.owner_password:
            admin_id = str(uuid.uuid4())
            await db.users.insert_one({
                "id": admin_id,
                "name": (data.owner_name or data.owner_email).strip(),
                "email": data.owner_email.strip().lower(),
                "password_hash": hash_password(data.owner_password),
                "role": "admin",
                "status": "active",
                "location_id": campus_id,
                "location_ids": [campus_id],
                "active_campus_id": campus_id,
                "created_at": now,
            })
            seeded["admin_id"] = admin_id
    await _audit(current_user.get("id"), "create", "organization", org_id, {"name": org["name"], "slug": slug})
    org.pop("_id", None)
    return {"organization": org, "seeded": seeded}


@router.put("/organizations/{org_id}")
async def update_organization(
    org_id: str, data: OrganizationUpdate, current_user: dict = Depends(require_super_admin)
) -> dict:
    updates = {}
    if data.name is not None:
        updates["name"] = data.name.strip()
    if data.hostnames is not None:
        hostnames = _clean_hostnames(data.hostnames)
        with org_bypass():
            for h in hostnames:
                clash = await raw_db.organizations.find_one({"hostnames": h, "id": {"$ne": org_id}})
                if clash:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Hostname '{h}' already belongs to {clash.get('name')}",
                    )
        updates["hostnames"] = hostnames
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    mutation: dict = {}
    if updates.get("hostnames") == []:
        mutation["$unset"] = {"hostnames": ""}
        updates = {k: v for k, v in updates.items() if k != "hostnames"}
        if updates:
            mutation["$set"] = updates
        updates["hostnames"] = []
    else:
        mutation["$set"] = updates
    with org_bypass():
        try:
            res = await raw_db.organizations.update_one({"id": org_id}, mutation)
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="That web address was just claimed by another organisation")
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await _audit(current_user.get("id"), "update", "organization", org_id, updates)
    return {"message": "Updated", "updates": updates}


@router.post("/organizations/{org_id}/status")
async def set_status(
    org_id: str, data: dict, current_user: dict = Depends(require_super_admin)
) -> dict:
    """Suspend or reactivate. Suspension blocks every login for that tenant on
    the next request — data is retained untouched."""
    status_value = (data.get("status") or "").lower()
    if status_value not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'suspended'")
    patch = {"status": status_value}
    if status_value == "suspended":
        patch["suspended_at"] = datetime.now(timezone.utc).isoformat()
        patch["suspend_reason"] = (data.get("reason") or "").strip()[:300]
    else:
        patch["suspended_at"] = None
        patch["suspend_reason"] = ""
    with org_bypass():
        res = await raw_db.organizations.update_one({"id": org_id}, {"$set": patch})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Organisation not found")
        # Pull the rug on live sessions so suspension is immediate.
        if status_value == "suspended":
            member_ids = await raw_db.users.distinct("id", {"organization_id": org_id})
            if member_ids:
                await raw_db.sessions.update_many(
                    {"user_id": {"$in": member_ids}}, {"$set": {"revoked": True}}
                )
    await _audit(current_user.get("id"), "update", "organization", org_id, patch)
    return {"message": f"Organisation {status_value}", "status": status_value}


@router.get("/organizations/{org_id}/export")
async def export_organization(
    org_id: str, current_user: dict = Depends(require_super_admin)
) -> dict:
    """Full JSON dump of one tenant — taken before a delete, and the same shape
    that /organizations/import accepts back."""
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail="Organisation not found")
        names = await raw_db.list_collection_names()
        data = {}
        total = 0
        for name in names:
            if name in UNSCOPED_COLLECTIONS:
                continue
            rows = await raw_db[name].find({"organization_id": org_id}, {"_id": 0}).to_list(100000)
            if rows:
                data[name] = rows
                total += len(rows)
    await _audit(current_user.get("id"), "export", "organization", org_id, {"documents": total})
    return {
        "format": "5812-org-export/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "organization": org,
        "collections": data,
        "document_count": total,
    }


@router.post("/organizations/import")
async def import_organization(payload: dict, current_user: dict = Depends(require_super_admin)) -> dict:
    """Restore an exported tenant. A fresh organisation id is minted and every
    row is re-stamped, so an import can never collide with a live tenant."""
    if payload.get("format") != "5812-org-export/v1":
        raise HTTPException(status_code=400, detail="Unrecognised export format")
    src_org = payload.get("organization") or {}
    collections = payload.get("collections") or {}
    if not src_org.get("name"):
        raise HTTPException(status_code=400, detail="Export is missing its organisation record")

    new_id = str(uuid.uuid4())
    slug = (src_org.get("slug") or "imported")[:30]

    # Record ids are globally unique, so a restore cannot reuse them while the
    # original still exists. Mint a fresh id for every row and rewrite any
    # field that referenced an old one, so internal links survive the copy.
    id_map = {}
    for rows in collections.values():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                id_map[r["id"]] = str(uuid.uuid4())

    def _remap(value):
        if isinstance(value, str):
            return id_map.get(value, value)
        if isinstance(value, list):
            return [_remap(v) for v in value]
        if isinstance(value, dict):
            return {k: _remap(v) for k, v in value.items()}
        return value

    with org_bypass():
        n = 0
        base_slug = slug
        while await raw_db.organizations.find_one({"slug": slug}):
            n += 1
            slug = f"{base_slug}-{n}"
        org = {
            # is_default decides which organisation answers public pages on an
            # unclaimed hostname — a restored copy must never inherit it.
            **{k: v for k, v in src_org.items()
               if k not in ("id", "_id", "hostnames", "slug", "is_default")},
            "id": new_id,
            "slug": slug,
            "hostnames": [],
            "status": "active",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "imported_by": current_user.get("id"),
        }
        await raw_db.organizations.insert_one(dict(org))

        restored = 0
        for name, rows in collections.items():
            if name in UNSCOPED_COLLECTIONS or not isinstance(rows, list) or not rows:
                continue
            docs = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                d = {k: _remap(v) for k, v in r.items() if k != "_id"}
                d["organization_id"] = new_id
                docs.append(d)
            if docs:
                try:
                    await raw_db[name].insert_many(docs, ordered=False)
                    restored += len(docs)
                except Exception as e:
                    logger.warning(f"Import: {name} partially failed: {e}")
    await _audit(current_user.get("id"), "import", "organization", new_id, {"documents": restored, "slug": slug})
    org.pop("_id", None)
    return {"organization": org, "restored_documents": restored}


@router.delete("/organizations/{org_id}")
async def delete_organization(
    org_id: str, confirm: str = "", current_user: dict = Depends(require_super_admin)
) -> dict:
    """Hard delete. Requires the slug as confirmation, and refuses unless the
    organisation is suspended first — so nobody deletes a live tenant by
    mistake. Export first; this does not keep a copy."""
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail="Organisation not found")
        if org.get("status") != "suspended":
            raise HTTPException(
                status_code=400,
                detail="Suspend the organisation before deleting it, so you can be sure nobody is still working in it.",
            )
        if confirm != org.get("slug"):
            raise HTTPException(
                status_code=400,
                detail=f"Type the slug '{org.get('slug')}' to confirm deletion",
            )
        names = await raw_db.list_collection_names()
        removed = 0
        for name in names:
            if name in UNSCOPED_COLLECTIONS:
                continue
            res = await raw_db[name].delete_many({"organization_id": org_id})
            removed += res.deleted_count
        await raw_db.organizations.delete_one({"id": org_id})
    await _audit(current_user.get("id"), "delete", "organization", org_id,
                 {"name": org.get("name"), "documents": removed})
    return {"message": f"Deleted {org.get('name')}", "documents_removed": removed}


@router.post("/organizations/{org_id}/enter")
async def enter_organization(
    org_id: str, request: Request, current_user: dict = Depends(require_super_admin)
) -> dict:
    """Switch the super admin into one organisation. Never additive — entering
    one leaves the previous one entirely."""
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail="Organisation not found")
        if org.get("status") == "suspended":
            raise HTTPException(status_code=403, detail=f"{org.get('name')} is suspended")
        await raw_db.users.update_one(
            {"id": current_user["id"]}, {"$set": {"active_organization_id": org_id}}
        )
    # Fresh token so the previous organisation's session can't be replayed.
    token = await create_token_with_session(current_user["id"], request)
    await _audit(current_user.get("id"), "enter", "organization", org_id, {"name": org.get("name")})
    return {"token": token, "organization": org}


@router.post("/organizations/exit")
async def exit_organization(current_user: dict = Depends(require_super_admin)) -> dict:
    with org_bypass():
        await raw_db.users.update_one(
            {"id": current_user["id"]}, {"$set": {"active_organization_id": None}}
        )
    return {"message": "Left organisation"}


# ─── Setup tools: moving a person between organisations ─────────────────────
# A person's *account* can move; their records stay with the organisation that
# owns them. Anything else would mean copying tenant data across the boundary.

@router.get("/organizations/{org_id}/people")
async def list_org_people(
    org_id: str, q: Optional[str] = None, current_user: dict = Depends(require_super_admin)
) -> dict:
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    query: dict = {}
    if q:
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query = {"$or": [{"name": rx}, {"email": rx}]}
    with org_as(org_id):
        rows = await db.users.find(
            query, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "status": 1}
        ).sort("name", 1).to_list(500)
    return {"organization": {"id": org_id, "name": org.get("name")}, "people": rows}


class TransferPerson(BaseModel):
    user_id: str
    from_org_id: str
    to_org_id: str


@router.post("/organizations/transfer-person")
async def transfer_person(
    payload: TransferPerson, current_user: dict = Depends(require_super_admin)
) -> dict:
    """Move one login from one organisation to another.

    Only the account moves. Their history (members, tasks, payslips…) belongs to
    the organisation it was created in and stays there — copying it would break
    the isolation the whole system is built on."""
    if payload.from_org_id == payload.to_org_id:
        raise HTTPException(status_code=400, detail="Pick a different organisation to move them to")
    with org_bypass():
        target = await raw_db.organizations.find_one({"id": payload.to_org_id}, {"_id": 0, "name": 1, "status": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Destination organisation not found")
        if target.get("status") == "suspended":
            raise HTTPException(status_code=400, detail=f"{target.get('name')} is suspended")
        user = await raw_db.users.find_one(
            {"id": payload.user_id, "organization_id": payload.from_org_id},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
        )
        if not user:
            raise HTTPException(status_code=404, detail="That person is not in the organisation you picked")
        if (user.get("role") or "").lower() == "super_admin":
            raise HTTPException(status_code=400, detail="The platform owner is not inside any organisation")
        email = (user.get("email") or "").strip()
        clash = await raw_db.users.find_one(
            {"organization_id": payload.to_org_id,
             "email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        ) if email else None
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"{target.get('name')} already has someone using {user.get('email')}",
            )
        await raw_db.users.update_one(
            {"id": payload.user_id},
            {"$set": {
                "organization_id": payload.to_org_id,
                "location_id": None,
                "location_ids": [],
                "active_campus_id": None,
                "moved_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        # Their old session would still be pinned to the previous organisation.
        await raw_db.sessions.update_many({"user_id": payload.user_id}, {"$set": {"revoked": True}})
    await _audit(current_user.get("id"), "transfer", "person", payload.user_id, {
        "name": user.get("name"), "email": user.get("email"),
        "from": payload.from_org_id, "to": payload.to_org_id,
    })
    return {
        "message": f"{user.get('name') or 'That person'} now signs in under {target.get('name')}. "
                   "Their previous records stayed with the organisation that owns them, and they "
                   "need to choose a campus on their next sign-in.",
        "user_id": payload.user_id,
    }


# ─── Owner activity log ─────────────────────────────────────────────────────

@router.get("/organizations/activity")
async def organization_activity(
    org_id: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    current_user: dict = Depends(require_super_admin),
) -> dict:
    """What the owner did and what admins changed, across every organisation.

    Two sources: the platform log (entering, creating, suspending, deleting an
    organisation — kept outside any tenant so it survives deletion) and each
    tenant's own admin audit trail. Rows are merged newest-first and tagged with
    the organisation they belong to; it is a history, not a live combined view
    of anyone's data."""
    limit = max(1, min(limit, 300))
    with org_bypass():
        orgs = await raw_db.organizations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        names = {o["id"]: o.get("name") or o["id"] for o in orgs}

        platform_q: dict = {}
        if org_id:
            platform_q = {"$or": [{"resource_id": org_id}, {"details.to": org_id}, {"details.from": org_id}]}
        # Fetch enough of each source to fill the requested page after merging.
        window = limit + skip
        platform = await raw_db.org_audit_log.find(platform_q, {"_id": 0}).sort(
            "timestamp", -1).to_list(window)

        # audit_log only ever receives admin-level writes (staff/user changes,
        # settings, campuses, money corrections), so no action filter is needed.
        tenant_q: dict = {}
        if org_id:
            tenant_q["organization_id"] = org_id
        tenant = await raw_db.audit_log.find(tenant_q, {"_id": 0}).sort(
            "timestamp", -1).to_list(window)
        # The real size of the history, not just what this page fetched.
        total = (await raw_db.org_audit_log.count_documents(platform_q)
                 + await raw_db.audit_log.count_documents(tenant_q))

    rows = []
    for r in platform:
        d = r.get("details") or {}
        # A move names two organisations; show where they went. Rows about an
        # organisation that has since been deleted keep the name recorded at
        # the time, so the history still reads properly.
        row_org = (r.get("resource_id") if r.get("resource") == "organization"
                   else d.get("to") or d.get("from"))
        row_name = names.get(row_org) or d.get("name") or d.get("slug") or ("(deleted organisation)" if row_org else "")
        if r.get("resource") == "person" and d.get("to"):
            row_name = f"{names.get(d.get('from'), 'another organisation')} → {names.get(d.get('to'), 'another organisation')}"
        rows.append({
            "id": r.get("id"),
            "scope": "platform",
            "organization_id": row_org,
            "organization_name": row_name,
            "user_id": r.get("user_id"),
            "user_name": r.get("details", {}).get("actor_name") or "",
            "action": r.get("action"),
            "resource": r.get("resource"),
            "resource_id": r.get("resource_id"),
            "details": r.get("details") or {},
            "timestamp": r.get("timestamp"),
        })
    for r in tenant:
        rows.append({
            "id": r.get("id"),
            "scope": "organization",
            "organization_id": r.get("organization_id"),
            "organization_name": names.get(r.get("organization_id")) or "(deleted organisation)",
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name") or "",
            "action": r.get("action"),
            "resource": r.get("resource"),
            "resource_id": r.get("resource_id"),
            "details": r.get("details") or {},
            "timestamp": r.get("timestamp"),
        })
    rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    page = rows[skip:skip + limit]
    # Fill in who did it, for rows that only stored an id.
    missing = {r["user_id"] for r in page if r["user_id"] and not r["user_name"]}
    if missing:
        with org_bypass():
            people = await raw_db.users.find(
                {"id": {"$in": list(missing)}}, {"_id": 0, "id": 1, "name": 1}
            ).to_list(len(missing))
        who = {p["id"]: p.get("name") or "" for p in people}
        for r in page:
            if not r["user_name"]:
                r["user_name"] = who.get(r["user_id"], "")
    return {
        "activity": page,
        "total": total,
        "organizations": [{"id": o["id"], "name": names[o["id"]]} for o in orgs],
    }
