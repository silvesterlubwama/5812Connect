"""Staff/Member Self-Service Portal — scoped to logged-in user's own data"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger, get_campus_filter
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("/dashboard")
async def portal_dashboard(current_user: dict = Depends(get_current_user)):
    """Overview stats for the logged-in user"""
    uid = current_user["id"]
    email = current_user.get("email", "")

    # Find linked member record
    member = await db.members.find_one(
        {"$or": [{"email": email}, {"created_by": uid}]},
        {"_id": 0, "id": 1, "name": 1}
    ) if email else None
    member_id = member["id"] if member else uid

    # My tasks
    my_tasks = await db.tasks.find(
        {"$or": [
            {"assignees": {"$in": [uid, email, current_user.get("name", "")]}},
            {"assignee": {"$in": [uid, email, current_user.get("name", "")]}},
            {"created_by": uid},
        ]},
        {"_id": 0}
    ).to_list(200)
    tasks_todo = sum(1 for t in my_tasks if t.get("status") == "todo")
    tasks_progress = sum(1 for t in my_tasks if t.get("status") == "in-progress")
    tasks_done = sum(1 for t in my_tasks if t.get("status") == "done")

    # My expenses
    my_expenses = await db.expenses.find(
        {"created_by": uid}, {"_id": 0, "amount": 1, "status": 1}
    ).to_list(200)
    total_expenses = sum(e.get("amount", 0) for e in my_expenses)
    pending_expenses = sum(1 for e in my_expenses if e.get("status") == "pending")

    # My check-ins
    recent_checkins = await db.checkins.find(
        {"$or": [{"member_id": member_id}, {"member_name": current_user.get("name", "")}]},
        {"_id": 0}
    ).sort("check_in_time", -1).limit(5).to_list(5)

    # My upcoming events (scoped to user's campus)
    now_str = datetime.now(timezone.utc).isoformat()[:10]
    event_query = {"date": {"$gte": now_str}, "status": "upcoming"}
    campus = await get_campus_filter(current_user)
    if campus:
        event_query.update(campus)
    upcoming_events = await db.events.find(
        event_query, {"_id": 0}
    ).sort("date", 1).limit(5).to_list(5)

    # Unread messages
    my_conversations = await db.conversations.find(
        {"participants": uid}, {"_id": 0, "id": 1}
    ).to_list(50)
    conv_ids = [c["id"] for c in my_conversations]
    unread_count = 0
    if conv_ids:
        unread_count = await db.chat_messages.count_documents({
            "conversation_id": {"$in": conv_ids},
            "sender_id": {"$ne": uid},
            "read_by": {"$not": {"$elemMatch": {"$eq": uid}}}
        })

    return {
        "member_id": member_id,
        "tasks": {"total": len(my_tasks), "todo": tasks_todo, "in_progress": tasks_progress, "done": tasks_done},
        "expenses": {"total_amount": total_expenses, "count": len(my_expenses), "pending": pending_expenses},
        "recent_checkins": recent_checkins,
        "upcoming_events": upcoming_events,
        "unread_messages": unread_count,
    }


@router.get("/profile")
async def portal_profile(current_user: dict = Depends(get_current_user)):
    """Get the logged-in user's profile + linked member record"""
    email = current_user.get("email", "")
    member = await db.members.find_one({"email": email}, {"_id": 0}) if email else None
    user_out = {k: v for k, v in current_user.items() if k not in ("password_hash", "_id")}
    return {"user": user_out, "member": member}


@router.put("/profile")
async def update_portal_profile(data: dict, current_user: dict = Depends(get_current_user)):
    """Update own profile fields (phone, address, emergency_contact, notes)"""
    allowed = {"phone", "address", "emergency_contact", "notes", "name"}
    update = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Update user record
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": current_user["id"]}, {"$set": update})

    # Also update linked member record
    email = current_user.get("email", "")
    if email:
        await db.members.update_one({"email": email}, {"$set": update})

    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "password_hash": 0})
    return user


@router.post("/my-wallet-badge")
async def portal_issue_own_badge(current_user: dict = Depends(get_current_user)):
    """Self-service: issue/return the caller's own wallet badge token so they
    can view + download it from the user portal. Idempotent — reuses an existing
    active badge if there is one. Works whether the user is linked to a members
    row or is just a bare user account."""
    uid = current_user["id"]
    email = (current_user.get("email") or "").strip().lower()
    # Prefer the linked members row (has photo/dept/role); fall back to the user
    member = None
    if email:
        member = await db.members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not member:
        member = await db.members.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
    subject_id = member["id"] if member else uid
    subject = member or current_user
    existing = await db.wallet_badges.find_one(
        {"member_id": subject_id, "status": {"$ne": "invalidated"}}, {"_id": 0},
    )
    if existing:
        return existing
    token = uuid.uuid4().hex[:16]
    loc = await db.locations.find_one(
        {"id": subject.get("location_id") or subject.get("active_campus_id") or ""},
        {"_id": 0, "name": 1, "country": 1, "country_code": 1},
    ) if (subject.get("location_id") or subject.get("active_campus_id")) else None
    badge = {
        "id": f"wbadge_{token}", "token": token,
        "member_id": subject_id,
        "name": subject.get("name", ""),
        "role": subject.get("role", subject.get("membership_type", "")),
        "title": subject.get("title", ""),
        "department": subject.get("department", ""),
        "photo_url": subject.get("photo_url", ""),
        "location_name": loc.get("name") if loc else "",
        "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
        "qr_data": subject_id,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": uid,
        "self_issued": True,
    }
    await db.wallet_badges.update_one({"member_id": subject_id}, {"$set": badge}, upsert=True)
    return badge


