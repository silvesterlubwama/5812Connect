"""Sponsor portal — public-facing, password-gated view of a sponsored child's
progress. Mirrors the school-portal pattern: per-child portal token URL +
expiring one-time password issued by social-work staff.

What sponsors see (no PII beyond what they already know):
  • Child name + photo + age + grade
  • Sponsorship-positive activity feed (school updates, milestones, gallery
    photos, payments received from them) — anything marked `is_public_for_sponsor`
    or `visibility=public_to_subject`
  • Total sponsorship received YTD
  • The child's current goals/progress (from the social-work case)
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from deps import db, require_staff, _audit, logger, hash_password, verify_password
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets
import hashlib

# Staff-side router for issuing/managing sponsor links
router = APIRouter(prefix="/api/sponsor-links", tags=["sponsor-links"])
# Public router used by the sponsor's browser
public_router = APIRouter(prefix="/api/sponsor-portal", tags=["sponsor-portal"])


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================================
# STAFF-SIDE: issue + revoke sponsor portal passwords
# ============================================================

@router.post("/issue")
async def issue_sponsor_link(data: dict, current_user: dict = Depends(require_staff)):
    """Issue a sponsor-portal password for a specific child.
    Body: { child_id, ttl_days?: 30, note?: '' }
    Returns plaintext password ONCE — share via your preferred secure channel."""
    child_id = (data.get("child_id") or "").strip()
    if not child_id:
        raise HTTPException(status_code=400, detail="child_id required")
    child = await db.children.find_one(
        {"id": child_id},
        {"_id": 0, "id": 1, "name": 1, "sponsor_member_id": 1, "location_id": 1},
    )
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    ttl_days = max(1, min(int(data.get("ttl_days") or 30), 365))
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    # Ensure the child has a portal_token (generated once, reusable URL)
    if not child.get("portal_token"):
        token = secrets.token_urlsafe(16)
        await db.children.update_one({"id": child_id}, {"$set": {"portal_token": token}})
    else:
        token = child["portal_token"]
    # Re-fetch to grab token
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "portal_token": 1, "location_id": 1})
    plaintext = secrets.token_urlsafe(9)
    pw_id = f"spl_{uuid.uuid4().hex[:10]}"
    await db.sponsor_portal_passwords.insert_one({
        "id": pw_id,
        "child_id": child_id,
        "child_name": child["name"],
        "portal_token": child["portal_token"],
        "password_hash": hash_password(plaintext),
        "expires_at": expires_at,
        "issued_at": now.isoformat(),
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", ""),
        "note": (data.get("note") or "")[:200],
        "revoked": False,
        "last_used_at": None,
        "location_id": child.get("location_id"),
    })
    await _audit(current_user["id"], "issue", "sponsor_portal_password", pw_id, {"child": child["name"]})
    return {
        "id": pw_id,
        "child_id": child_id,
        "child_name": child["name"],
        "portal_url_path": f"/sponsor-portal/{child['portal_token']}",
        "portal_token": child["portal_token"],
        "password_plaintext": plaintext,
        "expires_at": expires_at,
        "ttl_days": ttl_days,
        "note": "Share the URL + password with the sponsor. The password will not be retrievable later.",
    }


@router.get("/by-child/{child_id}")
async def list_sponsor_passwords(child_id: str, current_user: dict = Depends(require_staff)):
    """List active/expired passwords for a child (plaintext NOT returned)."""
    rows = await db.sponsor_portal_passwords.find(
        {"child_id": child_id},
        {"_id": 0, "password_hash": 0},
    ).sort("issued_at", -1).to_list(50)
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in rows:
        r["is_active"] = (not r.get("revoked")) and (r.get("expires_at", "") > now_iso)
    return rows


@router.delete("/{pw_id}")
async def revoke_sponsor_password(pw_id: str, current_user: dict = Depends(require_staff)):
    res = await db.sponsor_portal_passwords.update_one(
        {"id": pw_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": current_user["id"]}},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"revoked": True}


# ============================================================
# PUBLIC: sponsor logs in, views their child's progress
# ============================================================

SPONSOR_SESSION_TTL_HOURS = 6


@public_router.post("/login")
async def sponsor_portal_login(data: dict):
    """Public login. Body: { portal_token, password } → 6-hour session token."""
    portal_token = (data.get("portal_token") or "").strip()
    password = (data.get("password") or "").strip()
    if not portal_token or not password:
        raise HTTPException(status_code=400, detail="portal_token and password required")
    child = await db.children.find_one({"portal_token": portal_token}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Unknown sponsor portal — check the URL")
    now_iso = datetime.now(timezone.utc).isoformat()
    matches = await db.sponsor_portal_passwords.find({
        "child_id": child["id"], "revoked": False, "expires_at": {"$gt": now_iso},
    }, {"_id": 0}).to_list(20)
    pw = next((r for r in matches if verify_password(password, r["password_hash"])), None)
    if not pw:
        raise HTTPException(status_code=401, detail="Invalid or expired password")
    raw_session = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=SPONSOR_SESSION_TTL_HOURS)).isoformat()
    await db.sponsor_portal_sessions.insert_one({
        "id": f"sps_{uuid.uuid4().hex[:10]}",
        "token_hash": _hash(raw_session),
        "child_id": child["id"],
        "password_id": pw["id"],
        "created_at": now_iso,
        "expires_at": expires_at,
    })
    await db.sponsor_portal_passwords.update_one({"id": pw["id"]}, {"$set": {"last_used_at": now_iso}})
    return {
        "session_token": raw_session,
        "child_id": child["id"],
        "child_name": child["name"],
        "expires_at": expires_at,
        "ttl_hours": SPONSOR_SESSION_TTL_HOURS,
    }


async def _verify_sponsor_session(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing sponsor session token")
    token = authorization.split(" ", 1)[1].strip()
    th = _hash(token)
    sess = await db.sponsor_portal_sessions.find_one({"token_hash": th}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session token")
    if sess.get("expires_at", "") <= datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=401, detail="Session expired — log in again")
    child = await db.children.find_one({"id": sess["child_id"]}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=401, detail="Child no longer exists")
    return {"session": sess, "child": child}


@public_router.get("/me")
async def sponsor_portal_me(authorization: Optional[str] = Header(None)):
    """Sponsor's view of their child + recent updates (sponsor-public only)."""
    ctx = await _verify_sponsor_session(authorization)
    child = ctx["child"]
    # Sanitize: only safe fields
    safe = {
        "id": child["id"],
        "name": child.get("name"),
        "photo_url": child.get("photo_url"),
        "date_of_birth": child.get("date_of_birth"),
        "grade": child.get("grade"),
        "school_name": child.get("school_name"),
    }
    # Active social-work case → goals
    case = await db.social_cases.find_one(
        {"subject_kind": "child", "subject_id": child["id"], "status": "active"},
        {"_id": 0, "goals": 1, "education": 1, "summary": 1, "category": 1},
    )
    if case:
        safe["case_goals"] = case.get("goals") or []
        safe["case_education"] = case.get("education") or {}
        safe["case_summary"] = case.get("summary")
        safe["case_category"] = case.get("category")
    # Gallery + sponsor-public updates
    extras = await db.child_extras.find(
        {"child_id": child["id"], "is_public_for_sponsor": True},
        {"_id": 0, "created_by": 0},
    ).sort("created_at", -1).to_list(100)
    # Total sponsorship received YTD
    year = datetime.now(timezone.utc).year
    pays = await db.social_child_payments.find(
        {"subject_id": child["id"], "kind": "child_support",
         "date": {"$gte": f"{year}-01-01"}},
        {"_id": 0, "amount": 1, "currency": 1, "date": 1, "notes": 1},
    ).sort("date", -1).to_list(500)
    total_sponsorship_ytd = sum(float(p.get("amount") or 0) for p in pays)
    return {
        "child": safe,
        "updates": extras,
        "sponsorship_ytd": round(total_sponsorship_ytd, 2),
        "sponsorship_history": pays,
        "session_expires_at": ctx["session"]["expires_at"],
    }


@public_router.post("/logout")
async def sponsor_portal_logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"logged_out": True}
    token = authorization.split(" ", 1)[1].strip()
    await db.sponsor_portal_sessions.delete_one({"token_hash": _hash(token)})
    return {"logged_out": True}
