"""Financial routes: donations, expenses, products, sales, cashflow, balance, approval workflow"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from deps import db, get_current_user, require_staff, require_manager, require_director, require_admin, _audit, logger, is_system_admin, get_campus_filter, get_role_level, require_finance_view, require_finance_admin
from datetime import datetime, timezone
from typing import Optional, List
import uuid

async def _financial_campus_filter(user: dict) -> dict:
    """Financial data access: enforces need-to-know.
    - System admins/EDs/Advisers: see all
    - Directors: see entire campus
    - Finance dept staff: see entire campus
    - Managers at sub-location: see only their sub-location
    - Others: no access"""
    role = user.get("role", "")
    if is_system_admin(user) or role in ("Executive Director", "Adviser"):
        return {}
    if role == "Director":
        return await get_campus_filter(user)
    depts = [d.lower() for d in (user.get("departments") or [])]
    dept = (user.get("department") or "").lower()
    is_finance = "finance" in depts or dept == "finance"
    if is_finance:
        return await get_campus_filter(user)
    role_level = get_role_level(role)
    if role_level >= 7:  # Manager
        # Restrict to their primary location (sub-location)
        loc_id = user.get("active_campus_id") or user.get("location_id") or ""
        return {"location_id": loc_id} if loc_id else await get_campus_filter(user)
    return {"location_id": "__no_access__"}


router = APIRouter(prefix="/api", tags=["financial"])


# ========== SELF-SERVICE EDIT/DELETE WINDOW (iter220) ==========
# By popular request: any user who created a financial record (donation,
# expense) can edit or delete it within 7 days of entry without needing
# admin.  After the window closes, only admins can modify.
SELF_EDIT_WINDOW_DAYS = 7


def _is_finance_admin(user: dict) -> bool:
    role = (user.get("role") or "")
    return role in {"admin", "system_admin", "Executive Director", "Adviser", "Director"}


def _within_self_edit_window(doc: dict, user: dict) -> tuple[bool, str]:
    """Return (allowed, reason_if_denied).  Admins bypass everything.
    Otherwise: creator + within 7-day window."""
    if _is_finance_admin(user):
        return True, ""
    if not doc:
        return False, "Record not found"
    if doc.get("created_by") != user.get("id"):
        return False, "Only the record's creator or an administrator can modify it"
    created_at = doc.get("created_at") or ""
    if not created_at:
        return False, "Record has no creation timestamp — ask an admin to update it"
    try:
        # Handle both 'Z' suffix and offset formats
        s = created_at.rstrip("Z")
        created_dt = datetime.fromisoformat(s)
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False, "Invalid creation timestamp"
    age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
    if age_days > SELF_EDIT_WINDOW_DAYS:
        return False, f"Edit window closed ({SELF_EDIT_WINDOW_DAYS} days) — ask an administrator"
    return True, ""


class DonationCreate(BaseModel):
    donor_name: str; amount: float; currency: str = "UGX"; type: str = "tithe"
    date: Optional[str] = None; notes: str = ""; member_id: Optional[str] = None
    location_id: Optional[str] = None; sublocation_id: Optional[str] = None
    deposit_to_account_id: Optional[str] = None  # FK → chart_accounts.id (which cash/bank account received this)

    @field_validator("amount", mode="before")
    @classmethod
    def _blank_to_none_or_float(cls, v, info):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, str):
            try: return float(v.strip())
            except ValueError: return v
        return v

class ExpenseCreate(BaseModel):
    title: str; amount: float; currency: str = "UGX"; category: str = "general"
    date: Optional[str] = None; notes: str = ""; submitted_by: Optional[str] = None
    location_id: Optional[str] = None; sublocation_id: Optional[str] = None
    # Extended fields aligned with 58:12 Global budget spreadsheet columns
    vendor: Optional[str] = None  # Who was paid (e.g. "Bulunzi bugagga farm supply")
    purpose: Optional[str] = None  # Purpose/Beneficiary/Notes — free text
    receipt_number: Optional[str] = None  # Reff./Receipt# for reconciliation
    account: Optional[str] = None  # Payment source label (legacy free-text/enum)
    paid_from_account_id: Optional[str] = None  # FK → financial_accounts.id (which cash/bank account funded this expense)
    department: Optional[str] = None  # FARM, SHELTER, OUTREACH, ADMIN/OPS, SECURITY, EDUCATION, MAINTENANCE
    budget_category: Optional[str] = None  # Uganda Farm, Petty Cash, Wages & Salaries, Bank Fees, etc.
    usd_equivalent: Optional[float] = None  # For multi-currency tracking
    exchange_rate: Optional[float] = None  # UGX per USD

    # Pydantic v2 by default rejects empty-string for Optional[float] with "input should
    # be a valid number, unable to parse string as a number". This bit non-admin
    # expense entries hard because the FE blanks out unused fields rather than omitting
    # them. Coerce '', None, ' ' to None up front so the field stays validly absent.
    @field_validator("amount", "usd_equivalent", "exchange_rate", mode="before")
    @classmethod
    def _blank_to_none_or_float(cls, v, info):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if not s:
                # `amount` is REQUIRED in this model — pydantic will then raise the
                # standard "Field required" error which the FE renders as a clear
                # red banner. Optional fields drop quietly.
                return None
            try:
                return float(s)
            except ValueError:
                # Let pydantic produce its own structured "valid number" error so
                # the FE can show the precise field that failed validation.
                return v
        return v



@router.get("/financial/summary")
async def financial_summary(location_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).isoformat()[:7]
    # Build location filter from campus context
    campus = await get_campus_filter(current_user)
    if location_id:
        loc_match = {"location_id": location_id}
    elif campus:
        loc_match = campus
    else:
        loc_match = {}
    donations_result = await db.donations.aggregate([{"$match": {**loc_match, "date": {"$regex": f"^{month_start}"}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    # Only count approved expenses (exclude pending/rejected requests)
    exp_match = {**loc_match, "date": {"$regex": f"^{month_start}"}, "status": {"$in": ["approved", None]}}
    expenses_result = await db.expenses.aggregate([{"$match": exp_match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    sales_result = await db.sales.aggregate([{"$match": {**loc_match, "created_at": {"$regex": f"^{month_start}"}}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    monthly_donations = donations_result[0]["total"] if donations_result else 0
    monthly_expenses = expenses_result[0]["total"] if expenses_result else 0
    monthly_sales = sales_result[0]["total"] if sales_result else 0
    all_donations = await db.donations.aggregate([{"$match": loc_match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_expenses = await db.expenses.aggregate([{"$match": {**loc_match, "status": {"$in": ["approved", None]}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_sales = await db.sales.aggregate([{"$match": loc_match}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    total_in = (all_donations[0]["total"] if all_donations else 0) + (all_sales[0]["total"] if all_sales else 0)
    total_out = all_expenses[0]["total"] if all_expenses else 0
    # Pending (awaiting approval) — surfaced separately for UI
    pending_exp = await db.expenses.aggregate([{"$match": {**loc_match, "status": "pending"}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}]).to_list(1)
    pending_expenses_total = pending_exp[0]["total"] if pending_exp else 0
    pending_expenses_count = pending_exp[0]["count"] if pending_exp else 0
    return {"monthly_donations": monthly_donations, "monthly_expenses": monthly_expenses, "monthly_sales": monthly_sales, "cashflow_in": total_in, "cashflow_out": total_out, "net_balance": total_in - total_out, "pending_expenses_total": pending_expenses_total, "pending_expenses_count": pending_expenses_count}


@router.post("/financial/distribute-funds")
async def distribute_funds(data: dict, current_user: dict = Depends(require_director)):
    from_location_id = data.get("from_location_id"); to_location_id = data.get("to_location_id")
    amount = float(data.get("amount", 0)); currency = data.get("currency", "UGX"); notes = data.get("notes", "")
    exchange_rate = float(data.get("exchange_rate", 1.0))
    receiving_currency = data.get("receiving_currency", currency)
    if amount <= 0: raise HTTPException(status_code=400, detail="Amount must be > 0")
    receiving_amount = round(amount * exchange_rate, 2) if exchange_rate != 1.0 else amount
    transfer_id = f"tfr_{str(uuid.uuid4())[:8]}"; now = datetime.now(timezone.utc).isoformat()
    rate_note = f" (Rate: {exchange_rate} {currency}→{receiving_currency})" if exchange_rate != 1.0 else ""
    await db.expenses.insert_one({"id": f"exp_{str(uuid.uuid4())[:8]}", "title": f"Fund transfer to {to_location_id}", "amount": amount, "currency": currency, "category": "transfer", "date": now[:10], "notes": f"Transfer {transfer_id}: {notes}{rate_note}", "location_id": from_location_id, "transfer_id": transfer_id, "exchange_rate": exchange_rate, "created_at": now, "created_by": current_user["id"]})
    await db.donations.insert_one({"id": f"don_{str(uuid.uuid4())[:8]}", "donor_name": "Internal Transfer", "amount": receiving_amount, "currency": receiving_currency, "type": "transfer", "date": now[:10], "notes": f"Transfer {transfer_id} from {from_location_id}: {notes}{rate_note}", "location_id": to_location_id, "transfer_id": transfer_id, "exchange_rate": exchange_rate, "original_amount": amount, "original_currency": currency, "created_at": now, "created_by": current_user["id"]})
    await _audit(current_user["id"], "create", "fund_transfer", transfer_id)
    return {"transfer_id": transfer_id, "amount": amount, "receiving_amount": receiving_amount, "exchange_rate": exchange_rate, "from": from_location_id, "to": to_location_id}


# ========== DONATIONS ==========

@router.get("/financial/donations")
async def list_donations(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    query = {**await _financial_campus_filter(current_user)}
    if location_id: query["location_id"] = location_id
    if date_from or date_to:
        query["date"] = {}
        if date_from: query["date"]["$gte"] = date_from
        if date_to: query["date"]["$lte"] = date_to
    return await db.donations.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/financial/donations")
async def create_donation(data: DonationCreate, current_user: dict = Depends(require_finance_view)):
    # Enforce account assignment: non-admins can only deposit into accounts they're assigned to
    if data.deposit_to_account_id:
        from routers.chart_accounts import user_can_use_account
        if not await user_can_use_account(current_user, data.deposit_to_account_id):
            raise HTTPException(status_code=403, detail="You are not assigned to that account. Ask an admin to assign it to you.")
    doc = {"id": f"don_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"], "entered_by": current_user.get("name", "")}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if doc.get("sublocation_id") and not doc.get("location_id"):
        doc["location_id"] = doc["sublocation_id"]
    # Auto-tag to the location's default cash account when caller left it blank,
    # so Finance sub-location totals stay in lockstep with Chart cash account balances.
    if not doc.get("deposit_to_account_id") and doc.get("location_id"):
        ss = await db.store_settings.find_one({"location_id": doc["location_id"]}, {"_id": 0, "default_cash_account_id": 1}) or {}
        if ss.get("default_cash_account_id"):
            doc["deposit_to_account_id"] = ss["default_cash_account_id"]
            doc["deposit_auto_tagged"] = True
    await db.donations.insert_one(doc); doc.pop("_id", None)
    if doc.get("deposit_to_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([doc["deposit_to_account_id"]])
    # Auto-create/update donor profile (iter209b) — enables typeahead + drilldown
    try:
        from routers.donors_vendors import upsert_donor_from_donation
        donor_id = await upsert_donor_from_donation(doc, current_user)
        if donor_id:
            await db.donations.update_one({"id": doc["id"]}, {"$set": {"donor_id": donor_id}})
            doc["donor_id"] = donor_id
    except Exception as e:
        logger.warning(f"Donor auto-upsert skipped: {e}")
    await _audit(current_user["id"], "create", "donation", doc["id"])
    # Auto-post to accounting ledger (silent no-op if CoA not configured)
    try:
        await _post_to_accounting("donation", doc, current_user)
    except Exception as e:
        logger.warning(f"Donation auto-post to accounting skipped: {e}")
    return doc


# ========== AUTO-POST FINANCIAL FLOWS TO ACCOUNTING LEDGER ==========

# Heuristic mapping from financial expense category → CoA account name fragment.
# First active expense-type account whose name contains the fragment wins;
# falls back to the first expense-type account in the location.
_EXPENSE_CATEGORY_HINTS = {
    "salaries": ["salar", "wage"],
    "utilities": ["utilit", "rent"],
    "rent": ["rent", "utilit"],
    "supplies": ["suppl"],
    "maintenance": ["maint", "repair"],
    "programs": ["program"],
    "travel": ["travel", "meal"],
    "meals": ["meal", "travel"],
    "fuel": ["fuel", "travel"],
    "training": ["train", "develop"],
    "accommodation": ["accommod", "travel"],
}


async def _find_account(location_id: str, *, account_type: str = None, name_hints: list = None) -> dict:
    """Find a matching CoA account by type, optionally narrowed by name hints (case-insensitive contains)."""
    q = {"location_id": location_id, "active": True}
    if account_type:
        q["type"] = account_type
    candidates = await db.accounting_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(100)
    if not candidates:
        return None
    if name_hints:
        for h in name_hints:
            for c in candidates:
                if h.lower() in (c.get("name") or "").lower():
                    return c
    return candidates[0]


async def _reverse_auto_posted_je(source_kind: str, source_id: str, current_user: dict) -> int:
    """When a donation or expense is deleted, its auto-posted journal entry stays in
    the ledger causing Finance and Accounting to drift. This finds the linked JE
    (matched by auto_generated_from + source_id) and reverses it if still posted."""
    # Target the currently-active JE, NOT an older already-reversed one
    # (fixes iter212 bug where 3rd+ payroll re-aggregations were no-ops
    # because Mongo's natural insertion order returned the oldest match).
    entry = await db.accounting_entries.find_one(
        {"auto_generated_from": source_kind, "source_id": source_id, "is_reversed": {"$ne": True}},
        {"_id": 0},
    )
    if not entry or entry.get("status") != "posted":
        return 0
    try:
        from routers.accounting import reverse_entry
        await reverse_entry(entry["id"], {"reason": f"Source {source_kind} deleted"}, current_user)
        return 1
    except Exception as ex:
        logger.error(f"Auto-reverse failed for {source_kind} {source_id}: {ex}")
        return 0


async def _post_to_accounting(kind: str, doc: dict, current_user: dict) -> None:
    """Create + post a balanced JE for a financial-module record.
    `kind` ∈ {'donation', 'expense_approved', 'payroll'}.
    Silently no-ops if the location has no Chart of Accounts yet."""
    loc_id = doc.get("location_id")
    if not loc_id:
        return
    try:
        amount = float(doc.get("amount") or 0)
    except (TypeError, ValueError):
        return
    if amount <= 0:
        return
    # Find a general-purpose journal — MUST NOT fall back to a sales journal
    # (fixes production bug where donations/expenses/payroll were all prefixed
    # SALES/... because the loose "any active" fallback picked the sales journal).
    journal = await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": "miscellaneous", "active": True}, {"_id": 0}
    ) or await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": {"$in": ["general", "purchases"]}, "active": True}, {"_id": 0}
    )
    if not journal:
        # Auto-create a miscellaneous journal so future entries have a home.
        # This avoids the silent-skip that leaves half a location's activity
        # missing from the ledger.
        journal = {
            "id": f"jrn_{uuid.uuid4().hex[:10]}",
            "code": "GL",
            "name": "General Ledger",
            "kind": "miscellaneous",
            "location_id": loc_id,
            "active": True,
            "auto_created": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.accounting_journals.insert_one(journal)
        journal.pop("_id", None)
        logger.info(f"Auto-created General Ledger journal for location {loc_id}")
    if kind == "donation":
        debit_acc = await _find_account(loc_id, account_type="asset_cash")
        credit_acc = await _find_account(loc_id, account_type="income", name_hints=["donation", "contribut"])
        narration = f"Donation from {doc.get('donor_name', 'anonymous')} ({doc.get('type', '')})"
        ref = doc["id"]
        source_kind = "donation"
    elif kind == "expense_approved":
        category = (doc.get("category") or "").lower().strip()
        hints = _EXPENSE_CATEGORY_HINTS.get(category, ["other"])
        debit_acc = await _find_account(loc_id, account_type="expense", name_hints=hints)
        credit_acc = await _find_account(loc_id, account_type="asset_cash")
        narration = f"Expense: {doc.get('title', '')} [{category or 'general'}]"
        ref = doc["id"]
        source_kind = "expense"
    elif kind == "payroll":
        # Payroll: Dr Wages & Salaries expense / Cr Cash
        debit_acc = await _find_account(loc_id, account_type="expense", name_hints=["wage", "salar", "payroll"])
        credit_acc = await _find_account(loc_id, account_type="asset_cash")
        narration = f"Salary — {doc.get('notes', 'Payroll')}"
        ref = doc["id"]
        source_kind = "payroll"
    else:
        return
    if not debit_acc or not credit_acc:
        logger.warning(f"Skipping JE for {kind} {doc.get('id')} — missing debit/credit account at location {loc_id}")
        return
    # Idempotency — never post twice for the same (still-active) source.
    # We must EXCLUDE reversed entries so that aggregate flows (like payroll)
    # which reverse+repost on every update actually get a fresh JE for the
    # new total.  Without the `is_reversed` filter, the re-post is a no-op
    # and the ledger only carries the (now-cancelled) original pair.
    existing = await db.accounting_entries.find_one(
        {"auto_generated_from": source_kind, "source_id": doc["id"], "is_reversed": {"$ne": True}},
        {"_id": 0, "id": 1},
    )
    if existing:
        return
    from routers.accounting import _next_entry_number
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal["id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    entry_date = (doc.get("date") or now_iso)[:10]
    entry = {
        "id": entry_id,
        "number": entry_number,
        "journal_id": journal["id"],
        "journal_code": journal.get("code"),
        "date": entry_date,
        "ref": ref,
        "narration": narration,
        "total_debit": round(amount, 2),
        "total_credit": round(amount, 2),
        "status": "posted",
        "location_id": loc_id,
        "currency": doc.get("currency") or "UGX",
        "auto_generated_from": source_kind,
        "source_id": doc["id"],
        "created_at": now_iso,
        "posted_at": now_iso,
        "posted_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    await db.accounting_entry_lines.insert_many([
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": entry_date, "location_id": loc_id, "status": "posted",
         "account_id": debit_acc["id"], "debit": round(amount, 2), "credit": 0, "description": narration},
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": entry_date, "location_id": loc_id, "status": "posted",
         "account_id": credit_acc["id"], "debit": 0, "credit": round(amount, 2), "description": narration},
    ])


# ========== EXPENSES ==========

@router.get("/financial/expenses")
async def list_expenses(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    query = {**await _financial_campus_filter(current_user)}
    if location_id: query["location_id"] = location_id
    if status: query["status"] = status
    if date_from or date_to:
        query["date"] = {}
        if date_from: query["date"]["$gte"] = date_from
        if date_to: query["date"]["$lte"] = date_to
    return await db.expenses.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/financial/expenses")
async def create_expense(data: ExpenseCreate, current_user: dict = Depends(require_finance_view)):
    # Enforce account assignment: non-admins can only pull from accounts they're assigned to
    if data.paid_from_account_id:
        from routers.chart_accounts import user_can_use_account
        if not await user_can_use_account(current_user, data.paid_from_account_id):
            raise HTTPException(status_code=403, detail="You are not assigned to that account. Ask an admin to assign it to you.")
    doc = {"id": f"exp_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"], "entered_by": current_user.get("name", "")}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    # Auto-tag to the location's default cash account when caller left it blank,
    # so Finance sub-location totals stay in lockstep with Chart cash account balances.
    if not doc.get("paid_from_account_id") and doc.get("location_id"):
        ss = await db.store_settings.find_one({"location_id": doc["location_id"]}, {"_id": 0, "default_cash_account_id": 1}) or {}
        if ss.get("default_cash_account_id"):
            doc["paid_from_account_id"] = ss["default_cash_account_id"]
            doc["paid_auto_tagged"] = True
    if doc.get("sublocation_id") and not doc.get("location_id"):
        doc["location_id"] = doc["sublocation_id"]
    await db.expenses.insert_one(doc); doc.pop("_id", None)
    if doc.get("paid_from_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([doc["paid_from_account_id"]])
    # Auto-create/update vendor profile (iter209b)
    try:
        from routers.donors_vendors import upsert_vendor_from_expense
        vendor_id = await upsert_vendor_from_expense(doc, current_user)
        if vendor_id:
            await db.expenses.update_one({"id": doc["id"]}, {"$set": {"vendor_id": vendor_id}})
            doc["vendor_id"] = vendor_id
    except Exception as e:
        logger.warning(f"Vendor auto-upsert skipped: {e}")
    await _audit(current_user["id"], "create", "expense", doc["id"])
    return doc


@router.delete("/financial/donations/{donation_id}")
async def delete_donation(donation_id: str, current_user: dict = Depends(require_finance_view)):
    """Delete a donation entry.  Creator can delete within 7 days; admins any time.
    Also reverses any auto-posted JE so the ledger stays consistent."""
    doc = await db.donations.find_one({"id": donation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Donation not found")
    ok, reason = _within_self_edit_window(doc, current_user)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    await _reverse_auto_posted_je("donation", donation_id, current_user)
    await db.donations.delete_one({"id": donation_id})
    if doc.get("deposit_to_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([doc["deposit_to_account_id"]])
    await _audit(current_user["id"], "delete", "donation", donation_id,
                 {"by_creator": not _is_finance_admin(current_user)})
    return {"message": "Donation deleted"}


@router.delete("/financial/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(require_finance_view)):
    """Delete an expense entry.  Creator can delete within 7 days; admins any time.
    Also reverses any auto-posted JE so the ledger stays consistent."""
    doc = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Expense not found")
    ok, reason = _within_self_edit_window(doc, current_user)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    await _reverse_auto_posted_je("expense", expense_id, current_user)
    await db.expenses.delete_one({"id": expense_id})
    if doc.get("paid_from_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([doc["paid_from_account_id"]])
    await _audit(current_user["id"], "delete", "expense", expense_id,
                 {"by_creator": not _is_finance_admin(current_user)})
    return {"message": "Expense deleted"}


# ========== BULK DELETE (Finance module) ==========

@router.post("/financial/donations/bulk-delete")
async def bulk_delete_donations(data: dict, current_user: dict = Depends(require_admin)):
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    reversed_count = 0
    for did in ids:
        reversed_count += await _reverse_auto_posted_je("donation", did, current_user)
    result = await db.donations.delete_many({"id": {"$in": ids}})
    from routers.chart_accounts import invalidate_balance_cache
    invalidate_balance_cache()  # bulk — clear all
    await _audit(current_user["id"], "bulk_delete", "donations", None, {"count": result.deleted_count, "je_reversed": reversed_count})
    return {"deleted": result.deleted_count, "je_reversed": reversed_count}


@router.post("/financial/expenses/bulk-delete")
async def bulk_delete_expenses(data: dict, current_user: dict = Depends(require_admin)):
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    reversed_count = 0
    for eid in ids:
        reversed_count += await _reverse_auto_posted_je("expense", eid, current_user)
    result = await db.expenses.delete_many({"id": {"$in": ids}})
    from routers.chart_accounts import invalidate_balance_cache
    invalidate_balance_cache()  # bulk — clear all
    await _audit(current_user["id"], "bulk_delete", "expenses", None, {"count": result.deleted_count, "je_reversed": reversed_count})
    return {"deleted": result.deleted_count, "je_reversed": reversed_count}


@router.post("/financial/assets/bulk-delete")
async def bulk_delete_assets(data: dict, current_user: dict = Depends(require_admin)):
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    result = await db.assets.delete_many({"id": {"$in": ids}})
    await _audit(current_user["id"], "bulk_delete", "assets", None, {"count": result.deleted_count})
    return {"deleted": result.deleted_count}


@router.post("/financial/budgets/bulk-delete")
async def bulk_delete_budgets(data: dict, current_user: dict = Depends(require_manager)):
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    result = await db.financial_budgets.delete_many({"id": {"$in": ids}})
    await _audit(current_user["id"], "bulk_delete", "budgets", None, {"count": result.deleted_count})
    return {"deleted": result.deleted_count}




@router.put("/financial/donations/{donation_id}")
async def update_donation(donation_id: str, data: dict, current_user: dict = Depends(require_finance_view)):
    """Edit a donation entry.  Creator can edit within 7 days; admins any time."""
    doc = await db.donations.find_one({"id": donation_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Donation not found")
    ok, reason = _within_self_edit_window(doc, current_user)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    allowed = {"donor_name", "amount", "currency", "type", "date", "notes", "location_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.donations.update_one({"id": donation_id}, {"$set": update})
    # If amount/date changed and there's a live JE, reverse+repost so ledger stays honest
    if any(k in update for k in ("amount", "date")):
        try:
            await _reverse_auto_posted_je("donation", donation_id, current_user)
            fresh = await db.donations.find_one({"id": donation_id}, {"_id": 0})
            await _post_to_accounting("donation", fresh, current_user)
        except Exception as ex:
            logger.warning(f"Donation edit re-post skipped: {ex}")
    if doc.get("deposit_to_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([doc["deposit_to_account_id"]])
    await _audit(current_user["id"], "update", "donation", donation_id,
                 {"by_creator": not _is_finance_admin(current_user)})
    return await db.donations.find_one({"id": donation_id}, {"_id": 0})


@router.put("/financial/expenses/{expense_id}")
async def update_expense(expense_id: str, data: dict, current_user: dict = Depends(require_finance_view)):
    """Edit an expense entry.  Creator can edit within 7 days; admins any time.
    Amount/category/paid-from changes trigger JE reversal + repost to keep the
    ledger in sync."""
    doc = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Expense not found")
    ok, reason = _within_self_edit_window(doc, current_user)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
    allowed = {"title", "amount", "currency", "category", "date", "notes", "location_id",
               "sublocation_id", "department", "budget_category", "paid_from_account_id",
               "vendor_name", "receipt_url"}
    update = {k: v for k, v in data.items() if k in allowed}
    # Verify user can still use the paid_from_account if they changed it
    if "paid_from_account_id" in update and update["paid_from_account_id"]:
        from routers.chart_accounts import user_can_use_account
        if not await user_can_use_account(current_user, update["paid_from_account_id"]):
            raise HTTPException(status_code=403, detail="You are not assigned to that account")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.expenses.update_one({"id": expense_id}, {"$set": update})
    # If amount/category/paid_from changed and there's a live JE, reverse+repost
    if any(k in update for k in ("amount", "category", "paid_from_account_id", "date")):
        try:
            await _reverse_auto_posted_je("expense", expense_id, current_user)
            fresh = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
            if fresh.get("status") == "approved":
                await _post_to_accounting("expense_approved", fresh, current_user)
        except Exception as ex:
            logger.warning(f"Expense edit re-post skipped: {ex}")
    from routers.chart_accounts import invalidate_balance_cache
    invalidate_balance_cache([doc.get("paid_from_account_id"), update.get("paid_from_account_id")])
    await _audit(current_user["id"], "update", "expense", expense_id,
                 {"by_creator": not _is_finance_admin(current_user), "fields": list(update.keys())})
    return await db.expenses.find_one({"id": expense_id}, {"_id": 0})




# ========== EXPENSE APPROVAL WORKFLOW ==========

@router.get("/financial/expenses/pending")
async def list_pending_expenses(current_user: dict = Depends(require_manager)):
    expenses = await db.expenses.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return expenses


@router.put("/financial/expenses/{expense_id}/approve")
async def approve_expense(expense_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    data = data or {}
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense: raise HTTPException(status_code=404, detail="Expense not found")
    update = {"status": "approved", "approved_by": current_user["id"], "approved_by_name": current_user.get("name", ""), "approved_at": datetime.now(timezone.utc).isoformat(), "approval_comment": data.get("comment", "")}
    await db.expenses.update_one({"id": expense_id}, {"$set": update})
    if expense.get("paid_from_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([expense["paid_from_account_id"]])
    await _audit(current_user["id"], "update", "expense_approval", expense_id)
    # Auto-post to accounting ledger on approval (silent no-op if CoA not configured)
    try:
        await _post_to_accounting("expense_approved", {**expense, **update}, current_user)
    except Exception as e:
        logger.warning(f"Expense auto-post to accounting skipped: {e}")
    if expense.get("created_by"):
        try:
            from routers.notifications import _create_notification
            await _create_notification("Expense Approved", f"Your expense '{expense.get('title')}' ({expense.get('amount', 0):,.0f} {expense.get('currency', 'UGX')}) has been approved by {current_user.get('name', 'admin')}.", expense.get("created_by"), "success", "/portal/expenses")
        except Exception:
            pass
    return {**expense, **update}


@router.put("/financial/expenses/{expense_id}/reject")
async def reject_expense(expense_id: str, data: dict = None, current_user: dict = Depends(require_manager)):
    data = data or {}
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense: raise HTTPException(status_code=404, detail="Expense not found")
    update = {"status": "rejected", "rejected_by": current_user["id"], "rejected_by_name": current_user.get("name", ""), "rejected_at": datetime.now(timezone.utc).isoformat(), "rejection_comment": data.get("comment", "")}
    await db.expenses.update_one({"id": expense_id}, {"$set": update})
    if expense.get("paid_from_account_id"):
        from routers.chart_accounts import invalidate_balance_cache
        invalidate_balance_cache([expense["paid_from_account_id"]])
    await _audit(current_user["id"], "update", "expense_rejection", expense_id)
    if expense.get("created_by"):
        try:
            from routers.notifications import _create_notification
            await _create_notification("Expense Rejected", f"Your expense '{expense.get('title')}' was rejected. Reason: {data.get('comment', 'No reason given')}", expense.get("created_by"), "error", "/portal/expenses")
        except Exception:
            pass
    return {**expense, **update}




# ========== CASHFLOW & BALANCE ==========

@router.get("/financial/cashflow")
async def financial_cashflow(months: int = 6, current_user: dict = Depends(require_finance_view)):
    from datetime import timedelta
    campus = await get_campus_filter(current_user)
    now = datetime.now(timezone.utc); monthly = []
    for i in range(months - 1, -1, -1):
        month_dt = now.replace(day=1) - timedelta(days=i * 28)
        month_start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        month_end = (month_dt.replace(year=month_dt.year + 1, month=1, day=1) if month_dt.month == 12 else month_dt.replace(month=month_dt.month + 1, day=1)).isoformat()
        don_q = {"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}
        exp_q = {"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}
        sale_q = {"created_at": {"$gte": month_start, "$lt": month_end}}
        if campus:
            don_q.update(campus); exp_q.update(campus); sale_q.update(campus)
        donations = await db.donations.find(don_q, {"_id": 0, "amount": 1}).to_list(5000)
        expenses_list = await db.expenses.find(exp_q, {"_id": 0, "amount": 1}).to_list(5000)
        sales = await db.sales.find(sale_q, {"_id": 0, "total": 1}).to_list(5000)
        inflow = sum(d.get("amount", 0) for d in donations) + sum(s.get("total", 0) for s in sales)
        outflow = sum(e.get("amount", 0) for e in expenses_list)
        monthly.append({"month": month_dt.strftime("%b"), "inflow": inflow, "outflow": outflow, "net": inflow - outflow})
    return {"monthly": monthly}

@router.get("/financial/balance")
async def get_financial_balance(current_user: dict = Depends(require_finance_view)):
    doc = await db.financial_settings.find_one({}, {"_id": 0})
    return doc or {"opening_balance": 0, "current_balance": 0, "set_at": None}

@router.put("/financial/balance")
async def set_financial_balance(opening_balance: float, current_user: dict = Depends(require_finance_admin)):
    now = datetime.now(timezone.utc).isoformat()
    await db.financial_settings.update_one({}, {"$set": {"opening_balance": opening_balance, "set_at": now, "set_by": current_user["id"]}}, upsert=True)
    return {"opening_balance": opening_balance, "set_at": now}


# ========== STORE SETTINGS PER LOCATION ==========

@router.get("/store-settings/{location_id}")
async def get_store_settings(location_id: str, current_user: dict = Depends(get_current_user)):
    """Get store configuration for a specific location.
    Merges any new default keys over stored docs so legacy locations always see the full schema."""
    defaults = {
        "location_id": location_id,
        "store_name": "",
        "payment_methods": ["cash", "mobile_money"],
        "mobile_money_providers": [],
        "tax_rate": 0,
        "receipt_footer": "",
        "receipt_paper_size": "80mm",
        "receipt_show_logo": True,
        "receipt_show_qr": True,
        "api_integrations": [],
        "currency": "UGX",
        "default_cash_account_id": "",
        "default_bank_account_id": "",
        "default_momo_account_id": "",
    }
    doc = await db.store_settings.find_one({"location_id": location_id}, {"_id": 0})
    if doc:
        return {**defaults, **doc}
    return defaults


@router.put("/store-settings/{location_id}")
async def update_store_settings(location_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Update store configuration for a specific location."""
    data.pop("_id", None)
    data["location_id"] = location_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = current_user["id"]
    await db.store_settings.update_one(
        {"location_id": location_id},
        {"$set": data},
        upsert=True
    )
    await _audit(current_user["id"], "update", "store_settings", location_id)
    return data


