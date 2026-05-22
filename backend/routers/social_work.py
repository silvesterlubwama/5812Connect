"""Social Work & Welfare module.

Tracks sponsored children, residents of restricted spaces, and members receiving
welfare support. Wires school-tuition / resource / medical payments into the
financial + accounting ledgers automatically (mirrors the donations/expenses
pattern). Exposes a campus-aware staff API and a separate password-gated school
portal so external teachers can upload report cards & notes.

Auth model
  • Staff-facing endpoints: require_staff and above; sensitive writes
    (issuing portal passwords, discharging a case) require Manager+.
  • School portal endpoints: public auth via a per-school portal-token URL +
    one-time password; returns a short-lived JWT-style portal token used for
    subsequent reads/writes from the external teacher.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from deps import (
    db, get_current_user, require_staff, require_manager, require_director,
    _audit, logger, get_campus_filter, is_system_admin, hash_password, verify_password,
)
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
import secrets
import hashlib

router = APIRouter(prefix="/api/social-work", tags=["social-work"])
portal_router = APIRouter(prefix="/api/school-portal", tags=["school-portal"])

CASE_CATEGORIES = {"sponsored", "restricted_location", "welfare_support", "multiple"}
CASE_STATUSES = {"active", "on_hold", "discharged"}
NOTE_KINDS = {"visit", "counseling", "safeguarding", "milestone", "school", "medical", "other"}
PAYMENT_KINDS = {"tuition", "resource", "medical", "child_support"}
RISK_LEVELS = {"low", "medium", "high"}


def _can_manage_social_work(user: dict) -> bool:
    """Manager+ OR explicit social_work role/department."""
    role = user.get("role", "")
    dept = (user.get("department") or "").lower()
    if is_system_admin(user) or role in {"admin", "Executive Director", "Adviser", "Director", "Manager"}:
        return True
    if role.lower() in {"social_work", "social worker", "welfare"}:
        return True
    if "social" in dept or "welfare" in dept:
        return True
    return False


async def _can_issue_portal_password(user: dict) -> bool:
    """Only social-work staff/manager/director can hand out school-portal passwords."""
    return _can_manage_social_work(user)


# ============================================================
# CASES
# ============================================================

@router.get("/cases")
async def list_cases(
    category: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    school_id: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Search cases. Scoped to user's campus."""
    query = {}
    if category and category in CASE_CATEGORIES:
        query["category"] = category
    if status and status in CASE_STATUSES:
        query["status"] = status
    if risk_level and risk_level in RISK_LEVELS:
        query["risk_level"] = risk_level
    if school_id:
        query["education.school_id"] = school_id
    if search:
        s = search.strip()
        query["$or"] = [
            {"subject_name": {"$regex": s, "$options": "i"}},
            {"summary": {"$regex": s, "$options": "i"}},
        ]
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    return await db.social_cases.find(query, {"_id": 0}).sort("opened_at", -1).to_list(500)


