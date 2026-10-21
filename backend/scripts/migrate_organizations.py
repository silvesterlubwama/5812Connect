"""One-time migration: give every existing row an organisation.

Everything currently in the database belongs to 58:12 Global (organisation #1).
Run with --dry-run first to see the row counts it will touch.

    python scripts/migrate_organizations.py --dry-run
    python scripts/migrate_organizations.py
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from org_context import UNSCOPED_COLLECTIONS  # noqa: E402

DEFAULT_NAME = "58:12 Global"
DEFAULT_SLUG = "5812global"


async def main(dry_run: bool, name: str, slug: str, hostnames: list):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    org = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if org:
        org_id = org["id"]
        print(f"Organisation '{name}' already exists -> {org_id}")
    else:
        org_id = str(uuid.uuid4())
        doc = {
            "id": org_id,
            "name": name,
            "slug": slug,
            "hostnames": hostnames,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "migration",
            "last_activity_at": datetime.now(timezone.utc).isoformat(),
        }
        if dry_run:
            print(f"[dry-run] would create organisation {name} ({slug})")
        else:
            await db.organizations.insert_one(doc)
            print(f"Created organisation {name} -> {org_id}")

    names = sorted(await db.list_collection_names())
    total = 0
    touched = []
    for coll in names:
        if coll in UNSCOPED_COLLECTIONS:
            continue
        pending = await db[coll].count_documents({"organization_id": {"$exists": False}})
        if not pending:
            continue
        total += pending
        touched.append((coll, pending))
        if not dry_run:
            await db[coll].update_many(
                {"organization_id": {"$exists": False}},
                {"$set": {"organization_id": org_id}},
            )

    for coll, n in touched:
        print(f"  {coll}: {n}")
    verb = "would stamp" if dry_run else "stamped"
    print(f"\n{verb} {total} documents across {len(touched)} collections")

    if not dry_run:
        # An index on the tenant key keeps the injected filter cheap.
        for coll, _ in touched:
            try:
                await db[coll].create_index("organization_id")
            except Exception as e:
                print(f"  index on {coll} failed: {e}")
        remaining = 0
        for coll in names:
            if coll in UNSCOPED_COLLECTIONS:
                continue
            remaining += await db[coll].count_documents({"organization_id": {"$exists": False}})
        print(f"Unstamped documents remaining: {remaining}")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--slug", default=DEFAULT_SLUG)
    ap.add_argument("--hostname", action="append", default=[])
    args = ap.parse_args()
    asyncio.run(main(args.dry_run, args.name, args.slug, args.hostname))
