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


class LedgerSetupError(Exception):
    """The ledger can't take this posting yet — e.g. the chart of accounts is
    missing the account payroll or sales needs. Raised instead of returning
    quietly, so the caller can tell the user what to fix."""


async def post_payroll_payslip(payslip: dict, current_user: dict) -> Optional[dict]:
    """Called by HR when a payslip's status flips to 'paid'.

    iter381 — a payslip is no longer a single Dr Wages / Cr Bank line. What the
    staff member earns, what was withheld on their behalf and what the employer
    contributes on top are three different movements and the books have to show
    all three:

        Debit  5002 Wages & Salaries         gross earnings (net + withheld)
        Debit  <employer line account>       each employer contribution
        Credit 2200 Taxes Payable            withheld + employer statutory
        Credit 1010 Bank / configured cash   net actually paid out

    Idempotent by payslip.id — running twice yields the same JE, not two.
    Raises LedgerSetupError when the chart of accounts can't support it (this
    used to return None, which is how paid payslips ended up with nothing in
    the ledger and HR still saw a success message).
    """
    net = _q(payslip.get("net_salary"))
    if net <= 0:
        return None
    expense_acct = (await get_account_by_code("5002")) or (await get_account_by_code("5000"))
    if not expense_acct:
        raise LedgerSetupError(
            "Chart of accounts has no 5002 Wages & Salaries (or 5000 Salaries & Wages) account — "
            "add it in Finance → Chart of Accounts (or seed the defaults) and post again"
        )
    cash_acct = await _cash_account_id(payslip.get("payroll_location_id") or payslip.get("location_id"))
    if not cash_acct:
        raise LedgerSetupError(
            "No bank or cash account to pay from — set a default cash account for this "
            "campus, or add 1010 Bank — Operating in Finance → Chart of Accounts"
        )

    items = payslip.get("line_items") or []

    def _amt(li):
        return _q(li.get("calculated_amount") if li.get("calculated_amount") is not None else li.get("amount"))

    # Withheld on the employee's behalf (PAYE, NSSF employee …) — pay reduces,
    # but the money is owed to an authority, not kept.
    withheld = {}
    for li in items:
        if (li.get("type") or "") != "deduction" or li.get("source") != "statutory":
            continue
        amt = _amt(li)
        if amt > 0:
            withheld[li.get("liability_account_code") or "2200"] = \
                withheld.get(li.get("liability_account_code") or "2200", 0) + amt
    # Employer contributions that are NOT paid to the employee.
    employer = []
    for li in items:
        if (li.get("type") or "") != "employer_contribution":
            continue
        if (li.get("mode") or "employer_cost") == "add_to_pay":
            continue       # already inside net pay
        amt = _amt(li)
        if amt > 0:
            employer.append((li.get("account_code") or "5002",
                             li.get("liability_account_code") or "2200", amt, li.get("name") or ""))

    withheld_total = round(sum(withheld.values()), 2)
    lines = [
        {"account_id": expense_acct["id"], "account_code": expense_acct["code"],
         "account_name": expense_acct["name"], "debit": float(round(net + withheld_total, 2)), "credit": 0,
         "memo": "Gross earnings"},
    ]
    liability_credits: dict = dict(withheld)
    for exp_code, liab_code, amt, name in employer:
        acct = await get_account_by_code(exp_code) or expense_acct
        lines.append({"account_id": acct["id"], "account_code": acct["code"],
                      "account_name": acct["name"], "debit": float(amt), "credit": 0,
                      "memo": f"Employer contribution — {name}"})
        liability_credits[liab_code] = liability_credits.get(liab_code, 0) + amt
    for liab_code, amt in liability_credits.items():
        liab = await get_account_by_code(liab_code) or await get_account_by_code("2200")
        if not liab:
            raise LedgerSetupError(
                f"Chart of accounts has no {liab_code} account for payroll deductions — "
                "add it in Finance → Chart of Accounts (2200 Taxes Payable) and post again"
            )
        lines.append({"account_id": liab["id"], "account_code": liab["code"],
                      "account_name": liab["name"], "debit": 0, "credit": float(round(amt, 2)),
                      "memo": "Payroll deductions / contributions payable"})
    lines.append({"account_id": cash_acct["id"], "account_code": cash_acct["code"],
                  "account_name": cash_acct["name"], "debit": 0, "credit": float(net),
                  "memo": "Net pay"})

    return await post_journal_entry(
        date=(payslip.get("paid_at") or payslip.get("date") or "")[:10],
        description=f"Payroll — {payslip.get('staff_name') or 'staff'} — {payslip.get('period') or ''}",
        lines=lines,
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
