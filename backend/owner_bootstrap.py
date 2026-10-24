"""First-boot platform owner.

Every deployment needs exactly one account that can move between organisations.
It cannot be created through the app — the database layer refuses to write
`role: super_admin` on any request path — so a fresh server would otherwise have
no way in at all.

On startup, if no owner exists yet and `OWNER_EMAIL` + `OWNER_PASSWORD` are set,
one is created from those values. It runs once: an owner that already exists is
never touched, so this is not a standing password reset and the value in .env
cannot be used to take over a live server later. Changing the password
afterwards is `scripts/create_super_admin.py`.

The password belongs in each server's own `.env` (chmod 600), never in the
repository or an image — anything published is a key to every installation.
"""
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from deps import raw_db, hash_password
from org_context import org_bypass

logger = logging.getLogger(__name__)


async def ensure_platform_owner() -> None:
    email = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    password = os.environ.get("OWNER_PASSWORD") or ""
    if not email or not password:
        return
    try:
        with org_bypass():
            existing_owner = await raw_db.users.find_one(
                {"role": {"$regex": "^super_admin$", "$options": "i"}}, {"_id": 0, "id": 1}
            )
            if existing_owner:
                return
            clash = await raw_db.users.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1})
            if clash:
                # An ordinary account already owns this address. Promoting it
                # would pull it out of its organisation and strip its campus
                # access, which is not something to do silently at boot.
                logger.warning(
                    "OWNER_EMAIL %s already belongs to a %s account — not promoting it. "
                    "Use scripts/create_super_admin.py if that is really what you want.",
                    email, clash.get("role"),
                )
                return
            await raw_db.users.insert_one({
                "id": str(uuid4()),
                "name": os.environ.get("OWNER_NAME") or "Platform Owner",
                "email": email,
                "password_hash": hash_password(password),
                "role": "super_admin",
                "status": "active",
                "organization_id": None,
                "active_organization_id": None,
                "location_id": "",
                "location_ids": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "first-boot",
            })
        logger.info("Platform owner %s created on first boot", email)
    except Exception as e:
        logger.warning("Platform owner bootstrap skipped: %s", e)
