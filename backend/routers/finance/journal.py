"""Journal entries — direct read/list + manual post + reversal.

Manual journal posting is `require_director` only (staff can only create
income/expenses via the friendly `/api/finance/transactions` endpoint, which
internally posts a balanced JE — see transactions.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, require_staff, require_director

from ._common import post_journal_entry, reverse_journal_entry, delete_journal_entry
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
        q["voided"] = {"$ne": True}
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
    locked/closed. Safe fields (description, reference, date, memos) are edited
    in place. Changing `lines` / `total` voids this entry and posts the
    corrected one in its place (linked by `supersedes`), so the journal shows a
    single live line instead of an entry plus a confusing contra."""
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
        # Safe in-place edit — metadata / date / scope fields. `location_id`,
        # `department_id`, and `vendor` land here too so admins can retag a
        # JE without a reverse+repost when the amounts are right but the
        # cost centre / campus / vendor was wrong at post time.
        allowed = {"description", "reference", "date", "location_id", "department_id", "vendor"}
        update = {k: v for k, v in data.items() if k in allowed}
        if not update:
            return doc
        # Refuse retagging into a locked target campus for non-admins.
        if update.get("location_id") and update["location_id"] != doc.get("location_id"):
            if await period_is_locked(new_date, update["location_id"]):
                raise HTTPException(status_code=400, detail=f"Target campus fiscal period covering {new_date} is locked — pick a date outside the closed period")
        update["updated_at"] = _now()
        update["updated_by"] = current_user["id"]
        await db.finance_journal_entries.update_one({"id": je_id}, {"$set": update, "$push": {"edit_history": {"at": _now(), "by": current_user["id"], "changes": list(update.keys())}}})
        return await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})

    # Lines changed → void the old entry and post the corrected one.
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
    """Undo an entry. Open period → the entry is deleted (a copy plus who/why
    goes to the audit trail). Locked period → a contra entry is posted."""
    reason = (data or {}).get("reason") or ""
    if not reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required so the audit trail means something")
    return await reverse_journal_entry(je_id, reason=reason.strip(), current_user=current_user)


@router.get("/deleted/list")
async def list_deleted_entries(
    limit: int = Query(200, le=1000),
    current_user: dict = Depends(require_staff),
):
    """Audit trail of deleted journal entries — who, when, why and what."""
    rows = await db.finance_deleted_entries.find(
        {}, {"_id": 0},
    ).sort("deleted_at", -1).limit(limit).to_list(limit)
    out = []
    for r in rows:
        entry = r.pop("entry", None)
        out.append({**r, "can_restore": bool(entry) and not r.get("restored_at")})
    return {"deleted": out, "count": len(out)}


@router.post("/deleted/{trail_id}/restore")
async def restore_deleted_entry(trail_id: str, current_user: dict = Depends(require_director)):
    """Put a deleted entry back, exactly as it was, from the stored copy."""
    from .setup import period_is_locked
    from deps import _audit
    snap = await db.finance_deleted_entries.find_one({"id": trail_id}, {"_id": 0})
    if not snap:
        raise HTTPException(status_code=404, detail="Deleted entry not found")
    if snap.get("restored_at"):
        raise HTTPException(status_code=400, detail="That entry has already been restored")
    entry = snap.get("entry")
    if not entry:
        raise HTTPException(
            status_code=400,
            detail="This row was rebuilt from the audit log and has no line detail, so it can't be restored — re-enter it by hand",
        )
    if await db.finance_journal_entries.find_one({"id": entry.get("id")}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="That entry is already back in the ledger")
    if await period_is_locked(entry.get("date") or "", entry.get("location_id")):
        raise HTTPException(
            status_code=400,
            detail="Fiscal period covering this entry is closed — post a fresh entry in the open period instead",
        )
    entry.pop("_id", None)
    for stale in ("reversed", "reversed_at", "reversed_by", "reversed_by_je", "reversed_reason",
                  "voided", "voided_at", "voided_by", "voided_by_name"):
        entry.pop(stale, None)
    entry["restored_at"] = _now()
    entry["restored_by"] = current_user["id"]
    entry["restored_by_name"] = current_user.get("name") or ""
    await db.finance_journal_entries.insert_one(entry)
    await db.finance_deleted_entries.update_one({"id": trail_id}, {"$set": {
        "restored_at": _now(), "restored_by": current_user["id"],
        "restored_by_name": current_user.get("name") or "",
    }})
    await _audit(current_user["id"], "restore", "journal_entry", entry["id"], {
        "date": entry.get("date"), "description": entry.get("description"),
        "total": float(entry.get("total") or 0), "from_trail": trail_id,
    })
    entry.pop("_id", None)
    return {"restored": entry["id"], "entry": entry}


@router.delete("/{je_id}")
async def delete_entry(je_id: str, reason: str = Query("", max_length=300),
                       current_user: dict = Depends(require_director)):
    """Delete an entry outright while its fiscal period is open.

    A copy, the reason and the user's name go to `finance_deleted_entries` and
    the audit trail. Deleting a contra entry also un-marks the entry it
    reversed, so the original posts again.
    """
    from .setup import period_is_locked
    doc = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if await period_is_locked(doc.get("date") or "", doc.get("location_id")):
        raise HTTPException(
            status_code=400,
            detail="Fiscal period covering this entry is closed — reverse it instead so the correction lands in the open period",
        )
    if not (reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required so the audit trail means something")
    # The contra JE records the entry it reverses in `reference` (older rows
    # used reverses_id / reversed_je_id), so check every shape — otherwise the
    # original silently stays marked reversed and can never post again.
    original_id = None
    if doc.get("source") == "reversal":
        original_id = (doc.get("reverses_id") or doc.get("reversed_je_id")
                       or doc.get("reverses") or doc.get("reference"))
    snapshot = await delete_journal_entry(je_id, reason=reason.strip(), current_user=current_user)
    if original_id:
        await db.finance_journal_entries.update_one(
            {"id": original_id},
            {"$unset": {"reversed": "", "reversed_at": "", "reversed_by": "", "reversed_reason": "", "reversed_by_je": "", "voided": "", "voided_at": "", "voided_by": "", "voided_by_name": ""}},
        )
    return {"deleted": je_id, "restored_original": original_id, "audit_id": snapshot["id"]}

