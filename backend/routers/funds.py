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
from html import escape as _esc
from deps import db, get_current_user, _audit, require_staff, logger, get_campus_filter, has_module_access, is_system_admin, default_creation_location
from datetime import datetime, timezone
from typing import Optional
import uuid
import os

router = APIRouter(prefix="/api/funds", tags=["funds"])

UPLOADS_DIR = "/app/uploads/funds-receipts"  # mounted volume in compose

DEFAULT_WORKFLOW_ID = "wf_fund_request_default"

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def h(value) -> str:
    """HTML-escape anything that lands in the printed voucher."""
    return _esc(str(value or ""))


def _chunk_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")).strip()
    return (_ONES[n // 100] + " hundred" + (" and " + _chunk_words(n % 100) if n % 100 else "")).strip()


def _amount_in_words(amount: float, currency: str = "UGX") -> str:
    """'Two hundred thousand shillings only' — what a signed voucher needs."""
    whole = int(round(float(amount or 0)))
    if whole == 0:
        words = "zero"
    else:
        parts, scales = [], [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand"), (1, "")]
        rest = whole
        for size, label in scales:
            if rest >= size:
                count, rest = divmod(rest, size)
                parts.append((_chunk_words(count) + " " + label).strip())
        words = " ".join(parts)
    tail = "shillings" if (currency or "").upper() in ("UGX", "KES", "TZS") else (currency or "").upper()
    return f"{words.capitalize()} {tail} only"


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
    """Finance closes the request by paying out — posts the money properly.

    Body: {
        paid_from_account_id: str,   # REQUIRED — the cash/bank account the money leaves
        expense_account_id: str,     # REQUIRED — what the money was spent on
        match_expense_id?: str,      # link to an existing expense instead of creating
        notes?: str,
    }
    The approver says which account the funds come out of — nothing is paid
    from a guessed default. Creates the db.financial expense row AND a
    balanced journal entry, then stamps a voucher number so the printed slip
    can be signed for and filed. Idempotent: if already paid, returns as-is.
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
        return {"message": "Already paid", "expense_id": md["expense_id"], "voucher_no": md.get("voucher_no")}

    # Which accounts — asked, never assumed.
    from routers.finance.account_access import assert_can_use_account
    from routers.finance._common import post_journal_entry
    paid_from_id = (data.get("paid_from_account_id") or "").strip()
    expense_acct_id = (data.get("expense_account_id") or "").strip()
    if not paid_from_id or not expense_acct_id:
        raise HTTPException(status_code=400, detail="Choose which account the funds come out of and which expense account to post against")
    paid_from = await db.finance_chart_of_accounts.find_one({"id": paid_from_id}, {"_id": 0})
    expense_acct = await db.finance_chart_of_accounts.find_one({"id": expense_acct_id}, {"_id": 0})
    if not paid_from or not expense_acct:
        raise HTTPException(status_code=400, detail="That account no longer exists — pick another")
    if paid_from.get("type") != "asset":
        raise HTTPException(status_code=400, detail=f"'{paid_from['name']}' is not a cash or bank account")
    if expense_acct.get("type") != "expense":
        raise HTTPException(status_code=400, detail=f"'{expense_acct['name']}' is not an expense account")
    await assert_can_use_account(current_user, paid_from)
    await assert_can_use_account(current_user, expense_acct)

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
            "account_id": expense_acct["id"],
            "account_code": expense_acct["code"],
            "paid_from_account_id": paid_from["id"],
            "receipt_url": md.get("receipt_url"),
            "notes": data.get("notes", "")[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.financial.insert_one(expense)

    amount = float(req.get("amount") or 0)
    voucher_no = md.get("voucher_no") or f"FV-{datetime.now(timezone.utc).strftime('%Y%m')}-{request_id[-6:].upper()}"
    je = await post_journal_entry(
        date=datetime.now(timezone.utc).date().isoformat(),
        description=f"Fund request {voucher_no} — {req.get('summary') or req.get('title') or ''}"[:280],
        lines=[
            {"account_id": expense_acct["id"], "account_code": expense_acct["code"], "account_name": expense_acct["name"],
             "debit": amount, "credit": 0, "memo": f"Paid to {req.get('submitted_by_name', '')}"},
            {"account_id": paid_from["id"], "account_code": paid_from["code"], "account_name": paid_from["name"],
             "debit": 0, "credit": amount, "memo": f"Paid from {paid_from['name']}"},
        ],
        source="fund_request",
        reference=request_id,
        location_id=req.get("location_id"),
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
        idempotency_key=f"fund_request:{request_id}",
    )

    await db.approval_requests.update_one(
        {"id": request_id},
        {"$set": {
            "metadata.expense_id": expense_id,
            "metadata.voucher_no": voucher_no,
            "metadata.journal_entry_id": je.get("id"),
            "metadata.paid_from_account_id": paid_from["id"],
            "metadata.paid_from_account_code": paid_from["code"],
            "metadata.paid_from_account_name": paid_from["name"],
            "metadata.expense_account_id": expense_acct["id"],
            "metadata.expense_account_code": expense_acct["code"],
            "metadata.expense_account_name": expense_acct["name"],
            "metadata.paid_at": datetime.now(timezone.utc).isoformat(),
            "metadata.paid_by": current_user["id"],
            "metadata.paid_by_name": current_user.get("name", ""),
            "metadata.payment_notes": data.get("notes", "")[:500],
        }},
    )
    await _audit(current_user["id"], "update", "fund_request_paid", request_id,
                 {"expense_id": expense_id, "voucher_no": voucher_no, "paid_from": paid_from["code"], "je": je.get("id")})
    return {"message": "Marked paid", "expense_id": expense_id, "voucher_no": voucher_no,
            "journal_entry_id": je.get("id"), "paid_from_account_name": paid_from["name"]}


@router.get("/requests/{request_id}/voucher")
async def fund_voucher(request_id: str, current_user: dict = Depends(get_current_user)):
    """The signable payment voucher — print, sign, file.

    Returns a print-ready A5 HTML slip with the amount in words, the approval
    trail, the account the money came from and ruled lines for the three
    signatures an auditor looks for: prepared, approved, received.
    """
    req = await db.approval_requests.find_one({"id": request_id, "subject_kind": "fund_request"}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Fund request not found")
    if (req.get("submitted_by") != current_user["id"]
            and not is_system_admin(current_user)
            and not has_module_access(current_user, "finance")):
        raise HTTPException(status_code=403, detail="Only the submitter or finance can print this voucher")
    md = req.get("metadata") or {}
    amount = float(req.get("amount") or 0)
    currency = req.get("currency", "UGX")
    voucher_no = md.get("voucher_no") or f"FV-{datetime.now(timezone.utc).strftime('%Y%m')}-{request_id[-6:].upper()}"
    loc_name = ""
    if req.get("location_id"):
        loc = await db.locations.find_one({"id": req["location_id"]}, {"_id": 0, "name": 1})
        loc_name = (loc or {}).get("name", "")
    approvals = []
    for st in req.get("step_states") or []:
        for a in st.get("approvals") or []:
            approvals.append(a)
    approved_rows = "".join(
        f"<tr><td>{h(a.get('user_name') or '')}</td><td>{h(a.get('user_role') or '')}</td>"
        f"<td>{h((a.get('at') or '')[:10])}</td><td>{h(a.get('outcome') or '')}</td></tr>"
        for a in approvals
    ) or "<tr><td colspan='4' style='color:#777'>Not yet approved</td></tr>"
    paid_block = (
        f"<div><span class='k'>Paid from</span> {h(md.get('paid_from_account_name') or '')} "
        f"({h(md.get('paid_from_account_code') or '')})</div>"
        f"<div><span class='k'>Posted to</span> {h(md.get('expense_account_name') or '')} "
        f"({h(md.get('expense_account_code') or '')})</div>"
        f"<div><span class='k'>Paid on</span> {h((md.get('paid_at') or '')[:10])} by {h(md.get('paid_by_name') or '')}</div>"
        if md.get("paid_at") else
        "<div style='color:#777'>Not yet paid out — finance completes the account details on payment.</div>"
    )
    html_doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Payment Voucher {h(voucher_no)}</title>
<style>
  @page {{ size: A5 portrait; margin: 10mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:#111; margin:0; font-size:12px; }}
  h1 {{ font-size:16px; margin:0; letter-spacing:.04em; text-transform:uppercase; }}
  .no {{ font-size:13px; font-weight:700; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #111; padding-bottom:6px; }}
  .k {{ display:inline-block; min-width:84px; color:#555; }}
  .grid {{ margin:8px 0; line-height:1.55; }}
  .amt {{ border:1px solid #111; padding:6px 8px; margin:8px 0; font-size:15px; font-weight:700; }}
  .words {{ font-size:11px; font-weight:400; font-style:italic; color:#333; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:11px; margin-top:4px; }}
  th, td {{ border:1px solid #666; padding:3px 5px; text-align:left; }}
  th {{ background:#f2f2f2; }}
  .sigs {{ display:flex; gap:10px; margin-top:18px; }}
  .sig {{ flex:1; border-top:1px solid #111; padding-top:3px; font-size:10px; color:#444; }}
  .sig small {{ display:block; color:#888; }}
  .foot {{ margin-top:12px; font-size:9px; color:#666; }}
  .print-btn {{ background:#111; color:#fff; padding:5px 10px; border:none; border-radius:4px; cursor:pointer; font-size:11px; }}
  @media print {{ .print-btn {{ display:none; }} }}
</style></head><body>
<div class='hdr'>
  <div>
    <h1>Payment Voucher</h1>
    <div style='font-size:11px;color:#555'>{h(loc_name or '58:12 Global')}</div>
  </div>
  <div style='text-align:right'>
    <div class='no'>{h(voucher_no)}</div>
    <div style='font-size:10px;color:#555'>{h((md.get('paid_at') or req.get('created_at') or '')[:10])}</div>
    <button class='print-btn' onclick='window.print()'>Print</button>
  </div>
</div>

<div class='grid'>
  <div><span class='k'>Paid to</span> <strong>{h(req.get('submitted_by_name') or '')}</strong></div>
  <div><span class='k'>Request</span> {h(req.get('title') or '')}</div>
  <div><span class='k'>Purpose</span> {h(req.get('summary') or '')}</div>
  <div><span class='k'>Type</span> {h((md.get('kind') or 'reimbursement').title())}{(' · ' + h(md.get('category'))) if md.get('category') else ''}</div>
  <div><span class='k'>Status</span> {h((req.get('status') or '').replace('_', ' ').title())}</div>
</div>

<div class='amt'>{h(currency)} {amount:,.2f}
  <div class='words'>{h(_amount_in_words(amount, currency))}</div>
</div>

{paid_block}

<table>
  <thead><tr><th>Approved by</th><th>Role</th><th>Date</th><th>Outcome</th></tr></thead>
  <tbody>{approved_rows}</tbody>
</table>

<div class='sigs'>
  <div class='sig'>Prepared by<small>name &amp; signature</small></div>
  <div class='sig'>Approved by<small>name &amp; signature</small></div>
  <div class='sig'>Received by<small>signature &amp; date</small></div>
</div>
<p class='foot'>Voucher {h(voucher_no)} · request {h(request_id)}{(' · journal ' + h(md.get('journal_entry_id'))) if md.get('journal_entry_id') else ''}. Keep the signed copy with the receipt for audit.</p>
</body></html>"""
    from fastapi.responses import Response
    return Response(content=html_doc, media_type="text/html; charset=utf-8")


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
