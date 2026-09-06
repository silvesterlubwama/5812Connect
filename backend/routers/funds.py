"""Fund Requests — staff workflow for advances and reimbursements.

Design:
  • Wraps the existing Approvals system. A fund request is just an approval
    request with `subject_kind='fund_request'` and a richer `metadata` block
    (kind, receipt_url, etc.). All approval routing rides on top of whatever
    workflow the admin configured — including delegation, multi-step, etc.
  • Auto-seeds a default 1-step "Fund Request" workflow on first use so the
    UI works out-of-the-box on a fresh install without admin intervention.
  • On approval, the finance officer hits POST /funds/requests/{id}/mark-paid
    which (a) creates a financial expense row, (b) attaches the receipt URL
    if uploaded, (c) closes the request.

Two kinds:
  • 'advance'        - staff requests funds upfront → approved → cash out →
                       staff returns with receipts → reconciled.
  • 'reimbursement'  - staff spent own money → uploads receipt with request →
                       approved → expense recorded + staff is paid back.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from deps import db, get_current_user, _audit, require_staff, logger, get_campus_filter, has_module_access, is_system_admin, default_creation_location
from datetime import datetime, timezone
from typing import Optional
import uuid
import os

router = APIRouter(prefix="/api/funds", tags=["funds"])

UPLOADS_DIR = "/app/uploads/funds-receipts"  # mounted volume in compose

DEFAULT_WORKFLOW_ID = "wf_fund_request_default"


async def _ensure_default_workflow() -> dict:
    """Idempotent: create the default 'Fund Request' workflow on first call."""
    wf = await db.approval_workflows.find_one({"id": DEFAULT_WORKFLOW_ID}, {"_id": 0})
    if wf:
        return wf
    wf = {
        "id": DEFAULT_WORKFLOW_ID,
        "name": "Fund Request",
        "kind": "fund_request",
        "active": True,
        "steps": [
            {
                "name": "Finance / Director approval",
                "approver_roles": ["Director", "Adviser", "Executive Director", "Manager", "admin", "system_admin"],
                "min_approvals": 1,
            }
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_default": True,
    }
    try:
        await db.approval_workflows.insert_one(wf)
    except Exception:
        pass  # race-condition safe
    wf.pop("_id", None)
    return wf


@router.get("/workflow")
async def get_workflow(current_user: dict = Depends(get_current_user)):
    """Return the default fund-request workflow (auto-seeded)."""
    return await _ensure_default_workflow()


@router.get("/requests/mine")
async def my_fund_requests(current_user: dict = Depends(get_current_user)):
    """Every fund request submitted by the calling user, newest first."""
    rows = await db.approval_requests.find(
        {"subject_kind": "fund_request", "submitted_by": current_user["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return rows


@router.get("/requests")
async def all_fund_requests(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Fund-request list view.

    Visibility rules (intentionally restrictive — fund requests can mention
    salary advances, hardship payments, and other sensitive amounts):
      • system_admin / finance-module users → all requests across their campus.
      • everyone else → only their OWN submissions (use /requests/mine for the
        explicit-self surface; this endpoint also self-scopes to avoid an
        accidental cross-staff data leak when the role check below is bypassed).
    """
    query = {"subject_kind": "fund_request"}
    if status:
        query["status"] = status
    if is_system_admin(current_user) or has_module_access(current_user, "finance"):
        # Privileged: campus-scope only
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    else:
        # Everyone else: self-scope, regardless of campus
        query["submitted_by"] = current_user["id"]
    rows = await db.approval_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@router.post("/requests")
async def create_fund_request(data: dict, current_user: dict = Depends(require_staff)):
    """Create a new fund request.
    Body: {
        kind: 'advance' | 'reimbursement',
        amount: number,
        currency?: str (default UGX),
        purpose: str,
        category?: str (financial category for the resulting expense),
        location_id?: str,
        budget_id?: str,
        receipt_url?: str (for reimbursements where the receipt was already uploaded),
    }
    Returns the created approval-request doc."""
    kind = (data.get("kind") or "").lower().strip()
    if kind not in {"advance", "reimbursement"}:
        raise HTTPException(status_code=400, detail="kind must be 'advance' or 'reimbursement'")
    try:
        amount = float(data.get("amount") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be a number")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than zero")
    purpose = (data.get("purpose") or "").strip()
    if not purpose:
        raise HTTPException(status_code=400, detail="purpose is required")

    wf = await _ensure_default_workflow()
    now = datetime.now(timezone.utc).isoformat()
    steps = wf.get("steps") or []
    step_states = [
        {"step_index": i, "status": "pending", "approvals": [], "started_at": (now if i == 0 else None)}
        for i, _ in enumerate(steps)
    ]
    doc = {
        "id": f"areq_{uuid.uuid4().hex[:10]}",
        "workflow_id": wf["id"],
        "workflow_name": wf.get("name"),
        "workflow_snapshot": {"steps": steps, "kind": wf.get("kind")},
        "subject_kind": "fund_request",
        "subject_id": "",
        "title": f"{kind.title()}: {purpose[:60]}",
        "summary": purpose[:1000],
        "amount": amount,
        "currency": (data.get("currency") or "UGX")[:8],
        "metadata": {
            "kind": kind,
            "category": (data.get("category") or "")[:60],
            "budget_id": data.get("budget_id") or None,
            "receipt_url": (data.get("receipt_url") or "")[:500],
            "expense_id": None,  # filled in when finance marks paid
        },
        "status": "in_progress",
        "current_step": 0,
        "step_states": step_states,
        "submitted_by": current_user["id"],
        "submitted_by_name": current_user.get("name", ""),
        "submitted_by_email": current_user.get("email", ""),
        "location_id": default_creation_location(current_user, data.get("location_id")),
        "created_at": now,
    }
    await db.approval_requests.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "fund_request", doc["id"], {"kind": kind, "amount": amount})
    return doc


