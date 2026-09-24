"""One-off repair: families whose location_id was blanked by the old
full-overwrite PUT /families/{id} become invisible in the campus-scoped
Families tab. Backfill the campus from the household's own people.

Run: python3 scripts/repair_family_locations.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    blank = {"$in": [None, ""]}
    families = await db.families.find(
        {"$or": [{"location_id": blank}, {"location_id": {"$exists": False}}]}, {"_id": 0}
    ).to_list(2000)
    fixed = 0
    for fam in families:
        loc = ""
        for uid in fam.get("parent_ids") or []:
            for coll in (db.users, db.members, db.guests):
                row = await coll.find_one({"id": uid, "location_id": {"$nin": [None, ""]}},
                                          {"_id": 0, "location_id": 1})
                if row:
                    loc = row["location_id"]
                    break
            if loc:
                break
        if not loc:
            for coll in (db.guests, db.members, db.users, db.children):
                row = await coll.find_one({"family_id": fam["id"], "location_id": {"$nin": [None, ""]}},
                                          {"_id": 0, "location_id": 1})
                if row:
                    loc = row["location_id"]
                    break
        if loc:
            await db.families.update_one({"id": fam["id"]}, {"$set": {"location_id": loc}})
            fixed += 1
            print(f"  {fam['id']} {fam.get('family_name')} -> {loc}")
    print(f"families missing campus: {len(families)}; backfilled: {fixed}")


asyncio.run(main())
