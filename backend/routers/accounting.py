"""[DEPRECATED — iter 291] Legacy accounting router.

This file is retained ONLY because `bank.py` imports three helpers from it
(`_next_entry_number`, `create_entry`, `reverse_entry`) for the recurring-
entries scheduler. The FastAPI router below is NOT included in `server.py`
so none of the endpoints in this file are served over HTTP — all live
accounting/finance UI now flows through `routers/finance/*`. Do NOT add
new endpoints here. When `bank.py`'s recurring-entries scheduler is
migrated to `post_journal_entry`, this whole file can be deleted.

See PRD → "Legacy Accounting Purge" (session #4).
"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_director, require_admin, _audit, logger, get_campus_filter, is_system_admin, require_finance_view, require_finance_admin
from datetime import datetime, timezone, date as dt_date
from typing import Optional, List, Dict, Any
import uuid
import io
import csv

# NB: this router is deliberately NOT mounted in server.py. Present only so
# the module-level helper functions below (`_next_entry_number`,
# `create_entry`, `reverse_entry`) remain callable by `bank.py`.
router = APIRouter(prefix="/api/_legacy_accounting", tags=["accounting-legacy"])


async def _user_can_access_location(user: dict, location_id: str) -> bool:
    """Mirror of Financial's campus scoping: admins/system_admin/Executive Director see all.
    Other roles must have the location_id in their own location_ids/active_campus."""
    if not location_id:
        return True
    if is_system_admin(user):
        return True
    role = (user.get("role") or "")
    if role in {"admin", "Executive Director"}:
        return True
    user_locs = set(user.get("location_ids") or [])
    if user.get("location_id"):
        user_locs.add(user["location_id"])
    if user.get("active_campus_id"):
        user_locs.add(user["active_campus_id"])
    # Include sub-locations whose parent is in the user's set
    if user_locs:
        children = await db.locations.find(
            {"parent_id": {"$in": list(user_locs)}}, {"_id": 0, "id": 1}
        ).to_list(500)
        user_locs.update(c["id"] for c in children)
    return location_id in user_locs


async def _require_location_access(user: dict, location_id: str):
    """Raise 403 if user can't act on this location's accounting data."""
    if not await _user_can_access_location(user, location_id):
        raise HTTPException(status_code=403, detail="You don't have access to this campus's accounting data")


# ============================================================
# CHART OF ACCOUNTS
# ============================================================
# Standard Odoo-style account types
ACCOUNT_TYPES = {
    "asset_current": {"category": "asset", "label": "Current Asset", "normal_balance": "debit"},
    "asset_non_current": {"category": "asset", "label": "Non-current Asset", "normal_balance": "debit"},
    "asset_receivable": {"category": "asset", "label": "Accounts Receivable", "normal_balance": "debit"},
    "asset_cash": {"category": "asset", "label": "Cash & Bank", "normal_balance": "debit"},
    "asset_inventory": {"category": "asset", "label": "Inventory", "normal_balance": "debit"},
    "asset_fixed": {"category": "asset", "label": "Fixed Asset", "normal_balance": "debit"},
    "liability_current": {"category": "liability", "label": "Current Liability", "normal_balance": "credit"},
    "liability_non_current": {"category": "liability", "label": "Non-current Liability", "normal_balance": "credit"},
    "liability_payable": {"category": "liability", "label": "Accounts Payable", "normal_balance": "credit"},
    "liability_tax": {"category": "liability", "label": "Tax Payable", "normal_balance": "credit"},
    "equity": {"category": "equity", "label": "Equity", "normal_balance": "credit"},
    "income": {"category": "income", "label": "Income", "normal_balance": "credit"},
    "income_other": {"category": "income", "label": "Other Income", "normal_balance": "credit"},
    "expense": {"category": "expense", "label": "Expense", "normal_balance": "debit"},
    "expense_cogs": {"category": "expense", "label": "Cost of Goods Sold", "normal_balance": "debit"},
    "expense_depreciation": {"category": "expense", "label": "Depreciation", "normal_balance": "debit"},
}

# Default chart of accounts seeded for new locations
DEFAULT_COA = [
    # Assets
    {"code": "1000", "name": "Cash on Hand", "type": "asset_cash"},
    {"code": "1010", "name": "Bank Account", "type": "asset_cash"},
    {"code": "1200", "name": "Accounts Receivable", "type": "asset_receivable"},
    {"code": "1300", "name": "Inventory", "type": "asset_inventory"},
    {"code": "1500", "name": "Equipment & Fixtures", "type": "asset_fixed"},
    {"code": "1510", "name": "Accumulated Depreciation", "type": "asset_fixed"},
    # Liabilities
    {"code": "2000", "name": "Accounts Payable", "type": "liability_payable"},
    {"code": "2100", "name": "Tax Payable (VAT/Sales Tax)", "type": "liability_tax"},
    {"code": "2200", "name": "Salaries Payable", "type": "liability_current"},
    # Equity
    {"code": "3000", "name": "Owner's Equity", "type": "equity"},
    {"code": "3100", "name": "Retained Earnings", "type": "equity"},
    # Income
    {"code": "4000", "name": "Sales Revenue", "type": "income"},
    {"code": "4100", "name": "Donations / Contributions", "type": "income"},
    {"code": "4200", "name": "Other Income", "type": "income_other"},
    # Expenses
    {"code": "5000", "name": "Cost of Goods Sold", "type": "expense_cogs"},
    {"code": "5100", "name": "Salaries & Wages", "type": "expense"},
    {"code": "5200", "name": "Rent & Utilities", "type": "expense"},
    {"code": "5300", "name": "Supplies", "type": "expense"},
    {"code": "5400", "name": "Travel & Meals", "type": "expense"},
    {"code": "5500", "name": "Depreciation Expense", "type": "expense_depreciation"},
    {"code": "5900", "name": "Other Expenses", "type": "expense"},
]


@router.get("/account-types")
async def list_account_types(current_user: dict = Depends(require_finance_view)):
    """Return the standard account-type catalog for the CoA builder."""
    return [{"id": k, **v} for k, v in ACCOUNT_TYPES.items()]


@router.post("/seed")
async def seed_default_coa(data: dict = None, current_user: dict = Depends(require_director)):
    """Seed the default chart of accounts for a location (idempotent — only creates missing codes).
    Body: { location_id?, currency?: 'UGX' }"""
    data = data or {}
    location_id = data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id")
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id required")
    await _require_location_access(current_user, location_id)
    currency = (data.get("currency") or "UGX").upper()[:5]
    created = []
    for acc in DEFAULT_COA:
        existing = await db.accounting_accounts.find_one({"location_id": location_id, "code": acc["code"]})
        if existing:
            continue
        doc = {
            "id": f"acc_{uuid.uuid4().hex[:10]}",
            "code": acc["code"],
            "name": acc["name"],
            "type": acc["type"],
            "currency": currency,
            "location_id": location_id,
            "active": True,
            "is_default_seeded": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.accounting_accounts.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
    return {"seeded": len(created), "skipped": len(DEFAULT_COA) - len(created), "accounts": created}


@router.post("/seed-bulk")
async def seed_default_coa_bulk(data: dict, current_user: dict = Depends(require_admin)):
    """Seed the default CoA for a LIST of locations in one call (idempotent).
    Body: { location_ids: [...], currency?: 'UGX' }
    Companion to `/hr/repair-payslip-journals` — feed it the `locations_missing_accounts`
    list and it wires up the minimum accounts needed for payroll postings to succeed."""
    location_ids = data.get("location_ids") or []
    if not location_ids or not isinstance(location_ids, list):
        raise HTTPException(status_code=400, detail="location_ids (list) is required")
    currency = (data.get("currency") or "UGX").upper()[:5]
    results = []
    for loc_id in location_ids:
        if not loc_id:
            continue
        created_count = 0
        try:
            for acc in DEFAULT_COA:
                existing = await db.accounting_accounts.find_one(
                    {"location_id": loc_id, "code": acc["code"]}, {"_id": 0, "id": 1}
                )
                if existing:
                    continue
                doc = {
                    "id": f"acc_{uuid.uuid4().hex[:10]}",
                    "code": acc["code"], "name": acc["name"], "type": acc["type"],
                    "currency": currency, "location_id": loc_id,
                    "active": True, "is_default_seeded": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"],
                }
                await db.accounting_accounts.insert_one(doc)
                created_count += 1
            results.append({"location_id": loc_id, "seeded": created_count, "ok": True})
        except Exception as ex:
            results.append({"location_id": loc_id, "ok": False, "error": str(ex)[:200]})
    await _audit(current_user["id"], "bulk_seed_coa", "accounting_accounts", None, {
        "locations": len(results),
        "total_seeded": sum(r.get("seeded", 0) for r in results),
    })
    return {
        "locations_processed": len(results),
        "total_accounts_seeded": sum(r.get("seeded", 0) for r in results),
        "results": results,
    }


@router.get("/accounts")
async def list_accounts(
    location_id: Optional[str] = None,
    category: Optional[str] = None,
    active: bool = True,
    current_user: dict = Depends(require_finance_view),
):
    query = {}
    if active:
        query["active"] = True
    if location_id:
        scope_ids = await _expand_location_scope(location_id)
        query["location_id"] = {"$in": scope_ids} if len(scope_ids) > 1 else location_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    if category:
        # Match all types within category
        matching = [t for t, meta in ACCOUNT_TYPES.items() if meta["category"] == category]
        query["type"] = {"$in": matching}
    rows = await db.accounting_accounts.find(query, {"_id": 0}).sort("code", 1).to_list(1000)
    # Enrich with category & normal_balance
    for r in rows:
        meta = ACCOUNT_TYPES.get(r.get("type"), {})
        r["category"] = meta.get("category", "")
        r["normal_balance"] = meta.get("normal_balance", "debit")
        r["type_label"] = meta.get("label", r.get("type"))
    return rows


@router.post("/accounts")
async def create_account(data: dict, current_user: dict = Depends(require_director)):
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    acc_type = (data.get("type") or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name required")
    if acc_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    loc = data.get("location_id") or current_user.get("active_campus_id")
    if not loc:
        raise HTTPException(status_code=400, detail="location_id required")
    await _require_location_access(current_user, loc)
    existing = await db.accounting_accounts.find_one({"location_id": loc, "code": code})
    if existing:
        raise HTTPException(status_code=400, detail=f"Account code {code} already exists")
    doc = {
        "id": f"acc_{uuid.uuid4().hex[:10]}",
        "code": code,
        "name": name[:120],
        "type": acc_type,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "location_id": loc,
        "active": True,
        "is_default_seeded": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "code", "type", "currency", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "type" in update and update["type"] not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.accounting_accounts.update_one({"id": account_id}, {"$set": update})
    return await db.accounting_accounts.find_one({"id": account_id}, {"_id": 0})


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, current_user: dict = Depends(require_admin)):
    # Soft delete by deactivating — never destructive if entries exist
    has_lines = await db.accounting_entry_lines.find_one({"account_id": account_id})
    if has_lines:
        await db.accounting_accounts.update_one({"id": account_id}, {"$set": {"active": False}})
        return {"deactivated": True, "note": "Account had journal lines — deactivated instead of deleted"}
    await db.accounting_accounts.delete_one({"id": account_id})
    return {"deleted": True}


# ============================================================
# JOURNALS
# ============================================================
JOURNAL_KINDS = {"sales", "purchases", "bank", "cash", "miscellaneous"}


@router.get("/journals")
async def list_journals(current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope, "active": True} if scope else {"active": True}
    return await db.accounting_journals.find(query, {"_id": 0}).sort("code", 1).to_list(200)


@router.post("/journals")
async def create_journal(data: dict, current_user: dict = Depends(require_director)):
    """Create a journal. Body: { code, name, kind: 'sales|purchases|bank|cash|miscellaneous',
    default_debit_account_id?, default_credit_account_id?, location_id? }"""
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    kind = (data.get("kind") or "miscellaneous").strip().lower()
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name required")
    if kind not in JOURNAL_KINDS:
        raise HTTPException(status_code=400, detail="Invalid journal kind")
    loc = data.get("location_id") or current_user.get("active_campus_id")
    existing = await db.accounting_journals.find_one({"location_id": loc, "code": code})
    if existing:
        raise HTTPException(status_code=400, detail=f"Journal code {code} already exists")
    doc = {
        "id": f"jrn_{uuid.uuid4().hex[:10]}",
        "code": code[:10],
        "name": name[:80],
        "kind": kind,
        "default_debit_account_id": data.get("default_debit_account_id"),
        "default_credit_account_id": data.get("default_credit_account_id"),
        "location_id": loc,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_journals.insert_one(doc)
    doc.pop("_id", None)
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
    has_entries = await db.accounting_entries.find_one({"journal_id": journal_id})
    if has_entries:
        await db.accounting_journals.update_one({"id": journal_id}, {"$set": {"active": False}})
        return {"deactivated": True}
    await db.accounting_journals.delete_one({"id": journal_id})
    return {"deleted": True}


# ============================================================
# FISCAL PERIODS
# ============================================================
@router.get("/fiscal-periods")
async def list_fiscal_periods(current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope} if scope else {}
    return await db.accounting_fiscal_periods.find(query, {"_id": 0}).sort("start_date", -1).to_list(100)


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
        "name": name[:60],
        "start_date": start,
        "end_date": end,
        "status": "open",  # open|closed|locked
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_fiscal_periods.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/fiscal-periods/{period_id}")
async def update_fiscal_period(period_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Update or change status (open|closed|locked). Locked periods block edits to entries within them."""
    allowed = {"name", "start_date", "end_date", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "status" in update and update["status"] not in {"open", "closed", "locked"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.accounting_fiscal_periods.update_one({"id": period_id}, {"$set": update})
    return await db.accounting_fiscal_periods.find_one({"id": period_id}, {"_id": 0})


async def _period_is_locked(date_iso: str, location_id: str) -> bool:
    p = await db.accounting_fiscal_periods.find_one({
        "location_id": location_id,
        "start_date": {"$lte": date_iso[:10]},
        "end_date": {"$gte": date_iso[:10]},
        "status": "locked",
    })
    return bool(p)


# ============================================================
# TAX CODES
# ============================================================
@router.get("/taxes")
async def list_taxes(current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope, "active": True} if scope else {"active": True}
    return await db.accounting_taxes.find(query, {"_id": 0}).sort("name", 1).to_list(100)


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
    doc = {
        "id": f"tax_{uuid.uuid4().hex[:10]}",
        "name": name[:60],
        "rate": rate,
        "kind": (data.get("kind") or "sales").strip().lower(),  # 'sales' (output) or 'purchase' (input)
        "inclusive": bool(data.get("inclusive", False)),
        "account_id": data.get("account_id"),  # account where tax accrues
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.accounting_taxes.insert_one(doc)
    doc.pop("_id", None)
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
    await db.accounting_taxes.update_one({"id": tax_id}, {"$set": update})
    return await db.accounting_taxes.find_one({"id": tax_id}, {"_id": 0})


@router.delete("/taxes/{tax_id}")
async def delete_tax(tax_id: str, current_user: dict = Depends(require_admin)):
    await db.accounting_taxes.delete_one({"id": tax_id})
    return {"deleted": True}


# ============================================================
# JOURNAL ENTRIES (double-entry ledger)
# ============================================================
@router.get("/entries")
async def list_entries(
    journal_id: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_reversed: bool = False,
    limit: int = 200,
    current_user: dict = Depends(require_finance_view),
):
    query = {}
    if journal_id:
        query["journal_id"] = journal_id
    if status:
        query["status"] = status
    if date_from or date_to:
        df = {}
        if date_from:
            df["$gte"] = date_from[:10]
        if date_to:
            df["$lte"] = date_to[:10]
        query["date"] = df
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    # Hide reversed pairs by default — the original AND its reversal both
    # carry linking metadata (`is_reversed=true` on original, `reverses=<id>`
    # on the reversal). Pass `?include_reversed=true` to unhide.
    if not include_reversed:
        query["is_reversed"] = {"$ne": True}
        query["reverses"] = {"$exists": False}
    return await db.accounting_entries.find(query, {"_id": 0}).sort("date", -1).to_list(min(limit, 1000))


async def _next_entry_number(journal_id: str) -> str:
    j = await db.accounting_journals.find_one({"id": journal_id}, {"_id": 0, "code": 1})
    code = (j or {}).get("code", "JRN")
    today = datetime.now(timezone.utc).strftime("%Y%m")
    counter_key = f"acc_entry_{journal_id}_{today}"
    counter = await db.counters.find_one_and_update(
        {"_id": counter_key}, {"$inc": {"seq": 1}}, upsert=True, return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    return f"{code}/{today}/{seq:04d}"


@router.post("/entries")
async def create_entry(data: dict, current_user: dict = Depends(require_director)):
    """Create a journal entry (draft).
    Body: {
      journal_id, date (YYYY-MM-DD), ref?, narration?, location_id?,
      lines: [ { account_id, debit, credit, description? } ]   <-- sum(debit) MUST == sum(credit)
    }"""
    journal_id = data.get("journal_id")
    if not journal_id:
        raise HTTPException(status_code=400, detail="journal_id required")
    journal = await db.accounting_journals.find_one({"id": journal_id}, {"_id": 0})
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    date = (data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    location_id = data.get("location_id") or journal.get("location_id") or current_user.get("active_campus_id")
    await _require_location_access(current_user, location_id)
    if await _period_is_locked(date, location_id):
        raise HTTPException(status_code=400, detail="Fiscal period is locked for this date")
    lines_in = data.get("lines") or []
    if len(lines_in) < 2:
        raise HTTPException(status_code=400, detail="At least 2 lines required for a valid entry")
    cleaned_lines = []
    total_debit = 0.0
    total_credit = 0.0
    for i, ln in enumerate(lines_in):
        if not ln.get("account_id"):
            raise HTTPException(status_code=400, detail=f"Line {i+1}: account_id required")
        try:
            debit = round(float(ln.get("debit") or 0), 2)
            credit = round(float(ln.get("credit") or 0), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Line {i+1}: debit/credit must be numeric")
        if debit < 0 or credit < 0:
            raise HTTPException(status_code=400, detail=f"Line {i+1}: amounts must be non-negative")
        if debit > 0 and credit > 0:
            raise HTTPException(status_code=400, detail=f"Line {i+1}: a line cannot be both debit and credit")
        if debit == 0 and credit == 0:
            raise HTTPException(status_code=400, detail=f"Line {i+1}: at least one of debit/credit must be > 0")
        cleaned_lines.append({
            "account_id": ln["account_id"],
            "debit": debit,
            "credit": credit,
            "description": (ln.get("description") or "")[:200],
        })
        total_debit += debit
        total_credit += credit
    total_debit = round(total_debit, 2)
    total_credit = round(total_credit, 2)
    if abs(total_debit - total_credit) > 0.01:
        raise HTTPException(status_code=400, detail=f"Entry is unbalanced: debit {total_debit} ≠ credit {total_credit}")
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal_id)
    entry = {
        "id": entry_id,
        "number": entry_number,
        "journal_id": journal_id,
        "journal_code": journal.get("code"),
        "date": date,
        "ref": (data.get("ref") or "")[:120],
        "narration": (data.get("narration") or "")[:500],
        "total_debit": total_debit,
        "total_credit": total_credit,
        "status": "draft",  # draft | posted | cancelled
        "location_id": location_id,
        "currency": data.get("currency") or "UGX",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    entry.pop("_id", None)
    # Persist lines separately for fast aggregation
    line_docs = []
    for ln in cleaned_lines:
        line_docs.append({
            "id": f"jel_{uuid.uuid4().hex[:10]}",
            "entry_id": entry_id,
            "entry_number": entry_number,
            "journal_id": journal_id,
            "date": date,
            "location_id": location_id,
            "status": "draft",
            **ln,
        })
    if line_docs:
        await db.accounting_entry_lines.insert_many(line_docs)
    entry["lines"] = cleaned_lines
    return entry


@router.get("/entries/{entry_id}")
async def get_entry(entry_id: str, current_user: dict = Depends(require_finance_view)):
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    entry["lines"] = await db.accounting_entry_lines.find({"entry_id": entry_id}, {"_id": 0}).to_list(100)
    # Enrich line accounts
    acc_ids = list({ln["account_id"] for ln in entry["lines"]})
    if acc_ids:
        accs = await db.accounting_accounts.find({"id": {"$in": acc_ids}}, {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(100)
        acc_map = {a["id"]: a for a in accs}
        for ln in entry["lines"]:
            a = acc_map.get(ln["account_id"]) or {}
            ln["account_code"] = a.get("code")
            ln["account_name"] = a.get("name")
    return entry


@router.post("/entries/{entry_id}/post")
async def post_entry(entry_id: str, current_user: dict = Depends(require_director)):
    """Move a draft entry to 'posted' (immutable). Locks the lines into the ledger."""
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry["status"] == "posted":
        return entry
    if entry["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot post a cancelled entry")
    if await _period_is_locked(entry["date"], entry.get("location_id")):
        raise HTTPException(status_code=400, detail="Fiscal period is locked")
    now = datetime.now(timezone.utc).isoformat()
    await db.accounting_entries.update_one({"id": entry_id}, {"$set": {"status": "posted", "posted_at": now, "posted_by": current_user["id"]}})
    await db.accounting_entry_lines.update_many({"entry_id": entry_id}, {"$set": {"status": "posted"}})
    return await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})


@router.post("/entries/{entry_id}/cancel")
async def cancel_entry(entry_id: str, current_user: dict = Depends(require_director)):
    """Cancel a draft. Posted entries cannot be cancelled — make a reverse entry instead."""
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only draft entries can be cancelled — make a reverse entry instead")
    await db.accounting_entries.update_one({"id": entry_id}, {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}})
    await db.accounting_entry_lines.update_many({"entry_id": entry_id}, {"$set": {"status": "cancelled"}})
    return {"cancelled": True}


@router.post("/entries/{entry_id}/reverse")
async def reverse_entry(entry_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    """Create a reverse entry (debits become credits and vice versa) on the given date.

    Idempotent — if the original was already reversed, returns the existing
    reversal instead of creating a duplicate. Marks the original with
    `is_reversed=true`, `reversed_by`, and `reversed_at` so UI filters can
    hide reversed pairs by default."""
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry["status"] != "posted":
        raise HTTPException(status_code=400, detail="Only posted entries can be reversed")
    # Guard against duplicates — user reported "some duplicated on reverse".
    if entry.get("is_reversed") and entry.get("reversed_by"):
        existing = await db.accounting_entries.find_one(
            {"id": entry["reversed_by"]}, {"_id": 0},
        )
        if existing:
            return existing  # idempotent — return the prior reversal
    data = data or {}
    rev_date = (data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    lines = await db.accounting_entry_lines.find({"entry_id": entry_id}, {"_id": 0}).to_list(200)
    rev_lines = [{"account_id": ln["account_id"], "debit": ln.get("credit", 0), "credit": ln.get("debit", 0), "description": f"Reversal of {entry['number']}: {ln.get('description','')}"} for ln in lines]
    new = await create_entry({
        "journal_id": entry["journal_id"],
        "date": rev_date,
        "ref": f"REV-{entry['number']}",
        "narration": f"Reversal of {entry['number']}",
        "lines": rev_lines,
        "location_id": entry.get("location_id"),
        "currency": entry.get("currency"),
    }, current_user)
    # Post the reversal immediately (matches the intent — a reversal in draft
    # state is useless, it needs to affect the ledger to cancel the original).
    now = datetime.now(timezone.utc).isoformat()
    await db.accounting_entries.update_one(
        {"id": new["id"]},
        {"$set": {
            "status": "posted",
            "posted_at": now,
            "posted_by": current_user["id"],
            "reverses": entry_id,  # link back to the original
        }},
    )
    # CRITICAL: also flip the LINES to posted so trial_balance / P&L include
    # them (they filter `status == "posted"` at the line level). Missing this
    # step was the root cause of "reversed transactions still showing as
    # income" in the Trial Balance / Net Profit reports.
    await db.accounting_entry_lines.update_many(
        {"entry_id": new["id"]},
        {"$set": {"status": "posted"}},
    )
    # Mark the ORIGINAL as reversed so the UI can hide it (this was the
    # missing step — user reported "original sale still shows as active").
    await db.accounting_entries.update_one(
        {"id": entry_id},
        {"$set": {
            "is_reversed": True,
            "reversed_by": new["id"],
            "reversed_at": datetime.now(timezone.utc).isoformat(),
            "reversed_by_user": current_user["id"],
        }},
    )
    new["reverses"] = entry_id
    new["status"] = "posted"
    return new


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str, current_user: dict = Depends(require_admin)):
    """Hard-delete a draft or cancelled journal entry. Posted entries must be reversed, not deleted."""
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.get("status") == "posted":
        raise HTTPException(status_code=400, detail="Posted entries cannot be deleted — reverse them instead")
    await db.accounting_entries.delete_one({"id": entry_id})
    await db.accounting_entry_lines.delete_many({"entry_id": entry_id})
    await _audit(current_user["id"], "delete", "accounting_entry", entry_id)
    return {"deleted": True}


@router.post("/entries/repair-reversal-lines")
async def repair_reversal_lines(current_user: dict = Depends(require_admin)):
    """One-time repair: reversals created before iter 206 left their
    accounting_entry_lines at status='draft' while the entry itself was
    posted. That caused Trial Balance / P&L / Net Profit to include the
    original but NOT the reversal — so already-reversed transactions kept
    showing up as income.

    This endpoint finds all posted entries whose lines are still draft and
    flips those lines to posted so reports finally net correctly."""
    fixed_ids = []
    async for entry in db.accounting_entries.find({"status": "posted"}, {"_id": 0, "id": 1}):
        eid = entry["id"]
        # Are any of this entry's lines still draft?
        drafted = await db.accounting_entry_lines.count_documents({"entry_id": eid, "status": {"$ne": "posted"}})
        if drafted:
            await db.accounting_entry_lines.update_many({"entry_id": eid}, {"$set": {"status": "posted"}})
            fixed_ids.append(eid)
    await _audit(current_user["id"], "repair", "accounting_entry_lines", None, {"count": len(fixed_ids)})
    return {"fixed_entries": len(fixed_ids), "entry_ids": fixed_ids[:100]}


@router.post("/entries/bulk-reverse")
async def bulk_reverse_entries(data: dict, current_user: dict = Depends(require_admin)):
    """Bulk-reverse posted journal entries. Skips already-reversed or non-posted ones."""
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    reversed_count = 0
    skipped_already = 0
    skipped_status = 0
    errors = []
    for eid in ids:
        entry = await db.accounting_entries.find_one({"id": eid}, {"_id": 0, "status": 1, "is_reversed": 1})
        if not entry:
            errors.append({"id": eid, "reason": "not_found"})
            continue
        if entry.get("status") != "posted":
            skipped_status += 1
            continue
        if entry.get("is_reversed"):
            skipped_already += 1
            continue
        try:
            await reverse_entry(eid, {}, current_user)
            reversed_count += 1
        except Exception as ex:
            errors.append({"id": eid, "reason": str(ex)[:120]})
    await _audit(current_user["id"], "bulk_reverse", "accounting_entries", None, {"count": reversed_count})
    return {
        "reversed": reversed_count,
        "skipped_already_reversed": skipped_already,
        "skipped_not_posted": skipped_status,
        "errors": errors,
    }


@router.post("/entries/bulk-delete")
async def bulk_delete_entries(data: dict, current_user: dict = Depends(require_admin)):
    """Bulk-delete draft/cancelled journal entries. Posted entries are skipped (must be reversed)."""
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    # Fetch matching entries once so we can distinguish missing vs posted vs deletable
    matching = await db.accounting_entries.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "status": 1}).to_list(len(ids))
    deletable_ids = [m["id"] for m in matching if m.get("status") != "posted"]
    skipped_posted = sum(1 for m in matching if m.get("status") == "posted")
    if deletable_ids:
        await db.accounting_entries.delete_many({"id": {"$in": deletable_ids}})
        await db.accounting_entry_lines.delete_many({"entry_id": {"$in": deletable_ids}})
    await _audit(current_user["id"], "bulk_delete", "accounting_entries", None, {"count": len(deletable_ids), "skipped_posted": skipped_posted})
    return {"deleted": len(deletable_ids), "skipped_posted": skipped_posted}


# ============================================================
# REPORTS: TRIAL BALANCE + P&L + BALANCE SHEET
# ============================================================
async def _expand_location_scope(location_id: str) -> list:
    """Return a list of location IDs that should be considered "within" the
    given location for reporting.  Walks the tree recursively (bounded to
    depth 3) to include: the picked id, ALL descendants (children, grand-
    children), and ancestors (parent, grandparent).

    Rationale (iter222 production bug): payroll/expense auto-postings often
    tag entries with a sub-location id, while operators pick campuses in the
    report filter — strict equality would hide those very transactions.
    """
    ids = {location_id}
    # Walk downward — collect descendants up to depth 3
    frontier = {location_id}
    for _ in range(3):
        if not frontier:
            break
        subs = await db.locations.find(
            {"parent_id": {"$in": list(frontier)}}, {"_id": 0, "id": 1}
        ).to_list(500)
        frontier = {s["id"] for s in subs if s["id"] not in ids}
        ids.update(frontier)
    # Walk upward — collect ancestors up to depth 3
    current = location_id
    for _ in range(3):
        node = await db.locations.find_one({"id": current}, {"_id": 0, "parent_id": 1})
        if not node or not node.get("parent_id"):
            break
        current = node["parent_id"]
        ids.add(current)
    return list(ids)


@router.get("/reports/trial-balance")
async def trial_balance(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_finance_view),
):
    """Trial Balance — totals of debit/credit per account from posted entries.
    Defaults to all posted entries up to today."""
    match = {"status": "posted"}
    if date_from:
        match.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        match.setdefault("date", {})["$lte"] = date_to[:10]
    if location_id:
        scope_ids = await _expand_location_scope(location_id)
        match["location_id"] = {"$in": scope_ids} if len(scope_ids) > 1 else location_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            match.update(scope)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$account_id",
            "debit": {"$sum": "$debit"},
            "credit": {"$sum": "$credit"},
        }},
    ]
    grouped = await db.accounting_entry_lines.aggregate(pipeline).to_list(2000)
    accounts = await db.accounting_accounts.find({}, {"_id": 0}).to_list(2000)
    acc_map = {a["id"]: a for a in accounts}
    rows = []
    total_debit = 0.0
    total_credit = 0.0
    for g in grouped:
        acc = acc_map.get(g["_id"]) or {}
        meta = ACCOUNT_TYPES.get(acc.get("type", ""), {})
        debit = round(g.get("debit") or 0, 2)
        credit = round(g.get("credit") or 0, 2)
        balance = round(debit - credit, 2)
        rows.append({
            "account_id": g["_id"],
            "code": acc.get("code", ""),
            "name": acc.get("name", "(deleted)"),
            "type": acc.get("type", ""),
            "category": meta.get("category", ""),
            "normal_balance": meta.get("normal_balance", "debit"),
            "debit": debit,
            "credit": credit,
            "balance": balance,
        })
        total_debit += debit
        total_credit += credit
    rows.sort(key=lambda r: r.get("code") or "")
    return {
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "totals": {
            "debit": round(total_debit, 2),
            "credit": round(total_credit, 2),
            "balanced": abs(total_debit - total_credit) < 0.01,
        },
    }


