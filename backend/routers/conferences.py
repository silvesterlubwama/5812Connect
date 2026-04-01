"""
Conference Calls with Calendar Scheduling and Non-User Invites
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import uuid
import secrets

router = APIRouter(prefix="/api/conferences", tags=["conferences"])

def get_db():
    from deps import db
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

# ============== MODELS ==============

class ConferenceCreate(BaseModel):
    title: str
    description: Optional[str] = None
    scheduled_at: Optional[datetime] = None  # None = instant meeting
    duration_minutes: int = 60
    max_participants: Optional[int] = None  # None = unlimited
    is_video_enabled: bool = True
    is_recording_enabled: bool = False
    waiting_room_enabled: bool = False
    password: Optional[str] = None
    # Invites
    user_ids: List[str] = []  # Internal user IDs
    external_emails: List[str] = []  # Non-user email invites
    # Calendar integration
    create_calendar_event: bool = True
    send_email_invites: bool = True

class ConferenceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    max_participants: Optional[int] = None
    is_video_enabled: Optional[bool] = None
    is_recording_enabled: Optional[bool] = None
    waiting_room_enabled: Optional[bool] = None
    password: Optional[str] = None

class ExternalInvite(BaseModel):
    email: str
    name: Optional[str] = None

class JoinRequest(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None

# ============== ENDPOINTS ==============

@router.get("")
async def list_conferences(
    user_id: str = Query(...),
    include_past: bool = False,
    limit: int = 50,
    db=Depends(get_db)
):
    """List conferences user is invited to or hosts"""
    query = {
        "$or": [
            {"host_id": user_id},
            {"participants.user_id": user_id},
            {"invited_users": user_id}
        ]
    }
    
    if not include_past:
        # Only upcoming or ongoing
        query["$or"].append({"status": "ongoing"})
        now = datetime.now(timezone.utc)
        query["$and"] = [
            {"$or": [
                {"scheduled_at": {"$gte": now}},
                {"scheduled_at": None},
                {"status": "ongoing"}
            ]}
        ]
    
    conferences = await db.conferences.find(query, {"_id": 0}).sort("scheduled_at", 1).limit(limit).to_list(limit)
    return conferences

@router.post("")
async def create_conference(
    data: ConferenceCreate,
    user_id: str = Query(...),
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db)
):
    """Create a new conference/meeting"""
    conference_id = str(uuid.uuid4())
    meeting_code = secrets.token_urlsafe(8)[:10].upper()  # e.g., "ABC123XYZ"
    join_link = f"/conference/{conference_id}?code={meeting_code}"
    
    # Get host info
    host = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1, "email": 1})
    
    conference_doc = {
        "id": conference_id,
        "title": data.title,
        "description": data.description,
        "host_id": user_id,
        "host_name": host.get("name") if host else "Unknown",
        "scheduled_at": data.scheduled_at,
        "duration_minutes": data.duration_minutes,
        "max_participants": data.max_participants,
        "is_video_enabled": data.is_video_enabled,
        "is_recording_enabled": data.is_recording_enabled,
        "waiting_room_enabled": data.waiting_room_enabled,
        "password": data.password,
        "meeting_code": meeting_code,
        "join_link": join_link,
        "status": "scheduled" if data.scheduled_at else "ready",
        "invited_users": data.user_ids,
        "external_invites": [{"email": e, "invited_at": datetime.now(timezone.utc)} for e in data.external_emails],
        "participants": [],  # Active participants
        "created_at": datetime.now(timezone.utc),
        "calendar_event_id": None,
    }
    
    await db.conferences.insert_one(conference_doc)
    
    # Create calendar event if requested
    if data.create_calendar_event and data.scheduled_at:
        event_doc = {
            "id": str(uuid.uuid4()),
            "title": f"Conference: {data.title}",
            "description": f"{data.description or ''}\n\nJoin: {join_link}",
            "date": data.scheduled_at.strftime("%Y-%m-%d"),
            "start_time": data.scheduled_at.strftime("%H:%M"),
            "end_time": (data.scheduled_at + timedelta(minutes=data.duration_minutes)).strftime("%H:%M"),
            "event_type": "conference",
            "conference_id": conference_id,
            "created_by": user_id,
            "attendees": data.user_ids,
            "created_at": datetime.now(timezone.utc),
        }
        await db.events.insert_one(event_doc)
        conference_doc["calendar_event_id"] = event_doc["id"]
        await db.conferences.update_one({"id": conference_id}, {"$set": {"calendar_event_id": event_doc["id"]}})
    
    # Send email invites (in background)
    if data.send_email_invites and (data.user_ids or data.external_emails):
        try:
            from routers.notifications import send_bulk_notifications
            # Get internal user emails
            recipients = []
            if data.user_ids:
                users = await db.users.find({"id": {"$in": data.user_ids}}, {"_id": 0, "email": 1, "name": 1}).to_list(100)
                recipients.extend(users)
            # Add external emails
            for email in data.external_emails:
                recipients.append({"email": email, "name": email.split("@")[0]})
            if recipients:
                await send_bulk_notifications({
                    "recipients": recipients,
                    "type": "conference_invite",
                    "data": {
                        "conference_title": data.title,
                        "host_name": host.get("name") if host else "Unknown",
                        "scheduled_at": data.scheduled_at.isoformat() if data.scheduled_at else "Now",
                        "join_link": join_link,
                        "meeting_code": meeting_code,
                    },
                })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Conference invite email failed: {e}")
    
    conference_doc.pop("_id", None)
    return conference_doc

@router.get("/{conference_id}")
async def get_conference(conference_id: str, db=Depends(get_db)):
    """Get conference details"""
    conf = await db.conferences.find_one({"id": conference_id}, {"_id": 0})
    if not conf:
        raise HTTPException(404, "Conference not found")
    return conf

@router.put("/{conference_id}")
async def update_conference(
    conference_id: str,
    data: ConferenceUpdate,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Update conference (host only)"""
    conf = await db.conferences.find_one({"id": conference_id})
    if not conf:
        raise HTTPException(404, "Conference not found")
    if conf.get("host_id") != user_id:
        raise HTTPException(403, "Only host can update conference")
    
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        await db.conferences.update_one({"id": conference_id}, {"$set": update_data})
    
    return {"success": True}

