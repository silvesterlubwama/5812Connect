"""Resources, Resource Types, Announcements, Analytics, Search, Export routes"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from deps import db, get_current_user, require_admin, require_manager, _audit, logger, is_system_admin, get_campus_filter
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import uuid, csv, io

router = APIRouter(prefix="/api", tags=["misc"])


def _can_issue_barcodes(user: dict) -> bool:
    """Only admins and directors can issue barcodes / serial numbers."""
    if is_system_admin(user):
        return True
    role = (user.get("role") or "").lower()
    return role in {"admin", "system_admin", "executive director", "director", "adviser"}


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
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None

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
    campus = await get_campus_filter(current_user)
    if campus:
        # Include resources from user's campus + unassigned (global) resources
        query = {"$or": []}
        if "$or" in campus:
            query["$or"].extend(campus["$or"])
        else:
            query["$or"].append(campus)
        # Also include resources with no location (global/unassigned)
        query["$or"].extend([{"location_id": {"$exists": False}}, {"location_id": None}, {"location_id": ""}])
    else:
        query = {}
    return await db.resources.find(query, {"_id": 0}).sort("name", 1).to_list(200)


# ---------- Serial / barcode helpers ----------

COUNTRY_TO_CODE = {
    "uganda": "UG", "kenya": "KE", "usa": "US", "united states": "US",
    "haiti": "HT", "thailand": "TH",
}


def _country_code(country: str) -> str:
    if not country:
        return "XX"
    return COUNTRY_TO_CODE.get(country.strip().lower(), country[:2].upper())


def _abbr(name: str) -> str:
    """Derive a 3-letter abbreviation from a name (e.g. 'Holmes County' → 'HCO')."""
    if not name:
        return "XXX"
    words = [w for w in name.replace(":", " ").replace("/", " ").split() if w and not w.isdigit()]
    if not words:
        return "XXX"
    if len(words) == 1:
        return words[0][:3].upper()
    return ("".join(w[0] for w in words[:3]) + words[-1][:1]).upper()[:3] or "XXX"


async def _generate_resource_serial(location_id: str = "") -> str:
    """Generate a 58:12 serial: 5812-{CCABBR}-{DDMMYY}-{NNNN}.
    Country code from location.country, abbr from location.code or derived from name.
    Sequence is per (loc_id, date) and stored in db.counters."""
    loc = None
    if location_id:
        loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "country": 1, "code": 1, "name": 1})
    country_code = _country_code(loc.get("country") if loc else "")
    if loc and loc.get("code"):
        abbr = _abbr(loc["code"])
    elif loc and loc.get("name"):
        abbr = _abbr(loc["name"])
    else:
        abbr = "XXX"
    today = datetime.now(timezone.utc)
    date_tag = today.strftime("%d%m%y")
    counter_key = f"resource_serial_{location_id or 'NOLOC'}_{date_tag}"
    counter = await db.counters.find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    return f"5812-{country_code}{abbr}-{date_tag}-{seq:04d}"


@router.get("/resource-types-distinct")
async def list_resource_types_distinct(current_user: dict = Depends(get_current_user)):
    """Return distinct resource types from existing resources (legacy autocomplete)."""
    types = await db.resources.distinct("type")
    return [t for t in types if t]


@router.post("/resources")
async def create_resource(data: ResourceCreate, current_user: dict = Depends(get_current_user)):
    # Only admins/directors may issue barcodes — but anyone can create a resource without one.
    user_can_issue = _can_issue_barcodes(current_user)
    doc = {"id": f"res_{str(uuid.uuid4())[:8]}", **data.model_dump(), "available": True, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    # Auto-issue serial number / barcode ONLY if the user is allowed to AND a location is set.
    if not doc.get("serial_number"):
        if user_can_issue and doc.get("location_id"):
            doc["serial_number"] = await _generate_resource_serial(doc["location_id"])
            doc["serial_auto_generated"] = True
            doc["barcode"] = doc["serial_number"]
        # else: leave serial blank — admin/director can issue later via /generate-serial
    else:
        doc["barcode"] = doc["serial_number"]
    await db.resources.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "resource", doc["id"])
    return doc


@router.put("/resources/{res_id}")
async def update_resource(res_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "type", "category", "capacity", "quantity", "description", "location_id",
               "hourly_rate", "is_bookable", "staff_only", "is_consumable", "available",
               "serial_number", "barcode", "purchase_date", "purchase_value", "condition", "owner"}
    update = {k: v for k, v in data.items() if k in allowed}
    # Only admins/directors can change the serial number after creation
    if "serial_number" in update or "barcode" in update:
        if not _can_issue_barcodes(current_user):
            raise HTTPException(status_code=403, detail="Only admins and directors can issue or change resource serial numbers / barcodes")
    if "serial_number" in update and update["serial_number"]:
        update["barcode"] = update["serial_number"]
        update["serial_auto_generated"] = False
    await db.resources.update_one({"id": res_id}, {"$set": update})
    return await db.resources.find_one({"id": res_id}, {"_id": 0})


@router.post("/resources/{res_id}/generate-serial")
async def generate_resource_serial(res_id: str, current_user: dict = Depends(get_current_user)):
    """Issue a fresh 58:12 serial / barcode for a resource — admins & directors only.
    The serial uses the RESOURCE'S location (NOT the issuing user's campus)."""
    if not _can_issue_barcodes(current_user):
        raise HTTPException(status_code=403, detail="Only admins and directors can issue resource serial numbers")
    res = await db.resources.find_one({"id": res_id}, {"_id": 0})
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")
    res_loc = res.get("location_id") or ""
    if not res_loc:
        raise HTTPException(
            status_code=400,
            detail="Set the resource's location/campus before issuing a serial — the barcode prefix derives from the resource's campus, not yours."
        )
    serial = await _generate_resource_serial(res_loc)
    await db.resources.update_one(
        {"id": res_id},
        {"$set": {"serial_number": serial, "barcode": serial, "serial_auto_generated": True,
                  "serial_issued_at": datetime.now(timezone.utc).isoformat(),
                  "serial_issued_by": current_user["id"]}}
    )
    await _audit(current_user["id"], "issue", "resource_serial", f"{res_id}:{serial}")
    return {"serial_number": serial, "barcode": serial, "location_id": res_loc}


@router.get("/resources/by-serial/{serial}")
async def get_resource_by_serial(serial: str):
    """Public lookup — used for barcode scanners. Returns resource details (sanitized)."""
    res = await db.resources.find_one(
        {"$or": [{"serial_number": serial}, {"barcode": serial}, {"id": serial}]},
        {"_id": 0}
    )
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")
    loc = None
    if res.get("location_id"):
        loc = await db.locations.find_one(
            {"id": res["location_id"]},
            {"_id": 0, "name": 1, "country": 1, "code": 1}
        )
    return {
        "id": res.get("id"),
        "serial_number": res.get("serial_number"),
        "barcode": res.get("barcode"),
        "name": res.get("name"),
        "type": res.get("type"),
        "category": res.get("category"),
        "description": res.get("description"),
        "quantity": res.get("quantity"),
        "available": res.get("available", True),
        "condition": res.get("condition"),
        "owner": res.get("owner"),
        "purchase_date": res.get("purchase_date"),
        "purchase_value": res.get("purchase_value"),
        "location": loc,
        "created_at": res.get("created_at"),
    }


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
    """List announcements — campus-specific + org-wide"""
    user_locs = current_user.get("location_ids") or []
    user_loc = current_user.get("location_id", "")
    all_locs = list(set(user_locs + ([user_loc] if user_loc else [])))
    # Show: org-wide (no location_id) + user's campus announcements
    query = {"$or": [
        {"location_id": {"$exists": False}}, {"location_id": None}, {"location_id": ""},
        {"scope": "organization"},
    ]}
    if all_locs:
        query["$or"].append({"location_id": {"$in": all_locs}})
    return await db.announcements.find(query, {"_id": 0}).sort([("pinned", -1), ("created_at", -1)]).to_list(100)

@router.post("/announcements")
async def create_announcement(data: AnnouncementCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"ann_{str(uuid.uuid4())[:8]}", **data.model_dump(),
        "author_name": current_user.get("name", "Admin"),
        "author_role": current_user.get("role", "admin"),
        "location_id": getattr(data, 'location_id', None) or current_user.get("location_id"),
        "scope": getattr(data, 'scope', 'campus'),  # campus or organization
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
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


# ========== UPLOADED FILES SERVING ==========

from fastapi.responses import FileResponse
import os

@router.get("/uploads/photos/{filename}")
async def serve_uploaded_photo(filename: str):
    """Serve locally stored profile photos."""
    filepath = f"/app/backend/uploads/photos/{filename}"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Photo not found")
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    ct = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'image/jpeg')
    return FileResponse(filepath, media_type=ct)


@router.get("/uploads/social-review-scans/{filename}")
async def serve_local_review_scan(filename: str):
    """Serve locally saved social-work review scans.

    We now save every uploaded scan to local disk FIRST (fast, no
    Cloudflare timeout) and try to swap in the cloud URL later. This
    endpoint keeps the local URL working even if the cloud upload is
    still in flight or has failed permanently.
    """
    # Defence-in-depth: strip any path traversal attempts.
    safe = os.path.basename(filename)
    filepath = f"/app/backend/uploads/social-review-scans/{safe}"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Scan not found")
    ext = safe.rsplit('.', 1)[-1].lower() if '.' in safe else 'pdf'
    ct = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'application/octet-stream')
    return FileResponse(filepath, media_type=ct)


@router.get("/uploads/security-company-logos/{filename}")
async def serve_local_security_logo(filename: str):
    """Serve locally saved security company logos (fallback when object
    storage is unavailable). Public — logos aren't sensitive."""
    safe = os.path.basename(filename)
    filepath = f"/app/backend/uploads/security-company-logos/{safe}"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Logo not found")
    ext = safe.rsplit('.', 1)[-1].lower() if '.' in safe else 'png'
    ct = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp', 'svg': 'image/svg+xml'}.get(ext, 'image/png')
    return FileResponse(filepath, media_type=ct)


@router.get("/storage/{full_path:path}")
async def serve_object_storage(full_path: str):
    """Proxy through Emergent object storage.

    Uploaders (profile photos, receipts, ID scans, shipment item photos,
    social-work review scans) fall back to `/api/storage/{path}` when the
    object-storage init call succeeded but didn't return a signed URL.
    Without this endpoint every `<img src="/api/storage/…">` in the app
    404s — which is why staff profile photos, printed ID badges, and
    social-work photo galleries were showing blank tiles.

    Public so <img>/print windows can load without auth headers; the
    object keys are UUID-scoped and treated as unguessable capability
    tokens (same pattern as `/api/uploads/photos/*` above).
    """
    try:
        from storage import get_object
        content, ct = get_object(full_path)
    except Exception as e:
        logger.warning(f"Object-storage fetch failed for {full_path}: {e}")
        raise HTTPException(status_code=404, detail="Object not found")
    return StreamingResponse(iter([content]), media_type=ct)
