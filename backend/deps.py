"""Shared dependencies for all routers"""
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path
import os
import uuid
import logging

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
try:
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', '5812global')]
except Exception as e:
    logging.error(f"MongoDB connection error: {e}")
    client = None
    db = None

# Auth
SECRET_KEY = os.environ.get('SECRET_KEY', '5812global_secret_key_change_in_production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def _audit(user_id: str, action: str, resource: str, resource_id: str = None, details: dict = None):
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


# ---- RBAC HELPERS ----

ROLE_LEVELS = {
    "system_admin": 10, "admin": 10,
    "Executive Director": 9, "Director": 8,
    "Manager": 7, "Coordinator": 6,
    "Staff": 5, "Volunteer": 4,
    "Member": 3, "Parent": 2,
    "Customer": 1, "Guest": 1,
}

# Roles that bypass campus isolation (see everything)
SYSTEM_ADMIN_ROLES = {"admin", "system_admin", "executive director", "director"}

def get_role_level(role: str) -> int:
    return ROLE_LEVELS.get(role, 0)


def is_system_admin(user: dict) -> bool:
    """Returns True if user role grants cross-campus (global) visibility."""
    return (user.get("role") or "").lower() in SYSTEM_ADMIN_ROLES


def get_campus_filter(user: dict, field: str = "location_id") -> dict:
    """Return a MongoDB query fragment that restricts results to the user's campus.
    System admins get an empty dict (no restriction).
    Non-admin users without a location_id assigned also get no restriction
    (they'd see nothing if we filtered on an empty value)."""
    if is_system_admin(user):
        return {}
    loc = user.get("location_id")
    if not loc:
        return {}
    return {field: loc}


def require_role(min_level: int):
    """Dependency factory: raises 403 if user role < min_level"""
    async def checker(current_user: dict = Depends(get_current_user)):
        level = get_role_level(current_user.get("role", ""))
        if level < min_level:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return checker


# Convenience shortcuts
require_admin = require_role(10)      # system_admin, admin
require_director = require_role(8)    # Director+
require_manager = require_role(7)     # Manager+
require_coordinator = require_role(6) # Coordinator+
require_staff = require_role(5)       # Staff+


# ---- SHARED HELPERS ----

from fastapi import HTTPException as _HTTPException

def normalize_gender(value):
    if value is None or value == "":
        return None
    gender = value.lower()
    if gender not in ("male", "female"):
        raise _HTTPException(status_code=400, detail="Gender must be male or female")
    return gender


async def resolve_department(location_id, department):
    if not location_id:
        return department
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1, "type": 1, "departments": 1})
    if not loc:
        return department
    available = loc.get("departments") or []
    if department:
        if department in available:
            return department
        if loc.get("type") == "sub-location" and department == loc.get("name"):
            return department
        raise _HTTPException(status_code=400, detail="Department must match selected location")
    if loc.get("type") == "sub-location":
        return loc.get("name")
    return department
