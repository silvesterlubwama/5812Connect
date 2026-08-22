"""Admin: reset the finance module (archive old collections → seed fresh).

DESTRUCTIVE but recoverable: every wiped doc lands in `<collection>_archive_<ts>`
so we can always restore. Requires `require_admin`.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from deps import db, require_admin

from ._common import FINANCE_COLLECTIONS, ensure_seed_accounts, _now

router = APIRouter(prefix="/api/finance/admin", tags=["finance"])


@router.get("/status")
async def status(current_user: dict = Depends(require_admin)):
    """Snapshot for the reset dialog UI: doc counts + last JE date."""
    counts = {}
    for c in FINANCE_COLLECTIONS:
        counts[c] = await db[c].count_documents({})
    last_je = await db.finance_journal_entries.find_one({}, {"_id": 0, "date": 1, "created_at": 1}, sort=[("created_at", -1)])
    return {"collections": counts, "last_journal_entry": last_je}


@router.post("/reset")
async def reset_finance(data: dict, current_user: dict = Depends(require_admin)):
    """Archive → wipe → reseed.

    Body: {confirm: "RESET FINANCE"} (guard so nothing runs accidentally).
    Returns per-collection archived count + how many seed accounts were
    inserted after wipe.
    """
    if (data or {}).get("confirm") != "RESET FINANCE":
        return {"error": "Confirmation phrase missing", "expected": "RESET FINANCE"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archived = {}
    for c in FINANCE_COLLECTIONS:
        docs = await db[c].find({}, {"_id": 0}).to_list(100000)
        if docs:
            for d in docs:
                d["_archived_at"] = _now()
                d["_archived_by"] = current_user["id"]
            await db[f"{c}_archive_{ts}"].insert_many(docs)
        archived[c] = len(docs)
        await db[c].delete_many({})

    inserted = await ensure_seed_accounts()
    return {"archived": archived, "archive_suffix": ts, "seeded_accounts": inserted}
