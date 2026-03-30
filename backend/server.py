from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from storage import init_storage
from deps import get_role_level, require_role, require_admin, require_director, require_manager, require_coordinator, require_staff, get_current_user, hash_password, verify_password, create_token, is_system_admin, get_campus_filter
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import time
import asyncio
from collections import defaultdict
from pathlib import Path
from pydantic import BaseModel, Field
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
        if request.headers.get("upgrade") == "websocket":
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = now - 60
        self.request_counts[client_ip] = [t for t in self.request_counts[client_ip] if t > window]
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again in a minute."})
        self.request_counts[client_ip].append(now)
        response = await call_next(request)
        return response

app.add_middleware(RateLimitMiddleware, requests_per_minute=120)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from deps import _audit, normalize_gender, resolve_department


# ========== MODELS (imported from models.py) ==========
from models import (
    UserRegister, UserLogin, UserOut, MemberCreate, MemberUpdate,
    EventCreate, EventUpdate, TaskCreate, TaskUpdate, CheckInCreate,
    VenueCreate, VenueUpdate, PublicBookingCreate, SpaceBookingCreate,
    FamilyCreate, ChildCreate, GuestCreate, AuditLogCreate,
)


# ========== LOCATION MODELS (moved to routers/locations.py) ==========

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"
    target_role: Optional[str] = None
    link: Optional[str] = None


# ========== SEED ENDPOINTS ==========

