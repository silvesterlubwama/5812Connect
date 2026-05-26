"""Bank accounts, statement import + reconciliation, vendors, bills (AP),
recurring journal entries / bills.

This module wires into the existing accounting ledger (`accounting_*` collections)
— every cash movement from a bank account or a paid bill auto-posts a balanced
journal entry via the existing `accounting_entries` / `accounting_entry_lines`.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from deps import (
    db, get_current_user, require_staff, require_director, require_admin,
    require_manager, _audit, logger, get_campus_filter,
    require_finance_view, require_finance_admin,
)
from datetime import datetime, timezone, timedelta, date as dt_date
from typing import Optional, List, Dict, Any
import uuid
import re
import io
import csv

router = APIRouter(prefix="/api/bank", tags=["bank"])

BANK_ACCOUNT_TYPES = {"checking", "savings", "mobile_money", "fixed_deposit", "credit_card"}
BILL_STATUSES = {"draft", "open", "partially_paid", "paid", "void"}
RECURRING_KINDS = {"journal_entry", "bill"}
RECURRING_SCHEDULES = {"daily", "weekly", "biweekly", "monthly", "quarterly", "yearly"}


# ============================================================
# BANK ACCOUNTS
# ============================================================

@router.get("/accounts")
async def list_bank_accounts(country: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope, "active": True} if scope else {"active": True}
    if country:
        query["country"] = country.upper()
    accounts = await db.bank_accounts.find(query, {"_id": 0}).sort("name", 1).to_list(200)
    # Compute current balance from posted journal entries hitting the linked CoA account
    for acc in accounts:
        linked = acc.get("linked_account_id")
        if linked:
            pipeline = [
                {"$match": {"account_id": linked, "status": "posted"}},
                {"$group": {"_id": None, "debit": {"$sum": "$debit"}, "credit": {"$sum": "$credit"}}},
            ]
            row = await db.accounting_entry_lines.aggregate(pipeline).to_list(1)
            if row:
                acc["current_balance"] = round(
                    float(acc.get("opening_balance") or 0) + (row[0]["debit"] - row[0]["credit"]), 2
                )
            else:
                acc["current_balance"] = float(acc.get("opening_balance") or 0)
        else:
            acc["current_balance"] = float(acc.get("opening_balance") or 0)
    return accounts


@router.post("/accounts")
async def create_bank_account(data: dict, current_user: dict = Depends(require_finance_admin)):
    """Create a bank account linked to a CoA cash account.
    Body: { name, bank_name, account_number, account_type, currency, country, branch?,
            swift_bic?, iban?, opening_balance?, opening_balance_date?, linked_account_id, location_id? }"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    account_type = (data.get("account_type") or "checking").strip()
    if account_type not in BANK_ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail=f"account_type must be in {sorted(BANK_ACCOUNT_TYPES)}")
    linked_account_id = data.get("linked_account_id")
    if linked_account_id:
        linked = await db.accounting_accounts.find_one({"id": linked_account_id}, {"_id": 0, "type": 1})
        if not linked:
            raise HTTPException(status_code=400, detail="linked_account_id not found in chart of accounts")
        if not linked.get("type", "").startswith("asset_"):
            raise HTTPException(status_code=400, detail="linked CoA account must be an asset (cash/bank)")
    doc = {
        "id": f"bnk_{uuid.uuid4().hex[:10]}",
        "name": name[:120],
        "bank_name": (data.get("bank_name") or "")[:120],
        "account_number": (data.get("account_number") or "")[:40],
        "account_type": account_type,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "country": (data.get("country") or "UG").upper()[:3],
        "branch": (data.get("branch") or "")[:120],
        "swift_bic": (data.get("swift_bic") or "")[:20],
        "iban": (data.get("iban") or "")[:40],
        "opening_balance": float(data.get("opening_balance") or 0),
        "opening_balance_date": (data.get("opening_balance_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10],
        "linked_account_id": linked_account_id,
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "active": True,
        "notes": (data.get("notes") or "")[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.bank_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/accounts/{acc_id}")
async def update_bank_account(acc_id: str, data: dict, current_user: dict = Depends(require_finance_admin)):
    allowed = {"name", "bank_name", "account_number", "account_type", "branch",
               "swift_bic", "iban", "linked_account_id", "active", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "account_type" in update and update["account_type"] not in BANK_ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="invalid account_type")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.bank_accounts.update_one({"id": acc_id}, {"$set": update})
    return await db.bank_accounts.find_one({"id": acc_id}, {"_id": 0})


@router.delete("/accounts/{acc_id}")
async def delete_bank_account(acc_id: str, current_user: dict = Depends(require_admin)):
    # Don't destroy if any imported statements / transactions exist
    has_tx = await db.bank_transactions.find_one({"bank_account_id": acc_id})
    if has_tx:
        await db.bank_accounts.update_one({"id": acc_id}, {"$set": {"active": False}})
        return {"deactivated": True, "note": "Bank account has transactions — deactivated instead of deleted"}
    await db.bank_accounts.delete_one({"id": acc_id})
    return {"deleted": True}


# ============================================================
# CSV / OFX STATEMENT IMPORT
# ============================================================

def _detect_csv_columns(headers: list) -> dict:
    """Heuristically map common bank-CSV column headers to our canonical fields.
    Returns dict: { date, description, amount, debit, credit, reference, balance }.
    Missing keys mean the importer will rely on per-row hints."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())  # noqa: E731
    cols = {}
    for idx, h in enumerate(headers):
        n = norm(h)
        if n in {"date", "txdate", "transactiondate", "valuedate", "postingdate", "postdate"} and "date" not in cols:
            cols["date"] = idx
        elif n in {"description", "details", "narration", "particulars", "memo", "transactiondetails", "remarks"} and "description" not in cols:
            cols["description"] = idx
        elif n in {"amount", "txamount"} and "amount" not in cols:
            cols["amount"] = idx
        elif n in {"debit", "withdrawal", "out", "moneyout"} and "debit" not in cols:
            cols["debit"] = idx
        elif n in {"credit", "deposit", "in", "moneyin"} and "credit" not in cols:
            cols["credit"] = idx
        elif n in {"reference", "ref", "txnref", "transactionid", "txnid"} and "reference" not in cols:
            cols["reference"] = idx
        elif n in {"balance", "runningbalance", "bookbalance"} and "balance" not in cols:
            cols["balance"] = idx
    return cols


def _parse_money(s: str) -> float:
    """Parse a money value tolerating commas, currency prefixes, parens-for-negative."""
    if s is None:
        return 0.0
    raw = str(s).strip()
    if not raw or raw.lower() in {"-", "nil", "na", "n/a"}:
        return 0.0
    neg = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^\d.\-]", "", raw.replace(",", ""))
    try:
        v = float(cleaned) if cleaned not in {"", "-", "."} else 0.0
    except ValueError:
        return 0.0
    return -abs(v) if neg else v


def _parse_date_tolerant(s: str) -> Optional[str]:
    """Return YYYY-MM-DD or None. Accepts dd/mm/yyyy, mm/dd/yyyy, yyyy-mm-dd, dd-mmm-yyyy, etc."""
    if not s:
        return None
    raw = str(s).strip()
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y",
        "%d-%b-%Y", "%d-%b-%y", "%d %B %Y", "%Y%m%d", "%d/%m/%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


@router.post("/accounts/{acc_id}/import-csv")
async def import_csv_statement(
    acc_id: str,
    file: UploadFile = File(...),
    column_map: Optional[str] = Form(None),  # JSON string {date, description, ...}
    current_user: dict = Depends(require_finance_view),
):
    """Import a bank statement CSV. The importer auto-detects common column names
    but accepts an explicit `column_map` JSON for non-standard banks.

    Workflow: imports as `unreconciled` bank_transactions. Auto-suggestions from
    bank_rules engine are applied. Staff then reconcile/categorise per row."""
    import json as _json
    bank_acc = await db.bank_accounts.find_one({"id": acc_id}, {"_id": 0})
    if not bank_acc:
        raise HTTPException(status_code=404, detail="Bank account not found")
    contents = (await file.read()).decode("utf-8", errors="ignore")
    if not contents.strip():
        raise HTTPException(status_code=400, detail="Empty file")
    reader = csv.reader(io.StringIO(contents))
    rows = list(reader)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="CSV needs a header and at least one data row")
    headers = rows[0]
    data_rows = rows[1:]
    cols = _detect_csv_columns(headers)
    if column_map:
        try:
            override = _json.loads(column_map)
            for k, v in override.items():
                if isinstance(v, int):
                    cols[k] = v
        except Exception:
            pass
    if "date" not in cols:
        raise HTTPException(status_code=400, detail=f"Couldn't detect a date column from headers: {headers}")
    if "description" not in cols:
        raise HTTPException(status_code=400, detail="Couldn't detect a description/narration column")
    if "amount" not in cols and "debit" not in cols and "credit" not in cols:
        raise HTTPException(status_code=400, detail="Couldn't detect amount/debit/credit columns")

    # Load active categorization rules once
    rules = await db.bank_rules.find({"is_active": True}, {"_id": 0}).sort("priority", 1).to_list(500)
    compiled_rules = []
    for r in rules:
        try:
            compiled_rules.append((re.compile(r.get("match_pattern", ""), re.IGNORECASE), r))
        except re.error:
            continue

    statement_id = f"stmt_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    transactions = []
    total_credits = 0.0
    total_debits = 0.0
    earliest = None
    latest = None
    for r_idx, row in enumerate(data_rows):
        if not row or all(not (c or "").strip() for c in row):
            continue
        def cell(key):
            idx = cols.get(key)
            return row[idx].strip() if idx is not None and idx < len(row) else ""
        d_iso = _parse_date_tolerant(cell("date"))
        if not d_iso:
            continue
        desc = cell("description")[:300]
        ref = cell("reference")[:120]
        if "amount" in cols:
            amount = _parse_money(cell("amount"))
        else:
            debit = _parse_money(cell("debit"))
            credit = _parse_money(cell("credit"))
            amount = credit - debit  # positive = inflow
        if amount == 0:
            continue
        balance = _parse_money(cell("balance")) if "balance" in cols else None
        # Apply rules
        suggested_account_id = None
        applied_rule_id = None
        for pattern, rule in compiled_rules:
            if pattern.search(desc) or pattern.search(ref):
                suggested_account_id = rule.get("target_account_id")
                applied_rule_id = rule.get("id")
                break
        tx = {
            "id": f"btx_{uuid.uuid4().hex[:10]}",
            "statement_id": statement_id,
            "bank_account_id": acc_id,
            "date": d_iso,
            "description": desc,
            "reference": ref,
            "amount": amount,
            "balance": balance,
            "status": "unreconciled",
            "matched_entry_id": None,
            "suggested_account_id": suggested_account_id,
            "applied_rule_id": applied_rule_id,
            "notes": "",
            "imported_at": now_iso,
            "imported_by": current_user["id"],
            "row_index": r_idx,
            "location_id": bank_acc.get("location_id"),
        }
        transactions.append(tx)
        if amount > 0:
            total_credits += amount
        else:
            total_debits += -amount
        earliest = d_iso if not earliest or d_iso < earliest else earliest
        latest = d_iso if not latest or d_iso > latest else latest
    if not transactions:
        raise HTTPException(status_code=400, detail="No valid transactions found in file")
    # Persist
    await db.bank_transactions.insert_many(transactions)
    statement = {
        "id": statement_id,
        "bank_account_id": acc_id,
        "bank_account_name": bank_acc.get("name"),
        "period_start": earliest,
        "period_end": latest,
        "source_filename": file.filename[:200],
        "format": "csv",
        "uploaded_at": now_iso,
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
        "transaction_count": len(transactions),
        "total_credits": round(total_credits, 2),
        "total_debits": round(total_debits, 2),
        "location_id": bank_acc.get("location_id"),
        "auto_suggested_count": sum(1 for t in transactions if t["suggested_account_id"]),
    }
    await db.bank_statements.insert_one(statement)
    statement.pop("_id", None)
    await _audit(current_user["id"], "import", "bank_statement", statement_id,
                 {"bank": bank_acc.get("name"), "rows": len(transactions)})
    return statement


@router.get("/statements")
async def list_statements(bank_account_id: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    query = {}
    if bank_account_id:
        query["bank_account_id"] = bank_account_id
    else:
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    return await db.bank_statements.find(query, {"_id": 0}).sort("uploaded_at", -1).to_list(200)


@router.get("/transactions")
async def list_transactions(
    bank_account_id: Optional[str] = None,
    statement_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 500,
    current_user: dict = Depends(require_finance_view),
):
    query = {}
    if bank_account_id:
        query["bank_account_id"] = bank_account_id
    if statement_id:
        query["statement_id"] = statement_id
    if status:
        query["status"] = status
    if not (bank_account_id or statement_id):
        scope = await get_campus_filter(current_user)
        if scope:
            query.update(scope)
    return await db.bank_transactions.find(query, {"_id": 0}).sort("date", -1).to_list(min(limit, 2000))


# ============================================================
# CATEGORIZATION RULES
# ============================================================

@router.get("/rules")
async def list_rules(current_user: dict = Depends(require_finance_view)):
    return await db.bank_rules.find({}, {"_id": 0}).sort("priority", 1).to_list(500)


@router.post("/rules")
async def create_rule(data: dict, current_user: dict = Depends(require_finance_admin)):
    """Create a categorization rule.
    Body: { name, match_pattern (regex), target_account_id, priority?, is_active? }"""
    name = (data.get("name") or "").strip()
    pattern = (data.get("match_pattern") or "").strip()
    target = data.get("target_account_id")
    if not name or not pattern or not target:
        raise HTTPException(status_code=400, detail="name, match_pattern, target_account_id required")
    # Validate regex
    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
    if not await db.accounting_accounts.find_one({"id": target}):
        raise HTTPException(status_code=400, detail="target_account_id not in CoA")
    doc = {
        "id": f"rule_{uuid.uuid4().hex[:10]}",
        "name": name[:120],
        "match_pattern": pattern,
        "target_account_id": target,
        "priority": int(data.get("priority") or 100),
        "is_active": bool(data.get("is_active", True)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.bank_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, data: dict, current_user: dict = Depends(require_finance_admin)):
    allowed = {"name", "match_pattern", "target_account_id", "priority", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "match_pattern" in update:
        try:
            re.compile(update["match_pattern"], re.IGNORECASE)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
    await db.bank_rules.update_one({"id": rule_id}, {"$set": update})
    return await db.bank_rules.find_one({"id": rule_id}, {"_id": 0})


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, current_user: dict = Depends(require_finance_admin)):
    await db.bank_rules.delete_one({"id": rule_id})
    return {"deleted": True}


# ============================================================
# RECONCILIATION
# ============================================================

async def _post_bank_tx_to_ledger(tx: dict, target_account_id: str, current_user: dict) -> str:
    """Create + post a balanced JE for a bank-statement transaction.
    Returns the entry_id."""
    bank_acc = await db.bank_accounts.find_one({"id": tx["bank_account_id"]}, {"_id": 0})
    if not bank_acc:
        raise HTTPException(status_code=400, detail="Bank account missing")
    if not bank_acc.get("linked_account_id"):
        raise HTTPException(status_code=400, detail="Bank account has no linked CoA account — set linked_account_id first")
    target = await db.accounting_accounts.find_one({"id": target_account_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=400, detail="target CoA account missing")
    # Pick a misc journal at this location
    journal = (await db.accounting_journals.find_one(
        {"location_id": bank_acc.get("location_id"), "kind": "miscellaneous", "active": True}, {"_id": 0}
    )) or (await db.accounting_journals.find_one(
        {"location_id": bank_acc.get("location_id"), "active": True}, {"_id": 0}
    ))
    if not journal:
        raise HTTPException(status_code=400, detail="No journal configured for this location")
    amount = abs(float(tx.get("amount") or 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Transaction amount is zero")
    # Inflow: Dr Bank / Cr Target. Outflow: Dr Target / Cr Bank.
    if tx["amount"] > 0:
        debit_acc = bank_acc["linked_account_id"]
        credit_acc = target_account_id
    else:
        debit_acc = target_account_id
        credit_acc = bank_acc["linked_account_id"]
    from routers.accounting import _next_entry_number
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal["id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": entry_id, "number": entry_number,
        "journal_id": journal["id"], "journal_code": journal.get("code"),
        "date": tx["date"], "ref": tx.get("reference") or tx["id"],
        "narration": tx.get("description", "")[:200],
        "total_debit": amount, "total_credit": amount,
        "status": "posted",
        "location_id": bank_acc.get("location_id"),
        "currency": bank_acc.get("currency"),
        "auto_generated_from": "bank_tx",
        "source_id": tx["id"],
        "created_at": now_iso, "posted_at": now_iso, "posted_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    await db.accounting_entry_lines.insert_many([
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": tx["date"], "location_id": bank_acc.get("location_id"),
         "status": "posted", "account_id": debit_acc, "debit": amount, "credit": 0,
         "description": tx.get("description", "")[:200]},
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": tx["date"], "location_id": bank_acc.get("location_id"),
         "status": "posted", "account_id": credit_acc, "debit": 0, "credit": amount,
         "description": tx.get("description", "")[:200]},
    ])
    return entry_id


@router.post("/transactions/{tx_id}/reconcile")
async def reconcile_transaction(tx_id: str, data: dict, current_user: dict = Depends(require_finance_view)):
    """Reconcile a bank transaction by either:
      - Matching an existing journal entry: { matched_entry_id }
      - Posting a new JE to a category account: { target_account_id }
      - Marking as ignored: { action: 'ignore' }"""
    tx = await db.bank_transactions.find_one({"id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.get("status") == "matched":
        raise HTTPException(status_code=400, detail="Transaction already reconciled")
    action = data.get("action")
    if action == "ignore":
        await db.bank_transactions.update_one({"id": tx_id}, {"$set": {
            "status": "ignored",
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
            "reconciled_by": current_user["id"],
        }})
        return {"ignored": True}
    matched_entry_id = data.get("matched_entry_id")
    target_account_id = data.get("target_account_id")
    if matched_entry_id:
        entry = await db.accounting_entries.find_one({"id": matched_entry_id}, {"_id": 0, "id": 1})
        if not entry:
            raise HTTPException(status_code=400, detail="matched_entry_id not found")
        entry_id = matched_entry_id
    elif target_account_id:
        entry_id = await _post_bank_tx_to_ledger(tx, target_account_id, current_user)
    else:
        raise HTTPException(status_code=400, detail="Provide matched_entry_id OR target_account_id OR action='ignore'")
    await db.bank_transactions.update_one({"id": tx_id}, {"$set": {
        "status": "matched",
        "matched_entry_id": entry_id,
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
        "reconciled_by": current_user["id"],
    }})
    return {"reconciled": True, "entry_id": entry_id}


@router.post("/transactions/bulk-apply-suggestions")
async def bulk_apply_suggestions(data: dict, current_user: dict = Depends(require_finance_view)):
    """Reconcile all unreconciled transactions for a bank account that already have
    a `suggested_account_id` (from auto-rules). Skips ones without a suggestion."""
    bank_account_id = data.get("bank_account_id")
    if not bank_account_id:
        raise HTTPException(status_code=400, detail="bank_account_id required")
    txns = await db.bank_transactions.find({
        "bank_account_id": bank_account_id,
        "status": "unreconciled",
        "suggested_account_id": {"$ne": None},
    }, {"_id": 0}).to_list(500)
    posted = 0
    skipped = 0
    for tx in txns:
        try:
            entry_id = await _post_bank_tx_to_ledger(tx, tx["suggested_account_id"], current_user)
            await db.bank_transactions.update_one({"id": tx["id"]}, {"$set": {
                "status": "matched",
                "matched_entry_id": entry_id,
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
                "reconciled_by": current_user["id"],
                "auto_reconciled": True,
            }})
            posted += 1
        except Exception as e:
            logger.warning(f"Bulk-apply skipped {tx['id']}: {e}")
            skipped += 1
    return {"posted": posted, "skipped": skipped}


# ============================================================
# VENDORS
# ============================================================

@router.get("/vendors")
async def list_vendors(search: Optional[str] = None, current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope} if scope else {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    vendors = await db.vendors.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    # Compute outstanding AP balance per vendor
    for v in vendors:
        bills = await db.bills.find({"vendor_id": v["id"], "status": {"$in": ["open", "partially_paid"]}}, {"_id": 0}).to_list(500)
        v["outstanding_balance"] = round(sum(float(b.get("balance") or 0) for b in bills), 2)
    return vendors


@router.post("/vendors")
async def create_vendor(data: dict, current_user: dict = Depends(require_finance_view)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    doc = {
        "id": f"vnd_{uuid.uuid4().hex[:10]}",
        "name": name[:200],
        "tin": (data.get("tin") or "")[:40],  # Uganda TIN (Tax Identification Number)
        "vat_registered": bool(data.get("vat_registered", False)),
        "contact_name": (data.get("contact_name") or "")[:120],
        "email": (data.get("email") or "")[:120].lower(),
        "phone": (data.get("phone") or "")[:40],
        "address": (data.get("address") or "")[:300],
        "country": (data.get("country") or "UG").upper()[:3],
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "payment_terms_days": int(data.get("payment_terms_days") or 30),
        "default_account_id": data.get("default_account_id"),
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "active": True,
        "notes": (data.get("notes") or "")[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.vendors.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/vendors/{vid}")
async def update_vendor(vid: str, data: dict, current_user: dict = Depends(require_finance_view)):
    allowed = {"name", "tin", "vat_registered", "contact_name", "email", "phone",
               "address", "country", "currency", "payment_terms_days", "default_account_id", "active", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.vendors.update_one({"id": vid}, {"$set": update})
    return await db.vendors.find_one({"id": vid}, {"_id": 0})


@router.delete("/vendors/{vid}")
async def delete_vendor(vid: str, current_user: dict = Depends(require_finance_admin)):
    has_bills = await db.bills.find_one({"vendor_id": vid})
    if has_bills:
        await db.vendors.update_one({"id": vid}, {"$set": {"active": False}})
        return {"deactivated": True}
    await db.vendors.delete_one({"id": vid})
    return {"deleted": True}


# ============================================================
# BILLS (Vendor Invoices / Accounts Payable)
# ============================================================

def _bill_totals(items: list) -> tuple:
    subtotal = sum(float(i.get("qty", 0) or 0) * float(i.get("unit_price", 0) or 0) for i in items)
    tax = sum((float(i.get("qty", 0) or 0) * float(i.get("unit_price", 0) or 0)) * float(i.get("tax_rate", 0) or 0) / 100
              for i in items)
    return round(subtotal, 2), round(tax, 2), round(subtotal + tax, 2)


@router.get("/bills")
async def list_bills(
    vendor_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_finance_view),
):
    scope = await get_campus_filter(current_user)
    query = {**scope} if scope else {}
    if vendor_id:
        query["vendor_id"] = vendor_id
    if status:
        query["status"] = status
    return await db.bills.find(query, {"_id": 0}).sort("bill_date", -1).to_list(500)


@router.post("/bills")
async def create_bill(data: dict, current_user: dict = Depends(require_finance_view)):
    """Create a vendor bill (AP).
    Body: { vendor_id, bill_date, due_date?, items: [{description, qty, unit_price, account_id, tax_rate?}],
            currency?, notes?, status? (default 'open') }"""
    vendor_id = data.get("vendor_id")
    vendor = await db.vendors.find_one({"id": vendor_id}, {"_id": 0}) if vendor_id else None
    if not vendor:
        raise HTTPException(status_code=400, detail="vendor_id required & must exist")
    items = data.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="At least one line item required")
    subtotal, tax_amount, total = _bill_totals(items)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bill_date = (data.get("bill_date") or today)[:10]
    # Due date: explicit or vendor's default payment terms
    due_date = (data.get("due_date") or "")[:10]
    if not due_date:
        try:
            due_date = (dt_date.fromisoformat(bill_date) + timedelta(days=int(vendor.get("payment_terms_days") or 30))).isoformat()
        except Exception:
            due_date = bill_date
    # Generate bill number atomically
    date_tag = bill_date.replace("-", "")
    counter = await db.counters.find_one_and_update(
        {"_id": f"bills_{date_tag[:6]}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    seq = (counter or {}).get("seq", 1)
    bill_number = f"BILL-{date_tag[:6]}-{seq:04d}"
    status_val = (data.get("status") or "open").strip()
    if status_val not in BILL_STATUSES:
        status_val = "open"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"bil_{uuid.uuid4().hex[:10]}",
        "bill_number": bill_number,
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "vendor_tin": vendor.get("tin"),
        "bill_date": bill_date,
        "due_date": due_date,
        "items": items,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "total": total,
        "amount_paid": 0,
        "balance": total,
        "payments": [],
        "status": status_val,
        "currency": (data.get("currency") or vendor.get("currency") or "UGX").upper()[:5],
        "location_id": data.get("location_id") or vendor.get("location_id") or current_user.get("active_campus_id"),
        "reference": (data.get("reference") or "")[:120],
        "notes": (data.get("notes") or "")[:1000],
        "created_at": now_iso,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.bills.insert_one(doc)
    doc.pop("_id", None)
    # Auto-post AP entry: Dr Expense(s) / Cr Accounts Payable (when status=open)
    if status_val == "open":
        try:
            await _post_bill_to_ledger(doc, current_user)
        except Exception as e:
            logger.warning(f"Bill auto-post skipped: {e}")
    return doc


async def _post_bill_to_ledger(bill: dict, current_user: dict):
    """Post the bill: Dr each item's account / Cr Accounts Payable."""
    loc_id = bill.get("location_id")
    if not loc_id:
        return
    ap_acc = await db.accounting_accounts.find_one(
        {"location_id": loc_id, "type": "liability_payable", "active": True}, {"_id": 0}
    )
    if not ap_acc:
        return  # AP account not in CoA — silent no-op
    journal = (await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": "purchases", "active": True}, {"_id": 0}
    )) or (await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": "miscellaneous", "active": True}, {"_id": 0}
    )) or (await db.accounting_journals.find_one(
        {"location_id": loc_id, "active": True}, {"_id": 0}
    ))
    if not journal:
        return
    from routers.accounting import _next_entry_number
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal["id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    # Aggregate item lines by account_id (handles multi-line bills cleanly)
    lines_by_account = {}
    for item in bill.get("items", []):
        acc_id = item.get("account_id")
        amt = float(item.get("qty", 0) or 0) * float(item.get("unit_price", 0) or 0)
        if not acc_id or amt <= 0:
            continue
        lines_by_account[acc_id] = lines_by_account.get(acc_id, 0) + amt
    # Tax goes to a Tax Payable account if available, else just absorbed into the AP credit
    tax_amount = float(bill.get("tax_amount") or 0)
    tax_acc = None
    if tax_amount > 0:
        tax_acc = await db.accounting_accounts.find_one(
            {"location_id": loc_id, "type": "liability_tax", "active": True}, {"_id": 0}
        )
    entry = {
        "id": entry_id, "number": entry_number,
        "journal_id": journal["id"], "journal_code": journal.get("code"),
        "date": bill["bill_date"], "ref": bill["bill_number"],
        "narration": f"Bill {bill['bill_number']} - {bill.get('vendor_name','')}",
        "total_debit": round(bill.get("total") or 0, 2),
        "total_credit": round(bill.get("total") or 0, 2),
        "status": "posted",
        "location_id": loc_id,
        "currency": bill.get("currency"),
        "auto_generated_from": "bill",
        "source_id": bill["id"],
        "created_at": now_iso, "posted_at": now_iso, "posted_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    lines = []
    for acc_id, amt in lines_by_account.items():
        lines.append({
            "id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
            "journal_id": journal["id"], "date": bill["bill_date"], "location_id": loc_id, "status": "posted",
            "account_id": acc_id, "debit": round(amt, 2), "credit": 0,
            "description": entry["narration"],
        })
    if tax_acc:
        # When tax is broken out: Dr Tax / Cr AP (with the tax portion)
        # But that creates an AP credit too — handled below
        lines.append({
            "id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
            "journal_id": journal["id"], "date": bill["bill_date"], "location_id": loc_id, "status": "posted",
            "account_id": tax_acc["id"], "debit": round(tax_amount, 2), "credit": 0,
            "description": f"VAT input @ {round(tax_amount,2)}",
        })
    # Single AP credit = full bill total
    lines.append({
        "id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
        "journal_id": journal["id"], "date": bill["bill_date"], "location_id": loc_id, "status": "posted",
        "account_id": ap_acc["id"], "debit": 0, "credit": round(bill.get("total") or 0, 2),
        "description": f"AP - {bill.get('vendor_name','')}",
    })
    if lines:
        await db.accounting_entry_lines.insert_many(lines)


@router.put("/bills/{bid}")
async def update_bill(bid: str, data: dict, current_user: dict = Depends(require_finance_view)):
    bill = await db.bills.find_one({"id": bid}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.get("status") in {"paid", "void"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit a {bill['status']} bill — reverse it via /accounting first")
    allowed = {"bill_date", "due_date", "items", "currency", "reference", "notes", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "items" in update:
        sub, tax, total = _bill_totals(update["items"])
        update["subtotal"], update["tax_amount"], update["total"] = sub, tax, total
        update["balance"] = round(total - float(bill.get("amount_paid") or 0), 2)
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.bills.update_one({"id": bid}, {"$set": update})
    return await db.bills.find_one({"id": bid}, {"_id": 0})


@router.post("/bills/{bid}/payments")
async def pay_bill(bid: str, data: dict, current_user: dict = Depends(require_finance_view)):
    """Record a payment against a bill.
    Body: { amount, payment_date?, bank_account_id, method?, reference?, notes? }"""
    bill = await db.bills.find_one({"id": bid}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill["status"] in {"paid", "void"}:
        raise HTTPException(status_code=400, detail=f"Bill is {bill['status']}")
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    balance = float(bill.get("balance") or 0)
    if amount > balance + 0.01:
        raise HTTPException(status_code=400, detail=f"Payment ({amount}) exceeds outstanding balance ({balance})")
    bank_account_id = data.get("bank_account_id")
    bank_acc = await db.bank_accounts.find_one({"id": bank_account_id}, {"_id": 0}) if bank_account_id else None
    payment_date = (data.get("payment_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    now_iso = datetime.now(timezone.utc).isoformat()
    payment = {
        "id": f"pay_{uuid.uuid4().hex[:10]}",
        "date": payment_date,
        "amount": amount,
        "bank_account_id": bank_account_id,
        "bank_account_name": (bank_acc or {}).get("name"),
        "method": (data.get("method") or "bank_transfer").strip(),
        "reference": (data.get("reference") or "")[:120],
        "notes": (data.get("notes") or "")[:300],
        "paid_by": current_user["id"],
        "paid_by_name": current_user.get("name", ""),
        "created_at": now_iso,
    }
    new_paid = float(bill.get("amount_paid") or 0) + amount
    new_balance = round(float(bill.get("total") or 0) - new_paid, 2)
    new_status = "paid" if new_balance <= 0.01 else "partially_paid"
    await db.bills.update_one({"id": bid}, {
        "$push": {"payments": payment},
        "$set": {"amount_paid": round(new_paid, 2), "balance": new_balance, "status": new_status,
                 "updated_at": now_iso},
    })
    # Post JE: Dr AP / Cr Bank
    if bank_acc and bank_acc.get("linked_account_id"):
        try:
            await _post_bill_payment_to_ledger(bill, payment, bank_acc, current_user)
        except Exception as e:
            logger.warning(f"Bill payment ledger post skipped: {e}")
    return await db.bills.find_one({"id": bid}, {"_id": 0})


async def _post_bill_payment_to_ledger(bill: dict, payment: dict, bank_acc: dict, current_user: dict):
    loc_id = bill.get("location_id")
    ap_acc = await db.accounting_accounts.find_one(
        {"location_id": loc_id, "type": "liability_payable", "active": True}, {"_id": 0}
    )
    if not ap_acc:
        return
    journal = (await db.accounting_journals.find_one(
        {"location_id": loc_id, "kind": "purchases", "active": True}, {"_id": 0}
    )) or (await db.accounting_journals.find_one(
        {"location_id": loc_id, "active": True}, {"_id": 0}
    ))
    if not journal:
        return
    from routers.accounting import _next_entry_number
    entry_id = f"je_{uuid.uuid4().hex[:10]}"
    entry_number = await _next_entry_number(journal["id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    amount = float(payment["amount"])
    entry = {
        "id": entry_id, "number": entry_number,
        "journal_id": journal["id"], "journal_code": journal.get("code"),
        "date": payment["date"], "ref": payment["reference"] or f"PAY-{bill['bill_number']}",
        "narration": f"Payment of bill {bill['bill_number']} - {bill.get('vendor_name','')}",
        "total_debit": amount, "total_credit": amount, "status": "posted",
        "location_id": loc_id, "currency": bill.get("currency"),
        "auto_generated_from": "bill_payment", "source_id": payment["id"],
        "created_at": now_iso, "posted_at": now_iso, "posted_by": current_user["id"],
    }
    await db.accounting_entries.insert_one(entry)
    await db.accounting_entry_lines.insert_many([
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": payment["date"], "location_id": loc_id, "status": "posted",
         "account_id": ap_acc["id"], "debit": amount, "credit": 0,
         "description": f"AP cleared - {bill.get('vendor_name','')}"},
        {"id": f"jel_{uuid.uuid4().hex[:10]}", "entry_id": entry_id, "entry_number": entry_number,
         "journal_id": journal["id"], "date": payment["date"], "location_id": loc_id, "status": "posted",
         "account_id": bank_acc["linked_account_id"], "debit": 0, "credit": amount,
         "description": f"Paid via {bank_acc.get('name','')}"},
    ])


@router.delete("/bills/{bid}")
async def void_bill(bid: str, current_user: dict = Depends(require_finance_admin)):
    """Void a bill (does NOT delete the underlying JE — reverse that manually)."""
    await db.bills.update_one({"id": bid}, {"$set": {
        "status": "void",
        "voided_at": datetime.now(timezone.utc).isoformat(),
        "voided_by": current_user["id"],
    }})
    return {"voided": True, "note": "If a JE was posted, reverse it manually via /accounting/entries/{id}/reverse"}


# ============================================================
# RECURRING JOURNAL ENTRIES / BILLS
# ============================================================

@router.get("/recurring")
async def list_recurring(current_user: dict = Depends(require_finance_view)):
    scope = await get_campus_filter(current_user)
    query = {**scope} if scope else {}
    return await db.recurring_entries.find(query, {"_id": 0}).sort("next_run_date", 1).to_list(200)


@router.post("/recurring")
async def create_recurring(data: dict, current_user: dict = Depends(require_finance_admin)):
    """Create a recurring template.
    Body: { name, kind ('journal_entry'|'bill'), schedule, day_of_month?, next_run_date,
            template: {...}, is_active? }"""
    name = (data.get("name") or "").strip()
    kind = (data.get("kind") or "").strip()
    schedule = (data.get("schedule") or "monthly").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if kind not in RECURRING_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be in {sorted(RECURRING_KINDS)}")
    if schedule not in RECURRING_SCHEDULES:
        raise HTTPException(status_code=400, detail=f"schedule must be in {sorted(RECURRING_SCHEDULES)}")
    next_run = (data.get("next_run_date") or "")[:10]
    if not next_run:
        raise HTTPException(status_code=400, detail="next_run_date required")
    template = data.get("template")
    if not template or not isinstance(template, dict):
        raise HTTPException(status_code=400, detail="template payload required")
    doc = {
        "id": f"rec_{uuid.uuid4().hex[:10]}",
        "name": name[:120],
        "kind": kind,
        "schedule": schedule,
        "day_of_month": int(data.get("day_of_month") or 1) if schedule == "monthly" else None,
        "next_run_date": next_run,
        "template": template,
        "is_active": bool(data.get("is_active", True)),
        "last_run_date": None,
        "run_count": 0,
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.recurring_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/recurring/{rid}")
async def update_recurring(rid: str, data: dict, current_user: dict = Depends(require_finance_admin)):
    allowed = {"name", "schedule", "day_of_month", "next_run_date", "template", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    await db.recurring_entries.update_one({"id": rid}, {"$set": update})
    return await db.recurring_entries.find_one({"id": rid}, {"_id": 0})


@router.delete("/recurring/{rid}")
async def delete_recurring(rid: str, current_user: dict = Depends(require_finance_admin)):
    await db.recurring_entries.delete_one({"id": rid})
    return {"deleted": True}


def _advance_recurring_date(current: str, schedule: str, day_of_month: int = 1) -> str:
    """Compute the next run date for a recurring template."""
    d = dt_date.fromisoformat(current)
    if schedule == "daily":
        return (d + timedelta(days=1)).isoformat()
    if schedule == "weekly":
        return (d + timedelta(days=7)).isoformat()
    if schedule == "biweekly":
        return (d + timedelta(days=14)).isoformat()
    if schedule == "monthly":
        y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        from calendar import monthrange
        last_day = monthrange(y, m)[1]
        return dt_date(y, m, min(day_of_month or d.day, last_day)).isoformat()
    if schedule == "quarterly":
        y, m = d.year, d.month + 3
        while m > 12:
            m -= 12; y += 1
        from calendar import monthrange
        last_day = monthrange(y, m)[1]
        return dt_date(y, m, min(d.day, last_day)).isoformat()
    if schedule == "yearly":
        from calendar import monthrange
        last_day = monthrange(d.year + 1, d.month)[1]
        return dt_date(d.year + 1, d.month, min(d.day, last_day)).isoformat()
    return current


@router.post("/recurring/{rid}/run-now")
async def run_recurring_now(rid: str, current_user: dict = Depends(require_finance_admin)):
    """Manually trigger a recurring entry (and advance its next_run_date)."""
    rec = await db.recurring_entries.find_one({"id": rid}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    if not rec.get("is_active"):
        raise HTTPException(status_code=400, detail="Template is inactive")
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    created = None
    if rec["kind"] == "journal_entry":
        from routers.accounting import create_entry
        # Force the date to today on this run
        payload = {**rec["template"], "date": today_iso}
        # Use admin-like override — create_entry requires require_director; we already are
        created = await create_entry(payload, current_user)
    elif rec["kind"] == "bill":
        payload = {**rec["template"], "bill_date": today_iso}
        created = await create_bill(payload, current_user)
    new_next = _advance_recurring_date(rec["next_run_date"], rec["schedule"], rec.get("day_of_month") or 1)
    await db.recurring_entries.update_one({"id": rid}, {"$set": {
        "last_run_date": today_iso,
        "next_run_date": new_next,
    }, "$inc": {"run_count": 1}})
    return {"ran": True, "created": created, "next_run_date": new_next}


async def fire_due_recurring_entries():
    """Background task: run every day at 06:00 UTC; fires every recurring template
    whose next_run_date is on or before today. Idempotent — sets next_run_date forward."""
    try:
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = db.recurring_entries.find({
            "is_active": True,
            "next_run_date": {"$lte": today_iso},
        }, {"_id": 0})
        async for rec in cursor:
            try:
                # Use a synthetic system user for the run record
                sys_user = {"id": "system", "name": "System (recurring scheduler)", "role": "system_admin",
                            "active_campus_id": rec.get("location_id")}
                if rec["kind"] == "journal_entry":
                    from routers.accounting import create_entry
                    await create_entry({**rec["template"], "date": today_iso}, sys_user)
                elif rec["kind"] == "bill":
                    await create_bill({**rec["template"], "bill_date": today_iso}, sys_user)
                new_next = _advance_recurring_date(rec["next_run_date"], rec["schedule"], rec.get("day_of_month") or 1)
                await db.recurring_entries.update_one({"id": rec["id"]}, {"$set": {
                    "last_run_date": today_iso,
                    "next_run_date": new_next,
                }, "$inc": {"run_count": 1}})
            except Exception as e:
                logger.warning(f"Recurring {rec.get('id')} skipped: {e}")
    except Exception as e:
        logger.error(f"fire_due_recurring_entries error: {e}")
