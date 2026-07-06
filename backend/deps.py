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
    jti = uuid.uuid4().hex
    return jwt.encode({"sub": user_id, "exp": expire, "jti": jti}, SECRET_KEY, algorithm=ALGORITHM)


async def create_token_with_session(user_id: str, request=None) -> str:
    """Create a JWT with a jti AND persist a session record for the user.
    Sessions power the 'active sessions / revoke other sessions' admin feature."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    jti = uuid.uuid4().hex
    token = jwt.encode({"sub": user_id, "exp": expire, "jti": jti}, SECRET_KEY, algorithm=ALGORITHM)
    ua, ip = "", ""
    try:
        if request is not None:
            ua = (request.headers.get("user-agent") or "")[:300]
            ip = (request.headers.get("x-forwarded-for") or request.client.host if request.client else "") or ""
            ip = ip.split(",")[0].strip()[:64]
    except Exception:
        pass
    try:
        await db.sessions.insert_one({
            "jti": jti,
            "user_id": user_id,
            "user_agent": ua,
            "ip": ip,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "expires_at": expire,
            "revoked": False,
        })
    except Exception as e:
        logger.warning(f"Session insert failed: {e}")
    return token


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        jti = payload.get("jti")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    # If this token has a jti, verify the session hasn't been revoked.
    # Tokens without jti (legacy) are still accepted.
    if jti:
        try:
            session = await db.sessions.find_one({"jti": jti}, {"_id": 0, "revoked": 1})
            if session and session.get("revoked"):
                raise HTTPException(status_code=401, detail="Session revoked")
        except HTTPException:
            raise
        except Exception:
            pass  # DB issue — don't block auth
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def _audit(user_id: str, action: str, resource: str, resource_id: str = None, details: dict = None):
    try:
        # Snapshot the user's name at the time of the action so older audit log
        # rows remain human-readable even if the user is later deleted/renamed.
        user_name = ""
        if user_id:
            try:
                u = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
                user_name = (u or {}).get("name", "") or ""
            except Exception:
                user_name = ""
        await db.audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
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
    "Executive Director": 9, "Adviser": 8.5, "Director": 8,
    "Manager": 7, "Leader": 6.5, "Coordinator": 6,
    "Staff": 5, "Volunteer": 4,
    # Security Contractor — private contractor who only mans the security checkpoint
    # kiosk. Sits between Member and Volunteer so they can't reach any privileged data.
    "Security Contractor": 3.5,
    "Member": 3, "Parent": 2,
    "Customer": 1, "Guest": 1,
}

# Roles that bypass campus isolation (see everything)
SYSTEM_ADMIN_ROLES = {"admin", "system_admin", "executive director"}

# Roles that get the campus switcher (global visibility + location switching)
CAMPUS_SWITCHER_ROLES = {"admin", "system_admin", "executive director", "adviser"}

def get_role_level(role: str) -> int:
    """Get numeric role level — case-insensitive lookup"""
    if not role:
        return 0
    # Try exact match first
    level = ROLE_LEVELS.get(role)
    if level is not None:
        return level
    # Try case-insensitive match
    role_lower = role.lower()
    for k, v in ROLE_LEVELS.items():
        if k.lower() == role_lower:
            return v
    return 0


def is_system_admin(user: dict) -> bool:
    """Returns True if user role grants cross-campus (global) visibility.
    Only admin, system_admin, and Executive Director have global access."""
    return (user.get("role") or "").lower() in SYSTEM_ADMIN_ROLES


def has_campus_switcher(user: dict) -> bool:
    """Returns True if user gets the campus location switcher (Admins, EDs, Advisers)."""
    return (user.get("role") or "").lower() in CAMPUS_SWITCHER_ROLES


# Roles that always have finance access (no explicit flag needed):
FINANCE_PRIVILEGED_ROLES = {
    "admin", "system_admin", "Executive Director", "Adviser",
    "Director",
    # Managers are NOT automatically privileged any more — they must be granted explicitly.
}

# Per user request (iter 134): only Director+ get automatic access to gated modules.
# Manager and below must be granted explicit, optionally time-limited access by an admin.
PRIVILEGED_ROLES = FINANCE_PRIVILEGED_ROLES

# Modules that follow the "appointment-only for non-Directors" access pattern.
# Each module stores explicit grants on the user as: {module}_access (bool) + {module}_access_expires_at (iso str).
GRANTABLE_MODULES = {
    "finance": "Finance (Donations, Expenses, P&L, Balance Sheet)",
    "hr": "HR & Payroll (Salaries, Payslips, Contracts, Leave, Attendance, Reimbursements)",
    "sales": "Sales Portal / Marketplace / Products / POS",
    "banking": "Banking (Bank accounts, Statements, Vendor bills, Recurring entries)",
    "accounting": "Accounting (Chart of Accounts, Journals, Ledger, Reports)",
    "social_work": "Social Work (Cases, Notes, Schools, Sponsor portal)",
    "restricted": "Restricted-location data (shelters, sensitive sub-campuses)",
}


def _grant_active(user: dict, module: str) -> bool:
    """Return True if the user has an active explicit grant for the module
    (the boolean flag is set AND the grant hasn't expired yet)."""
    if not user:
        return False
    if not user.get(f"{module}_access"):
        return False
    expires = user.get(f"{module}_access_expires_at")
    if expires:
        try:
            from datetime import datetime as _dt
            exp_dt = _dt.fromisoformat(str(expires).replace("Z", "+00:00"))
            now = _dt.now(timezone.utc)
            if exp_dt <= now:
                return False  # Expired
        except Exception:
            pass
    return True


def has_module_access(user: dict, module: str) -> bool:
    """Generic gate for any grantable module. Privileged roles (Director+) get
    automatic access; everyone else needs an explicit, optionally time-limited grant."""
    if not user:
        return False
    if module not in GRANTABLE_MODULES:
        return False
    role = (user.get("role") or "")
    if role in PRIVILEGED_ROLES:
        return True
    # Special-case HR: members of HR role / department have implicit HR access too,
    # to preserve the original HR workflow without admin grants.
    if module == "hr":
        if role in ("HR", "hr"):
            return True
        dept = (user.get("department") or "").lower()
        depts = [d.lower() for d in (user.get("departments") or [])]
        if "hr" in depts or "human resources" in depts or dept in ("hr", "human resources"):
            return True
    return _grant_active(user, module)


def has_finance_access(user: dict) -> bool:
    """Backwards-compatible alias kept for routers that import this directly."""
    return has_module_access(user, "finance")


async def require_finance_view(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: 403 unless user has finance view access."""
    if not has_finance_access(current_user):
        raise HTTPException(
            status_code=403,
            detail="Finance data is restricted. Ask an administrator to grant you finance access.",
        )
    return current_user


async def require_finance_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: 403 unless user is Director+ with finance access, OR has been
    granted explicit finance access. Used for WRITES that create/modify financial records."""
    if not has_finance_access(current_user):
        raise HTTPException(status_code=403, detail="Finance access required")
    role = current_user.get("role") or ""
    # Director+ always allowed; Manager and below need the explicit grant (which they
    # passed the has_finance_access() check with).
    if role in {"Director", "Adviser", "Executive Director", "admin", "system_admin"}:
        return current_user
    if _grant_active(current_user, "finance"):
        return current_user
    raise HTTPException(
        status_code=403,
        detail="This action requires Director access or an explicit finance grant",
    )


def require_module_view(module: str):
    """Factory: dependency that 403s unless the user has access to the named module."""
    async def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_module_access(current_user, module):
            raise HTTPException(
                status_code=403,
                detail=f"{GRANTABLE_MODULES.get(module, module)} is restricted. "
                       f"Ask an administrator to grant you {module} access.",
            )
        return current_user
    _dep.__name__ = f"require_{module}_view"
    return _dep


# Pre-built dependencies for the modules other than finance.
require_hr_view = require_module_view("hr")
require_sales_view = require_module_view("sales")
require_banking_view = require_module_view("banking")
require_accounting_view = require_module_view("accounting")
require_social_work_view = require_module_view("social_work")
require_restricted_view = require_module_view("restricted")


async def get_campus_filter(user: dict, field: str = "location_id") -> dict:
    """Return a MongoDB query fragment that restricts results to the user's campus.
    Only expands to actual sub-locations (rooms, buildings), NOT sibling campuses.
    System admins/EDs get an empty dict unless they have active_campus_id set.
    Restricted sub-locations are EXCLUDED for users not explicitly assigned to them."""
    user_loc_ids = set(user.get("location_ids") or [])
    if user.get("location_id"):
        user_loc_ids.add(user.get("location_id"))
    # If user is tagged in a sub-location, they also belong to the parent campus.
    # This ensures sub-location users have full campus-level access for features/settings.
    if user_loc_ids:
        parents = await db.locations.find(
            {"id": {"$in": list(user_loc_ids)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "parent_id": 1}
        ).to_list(50)
        for p in parents:
            if p.get("parent_id"):
                user_loc_ids.add(p["parent_id"])
    _is_admin = is_system_admin(user)
    # active_campus_id is honoured for:
    #  - system admins / EDs / Advisers (can pin to any campus via switcher)
    #  - Any user with multiple assigned campuses (they can narrow via the multi-campus switcher)
    active = user.get("active_campus_id")
    can_use_switcher = _is_admin or has_campus_switcher(user) or (
        active and active in user_loc_ids
    )
    if can_use_switcher and active:
        # Only include sub-locations (type=sub-location), not sibling campuses
        sub_locs = await db.locations.find(
            {"parent_id": active, "type": "sub-location"},
            {"_id": 0, "id": 1, "is_restricted": 1}
        ).to_list(200)
        # For non-system-admins, exclude restricted sub-locs unless explicitly assigned
        if _is_admin:
            allowed_subs = [s["id"] for s in sub_locs]
        else:
            allowed_subs = [s["id"] for s in sub_locs
                            if not s.get("is_restricted") or s["id"] in user_loc_ids]
        all_locs = [active] + allowed_subs
        if len(all_locs) == 1:
            return {"$or": [{field: active}, {"location_ids": active}]}
        return {"$or": [{field: {"$in": all_locs}}, {"location_ids": {"$in": all_locs}}]}
    if _is_admin:
        return {}
    locs = list(user_loc_ids)
    if not locs:
        return {}
    # Only expand to sub-locations; restricted sub-locs only if in user's location_ids
    sub_locs = await db.locations.find(
        {"parent_id": {"$in": locs}, "type": "sub-location"},
        {"_id": 0, "id": 1, "is_restricted": 1}
    ).to_list(200)
    expanded = list(locs)
    for s in sub_locs:
        if s.get("is_restricted") and s["id"] not in user_loc_ids:
            continue  # Skip restricted sub-locs not explicitly assigned
        expanded.append(s["id"])
    all_locs = list(set(expanded))
    if len(all_locs) == 1:
        return {"$or": [{field: all_locs[0]}, {"location_ids": all_locs[0]}]}
    return {"$or": [{field: {"$in": all_locs}}, {"location_ids": {"$in": all_locs}}]}


async def generate_title(role: str, location_ids: list, department: str = None) -> str:
    """Auto-generate a human-readable title like 'Director of 58:12 Uganda'."""
    if not role:
        return ""
    loc_names = []
    for lid in (location_ids or []):
        loc = await db.locations.find_one({"id": lid}, {"_id": 0, "name": 1})
        if loc:
            loc_names.append(loc["name"])
    dept_prefix = f"{department} " if department and department.lower() not in role.lower() else ""
    role_str = f"{dept_prefix}{role}"
    if not loc_names:
        return role_str
    if len(loc_names) == 1:
        return f"{role_str} of {loc_names[0]}"
    return f"{role_str} of {', '.join(loc_names[:-1])} & {loc_names[-1]}"


async def resolve_parent_campus(location_id: str) -> str:
    """If location_id is a sub-location, return its parent campus ID."""
    if not location_id:
        return location_id
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "type": 1, "parent_id": 1})
    if loc and loc.get("type") == "sub-location" and loc.get("parent_id"):
        return loc["parent_id"]
    return location_id


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
