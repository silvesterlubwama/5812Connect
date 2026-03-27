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
    return await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)


@router.get("/chat/users")
async def list_chat_users(current_user: dict = Depends(get_current_user)):
    """Return users that the current user can message — scoped to campus for non-admins."""
    query = {**await get_campus_filter(current_user), "status": "active", "id": {"$ne": current_user["id"]}}
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
    msg = {
        "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id,
        "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"),
        "text": text, "type": "text", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if thread_id:
        msg["thread_id"] = thread_id
    if reply_to:
        msg["reply_to"] = reply_to
    await db.chat_messages.insert_one(msg); msg.pop("_id", None)
    await db.conversations.update_one({"id": conv_id}, {"$set": {"updated_at": msg["created_at"], "last_message": text[:100]}})
    try:
        from routers.websocket import manager
        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
        if conv:
            await manager.send_to_users(conv.get("participants", []), {"type": "chat_message", "conversation_id": conv_id, "message": msg})
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

        system_msg = f"""You are the AI Assistant for 58:12 Global Connect, a multi-location non-profit organization based in Uganda. Your role is to help staff navigate and understand the system.

Current user: {current_user.get('name')} (Role: {current_user.get('role', 'Staff')})
Access level: {'Full admin access' if is_admin else 'Manager/Coordinator' if is_manager else 'Staff/Member view'}

LIVE APP DATA (as of now, filtered to your access level):
{ctx}

AVAILABLE APP MODULES:
- People: Members, families, children management
- Events: Calendar, RSVP, recurring events, check-ins
- Check-ins: Attendance, kiosk mode, NFC scan
- Tasks/Kanban: Project boards (Trello-like), card assignments, archive
- Finance: Donations, expenses, products/POS, fund transfers
- Communications: Staff chat, AI assistant (you), announcements
- Reports: Attendance, financial, member analytics
- Admin: User management, profiles, badge printing, documents
- Settings: Locations (with timezone), roles, integrations, badges

INSTRUCTIONS:
- Answer questions about the app, its data, and how to use features
- Only share data the user's role permits (no financial data for non-admins unless their role includes it)
- Be concise (2–4 sentences max unless a detailed list is requested)
- If asked about something not in context, say you'd need to check the live system
- Suggest navigation paths: e.g., "Go to People > Members to find this"
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
