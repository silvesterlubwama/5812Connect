"""Dashboard, action items, people stats, parent portal. Extracted from server.py."""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from deps import db, get_current_user, is_system_admin, get_campus_filter
from typing import Optional

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/stats")
async def get_dashboard_stats(campus_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start_str = now.replace(day=1).isoformat()[:7]
    if campus_id and is_system_admin(current_user):
        campus = {"location_id": campus_id}
    else:
        campus = await get_campus_filter(current_user)
    total_members = await db.members.count_documents({**campus})
    active_members = await db.members.count_documents({"status": "active", **campus})
    total_families = await db.families.count_documents({**campus})
    total_children = await db.children.count_documents({**campus})
    events_this_month = await db.events.count_documents({"date": {"$regex": f"^{month_start_str}"}, **campus})
    upcoming_events = await db.events.count_documents({"status": "upcoming", **campus})
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    checkins_today = await db.checkins.count_documents({"check_in_time": {"$gte": today_start}, **campus})
    now_str = now.isoformat()[:10]
    # iter 257c/d — scope task counters to visible boards (see /action-items).
    _uid = current_user.get("id")
    _stats_and = [
        {"is_archived": {"$ne": True}},
        {"$or": [
            {"is_restricted": {"$ne": True}, "is_private": {"$ne": True}},
            {"tagged_members": _uid},
            {"created_by": _uid},
        ]},
    ]
    if campus:
        _stats_and.append(campus)
    _board_ids_a = await db.boards.distinct("id", {"$and": _stats_and})
    tasks_overdue = 0 if not _board_ids_a else await db.tasks.count_documents({
        "status": {"$nin": ["done"]},
        "is_archived": {"$ne": True},
        "board_id": {"$in": _board_ids_a},
        "due_date": {"$lt": now_str, "$ne": ""},
    })
    new_members_this_month = await db.members.count_documents({"join_date": {"$regex": f"^{month_start_str}"}, **campus})
    sales_result = await db.sales.aggregate([{"$match": {"created_at": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    monthly_sales = sales_result[0]["total"] if sales_result else 0
    donations_result = await db.donations.aggregate([{"$match": {"date": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    monthly_donations = donations_result[0]["total"] if donations_result else 0
    low_stock = await db.products.count_documents({"$expr": {"$lte": ["$stock", "$reorder_level"]}, **campus})
    recent_checkins = await db.checkins.find({**campus}, {"_id": 0}).sort("check_in_time", -1).limit(3).to_list(3)
    recent_members = await db.members.find({**campus}, {"_id": 0}).sort("created_at", -1).limit(2).to_list(2)
    activity = []
    for ci in recent_checkins:
        activity.append({"type": "checkin", "message": f"{ci.get('member_name')} checked in" + (f" to {ci.get('event_name', '')}" if ci.get('event_name') else ""), "time": ci.get("check_in_time", "")})
    for m in recent_members:
        activity.append({"type": "member", "message": f"New member: {m.get('name')} registered", "time": m.get("created_at", "")})
    activity.sort(key=lambda x: x.get("time", ""), reverse=True)
    expenses_result = await db.expenses.aggregate([{"$match": {"date": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    monthly_expenses = expenses_result[0]["total"] if expenses_result else 0
    return {
        "total_members": total_members, "active_members": active_members, "total_families": total_families,
        "total_children": total_children, "events_this_month": events_this_month, "upcoming_events": upcoming_events,
        "checkins_today": checkins_today, "tasks_overdue": tasks_overdue, "new_members_this_month": new_members_this_month,
        "monthly_sales": monthly_sales, "monthly_donations": monthly_donations, "low_stock_count": low_stock,
        "monthly_expenses": monthly_expenses, "recent_activity": activity[:5],
    }


@router.get("/dashboard/action-items")
async def get_action_items(campus_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Return counts of items needing attention for dashboard widgets."""
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()[:10]
    if campus_id and is_system_admin(current_user):
        campus = {"location_id": campus_id}
    else:
        campus = await get_campus_filter(current_user)

    # iter 257c/d — task counters now scope to boards the current user can
    # actually see. Previous versions leaked archived/other-campus tasks and
    # (after the restricted/private fix) collided with the campus $or via
    # duplicate top-level $or keys — the fix wraps campus + visibility in
    # $and so they compose safely.
    user_id = current_user.get("id")
    _and = [
        {"is_archived": {"$ne": True}},
        {"$or": [
            {"is_restricted": {"$ne": True}, "is_private": {"$ne": True}},
            {"tagged_members": user_id},
            {"created_by": user_id},
        ]},
    ]
    if campus:
        _and.append(campus)
    board_ids = await db.boards.distinct("id", {"$and": _and})
    if not board_ids:
        return {"overdue_tasks": 0, "pending_approvals": await db.users.count_documents({"status": "pending", **campus}), "expiring_passes": 0, "unassigned_tasks": 0}
    task_scope = {
        "status": {"$nin": ["done"]},
        "is_archived": {"$ne": True},
        "board_id": {"$in": board_ids},
    }

    overdue_tasks = await db.tasks.count_documents({
        **task_scope,
        "due_date": {"$lt": now_str, "$ne": "", "$exists": True},
    })

    pending_approvals = await db.users.count_documents({"status": "pending", **campus})

    week_from_now = (now + timedelta(days=7)).isoformat()[:10]
    expiring_passes = 0
    try:
        expiring_passes = await db.guests.count_documents({
            "expires_at": {"$lte": week_from_now, "$gte": now_str, "$exists": True, "$ne": ""},
            **campus,
        })
        expiring_access = await db.access_guest_passes.count_documents({
            "valid_until": {"$lte": week_from_now, "$gte": now_str},
            "status": "active",
        })
        expiring_passes += expiring_access
    except Exception:
        pass

    unassigned_tasks = await db.tasks.count_documents({
        **task_scope,
        "$or": [
            {"assignees": {"$size": 0}},
            {"assignees": {"$exists": False}},
            {"assignees": None},
        ],
    })

    return {
        "overdue_tasks": overdue_tasks,
        "pending_approvals": pending_approvals,
        "expiring_passes": expiring_passes,
        "unassigned_tasks": unassigned_tasks,
    }


@router.get("/people/stats")
async def people_stats(current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    return {
        "total_members": await db.members.count_documents({**campus}),
        "active_members": await db.members.count_documents({"status": "active", **campus}),
        "total_families": await db.families.count_documents({**campus}),
        "total_children": await db.children.count_documents({**campus}),
        "total_guests": await db.guests.count_documents({**campus}),
        "pending_approvals": await db.users.count_documents({"status": "pending", **campus}),
    }


@router.get("/parent/children")
async def get_parent_children(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user_email = current_user.get("email", "")
    children = await db.children.find(
        {"$or": [{"parent_id": user_id}, {"parent_email": user_email}]},
        {"_id": 0}
    ).to_list(50)
    enriched = []
    for child in children:
        last_checkin = await db.checkins.find_one(
            {"member_id": child.get("id", ""), "member_name": child.get("name", "")},
            {"_id": 0, "check_in_time": 1, "event_name": 1},
            sort=[("check_in_time", -1)]
        )
        enriched.append({**child, "last_checkin": last_checkin})
    return enriched


@router.get("/parent/dashboard")
async def parent_dashboard(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user_email = current_user.get("email", "")
    children = await db.children.find(
        {"$or": [{"parent_id": user_id}, {"parent_email": user_email}]},
        {"_id": 0}
    ).to_list(50)
    upcoming_events = await db.events.find(
        {"status": "upcoming", "is_public": True},
        {"_id": 0, "id": 1, "title": 1, "date": 1, "time": 1, "location": 1, "type": 1}
    ).sort("date", 1).limit(5).to_list(5)
    return {"children": children, "children_count": len(children), "checked_in_count": 0, "upcoming_events": upcoming_events}
