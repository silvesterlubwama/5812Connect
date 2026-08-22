"""Journal entries — direct read/list + manual post + reversal.

Manual journal posting is `require_director` only (staff can only create
income/expenses via the friendly `/api/finance/transactions` endpoint, which
internally posts a balanced JE — see transactions.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, require_staff, require_director

from ._common import post_journal_entry, reverse_journal_entry

router = APIRouter(prefix="/api/finance/journal", tags=["finance"])


@router.get("")
async def list_entries(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    account_id: Optional[str] = None,
    location_id: Optional[str] = None,
    include_reversed: bool = False,
    limit: int = Query(200, le=1000),
    current_user: dict = Depends(require_staff),
):
    q: dict = {}
    if date_from:
        q.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        q.setdefault("date", {})["$lte"] = date_to[:10]
    if source:
        q["source"] = source
    if location_id and location_id != "all":
        q["location_id"] = location_id
    if account_id:
        q["lines.account_id"] = account_id
    if not include_reversed:
        q["reversed"] = {"$ne": True}
    rows = await db.finance_journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    return rows


@router.get("/{je_id}")
async def get_entry(je_id: str, current_user: dict = Depends(require_staff)):
    doc = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return doc


@router.post("")
async def create_entry(data: dict, current_user: dict = Depends(require_director)):
    """Manual balanced JE — power-user only. Prefer the transactions endpoint
    for day-to-day income/expense entry."""
    return await post_journal_entry(
        date=data.get("date") or "",
        description=data.get("description") or "",
        lines=data.get("lines") or [],
        source="manual",
        reference=data.get("reference"),
        location_id=data.get("location_id"),
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )


@router.post("/{je_id}/reverse")
async def reverse_entry(je_id: str, data: dict, current_user: dict = Depends(require_director)):
    reason = (data or {}).get("reason") or "No reason provided"
    return await reverse_journal_entry(je_id, reason=reason, current_user=current_user)
