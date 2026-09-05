"""Inter-account transfers on the unified ledger.

Each transfer is ONE balanced JE:
  • Debit destination (money arrives)
  • Credit source (money leaves)

Optional transaction fee is a THIRD line:
  • Debit `fee_account_id` (expense) / additional Credit on source
Balance stays: Dr (amount + fee) == Cr (amount + fee), the source account
loses `amount + fee`, destination receives `amount`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, require_staff

from ._common import post_journal_entry

router = APIRouter(prefix="/api/finance/transfers", tags=["finance"])


async def _load_asset_account(account_id: str, label: str) -> dict:
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=400, detail=f"{label} account not found")
    if acct.get("type") != "asset":
        raise HTTPException(status_code=400, detail=f"{label} '{acct['name']}' is not an asset account — transfers only move between cash/bank/asset accounts")
    return acct


async def _load_expense_account(account_id: str) -> dict:
    acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=400, detail="Fee account not found")
    if acct.get("type") != "expense":
        raise HTTPException(status_code=400, detail=f"Fee account '{acct['name']}' must be an expense account")
    return acct


@router.post("")
async def record_transfer(data: dict, current_user: dict = Depends(require_staff)):
    """Body: {from_account_id, to_account_id, amount, date?, description?, location_id?,
             reference?, fee_amount?, fee_account_id?}"""
    from_id = (data.get("from_account_id") or "").strip()
    to_id = (data.get("to_account_id") or "").strip()
    amount = float(data.get("amount") or 0)
    fee_amount = float(data.get("fee_amount") or 0)
    fee_account_id = (data.get("fee_account_id") or "").strip()
    location_id = (data.get("location_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required — every transfer must be tagged to a campus or sub-location")
    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_account_id and to_account_id are required")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="Source and destination must be different")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if fee_amount < 0:
        raise HTTPException(status_code=400, detail="Fee cannot be negative")
    if fee_amount > 0 and not fee_account_id:
        raise HTTPException(status_code=400, detail="Fee account is required when a fee is entered")

    from_acct = await _load_asset_account(from_id, "Source")
    to_acct = await _load_asset_account(to_id, "Destination")
    fee_acct = await _load_expense_account(fee_account_id) if fee_amount > 0 else None

    desc = data.get("description") or f"Transfer: {from_acct['name']} → {to_acct['name']}"
    lines = [
        {"account_id": to_acct["id"], "account_code": to_acct["code"],
         "account_name": to_acct["name"], "debit": amount, "credit": 0,
         "memo": f"From {from_acct['name']}"},
        {"account_id": from_acct["id"], "account_code": from_acct["code"],
         "account_name": from_acct["name"], "debit": 0, "credit": amount + fee_amount,
         "memo": f"To {to_acct['name']}" + (f" (incl. fee {fee_amount})" if fee_amount else "")},
    ]
    if fee_acct:
        lines.append({
            "account_id": fee_acct["id"], "account_code": fee_acct["code"],
            "account_name": fee_acct["name"], "debit": fee_amount, "credit": 0,
            "memo": f"Bank/transfer fee on {desc}",
        })

    je = await post_journal_entry(
        date=data.get("date") or "",
        description=desc,
        lines=lines,
        source="transfer",
        reference=data.get("reference"),
        location_id=location_id,
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    return je


@router.get("")
async def list_transfers(
    limit: int = Query(100, le=500),
    current_user: dict = Depends(require_staff),
):
    """Recent transfers only (source='transfer'), newest first."""
    rows = await db.finance_journal_entries.find(
        {"source": "transfer", "reversed": {"$ne": True}}, {"_id": 0},
    ).sort([("date", -1), ("created_at", -1)]).limit(limit).to_list(limit)
    return rows
