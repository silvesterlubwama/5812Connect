"""Chart of Accounts CRUD + seed.

The COA is the *only* place accounts are defined — every journal line references
one by `id`. Deleting a system-seeded account is blocked; deleting a user-added
one is refused if any JE line references it (keeps the ledger closed).
"""
import uuid
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from deps import db, require_staff, require_director

from ._common import ACCOUNT_TYPES, ensure_seed_accounts, _now

router = APIRouter(prefix="/api/finance/chart-of-accounts", tags=["finance"])


@router.get("")
async def list_accounts(
    active_only: bool = True,
    type: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """All accounts, sorted by code. Directors see everything; staff can read
    the COA read-only so expense/income entry forms know what accounts exist."""
    q = {}
    if active_only:
        q["active"] = True
    if type:
        q["type"] = type
    return await db.finance_chart_of_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(500)


@router.post("")
async def create_account(data: dict, current_user: dict = Depends(require_director)):
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    acct_type = (data.get("type") or "").strip().lower()
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name are required")
    if acct_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(ACCOUNT_TYPES)}")
    if await db.finance_chart_of_accounts.find_one({"code": code}, {"_id": 1}):
        raise HTTPException(status_code=409, detail=f"Account code {code} already exists")
    doc = {
        "id": f"acc_{uuid.uuid4().hex[:10]}",
        "code": code,
        "name": name,
        "type": acct_type,
        "is_cash": bool(data.get("is_cash") or data.get("bank_subtype")),
        "bank_subtype": (data.get("bank_subtype") or "").strip().lower() or None,  # cash|checking|savings|momo|credit_card
        "is_system": False,
        "active": True,
        "created_at": _now(),
        "created_by": current_user["id"],
    }
    await db.finance_chart_of_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/bulk-import")
async def bulk_import_accounts(data: dict, current_user: dict = Depends(require_director)):
    """Bulk-import a list of accounts. Skips any row whose `code` already
    exists so re-uploading a spreadsheet mid-cleanup is safe. Returns
    `{created, skipped, invalid}` counts + the created accounts + the
    per-row reasons for anything skipped/invalid so the client can show
    a diff-style summary.

    Body: `{accounts: [{code, name, type, bank_subtype?, is_cash?}]}`.
    """
    rows = data.get("accounts") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="accounts must be a non-empty array")
    if len(rows) > 500:
        raise HTTPException(status_code=400, detail="Max 500 rows per import — split the file")

    existing_codes = {a["code"] async for a in db.finance_chart_of_accounts.find({}, {"_id": 0, "code": 1})}
    created: list = []
    skipped: list = []
    invalid: list = []
    seen_in_batch: set = set()

    for i, r in enumerate(rows):
        code = str(r.get("code") or "").strip()
        name = str(r.get("name") or "").strip()
        acct_type = str(r.get("type") or "").strip().lower()
        if not code or not name:
            invalid.append({"row": i + 1, "reason": "code and name required", "code": code})
            continue
        if acct_type not in ACCOUNT_TYPES:
            invalid.append({"row": i + 1, "reason": f"invalid type '{acct_type}'", "code": code})
            continue
        if code in existing_codes or code in seen_in_batch:
            skipped.append({"row": i + 1, "reason": "code already exists", "code": code})
            continue
        seen_in_batch.add(code)
        bank_subtype = (str(r.get("bank_subtype") or "").strip().lower() or None)
        doc = {
            "id": f"acc_{uuid.uuid4().hex[:10]}",
            "code": code, "name": name, "type": acct_type,
            "is_cash": bool(r.get("is_cash") or bank_subtype),
            "bank_subtype": bank_subtype,
            "is_system": False, "active": True,
            "created_at": _now(), "created_by": current_user["id"],
            "imported": True,
        }
        await db.finance_chart_of_accounts.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)

    return {
        "created_count": len(created), "skipped_count": len(skipped), "invalid_count": len(invalid),
        "created": created, "skipped": skipped, "invalid": invalid,
    }


