"""Iter 334 — biweekly period label + settings hygiene.

Confirms:
  1. `_biweekly_period(start, 14)` produces a `(Www-Www)` label whenever the
     14-day window straddles two ISO weeks (the common case) so the label
     reflects the real span. A rare single-ISO-week window (e.g. very short
     day count) still yields a single `(Www)` label.
  2. `_biweekly_period(start, 7)` weekly windows stay `(Www)`.
  3. The proration factor is still 12/26 for biweekly and 12/52 for weekly.
"""
import os
import sys
from datetime import date as dt_date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


def test_biweekly_label_spans_two_weeks():
    from routers.hr import _biweekly_period
    # Sep 16 2026 is a Wednesday, ISO W38. Sep 29 is a Tuesday, ISO W40.
    # Actually let's just verify the format contains the range marker.
    label = _biweekly_period(dt_date(2026, 9, 16), 14)
    assert label.startswith("2026-09-16_2026-09-29")
    assert "(W" in label
    # Must show BOTH weeks (span the 14 days) — this is the whole point.
    assert "-W" in label, f"biweekly label should show week range, got {label}"


def test_weekly_label_single_week():
    from routers.hr import _biweekly_period
    # Monday of an ISO week to Sunday of the same ISO week stays in one week.
    # Sep 14 2026 (Monday) → Sep 20 2026 (Sunday) = entirely W38.
    label = _biweekly_period(dt_date(2026, 9, 14), 7)
    assert label == "2026-09-14_2026-09-20 (W38)"


def test_weekly_label_spanning_two_weeks_still_shows_range():
    from routers.hr import _biweekly_period
    # A 7-day window that crosses ISO week boundary → should surface both weeks
    # so the label matches the real span.
    label = _biweekly_period(dt_date(2026, 9, 16), 7)
    assert "-W" in label, f"expected week range, got {label}"


def test_proration_factors():
    from routers.hr import _proration_factor
    assert abs(_proration_factor("biweekly") - (12 / 26)) < 1e-9
    assert abs(_proration_factor("bi-weekly") - (12 / 26)) < 1e-9
    assert abs(_proration_factor("fortnightly") - (12 / 26)) < 1e-9
    assert abs(_proration_factor("weekly") - (12 / 52)) < 1e-9
    assert _proration_factor("monthly") == 1.0


def test_biweekly_amount_matches_screenshot():
    """The user's screenshot shows Christopher Ssekito on 600k UGX biweekly →
    276,923.08. Verify the proration matches that verbatim so the amount
    isn't the bug — the label was."""
    from routers.hr import _proration_factor
    monthly_base = 600_000
    biweekly = round(monthly_base * _proration_factor("biweekly"), 2)
    assert biweekly == 276923.08, f"expected 276923.08, got {biweekly}"


def test_biweekly_2_pay_amount_matches_screenshot():
    from routers.hr import _proration_factor
    # Zipporah Lubega 400,000 monthly → 184,615.38 biweekly (screenshot)
    assert round(400_000 * _proration_factor("biweekly"), 2) == 184615.38
    # Henry Lubega 75,000 monthly → 34,615.38 biweekly (screenshot)
    assert round(75_000 * _proration_factor("biweekly"), 2) == 34615.38
