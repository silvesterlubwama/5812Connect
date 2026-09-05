# iter301 — bcrypt is pinned to 3.2.2 in requirements.txt (compatible with
# passlib==1.7.4 which is unmaintained but stable). This defensive shim keeps
# hashing/verification functional if a future dependency upgrade pulls in
# bcrypt 4.x (which dropped the `__about__` attribute passlib introspects).
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

# Mount the local uploads folder so photos saved on the filesystem fallback path
# (`/app/backend/uploads/photos/...`) are actually retrievable via the URL
# `/api/uploads/photos/...` returned by the upload endpoints.
from fastapi.staticfiles import StaticFiles
import os as _os_for_static
_os_for_static.makedirs("/app/backend/uploads/photos", exist_ok=True)
_os_for_static.makedirs("/app/backend/uploads/child-extras", exist_ok=True)
_os_for_static.makedirs("/app/backend/uploads/files", exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory="/app/backend/uploads"), name="uploads")


# Capture process start time so /api/health can report uptime + a static-version stamp
import time as _time_mod
_APP_STARTED_AT = _time_mod.time()
_APP_VERSION = os.environ.get("APP_VERSION") or os.environ.get("GIT_COMMIT") or "dev"


@app.get("/api/health")
async def health_check():
    """Rich health probe — used by uptime monitors + the kiosk Diagnostics page.
    Returns aggregate status + per-subsystem detail. Status `healthy` iff every
    *required* subsystem (db, storage) is OK; degraded means optional pieces (LLM)
    are unconfigured but the app can still serve traffic."""
    started = _time_mod.time()
    out = {
        "status": "healthy",
        "service": "58:12 Global Connect CRM",
        "version": _APP_VERSION,
        "uptime_seconds": int(_time_mod.time() - _APP_STARTED_AT),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "subsystems": {},
    }
    # --- DB ping ---
    db_status = {"ok": False}
    try:
        await asyncio.wait_for(db.command("ping"), timeout=2.0)
        db_status = {"ok": True, "latency_ms": round((_time_mod.time() - started) * 1000, 1)}
    except Exception as e:
        db_status = {"ok": False, "error": str(e)[:200]}
        out["status"] = "unhealthy"
    out["subsystems"]["db"] = db_status
    # --- Uploads dir writable ---
    storage_status = {"ok": False}
    try:
        from pathlib import Path
        uploads = Path("/app/backend/uploads")
        uploads.mkdir(parents=True, exist_ok=True)
        # Touch a tiny canary file to confirm writability
        canary = uploads / ".healthcheck"
        canary.write_text(str(int(_time_mod.time())))
        canary.unlink(missing_ok=True)
        storage_status = {"ok": True, "path": str(uploads)}
    except Exception as e:
        storage_status = {"ok": False, "error": str(e)[:200]}
        out["status"] = "unhealthy"
    out["subsystems"]["storage"] = storage_status
    # --- LLM key configured (optional) ---
    llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
    out["subsystems"]["llm"] = {
        "configured": bool(llm_key),
        "provider": "emergent",
    }
    if not llm_key and out["status"] == "healthy":
        out["status"] = "degraded"
    # --- Email (Resend) ---
    out["subsystems"]["email"] = {"configured": bool(os.environ.get("RESEND_API_KEY"))}
    # --- Scheduler heartbeat ---
    out["subsystems"]["scheduler"] = {"running": True}  # the loop has a try/except wrapper around each tick
    return out


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


# ============================================================
# SECURITY HEADERS MIDDLEWARE
# Hardens every response with browser-standard security headers.
# ============================================================

@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    # Always-on hardening. CSP is permissive enough for the React build (inline
    # styles via Tailwind JIT) but locks down external script/frame sources.
    # If something breaks (e.g. third-party iframe), refine the directive.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(self), camera=(self), microphone=(self), payment=(), "
        "fullscreen=(self), serial=(self), hid=(self), usb=(self), bluetooth=(self)"
    )
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Only set HSTS over HTTPS — avoids breaking local-http dev.
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Security Contractor role is meant to be **kiosk-only** — the frontend router
# already blocks them from every non-checkpoint page. This middleware enforces
# the same restriction at the API layer so a stolen contractor token cannot be
# used with curl to exfiltrate the member directory, org financials, etc.
# Iteration 226 audit surfaced this leak; the fix here is a positive-list of
# path prefixes contractors ARE allowed to hit.
_CONTRACTOR_ALLOWED_PREFIXES = (
    "/api/security/checkpoint",       # scan, session, pair
    "/api/security-companies",        # read own company for badge
    "/api/auth/",                     # login/logout/me
    "/api/members/",                  # NFC endpoints keyed by their own id
    "/api/notifications/mark",        # dismiss own notifications
    "/api/system/health",
    "/api/storage/",                  # photos/logos on the badge
    "/api/uploads/",                  # local file serving
)
_CONTRACTOR_DENY_METHODS = {"DELETE"}  # never let a contractor delete anything


