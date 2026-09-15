"""iter355 — retire the contra entries left by the old reversal behaviour.

Reversing used to post a mirror JE and mark the original `reversed`. Every
report filters out `reversed`, so the original vanished while its mirror stayed
in — the ledger carried the upside-down copy instead of netting to zero.

Reversals are now a void in place. This voids BOTH sides of every historical
pair so the totals read as if they had always been voided. Nothing is deleted;
the rows stay visible under "Include voided / reversed".

Idempotent: re-running skips anything already voided.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from deps import db  # noqa: E402

REASON = "Legacy reversal cleaned up (iter355) — voided instead of mirrored"


async def main(dry_run: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    contras = await db.finance_journal_entries.find(
        {"source": "reversal", "voided": {"$ne": True}},
        {"_id": 0, "id": 1, "reference": 1, "total": 1, "description": 1},
    ).to_list(1000)
    voided_contras, voided_originals, missing = 0, 0, []
    for c in contras:
        original_id = c.get("reference")
        orig = await db.finance_journal_entries.find_one({"id": original_id}, {"_id": 0, "id": 1, "voided": 1})
        if not orig:
            missing.append(c["id"])
        print(f"{'WOULD VOID' if dry_run else 'VOIDING'} contra {c['id']} ({c['total']}) "
              f"+ original {original_id or 'MISSING'}")
        if dry_run:
            continue
        patch = {"voided": True, "reversed": True, "voided_at": now,
                 "voided_by_name": "System migration", "reversed_reason": REASON}
        await db.finance_journal_entries.update_one({"id": c["id"]}, {"$set": patch})
        voided_contras += 1
        if orig and not orig.get("voided"):
            await db.finance_journal_entries.update_one({"id": original_id}, {"$set": patch})
            voided_originals += 1
    print(f"\ncontras voided: {voided_contras} · originals voided: {voided_originals} "
          f"· contras with no original: {len(missing)}")
    live = await db.finance_journal_entries.count_documents({"voided": {"$ne": True}})
    print(f"live entries remaining: {live}")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
