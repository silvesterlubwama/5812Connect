"""Reports — Trial Balance, P&L, Balance Sheet, Cashflow.

All read directly from `finance_journal_entries`. If a number here doesn't
match the journal, the JE list is the source of truth — not the other way
around.

Convention:
  • Debits increase assets & expenses
  • Credits increase liabilities, equity, revenue
  • Balance side per type is defined by DEBIT_TYPES / CREDIT_TYPES in _common
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from deps import db, require_staff

from ._common import DEBIT_TYPES

router = APIRouter(prefix="/api/finance/reports", tags=["finance"])


async def _load_coa() -> tuple[dict, dict]:
    """Return (accounts_by_id, accounts_by_type). Cheap — the COA is at most
    a few dozen rows."""
    by_id = {}
    by_type: dict = {t: [] for t in ("asset", "liability", "equity", "revenue", "expense")}
    async for a in db.finance_chart_of_accounts.find({}, {"_id": 0}):
        by_id[a["id"]] = a
        by_type.setdefault(a["type"], []).append(a)
    return by_id, by_type


async def _balances_by_account(
    date_from: Optional[str], date_to: Optional[str], location_id: Optional[str]
) -> dict[str, dict]:
    """Aggregate debits/credits per account for the window. Returns
    {account_id: {debit, credit, balance_debit_side, balance_credit_side}}.

    'balance' is the *sign-aware* net movement using the account's normal
    balance side — so asset debits and expense debits both come out positive.
    """
    match: dict = {"reversed": {"$ne": True}}
    if date_from:
        match.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        match.setdefault("date", {})["$lte"] = date_to[:10]
    if location_id and location_id != "all":
        match["location_id"] = location_id
    pipeline = [
        {"$match": match},
        {"$unwind": "$lines"},
        {"$group": {
            "_id": "$lines.account_id",
            "debit": {"$sum": "$lines.debit"},
            "credit": {"$sum": "$lines.credit"},
        }},
    ]
    coa_by_id, _ = await _load_coa()
    out: dict = {}
    async for r in db.finance_journal_entries.aggregate(pipeline):
        acct = coa_by_id.get(r["_id"])
        if not acct:
            continue
        debit = round(r["debit"], 2)
        credit = round(r["credit"], 2)
        balance = round(debit - credit, 2) if acct["type"] in DEBIT_TYPES else round(credit - debit, 2)
        out[r["_id"]] = {
            "account": acct,
            "debit": debit,
            "credit": credit,
            "balance": balance,
        }
    return out


@router.get("/trial-balance")
async def trial_balance(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Every non-zero account with its debit and credit totals.

    Total debits MUST equal total credits (if not, the JE invariant is broken
    — that's a data-corruption alarm, not a report bug)."""
    bal = await _balances_by_account(date_from, date_to, location_id)
    rows = sorted(
        [{"account_id": aid, **v["account"], "debit": v["debit"], "credit": v["credit"], "balance": v["balance"]}
         for aid, v in bal.items() if v["debit"] or v["credit"]],
        key=lambda r: (r.get("code") or ""),
    )
    total_debit = round(sum(r["debit"] for r in rows), 2)
    total_credit = round(sum(r["credit"] for r in rows), 2)
    return {
        "rows": rows,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": abs(total_debit - total_credit) < 0.01,
        "date_from": date_from or "",
        "date_to": date_to or "",
    }


