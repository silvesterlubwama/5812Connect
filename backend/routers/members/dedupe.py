"""Duplicate people detection + merge.

Live data grew several copies of the same person across `users`, `members`,
`guests` and `children` (a guest promoted to staff, a member re-imported, a
household form typed instead of searched). Editing one copy then looked like
"the change didn't save" because another surface still read the other copy.

A person can legitimately exist in more than one collection — `guests` rows are
mirrored into `members` under the SAME id, and a user's member row may carry the
user id. Those are one identity, not duplicates, so records are clustered by
their links first and only then grouped by name.
"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, require_admin, _audit, get_campus_filter
from datetime import datetime, timezone
from typing import Optional
import re

router = APIRouter(prefix="/api", tags=["members"])

COLLECTIONS = ("users", "members", "guests", "children")
FIELDS = {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "national_id": 1,
          "role": 1, "kind": 1, "location_id": 1, "family_id": 1, "user_id": 1,
          "member_id": 1, "photo_url": 1, "created_at": 1, "status": 1,
          "date_of_birth": 1, "gender": 1, "address": 1, "department": 1}

# Where a person id is referenced. (collection, field) for scalars and arrays.
SCALAR_REFS = [
    ("checkins", "member_id"), ("residents", "member_id"), ("files", "member_id"),
    ("documents", "member_id"), ("document_requests", "member_id"),
    ("badges", "member_id"), ("wallet_badges", "member_id"),
    ("event_registrations", "member_id"), ("enrollments", "member_id"),
    ("donations", "donor_id"), ("social_cases", "subject_id"),
    ("hr_salaries", "staff_id"), ("hr_payslips", "staff_id"), ("hr_timesheets", "staff_id"),
    ("hr_leave_requests", "staff_id"), ("hr_time_off", "staff_id"),
    ("hr_contracts", "staff_id"), ("hr_doc_requests", "staff_id"),
    ("hr_employees", "user_id"),
]
ARRAY_REFS = [
    ("children", "parent_ids"), ("families", "parent_ids"), ("families", "guardian_ids"),
    ("tasks", "assignees"), ("boards", "tagged_members"), ("kanban_boards", "tagged_members"),
]
# Scalar fields copied onto the keeper when it has nothing on file
FILLABLE = ("email", "phone", "national_id", "date_of_birth", "gender", "address",
            "photo_url", "family_id", "location_id", "department", "spouse_id")
# Emails that exist only because a form demanded one — never copy these onto
# a real account during a merge.
PLACEHOLDER_EMAIL = re.compile(
    r"(@(example|test|sample|invalid|localhost)\.|^(no|none|na|n/a|noemail|test)@)", re.I)


def _norm_name(v: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def _norm(v: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9@.+]", "", (v or "").strip().lower())


async def _collect(campus: dict) -> list:
    rows = []
    # People with no campus on file must still be checked — they are exactly
    # the half-finished records that tend to be duplicates.
    scope = ({"$or": [campus, {"location_id": {"$in": [None, ""]}},
                      {"location_id": {"$exists": False}}]} if campus else {})
    for coll in COLLECTIONS:
        async for r in db[coll].find(dict(scope), FIELDS):
            if not r.get("id") or not _norm_name(r.get("name")):
                continue
            rows.append({**r, "collection": coll})
    return rows


def _cluster(rows: list) -> dict:
    """Union records that are the same identity (shared id or explicit link)."""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for r in rows:
        parent.setdefault(r["id"], r["id"])
    for r in rows:
        for linked in (r.get("user_id"), r.get("member_id")):
            if linked and linked in parent:
                union(r["id"], linked)
    clusters = {}
    for r in rows:
        clusters.setdefault(find(r["id"]), []).append(r)
    return clusters


def _signals(a: list, b: list) -> list:
    out = []
    for key in ("email", "phone", "national_id"):
        va = {_norm(r.get(key)) for r in a if _norm(r.get(key))}
        vb = {_norm(r.get(key)) for r in b if _norm(r.get(key))}
        if va & vb:
            out.append(key)
    return out


@router.get("/people/duplicates")
async def list_duplicate_people(current_user: dict = Depends(require_admin)):
    """Groups of records that look like the same person, newest signal first."""
    campus = await get_campus_filter(current_user)
    rows = await _collect(campus)
    clusters = _cluster(rows)

    by_name = {}
    for cid, recs in clusters.items():
        name = _norm_name(recs[0].get("name"))
        for r in recs:      # a cluster can carry a renamed copy; index every name
            by_name.setdefault(_norm_name(r.get("name")), {})[cid] = recs

    groups = []
    seen = set()
    for name, cl in by_name.items():
        if len(cl) < 2:
            continue
        key = tuple(sorted(cl.keys()))
        if key in seen:
            continue
        seen.add(key)
        ids = list(cl.keys())
        sig = set()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                sig.update(_signals(cl[ids[i]], cl[ids[j]]))
        identities = []
        for cid, recs in cl.items():
            primary = next((r for r in recs if r["collection"] == "users"), recs[0])
            identities.append({
                "cluster_id": cid,
                "id": primary["id"],
                "name": primary.get("name") or "",
                "email": primary.get("email") or "",
                "phone": primary.get("phone") or "",
                "role": primary.get("role") or "",
                "location_id": primary.get("location_id") or "",
                "family_id": primary.get("family_id") or "",
                "photo_url": primary.get("photo_url") or "",
                "created_at": primary.get("created_at") or "",
                "has_login": any(r["collection"] == "users" for r in recs),
                "records": [{"collection": r["collection"], "id": r["id"],
                             "name": r.get("name"), "department": r.get("department") or ""}
                            for r in recs],
            })
        identities.sort(key=lambda i: (not i["has_login"], i["created_at"]))
        groups.append({
            "name": next(iter(cl.values()))[0].get("name") or name,
            "signals": sorted(sig),
            # "exact" = same name AND a matching email / phone / national id.
            "exact": bool(sig),
            "suggested_keep": identities[0]["id"],
            "identities": identities,
        })
    groups.sort(key=lambda g: (not g["exact"], g["name"].lower()))
    return {"groups": groups, "total": len(groups),
            "exact_total": sum(1 for g in groups if g["exact"])}


async def _merge_identity(keep_id: str, drop_id: str, actor: dict, skip_fields: set = None) -> dict:
    """Fold `drop_id` into `keep_id`: fill blanks, repoint references, archive."""
    if keep_id == drop_id:
        return {"moved": 0}
    skip_fields = skip_fields or set()
    keepers = {c: await db[c].find_one({"id": keep_id}, {"_id": 0}) for c in COLLECTIONS}
    keeper = next((v for v in keepers.values() if v), None)
    if not keeper:
        raise HTTPException(status_code=404, detail="The record to keep no longer exists")
    dropped = {c: await db[c].find_one({"id": drop_id}, {"_id": 0}) for c in COLLECTIONS}
    if not any(dropped.values()):
        raise HTTPException(status_code=404, detail="The duplicate record no longer exists")

    # 1. fill blanks on the keeper from the duplicate
    fill = {}
    alt_emails = []
    for src in dropped.values():
        if not src:
            continue
        for f in FILLABLE:
            if f in skip_fields or not src.get(f) or f in fill:
                continue
            if f == "email":
                email = str(src["email"]).strip()
                if PLACEHOLDER_EMAIL.search(email):
                    continue
                # A second real address is kept as an alternate contact so the
                # surviving account's login never changes underneath the user.
                if keeper.get("email") and keeper["email"].strip().lower() != email.lower():
                    alt_emails.append(email)
                    continue
            if not keeper.get(f):
                fill[f] = src[f]
    if alt_emails:
        for coll, row in keepers.items():
            if row:
                await db[coll].update_one({"id": keep_id}, {"$addToSet": {"alt_emails": {"$each": alt_emails}}})
    if fill:
        for coll, row in keepers.items():
            if row:
                await db[coll].update_one({"id": keep_id}, {"$set": fill})

    # 2. repoint every reference
    moved = 0
    for coll, field in SCALAR_REFS:
        res = await db[coll].update_many({field: drop_id}, {"$set": {field: keep_id}})
        moved += res.modified_count
    for coll, field in ARRAY_REFS:
        res = await db[coll].update_many({field: drop_id}, {"$addToSet": {field: keep_id}})
        await db[coll].update_many({field: drop_id}, {"$pull": {field: drop_id}})
        moved += res.modified_count
    res = await db.families.update_many(
        {"guardians.person_id": drop_id}, {"$set": {"guardians.$[g].person_id": keep_id}},
        array_filters=[{"g.person_id": drop_id}])
    moved += res.modified_count
    for f in ("spouse_id", "user_id", "member_id"):
        for coll in COLLECTIONS:
            res = await db[coll].update_many({f: drop_id}, {"$set": {f: keep_id}})
            moved += res.modified_count

    # 3. archive the duplicate rows
    for coll, row in dropped.items():
        if not row:
            continue
        await db.deleted_items.insert_one({
            **row, "_deleted_from": coll, "_merged_into": keep_id,
            "deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": actor["id"],
        })
        await db[coll].delete_one({"id": drop_id})
    await _audit(actor["id"], "merge", "person", keep_id,
                 {"merged": drop_id, "references_moved": moved, "filled": list(fill.keys()),
                  "alt_emails": alt_emails})
    return {"moved": moved, "filled": list(fill.keys()), "alt_emails": alt_emails}


@router.post("/people/duplicates/merge")
async def merge_duplicate_people(data: dict, current_user: dict = Depends(require_admin)):
    """Body: {keep_id, drop_ids: [...], skip_fields?: [...]} — folds each
    duplicate into the keeper. `skip_fields` leaves those fields untouched on
    the keeper (e.g. don't inherit a placeholder email)."""
    keep_id = (data.get("keep_id") or "").strip()
    drop_ids = [d for d in (data.get("drop_ids") or []) if d and d != keep_id]
    skip_fields = set(data.get("skip_fields") or [])
    if not keep_id or not drop_ids:
        raise HTTPException(status_code=400, detail="Pick the record to keep and at least one duplicate")
    results = []
    for did in drop_ids:
        results.append({"drop_id": did, **await _merge_identity(keep_id, did, current_user, skip_fields)})
    return {"merged": len(results), "keep_id": keep_id, "details": results}


@router.post("/people/duplicates/auto-merge")
async def auto_merge_exact_duplicates(current_user: dict = Depends(require_admin)):
    """Merge only the unambiguous ones: identical name AND a shared email,
    phone or national id. Everything else stays on the review list."""
    listing = await list_duplicate_people(current_user)
    merged, groups = 0, 0
    for g in listing["groups"]:
        if not g["exact"] or len(g["identities"]) < 2:
            continue
        keep = g["suggested_keep"]
        for ident in g["identities"]:
            if ident["id"] == keep:
                continue
            await _merge_identity(keep, ident["id"], current_user)
            merged += 1
        groups += 1
    return {"groups_merged": groups, "records_merged": merged}
