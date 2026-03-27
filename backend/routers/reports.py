"""Report builder, storage, and auto-update system."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from deps import get_current_user, db, require_manager, get_campus_filter
from typing import Optional
import uuid, openpyxl
from io import BytesIO

router = APIRouter(prefix="/api")


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
        query = {**campus}
        if filters.get("location_id"): query["location_id"] = filters["location_id"]
        if filters.get("status"): query["status"] = filters["status"]
        members = await db.members.find(query, {"_id": 0}).to_list(5000)
        data["members"] = members; data["members_count"] = len(members)
    if rtype in ("financial", "custom"):
        dq = {}
        if filters.get("date_from"): dq["date"] = {"$gte": filters["date_from"]}
        if filters.get("date_to"): dq.setdefault("date", {})["$lte"] = filters["date_to"]
        donations = await db.donations.find(dq, {"_id": 0}).to_list(5000)
        expenses = await db.expenses.find(dq, {"_id": 0}).to_list(5000)
        data["donations"] = donations; data["expenses"] = expenses
        data["total_donations"] = sum(d.get("amount", 0) for d in donations)
        data["total_expenses"] = sum(e.get("amount", 0) for e in expenses)
    if rtype in ("events", "custom"):
        eq = {}
        if filters.get("date_from"): eq["date"] = {"$gte": filters["date_from"]}
        events = await db.events.find(eq, {"_id": 0}).to_list(5000)
        data["events"] = events; data["events_count"] = len(events)
    if rtype in ("attendance", "custom"):
        checkins = await db.check_ins.find({}, {"_id": 0}).to_list(5000)
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
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    buf = BytesIO()
    wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={report.get('title', 'report')}.xlsx"})
