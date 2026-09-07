"""Shared helpers for the finance package.

One goal: EVERY monetary movement in the system flows through
`post_journal_entry()` here, which enforces `Σ debits == Σ credits`.
Reports read from `db.finance_journal_entries` exclusively — no other
collection is a source of truth for the ledger.

The seed Chart of Accounts is small on purpose (17 accounts). Add more
via the UI or the direct COA endpoints, but this covers 95% of what a
mid-size NGO/CRM needs on day 1.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import HTTPException

from deps import db, logger

# Canonical account types → normal balance side (used by reports).
DEBIT_TYPES = {"asset", "expense"}
CREDIT_TYPES = {"liability", "equity", "revenue"}
ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}

# Reset marker → collections we touch, in one place, so nothing gets missed
# when the user hits the "Reset Finance" button. Everything ending in
# `_archive_<ts>` is preserved for audit / recovery.
# HR data (hr_payslips/hr_salaries/hr_settings) is INTENTIONALLY excluded —
# HR lives in its own top-level section and has its own admin surface.
FINANCE_COLLECTIONS = [
    # Core ledger
    "finance_chart_of_accounts",
    "finance_journal_entries",
    "finance_transactions",
    # Legacy financial module (records that pre-date the double-entry ledger)
    "financial",
    "financial_accounts",
    "financial_transfers",
    "financial_categories",
    "financial_budgets",
    "financial_assets",
    "financial_settings",
    # Banking
    "bank_accounts",
    "bank_transactions",
    "bank_reconciliations",
    # AR / AP counterparties
    "donors",
    "vendors",
    # Marketplace + sales stack
    "products",
    "product_variants",
    "sales",
    "sales_orders",
    "sales_quotes",
    "sales_receipts",
    "cash_drops",
    "cashier_shifts",
    # Approvals + budgets tied to finance
    "approvals",
    "budgets",
    # Legacy accounting collections (deprecated iter 246 but never cleared —
    # they were still showing up in Banking, drop-downs & reports after a
    # reset. iter 284 pulls them into the reset scope so a "Reset Finance"
    # really does nuke every stale CoA/JE/tax row from the old module.)
    "accounting_accounts",
    "accounting_entries",
    "accounting_entry_lines",
    "accounting_journals",
    "accounting_taxes",
    "accounting_fiscal_periods",
    "chart_accounts",
    "chart_account_transfers",
    "customer_accounts",
]

# Seed COA — code prefixes follow the standard convention (1xxx assets,
# 2xxx liabilities, 3xxx equity, 4xxx revenue, 5xxx-6xxx expenses).
SEED_ACCOUNTS = [
    # Assets
    {"code": "1000", "name": "Cash on Hand", "type": "asset", "is_cash": True},
    {"code": "1010", "name": "Bank — Operating", "type": "asset", "is_cash": True},
    {"code": "1020", "name": "Bank — Reserves", "type": "asset", "is_cash": True},
    {"code": "1200", "name": "Accounts Receivable", "type": "asset"},
    {"code": "1500", "name": "Inventory", "type": "asset"},
    # Liabilities
    {"code": "2000", "name": "Accounts Payable", "type": "liability"},
    {"code": "2100", "name": "Salaries Payable", "type": "liability"},
    {"code": "2200", "name": "Taxes Payable (PAYE / NSSF)", "type": "liability"},
    # Equity
    {"code": "3000", "name": "Opening Balance Equity", "type": "equity"},
    {"code": "3100", "name": "Retained Earnings", "type": "equity"},
    # Revenue
    {"code": "4000", "name": "Sponsorship Income", "type": "revenue"},
    {"code": "4100", "name": "Sales Revenue", "type": "revenue"},
    {"code": "4900", "name": "Other Income", "type": "revenue"},
    # Expenses
    {"code": "5000", "name": "Salaries & Wages", "type": "expense"},
    {"code": "5100", "name": "Rent & Utilities", "type": "expense"},
    {"code": "5200", "name": "Food & Provisions", "type": "expense"},
    {"code": "5300", "name": "Programme Costs", "type": "expense"},
    {"code": "5400", "name": "Office & Admin", "type": "expense"},
    {"code": "5900", "name": "Other Expenses", "type": "expense"},
]


def _q(v) -> Decimal:
    """Money-safe decimal — 2dp, banker-safe."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_seed_accounts() -> int:
    """Idempotent seed. Returns how many accounts were newly inserted."""
    existing_codes = set()
    async for a in db.finance_chart_of_accounts.find({}, {"_id": 0, "code": 1}):
        if a.get("code"):
            existing_codes.add(a["code"])
    inserted = 0
    for seed in SEED_ACCOUNTS:
        if seed["code"] in existing_codes:
            continue
        await db.finance_chart_of_accounts.insert_one({
            "id": f"acc_{uuid.uuid4().hex[:10]}",
            "code": seed["code"],
            "name": seed["name"],
            "type": seed["type"],
            "is_cash": bool(seed.get("is_cash")),
            "is_system": True,          # seeded → cannot be deleted by users
            "active": True,
            "created_at": _now(),
        })
        inserted += 1
    return inserted


