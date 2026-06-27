"""Chat, AI Assistant, Offline Sync routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, logger, is_system_admin, get_campus_filter
from datetime import datetime, timezone
from typing import Optional
import uuid, os

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    query = {"participants": current_user["id"]}
    campus = await get_campus_filter(current_user)
    if campus:
        query["$or"] = [
            {"participants": current_user["id"]},
            {**campus, "participants": current_user["id"]},
        ]
        # Simplify: just filter by participant — conversations are already participant-scoped
        query = {"participants": current_user["id"]}
    convs = await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)
    # Filter out conversations hidden by this user
    uid = current_user["id"]
    return [c for c in convs if uid not in (c.get("hidden_by") or [])]


@router.get("/chat/users")
async def list_chat_users(current_user: dict = Depends(get_current_user)):
    """Return users that the current user can message — scoped to campus, staff-only,
    excluding soft-deleted accounts. Members/Customers/Guests cannot be DM'd from
    Comms because they don't have user accounts in the chat sense."""
    STAFF_ROLES = ["admin", "system_admin", "Executive Director", "Adviser", "Director",
                   "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer",
                   "Security Contractor"]
    campus = await get_campus_filter(current_user)
    base = {
        "status": "active",
        "role": {"$in": STAFF_ROLES},
        "id": {"$ne": current_user["id"]},
    }
    query = {"$and": [base, campus]} if campus else base
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(200)
    # Return only needed fields
    return [{"id": u.get("id"), "name": u.get("name"), "email": u.get("email"), "role": u.get("role"), "location_id": u.get("location_id")} for u in users]


@router.post("/chat/conversations")
async def create_conversation(data: dict, current_user: dict = Depends(get_current_user)):
    conv_type = data.get("type", "direct")
    participants = data.get("participants", [])
    if current_user["id"] not in participants:
        participants.append(current_user["id"])
    doc = {
        "id": f"conv_{str(uuid.uuid4())[:8]}", "type": conv_type, "name": data.get("name", ""),
        "participants": participants, "location_id": data.get("location_id"),
        "created_by": current_user["id"], "is_no_reply": data.get("is_no_reply", False),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(), "last_message": None,
    }
    await db.conversations.insert_one(doc); doc.pop("_id", None)
    return doc


@router.get("/chat/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, skip: int = 0, limit: int = 50, thread_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"conversation_id": conv_id}
    if thread_id:
        query["thread_id"] = thread_id
    else:
        # Top-level messages only (no thread_id or is the thread root)
        query["$or"] = [{"thread_id": {"$exists": False}}, {"thread_id": None}]
    msgs = await db.chat_messages.find(query, {"_id": 0}).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)
    # Attach thread reply counts for top-level messages
    if not thread_id:
        for m in msgs:
            count = await db.chat_messages.count_documents({"thread_id": m["id"]})
            if count > 0:
                m["thread_count"] = count
    return msgs


