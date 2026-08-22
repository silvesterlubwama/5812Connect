"""Chart of Accounts CRUD + seed.

The COA is the *only* place accounts are defined — every journal line references
one by `id`. Deleting a system-seeded account is blocked; deleting a user-added
one is refused if any JE line references it (keeps the ledger closed).
"""
import uuid
from typing import Optional

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
        "is_cash": bool(data.get("is_cash")),
        "is_system": False,
        "active": True,
        "created_at": _now(),
        "created_by": current_user["id"],
    }
    await db.finance_chart_of_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{account_id}")
async def update_account(account_id: str, data: dict, current_user: dict = Depends(require_director)):
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    # System accounts: only `active`, `is_cash` and `name` can be updated (never
    # the `type` or `code` — those would break historical JEs).
    allowed = {"name", "is_cash", "active"}
    if not acct.get("is_system"):
        allowed |= {"code", "type"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "type" in update and update["type"] not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
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


@router.post("/seed")
async def seed_accounts(current_user: dict = Depends(require_director)):
    """Idempotent — inserts any missing standard accounts without touching
    the ones you've already added or renamed."""
    inserted = await ensure_seed_accounts()
    return {"inserted": inserted}