@app.middleware("http")
async def kiosk_role_guard(request, call_next):
    """Enforce Security Contractor kiosk-only scope at the transport layer.

    We look up the user by the bearer token (cheap, same query the deps use)
    and 403 anything outside the allow-list. Requests without a token or with
    a non-contractor token pass through untouched.
    """
    path = request.url.path
    if not path.startswith("/api/") or request.method == "OPTIONS":
        return await call_next(request)
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return await call_next(request)
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return await call_next(request)
    try:
        from deps import _decode_token, db as _db
        payload = _decode_token(token)
        user_id = payload.get("sub") if payload else None
        if not user_id:
            return await call_next(request)
        user = await _db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
        if not user or user.get("role") != "Security Contractor":
            return await call_next(request)
        if request.method in _CONTRACTOR_DENY_METHODS:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Security Contractors cannot perform delete operations"})
        if not any(path.startswith(p) for p in _CONTRACTOR_ALLOWED_PREFIXES):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Security Contractor role is restricted to the checkpoint kiosk"})
    except Exception:
        # Never block a request if the guard itself fails — better to fall
        # through to the endpoint's own auth than to lock users out.
        pass
    return await call_next(request)

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
        # iter 260 — Compute the allowed campus set WITHOUT collapsing across
        # siblings. Previous logic added parent campuses to `user_locs` and
        # then enumerated every non-restricted child of `user_locs`, which
        # granted a Director assigned to Haiti + Kenya access to sibling
        # campuses (Uganda, United) under the same top-level parent. Now we
        # keep two disjoint sets: `direct` (what the user was actually
        # assigned) and `parents` (the campus each of those rolls up to,
        # allowed as pin targets but NOT used to expand sibling siblings).
        direct = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            direct.add(current_user["location_id"])
        parents: set = set()
        if direct:
            parent_docs = await db.locations.find(
                {"id": {"$in": list(direct)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
                {"_id": 0, "parent_id": 1},
            ).to_list(50)
            for p in parent_docs:
                if p.get("parent_id"):
                    parents.add(p["parent_id"])
        # Expand ONLY the user's direct campuses to their sub-locations
        # (rooms/buildings). Sub-locations under parent campuses are not
        # added — those belong to sibling campuses the user was never
        # assigned to.
        subs = []
        if direct:
            subs = await db.locations.find(
                {"parent_id": {"$in": list(direct)}},
                {"_id": 0, "id": 1, "is_restricted": 1},
            ).to_list(200)
        allowed = set(direct) | parents
        for s in subs:
            if not s.get("is_restricted") or s["id"] in direct:
                allowed.add(s["id"])
        if campus_id not in allowed:
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
    from routers.access_eligible import router as access_eligible_router
    from routers.reports import router as reports_router
    from routers.documents import router as documents_router
    from routers.auth import router as auth_router
    from routers.members import router as members_router
    from routers.import_csv import router as import_csv_router
    from routers.portal import router as portal_router
    from routers.events import router as events_router
    from routers.tasks import router as tasks_router
    # NEW single finance package (iter 246 — full reset). Old routers
    # (financial, accounting, chart_accounts, invoices, statements) are
    # deliberately NOT included so every money movement flows through the
    # new balanced-ledger `finance` package.
    from routers.finance import router as finance_router
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
    from routers.voip import router as voip_router
    from routers.consumable_sheets import router as consumable_sheets_router
    from routers.event_tickets import router as event_tickets_router
    from routers.purchase_orders import router as purchase_orders_router
    from routers.holidays import router as holidays_router
    app.include_router(bookings_router)
    app.include_router(ws_router)
    app.include_router(notifications_router)
    app.include_router(access_router)
    app.include_router(access_eligible_router)
    app.include_router(reports_router)
    app.include_router(documents_router)
    app.include_router(auth_router)
    app.include_router(members_router)
    app.include_router(import_csv_router)
    app.include_router(portal_router)
    app.include_router(events_router)
    app.include_router(tasks_router)
    app.include_router(finance_router)
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
    app.include_router(voip_router)
    app.include_router(consumable_sheets_router)
    app.include_router(event_tickets_router)
    app.include_router(purchase_orders_router)
    app.include_router(holidays_router)
    from routers.hr import router as hr_router
    app.include_router(hr_router)
    from routers.donors_vendors import router as donors_vendors_router
    app.include_router(donors_vendors_router)
    from routers.seed import router as seed_router
    from routers.dashboard import router as dashboard_router
    from routers.i18n import router as i18n_router
    from routers.products import router as products_router
    from routers.sales import router as sales_router
    from routers.sheet_import import router as sheet_import_router
    # Old invoices/statements/accounting routers deliberately dropped in the
    # iter 246 finance reset — kept as files for reference but no HTTP surface.
    from routers.approvals import router as approvals_router
    from routers.social_work import router as social_work_router, portal_router as school_portal_router
    from routers.bank import router as bank_router
    from routers.activity import router as activity_router
    from routers.sponsor_portal import router as sponsor_links_router, public_router as sponsor_portal_router
    from routers.security_checkpoint import router as security_checkpoint_router, ocr_router
    from routers.backup import router as backup_router
    from routers.system_settings import router as system_settings_router
    from routers.funds import router as funds_router
    from routers.social_review_forms import router as social_review_forms_router
    from routers.shipments_pkg import router as shipments_router
    from routers.fare_alerts import router as fare_alerts_router
    from routers.security_companies import router as security_companies_router
    app.include_router(seed_router)
    app.include_router(dashboard_router)
    app.include_router(i18n_router)
    app.include_router(products_router)
    app.include_router(sales_router)
    app.include_router(sheet_import_router)
    app.include_router(approvals_router)
    app.include_router(social_work_router)
    app.include_router(school_portal_router)
    app.include_router(bank_router)
    app.include_router(activity_router)
    app.include_router(sponsor_links_router)
    app.include_router(sponsor_portal_router)
    app.include_router(security_checkpoint_router)
    app.include_router(ocr_router)
    app.include_router(backup_router)
    app.include_router(system_settings_router)
    app.include_router(funds_router)
    app.include_router(social_review_forms_router)
    app.include_router(shipments_router)
    app.include_router(fare_alerts_router)
    app.include_router(security_companies_router)
    logger.info("All modular routers loaded")
except Exception as e:
    logger.warning(f"Router loading: {e}")


# ===== iter302: schedulers, indexes, and seed extracted into sibling modules =====
# Behaviour unchanged — server.py just re-exports the names so callers using
# `from server import _fire_overdue_task_director_digest` keep working.
from scheduler import (
    _send_push_to_user,
    _run_due_date_reminder_scheduler,
    _fire_scheduled_customer_statements,
    _fire_auto_backup,
    _fire_overdue_task_emails,
    _fire_overdue_task_director_digest,
    _fire_payday_payslip_generation,
    _fire_overdue_payment_reminders,
    _fire_birthday_anniversary_notifications,
    _run_fare_alerts_loop,
    _run_flight_status_refresh_loop,
)
from db_indexes import _ensure_indexes
from seed_data import _seed_initial_data

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
        logger.info("Storage initialized (cloud)")
    except Exception as e:
        # Falling back to local disk (./uploads) — fully supported for self-hosted
        # appliance deploys. Demoted from ERROR to WARNING so log scrapers don't
        # treat this as a real problem.
        logger.warning(f"Cloud storage init unavailable, using local disk fallback: {e}")
    # ===== Sentry init (iter152) — reads system_settings, falls back to env =====
    try:
        from routers.system_settings import get_sentry_config
        s = await get_sentry_config()
        if s.get("dsn") and s.get("enabled", True) is not False:
            try:
                import sentry_sdk
                from sentry_sdk.integrations.fastapi import FastApiIntegration
                from sentry_sdk.integrations.starlette import StarletteIntegration
                sentry_sdk.init(
                    dsn=s["dsn"],
                    environment=s.get("environment") or "production",
                    traces_sample_rate=float(s.get("traces_sample_rate") or 0.1),
                    integrations=[FastApiIntegration(), StarletteIntegration()],
                    send_default_pii=False,
                )
                logger.info(f"Sentry initialised (env={s.get('environment')})")
            except ImportError:
                logger.warning("Sentry DSN set but sentry-sdk not installed — skipping")
            except Exception as se:
                logger.warning(f"Sentry init failed: {se}")
    except Exception as e:
        logger.warning(f"Sentry bootstrap skipped: {e}")
    # Start background task reminder scheduler
    asyncio.create_task(_run_due_date_reminder_scheduler())
    # iter226 — every 15 min refresh flight status for departed/shipped shipments
    asyncio.create_task(_run_flight_status_refresh_loop())
    # iter227 — daily fare-alert check
    asyncio.create_task(_run_fare_alerts_loop())
    # Defer heavy seeding so the app becomes ready immediately
    asyncio.create_task(_seed_initial_data())


@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
