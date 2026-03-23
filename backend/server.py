from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
import csv
import io
from dotenv import load_dotenv
from storage import init_storage
from deps import get_role_level, require_role, require_admin, require_director, require_manager, require_coordinator, require_staff, get_current_user, hash_password, verify_password, create_token
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import time
from collections import defaultdict
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
try:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
except Exception as e:
    logging.error(f"MongoDB connection error: {e}")
    client = None
    db = None

app = FastAPI(title="58:12 Global Connect API")
api_router = APIRouter(prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "58:12 Global Connect CRM"}


# Rate limiting middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[str, list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for WebSocket upgrades
        if request.headers.get("upgrade") == "websocket":
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = now - 60
        self.request_counts[client_ip] = [t for t in self.request_counts[client_ip] if t > window]
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in a minute."}
            )
        self.request_counts[client_ip].append(now)
        response = await call_next(request)
        return response

app.add_middleware(RateLimitMiddleware, requests_per_minute=120)

# Auth setup
SECRET_KEY = os.environ.get('SECRET_KEY', '5812global_secret_key_change_in_production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ========== MODELS (imported from models.py) ==========
from models import (
    UserRegister, UserLogin, UserOut, MemberCreate, MemberUpdate,
    EventCreate, EventUpdate, TaskCreate, TaskUpdate, CheckInCreate,
    VenueCreate, VenueUpdate, PublicBookingCreate, SpaceBookingCreate,
    FamilyCreate, ChildCreate, GuestCreate, AuditLogCreate,
)


# ========== AUTH HELPERS (imported from deps.py) ==========
from deps import normalize_gender, resolve_department


# ========== AUTH ROUTES (moved to routers/auth.py) ==========


# ========== MEMBERS ROUTES (moved to routers/members.py) ==========


# ========== EVENTS ==========

@api_router.get("/events")
async def list_events(
    search: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    is_public: Optional[bool] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    if type and type != "all":
        query["type"] = type
    if status and status != "all":
        query["status"] = status
    if is_public is not None:
        query["is_public"] = is_public
    
    events = await db.events.find(query, {"_id": 0}).sort("date", -1).to_list(200)
    return events

@api_router.post("/events")
async def create_event(data: EventCreate, current_user: dict = Depends(get_current_user)):
    event_id = f"evt_{str(uuid.uuid4())[:8]}"
    event = {
        "id": event_id,
        **data.model_dump(),
        "registered": 0,
        "status": "upcoming",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.events.insert_one(event)
    event.pop("_id", None)
    try:
        from routers.notifications import send_bulk_notifications
        recipient_roles = ["admin", "system_admin", "Executive Director", "Director", "Manager"]
        recipients = await db.users.find(
            {"role": {"$in": recipient_roles}, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1, "name": 1}
        ).to_list(200)
        if recipients:
            await send_bulk_notifications({
                "recipients": recipients,
                "type": "event_reminder",
                "data": {
                    "event_title": event.get("title"),
                    "date": event.get("date"),
                    "time": event.get("time"),
                    "location": event.get("location"),
                },
            })
    except Exception as e:
        logger.warning(f"Event notify failed: {e}")
    return event

@api_router.get("/events/{event_id}")
async def get_event(event_id: str, current_user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Get attendees
    attendees = await db.event_registrations.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    event["attendees"] = attendees
    # Get check-ins for this event
    checkins = await db.checkins.find({"event_id": event_id}, {"_id": 0}).to_list(500)
    event["checkins"] = checkins
    return event

@api_router.put("/events/{event_id}")
async def update_event(event_id: str, data: EventUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.events.update_one({"id": event_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    return event

@api_router.delete("/events/{event_id}")
async def delete_event(event_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.events.delete_one({"id": event_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event deleted"}


# ========== TASKS ==========

@api_router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if status and status != "all":
        query["status"] = status
    if priority and priority != "all":
        query["priority"] = priority
    if assignee:
        query["assignee"] = assignee
    
    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return tasks

@api_router.post("/tasks")
async def create_task(data: TaskCreate, current_user: dict = Depends(get_current_user)):
    task_id = f"task_{str(uuid.uuid4())[:8]}"
    task = {
        "id": task_id,
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.tasks.insert_one(task)
    task.pop("_id", None)
    return task

@api_router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return task

@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


# ========== CHECK-INS ==========

@api_router.get("/checkins")
async def list_checkins(
    event_id: Optional[str] = None,
    member_id: Optional[str] = None,
    type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if event_id:
        query["event_id"] = event_id
    if member_id:
        query["member_id"] = member_id
    if type and type != "all":
        query["type"] = type
    if search:
        query["member_name"] = {"$regex": search, "$options": "i"}
    
    checkins = await db.checkins.find(query, {"_id": 0}).sort("check_in_time", -1).to_list(1000)
    return checkins

@api_router.post("/checkins")
async def create_checkin(data: CheckInCreate, current_user: dict = Depends(get_current_user)):
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id,
        **data.model_dump(),
        "check_in_time": datetime.now(timezone.utc).isoformat(),
        "checked_in_by": current_user["id"],
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return checkin

@api_router.get("/checkins/stats")
async def get_checkin_stats(current_user: dict = Depends(get_current_user)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    total = await db.checkins.count_documents({})
    today = await db.checkins.count_documents({"check_in_time": {"$gte": today_start}})
    members = await db.checkins.count_documents({"type": "member"})
    visitors = await db.checkins.count_documents({"type": "visitor"})
    staff = await db.checkins.count_documents({"type": "staff"})
    return {"total": total, "today": today, "members": members, "visitors": visitors, "staff": staff}


# ========== VENUES ==========

@api_router.get("/venues")
async def list_venues(current_user: dict = Depends(get_current_user)):
    venues = await db.venues.find({}, {"_id": 0}).to_list(100)
    return venues

@api_router.post("/venues")
async def create_venue(data: VenueCreate, current_user: dict = Depends(get_current_user)):
    venue_id = f"ven_{str(uuid.uuid4())[:8]}"
    venue = {"id": venue_id, **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.venues.insert_one(venue)
    venue.pop("_id", None)
    return venue

@api_router.put("/venues/{venue_id}")
async def update_venue(venue_id: str, data: VenueUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.venues.update_one({"id": venue_id}, {"$set": update_data})
    venue = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    return venue

@api_router.delete("/venues/{venue_id}")
async def delete_venue(venue_id: str, current_user: dict = Depends(get_current_user)):
    await db.venues.delete_one({"id": venue_id})
    return {"message": "Venue deleted"}


# ========== PUBLIC ENDPOINTS ==========

@api_router.get("/public/events")
async def public_events():
    events = await db.events.find(
        {"is_public": True, "status": "upcoming"},
        {"_id": 0}
    ).sort("date", 1).to_list(50)
    return events

@api_router.get("/public/venues")
async def public_venues():
    venues = await db.venues.find({"available": True}, {"_id": 0}).to_list(50)
    return venues

@api_router.post("/public/bookings/event")
async def public_book_event(data: PublicBookingCreate):
    # Check event
    event = await db.events.find_one({"id": data.event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.get("registered", 0) >= event.get("capacity", 0):
        raise HTTPException(status_code=400, detail="Event is fully booked")
    
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id,
        **data.model_dump(),
        "status": "confirmed",
        "ticket_ids": [f"TKT-{str(uuid.uuid4())[:4].upper()}" for _ in range(data.num_tickets)],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    
    # Increment registered count
    await db.events.update_one({"id": data.event_id}, {"$inc": {"registered": data.num_tickets}})
    
    booking.pop("_id", None)
    return booking

@api_router.post("/public/bookings/space")
async def public_book_space(data: SpaceBookingCreate):
    venue = await db.venues.find_one({"id": data.venue_id})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    
    booking_id = f"book_{str(uuid.uuid4())[:12]}"
    booking = {
        "id": booking_id,
        **data.model_dump(),
        "type": "space",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_bookings.insert_one(booking)
    booking.pop("_id", None)
    return booking

@api_router.get("/public/bookings/status")
async def check_booking_status(booking_id: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None):
    query = {}
    if booking_id:
        query["id"] = booking_id
    elif email:
        query["email"] = email.lower()
    elif phone:
        query["phone"] = phone
    else:
        raise HTTPException(status_code=400, detail="Provide booking_id, email, or phone")
    
    bookings = await db.public_bookings.find(query, {"_id": 0}).to_list(20)
    return bookings


# ========== KIOSK ==========

@api_router.post("/kiosk/checkin")
async def kiosk_checkin(data: CheckInCreate):
    """Public check-in endpoint for the kiosk"""
    # Try to find member by national_id if provided
    member = None
    if data.member_id:
        member = await db.members.find_one({"id": data.member_id}, {"_id": 0})
    
    ci_id = f"ci_{str(uuid.uuid4())[:8]}"
    checkin = {
        "id": ci_id,
        **data.model_dump(),
        "check_in_time": datetime.now(timezone.utc).isoformat(),
        "source": "kiosk",
    }
    await db.checkins.insert_one(checkin)
    checkin.pop("_id", None)
    return checkin

@api_router.get("/kiosk/lookup")
async def kiosk_lookup(identifier: str):
    """Look up a member by national ID, phone, or email"""
    member = await db.members.find_one(
        {"$or": [
            {"national_id": identifier},
            {"phone": identifier},
            {"email": identifier.lower()},
        ]},
        {"_id": 0, "password_hash": 0}
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


# ========== SEED ENDPOINT ==========

@api_router.post("/seed")
async def seed_data():
    """Seed the database with initial data"""
    # Create admin user
    existing_admin = await db.users.find_one({"email": "admin@5812global.org"})
    if not existing_admin:
        admin = {
            "id": str(uuid.uuid4()),
            "name": "Admin User",
            "email": "admin@5812global.org",
            "phone": "+256 800 5812",
            "password_hash": hash_password("Admin@1234"),
            "role": "admin",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(admin)

    # Seed members
    member_count = await db.members.count_documents({})
    if member_count == 0:
        members = [
            {"id": "mem_001", "name": "Alice Namukasa", "email": "alice@example.com", "phone": "+256 700 123456", "national_id": "CM900001000XXXX", "role": "Member", "status": "active", "join_date": "2024-01-15", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_002", "name": "Brian Ssekitto", "email": "brian@example.com", "phone": "+256 752 234567", "national_id": "CM850002000XXXX", "role": "Staff", "status": "active", "join_date": "2023-06-10", "group": "Leadership", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_003", "name": "Catherine Nakato", "email": "catherine@example.com", "phone": "+256 781 345678", "national_id": "CM920003000XXXX", "role": "Member", "status": "active", "join_date": "2024-03-20", "group": "Women", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_004", "name": "David Kiggundu", "email": "david@example.com", "phone": "+256 706 456789", "national_id": "CM880004000XXXX", "role": "Volunteer", "status": "active", "join_date": "2023-11-05", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_005", "name": "Esther Namirembe", "email": "esther@example.com", "phone": "+256 773 567890", "national_id": "CM950005000XXXX", "role": "Member", "status": "inactive", "join_date": "2022-08-30", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_006", "name": "Francis Tumwesigye", "email": "francis@example.com", "phone": "+256 712 678901", "national_id": "CM780006000XXXX", "role": "Leader", "status": "active", "join_date": "2021-05-12", "group": "Leadership", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_007", "name": "Grace Akello", "email": "grace@example.com", "phone": "+256 756 789012", "national_id": "CM960007000XXXX", "role": "Member", "status": "active", "join_date": "2024-07-01", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_008", "name": "Henry Wasswa", "email": "henry@example.com", "phone": "+256 701 890123", "national_id": "CM820008000XXXX", "role": "Staff", "status": "active", "join_date": "2023-01-18", "group": "Admin", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_009", "name": "Irene Nabatanzi", "email": "irene@example.com", "phone": "+256 784 901234", "national_id": "CM990009000XXXX", "role": "Member", "status": "active", "join_date": "2025-01-10", "group": "Women", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_010", "name": "Joseph Muwanguzi", "email": "joseph@example.com", "phone": "+256 715 012345", "national_id": "CM870010000XXXX", "role": "Volunteer", "status": "inactive", "join_date": "2022-04-22", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.members.insert_many(members)

    # Seed events
    event_count = await db.events.count_documents({})
    if event_count == 0:
        events = [
            {"id": "evt_001", "title": "Sunday Service", "type": "service", "status": "upcoming", "date": "2026-04-06", "time": "09:00", "end_time": "11:30", "location": "58:12 Global Centre", "capacity": 300, "registered": 212, "description": "Weekly Sunday worship service.", "is_public": True, "is_free": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_002", "title": "Youth Leadership Summit", "type": "conference", "status": "upcoming", "date": "2026-04-12", "time": "10:00", "end_time": "17:00", "location": "Kampala Conference Hall", "capacity": 100, "registered": 87, "description": "Annual leadership development summit.", "is_public": True, "is_free": False, "price": 25000, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_003", "title": "Community Outreach", "type": "community", "status": "upcoming", "date": "2026-04-19", "time": "08:00", "end_time": "14:00", "location": "Nakawa Market Area", "capacity": 50, "registered": 34, "description": "Community service outreach.", "is_public": False, "is_free": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_004", "title": "Women in Faith Conference", "type": "conference", "status": "upcoming", "date": "2026-04-26", "time": "09:00", "end_time": "16:00", "location": "58:12 Global Centre", "capacity": 150, "registered": 102, "description": "Annual conference empowering women.", "is_public": True, "is_free": False, "price": 15000, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_005", "title": "Staff Meeting", "type": "meeting", "status": "upcoming", "date": "2026-04-02", "time": "14:00", "end_time": "16:00", "location": "Admin Block", "capacity": 20, "registered": 15, "description": "Monthly all-staff meeting.", "is_public": False, "is_free": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_006", "title": "Easter Sunday Service", "type": "service", "status": "completed", "date": "2026-03-31", "time": "07:00", "end_time": "11:00", "location": "58:12 Global Centre", "capacity": 500, "registered": 487, "description": "Easter Sunday special service.", "is_public": True, "is_free": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_007", "title": "QR Test Event", "type": "meeting", "status": "upcoming", "date": "2026-04-01", "time": "10:00", "end_time": "12:00", "location": "Tech Lab", "capacity": 100, "registered": 11, "description": "Event for testing QR code check-in.", "is_public": True, "is_free": True, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.events.insert_many(events)

    # Seed tasks
    task_count = await db.tasks.count_documents({})
    if task_count == 0:
        tasks = [
            {"id": "task_001", "title": "Prepare Easter sermon notes", "description": "Compile sermon notes", "status": "done", "priority": "high", "assignee": "Brian Ssekitto", "due_date": "2026-03-30", "tags": ["sermon"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_002", "title": "Send membership renewal reminders", "description": "Email members expiring in April", "status": "in-progress", "priority": "high", "assignee": "Henry Wasswa", "due_date": "2026-04-05", "tags": ["membership"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_003", "title": "Set up Youth Summit registration", "description": "Configure online registration", "status": "in-progress", "priority": "medium", "assignee": "Alice Namukasa", "due_date": "2026-04-08", "tags": ["events"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_004", "title": "Update website event listings", "description": "Add April events to website", "status": "todo", "priority": "medium", "assignee": "Grace Akello", "due_date": "2026-04-10", "tags": ["website"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_005", "title": "Volunteer coordination for outreach", "description": "Assign volunteers to stations", "status": "todo", "priority": "high", "assignee": "David Kiggundu", "due_date": "2026-04-15", "tags": ["volunteers"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_006", "title": "Purchase office supplies", "description": "Order printer cartridges and stationery", "status": "todo", "priority": "low", "assignee": "Irene Nabatanzi", "due_date": "2026-04-20", "tags": ["admin"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_007", "title": "Finalize Women Conference speakers", "description": "Confirm all 5 speakers", "status": "in-progress", "priority": "high", "assignee": "Catherine Nakato", "due_date": "2026-04-12", "tags": ["events"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_008", "title": "Monthly financial report", "description": "Compile March financial report", "status": "done", "priority": "high", "assignee": "Francis Tumwesigye", "due_date": "2026-04-05", "tags": ["finance"], "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.tasks.insert_many(tasks)

    # Seed venues
    venue_count = await db.venues.count_documents({})
    if venue_count == 0:
        venues = [
            {"id": "ven_001", "name": "Main Auditorium", "capacity": 500, "type": "auditorium", "available": True, "hourly_rate": None, "description": "Main worship hall with full AV system.", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_002", "name": "Conference Room A", "capacity": 40, "type": "conference", "available": True, "hourly_rate": 20000, "description": "Small conference room with projector.", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_003", "name": "Youth Hall", "capacity": 150, "type": "hall", "available": False, "hourly_rate": 50000, "description": "Large multipurpose hall.", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_004", "name": "Prayer Garden", "capacity": 30, "type": "outdoor", "available": True, "hourly_rate": None, "description": "Peaceful outdoor garden space.", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.venues.insert_many(venues)

    # Seed checkins
    checkin_count = await db.checkins.count_documents({})
    if checkin_count == 0:
        checkins = [
            {"id": "ci_001", "member_id": "mem_001", "member_name": "Alice Namukasa", "type": "member", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "qr", "check_in_time": "2026-03-31T08:45:00Z", "source": "kiosk"},
            {"id": "ci_002", "member_id": "mem_002", "member_name": "Brian Ssekitto", "type": "staff", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "manual", "check_in_time": "2026-03-31T07:30:00Z", "source": "manual"},
            {"id": "ci_003", "member_id": None, "member_name": "Visitor - John Doe", "type": "visitor", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "manual", "check_in_time": "2026-03-31T09:05:00Z", "source": "kiosk"},
            {"id": "ci_004", "member_id": "mem_003", "member_name": "Catherine Nakato", "type": "member", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "id", "check_in_time": "2026-03-31T09:10:00Z", "source": "kiosk"},
        ]
        await db.checkins.insert_many(checkins)

    return {"message": "Database seeded successfully", "admin_email": "admin@5812global.org", "admin_password": "Admin@1234"}


# ========== APP SETUP ==========

# ========== FINANCIAL MODELS ==========

class DonationCreate(BaseModel):
    donor_name: str
    amount: float
    currency: str = "UGX"
    type: str = "tithe"
    date: Optional[str] = None
    notes: Optional[str] = None
    member_id: Optional[str] = None
    location_id: Optional[str] = None

class ExpenseCreate(BaseModel):
    title: str
    amount: float
    currency: str = "UGX"
    category: str = "general"
    date: Optional[str] = None
    notes: Optional[str] = None
    submitted_by: Optional[str] = None
    location_id: Optional[str] = None

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    currency: str = "UGX"
    stock: int = 0
    category: Optional[str] = None
    sku: Optional[str] = None
    reorder_level: int = 5
    location_id: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None
    reorder_level: Optional[int] = None
    location_id: Optional[str] = None

class SaleCreate(BaseModel):
    items: List[dict]
    customer_name: Optional[str] = "Walk-in Customer"
    customer_phone: Optional[str] = None
    total: float
    payment_method: str = "cash"
    notes: Optional[str] = None
    location_id: Optional[str] = None


# ========== FINANCIAL ROUTES ==========

@api_router.get("/financial/summary")
async def financial_summary(location_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).isoformat()[:7]
    loc_match = {"location_id": location_id} if location_id else {}

    pipeline_donations = [
        {"$match": {**loc_match, "date": {"$regex": f"^{month_start}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    pipeline_expenses = [
        {"$match": {**loc_match, "date": {"$regex": f"^{month_start}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    pipeline_sales = [
        {"$match": {**loc_match, "created_at": {"$regex": f"^{month_start}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]

    donations_result = await db.donations.aggregate(pipeline_donations).to_list(1)
    expenses_result = await db.expenses.aggregate(pipeline_expenses).to_list(1)
    sales_result = await db.sales.aggregate(pipeline_sales).to_list(1)

    monthly_donations = donations_result[0]["total"] if donations_result else 0
    monthly_expenses = expenses_result[0]["total"] if expenses_result else 0
    monthly_sales = sales_result[0]["total"] if sales_result else 0

    # All-time totals for cashflow
    all_donations = await db.donations.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_expenses = await db.expenses.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_sales = await db.sales.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)

    total_in = (all_donations[0]["total"] if all_donations else 0) + (all_sales[0]["total"] if all_sales else 0)
    total_out = all_expenses[0]["total"] if all_expenses else 0

    return {
        "monthly_donations": monthly_donations,
        "monthly_expenses": monthly_expenses,
        "monthly_sales": monthly_sales,
        "cashflow_in": total_in,
        "cashflow_out": total_out,
        "net_balance": total_in - total_out,
    }

@api_router.post("/financial/distribute-funds")
async def distribute_funds(data: dict, current_user: dict = Depends(require_director)):
    """Distribute funds from one location to another"""
    from_location_id = data.get("from_location_id")
    to_location_id = data.get("to_location_id")
    amount = float(data.get("amount", 0))
    currency = data.get("currency", "UGX")
    notes = data.get("notes", "")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    transfer_id = f"tfr_{str(uuid.uuid4())[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    # Create expense at source
    await db.expenses.insert_one({
        "id": f"exp_{str(uuid.uuid4())[:8]}", "title": f"Fund transfer to {to_location_id}",
        "amount": amount, "currency": currency, "category": "transfer",
        "date": now[:10], "notes": f"Transfer {transfer_id}: {notes}",
        "location_id": from_location_id, "transfer_id": transfer_id,
        "created_at": now, "created_by": current_user["id"],
    })
    # Create donation at destination
    await db.donations.insert_one({
        "id": f"don_{str(uuid.uuid4())[:8]}", "donor_name": "Internal Transfer",
        "amount": amount, "currency": currency, "type": "transfer",
        "date": now[:10], "notes": f"Transfer {transfer_id} from {from_location_id}: {notes}",
        "location_id": to_location_id, "transfer_id": transfer_id,
        "created_at": now, "created_by": current_user["id"],
    })
    await _audit(current_user["id"], "create", "fund_transfer", transfer_id)
    try:
        from routers.notifications import send_bulk_notifications
        recipient_roles = ["admin", "system_admin", "Executive Director", "Director", "Manager"]
        recipients = await db.users.find(
            {"role": {"$in": recipient_roles}, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1, "name": 1}
        ).to_list(200)
        if recipients:
            await send_bulk_notifications({
                "recipients": recipients,
                "type": "fund_transfer",
                "data": {
                    "amount": amount,
                    "currency": currency,
                    "from_location": from_location_id,
                    "to_location": to_location_id,
                    "notes": notes,
                },
            })
    except Exception as e:
        logger.warning(f"Fund transfer notify failed: {e}")
    return {"transfer_id": transfer_id, "amount": amount, "from": from_location_id, "to": to_location_id}

@api_router.get("/financial/donations")
async def list_donations(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    donations = await db.donations.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return donations

@api_router.post("/financial/donations")
async def create_donation(data: DonationCreate, current_user: dict = Depends(require_staff)):
    doc = {
        "id": f"don_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "date": data.date or datetime.now(timezone.utc).isoformat()[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.donations.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "donation", doc["id"])
    return doc

@api_router.get("/financial/expenses")
async def list_expenses(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return expenses

@api_router.post("/financial/expenses")
async def create_expense(data: ExpenseCreate, current_user: dict = Depends(require_manager)):
    doc = {
        "id": f"exp_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "date": data.date or datetime.now(timezone.utc).isoformat()[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.expenses.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "expense", doc["id"])
    return doc

# ========== PRODUCTS / SALES ==========

@api_router.get("/products")
async def list_products(current_user: dict = Depends(get_current_user)):
    products = await db.products.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return products

@api_router.post("/products")
async def create_product(data: ProductCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"prod_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.products.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    return product

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    await db.products.delete_one({"id": product_id})
    return {"message": "Product deleted"}

@api_router.get("/sales")
async def list_sales(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
    sales = await db.sales.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return sales

@api_router.post("/sales")
async def create_sale(data: SaleCreate, current_user: dict = Depends(get_current_user)):
    sale_id = f"inv_{str(uuid.uuid4())[:8].upper()}"
    doc = {
        "id": sale_id,
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "cashier": current_user.get("name", "Unknown"),
    }
    await db.sales.insert_one(doc)
    # Decrement stock for each product
    for item in data.items:
        if item.get("product_id"):
            await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": -item.get("qty", 1)}})
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "sale", sale_id)
    return doc

# ========== FAMILIES, CHILDREN, GUESTS (moved to routers/members.py) ==========

# ========== AUDIT TRAIL ==========

async def _audit(user_id: str, action: str, resource: str, resource_id: str = None, details: dict = None):
    """Internal helper to log audit events"""
    try:
        await db.audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

@api_router.get("/audit")
async def list_audit(skip: int = 0, limit: int = 100, current_user: dict = Depends(require_admin)):
    if current_user.get("role") not in ("admin", "system_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    logs = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.audit_log.count_documents({})
    return {"logs": logs, "total": total}

# ========== ENHANCED DASHBOARD ==========

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start_str = now.replace(day=1).isoformat()[:7]  # "2026-04"

    total_members = await db.members.count_documents({})
    active_members = await db.members.count_documents({"status": "active"})
    total_families = await db.families.count_documents({})
    total_children = await db.children.count_documents({})

    events_this_month = await db.events.count_documents({"date": {"$regex": f"^{month_start_str}"}})
    upcoming_events = await db.events.count_documents({"status": "upcoming"})

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    checkins_today = await db.checkins.count_documents({"check_in_time": {"$gte": today_start}})

    now_str = now.isoformat()[:10]
    tasks_overdue = await db.tasks.count_documents({"status": {"$nin": ["done"]}, "due_date": {"$lt": now_str, "$ne": ""}})

    new_members_this_month = await db.members.count_documents({"join_date": {"$regex": f"^{month_start_str}"}})

    # Monthly revenue
    sales_result = await db.sales.aggregate([
        {"$match": {"created_at": {"$regex": f"^{month_start_str}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]).to_list(1)
    monthly_sales = sales_result[0]["total"] if sales_result else 0

    donations_result = await db.donations.aggregate([
        {"$match": {"date": {"$regex": f"^{month_start_str}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]).to_list(1)
    monthly_donations = donations_result[0]["total"] if donations_result else 0

    # Low stock products
    low_stock = await db.products.count_documents({"$expr": {"$lte": ["$stock", "$reorder_level"]}})

    # Recent activity
    recent_checkins = await db.checkins.find({}, {"_id": 0}).sort("check_in_time", -1).limit(3).to_list(3)
    recent_members = await db.members.find({}, {"_id": 0}).sort("created_at", -1).limit(2).to_list(2)

    activity = []
    for ci in recent_checkins:
        activity.append({
            "type": "checkin",
            "message": f"{ci.get('member_name')} checked in" + (f" to {ci.get('event_name', '')}" if ci.get('event_name') else ""),
            "time": ci.get("check_in_time", ""),
        })
    for m in recent_members:
        activity.append({
            "type": "member",
            "message": f"New member: {m.get('name')} registered",
            "time": m.get("created_at", ""),
        })
    activity.sort(key=lambda x: x.get("time", ""), reverse=True)

    return {
        "total_members": total_members,
        "active_members": active_members,
        "total_families": total_families,
        "total_children": total_children,
        "events_this_month": events_this_month,
        "upcoming_events": upcoming_events,
        "checkins_today": checkins_today,
        "tasks_overdue": tasks_overdue,
        "new_members_this_month": new_members_this_month,
        "monthly_sales": monthly_sales,
        "monthly_donations": monthly_donations,
        "low_stock_count": low_stock,
        "recent_activity": activity[:5],
    }

# ========== PEOPLE STATS ==========

@api_router.get("/people/stats")
async def people_stats(current_user: dict = Depends(get_current_user)):
    return {
        "total_members": await db.members.count_documents({}),
        "active_members": await db.members.count_documents({"status": "active"}),
        "total_families": await db.families.count_documents({}),
        "total_children": await db.children.count_documents({}),
        "total_guests": await db.guests.count_documents({}),
        "pending_approvals": await db.users.count_documents({"status": "pending"}),
    }

# ========== SEED EXTENDED DATA ==========

@api_router.post("/seed-extended")
async def seed_extended():
    """Seed additional data for financial/products/families/children"""
    # Products
    product_count = await db.products.count_documents({})
    if product_count == 0:
        products = [
            {"id": "prod_001", "name": "4 Week Broiler Chicken", "price": 10000, "currency": "UGX", "stock": 198, "category": "Farm", "reorder_level": 20, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_002", "name": "Coffee", "price": 20000, "currency": "UGX", "stock": 0, "category": "Beverages", "reorder_level": 10, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_003", "name": "Eggs (Tray)", "price": 10000, "currency": "UGX", "stock": 0, "category": "Farm", "reorder_level": 15, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_004", "name": "Local Chicken", "price": 40000, "currency": "UGX", "stock": 20, "category": "Farm", "reorder_level": 5, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_005", "name": "2 Month Old Chicken", "price": 20000, "currency": "UGX", "stock": 20, "category": "Farm", "reorder_level": 10, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_006", "name": "Tea T-Shirt", "price": 25000, "currency": "UGX", "stock": 100, "category": "Merchandise", "reorder_level": 15, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.products.insert_many(products)

    # Families
    family_count = await db.families.count_documents({})
    if family_count == 0:
        families = [
            {"id": "fam_001", "family_name": "Nakato Family", "primary_contact_name": "Sarah Nakato", "primary_contact_email": "parent1@example.com", "primary_contact_phone": "+256 700 111001", "address": "Kampala", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_002", "family_name": "Ssekitto Family", "primary_contact_name": "James Ssekitto", "primary_contact_email": "james@example.com", "primary_contact_phone": "+256 700 222002", "address": "Entebbe", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_003", "family_name": "Kiggundu Family", "primary_contact_name": "Mary Kiggundu", "primary_contact_email": "mary@example.com", "primary_contact_phone": "+256 700 333003", "address": "Jinja", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.families.insert_many(families)

    # Children
    child_count = await db.children.count_documents({})
    if child_count == 0:
        children = [
            {"id": "chd_001", "name": "Emma Nakato", "date_of_birth": "2016-03-15", "gender": "female", "family_id": "fam_001", "class_group": "Primary 4", "medical_notes": "Nut allergy - carry epipen", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_002", "name": "Daniel Nakato", "date_of_birth": "2018-07-22", "gender": "male", "family_id": "fam_001", "class_group": "Primary 2", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_003", "name": "Peter Ssekitto", "date_of_birth": "2015-11-08", "gender": "male", "family_id": "fam_002", "class_group": "Primary 5", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_004", "name": "Grace Kiggundu", "date_of_birth": "2019-04-30", "gender": "female", "family_id": "fam_003", "class_group": "Nursery", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.children.insert_many(children)

    # Donations
    donation_count = await db.donations.count_documents({})
    if donation_count == 0:
        donations = [
            {"id": "don_001", "donor_name": "Alice Namukasa", "amount": 50000, "currency": "UGX", "type": "tithe", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_002", "donor_name": "Brian Ssekitto", "amount": 30000, "currency": "UGX", "type": "offering", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_003", "donor_name": "Anonymous", "amount": 100000, "currency": "UGX", "type": "donation", "date": "2026-04-06", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_004", "donor_name": "Francis Tumwesigye", "amount": 75000, "currency": "UGX", "type": "tithe", "date": "2026-03-25", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.donations.insert_many(donations)

    # Expenses
    expense_count = await db.expenses.count_documents({})
    if expense_count == 0:
        expenses = [
            {"id": "exp_001", "title": "Electricity Bill", "amount": 85000, "currency": "UGX", "category": "utilities", "date": "2026-04-02", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_002", "title": "Caretaker Salary", "amount": 150000, "currency": "UGX", "category": "salaries", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_003", "title": "Office Supplies", "amount": 25000, "currency": "UGX", "category": "supplies", "date": "2026-03-28", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.expenses.insert_many(expenses)

    return {"message": "Extended seed data added"}


# ========== LOCATION MODELS ==========

class LocationCreate(BaseModel):
    name: str
    code: Optional[str] = None
    type: str = "compass"  # main, compass, sub-location
    parent_id: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    currency: str = "USD"
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    director_id: Optional[str] = None
    is_venue: bool = False
    is_bookable: bool = False
    is_restricted: bool = False
    departments: Optional[List[str]] = []

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    director_id: Optional[str] = None
    is_venue: Optional[bool] = None
    is_bookable: Optional[bool] = None
    is_restricted: Optional[bool] = None
    departments: Optional[List[str]] = None
    active: Optional[bool] = None

# ========== NOTIFICATION MODEL ==========

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"
    target_role: Optional[str] = None
    link: Optional[str] = None

# ========== LOCATION ROUTES ==========

@api_router.get("/locations")
async def list_locations(current_user: dict = Depends(get_current_user)):
    locs = await db.locations.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return locs

@api_router.post("/locations")
async def create_location(data: LocationCreate, current_user: dict = Depends(require_admin)):
    doc = {
        "id": f"loc_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "active": True,
        "member_count": 0,
        "staff_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.locations.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "location", doc["id"])
    return doc

@api_router.put("/locations/{loc_id}")
async def update_location(loc_id: str, data: LocationUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.locations.update_one({"id": loc_id}, {"$set": update_data})
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0})
    return loc

@api_router.get("/locations/{loc_id}/staff")
async def get_location_staff(loc_id: str, current_user: dict = Depends(get_current_user)):
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    staff_ids = loc.get("staff_ids", [])
    if not staff_ids:
        return []
    staff = await db.members.find({"id": {"$in": staff_ids}}, {"_id": 0}).to_list(100)
    return staff

@api_router.put("/locations/{loc_id}/assign-staff")
async def assign_staff_to_location(loc_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    staff_ids = data.get("staff_ids", [])
    await db.locations.update_one({"id": loc_id}, {"$set": {"staff_ids": staff_ids}})
    return {"message": "Staff assigned"}

@api_router.put("/locations/{loc_id}/director")
async def set_location_director(loc_id: str, data: dict, current_user: dict = Depends(require_admin)):
    director_id = data.get("director_id")
    await db.locations.update_one({"id": loc_id}, {"$set": {"director_id": director_id}})
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0})
    return loc

@api_router.get("/exchange-rate")
async def get_exchange_rate(from_currency: str = "UGX", to_currency: str = "USD"):
    """Simple exchange rate lookup - in production, integrate with a rate API"""
    rates_to_usd = {
        "USD": 1.0, "UGX": 0.00027, "KES": 0.0077, "TZS": 0.00039,
        "RWF": 0.00074, "GBP": 1.27, "EUR": 1.09, "ZAR": 0.055,
        "NGN": 0.00065, "GHS": 0.063, "ETB": 0.008,
    }
    from_rate = rates_to_usd.get(from_currency.upper(), 1.0)
    to_rate = rates_to_usd.get(to_currency.upper(), 1.0)
    rate = from_rate / to_rate if to_rate else 1.0
    return {"from": from_currency, "to": to_currency, "rate": round(rate, 6)}

@api_router.delete("/locations/{loc_id}")
async def delete_location(loc_id: str, current_user: dict = Depends(require_admin)):
    await db.locations.delete_one({"id": loc_id})
    return {"message": "Location deleted"}

# ========== NOTIFICATION ROUTES ==========

@api_router.get("/notifications")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    notifs = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    user_id = current_user["id"]
    for n in notifs:
        n["read"] = user_id in n.get("read_by", [])
    return notifs

@api_router.get("/notifications/unread-count")
async def unread_notification_count(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}], "read_by": {"$ne": user_id}}
    count = await db.notifications.count_documents(query)
    return {"count": count}

@api_router.put("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    await db.notifications.update_many(query, {"$addToSet": {"read_by": user_id}})
    return {"message": "All marked as read"}

@api_router.put("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": notif_id}, {"$addToSet": {"read_by": current_user["id"]}})
    return {"message": "Marked as read"}

@api_router.post("/notifications")
async def create_notification(data: NotificationCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"notif_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "read_by": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.notifications.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.delete_one({"id": notif_id})
    return {"message": "Notification deleted"}


# ========== WEB PUSH SUBSCRIPTIONS ==========

@api_router.post("/push/subscribe")
async def subscribe_push(data: dict, current_user: dict = Depends(get_current_user)):
    """Store web push subscription for user"""
    subscription = data.get("subscription")
    if not subscription or not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Invalid push subscription")
    await db.push_subscriptions.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"user_id": current_user["id"], "subscription": subscription, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"message": "Push subscription saved"}


@api_router.delete("/push/subscribe")
async def unsubscribe_push(current_user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": current_user["id"]})
    return {"message": "Push subscription removed"}


@api_router.get("/push/vapid-key")
async def get_vapid_key():
    """Return the public VAPID key for push subscriptions"""
    pub_key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return {"publicKey": pub_key}


async def send_push_to_user(user_id: str, title: str, body: str, url: str = "/"):
    """Send a real push notification to a user via pywebpush"""
    try:
        from pywebpush import webpush
        subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(10)
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
        vapid_email = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@5812global.org")
        if not vapid_private:
            return
        import json
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": f"5812-{user_id[:8]}"})
        for sub in subs:
            try:
                webpush(
                    subscription_info=sub["subscription"],
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": f"mailto:{vapid_email}"},
                )
            except Exception as e:
                if "410" in str(e) or "404" in str(e):
                    await db.push_subscriptions.delete_one({"user_id": user_id, "subscription.endpoint": sub["subscription"].get("endpoint")})
    except Exception as e:
        logger.warning(f"Push failed: {e}")


async def send_push_to_role(min_level: int, title: str, body: str, url: str = "/"):
    """Send push to all users with role >= min_level"""
    try:
        role_map = {"system_admin": 10, "admin": 10, "Executive Director": 9, "Director": 8, "Manager": 7, "Coordinator": 6, "Staff": 5}
        eligible_roles = [r for r, l in role_map.items() if l >= min_level]
        users = await db.users.find({"role": {"$in": eligible_roles}}, {"_id": 0, "id": 1}).to_list(100)
        for u in users:
            await send_push_to_user(u["id"], title, body, url)
    except Exception as e:
        logger.warning(f"Role push failed: {e}")


# ========== OFFLINE SYNC ==========

@api_router.post("/sync/messages")
async def sync_offline_messages(data: dict, current_user: dict = Depends(get_current_user)):
    """Receive queued messages from offline clients"""
    messages = data.get("messages", [])
    synced = 0
    for msg in messages:
        if not msg.get("conversation_id") or not msg.get("text"):
            continue
        existing = await db.chat_messages.find_one({"id": msg.get("id")})
        if existing:
            continue
        doc = {
            "id": msg.get("id", f"msg_{str(uuid.uuid4())[:8]}"),
            "conversation_id": msg["conversation_id"],
            "sender_id": current_user["id"],
            "sender_name": current_user.get("name", "Unknown"),
            "text": msg["text"],
            "type": "text",
            "reply_to": msg.get("reply_to"),
            "read_by": [current_user["id"]],
            "created_at": msg.get("created_at", datetime.now(timezone.utc).isoformat()),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.chat_messages.insert_one(doc)
        synced += 1
    return {"synced": synced}


# ========== BIOMETRIC / NFC REGISTRATION ==========

@api_router.post("/biometric/register")
async def register_biometric(data: dict, current_user: dict = Depends(get_current_user)):
    """Register a WebAuthn credential for biometric access"""
    member_id = data.get("member_id") or current_user["id"]
    credential_id = data.get("credential_id")
    public_key = data.get("public_key")
    authenticator_type = data.get("type", "platform")  # platform or cross-platform
    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id required")
    doc = {
        "id": f"bio_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "credential_id": credential_id,
        "public_key": public_key,
        "type": authenticator_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
    }
    await db.biometric_credentials.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/biometric/verify")
async def verify_biometric(data: dict):
    """Verify a biometric credential for scan-in/out"""
    credential_id = data.get("credential_id")
    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id required")
    cred = await db.biometric_credentials.find_one({"credential_id": credential_id}, {"_id": 0})
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    await db.biometric_credentials.update_one(
        {"credential_id": credential_id},
        {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}}
    )
    member = await db.members.find_one({"id": cred["member_id"]}, {"_id": 0, "id": 1, "name": 1, "role": 1})
    return {"verified": True, "member": member, "credential_type": cred.get("type")}


@api_router.post("/nfc/register")
async def register_nfc(data: dict, current_user: dict = Depends(get_current_user)):
    """Register an NFC tag serial number for a member"""
    member_id = data.get("member_id")
    serial_number = data.get("serial_number")
    if not member_id or not serial_number:
        raise HTTPException(status_code=400, detail="member_id and serial_number required")
    existing = await db.nfc_tags.find_one({"serial_number": serial_number})
    if existing:
        raise HTTPException(status_code=409, detail="NFC tag already registered")
    doc = {
        "id": f"nfc_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "serial_number": serial_number,
        "registered_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.nfc_tags.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/nfc/scan")
async def scan_nfc(data: dict):
    """Scan an NFC tag and return the associated member"""
    serial_number = data.get("serial_number")
    if not serial_number:
        raise HTTPException(status_code=400, detail="serial_number required")
    tag = await db.nfc_tags.find_one({"serial_number": serial_number}, {"_id": 0})
    if not tag:
        raise HTTPException(status_code=404, detail="NFC tag not registered")
    member = await db.members.find_one({"id": tag["member_id"]}, {"_id": 0, "id": 1, "name": 1, "role": 1, "group": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"member": member, "tag_id": tag["id"]}

# ========== GLOBAL SEARCH ==========

@api_router.get("/search")
async def global_search(q: str, current_user: dict = Depends(get_current_user)):
    if not q or len(q.strip()) < 2:
        return {"results": []}
    pattern = {"$regex": q.strip(), "$options": "i"}
    results = []

    members = await db.members.find(
        {"$or": [{"name": pattern}, {"email": pattern}, {"phone": pattern}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).limit(5).to_list(5)
    for m in members:
        results.append({"type": "member", "id": m["id"], "title": m["name"], "subtitle": m.get("email", m.get("role", "")), "url": "/members"})

    events = await db.events.find(
        {"$or": [{"title": pattern}, {"location": pattern}]},
        {"_id": 0, "id": 1, "title": 1, "date": 1, "status": 1}
    ).limit(5).to_list(5)
    for e in events:
        results.append({"type": "event", "id": e["id"], "title": e["title"], "subtitle": e.get("date", ""), "url": "/events"})

    tasks = await db.tasks.find(
        {"$or": [{"title": pattern}, {"description": pattern}]},
        {"_id": 0, "id": 1, "title": 1, "status": 1, "priority": 1}
    ).limit(5).to_list(5)
    for t in tasks:
        results.append({"type": "task", "id": t["id"], "title": t["title"], "subtitle": f"{t.get('status', '')} · {t.get('priority', '')}", "url": "/tasks"})

    products = await db.products.find(
        {"name": pattern},
        {"_id": 0, "id": 1, "name": 1, "price": 1, "stock": 1}
    ).limit(3).to_list(3)
    for p in products:
        results.append({"type": "product", "id": p["id"], "title": p["name"], "subtitle": f"UGX {p.get('price', 0):,.0f} · Stock: {p.get('stock', 0)}", "url": "/sales"})

    return {"results": results}


# ========== CHAT & AI ROUTES ==========

@api_router.get("/chat/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """List conversations for current user"""
    convs = await db.conversations.find(
        {"participants": current_user["id"]}, {"_id": 0}
    ).sort("updated_at", -1).to_list(100)
    return convs

@api_router.post("/chat/conversations")
async def create_conversation(data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new conversation"""
    conv_type = data.get("type", "direct")  # direct, group, ai_assistant, announcements
    participants = data.get("participants", [])
    name = data.get("name", "")
    location_id = data.get("location_id")
    if current_user["id"] not in participants:
        participants.append(current_user["id"])
    doc = {
        "id": f"conv_{str(uuid.uuid4())[:8]}", "type": conv_type, "name": name,
        "participants": participants, "location_id": location_id,
        "created_by": current_user["id"], "is_no_reply": data.get("is_no_reply", False),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_message": None,
    }
    await db.conversations.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/chat/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, skip: int = 0, limit: int = 50, current_user: dict = Depends(get_current_user)):
    msgs = await db.chat_messages.find(
        {"conversation_id": conv_id}, {"_id": 0}
    ).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)
    return msgs

@api_router.post("/chat/conversations/{conv_id}/messages")
async def send_message(conv_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Send a message in a conversation"""
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text required")
    msg = {
        "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": conv_id,
        "sender_id": current_user["id"], "sender_name": current_user.get("name", "Unknown"),
        "text": text, "type": "text",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_messages.insert_one(msg)
    msg.pop("_id", None)
    await db.conversations.update_one(
        {"id": conv_id},
        {"$set": {"updated_at": msg["created_at"], "last_message": text[:100]}}
    )
    try:
        from routers.websocket import manager
        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
        participants = conv.get("participants", []) if conv else []
        if participants:
            await manager.send_to_users(participants, {
                "type": "chat_message",
                "conversation_id": conv_id,
                "message": msg,
            })
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")
    return msg

@api_router.post("/chat/ai-assistant")
async def ai_chat_assistant(data: dict, current_user: dict = Depends(get_current_user)):
    """AI Assistant powered by Gemini"""
    from dotenv import load_dotenv
    load_dotenv()
    message = data.get("message", "").strip()
    session_id = data.get("session_id", f"ai_{current_user['id']}")
    if not message:
        raise HTTPException(status_code=400, detail="Message required")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AI not configured")
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message="You are a helpful AI assistant for 58:12 Global Connect, a multi-location organization. Help staff with questions about processes, scheduling, member management, and general organizational tasks. Keep responses concise and helpful."
        ).with_model("gemini", "gemini-2.5-flash")
        user_msg = UserMessage(text=message)
        response = await chat.send_message(user_msg)
        # Store in chat_messages for persistence
        now = datetime.now(timezone.utc).isoformat()
        await db.chat_messages.insert_one({
            "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}",
            "sender_id": current_user["id"], "sender_name": current_user.get("name"),
            "text": message, "type": "user", "created_at": now,
        })
        await db.chat_messages.insert_one({
            "id": f"msg_{str(uuid.uuid4())[:8]}", "conversation_id": f"ai_{current_user['id']}",
            "sender_id": "ai_assistant", "sender_name": "AI Assistant",
            "text": response, "type": "ai", "created_at": now,
        })
        return {"response": response, "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI assistant error: {str(e)}")


# ========== EXPORT ROUTES ==========

@api_router.get("/export/members")
async def export_members_csv(current_user: dict = Depends(get_current_user)):
    members = await db.members.find({}, {"_id": 0}).sort("name", 1).to_list(5000)
    output = io.StringIO()
    fields = ["id", "name", "email", "phone", "national_id", "role", "group", "gender", "status", "join_date"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for m in members:
        writer.writerow({k: m.get(k, "") for k in fields})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=members.csv"})

@api_router.get("/export/financial")
async def export_financial_csv(current_user: dict = Depends(get_current_user)):
    donations = await db.donations.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["=== DONATIONS ==="])
    writer.writerow(["ID", "Donor", "Amount", "Currency", "Type", "Date"])
    for d in donations:
        writer.writerow([d.get("id"), d.get("donor_name"), d.get("amount"), d.get("currency"), d.get("type"), d.get("date")])
    writer.writerow([])
    writer.writerow(["=== EXPENSES ==="])
    writer.writerow(["ID", "Title", "Amount", "Currency", "Category", "Date"])
    for e in expenses:
        writer.writerow([e.get("id"), e.get("title"), e.get("amount"), e.get("currency"), e.get("category"), e.get("date")])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=financial.csv"})

@api_router.get("/export/events")
async def export_events_csv(current_user: dict = Depends(get_current_user)):
    events = await db.events.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    output = io.StringIO()
    fields = ["id", "title", "type", "date", "time", "location", "capacity", "registered", "status", "is_public"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for e in events:
        writer.writerow({k: e.get(k, "") for k in fields})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=events.csv"})

# ========== ICAL EXPORT ==========

@api_router.get("/export/events.ics")
async def export_ical(current_user: dict = Depends(get_current_user)):
    events = await db.events.find({}, {"_id": 0}).sort("date", 1).to_list(500)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//58:12 Global Connect//CRM//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    ]
    for e in events:
        date_str = e.get("date", "")
        time_str = e.get("time", "00:00")
        end_time_str = e.get("end_time", time_str)
        try:
            dt = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M")
            dt_end = datetime.strptime(f"{date_str}T{end_time_str}", "%Y-%m-%dT%H:%M")
            dtstart = dt.strftime("%Y%m%dT%H%M%S")
            dtend = dt_end.strftime("%Y%m%dT%H%M%S")
        except Exception:
            dtstart = date_str.replace("-", "") + "T000000"
            dtend = dtstart
        summary = e.get("title", "Event").replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")
        desc = e.get("description", "").replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")
        location = e.get("location", "").replace(",", "\\,")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@5812global.org",
            f"SUMMARY:{summary}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{location}",
            f"STATUS:{'CONFIRMED' if e.get('status') == 'upcoming' else 'COMPLETED'}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return StreamingResponse(iter(["\r\n".join(lines)]), media_type="text/calendar",
                             headers={"Content-Disposition": "attachment; filename=5812global-events.ics"})

# ========== SEED LOCATIONS & NOTIFICATIONS ==========

@api_router.post("/seed-locations")
async def seed_locations_and_notifications():
    loc_count = await db.locations.count_documents({})
    if loc_count == 0:
        locations = [
            {"id": "loc_001", "name": "58:12 Global Centre (Main)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_002", "name": "Entebbe Branch", "code": "ETB", "type": "branch", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_003", "name": "Jinja Chapter", "code": "JNJ", "type": "branch", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_004", "name": "Kampala East Cell", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.locations.insert_many(locations)

    notif_count = await db.notifications.count_documents({})
    if notif_count == 0:
        notifications = [
            {"id": "notif_001", "title": "New Member Approval", "message": "3 new member registrations are pending approval.", "type": "warning", "target_role": "admin", "link": "/members", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_002", "title": "Low Stock Alert", "message": "Coffee and Eggs (Tray) are out of stock. Please reorder.", "type": "error", "target_role": None, "link": "/sales", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_003", "title": "Event Reminder", "message": "Youth Leadership Summit is in 5 days. 13 spots remaining.", "type": "info", "target_role": None, "link": "/events", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_004", "title": "Tasks Overdue", "message": "2 high priority tasks are past due. Review task board.", "type": "warning", "target_role": None, "link": "/tasks", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.notifications.insert_many(notifications)
    return {"message": "Locations and notifications seeded"}


# ========== OUTREACH MODELS ==========

class OutreachProgramCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "community"
    status: str = "active"
    location: Optional[str] = None
    start_date: Optional[str] = None
    target: Optional[int] = None

class OutreachSessionCreate(BaseModel):
    program_id: str
    date: str
    time: Optional[str] = None
    location: Optional[str] = None
    attendees: int = 0
    notes: Optional[str] = None
    led_by: Optional[str] = None

# ========== RESOURCE MODELS ==========

class ResourceCreate(BaseModel):
    name: str
    type: str = "room"  # room, sports_equipment, media_equipment, educational, consumable, venue
    category: Optional[str] = None
    capacity: Optional[int] = None
    quantity: int = 1
    description: Optional[str] = None
    location_id: Optional[str] = None
    hourly_rate: Optional[float] = None
    is_bookable: bool = True
    staff_only: bool = False
    is_consumable: bool = False

class ResourceBookingCreate(BaseModel):
    resource_id: str
    title: str
    booked_by: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    notes: Optional[str] = None

# ========== ANNOUNCEMENT MODELS ==========

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    type: str = "general"
    target_role: Optional[str] = None
    pinned: bool = False
    expires_at: Optional[str] = None

# ========== BADGE MODELS ==========

class BadgeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: str = "award"
    criteria: Optional[str] = None

# ========== OUTREACH ROUTES ==========

@api_router.get("/outreach/programs")
async def list_outreach_programs(current_user: dict = Depends(get_current_user)):
    programs = await db.outreach_programs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return programs

@api_router.post("/outreach/programs")
async def create_outreach_program(data: OutreachProgramCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"op_{str(uuid.uuid4())[:8]}", **data.model_dump(), "sessions_count": 0, "total_reached": 0, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.outreach_programs.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "outreach_program", doc["id"])
    return doc

@api_router.put("/outreach/programs/{prog_id}")
async def update_outreach_program(prog_id: str, data: OutreachProgramCreate, current_user: dict = Depends(get_current_user)):
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.outreach_programs.update_one({"id": prog_id}, {"$set": update})
    return await db.outreach_programs.find_one({"id": prog_id}, {"_id": 0})

@api_router.delete("/outreach/programs/{prog_id}")
async def delete_outreach_program(prog_id: str, current_user: dict = Depends(get_current_user)):
    await db.outreach_programs.delete_one({"id": prog_id})
    return {"message": "Deleted"}

@api_router.get("/outreach/sessions")
async def list_outreach_sessions(program_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"program_id": program_id} if program_id else {}
    sessions = await db.outreach_sessions.find(query, {"_id": 0}).sort("date", -1).to_list(500)
    return sessions

@api_router.post("/outreach/sessions")
async def create_outreach_session(data: OutreachSessionCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"os_{str(uuid.uuid4())[:8]}", **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.outreach_sessions.insert_one(doc)
    doc.pop("_id", None)
    await db.outreach_programs.update_one({"id": data.program_id}, {"$inc": {"sessions_count": 1, "total_reached": data.attendees}})
    return doc

# ========== RESOURCE ROUTES ==========

@api_router.get("/resources")
async def list_resources(current_user: dict = Depends(get_current_user)):
    resources = await db.resources.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return resources

@api_router.post("/resources")
async def create_resource(data: ResourceCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"res_{str(uuid.uuid4())[:8]}", **data.model_dump(), "available": True, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.resources.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "resource", doc["id"])
    return doc

@api_router.put("/resources/{res_id}")
async def update_resource(res_id: str, data: ResourceCreate, current_user: dict = Depends(get_current_user)):
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.resources.update_one({"id": res_id}, {"$set": update})
    return await db.resources.find_one({"id": res_id}, {"_id": 0})

@api_router.delete("/resources/{res_id}")
async def delete_resource(res_id: str, current_user: dict = Depends(get_current_user)):
    await db.resources.delete_one({"id": res_id})
    return {"message": "Deleted"}

@api_router.get("/resources/bookings")
async def list_resource_bookings(resource_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"resource_id": resource_id} if resource_id else {}
    bookings = await db.resource_bookings.find(query, {"_id": 0}).sort("date", 1).to_list(500)
    return bookings

@api_router.post("/resources/bookings")
async def create_resource_booking(data: ResourceBookingCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"rb_{str(uuid.uuid4())[:8]}", **data.model_dump(), "status": "confirmed", "booked_by": data.booked_by or current_user.get("name", "Unknown"), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.resource_bookings.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/resources/bookings/{booking_id}")
async def delete_resource_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    await db.resource_bookings.delete_one({"id": booking_id})
    return {"message": "Deleted"}

# ========== ANNOUNCEMENT ROUTES ==========

@api_router.get("/announcements")
async def list_announcements(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    announcements = await db.announcements.find(query, {"_id": 0}).sort([("pinned", -1), ("created_at", -1)]).to_list(100)
    return announcements

@api_router.post("/announcements")
async def create_announcement(data: AnnouncementCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"ann_{str(uuid.uuid4())[:8]}", **data.model_dump(), "author_name": current_user.get("name", "Admin"), "author_role": current_user.get("role", "admin"), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.announcements.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "announcement", doc["id"])
    return doc

@api_router.delete("/announcements/{ann_id}")
async def delete_announcement(ann_id: str, current_user: dict = Depends(get_current_user)):
    await db.announcements.delete_one({"id": ann_id})
    return {"message": "Deleted"}

@api_router.put("/announcements/{ann_id}/pin")
async def toggle_announcement_pin(ann_id: str, current_user: dict = Depends(get_current_user)):
    ann = await db.announcements.find_one({"id": ann_id}, {"_id": 0})
    if ann:
        await db.announcements.update_one({"id": ann_id}, {"$set": {"pinned": not ann.get("pinned", False)}})
    return {"message": "Updated"}

# ========== BADGES, APPROVALS, IMPORTS (moved to routers/members.py & routers/import_csv.py) ==========


# ========== ANALYTICS ROUTES ==========

@api_router.get("/analytics/attendance")
async def attendance_analytics(current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    weekly_data = []
    for i in range(11, -1, -1):
        week_start = (now - timedelta(weeks=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        count = await db.checkins.count_documents({"check_in_time": {"$gte": week_start.isoformat(), "$lt": week_end.isoformat()}})
        weekly_data.append({"week": week_start.strftime("W%V"), "date": week_start.strftime("%b %d"), "checkins": count})
    recent = await db.checkins.find({}, {"_id": 0, "id": 1, "member_name": 1, "event_name": 1, "check_in_time": 1, "method": 1}).sort("check_in_time", -1).limit(10).to_list(10)
    total_today = await db.checkins.count_documents({"check_in_time": {"$gte": now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()}})
    total_week = weekly_data[-1]["checkins"] if weekly_data else 0
    total_month = await db.checkins.count_documents({"check_in_time": {"$gte": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()}})
    return {"weekly_data": weekly_data, "recent": recent, "total_today": total_today, "total_week": total_week, "total_month": total_month}

@api_router.get("/analytics/sales")
async def sales_analytics(current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    monthly_data = []
    for i in range(5, -1, -1):
        month_dt = now.replace(day=1) - timedelta(days=i * 28)
        month_start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_dt.month == 12:
            month_end = month_dt.replace(year=month_dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            month_end = month_dt.replace(month=month_dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        sales = await db.sales.find({"created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}}, {"_id": 0, "total": 1}).to_list(5000)
        revenue = sum(s.get("total", 0) for s in sales)
        monthly_data.append({"month": month_dt.strftime("%b %Y"), "revenue": revenue, "transactions": len(sales)})
    all_sales = await db.sales.find({}, {"_id": 0, "items": 1, "total": 1, "payment_method": 1}).to_list(5000)
    product_totals = {}
    payment_totals = {}
    for s in all_sales:
        method = s.get("payment_method", "cash")
        payment_totals[method] = payment_totals.get(method, 0) + s.get("total", 0)
        for item in s.get("items", []):
            name = item.get("name", "Unknown")
            product_totals[name] = product_totals.get(name, 0) + item.get("unit_price", 0) * item.get("qty", 0)
    top_products = sorted([{"name": k, "revenue": v} for k, v in product_totals.items()], key=lambda x: x["revenue"], reverse=True)[:8]
    payment_breakdown = [{"name": k.replace("_", " ").title(), "value": v} for k, v in payment_totals.items()]
    total_revenue = sum(s.get("total", 0) for s in all_sales)
    return {"monthly_data": monthly_data, "top_products": top_products, "payment_breakdown": payment_breakdown, "total_revenue": total_revenue, "total_transactions": len(all_sales)}

@api_router.get("/analytics/locations")
async def location_analytics(current_user: dict = Depends(get_current_user)):
    locations = await db.locations.find({}, {"_id": 0}).to_list(200)
    result = []
    for loc in locations:
        member_count = await db.members.count_documents({"location_id": loc["id"]})
        checkin_count = await db.checkins.count_documents({"location_id": loc["id"]})
        event_count = await db.events.count_documents({"location_id": loc["id"]})
        result.append({**loc, "member_count": member_count, "checkin_count": checkin_count, "event_count": event_count})
    total_members = await db.members.count_documents({})
    return {"locations": result, "total_members": total_members}

# ========== FINANCIAL: CASHFLOW & BALANCE ==========

@api_router.get("/financial/cashflow")
async def financial_cashflow(months: int = 6, current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    monthly = []
    for i in range(months - 1, -1, -1):
        month_dt = now.replace(day=1) - timedelta(days=i * 28)
        month_start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        if month_dt.month == 12:
            month_end = month_dt.replace(year=month_dt.year + 1, month=1, day=1).isoformat()
        else:
            month_end = month_dt.replace(month=month_dt.month + 1, day=1).isoformat()
        donations = await db.donations.find({"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}, {"_id": 0, "amount": 1}).to_list(5000)
        expenses_list = await db.expenses.find({"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}, {"_id": 0, "amount": 1}).to_list(5000)
        sales = await db.sales.find({"created_at": {"$gte": month_start, "$lt": month_end}}, {"_id": 0, "total": 1}).to_list(5000)
        inflow = sum(d.get("amount", 0) for d in donations) + sum(s.get("total", 0) for s in sales)
        outflow = sum(e.get("amount", 0) for e in expenses_list)
        monthly.append({"month": month_dt.strftime("%b"), "inflow": inflow, "outflow": outflow, "net": inflow - outflow})
    return {"monthly": monthly}

@api_router.get("/financial/balance")
async def get_financial_balance(current_user: dict = Depends(get_current_user)):
    doc = await db.financial_settings.find_one({}, {"_id": 0})
    if not doc:
        return {"opening_balance": 0, "current_balance": 0, "set_at": None}
    return doc

@api_router.put("/financial/balance")
async def set_financial_balance(opening_balance: float, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    await db.financial_settings.update_one({}, {"$set": {"opening_balance": opening_balance, "set_at": now, "set_by": current_user["id"]}}, upsert=True)
    return {"opening_balance": opening_balance, "set_at": now}

# ========== PARENT DASHBOARD ==========

@api_router.get("/parent/children")
async def get_parent_children(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user_email = current_user.get("email", "")
    children = await db.children.find({"$or": [{"parent_id": user_id}, {"parent_email": user_email}]}, {"_id": 0}).to_list(50)
    enriched = []
    for child in children:
        last_checkin = await db.checkins.find_one({"member_id": child.get("id", ""), "member_name": child.get("name", "")}, {"_id": 0, "check_in_time": 1, "event_name": 1}, sort=[("check_in_time", -1)])
        enriched.append({**child, "last_checkin": last_checkin})
    return enriched

@api_router.get("/parent/dashboard")
async def parent_dashboard(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user_email = current_user.get("email", "")
    children = await db.children.find({"$or": [{"parent_id": user_id}, {"parent_email": user_email}]}, {"_id": 0}).to_list(50)
    upcoming_events = await db.events.find({"status": "upcoming", "is_public": True}, {"_id": 0, "id": 1, "title": 1, "date": 1, "time": 1, "location": 1, "type": 1}).sort("date", 1).limit(5).to_list(5)
    return {"children": children, "children_count": len(children), "checked_in_count": 0, "upcoming_events": upcoming_events}

# ========== DARK MODE / APP SETTINGS ==========

@api_router.get("/app-settings")
async def get_app_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.app_settings.find_one({"user_id": current_user["id"]}, {"_id": 0})
    return doc or {"user_id": current_user["id"], "dark_mode": False, "language": "en"}

@api_router.put("/app-settings")
async def update_app_settings(settings: dict, current_user: dict = Depends(get_current_user)):
    settings.pop("_id", None)
    settings["user_id"] = current_user["id"]
    await db.app_settings.update_one({"user_id": current_user["id"]}, {"$set": settings}, upsert=True)
    return settings

# ========== SEED NEW COLLECTIONS ==========

@api_router.post("/seed-all")
async def seed_all_data():
    seeded = []
    if await db.outreach_programs.count_documents({}) == 0:
        programs = [
            {"id": "op_001", "name": "Community Health Drive", "description": "Free medical check-ups and health education in Kampala slums.", "category": "health", "status": "active", "location": "Katwe, Kampala", "start_date": "2026-01-15", "target": 500, "sessions_count": 3, "total_reached": 142, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_002", "name": "School Outreach Program", "description": "Bible studies and character formation in local schools.", "category": "education", "status": "active", "location": "Entebbe Municipality", "start_date": "2025-09-01", "target": 200, "sessions_count": 8, "total_reached": 316, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_003", "name": "Widows & Orphans Support", "description": "Monthly food distribution and counselling for vulnerable families.", "category": "welfare", "status": "active", "location": "Multiple Locations", "start_date": "2025-06-01", "target": 100, "sessions_count": 5, "total_reached": 89, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.outreach_programs.insert_many(programs)
        sessions = [
            {"id": "os_001", "program_id": "op_001", "date": "2026-03-10", "time": "09:00", "location": "Katwe Health Centre", "attendees": 47, "notes": "Distributed 47 medicine packs. 3 referrals to Mulago.", "led_by": "Dr. Auma Florence", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "os_002", "program_id": "op_002", "date": "2026-03-14", "time": "14:00", "location": "Entebbe Primary School", "attendees": 85, "notes": "Session on integrity and purpose. Very engaged students.", "led_by": "Pastor Amos", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.outreach_sessions.insert_many(sessions)
        seeded.append("outreach")
    if await db.resources.count_documents({}) == 0:
        resources = [
            {"id": "res_001", "name": "Main Auditorium", "type": "auditorium", "capacity": 400, "description": "Main worship hall with stage, PA system, and projectors.", "location_id": "loc_001", "hourly_rate": 50000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_002", "name": "Conference Room A", "type": "conference", "capacity": 30, "description": "Air-conditioned with whiteboard and AV equipment.", "location_id": "loc_001", "hourly_rate": 20000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_003", "name": "Youth Hall", "type": "hall", "capacity": 150, "description": "Multi-purpose hall for youth programs and events.", "location_id": "loc_001", "hourly_rate": 30000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_004", "name": "PA System (Mobile)", "type": "equipment", "capacity": None, "description": "Portable PA system with 2 wireless microphones.", "location_id": "loc_001", "hourly_rate": 15000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.resources.insert_many(resources)
        seeded.append("resources")
    if await db.announcements.count_documents({}) == 0:
        announcements = [
            {"id": "ann_001", "title": "Welcome to March 2026!", "content": "This month we launch our Community Health Drive with a goal of reaching 500 people. All staff are invited to join the orientation on Monday at 9 AM.", "type": "general", "target_role": None, "pinned": True, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ann_002", "title": "Staff Meeting — This Friday", "content": "Mandatory all-staff meeting this Friday at 3 PM in the Main Conference Room. Agenda: Q1 Review, Budget planning, and outreach assignments.", "type": "urgent", "target_role": "admin", "pinned": False, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ann_003", "title": "Easter Events Planning", "content": "Planning for Easter Week (April 13-20) begins now. Event coordinators, please submit your event proposals by March 28.", "type": "ministry", "target_role": None, "pinned": False, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.announcements.insert_many(announcements)
        seeded.append("announcements")
    if await db.badges.count_documents({}) == 0:
        badges = [
            {"id": "bdg_001", "name": "Faithful Servant", "description": "Awarded for 1+ year of consistent volunteering.", "color": "#f59e0b", "icon": "star", "criteria": "12+ months active service", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_002", "name": "Prayer Warrior", "description": "Regular participant in prayer meetings.", "color": "#6366f1", "icon": "heart", "criteria": "30+ prayer sessions attended", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_003", "name": "Outreach Champion", "description": "Led or participated in 5+ outreach sessions.", "color": "#10b981", "icon": "award", "criteria": "5+ outreach sessions", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_004", "name": "New Believer", "description": "Recently joined the faith community.", "color": "#3b82f6", "icon": "user-plus", "criteria": "First 90 days", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.badges.insert_many(badges)
        seeded.append("badges")
    return {"seeded": seeded, "message": "Seed complete"}


# Include modular routers
try:
    from routers.bookings import router as bookings_router
    from routers.websocket import router as ws_router
    from routers.notifications import router as notifications_router
    from routers.access import router as access_router
    from routers.reports import router as reports_router
    from routers.documents import router as documents_router
    from routers.auth import router as auth_router
    from routers.members import router as members_router
    from routers.import_csv import router as import_csv_router
    app.include_router(bookings_router)
    app.include_router(ws_router)
    app.include_router(notifications_router)
    app.include_router(access_router)
    app.include_router(reports_router)
    app.include_router(documents_router)
    app.include_router(auth_router)
    app.include_router(members_router)
    app.include_router(import_csv_router)
    logger.info("Modular routers loaded")
except Exception as e:
    logger.warning(f"Router loading: {e}")

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Auto-seed on startup if DB is empty
    user_count = await db.users.count_documents({})
    if user_count == 0:
        logger.info("Seeding initial data...")
        try:
            # Create indexes for performance
            await db.users.create_index("email", unique=True)
            await db.users.create_index("id", unique=True)
            await db.members.create_index("id", unique=True)
            await db.members.create_index("email")
            await db.events.create_index("id", unique=True)
            await db.tasks.create_index("id", unique=True)
            await db.checkins.create_index("id", unique=True)
            await db.chat_messages.create_index("conversation_id")
            await db.chat_messages.create_index([("conversation_id", 1), ("created_at", -1)])
            await db.notifications.create_index([("target_role", 1), ("created_at", -1)])
            await db.guest_requests.create_index([("location_id", 1), ("status", 1)])
            await db.access_logs.create_index([("location_id", 1), ("timestamp", -1)])
            await db.files.create_index([("member_id", 1), ("is_deleted", 1)])
            await db.password_resets.create_index("token")
            await db.password_resets.create_index("expires_at")
        except Exception as e:
            logger.warning(f"Index creation: {e}")
        
        admin = {
            "id": str(uuid.uuid4()),
            "name": "Admin User",
            "email": "admin@5812global.org",
            "phone": "+256 800 5812",
            "password_hash": hash_password("Admin@1234"),
            "role": "admin",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        admin2 = {
            "id": str(uuid.uuid4()),
            "name": "Admin",
            "email": "admin@5812uganda.org",
            "phone": "+256 800 5813",
            "password_hash": hash_password("Admin@5812"),
            "role": "admin",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.users.insert_one(admin)
            await db.users.insert_one(admin2)
            logger.info("Admin users created")
        except Exception as e:
            logger.warning(f"Admin creation: {e}")

    # Ensure admin@5812uganda.org always exists with correct credentials
    uganda_admin = await db.users.find_one({"email": "admin@5812uganda.org"})
    if not uganda_admin:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "name": "Admin",
            "email": "admin@5812uganda.org",
            "phone": "+256 800 5813",
            "password_hash": hash_password("Admin@5812"),
            "role": "admin",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        await db.users.update_one({"email": "admin@5812uganda.org"}, {"$set": {"password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active"}})

    # Seed locations and notifications if empty
    try:
        if await db.locations.count_documents({}) == 0:
            locations = [
                {"id": "loc_001", "name": "58:12 Global Centre (Main)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Administration", "Finance", "Operations"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_002", "name": "Entebbe Compass", "code": "ETB", "type": "compass", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "country": "Uganda", "currency": "UGX", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Youth", "Education"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_003", "name": "Jinja Compass", "code": "JNJ", "type": "compass", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "country": "Uganda", "currency": "UGX", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Community", "Sports"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_004", "name": "Kampala East", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "is_venue": True, "is_bookable": True, "is_restricted": False, "departments": [], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.locations.insert_many(locations)
        if await db.notifications.count_documents({}) == 0:
            notifications = [
                {"id": "notif_001", "title": "New Member Approval", "message": "3 new member registrations are pending approval.", "type": "warning", "target_role": "admin", "link": "/members", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "notif_002", "title": "Low Stock Alert", "message": "Coffee and Eggs (Tray) are out of stock. Please reorder.", "type": "error", "target_role": None, "link": "/sales", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "notif_003", "title": "Event Reminder", "message": "Youth Leadership Summit is in 5 days. 13 spots remaining.", "type": "info", "target_role": None, "link": "/events", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "notif_004", "title": "Tasks Overdue", "message": "2 high priority tasks are past due. Review task board.", "type": "warning", "target_role": None, "link": "/tasks", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.notifications.insert_many(notifications)
    except Exception as e:
        logger.warning(f"Location/notification seeding: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
