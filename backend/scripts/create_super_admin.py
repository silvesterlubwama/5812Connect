"""Create or promote the platform super admin.

Server-side only by design: this is the one account that can move between
organisations, so minting it should not be reachable from a browser session.

    python scripts/create_super_admin.py --email owner@example.org --name "Owner" --password '...'

To see who the platform owners are (no passwords are stored in readable form,
so this shows accounts, not secrets):

    python scripts/create_super_admin.py --list
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
from passlib.context import CryptContext  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main(email: str, name: str, password: str):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    email = email.strip().lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1})
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.users.update_one(
            {"id": existing["id"]},
            {"$set": {
                "role": "super_admin",
                "status": "active",
                "organization_id": None,
                "active_organization_id": None,
                "password_hash": pwd_context.hash(password),
                "updated_at": now,
            }},
        )
        print(f"Promoted existing account {email} to super_admin (was {existing.get('role')})")
    else:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password_hash": pwd_context.hash(password),
            "role": "super_admin",
            "status": "active",
            "organization_id": None,
            "active_organization_id": None,
            "location_id": "",
            "location_ids": [],
            "created_at": now,
        })
        print(f"Created super_admin {email}")
    client.close()


async def show():
    """Who can open more than one organisation, and where they are right now."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    owners = await db.users.find(
        {"role": {"$regex": "^super_admin$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "status": 1,
         "active_organization_id": 1, "last_seen": 1, "created_at": 1},
    ).to_list(50)
    if not owners:
        print("No platform owner exists yet. Create one with --email/--name/--password.")
    for o in owners:
        inside = "—"
        if o.get("active_organization_id"):
            org = await db.organizations.find_one(
                {"id": o["active_organization_id"]}, {"_id": 0, "name": 1})
            inside = (org or {}).get("name", o["active_organization_id"])
        print(f"{o.get('email')}")
        print(f"  name          : {o.get('name')}")
        print(f"  id            : {o.get('id')}")
        print(f"  status        : {o.get('status')}")
        print(f"  currently in  : {inside}")
        print(f"  last seen     : {o.get('last_seen') or 'not since this was added'}")
        print(f"  created       : {o.get('created_at')}")
    total = await db.users.count_documents({})
    print(f"\n{len(owners)} platform owner(s) out of {total} accounts.")
    print("Passwords are stored hashed and cannot be read back — re-run this "
          "script with --email and --password to set a new one.")
    client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show existing platform owners")
    ap.add_argument("--email")
    ap.add_argument("--name", default="Super Admin")
    ap.add_argument("--password")
    args = ap.parse_args()
    if args.list:
        asyncio.run(show())
    elif args.email and args.password:
        asyncio.run(main(args.email, args.name, args.password))
    else:
        ap.error("either --list, or both --email and --password")
