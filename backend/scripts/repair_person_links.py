"""Repair people records whose cross-collection links point at a different
person, and re-mirror guest rows that were overwritten as a result.

A guest promoted to staff gets `guests.user_id`. When that user account was
later renamed/reused, the guest's `members` mirror inherited the wrong
identity, so editing the staff member silently renamed an unrelated person.

Run: python3 scripts/repair_person_links.py [--apply]
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
APPLY = "--apply" in sys.argv

MIRROR_FIELDS = ("name", "email", "phone", "location_id", "is_parent", "family_id")


def norm(v):
    return (v or "").strip().lower()


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    fixed_links, remirrored = 0, 0

    guests = await db.guests.find({"user_id": {"$nin": [None, ""]}}, {"_id": 0}).to_list(1000)
    for g in guests:
        user = await db.users.find_one({"id": g["user_id"]}, {"_id": 0, "id": 1, "name": 1, "email": 1})
        if not user:
            continue
        same = norm(user.get("name")) == norm(g.get("name")) or (
            norm(user.get("email")) and norm(user.get("email")) == norm(g.get("email")))
        if same:
            continue
        print(f"MISLINK guest {g['id']} '{g.get('name')}' -> user {user['id']} '{user.get('name')}'")
        if APPLY:
            await db.guests.update_one({"id": g["id"]}, {"$unset": {"user_id": "", "is_staff_guest": ""}})
            await db.members.update_one({"id": g["id"]}, {"$unset": {"user_id": ""}})
            fixed_links += 1

    # Re-mirror guest identity onto its members row where they have drifted
    async for g in db.guests.find({}, {"_id": 0}):
        mirror = await db.members.find_one({"id": g["id"]}, {"_id": 0, "name": 1})
        if not mirror or norm(mirror.get("name")) == norm(g.get("name")):
            continue
        print(f"REMIRROR {g['id']}: members '{mirror.get('name')}' -> guests '{g.get('name')}'")
        if APPLY:
            await db.members.update_one(
                {"id": g["id"]},
                {"$set": {k: g.get(k) for k in MIRROR_FIELDS if g.get(k) is not None}})
            remirrored += 1

    print(f"{'applied' if APPLY else 'dry-run'} — links cleared: {fixed_links}, re-mirrored: {remirrored}")


asyncio.run(main())
