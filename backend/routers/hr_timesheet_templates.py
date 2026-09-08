"""Iter 337 — Printable / re-uploadable timesheet templates.

Two endpoints:
  • GET  /api/hr/timesheets/template   → downloadable XLSX seeded with the
    campus's active staff. Employees write in Days Worked, Hours Worked,
    Arrival/Exit for each day, sign, and hand back to HR.
  • POST /api/hr/timesheets/upload     → HR uploads the same XLSX (possibly
    typed up from a paper printout). We match rows by badge_number → staff
    and create timesheet drafts with status='submitted' + source='xlsx'.

The template supports every wage_type in one file:
  - Header row: Staff Name | Badge | Wage Type | Rate | Days Worked
    | Hours Worked | PTO Days | Notes | Signature
  - Data rows: pre-filled with active salaries for the picked period.

The upload matches by BADGE NUMBER (falls back to name) so paper sheets
signed by staff without app access flow straight into payroll approval.
"""
from __future__ import annotations
import io
from datetime import datetime, timezone, date as dt_date, timedelta as td
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse

from deps import db, logger, get_current_user
from routers.hr import require_director, _hr_scope, _period_span_days

router = APIRouter(prefix="/api/hr", tags=["hr-timesheet-templates"])


@router.get("/timesheets/template")
async def timesheet_template(
    period: str = Query(..., description="YYYY-MM or biweekly window label"),
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Return an XLSX template pre-seeded with active salaries for the given
    period. Directors download, print (or email), and hand to staff who
    don't use the app.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Timesheet"

    # Header + branding
    ws.merge_cells("A1:I1")
    c = ws.cell(row=1, column=1, value="58:12 Global — Employee Timesheet")
    c.font = Font(size=16, bold=True, color="0F172A")
    c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:I2")
    c = ws.cell(row=2, column=1, value=f"Pay Period: {period}  ·  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    c.font = Font(size=10, italic=True, color="475569")
    c.alignment = Alignment(horizontal="center")

    period_days = _period_span_days(period)
    ws.merge_cells("A3:I3")
    c = ws.cell(row=3, column=1, value=f"Instructions: staff fill Days Worked / Hours Worked / PTO / Sign — HR digitises and re-uploads. Period spans {period_days} calendar days.")
    c.font = Font(size=9, italic=True, color="64748B")
    c.alignment = Alignment(horizontal="center")

    # Column headers
    headers = ["Staff Name", "Badge Number", "Wage Type", "Rate", "Days Worked", "Hours Worked", "PTO Days", "Notes", "Signature"]
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    thin = Side(border_style="thin", color="94A3B8")
    border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=5, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[5].height = 26

    # Data rows — active salaries for this campus
    q = {"status": "active"}
    if location_id:
        q["location_id"] = location_id
    else:
        q.update(_hr_scope(current_user))
    salaries = await db.hr_salaries.find(q, {"_id": 0}).sort("staff_name", 1).to_list(500)

    # Prefetch users → badge number
    staff_ids = [s["staff_id"] for s in salaries]
    users = {}
    async for u in db.users.find({"id": {"$in": staff_ids}}, {"_id": 0, "id": 1, "badge_number": 1, "member_id": 1}):
        users[u["id"]] = u
    row_idx = 6
    for sal in salaries:
        u = users.get(sal["staff_id"], {})
        badge = u.get("badge_number") or u.get("member_id") or ""
        wage_type = (sal.get("wage_type") or "salary").title()
        rate = sal.get("hourly_rate") or sal.get("daily_rate") or sal.get("weekly_rate") or sal.get("biweekly_rate") or sal.get("base_salary") or 0
        row_data = [
            sal.get("staff_name", ""),
            str(badge),
            wage_type,
            f"{sal.get('currency','UGX')} {rate:,.0f}",
            "",  # Days Worked (staff fills in)
            "",  # Hours Worked
            "",  # PTO Days
            "",  # Notes
            "",  # Signature
        ]
        for col, v in enumerate(row_data, start=1):
            c = ws.cell(row=row_idx, column=col, value=v)
            c.border = border
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if col == 4:
                c.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[row_idx].height = 22
        row_idx += 1

    # Add ~5 blank rows for casual workers not in the salary table
    for _ in range(5):
        for col in range(1, 10):
            c = ws.cell(row=row_idx, column=col, value="")
            c.border = border
        ws.row_dimensions[row_idx].height = 22
        row_idx += 1

    # Column widths
    widths = [24, 16, 14, 18, 14, 14, 12, 30, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Footer / signature block
    footer_row = row_idx + 2
    ws.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=9)
    c = ws.cell(row=footer_row, column=1, value="HR Approval: ______________________________     Date: __________")
    c.font = Font(size=10, italic=True, color="475569")

    # ==================================================================
    # iter 338 — "Daily Log" sheet: per-staff × per-day rows so paper
    # time-cards (arrival/exit) can be typed directly into Excel and
    # auto-sum hours per day + per staff. Upload endpoint prefers the
    # Daily Log total when the Summary "Hours Worked" cell is blank.
    # ==================================================================
    ws_d = wb.create_sheet("Daily Log")

    ws_d.merge_cells("A1:G1")
    c = ws_d.cell(row=1, column=1, value="Daily Log — arrival / exit per day (auto-sums into hours)")
    c.font = Font(size=13, bold=True, color="0F172A")
    c.alignment = Alignment(horizontal="center")

    daily_headers = ["Staff Name", "Badge Number", "Date", "Arrival", "Exit", "Hours", "Notes"]
    for col, h in enumerate(daily_headers, start=1):
        cc = ws_d.cell(row=3, column=col, value=h)
        cc.font = header_font
        cc.fill = header_fill
        cc.alignment = Alignment(horizontal="center", vertical="center")
        cc.border = border
    ws_d.row_dimensions[3].height = 22

    # Figure out the concrete date range
    try:
        import re as _re
        m = _re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", period)
        if m:
            _start = dt_date.fromisoformat(m.group(1))
            _end = dt_date.fromisoformat(m.group(2))
        elif _re.match(r"^\d{4}-\d{2}$", period):
            _y, _mo = period.split("-")
            _start = dt_date(int(_y), int(_mo), 1)
            _end = dt_date(int(_y) + (1 if int(_mo) == 12 else 0),
                            1 if int(_mo) == 12 else int(_mo) + 1, 1) - td(days=1)
        else:
            _start = datetime.now(timezone.utc).date()
            _end = _start + td(days=13)
    except Exception:
        _start = datetime.now(timezone.utc).date()
        _end = _start + td(days=13)
    day_count = (_end - _start).days + 1

    daily_row = 4
    for sal in salaries:
        u = users.get(sal["staff_id"], {})
        badge = u.get("badge_number") or u.get("member_id") or ""
        for i in range(day_count):
            d = _start + td(days=i)
            row_vals = [
                sal.get("staff_name", "") if i == 0 else "",  # name on first row only for readability
                str(badge) if i == 0 else "",
                d.isoformat(),
                "",  # Arrival — HH:MM
                "",  # Exit — HH:MM
                None,  # Hours — formula written next
                "",  # Notes
            ]
            for col, v in enumerate(row_vals, start=1):
                cc = ws_d.cell(row=daily_row, column=col, value=v)
                cc.border = border
                cc.alignment = Alignment(vertical="center")
            # Hours formula: computes exit-arrival across midnight safely.
            # Arrival + Exit are typed as `08:00` / `17:00`; empty = blank.
            ws_d.cell(row=daily_row, column=6, value=(
                f'=IF(AND(D{daily_row}<>"",E{daily_row}<>""),'
                f'IF(E{daily_row}<D{daily_row},'
                f'(E{daily_row}-D{daily_row}+1)*24,'
                f'(E{daily_row}-D{daily_row})*24),"")'
            ))
            daily_row += 1
        # Blank separator row between staff for readability
        daily_row += 1

    ws_d.column_dimensions["A"].width = 24
    ws_d.column_dimensions["B"].width = 16
    ws_d.column_dimensions["C"].width = 14
    ws_d.column_dimensions["D"].width = 10
    ws_d.column_dimensions["E"].width = 10
    ws_d.column_dimensions["F"].width = 10
    ws_d.column_dimensions["G"].width = 28

    # Instructions on how to fill Daily Log
    dl_note_row = daily_row + 2
    ws_d.merge_cells(start_row=dl_note_row, start_column=1, end_row=dl_note_row, end_column=7)
    c = ws_d.cell(row=dl_note_row, column=1, value=(
        "Fill Arrival and Exit in 24h format (HH:MM). Hours will auto-calculate. "
        "If arrival/exit are blank the day is treated as not worked. "
        "For overnight shifts (exit next morning), enter the exit time as-is and Hours handles the wrap."
    ))
    c.font = Font(size=9, italic=True, color="64748B")
    c.alignment = Alignment(wrap_text=True)

    # Second sheet: instructions
    ws2 = wb.create_sheet("Instructions")
    ws2.column_dimensions["A"].width = 90
    lines = [
        "How to use this timesheet",
        "",
        "1. Staff (or their supervisor) fill in Days Worked, Hours Worked, and PTO for each row.",
        "2. Hourly staff should record TOTAL hours worked in the period (not per day).",
        "3. Daily staff record TOTAL days worked. Rows can be left blank for staff who didn't work.",
        "4. Salaried staff can skip Days/Hours — payroll uses the monthly base salary.",
        "5. Staff sign the Signature column with a pen (paper) or type their name (digital).",
        "6. HR uploads the completed file at: HR → Timesheets → Upload sheet.",
        "",
        "The upload matches by BADGE NUMBER. If a staff row has no badge number,",
        "the system falls back to name matching (case-insensitive).",
        "",
        f"Period: {period}  ·  Days in period: {period_days}",
    ]
    for i, ln in enumerate(lines, start=1):
        c = ws2.cell(row=i, column=1, value=ln)
        if i == 1:
            c.font = Font(bold=True, size=13)
        else:
            c.font = Font(size=10, color="334155")
    ws2.sheet_state = "visible"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_period = period.split(" ")[0].replace(":", "-")
    filename = f"timesheet-{safe_period}-{(location_id or 'all')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/timesheets/upload")
async def timesheet_upload(
    file: UploadFile = File(...),
    period: str = Query(..., description="Pay period this upload applies to"),
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Ingest an XLSX produced from `/timesheets/template`.

    Match rows by badge_number (fallback: case-insensitive name). Every
    matched staff gets a timesheet draft with status='submitted' so a
    reviewing director can approve them in bulk.

    Response: { created: [...], skipped: [{reason, row, name}], total_rows }
    """
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    from openpyxl import load_workbook
    try:
        content = await file.read()
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read spreadsheet: {e}")
    ws = wb.active

    # Locate header row (search first 10 rows for "Staff Name" / "Badge Number")
    header_row = None
    for r in range(1, min(15, ws.max_row) + 1):
        vals = [str(ws.cell(row=r, column=c).value or "").strip().lower() for c in range(1, 10)]
        if "staff name" in vals and "badge number" in vals:
            header_row = r
            break
    if not header_row:
        raise HTTPException(status_code=400, detail="Header row not found — is this a template file?")

    header_map = {}
    for c in range(1, 12):
        v = str(ws.cell(row=header_row, column=c).value or "").strip().lower()
        if v:
            header_map[v] = c

    def col(row: int, name: str):
        c = header_map.get(name)
        return ws.cell(row=row, column=c).value if c else None

    # iter 338 — build a per-badge hour total from the "Daily Log" sheet
    # (arrival/exit rows). If the Summary "Hours Worked" cell is blank
    # we'll fall back to this sum so paper time-cards flow through
    # untouched by HR.
    daily_hours_by_badge: dict[str, float] = {}
    daily_hours_by_name: dict[str, float] = {}
    daily_days_by_badge: dict[str, int] = {}
    daily_days_by_name: dict[str, int] = {}
    if "Daily Log" in wb.sheetnames:
        ws_d = wb["Daily Log"]
        d_header = None
        for r in range(1, min(10, ws_d.max_row) + 1):
            vals = [str(ws_d.cell(row=r, column=c).value or "").strip().lower() for c in range(1, 8)]
            if "arrival" in vals and "exit" in vals and "hours" in vals:
                d_header = r
                break
        if d_header:
            d_col = {}
            for c in range(1, 10):
                v = str(ws_d.cell(row=d_header, column=c).value or "").strip().lower()
                if v:
                    d_col[v] = c
            last_name, last_badge = "", ""
            for r in range(d_header + 1, ws_d.max_row + 1):
                name_v = str(ws_d.cell(row=r, column=d_col.get("staff name", 1)).value or "").strip()
                badge_v = str(ws_d.cell(row=r, column=d_col.get("badge number", 2)).value or "").strip()
                # Name/badge only appear on the first date row per staff — carry them forward.
                if name_v:
                    last_name = name_v
                if badge_v:
                    last_badge = badge_v
                hours_cell = ws_d.cell(row=r, column=d_col.get("hours", 6)).value
                try:
                    hrs = float(hours_cell) if hours_cell not in (None, "", 0) else 0
                except (TypeError, ValueError):
                    hrs = 0
                if hrs > 0 and (last_name or last_badge):
                    if last_badge:
                        daily_hours_by_badge[last_badge] = daily_hours_by_badge.get(last_badge, 0) + hrs
                        daily_days_by_badge[last_badge] = daily_days_by_badge.get(last_badge, 0) + 1
                    if last_name:
                        key = last_name.lower()
                        daily_hours_by_name[key] = daily_hours_by_name.get(key, 0) + hrs
                        daily_days_by_name[key] = daily_days_by_name.get(key, 0) + 1

    created = []
    skipped = []
    total_rows = 0
    for r in range(header_row + 1, ws.max_row + 1):
        name = (str(col(r, "staff name") or "").strip())
        badge = (str(col(r, "badge number") or "").strip())
        days_w = col(r, "days worked")
        hours_w = col(r, "hours worked")
        pto = col(r, "pto days")
        notes = str(col(r, "notes") or "").strip()
        if not name and not badge:
            continue
        total_rows += 1
        # Match staff — badge first, name second (case-insensitive)
        user = None
        if badge:
            user = await db.users.find_one(
                {"$or": [{"badge_number": badge}, {"member_id": badge}]},
                {"_id": 0, "id": 1, "name": 1, "department": 1, "location_id": 1},
            )
        if not user and name:
            import re as _re
            user = await db.users.find_one(
                {"name": {"$regex": f"^{_re.escape(name)}$", "$options": "i"}},
                {"_id": 0, "id": 1, "name": 1, "department": 1, "location_id": 1},
            )
        if not user:
            skipped.append({"row": r, "name": name, "badge": badge, "reason": "no matching user"})
            continue
        try:
            days_val = float(days_w or 0)
            hours_val = float(hours_w) if hours_w not in (None, "") else None
            pto_val = float(pto or 0)
        except (TypeError, ValueError):
            skipped.append({"row": r, "name": name, "badge": badge, "reason": "non-numeric days/hours"})
            continue
        # iter 338 — fall back to Daily Log totals when summary Hours Worked is blank
        source_bits = []
        if hours_val is None or hours_val == 0:
            fallback_hrs = daily_hours_by_badge.get(badge) or daily_hours_by_name.get(name.lower(), 0)
            if fallback_hrs > 0:
                hours_val = round(fallback_hrs, 2)
                source_bits.append("hours from Daily Log")
        if days_val == 0:
            fallback_days = daily_days_by_badge.get(badge) or daily_days_by_name.get(name.lower(), 0)
            if fallback_days > 0:
                days_val = float(fallback_days)
                source_bits.append("days from Daily Log")
        if days_val == 0 and (hours_val is None or hours_val == 0):
            skipped.append({"row": r, "name": name, "badge": badge, "reason": "no hours or days worked"})
            continue

        # Idempotent upsert — reuse existing draft/submitted/rejected row for
        # this staff+period so re-uploads don't leave stale entries.
        import uuid as _uuid
        existing = await db.hr_timesheets.find_one(
            {"staff_id": user["id"], "period": period, "status": {"$in": ["draft", "submitted", "rejected"]}}
        )
        doc = {
            "id": existing["id"] if existing else f"ts_{_uuid.uuid4().hex[:10]}",
            "staff_id": user["id"],
            "staff_name": user.get("name", name),
            "department": user.get("department", ""),
            "location_id": location_id or user.get("location_id") or "",
            "period": period,
            "days_worked": days_val,
            "hours_worked": hours_val,
            "pto_days": pto_val,
            "notes": (notes + (f" [{', '.join(source_bits)}]" if source_bits else ""))[:1000],
            "status": "submitted",
            "source": "xlsx_upload",
            "uploaded_from": file.filename,
            "submitted_by": current_user["id"],
            "submitted_by_name": current_user.get("name", ""),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            await db.hr_timesheets.update_one({"id": doc["id"]}, {"$set": doc})
        else:
            await db.hr_timesheets.insert_one(doc)
        created.append({"row": r, "staff_id": user["id"], "name": user.get("name"), "days_worked": days_val, "hours_worked": hours_val})

    logger.info(f"timesheet xlsx upload: {len(created)} created, {len(skipped)} skipped by {current_user['id']}")
    return {
        "created": created,
        "skipped": skipped,
        "total_rows": total_rows,
        "period": period,
    }