@router.post("/children/{child_id}/wallet-badge")
async def portal_issue_child_badge(child_id: str, current_user: dict = Depends(get_current_user)):
    """Self-service: parents issue a wallet badge for their own child.
    Auth: `current_user.id` must appear in `child.parent_ids`. Idempotent."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    parent_ids = child.get("parent_ids") or []
    if current_user["id"] not in parent_ids:
        # Also allow if the parent's members.id is listed
        m = await db.members.find_one({"user_id": current_user["id"]}, {"_id": 0, "id": 1})
        if not (m and m["id"] in parent_ids):
            raise HTTPException(status_code=403, detail="Only a listed parent can issue this child's badge")
    existing = await db.wallet_badges.find_one(
        {"member_id": child_id, "status": {"$ne": "invalidated"}}, {"_id": 0},
    )
    if existing:
        return existing
    token = uuid.uuid4().hex[:16]
    loc = await db.locations.find_one({"id": child.get("location_id", "")}, {"_id": 0, "name": 1, "country": 1, "country_code": 1, "contact_phone": 1}) if child.get("location_id") else None
    parents_summary = []
    for pid in parent_ids:
        p = await db.users.find_one({"id": pid}, {"_id": 0, "name": 1, "phone": 1})
        if not p:
            p = await db.members.find_one({"id": pid}, {"_id": 0, "name": 1, "phone": 1})
        if p:
            parents_summary.append({"name": p.get("name", ""), "phone": p.get("phone", "")})
    badge = {
        "id": f"wbadge_{token}", "token": token,
        "member_id": child_id, "name": child.get("name", ""), "role": "Child",
        "photo_url": child.get("photo_url", ""),
        "location_name": loc.get("name") if loc else "",
        "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
        "qr_data": child_id, "parents": parents_summary,
        "campus_phone": loc.get("contact_phone") if loc else "",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "self_issued": True,
    }
    await db.wallet_badges.update_one({"member_id": child_id}, {"$set": badge}, upsert=True)
    return badge


@router.get("/tasks")
async def portal_tasks(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get tasks assigned to the current user"""
    uid = current_user["id"]
    name = current_user.get("name", "")
    email = current_user.get("email", "")
    query = {"assignee": {"$in": [uid, email, name]}}
    if status:
        query["status"] = status
    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return tasks