@api_router.post("/seed")
async def seed_data():
    existing_admin = await db.users.find_one({"email": "admin@5812global.org"})
    if not existing_admin:
        admin = {
            "id": str(uuid.uuid4()), "name": "Admin User", "email": "admin@5812global.org",
            "phone": "+256 800 5812", "password_hash": hash_password("Admin@1234"),
            "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(admin)

    member_count = await db.members.count_documents({})
    if member_count == 0:
        members = [
            {"id": "mem_001", "name": "Alice Namukasa", "email": "alice@example.com", "phone": "+256 700 123456", "national_id": "CM900001000XXXX", "role": "Member", "status": "active", "join_date": "2024-01-15", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_002", "name": "Brian Ssekitto", "email": "brian@example.com", "phone": "+256 752 234567", "national_id": "CM850002000XXXX", "role": "Staff", "status": "active", "join_date": "2023-06-10", "group": "Leadership", "gender": "male", "pin": "1234", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_003", "name": "Catherine Nakato", "email": "catherine@example.com", "phone": "+256 781 345678", "national_id": "CM920003000XXXX", "role": "Member", "status": "active", "join_date": "2024-03-20", "group": "Women", "gender": "female", "pin": "5678", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_004", "name": "David Kiggundu", "email": "david@example.com", "phone": "+256 706 456789", "national_id": "CM880004000XXXX", "role": "Volunteer", "status": "active", "join_date": "2023-11-05", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_005", "name": "Esther Namirembe", "email": "esther@example.com", "phone": "+256 773 567890", "national_id": "CM950005000XXXX", "role": "Member", "status": "inactive", "join_date": "2022-08-30", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_006", "name": "Francis Tumwesigye", "email": "francis@example.com", "phone": "+256 712 678901", "national_id": "CM780006000XXXX", "role": "Leader", "status": "active", "join_date": "2021-05-12", "group": "Leadership", "gender": "male", "is_donor": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_007", "name": "Grace Akello", "email": "grace@example.com", "phone": "+256 756 789012", "national_id": "CM960007000XXXX", "role": "Member", "status": "active", "join_date": "2024-07-01", "group": "Youth", "gender": "female", "is_parent": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_008", "name": "Henry Wasswa", "email": "henry@example.com", "phone": "+256 701 890123", "national_id": "CM820008000XXXX", "role": "Staff", "status": "active", "join_date": "2023-01-18", "group": "Admin", "gender": "male", "pin": "9012", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_009", "name": "Irene Nabatanzi", "email": "irene@example.com", "phone": "+256 784 901234", "national_id": "CM990009000XXXX", "role": "Member", "status": "active", "join_date": "2025-01-10", "group": "Women", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_010", "name": "Joseph Muwanguzi", "email": "joseph@example.com", "phone": "+256 715 012345", "national_id": "CM870010000XXXX", "role": "Volunteer", "status": "inactive", "join_date": "2022-04-22", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.members.insert_many(members)

    event_count = await db.events.count_documents({})
    if event_count == 0:
        events = [
            {"id": "evt_001", "title": "Sunday Service", "type": "service", "status": "upcoming", "date": "2026-04-06", "time": "09:00", "end_time": "11:30", "location": "58:12 Global Centre", "capacity": 300, "registered": 212, "description": "Weekly Sunday worship service.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_002", "title": "Youth Leadership Summit", "type": "conference", "status": "upcoming", "date": "2026-04-12", "time": "10:00", "end_time": "17:00", "location": "Kampala Conference Hall", "capacity": 100, "registered": 87, "description": "Annual leadership development summit.", "is_public": True, "is_free": False, "price": 25000, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_003", "title": "Community Outreach", "type": "community", "status": "upcoming", "date": "2026-04-19", "time": "08:00", "end_time": "14:00", "location": "Nakawa Market Area", "capacity": 50, "registered": 34, "description": "Community service outreach.", "is_public": False, "is_free": True, "visibility": "internal", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_004", "title": "Women in Faith Conference", "type": "conference", "status": "upcoming", "date": "2026-04-26", "time": "09:00", "end_time": "16:00", "location": "58:12 Global Centre", "capacity": 150, "registered": 102, "description": "Annual conference empowering women.", "is_public": True, "is_free": False, "price": 15000, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_005", "title": "Staff Meeting", "type": "meeting", "status": "upcoming", "date": "2026-04-02", "time": "14:00", "end_time": "16:00", "location": "Admin Block", "capacity": 20, "registered": 15, "description": "Monthly all-staff meeting.", "is_public": False, "is_free": True, "visibility": "internal", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_006", "title": "Easter Sunday Service", "type": "service", "status": "completed", "date": "2026-03-31", "time": "07:00", "end_time": "11:00", "location": "58:12 Global Centre", "capacity": 500, "registered": 487, "description": "Easter Sunday special service.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_007", "title": "QR Test Event", "type": "meeting", "status": "upcoming", "date": "2026-04-01", "time": "10:00", "end_time": "12:00", "location": "Tech Lab", "capacity": 100, "registered": 11, "description": "Event for testing QR code check-in.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.events.insert_many(events)

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

    venue_count = await db.venues.count_documents({})
    if venue_count == 0:
        venues = [
            {"id": "ven_001", "name": "Main Auditorium", "capacity": 500, "type": "auditorium", "available": True, "hourly_rate": None, "description": "Main worship hall with full AV system.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_002", "name": "Conference Room A", "capacity": 40, "type": "conference", "available": True, "hourly_rate": 20000, "description": "Small conference room with projector.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_003", "name": "Youth Hall", "capacity": 150, "type": "hall", "available": False, "hourly_rate": 50000, "description": "Large multipurpose hall.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_004", "name": "Prayer Garden", "capacity": 30, "type": "outdoor", "available": True, "hourly_rate": None, "description": "Peaceful outdoor garden space.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.venues.insert_many(venues)

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


@api_router.post("/seed-extended")
async def seed_extended():
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
    family_count = await db.families.count_documents({})
    if family_count == 0:
        families = [
            {"id": "fam_001", "family_name": "Nakato Family", "primary_contact_name": "Sarah Nakato", "primary_contact_email": "parent1@example.com", "primary_contact_phone": "+256 700 111001", "address": "Kampala", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_002", "family_name": "Ssekitto Family", "primary_contact_name": "James Ssekitto", "primary_contact_email": "james@example.com", "primary_contact_phone": "+256 700 222002", "address": "Entebbe", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_003", "family_name": "Kiggundu Family", "primary_contact_name": "Mary Kiggundu", "primary_contact_email": "mary@example.com", "primary_contact_phone": "+256 700 333003", "address": "Jinja", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.families.insert_many(families)
    child_count = await db.children.count_documents({})
    if child_count == 0:
        children = [
            {"id": "chd_001", "name": "Emma Nakato", "date_of_birth": "2016-03-15", "gender": "female", "family_id": "fam_001", "class_group": "Primary 4", "medical_notes": "Nut allergy - carry epipen", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_002", "name": "Daniel Nakato", "date_of_birth": "2018-07-22", "gender": "male", "family_id": "fam_001", "class_group": "Primary 2", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_003", "name": "Peter Ssekitto", "date_of_birth": "2015-11-08", "gender": "male", "family_id": "fam_002", "class_group": "Primary 5", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_004", "name": "Grace Kiggundu", "date_of_birth": "2019-04-30", "gender": "female", "family_id": "fam_003", "class_group": "Nursery", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.children.insert_many(children)
    donation_count = await db.donations.count_documents({})
    if donation_count == 0:
        donations = [
            {"id": "don_001", "donor_name": "Alice Namukasa", "amount": 50000, "currency": "UGX", "type": "tithe", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_002", "donor_name": "Brian Ssekitto", "amount": 30000, "currency": "UGX", "type": "offering", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_003", "donor_name": "Anonymous", "amount": 100000, "currency": "UGX", "type": "donation", "date": "2026-04-06", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_004", "donor_name": "Francis Tumwesigye", "amount": 75000, "currency": "UGX", "type": "tithe", "date": "2026-03-25", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.donations.insert_many(donations)
    expense_count = await db.expenses.count_documents({})
    if expense_count == 0:
        expenses = [
            {"id": "exp_001", "title": "Electricity Bill", "amount": 85000, "currency": "UGX", "category": "utilities", "date": "2026-04-02", "status": "approved", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_002", "title": "Caretaker Salary", "amount": 150000, "currency": "UGX", "category": "salaries", "date": "2026-04-01", "status": "approved", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_003", "title": "Office Supplies", "amount": 25000, "currency": "UGX", "category": "supplies", "date": "2026-03-28", "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.expenses.insert_many(expenses)
    return {"message": "Extended seed data added"}


# ========== DASHBOARD ==========

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(campus_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    month_start_str = now.replace(day=1).isoformat()[:7]
    # System admins can override with a specific campus_id; non-admins always use their own
    if campus_id and is_system_admin(current_user):
        campus = {"location_id": campus_id}
    else:
        campus = await get_campus_filter(current_user)
    total_members = await db.members.count_documents({**campus})
    active_members = await db.members.count_documents({"status": "active", **campus})
    total_families = await db.families.count_documents({**campus})
    total_children = await db.children.count_documents({**campus})
    events_this_month = await db.events.count_documents({"date": {"$regex": f"^{month_start_str}"}, **campus})
    upcoming_events = await db.events.count_documents({"status": "upcoming", **campus})
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    checkins_today = await db.checkins.count_documents({"check_in_time": {"$gte": today_start}, **campus})
    now_str = now.isoformat()[:10]
    tasks_overdue = await db.tasks.count_documents({"status": {"$nin": ["done"]}, "due_date": {"$lt": now_str, "$ne": ""}})
    new_members_this_month = await db.members.count_documents({"join_date": {"$regex": f"^{month_start_str}"}, **campus})
    sales_result = await db.sales.aggregate([{"$match": {"created_at": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    monthly_sales = sales_result[0]["total"] if sales_result else 0
    donations_result = await db.donations.aggregate([{"$match": {"date": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    monthly_donations = donations_result[0]["total"] if donations_result else 0
    low_stock = await db.products.count_documents({"$expr": {"$lte": ["$stock", "$reorder_level"]}, **campus})
    recent_checkins = await db.checkins.find({**campus}, {"_id": 0}).sort("check_in_time", -1).limit(3).to_list(3)
    recent_members = await db.members.find({**campus}, {"_id": 0}).sort("created_at", -1).limit(2).to_list(2)
    activity = []
    for ci in recent_checkins:
        activity.append({"type": "checkin", "message": f"{ci.get('member_name')} checked in" + (f" to {ci.get('event_name', '')}" if ci.get('event_name') else ""), "time": ci.get("check_in_time", "")})
    for m in recent_members:
        activity.append({"type": "member", "message": f"New member: {m.get('name')} registered", "time": m.get("created_at", "")})
    activity.sort(key=lambda x: x.get("time", ""), reverse=True)
    expenses_result = await db.expenses.aggregate([{"$match": {"date": {"$regex": f"^{month_start_str}"}, **campus}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    monthly_expenses = expenses_result[0]["total"] if expenses_result else 0
    return {
        "total_members": total_members, "active_members": active_members, "total_families": total_families,
        "total_children": total_children, "events_this_month": events_this_month, "upcoming_events": upcoming_events,
        "checkins_today": checkins_today, "tasks_overdue": tasks_overdue, "new_members_this_month": new_members_this_month,
        "monthly_sales": monthly_sales, "monthly_donations": monthly_donations, "low_stock_count": low_stock,
        "monthly_expenses": monthly_expenses, "recent_activity": activity[:5],
    }


@api_router.get("/people/stats")
async def people_stats(current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    return {
        "total_members": await db.members.count_documents({**campus}),
        "active_members": await db.members.count_documents({"status": "active", **campus}),
        "total_families": await db.families.count_documents({**campus}),
        "total_children": await db.children.count_documents({**campus}),
        "total_guests": await db.guests.count_documents({**campus}),
        "pending_approvals": await db.users.count_documents({"status": "pending", **campus}),
    }


# ========== CAMPUS SWITCHER ==========

@api_router.put("/user/active-campus")
async def set_active_campus(data: dict, current_user: dict = Depends(get_current_user)):
    """Set active campus for data filtering. Admins/EDs/Advisers."""
    from deps import has_campus_switcher
    if not has_campus_switcher(current_user):
        raise HTTPException(status_code=403, detail="Insufficient permissions for campus switching")
    campus_id = data.get("campus_id")
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"active_campus_id": campus_id}})
    return {"active_campus_id": campus_id}


@api_router.put("/user/active-campus/clear")
async def clear_active_campus(current_user: dict = Depends(get_current_user)):
    """Clear campus filter to show all data."""
    await db.users.update_one({"id": current_user["id"]}, {"$unset": {"active_campus_id": ""}})
    return {"active_campus_id": None}


# ========== LOCATIONS (extracted to routers/locations.py) ==========
# Location models also moved to routers/locations.py


# ========== NOTIFICATIONS ==========

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
    return {"count": await db.notifications.count_documents(query)}

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
    doc = {"id": f"notif_{str(uuid.uuid4())[:8]}", **data.model_dump(), "read_by": [], "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.notifications.insert_one(doc); doc.pop("_id", None)
    return doc

@api_router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.delete_one({"id": notif_id}); return {"message": "Notification deleted"}


# ========== WEB PUSH ==========

@api_router.post("/push/subscribe")
async def subscribe_push(data: dict, current_user: dict = Depends(get_current_user)):
    subscription = data.get("subscription")
    if not subscription or not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Invalid push subscription")
    await db.push_subscriptions.update_one({"user_id": current_user["id"]}, {"$set": {"user_id": current_user["id"], "subscription": subscription, "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"message": "Push subscription saved"}

@api_router.delete("/push/subscribe")
async def unsubscribe_push(current_user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": current_user["id"]})
    return {"message": "Push subscription removed"}

@api_router.get("/push/vapid-key")
async def get_vapid_key():
    return {"publicKey": os.environ.get("VAPID_PUBLIC_KEY", "")}

async def send_push_to_user(user_id: str, title: str, body: str, url: str = "/"):
    try:
        from pywebpush import webpush
        subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(10)
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
        vapid_email = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@5812global.org")
        if not vapid_private: return
        import json
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": f"5812-{user_id[:8]}"})
        for sub in subs:
            try:
                webpush(subscription_info=sub["subscription"], data=payload, vapid_private_key=vapid_private, vapid_claims={"sub": f"mailto:{vapid_email}"})
            except Exception as e:
                if "410" in str(e) or "404" in str(e):
                    await db.push_subscriptions.delete_one({"user_id": user_id, "subscription.endpoint": sub["subscription"].get("endpoint")})
    except Exception as e:
        logger.warning(f"Push failed: {e}")


# ========== BIOMETRIC / NFC ==========

@api_router.post("/biometric/register")
async def register_biometric(data: dict, current_user: dict = Depends(get_current_user)):
    member_id = data.get("member_id") or current_user["id"]
    credential_id = data.get("credential_id")
    public_key = data.get("public_key")
    authenticator_type = data.get("type", "platform")
    if not credential_id: raise HTTPException(status_code=400, detail="credential_id required")
    doc = {"id": f"bio_{str(uuid.uuid4())[:8]}", "member_id": member_id, "credential_id": credential_id, "public_key": public_key, "type": authenticator_type, "created_at": datetime.now(timezone.utc).isoformat(), "last_used": None}
    await db.biometric_credentials.insert_one(doc); doc.pop("_id", None)
    return doc

@api_router.post("/biometric/verify")
async def verify_biometric(data: dict):
    credential_id = data.get("credential_id")
    if not credential_id: raise HTTPException(status_code=400, detail="credential_id required")
    cred = await db.biometric_credentials.find_one({"credential_id": credential_id}, {"_id": 0})
    if not cred: raise HTTPException(status_code=404, detail="Credential not found")
    await db.biometric_credentials.update_one({"credential_id": credential_id}, {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}})
    member = await db.members.find_one({"id": cred["member_id"]}, {"_id": 0, "id": 1, "name": 1, "role": 1})
    return {"verified": True, "member": member, "credential_type": cred.get("type")}

@api_router.post("/nfc/register")
async def register_nfc(data: dict, current_user: dict = Depends(get_current_user)):
    member_id = data.get("member_id"); serial_number = data.get("serial_number")
    if not member_id or not serial_number: raise HTTPException(status_code=400, detail="member_id and serial_number required")
    existing = await db.nfc_tags.find_one({"serial_number": serial_number})
    if existing: raise HTTPException(status_code=409, detail="NFC tag already registered")
    doc = {"id": f"nfc_{str(uuid.uuid4())[:8]}", "member_id": member_id, "serial_number": serial_number, "registered_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.nfc_tags.insert_one(doc); doc.pop("_id", None)
    return doc

@api_router.post("/nfc/scan")
async def scan_nfc(data: dict):
    serial_number = data.get("serial_number")
    if not serial_number: raise HTTPException(status_code=400, detail="serial_number required")
    tag = await db.nfc_tags.find_one({"serial_number": serial_number}, {"_id": 0})
    if not tag: raise HTTPException(status_code=404, detail="NFC tag not registered")
    member = await db.members.find_one({"id": tag["member_id"]}, {"_id": 0, "id": 1, "name": 1, "role": 1, "group": 1})
    if not member: raise HTTPException(status_code=404, detail="Member not found")
    return {"member": member, "tag_id": tag["id"]}


# ========== PARENT DASHBOARD ==========

@api_router.get("/parent/children")
async def get_parent_children(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]; user_email = current_user.get("email", "")
    children = await db.children.find({"$or": [{"parent_id": user_id}, {"parent_email": user_email}]}, {"_id": 0}).to_list(50)
    enriched = []
    for child in children:
        last_checkin = await db.checkins.find_one({"member_id": child.get("id", ""), "member_name": child.get("name", "")}, {"_id": 0, "check_in_time": 1, "event_name": 1}, sort=[("check_in_time", -1)])
        enriched.append({**child, "last_checkin": last_checkin})
    return enriched

@api_router.get("/parent/dashboard")
async def parent_dashboard(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]; user_email = current_user.get("email", "")
    children = await db.children.find({"$or": [{"parent_id": user_id}, {"parent_email": user_email}]}, {"_id": 0}).to_list(50)
    upcoming_events = await db.events.find({"status": "upcoming", "is_public": True}, {"_id": 0, "id": 1, "title": 1, "date": 1, "time": 1, "location": 1, "type": 1}).sort("date", 1).limit(5).to_list(5)
    return {"children": children, "children_count": len(children), "checked_in_count": 0, "upcoming_events": upcoming_events}


# ========== APP SETTINGS (extracted to routers/settings.py) ==========


# ========== GOOGLE OAUTH ==========

@api_router.post("/auth/google")
async def google_auth(data: dict):
    """Authenticate via Google OAuth token."""
    google_token = data.get("token") or data.get("credential")
    if not google_token:
        raise HTTPException(status_code=400, detail="Google token required")
    try:
        from emergentintegrations.llm.google_auth import verify_google_token
        google_user = verify_google_token(google_token)
    except ImportError:
        # Fallback: decode JWT manually
        import base64
        parts = google_token.split(".")
        if len(parts) >= 2:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            google_user = {"email": payload.get("email"), "name": payload.get("name"), "picture": payload.get("picture")}
        else:
            raise HTTPException(status_code=400, detail="Invalid Google token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Google auth failed: {str(e)}")
    email = google_user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Google")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {
            "id": str(uuid.uuid4()), "name": google_user.get("name", email.split("@")[0]),
            "email": email, "phone": "", "password_hash": "",
            "role": "Member", "status": "active", "avatar": google_user.get("picture", ""),
            "auth_provider": "google",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one({**user})
        user.pop("_id", None)
    else:
        if google_user.get("picture"):
            await db.users.update_one({"email": email}, {"$set": {"avatar": google_user["picture"]}})
    token = create_token(user["id"])
    return {"token": token, "user": {k: v for k, v in user.items() if k != "password_hash"}}


# ========== 2FA (TOTP) ==========

@api_router.post("/auth/2fa/setup")
async def setup_2fa(current_user: dict = Depends(get_current_user)):
    import pyotp
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.get("email", ""), issuer_name="58:12 Global Connect")
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_secret": secret, "totp_enabled": False}})
    try:
        import qrcode, base64
        from io import BytesIO
        img = qrcode.make(uri)
        buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        qr_base64 = base64.b64encode(buf.read()).decode()
        return {"secret": secret, "uri": uri, "qr_code": f"data:image/png;base64,{qr_base64}"}
    except Exception:
        return {"secret": secret, "uri": uri}


@api_router.post("/auth/2fa/verify")
async def verify_2fa(data: dict, current_user: dict = Depends(get_current_user)):
    import pyotp
    code = data.get("code", "")
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "totp_secret": 1})
    secret = user.get("totp_secret") if user else None
    if not secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    totp = pyotp.TOTP(secret)
    if totp.verify(code):
        await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_enabled": True}})
        return {"verified": True, "message": "2FA enabled successfully"}
    raise HTTPException(status_code=400, detail="Invalid code")


@api_router.post("/auth/2fa/validate")
async def validate_2fa_login(data: dict):
    """Validate 2FA code during login."""
    import pyotp
    user_id = data.get("user_id")
    code = data.get("code", "")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "totp_secret": 1, "totp_enabled": 1})
    if not user or not user.get("totp_enabled"):
        return {"valid": True}
    totp = pyotp.TOTP(user["totp_secret"])
    if totp.verify(code):
        return {"valid": True}
    raise HTTPException(status_code=400, detail="Invalid 2FA code")


@api_router.delete("/auth/2fa")
async def disable_2fa(current_user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_enabled": False, "totp_secret": None}})
    return {"message": "2FA disabled"}


# ========== GDPR, INVENTORY, FINANCIAL APIs (extracted to routers/settings.py) ==========


# ========== WEBCAL SUBSCRIPTION ==========

@api_router.get("/webcal/{user_id}.ics")
async def webcal_feed(user_id: str):
    """Public webcal feed URL for a user's events."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "location_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    query = {"$or": [{"is_public": True}, {"created_by": user_id}]}
    if user.get("location_id"):
        query["$or"].append({"location_id": user["location_id"]})
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(200)
    ical = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//58:12 Global Connect//CRM//EN\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
    for ev in events:
        date_str = (ev.get("date") or "").replace("-", "")
        time_str = (ev.get("time") or "0000").replace(":", "")
        dtstart = f"{date_str}T{time_str}00" if time_str else date_str
        ical += f"BEGIN:VEVENT\r\nUID:{ev['id']}@5812global\r\nDTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\nDTSTART:{dtstart}\r\nSUMMARY:{ev.get('title','')}\r\nDESCRIPTION:{ev.get('description','')}\r\nLOCATION:{ev.get('location','')}\r\nEND:VEVENT\r\n"
    ical += "END:VCALENDAR\r\n"
    from starlette.responses import Response
    return Response(content=ical, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=5812global-events.ics"})


# ========== FINANCIAL API MANAGEMENT (extracted to routers/settings.py) ==========


# ========== I18N / TRANSLATIONS ==========

TRANSLATIONS = {
    "en": {"dashboard": "Dashboard", "people": "People", "events": "Events", "calendar": "Calendar", "tasks": "Tasks", "checkins": "Check-Ins", "outreach": "Outreach", "communications": "Communications", "resources": "Resources", "access": "Access Control", "financial": "Financial", "sales": "Sales & Products", "analytics": "Analytics", "reports": "Reports", "settings": "Settings", "logout": "Logout", "search": "Search", "save": "Save", "cancel": "Cancel", "delete": "Delete", "edit": "Edit", "add": "Add", "close": "Close", "welcome": "Welcome", "members": "Members", "volunteers": "Volunteers", "shifts": "Shifts", "templates": "Email Templates"},
    "fr": {"dashboard": "Tableau de bord", "people": "Personnes", "events": "Evenements", "calendar": "Calendrier", "tasks": "Taches", "checkins": "Enregistrements", "outreach": "Sensibilisation", "communications": "Communications", "resources": "Ressources", "access": "Controle d'acces", "financial": "Finances", "sales": "Ventes et Produits", "analytics": "Analyses", "reports": "Rapports", "settings": "Parametres", "logout": "Deconnexion", "search": "Rechercher", "save": "Enregistrer", "cancel": "Annuler", "delete": "Supprimer", "edit": "Modifier", "add": "Ajouter", "close": "Fermer", "welcome": "Bienvenue", "members": "Membres", "volunteers": "Benevoles", "shifts": "Quarts", "templates": "Modeles d'email"},
    "sw": {"dashboard": "Dashibodi", "people": "Watu", "events": "Matukio", "calendar": "Kalenda", "tasks": "Kazi", "checkins": "Kuingia", "outreach": "Kufikia", "communications": "Mawasiliano", "resources": "Rasilimali", "access": "Udhibiti wa Ufikiaji", "financial": "Fedha", "sales": "Mauzo na Bidhaa", "analytics": "Uchambuzi", "reports": "Ripoti", "settings": "Mipangilio", "logout": "Ondoka", "search": "Tafuta", "save": "Hifadhi", "cancel": "Ghairi", "delete": "Futa", "edit": "Hariri", "add": "Ongeza", "close": "Funga", "welcome": "Karibu", "members": "Wanachama", "volunteers": "Watu wa kujitolea", "shifts": "Zamu", "templates": "Violezo vya barua pepe"},
    "lg": {"dashboard": "Dashiboodi", "people": "Abantu", "events": "Ebikozesebwa", "calendar": "Kalenda", "tasks": "Emirimu", "checkins": "Okwingira", "outreach": "Okubuulira", "communications": "Amawulire", "resources": "Ebyetaagisa", "access": "Okufuna Emikisa", "financial": "Ensimbi", "sales": "Okutunda", "analytics": "Okusengejja", "reports": "Lipoota", "settings": "Entegeka", "logout": "Fuluma", "search": "Noonya", "save": "Tereka", "cancel": "Sazaamu", "delete": "Sangula", "edit": "Kyusa", "add": "Gatta", "close": "Ggalawo", "welcome": "Tukusanyukidde", "members": "Bameemba", "volunteers": "Abayizi", "shifts": "Emirembe", "templates": "Ekifaananyi"},
    "th": {"dashboard": "แดชบอร์ด", "people": "ผู้คน", "events": "กิจกรรม", "calendar": "ปฏิทิน", "tasks": "งาน", "checkins": "เช็คอิน", "outreach": "การเผยแพร่", "communications": "การสื่อสาร", "resources": "ทรัพยากร", "access": "การควบคุมการเข้าถึง", "financial": "การเงิน", "sales": "การขายและสินค้า", "analytics": "การวิเคราะห์", "reports": "รายงาน", "settings": "การตั้งค่า", "logout": "ออกจากระบบ", "search": "ค้นหา", "save": "บันทึก", "cancel": "ยกเลิก", "delete": "ลบ", "edit": "แก้ไข", "add": "เพิ่ม", "close": "ปิด", "welcome": "ยินดีต้อนรับ", "members": "สมาชิก", "volunteers": "อาสาสมัคร", "shifts": "กะ", "templates": "เทมเพลตอีเมล"},
}


@api_router.get("/i18n/{lang}")
async def get_translations(lang: str = "en"):
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])


@api_router.get("/i18n")
async def get_all_translations():
    return {"languages": [{"code": "en", "name": "English"}, {"code": "fr", "name": "Francais"}, {"code": "sw", "name": "Kiswahili"}, {"code": "lg", "name": "Luganda"}, {"code": "th", "name": "ไทย (Thai)"}], "translations": TRANSLATIONS}


# ========== SEED LOCATIONS & ALL ==========

@api_router.post("/seed-locations")
async def seed_locations_and_notifications():
    loc_count = await db.locations.count_documents({})
    if loc_count == 0:
        locations = [
            {"id": "loc_001", "name": "58:12 Global (Central)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Administration", "Finance", "Operations"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_002", "name": "Entebbe Campus", "code": "ETB", "type": "campus", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "country": "Uganda", "currency": "UGX", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Youth", "Education"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_003", "name": "Jinja Campus", "code": "JNJ", "type": "campus", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "country": "Uganda", "currency": "UGX", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Community", "Sports"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_004", "name": "Kampala East", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "is_venue": True, "is_bookable": True, "is_restricted": False, "departments": [], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
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


@api_router.post("/seed-all")
async def seed_all_data():
    seeded = []
    if await db.outreach_programs.count_documents({}) == 0:
        programs = [
            {"id": "op_001", "name": "Community Health Drive", "description": "Free medical check-ups and health education in Kampala slums.", "category": "health", "status": "active", "location": "Katwe, Kampala", "start_date": "2026-01-15", "target": 500, "sessions_count": 3, "total_reached": 142, "is_recurring": True, "recurrence_pattern": "saturday", "recurrence_day": 2, "recurrence_time": "09:00", "recurrence_end_time": "14:00", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_002", "name": "School Outreach Program", "description": "Bible studies and character formation in local schools.", "category": "education", "status": "active", "location": "Entebbe Municipality", "start_date": "2025-09-01", "target": 200, "sessions_count": 8, "total_reached": 316, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_003", "name": "Widows & Orphans Support", "description": "Monthly food distribution and counselling for vulnerable families.", "category": "welfare", "status": "active", "location": "Multiple Locations", "start_date": "2025-06-01", "target": 100, "sessions_count": 5, "total_reached": 89, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.outreach_programs.insert_many(programs)
        sessions = [
            {"id": "os_001", "program_id": "op_001", "date": "2026-03-10", "time": "09:00", "location": "Katwe Health Centre", "attendees": 47, "notes": "Distributed 47 medicine packs.", "led_by": "Dr. Auma Florence", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "os_002", "program_id": "op_002", "date": "2026-03-14", "time": "14:00", "location": "Entebbe Primary School", "attendees": 85, "notes": "Session on integrity and purpose.", "led_by": "Pastor Amos", "created_at": datetime.now(timezone.utc).isoformat()},
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
            {"id": "ann_001", "title": "Welcome to March 2026!", "content": "This month we launch our Community Health Drive.", "type": "general", "target_role": None, "pinned": True, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ann_002", "title": "Staff Meeting - This Friday", "content": "Mandatory all-staff meeting this Friday at 3 PM.", "type": "urgent", "target_role": "admin", "pinned": False, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.announcements.insert_many(announcements)
        seeded.append("announcements")
    if await db.badges.count_documents({}) == 0:
        badges = [
            {"id": "bdg_001", "name": "Faithful Servant", "description": "Awarded for 1+ year of consistent volunteering.", "color": "#f59e0b", "icon": "star", "criteria": "12+ months active service", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_002", "name": "Prayer Warrior", "description": "Regular participant in prayer meetings.", "color": "#6366f1", "icon": "heart", "criteria": "30+ prayer sessions attended", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_003", "name": "Outreach Champion", "description": "Led or participated in 5+ outreach sessions.", "color": "#10b981", "icon": "award", "criteria": "5+ outreach sessions", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.badges.insert_many(badges)
        seeded.append("badges")
    return {"seeded": seeded, "message": "Seed complete"}


# ========== INCLUDE ALL ROUTERS ==========
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
    from routers.portal import router as portal_router
    from routers.events import router as events_router
    from routers.tasks import router as tasks_router
    from routers.financial import router as financial_router
    from routers.chat import router as chat_router
    from routers.admin import router as admin_router
    from routers.programmes import router as programmes_router
    from routers.misc import router as misc_router
    from routers.webauthn import router as webauthn_router
    from routers.boards import router as boards_router
    from routers.email import router as email_router
    from routers.analytics import router as analytics_router
    from routers.scheduling import router as scheduling_router
    from routers.templates import router as templates_router
    from routers.calling import router as calling_router
    from routers.presence import router as presence_router
    from routers.conferences import router as conferences_router
    from routers.reactions import router as reactions_router
    from routers.locations import router as locations_router
    from routers.settings import router as settings_router
    from routers.wave import router as wave_router
    app.include_router(bookings_router)
    app.include_router(ws_router)
    app.include_router(notifications_router)
    app.include_router(access_router)
    app.include_router(reports_router)
    app.include_router(documents_router)
    app.include_router(auth_router)
    app.include_router(members_router)
    app.include_router(import_csv_router)
    app.include_router(portal_router)
    app.include_router(events_router)
    app.include_router(tasks_router)
    app.include_router(financial_router)
    app.include_router(chat_router)
    app.include_router(admin_router)
    app.include_router(programmes_router)
    app.include_router(misc_router)
    app.include_router(webauthn_router)
    app.include_router(boards_router)
    app.include_router(email_router)
    app.include_router(analytics_router)
    app.include_router(scheduling_router)
    app.include_router(templates_router)
    app.include_router(calling_router)
    app.include_router(presence_router)
    app.include_router(conferences_router)
    app.include_router(reactions_router)
    app.include_router(locations_router)
    app.include_router(settings_router)
    app.include_router(wave_router)
    logger.info("All modular routers loaded")
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


async def _send_push_to_user(user_id: str, title: str, body: str, url: str = "/tasks"):
    """Send a Web Push notification to all devices of a user."""
    try:
        from pywebpush import webpush
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
        vapid_email = os.environ.get("VAPID_EMAIL", "admin@5812.org")
        if not vapid_private:
            return
        subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(10)
        payload = json.dumps({"title": title, "body": body, "icon": "/icon-192.png", "url": url})
        for sub in subs:
            try:
                webpush(subscription_info=sub["subscription"], data=payload, vapid_private_key=vapid_private, vapid_claims={"sub": f"mailto:{vapid_email}"})
            except Exception as e:
                logger.warning(f"Push send failed for {user_id}: {e}")
                if "expired" in str(e).lower() or "unsubscribe" in str(e).lower():
                    await db.push_subscriptions.delete_one({"user_id": user_id, "subscription.endpoint": sub["subscription"].get("endpoint")})
    except Exception as e:
        logger.warning(f"Push notification error: {e}")


async def _run_due_date_reminder_scheduler():
    """Hourly background task: notify assignees when their task is due tomorrow or today."""
    from datetime import date
    await asyncio.sleep(30)  # short initial delay to let startup finish
    while True:
        try:
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            today_str = date.today().isoformat()
            
            # Tasks due tomorrow
            due_tasks = await db.tasks.find({
                "due_date": tomorrow,
                "is_archived": {"$ne": True},
                "status": {"$ne": "done"},
            }, {"_id": 0, "id": 1, "title": 1, "assignees": 1, "assignee": 1, "board_id": 1}).to_list(200)

            for task in due_tasks:
                assignees = list(task.get("assignees") or [])
                if task.get("assignee") and task["assignee"] not in assignees:
                    assignees.append(task["assignee"])
                for uid in assignees:
                    await _send_push_to_user(uid, "Task Due Tomorrow", f'"{task["title"]}" is due tomorrow', "/tasks")
            
            # Tasks due today
            today_tasks = await db.tasks.find({
                "due_date": today_str,
                "is_archived": {"$ne": True},
                "status": {"$ne": "done"},
            }, {"_id": 0, "id": 1, "title": 1, "assignees": 1, "assignee": 1, "board_id": 1}).to_list(200)

            for task in today_tasks:
                assignees = list(task.get("assignees") or [])
                if task.get("assignee") and task["assignee"] not in assignees:
                    assignees.append(task["assignee"])
                for uid in assignees:
                    await _send_push_to_user(uid, "Task Due Today", f'"{task["title"]}" is due today!', "/tasks")

            total = len(due_tasks) + len(today_tasks)
            if total:
                logger.info(f"Sent due-date reminders for {total} tasks ({len(today_tasks)} today, {len(due_tasks)} tomorrow)")
        except Exception as e:
            logger.error(f"Due-date scheduler error: {e}")
        await asyncio.sleep(3600)  # Run every hour


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Start background task reminder scheduler
    asyncio.create_task(_run_due_date_reminder_scheduler())
    user_count = await db.users.count_documents({})
    if user_count == 0:
        logger.info("Seeding initial data...")
        try:
            await db.users.create_index("email", unique=True)
            await db.users.create_index("id", unique=True)
            await db.members.create_index("id", unique=True)
            await db.members.create_index("email")
            await db.members.create_index("pin")
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
        admin = {"id": str(uuid.uuid4()), "name": "Admin User", "email": "admin@5812global.org", "phone": "+256 800 5812", "password_hash": hash_password("Admin@1234"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        admin2 = {"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            await db.users.insert_one(admin)
            await db.users.insert_one(admin2)
            logger.info("Admin users created")
        except Exception as e:
            logger.warning(f"Admin creation: {e}")
    uganda_admin = await db.users.find_one({"email": "admin@5812uganda.org"})
    if not uganda_admin:
        await db.users.insert_one({"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()})
    else:
        await db.users.update_one({"email": "admin@5812uganda.org"}, {"$set": {"password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active"}})
    try:
        if await db.locations.count_documents({}) == 0:
            locations = [
                {"id": "loc_001", "name": "58:12 Global (Central)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Administration", "Finance", "Operations"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_002", "name": "Entebbe Campus", "code": "ETB", "type": "campus", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "country": "Uganda", "currency": "UGX", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Youth", "Education"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_003", "name": "Jinja Campus", "code": "JNJ", "type": "campus", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "country": "Uganda", "currency": "UGX", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Community", "Sports"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "loc_004", "name": "Kampala East", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "is_venue": True, "is_bookable": True, "is_restricted": False, "departments": [], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.locations.insert_many(locations)
        if await db.notifications.count_documents({}) == 0:
            notifications = [
                {"id": "notif_001", "title": "New Member Approval", "message": "3 new member registrations are pending approval.", "type": "warning", "target_role": "admin", "link": "/members", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
                {"id": "notif_002", "title": "Low Stock Alert", "message": "Coffee and Eggs (Tray) are out of stock.", "type": "error", "target_role": None, "link": "/sales", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            ]
            await db.notifications.insert_many(notifications)
    except Exception as e:
        logger.warning(f"Location/notification seeding: {e}")

    # Auto-promote silvester@lubwamas.org to system admin
    silvester = await db.users.find_one({"email": "silvester@lubwamas.org"})
    if silvester:
        if silvester.get("role") != "admin":
            await db.users.update_one({"email": "silvester@lubwamas.org"}, {"$set": {"role": "admin"}})
            logger.info("Promoted silvester@lubwamas.org to admin")
    else:
        # Create admin account if doesn't exist
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "name": "Silvester Lubwama",
            "email": "silvester@lubwamas.org",
            "phone": "",
            "password_hash": hash_password("Admin@5812"),
            "role": "admin",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Created admin account for silvester@lubwamas.org")


@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
