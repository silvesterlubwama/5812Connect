"""Members package — routes for members, families, children, guests, badges, NFC,
photos, bulk import, and profile PDF generation.

The 1,973-line monolith was split (iter 158) into focused sub-modules:
  • core.py       — members CRUD + approve/reject (~200 LOC)
  • families.py   — families + portal/family + family-members (~280 LOC)
  • children.py   — children CRUD + education + residency + extras + photos + bulk + move-to-guest (~440 LOC)
  • guests.py     — guests CRUD + members-mirror helper + move-to-staff (~150 LOC)
  • badges.py     — badges + wallet-badge + auto-issue + list + invalidate (~370 LOC)
  • nfc.py        — NFC tag CRUD + write + signed payload + verify (~160 LOC)
  • bulk_import.py — members & children bulk-import (~190 LOC)
  • pdf.py        — member profile PDF download (~100 LOC)

Each sub-module exposes its own `router = APIRouter(prefix="/api", ...)`. This
package's `__init__.py` aggregates them into a single `router` that server.py
imports — so external import paths and URL paths are unchanged.
"""
from fastapi import APIRouter

from .core import router as _core_router
from .families import router as _families_router
from .children import router as _children_router
from .guests import router as _guests_router
from .badges import router as _badges_router
from .nfc import router as _nfc_router
from .bulk_import import router as _bulk_import_router
from .pdf import router as _pdf_router

# Aggregator — server.py does `from routers.members import router` and then
# `app.include_router(router)`, exactly like before.
router = APIRouter()
router.include_router(_core_router)
router.include_router(_families_router)
router.include_router(_children_router)
router.include_router(_guests_router)
router.include_router(_badges_router)
router.include_router(_nfc_router)
router.include_router(_bulk_import_router)
router.include_router(_pdf_router)
