from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', '5812global')]

app = FastAPI(title="58:12 Global Connect API")
api_router = APIRouter(prefix="/api")

# Auth setup
SECRET_KEY = os.environ.get('SECRET_KEY', '5812global_secret_key_change_in_production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ========== MODELS ==========

class UserRegister(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    national_id: Optional[str] = None
    password: str

class UserLogin(BaseModel):
    identifier: str  # email, phone, or national_id
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: str = "volunteer"
    status: str = "active"
    created_at: str

class MemberCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: str = "Member"
    group: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None

class MemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None
    role: Optional[str] = None
    group: Optional[str] = None
    gender: Optional[str] = None
    status: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None

class EventCreate(BaseModel):
    title: str
    type: str = "service"
    date: str
    time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    capacity: int = 100
    description: Optional[str] = None
    is_public: bool = True
    is_free: bool = True
    price: Optional[float] = None
    venue_id: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    is_free: Optional[bool] = None
    price: Optional[float] = None
    status: Optional[str] = None

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = []

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None

class CheckInCreate(BaseModel):
    member_id: Optional[str] = None
    member_name: str
    type: str = "member"  # member, staff, visitor
    event_id: Optional[str] = None
    event_name: Optional[str] = None
    method: str = "manual"  # manual, qr, id

class VenueCreate(BaseModel):
    name: str
    capacity: int
    type: str = "hall"
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    available: bool = True

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    type: Optional[str] = None
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    available: Optional[bool] = None

class PublicBookingCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    event_id: str
    num_tickets: int = 1

class SpaceBookingCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    venue_id: str
    booking_date: str
    start_time: str
    end_time: str
    purpose: Optional[str] = None


# ========== AUTH HELPERS ==========

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        return user
    except:
        return None


# ========== AUTH ROUTES ==========

@api_router.post("/auth/register")
async def register(data: UserRegister):
    # Check if email already exists
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "name": data.name,
        "email": data.email.lower(),
        "phone": data.phone,
        "national_id": data.national_id,
        "password_hash": hash_password(data.password),
        "role": "volunteer",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = create_token(user_id)
    user_out = {k: v for k, v in user.items() if k != "password_hash"}
    return {"token": token, "user": user_out}

@api_router.post("/auth/login")
async def login(data: UserLogin):
    identifier = data.identifier.strip().lower()
    # Find by email, phone, or national_id
    user = await db.users.find_one({
        "$or": [
            {"email": identifier},
            {"phone": identifier},
            {"national_id": data.identifier.strip()},
        ]
    })
    if not user or not verify_password(data.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"])
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": token, "user": user_out}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    user_out = {k: v for k, v in current_user.items() if k not in ("password_hash", "_id")}
    return user_out

@api_router.post("/auth/logout")
async def logout():
    return {"message": "Logged out successfully"}


# ========== MEMBERS ==========

@api_router.get("/members")
async def list_members(
    search: Optional[str] = None,
    group: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"national_id": {"$regex": search, "$options": "i"}},
        ]
    if group and group != "all":
        query["group"] = group
    if status and status != "all":
        query["status"] = status
    if role and role != "all":
        query["role"] = role
    
    total = await db.members.count_documents(query)
    members = await db.members.find(query, {"_id": 0}).skip(skip).limit(limit).sort("name", 1).to_list(limit)
    return {"members": members, "total": total}

@api_router.post("/members")
async def create_member(data: MemberCreate, current_user: dict = Depends(get_current_user)):
    member_id = f"mem_{str(uuid.uuid4())[:8]}"
    member = {
        "id": member_id,
        **data.model_dump(),
        "status": "active",
        "join_date": datetime.now(timezone.utc).isoformat().split("T")[0],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.members.insert_one(member)
    member.pop("_id", None)
    return member

@api_router.get("/members/{member_id}")
async def get_member(member_id: str, current_user: dict = Depends(get_current_user)):
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Fetch check-in history
    checkins = await db.checkins.find({"member_id": member_id}, {"_id": 0}).sort("check_in_time", -1).limit(20).to_list(20)
    member["checkin_history"] = checkins
    return member

@api_router.put("/members/{member_id}")
async def update_member(member_id: str, data: MemberUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.members.update_one({"id": member_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    return member

@api_router.delete("/members/{member_id}")
async def delete_member(member_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.members.delete_one({"id": member_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"message": "Member deleted"}


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


# ========== DASHBOARD STATS ==========

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    total_members = await db.members.count_documents({})
    active_members = await db.members.count_documents({"status": "active"})
    
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
    
    events_this_month = await db.events.count_documents({"date": {"$gte": month_start[:7]}})
    upcoming_events = await db.events.count_documents({"status": "upcoming"})
    
    today_start = now.replace(hour=0, minute=0, second=0).isoformat()
    checkins_today = await db.checkins.count_documents({"check_in_time": {"$gte": today_start}})
    
    now_str = now.isoformat()[:10]
    tasks_overdue = await db.tasks.count_documents({"status": {"$nin": ["done"]}, "due_date": {"$lt": now_str}})
    
    new_members_this_month = await db.members.count_documents({"join_date": {"$gte": month_start[:7]}})
    
    # Recent activity (combine from all collections)
    recent_checkins = await db.checkins.find({}, {"_id": 0}).sort("check_in_time", -1).limit(3).to_list(3)
    recent_members = await db.members.find({}, {"_id": 0}).sort("created_at", -1).limit(2).to_list(2)
    
    activity = []
    for ci in recent_checkins:
        activity.append({
            "type": "checkin",
            "message": f"{ci.get('member_name', 'Someone')} checked in" + (f" to {ci.get('event_name', '')}" if ci.get('event_name') else ""),
            "time": ci.get("check_in_time", ""),
        })
    for m in recent_members:
        activity.append({
            "type": "member",
            "message": f"New member: {m.get('name', '')} registered",
            "time": m.get("created_at", ""),
        })
    activity.sort(key=lambda x: x.get("time", ""), reverse=True)
    
    return {
        "total_members": total_members,
        "active_members": active_members,
        "events_this_month": events_this_month,
        "upcoming_events": upcoming_events,
        "checkins_today": checkins_today,
        "tasks_overdue": tasks_overdue,
        "new_members_this_month": new_members_this_month,
        "recent_activity": activity[:5],
    }


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
    # Auto-seed on startup if DB is empty
    user_count = await db.users.count_documents({})
    if user_count == 0:
        logger.info("Seeding initial data...")
        try:
            # Create indexes
            await db.users.create_index("email", unique=True)
            await db.members.create_index("id", unique=True)
            await db.events.create_index("id", unique=True)
            await db.tasks.create_index("id", unique=True)
            await db.checkins.create_index("id", unique=True)
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
        try:
            await db.users.insert_one(admin)
            logger.info("Admin user created: admin@5812global.org / Admin@1234")
        except Exception as e:
            logger.warning(f"Admin creation: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
