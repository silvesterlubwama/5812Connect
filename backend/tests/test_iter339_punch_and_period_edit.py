"""Iter 339-340 — Punch correction log + Period-based financial edit window.

Verifies:
  1. `PUT /hr/timesheets/{id}/entries/{index}` edits a punch, records
     the correction, and re-rolls hours.
  2. `DELETE /hr/timesheets/{id}/entries/{index}` removes a punch with
     the required `reason` and re-rolls hours.
  3. `_period_open_or_admin` allows a creator to edit their donation
     any time before the fiscal period closes (old 7-day gate is gone).
"""
import os
import sys
import io
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


def test_iter339_punch_correction():
    async def _t():
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.hr import edit_timesheet_punch, delete_timesheet_punch

        ts_id = f"ts_test_{uuid.uuid4().hex[:8]}"
        staff_id = f"u_test_{uuid.uuid4().hex[:8]}"
        # Punch 1: 8h; Punch 2: 4h → total 12h
        e1_in = "2026-02-10T08:00:00+00:00"; e1_out = "2026-02-10T16:00:00+00:00"
        e2_in = "2026-02-11T08:00:00+00:00"; e2_out = "2026-02-11T12:00:00+00:00"
        await db.hr_timesheets.insert_one({
            "id": ts_id, "staff_id": staff_id, "staff_name": "Punch Test",
            "period": "2026-02", "status": "draft", "location_id": "loc_test",
            "entries": [
                {"check_in_time": e1_in, "check_out_time": e1_out, "source": "kiosk"},
                {"check_in_time": e2_in, "check_out_time": e2_out, "source": "kiosk"},
            ],
            "hours_worked": 12.0, "days_worked": 2.0,
        })
        director = {"id": "u_admin", "name": "HR Admin", "role": "admin"}
        try:
            # (1) Missing reason → 400
            from fastapi import HTTPException
            try:
                await edit_timesheet_punch(ts_id, 0, {"check_out_time": "2026-02-10T17:00:00+00:00"}, director)
                raise AssertionError("expected 400 for missing reason")
            except HTTPException as e:
                assert e.status_code == 400 and "reason" in e.detail.lower()

            # (2) Extend punch 1 to 09:00 exit → now 9h; total should be 13h
            res = await edit_timesheet_punch(
                ts_id, 0,
                {"check_out_time": "2026-02-10T17:00:00+00:00", "reason": "kiosk mis-scan"},
                director,
            )
            assert res["hours_worked"] == 13.0, f"hours={res['hours_worked']}"
            assert res["entries"][0]["corrected"] is True
            assert len(res["punch_corrections"]) == 1
            assert res["punch_corrections"][0]["reason"] == "kiosk mis-scan"

            # (3) Reject invalid ordering
            try:
                await edit_timesheet_punch(
                    ts_id, 0,
                    {"check_in_time": "2026-02-10T18:00:00+00:00", "check_out_time": "2026-02-10T17:00:00+00:00", "reason": "test"},
                    director,
                )
                raise AssertionError("expected 400 for reversed ts")
            except HTTPException as e:
                assert e.status_code == 400

            # (4) Delete punch 2 → hours drop from 13 to 9
            res = await delete_timesheet_punch(ts_id, 1, reason="ghost scan", current_user=director)
            assert res["hours_worked"] == 9.0
            assert res["days_worked"] == 1
            assert res["punch_corrections"][-1]["op"] == "delete"
        finally:
            await db.hr_timesheets.delete_one({"id": ts_id})
    asyncio.run(_t())


def test_iter340_financial_edit_gate_period_based():
    async def _t():
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.financial import _period_open_or_admin

        loc_id = f"loc_test_{uuid.uuid4().hex[:8]}"
        creator = {"id": "u_creator", "name": "Creator", "role": "Staff"}
        # Simulate a donation created 30 days ago — old 7d gate would deny.
        old_iso = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        doc_open = {
            "created_by": creator["id"], "created_at": old_iso,
            "date": (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat(),
            "location_id": loc_id, "amount": 100,
        }
        try:
            # No period locked → allowed
            ok, reason = await _period_open_or_admin(doc_open, creator)
            assert ok, f"expected allow, got: {reason}"

            # Lock the period covering that date → deny
            await db.accounting_fiscal_periods.insert_one({
                "id": f"per_{uuid.uuid4().hex[:6]}",
                "location_id": loc_id,
                "start_date": doc_open["date"][:7] + "-01",
                "end_date": doc_open["date"][:7] + "-28",
                "status": "locked",
            })
            ok, reason = await _period_open_or_admin(doc_open, creator)
            assert not ok
            assert "closed" in reason.lower() or "locked" in reason.lower()

            # Admin bypasses the lock
            admin = {"id": "u_admin", "name": "Admin", "role": "admin"}
            ok, _ = await _period_open_or_admin(doc_open, admin)
            assert ok
        finally:
            await db.accounting_fiscal_periods.delete_many({"location_id": loc_id})
    asyncio.run(_t())
