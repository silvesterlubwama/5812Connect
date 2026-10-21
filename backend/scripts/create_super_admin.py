"""Create or promote the platform super admin.

Server-side only by design: this is the one account that can move between
organisations, so minting it should not be reachable from a browser session.

    python scripts/create_super_admin.py --email owner@example.org --name "Owner" --password '...'
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Super Admin")
    ap.add_argument("--password", required=True)
    args = ap.parse_args()
    asyncio.run(main(args.email, args.name, args.password))
