"""Report builder, storage, and auto-update system."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from deps import get_current_user, db, require_manager, get_campus_filter
from typing import Optional
import uuid, openpyxl
from io import BytesIO

router = APIRouter(prefix="/api")


@router.get("/reports/summary")
async def reports_summary(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Quick summary for the dashboard / reports page.

    iter345 — income and expenses now come from the LEDGER
    (`finance_journal_entries`), not the legacy `donations` / `expenses`
    mirror collections. Receipts, payroll, sales and transfers only ever
    produced journal entries, so the old numbers were always short and never
    matched the Finance module. Breakdowns are per ledger account.
    """
    campus = await get_campus_filter(current_user)
    query = campus or {}
    if location_id:
        query["location_id"] = location_id
    loc_for_ledger = location_id or (query.get("location_id") if isinstance(query.get("location_id"), str) else None)

    from routers.finance.reports import _balances_by_account
    bal = await _balances_by_account(date_from, date_to, loc_for_ledger)
    donations, expenses = [], []
    for v in bal.values():
        a = v["account"]
        if v["balance"] == 0:
            continue
        row = {"_id": f"{a.get('code', '')} {a.get('name', '')}".strip(), "total": v["balance"], "count": 1}
        if a["type"] == "revenue":
            donations.append(row)
        elif a["type"] == "expense":
            expenses.append(row)
    donations.sort(key=lambda r: -r["total"])
    expenses.sort(key=lambda r: -r["total"])

    members_count = await db.members.count_documents(query if query else {})
    events_count = await db.events.count_documents(query if query else {})
    children_count = await db.children.count_documents(query if query else {})

    total_income = round(sum(d["total"] for d in donations), 2)
    total_expenses = round(sum(e["total"] for e in expenses), 2)

    return {
        "total_income": total_income, "total_expenses": total_expenses,
        "net": round(total_income - total_expenses, 2),
        "income_breakdown": donations, "expense_breakdown": expenses,
        "members_count": members_count, "events_count": events_count, "children_count": children_count,
        "date_from": date_from or "", "date_to": date_to or "", "source": "ledger",
    }


