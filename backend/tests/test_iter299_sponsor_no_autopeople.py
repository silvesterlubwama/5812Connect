"""Iter 299 — Verify external sponsors are NOT auto-added to People.

`_upsert_external_sponsor_guest` used to insert a new `db.guests` row for
every manual sponsor, polluting the People directory. Now it only
backfills existing directory rows and otherwise leaves the sponsor
purely on the case's `sponsor_manual` object.
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


async def _no_match_stays_off_people(db, _upsert):
    email = f"sponsor_{uuid.uuid4().hex[:8]}@example.test"
    before = await db.guests.count_documents({"email": email})
    assert before == 0
    gid = await _upsert({"name": "External Sponsor", "email": email, "phone": "+15550000000"}, {"id": "u_admin", "name": "Admin"})
    assert gid is None, f"expected no guest created, got {gid}"
    after = await db.guests.count_documents({"email": email})
    assert after == 0, f"guest row created for non-matching sponsor (count={after})"


async def _matching_user_returns_none(db, _upsert):
    email = f"user_{uuid.uuid4().hex[:8]}@example.test"
    user_id = f"u_{uuid.uuid4().hex[:8]}"
    await db.users.insert_one({"id": user_id, "email": email, "name": "Real User", "role": "Staff"})
    try:
        gid = await _upsert({"name": "Real User", "email": email}, {"id": "u_admin", "name": "Admin"})
        assert gid is None, "matching user should short-circuit — no guest linked"
        # Nothing new created for that email
        cnt = await db.guests.count_documents({"email": email})
        assert cnt == 0, "no guest row should have been created"
    finally:
        await db.users.delete_one({"id": user_id})


async def _matching_guest_gets_backfilled(db, _upsert):
    email = f"guest_{uuid.uuid4().hex[:8]}@example.test"
    guest_id = f"gst_{uuid.uuid4().hex[:8]}"
    await db.guests.insert_one({
        "id": guest_id, "name": "Existing Guest", "email": email,
        "kind": "parent",
    })
    try:
        gid = await _upsert(
            {"name": "Existing Guest", "email": email, "phone": "+15550001111", "notes": "sponsor for X"},
            {"id": "u_admin", "name": "Admin"},
        )
        assert gid == guest_id, f"expected existing guest id back, got {gid}"
        fresh = await db.guests.find_one({"id": guest_id}, {"_id": 0})
        # Kind preserved (was parent, must NOT flip to external_sponsor)
        assert fresh["kind"] == "parent"
        # is_sponsor flag flipped on so downstream reports see it
        assert fresh.get("is_sponsor") is True
        assert fresh.get("phone") == "+15550001111"
        assert fresh.get("notes") == "sponsor for X"
    finally:
        await db.guests.delete_one({"id": guest_id})


def test_iter299_sponsor_never_auto_added_to_people():
    async def _run():
        # Rebind deps.db to this loop's motor client so co-running with
        # other iter tests doesn't hit "Event loop is closed" against a
        # client that was bound to a previously-closed loop.
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.social_work import _upsert_external_sponsor_guest
        await _no_match_stays_off_people(db, _upsert_external_sponsor_guest)
        await _matching_user_returns_none(db, _upsert_external_sponsor_guest)
        await _matching_guest_gets_backfilled(db, _upsert_external_sponsor_guest)
    asyncio.run(_run())
