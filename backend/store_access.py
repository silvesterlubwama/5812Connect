"""Who belongs to which store.

A till, a kitchen and its settings belong to the people who work there. One
manager at the shop in Kampala has no business seeing the kitchen setup of the
restaurant in Jinja, so anything store-shaped asks here first (iter420).
"""
from deps import db, is_system_admin


async def store_ids_for(user: dict) -> set:
    """Every store this person is signed in to: their own assignment, the
    campus above a sub-location, and the sub-locations under it."""
    stores = set(user.get("location_ids") or [])
    if user.get("location_id"):
        stores.add(user["location_id"])
    if user.get("active_campus_id"):
        stores.add(user["active_campus_id"])
    if not stores:
        return stores
    parents = await db.locations.find(
        {"id": {"$in": list(stores)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "parent_id": 1}).to_list(100)
    for p in parents:
        if p.get("parent_id"):
            stores.add(p["parent_id"])
    subs = await db.locations.find({"parent_id": {"$in": list(stores)}}, {"_id": 0, "id": 1}).to_list(300)
    for s in subs:
        stores.add(s["id"])
    return stores


async def is_store_member(user: dict, store_id: str) -> bool:
    """A system admin keeps the keys to every door; everyone else needs to work
    at this one."""
    if not store_id:
        return True
    if is_system_admin(user):
        return True
    return store_id in await store_ids_for(user)
