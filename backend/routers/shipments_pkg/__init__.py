"""Shipments package — combined router.

Split from a single 2700-line file into logical submodules while preserving
all /api/shipments/* and /api/public/shipments/* routes exactly.
"""
from fastapi import APIRouter

from . import core, items, pallets, public, airport

router = APIRouter()
router.include_router(core.router)
router.include_router(items.router)
router.include_router(pallets.router)
router.include_router(public.router)
router.include_router(airport.router)

__all__ = ["router"]
