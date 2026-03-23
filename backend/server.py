from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
import csv
import io
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
    type: str = "tithe"  # tithe, offering, donation, pledge
    date: Optional[str] = None
    notes: Optional[str] = None
    member_id: Optional[str] = None

class ExpenseCreate(BaseModel):
    title: str
    amount: float
    currency: str = "UGX"
    category: str = "general"  # salaries, utilities, supplies, maintenance, programs
    date: Optional[str] = None
    notes: Optional[str] = None
    submitted_by: Optional[str] = None

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    currency: str = "UGX"
    stock: int = 0
    category: Optional[str] = None
    sku: Optional[str] = None
    reorder_level: int = 5

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    category: Optional[str] = None
    reorder_level: Optional[int] = None

class SaleCreate(BaseModel):
    items: List[dict]  # [{product_id, name, qty, unit_price}]
    customer_name: Optional[str] = "Walk-in Customer"
    customer_phone: Optional[str] = None
    total: float
    payment_method: str = "cash"  # cash, mobile_money, card
    notes: Optional[str] = None

class FamilyCreate(BaseModel):
    family_name: str
    primary_contact_name: str
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class ChildCreate(BaseModel):
    name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    family_id: Optional[str] = None
    class_group: Optional[str] = None
    medical_notes: Optional[str] = None
    allergies: Optional[str] = None
    emergency_contact: Optional[str] = None
    notes: Optional[str] = None

class GuestCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    visit_date: Optional[str] = None
    referred_by: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class AuditLogCreate(BaseModel):
    action: str
    resource: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None

# ========== FINANCIAL ROUTES ==========

@api_router.get("/financial/summary")
async def financial_summary(current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).isoformat()[:7]

    pipeline_donations = [
        {"$match": {"date": {"$regex": f"^{month_start}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    pipeline_expenses = [
        {"$match": {"date": {"$regex": f"^{month_start}"}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    pipeline_sales = [
        {"$match": {"created_at": {"$regex": f"^{month_start}"}}},
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

@api_router.get("/financial/donations")
async def list_donations(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
    donations = await db.donations.find({}, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return donations

@api_router.post("/financial/donations")
async def create_donation(data: DonationCreate, current_user: dict = Depends(get_current_user)):
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
async def list_expenses(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
    expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return expenses

@api_router.post("/financial/expenses")
async def create_expense(data: ExpenseCreate, current_user: dict = Depends(get_current_user)):
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

# ========== FAMILIES ==========

@api_router.get("/families")
async def list_families(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["$or"] = [
            {"family_name": {"$regex": search, "$options": "i"}},
            {"primary_contact_name": {"$regex": search, "$options": "i"}},
        ]
    families = await db.families.find(query, {"_id": 0}).sort("family_name", 1).to_list(500)
    return families

@api_router.post("/families")
async def create_family(data: FamilyCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"fam_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.families.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/families/{family_id}")
async def update_family(family_id: str, data: FamilyCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.families.update_one({"id": family_id}, {"$set": update})
    return await db.families.find_one({"id": family_id}, {"_id": 0})

@api_router.delete("/families/{family_id}")
async def delete_family(family_id: str, current_user: dict = Depends(get_current_user)):
    await db.families.delete_one({"id": family_id})
    return {"message": "Family deleted"}

# ========== CHILDREN ==========

@api_router.get("/children")
async def list_children(family_id: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if family_id:
        query["family_id"] = family_id
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    children = await db.children.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return children

@api_router.post("/children")
async def create_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"chd_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.children.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.put("/children/{child_id}")
async def update_child(child_id: str, data: ChildCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.children.update_one({"id": child_id}, {"$set": update})
    return await db.children.find_one({"id": child_id}, {"_id": 0})

@api_router.delete("/children/{child_id}")
async def delete_child(child_id: str, current_user: dict = Depends(get_current_user)):
    await db.children.delete_one({"id": child_id})
    return {"message": "Child deleted"}

# ========== GUESTS ==========

@api_router.get("/guests")
async def list_guests(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    guests = await db.guests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return guests

@api_router.post("/guests")
async def create_guest(data: GuestCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"gst_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "visit_date": data.visit_date or datetime.now(timezone.utc).isoformat()[:10],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guests.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/guests/{guest_id}")
async def delete_guest(guest_id: str, current_user: dict = Depends(get_current_user)):
    await db.guests.delete_one({"id": guest_id})
    return {"message": "Guest deleted"}

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
async def list_audit(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
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
    type: str = "branch"
    parent_id: Optional[str] = None
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
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
async def create_location(data: LocationCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "id": f"loc_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "active": True,
        "member_count": 0,
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

@api_router.delete("/locations/{loc_id}")
async def delete_location(loc_id: str, current_user: dict = Depends(get_current_user)):
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

    # Seed locations and notifications if empty
    try:
        if await db.locations.count_documents({}) == 0:
            locations = [
                {"id": "loc_001", "name": "58:12 Global Centre (Main)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_002", "name": "Entebbe Branch", "code": "ETB", "type": "branch", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_003", "name": "Jinja Chapter", "code": "JNJ", "type": "branch", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_004", "name": "Kampala East Cell", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
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
    client.close()
