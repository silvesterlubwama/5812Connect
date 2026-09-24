"""One definition of a household, shared by the kiosk, the portal and admin.

`families` is the anchor: children live in `children` with a `family_id`, adults
can be a `users` row (staff/member accounts), a `guests` row (parents) or a
`members` row, and spouses/guardians are also listed on `families.guardians[]`.
Before this module each surface stitched that together differently — the kiosk
only ever knew about children, so a spouse could never be checked in.
"""
from datetime import datetime, timezone

from deps import db, logger

ADULT_TYPES = ("self", "guardian", "parent", "member", "user")


def _norm(v):
    return (v or "").strip().lower()


async def resolve_family_id(person: dict) -> str:
    """The household a person belongs to, however they were first recorded."""
    if person.get("family_id"):
        return person["family_id"]
    pid = person.get("id") or ""
    uid = person.get("user_id") or ""
    ids = [i for i in (pid, uid) if i]
    if not ids:
        return ""
    fam = await db.families.find_one({"parent_ids": {"$in": ids}}, {"_id": 0, "id": 1})
    if fam:
        return fam["id"]
    email = _norm(person.get("email"))
    if email:
        fam = await db.families.find_one(
            {"$or": [{"primary_contact_email": {"$regex": f"^{email}$", "$options": "i"}},
                     {"guardians.email": {"$regex": f"^{email}$", "$options": "i"}}]},
            {"_id": 0, "id": 1})
        if fam:
            return fam["id"]
    child = await db.children.find_one({"parent_ids": {"$in": ids}}, {"_id": 0, "family_id": 1})
    return (child or {}).get("family_id") or ""


async def household_members(person: dict, include_pending: bool = False) -> list:
    """Everyone in this person's household, the person first.

    Returns rows of {id, name, type, relationship, photo_url, linked} — safe for
    an anonymous kiosk (no phone, email, DOB, national ID or address).
    """
    rows = [{
        "id": person.get("id"), "name": person.get("name") or "",
        "type": "self", "relationship": "You",
        "photo_url": person.get("photo_url"), "linked": True,
    }]
    seen_ids = {person.get("id")}
    seen_names = {_norm(person.get("name"))}

    def add(row):
        if not row.get("name") and not row.get("id"):
            return
        if row.get("id") in seen_ids or _norm(row.get("name")) in seen_names:
            return
        seen_ids.add(row.get("id"))
        seen_names.add(_norm(row.get("name")))
        rows.append(row)

    family_id = await resolve_family_id(person)
    if family_id:
        family = await db.families.find_one({"id": family_id}, {"_id": 0}) or {}
        for g in family.get("guardians") or []:
            if not include_pending and (g.get("approval_status") or "approved") == "pending":
                continue
            add({
                "id": g.get("person_id") or g.get("id"),
                "name": g.get("name") or "",
                "type": "guardian",
                "relationship": g.get("relationship") or "Guardian",
                "photo_url": g.get("photo_url"),
                "linked": bool(g.get("person_id")),
                # iter364 — parents vs pickup-only, so the kiosk can show who
                # is actually allowed to collect a child.
                "is_parent": bool(g.get("is_parent")),
                "can_pickup": g.get("can_pickup") is not False,
                "guardian_id": g.get("id"),
            })
        for coll, kind, label in (("guests", "parent", "Parent"),
                                  ("users", "user", "Household member"),
                                  ("members", "member", "Household member")):
            try:
                async for p in db[coll].find(
                    {"family_id": family_id},
                    {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "relationship": 1},
                ):
                    add({"id": p.get("id"), "name": p.get("name") or "", "type": kind,
                         "relationship": p.get("relationship") or label,
                         "photo_url": p.get("photo_url"), "linked": True})
            except Exception as e:
                logger.warning(f"household scan of {coll} failed: {e}")

    child_or = []
    if family_id:
        child_or.append({"family_id": family_id})
    if person.get("id"):
        child_or.append({"parent_ids": person["id"]})
    if child_or:
        query = {"$or": child_or}
        if not include_pending:
            query["approval_status"] = {"$ne": "pending"}
        async for c in db.children.find(
            query, {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "relationship": 1},
        ):
            add({"id": c.get("id"), "name": c.get("name") or "", "type": "child",
                 "relationship": c.get("relationship") or "Child",
                 "photo_url": c.get("photo_url"), "linked": True})
    return rows


async def mark_checked_in_today(rows: list) -> list:
    """Flag who already has a check-in today so the kiosk can grey them out."""
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return rows
    today = datetime.now(timezone.utc).date().isoformat()
    already = set()
    try:
        async for ci in db.checkins.find(
            {"member_id": {"$in": ids}, "check_in_time": {"$gte": today}},
            {"_id": 0, "member_id": 1},
        ):
            already.add(ci["member_id"])
    except Exception as e:
        logger.warning(f"household check-in scan failed: {e}")
    for r in rows:
        r["checked_in_today"] = r.get("id") in already
    return rows


async def household_for_kiosk(person: dict) -> dict:
    rows = await mark_checked_in_today(await household_members(person))
    return {
        "household": rows,
        # Children are still returned on their own for older kiosk clients.
        "children": [{"id": r["id"], "name": r["name"], "photo_url": r.get("photo_url")}
                     for r in rows if r["type"] == "child"],
    }