@router.post("/cases")
async def create_case(data: dict, current_user: dict = Depends(require_staff)):
    """Create a social-work case linked to a child OR member.
    Body: { subject_id, subject_kind ('child'|'member'), category, summary?, education?,
            medical?, family?, goals?, risk_level?, sponsor_member_id?, location_id? }"""
    subject_id = (data.get("subject_id") or "").strip()
    subject_kind = (data.get("subject_kind") or "child").strip().lower()
    category = (data.get("category") or "welfare_support").strip()
    if subject_kind not in {"child", "member"}:
        raise HTTPException(status_code=400, detail="subject_kind must be 'child' or 'member'")
    if category not in CASE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CASE_CATEGORIES)}")
    if not subject_id:
        raise HTTPException(status_code=400, detail="subject_id required")
    # Resolve subject snapshot
    if subject_kind == "child":
        subject = await db.children.find_one({"id": subject_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "photo_url": 1, "date_of_birth": 1})
    else:
        subject = await db.members.find_one({"id": subject_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "photo_url": 1, "date_of_birth": 1})
    if not subject:
        raise HTTPException(status_code=404, detail=f"{subject_kind} {subject_id} not found")
    # De-dup: don't open two active cases for the same subject
    existing = await db.social_cases.find_one({"subject_id": subject_id, "subject_kind": subject_kind, "status": "active"})
    if existing:
        raise HTTPException(status_code=400, detail="An active case already exists for this subject — re-open or edit it instead")
    case_id = f"sc_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": case_id,
        "subject_id": subject_id,
        "subject_kind": subject_kind,
        "subject_name": subject.get("name", ""),
        "subject_photo_url": subject.get("photo_url"),
        "subject_dob": subject.get("date_of_birth"),
        "category": category,
        "status": "active",
        "summary": (data.get("summary") or "")[:1000],
        "education": data.get("education") or {
            # { grade, school_id, school_name, enrollment_date, extracurricular: [str] }
        },
        "medical": data.get("medical") or {
            # { conditions: [], allergies: [], receives_medical_support: bool, primary_doctor, notes }
        },
        "family": data.get("family") or {
            # { guardians: [str], siblings: int, household_income, notes }
        },
        "goals": data.get("goals") or [],  # [{ goal, target_date, progress_pct, notes }]
        "risk_level": (data.get("risk_level") if data.get("risk_level") in RISK_LEVELS else "low"),
        "sponsor_member_id": data.get("sponsor_member_id"),
        "location_id": data.get("location_id") or subject.get("location_id") or current_user.get("active_campus_id"),
        "opened_at": now,
        "opened_by": current_user["id"],
        "opened_by_name": current_user.get("name", ""),
        "updated_at": now,
    }
    await db.social_cases.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "social_case", case_id, {"subject": subject.get("name"), "category": category})
    return doc


@router.get("/cases/{case_id}")
async def get_case(case_id: str, current_user: dict = Depends(require_staff)):
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # Attach computed aggregates
    case["payments_total"] = await _case_payments_summary(case_id)
    case["notes_count"] = await db.social_case_notes.count_documents({"case_id": case_id})
    return case


@router.put("/cases/{case_id}")
async def update_case(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"category", "status", "summary", "education", "medical", "family", "goals",
               "risk_level", "sponsor_member_id"}
    if "status" in data and data["status"] not in CASE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(CASE_STATUSES)}")
    if data.get("status") == "discharged" and not _can_manage_social_work(current_user):
        raise HTTPException(status_code=403, detail="Only social-work manager+ can discharge a case")
    if "risk_level" in data and data["risk_level"] not in RISK_LEVELS:
        raise HTTPException(status_code=400, detail=f"risk_level must be one of {sorted(RISK_LEVELS)}")
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    if data.get("status") == "discharged":
        update["discharged_at"] = update["updated_at"]
        update["discharged_by"] = current_user["id"]
        update["discharged_by_name"] = current_user.get("name", "")
    await db.social_cases.update_one({"id": case_id}, {"$set": update})
    await _audit(current_user["id"], "update", "social_case", case_id, {"fields": list(update.keys())})
    return await db.social_cases.find_one({"id": case_id}, {"_id": 0})


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str, current_user: dict = Depends(require_director)):
    """Hard delete — director only. Use status='discharged' to soft-close instead."""
    await db.social_cases.delete_one({"id": case_id})
    await db.social_case_notes.delete_many({"case_id": case_id})
    await db.social_child_payments.delete_many({"case_id": case_id})
    await _audit(current_user["id"], "delete", "social_case", case_id)
    return {"deleted": True}


# ============================================================
# CASE NOTES (chronological narrative)
# ============================================================

@router.get("/cases/{case_id}/notes")
async def list_notes(case_id: str, current_user: dict = Depends(require_staff)):
    return await db.social_case_notes.find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/cases/{case_id}/notes")
