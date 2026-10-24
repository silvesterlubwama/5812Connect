"""The first organisation.

Everything in this system belongs to an organisation: the database layer refuses
any query that isn't scoped to one. A brand-new deployment has none, so every
public route — Google sign-in, passkeys, the login page's branding call — failed
with a 500, and seeding never ran because it waits for an organisation to exist.

So the very first thing a fresh database gets is organisation #1. Name and slug
can be set per deployment with ORG_NAME / ORG_SLUG; the defaults match the
original tenant so existing installs are unaffected (they already have it, and
this does nothing when any organisation is present).
"""
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from deps import raw_db
from org_context import UNSCOPED_COLLECTIONS, org_bypass

logger = logging.getLogger(__name__)


async def ensure_default_organization() -> None:
    try:
        with org_bypass():
            if await raw_db.organizations.find_one({}, {"_id": 0, "id": 1}):
                return
            name = (os.environ.get("ORG_NAME") or "58:12 Global").strip()
            slug = (os.environ.get("ORG_SLUG") or "").strip().lower()
            if not re.fullmatch(r"[a-z0-9-]{3,40}", slug or ""):
                slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:40] or "org"
            org_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            await raw_db.organizations.insert_one({
                "id": org_id,
                "name": name,
                "slug": slug,
                "status": "active",
                "is_default": True,
                "created_at": now,
                "created_by": "first-boot",
                "last_activity_at": now,
            })
        logger.info("Created the first organisation '%s' (%s)", name, slug)
        await _adopt_existing_data(org_id)
    except Exception as e:
        logger.warning("Default organisation bootstrap skipped: %s", e)


async def _adopt_existing_data(org_id: str) -> None:
    """Give rows that predate organisations their organisation.

    A deployment that ran before multi-tenancy has data but no organisation, so
    creating organisation #1 is not enough — every one of those rows is
    invisible until it carries the tenant key. Only rows that have none are
    touched, so this can never move data between organisations.

    The platform owner is deliberately left out: that account sits outside all
    organisations and is the one login allowed to move between them.
    """
    stamped = 0
    collections = 0
    with org_bypass():
        for coll in sorted(await raw_db.list_collection_names()):
            if coll in UNSCOPED_COLLECTIONS or coll == "organizations":
                continue
            query = {"organization_id": {"$exists": False}}
            if coll == "users":
                query["role"] = {"$not": {"$regex": "^super_admin$", "$options": "i"}}
            pending = await raw_db[coll].count_documents(query)
            if not pending:
                continue
            await raw_db[coll].update_many(query, {"$set": {"organization_id": org_id}})
            try:
                await raw_db[coll].create_index("organization_id")
            except Exception:
                pass
            stamped += pending
            collections += 1
    if stamped:
        logger.info("Adopted %s pre-existing documents across %s collections into organisation %s",
                    stamped, collections, org_id)
