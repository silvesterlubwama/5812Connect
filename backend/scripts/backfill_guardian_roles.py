"""Backfill is_parent / can_pickup on existing household adults.

Before iter364 every non-child household member was one undifferentiated
"guardian". Spouses and guardians are parents by definition; everyone else
starts as authorised-pickup-only and staff can promote them.

Run: python3 scripts/backfill_guardian_roles.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
PARENT_WORDS = {"spouse", "husband", "wife", "partner", "guardian", "parent",
                "mother", "father", "mum", "mom", "dad"}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    touched = 0
    async for fam in db.families.find({"guardians.0": {"$exists": True}}, {"_id": 0, "id": 1, "guardians": 1}):
        guardians = fam["guardians"]
        changed = False
        for g in guardians:
            if "is_parent" in g and "can_pickup" in g:
                continue
            rel = (g.get("relationship") or "").strip().lower()
            locked = rel in PARENT_WORDS
            g["is_parent"] = locked
            g["can_pickup"] = True
            g["parent_locked"] = locked
            changed = True
        if changed:
            await db.families.update_one({"id": fam["id"]}, {"$set": {"guardians": guardians}})
            touched += 1
    print(f"families updated: {touched}")


asyncio.run(main())
