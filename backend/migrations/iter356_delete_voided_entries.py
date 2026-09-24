"""iter356 — turn the iter355 "voided" entries into proper deletions.

Reversing in an open period now DELETES the entry (with a full copy + the
user's name + reason kept in `finance_deleted_entries` and the audit trail).
The short-lived `voided` flag left struck-through rows in the journal; the user
wants them gone. Each row is snapshotted exactly like a live delete, so the
audit trail still answers "what was here and who removed it".

Idempotent: once a row is deleted there is nothing left to migrate.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from deps import db  # noqa: E402

REASON = "Removed by the iter356 cleanup — reversed entries are deleted, not voided"


async def main(dry_run: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    rows = await db.finance_journal_entries.find({"voided": True}, {"_id": 0}).to_list(2000)
    print(f"{len(rows)} voided entr{'y' if len(rows) == 1 else 'ies'} to delete")
    for r in rows:
        print(f"{'WOULD DELETE' if dry_run else 'DELETING'} {r['id']} · {r.get('date')} · "
              f"{r.get('description')} · {r.get('total')}")
        if dry_run:
            continue
        await db.finance_deleted_entries.insert_one({
            "id": f"jedel_{uuid.uuid4().hex[:10]}",
            "je_id": r["id"],
            "date": r.get("date"),
            "description": r.get("description"),
            "source": r.get("source"),
            "reference": r.get("reference"),
            "total": float(r.get("total") or 0),
            "location_id": r.get("location_id"),
            "lines": r.get("lines") or [],
            "reason": r.get("reversed_reason") or REASON,
            "deleted_at": r.get("voided_at") or now,
            "deleted_by": r.get("voided_by") or "system",
            "deleted_by_name": r.get("voided_by_name") or "System cleanup",
            "original_created_by_name": r.get("created_by_name") or "",
            "original_created_at": r.get("created_at"),
            "entry": r,
        })
        await db.audit_log.insert_one({
            "id": f"aud_{uuid.uuid4().hex[:10]}",
            "user_id": r.get("voided_by") or "system",
            "user_name": r.get("voided_by_name") or "System cleanup",
            "action": "delete",
            "resource": "journal_entry",
            "resource_id": r["id"],
            "details": {"date": r.get("date"), "description": r.get("description"),
                        "total": float(r.get("total") or 0),
                        "reason": r.get("reversed_reason") or REASON},
            "timestamp": now,
        })
        await db.finance_journal_entries.delete_one({"id": r["id"]})
    live = await db.finance_journal_entries.count_documents({})
    print(f"\njournal entries remaining: {live} · deleted-entry trail: "
          f"{await db.finance_deleted_entries.count_documents({})}")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