@router.get("/reports/profit-loss")
async def profit_loss(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_finance_view),
):
    """P&L for a period: sums income and expense accounts, returns net profit."""
    tb = await trial_balance(date_from=date_from, date_to=date_to, location_id=location_id, current_user=current_user)
    income_rows = [r for r in tb["rows"] if r["category"] == "income"]
    expense_rows = [r for r in tb["rows"] if r["category"] == "expense"]
    # Income: normal credit balance — use credit - debit
    total_income = round(sum(r["credit"] - r["debit"] for r in income_rows), 2)
    total_expense = round(sum(r["debit"] - r["credit"] for r in expense_rows), 2)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "income": income_rows,
        "expense": expense_rows,
        "totals": {
            "income": total_income,
            "expense": total_expense,
            "net_profit": round(total_income - total_expense, 2),
        },
    }


@router.get("/reports/balance-sheet")
async def balance_sheet(
    as_of: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_finance_view),
):
    """Balance Sheet at a given date — assets vs. liabilities + equity."""
    tb = await trial_balance(date_to=as_of, location_id=location_id, current_user=current_user)
    assets = [r for r in tb["rows"] if r["category"] == "asset"]
    liabilities = [r for r in tb["rows"] if r["category"] == "liability"]
    equity = [r for r in tb["rows"] if r["category"] == "equity"]
    # Net profit (income - expense) is added to equity for the BS
    pl = await profit_loss(date_to=as_of, location_id=location_id, current_user=current_user)
    total_assets = round(sum(r["debit"] - r["credit"] for r in assets), 2)
    total_liabilities = round(sum(r["credit"] - r["debit"] for r in liabilities), 2)
    total_equity = round(sum(r["credit"] - r["debit"] for r in equity), 2) + pl["totals"]["net_profit"]
    return {
        "as_of": as_of,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "totals": {
            "assets": total_assets,
            "liabilities": total_liabilities,
            "equity": round(total_equity, 2),
            "retained_net_profit": pl["totals"]["net_profit"],
            "balanced": abs(total_assets - (total_liabilities + total_equity)) < 0.01,
        },
    }


