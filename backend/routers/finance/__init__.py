"""Finance package — single source of truth for the money ledger.

Structure:
  • _common.py           — journal-entry post/reverse helpers + seed COA + invariants
  • chart_of_accounts.py — /api/finance/chart-of-accounts CRUD
  • journal.py           — /api/finance/journal read + manual post + reverse
  • transactions.py      — /api/finance/transactions/{expense,income,recent}
  • reports.py           — /api/finance/reports/{trial-balance,pnl,balance-sheet,cashflow}
  • postings.py          — internal-only helpers called by HR/Sales
  • admin.py             — /api/finance/admin/{status,reset}

Server includes the aggregator router below; every HTTP surface for the
finance module funnels through the ONE `post_journal_entry` invariant.
"""
from fastapi import APIRouter

from .chart_of_accounts import router as _coa_router
from .journal import router as _journal_router
from .transactions import router as _tx_router
from .transfers import router as _transfers_router
from .receipts import router as _receipts_router
from .reports import router as _reports_router
from .admin import router as _admin_router
from .setup import router as _setup_router

router = APIRouter()
router.include_router(_coa_router)
router.include_router(_journal_router)
router.include_router(_tx_router)
router.include_router(_transfers_router)
router.include_router(_receipts_router)
router.include_router(_reports_router)
router.include_router(_admin_router)
router.include_router(_setup_router)
