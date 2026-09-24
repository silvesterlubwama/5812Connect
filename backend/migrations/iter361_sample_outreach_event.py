"""Remove the iter361 test events and leave ONE real sample outreach event.

The end-to-end test creates events tagged `iter361 sample outreach` in the
description. This clears those (and anything hanging off them) and seeds a
single "Kids Club Outreach" event so the planner opens with something in it.
Idempotent.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

TEST_TAG = "iter361 sample outreach"
SAMPLE_TITLE = "Kids Club Outreach (sample)"


async def main(dry_run=False):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "5812global")]

    stale = await db.events.find({"description": TEST_TAG}, {"_id": 0, "id": 1, "title": 1}).to_list(500)
    ids = [e["id"] for e in stale]
    print(f"test events to remove: {len(ids)}")
    plans = await db.lesson_plans.find({"event_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(500)
    pos = await db.purchase_orders.find(
        {"lesson_plan_id": {"$in": [p["id"] for p in plans]}}, {"_id": 0, "id": 1, "po_number": 1}
    ).to_list(500)
    print(f"  plans: {len(plans)}  purchase orders: {[p['po_number'] for p in pos]}")

    if not dry_run and ids:
        await db.lesson_plans.delete_many({"event_id": {"$in": ids}})
        if pos:
            await db.purchase_orders.delete_many({"id": {"$in": [p["id"] for p in pos]}})
        await db.events.delete_many({"id": {"$in": ids}})

    existing = await db.events.find_one({"title": SAMPLE_TITLE}, {"_id": 0, "id": 1})
    if existing:
        print(f"sample event already present: {existing['id']}")
        return

    admin = await db.users.find_one({"role": {"$in": ["admin", "system_admin"]}}, {"_id": 0, "id": 1, "location_id": 1})
    saturday = datetime.now(timezone.utc).date()
    saturday += timedelta(days=(5 - saturday.weekday()) % 7 or 7)
    doc = {
        "id": f"evt_{uuid.uuid4().hex[:8]}",
        "title": SAMPLE_TITLE,
        "type": "outreach",
        "date": saturday.isoformat(),
        "time": "09:00",
        "end_time": "12:00",
        "location": "Community field",
        "location_id": (admin or {}).get("location_id") or "",
        "description": "Sample Saturday kids club — plan it in Lesson Planning.",
        "capacity": 120,
        "registered": 0,
        "is_public": False,
        "is_free": True,
        "visibility": "internal",
        "status": "upcoming",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": (admin or {}).get("id", ""),
    }
    if dry_run:
        print(f"would create {doc['title']} on {doc['date']}")
        return
    await db.events.insert_one(doc)
    print(f"created sample outreach event {doc['id']} on {doc['date']}")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