@router.get("/accounts/{account_id}/ledger")
async def account_ledger(
    account_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
    current_user: dict = Depends(require_finance_view),
):
    """Per-account ledger: chronological list of postings + running balance."""
    acc = await db.accounting_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    q = {"account_id": account_id, "status": "posted"}
    if date_from:
        q.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        q.setdefault("date", {})["$lte"] = date_to[:10]
    lines = await db.accounting_entry_lines.find(q, {"_id": 0}).sort("date", 1).to_list(min(limit, 2000))
    # Enrich with entry narration
    entry_ids = list({ln["entry_id"] for ln in lines})
    entries = await db.accounting_entries.find({"id": {"$in": entry_ids}}, {"_id": 0, "id": 1, "number": 1, "narration": 1, "ref": 1}).to_list(min(limit, 2000)) if entry_ids else []
    e_map = {e["id"]: e for e in entries}
    running = 0.0
    out = []
    for ln in lines:
        running += (ln.get("debit") or 0) - (ln.get("credit") or 0)
        e = e_map.get(ln["entry_id"]) or {}
        out.append({**ln, "entry_number": e.get("number"), "narration": e.get("narration"), "ref": e.get("ref"), "running_balance": round(running, 2)})
    return {"account": acc, "lines": out, "ending_balance": round(running, 2)}


