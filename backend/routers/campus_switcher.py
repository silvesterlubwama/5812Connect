"""Campus switcher endpoints — moved out of server.py in iter303.

Regional Directors + multi-campus users use these two endpoints to swap
their `active_campus_id`, which every campus-scoped list query filters on.
"""
from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user, is_system_admin, has_campus_switcher

router = APIRouter(prefix="/api")


@router.put("/user/active-campus")
async def set_active_campus(data: dict, current_user: dict = Depends(get_current_user)):
    """Set active campus for data filtering. Admins/EDs/Advisers can switch to any campus.
    Multi-campus users can switch among their assigned campuses."""
    campus_id = data.get("campus_id")
    if not campus_id:
        raise HTTPException(status_code=400, detail="campus_id is required")
    if has_campus_switcher(current_user) or is_system_admin(current_user):
        pass  # Can switch to any campus
    else:
        # iter 260 — Compute the allowed campus set WITHOUT collapsing across
        # siblings. Previous logic added parent campuses to `user_locs` and
        # then enumerated every non-restricted child of `user_locs`, which
        # granted a Director assigned to Haiti + Kenya access to sibling
        # campuses (Uganda, United) under the same top-level parent. Now we
        # keep two disjoint sets: `direct` (what the user was actually
        # assigned) and `parents` (the campus each of those rolls up to,
        # allowed as pin targets but NOT used to expand sibling siblings).
        direct = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            direct.add(current_user["location_id"])
        parents: set = set()
        if direct:
            parent_docs = await db.locations.find(
                {"id": {"$in": list(direct)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
                {"_id": 0, "parent_id": 1},
            ).to_list(50)
            for p in parent_docs:
                if p.get("parent_id"):
                    parents.add(p["parent_id"])
        # Expand ONLY the user's direct campuses to their sub-locations
        # (rooms/buildings). Sub-locations under parent campuses are not
        # added — those belong to sibling campuses the user was never
        # assigned to.
        subs = []
        if direct:
            subs = await db.locations.find(
                {"parent_id": {"$in": list(direct)}},
                {"_id": 0, "id": 1, "is_restricted": 1},
            ).to_list(200)
        allowed = set(direct) | parents
        for s in subs:
            if not s.get("is_restricted") or s["id"] in direct:
                allowed.add(s["id"])
        if campus_id not in allowed:
            loc = await db.locations.find_one({"id": campus_id}, {"_id": 0, "type": 1})
            if not loc:
                raise HTTPException(status_code=404, detail="Campus not found")
            raise HTTPException(status_code=403, detail="You are not assigned to this campus or its sub-locations")
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"active_campus_id": campus_id}})
    return {"active_campus_id": campus_id}


@router.put("/user/active-campus/clear")
async def clear_active_campus(current_user: dict = Depends(get_current_user)):
    """Clear campus filter to show all data."""
    await db.users.update_one({"id": current_user["id"]}, {"$unset": {"active_campus_id": ""}})
    return {"active_campus_id": None}
