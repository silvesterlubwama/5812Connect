"""
Calling Router - Audio/Video Calling with PBX Integration
Supports: WebRTC standalone, FreePBX/Asterisk, 3CX, Generic SIP
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import uuid
import json
import asyncio
import httpx

router = APIRouter(prefix="/api/calling", tags=["calling"])

# ============== MODELS ==============

class ExtensionCreate(BaseModel):
    user_id: str
    extension: str = Field(..., pattern=r'^\d{3,6}$')
    display_name: Optional[str] = None
    voicemail_enabled: bool = True
    voicemail_pin: Optional[str] = None
    dnd_enabled: bool = False
    forward_to: Optional[str] = None

class ExtensionUpdate(BaseModel):
    extension: Optional[str] = None
    display_name: Optional[str] = None
    voicemail_enabled: Optional[bool] = None
    voicemail_pin: Optional[str] = None
    dnd_enabled: Optional[bool] = None
    forward_to: Optional[str] = None

class PbxConfigCreate(BaseModel):
    name: str
    provider: str  # freepbx, 3cx, asterisk, generic_sip
    host: str
    port: int = 5060
    username: Optional[str] = None
    password: Optional[str] = None
    sip_username: Optional[str] = None
    sip_password: Optional[str] = None
    sip_domain: Optional[str] = None
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    websocket_url: Optional[str] = None
    stun_servers: List[str] = ["stun:stun.l.google.com:19302"]
    turn_servers: List[Dict] = []
    is_active: bool = True
    is_default: bool = False

class CallInitiate(BaseModel):
    to_user_id: Optional[str] = None
    to_extension: Optional[str] = None
    to_number: Optional[str] = None  # External number
    call_type: str = "audio"  # audio, video
    use_pbx: bool = False

class CallAction(BaseModel):
    action: str  # answer, reject, hangup, hold, unhold, mute, unmute, transfer, add_participant
    target_user_id: Optional[str] = None
    target_extension: Optional[str] = None

class VoicemailGreeting(BaseModel):
    greeting_type: str = "default"  # default, custom, name
    custom_greeting_url: Optional[str] = None

# ============== DATABASE HELPERS ==============

def get_db():
    from server import db
    return db

def serialize_doc(doc):
    if doc is None:
        return None
    doc = dict(doc)
    if '_id' in doc:
        doc['id'] = str(doc.pop('_id'))
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

# ============== EXTENSIONS ==============

@router.get("/extensions")
async def list_extensions(
    location_id: Optional[str] = None,
    db=Depends(get_db)
):
    """List all extensions with user info"""
    pipeline = [
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "id",
            "as": "user"
        }},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "id": {"$toString": "$_id"},
            "user_id": 1,
            "extension": 1,
            "display_name": 1,
            "voicemail_enabled": 1,
            "dnd_enabled": 1,
            "forward_to": 1,
            "status": 1,
            "user_name": "$user.name",
            "user_email": "$user.email",
            "user_role": "$user.role",
            "created_at": 1
        }}
    ]
    
    if location_id:
        pipeline.insert(0, {"$match": {"location_id": location_id}})
    
    extensions = await db.extensions.aggregate(pipeline).to_list(500)
    return extensions

@router.post("/extensions")
async def create_extension(data: ExtensionCreate, db=Depends(get_db)):
    """Create/assign extension to user"""
    # Check if extension already exists
    existing = await db.extensions.find_one({"extension": data.extension})
    if existing:
        raise HTTPException(400, "Extension already assigned")
    
    # Check if user already has extension
    user_ext = await db.extensions.find_one({"user_id": data.user_id})
    if user_ext:
        raise HTTPException(400, "User already has an extension")
    
    # Get user info for display name
    user = await db.users.find_one({"id": data.user_id})
    if not user:
        raise HTTPException(404, "User not found")
    
    ext_doc = {
        "user_id": data.user_id,
        "extension": data.extension,
        "display_name": data.display_name or user.get("name", ""),
        "voicemail_enabled": data.voicemail_enabled,
        "voicemail_pin": data.voicemail_pin or data.extension,  # Default PIN = extension
        "dnd_enabled": data.dnd_enabled,
        "forward_to": data.forward_to,
        "status": "available",
        "created_at": datetime.now(timezone.utc)
    }
    
    result = await db.extensions.insert_one(ext_doc)
    ext_doc["id"] = str(result.inserted_id)
    if "_id" in ext_doc:
        del ext_doc["_id"]
    return ext_doc

@router.put("/extensions/{extension}")
async def update_extension(extension: str, data: ExtensionUpdate, db=Depends(get_db)):
    """Update extension settings"""
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No data to update")
    
    # If changing extension number, check availability
    if "extension" in update_data:
        existing = await db.extensions.find_one({"extension": update_data["extension"]})
        if existing:
            raise HTTPException(400, "Extension already in use")
    
    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await db.extensions.update_one(
        {"extension": extension},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Extension not found")
    
    return {"success": True}

@router.delete("/extensions/{extension}")
async def delete_extension(extension: str, db=Depends(get_db)):
    """Remove extension assignment"""
    result = await db.extensions.delete_one({"extension": extension})
    if result.deleted_count == 0:
        raise HTTPException(404, "Extension not found")
    return {"success": True}

@router.get("/extensions/user/{user_id}")
async def get_user_extension(user_id: str, db=Depends(get_db)):
    """Get extension for a specific user"""
    ext = await db.extensions.find_one({"user_id": user_id}, {"_id": 0})
    return ext

# ============== PBX CONFIGURATION ==============

@router.get("/pbx-configs")
async def list_pbx_configs(db=Depends(get_db)):
    """List all PBX configurations"""
    configs = await db.pbx_configs.find({}, {"_id": 0, "password": 0, "api_key": 0, "sip_password": 0}).to_list(50)
    return configs

@router.post("/pbx-configs")
async def create_pbx_config(data: PbxConfigCreate, db=Depends(get_db)):
    """Add new PBX configuration"""
    config_doc = data.dict()
    config_doc["id"] = str(uuid.uuid4())
    config_doc["created_at"] = datetime.now(timezone.utc)
    
    # If setting as default, unset other defaults
    if data.is_default:
        await db.pbx_configs.update_many({}, {"$set": {"is_default": False}})
    
    await db.pbx_configs.insert_one(config_doc)
    
    # Don't return sensitive fields
    config_doc.pop("password", None)
    config_doc.pop("api_key", None)
    config_doc.pop("sip_password", None)
    config_doc.pop("_id", None)
    return config_doc

@router.put("/pbx-configs/{config_id}")
async def update_pbx_config(config_id: str, data: dict, db=Depends(get_db)):
    """Update PBX configuration"""
    # Remove sensitive read from response
    update_data = {k: v for k, v in data.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    if update_data.get("is_default"):
        await db.pbx_configs.update_many({"id": {"$ne": config_id}}, {"$set": {"is_default": False}})
    
    result = await db.pbx_configs.update_one({"id": config_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(404, "PBX config not found")
    return {"success": True}

@router.delete("/pbx-configs/{config_id}")
async def delete_pbx_config(config_id: str, db=Depends(get_db)):
    """Delete PBX configuration"""
    result = await db.pbx_configs.delete_one({"id": config_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "PBX config not found")
    return {"success": True}

@router.post("/pbx-configs/{config_id}/test")
async def test_pbx_connection(config_id: str, db=Depends(get_db)):
    """Test PBX connection"""
    config = await db.pbx_configs.find_one({"id": config_id})
    if not config:
        raise HTTPException(404, "PBX config not found")
    
    provider = config.get("provider")
    try:
        if provider == "3cx":
            # Test 3CX API
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{config['api_url']}/api/SystemStatus",
                    headers={"Authorization": f"Bearer {config.get('api_key', '')}"},
                    timeout=10
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "3CX connection successful"}
        elif provider in ["freepbx", "asterisk"]:
            # Test Asterisk AMI or FreePBX API
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{config['api_url']}/admin/api/api.php?action=ping",
                    auth=(config.get("username", ""), config.get("password", "")),
                    timeout=10
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "FreePBX connection successful"}
        else:
            # Generic SIP - just check if host is reachable
            return {"success": True, "message": "Configuration saved (SIP connectivity tested on call)"}
    except Exception as e:
        return {"success": False, "message": str(e)}
    
    return {"success": False, "message": "Connection failed"}

# ============== CALL MANAGEMENT ==============

# In-memory active calls (in production, use Redis)
active_calls: Dict[str, Dict] = {}
call_participants: Dict[str, set] = {}  # call_id -> set of user_ids

@router.post("/calls/initiate")
async def initiate_call(data: CallInitiate, user_id: str = Query(...), db=Depends(get_db)):
    """Initiate a new call"""
    call_id = str(uuid.uuid4())
    
    # Determine target
    target_user_id = data.to_user_id
    target_extension = data.to_extension
    target_number = data.to_number
    
    if target_extension and not target_user_id:
        # Look up user by extension
        ext = await db.extensions.find_one({"extension": target_extension})
        if ext:
            target_user_id = ext["user_id"]
    
    # Get caller info
    caller = await db.users.find_one({"id": user_id})
    caller_ext = await db.extensions.find_one({"user_id": user_id})
    
    call_doc = {
        "id": call_id,
        "caller_id": user_id,
        "caller_name": caller.get("name") if caller else "Unknown",
        "caller_extension": caller_ext.get("extension") if caller_ext else None,
        "target_user_id": target_user_id,
        "target_extension": target_extension,
        "target_number": target_number,
        "call_type": data.call_type,
        "use_pbx": data.use_pbx,
        "status": "initiating",
        "started_at": datetime.now(timezone.utc),
        "participants": [user_id],
        "is_conference": False,
        "is_recorded": False,
        "is_on_hold": False
    }
    
    # Store in memory for real-time
    active_calls[call_id] = call_doc
    call_participants[call_id] = {user_id}
    
    # Store in DB for history
    await db.call_logs.insert_one({**call_doc, "_id": ObjectId()})
    
    # Get ICE servers
    pbx_config = await db.pbx_configs.find_one({"is_default": True, "is_active": True})
    ice_servers = [{"urls": "stun:stun.l.google.com:19302"}]
    if pbx_config:
        ice_servers = [{"urls": s} for s in pbx_config.get("stun_servers", [])]
        ice_servers.extend(pbx_config.get("turn_servers", []))
    
    return {
        "call_id": call_id,
        "ice_servers": ice_servers,
        "call": call_doc
    }

@router.post("/calls/{call_id}/action")
async def call_action(call_id: str, data: CallAction, user_id: str = Query(...), db=Depends(get_db)):
    """Perform action on active call"""
    call = active_calls.get(call_id)
    if not call:
        raise HTTPException(404, "Call not found or ended")
    
    action = data.action
    now = datetime.now(timezone.utc)
    
    if action == "answer":
        call["status"] = "connected"
        call["answered_at"] = now
        call_participants[call_id].add(user_id)
        await db.call_logs.update_one({"id": call_id}, {"$set": {"status": "connected", "answered_at": now}})
        
    elif action == "reject":
        call["status"] = "rejected"
        call["ended_at"] = now
        await db.call_logs.update_one({"id": call_id}, {"$set": {"status": "rejected", "ended_at": now}})
        del active_calls[call_id]
        
    elif action == "hangup":
        call["status"] = "ended"
        call["ended_at"] = now
        duration = 0
        if call.get("answered_at"):
            duration = int((now - call["answered_at"]).total_seconds())
        call["duration"] = duration
        await db.call_logs.update_one({"id": call_id}, {"$set": {"status": "ended", "ended_at": now, "duration": duration}})
        del active_calls[call_id]
        
    elif action == "hold":
        call["is_on_hold"] = True
        await db.call_logs.update_one({"id": call_id}, {"$set": {"is_on_hold": True}})
        
    elif action == "unhold":
        call["is_on_hold"] = False
        await db.call_logs.update_one({"id": call_id}, {"$set": {"is_on_hold": False}})
        
    elif action == "mute":
        if "muted_participants" not in call:
            call["muted_participants"] = []
        if user_id not in call["muted_participants"]:
            call["muted_participants"].append(user_id)
            
    elif action == "unmute":
        if "muted_participants" in call and user_id in call["muted_participants"]:
            call["muted_participants"].remove(user_id)
            
    elif action == "transfer":
        if not data.target_user_id and not data.target_extension:
            raise HTTPException(400, "Transfer target required")
        call["transfer_to"] = data.target_user_id or data.target_extension
        call["status"] = "transferring"
        
    elif action == "add_participant":
        if not data.target_user_id:
            raise HTTPException(400, "Participant user_id required")
        call["is_conference"] = True
        call["participants"].append(data.target_user_id)
        call_participants[call_id].add(data.target_user_id)
        await db.call_logs.update_one({"id": call_id}, {
            "$set": {"is_conference": True},
            "$push": {"participants": data.target_user_id}
        })
    
    return {"success": True, "call": call}

@router.get("/calls/active")
async def get_active_calls(user_id: str = Query(...)):
    """Get user's active calls"""
    user_calls = []
    for call_id, call in active_calls.items():
        if user_id in call_participants.get(call_id, set()) or call.get("target_user_id") == user_id:
            user_calls.append(call)
    return user_calls

