"""Eligible staff for a restricted location's staff-pass picker.

Bug reported iter 291: staff-picker dialog was showing empty even though
staff existed at the campus. Root cause: the picker was calling
`/api/admin/users/directory` which is campus-filtered by the CALLER's
active_campus, not the location the pass is being issued for. Result:
issuing a staff pass for a sub-location whose PARENT campus you weren't
pinned to returned []. This dedicated endpoint fixes that by scoping to
the pass location's parent campus, honouring active-campus switchers on
admins/directors but never dropping to an empty set when there's obvious
staff to surface.
"""
from typing import Optional

from fastapi import APIRouter, Depends

from deps import db, get_current_user


router = APIRouter(prefix="/api/access", tags=["access"])


@router.get("/eligible-staff/{location_id}")
async def list_eligible_staff(location_id: str, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """People eligible for a staff-pass at `location_id`:
    – Users assigned to the parent campus (or the sub-location itself)
    – Admins / directors always included
    """
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    parent_campus = (loc or {}).get("parent_id") or location_id

    location_matches = {location_id, parent_campus}
    q = {
        "$or": [
            {"location_id": {"$in": list(location_matches)}},
            {"location_ids": {"$in": list(location_matches)}},
            {"active_campus_id": {"$in": list(location_matches)}},
        ]
    }
    if search:
        q = {"$and": [q, {"name": {"$regex": search, "$options": "i"}}]}

    users = await db.users.find(q, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1, "department": 1}).to_list(300)

    # Always include high-privilege users
    priv_q = {"role": {"$in": ["admin", "system_admin", "Executive Director", "Executive", "Director"]}}
    if search:
        priv_q = {"$and": [priv_q, {"name": {"$regex": search, "$options": "i"}}]}
    priv_users = await db.users.find(priv_q, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1, "department": 1}).to_list(100)

    # Same for members (staff records live in the members collection in this codebase)
    m_q = {
        "$or": [
            {"location_id": {"$in": list(location_matches)}},
            {"location_ids": {"$in": list(location_matches)}},
        ],
        "role": {"$ne": "Child"},
    }
    if search:
        m_q = {"$and": [m_q, {"name": {"$regex": search, "$options": "i"}}]}
    members = await db.members.find(m_q, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1, "department": 1}).to_list(300)

    seen = set()
    out = []
    for row in users + priv_users + members:
        rid = row.get("id")
        if rid and rid not in seen:
            seen.add(rid)
            out.append(row)
    return out