@router.get("/pnl")
async def profit_and_loss(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Revenue - Expenses for the period."""
    bal = await _balances_by_account(date_from, date_to, location_id)
    revenue_rows, expense_rows = [], []
    for v in bal.values():
        a = v["account"]
        row = {"account_id": a["id"], "code": a["code"], "name": a["name"], "amount": v["balance"]}
        if a["type"] == "revenue" and v["balance"] != 0:
            revenue_rows.append(row)
        elif a["type"] == "expense" and v["balance"] != 0:
            expense_rows.append(row)
    revenue_rows.sort(key=lambda r: r["code"])
    expense_rows.sort(key=lambda r: r["code"])
    total_revenue = round(sum(r["amount"] for r in revenue_rows), 2)
    total_expenses = round(sum(r["amount"] for r in expense_rows), 2)
    return {
        "revenue": revenue_rows,
        "expenses": expense_rows,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_income": round(total_revenue - total_expenses, 2),
        "date_from": date_from or "",
        "date_to": date_to or "",
    }


@router.get("/balance-sheet")
async def balance_sheet(
    as_of: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Assets = Liabilities + Equity (+ Net Income for the period).

    We fold running Net Income into equity as "Current-year earnings" so a
    fresh install (empty Retained Earnings + revenue > expenses) still
    balances without staff having to run a manual year-end close."""
    bal = await _balances_by_account(None, as_of, location_id)
    assets, liabilities, equity = [], [], []
    revenue_total = expense_total = 0.0
    for v in bal.values():
        a = v["account"]
        row = {"account_id": a["id"], "code": a["code"], "name": a["name"], "amount": v["balance"]}
        if a["type"] == "asset" and v["balance"] != 0:
            assets.append(row)
        elif a["type"] == "liability" and v["balance"] != 0:
            liabilities.append(row)
        elif a["type"] == "equity" and v["balance"] != 0:
            equity.append(row)
        elif a["type"] == "revenue":
            revenue_total += v["balance"]
        elif a["type"] == "expense":
            expense_total += v["balance"]

    current_earnings = round(revenue_total - expense_total, 2)
    if current_earnings:
        equity.append({"account_id": "_ce_", "code": "3999", "name": "Current-year earnings", "amount": current_earnings})

    for group in (assets, liabilities, equity):
        group.sort(key=lambda r: r["code"])
    total_assets = round(sum(r["amount"] for r in assets), 2)
    total_liab = round(sum(r["amount"] for r in liabilities), 2)
    total_equity = round(sum(r["amount"] for r in equity), 2)
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liab,
        "total_equity": total_equity,
        "total_liab_equity": round(total_liab + total_equity, 2),
        "balanced": abs(total_assets - (total_liab + total_equity)) < 0.01,
        "as_of": as_of or "",
    }


@router.get("/cashflow")
async def cashflow(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Movement across every cash/bank account (is_cash=True) in the period.

    Simpler than a full three-section cashflow statement, but exactly what
    an operations director wants: "did cash go up or down and where did it
    go?"
    """
    coa_by_id, _ = await _load_coa()
    cash_ids = {a["id"] for a in coa_by_id.values() if a.get("is_cash")}
    if not cash_ids:
        return {"lines": [], "net_change": 0.0, "note": "No cash accounts flagged (is_cash)"}

    match: dict = {"reversed": {"$ne": True}, "lines.account_id": {"$in": list(cash_ids)}}
    if date_from:
        match.setdefault("date", {})["$gte"] = date_from[:10]
    if date_to:
        match.setdefault("date", {})["$lte"] = date_to[:10]
    if location_id and location_id != "all":
        match["location_id"] = location_id

    pipeline = [
        {"$match": match},
        {"$unwind": "$lines"},
        {"$match": {"lines.account_id": {"$in": list(cash_ids)}}},
        {"$group": {
            "_id": {"account": "$lines.account_id", "source": "$source"},
            "debit": {"$sum": "$lines.debit"},
            "credit": {"$sum": "$lines.credit"},
        }},
    ]
    rows = []
    net_change = 0.0
    async for r in db.finance_journal_entries.aggregate(pipeline):
        a = coa_by_id.get(r["_id"]["account"])
        if not a:
            continue
        # Debit to cash = inflow, credit = outflow
        delta = round(r["debit"] - r["credit"], 2)
        rows.append({
            "account_id": a["id"], "code": a["code"], "name": a["name"],
            "source": r["_id"]["source"],
            "inflow": round(r["debit"], 2),
            "outflow": round(r["credit"], 2),
            "net": delta,
        })
        net_change += delta
    rows.sort(key=lambda r: (r["code"], r["source"]))
    return {"lines": rows, "net_change": round(net_change, 2),
            "date_from": date_from or "", "date_to": date_to or ""}