# ============================================================
# ASSET DEPRECIATION SCHEDULES
# ============================================================

@router.get("/assets/{asset_id}/depreciation-schedule")
async def asset_depreciation_schedule(asset_id: str, method: str = "straight_line", current_user: dict = Depends(require_finance_view)):
    """Generate a depreciation schedule for an asset (straight-line or declining-balance).
    Doesn't mutate anything — pure projection for review/printing.
    Methods:
      • straight_line: equal monthly portion across (depreciation_years × 12) months
      • declining_balance: 2× straight-line rate applied to remaining book value
    """
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    years = int(asset.get("depreciation_years") or 0)
    if years <= 0:
        raise HTTPException(status_code=400, detail="Asset has no depreciation_years set")
    initial = float(asset.get("value") or asset.get("current_value") or asset.get("purchase_value") or 0)
    if initial <= 0:
        raise HTTPException(status_code=400, detail="Asset has no value")
    start = (asset.get("purchase_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    try:
        from datetime import date as dt_date
        sd = dt_date.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid purchase_date")
    months = years * 12
    schedule = []
    if method == "declining_balance":
        rate = (1 / years) * 2
        book = initial
        for m in range(months):
            month_dep = round(book * (rate / 12), 2)
            # last month: write down to ~0 if it would go negative
            if m == months - 1 and book - month_dep > 0.01:
                month_dep = round(book, 2)
            book = round(max(0.0, book - month_dep), 2)
            y, mo = sd.year + (sd.month - 1 + m) // 12, ((sd.month - 1 + m) % 12) + 1
            schedule.append({
                "month_index": m + 1,
                "period": f"{y:04d}-{mo:02d}",
                "depreciation": month_dep,
                "book_value": book,
            })
    else:
        # Straight-line
        monthly = round(initial / months, 2)
        book = initial
        for m in range(months):
            # last month catches rounding drift
            month_dep = monthly if m < months - 1 else round(book, 2)
            book = round(max(0.0, book - month_dep), 2)
            y, mo = sd.year + (sd.month - 1 + m) // 12, ((sd.month - 1 + m) % 12) + 1
            schedule.append({
                "month_index": m + 1,
                "period": f"{y:04d}-{mo:02d}",
                "depreciation": month_dep,
                "book_value": book,
            })
    total_dep = round(sum(s["depreciation"] for s in schedule), 2)
    return {
        "asset_id": asset_id,
        "asset_name": asset.get("name"),
        "method": method,
        "initial_value": initial,
        "months": months,
        "total_depreciation": total_dep,
        "schedule": schedule,
    }


@router.post("/assets/{asset_id}/depreciate/{period}")
async def post_asset_depreciation(asset_id: str, period: str, data: dict = None, current_user: dict = Depends(require_director)):
    """Post a depreciation journal entry for one period (YYYY-MM) for an asset.
    Debits 'Depreciation Expense' (expense_depreciation), credits 'Accumulated Depreciation' (asset_fixed account named 'Accumulated Depreciation').
    Idempotent — skips if an entry for this asset+period already exists."""
    data = data or {}
    method = data.get("method") or "straight_line"
    # Get the schedule and find the month
    schedule_resp = await asset_depreciation_schedule(asset_id, method=method, current_user=current_user)
    line = next((s for s in schedule_resp["schedule"] if s["period"] == period), None)
    if not line:
        raise HTTPException(status_code=400, detail=f"Period {period} not in asset's depreciation schedule")
    amount = line["depreciation"]
    if amount <= 0:
        return {"skipped": True, "reason": "no depreciation in this period"}
    # Idempotency
    existing = await db.accounting_entries.find_one({
        "auto_generated_from": "asset_depreciation",
        "source_id": asset_id,
        "period": period,
    }, {"_id": 0})
    if existing:
        return {"skipped": True, "reason": "already posted", "entry_id": existing["id"]}
    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    loc_id = asset.get("location_id")
    # Find depreciation expense account + accumulated depreciation account
    dep_exp = await db.accounting_accounts.find_one({"location_id": loc_id, "type": "expense_depreciation", "active": True}, {"_id": 0, "id": 1})
    acc_dep = await db.accounting_accounts.find_one({"location_id": loc_id, "name": {"$regex": "accumulated", "$options": "i"}, "active": True}, {"_id": 0, "id": 1})
    if not dep_exp or not acc_dep:
        raise HTTPException(status_code=400, detail="Configure CoA: need a 'Depreciation Expense' account and an 'Accumulated Depreciation' account")
    # Pick a journal — prefer miscellaneous
    journal = await db.accounting_journals.find_one({"location_id": loc_id, "kind": "miscellaneous", "active": True}, {"_id": 0})
    if not journal:
        journal = await db.accounting_journals.find_one({"location_id": loc_id, "active": True}, {"_id": 0})
    if not journal:
        raise HTTPException(status_code=400, detail="No journal configured for this location")
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal["id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": entry_id, "number": entry_number, "journal_id": journal["id"], "journal_code": journal.get("code"),
        "date": f"{period}-15", "ref": f"DEP-{asset.get('name','')}-{period}",
        "narration": f"Depreciation of {asset.get('name','asset')} for {period} ({method})",
        "total_debit": amount, "total_credit": amount, "status": "posted",
        "location_id": loc_id, "currency": "UGX",
        "auto_generated_from": "asset_depreciation", "source_id": asset_id, "period": period,
        "created_at": now_iso, "posted_at": now_iso, "posted_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    await db.accounting_entry_lines.insert_many([
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": entry["date"], "location_id": loc_id, "status": "posted",
         "account_id": dep_exp["id"], "debit": amount, "credit": 0, "description": entry["narration"]},
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": entry["date"], "location_id": loc_id, "status": "posted",
         "account_id": acc_dep["id"], "debit": 0, "credit": amount, "description": "Accumulated depreciation"},
    ])
    # Also reduce current_value on the asset record itself
    await db.assets.update_one({"id": asset_id}, {"$set": {"current_value": line["book_value"]}})
    entry.pop("_id", None)
    return entry



