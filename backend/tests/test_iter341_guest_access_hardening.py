"""Iter 341 — guest access request hardening.

Verifies:
  1. Missing name → 400.
  2. Malformed email → 400.
  3. 6th submit from same IP inside 10 min → 429.
  4. Atomic uses-limit — 11 parallel submits against a max_uses=10 link
     never exceed 10 successes.
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


class FakeRequest:
    def __init__(self, ip="1.2.3.4"):
        class C:
            def __init__(self, host): self.host = host
        self.client = C(ip)


def test_iter341_guest_access_hardening():
    async def _t():
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        from fastapi import HTTPException
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.access import submit_guest_access_request

        token = f"tk_{uuid.uuid4().hex[:12]}"
        await db.guest_access_links.insert_one({
            "id": f"gal_{uuid.uuid4().hex[:8]}", "token": token,
            "location_id": "loc_test", "space_name": "Test",
            "uses": 0, "max_uses": 10, "requires_approval": False,
        })
        try:
            req = FakeRequest("9.9.9.1")
            # 1. Missing name
            try:
                await submit_guest_access_request(token, {"name": ""}, req)
                raise AssertionError("expected 400 for missing name")
            except HTTPException as e:
                assert e.status_code == 400

            # 2. Malformed email
            try:
                await submit_guest_access_request(token, {"name": "T Test", "email": "not-an-email"}, req)
                raise AssertionError("expected 400 for bad email")
            except HTTPException as e:
                assert e.status_code == 400

            # 3. Rate limit — 5 succeed, 6th → 429
            req2 = FakeRequest("9.9.9.2")
            for i in range(5):
                await submit_guest_access_request(token, {"name": f"Test {i} Rate"}, req2)
            try:
                await submit_guest_access_request(token, {"name": "Rate Sixth"}, req2)
                raise AssertionError("expected 429 on 6th submission")
            except HTTPException as e:
                assert e.status_code == 429

            # 4. Atomic uses guard — parallel submits against a fresh link
            token2 = f"tk_{uuid.uuid4().hex[:12]}"
            await db.guest_access_links.insert_one({
                "id": f"gal_{uuid.uuid4().hex[:8]}", "token": token2,
                "location_id": "loc_test", "space_name": "Race",
                "uses": 0, "max_uses": 3, "requires_approval": False,
            })
            # Use unique IPs so rate limit doesn't block them
            async def _one(i):
                r = FakeRequest(f"7.7.7.{i}")
                try:
                    await submit_guest_access_request(token2, {"name": f"Race {i} User"}, r)
                    return "ok"
                except HTTPException as e:
                    return e.status_code
            results = await asyncio.gather(*[_one(i) for i in range(8)])
            oks = sum(1 for r in results if r == "ok")
            assert oks == 3, f"expected exactly 3 successes, got {oks} (results={results})"
            link_after = await db.guest_access_links.find_one({"token": token2}, {"_id": 0, "uses": 1})
            assert link_after["uses"] == 3
        finally:
            await db.guest_access_links.delete_many({"token": {"$in": [token, "" ]}})
            await db.guest_access_requests.delete_many({"client_ip": {"$in": ["9.9.9.1", "9.9.9.2"] + [f"7.7.7.{i}" for i in range(8)]}})
            await db.guests.delete_many({"name": {"$regex": "^(T Test|Test \\d Rate|Rate Sixth|Race \\d User)$"}})
    asyncio.run(_t())
