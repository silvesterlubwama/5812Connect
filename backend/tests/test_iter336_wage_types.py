"""Iter 336 — Per-salary wage types (hourly / daily / weekly / biweekly).

Even though everyone gets paid on the same biweekly schedule, individual
staff can now have their base amount interpreted as hourly / daily /
weekly / biweekly / monthly. The classic example:

  Daily rate 60,000 UGX × 10 working days in a biweekly period = 600,000.

This test verifies:
  1. `_compute_base_gross` returns 600,000 for the daily case above.
  2. `_compute_base_gross` returns hourly_rate × hours (with 8h/day fallback).
  3. Monthly-salary path stays byte-identical to the old
     `monthly_base × proration_factor` behaviour.
  4. `POST /hr/payslips/preview` picks up the wage_type and reports the
     right gross without persisting.
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


def test_iter336_compute_base_gross_daily():
    from routers.hr import _compute_base_gross
    sal = {"wage_type": "daily", "daily_rate": 60_000, "base_salary": 0,
           "pay_frequency": "biweekly", "currency": "UGX"}
    period = "2026-09-16_2026-09-29 (W38-W39)"
    gross, details = _compute_base_gross(sal, period, working_days=10, days_worked=10, hours_worked=None)
    assert gross == 600_000.0, f"expected 600000, got {gross}"
    assert "60,000" in details and "10" in details


def test_iter336_compute_base_gross_hourly():
    from routers.hr import _compute_base_gross
    sal = {"wage_type": "hourly", "hourly_rate": 7_500, "base_salary": 0,
           "pay_frequency": "biweekly", "currency": "UGX"}
    period = "2026-09-16_2026-09-29 (W38-W39)"
    # explicit 80 hours worked
    gross, _ = _compute_base_gross(sal, period, working_days=10, days_worked=10, hours_worked=80)
    assert gross == 600_000.0
    # fallback: days × 8h
    gross2, _ = _compute_base_gross(sal, period, working_days=10, days_worked=10, hours_worked=None)
    assert gross2 == 600_000.0


def test_iter336_compute_base_gross_weekly():
    from routers.hr import _compute_base_gross
    sal = {"wage_type": "weekly", "weekly_rate": 300_000, "base_salary": 0,
           "pay_frequency": "biweekly"}
    period = "2026-09-16_2026-09-29 (W38-W39)"  # 14 days → 2 weeks
    gross, _ = _compute_base_gross(sal, period, working_days=10, days_worked=10, hours_worked=None)
    assert gross == 600_000.0


def test_iter336_compute_base_gross_biweekly_rate():
    from routers.hr import _compute_base_gross
    sal = {"wage_type": "biweekly", "biweekly_rate": 600_000, "base_salary": 0,
           "pay_frequency": "biweekly"}
    period = "2026-09-16_2026-09-29 (W38-W39)"  # 14 days → 1 biweekly cheque
    gross, _ = _compute_base_gross(sal, period, working_days=10, days_worked=10, hours_worked=None)
    assert gross == 600_000.0


def test_iter336_compute_base_gross_monthly_unchanged():
    from routers.hr import _compute_base_gross, _proration_factor
    sal = {"wage_type": "salary", "base_salary": 600_000,
           "pay_frequency": "biweekly"}
    period = "2026-09-16_2026-09-29 (W38-W39)"
    gross, _ = _compute_base_gross(sal, period, working_days=10, days_worked=None, hours_worked=None)
    # Must still be 12/26 proration of 600k.
    assert gross == round(600_000 * _proration_factor("biweekly"), 2) == 276_923.08


def test_iter336_preview_reports_wage_type():
    async def _t():
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.hr import preview_payslips

        loc_id = f"loc_test_{uuid.uuid4().hex[:8]}"
        staff_id = f"u_test_{uuid.uuid4().hex[:8]}"
        sal_id = f"sal_{uuid.uuid4().hex[:8]}"
        await db.users.insert_one({
            "id": staff_id, "name": "Daily Test", "role": "Staff",
            "location_id": loc_id, "email": f"{staff_id}@test.local",
        })
        await db.hr_salaries.insert_one({
            "id": sal_id, "staff_id": staff_id, "staff_name": "Daily Test",
            "base_salary": 0, "daily_rate": 60_000,
            "currency": "UGX", "pay_frequency": "biweekly",
            "wage_type": "daily", "location_id": loc_id,
            "line_items": [], "status": "active",
        })
        try:
            period = "2026-09-16_2026-09-29 (W38-W39)"
            res = await preview_payslips(
                {"period": period, "location_id": loc_id,
                 "days_worked_override": {staff_id: 10}},
                {"id": "u_admin", "name": "Admin", "role": "admin"},
            )
            assert res["count"] == 1
            row = res["rows"][0]
            assert row["wage_type"] == "daily"
            assert row["gross"] == 600_000.0, f"gross={row['gross']}"
            assert "60,000" in row["wage_details"]
            # Preview must not have persisted anything
            wrote = await db.hr_payslips.count_documents({"salary_id": sal_id})
            assert wrote == 0
        finally:
            await db.users.delete_one({"id": staff_id})
            await db.hr_salaries.delete_one({"id": sal_id})
    asyncio.run(_t())
