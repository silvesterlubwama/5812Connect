"""Analytics dashboard endpoints."""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from deps import get_current_user, db, get_campus_filter
from typing import Optional

router = APIRouter(prefix="/api")


@router.get("/analytics/overview")
async def analytics_overview(months: int = 12, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=months * 30)).isoformat()
    members = await db.members.count_documents({**get_campus_filter(current_user)})
    active = await db.members.count_documents({**get_campus_filter(current_user), "status": "active"})
    events_count = await db.events.count_documents({"date": {"$gte": start[:10]}})
    checkins = await db.check_ins.count_documents({"checked_in_at": {"$gte": start}})
    donations = await db.donations.find({"date": {"$gte": start[:7]}}, {"_id": 0, "amount": 1}).to_list(5000)
    expenses = await db.expenses.find({"date": {"$gte": start[:7]}}, {"_id": 0, "amount": 1}).to_list(5000)
    sales = await db.sales.find({"created_at": {"$gte": start}}, {"_id": 0, "total": 1}).to_list(5000)
    total_donations = sum(d.get("amount", 0) for d in donations)
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    total_sales = sum(s.get("total", 0) for s in sales)
    return {
        "members": {"total": members, "active": active, "inactive": members - active},
        "events": {"total": events_count},
        "checkins": {"total": checkins},
        "financial": {"donations": total_donations, "expenses": total_expenses, "sales": total_sales, "net": total_donations + total_sales - total_expenses},
    }


@router.get("/analytics/trends")
async def analytics_trends(months: int = 6, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    monthly = []
    for i in range(months - 1, -1, -1):
        dt = now - timedelta(days=i * 30)
        ym = dt.strftime("%Y-%m")
        label = dt.strftime("%b %Y")
        new_members = await db.members.count_documents({"created_at": {"$regex": f"^{ym}"}})
        checkins = await db.check_ins.count_documents({"checked_in_at": {"$regex": f"^{ym}"}})
        donations = await db.donations.find({"date": {"$regex": f"^{ym}"}}, {"_id": 0, "amount": 1}).to_list(5000)
        expenses = await db.expenses.find({"date": {"$regex": f"^{ym}"}}, {"_id": 0, "amount": 1}).to_list(5000)
        monthly.append({
            "month": label, "new_members": new_members, "checkins": checkins,
            "donations": sum(d.get("amount", 0) for d in donations),
            "expenses": sum(e.get("amount", 0) for e in expenses),
        })
    return {"monthly": monthly}


@router.get("/analytics/location-breakdown")
async def analytics_by_location(current_user: dict = Depends(get_current_user)):
    locations = await db.locations.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(50)
    result = []
    for loc in locations:
        lid = loc["id"]
        members = await db.members.count_documents({"location_id": lid})
        events = await db.events.count_documents({"location_id": lid})
        checkins = await db.check_ins.count_documents({"location_id": lid})
        result.append({"location_id": lid, "name": loc["name"], "members": members, "events": events, "checkins": checkins})
    return result


@router.get("/analytics/member-growth")
async def member_growth(months: int = 12, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    data = []
    cumulative = 0
    for i in range(months - 1, -1, -1):
        dt = now - timedelta(days=i * 30)
        ym = dt.strftime("%Y-%m")
        count = await db.members.count_documents({"created_at": {"$regex": f"^{ym}"}})
        cumulative += count
        data.append({"month": dt.strftime("%b"), "new": count, "cumulative": cumulative})
    return data


@router.get("/analytics/outreach-impact")
async def outreach_impact(current_user: dict = Depends(get_current_user)):
    programs = await db.outreach_programs.find({}, {"_id": 0}).to_list(100)
    total_reached = sum(p.get("total_reached", 0) for p in programs)
    total_sessions = sum(p.get("sessions_count", 0) for p in programs)
    return {"programs": len(programs), "total_sessions": total_sessions, "total_reached": total_reached, "programs_list": programs}