@router.put("/tasks/{task_id}/status")
async def update_portal_task_status(task_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update task status (only if assigned to me)"""
    uid = current_user["id"]
    name = current_user.get("name", "")
    email = current_user.get("email", "")
    task = await db.tasks.find_one(
        {"id": task_id, "assignee": {"$in": [uid, email, name]}},
        {"_id": 0}
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
    new_status = data.get("status")
    if new_status not in ("todo", "in-progress", "done"):
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.tasks.update_one({"id": task_id}, {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return updated


@router.get("/expenses")
async def portal_expenses(current_user: dict = Depends(get_current_user)):
    """Get expenses submitted by the current user"""
    expenses = await db.expenses.find(
        {"created_by": current_user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return expenses


@router.post("/expenses")
async def create_portal_expense(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a new expense"""
    title = data.get("title", "").strip()
    amount = float(data.get("amount", 0))
    if not title or amount <= 0:
        raise HTTPException(status_code=400, detail="Title and positive amount required")
    expense = {
        "id": f"exp_{str(uuid.uuid4())[:8]}",
        "title": title,
        "amount": amount,
        "currency": data.get("currency", "UGX"),
        "category": data.get("category", "general"),
        "date": data.get("date", datetime.now(timezone.utc).isoformat()[:10]),
        "notes": data.get("notes", ""),
        "status": "pending",
        "submitted_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.expenses.insert_one(expense)
    expense.pop("_id", None)
    await _audit(current_user["id"], "create", "expense", expense["id"])
    return expense


@router.post("/cash-request")
async def submit_cash_request(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a cash request — creates an expense record + sends chat message to admins"""
    amount = float(data.get("amount", 0))
    reason = data.get("reason", "").strip()
    if amount <= 0 or not reason:
        raise HTTPException(status_code=400, detail="Amount and reason required")

    # Create pending expense
    expense_id = f"exp_{str(uuid.uuid4())[:8]}"
    expense = {
        "id": expense_id,
        "title": f"Cash Request: {reason}",
        "amount": amount,
        "currency": data.get("currency", "UGX"),
        "category": "cash_request",
        "date": datetime.now(timezone.utc).isoformat()[:10],
        "notes": f"Cash request by {current_user.get('name', '')}. Reason: {reason}",
        "status": "pending",
        "is_cash_request": True,
        "submitted_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.expenses.insert_one(expense)
    expense.pop("_id", None)

    # Send chat message to admin conversation (find or create)
    admin_users = await db.users.find(
        {"role": {"$in": ["admin", "system_admin"]}},
        {"_id": 0, "id": 1}
    ).to_list(10)
    admin_ids = [a["id"] for a in admin_users]

    if admin_ids:
        participants = list(set([current_user["id"]] + admin_ids))
        # Find existing cash request conversation or create one
        conv = await db.conversations.find_one({
            "type": "cash_requests",
            "participants": {"$all": [current_user["id"]]}
        }, {"_id": 0})
        if not conv:
            conv_id = f"conv_{str(uuid.uuid4())[:8]}"
            conv = {
                "id": conv_id,
                "name": f"Cash Requests — {current_user.get('name', '')}",
                "type": "cash_requests",
                "participants": participants,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.conversations.insert_one(conv)
        else:
            conv_id = conv["id"]

        # Post the message
        msg = {
            "id": f"msg_{str(uuid.uuid4())[:8]}",
            "conversation_id": conv_id,
            "sender_id": current_user["id"],
            "sender_name": current_user.get("name", ""),
            "text": f"Cash Request: {amount:,.0f} {expense.get('currency', 'UGX')}\nReason: {reason}\nExpense ID: {expense_id}",
            "type": "cash_request",
            "read_by": [current_user["id"]],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.chat_messages.insert_one(msg)

    await _audit(current_user["id"], "create", "cash_request", expense_id)
    return {"expense": expense, "message": "Cash request submitted and admins notified"}


@router.get("/events")
async def portal_events(current_user: dict = Depends(get_current_user)):
    """Upcoming events"""
    now_str = datetime.now(timezone.utc).isoformat()[:10]
    events = await db.events.find(
        {"date": {"$gte": now_str}}, {"_id": 0}
    ).sort("date", 1).to_list(50)
    return events


@router.post("/events/{event_id}/rsvp")
async def portal_event_rsvp(event_id: str, current_user: dict = Depends(get_current_user)):
    """RSVP to an event"""
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    attendees = event.get("attendees", [])
    if current_user["id"] in attendees:
        return {"message": "Already registered", "event": event}
    await db.events.update_one(
        {"id": event_id},
        {"$push": {"attendees": current_user["id"]}, "$inc": {"registered": 1}}
    )
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    return {"message": "RSVP confirmed", "event": event}


@router.get("/checkins")
async def portal_checkins(current_user: dict = Depends(get_current_user)):
    """My check-in/access history"""
    email = current_user.get("email", "")
    member = await db.members.find_one({"email": email}, {"_id": 0, "id": 1}) if email else None
    member_id = member["id"] if member else current_user["id"]

    checkins = await db.checkins.find(
        {"$or": [{"member_id": member_id}, {"member_name": current_user.get("name", "")}]},
        {"_id": 0}
    ).sort("check_in_time", -1).limit(50).to_list(50)

    access_logs = await db.access_logs.find(
        {"member_id": member_id}, {"_id": 0}
    ).sort("timestamp", -1).limit(50).to_list(50)

    return {"checkins": checkins, "access_logs": access_logs}


@router.get("/documents")
async def portal_documents(current_user: dict = Depends(get_current_user)):
    """My documents — returns docs + pending requests for the logged-in member"""
    email = current_user.get("email", "")
    member = await db.members.find_one({"email": email}, {"_id": 0, "id": 1}) if email else None
    member_id = member["id"] if member else current_user["id"]

    docs = await db.files.find(
        {"member_id": member_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    requests = await db.document_requests.find(
        {"member_id": member_id}, {"_id": 0}
    ).sort("requested_at", -1).to_list(50)
    return {"documents": docs, "requests": requests, "member_id": member_id}


@router.post("/documents/upload")
async def portal_upload_document(
    file = None,
    doc_type: str = None,
    request_id: str = None,
    current_user: dict = Depends(get_current_user),
):
    """Portal self-upload — handled by /api/members/{id}/documents in documents router"""
    from fastapi import UploadFile, File, Form
    raise HTTPException(status_code=405, detail="Use /api/members/{member_id}/documents for uploads")


@router.get("/sales")
async def portal_sales(current_user: dict = Depends(get_current_user)):
    """Sales I created"""
    sales = await db.sales.find(
        {"created_by": current_user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return sales