@router.put("/{account_id}")
async def update_account(account_id: str, data: dict, current_user: dict = Depends(require_director)):
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    # System accounts: only `active`, `is_cash`, `bank_subtype` and `name` can be updated (never
    # the `type` or `code` — those would break historical JEs).
    allowed = {"name", "is_cash", "bank_subtype", "active"}
    if not acct.get("is_system"):
        allowed |= {"code", "type"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "type" in update and update["type"] not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    if "bank_subtype" in update:
        sub = (update["bank_subtype"] or "").strip().lower() or None
        update["bank_subtype"] = sub
        # If they picked a subtype, force is_cash on; if they cleared it, leave is_cash alone
        if sub:
            update["is_cash"] = True
    update["updated_at"] = _now()
    await db.finance_chart_of_accounts.update_one({"id": account_id}, {"$set": update})
    return await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})


@router.delete("/{account_id}")
async def delete_account(account_id: str, current_user: dict = Depends(require_director)):
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    if acct.get("is_system"):
        raise HTTPException(status_code=400, detail="System accounts cannot be deleted (deactivate instead)")
    in_use = await db.finance_journal_entries.find_one({"lines.account_id": account_id}, {"_id": 1})
    if in_use:
        raise HTTPException(status_code=400, detail="Account referenced by journal entries — deactivate instead")
    await db.finance_chart_of_accounts.delete_one({"id": account_id})
    return {"deleted": True}


@router.post("/{account_id}/opening-balance")
async def post_opening_balance(account_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Post a balanced journal entry that sets an account's opening balance.
    Body: `{ amount: number, date?: 'YYYY-MM-DD', currency?: str, memo?: str }`.
    The counter-account is `Opening Balance Equity` (code 3000) — auto-seeded
    if missing. Sign is inferred from the account category:
      * asset / expense  → debit target, credit equity
      * liability / equity / income → credit target, debit equity
    """
    from ._common import post_journal_entry
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        amount = float(data.get("amount") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be numeric")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    # Ensure the Opening Balance Equity account exists (code 3000).
    ob = await db.finance_chart_of_accounts.find_one({"code": "3000"}, {"_id": 0})
    if not ob:
        ob = {
            "id": f"acc_{__import__('uuid').uuid4().hex[:10]}",
            "code": "3000", "name": "Opening Balance Equity",
            "type": "equity", "category": "equity",
            "currency": acct.get("currency") or "UGX",
            "active": True, "is_system": True,
            "location_id": acct.get("location_id"),
        }
        await db.finance_chart_of_accounts.insert_one(ob)
    # Direction — assets & expenses have a natural debit balance; equity,
    # liability, income sit on the credit side.
    cat = (acct.get("category") or acct.get("type") or "").lower()
    debit_target = any(cat.startswith(p) for p in ("asset", "expense"))
    if debit_target:
        lines = [
            {"account_id": account_id, "account_code": acct.get("code"), "account_name": acct.get("name"), "debit": amount, "credit": 0},
            {"account_id": ob["id"],   "account_code": ob["code"],       "account_name": ob["name"],       "debit": 0, "credit": amount},
        ]
    else:
        lines = [
            {"account_id": ob["id"],   "account_code": ob["code"],       "account_name": ob["name"],       "debit": amount, "credit": 0},
            {"account_id": account_id, "account_code": acct.get("code"), "account_name": acct.get("name"), "debit": 0, "credit": amount},
        ]
    je = await post_journal_entry(
        date=data.get("date") or datetime.now(timezone.utc).date().isoformat(),
        description=data.get("memo") or f"Opening balance · {acct.get('name')}",
        lines=lines, source="opening_balance",
        reference=account_id, location_id=acct.get("location_id"),
        created_by=current_user["id"], created_by_name=current_user.get("name"),
        idempotency_key=f"open:{account_id}:{data.get('date') or ''}",
    )
    return {"journal_entry": je, "amount": amount, "account": acct}


@router.post("/seed")
async def seed_accounts(current_user: dict = Depends(require_director)):
    """Idempotent — inserts any missing standard accounts without touching
    the ones you've already added or renamed."""
    inserted = await ensure_seed_accounts()
    return {"inserted": inserted}
