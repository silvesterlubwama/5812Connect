"""Chat, AI Assistant routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, logger
from datetime import datetime, timezone
from typing import Optional
import uuid, os

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/chat/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    return await db.conversations.find({"participants": current_user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)


@router.post("/chat/conversations")
async def create_conversation(data: dict, current_user: dict = Depends(get_current_user)):
    conv_type = data.get("type", "direct")
    participants = data.get("participants", [])
    if current_user["id"] not in participants:
        participants.append(current_user["id"])
    doc = {"id": f"conv_{str(uuid.uuid4())[:8]}", "type": conv_type, "name": data.get("name", ""), "participants": participants, "location_id": data.get("location_id"), "created_by": current_user["id"], "is_no_reply": data.get("is_no_reply", False), "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "last_message": None}
    await db.conversations.insert_one(doc); doc.pop("_id", None)
    return doc


@router.get("/chat/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, skip: int = 0, limit: int = 50, current_user: dict = Depends(get_current_user)):
    return await db.chat_messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)


@router.post("/chat/conversations/{conv_id}/messages")
async def send_message(conv_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    text = data.get("text", "").strip()
    if not text: raise HTTPException(status_code=400, detail="Message text required")
    msg = {"id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id, "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"), "text": text, "type": "text", "created_at": datetime.now(timezone.utc).isoformat()}
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
        chat = LlmChat(api_key=api_key, session_id=session_id, system_message="You are a helpful AI assistant for 58:12 Global Connect, a multi-location organization. Help staff with questions about processes, scheduling, member management, and general organizational tasks. Keep responses concise and helpful.").with_model("gemini", "gemini-2.5-flash")
        response = await chat.send_message(UserMessage(text=message))
        now = datetime.now(timezone.utc).isoformat()
        await db.chat_messages.insert_one({"id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}", "sender_id": current_user["id"], "sender_name": current_user.get("name"), "text": message, "type": "user", "created_at": now})
        await db.chat_messages.insert_one({"id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}", "sender_id": "ai_assistant", "sender_name": "AI Assistant", "text": response, "type": "ai", "created_at": now})
        return {"response": response, "session_id": session_id}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI assistant error: {str(e)}")


# ========== OFFLINE SYNC ==========

@router.post("/sync/messages")
async def sync_offline_messages(data: dict, current_user: dict = Depends(get_current_user)):
    messages = data.get("messages", []); synced = 0
    for msg in messages:
        if not msg.get("conversation_id") or not msg.get("text"): continue
        existing = await db.chat_messages.find_one({"id": msg.get("id")})
        if existing: continue
        doc = {"id": msg.get("id", f"msg_{str(uuid.uuid4())[:8]}"), "conversation_id": msg["conversation_id"], "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"), "text": msg["text"], "type": "text", "reply_to": msg.get("reply_to"), "read_by": [current_user["id"]], "created_at": msg.get("created_at", datetime.now(timezone.utc).isoformat()), "synced_at": datetime.now(timezone.utc).isoformat()}
        await db.chat_messages.insert_one(doc); synced += 1
    return {"synced": synced}