# ============================================================
# PHASE D — UGANDA-SPECIFIC + UNIVERSAL ADVANCED REPORTS
# ============================================================

@router.get("/reports/cash-flow")
async def cash_flow_statement(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_finance_view),
):
    """Indirect-method cash flow statement: classifies postings into operating /
    investing / financing based on the *other* account's type in each posting.

    Operating: postings against income/expense accounts
    Investing: postings against fixed-asset accounts
    Financing: postings against equity / non-current-liability accounts
    """
    match = {"status": "posted"}
    if date_from:
        match.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        match.setdefault("date", {})["$lte"] = date_to[:10]
    if location_id:
        scope_ids = await _expand_location_scope(location_id)
        match["location_id"] = {"$in": scope_ids} if len(scope_ids) > 1 else location_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            match.update(scope)
    # We classify CASH movements: find lines hitting cash accounts, look at the
    # paired (other-side) line in the same entry.
    cash_accs = await db.accounting_accounts.find(
        {"type": "asset_cash", "active": True}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(200)
    if not cash_accs:
        return {"date_from": date_from, "date_to": date_to,
                "operating": [], "investing": [], "financing": [],
                "totals": {"operating": 0, "investing": 0, "financing": 0, "net_change": 0}}
    cash_ids = {a["id"] for a in cash_accs}
    cash_lines = await db.accounting_entry_lines.find(
        {**match, "account_id": {"$in": list(cash_ids)}}, {"_id": 0},
    ).to_list(5000)
    # For each cash line, fetch siblings in the same entry and classify
    entry_ids = list({L["entry_id"] for L in cash_lines})
    all_lines = await db.accounting_entry_lines.find(
        {"entry_id": {"$in": entry_ids}}, {"_id": 0},
    ).to_list(20000) if entry_ids else []
    lines_by_entry = {}
    for L in all_lines:
        lines_by_entry.setdefault(L["entry_id"], []).append(L)
    # Build account-id → type map
    all_acc_ids = {L["account_id"] for L in all_lines}
    accs = await db.accounting_accounts.find(
        {"id": {"$in": list(all_acc_ids)}}, {"_id": 0, "id": 1, "name": 1, "type": 1, "code": 1},
    ).to_list(2000) if all_acc_ids else []
    acc_map = {a["id"]: a for a in accs}
    operating = {}
    investing = {}
    financing = {}
    for L in cash_lines:
        cash_delta = float(L.get("debit") or 0) - float(L.get("credit") or 0)  # positive = cash in
        siblings = [s for s in lines_by_entry.get(L["entry_id"], []) if s["id"] != L["id"]]
        for s in siblings:
            sib_acc = acc_map.get(s["account_id"]) or {}
            sib_type = sib_acc.get("type", "")
            sib_category = ACCOUNT_TYPES.get(sib_type, {}).get("category", "")
            # The amount attributed to this sibling
            sib_amount = float(s.get("credit") or 0) - float(s.get("debit") or 0)
            # If multiple siblings, allocate proportionally (rare for our entries — most are 1:1)
            if cash_delta != 0 and sib_amount == 0:
                continue
            label = f"{sib_acc.get('code','')} {sib_acc.get('name','(unknown)')}".strip()
            attribution = sib_amount  # Sign: positive = cash in from this source
            if sib_type == "asset_fixed":
                bucket = investing
            elif sib_category == "equity" or sib_type == "liability_non_current":
                bucket = financing
            else:  # income/expense/AR/AP/current-asset/current-liability → operating
                bucket = operating
            bucket[label] = bucket.get(label, 0) + attribution
    def _to_rows(d):
        return [{"account": k, "amount": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -abs(kv[1]))]
    op_total = round(sum(operating.values()), 2)
    inv_total = round(sum(investing.values()), 2)
    fin_total = round(sum(financing.values()), 2)
    return {
        "date_from": date_from,
        "date_to": date_to,
        "operating": _to_rows(operating),
        "investing": _to_rows(investing),
        "financing": _to_rows(financing),
        "totals": {
            "operating": op_total,
            "investing": inv_total,
            "financing": fin_total,
            "net_change": round(op_total + inv_total + fin_total, 2),
        },
    }


def _age_bucket(days_old: int) -> str:
    if days_old <= 30:
        return "0-30"
    if days_old <= 60:
        return "31-60"
    if days_old <= 90:
        return "61-90"
    return "90+"


@router.get("/reports/ar-aging")
async def ar_aging(as_of: Optional[str] = None, location_id: Optional[str] = None,
                  current_user: dict = Depends(require_finance_view)):
    """Accounts receivable aging — buckets sales' outstanding amounts by age."""
    today = (as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    query = {"payment_status": "pending", "voided": {"$ne": True}}
    if location_id:
        query["location_id"] = location_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    sales = await db.sales.find(query, {"_id": 0}).to_list(5000)
    today_dt = dt_date.fromisoformat(today)
    by_customer = {}
    bucket_totals = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0, "total": 0}
    for s in sales:
        try:
            sale_date = dt_date.fromisoformat((s.get("created_at") or s.get("date", ""))[:10])
        except Exception:
            sale_date = today_dt
        age = (today_dt - sale_date).days
        b = _age_bucket(age)
        amt = float(s.get("total") or 0)
        bucket_totals[b] += amt
        bucket_totals["total"] += amt
        key = s.get("customer_id") or s.get("customer_phone") or s.get("customer_name") or "Walk-in"
        if key not in by_customer:
            by_customer[key] = {
                "customer_id": s.get("customer_id"),
                "customer_name": s.get("customer_name") or "Walk-in",
                "customer_phone": s.get("customer_phone"),
                "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0, "total": 0,
                "oldest_days": 0,
                "sales_count": 0,
            }
        row = by_customer[key]
        row[b] += amt
        row["total"] += amt
        row["oldest_days"] = max(row["oldest_days"], age)
        row["sales_count"] += 1
    # Round
    for r in by_customer.values():
        for b in ("0-30", "31-60", "61-90", "90+", "total"):
            r[b] = round(r[b], 2)
    rows = sorted(by_customer.values(), key=lambda r: -r["total"])
    return {
        "as_of": today,
        "rows": rows,
        "totals": {k: round(v, 2) for k, v in bucket_totals.items()},
    }


@router.get("/reports/ap-aging")
async def ap_aging(as_of: Optional[str] = None, location_id: Optional[str] = None,
                  current_user: dict = Depends(require_finance_view)):
    """Accounts payable aging — bills outstanding by age (from due_date)."""
    today = (as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    query = {"status": {"$in": ["open", "partially_paid"]}}
    if location_id:
        query["location_id"] = location_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    bills = await db.bills.find(query, {"_id": 0}).to_list(5000)
    today_dt = dt_date.fromisoformat(today)
    by_vendor = {}
    bucket_totals = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0, "total": 0}
    for b in bills:
        try:
            due_dt = dt_date.fromisoformat((b.get("due_date") or b.get("bill_date", ""))[:10])
        except Exception:
            due_dt = today_dt
        age = (today_dt - due_dt).days  # positive = past due
        bucket = _age_bucket(max(0, age))
        amt = float(b.get("balance") or 0)
        bucket_totals[bucket] += amt
        bucket_totals["total"] += amt
        key = b.get("vendor_id") or b.get("vendor_name") or "unknown"
        if key not in by_vendor:
            by_vendor[key] = {
                "vendor_id": b.get("vendor_id"),
                "vendor_name": b.get("vendor_name"),
                "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0, "total": 0,
                "oldest_days": 0,
                "bills_count": 0,
            }
        row = by_vendor[key]
        row[bucket] += amt
        row["total"] += amt
        row["oldest_days"] = max(row["oldest_days"], age)
        row["bills_count"] += 1
    for r in by_vendor.values():
        for k in ("0-30", "31-60", "61-90", "90+", "total"):
            r[k] = round(r[k], 2)
    rows = sorted(by_vendor.values(), key=lambda r: -r["total"])
    return {
        "as_of": today,
        "rows": rows,
        "totals": {k: round(v, 2) for k, v in bucket_totals.items()},
    }


# ============================================================
# MULTI-CURRENCY REVALUATION
# ============================================================
@router.post("/fx/revalue")
async def revalue_currencies(data: dict, current_user: dict = Depends(require_director)):
    """End-of-period FX revaluation. Posts unrealized FX gain/loss for accounts
    held in foreign currencies vs the campus's functional currency.

    Body: { as_of (YYYY-MM-DD), rates: { 'USD': 3700, 'KES': 28, ... },
            functional_currency: 'UGX', location_id }

    For each FX-denominated CoA account, compares the balance at the supplied
    rate to the historical book value (which is implicit in the entries' UGX
    amounts). The difference is posted as an unrealized FX gain or loss."""
    as_of = (data.get("as_of") or "")[:10]
    rates = data.get("rates") or {}
    functional = (data.get("functional_currency") or "UGX").upper()
    loc_id = data.get("location_id") or current_user.get("active_campus_id")
    if not as_of:
        raise HTTPException(status_code=400, detail="as_of required")
    if not rates:
        raise HTTPException(status_code=400, detail="rates required")
    if not loc_id:
        raise HTTPException(status_code=400, detail="location_id required")
    # Find FX accounts: any account whose currency differs from functional
    fx_accs = await db.accounting_accounts.find(
        {"location_id": loc_id, "active": True, "currency": {"$nin": [functional, "", None]}},
        {"_id": 0},
    ).to_list(500)
    if not fx_accs:
        return {"posted": 0, "note": "No foreign-currency accounts found"}
    # Find / create FX gain & loss accounts
    fx_gain = await db.accounting_accounts.find_one(
        {"location_id": loc_id, "active": True, "name": {"$regex": "fx gain|fx revaluation gain|forex gain", "$options": "i"}},
        {"_id": 0},
    )
    fx_loss = await db.accounting_accounts.find_one(
        {"location_id": loc_id, "active": True, "name": {"$regex": "fx loss|fx revaluation loss|forex loss", "$options": "i"}},
        {"_id": 0},
    )
    if not fx_gain or not fx_loss:
        raise HTTPException(
            status_code=400,
            detail="Create CoA accounts 'FX Revaluation Gain' (type=income_other) and 'FX Revaluation Loss' (type=expense) first",
        )
    journal = (await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": "miscellaneous", "active": True}, {"_id": 0}
    )) or (await db.accounting_journals.find_one(
        {"location_id": loc_id, "active": True}, {"_id": 0}
    ))
    if not journal:
        raise HTTPException(status_code=400, detail="No journal configured")
    posted_entries = []
    for acc in fx_accs:
        currency = acc.get("currency", "")
        rate = float(rates.get(currency, 0))
        if not rate:
            continue  # No rate supplied → skip
        # Current local balance from posted entries
        agg = await db.accounting_entry_lines.aggregate([
            {"$match": {"account_id": acc["id"], "status": "posted", "date": {"$lte": as_of}}},
            {"$group": {"_id": None, "d": {"$sum": "$debit"}, "c": {"$sum": "$credit"}}},
        ]).to_list(1)
        if not agg:
            continue
        book_value_fc = round(agg[0]["d"] - agg[0]["c"], 2)  # in functional currency (UGX)
        if book_value_fc == 0:
            continue
        # We need the FX balance — but we don't have it stored. Heuristic: assume
        # the recorded debit/credit amounts ARE in functional currency. To revalue,
        # treat the account's natural-FX balance as book_value_fc / historical_rate
        # — since we don't track historical rates per-line, we just expose the
        # diff = book_value_fc * (rate / historical_rate - 1). Without history,
        # the caller supplies BOTH 'current_rate' (in `rates`) AND optional
        # 'historical_rate' overrides. If only one rate is given, we assume the
        # historical rate is 1 (i.e., the book value is the FX balance) and
        # convert at the new rate.
        hist_rate = float(data.get("historical_rates", {}).get(currency) or 1)
        new_local = book_value_fc * rate / hist_rate
        diff = round(new_local - book_value_fc, 2)
        if abs(diff) < 0.01:
            continue
        # Post: Dr/Cr the FX account by diff, opposite side to FX gain/loss
        is_gain = diff > 0
        from routers.accounting import _next_entry_number
        entry_id = f"je_{uuid.uuid4().hex[:10]}"
        entry_number = await _next_entry_number(journal["id"])
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": entry_id, "number": entry_number,
            "journal_id": journal["id"], "journal_code": journal.get("code"),
            "date": as_of, "ref": f"FX-{currency}-{as_of}",
            "narration": f"FX revaluation: {acc.get('name')} ({currency} @ {rate})",
            "total_debit": abs(diff), "total_credit": abs(diff), "status": "posted",
            "location_id": loc_id, "currency": functional,
            "auto_generated_from": "fx_revaluation", "source_id": f"{acc['id']}_{as_of}",
            "created_at": now_iso, "posted_at": now_iso, "posted_by": current_user["id"],
        }
        await db.accounting_entries.insert_one(entry)
        gain_or_loss = fx_gain if is_gain else fx_loss
        if is_gain:
            # Asset gains: Dr Asset / Cr FX Gain. Liabilities reversed.
            debit_acc, credit_acc = acc["id"], gain_or_loss["id"]
        else:
            debit_acc, credit_acc = gain_or_loss["id"], acc["id"]
        await db.accounting_entry_lines.insert_many([
            {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
             "journal_id": journal["id"], "date": as_of, "location_id": loc_id, "status": "posted",
             "account_id": debit_acc, "debit": abs(diff), "credit": 0, "description": entry["narration"]},
            {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
             "journal_id": journal["id"], "date": as_of, "location_id": loc_id, "status": "posted",
             "account_id": credit_acc, "debit": 0, "credit": abs(diff), "description": entry["narration"]},
        ])
        posted_entries.append({"account_id": acc["id"], "currency": currency, "diff": diff, "entry_id": entry_id})
    await _audit(current_user["id"], "create", "fx_revaluation", as_of, {"count": len(posted_entries)})
    return {"posted": len(posted_entries), "entries": posted_entries}


