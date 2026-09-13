"""Staff/Member Self-Service Portal — scoped to logged-in user's own data"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger, get_campus_filter
from datetime import datetime, timezone
from typing import Optional
import re
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
    """Update own profile fields. Whitelisted: contact info + basic identity."""
    allowed = {"phone", "address", "emergency_contact", "notes", "name",
               "date_of_birth", "dob", "birthday", "gender", "emergency_phone",
               "address_line2", "city", "country"}
    update = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Normalise DOB aliases → date_of_birth
    for alias in ("dob", "birthday"):
        if alias in update and "date_of_birth" not in update:
            update["date_of_birth"] = update.pop(alias)
        else:
            update.pop(alias, None)

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
    # A photo (or a rename, or a transfer) that lands AFTER the badge was first
    # minted must show up on the badge. The old code returned the stored
    # snapshot untouched, which is why a photo visible on the dashboard was
    # missing from the badge tab.
    live = await _badge_display_fields(subject, uid)
    existing = await db.wallet_badges.find_one(
        {"member_id": subject_id, "status": {"$ne": "invalidated"}}, {"_id": 0},
    )
    if existing:
        drifted = {k: v for k, v in live.items() if v and existing.get(k) != v}
        if drifted:
            await db.wallet_badges.update_one({"member_id": subject_id}, {"$set": drifted})
            existing.update(drifted)
        return existing
    token = uuid.uuid4().hex[:16]
    badge = {
        "id": f"wbadge_{token}", "token": token,
        "member_id": subject_id,
        **live,
        "qr_data": subject_id,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": uid,
        "self_issued": True,
    }
    await db.wallet_badges.update_one({"member_id": subject_id}, {"$set": badge}, upsert=True)
    return badge


async def _badge_display_fields(subject: dict, uid: str) -> dict:
    """The parts of a badge that can change after it's issued."""
    loc_id = subject.get("location_id") or subject.get("active_campus_id") or ""
    loc = await db.locations.find_one(
        {"id": loc_id}, {"_id": 0, "name": 1, "country": 1, "country_code": 1},
    ) if loc_id else None
    photo = subject.get("photo_url") or subject.get("picture") or ""
    if not photo:
        # Photos are uploaded against either record; check the other one.
        other = await db.users.find_one({"id": uid}, {"_id": 0, "photo_url": 1, "picture": 1})
        if not (other and (other.get("photo_url") or other.get("picture"))):
            other = await db.members.find_one(
                {"$or": [{"user_id": uid}, {"id": subject.get("id", "")}]},
                {"_id": 0, "photo_url": 1},
            )
        photo = (other or {}).get("photo_url") or (other or {}).get("picture") or ""
    return {
        "name": subject.get("name", ""),
        "role": subject.get("role", subject.get("membership_type", "")),
        "title": subject.get("title", ""),
        "department": subject.get("department", ""),
        "photo_url": photo,
        "location_name": loc.get("name") if loc else "",
        "country": loc.get("country") if loc else "",
        "country_code": loc.get("country_code") if loc else "",
    }


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
        # Keep the child's photo/name current — see _badge_display_fields note.
        drift = {k: v for k, v in
                 {"name": child.get("name", ""), "photo_url": child.get("photo_url", "")}.items()
                 if v and existing.get(k) != v}
        if drift:
            await db.wallet_badges.update_one({"member_id": child_id}, {"$set": drift})
            existing.update(drift)
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


def _assignee_match(current_user: dict) -> dict:
    """Match a task to the caller however it was assigned.

    Boards write the multi-assignee array `assignees`; older/imported cards use
    the singular `assignee`. The portal only checked the singular field, so
    anyone assigned through the Kanban board saw an empty Tasks tab.
    """
    ids = [v for v in (
        current_user.get("id"),
        (current_user.get("email") or "").strip(),
        (current_user.get("name") or "").strip(),
    ) if v]
    return {"$or": [{"assignees": {"$in": ids}}, {"assignee": {"$in": ids}}]}


