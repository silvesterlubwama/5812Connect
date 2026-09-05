"""Backwards-compat shim for the deleted `routers.accounting` module.

`bank.py` (bill posting, bill payment posting) and the unmounted `financial.py`
still import `_next_entry_number` and `reverse_entry` from what used to be
`routers.accounting`. Rather than untangle both files right now, this shim
provides just those two symbols.

DO NOT add anything new here — new finance work must go through
`routers/finance/*`. This exists only until `bank.py`'s Odoo-style
`accounting_entries` bill-posting path is migrated to `post_journal_entry`,
at which point this file can be deleted as well.
"""
from datetime import datetime, timezone

from deps import db, logger


async def _next_entry_number(journal_id: str) -> str:
    """Journal-scoped monotonic counter for `accounting_entries.number`."""
    yr = datetime.now(timezone.utc).year
    count = await db.accounting_entries.count_documents(
        {"journal_id": journal_id, "number": {"$regex": f"/{yr}/"}}
    )
    return f"JE/{yr}/{count + 1:04d}"


async def reverse_entry(entry_id: str, data: dict, current_user: dict):
    """Post a mirror JE reversing `entry_id`. Preserves the original — the
    reversal is a fresh entry with `auto_generated_from='reversal'` and
    debit/credit sides flipped on every line. Matches the pre-purge
    behaviour of `routers.accounting.reverse_entry` closely enough for the
    two callers we still have (`financial.py::_reverse_auto_posted_je` and
    its social-payments equivalent — both currently dead code because
    financial.py isn't mounted, but kept for safety).
    """
    import uuid
    orig = await db.accounting_entries.find_one({"id": entry_id}, {"_id": 0})
    if not orig:
        raise ValueError(f"Entry {entry_id} not found")
    if orig.get("is_reversed"):
        return orig
    rev_id = f"je_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    rev_number = await _next_entry_number(orig["journal_id"])
    reason = (data or {}).get("reason") or "Reversal"
    rev = {
        **{k: v for k, v in orig.items() if k not in ("id", "number", "created_at", "posted_at", "is_reversed", "reversed_by", "_id")},
        "id": rev_id,
        "number": rev_number,
        "narration": f"REVERSAL of {orig.get('number')} — {reason}",
        "auto_generated_from": "reversal",
        "reverses_id": entry_id,
        "created_at": now_iso,
        "posted_at": now_iso,
        "posted_by": current_user.get("id"),
    }
    await db.accounting_entries.insert_one(rev)
    # Mirror the line items with debit/credit swapped
    lines = await db.accounting_entry_lines.find({"entry_id": entry_id}, {"_id": 0}).to_list(500)
    if lines:
        rev_lines = []
        for ln in lines:
            new_line = {k: v for k, v in ln.items() if k != "_id"}
            new_line["entry_id"] = rev_id
            new_line["id"] = f"jel_{uuid.uuid4().hex[:10]}"
            new_line["debit"], new_line["credit"] = ln.get("credit", 0), ln.get("debit", 0)
            rev_lines.append(new_line)
        await db.accounting_entry_lines.insert_many(rev_lines)
    await db.accounting_entries.update_one(
        {"id": entry_id},
        {"$set": {"is_reversed": True, "reversed_by": rev_id, "reversed_at": now_iso, "reversal_reason": reason}},
    )
    logger.info(f"[accounting_shim] Reversed {entry_id} → {rev_id}")
    return rev