async def add_note(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    kind = (data.get("kind") or "other").strip().lower()
    if kind not in NOTE_KINDS:
        kind = "other"
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0, "id": 1, "subject_name": 1, "location_id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    note = {
        "id": f"scn_{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "kind": kind,
        "body": body[:5000],
        "attachments": data.get("attachments") or [],
        "tags": data.get("tags") or [],
        "is_confidential": bool(data.get("is_confidential", False)),
        "location_id": case.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.social_case_notes.insert_one(note)
    note.pop("_id", None)
    # Bump case updated_at
    await db.social_cases.update_one({"id": case_id}, {"$set": {"updated_at": note["created_at"]}})
    return note


@router.delete("/cases/{case_id}/notes/{note_id}")
async def delete_note(case_id: str, note_id: str, current_user: dict = Depends(require_staff)):
    note = await db.social_case_notes.find_one({"id": note_id, "case_id": case_id}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note["created_by"] != current_user["id"] and not _can_manage_social_work(current_user):
        raise HTTPException(status_code=403, detail="Only the author or a social-work manager can delete this note")
    await db.social_case_notes.delete_one({"id": note_id})
    return {"deleted": True}


# ============================================================
# SCHOOLS
# ============================================================

@router.get("/schools")
async def list_schools(current_user: dict = Depends(require_staff)):
    scope = await get_campus_filter(current_user)
    query = {**scope} if scope else {}
    schools = await db.social_schools.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    # Attach a student count per school
    for s in schools:
        s["student_count"] = await db.social_cases.count_documents({
            "education.school_id": s["id"], "status": "active"
        })
    return schools


@router.post("/schools")
async def create_school(data: dict, current_user: dict = Depends(require_staff)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    # De-dup by name+location
    loc = data.get("location_id") or current_user.get("active_campus_id")
    existing = await db.social_schools.find_one({"name": name, "location_id": loc})
    if existing:
        raise HTTPException(status_code=400, detail=f"School '{name}' already exists for this campus")
    school_id = f"sch_{uuid.uuid4().hex[:10]}"
    portal_token = secrets.token_urlsafe(16)  # used in the public URL — opaque
    doc = {
        "id": school_id,
        "name": name[:200],
        "address": (data.get("address") or "")[:300],
        "country": (data.get("country") or "")[:60],
        "phone": (data.get("phone") or "")[:40],
        "email": (data.get("email") or "")[:120],
        "head_teacher": (data.get("head_teacher") or "")[:120],
        "notes": (data.get("notes") or "")[:1000],
        "portal_token": portal_token,
        "location_id": loc,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.social_schools.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/schools/{school_id}")
async def update_school(school_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "address", "country", "phone", "email", "head_teacher", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.social_schools.update_one({"id": school_id}, {"$set": update})
    return await db.social_schools.find_one({"id": school_id}, {"_id": 0})


@router.delete("/schools/{school_id}")
async def delete_school(school_id: str, current_user: dict = Depends(require_director)):
    in_use = await db.social_cases.count_documents({"education.school_id": school_id, "status": "active"})
    if in_use > 0:
        raise HTTPException(status_code=400, detail=f"School is referenced by {in_use} active case(s) — reassign first")
    await db.social_schools.delete_one({"id": school_id})
    await db.social_school_portal_passwords.delete_many({"school_id": school_id})
    return {"deleted": True}


# ---------- SCHOOL PORTAL PASSWORDS ----------

@router.post("/schools/{school_id}/portal-passwords")
async def issue_school_portal_password(school_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Issue a one-time portal password (7-day expiry by default).
    Returned plaintext can be shown to the social worker ONCE — store hash only.
    Body: { ttl_days?, note? }"""
    if not await _can_issue_portal_password(current_user):
        raise HTTPException(status_code=403, detail="Only social-work staff/manager/director can issue portal passwords")
    school = await db.social_schools.find_one({"id": school_id}, {"_id": 0, "id": 1, "name": 1, "portal_token": 1})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    data = data or {}
    ttl_days = max(1, min(int(data.get("ttl_days") or 7), 30))
    plaintext = secrets.token_urlsafe(9)  # ~12-char alphanumeric token, easy to share
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    pw_id = f"spw_{uuid.uuid4().hex[:10]}"
    await db.social_school_portal_passwords.insert_one({
        "id": pw_id,
        "school_id": school_id,
        "password_hash": hash_password(plaintext),
        "expires_at": expires_at,
        "issued_at": now.isoformat(),
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", ""),
        "note": (data.get("note") or "")[:200],
        "revoked": False,
        "last_used_at": None,
        "last_used_ip": None,
    })
    await _audit(current_user["id"], "issue", "school_portal_password", pw_id, {"school": school["name"]})
    return {
        "id": pw_id,
        "school_id": school_id,
        "school_name": school["name"],
        "portal_url_path": f"/school-portal/{school['portal_token']}",
        "portal_token": school["portal_token"],
        "password_plaintext": plaintext,  # ONLY returned here — never stored
        "expires_at": expires_at,
        "ttl_days": ttl_days,
        "note": "Share this URL + password with the school. Both are required to log in. Password expires on the date shown.",
    }


@router.get("/schools/{school_id}/portal-passwords")
async def list_school_portal_passwords(school_id: str, current_user: dict = Depends(require_staff)):
    """List active+expired passwords for a school — does NOT return plaintext."""
    rows = await db.social_school_portal_passwords.find(
        {"school_id": school_id},
        {"_id": 0, "password_hash": 0},
    ).sort("issued_at", -1).to_list(50)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        r["is_active"] = (not r.get("revoked")) and (r.get("expires_at", "") > now)
    return rows


@router.delete("/schools/{school_id}/portal-passwords/{pw_id}")
async def revoke_school_portal_password(school_id: str, pw_id: str, current_user: dict = Depends(require_staff)):
    if not await _can_issue_portal_password(current_user):
        raise HTTPException(status_code=403, detail="Only social-work staff/manager/director can revoke portal passwords")
    await db.social_school_portal_passwords.update_one(
        {"id": pw_id, "school_id": school_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": current_user["id"]}},
    )
    return {"revoked": True}


# ============================================================
# CHILD PAYMENTS — wired to financials + accounting
# ============================================================

async def _case_payments_summary(case_id: str) -> dict:
    """Total payments per kind for a case."""
    out = {"tuition": 0.0, "resource": 0.0, "medical": 0.0, "child_support_received": 0.0}
    async for p in db.social_child_payments.find({"case_id": case_id}, {"_id": 0}):
        amt = float(p.get("amount") or 0)
        kind = p.get("kind")
        if kind == "child_support":
            out["child_support_received"] += amt
        elif kind in out:
            out[kind] += amt
    # Round to 2dp
    return {k: round(v, 2) for k, v in out.items()}


@router.get("/cases/{case_id}/payments")
async def list_case_payments(case_id: str, current_user: dict = Depends(require_staff)):
    return await db.social_child_payments.find({"case_id": case_id}, {"_id": 0}).sort("date", -1).to_list(500)


@router.post("/cases/{case_id}/payments")
async def add_case_payment(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Record a payment FOR or FROM a child case.
    Body: { kind ('tuition'|'resource'|'medical'|'child_support'), amount, currency?, date?,
            paid_to (school/clinic/etc), notes?, source ('sponsor'|'org_fund'|'partner'|'other') }
    Side effects:
      • Mirror to financial.donations (child_support) or financial.expenses (tuition/resource/medical)
      • Auto-post a balanced journal entry to accounting (via the same helper sales/donations use)."""
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    kind = (data.get("kind") or "").strip().lower()
    if kind not in PAYMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(PAYMENT_KINDS)}")
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be numeric")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    pay_id = f"scp_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    payment = {
        "id": pay_id,
        "case_id": case_id,
        "subject_id": case.get("subject_id"),
        "subject_name": case.get("subject_name"),
        "kind": kind,
        "direction": "in" if kind == "child_support" else "out",
        "amount": amount,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "date": (data.get("date") or now_iso)[:10],
        "paid_to": (data.get("paid_to") or "")[:200],
        "source": (data.get("source") or "org_fund")[:60],
        "notes": (data.get("notes") or "")[:500],
        "location_id": case.get("location_id"),
        "created_at": now_iso,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    # Mirror into the existing financial collections so the Finance page shows it too.
    try:
        if kind == "child_support":
            mirror = {
                "id": f"don_{uuid.uuid4().hex[:8]}",
                "donor_name": data.get("source_name") or "Child Sponsor",
                "amount": amount,
                "currency": payment["currency"],
                "type": "sponsorship",
                "date": payment["date"],
                "notes": f"Sponsorship for {case.get('subject_name')} [{case_id}]: {payment.get('notes','')}".strip(),
                "location_id": payment["location_id"],
                "created_at": now_iso,
                "created_by": current_user["id"],
                "entered_by": current_user.get("name", ""),
                "social_case_id": case_id,
                "social_payment_id": pay_id,
            }
            await db.donations.insert_one(mirror)
            payment["mirror_id"] = mirror["id"]
            payment["mirror_collection"] = "donations"
        else:
            category_map = {"tuition": "education", "resource": "supplies", "medical": "medical"}
            mirror = {
                "id": f"exp_{uuid.uuid4().hex[:8]}",
                "title": f"{kind.title()} for {case.get('subject_name')}",
                "amount": amount,
                "currency": payment["currency"],
                "category": category_map.get(kind, "general"),
                "date": payment["date"],
                "notes": (payment.get("notes") or "") + f" [case: {case_id}]",
                "location_id": payment["location_id"],
                "status": "approved",  # social-work-recorded payments are post-fact, not pending
                "approved_by": current_user["id"],
                "approved_by_name": current_user.get("name", ""),
                "approved_at": now_iso,
                "created_at": now_iso,
                "created_by": current_user["id"],
                "entered_by": current_user.get("name", ""),
                "social_case_id": case_id,
                "social_payment_id": pay_id,
            }
            await db.expenses.insert_one(mirror)
            payment["mirror_id"] = mirror["id"]
            payment["mirror_collection"] = "expenses"
        # Re-use the financial→accounting auto-post helper if the location has a CoA.
        try:
            from routers.financial import _post_to_accounting
            await _post_to_accounting(
                "donation" if kind == "child_support" else "expense_approved",
                mirror,
                current_user,
            )
        except Exception as e:
            logger.warning(f"Social-work payment ledger auto-post skipped: {e}")
    except Exception as e:
        logger.error(f"Social-work payment mirror failed: {e}")
    await db.social_child_payments.insert_one(payment)
    payment.pop("_id", None)
    await _audit(current_user["id"], "create", "social_payment", pay_id, {"case": case_id, "kind": kind, "amount": amount})
    return payment


@router.delete("/cases/{case_id}/payments/{payment_id}")
async def delete_case_payment(case_id: str, payment_id: str, current_user: dict = Depends(require_manager)):
    """Delete a payment + its mirrored finance entry. Manager+ only (audit-critical)."""
    p = await db.social_child_payments.find_one({"id": payment_id, "case_id": case_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.get("mirror_collection") == "donations" and p.get("mirror_id"):
        await db.donations.delete_one({"id": p["mirror_id"]})
    elif p.get("mirror_collection") == "expenses" and p.get("mirror_id"):
        await db.expenses.delete_one({"id": p["mirror_id"]})
    # Note: we don't auto-reverse the journal entry — leave it for the books.
    # A finance admin can post a reversal manually via /accounting/entries/{id}/reverse.
    await db.social_child_payments.delete_one({"id": payment_id})
    await _audit(current_user["id"], "delete", "social_payment", payment_id, {"reason": "user-initiated"})
    return {"deleted": True, "ledger_reversal_required": True}


@router.get("/payments/summary")
async def payments_summary(period: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """Org-wide payments overview (YYYY-MM, defaults to current month)."""
    period = period or datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{period}-01"
    y, m = map(int, period.split("-"))
    nm_y, nm_m = (y, m + 1) if m < 12 else (y + 1, 1)
    end = f"{nm_y:04d}-{nm_m:02d}-01"
    query = {"date": {"$gte": start, "$lt": end}}
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    rows = await db.social_child_payments.find(query, {"_id": 0}).to_list(2000)
    by_kind: dict = {}
    by_subject: dict = {}
    for r in rows:
        kind = r.get("kind", "")
        by_kind[kind] = by_kind.get(kind, 0) + float(r.get("amount") or 0)
        subj = r.get("subject_id") or ""
        if subj:
            d = by_subject.setdefault(subj, {"subject_name": r.get("subject_name"), "total": 0, "count": 0})
            d["total"] += float(r.get("amount") or 0)
            d["count"] += 1
    return {
        "period": period,
        "by_kind": by_kind,
        "by_subject": list(by_subject.values()),
        "total_out": sum(v for k, v in by_kind.items() if k != "child_support"),
        "total_in": by_kind.get("child_support", 0),
        "count": len(rows),
    }


# ============================================================
# PUBLIC SCHOOL PORTAL — separate auth (token + password)
# ============================================================

PORTAL_SESSION_TTL_HOURS = 6


def _hash_session_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@portal_router.post("/login")
async def school_portal_login(data: dict):
    """Public login for an external school user.
    Body: { portal_token, password }
    Returns: { session_token, school_id, school_name, expires_at } — store the session_token
    client-side and pass via Authorization: Bearer header for subsequent calls."""
    portal_token = (data.get("portal_token") or "").strip()
    password = (data.get("password") or "").strip()
    if not portal_token or not password:
        raise HTTPException(status_code=400, detail="portal_token and password required")
    school = await db.social_schools.find_one({"portal_token": portal_token}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="Unknown school portal — check the URL")
    now_iso = datetime.now(timezone.utc).isoformat()
    # Find a non-revoked, non-expired password whose hash matches
    matches = await db.social_school_portal_passwords.find({
        "school_id": school["id"],
        "revoked": False,
        "expires_at": {"$gt": now_iso},
    }, {"_id": 0}).to_list(20)
    pw_row = next((r for r in matches if verify_password(password, r["password_hash"])), None)
    if not pw_row:
        raise HTTPException(status_code=401, detail="Invalid or expired password")
    # Create a short-lived session token
    raw_session = secrets.token_urlsafe(32)
    session_id = f"sps_{uuid.uuid4().hex[:10]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=PORTAL_SESSION_TTL_HOURS)).isoformat()
    await db.social_school_portal_sessions.insert_one({
        "id": session_id,
        "token_hash": _hash_session_token(raw_session),
        "school_id": school["id"],
        "password_id": pw_row["id"],
        "created_at": now_iso,
        "expires_at": expires_at,
    })
    # Update last-used on the password
    await db.social_school_portal_passwords.update_one(
        {"id": pw_row["id"]},
        {"$set": {"last_used_at": now_iso}},
    )
    return {
        "session_token": raw_session,
        "school_id": school["id"],
        "school_name": school["name"],
        "expires_at": expires_at,
        "ttl_hours": PORTAL_SESSION_TTL_HOURS,
    }


async def _verify_portal_session(authorization: Optional[str]) -> dict:
    """Resolve a school-portal session from the Authorization header.
    Returns the session row + school. Raises 401 on any failure."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing portal session token")
    token = authorization.split(" ", 1)[1].strip()
    th = _hash_session_token(token)
    sess = await db.social_school_portal_sessions.find_one({"token_hash": th}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid portal session token")
    now_iso = datetime.now(timezone.utc).isoformat()
    if sess.get("expires_at", "") <= now_iso:
        raise HTTPException(status_code=401, detail="Portal session expired — log in again")
    school = await db.social_schools.find_one({"id": sess["school_id"]}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=401, detail="School no longer exists")
    return {"session": sess, "school": school}


@portal_router.get("/me")
async def school_portal_me(authorization: Optional[str] = Header(None)):
    """Return the school + its active students for the logged-in school user."""
    ctx = await _verify_portal_session(authorization)
    school = ctx["school"]
    # Active cases at this school
    cases = await db.social_cases.find(
        {"education.school_id": school["id"], "status": "active"},
        {"_id": 0, "id": 1, "subject_id": 1, "subject_name": 1, "subject_photo_url": 1,
         "subject_dob": 1, "category": 1, "education": 1, "risk_level": 1},
    ).sort("subject_name", 1).to_list(500)
    return {
        "school": {
            "id": school["id"],
            "name": school["name"],
            "head_teacher": school.get("head_teacher", ""),
        },
        "students": cases,
        "session_expires_at": ctx["session"]["expires_at"],
    }


@portal_router.get("/students/{case_id}")
async def school_portal_student(case_id: str, authorization: Optional[str] = Header(None)):
    """Detail view (limited) of one student for the school user — includes prior notes."""
    ctx = await _verify_portal_session(authorization)
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case or case.get("education", {}).get("school_id") != ctx["school"]["id"]:
        raise HTTPException(status_code=404, detail="Student not at your school")
    # Strip confidential / private fields before sending out
    safe_case = {
        "id": case["id"],
        "subject_id": case.get("subject_id"),
        "subject_name": case.get("subject_name"),
        "subject_photo_url": case.get("subject_photo_url"),
        "subject_dob": case.get("subject_dob"),
        "category": case.get("category"),
        "education": case.get("education"),
        # Limited medical (just allergies + receives_support) — no diagnoses
        "medical_summary": {
            "allergies": (case.get("medical") or {}).get("allergies") or [],
            "receives_medical_support": (case.get("medical") or {}).get("receives_medical_support") or False,
        },
    }
    # Notes from the school (kind in {school, milestone}) OR uploaded via this portal
    notes = await db.social_case_notes.find(
        {"case_id": case_id, "kind": {"$in": ["school", "milestone"]}, "is_confidential": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"student": safe_case, "notes": notes}


@portal_router.post("/students/{case_id}/notes")
async def school_portal_add_note(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """External school staff can upload a report card / note / incident.
    Body: { kind ('school'|'medical'|'other'), body, attachments?: [{name, url}] }"""
    ctx = await _verify_portal_session(authorization)
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0, "id": 1, "education": 1, "location_id": 1, "subject_name": 1})
    if not case or case.get("education", {}).get("school_id") != ctx["school"]["id"]:
        raise HTTPException(status_code=404, detail="Student not at your school")
    kind = (data.get("kind") or "school").strip().lower()
    if kind not in {"school", "medical", "other"}:
        kind = "school"
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now_iso = datetime.now(timezone.utc).isoformat()
    note = {
        "id": f"scn_{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "kind": kind,
        "body": body[:5000],
        "attachments": data.get("attachments") or [],
        "tags": ["school-portal-upload"],
        "is_confidential": False,
        "location_id": case.get("location_id"),
        "source": "school_portal",
        "school_id": ctx["school"]["id"],
        "school_name": ctx["school"]["name"],
        "created_at": now_iso,
        "created_by": f"school_portal:{ctx['school']['id']}",
        "created_by_name": ctx["school"]["name"] + " (external)",
    }
    await db.social_case_notes.insert_one(note)
    note.pop("_id", None)
    await db.social_cases.update_one({"id": case_id}, {"$set": {"updated_at": now_iso}})
    return note


@portal_router.post("/logout")
async def school_portal_logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"logged_out": True}
    token = authorization.split(" ", 1)[1].strip()
    await db.social_school_portal_sessions.delete_one({"token_hash": _hash_session_token(token)})
    return {"logged_out": True}