@router.post("/calls/{call_id}/recording/start")
async def start_recording(call_id: str, db=Depends(get_db)):
    """Start call recording"""
    call = active_calls.get(call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    
    call["is_recorded"] = True
    call["recording_started_at"] = datetime.now(timezone.utc)
    await db.call_logs.update_one({"id": call_id}, {"$set": {"is_recorded": True}})
    return {"success": True}

@router.post("/calls/{call_id}/recording/stop")
async def stop_recording(call_id: str, db=Depends(get_db)):
    """Stop call recording"""
    call = active_calls.get(call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    
    call["is_recorded"] = False
    return {"success": True}

# ============== CALL HISTORY ==============

@router.get("/history")
async def get_call_history(
    user_id: str = Query(...),
    call_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    db=Depends(get_db)
):
    """Get call history for user"""
    query = {
        "$or": [
            {"caller_id": user_id},
            {"target_user_id": user_id},
            {"participants": user_id}
        ]
    }
    
    if call_type:
        query["call_type"] = call_type
    if status:
        query["status"] = status
    
    calls = await db.call_logs.find(query, {"_id": 0}).sort("started_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.call_logs.count_documents(query)
    
    return {"calls": calls, "total": total}

@router.get("/history/{call_id}")
async def get_call_detail(call_id: str, db=Depends(get_db)):
    """Get detailed call info"""
    call = await db.call_logs.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(404, "Call not found")
    return call

@router.delete("/history/{call_id}")
async def delete_call_record(call_id: str, db=Depends(get_db)):
    """Delete call from history"""
    result = await db.call_logs.delete_one({"id": call_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Call not found")
    return {"success": True}

# ============== VOICEMAIL ==============

@router.get("/voicemail")
async def get_voicemails(user_id: str = Query(...), unread_only: bool = False, db=Depends(get_db)):
    """Get user's voicemails"""
    query = {"to_user_id": user_id}
    if unread_only:
        query["is_read"] = False
    
    voicemails = await db.voicemails.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return voicemails

@router.post("/voicemail")
async def create_voicemail(
    to_user_id: str,
    from_user_id: Optional[str] = None,
    from_number: Optional[str] = None,
    audio_url: str = "",
    duration: int = 0,
    transcript: Optional[str] = None,
    db=Depends(get_db)
):
    """Create new voicemail"""
    voicemail_doc = {
        "id": str(uuid.uuid4()),
        "to_user_id": to_user_id,
        "from_user_id": from_user_id,
        "from_number": from_number,
        "audio_url": audio_url,
        "duration": duration,
        "transcript": transcript,
        "is_read": False,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.voicemails.insert_one(voicemail_doc)
    voicemail_doc.pop("_id", None)
    return voicemail_doc

@router.put("/voicemail/{voicemail_id}/read")
async def mark_voicemail_read(voicemail_id: str, db=Depends(get_db)):
    """Mark voicemail as read"""
    result = await db.voicemails.update_one(
        {"id": voicemail_id},
        {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Voicemail not found")
    return {"success": True}

@router.delete("/voicemail/{voicemail_id}")
async def delete_voicemail(voicemail_id: str, db=Depends(get_db)):
    """Delete voicemail"""
    result = await db.voicemails.delete_one({"id": voicemail_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Voicemail not found")
    return {"success": True}

@router.get("/voicemail/unread-count")
async def get_unread_voicemail_count(user_id: str = Query(...), db=Depends(get_db)):
    """Get count of unread voicemails"""
    count = await db.voicemails.count_documents({"to_user_id": user_id, "is_read": False})
    return {"count": count}

# ============== CALL RECORDINGS ==============

@router.get("/recordings")
async def get_recordings(
    user_id: str = Query(...),
    limit: int = 50,
    db=Depends(get_db)
):
    """Get call recordings for user"""
    query = {
        "is_recorded": True,
        "$or": [
            {"caller_id": user_id},
            {"target_user_id": user_id},
            {"participants": user_id}
        ]
    }
    
    recordings = await db.call_logs.find(query, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)
    return recordings

@router.post("/recordings/{call_id}/save")
async def save_recording(call_id: str, recording_url: str, db=Depends(get_db)):
    """Save recording URL to call"""
    result = await db.call_logs.update_one(
        {"id": call_id},
        {"$set": {"recording_url": recording_url}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Call not found")
    return {"success": True}

# ============== PRESENCE/STATUS ==============

@router.put("/status")
async def update_call_status(user_id: str = Query(...), status: str = Query(...), db=Depends(get_db)):
    """Update user's calling status (available, busy, dnd, offline)"""
    valid_statuses = ["available", "busy", "dnd", "offline", "on_call"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid_statuses}")
    
    await db.extensions.update_one(
        {"user_id": user_id},
        {"$set": {"status": status, "status_updated_at": datetime.now(timezone.utc)}}
    )
    return {"success": True, "status": status}

@router.get("/status/{user_id}")
async def get_user_call_status(user_id: str, db=Depends(get_db)):
    """Get user's calling status"""
    ext = await db.extensions.find_one({"user_id": user_id}, {"_id": 0, "status": 1, "dnd_enabled": 1})
    if not ext:
        return {"status": "offline", "dnd_enabled": False}
    return ext

# ============== MISSED CALLS ==============

@router.get("/missed")
async def get_missed_calls(user_id: str = Query(...), db=Depends(get_db)):
    """Get missed calls for user"""
    query = {
        "target_user_id": user_id,
        "status": {"$in": ["missed", "rejected", "no_answer"]}
    }
    
    missed = await db.call_logs.find(query, {"_id": 0}).sort("started_at", -1).limit(50).to_list(50)
    return missed

@router.get("/missed/count")
async def get_missed_call_count(user_id: str = Query(...), db=Depends(get_db)):
    """Get count of missed calls since last check"""
    # Get unread missed calls
    count = await db.call_logs.count_documents({
        "target_user_id": user_id,
        "status": {"$in": ["missed", "rejected", "no_answer"]},
        "is_seen": {"$ne": True}
    })
    return {"count": count}

@router.put("/missed/mark-seen")
async def mark_missed_calls_seen(user_id: str = Query(...), db=Depends(get_db)):
    """Mark all missed calls as seen"""
    await db.call_logs.update_many(
        {"target_user_id": user_id, "status": {"$in": ["missed", "rejected", "no_answer"]}},
        {"$set": {"is_seen": True}}
    )
    return {"success": True}

# ============== CONTACTS/SPEED DIAL ==============

@router.get("/contacts")
async def get_callable_contacts(user_id: str = Query(...), db=Depends(get_db)):
    """Get list of contacts that can be called (users with extensions + all staff)"""
    # Users with extensions
    pipeline = [
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "id",
            "as": "user"
        }},
        {"$unwind": "$user"},
        {"$match": {"user_id": {"$ne": user_id}}},
        {"$project": {
            "_id": 0,
            "user_id": 1,
            "extension": 1,
            "display_name": 1,
            "status": 1,
            "name": "$user.name",
            "email": "$user.email",
            "role": "$user.role"
        }}
    ]
    ext_contacts = await db.extensions.aggregate(pipeline).to_list(200)
    ext_user_ids = {c["user_id"] for c in ext_contacts}
    
    # Also include staff users without extensions
    staff_roles = ["admin", "system_admin", "Executive Director", "Adviser", "Director", "Manager", "Coordinator", "Staff", "HR"]
    staff_users = await db.users.find(
        {"id": {"$ne": user_id, "$nin": list(ext_user_ids)}, "role": {"$in": staff_roles}, "status": "active"},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)
    for u in staff_users:
        ext_contacts.append({"user_id": u["id"], "extension": None, "display_name": u.get("name"), "name": u.get("name"), "email": u.get("email"), "role": u.get("role")})
    
    return ext_contacts

# ============== ICE SERVERS ==============

@router.get("/ice-servers")
async def get_ice_servers(db=Depends(get_db)):
    """Get ICE servers for WebRTC"""
    pbx_config = await db.pbx_configs.find_one({"is_default": True, "is_active": True})
    
    servers = [{"urls": "stun:stun.l.google.com:19302"}]
    
    if pbx_config:
        servers = [{"urls": s} for s in pbx_config.get("stun_servers", ["stun:stun.l.google.com:19302"])]
        turn_servers = pbx_config.get("turn_servers", [])
        servers.extend(turn_servers)
    
    return {"ice_servers": servers}


# ============== AUTO-ATTENDANT ==============

@router.get("/auto-attendant")
async def get_auto_attendant(db=Depends(get_db)):
    """Get auto-attendant configuration"""
    doc = await db.auto_attendant.find_one({"_key": "main"}, {"_id": 0})
    return doc or {
        "_key": "main", "enabled": False, "greeting": "Welcome to 58:12 Global. Press 1 for reception, 2 for directory.",
        "menu_options": [
            {"key": "1", "action": "transfer", "target": "reception", "label": "Reception"},
            {"key": "2", "action": "directory", "target": "directory", "label": "Staff Directory"},
            {"key": "0", "action": "operator", "target": "operator", "label": "Operator"},
        ],
        "business_hours": {"start": "08:00", "end": "17:00", "timezone": "Africa/Kampala"},
        "after_hours_greeting": "Our office is currently closed. Please leave a message.",
        "after_hours_action": "voicemail",
    }

@router.put("/auto-attendant")
async def update_auto_attendant(data: dict, db=Depends(get_db)):
    """Update auto-attendant configuration (admin only)"""
    data.pop("_id", None)
    data["_key"] = "main"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.auto_attendant.update_one({"_key": "main"}, {"$set": data}, upsert=True)
    data.pop("_id", None)
    return data

# ============== CALL QUEUES ==============

@router.get("/queues")
async def list_call_queues(db=Depends(get_db)):
    """List call queues"""
    return await db.call_queues.find({}, {"_id": 0}).sort("name", 1).to_list(50)

@router.post("/queues")
async def create_call_queue(data: dict, db=Depends(get_db)):
    """Create a call queue"""
    doc = {
        "id": f"queue_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "strategy": data.get("strategy", "ring_all"),  # ring_all, round_robin, least_recent, random
        "timeout": data.get("timeout", 30),
        "max_wait": data.get("max_wait", 300),
        "members": data.get("members", []),  # list of extension numbers
        "music_on_hold": data.get("music_on_hold", "default"),
        "announce_position": data.get("announce_position", True),
        "wrap_up_time": data.get("wrap_up_time", 10),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.call_queues.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/queues/{queue_id}")
async def update_call_queue(queue_id: str, data: dict, db=Depends(get_db)):
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.call_queues.update_one({"id": queue_id}, {"$set": data})
    return await db.call_queues.find_one({"id": queue_id}, {"_id": 0})

@router.delete("/queues/{queue_id}")
async def delete_call_queue(queue_id: str, db=Depends(get_db)):
    await db.call_queues.delete_one({"id": queue_id})
    return {"message": "Queue deleted"}

# ============== CALL FORWARDING RULES ==============

@router.get("/forwarding/{user_id}")
async def get_forwarding_rules(user_id: str, db=Depends(get_db)):
    """Get call forwarding rules for a user"""
    doc = await db.call_forwarding.find_one({"user_id": user_id}, {"_id": 0})
    return doc or {
        "user_id": user_id,
        "enabled": False,
        "forward_always": None,
        "forward_busy": None,
        "forward_no_answer": None,
        "forward_no_answer_timeout": 20,
        "forward_offline": None,
    }

@router.put("/forwarding/{user_id}")
async def update_forwarding_rules(user_id: str, data: dict, db=Depends(get_db)):
    """Update call forwarding rules"""
    data["user_id"] = user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data.pop("_id", None)
    await db.call_forwarding.update_one({"user_id": user_id}, {"$set": data}, upsert=True)
    data.pop("_id", None)
    return data

# ============== OUTGOING CALL RULES ==============

@router.get("/outgoing-rules")
async def list_outgoing_rules(db=Depends(get_db)):
    """List outgoing call rules"""
    return await db.outgoing_rules.find({}, {"_id": 0}).sort("priority", 1).to_list(50)

@router.post("/outgoing-rules")
async def create_outgoing_rule(data: dict, db=Depends(get_db)):
    doc = {
        "id": f"rule_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "pattern": data.get("pattern", ""),  # regex pattern for number matching
        "action": data.get("action", "allow"),  # allow, block, prefix
        "prefix": data.get("prefix", ""),
        "priority": data.get("priority", 10),
        "enabled": data.get("enabled", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.outgoing_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.delete("/outgoing-rules/{rule_id}")
async def delete_outgoing_rule(rule_id: str, db=Depends(get_db)):
    await db.outgoing_rules.delete_one({"id": rule_id})
    return {"message": "Rule deleted"}