async def get_account_by_code(code: str) -> Optional[dict]:
    """Fast lookup used by postings — return the whole account doc or None."""
    return await db.finance_chart_of_accounts.find_one({"code": code}, {"_id": 0})


async def post_journal_entry(
    *,
    date: str,
    description: str,
    lines: list[dict],
    source: str,
    reference: Optional[str] = None,
    location_id: Optional[str] = None,
    department_id: Optional[str] = None,
    created_by: Optional[str] = None,
    created_by_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """The ONE way to record a movement.

    `lines` is a list of `{account_id, debit, credit}` — one of debit/credit
    must be > 0, the other 0, on each line. Total debits MUST equal total
    credits (raises 400 otherwise).

    `idempotency_key` (optional) lets callers replay the same posting safely
    — if a JE with that key already exists we return it untouched instead
    of duplicating.
    """
    if not lines or len(lines) < 2:
        raise HTTPException(status_code=400, detail="Journal entry needs at least 2 lines")

    if idempotency_key:
        prior = await db.finance_journal_entries.find_one(
            {"idempotency_key": idempotency_key, "reversed": {"$ne": True}},
            {"_id": 0},
        )
        if prior:
            return prior

    total_debit = Decimal("0")
    total_credit = Decimal("0")
    cleaned_lines = []
    for i, ln in enumerate(lines):
        if not ln.get("account_id"):
            raise HTTPException(status_code=400, detail=f"Line {i}: account_id required")
        d = _q(ln.get("debit"))
        c = _q(ln.get("credit"))
        if d > 0 and c > 0:
            raise HTTPException(status_code=400, detail=f"Line {i}: debit AND credit cannot both be > 0")
        if d == 0 and c == 0:
            raise HTTPException(status_code=400, detail=f"Line {i}: debit or credit must be > 0")
        total_debit += d
        total_credit += c
        cleaned_lines.append({
            "account_id": ln["account_id"],
            "account_code": ln.get("account_code") or "",
            "account_name": ln.get("account_name") or "",
            "debit": float(d),
            "credit": float(c),
            "memo": (ln.get("memo") or "")[:200],
        })

    if total_debit != total_credit:
        raise HTTPException(
            status_code=400,
            detail=f"Journal not balanced: debits={total_debit} vs credits={total_credit}",
        )

    # Refuse to post into a locked fiscal period (iter 279)
    if location_id:
        try:
            from routers.finance.setup import period_is_locked
            if await period_is_locked((date or "")[:10], location_id):
                raise HTTPException(
                    status_code=400,
                    detail=f"Fiscal period covering {date} is locked at this campus — reopen it before posting",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"period_is_locked check skipped: {e}")

    doc = {
        "id": f"je_{uuid.uuid4().hex[:12]}",
        "date": (date or datetime.now(timezone.utc).date().isoformat())[:10],
        "description": (description or "")[:300],
        "source": source,        # e.g. "manual", "payroll", "sale", "reset_seed"
        "reference": reference,  # e.g. payslip.id, invoice.id
        "lines": cleaned_lines,
        "total": float(total_debit),
        "location_id": location_id or "",
        # iter-je-department: cost-centre tag so this JE rolls into the right
        # Dept P&L card. Kept optional so legacy callers (payroll, sales,
        # opening balances) keep working without changes.
        "department_id": department_id or "",
        "reversed": False,
        "reverses_id": None,
        "idempotency_key": idempotency_key,
        "created_at": _now(),
        "created_by": created_by,
        "created_by_name": created_by_name,
    }
    await db.finance_journal_entries.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"[finance] JE posted {doc['id']} source={source} total={doc['total']}")
    return doc


async def reverse_journal_entry(je_id: str, *, reason: str, current_user: dict) -> dict:
    """Reversal is another JE with debits/credits swapped, linked back by
    `reverses_id`. We never edit or delete a posted JE — audit-trail intact."""
    orig = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not orig:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if orig.get("reversed"):
        raise HTTPException(status_code=400, detail="Already reversed")
    swapped = [
        {**ln, "debit": ln["credit"], "credit": ln["debit"]}
        for ln in orig["lines"]
    ]
    rev = await post_journal_entry(
        date=datetime.now(timezone.utc).date().isoformat(),
        description=f"REVERSAL of {je_id}: {reason}"[:300],
        lines=[{"account_id": ln["account_id"], "account_code": ln["account_code"],
                "account_name": ln["account_name"], "debit": ln["debit"], "credit": ln["credit"]}
               for ln in swapped],
        source="reversal",
        reference=je_id,
        location_id=orig.get("location_id"),
        created_by=current_user.get("id"),
        created_by_name=current_user.get("name"),
    )
    await db.finance_journal_entries.update_one(
        {"id": je_id},
        {"$set": {"reversed": True, "reversed_at": _now(),
                  "reversed_by_je": rev["id"], "reversed_reason": reason}},
    )
    return rev
