"""Auth routes: register, login, me, logout, google-session, password reset"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, hash_password, verify_password, create_token, logger
from models import UserRegister, UserLogin
from datetime import datetime, timezone, timedelta
import uuid

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/register")
async def register(data: UserRegister):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    # Allow self-registration as visitor/parent with pending status
    role = getattr(data, 'role', None) or 'Guest'
    if role not in {'Guest', 'Member', 'visitor', 'parent'}:
        role = 'Guest'  # new signups start as guests, approved by director/manager
    expiry = None
    if role == 'visitor':
        # Visitors get 30-day access by default
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    user = {
        "id": user_id,
        "name": data.name,
        "email": data.email.lower(),
        "phone": getattr(data, 'phone', None),
        "national_id": getattr(data, 'national_id', None),
        "password_hash": hash_password(data.password),
        "role": role,
        "status": "pending",
        "expires_at": expiry,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = create_token(user_id)
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": token, "user": user_out}


@router.post("/auth/visitor-register")
async def visitor_register(data: dict):
    """Quick visitor/parent guest account creation — no password required, phone-based."""
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or f"visitor_{uuid.uuid4().hex[:8]}@kiosk.local").strip().lower()
    role = data.get("role", "visitor")
    if role not in {"visitor", "parent"}:
        role = "visitor"
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    existing = await db.users.find_one({"phone": phone}) if phone else None
    if existing:
        user_out = {k: v for k, v in existing.items() if k not in ("password_hash", "_id")}
        return {"token": None, "user": user_out, "existing": True}

    user_id = str(uuid.uuid4())
    pin = data.get("pin") or uuid.uuid4().hex[:4].upper()
    expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    user = {
        "id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "national_id": data.get("national_id"),
        "password_hash": hash_password(pin),
        "role": role,
        "status": "active",
        "guest_pin": pin,
        "expires_at": expiry,
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    # Also create a member record for check-in purposes
    member_id = str(uuid.uuid4())
    await db.members.insert_one({
        "id": member_id, "user_id": user_id, "name": name, "email": email,
        "phone": phone, "role": "member", "status": "active",
        "membership_type": role, "national_id": data.get("national_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": None, "user": user_out, "pin": pin, "member_id": member_id}


@router.post("/auth/login")
async def login(data: UserLogin):
    identifier = data.identifier.strip().lower()
    user = await db.users.find_one({
        "$or": [
            {"email": identifier},
            {"phone": identifier},
            {"national_id": data.identifier.strip()},
        ]
    })
    if not user or not verify_password(data.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Default active campus to user's primary location on every login
    user_loc = user.get("location_id", "")
    if user_loc and not user.get("active_campus_id"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"active_campus_id": user_loc}})
        user["active_campus_id"] = user_loc
    token = create_token(user["id"])
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": token, "user": user_out}


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    user_out = {k: v for k, v in current_user.items() if k not in ("password_hash", "_id")}
    # Enrich with location name for campus display
    if user_out.get("location_id"):
        loc = await db.locations.find_one({"id": user_out["location_id"]}, {"_id": 0, "name": 1})
        user_out["location_name"] = loc.get("name") if loc else ""
    return user_out


@router.post("/auth/logout")
async def logout():
    return {"message": "Logged out successfully"}


@router.post("/auth/google-session")
async def google_auth_session(data: dict):
    import httpx
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
                timeout=10.0,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google session")
        google_data = resp.json()
        email = google_data.get("email", "").lower()
        name = google_data.get("name", "")
        picture = google_data.get("picture", "")
        if not email:
            raise HTTPException(status_code=400, detail="No email from Google")
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing:
            user_id = existing["id"]
            if picture and not existing.get("picture"):
                await db.users.update_one({"id": user_id}, {"$set": {"picture": picture}})
        else:
            user_id = str(uuid.uuid4())
            new_user = {
                "id": user_id, "name": name, "email": email,
                "phone": None, "national_id": None,
                "password_hash": hash_password(str(uuid.uuid4())),
                "role": "volunteer", "status": "active", "picture": picture,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.users.insert_one(new_user)
        token = create_token(user_id)
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        return {"token": token, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail="Google authentication failed")


@router.post("/auth/forgot-password")
async def forgot_password(data: dict):
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "name": 1})
    if not user:
        return {"message": "If an account exists with that email, a reset link has been sent."}
    reset_token = str(uuid.uuid4())
    await db.password_resets.insert_one({
        "token": reset_token,
        "user_id": user["id"],
        "email": email,
        "used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    try:
        from routers.notifications import send_email
        await send_email(
            email,
            "58:12 Global — Password Reset",
            f"""<h2>Password Reset Request</h2>
            <p>Hi {user.get('name', '')},</p>
            <p>Use this code to reset your password: <strong>{reset_token[:8].upper()}</strong></p>
            <p>This code expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
            <p>— 58:12 Global Connect</p>"""
        )
    except Exception as e:
        logger.warning(f"Failed to send reset email: {e}")
    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password(data: dict):
    token = (data.get("token") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    reset = await db.password_resets.find_one({
        "used": False,
        "$or": [
            {"token": token},
            {"token": {"$regex": f"^{token.lower()[:8]}", "$options": "i"}}
        ]
    }, {"_id": 0})
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    if reset.get("expires_at") and reset["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=400, detail="Reset code has expired")
    await db.users.update_one(
        {"id": reset["user_id"]},
        {"$set": {"password_hash": hash_password(new_password)}}
    )
    await db.password_resets.update_one({"token": reset["token"]}, {"$set": {"used": True}})
    return {"message": "Password reset successfully. You can now login with your new password."}
