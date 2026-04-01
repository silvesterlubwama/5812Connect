"""
Message Reactions API
Supports quick reactions (predefined emojis) and custom emoji reactions
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
from typing import List, Optional

router = APIRouter(prefix="/api/reactions", tags=["reactions"])

def get_db():
    from deps import db
    return db

# Quick reaction emojis
QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "😡", "🎉", "🙏", "👏", "🔥", "💯", "✅"]

@router.get("/quick")
async def get_quick_reactions():
    """Get list of quick reaction emojis"""
    return {"reactions": QUICK_REACTIONS}

@router.post("/message/{message_id}")
async def add_reaction(
    message_id: str,
    emoji: str = Query(...),
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Add reaction to a message"""
    # Find the message
    message = await db.chat_messages.find_one({"id": message_id})
    if not message:
        raise HTTPException(404, "Message not found")
    
    # Get user name
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
    user_name = user.get("name", "Unknown") if user else "Unknown"
    
    # Check if user already reacted with this emoji
    existing_reactions = message.get("reactions", [])
    user_reaction = next(
        (r for r in existing_reactions if r.get("emoji") == emoji and r.get("user_id") == user_id),
        None
    )
    
    if user_reaction:
        # Remove reaction (toggle off)
        await db.chat_messages.update_one(
            {"id": message_id},
            {"$pull": {"reactions": {"emoji": emoji, "user_id": user_id}}}
        )
        return {"action": "removed", "emoji": emoji}
    else:
        # Add reaction
        reaction = {
            "emoji": emoji,
            "user_id": user_id,
            "user_name": user_name,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages.update_one(
            {"id": message_id},
            {"$push": {"reactions": reaction}}
        )
        return {"action": "added", "emoji": emoji, "reaction": reaction}

@router.delete("/message/{message_id}")
async def remove_reaction(
    message_id: str,
    emoji: str = Query(...),
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Remove a reaction from a message"""
    result = await db.chat_messages.update_one(
        {"id": message_id},
        {"$pull": {"reactions": {"emoji": emoji, "user_id": user_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(404, "Reaction not found")
    
    return {"success": True}

@router.get("/message/{message_id}")
async def get_message_reactions(message_id: str, db=Depends(get_db)):
    """Get all reactions for a message"""
    message = await db.chat_messages.find_one(
        {"id": message_id},
        {"_id": 0, "reactions": 1}
    )
    
    if not message:
        raise HTTPException(404, "Message not found")
    
    reactions = message.get("reactions", [])
    
    # Group by emoji
    grouped = {}
    for r in reactions:
        emoji = r.get("emoji")
        if emoji not in grouped:
            grouped[emoji] = {"emoji": emoji, "count": 0, "users": []}
        grouped[emoji]["count"] += 1
        grouped[emoji]["users"].append({
            "user_id": r.get("user_id"),
            "user_name": r.get("user_name")
        })
    
    return {"reactions": list(grouped.values())}

@router.get("/conversation/{conversation_id}/recent")
async def get_recent_reactions(
    conversation_id: str,
    limit: int = 10,
    db=Depends(get_db)
):
    """Get recent reactions in a conversation"""
    messages = await db.chat_messages.find(
        {"conversation_id": conversation_id, "reactions": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "reactions": 1, "content": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"messages": messages}