@router.delete("/{conference_id}")
async def delete_conference(
    conference_id: str,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Delete/cancel conference (host only)"""
    conf = await db.conferences.find_one({"id": conference_id})
    if not conf:
        raise HTTPException(404, "Conference not found")
    if conf.get("host_id") != user_id:
        raise HTTPException(403, "Only host can delete conference")
    
    # Delete associated calendar event
    if conf.get("calendar_event_id"):
        await db.events.delete_one({"id": conf["calendar_event_id"]})
    
    await db.conferences.delete_one({"id": conference_id})
    return {"success": True}

@router.post("/{conference_id}/invite")
async def invite_to_conference(
    conference_id: str,
    user_ids: List[str] = [],
    external_invites: List[ExternalInvite] = [],
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Add invites to conference"""
    conf = await db.conferences.find_one({"id": conference_id})
    if not conf:
        raise HTTPException(404, "Conference not found")
    
    update = {}
    if user_ids:
        update["$addToSet"] = {"invited_users": {"$each": user_ids}}
    if external_invites:
        new_externals = [
            {"email": inv.email, "name": inv.name, "invited_at": datetime.now(timezone.utc)}
            for inv in external_invites
        ]
        if "$addToSet" not in update:
            update["$addToSet"] = {}
        update["$addToSet"]["external_invites"] = {"$each": new_externals}
    
    if update:
        await db.conferences.update_one({"id": conference_id}, update)
    
    return {"success": True}

@router.post("/{conference_id}/join")
async def join_conference(
    conference_id: str,
    data: JoinRequest,
    user_id: Optional[str] = None,
    db=Depends(get_db)
):
    """Join a conference (returns connection info)"""
    conf = await db.conferences.find_one({"id": conference_id}, {"_id": 0})
    if not conf:
        raise HTTPException(404, "Conference not found")
    
    # Check password
    if conf.get("password") and data.password != conf["password"]:
        raise HTTPException(403, "Invalid password")
    
    # Check max participants
    if conf.get("max_participants"):
        current = len(conf.get("participants", []))
        if current >= conf["max_participants"]:
            raise HTTPException(403, "Conference is full")
    
    # Add participant
    participant = {
        "user_id": user_id,
        "display_name": data.display_name or "Guest",
        "joined_at": datetime.now(timezone.utc),
        "is_muted": False,
        "is_video_on": conf.get("is_video_enabled", True),
        "is_screen_sharing": False,
    }
    
    await db.conferences.update_one(
        {"id": conference_id},
        {
            "$push": {"participants": participant},
            "$set": {"status": "ongoing"}
        }
    )
    
    # Get ICE servers
    pbx_config = await db.pbx_configs.find_one({"is_default": True, "is_active": True})
    ice_servers = [{"urls": "stun:stun.l.google.com:19302"}]
    if pbx_config:
        ice_servers = [{"urls": s} for s in pbx_config.get("stun_servers", [])]
        ice_servers.extend(pbx_config.get("turn_servers", []))
    
    return {
        "conference": conf,
        "participant": participant,
        "ice_servers": ice_servers,
    }

@router.post("/{conference_id}/leave")
async def leave_conference(
    conference_id: str,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Leave a conference"""
    await db.conferences.update_one(
        {"id": conference_id},
        {"$pull": {"participants": {"user_id": user_id}}}
    )
    
    # Check if conference is empty
    conf = await db.conferences.find_one({"id": conference_id})
    if conf and len(conf.get("participants", [])) == 0:
        await db.conferences.update_one(
            {"id": conference_id},
            {"$set": {"status": "ended", "ended_at": datetime.now(timezone.utc)}}
        )
    
    return {"success": True}

@router.post("/{conference_id}/end")
async def end_conference(
    conference_id: str,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """End conference (host only)"""
    conf = await db.conferences.find_one({"id": conference_id})
    if not conf:
        raise HTTPException(404, "Conference not found")
    if conf.get("host_id") != user_id:
        raise HTTPException(403, "Only host can end conference")
    
    await db.conferences.update_one(
        {"id": conference_id},
        {"$set": {
            "status": "ended",
            "ended_at": datetime.now(timezone.utc),
            "participants": []
        }}
    )
    
    return {"success": True}

@router.get("/{conference_id}/participants")
async def get_participants(conference_id: str, db=Depends(get_db)):
    """Get current participants in conference"""
    conf = await db.conferences.find_one({"id": conference_id}, {"_id": 0, "participants": 1})
    if not conf:
        raise HTTPException(404, "Conference not found")
    return conf.get("participants", [])

@router.post("/{conference_id}/recording/start")
async def start_conference_recording(
    conference_id: str,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Start recording (host only)"""
    conf = await db.conferences.find_one({"id": conference_id})
    if not conf:
        raise HTTPException(404, "Conference not found")
    if conf.get("host_id") != user_id:
        raise HTTPException(403, "Only host can start recording")
    
    await db.conferences.update_one(
        {"id": conference_id},
        {"$set": {"is_recording": True, "recording_started_at": datetime.now(timezone.utc)}}
    )
    
    return {"success": True}

@router.post("/{conference_id}/recording/stop")
async def stop_conference_recording(
    conference_id: str,
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Stop recording"""
    await db.conferences.update_one(
        {"id": conference_id},
        {"$set": {"is_recording": False}}
    )
    return {"success": True}

# ============== INSTANT MEETING ==============

@router.post("/instant")
async def create_instant_meeting(
    title: str = "Instant Meeting",
    user_id: str = Query(...),
    db=Depends(get_db)
):
    """Create and start an instant meeting"""
    data = ConferenceCreate(
        title=title,
        scheduled_at=None,
        create_calendar_event=False,
        send_email_invites=False,
    )
    
    result = await create_conference(data, user_id, None, db)
    
    # Mark as ongoing immediately
    await db.conferences.update_one(
        {"id": result["id"]},
        {"$set": {"status": "ongoing", "started_at": datetime.now(timezone.utc)}}
    )
    result["status"] = "ongoing"
    
    return result

# ============== SCHEDULING HELPERS ==============

@router.get("/schedule/available-slots")
async def get_available_slots(
    user_ids: str = Query(..., description="Comma-separated user IDs"),
    date: str = Query(..., description="YYYY-MM-DD"),
    duration_minutes: int = 60,
    db=Depends(get_db)
):
    """Find available time slots when all users are free"""
    ids = [uid.strip() for uid in user_ids.split(",")]
    
    # Get events for all users on that date
    events = await db.events.find({
        "date": date,
        "$or": [
            {"created_by": {"$in": ids}},
            {"attendees": {"$in": ids}}
        ]
    }, {"_id": 0, "start_time": 1, "end_time": 1}).to_list(100)
    
    # Find free slots (simple implementation)
    busy_times = [(e.get("start_time", "00:00"), e.get("end_time", "23:59")) for e in events]
    
    # Generate available slots (9 AM to 6 PM, hourly)
    available = []
    for hour in range(9, 18):
        start = f"{hour:02d}:00"
        end = f"{hour + 1:02d}:00"
        is_free = True
        for busy_start, busy_end in busy_times:
            if not (end <= busy_start or start >= busy_end):
                is_free = False
                break
        if is_free:
            available.append({"start": start, "end": end})
    
    return {"date": date, "available_slots": available}
