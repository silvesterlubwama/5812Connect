"""Finance module — Journals, Taxes, Fiscal Periods.

Lightweight CRUD on top of the pre-existing `accounting_*` collections so the
old data survives the iter 246 finance reset. These are books/config only;
the actual money moves through /api/finance/journal (the JE ledger).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_campus_filter, require_staff, require_director, require_admin

router = APIRouter(prefix="/api/finance", tags=["finance-setup"])

JOURNAL_KINDS = {"sales", "purchases", "bank", "cash", "miscellaneous"}
FISCAL_STATUSES = {"open", "closed", "locked"}
TAX_KINDS = {"sales", "purchase"}


# ─────────────── JOURNALS ───────────────

@router.get("/journals")
async def list_journals(current_user: dict = Depends(require_staff)):
    scope = await get_campus_filter(current_user)
    q = {**(scope or {}), "active": True}
    return await db.accounting_journals.find(q, {"_id": 0}).sort("code", 1).to_list(200)


@router.post("/journals")
async def create_journal(data: dict, current_user: dict = Depends(require_director)):
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    kind = (data.get("kind") or "miscellaneous").strip().lower()
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name required")
    if kind not in JOURNAL_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(JOURNAL_KINDS)}")
    loc = data.get("location_id") or current_user.get("active_campus_id")
    if await db.accounting_journals.find_one({"location_id": loc, "code": code, "active": True}):
        raise HTTPException(status_code=409, detail=f"Journal code {code} already exists at this campus")
    doc = {
        "id": f"jrn_{uuid.uuid4().hex[:10]}",
        "code": code[:10], "name": name[:80], "kind": kind,
        "default_debit_account_id": data.get("default_debit_account_id"),
        "default_credit_account_id": data.get("default_credit_account_id"),
        "location_id": loc,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_journals.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/journals/{journal_id}")
async def update_journal(journal_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "kind", "default_debit_account_id", "default_credit_account_id", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "kind" in update and update["kind"] not in JOURNAL_KINDS:
        raise HTTPException(status_code=400, detail="Invalid kind")
    await db.accounting_journals.update_one({"id": journal_id}, {"$set": update})
    return await db.accounting_journals.find_one({"id": journal_id}, {"_id": 0})


@router.delete("/journals/{journal_id}")
async def delete_journal(journal_id: str, current_user: dict = Depends(require_admin)):
    # If any JE references it, deactivate instead of delete to keep ledger closed
    used = await db.finance_journal_entries.find_one({"journal_id": journal_id}, {"_id": 1})
    if used:
        await db.accounting_journals.update_one({"id": journal_id}, {"$set": {"active": False}})
        return {"deactivated": True}
    await db.accounting_journals.delete_one({"id": journal_id})
    return {"deleted": True}


# ─────────────── FISCAL PERIODS ───────────────

@router.get("/fiscal-periods")
async def list_fiscal_periods(current_user: dict = Depends(require_staff)):
    scope = await get_campus_filter(current_user)
    q = {**(scope or {})}
    return await db.accounting_fiscal_periods.find(q, {"_id": 0}).sort("start_date", -1).to_list(100)


@router.post("/fiscal-periods")
async def create_fiscal_period(data: dict, current_user: dict = Depends(require_director)):
    name = (data.get("name") or "").strip()
    start = (data.get("start_date") or "").strip()[:10]
    end = (data.get("end_date") or "").strip()[:10]
    if not name or not start or not end:
        raise HTTPException(status_code=400, detail="name, start_date, end_date required")
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be ≥ start_date")
    doc = {
        "id": f"fp_{uuid.uuid4().hex[:10]}",
        "name": name[:60], "start_date": start, "end_date": end,
        "status": "open",
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_fiscal_periods.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/fiscal-periods/{period_id}")
async def update_fiscal_period(period_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "start_date", "end_date", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "status" in update and update["status"] not in FISCAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(FISCAL_STATUSES)}")
    await db.accounting_fiscal_periods.update_one({"id": period_id}, {"$set": update})
    return await db.accounting_fiscal_periods.find_one({"id": period_id}, {"_id": 0})


@router.delete("/fiscal-periods/{period_id}")
async def delete_fiscal_period(period_id: str, current_user: dict = Depends(require_admin)):
    await db.accounting_fiscal_periods.delete_one({"id": period_id})
    return {"deleted": True}


# ─────────────── TAXES ───────────────

@router.get("/taxes")
async def list_taxes(current_user: dict = Depends(require_staff)):
    scope = await get_campus_filter(current_user)
    q = {**(scope or {}), "active": True}
    return await db.accounting_taxes.find(q, {"_id": 0}).sort("name", 1).to_list(100)


@router.post("/taxes")
async def create_tax(data: dict, current_user: dict = Depends(require_director)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        rate = float(data.get("rate") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="rate must be numeric")
    if not (0 <= rate <= 100):
        raise HTTPException(status_code=400, detail="rate must be 0..100")
    kind = (data.get("kind") or "sales").strip().lower()
    if kind not in TAX_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(TAX_KINDS)}")
    doc = {
        "id": f"tax_{uuid.uuid4().hex[:10]}",
        "name": name[:60], "rate": rate, "kind": kind,
        "inclusive": bool(data.get("inclusive", False)),
        "account_id": data.get("account_id"),
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.accounting_taxes.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/taxes/{tax_id}")
async def update_tax(tax_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "rate", "kind", "inclusive", "account_id", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "rate" in update:
        try:
            update["rate"] = float(update["rate"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="rate must be numeric")
        if not (0 <= update["rate"] <= 100):
            raise HTTPException(status_code=400, detail="rate must be 0..100")
    if "kind" in update and update["kind"] not in TAX_KINDS:
        raise HTTPException(status_code=400, detail="Invalid kind")
    await db.accounting_taxes.update_one({"id": tax_id}, {"$set": update})
    return await db.accounting_taxes.find_one({"id": tax_id}, {"_id": 0})


@router.delete("/taxes/{tax_id}")
async def delete_tax(tax_id: str, current_user: dict = Depends(require_admin)):
    await db.accounting_taxes.delete_one({"id": tax_id})
    return {"deleted": True}


# Helper — locked period guard so callers (e.g. finance/postings.py) can
# refuse to post into a closed month.
async def period_is_locked(date_iso: str, location_id: Optional[str]) -> bool:
    if not date_iso or not location_id:
        return False
    p = await db.accounting_fiscal_periods.find_one({
        "location_id": location_id,
        "start_date": {"$lte": date_iso[:10]},
        "end_date": {"$gte": date_iso[:10]},
        "status": "locked",
    }, {"_id": 0, "id": 1})
    return bool(p)
