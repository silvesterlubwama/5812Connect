"""iter372 — repair events that no campus could see.

Events created before `default_creation_location` existed carry
`location_id: None`, and one points at `loc_001`, a campus that no longer
exists. `get_campus_filter` matches on campus id, so those rows matched NOTHING
and were invisible on every calendar — the user's "I added an event and it
didn't save".

Per the user's decision: file the real ones under the org's root campus and
delete the obvious test rows.

    python -m migrations.iter372_orphan_events            # apply
    python -m migrations.iter372_orphan_events --dry-run
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

# Exact ids only — never a regex delete (see the iter357 note in PRD.md).
DELETE_IDS = [
    "evt_52a1fa08",   # "Test Event"
    "evt_f5b3b5db",   # duplicate "Deliver Beans"
    "evt_4659883e",   # duplicate "Deliver Beans"
    "evt_541a6631",   # duplicate "Deliver Beans"
]
KEEP_IDS = [
    "evt_f6bf0fea",   # Magoggo Kids Christmas Party — 19 Dec
    "evt_3300554d",   # Deliver Beans to Shelter
    "evt_35f6accb",   # Director's Meeting (was pointing at the dead loc_001)
]


async def main(dry_run: bool):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    root = await db.locations.find_one({"parent_id": None}, {"_id": 0, "id": 1, "name": 1})
    if not root:
        print("No root campus found — nothing done")
        return
    print(f"Root campus: {root['name']} ({root['id']})")

    for eid in DELETE_IDS:
        ev = await db.events.find_one({"id": eid}, {"_id": 0, "title": 1, "date": 1})
        if not ev:
            print(f"  skip delete {eid} — already gone")
            continue
        print(f"  delete {eid} {ev['title']} ({ev.get('date')})")
        if not dry_run:
            await db.events.delete_one({"id": eid})

    for eid in KEEP_IDS:
        ev = await db.events.find_one({"id": eid}, {"_id": 0, "title": 1, "location_id": 1})
        if not ev:
            print(f"  skip fix {eid} — not found")
            continue
        print(f"  fix {eid} {ev['title']}: {ev.get('location_id')!r} -> {root['id']}")
        if not dry_run:
            await db.events.update_one({"id": eid}, {"$set": {"location_id": root["id"]}})

    # Anything else still unscoped (or pointing at a campus that no longer
    # exists) gets the root campus too, so it can never be invisible again.
    live = {l["id"] async for l in db.locations.find({}, {"_id": 0, "id": 1})}
    live |= {l["id"] async for l in db.sublocations.find({}, {"_id": 0, "id": 1})}
    stragglers = []
    async for ev in db.events.find({}, {"_id": 0, "id": 1, "title": 1, "location_id": 1}):
        lid = ev.get("location_id")
        if not lid or lid not in live:
            stragglers.append(ev)
    for ev in stragglers:
        print(f"  straggler {ev['id']} {ev['title']}: {ev.get('location_id')!r} -> {root['id']}")
        if not dry_run:
            await db.events.update_one({"id": ev["id"]}, {"$set": {"location_id": root["id"]}})

    print(f"{'DRY RUN — nothing written' if dry_run else 'Done'}")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
