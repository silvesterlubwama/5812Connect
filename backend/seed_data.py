"""Initial data seeding (default admins, locations, notifications).

Extracted from server.py in iter302. `_seed_initial_data()` runs in the
background at startup so it never blocks readiness. Behaviour is byte-for-
byte the same as the original in-server implementation.
"""
import uuid
from datetime import datetime, timezone

from deps import db, logger, hash_password
from db_indexes import _ensure_indexes


async def _seed_initial_data():
    """Background-seed default admin, locations, notifications without blocking startup/readiness."""
    # Always ensure indexes (fast + idempotent)
    await _ensure_indexes()
    try:
        user_count = await db.users.count_documents({})
    except Exception as e:
        logger.warning(f"Seed skipped — DB not reachable yet: {e}")
        return
    if user_count == 0:
        logger.info("Seeding initial data...")
        admin = {"id": str(uuid.uuid4()), "name": "Admin User", "email": "admin@5812global.org", "phone": "+256 800 5812", "password_hash": hash_password("Admin@1234"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        admin2 = {"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            await db.users.insert_one(admin)
            await db.users.insert_one(admin2)
            logger.info("Admin users created")
        except Exception as e:
            logger.warning(f"Admin creation: {e}")
    try:
        uganda_admin = await db.users.find_one({"email": "admin@5812uganda.org"})
        if not uganda_admin:
            await db.users.insert_one({"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        logger.warning(f"Uganda admin seed: {e}")
    try:
        if await db.locations.count_documents({}) == 0:
            locations = [
                {"id": "loc_001", "name": "58:12 Global (Central)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Administration", "Finance", "Operations"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_002", "name": "Entebbe Campus", "code": "ETB", "type": "campus", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "country": "Uganda", "currency": "UGX", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Youth", "Education"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_003", "name": "Jinja Campus", "code": "JNJ", "type": "campus", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "country": "Uganda", "currency": "UGX", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Community", "Sports"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_004", "name": "Kampala East", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "is_venue": True, "is_bookable": True, "is_restricted": False, "departments": [], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.locations.insert_many(locations)
        if await db.notifications.count_documents({}) == 0:
            notifications = [
                {"id": "notif_001", "title": "New Member Approval", "message": "3 new member registrations are pending approval.", "type": "warning", "target_role": "admin", "link": "/members", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "notif_002", "title": "Low Stock Alert", "message": "Coffee and Eggs (Tray) are out of stock.", "type": "error", "target_role": None, "link": "/sales", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.notifications.insert_many(notifications)
    except Exception as e:
        logger.warning(f"Location/notification seeding: {e}")

    # Auto-promote silvester@lubwamas.org to system admin (non-fatal)
    try:
        silvester = await db.users.find_one({"email": "silvester@lubwamas.org"})
        if silvester:
            if silvester.get("role") != "admin":
                await db.users.update_one({"email": "silvester@lubwamas.org"}, {"$set": {"role": "admin"}})
                logger.info("Promoted silvester@lubwamas.org to admin")
        else:
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "name": "Silvester Lubwama",
                "email": "silvester@lubwamas.org",
                "phone": "",
                "password_hash": hash_password("Admin@5812"),
                "role": "admin",
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Created admin account for silvester@lubwamas.org")
    except Exception as e:
        logger.warning(f"Silvester seed: {e}")
