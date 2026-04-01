"""
Enhanced Presence System with Activity Tracking
Supports: online (active), idle (5 min timeout), offline, pbx_only
"""
from fastapi import APIRouter, Depends, Query, WebSocket
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
import asyncio

router = APIRouter(prefix="/api/presence", tags=["presence"])

# In-memory presence store (in production, use Redis)
user_presence: Dict[str, Dict] = {}  # user_id -> {status, last_activity, socket_connected, pbx_registered}

IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

def get_db():
    from deps import db
    return db

def calculate_presence_status(user_data: Dict) -> str:
    """Calculate presence status based on activity and connections"""
    if not user_data:
        return "offline"
    
    now = datetime.now(timezone.utc)
    last_activity = user_data.get("last_activity")
    socket_connected = user_data.get("socket_connected", False)
    pbx_registered = user_data.get("pbx_registered", False)
    manual_status = user_data.get("manual_status")  # dnd, away, etc.
    
    # Check manual status first
    if manual_status == "dnd":
        return "dnd"
    
    # Check if only on PBX
    if pbx_registered and not socket_connected:
        return "pbx_only"  # Blue dot
    
    # Check if socket connected
    if not socket_connected:
        return "offline"  # Red dot
    
    # Check idle timeout
    if last_activity:
        idle_duration = (now - last_activity).total_seconds()
        if idle_duration > IDLE_TIMEOUT_SECONDS:
            return "idle"  # Yellow dot
    
    return "online"  # Green dot

def get_presence_display(status: str) -> Dict:
    """Get display info for presence status"""
    display_map = {
        "online": {"color": "green", "label": "Available", "dot_class": "bg-green-500"},
        "idle": {"color": "yellow", "label": "Away", "dot_class": "bg-yellow-500"},
        "pbx_only": {"color": "blue", "label": "Phone Only", "dot_class": "bg-blue-500"},
        "offline": {"color": "red", "label": "Offline", "dot_class": "bg-red-500"},
        "dnd": {"color": "red", "label": "Do Not Disturb", "dot_class": "bg-red-600"},
        "on_call": {"color": "blue", "label": "On a Call", "dot_class": "bg-blue-500 animate-pulse"},
    }
    return display_map.get(status, display_map["offline"])

@router.get("/status/{user_id}")
async def get_user_presence(user_id: str):
    """Get presence status for a single user"""
    user_data = user_presence.get(user_id, {})
    status = calculate_presence_status(user_data)
    display = get_presence_display(status)
    
    return {
        "user_id": user_id,
        "status": status,
        **display,
        "last_activity": user_data.get("last_activity"),
        "status_message": user_data.get("status_message", ""),
    }

@router.get("/bulk")
async def get_bulk_presence(user_ids: str = Query(..., description="Comma-separated user IDs")):
    """Get presence status for multiple users"""
    ids = [uid.strip() for uid in user_ids.split(",") if uid.strip()]
    result = {}
    
    for user_id in ids:
        user_data = user_presence.get(user_id, {})
        status = calculate_presence_status(user_data)
        display = get_presence_display(status)
        result[user_id] = {
            "status": status,
            **display,
            "last_activity": user_data.get("last_activity"),
        }
    
    return result

@router.put("/heartbeat")
async def update_heartbeat(user_id: str = Query(...)):
    """Update user's last activity (called periodically by frontend)"""
    now = datetime.now(timezone.utc)
    
    if user_id not in user_presence:
        user_presence[user_id] = {}
    
    user_presence[user_id]["last_activity"] = now
    user_presence[user_id]["socket_connected"] = True
    
    return {"success": True, "timestamp": now.isoformat()}

@router.put("/status")
async def set_manual_status(
    user_id: str = Query(...),
    status: str = Query(..., description="online, away, dnd, offline"),
    status_message: Optional[str] = None
):
    """Set manual presence status"""
    valid_statuses = ["online", "away", "dnd", "offline"]
    if status not in valid_statuses:
        status = "online"
    
    if user_id not in user_presence:
        user_presence[user_id] = {}
    
    user_presence[user_id]["manual_status"] = status if status != "online" else None
    if status_message is not None:
        user_presence[user_id]["status_message"] = status_message
    
    return {"success": True, "status": status}

@router.put("/pbx-register")
async def register_pbx_presence(user_id: str = Query(...), registered: bool = True):
    """Mark user as registered on PBX (called by PBX integration)"""
    if user_id not in user_presence:
        user_presence[user_id] = {}
    
    user_presence[user_id]["pbx_registered"] = registered
    
    return {"success": True}

@router.put("/connect")
async def mark_connected(user_id: str = Query(...)):
    """Mark user as connected (WebSocket connected)"""
    now = datetime.now(timezone.utc)
    
    if user_id not in user_presence:
        user_presence[user_id] = {}
    
    user_presence[user_id]["socket_connected"] = True
    user_presence[user_id]["last_activity"] = now
    user_presence[user_id]["connected_at"] = now
    
    return {"success": True}

@router.put("/disconnect")
async def mark_disconnected(user_id: str = Query(...)):
    """Mark user as disconnected"""
    if user_id in user_presence:
        user_presence[user_id]["socket_connected"] = False
    
    return {"success": True}

@router.get("/online-users")
async def get_online_users(db=Depends(get_db)):
    """Get list of all online/available users"""
    online_users = []
    
    for user_id, data in user_presence.items():
        status = calculate_presence_status(data)
        if status in ["online", "idle", "pbx_only"]:
            online_users.append({
                "user_id": user_id,
                "status": status,
                **get_presence_display(status),
            })
    
    # Enrich with user info
    if online_users:
        user_ids = [u["user_id"] for u in online_users]
        users = await db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
        ).to_list(500)
        
        user_map = {u["id"]: u for u in users}
        for ou in online_users:
            user_info = user_map.get(ou["user_id"], {})
            ou["name"] = user_info.get("name", "Unknown")
            ou["email"] = user_info.get("email", "")
            ou["role"] = user_info.get("role", "")
    
    return online_users

# Helper functions for WebSocket integration
def set_user_online(user_id: str):
    """Called when WebSocket connects"""
    now = datetime.now(timezone.utc)
    if user_id not in user_presence:
        user_presence[user_id] = {}
    user_presence[user_id]["socket_connected"] = True
    user_presence[user_id]["last_activity"] = now
    user_presence[user_id]["connected_at"] = now

def set_user_offline(user_id: str):
    """Called when WebSocket disconnects"""
    if user_id in user_presence:
        user_presence[user_id]["socket_connected"] = False

def update_user_activity(user_id: str):
    """Called on any user activity"""
    if user_id in user_presence:
        user_presence[user_id]["last_activity"] = datetime.now(timezone.utc)

def set_user_on_call(user_id: str, on_call: bool = True):
    """Called when user starts/ends a call"""
    if user_id not in user_presence:
        user_presence[user_id] = {}
    user_presence[user_id]["on_call"] = on_call

def get_user_status(user_id: str) -> str:
    """Get current status for a user"""
    user_data = user_presence.get(user_id, {})
    if user_data.get("on_call"):
        return "on_call"
    return calculate_presence_status(user_data)
