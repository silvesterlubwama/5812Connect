"""Friendly income / expense endpoints for staff.

Each POST here becomes ONE journal entry under the hood, so users get a
simple form ("record an expense") and the ledger stays properly double-entry
without them having to think about debits and credits.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import db, require_staff

from ._common import post_journal_entry, get_account_by_code, _now

router = APIRouter(prefix="/api/finance/transactions", tags=["finance"])


async def _resolve_account(account_id: Optional[str], code_fallback: Optional[str]) -> dict:
    """Look up by id first, fall back to seeded code (so callers can just
    reference '5000' without knowing UUIDs)."""
    acct = None
    if account_id:
        acct = await db.finance_chart_of_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct and code_fallback:
        acct = await get_account_by_code(code_fallback)
    if not acct:
        raise HTTPException(status_code=400, detail=f"Account not found: id={account_id} code={code_fallback}")
    return acct


@router.post("/expense")
async def record_expense(data: dict, current_user: dict = Depends(require_staff)):
    """One-line expense entry — auto-posts to the ledger.

    Body: {amount, expense_account_id | expense_account_code, paid_from_account_id | paid_from_code,
           date?, description?, location_id?, department_id?, reference?}
    """
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    location_id = (data.get("location_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required — every entry must belong to a campus or sub-location")
    department_id = (data.get("department_id") or "").strip() or None
    expense_acct = await _resolve_account(data.get("expense_account_id"), data.get("expense_account_code"))
    if expense_acct["type"] != "expense":
        raise HTTPException(status_code=400, detail=f"'{expense_acct['name']}' is not an expense account")
    paid_from = await _resolve_account(data.get("paid_from_account_id"), data.get("paid_from_code") or "1000")
    if paid_from["type"] != "asset":
        raise HTTPException(status_code=400, detail=f"'{paid_from['name']}' is not an asset (cash/bank) account")

    je = await post_journal_entry(
        date=data.get("date") or "",
        description=data.get("description") or f"Expense — {expense_acct['name']}",
        lines=[
            {"account_id": expense_acct["id"], "account_code": expense_acct["code"],
             "account_name": expense_acct["name"], "debit": amount, "credit": 0,
             "memo": data.get("description") or ""},
            {"account_id": paid_from["id"], "account_code": paid_from["code"],
             "account_name": paid_from["name"], "debit": 0, "credit": amount,
             "memo": f"Paid from {paid_from['name']}"},
        ],
        source="expense",
        reference=data.get("reference"),
        location_id=location_id,
        department_id=department_id,
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    who = await _resolve_staff(data.get("paid_by_id"), data.get("paid_by_name"))
    if who["staff_id"] or who["staff_name"]:
        await db.finance_journal_entries.update_one({"id": je["id"]}, {"$set": {
            "paid_by_id": who["staff_id"], "paid_by_name": who["staff_name"]}})
        je.update({"paid_by_id": who["staff_id"], "paid_by_name": who["staff_name"]})
    return je


async def _resolve_staff(staff_id: str = "", staff_name: str = "") -> dict:
    """Who physically handled the cash — not the person keying the entry.

    Accepts an id (from the type-ahead) or a typed name; a typed name that
    matches a staff member is linked, and one that doesn't is kept as free text
    rather than thrown away.
    """
    staff_id = (staff_id or "").strip()
    staff_name = (staff_name or "").strip()
    if staff_id:
        u = await db.users.find_one({"id": staff_id}, {"_id": 0, "id": 1, "name": 1})
        if u:
            return {"staff_id": u["id"], "staff_name": u.get("name", "")}
    if staff_name:
        import re as _re
        u = await db.users.find_one(
            {"name": {"$regex": f"^{_re.escape(staff_name)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if u:
            return {"staff_id": u["id"], "staff_name": u.get("name", "")}
        return {"staff_id": None, "staff_name": staff_name[:120]}
    return {"staff_id": None, "staff_name": ""}


@router.post("/income")
async def record_income(data: dict, current_user: dict = Depends(require_staff)):
    """One-line income entry (sponsor gift, donation, misc revenue).

    Body: {amount, revenue_account_id | revenue_account_code, deposited_to_account_id | deposited_to_code,
           date?, description?, location_id (required), department_id?, reference?}
    """
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    location_id = (data.get("location_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required — every entry must belong to a campus or sub-location")
    department_id = (data.get("department_id") or "").strip() or None
    revenue_acct = await _resolve_account(data.get("revenue_account_id"), data.get("revenue_account_code"))
    if revenue_acct["type"] != "revenue":
        raise HTTPException(status_code=400, detail=f"'{revenue_acct['name']}' is not a revenue account")
    deposit_to = await _resolve_account(data.get("deposited_to_account_id"), data.get("deposited_to_code") or "1010")
    if deposit_to["type"] != "asset":
        raise HTTPException(status_code=400, detail=f"'{deposit_to['name']}' is not an asset (cash/bank) account")

    je = await post_journal_entry(
        date=data.get("date") or "",
        description=data.get("description") or f"Income — {revenue_acct['name']}",
        lines=[
            {"account_id": deposit_to["id"], "account_code": deposit_to["code"],
             "account_name": deposit_to["name"], "debit": amount, "credit": 0,
             "memo": f"Deposited to {deposit_to['name']}"},
            {"account_id": revenue_acct["id"], "account_code": revenue_acct["code"],
             "account_name": revenue_acct["name"], "debit": 0, "credit": amount,
             "memo": data.get("description") or ""},
        ],
        source="income",
        reference=data.get("reference"),
        location_id=location_id,
        department_id=department_id,
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    who = await _resolve_staff(data.get("received_by_id"), data.get("received_by_name"))
    if who["staff_id"] or who["staff_name"]:
        await db.finance_journal_entries.update_one({"id": je["id"]}, {"$set": {
            "received_by_id": who["staff_id"], "received_by_name": who["staff_name"]}})
        je.update({"received_by_id": who["staff_id"], "received_by_name": who["staff_name"]})
    return je


@router.get("/staff-search")
async def staff_search(q: str = Query(..., min_length=2), current_user: dict = Depends(require_staff)):
    """Type-ahead for "who spent / received this".

    Deliberately NOT `/admin/users`: that endpoint is admin-only (a finance
    manager got a 403) and campus-filters people who have no campus set, so
    half the staff were unfindable. Cash can be handled by anyone on the team,
    so this searches all active staff by name or email.
    """
    import re as _re
    rx = {"$regex": _re.escape(q.strip()), "$options": "i"}
    rows = await db.users.find(
        {"status": {"$ne": "inactive"}, "$or": [{"name": rx}, {"email": rx}]},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1},
    ).sort("name", 1).to_list(10)
    return rows


@router.get("/recent")
async def recent_transactions(
    limit: int = Query(50, le=500),
    current_user: dict = Depends(require_staff),
):
    """Flat list of the newest journal entries with a friendlier shape for a
    dashboard "recent activity" widget — hides internal columns and picks the
    most-relevant line's account name for the primary label.
    """
    rows = await db.finance_journal_entries.find(
        {"reversed": {"$ne": True}}, {"_id": 0},
    ).sort([("date", -1), ("created_at", -1)]).limit(limit).to_list(limit)
    out = []
    for r in rows:
        lines = r.get("lines") or []
        # Primary line = the debit for expenses (the expense account itself),
        # credit for income (the revenue account itself). Fallback = first line.
        primary = next((ln for ln in lines if r.get("source") == "expense" and ln.get("debit")), None)
        if not primary:
            primary = next((ln for ln in lines if r.get("source") == "income" and ln.get("credit")), None)
        if not primary:
            primary = lines[0] if lines else {}
        out.append({
            "id": r["id"],
            "date": r["date"],
            "source": r["source"],
            "description": r.get("description"),
            "account": primary.get("account_name"),
            "total": r.get("total"),
            "location_id": r.get("location_id"),
            "created_by_name": r.get("created_by_name"),
            # Who handled the cash (manual entries) and the origin/reference
            # for automatic ones — the widget shows both.
            "paid_by_name": r.get("paid_by_name"),
            "received_by_name": r.get("received_by_name"),
            "reference": r.get("reference"),
        })
    return out