@router.get("/reports/pdf")
async def reports_pdf(location_id: Optional[str] = None, date_from: Optional[str] = None,
                      date_to: Optional[str] = None,
                      fx_target: Optional[str] = None, fx_rate: Optional[float] = None,
                      current_user: dict = Depends(get_current_user)):
    """Render the summary report as a printable PDF (WeasyPrint).

    Optional `fx_target` (e.g. "USD") and `fx_rate` (1 base = ? target) convert
    every money figure in the output. If either is missing or fx_rate<=0, the
    report renders in the base currency untouched.

    Same numbers as /reports/summary, wrapped in a clean HTML template.
    Placed BEFORE /reports/{report_id} so the literal /pdf path wins on match.
    """
    summary = await reports_summary(location_id=location_id, date_from=date_from,
                                    date_to=date_to, current_user=current_user)

    # FX conversion — apply to every displayed money figure
    fx_active = bool(fx_target) and fx_rate is not None and float(fx_rate) > 0
    def fx(v):
        return round(float(v or 0) * float(fx_rate), 2) if fx_active else float(v or 0)
    currency_suffix = f" ({fx_target} @ {fx_rate})" if fx_active else ""

    loc_name = "All locations"
    if location_id:
        loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1})
        if loc:
            loc_name = loc.get("name", loc_name)

    period = "All time"
    if date_from and date_to:
        period = f"{date_from} → {date_to}"
    elif date_from:
        period = f"from {date_from}"
    elif date_to:
        period = f"through {date_to}"

    def _rows(items):
        if not items:
            return '<tr><td colspan="3" style="text-align:center;color:#94a3b8;padding:12px">No entries.</td></tr>'
        return "".join(
            f'<tr><td>{(x.get("_id") or "—")}</td>'
            f'<td style="text-align:right">{x.get("count", 0)}</td>'
            f'<td style="text-align:right">{fx(x.get("total", 0)):,.2f}</td></tr>'
            for x in items
        )

    net = fx(summary["net"])
    net_color = "#059669" if net >= 0 else "#dc2626"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>58:12 Connect — Summary Report</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  body {{ font-family: 'Helvetica','Arial',sans-serif; color: #0f172a; font-size: 11pt; }}
  h1 {{ font-size: 18pt; margin: 0 0 4px; }}
  .meta {{ color: #64748b; font-size: 9pt; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 12px; margin: 18px 0 24px; }}
  .stat {{ flex: 1; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; }}
  .stat .label {{ font-size: 8pt; text-transform: uppercase; color: #64748b; letter-spacing: 0.03em; }}
  .stat .value {{ font-size: 14pt; font-weight: 600; margin-top: 4px; }}
  h2 {{ font-size: 12pt; margin: 20px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #e2e8f0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th {{ text-align: left; color: #64748b; font-weight: 500; font-size: 9pt; padding: 4px 6px; border-bottom: 1px solid #e2e8f0; }}
  td {{ padding: 4px 6px; border-bottom: 1px solid #f1f5f9; }}
  .footer {{ margin-top: 30px; font-size: 8pt; color: #94a3b8; text-align: center; }}
  .fx-note {{ margin-top: 8px; font-size: 9pt; color: #64748b; font-style: italic; }}
</style></head>
<body>
  <h1>58:12 Connect · Summary Report</h1>
  <div class="meta">
    Location: <strong>{loc_name}</strong> · Period: <strong>{period}</strong> ·
    Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
  </div>
  {f'<div class="fx-note">All amounts converted to {fx_target} at rate {fx_rate}.</div>' if fx_active else ''}

  <div class="stats">
    <div class="stat"><div class="label">Total Income{currency_suffix}</div>
      <div class="value" style="color:#059669">{fx(summary["total_income"]):,.2f}</div></div>
    <div class="stat"><div class="label">Total Expenses{currency_suffix}</div>
      <div class="value" style="color:#dc2626">{fx(summary["total_expenses"]):,.2f}</div></div>
    <div class="stat"><div class="label">Net Balance{currency_suffix}</div>
      <div class="value" style="color:{net_color}">{net:,.2f}</div></div>
  </div>

  <div class="stats">
    <div class="stat"><div class="label">Members</div><div class="value">{summary["members_count"]:,}</div></div>
    <div class="stat"><div class="label">Children</div><div class="value">{summary["children_count"]:,}</div></div>
    <div class="stat"><div class="label">Events</div><div class="value">{summary["events_count"]:,}</div></div>
  </div>

  <h2>Income breakdown</h2>
  <table><thead><tr><th>Category</th><th style="text-align:right">Count</th><th style="text-align:right">Total{currency_suffix}</th></tr></thead>
  <tbody>{_rows(summary["income_breakdown"])}</tbody></table>

  <h2>Expense breakdown</h2>
  <table><thead><tr><th>Category</th><th style="text-align:right">Count</th><th style="text-align:right">Total{currency_suffix}</th></tr></thead>
  <tbody>{_rows(summary["expense_breakdown"])}</tbody></table>

  <div class="footer">58:12 Connect — Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}</div>
</body></html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception as e:
        # Never leak a raw stack trace to the frontend — the toast just says
        # "PDF download failed". Log the real reason for diagnosis.
        import logging
        logging.getLogger(__name__).error(f"WeasyPrint failed for /reports/pdf: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    filename = f"5812_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports")
async def list_reports(current_user: dict = Depends(get_current_user)):
    reports = await db.reports.find({"$or": [{"created_by": current_user["id"]}, {"is_shared": True}]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return reports


@router.post("/reports")
async def create_report(data: dict, current_user: dict = Depends(get_current_user)):
    report_id = f"rpt_{str(uuid.uuid4())[:8]}"
    doc = {
        "id": report_id, "title": data.get("title", "Untitled Report"), "type": data.get("type", "custom"),
        "config": data.get("config", {}), "filters": data.get("filters", {}), "columns": data.get("columns", []),
        "is_shared": data.get("is_shared", False), "auto_update": data.get("auto_update", True),
        "schedule": data.get("schedule", "manual"), "last_generated": None, "data_snapshot": None,
        "created_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reports.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/reports/{report_id}")
async def get_report(report_id: str, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.put("/reports/{report_id}")
async def update_report(report_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    data.pop("_id", None); data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.reports.update_one({"id": report_id}, {"$set": data})
    return {**data, "id": report_id}


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, current_user: dict = Depends(get_current_user)):
    await db.reports.delete_one({"id": report_id})
    return {"message": "Report deleted"}


@router.post("/reports/{report_id}/generate")
async def generate_report_data(report_id: str, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    filters = report.get("filters", {})
    rtype = report.get("type", "custom")
    data = {}
    campus = await get_campus_filter(current_user)
    if rtype in ("members", "custom"):
        query = {}
        if filters.get("location_id"): query["location_id"] = filters["location_id"]
        if filters.get("status"): query["status"] = filters["status"]
        mem_query = {"$and": [campus, query]} if campus else query
        members = await db.members.find(mem_query, {"_id": 0}).to_list(5000)
        data["members"] = members; data["members_count"] = len(members)
    if rtype in ("financial", "custom"):
        dq = {}
        if filters.get("date_from"): dq["date"] = {"$gte": filters["date_from"]}
        if filters.get("date_to"): dq.setdefault("date", {})["$lte"] = filters["date_to"]
        fin_query = {"$and": [campus, dq]} if campus else dq
        donations = await db.donations.find(fin_query, {"_id": 0}).to_list(5000)
        expenses = await db.expenses.find(fin_query, {"_id": 0}).to_list(5000)
        data["donations"] = donations; data["expenses"] = expenses
        data["total_donations"] = sum(d.get("amount", 0) for d in donations)
        data["total_expenses"] = sum(e.get("amount", 0) for e in expenses)
    if rtype in ("events", "custom"):
        eq = {}
        if filters.get("date_from"): eq["date"] = {"$gte": filters["date_from"]}
        evt_query = {"$and": [campus, eq]} if campus else eq
        events = await db.events.find(evt_query, {"_id": 0}).to_list(5000)
        data["events"] = events; data["events_count"] = len(events)
    if rtype in ("attendance", "custom"):
        aq = {}
        att_query = {"$and": [campus, aq]} if campus else aq
        checkins = await db.checkins.find(att_query, {"_id": 0}).to_list(5000)
        data["checkins"] = checkins; data["checkins_count"] = len(checkins)
    now = datetime.now(timezone.utc).isoformat()
    await db.reports.update_one({"id": report_id}, {"$set": {"data_snapshot": data, "last_generated": now}})
    return {"report_id": report_id, "data": data, "generated_at": now}


@router.get("/reports/{report_id}/export/xlsx")
async def export_report_xlsx(report_id: str, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    data = report.get("data_snapshot")
    if not data:
        raise HTTPException(status_code=400, detail="Generate report data first")
    wb = openpyxl.Workbook()
    for key in data:
        if isinstance(data[key], list) and data[key]:
            ws = wb.create_sheet(title=key[:31])
            headers = list(data[key][0].keys())
            ws.append(headers)
            for row in data[key]:
                ws.append([str(row.get(h, "")) for h in headers])
    # A report with no rows (e.g. attendance for a quiet week) used to leave a
    # sheet-less workbook, which openpyxl refuses to save → HTTP 500. Always
    # ship at least a summary sheet.
    if len(wb.sheetnames) == 1 and "Sheet" in wb.sheetnames:
        ws = wb["Sheet"]
        ws.title = "Summary"
        ws.append([report.get("title") or "Report", report.get("type") or ""])
        ws.append(["Generated", str(report.get("generated_at") or "")])
        ws.append([])
        ws.append(["Section", "Rows"])
        for key, val in data.items():
            if isinstance(val, list):
                ws.append([key, len(val)])
            elif not isinstance(val, dict):
                ws.append([key, str(val)])
        ws.append([])
        ws.append(["No detail rows matched this report's filters."])
    elif "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    buf = BytesIO()
    wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={report.get('title', 'report')}.xlsx"})