@router.get("/tasks")
async def portal_tasks(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Tasks assigned to the caller — archived cards are never shown."""
    query = {**_assignee_match(current_user), "is_archived": {"$ne": True}}
    if status:
        query["status"] = status
    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    board_ids = list({t.get("board_id") for t in tasks if t.get("board_id")})
    boards = {}
    if board_ids:
        async for b in db.boards.find({"id": {"$in": board_ids}}, {"_id": 0, "id": 1, "name": 1}):
            boards[b["id"]] = b.get("name", "")
    for t in tasks:
        t["board_name"] = boards.get(t.get("board_id"), "")
    return tasks


@router.put("/tasks/{task_id}/status")
async def update_portal_task_status(task_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update task status (only if assigned to me)"""
    task = await db.tasks.find_one(
        {"id": task_id, **_assignee_match(current_user)},
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
    """My expense claims — including receipts I uploaded.

    A scanned receipt posts straight to the ledger as a journal entry, so it
    never appeared in My Expenses and the total under-reported what the person
    had actually spent (iter350). Those now show up as rows with the same
    shape, flagged `source: 'receipt'`.
    """
    uid = current_user["id"]
    expenses = await db.expenses.find(
        {"created_by": uid}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    receipts = await db.finance_journal_entries.find(
        {"source": "receipt_scan", "reversed": {"$ne": True},
         "$or": [{"uploaded_by": uid}, {"created_by": uid}]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    for je in receipts:
        expenses.append({
            "id": je["id"],
            "title": je.get("receipt_vendor") or je.get("description") or "Receipt",
            "amount": float(je.get("total") or 0),
            "currency": je.get("currency", "UGX"),
            "category": "receipt",
            "date": je.get("date"),
            "notes": je.get("description", ""),
            "status": "rejected" if je.get("rejected") else ("pending" if je.get("needs_review") else "approved"),
            "rejected_reason_label": je.get("rejected_reason_label"),
            "rejected_note": je.get("rejected_note"),
            "receipt_url": je.get("receipt_url"),
            "source": "receipt",
            "created_at": je.get("created_at"),
        })
    expenses.sort(key=lambda e: e.get("created_at") or "", reverse=True)
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
    """RSVP to an event — and issue a real, scannable pass.

    iter345: an RSVP used to only push the user id onto `events.attendees`,
    so nothing ever showed up in the ticket wallet or at the door. Now every
    RSVP creates a free `public_bookings` row plus its canonical
    `event_tickets` row, exactly like an auto-issued ticket.
    """
    import uuid as _uuid
    from routers.event_tickets import ensure_ticket_row

    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    email = (current_user.get("email") or "").strip().lower()

    existing = await db.public_bookings.find_one(
        {"event_id": event_id, "auto_member_id": current_user["id"], "status": {"$ne": "cancelled"}},
        {"_id": 0},
    )
    if existing:
        return {"message": "Already registered", "event": event,
                "ticket_ids": existing.get("ticket_ids") or []}

    capacity = int(event.get("capacity") or 0)
    if capacity and int(event.get("registered") or 0) >= capacity:
        raise HTTPException(status_code=409, detail="This event is full")

    ticket_id = f"TKT-{_uuid.uuid4().hex[:4].upper()}"
    booking = {
        "id": f"book_{_uuid.uuid4().hex[:12]}",
        "event_id": event_id,
        "event_title": event.get("title", ""),
        "name": current_user.get("name", ""),
        "email": email,
        "phone": current_user.get("phone", ""),
        "num_tickets": 1,
        "is_free": True, "price": 0, "total": 0,
        "payment_status": "paid", "status": "confirmed",
        "ticket_ids": [ticket_id],
        "auto_issued": True,
        "auto_member_id": current_user["id"],
        "source": "portal_rsvp",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    await ensure_ticket_row(
        ticket_id, event,
        holder_name=current_user.get("name", ""),
        holder_person_id=current_user["id"], holder_email=email,
        holder_phone=current_user.get("phone", ""),
        booking_id=booking["id"], source="portal_rsvp",
    )
    await db.events.update_one(
        {"id": event_id},
        {"$addToSet": {"attendees": current_user["id"]}, "$inc": {"registered": 1}},
    )
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    return {"message": "RSVP confirmed — your pass is in My Tickets",
            "event": event, "ticket_ids": [ticket_id]}


@router.get("/checkins")
async def portal_checkins(current_user: dict = Depends(get_current_user)):
    """My check-in/access history, readable.

    Raw rows only carry `location_id` / `checkpoint_id`, so the portal used to
    show "Check-in · manual" with no idea WHERE it happened. Every row now
    carries a resolved campus name, the space/event it was for, and a
    normalised timestamp.
    """
    ids = await _my_identity_ids(current_user)
    name = current_user.get("name", "")

    checkins = await db.checkins.find(
        {"$or": [{"member_id": {"$in": ids}}, {"member_name": name}]}, {"_id": 0},
    ).sort("check_in_time", -1).limit(50).to_list(50)
    access_logs = await db.access_logs.find(
        {"$or": [{"member_id": {"$in": ids}}, {"person_id": {"$in": ids}}]}, {"_id": 0},
    ).sort("timestamp", -1).limit(50).to_list(50)

    loc_ids = {r.get("location_id") for r in (checkins + access_logs) if r.get("location_id")}
    event_ids = {r.get("event_id") for r in checkins if r.get("event_id")}
    locations, events = {}, {}
    if loc_ids:
        async for loc in db.locations.find({"id": {"$in": list(loc_ids)}}, {"_id": 0, "id": 1, "name": 1}):
            locations[loc["id"]] = loc.get("name", "")
    if event_ids:
        async for ev in db.events.find({"id": {"$in": list(event_ids)}}, {"_id": 0, "id": 1, "title": 1, "date": 1}):
            events[ev["id"]] = ev

    for c in checkins:
        ev = events.get(c.get("event_id"), {})
        c["location_name"] = locations.get(c.get("location_id")) or c.get("location_name") or ""
        c["event_title"] = ev.get("title") or c.get("event_name") or c.get("event_title") or ""
        c["when"] = c.get("check_in_time") or c.get("created_at") or ""
        c["label"] = c["event_title"] or (c.get("type") or "Check-in").replace("_", " ").title()
    for a in access_logs:
        a["location_name"] = locations.get(a.get("location_id")) or a.get("space_name") or ""
        a["when"] = a.get("timestamp") or a.get("created_at") or ""
        a["label"] = (a.get("action") or a.get("direction") or "Access").replace("_", " ").title()

    return {"checkins": checkins, "access_logs": access_logs}


async def _my_identity_ids(current_user: dict) -> list:
    """Every id this person is known by: user, member and guest rows.

    Tickets, check-ins and access logs are written against whichever record
    the staff member happened to be looking at, so a portal query on the user
    id alone misses anything issued against the member/guest row.
    """
    uid = current_user.get("id") or ""
    email = (current_user.get("email") or "").strip().lower()
    ids = [uid] if uid else []
    ors: list = []
    if uid:
        ors.append({"user_id": uid})
    if email:
        ors.append({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    if not ors:
        return ids
    for coll in (db.members, db.guests):
        async for row in coll.find({"$or": ors}, {"_id": 0, "id": 1}):
            if row["id"] not in ids:
                ids.append(row["id"])
    return ids


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


@router.get("/statement")
async def portal_statement(month: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Live monthly account statement for the caller — everything they bought
    from us (shop / POS) plus every event ticket, in one running list.

    `month` is `YYYY-MM`; defaults to the current month. Designed to be
    printed straight from the portal.
    """
    now = datetime.now(timezone.utc)
    month = (month or now.strftime("%Y-%m")).strip()[:7]
    try:
        year, mon = int(month[:4]), int(month[5:7])
        if not 1 <= mon <= 12:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="month must look like YYYY-MM")
    start = f"{year:04d}-{mon:02d}-01"
    end = f"{year + (mon == 12):04d}-{(mon % 12) + 1:02d}-01"

    uid = current_user["id"]
    email = (current_user.get("email") or "").strip().lower()
    name = (current_user.get("name") or "").strip()

    sale_or = [{"created_by": uid}, {"customer_id": uid}]
    if email:
        sale_or.append({"customer_email": email})
    if name:
        sale_or.append({"customer_name": name})
    sales = await db.sales.find(
        {"$or": sale_or, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0},
    ).sort("created_at", 1).to_list(500)

    lines = []
    charged = 0.0
    paid = 0.0
    # Sale line items only store product_id in some flows — resolve names once.
    prod_ids = list({i.get("product_id") for s in sales for i in (s.get("items") or []) if i.get("product_id")})
    prod_names: dict = {}
    if prod_ids:
        async for p in db.products.find({"id": {"$in": prod_ids}}, {"_id": 0, "id": 1, "name": 1}):
            prod_names[p["id"]] = p.get("name") or ""
    for s in sales:
        amount = float(s.get("total") or 0)
        is_paid = (s.get("payment_status") or "paid").lower() == "paid"
        charged += amount
        if is_paid:
            paid += amount
        lines.append({
            "date": (s.get("created_at") or "")[:10],
            "kind": "purchase",
            "reference": s.get("receipt_number") or s.get("id"),
            "description": ", ".join(
                f"{i.get('name') or prod_names.get(i.get('product_id')) or 'Item'}"
                f" × {i.get('qty') or i.get('quantity') or 1}"
                for i in (s.get("items") or [])
            ) or "Purchase",
            "channel": s.get("channel") or s.get("payment_method") or "",
            "amount": amount,
            "status": "Paid" if is_paid else (s.get("payment_status") or "pending").title(),
            "currency": s.get("currency") or "UGX",
        })

    from routers.event_tickets import ticket_flags_for
    for t in await ticket_flags_for([uid], email):
        row = await db.event_tickets.find_one({"id": t["ticket_id"]}, {"_id": 0, "created_at": 1, "price": 1, "booking_id": 1})
        issued = (row or {}).get("created_at") or ""
        if not (start <= issued[:10] < end):
            continue
        amount = float((row or {}).get("price") or 0)
        charged += amount
        paid += amount
        lines.append({
            "date": issued[:10],
            "kind": "ticket",
            "reference": t["ticket_id"],
            "description": f"Event ticket — {t['event_title']}" + (f" ({t['tier_name']})" if t.get("tier_name") else ""),
            "channel": "event",
            "amount": amount,
            "status": "Used" if t.get("used_at") else "Valid",
            "currency": "UGX",
        })

    lines.sort(key=lambda r: r["date"])
    return {
        "month": month,
        "period": {"start": start, "end": end},
        "holder": {"name": current_user.get("name"), "email": current_user.get("email")},
        "lines": lines,
        "totals": {"charged": round(charged, 2), "paid": round(paid, 2),
                   "outstanding": round(charged - paid, 2), "count": len(lines)},
        "currency": (lines[0]["currency"] if lines else "UGX"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/tickets")
async def portal_tickets(current_user: dict = Depends(get_current_user)):
    """Ticket wallet — every event ticket bought or auto-issued to the
    caller, plus enough event context (title/date/venue) to render a
    scannable pass. Consumed by `PortalTickets.jsx`.

    Matches on either `auto_member_id` (admin-issued tickets) or the
    caller's email (public checkout tickets). Tickets are flattened out
    of `public_bookings.ticket_ids[]` so each row is a scannable pass.
    """
    email = (current_user.get("email") or "").strip().lower()
    my_ids = await _my_identity_ids(current_user)
    match: list = [{"auto_member_id": {"$in": my_ids}}, {"member_id": {"$in": my_ids}}]
    if email:
        match.append({"email": email})
    bookings = await db.public_bookings.find(
        {"$or": match, "status": {"$ne": "cancelled"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(300)
    # Pull all events referenced so we can attach date/venue etc.
    event_ids = list({b["event_id"] for b in bookings if b.get("event_id")})
    events = {}
    if event_ids:
        async for ev in db.events.find(
            {"id": {"$in": event_ids}},
            {"_id": 0, "id": 1, "title": 1, "date": 1, "time": 1, "end_time": 1, "end_date": 1, "location": 1},
        ):
            events[ev["id"]] = ev
    # Redemption status (event_tickets rows track used/void)
    all_ticket_ids = [tid for b in bookings for tid in (b.get("ticket_ids") or [])]
    used_map = {}
    if all_ticket_ids:
        async for t in db.event_tickets.find(
            {"id": {"$in": all_ticket_ids}}, {"_id": 0, "id": 1, "status": 1, "used_at": 1},
        ):
            used_map[t["id"]] = {"status": t.get("status"), "used_at": t.get("used_at")}
    passes = []
    seen = set()
    for b in bookings:
        ev = events.get(b.get("event_id"), {}) or {}
        for tid in (b.get("ticket_ids") or [b.get("id")]):
            u = used_map.get(tid, {})
            seen.add(tid)
            passes.append({
                "ticket_id": tid,
                "booking_id": b.get("id"),
                "event_id": b.get("event_id"),
                "event_title": ev.get("title") or b.get("event_title", ""),
                "event_date": ev.get("date") or b.get("event_date", ""),
                "event_time": ev.get("time") or b.get("event_time", ""),
                "event_location": ev.get("location", ""),
                "holder_name": b.get("name"),
                "tier_name": b.get("tier_name"),
                "price": b.get("price") or 0,
                "currency": b.get("currency") or "UGX",
                "is_free": b.get("is_free", False),
                "auto_issued": b.get("auto_issued", False),
                "purchased_at": b.get("created_at"),
                "status": u.get("status") or ("used" if u.get("used_at") else "valid"),
                "used_at": u.get("used_at"),
            })
    # Tickets issued straight into `event_tickets` (POS / marketplace sales)
    # never had a public_bookings row — pull them in too (iter345). Matching on
    # every identity id, not just the user id: a ticket sold at the POS is
    # tagged with the member/guest row, so those were invisible here (iter349).
    from routers.event_tickets import ticket_flags_for
    for t in await ticket_flags_for(my_ids, email):
        if t["ticket_id"] in seen:
            continue
        seen.add(t["ticket_id"])
        passes.append({
            **t,
            "booking_id": None,
            "price": 0, "currency": "UGX", "is_free": True,
            "auto_issued": True, "purchased_at": None,
            "status": "used" if t.get("used_at") else (t.get("status") or "valid"),
        })
    # Access passes (guest/visitor day passes) live in their own collection but
    # belong in the same wallet — they're what door staff scan.
    async for gp in db.guest_passes.find(
        {"$or": [{"member_id": {"$in": my_ids}}, {"guest_id": {"$in": my_ids}},
                 {"guest_email": email}] if email else
                [{"member_id": {"$in": my_ids}}, {"guest_id": {"$in": my_ids}}],
         "status": {"$nin": ["revoked", "void"]}},
        {"_id": 0},
    ):
        pid = gp.get("id") or gp.get("code")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        passes.append({
            "ticket_id": pid,
            "booking_id": None,
            "event_id": None,
            "event_title": gp.get("space_name") or "Access pass",
            "event_date": (gp.get("valid_from") or "")[:10],
            "event_time": "",
            "event_location": gp.get("space_name") or "",
            "holder_name": gp.get("guest_name") or current_user.get("name", ""),
            "tier_name": "Access pass",
            "price": 0, "currency": "UGX", "is_free": True,
            "auto_issued": True,
            "purchased_at": gp.get("created_at"),
            "status": "used" if gp.get("used_at") else (gp.get("status") or "valid"),
            "used_at": gp.get("used_at"),
            "kind": "access_pass",
            "code": gp.get("code"),
            "valid_to": gp.get("valid_to"),
        })
    return passes


@router.get("/profile-pdf")
async def portal_profile_pdf(current_user: dict = Depends(get_current_user)):
    """My own profile as a PDF.

    The portal button used to call the staff-only
    `/api/members/{id}/profile-pdf` with the caller's USER id — so it 404'd on
    the id lookup, or 403'd for anyone who isn't staff. This resolves the
    caller's own member row (falling back to their user record) and renders the
    same document.
    """
    email = (current_user.get("email") or "").strip().lower()
    member = None
    if email:
        member = await db.members.find_one(
            {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0})
    if not member:
        member = await db.members.find_one({"user_id": current_user["id"]}, {"_id": 0})
    if not member:
        # No member row (bare staff account) — build one from the user record
        # so the download still works instead of erroring.
        member = {k: v for k, v in current_user.items() if k not in ("password_hash", "pin_hash", "_id")}
        member.setdefault("id", current_user["id"])
    from routers.members.pdf import render_member_profile_pdf
    return await render_member_profile_pdf(member)