# ============================================================
# UGANDA VAT / EFRIS EXPORT
# ============================================================
@router.get("/reports/uganda-vat-export")
async def uganda_vat_export(
    date_from: str,
    date_to: str,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Export VAT-relevant transactions in URA EFRIS-compatible CSV format.

    URA EFRIS (Electronic Fiscal Receipting & Invoicing System) requires monthly
    VAT returns with sales invoices + purchase bills. This endpoint produces a
    CSV with one row per VAT-bearing transaction.
    """
    from starlette.responses import StreamingResponse
    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="date_from and date_to required")
    query_sales = {
        "voided": {"$ne": True},
        "created_at": {"$gte": date_from + "T00:00:00", "$lte": date_to + "T23:59:59.999"},
    }
    query_bills = {
        "bill_date": {"$gte": date_from, "$lte": date_to},
        "status": {"$ne": "void"},
    }
    if location_id:
        query_sales["location_id"] = location_id
        query_bills["location_id"] = location_id
    sales = await db.sales.find(query_sales, {"_id": 0}).to_list(5000)
    bills = await db.bills.find(query_bills, {"_id": 0}).to_list(5000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Type", "Date", "Invoice/Bill No", "Counterparty", "TIN",
        "Subtotal (excl VAT)", "VAT Amount", "Total", "Currency", "Description",
    ])
    # Sales (output VAT)
    for s in sales:
        sub = float(s.get("subtotal") or 0)
        tax = float(s.get("tax_amount") or 0)
        # If subtotal is missing, derive it from items
        if not sub and s.get("items"):
            sub = sum((float(i.get("qty", 0) or 0) * float(i.get("unit_price", 0) or 0)) for i in s["items"])
        writer.writerow([
            "Sale",
            (s.get("created_at") or "")[:10],
            s.get("receipt_number") or s.get("id"),
            s.get("customer_name") or "Walk-in",
            s.get("customer_tin", ""),
            f"{sub:.2f}",
            f"{tax:.2f}",
            f"{float(s.get('total') or 0):.2f}",
            s.get("currency") or "UGX",
            (s.get("notes") or "")[:200],
        ])
    # Bills (input VAT)
    for b in bills:
        writer.writerow([
            "Purchase",
            (b.get("bill_date") or "")[:10],
            b.get("bill_number") or b.get("id"),
            b.get("vendor_name") or "(unknown)",
            b.get("vendor_tin", ""),
            f"{float(b.get('subtotal') or 0):.2f}",
            f"{float(b.get('tax_amount') or 0):.2f}",
            f"{float(b.get('total') or 0):.2f}",
            b.get("currency") or "UGX",
            (b.get("notes") or "")[:200],
        ])
    buf.seek(0)
    filename = f"uganda-vat-{date_from}-to-{date_to}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

