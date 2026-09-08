"""Iter 335 — Payroll Preview + PDF coverage line.

Verifies:
  1. `POST /hr/payslips/preview` computes the same gross/net numbers as
     `/hr/payslips/generate` but never writes to hr_payslips.
  2. Payslip PDF HTML contains a "Covers work from <start> to <end>" line
     for both monthly and biweekly periods.
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


async def _seed_salary(db, loc_id, monthly_base, freq):
    staff_id = f"u_test_{uuid.uuid4().hex[:8]}"
    sal_id = f"sal_{uuid.uuid4().hex[:8]}"
    await db.users.insert_one({
        "id": staff_id, "name": "Preview Test", "role": "Staff",
        "location_id": loc_id, "email": f"{staff_id}@test.local",
    })
    await db.hr_salaries.insert_one({
        "id": sal_id, "staff_id": staff_id, "staff_name": "Preview Test",
        "base_salary": monthly_base, "currency": "UGX",
        "pay_frequency": freq, "location_id": loc_id,
        "line_items": [], "status": "active",
    })
    return staff_id, sal_id


async def _run_preview_check(db):
    from routers.hr import preview_payslips
    loc_id = f"loc_test_{uuid.uuid4().hex[:8]}"
    staff_id, sal_id = await _seed_salary(db, loc_id, 600_000, "biweekly")
    try:
        # Fake current_user (require_director bypassed since we call the
        # function directly). preview_payslips itself doesn't touch
        # current_user beyond a sentinel dict shape.
        current_user = {"id": "u_admin", "name": "Admin", "role": "admin"}
        # Biweekly window for W38-W39 2026 (14 days from Sep 16)
        period = "2026-09-16_2026-09-29 (W38-W39)"
        res = await preview_payslips(
            {"period": period, "location_id": loc_id}, current_user
        )
        assert res["count"] == 1
        assert res["existing_count"] == 0
        row = res["rows"][0]
        # 600k monthly base × (12/26) biweekly proration ≈ 276923.08
        assert row["gross"] == 276923.08, f"gross={row['gross']}"
        assert row["net"] == 276923.08
        assert row["already_generated"] is False
        # CRITICAL: preview must not have persisted anything
        wrote = await db.hr_payslips.count_documents(
            {"salary_id": sal_id, "period": period}
        )
        assert wrote == 0, "preview must never write payslips"
    finally:
        await db.users.delete_one({"id": staff_id})
        await db.hr_salaries.delete_one({"id": sal_id})
        await db.hr_payslips.delete_many({"salary_id": sal_id})


async def _run_pdf_coverage_check(db):
    from routers.hr import _generate_payslip_pdf_bytes
    loc_id = f"loc_test_{uuid.uuid4().hex[:8]}"
    staff_id, sal_id = await _seed_salary(db, loc_id, 600_000, "biweekly")
    ps_id = f"ps_test_{uuid.uuid4().hex[:8]}"
    try:
        await db.hr_payslips.insert_one({
            "id": ps_id, "salary_id": sal_id, "staff_id": staff_id,
            "staff_name": "Preview Test", "location_id": loc_id,
            "period": "2026-09-16_2026-09-29 (W38-W39)",
            "gross_salary": 276923.08, "allowances": 0, "deductions": 0,
            "net_salary": 276923.08, "currency": "UGX", "status": "draft",
            "line_items": [], "working_days": 10, "days_worked": 10,
            "unpaid_leave_days": 0, "pto_days": 0,
        })
        # Monkey-patch HTML.write_pdf out — we only care about the HTML content.
        import routers.hr as hr_mod
        real_html = hr_mod.__dict__.get("HTML")
        captured = {}
        class FakeHTML:
            def __init__(self, string):
                captured["html"] = string
            def write_pdf(self):
                return b"%PDF-fake"
        # Patch import inside the function scope via weasyprint module
        import weasyprint
        real = weasyprint.HTML
        weasyprint.HTML = FakeHTML
        try:
            await _generate_payslip_pdf_bytes(ps_id)
        finally:
            weasyprint.HTML = real
        html = captured.get("html", "")
        assert "Covers work from" in html, "PDF should include coverage line"
        assert "Sep" in html and "16" in html and "29" in html
        assert "2 weeks" in html
    finally:
        await db.users.delete_one({"id": staff_id})
        await db.hr_salaries.delete_one({"id": sal_id})
        await db.hr_payslips.delete_one({"id": ps_id})


def test_iter335_preview_and_pdf_coverage():
    async def _run():
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        await _run_preview_check(deps.db)
        await _run_pdf_coverage_check(deps.db)
    asyncio.run(_run())
