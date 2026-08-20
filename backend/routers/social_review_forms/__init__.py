"""Social Work Review Forms — School Progress + Welfare Home Visit + Medical Exam.

The old 1,449-line monolith was split (iter 227) into focused sub-modules:
  • _common.py     — shared constants (VALID_KINDS, TEMPLATES_DIR, file-doc keys)
  • child_sync.py  — merge review fields into child profile + compute risk (~290 LOC)
  • timeline.py    — append a rich note to the case timeline (~95 LOC)
  • crud.py        — list/get/create/update/delete review endpoints (~120 LOC)
  • templates.py   — printable blank template PDF endpoint (~50 LOC)
  • ocr.py         — Gemini system prompts + `_ocr_review_form` + `_ocr_background` (~330 LOC)
  • scan_upload.py — POST children/{id}/upload-scan with background OCR (~200 LOC)
  • photos.py      — POST/DELETE {review_id}/photos (~100 LOC)
  • compliance.py  — /compliance/due + /compliance/completeness dashboards (~180 LOC)

Each sub-module exposes its own `APIRouter(prefix="/api/social-work/reviews")`.
This package's `__init__.py` aggregates them so `server.py`'s existing
`from routers.social_review_forms import router` keeps working unchanged.
"""
from fastapi import APIRouter

from .crud import router as _crud_router
from .templates import router as _templates_router
from .scan_upload import router as _scan_upload_router
from .photos import router as _photos_router
from .compliance import router as _compliance_router

# Aggregator — server.py does `from routers.social_review_forms import router` and
# then `app.include_router(router)`, exactly like before.
router = APIRouter()
# Order matters ONLY for routes that share a segment count — /compliance/*
# and /templates/* are two-segment paths so they never collide with the
# one-segment /{review_id} in crud. Kept in the order that reads most
# naturally: CRUD first, then narrow-purpose helpers.
router.include_router(_crud_router)
router.include_router(_templates_router)
router.include_router(_scan_upload_router)
router.include_router(_photos_router)
router.include_router(_compliance_router)
