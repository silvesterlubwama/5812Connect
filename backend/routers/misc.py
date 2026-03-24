"""Resources, Resource Types, Announcements, Analytics, Search, Export routes"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from deps import db, get_current_user, require_admin, require_manager, _audit, logger
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import uuid, csv, io

router = APIRouter(prefix="/api", tags=["misc"])


# ========== RESOURCE TYPES ==========

@router.get("/resource-types")
async def list_resource_types(current_user: dict = Depends(get_current_user)):
    types = await db.resource_types.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    if not types:
        defaults = [
            {"id": "rtype_room", "name": "room", "label": "Room", "icon": "door-open"},
            {"id": "rtype_auditorium", "name": "auditorium", "label": "Auditorium", "icon": "building"},
            {"id": "rtype_conference", "name": "conference", "label": "Conference Room", "icon": "users"},
            {"id": "rtype_hall", "name": "hall", "label": "Hall", "icon": "warehouse"},
            {"id": "rtype_equipment", "name": "equipment", "label": "Equipment", "icon": "wrench"},
            {"id": "rtype_vehicle", "name": "vehicle", "label": "Vehicle", "icon": "car"},
            {"id": "rtype_outdoor", "name": "outdoor", "label": "Outdoor Space", "icon": "tree"},
        ]
        await db.resource_types.insert_many(defaults)
        for d in defaults:
            d.pop("_id", None)
        return defaults
    return types


@router.post("/resource-types")
async def create_resource_type(data: dict, current_user: dict = Depends(require_manager)):
    doc = {
        "id": f"rtype_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", "").lower().replace(" ", "_"),
        "label": data.get("label", data.get("name", "")),
        "icon": data.get("icon", "box"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.resource_types.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/resource-types/{type_id}")
async def update_resource_type(type_id: str, data: dict, current_user: dict = Depends(require_manager)):
    update = {k: v for k, v in data.items() if k in ("name", "label", "icon") and v is not None}
    if update.get("name"):
        update["name"] = update["name"].lower().replace(" ", "_")
    await db.resource_types.update_one({"id": type_id}, {"$set": update})
    return await db.resource_types.find_one({"id": type_id}, {"_id": 0})


@router.delete("/resource-types/{type_id}")
async def delete_resource_type(type_id: str, current_user: dict = Depends(require_admin)):
    await db.resource_types.delete_one({"id": type_id})
    return {"message": "Resource type deleted"}


# ========== RESOURCES ==========

class ResourceCreate(BaseModel):
    name: str
    type: str = "room"
    category: Optional[str] = None
    capacity: Optional[int] = None
    quantity: int = 1
    description: Optional[str] = None
    location_id: Optional[str] = None
    hourly_rate: Optional[float] = None
    is_bookable: bool = True
    staff_only: bool = False
    is_consumable: bool = False

class ResourceBookingCreate(BaseModel):
    resource_id: str
    title: str
    booked_by: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    notes: Optional[str] = None


@router.get("/resources")
async def list_resources(current_user: dict = Depends(get_current_user)):
    return await db.resources.find({}, {"_id": 0}).sort("name", 1).to_list(200)

@router.post("/resources")
async def create_resource(data: ResourceCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"res_{str(uuid.uuid4())[:8]}", **data.model_dump(), "available": True, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.resources.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "resource", doc["id"])
    return doc

@router.put("/resources/{res_id}")
async def update_resource(res_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "type", "category", "capacity", "quantity", "description", "location_id", "hourly_rate", "is_bookable", "staff_only", "is_consumable", "available"}
    update = {k: v for k, v in data.items() if k in allowed}
    await db.resources.update_one({"id": res_id}, {"$set": update})
    return await db.resources.find_one({"id": res_id}, {"_id": 0})

@router.delete("/resources/{res_id}")
async def delete_resource(res_id: str, current_user: dict = Depends(get_current_user)):
    await db.resources.delete_one({"id": res_id}); return {"message": "Deleted"}

@router.get("/resources/bookings")
async def list_resource_bookings(resource_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"resource_id": resource_id} if resource_id else {}
    return await db.resource_bookings.find(query, {"_id": 0}).sort("date", 1).to_list(500)

@router.post("/resources/bookings")
async def create_resource_booking(data: ResourceBookingCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"rb_{str(uuid.uuid4())[:8]}", **data.model_dump(), "status": "confirmed", "booked_by": data.booked_by or current_user.get("name", "Unknown"), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.resource_bookings.insert_one(doc); doc.pop("_id", None)
    return doc

@router.delete("/resources/bookings/{booking_id}")
async def delete_resource_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    await db.resource_bookings.delete_one({"id": booking_id}); return {"message": "Deleted"}


# ========== ANNOUNCEMENTS ==========

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    type: str = "general"
    target_role: Optional[str] = None
    pinned: bool = False
    expires_at: Optional[str] = None

@router.get("/announcements")
async def list_announcements(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    return await db.announcements.find(query, {"_id": 0}).sort([("pinned", -1), ("created_at", -1)]).to_list(100)

@router.post("/announcements")
async def create_announcement(data: AnnouncementCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"ann_{str(uuid.uuid4())[:8]}", **data.model_dump(), "author_name": current_user.get("name", "Admin"), "author_role": current_user.get("role", "admin"), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.announcements.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "announcement", doc["id"])
    return doc

@router.delete("/announcements/{ann_id}")
async def delete_announcement(ann_id: str, current_user: dict = Depends(get_current_user)):
    await db.announcements.delete_one({"id": ann_id}); return {"message": "Deleted"}

@router.put("/announcements/{ann_id}/pin")
async def toggle_announcement_pin(ann_id: str, current_user: dict = Depends(get_current_user)):
    ann = await db.announcements.find_one({"id": ann_id}, {"_id": 0})
    if ann:
        await db.announcements.update_one({"id": ann_id}, {"$set": {"pinned": not ann.get("pinned", False)}})
    return {"message": "Updated"}


# ========== ANALYTICS ==========

@router.get("/analytics/attendance")
async def attendance_analytics(current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    weekly_data = []
    for i in range(11, -1, -1):
        week_start = (now - timedelta(weeks=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        count = await db.checkins.count_documents({"check_in_time": {"$gte": week_start.isoformat(), "$lt": week_end.isoformat()}})
        weekly_data.append({"week": week_start.strftime("W%V"), "date": week_start.strftime("%b %d"), "checkins": count})
    recent = await db.checkins.find({}, {"_id": 0, "id": 1, "member_name": 1, "event_name": 1, "check_in_time": 1, "method": 1}).sort("check_in_time", -1).limit(10).to_list(10)
    total_today = await db.checkins.count_documents({"check_in_time": {"$gte": now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()}})
    total_week = weekly_data[-1]["checkins"] if weekly_data else 0
    total_month = await db.checkins.count_documents({"check_in_time": {"$gte": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()}})
    return {"weekly_data": weekly_data, "recent": recent, "total_today": total_today, "total_week": total_week, "total_month": total_month}

@router.get("/analytics/sales")
async def sales_analytics(current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    monthly_data = []
    for i in range(5, -1, -1):
        month_dt = now.replace(day=1) - timedelta(days=i * 28)
        month_start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = month_dt.replace(year=month_dt.year + 1, month=1, day=1) if month_dt.month == 12 else month_dt.replace(month=month_dt.month + 1, day=1)
        sales = await db.sales.find({"created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}}, {"_id": 0, "total": 1}).to_list(5000)
        revenue = sum(s.get("total", 0) for s in sales)
        monthly_data.append({"month": month_dt.strftime("%b %Y"), "revenue": revenue, "transactions": len(sales)})
    all_sales = await db.sales.find({}, {"_id": 0, "items": 1, "total": 1, "payment_method": 1}).to_list(5000)
    product_totals = {}; payment_totals = {}
    for s in all_sales:
        method = s.get("payment_method", "cash")
        payment_totals[method] = payment_totals.get(method, 0) + s.get("total", 0)
        for item in s.get("items", []):
            name = item.get("name", "Unknown")
            product_totals[name] = product_totals.get(name, 0) + item.get("unit_price", 0) * item.get("qty", 0)
    top_products = sorted([{"name": k, "revenue": v} for k, v in product_totals.items()], key=lambda x: x["revenue"], reverse=True)[:8]
    payment_breakdown = [{"name": k.replace("_", " ").title(), "value": v} for k, v in payment_totals.items()]
    total_revenue = sum(s.get("total", 0) for s in all_sales)
    return {"monthly_data": monthly_data, "top_products": top_products, "payment_breakdown": payment_breakdown, "total_revenue": total_revenue, "total_transactions": len(all_sales)}

@router.get("/analytics/locations")
async def location_analytics(current_user: dict = Depends(get_current_user)):
    locations = await db.locations.find({}, {"_id": 0}).to_list(200)
    result = []
    for loc in locations:
        member_count = await db.members.count_documents({"location_id": loc["id"]})
        checkin_count = await db.checkins.count_documents({"location_id": loc["id"]})
        event_count = await db.events.count_documents({"location_id": loc["id"]})
        result.append({**loc, "member_count": member_count, "checkin_count": checkin_count, "event_count": event_count})
    total_members = await db.members.count_documents({})
    return {"locations": result, "total_members": total_members}


# ========== SEARCH ==========

@router.get("/search")
async def global_search(q: str, current_user: dict = Depends(get_current_user)):
    if not q or len(q.strip()) < 2:
        return {"results": []}
    pattern = {"$regex": q.strip(), "$options": "i"}
    results = []
    members = await db.members.find({"$or": [{"name": pattern}, {"email": pattern}, {"phone": pattern}]}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).limit(5).to_list(5)
    for m in members:
        results.append({"type": "member", "id": m["id"], "title": m["name"], "subtitle": m.get("email", m.get("role", "")), "url": "/members"})
    events = await db.events.find({"$or": [{"title": pattern}, {"location": pattern}]}, {"_id": 0, "id": 1, "title": 1, "date": 1, "status": 1}).limit(5).to_list(5)
    for e in events:
        results.append({"type": "event", "id": e["id"], "title": e["title"], "subtitle": e.get("date", ""), "url": "/events"})
    tasks = await db.tasks.find({"$or": [{"title": pattern}, {"description": pattern}]}, {"_id": 0, "id": 1, "title": 1, "status": 1, "priority": 1}).limit(5).to_list(5)
    for t in tasks:
        results.append({"type": "task", "id": t["id"], "title": t["title"], "subtitle": f"{t.get('status', '')} · {t.get('priority', '')}", "url": "/tasks"})
    products = await db.products.find({"name": pattern}, {"_id": 0, "id": 1, "name": 1, "price": 1, "stock": 1}).limit(3).to_list(3)
    for p in products:
        results.append({"type": "product", "id": p["id"], "title": p["name"], "subtitle": f"UGX {p.get('price', 0):,.0f} · Stock: {p.get('stock', 0)}", "url": "/sales"})
    return {"results": results}


# ========== EXPORTS ==========

@router.get("/export/members")
async def export_members_csv(current_user: dict = Depends(get_current_user)):
    members = await db.members.find({}, {"_id": 0}).sort("name", 1).to_list(5000)
    output = io.StringIO()
    fields = ["id", "name", "email", "phone", "national_id", "role", "group", "gender", "status", "join_date"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for m in members:
        writer.writerow({k: m.get(k, "") for k in fields})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=members.csv"})

@router.get("/export/financial")
async def export_financial_csv(current_user: dict = Depends(get_current_user)):
    donations = await db.donations.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["=== DONATIONS ==="])
    writer.writerow(["ID", "Donor", "Amount", "Currency", "Type", "Date"])
    for d in donations:
        writer.writerow([d.get("id"), d.get("donor_name"), d.get("amount"), d.get("currency"), d.get("type"), d.get("date")])
    writer.writerow([])
    writer.writerow(["=== EXPENSES ==="])
    writer.writerow(["ID", "Title", "Amount", "Currency", "Category", "Date"])
    for e in expenses:
        writer.writerow([e.get("id"), e.get("title"), e.get("amount"), e.get("currency"), e.get("category"), e.get("date")])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=financial.csv"})

@router.get("/export/events")
async def export_events_csv(current_user: dict = Depends(get_current_user)):
    events = await db.events.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    output = io.StringIO()
    fields = ["id", "title", "type", "date", "time", "location", "capacity", "registered", "status", "is_public"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for e in events:
        writer.writerow({k: e.get(k, "") for k in fields})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=events.csv"})

@router.get("/export/events.ics")
async def export_ical(current_user: dict = Depends(get_current_user)):
    events = await db.events.find({}, {"_id": 0}).sort("date", 1).to_list(500)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//58:12 Global Connect//CRM//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for e in events:
        date_str = e.get("date", ""); time_str = e.get("time", "00:00"); end_time_str = e.get("end_time", time_str)
        try:
            dt = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M")
            dt_end = datetime.strptime(f"{date_str}T{end_time_str}", "%Y-%m-%dT%H:%M")
            dtstart = dt.strftime("%Y%m%dT%H%M%S"); dtend = dt_end.strftime("%Y%m%dT%H%M%S")
        except Exception:
            dtstart = date_str.replace("-", "") + "T000000"; dtend = dtstart
        summary = e.get("title", "Event").replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")
        desc = e.get("description", "").replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")
        location = e.get("location", "").replace(",", "\\,")
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@5812global.org", f"SUMMARY:{summary}", f"DTSTART:{dtstart}", f"DTEND:{dtend}", f"DESCRIPTION:{desc}", f"LOCATION:{location}", f"STATUS:{'CONFIRMED' if e.get('status') == 'upcoming' else 'COMPLETED'}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return StreamingResponse(iter(["\r\n".join(lines)]), media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=5812global-events.ics"})
