# Fix bcrypt 4.x + passlib 1.7.4 compatibility
import bcrypt
if not hasattr(bcrypt, '__about__'):
    class _About:
        __version__ = getattr(bcrypt, '__version__', '4.0.0')
    bcrypt.__about__ = _About()

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


@app.get("/health")
async def root_health_check():
    """Root-level health endpoint for deployment probes that hit /health directly."""
    return {"status": "healthy", "service": "58:12 Global Connect CRM"}


@app.get("/readyz")
async def readyz():
    """Readiness probe — verifies MongoDB round-trip. Returns 503 if DB unreachable."""
    started = time.time()
    try:
        await asyncio.wait_for(db.command("ping"), timeout=3.0)
        return {"status": "ready", "db_latency_ms": round((time.time() - started) * 1000, 1)}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db_error": str(e)[:200], "db_latency_ms": round((time.time() - started) * 1000, 1)},
        )


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


# ========== CAMPUS SWITCHER ==========

@api_router.put("/user/active-campus")
async def set_active_campus(data: dict, current_user: dict = Depends(get_current_user)):
    """Set active campus for data filtering. Admins/EDs/Advisers can switch to any campus.
    Multi-campus users can switch among their assigned campuses."""
    from deps import has_campus_switcher
    campus_id = data.get("campus_id")
    if not campus_id:
        raise HTTPException(status_code=400, detail="campus_id is required")
    if has_campus_switcher(current_user) or is_system_admin(current_user):
        pass  # Can switch to any campus
    else:
        # Build the set of allowed locations: user's own + their sub-locations' parent campuses
        user_locs = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            user_locs.add(current_user["location_id"])
        # Add parent campuses (if user is in a sub-location, they belong to its campus)
        if user_locs:
            parents = await db.locations.find(
                {"id": {"$in": list(user_locs)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
                {"_id": 0, "parent_id": 1}
            ).to_list(50)
            for p in parents:
                if p.get("parent_id"):
                    user_locs.add(p["parent_id"])
        # Add sub-locations under user's campuses (so they can switch INTO a sub)
        if user_locs:
            subs = await db.locations.find(
                {"parent_id": {"$in": list(user_locs)}},
                {"_id": 0, "id": 1, "is_restricted": 1}
            ).to_list(200)
            for s in subs:
                # Only auto-include non-restricted; restricted ones must be explicit
                if not s.get("is_restricted") or s["id"] in user_locs:
                    user_locs.add(s["id"])
        if campus_id not in user_locs:
            loc = await db.locations.find_one({"id": campus_id}, {"_id": 0, "type": 1})
            if not loc:
                raise HTTPException(status_code=404, detail="Campus not found")
            raise HTTPException(status_code=403, detail="You are not assigned to this campus or its sub-locations")
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
            "role": "Guest", "status": "pending", "avatar": google_user.get("picture", ""),
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


# ========== FINANCIAL API MANAGEMENT (extracted to routers/settings.py) ==========


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
    from routers.hr import router as hr_router
    app.include_router(hr_router)
    from routers.seed import router as seed_router
    from routers.dashboard import router as dashboard_router
    from routers.i18n import router as i18n_router
    from routers.products import router as products_router
    from routers.sales import router as sales_router
    from routers.sheet_import import router as sheet_import_router
    from routers.invoices import router as invoices_router
    from routers.statements import router as statements_router
    from routers.accounting import router as accounting_router
    from routers.approvals import router as approvals_router
    from routers.social_work import router as social_work_router, portal_router as school_portal_router
    app.include_router(seed_router)
    app.include_router(dashboard_router)
    app.include_router(i18n_router)
    app.include_router(products_router)
    app.include_router(sales_router)
    app.include_router(sheet_import_router)
    app.include_router(invoices_router)
    app.include_router(statements_router)
    app.include_router(accounting_router)
    app.include_router(approvals_router)
    app.include_router(social_work_router)
    app.include_router(school_portal_router)
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
    """Hourly background task: notify assignees when their task is due tomorrow or today.
    Also fires a daily birthday/anniversary check at ~08:00 local UTC."""
    from datetime import date
    await asyncio.sleep(30)  # short initial delay to let startup finish
    last_birthday_check_date = None
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

            # Daily birthday & anniversary check (once per day, during 08:00-09:00 UTC hour)
            now = datetime.now(timezone.utc)
            if last_birthday_check_date != date.today() and now.hour == 8:
                await _fire_birthday_anniversary_notifications()
                await _fire_scheduled_customer_statements()
                await _fire_overdue_payment_reminders()
                last_birthday_check_date = date.today()
        except Exception as e:
            logger.error(f"Due-date scheduler error: {e}")
        await asyncio.sleep(3600)  # Run every hour


async def _fire_scheduled_customer_statements():
    """Daily 08:00 UTC: check scheduled statements due today (weekly/monthly) and auto-email them."""
    try:
        today = datetime.now(timezone.utc)
        weekday = today.weekday()  # 0=Mon
        dom = today.day
        scheds = await db.statement_schedules.find({"active": True}, {"_id": 0}).to_list(1000)
        for s in scheds:
            cadence = s.get("cadence")
            due = False
            if cadence == "weekly" and (s.get("day_of_week") or 0) == weekday:
                due = True
            elif cadence == "monthly" and (s.get("day_of_month") or 1) == dom:
                due = True
            if not due:
                continue
            try:
                from routers.statements import _render_statement_html, _html_to_pdf
                # Compute period: weekly = last 7 days, monthly = last month
                if cadence == "weekly":
                    pf = (today - timedelta(days=7)).strftime("%Y-%m-%d")
                else:
                    pf = (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
                pt = today.strftime("%Y-%m-%d")
                customer = await db.customer_accounts.find_one({"id": s.get("customer_id")}, {"_id": 0}) or {}
                sale_q = {
                    "$or": [{"customer_id": s.get("customer_id")}, {"customer_name": customer.get("name", "")}],
                    "voided": {"$ne": True},
                    "created_at": {"$gte": pf + "T00:00:00", "$lte": pt + "T23:59:59.999"},
                }
                sales = await db.sales.find(sale_q, {"_id": 0}).to_list(2000)
                if not sales:
                    continue  # skip empty statements
                to_email = s.get("email_override") or customer.get("email")
                if not to_email:
                    continue
                html = _render_statement_html(customer, sales, pf, pt)
                pdf = _html_to_pdf(html)
                import resend
                resend.api_key = os.environ.get("RESEND_API_KEY", "")
                sender = os.environ.get("SENDER_EMAIL", "no-reply@5812global.org")
                if not resend.api_key:
                    continue
                resend.Emails.send({
                    "from": sender, "to": to_email,
                    "subject": f"Your 58:12 {cadence} statement ({pf} → {pt})",
                    "html": f"<p>Hi {customer.get('name', '')},</p><p>Your {cadence} statement is attached.</p><p>— 58:12 Global</p>",
                    "attachments": [{"filename": f"statement-{pf}-{pt}.pdf", "content": list(pdf)}],
                })
                await db.statement_emails.insert_one({
                    "id": f"stmt_{uuid.uuid4().hex[:8]}",
                    "customer_id": s.get("customer_id"),
                    "customer_name": customer.get("name"),
                    "to_email": to_email,
                    "period_from": pf, "period_to": pt,
                    "sales_count": len(sales),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "auto_scheduled": True,
                    "cadence": cadence,
                })
            except Exception as e:
                logger.error(f"Auto-statement send for customer {s.get('customer_id')}: {e}")
    except Exception as e:
        logger.error(f"Scheduled statements error: {e}")


async def _fire_overdue_payment_reminders():
    """Daily 08:00 UTC: tiered dunning ladder.
    Tier 1 (gentle) ≥ 14d, Tier 2 (firmer) ≥ 30d, Tier 3 (final) ≥ 60d.
    Skips customers with active "payment_promise" until the promised_date.
    Idempotent — won't repeat the same tier; advances to the next when threshold crossed."""
    try:
        now = datetime.now(timezone.utc)
        cutoff_14 = (now - timedelta(days=14)).isoformat()
        # Aggregate pending sales ≥ 14d old
        pending = await db.sales.find({
            "payment_status": "pending",
            "voided": {"$ne": True},
            "created_at": {"$lte": cutoff_14},
        }, {"_id": 0}).to_list(2000)
        if not pending:
            return
        by_customer = {}
        for s in pending:
            key = s.get("customer_id") or s.get("customer_name") or "unknown"
            if key == "unknown" or key.lower().startswith("walk-in"):
                continue
            by_customer.setdefault(key, []).append(s)
        sent_count = 0
        for cust_key, sales in by_customer.items():
            try:
                # Active payment_promise — skip until promised_date elapses
                promise = await db.payment_promises.find_one({
                    "customer_key": cust_key,
                    "status": "active",
                })
                if promise and promise.get("promised_date"):
                    try:
                        promised = datetime.fromisoformat(promise["promised_date"].replace("Z", "+00:00"))
                        if promised >= now:
                            continue
                    except Exception:
                        pass

                oldest_days = max(((now - datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))).days) for o in sales)
                # Pick the next tier
                if oldest_days >= 60:
                    next_tier = 3
                elif oldest_days >= 30:
                    next_tier = 2
                else:
                    next_tier = 1
                # Was this tier already sent?
                already = await db.payment_reminders.find_one({
                    "customer_key": cust_key,
                    "tier": next_tier,
                })
                if already:
                    continue

                from routers.statements import _render_statement_html, _html_to_pdf
                customer = await db.customer_accounts.find_one(
                    {"$or": [{"id": cust_key}, {"name": cust_key}]},
                    {"_id": 0}
                ) or {}
                to_email = customer.get("email") or (sales[0].get("customer_email") if sales else None)
                if not to_email:
                    continue
                period_from = (now - timedelta(days=90)).strftime("%Y-%m-%d")
                period_to = now.strftime("%Y-%m-%d")
                total_outstanding = sum(float(s.get("total") or 0) for s in sales)
                full_sales = await db.sales.find({
                    "$or": [{"customer_id": cust_key}, {"customer_name": customer.get("name") or cust_key}],
                    "voided": {"$ne": True},
                    "created_at": {"$gte": period_from + "T00:00:00", "$lte": period_to + "T23:59:59.999"},
                }, {"_id": 0}).sort("created_at", 1).to_list(2000)
                html = _render_statement_html(customer, full_sales, period_from, period_to)
                pdf = _html_to_pdf(html)
                import resend
                resend.api_key = os.environ.get("RESEND_API_KEY", "")
                sender = os.environ.get("SENDER_EMAIL", "no-reply@5812global.org")
                if not resend.api_key:
                    continue
                currency = sales[0].get("items", [{}])[0].get("currency") if sales[0].get("items") else "UGX"

                # Build tier-specific copy + subject
                if next_tier == 1:
                    subject = f"Friendly reminder: Outstanding balance — {currency} {total_outstanding:,.2f}"
                    intro = (f"<p>This is a friendly reminder of <strong>{len(sales)} outstanding payment(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is <strong>{oldest_days} days</strong> old.</p>"
                             f"<p>If you have already paid, please disregard. Otherwise, kindly settle at your earliest convenience.</p>")
                    cc = None
                elif next_tier == 2:
                    late_fee = total_outstanding * 0.05
                    subject = f"Second notice: please settle {currency} {total_outstanding:,.2f}"
                    intro = (f"<p>We have not yet received payment for <strong>{len(sales)} invoice(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is now <strong>{oldest_days} days</strong> overdue.</p>"
                             f"<p>To avoid a possible late fee of approximately <strong>{currency} {late_fee:,.2f}</strong> "
                             f"(≈5%), please arrange payment within the next 7 days. If you have already paid, please reply with confirmation.</p>")
                    cc = None
                else:  # tier 3 — final
                    subject = f"FINAL NOTICE: {currency} {total_outstanding:,.2f} overdue"
                    intro = (f"<p>This is our <strong>final reminder</strong> regarding <strong>{len(sales)} unpaid invoice(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is now <strong>{oldest_days} days</strong> overdue.</p>"
                             f"<p>If payment is not received within 7 days, the account may be referred to management. "
                             f"Please contact us immediately if there are any issues.</p>")
                    # CC manager — look up a director/manager in the customer's home location if available
                    cc = None
                    try:
                        loc_id = (sales[0] or {}).get("location_id")
                        if loc_id:
                            mgr = await db.users.find_one({
                                "location_id": loc_id,
                                "role": {"$in": ["Manager", "Director", "Executive Director"]},
                                "status": "active",
                                "email": {"$exists": True, "$ne": ""},
                            }, {"_id": 0, "email": 1})
                            if mgr and mgr.get("email"):
                                cc = [mgr["email"]]
                    except Exception:
                        cc = None

                body = (f"<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                        f"<img src='https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1' style='height: 40px; margin-bottom: 20px;' />"
                        f"<p>Hi {customer.get('name') or cust_key},</p>"
                        f"{intro}"
                        f"<p>A full statement is attached for your reference.</p>"
                        f"<p>Thank you,<br/>58:12 Global</p></div>")
                payload = {
                    "from": sender, "to": to_email,
                    "subject": subject,
                    "html": body,
                    "attachments": [{"filename": f"statement-{period_from}-{period_to}.pdf", "content": list(pdf)}],
                }
                if cc:
                    payload["cc"] = cc
                resend.Emails.send(payload)
                await db.payment_reminders.insert_one({
                    "id": f"rem_{uuid.uuid4().hex[:8]}",
                    "customer_key": cust_key,
                    "customer_name": customer.get("name") or cust_key,
                    "to_email": to_email,
                    "cc": cc or [],
                    "tier": next_tier,
                    "outstanding_total": total_outstanding,
                    "outstanding_count": len(sales),
                    "oldest_days": oldest_days,
                    "sent_at": now.isoformat(),
                    "auto_triggered": True,
                })
                sent_count += 1
            except Exception as e:
                logger.error(f"Auto payment-reminder for {cust_key}: {e}")
        if sent_count:
            logger.info(f"Auto-sent {sent_count} payment reminders (tiered)")
    except Exception as e:
        logger.error(f"Overdue payment reminders error: {e}")


async def _fire_birthday_anniversary_notifications():
    """Create in-app notifications for today's birthdays + work anniversaries across all members.
    Safe + idempotent per day (scheduler only calls once per day)."""
    from datetime import date
    try:
        today = date.today()
        mm_dd = f"-{today.month:02d}-{today.day:02d}"
        # Birthdays: match any date_of_birth ending with -MM-DD
        birthday_people = await db.members.find(
            {"date_of_birth": {"$regex": f"{mm_dd}$"}, "status": "active"},
            {"_id": 0, "id": 1, "name": 1, "location_id": 1, "date_of_birth": 1}
        ).to_list(500)
        # Work anniversaries: match join_date ending with -MM-DD
        anniversary_people = await db.members.find(
            {"join_date": {"$regex": f"{mm_dd}$"}, "status": "active"},
            {"_id": 0, "id": 1, "name": 1, "location_id": 1, "join_date": 1, "role": 1}
        ).to_list(500)

        fired = 0
        for m in birthday_people:
            try:
                years = today.year - int((m.get("date_of_birth") or "0000")[:4])
            except Exception:
                years = 0
            if years <= 0:
                continue
            # Idempotency: skip if a birthday notification for this member was already fired today
            existing = await db.notifications.find_one({
                "kind": "birthday",
                "ref_member_id": m.get("id"),
                "created_at": {"$gte": today.isoformat()},
            })
            if existing:
                continue
            msg = f"🎂 {m.get('name', 'Someone')} turns {years} today!"
            await db.notifications.insert_one({
                "id": f"notif_{uuid.uuid4().hex[:10]}",
                "title": "Birthday today",
                "message": msg,
                "type": "info",
                "target_role": None,
                "link": "/members",
                "read_by": [],
                "location_id": m.get("location_id"),
                "kind": "birthday",
                "ref_member_id": m.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            fired += 1

        for m in anniversary_people:
            try:
                years = today.year - int((m.get("join_date") or "0000")[:4])
            except Exception:
                years = 0
            if years <= 0:
                continue
            existing = await db.notifications.find_one({
                "kind": "anniversary",
                "ref_member_id": m.get("id"),
                "created_at": {"$gte": today.isoformat()},
            })
            if existing:
                continue
            title = "Work anniversary" if (m.get("role") or "").lower() in {"staff", "manager", "director", "leader", "coordinator", "admin", "hr"} else "Member anniversary"
            msg = f"🎉 {m.get('name', 'Someone')} — {years} year{'s' if years > 1 else ''} with us today!"
            await db.notifications.insert_one({
                "id": f"notif_{uuid.uuid4().hex[:10]}",
                "title": title,
                "message": msg,
                "type": "info",
                "target_role": None,
                "link": "/members",
                "read_by": [],
                "location_id": m.get("location_id"),
                "kind": "anniversary",
                "ref_member_id": m.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            fired += 1

        if fired:
            logger.info(f"Fired {fired} birthday/anniversary notifications ({len(birthday_people)} birthdays, {len(anniversary_people)} anniversaries)")
    except Exception as e:
        logger.error(f"Birthday/anniversary fire error: {e}")


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Start background task reminder scheduler
    asyncio.create_task(_run_due_date_reminder_scheduler())
    # Defer heavy seeding so the app becomes ready immediately
    asyncio.create_task(_seed_initial_data())


async def _ensure_indexes():
    """Idempotent index creation. Runs on every startup. Safe to call repeatedly."""
    try:
        # Users: lookups by email, id, role, location, status
        await db.users.create_index("email", unique=True)
        await db.users.create_index("id", unique=True)
        await db.users.create_index([("role", 1), ("status", 1)])
        await db.users.create_index([("location_id", 1), ("status", 1)])
        await db.users.create_index("location_ids")
        # Members
        await db.members.create_index("id", unique=True)
        await db.members.create_index("email")
        await db.members.create_index("pin")
        await db.members.create_index([("location_id", 1), ("status", 1)])
        await db.members.create_index("user_id")
        await db.members.create_index("date_of_birth")
        # Events — date-range queries are hot
        await db.events.create_index("id", unique=True)
        await db.events.create_index([("date", 1), ("status", 1)])
        await db.events.create_index([("location_id", 1), ("date", 1)])
        # Tasks / Boards
        await db.tasks.create_index("id", unique=True)
        await db.tasks.create_index([("board_id", 1), ("list_id", 1), ("position", 1)])
        await db.tasks.create_index([("assignees", 1), ("due_date", 1)])
        await db.tasks.create_index([("due_date", 1), ("is_archived", 1), ("status", 1)])
        await db.boards.create_index("id", unique=True)
        await db.boards.create_index([("location_id", 1), ("is_global", 1)])
        # Check-ins
        await db.checkins.create_index("id", unique=True)
        await db.checkins.create_index([("event_id", 1), ("check_in_time", -1)])
        await db.checkins.create_index([("date", 1), ("location_id", 1)])
        # Chat
        await db.chat_messages.create_index("conversation_id")
        await db.chat_messages.create_index([("conversation_id", 1), ("created_at", -1)])
        await db.chat_messages.create_index("thread_id")
        await db.conversations.create_index("participants")
        await db.conversations.create_index([("participants", 1), ("updated_at", -1)])
        # Notifications
        await db.notifications.create_index([("target_role", 1), ("created_at", -1)])
        await db.notifications.create_index("read_by")
        # Access / Residents
        await db.guest_requests.create_index([("location_id", 1), ("status", 1)])
        await db.access_logs.create_index([("location_id", 1), ("timestamp", -1)])
        await db.residents.create_index([("member_id", 1), ("status", 1)])
        await db.residents.create_index([("location_id", 1), ("status", 1)])
        # Files / Documents
        await db.files.create_index([("member_id", 1), ("is_deleted", 1)])
        # Auth
        await db.password_resets.create_index("token")
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
        await db.sessions.create_index("user_id")
        await db.sessions.create_index("jti", unique=True)
        await db.sessions.create_index("expires_at", expireAfterSeconds=0)
        # Financial
        await db.financial.create_index([("location_id", 1), ("date", -1)])
        await db.financial.create_index([("type", 1), ("date", -1)])
        # Locations
        await db.locations.create_index("id", unique=True)
        await db.locations.create_index([("parent_id", 1), ("type", 1)])
        # Push
        await db.push_subscriptions.create_index("user_id")
        await db.push_subscriptions.create_index("subscription.endpoint", unique=True)
        # Audit
        await db.audit_log.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_log.create_index("timestamp")
        # Wallet
        await db.wallet_badges.create_index("token", unique=True)
        await db.wallet_badges.create_index("member_id")
        # Deleted items (recycle bin) — TTL cleanup after 30 days
        await db.deleted_items.create_index("deleted_at", expireAfterSeconds=2592000)
        logger.info("Indexes ensured (idempotent)")
    except Exception as e:
        logger.warning(f"Index ensure: {e}")


async def _seed_initial_data():
    """Background-seed default admin, locations, notifications without blocking startup/readiness."""
    # Always ensure indexes (fast + idempotent)
    await _ensure_indexes()
    try:
        user_count = await db.users.count_documents({})
    except Exception as e:
        logger.warning(f"Seed skipped — DB not reachable yet: {e}")
        return
    if user_count == 0:
        logger.info("Seeding initial data...")
        admin = {"id": str(uuid.uuid4()), "name": "Admin User", "email": "admin@5812global.org", "phone": "+256 800 5812", "password_hash": hash_password("Admin@1234"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        admin2 = {"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            await db.users.insert_one(admin)
            await db.users.insert_one(admin2)
            logger.info("Admin users created")
        except Exception as e:
            logger.warning(f"Admin creation: {e}")
    try:
        uganda_admin = await db.users.find_one({"email": "admin@5812uganda.org"})
        if not uganda_admin:
            await db.users.insert_one({"id": str(uuid.uuid4()), "name": "Admin", "email": "admin@5812uganda.org", "phone": "+256 800 5813", "password_hash": hash_password("Admin@5812"), "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        logger.warning(f"Uganda admin seed: {e}")
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

    # Auto-promote silvester@lubwamas.org to system admin (non-fatal)
    try:
        silvester = await db.users.find_one({"email": "silvester@lubwamas.org"})
        if silvester:
            if silvester.get("role") != "admin":
                await db.users.update_one({"email": "silvester@lubwamas.org"}, {"$set": {"role": "admin"}})
                logger.info("Promoted silvester@lubwamas.org to admin")
        else:
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
    except Exception as e:
        logger.warning(f"Silvester seed: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