@router.get("/store-settings")
async def list_all_store_settings(current_user: dict = Depends(get_current_user)):
    """List store settings for all locations."""
    return await db.store_settings.find({}, {"_id": 0}).to_list(100)






# ========== FINANCIAL EXPORT / IMPORT ==========

@router.get("/financial/export")
async def export_financial_data(
    location_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Export donations and expenses as JSON."""
    query = {**await _financial_campus_filter(current_user)}
    if location_id:
        query["location_id"] = location_id
    date_filter = {}
    if date_from:
        date_filter["$gte"] = date_from
    if date_to:
        date_filter["$lte"] = date_to
    don_q = {**query}
    exp_q = {**query}
    if date_filter:
        don_q["date"] = date_filter
        exp_q["date"] = date_filter
    donations = await db.donations.find(don_q, {"_id": 0}).sort("date", -1).to_list(5000)
    expenses = await db.expenses.find(exp_q, {"_id": 0}).sort("date", -1).to_list(5000)
    return {
        "donations": donations,
        "expenses": expenses,
        "donations_count": len(donations),
        "expenses_count": len(expenses),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/financial/import")
async def import_financial_data(data: dict, current_user: dict = Depends(require_manager)):
    """Import donations and/or expenses from JSON."""
    don_data = data.get("donations", [])
    exp_data = data.get("expenses", [])
    if not don_data and not exp_data:
        raise HTTPException(status_code=400, detail="No financial data provided")
    don_imported = 0
    for d in don_data:
        doc = {
            "id": f"don_{str(uuid.uuid4())[:8]}",
            "donor_name": d.get("donor_name", "Imported"),
            "amount": float(d.get("amount", 0)),
            "currency": d.get("currency", "UGX"),
            "type": d.get("type", "donation"),
            "date": d.get("date", datetime.now(timezone.utc).isoformat()[:10]),
            "notes": d.get("notes", "Imported"),
            "location_id": d.get("location_id", current_user.get("location_id", "")),
            "member_id": d.get("member_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.donations.insert_one(doc)
        don_imported += 1
    exp_imported = 0
    for e in exp_data:
        doc = {
            "id": f"exp_{str(uuid.uuid4())[:8]}",
            "title": e.get("title", "Imported"),
            "amount": float(e.get("amount", 0)),
            "currency": e.get("currency", "UGX"),
            "category": e.get("category", "general"),
            "date": e.get("date", datetime.now(timezone.utc).isoformat()[:10]),
            "notes": e.get("notes", "Imported"),
            "status": "approved",
            "location_id": e.get("location_id", current_user.get("location_id", "")),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.expenses.insert_one(doc)
        exp_imported += 1
    await _audit(current_user["id"], "create", "financial_import", None, {"donations": don_imported, "expenses": exp_imported})
    return {"donations_imported": don_imported, "expenses_imported": exp_imported}



# ========== BALANCE SHEET ==========

@router.get("/financial/balance-sheet")
async def get_balance_sheet(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(require_manager)):
    """Generate a balance sheet (income vs expenses) for a campus + Net Profit/Loss + Net Worth (with assets)."""
    campus = await _financial_campus_filter(current_user)
    query = {**campus}
    if location_id:
        query["location_id"] = location_id

    date_q = {}
    if date_from: date_q["$gte"] = date_from
    if date_to: date_q["$lte"] = date_to

    don_query = {**query}
    exp_query = {**query}
    if date_q:
        don_query["date"] = date_q
        exp_query["date"] = date_q

    # Income
    donations = await db.donations.find(don_query, {"_id": 0}).to_list(2000)
    total_income = sum(d.get("amount", 0) for d in donations)
    income_by_type = {}
    for d in donations:
        t = d.get("type", "general")
        income_by_type[t] = income_by_type.get(t, 0) + d.get("amount", 0)

    # Expenses (only count approved + legacy unstatused; pending/rejected excluded)
    exp_query["status"] = {"$nin": ["pending", "rejected"]}
    expenses = await db.expenses.find(exp_query, {"_id": 0}).to_list(2000)
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    expense_by_category = {}
    for e in expenses:
        c = e.get("category", "general")
        expense_by_category[c] = expense_by_category.get(c, 0) + e.get("amount", 0)

    # Sales income — only count paid sales as realized revenue (pending non-cash is receivable, not income yet)
    sale_query = {**query}
    if date_q: sale_query["date"] = date_q
    all_sales = await db.sales.find(sale_query, {"_id": 0}).to_list(2000)
    paid_sales = [s for s in all_sales if s.get("payment_status", "paid") != "pending"]
    pending_sales = [s for s in all_sales if s.get("payment_status") == "pending"]
    total_sales = sum(s.get("total", 0) for s in paid_sales)
    accounts_receivable = sum(s.get("total", 0) for s in pending_sales)

    total_revenue = total_income + total_sales
    net_profit_loss = total_revenue - total_expenses
    is_profit = net_profit_loss >= 0

    # Net Worth: include assets (current value) — assets_total - net_loss is informative
    asset_query = {**campus}
    if location_id: asset_query["location_id"] = location_id
    assets = await db.financial_assets.find(asset_query, {"_id": 0, "current_value": 1, "purchase_value": 1}).to_list(500)
    assets_total = sum(float(a.get("current_value") or a.get("purchase_value") or 0) for a in assets)
    net_worth = assets_total + net_profit_loss

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "net_balance": net_profit_loss,        # legacy alias — same value
        "net_profit_loss": net_profit_loss,
        "is_profit": is_profit,
        "profit_margin_pct": round((net_profit_loss / total_revenue * 100), 2) if total_revenue else 0,
        "accounts_receivable": accounts_receivable,
        "pending_sales_count": len(pending_sales),
        "assets_total": assets_total,
        "asset_count": len(assets),
        "net_worth": net_worth,
        "income_by_type": income_by_type,
        "expense_by_category": expense_by_category,
        "donation_count": len(donations),
        "expense_count": len(expenses),
        "sale_count": len(paid_sales),
        "period": {"from": date_from, "to": date_to},
        "location_id": location_id,
    }



# ========== ASSETS ==========

@router.get("/financial/assets")
async def list_assets(location_id: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    campus = await _financial_campus_filter(current_user)
    query = {**campus} if campus else {}
    if location_id: query["location_id"] = location_id
    return await db.assets.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/financial/assets")
async def create_asset(data: dict, current_user: dict = Depends(require_manager)):
    doc = {
        "id": f"ast_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "value": float(data.get("value", 0)),
        "category": data.get("category", "equipment"),
        "purchase_date": data.get("purchase_date", ""),
        "depreciation_years": int(data.get("depreciation_years", 5)),
        "serial_number": data.get("serial_number", ""),
        "condition": data.get("condition", "good"),
        "location_id": data.get("location_id", current_user.get("location_id", "")),
        "notes": data.get("notes", ""),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.assets.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/financial/assets/{asset_id}")
async def update_asset(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    allowed = {"name", "value", "category", "purchase_date", "depreciation_years", "serial_number", "condition", "location_id", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.assets.update_one({"id": asset_id}, {"$set": update})
    return await db.assets.find_one({"id": asset_id}, {"_id": 0})


@router.delete("/financial/assets/{asset_id}")
async def delete_asset(asset_id: str, current_user: dict = Depends(require_admin)):
    await db.assets.delete_one({"id": asset_id})
    return {"message": "Asset deleted"}



# ========== RECEIPT SCANNING ==========

@router.post("/financial/expenses/{expense_id}/receipt")
async def upload_receipt(expense_id: str, current_user: dict = Depends(require_staff)):
    """Upload receipt image for an expense"""
    from fastapi import UploadFile, File, Form
    # This endpoint accepts multipart form data
    # For now, store receipt reference on the expense
    return {"message": "Receipt endpoint ready — use multipart upload"}


@router.put("/financial/expenses/{expense_id}/receipt-url")
async def set_receipt_url(expense_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Set receipt URL/reference for an expense"""
    url = data.get("receipt_url", "")
    notes = data.get("receipt_notes", "")
    await db.expenses.update_one({"id": expense_id}, {"$set": {
        "receipt_url": url, "receipt_notes": notes,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"message": "Receipt attached"}


# ========== PUBLIC PRODUCTS / SHOP ==========

@router.get("/public/products")
async def public_products(location_id: Optional[str] = None, category: Optional[str] = None):
    """Public product listing for online shop"""
    query = {"stock": {"$gt": 0}, "is_public": {"$ne": False}}
    if location_id: query["location_id"] = location_id
    if category: query["category"] = category
    products = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(200)
    return products


@router.post("/public/orders")
async def create_public_order(data: dict):
    """Create a public order"""
    items = data.get("items", [])
    if not items: raise HTTPException(status_code=400, detail="No items in order")
    order_id = f"ord_{str(uuid.uuid4())[:8]}"
    total = 0
    order_items = []
    for item in items:
        product = await db.products.find_one({"id": item.get("product_id")}, {"_id": 0})
        if not product: continue
        qty = int(item.get("quantity", 1))
        line_total = (product.get("price", 0)) * qty
        total += line_total
        order_items.append({
            "product_id": product["id"], "name": product.get("name"),
            "price": product.get("price", 0), "quantity": qty, "total": line_total,
        })
    order = {
        "id": order_id,
        "customer_name": data.get("name", ""),
        "customer_email": data.get("email", ""),
        "customer_phone": data.get("phone", ""),
        "items": order_items,
        "total": total,
        "payment_method": data.get("payment_method", "card"),
        "payment_status": "pending",
        "status": "pending",
        "location_id": data.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_orders.insert_one(order)
    order.pop("_id", None)
    return order



# ========== CHILD SPONSORSHIP ==========

@router.get("/financial/sponsors")
async def list_sponsors(location_id: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """List child sponsors, filtered by campus"""
    campus = await _financial_campus_filter(current_user)
    query = {**campus}
    if location_id:
        query["location_id"] = location_id
    sponsors = await db.sponsors.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # For each sponsor, only show sponsor first name in child's context
    for s in sponsors:
        s["sponsor_display_name"] = s.get("name", "").split(" ")[0] if s.get("name") else "Anonymous"
    return sponsors


@router.post("/financial/sponsors")
async def create_sponsor(data: dict, current_user: dict = Depends(require_staff)):
    """Create a child sponsor. Auto-creates child profile if child doesn't exist."""
    sponsor_id = f"spon_{str(uuid.uuid4())[:8]}"
    child_id = data.get("child_id")
    child_name = data.get("child_name", "")
    location_id = data.get("location_id", "")

    # If no child_id but child_name provided, find or create child
    if not child_id and child_name:
        existing_child = await db.children.find_one({"name": {"$regex": f"^{child_name}$", "$options": "i"}})
        if existing_child:
            child_id = existing_child["id"]
        else:
            child_id = f"chd_{str(uuid.uuid4())[:8]}"
            await db.children.insert_one({
                "id": child_id, "name": child_name, "location_id": location_id,
                "is_sponsored": True, "sponsor_id": sponsor_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    doc = {
        "id": sponsor_id,
        "name": data.get("name", ""),
        "first_name": data.get("name", "").split(" ")[0] if data.get("name") else "",
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "address": data.get("address", ""),
        "child_id": child_id,
        "child_name": child_name or "",
        "amount": float(data.get("amount", 0)),
        "currency": data.get("currency", "USD"),
        "frequency": data.get("frequency", "monthly"),  # monthly, quarterly, yearly, one_time
        "location_id": location_id,
        "status": "active",
        "notes": data.get("notes", ""),
        "visibility": data.get("visibility", "restricted"),  # restricted = need-to-know
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sponsors.insert_one(doc)
    doc.pop("_id", None)

    # Tag child as sponsored (only first name visible to authorized staff)
    if child_id:
        await db.children.update_one({"id": child_id}, {"$set": {
            "is_sponsored": True, "sponsor_id": sponsor_id,
            "sponsor_first_name": doc["first_name"],
        }})

    return doc


@router.put("/financial/sponsors/{sponsor_id}")
async def update_sponsor(sponsor_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "email", "phone", "address", "amount", "currency", "frequency", "status", "notes", "child_id", "child_name", "visibility"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "name" in update:
        update["first_name"] = update["name"].split(" ")[0] if update["name"] else ""
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sponsors.update_one({"id": sponsor_id}, {"$set": update})
    # Update child's sponsor first name if name changed
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if sponsor and sponsor.get("child_id"):
        await db.children.update_one({"id": sponsor["child_id"]}, {"$set": {"sponsor_first_name": update.get("first_name", sponsor.get("first_name", ""))}})
    return sponsor


@router.delete("/financial/sponsors/{sponsor_id}")
async def delete_sponsor(sponsor_id: str, current_user: dict = Depends(require_admin)):
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if sponsor and sponsor.get("child_id"):
        await db.children.update_one({"id": sponsor["child_id"]}, {"$unset": {"is_sponsored": "", "sponsor_id": "", "sponsor_first_name": ""}})
    await db.sponsors.delete_one({"id": sponsor_id})
    return {"message": "Sponsor removed"}


@router.get("/financial/sponsors/{sponsor_id}")
async def get_sponsor(sponsor_id: str, current_user: dict = Depends(require_staff)):
    """Get full sponsor details — need-to-know access based on user's location"""
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    # Check access: director of the child's location, campus director, or ED/admin
    user_role = (current_user.get("role") or "").lower()
    if user_role not in {"admin", "system_admin", "executive director"}:
        user_locs = current_user.get("location_ids") or []
        user_loc = current_user.get("location_id", "")
        if user_loc and user_loc not in user_locs:
            user_locs.append(user_loc)
        sponsor_loc = sponsor.get("location_id", "")
        if sponsor_loc not in user_locs:
            # Hide sensitive info
            sponsor = {k: v for k, v in sponsor.items() if k in {"id", "child_id", "child_name", "first_name", "status", "frequency"}}
    return sponsor



# ========== SUB-LOCATION ACCOUNTS (unified at campus) ==========

@router.get("/financial/accounts")
async def list_sublocation_accounts(campus_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    """Get financial accounts per sub-location within a campus, unified at campus level.

    (iter208d) The `starting_balance` for each sub-location is now DERIVED from
    the sum of `chart_accounts.starting_balance` at that location — chart
    accounts are the single source of truth for opening cash.  The legacy
    `financial_accounts.starting_balance` field is retained only as a fallback
    for locations that have not yet been migrated (see /repair-starting-balances).
    """
    target_campus = campus_id or current_user.get("active_campus_id") or ""
    if not target_campus:
        raise HTTPException(status_code=400, detail="Campus ID required")
    subs = await db.locations.find(
        {"$or": [{"parent_id": target_campus}, {"id": target_campus}]},
        {"_id": 0, "id": 1, "name": 1, "type": 1}
    ).to_list(50)
    accounts = []
    campus_total_in = 0
    campus_total_out = 0
    campus_starting = 0
    for sub in subs:
        sid = sub["id"]
        # Get/create the legacy financial_account record (kept for backward-compat only)
        acct = await db.financial_accounts.find_one({"campus_id": target_campus, "location_id": sid}, {"_id": 0})
        if not acct:
            acct = {
                "id": f"acct_{uuid.uuid4().hex[:8]}",
                "campus_id": target_campus,
                "location_id": sid,
                "name": sub.get("name", ""),
                "type": "operational",
                "starting_balance": 0,
                "currency": "UGX",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.financial_accounts.insert_one(acct)
            acct.pop("_id", None)
        # NEW canonical starting balance = sum of chart cash accounts at this location
        chart_start_result = await db.chart_accounts.aggregate([
            {"$match": {"location_id": sid, "active": {"$ne": False}}},
            {"$group": {"_id": None, "total": {"$sum": "$starting_balance"}}}
        ]).to_list(1)
        chart_start = float((chart_start_result[0]["total"] if chart_start_result else 0) or 0)
        # Fallback to legacy value only when no chart accounts exist for this location yet
        legacy_start = float(acct.get("starting_balance", 0) or 0)
        starting_balance = chart_start if chart_start > 0 else legacy_start
        donations = await db.donations.aggregate([{"$match": {"location_id": sid}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        expenses = await db.expenses.aggregate([{"$match": {"location_id": sid, "status": {"$in": ["approved", None]}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        sales = await db.sales.aggregate([{"$match": {"location_id": sid}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
        total_in = (donations[0]["total"] if donations else 0) + (sales[0]["total"] if sales else 0)
        total_out = expenses[0]["total"] if expenses else 0
        campus_total_in += total_in
        campus_total_out += total_out
        campus_starting += starting_balance
        accounts.append({
            "id": acct["id"],
            "location_id": sid,
            "location_name": sub.get("name", ""),
            "location_type": sub.get("type", ""),
            "starting_balance": starting_balance,          # now derived from chart accounts
            "starting_balance_source": "chart_accounts" if chart_start > 0 else "legacy",
            "legacy_starting_balance": legacy_start,        # so admins can spot unmigrated data
            "currency": acct.get("currency", "UGX"),
            "total_income": total_in,
            "total_expenses": total_out,
            "balance": round(starting_balance + total_in - total_out, 2),  # true current cash
        })
    return {
        "campus_id": target_campus,
        "accounts": accounts,
        "campus_total_income": campus_total_in,
        "campus_total_expenses": campus_total_out,
        "campus_starting_balance": round(campus_starting, 2),
        "campus_balance": round(campus_starting + campus_total_in - campus_total_out, 2),
        "campus_net_change": round(campus_total_in - campus_total_out, 2),
    }



# ========== CUSTOMER ACCOUNTS ==========

@router.get("/customers")
async def list_customers(location_id: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List customer accounts. Each customer is linked to a guest and a location."""
    query = {}
    if location_id:
        query["location_id"] = location_id
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    return await db.customer_accounts.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/customers")
async def create_customer(data: dict, current_user: dict = Depends(require_staff)):
    """Create or link a customer account. Optionally link to existing guest."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    location_id = data.get("location_id") or current_user.get("active_campus_id") or ""
    guest_id = data.get("guest_id", "")
    # Auto-link to guest if email/phone matches
    if not guest_id:
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()
        if email or phone:
            q = []
            if email: q.append({"email": email})
            if phone: q.append({"phone": phone})
            guest = await db.guests.find_one({"$or": q}, {"_id": 0, "id": 1})
            if guest:
                guest_id = guest["id"]
    doc = {
        "id": f"cust_{uuid.uuid4().hex[:8]}",
        "name": name,
        "email": (data.get("email") or "").strip().lower(),
        "phone": (data.get("phone") or "").strip(),
        "guest_id": guest_id,
        "location_id": location_id,
        "notes": data.get("notes", ""),
        "total_purchases": 0,
        "total_spent": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.customer_accounts.insert_one(doc)
    doc.pop("_id", None)
    # Also mark the guest as customer
    if guest_id:
        await db.guests.update_one({"id": guest_id}, {"$set": {"is_customer": True, "customer_id": doc["id"]}})
    return doc


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Include purchase history
    purchases = await db.sales.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    customer["purchases"] = purchases
    return customer


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "email", "phone", "notes", "guest_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.customer_accounts.update_one({"id": customer_id}, {"$set": update})
    return await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(require_manager)):
    await db.customer_accounts.delete_one({"id": customer_id})
    return {"message": "Customer account deleted"}


@router.get("/customers/{customer_id}/purchases")
async def get_customer_purchases(customer_id: str, current_user: dict = Depends(get_current_user)):
    purchases = await db.sales.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    total = sum(p.get("total", 0) for p in purchases)
    return {"purchases": purchases, "total_count": len(purchases), "total_spent": total}



# ========== FINANCIAL ACCOUNTS (editable, with starting balance) ==========

@router.get("/financial/campus-accounts/{campus_id}")
async def list_campus_accounts(campus_id: str, current_user: dict = Depends(get_current_user)):
    """List financial accounts for a campus (each sub-location + savings)."""
    accounts = await db.financial_accounts.find({"campus_id": campus_id}, {"_id": 0}).sort("name", 1).to_list(50)
    if not accounts:
        # Auto-create accounts from sub-locations
        subs = await db.locations.find({"$or": [{"parent_id": campus_id}, {"id": campus_id}]}, {"_id": 0, "id": 1, "name": 1}).to_list(50)
        for sub in subs:
            doc = {"id": f"acct_{uuid.uuid4().hex[:8]}", "campus_id": campus_id, "location_id": sub["id"], "name": sub["name"], "type": "operational", "starting_balance": 0, "currency": "UGX", "created_at": datetime.now(timezone.utc).isoformat()}
            await db.financial_accounts.insert_one(doc); doc.pop("_id", None); accounts.append(doc)
        # Add savings account
        savings = {"id": f"acct_{uuid.uuid4().hex[:8]}", "campus_id": campus_id, "location_id": "", "name": "Savings", "type": "savings", "starting_balance": 0, "currency": "UGX", "created_at": datetime.now(timezone.utc).isoformat()}
        await db.financial_accounts.insert_one(savings); savings.pop("_id", None); accounts.append(savings)
    return accounts


@router.put("/financial/campus-accounts/{account_id}")
async def update_campus_account(account_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Update account details (name, starting_balance, currency). Director or Finance Manager."""
    allowed = {"name", "starting_balance", "currency", "type", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.financial_accounts.update_one({"id": account_id}, {"$set": update})
    return await db.financial_accounts.find_one({"id": account_id}, {"_id": 0})


# ========== INTER-ACCOUNT TRANSFERS ==========

@router.post("/financial/transfers")
async def create_transfer(data: dict, current_user: dict = Depends(require_manager)):
    """Transfer between accounts (recorded as expense from source, income to destination)."""
    from_account_id = data.get("from_account_id")
    to_account_id = data.get("to_account_id")
    amount = float(data.get("amount", 0))
    if not from_account_id or not to_account_id or amount <= 0:
        raise HTTPException(status_code=400, detail="from_account_id, to_account_id, and amount required")
    from_acct = await db.financial_accounts.find_one({"id": from_account_id}, {"_id": 0})
    to_acct = await db.financial_accounts.find_one({"id": to_account_id}, {"_id": 0})
    if not from_acct or not to_acct:
        raise HTTPException(status_code=404, detail="Account not found")
    transfer_id = f"txfr_{uuid.uuid4().hex[:8]}"
    # Record expense on source
    await db.expenses.insert_one({
        "id": f"exp_{uuid.uuid4().hex[:8]}", "category": "Transfer Out", "description": f"Transfer to {to_acct['name']}",
        "amount": amount, "date": datetime.now(timezone.utc).isoformat()[:10], "status": "approved",
        "location_id": from_acct.get("location_id", ""), "transfer_id": transfer_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    })
    # Record income on destination
    await db.donations.insert_one({
        "id": f"don_{uuid.uuid4().hex[:8]}", "donor_name": f"Transfer from {from_acct['name']}",
        "amount": amount, "date": datetime.now(timezone.utc).isoformat()[:10], "category": "Transfer In",
        "location_id": to_acct.get("location_id", ""), "transfer_id": transfer_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    })
    doc = {"id": transfer_id, "from_account_id": from_account_id, "to_account_id": to_account_id,
           "from_name": from_acct["name"], "to_name": to_acct["name"], "amount": amount,
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.financial_transfers.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "transfer", transfer_id, {"amount": amount})
    return doc


@router.get("/financial/transfers")
async def list_transfers(campus_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if campus_id:
        acct_ids = [a["id"] for a in await db.financial_accounts.find({"campus_id": campus_id}, {"_id": 0, "id": 1}).to_list(50)]
        query = {"$or": [{"from_account_id": {"$in": acct_ids}}, {"to_account_id": {"$in": acct_ids}}]}
    return await db.financial_transfers.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)


# ========== BUDGETING ==========

@router.get("/financial/budgets")
async def list_budgets(campus_id: Optional[str] = None, period: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if campus_id: query["campus_id"] = campus_id
    if period: query["period"] = period
    return await db.financial_budgets.find(query, {"_id": 0}).sort("period", -1).to_list(100)


@router.post("/financial/budgets")
async def create_budget(data: dict, current_user: dict = Depends(require_manager)):
    """Create/update budget for a sub-location or department."""
    doc = {
        "id": f"bgt_{uuid.uuid4().hex[:8]}",
        "campus_id": data.get("campus_id") or current_user.get("active_campus_id", ""),
        "location_id": data.get("location_id", ""),
        "department": data.get("department", ""),
        "period": data.get("period", datetime.now(timezone.utc).strftime("%Y-%m")),
        "amount": float(data.get("amount", 0)),
        "category": data.get("category", "general"),
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    }
    await db.financial_budgets.insert_one(doc); doc.pop("_id", None)
    return doc


@router.delete("/financial/budgets/{budget_id}")
async def delete_budget(budget_id: str, current_user: dict = Depends(require_manager)):
    await db.financial_budgets.delete_one({"id": budget_id})
    return {"message": "Budget deleted"}


# ========== CATEGORIES & INCOME SOURCES (admin-editable) ==========

@router.get("/financial/categories")
async def list_financial_categories(current_user: dict = Depends(get_current_user)):
    cats = await db.financial_categories.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    if not cats:
        defaults = [
            {"id": "fcat_tithe", "name": "Tithes", "type": "income"}, {"id": "fcat_offering", "name": "Offerings", "type": "income"},
            {"id": "fcat_donation", "name": "Donations", "type": "income"}, {"id": "fcat_grant", "name": "Grants", "type": "income"},
            {"id": "fcat_sales", "name": "Sales Revenue", "type": "income"}, {"id": "fcat_transfer_in", "name": "Transfer In", "type": "income"},
            {"id": "fcat_salary", "name": "Salaries", "type": "expense"}, {"id": "fcat_rent", "name": "Rent/Utilities", "type": "expense"},
            {"id": "fcat_supplies", "name": "Supplies", "type": "expense"}, {"id": "fcat_transport", "name": "Transport", "type": "expense"},
            {"id": "fcat_food", "name": "Food/Meals", "type": "expense"}, {"id": "fcat_maintenance", "name": "Maintenance", "type": "expense"},
            {"id": "fcat_transfer_out", "name": "Transfer Out", "type": "expense"}, {"id": "fcat_other", "name": "Other", "type": "both"},
        ]
        await db.financial_categories.insert_many(defaults)
        for d in defaults: d.pop("_id", None)
        return defaults
    return cats


@router.post("/financial/categories")
async def create_financial_category(data: dict, current_user: dict = Depends(require_admin)):
    doc = {"id": f"fcat_{uuid.uuid4().hex[:8]}", "name": data.get("name", ""), "type": data.get("type", "both"), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.financial_categories.insert_one(doc); doc.pop("_id", None)
    return doc


@router.delete("/financial/categories/{cat_id}")
async def delete_financial_category(cat_id: str, current_user: dict = Depends(require_admin)):
    await db.financial_categories.delete_one({"id": cat_id})
    return {"message": "Category deleted"}


# ========== ASSETS (appreciation default, manual depreciation) ==========

@router.put("/financial/assets/{asset_id}/valuation")


# ========== RECONCILIATION (Finance <-> Chart cash accounts) ==========

@router.get("/financial/reconciliation")
async def financial_reconciliation(location_id: str, current_user: dict = Depends(require_finance_view)):
    """For a given location, compare:
      - Finance sub-location aggregate (all donations − all approved expenses at location_id)
      - Sum of Chart cash account activity at the same location
    Highlights untagged rows so the user can fix drift with one click."""
    # Sub-location totals (all rows at location_id)
    inc = await db.donations.aggregate([{"$match": {"location_id": location_id}}, {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]).to_list(1)
    exp = await db.expenses.aggregate([{"$match": {"location_id": location_id, "status": {"$in": ["approved", None]}}}, {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]).to_list(1)
    sublocation_income = (inc[0]["t"] if inc else 0) or 0
    sublocation_expenses = (exp[0]["t"] if exp else 0) or 0
    sublocation_net = round(sublocation_income - sublocation_expenses, 2)

    # Chart cash accounts at this location — sum their activity (excluding starting_balance)
    accts = await db.chart_accounts.find({"location_id": location_id, "active": {"$ne": False}}, {"_id": 0}).to_list(200)
    from routers.chart_accounts import _batch_compute_balances
    deltas = await _batch_compute_balances([a["id"] for a in accts]) if accts else {}
    chart_delta_sum = round(sum(deltas.values()), 2)
    for a in accts:
        a["balance"] = round(float(a.get("starting_balance", 0) or 0) + deltas.get(a["id"], 0), 2)
        a["activity"] = round(deltas.get(a["id"], 0), 2)

    # Untagged rows at this location
    untagged_don = await db.donations.find({"location_id": location_id, "$or": [{"deposit_to_account_id": {"$exists": False}}, {"deposit_to_account_id": ""}, {"deposit_to_account_id": None}]}, {"_id": 0, "id": 1, "date": 1, "donor_name": 1, "amount": 1, "notes": 1}).to_list(500)
    untagged_exp = await db.expenses.find({"location_id": location_id, "status": {"$in": ["approved", None]}, "$or": [{"paid_from_account_id": {"$exists": False}}, {"paid_from_account_id": ""}, {"paid_from_account_id": None}]}, {"_id": 0, "id": 1, "date": 1, "title": 1, "amount": 1, "vendor": 1}).to_list(500)
    # Sub-location transfers (legacy inter-sublocation moves) — treat as "untagged"
    # when neither the from nor to side references a chart cash account, since those
    # moves shift cash but never touch our chart-account balances.
    untagged_transfers = await db.sublocation_transfers.find({
        "$or": [{"from_location_id": location_id}, {"to_location_id": location_id}],
        "$and": [
            {"$or": [{"from_account_id": {"$exists": False}}, {"from_account_id": ""}, {"from_account_id": None}]},
            {"$or": [{"to_account_id": {"$exists": False}}, {"to_account_id": ""}, {"to_account_id": None}]},
        ],
    }, {"_id": 0, "id": 1, "date": 1, "amount": 1, "from_location_id": 1, "to_location_id": 1, "notes": 1}).to_list(500)
    untagged_income = round(sum((d.get("amount") or 0) for d in untagged_don), 2)
    untagged_expenses = round(sum((e.get("amount") or 0) for e in untagged_exp), 2)
    untagged_net = round(untagged_income - untagged_expenses, 2)

    # Recent chart-account transfers touching this location (context, not "untagged" — transfers
    # are fully-linked by definition, but users like to see them alongside for a full audit).
    loc_account_ids = [a["id"] for a in accts]
    recent_transfers = []
    if loc_account_ids:
        async for t in db.chart_account_transfers.find({
            "$or": [{"from_account_id": {"$in": loc_account_ids}}, {"to_account_id": {"$in": loc_account_ids}}]
        }, {"_id": 0}).sort("date", -1).limit(50):
            recent_transfers.append(t)

    # Matches when: sub-location net == chart_delta_sum. Untagged transactions explain any drift.
    matches = abs(sublocation_net - chart_delta_sum) < 0.01
    return {
        "location_id": location_id,
        "sublocation_income": round(sublocation_income, 2),
        "sublocation_expenses": round(sublocation_expenses, 2),
        "sublocation_net": sublocation_net,
        "chart_delta_sum": chart_delta_sum,
        "untagged_income": untagged_income,
        "untagged_expenses": untagged_expenses,
        "untagged_net": untagged_net,
        "matches": matches,
        "drift": round(sublocation_net - chart_delta_sum, 2),
        "chart_accounts": accts,
        "untagged_donations": untagged_don,
        "untagged_expenses_list": untagged_exp,
        "untagged_transfers": untagged_transfers,
        "recent_transfers": recent_transfers,
    }


@router.post("/financial/reconciliation/auto-tag")
async def reconciliation_auto_tag(data: dict, current_user: dict = Depends(require_finance_admin)):
    """Batch-tag all currently-untagged donations/expenses at a location to a
    caller-picked chart account (default: the location's default_cash_account_id).
    Body: { location_id: str, account_id?: str (falls back to default_cash), only?: 'donations'|'expenses'|'both' }"""
    location_id = data.get("location_id")
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id required")
    only = data.get("only") or "both"
    account_id = data.get("account_id") or ""
    if not account_id:
        ss = await db.store_settings.find_one({"location_id": location_id}, {"_id": 0, "default_cash_account_id": 1}) or {}
        account_id = ss.get("default_cash_account_id") or ""
    if not account_id:
        raise HTTPException(status_code=400, detail="No account_id given and no default_cash_account_id set on this location")
    # Validate account exists + belongs to (or is org-wide) location
    acct = await db.chart_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Chart account not found")

    results = {"donations_tagged": 0, "expenses_tagged": 0, "account_id": account_id}
    untagged_filter_don = {"location_id": location_id, "$or": [{"deposit_to_account_id": {"$exists": False}}, {"deposit_to_account_id": ""}, {"deposit_to_account_id": None}]}
    untagged_filter_exp = {"location_id": location_id, "$or": [{"paid_from_account_id": {"$exists": False}}, {"paid_from_account_id": ""}, {"paid_from_account_id": None}]}
    if only in ("donations", "both"):
        r = await db.donations.update_many(untagged_filter_don, {"$set": {"deposit_to_account_id": account_id, "deposit_auto_tagged_batch": True}})
        results["donations_tagged"] = r.modified_count
    if only in ("expenses", "both"):
        r = await db.expenses.update_many(untagged_filter_exp, {"$set": {"paid_from_account_id": account_id, "paid_auto_tagged_batch": True}})
        results["expenses_tagged"] = r.modified_count
    await _audit(current_user["id"], "batch_tag", "reconciliation", None, {"location_id": location_id, **results})
    return results

async def update_asset_valuation(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Manually update asset current value. Supports appreciation (default) or depreciation."""
    new_value = data.get("current_value")
    method = data.get("method", "appreciation")  # appreciation or depreciation
    if new_value is None:
        raise HTTPException(status_code=400, detail="current_value required")
    await db.assets.update_one({"id": asset_id}, {"$set": {
        "current_value": float(new_value), "valuation_method": method,
        "last_valued_at": datetime.now(timezone.utc).isoformat(), "valued_by": current_user["id"],
    }})
    return await db.assets.find_one({"id": asset_id}, {"_id": 0})





@router.post("/financial/repair-wrong-journal")
async def repair_wrong_journal(current_user: dict = Depends(require_admin)):
    """One-time migration (iter210b): re-tag auto-posted journal entries that
    were routed to a SALES journal by the old '$or any active' fallback.
    Moves them to the location's miscellaneous journal (creating one if needed).
    Idempotent — skips entries already on a non-sales journal.

    Fixes production ledgers where every donation/expense was numbered
    SALES/... because no miscellaneous journal existed at the location.
    """
    entries_fixed = 0
    journals_created = 0
    scanned = 0
    # Find all JEs whose current journal is a SALES-kind journal but that
    # were auto-posted from donation/expense/payroll (which should never be
    # in a sales journal).
    sales_journals = await db.accounting_journals.find({"kind": "sales"}, {"_id": 0, "id": 1, "location_id": 1}).to_list(200)
    sales_journal_ids = {j["id"] for j in sales_journals}
    if not sales_journal_ids:
        return {"scanned": 0, "entries_fixed": 0, "journals_created": 0, "message": "No sales journals found — nothing to repair."}
    async for je in db.accounting_entries.find(
        {"journal_id": {"$in": list(sales_journal_ids)}, "auto_generated_from": {"$in": ["donation", "expense", "payroll"]}},
        {"_id": 0, "id": 1, "location_id": 1, "auto_generated_from": 1},
    ):
        scanned += 1
        loc_id = je.get("location_id")
        if not loc_id:
            continue
        # Find or create a miscellaneous journal at this location
        misc = await db.accounting_journals.find_one(
            {"location_id": loc_id, "kind": "miscellaneous", "active": True},
            {"_id": 0, "id": 1, "code": 1},
        )
        if not misc:
            misc = {
                "id": f"jrn_{uuid.uuid4().hex[:10]}",
                "code": "GL",
                "name": "General Ledger",
                "kind": "miscellaneous",
                "location_id": loc_id,
                "active": True,
                "auto_created": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": current_user["id"],
            }
            await db.accounting_journals.insert_one(misc)
            misc.pop("_id", None)
            journals_created += 1
        # Re-tag the JE header + its lines
        await db.accounting_entries.update_one(
            {"id": je["id"]},
            {"$set": {"journal_id": misc["id"], "journal_code": misc.get("code")}},
        )
        await db.accounting_entry_lines.update_many(
            {"entry_id": je["id"]},
            {"$set": {"journal_id": misc["id"]}},
        )
        entries_fixed += 1
    await _audit(current_user["id"], "repair", "wrong_journal", None, {"scanned": scanned, "fixed": entries_fixed, "journals_created": journals_created})
    return {
        "scanned": scanned,
        "entries_fixed": entries_fixed,
        "journals_created": journals_created,
        "message": f"Scanned {scanned} auto-posted entries mis-attributed to a sales journal. Re-tagged {entries_fixed} entries; auto-created {journals_created} General Ledger journals.",
    }


@router.post("/financial/repair-starting-balances")
async def repair_starting_balances(current_user: dict = Depends(require_admin)):
    """One-time migration (iter208d): copy any legacy per-sub-location
    `financial_accounts.starting_balance` into a chart cash account for that
    location so the two views agree.  Idempotent — skips locations that already
    have chart accounts carrying a starting balance.

    Behaviour per legacy record with `starting_balance > 0`:
      - If the location already has ≥1 active chart account with any
        `starting_balance > 0`: skip (assume already migrated).
      - Otherwise: find the location's first active chart account and stamp
        the legacy value onto its `starting_balance`. If no active chart
        account exists, create one named "Opening Cash".
    """
    migrated = []
    skipped_already_migrated = []
    created_accounts = []
    async for legacy in db.financial_accounts.find({"starting_balance": {"$gt": 0}}, {"_id": 0}):
        loc_id = legacy.get("location_id")
        amount = float(legacy.get("starting_balance") or 0)
        if not loc_id or amount <= 0:
            continue
        # Any active chart account at this location already carrying opening cash?
        existing = await db.chart_accounts.find_one(
            {"location_id": loc_id, "active": {"$ne": False}, "starting_balance": {"$gt": 0}},
            {"_id": 0, "id": 1, "starting_balance": 1},
        )
        if existing:
            skipped_already_migrated.append({"location_id": loc_id, "chart_account_id": existing["id"]})
            continue
        # Find first active chart account at this location
        target = await db.chart_accounts.find_one(
            {"location_id": loc_id, "active": {"$ne": False}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if target:
            await db.chart_accounts.update_one(
                {"id": target["id"]},
                {"$set": {"starting_balance": amount, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            migrated.append({"location_id": loc_id, "chart_account_id": target["id"], "name": target.get("name"), "amount": amount})
        else:
            new_acct = {
                "id": f"cha_{uuid.uuid4().hex[:10]}",
                "name": "Opening Cash",
                "location_id": loc_id,
                "campus_id": legacy.get("campus_id"),
                "starting_balance": amount,
                "currency": legacy.get("currency", "UGX"),
                "active": True,
                "assigned_user_ids": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.chart_accounts.insert_one(new_acct)
            new_acct.pop("_id", None)
            created_accounts.append({"location_id": loc_id, "chart_account_id": new_acct["id"], "amount": amount})
        # Zero the legacy field so it no longer competes
        await db.financial_accounts.update_one(
            {"id": legacy["id"]},
            {"$set": {"starting_balance": 0, "migrated_to_chart_accounts_at": datetime.now(timezone.utc).isoformat()}},
        )
    # Bust balance cache so users see the new numbers immediately
    from routers.chart_accounts import invalidate_balance_cache
    invalidate_balance_cache()
    await _audit(current_user["id"], "repair", "starting_balances", None, {
        "migrated": len(migrated), "created": len(created_accounts), "skipped": len(skipped_already_migrated),
    })
    return {
        "migrated": migrated,
        "created_accounts": created_accounts,
        "skipped_already_migrated": skipped_already_migrated,
        "message": (
            f"Migrated {len(migrated)} legacy starting balances into existing chart accounts, "
            f"created {len(created_accounts)} new chart accounts, "
            f"skipped {len(skipped_already_migrated)} already-migrated locations."
        ),
    }


# ========== RETROACTIVE REPAIR: Orphaned Journal Entries ==========
# When donations/expenses were deleted BEFORE the cascade-reverse fix landed,
# their auto-posted journal entries were left behind — causing the Trial
# Balance to drift from the Finance module totals. This endpoint scans all
# auto-generated journal entries and reverses the ones whose source record
# no longer exists.  It is idempotent (skips already-reversed entries) and
# safe to re-run.

@router.post("/financial/repair-orphaned-journals")
async def repair_orphaned_journals(current_user: dict = Depends(require_admin)):
    """Scan every auto-posted JE and reverse the ones whose source record was deleted.

    Returns per-kind counts of what was reversed / already-clean / skipped.
    Idempotent — safe to run multiple times.
    """
    from routers.accounting import reverse_entry
    reversed_count = 0
    already_reversed = 0
    orphan_ids: list = []
    scanned = 0
    # Only touch entries auto-generated from finance sources (donation, expense).
    # Never touch manually-created journal entries.
    cursor = db.accounting_entries.find(
        {"auto_generated_from": {"$in": ["donation", "expense"]}, "status": "posted"},
        {"_id": 0, "id": 1, "auto_generated_from": 1, "source_id": 1, "is_reversed": 1},
    )
    async for je in cursor:
        scanned += 1
        source_kind = je.get("auto_generated_from")
        source_id = je.get("source_id")
        if not source_id or not source_kind:
            continue
        # Check if the source still exists
        coll = db.donations if source_kind == "donation" else db.expenses
        exists = await coll.find_one({"id": source_id}, {"_id": 0, "id": 1})
        if exists:
            continue  # not orphaned — leave as-is
        orphan_ids.append(je["id"])
        if je.get("is_reversed"):
            already_reversed += 1
            continue
        try:
            await reverse_entry(je["id"], {"reason": f"Retroactive repair — orphaned {source_kind}"}, current_user)
            reversed_count += 1
        except Exception as ex:
            logger.error(f"Retroactive repair failed for JE {je['id']}: {ex}")
    await _audit(current_user["id"], "repair", "orphaned_journals", None, {
        "scanned": scanned, "orphans_found": len(orphan_ids), "reversed": reversed_count, "already_reversed": already_reversed,
    })
    logger.warning(f"REPAIR ORPHANED JOURNALS by {current_user.get('email','?')} — scanned={scanned} orphans={len(orphan_ids)} reversed={reversed_count}")
    return {
        "scanned": scanned,
        "orphans_found": len(orphan_ids),
        "reversed": reversed_count,
        "already_reversed": already_reversed,
        "message": (
            f"Scanned {scanned} auto-posted journal entries. Found {len(orphan_ids)} orphans "
            f"(source donation/expense deleted). Reversed {reversed_count}; "
            f"{already_reversed} were already reversed."
        ),
    }


# ========== FINANCIAL RESET (nuclear — clears test transactions) ==========
# Admin-only. Requires the caller to POST `confirm: "RESET"` in the body,
# plus an explicit scope + list of collections to wipe. This exists because
# testing mistakes leave stale balances that are painful to clean row-by-row.
# Filters honour location + date range so a director can wipe only a single
# campus's test data without touching another campus's real records.

ALLOWED_RESET_COLLECTIONS = {
    "donations": "donations",
    "expenses": "expenses",
    "sales": "sales",
    "accounting_entries": "accounting_entries",
    "accounting_entry_lines": "accounting_entry_lines",
    "budgets": "financial_budgets",
    "chart_account_transfers": "chart_account_transfers",
    "assets": "assets",
    "sublocation_transfers": "sublocation_transfers",
    "hr_payslips": "hr_payslips",  # optional — nuke test payslips too
}


@router.post("/financial/reset")
async def reset_financial_data(data: dict, current_user: dict = Depends(require_admin)):
    """Wipe financial transactional data. STRICT admin-only. Body:
    {
      "confirm": "RESET",                          # must equal this exactly
      "scope": "all" | "location" | "period",       # controls the filter
      "location_id": "loc_001",                    # required if scope=location
      "date_from": "2026-01-01",                    # optional YYYY-MM-DD
      "date_to":   "2026-02-28",
      "include": ["donations","expenses","sales",...],  # subset of ALLOWED_RESET_COLLECTIONS keys
      "reset_chart_account_starting_balances": false,   # optional — zero starting_balance too
    }
    Returns per-collection deleted counts.
    Chart accounts themselves are NEVER deleted — only their transactions are wiped, so
    balances recompute correctly (starting_balance + zero transactions = starting_balance).
    """
    if data.get("confirm") != "RESET":
        raise HTTPException(status_code=400, detail="confirm must equal 'RESET' (case-sensitive) to proceed")
    scope = data.get("scope") or "all"
    location_id = data.get("location_id") or ""
    date_from = data.get("date_from") or ""
    date_to = data.get("date_to") or ""
    include = data.get("include") or list(ALLOWED_RESET_COLLECTIONS.keys())
    if scope == "location" and not location_id:
        raise HTTPException(status_code=400, detail="location_id required when scope='location'")
    if scope == "period" and not (date_from or date_to):
        raise HTTPException(status_code=400, detail="date_from and/or date_to required when scope='period'")

    # Build the base filter shared across collections
    def base_filter(date_field: str = "date") -> dict:
        f: dict = {}
        if scope == "location" or location_id:
            f["location_id"] = location_id
        if date_from and date_to:
            f[date_field] = {"$gte": date_from, "$lte": date_to}
        elif date_from:
            f[date_field] = {"$gte": date_from}
        elif date_to:
            f[date_field] = {"$lte": date_to}
        return f

    results = {}
    entry_ids_to_wipe = []

    for key in include:
        if key not in ALLOWED_RESET_COLLECTIONS:
            continue
        coll_name = ALLOWED_RESET_COLLECTIONS[key]
        # Sales use "created_at" for date field but also have location_id; use dedicated logic
        if key == "sales":
            f = base_filter("created_at")
        elif key == "accounting_entries":
            f = base_filter("date")
            # Pre-fetch entry ids so we can also wipe their lines
            async for e in db.accounting_entries.find(f, {"_id": 0, "id": 1}):
                entry_ids_to_wipe.append(e["id"])
        elif key == "accounting_entry_lines":
            # Wipe orphaned lines matching the pre-collected entry ids
            if entry_ids_to_wipe:
                f = {"entry_id": {"$in": entry_ids_to_wipe}}
            else:
                # Standalone use — apply base filter directly (uses 'date')
                f = base_filter("date")
        elif key == "hr_payslips":
            f = {}
            if location_id:
                f["location_id"] = location_id
            if date_from and date_to:
                f["period"] = {"$gte": date_from[:7], "$lte": date_to[:7]}
        else:
            f = base_filter("date")
        res = await db[coll_name].delete_many(f)
        results[key] = res.deleted_count

    # Optional: also zero the starting_balance on chart accounts (rare, per-request opt-in)
    if data.get("reset_chart_account_starting_balances"):
        q = {}
        if location_id:
            q["location_id"] = location_id
        chart_res = await db.chart_accounts.update_many(q, {"$set": {"starting_balance": 0}})
        results["chart_account_starting_balances_zeroed"] = chart_res.modified_count

    await _audit(current_user["id"], "reset", "financial_module", None, {
        "scope": scope, "location_id": location_id, "date_from": date_from, "date_to": date_to,
        "results": results,
    })
    logger.warning(f"FINANCIAL RESET by {current_user.get('email','?')} — scope={scope} loc={location_id or 'ALL'} results={results}")
    return {"reset": True, "scope": scope, "location_id": location_id, "date_from": date_from, "date_to": date_to, "deleted": results}