@router.post("/requests/{request_id}/receipt")
async def upload_receipt(
    request_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Attach a receipt file to a fund request. Submitter or finance can do this
    at any time before mark-paid. Uses local disk; cloud storage when available."""
    req = await db.approval_requests.find_one({"id": request_id, "subject_kind": "fund_request"}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Fund request not found")
    if (req.get("submitted_by") != current_user["id"]
            and not is_system_admin(current_user)
            and not has_module_access(current_user, "finance")):
        raise HTTPException(status_code=403, detail="Only the submitter or finance staff can attach receipts")
    if not file.content_type or not (file.content_type.startswith("image/") or file.content_type == "application/pdf"):
        raise HTTPException(status_code=400, detail="Receipt must be an image or PDF")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Receipt must be under 10 MB")
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin"
    unique = f"{request_id}-{uuid.uuid4().hex[:8]}.{ext}"
    try:
        from upload_helper import save_upload_sync
        receipt_url = save_upload_sync("funds-receipts", unique, data, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.warning(f"Receipt upload failed: {e}")
        raise HTTPException(status_code=502, detail="Could not save receipt")
    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {
            "metadata.receipt_url": receipt_url,
            "metadata.receipt_uploaded_at": datetime.now(timezone.utc).isoformat(),
            "metadata.receipt_uploaded_by": current_user["id"],
        }},
    )
    await _audit(current_user["id"], "update", "fund_request_receipt", request_id, {"size": len(data)})
    return {"receipt_url": receipt_url}


@router.post("/requests/{request_id}/mark-paid")
async def mark_paid(request_id: str, data: dict = None, current_user: dict = Depends(get_current_user)):
    """Finance closes the request by paying out — creates the matching expense row.

    Body (optional): {
        match_expense_id?: str,   # link to an existing expense instead of creating
        notes?: str,
    }
    Auto-creates a db.financial row of type='expense' so the books match. Idempotent:
    if the request is already marked paid, returns the existing expense_id.
    """
    if not is_system_admin(current_user) and not has_module_access(current_user, "finance"):
        raise HTTPException(status_code=403, detail="Only finance staff can mark fund requests as paid")
    data = data or {}
    req = await db.approval_requests.find_one({"id": request_id, "subject_kind": "fund_request"}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Fund request not found")
    if req.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Request must be approved before it can be paid")
    md = req.get("metadata") or {}
    if md.get("expense_id"):
        return {"message": "Already paid", "expense_id": md["expense_id"]}

    match_id = (data.get("match_expense_id") or "").strip()
    if match_id:
        existing = await db.financial.find_one({"id": match_id, "type": "expense"}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail=f"Expense {match_id} not found")
        expense_id = match_id
        await db.financial.update_one(
            {"id": expense_id},
            {"$set": {
                "fund_request_id": request_id,
                "matched_at": datetime.now(timezone.utc).isoformat(),
                "matched_by": current_user["id"],
            }},
        )
    else:
        expense_id = f"exp_{uuid.uuid4().hex[:10]}"
        kind = md.get("kind", "reimbursement")
        category = md.get("category") or ("Staff Advance" if kind == "advance" else "Staff Reimbursement")
        expense = {
            "id": expense_id,
            "type": "expense",
            "amount": float(req.get("amount") or 0),
            "currency": req.get("currency", "UGX"),
            "category": category,
            "description": f"[{kind.title()}] {req.get('summary', '')} — submitted by {req.get('submitted_by_name', '')}",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "location_id": req.get("location_id"),
            "entered_by": current_user["id"],
            "entered_by_name": current_user.get("name", ""),
            "fund_request_id": request_id,
            "fund_request_kind": kind,
            "receipt_url": md.get("receipt_url"),
            "notes": data.get("notes", "")[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.financial.insert_one(expense)

    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {
            "metadata.expense_id": expense_id,
            "metadata.paid_at": datetime.now(timezone.utc).isoformat(),
            "metadata.paid_by": current_user["id"],
            "metadata.paid_by_name": current_user.get("name", ""),
            "metadata.payment_notes": data.get("notes", "")[:500],
        }},
    )
    await _audit(current_user["id"], "update", "fund_request_paid", request_id, {"expense_id": expense_id})
    return {"message": "Marked paid", "expense_id": expense_id}


@router.delete("/requests/{request_id}")
async def cancel_my_fund_request(request_id: str, current_user: dict = Depends(get_current_user)):
    """Submitter cancels their own pending request. Admins / finance can cancel any."""
    req = await db.approval_requests.find_one({"id": request_id, "subject_kind": "fund_request"}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Fund request not found")
    if (req.get("submitted_by") != current_user["id"]
            and not is_system_admin(current_user)
            and not has_module_access(current_user, "finance")):
        raise HTTPException(status_code=403, detail="Only the submitter or finance can cancel")
    if req.get("status") not in ("in_progress",):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a request that is {req.get('status')}")
    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "cancelled",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "cancelled_by": current_user["id"],
        }},
    )
    await _audit(current_user["id"], "update", "fund_request_cancelled", request_id)
    return {"message": "Cancelled"}
