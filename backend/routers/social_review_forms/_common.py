"""Shared constants for the social_review_forms package.

Duplicating a small handful of constants here keeps every submodule import-light
(no circular routers.members.children pull) and lets each file be read in
isolation without hopping between modules to look up a magic string.
"""
from pathlib import Path

# The three kinds of paper forms field staff currently fill by hand. Keep in
# sync with the templates that live in /app/backend/templates/social_reviews/.
VALID_KINDS = {"school_progress", "welfare_visit", "medical_exam"}

# HTML templates for the printable blank PDFs. Edit the .html files in-place
# and they'll be picked up on the next request (no restart required).
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "social_reviews"

# Canonical child file-doc types (mirrors routers/members/children.py). Kept
# here to avoid a circular import when compliance endpoints roll up per-child
# checklist completion.
FILE_DOC_TYPE_KEYS = [
    "ovcmis_form_008", "sponsorship_assessment", "lc1_introduction_letter",
    "school_report", "guardian_national_id", "family_consent_letter",
    "medical_assessment", "exit_form", "sponsor_letter_in", "sponsor_letter_out",
]
