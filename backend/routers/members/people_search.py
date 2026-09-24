"""One people type-ahead for every "who is this?" field in the app.

Before this, family and household forms were free-text boxes, so the same
person was typed in again and again and nothing linked back to their profile.
`/api/people/suggest` searches members, staff/user accounts, parents (guests)
and children in one call; the portal gets a deliberately thinner version so a
member can link their own spouse without being able to read the directory.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_campus_filter, get_current_user, require_role

router = APIRouter(prefix="/api", tags=["members"])

require_staff_search = require_role(5)

SOURCES = (
    ("members", "member"),
    ("users", "user"),
    ("guests", "guest"),
    ("children", "child"),
)

# Searched only when a caller explicitly asks for `customer` (the POS), so the
# family / household pickers keep returning people, not billing accounts.
OPTIONAL_SOURCES = (("customer_accounts", "customer"),)


def _rx(q):
    return {"$regex": re.escape(q), "$options": "i"}


async def _search(q: str, kinds, scope, limit: int, name_only: bool = False):
    """Name/phone/email/ID match across the people collections."""
    rx = _rx(q)
    out = []
    sources = list(SOURCES) + [s for s in OPTIONAL_SOURCES if kinds and s[1] in kinds]
    for coll, kind in sources:
        if kinds and kind not in kinds:
            continue
        query = {"name": rx} if name_only else {
            "$or": [{"name": rx}, {"email": rx}, {"phone": rx}, {"national_id": rx}]}
        if coll == "users":
            query["status"] = "active"
        clauses = [query]
        if scope:
            # Children and members can sit at a campus; global-scope staff have none.
            clauses.append({"$or": [scope, {"location_id": {"$in": ["", None]}}]})
        try:
            async for p in db[coll].find(
                {"$and": clauses} if len(clauses) > 1 else query,
                {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "role": 1,
                 "photo_url": 1, "family_id": 1, "relationship": 1, "date_of_birth": 1,
                 "gender": 1, "kind": 1, "user_id": 1},
            ).sort("name", 1).limit(limit):
                out.append({**p, "type": kind})
        except Exception:
            continue
    return out


def _dedupe(rows, limit):
    """The same human is often a members row AND a users row — show them once."""
    best, order = {}, []
    priority = {"user": 0, "member": 1, "guest": 2, "child": 3, "customer": 4}
    for r in rows:
        key = (r.get("email") or "").strip().lower() or f"name:{(r.get('name') or '').strip().lower()}"
        if not key or key == "name:":
            continue
        if key not in best:
            best[key] = r
            order.append(key)
        elif priority.get(r["type"], 9) < priority.get(best[key]["type"], 9):
            best[key] = {**r, "also": best[key]["type"]}
    return [best[k] for k in order][:limit]


@router.get("/people/suggest")
async def suggest_people(
    q: str = "",
    kinds: Optional[str] = None,        # csv of member|user|guest|child|customer
    limit: int = 12,
    current_user: dict = Depends(require_staff_search),
):
    """Staff type-ahead — enough detail to tell two people with the same name apart."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"people": [], "count": 0}
    wanted = {k.strip() for k in (kinds or "").split(",") if k.strip()}
    scope = await get_campus_filter(current_user)
    rows = _dedupe(await _search(q, wanted, scope, min(limit * 2, 50)), min(limit, 25))
    return {
        "people": [{
            "id": r.get("id"), "name": r.get("name") or "", "type": r["type"],
            "role": r.get("role") or "", "relationship": r.get("relationship") or "",
            "email": r.get("email") or "", "phone": r.get("phone") or "",
            "photo_url": r.get("photo_url"), "family_id": r.get("family_id") or "",
            "date_of_birth": r.get("date_of_birth") or "", "gender": r.get("gender") or "",
            "user_id": r.get("user_id") or "",
        } for r in rows],
        "count": len(rows),
    }


@router.get("/portal/people/suggest")
async def suggest_people_for_portal(q: str = "", current_user: dict = Depends(get_current_user)):
    """The same search for a member adding their own spouse or guardian.

    Deliberately thin: three characters minimum, matched on the NAME only (so a
    member can't probe the directory with a phone or email prefix), no contact
    detail in the response and only a handful of rows.
    """
    q = (q or "").strip()
    if len(q) < 3:
        return {"people": [], "count": 0, "hint": "Type at least 3 letters of their name"}
    if (current_user.get("status") or "").lower() == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval")
    scope = await get_campus_filter(current_user)
    rows = _dedupe(await _search(q, {"member", "user", "guest"}, scope, 12, name_only=True), 8)
    return {
        "people": [{
            "id": r.get("id"), "name": r.get("name") or "", "type": r["type"],
            "photo_url": r.get("photo_url"),
            "hint": "Staff" if r["type"] == "user" and r.get("role") not in ("Member", "Parent", "Guest")
                    else ("Child" if r["type"] == "child" else "Member"),
        } for r in rows],
        "count": len(rows),
    }