@router.post("/chat/conversations/{conv_id}/messages")
async def send_message(conv_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    text = data.get("text", "").strip()
    if not text: raise HTTPException(status_code=400, detail="Message text required")
    thread_id = data.get("thread_id")
    reply_to = data.get("reply_to")
    # Parse @mentions (allow client to pass parsed list OR detect from text)
    mentions = data.get("mentions") or []
    if not mentions:
        # Cheap fallback: extract @word tokens and try to resolve to participant names
        import re
        candidates = list(set(re.findall(r"@([\w'.-]+)", text)))
        if candidates:
            conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
            if conv and conv.get("participants"):
                participants = await db.users.find(
                    {"id": {"$in": conv["participants"]}},
                    {"_id": 0, "id": 1, "name": 1}
                ).to_list(50)
                for cand in candidates:
                    low = cand.lower()
                    for u in participants:
                        if (u.get("name") or "").lower().replace(" ", "").startswith(low.replace(" ", "")):
                            mentions.append({"user_id": u["id"], "user_name": u.get("name")})
                            break
    msg = {
        "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id,
        "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"),
        "text": text, "type": "text", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if thread_id:
        msg["thread_id"] = thread_id
    if reply_to:
        msg["reply_to"] = reply_to
    if mentions:
        msg["mentions"] = mentions
    await db.chat_messages.insert_one(msg); msg.pop("_id", None)
    await db.conversations.update_one({"id": conv_id}, {"$set": {"updated_at": msg["created_at"], "last_message": text[:100]}})
    try:
        from routers.websocket import manager
        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
        if conv:
            await manager.send_to_users(conv.get("participants", []), {"type": "chat_message", "conversation_id": conv_id, "message": msg})
        # Fire mention notifications
        for m in mentions:
            uid = m.get("user_id")
            if not uid or uid == current_user["id"]:
                continue
            try:
                await db.notifications.insert_one({
                    "id": f"ntf_{uuid.uuid4().hex[:10]}",
                    "user_id": uid,
                    "kind": "chat_mention",
                    "title": f"{current_user.get('name','Someone')} mentioned you",
                    "body": text[:140],
                    "ref": {"conversation_id": conv_id, "message_id": msg["id"]},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "read": False,
                })
                await manager.send_to_users([uid], {"type": "notification", "kind": "chat_mention", "conversation_id": conv_id, "message": msg})
            except Exception as ee:
                logger.warning(f"Mention notify failed: {ee}")
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")
    return msg


@router.post("/chat/ai-assistant")
async def ai_chat_assistant(data: dict, current_user: dict = Depends(get_current_user)):
    from dotenv import load_dotenv; load_dotenv()
    message = data.get("message", "").strip()
    session_id = data.get("session_id", f"ai_{current_user['id']}")
    if not message: raise HTTPException(status_code=400, detail="Message required")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key: raise HTTPException(status_code=500, detail="AI not configured")

        # Build live app context based on user's role & access level
        role = (current_user.get("role") or "").lower()
        is_admin = role in {"admin", "system_admin", "executive director", "director"}
        is_manager = is_admin or role in {"manager", "coordinator", "hr"}
        user_loc = current_user.get("location_id")
        ctx = await _build_app_context(current_user, is_admin, is_manager, user_loc)

        system_msg = f"""You are the AI Assistant for 58:12 Connect, a multi-location non-profit CRM. You have full access to live data and can help users work efficiently.

Current user: {current_user.get('name')} (Role: {current_user.get('role', 'Staff')})
Access level: {'Full admin access' if is_admin else 'Manager/Coordinator' if is_manager else 'Staff/Member view'}

LIVE APP DATA:
{ctx}

CAPABILITIES:
- Answer questions about data, members, events, finances, attendance
- Generate summaries and reports from real data (present in the chat)
- Suggest actions: "Go to People > Members", "Open Financial > Balance Sheet"
- If user asks to generate a report, summarize the relevant data directly in your response
- For financial queries, calculate totals, averages, and trends from the live data
- For attendance, show check-in counts and patterns
- Be specific with numbers — use the real data provided above

RULES:
- Only share data the user's role permits
- Be concise (2-4 sentences unless detailed report requested)
- For reports: format as clear tables or bullet points
- If asked to make changes you can't do, explain what the user should do and where
"""

        chat = LlmChat(api_key=api_key, session_id=session_id, system_message=system_msg).with_model("gemini", "gemini-2.5-flash")
        response = await chat.send_message(UserMessage(text=message))
        now = datetime.now(timezone.utc).isoformat()
        await db.chat_messages.insert_one({"id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}", "sender_id": current_user["id"], "sender_name": current_user.get("name"), "text": message, "type": "user", "created_at": now})
        await db.chat_messages.insert_one({"id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}", "sender_id": "ai_assistant", "sender_name": "AI Assistant", "text": response, "type": "ai", "created_at": now})
        return {"response": response, "session_id": session_id}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI assistant error: {str(e)}")


async def _build_app_context(user: dict, is_admin: bool, is_manager: bool, user_loc: str) -> str:
    """Fetch live data from DB and format as context string based on user access level."""
    parts = []
    from datetime import date, timedelta
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    this_month_start = date.today().replace(day=1).isoformat()

    try:
        # ---- Members ----
        mem_query = {} if is_admin else {"location_id": user_loc} if user_loc else {}
        total_members = await db.members.count_documents(mem_query)
        active_members = await db.members.count_documents({**mem_query, "status": "active"})
        parts.append(f"Members: {total_members} total, {active_members} active")

        # ---- Families / Children ----
        if is_manager:
            fam_count = await db.families.count_documents({})
            child_count = await db.children.count_documents({})
            parts.append(f"Families: {fam_count} families, {child_count} children registered")

        # ---- Check-ins today ----
        ci_query = {"date": today}
        if not is_admin and user_loc:
            ci_query["location_id"] = user_loc
        checkins_today = await db.checkins.count_documents(ci_query)
        parts.append(f"Check-ins today: {checkins_today}")

        # ---- Upcoming events ----
        ev_query = {"date": {"$gte": today, "$lte": (date.today().replace(month=min(date.today().month+1, 12))).isoformat()}}
        if not is_admin and user_loc:
            ev_query["$or"] = [{"location_id": user_loc}, {"is_public": True}]
        events = await db.events.find(ev_query, {"_id": 0, "title": 1, "date": 1, "time": 1, "location": 1}).sort("date", 1).to_list(5)
        if events:
            ev_lines = [f"  - {e['title']} on {e['date']}{' at ' + e['time'] if e.get('time') else ''}" for e in events]
            parts.append(f"Upcoming events (next ~30 days):\n" + "\n".join(ev_lines))
        else:
            parts.append("Upcoming events: None scheduled")

        # ---- Active tasks (Kanban) ----
        task_query = {"is_archived": {"$ne": True}, "status": {"$ne": "done"}}
        if not is_admin and user_loc:
            boards = await db.boards.find({"$or": [{"location_id": user_loc}, {"is_global": True}]}, {"id": 1}).to_list(20)
            board_ids = [b["id"] for b in boards]
            task_query["board_id"] = {"$in": board_ids}
        task_due_soon = await db.tasks.count_documents({**task_query, "due_date": {"$lte": tomorrow, "$gte": today}})
        total_tasks = await db.tasks.count_documents(task_query)
        parts.append(f"Tasks: {total_tasks} open tasks, {task_due_soon} due within 24 hours")

        # ---- Financial (admin/manager only) ----
        if is_manager:
            fin_query = {"date": {"$gte": this_month_start}}
            if not is_admin and user_loc:
                fin_query["location_id"] = user_loc
            donations = await db.financial.find({**fin_query, "type": "donation"}, {"_id": 0, "amount": 1}).to_list(500)
            expenses = await db.financial.find({**fin_query, "type": "expense"}, {"_id": 0, "amount": 1}).to_list(500)
            total_don = sum(d.get("amount", 0) for d in donations)
            total_exp = sum(e.get("amount", 0) for e in expenses)
            parts.append(f"Finance this month: UGX {total_don:,.0f} income, UGX {total_exp:,.0f} expenses, Net: UGX {total_don - total_exp:,.0f}")

        # ---- Locations ----
        if is_admin:
            locs = await db.locations.find({}, {"_id": 0, "name": 1, "type": 1, "timezone": 1}).to_list(20)
            loc_names = [f"{l['name']} ({l.get('timezone', 'N/A')} timezone)" for l in locs]
            parts.append(f"Locations ({len(locs)}): " + ", ".join(loc_names))

    except Exception as e:
        logger.warning(f"AI context build error: {e}")
        parts.append("(Some live data unavailable)")

    return "\n".join(parts) if parts else "No data available"


# ========== OFFLINE SYNC ==========

@router.post("/sync/messages")
async def sync_offline_messages(data: dict, current_user: dict = Depends(get_current_user)):
    messages = data.get("messages", []); synced = 0
    for msg in messages:
        if not msg.get("conversation_id") or not msg.get("text"): continue
        existing = await db.chat_messages.find_one({"id": msg.get("id")})
        if existing: continue
        doc = {
            "id": msg.get("id", f"msg_{str(uuid.uuid4())[:8]}"), "conversation_id": msg["conversation_id"],
            "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"),
            "text": msg["text"], "type": "text", "reply_to": msg.get("reply_to"),
            "read_by": [current_user["id"]],
            "created_at": msg.get("created_at", datetime.now(timezone.utc).isoformat()),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.chat_messages.insert_one(doc); synced += 1
    return {"synced": synced}



# ========== CONVERSATION MANAGEMENT ==========

@router.delete("/chat/conversations/{conv_id}")
async def delete_conversation_for_user(conv_id: str, current_user: dict = Depends(get_current_user)):
    """Hide a conversation for the current user only (doesn't delete for others)."""
    conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Add user to hidden_by list
    await db.conversations.update_one({"id": conv_id}, {"$addToSet": {"hidden_by": current_user["id"]}})
    return {"message": "Conversation hidden"}


@router.put("/chat/conversations/{conv_id}/members")
async def update_group_members(conv_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add or remove members from a group conversation."""
    conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.get("type") != "group":
        raise HTTPException(status_code=400, detail="Can only edit group conversations")
    add_ids = data.get("add", [])
    remove_ids = data.get("remove", [])
    update_ops = {}
    if add_ids:
        update_ops["$addToSet"] = {"participants": {"$each": add_ids}}
    if remove_ids:
        if "$pull" not in update_ops:
            update_ops["$pull"] = {}
        # Can't use $addToSet and $pull together, handle sequentially
    if add_ids:
        await db.conversations.update_one({"id": conv_id}, {"$addToSet": {"participants": {"$each": add_ids}}})
        # Add system message
        names = []
        for uid in add_ids:
            u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1})
            if u: names.append(u.get("name", ""))
        if names:
            await db.chat_messages.insert_one({
                "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id,
                "sender_id": "system", "sender_name": "System", "text": f"{', '.join(names)} joined the group",
                "type": "system", "created_at": datetime.now(timezone.utc).isoformat(),
            })
    if remove_ids:
        await db.conversations.update_one({"id": conv_id}, {"$pull": {"participants": {"$in": remove_ids}}})
        names = []
        for uid in remove_ids:
            u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1})
            if u: names.append(u.get("name", ""))
        if names:
            await db.chat_messages.insert_one({
                "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id,
                "sender_id": "system", "sender_name": "System", "text": f"{', '.join(names)} left the group",
                "type": "system", "created_at": datetime.now(timezone.utc).isoformat(),
            })
    if data.get("name"):
        await db.conversations.update_one({"id": conv_id}, {"$set": {"name": data["name"]}})
    updated = await db.conversations.find_one({"id": conv_id}, {"_id": 0})
    return updated


@router.delete("/chat/messages/{message_id}")
async def delete_message(message_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a message — only if sender and not yet read by others."""
    msg = await db.chat_messages.find_one({"id": message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.get("sender_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")
    # Check if read by others
    read_by = msg.get("read_by", [])
    others_read = [r for r in read_by if r != current_user["id"]]
    if others_read:
        raise HTTPException(status_code=400, detail="Message already read by other members — cannot delete")
    await db.chat_messages.delete_one({"id": message_id})
    # Broadcast deletion to conversation participants
    try:
        from routers.websocket import manager
        conv = await db.conversations.find_one({"id": msg.get("conversation_id")}, {"_id": 0, "participants": 1})
        if conv:
            await manager.send_to_users(conv.get("participants", []), {"type": "message_deleted", "conversation_id": msg["conversation_id"], "message_id": message_id})
    except Exception:
        pass
    return {"message": "Message deleted"}
