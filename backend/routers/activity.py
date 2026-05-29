"""Universal activity trail.

A single `activity_log` collection accumulates every meaningful action that
concerns a member, child, staff, or customer — across finance, sales, social
work, access, payroll, events, attendance, etc.

Each module instruments its writes via the `log_activity()` helper below.
The Profile Activity tab fetches `/api/activity/{subject_kind}/{subject_id}`
and renders a chronological feed. Profiles can also be downloaded as JSON for
compliance / authority requests.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from deps import db, get_current_user, require_staff, logger
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

router = APIRouter(prefix="/api/activity", tags=["activity"])

SUBJECT_KINDS = {"member", "child", "staff", "user", "customer", "guest"}
ACTIVITY_CATEGORIES = {
    "sale", "payment", "donation", "expense", "bill", "bill_payment",
    "social_case", "social_note", "social_payment",
    "checkin", "access", "event",
    "payslip", "salary", "leave", "reimbursement", "attendance",
    "document", "photo", "badge", "report",
    "note", "system", "other",
}


async def log_activity(
    subject_kind: str,
    subject_id: str,
    category: str,
    title: str,
    body: str = "",
    *,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    ref_id: Optional[str] = None,  # the source record's id (e.g. sale_id, payment_id)
    ref_kind: Optional[str] = None,  # 'sale' | 'payment' | etc — drives deep-link
    location_id: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    visibility: str = "internal",  # 'internal' | 'public_to_subject' | 'authorities_only'
) -> Dict[str, Any]:
    """Append an activity-log row. Best-effort; never raises so callers can wrap in try."""
    if not subject_kind or not subject_id:
        return {}
    if subject_kind not in SUBJECT_KINDS:
        subject_kind = "other"
    if category not in ACTIVITY_CATEGORIES:
        category = "other"
    doc = {
        "id": f"act_{uuid.uuid4().hex[:10]}",
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "category": category,
        "title": (title or "")[:200],
        "body": (body or "")[:2000],
        "actor_id": actor_id,
        "actor_name": actor_name,
        "amount": amount,
        "currency": currency,
        "ref_id": ref_id,
        "ref_kind": ref_kind,
        "location_id": location_id,
        "attachments": attachments or [],
        "visibility": visibility if visibility in {"internal", "public_to_subject", "authorities_only"} else "internal",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.activity_log.insert_one(doc)
        doc.pop("_id", None)
        return doc
    except Exception as e:
        logger.warning(f"activity log insert failed: {e}")
        return {}


@router.get("/{subject_kind}/{subject_id}")
async def get_subject_activity(
    subject_kind: str,
    subject_id: str,
    category: Optional[str] = None,
    limit: int = 200,
    current_user: dict = Depends(require_staff),
):
    """Return chronological activity for a subject. Newest first.
    Merges the curated `activity_log` with on-the-fly records from related collections
    (checkins, sales, payments, social-work) so historical data shows without
    requiring retroactive instrumentation."""
    query = {"subject_kind": subject_kind, "subject_id": subject_id}
    if category:
        query["category"] = category
    rows = await db.activity_log.find(query, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 2000))

    # ---- Live merge from related collections ----
    extra = []
    # Check-ins (members + children)
    if subject_kind in {"member", "child", "guest", "user", "staff"}:
        async for c in db.checkins.find({"member_id": subject_id}, {"_id": 0}).sort("check_in_time", -1).limit(100):
            extra.append({
                "id": f"derived:{c['id']}",
                "subject_kind": subject_kind, "subject_id": subject_id,
                "category": "checkin",
                "title": f"Checked in to {c.get('event_name') or c.get('event_id') or 'kiosk'}",
                "body": f"Method: {c.get('method', '?')} · Type: {c.get('type', '?')}",
                "actor_name": c.get("checked_in_by") or "kiosk",
                "ref_id": c["id"], "ref_kind": "checkin",
                "location_id": c.get("location_id"),
                "created_at": c.get("check_in_time"),
                "derived": True,
            })
    # Customer sales
    if subject_kind == "customer":
        async for s in db.sales.find({"customer_id": subject_id}, {"_id": 0}).sort("created_at", -1).limit(100):
            extra.append({
                "id": f"derived:{s['id']}",
                "subject_kind": "customer", "subject_id": subject_id,
                "category": "sale",
                "title": f"Sale {s.get('receipt_number') or s['id']}",
                "body": f"{len(s.get('items', []) or [])} item(s) · {s.get('payment_method', '?')}",
                "amount": s.get("total"), "currency": s.get("currency"),
                "ref_id": s["id"], "ref_kind": "sale",
                "location_id": s.get("location_id"),
                "created_at": s.get("created_at"),
                "derived": True,
            })
    # Social-work payments + case notes for children
    if subject_kind == "child":
        async for p in db.social_child_payments.find({"subject_id": subject_id}, {"_id": 0}).sort("created_at", -1).limit(100):
            extra.append({
                "id": f"derived:{p['id']}",
                "subject_kind": "child", "subject_id": subject_id,
                "category": "social_payment",
                "title": f"{p.get('kind', '?').replace('_', ' ').title()}: {p.get('currency', 'UGX')} {float(p.get('amount') or 0):,.2f}",
                "body": p.get("notes", ""),
                "amount": p.get("amount"), "currency": p.get("currency"),
                "actor_name": p.get("created_by_name"),
                "ref_id": p["id"], "ref_kind": "social_payment",
                "location_id": p.get("location_id"),
                "created_at": p.get("created_at"),
                "derived": True,
            })
        # Case notes (only non-confidential)
        case = await db.social_cases.find_one({"subject_kind": "child", "subject_id": subject_id, "status": "active"}, {"_id": 0, "id": 1})
        if case:
            async for n in db.social_case_notes.find({"case_id": case["id"], "is_confidential": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(100):
                extra.append({
                    "id": f"derived:{n['id']}",
                    "subject_kind": "child", "subject_id": subject_id,
                    "category": "social_note",
                    "title": f"Case note: {n.get('kind', 'note')}",
                    "body": n.get("body", ""),
                    "actor_name": n.get("created_by_name"),
                    "ref_id": n["id"], "ref_kind": "case_note",
                    "location_id": n.get("location_id"),
                    "created_at": n.get("created_at"),
                    "attachments": n.get("attachments", []),
                    "derived": True,
                })
    # HR Reimbursements + Attendance for staff/user/member
    if subject_kind in {"member", "staff", "user"}:
        async for e in db.hr_employee_expenses.find({"staff_id": subject_id}, {"_id": 0}).sort("created_at", -1).limit(50):
            extra.append({
                "id": f"derived:{e['id']}",
                "subject_kind": subject_kind, "subject_id": subject_id,
                "category": "reimbursement",
                "title": f"Reimbursement: {e.get('title', '')}",
                "body": f"{e.get('category', '?')} · {e.get('status', 'pending')}",
                "amount": e.get("amount"), "currency": e.get("currency"),
                "actor_name": e.get("staff_name"),
                "ref_id": e["id"], "ref_kind": "reimbursement",
                "location_id": e.get("location_id"),
                "created_at": e.get("created_at"),
                "derived": True,
            })
        async for a in db.hr_attendance.find({"staff_id": subject_id}, {"_id": 0}).sort("check_in_time", -1).limit(30):
            extra.append({
                "id": f"derived:{a['id']}",
                "subject_kind": subject_kind, "subject_id": subject_id,
                "category": "attendance",
                "title": f"Worked {round((a.get('duration_minutes') or 0) / 60, 1)}h" if a.get("check_out_time") else "Clocked in",
                "body": a.get("notes", ""),
                "actor_name": a.get("staff_name"),
                "ref_id": a["id"], "ref_kind": "attendance",
                "location_id": a.get("location_id"),
                "created_at": a.get("check_in_time"),
                "derived": True,
            })
    # Optional category filter applies to merged too
    if category:
        extra = [e for e in extra if e.get("category") == category]
    # Merge + sort + cap
    combined = (rows or []) + extra
    combined.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return combined[: min(limit, 2000)]


@router.post("/{subject_kind}/{subject_id}/note")
async def add_subject_note(
    subject_kind: str,
    subject_id: str,
    file: UploadFile = File(None),
    body: str = Form(""),
    visibility: str = Form("internal"),
    current_user: dict = Depends(require_staff),
):
    """Anyone (volunteer+) can add a note or attach a file to a subject's activity feed.
    Used during events ('Saw Alice playing with the new puppets today.'), home visits, etc."""
    body = (body or "").strip()
    if not body and not (file and file.filename):
        raise HTTPException(status_code=400, detail="Provide a note body or a file")
    attachments = []
    if file and file.filename:
        data = await file.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File must be under 15MB")
        ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else 'bin'
        unique = f"{subject_id}-{uuid.uuid4().hex[:8]}.{ext}"
        try:
            from storage import put_object
            result = put_object(f"activity/{unique}", data, file.content_type or 'application/octet-stream')
            url = result.get("url", f"/api/storage/activity/{unique}")
        except Exception as e:
            logger.warning(f"Storage put failed, falling back to local: {e}")
            import os
            os.makedirs("/app/backend/uploads/files", exist_ok=True)
            with open(f"/app/backend/uploads/files/{unique}", "wb") as fh:
                fh.write(data)
            url = f"/api/uploads/files/{unique}"
        attachments.append({"name": file.filename, "url": url, "size": len(data), "mime": file.content_type})
    return await log_activity(
        subject_kind, subject_id, "note",
        title=(body[:60] + ("…" if len(body) > 60 else "")) or "Attachment",
        body=body,
        actor_id=current_user["id"],
        actor_name=current_user.get("name", ""),
        attachments=attachments,
        visibility=visibility,
    )


@router.delete("/{activity_id}")
async def delete_activity(activity_id: str, current_user: dict = Depends(require_staff)):
    """Delete an activity entry. Only the author or a manager+ may delete."""
    a = await db.activity_log.find_one({"id": activity_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    is_owner = a.get("actor_id") == current_user["id"]
    is_manager = current_user.get("role") in {"admin", "system_admin", "Executive Director", "Adviser", "Director", "Manager"}
    if not (is_owner or is_manager):
        raise HTTPException(status_code=403, detail="Only the author or a manager may delete")
    await db.activity_log.delete_one({"id": activity_id})
    return {"deleted": True}


@router.get("/{subject_kind}/{subject_id}/export")
async def export_subject_profile(
    subject_kind: str,
    subject_id: str,
    current_user: dict = Depends(require_staff),
):
    """Download a subject's full activity feed + core profile as JSON. Useful for
    compliance, authority requests, or the subject's own GDPR-style export."""
    if subject_kind not in SUBJECT_KINDS:
        raise HTTPException(status_code=400, detail="Invalid subject_kind")
    subject = None
    if subject_kind == "member":
        subject = await db.members.find_one({"id": subject_id}, {"_id": 0})
    elif subject_kind == "child":
        subject = await db.children.find_one({"id": subject_id}, {"_id": 0})
    elif subject_kind in {"staff", "user"}:
        subject = await db.users.find_one({"id": subject_id}, {"_id": 0, "password_hash": 0, "pin_hash": 0})
    elif subject_kind == "guest":
        subject = await db.guests.find_one({"id": subject_id}, {"_id": 0})
    elif subject_kind == "customer":
        subject = await db.customer_accounts.find_one({"id": subject_id}, {"_id": 0})
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    activity = await db.activity_log.find(
        {"subject_kind": subject_kind, "subject_id": subject_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(5000)
    return {
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "profile": subject,
        "activity_count": len(activity),
        "activity": activity,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": current_user["id"],
        "exported_by_name": current_user.get("name", ""),
    }
