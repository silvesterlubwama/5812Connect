"""Postings from other modules (HR payroll, Sales/POS).

Both call into `post_journal_entry` — they don't have their own ledger, they
just build the right line-shape and hand it off. This is the single source
of truth for how payroll and sales become ledger movements.
"""
from typing import Optional

from deps import db, logger

from ._common import post_journal_entry, get_account_by_code, _q


async def _cash_account_id(location_id: Optional[str] = None, channel: Optional[str] = None) -> Optional[dict]:
    """Pick the account the money lands in.

    iter320: online orders land in their OWN account (1030 Online Payments) —
    the user asked to keep web takings separate from till/bank cash, so a
    gateway payout can be reconciled on its own. Everything else keeps the
    location-configured cash account, then 1010 Bank — Operating, then 1000
    Cash on Hand as a last resort.
    """
    if channel == "online":
        online = await get_account_by_code("1030")
        if online:
            return online
    if location_id:
        s = await db.store_settings.find_one({"location_id": location_id}, {"_id": 0, "default_cash_account_id": 1})
        cash_id = (s or {}).get("default_cash_account_id")
        if cash_id:
            a = await db.finance_chart_of_accounts.find_one({"id": cash_id}, {"_id": 0})
            if a:
                return a
    return (await get_account_by_code("1010")) or (await get_account_by_code("1000"))


async def post_payroll_payslip(payslip: dict, current_user: dict) -> Optional[dict]:
    """Called by HR when a payslip's status flips to 'paid'. Posts:

        Debit  5000 Salaries & Wages
        Credit 1010 Bank — Operating (or configured location cash account)

    Idempotent by payslip.id — running twice yields the same JE, not two.
    """
    net = _q(payslip.get("net_salary"))
    if net <= 0:
        return None
    expense_acct = await get_account_by_code("5000")
    if not expense_acct:
        logger.warning("[finance] post_payroll_payslip: no 5000 Salaries account (COA not seeded)")
        return None
    cash_acct = await _cash_account_id(payslip.get("payroll_location_id") or payslip.get("location_id"))
    if not cash_acct:
        logger.warning("[finance] post_payroll_payslip: no cash account available")
        return None

    return await post_journal_entry(
        date=(payslip.get("paid_at") or payslip.get("date") or "")[:10],
        description=f"Payroll — {payslip.get('staff_name') or 'staff'} — {payslip.get('period') or ''}",
        lines=[
            {"account_id": expense_acct["id"], "account_code": expense_acct["code"],
             "account_name": expense_acct["name"], "debit": float(net), "credit": 0},
            {"account_id": cash_acct["id"], "account_code": cash_acct["code"],
             "account_name": cash_acct["name"], "debit": 0, "credit": float(net)},
        ],
        source="payroll",
        reference=payslip.get("id"),
        location_id=payslip.get("payroll_location_id") or payslip.get("location_id"),
        created_by=current_user.get("id"),
        created_by_name=current_user.get("name"),
        idempotency_key=f"payslip:{payslip.get('id')}",
    )


async def post_sale(sale: dict, current_user: dict) -> Optional[dict]:
    """Called by POS/Sales when a sale is settled as paid.

        Debit  1010 Bank / 1000 Cash on Hand
        Credit 4100 Sales Revenue

    Cost of goods sold NOT auto-posted — that's a phase-2 refinement that
    needs a proper inventory valuation policy.
    """
    total = _q(sale.get("total") or sale.get("amount"))
    if total <= 0:
        return None
    revenue_acct = await get_account_by_code("4100")
    if not revenue_acct:
        return None
    cash_acct = await _cash_account_id(sale.get("location_id"), sale.get("channel"))
    if not cash_acct:
        return None
    return await post_journal_entry(
        date=(sale.get("date") or sale.get("created_at") or "")[:10],
        description=f"Sale — invoice {sale.get('invoice_number') or sale.get('id')}",
        lines=[
            {"account_id": cash_acct["id"], "account_code": cash_acct["code"],
             "account_name": cash_acct["name"], "debit": float(total), "credit": 0},
            {"account_id": revenue_acct["id"], "account_code": revenue_acct["code"],
             "account_name": revenue_acct["name"], "debit": 0, "credit": float(total)},
        ],
        source="sale",
        reference=sale.get("id"),
        location_id=sale.get("location_id"),
        created_by=current_user.get("id"),
        created_by_name=current_user.get("name"),
        idempotency_key=f"sale:{sale.get('id')}",
    )
