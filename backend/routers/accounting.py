"""Accounting depth (Odoo-style): Chart of Accounts, Journals, Double-entry Ledger,
Fiscal Periods, Tax Codes, Trial Balance + P&L."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_director, require_admin, _audit, logger, get_campus_filter
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


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
async def list_account_types(current_user: dict = Depends(get_current_user)):
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


@router.get("/accounts")
async def list_accounts(
    location_id: Optional[str] = None,
    category: Optional[str] = None,
    active: bool = True,
    current_user: dict = Depends(get_current_user),
):
    query = {}
    if active:
        query["active"] = True
    if location_id:
        query["location_id"] = location_id
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
async def list_journals(current_user: dict = Depends(get_current_user)):
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
async def list_fiscal_periods(current_user: dict = Depends(get_current_user)):
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
async def list_taxes(current_user: dict = Depends(get_current_user)):
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
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
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
async def get_entry(entry_id: str, current_user: dict = Depends(get_current_user)):
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
    """Create a reverse entry (debits become credits and vice versa) on the given date."""
    entry = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry["status"] != "posted":
        raise HTTPException(status_code=400, detail="Only posted entries can be reversed")
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
    return new


# ============================================================
# REPORTS: TRIAL BALANCE + P&L + BALANCE SHEET
# ============================================================
@router.get("/reports/trial-balance")
async def trial_balance(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Trial Balance — totals of debit/credit per account from posted entries.
    Defaults to all posted entries up to today."""
    match = {"status": "posted"}
    if date_from:
        match.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        match.setdefault("date", {})["$lte"] = date_to[:10]
    if location_id:
        match["location_id"] = location_id
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
