"""Journal entries — direct read/list + manual post + reversal.

Manual journal posting is `require_director` only (staff can only create
income/expenses via the friendly `/api/finance/transactions` endpoint, which
internally posts a balanced JE — see transactions.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, require_staff, require_director

from ._common import post_journal_entry, reverse_journal_entry
from ._common import _now

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
    location_id = (data.get("location_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required — every entry must belong to a campus or sub-location")
    return await post_journal_entry(
        date=data.get("date") or "",
        description=data.get("description") or "",
        lines=data.get("lines") or [],
        source="manual",
        reference=data.get("reference"),
        location_id=location_id,
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )


@router.put("/{je_id}")
async def update_entry(je_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Edit a journal entry — allowed only when its fiscal period is not
    locked/closed. To keep the ledger balanced we edit safe fields directly
    (description, reference, date, memos) but any change to `lines` /
    `total` reverses the JE and posts a fresh replacement so the audit
    trail preserves both sides."""
    from .setup import period_is_locked
    doc = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if doc.get("reversed"):
        raise HTTPException(status_code=400, detail="Entry is already reversed — post a fresh one instead")
    # Guard: refuse edits into a locked period (either the current date OR
    # the caller's proposed new date).
    if await period_is_locked(doc.get("date") or "", doc.get("location_id")):
        raise HTTPException(status_code=400, detail="Fiscal period covering this entry is locked — reopen it before editing")
    new_date = (data.get("date") or doc.get("date"))[:10]
    if await period_is_locked(new_date, data.get("location_id") or doc.get("location_id")):
        raise HTTPException(status_code=400, detail=f"Fiscal period covering {new_date} is locked — pick a date outside the closed period")

    lines_changed = "lines" in data and data["lines"] is not None
    if not lines_changed:
        # Safe in-place edit — only metadata / date fields.
        allowed = {"description", "reference", "date"}
        update = {k: v for k, v in data.items() if k in allowed}
        if not update:
            return doc
        update["updated_at"] = _now()
        update["updated_by"] = current_user["id"]
        await db.finance_journal_entries.update_one({"id": je_id}, {"$set": update, "$push": {"edit_history": {"at": _now(), "by": current_user["id"], "changes": list(update.keys())}}})
        return await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})

    # Lines changed → reverse + repost so the audit trail is preserved.
    from ._common import reverse_journal_entry
    await reverse_journal_entry(je_id, reason=f"Edited by {current_user.get('name') or current_user['id']}", current_user=current_user)
    new_je = await post_journal_entry(
        date=new_date,
        description=data.get("description") or doc.get("description"),
        lines=data["lines"],
        source=doc.get("source") or "manual",
        reference=data.get("reference") if data.get("reference") is not None else doc.get("reference"),
        location_id=data.get("location_id") or doc.get("location_id"),
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    await db.finance_journal_entries.update_one({"id": new_je["id"]}, {"$set": {"supersedes": je_id}})
    # Re-fetch so the response includes the supersedes link the caller expects.
    return await db.finance_journal_entries.find_one({"id": new_je["id"]}, {"_id": 0})


@router.post("/{je_id}/reverse")
async def reverse_entry(je_id: str, data: dict, current_user: dict = Depends(require_director)):
    reason = (data or {}).get("reason") or "No reason provided"
    return await reverse_journal_entry(je_id, reason=reason, current_user=current_user)


@router.delete("/{je_id}")
async def delete_entry(je_id: str, current_user: dict = Depends(require_director)):
    """Delete a reversal JE (source='reversal') and un-mark the entry it
    reversed so the original posts again. Refuses when the fiscal period
    covering the entry is locked. Non-reversal JEs must go through
    /reverse — deleting a live posted transaction outright would break
    the audit trail."""
    from .setup import period_is_locked
    doc = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if doc.get("source") != "reversal":
        raise HTTPException(status_code=400, detail="Only reversal entries can be deleted directly. Use /reverse on live entries.")
    if await period_is_locked(doc.get("date") or "", doc.get("location_id")):
        raise HTTPException(status_code=400, detail="Fiscal period is locked — reversal cannot be undone")
    original_id = doc.get("reverses_id") or doc.get("reversed_je_id") or doc.get("reverses")
    # Delete this reversal + un-mark the original
    await db.finance_journal_entries.delete_one({"id": je_id})
    if original_id:
        await db.finance_journal_entries.update_one(
            {"id": original_id},
            {"$unset": {"reversed": "", "reversed_at": "", "reversed_by": "", "reversed_reason": "", "reversed_by_je": ""}},
        )
    return {"deleted": je_id, "restored_original": original_id}

