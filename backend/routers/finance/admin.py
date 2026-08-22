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



@router.post("/backfill-payroll")
async def backfill_payroll(current_user: dict = Depends(require_admin)):
    """Sweep every paid payslip that isn't already on the new ledger and post it.

    Idempotent by payslip.id (via `post_payroll_payslip`'s idempotency key),
    so running this twice never double-posts. Returns per-payslip result
    counts + a per-error sample so ops can see WHAT was skipped, not just
    HOW MANY.
    """
    from routers.finance.postings import post_payroll_payslip

    posted = skipped = failed = 0
    errors: list = []
    async for slip in db.hr_payslips.find({"status": "paid"}, {"_id": 0}):
        try:
            je = await post_payroll_payslip(slip, current_user)
            if je is None:
                skipped += 1
            else:
                # `post_journal_entry` returns the existing JE if idempotency_key
                # was seen before. We treat re-hit as "posted" for reporting so
                # the number matches count-of-paid-payslips.
                posted += 1
        except Exception as e:
            failed += 1
            if len(errors) < 10:
                errors.append({"payslip_id": slip.get("id"), "error": str(e)[:200]})
    return {"processed": posted + skipped + failed, "posted_or_replayed": posted,
            "skipped_no_amount": skipped, "failed": failed, "error_sample": errors}


@router.post("/backfill-social-payments")
async def backfill_social_payments(current_user: dict = Depends(require_admin)):
    """Sweep every social-work payment (donation/expense) that isn't on the
    new ledger yet. Idempotent by payment.id."""
    from routers.finance._common import post_journal_entry, get_account_by_code

    posted = skipped = failed = 0
    errors: list = []
    async for pay in db.social_child_payments.find({}, {"_id": 0}):
        try:
            kind = pay.get("kind")
            amount = float(pay.get("amount") or 0)
            if amount <= 0:
                skipped += 1
                continue
            if kind == "child_support":
                revenue = await get_account_by_code("4000")
                bank = await get_account_by_code("1010")
                if not (revenue and bank):
                    skipped += 1; continue
                await post_journal_entry(
                    date=pay.get("date") or "",
                    description=f"Sponsorship gift — backfill {pay.get('id')}"[:280],
                    lines=[
                        {"account_id": bank["id"], "account_code": bank["code"], "account_name": bank["name"], "debit": amount, "credit": 0},
                        {"account_id": revenue["id"], "account_code": revenue["code"], "account_name": revenue["name"], "debit": 0, "credit": amount},
                    ],
                    source="social_donation",
                    reference=pay.get("id"),
                    location_id=pay.get("location_id"),
                    created_by=current_user["id"],
                    created_by_name=current_user.get("name"),
                    idempotency_key=f"social_payment:{pay.get('id')}",
                )
                posted += 1
            else:
                expense_code = {"tuition": "5300", "medical": "5300", "resource": "5300"}.get(kind, "5900")
                expense_acct = await get_account_by_code(expense_code)
                cash = await get_account_by_code("1000")
                if not (expense_acct and cash):
                    skipped += 1; continue
                await post_journal_entry(
                    date=pay.get("date") or "",
                    description=f"{(kind or 'expense').title()} — backfill {pay.get('id')}"[:280],
                    lines=[
                        {"account_id": expense_acct["id"], "account_code": expense_acct["code"], "account_name": expense_acct["name"], "debit": amount, "credit": 0},
                        {"account_id": cash["id"], "account_code": cash["code"], "account_name": cash["name"], "debit": 0, "credit": amount},
                    ],
                    source="social_expense",
                    reference=pay.get("id"),
                    location_id=pay.get("location_id"),
                    created_by=current_user["id"],
                    created_by_name=current_user.get("name"),
                    idempotency_key=f"social_payment:{pay.get('id')}",
                )
                posted += 1
        except Exception as e:
            failed += 1
            if len(errors) < 10:
                errors.append({"payment_id": pay.get("id"), "error": str(e)[:200]})
    return {"processed": posted + skipped + failed, "posted_or_replayed": posted,
            "skipped": skipped, "failed": failed, "error_sample": errors}
