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
    format: str = "json",
    current_user: dict = Depends(require_staff),
):
    """Download a subject's full activity feed + core profile.
    `format=json` (default) returns the raw JSON envelope — useful for GDPR / compliance.
    `format=pdf` returns a presentation-ready PDF with profile + chronological activity."""
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
            # Fall back to sales-aggregator: the /api/customers tab in ProductsPage
            # surfaces synthetic rows that don't exist in customer_accounts. Build
            # a minimal profile from sales so the export contract matches the read
            # endpoint, which also aggregates from sales.
            sales_rows = await db.sales.find(
                {"customer_id": subject_id},
                {"_id": 0, "customer_name": 1, "customer_phone": 1, "total": 1, "created_at": 1, "location_id": 1},
            ).to_list(2000)
            if sales_rows:
                total_spent = sum(float(s.get("total") or 0) for s in sales_rows)
                last_visit = max((s.get("created_at") or "") for s in sales_rows)
                subject = {
                    "id": subject_id,
                    "name": next((s.get("customer_name") for s in sales_rows if s.get("customer_name")), "Customer"),
                    "phone": next((s.get("customer_phone") for s in sales_rows if s.get("customer_phone")), ""),
                    "total_spent": round(total_spent, 2),
                    "total_purchases": len(sales_rows),
                    "last_visit": last_visit,
                    "location_id": next((s.get("location_id") for s in sales_rows if s.get("location_id")), ""),
                    "source": "sales_aggregator",
                }
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    # Pull curated log + live-derived rows (same logic as the read endpoint).
    curated = await db.activity_log.find(
        {"subject_kind": subject_kind, "subject_id": subject_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(5000)
    # Re-use the merging logic by calling the GET handler in-process would be neat but
    # would re-apply auth; cheaper to call the same merge inline here.
    activity = curated
    try:
        merged = await get_subject_activity(subject_kind, subject_id, None, 5000, current_user)
        activity = merged if isinstance(merged, list) else curated
    except Exception as e:
        logger.warning(f"export merge fallback: {e}")
    if (format or "json").lower() == "pdf":
        return _render_profile_pdf(subject_kind, subject, activity, current_user)
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


def _render_profile_pdf(subject_kind: str, subject: dict, activity: list, current_user: dict):
    """Render a clean WeasyPrint PDF of a subject's profile + activity trail.
    Returns a fastapi.responses.Response with content_type=application/pdf."""
    from fastapi.responses import Response
    import html as _html
    name = _html.escape(str(subject.get("name") or subject.get("full_name") or subject.get("id") or "Profile"))
    photo_url = subject.get("photo_url") or ""
    if photo_url and not photo_url.startswith("http"):
        # WeasyPrint can't resolve relative URLs at print time — skip photo if relative.
        photo_url = ""
    rows_html = []
    for it in activity[:500]:
        cat = _html.escape(str(it.get("category") or "")).replace("_", " ")
        title = _html.escape(str(it.get("title") or ""))
        body = _html.escape(str(it.get("body") or ""))
        at = (it.get("created_at") or "")[:16].replace("T", " ")
        actor = _html.escape(str(it.get("actor_name") or ""))
        amount = it.get("amount")
        cur = _html.escape(str(it.get("currency") or ""))
        money = f" · {cur} {float(amount):,.2f}" if amount is not None else ""
        rows_html.append(
            f'<tr>'
            f'<td class="cat">{cat}</td>'
            f'<td class="title"><div class="t">{title}</div>'
            f'{f"<div class=b>{body}</div>" if body else ""}</td>'
            f'<td class="meta">{at}{f" · {actor}" if actor else ""}{money}</td>'
            f"</tr>"
        )
    activity_html = "".join(rows_html) or "<tr><td colspan='3' class='empty'>No activity recorded.</td></tr>"
    # Render a small profile facts box
    facts = []
    fact_keys = [
        ("Email", "email"), ("Phone", "phone"), ("National ID", "national_id"),
        ("Role", "role"), ("Group", "group"), ("Department", "department"),
        ("Status", "status"), ("Joined", "join_date"), ("Date of birth", "date_of_birth"),
        ("Grade", "grade"), ("School", "school_name"), ("Location", "location_id"),
    ]
    for label, key in fact_keys:
        val = subject.get(key)
        if val:
            facts.append(f'<div class="fact"><div class="lbl">{label}</div><div class="val">{_html.escape(str(val))}</div></div>')
    facts_html = "".join(facts) or '<div class="fact"><div class="lbl">—</div></div>'
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    org = "58:12 Connect"
    css = """
      @page { size: A4; margin: 18mm 14mm 16mm 14mm; @bottom-center { content: "Page " counter(page) " / " counter(pages); font-size: 8pt; color: #777; } }
      body { font-family: 'Helvetica', 'Arial', sans-serif; color: #222; font-size: 10pt; }
      .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #14b8a6; padding-bottom: 10px; }
      .title { font-size: 20pt; font-weight: bold; }
      .subkind { font-size: 9pt; color: #14b8a6; text-transform: uppercase; letter-spacing: 1.5px; }
      .meta { font-size: 8pt; color: #888; }
      .photo { width: 80px; height: 80px; object-fit: cover; border-radius: 12px; border: 1px solid #ddd; }
      .facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px 18px; margin: 14px 0 16px; }
      .fact .lbl { font-size: 7pt; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
      .fact .val { font-size: 10pt; }
      h2 { font-size: 12pt; margin: 18px 0 6px; padding-bottom: 4px; border-bottom: 1px solid #e5e7eb; color: #0f766e; }
      table { width: 100%; border-collapse: collapse; }
      td { padding: 6px 4px; border-bottom: 1px solid #f0f0f0; vertical-align: top; font-size: 9pt; }
      td.cat { text-transform: capitalize; color: #14b8a6; font-weight: 600; width: 18%; }
      td.title .t { font-weight: 600; }
      td.title .b { color: #555; margin-top: 2px; white-space: pre-wrap; font-size: 8.5pt; }
      td.meta { color: #888; width: 22%; text-align: right; font-size: 8pt; }
      .empty { text-align: center; color: #999; padding: 20px; font-style: italic; }
      .footer { margin-top: 24px; padding-top: 10px; border-top: 1px solid #eee; color: #888; font-size: 7.5pt; text-align: center; }
    """
    photo_block = f'<img class="photo" src="{photo_url}" />' if photo_url else ""
    html_doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
      <div class="header">
        <div>
          <div class="subkind">{_html.escape(subject_kind)} profile</div>
          <div class="title">{name}</div>
          <div class="meta">Generated {generated_at} · {_html.escape(current_user.get('name') or 'staff')} · {org}</div>
        </div>
        {photo_block}
      </div>
      <h2>Profile</h2>
      <div class="facts">{facts_html}</div>
      <h2>Activity Trail ({len(activity)})</h2>
      <table>
        <thead><tr><td class="cat" style="font-weight:bold; border-bottom:1px solid #ccc">Category</td><td class="title" style="font-weight:bold; border-bottom:1px solid #ccc">Detail</td><td class="meta" style="font-weight:bold; border-bottom:1px solid #ccc">When / Who</td></tr></thead>
        <tbody>{activity_html}</tbody>
      </table>
      <div class="footer">Confidential — for internal use. {org} · activity-trail export.</div>
    </body></html>"""
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_doc).write_pdf()
    except Exception as e:
        logger.error(f"WeasyPrint failed for activity export: {e}")
        raise HTTPException(status_code=500, detail=f"PDF render failed: {e}")
    fname = f"profile-{subject_kind}-{subject.get('id')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
