"""Public holidays — US federal + Ugandan public holidays.

Server-computed so the frontend can just ask "give me holidays for these years"
and render them on the calendar without shipping a static JSON that goes stale.

Rules:
- US federal: fixed dates OR nth-weekday of month (e.g. 3rd Monday of January).
- Uganda: fixed dates (most are Christian/Muslim/independence-related fixed).
  Muslim holidays (Eid al-Fitr, Eid al-Adha) shift each year; we ship a
  pre-computed table for 2024–2028 and gracefully skip unknown years.

Anyone can read this — it's public reference data, not tenant data.
"""
from fastapi import APIRouter, Query
from datetime import date

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth (1-based) `weekday` of the given month/year. weekday: Mon=0.
    n=-1 means last."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return date(year, month, 1 + offset + (n - 1) * 7)
    # last
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    from datetime import timedelta
    d = nxt - timedelta(days=1)
    while d.weekday() != weekday:
        d = d - timedelta(days=1)
    return d


def _us_holidays(year: int) -> list:
    """US federal holidays."""
    # Monday = 0, Thursday = 3, Sunday = 6 (Python's weekday())
    holidays = [
        {"date": date(year, 1, 1), "name": "New Year's Day"},
        {"date": _nth_weekday(year, 1, 0, 3), "name": "Martin Luther King Jr. Day"},
        {"date": _nth_weekday(year, 2, 0, 3), "name": "Presidents' Day"},
        {"date": _nth_weekday(year, 5, 0, -1), "name": "Memorial Day"},
        {"date": date(year, 6, 19), "name": "Juneteenth"},
        {"date": date(year, 7, 4), "name": "Independence Day"},
        {"date": _nth_weekday(year, 9, 0, 1), "name": "Labor Day"},
        {"date": _nth_weekday(year, 10, 0, 2), "name": "Columbus Day"},
        {"date": date(year, 11, 11), "name": "Veterans Day"},
        {"date": _nth_weekday(year, 11, 3, 4), "name": "Thanksgiving Day"},
        {"date": date(year, 12, 25), "name": "Christmas Day"},
    ]
    return [
        {"date": h["date"].isoformat(), "name": h["name"], "country": "US"}
        for h in holidays
    ]


# Muslim holidays shift each year — Uganda observes Eid al-Fitr (2 days) and Eid al-Adha (1 day).
# Pre-computed for 2024–2028 using the Umm al-Qura calendar; edit here as new years are set.
_UG_MUSLIM = {
    2024: {"eid_fitr": ("2024-04-10", "2024-04-11"), "eid_adha": "2024-06-17"},
    2025: {"eid_fitr": ("2025-03-31", "2025-04-01"), "eid_adha": "2025-06-07"},
    2026: {"eid_fitr": ("2026-03-20", "2026-03-21"), "eid_adha": "2026-05-27"},
    2027: {"eid_fitr": ("2027-03-10", "2027-03-11"), "eid_adha": "2027-05-17"},
    2028: {"eid_fitr": ("2028-02-27", "2028-02-28"), "eid_adha": "2028-05-05"},
}


def _ug_holidays(year: int) -> list:
    """Uganda public holidays (fixed + shifting)."""
    fixed = [
        {"date": date(year, 1, 1), "name": "New Year's Day"},
        {"date": date(year, 1, 26), "name": "NRM Liberation Day"},
        {"date": date(year, 3, 8), "name": "International Women's Day"},
        {"date": date(year, 5, 1), "name": "Labour Day"},
        {"date": date(year, 6, 3), "name": "Martyrs' Day"},
        {"date": date(year, 6, 9), "name": "National Heroes' Day"},
        {"date": date(year, 10, 9), "name": "Independence Day"},
        {"date": date(year, 12, 25), "name": "Christmas Day"},
        {"date": date(year, 12, 26), "name": "Boxing Day"},
    ]
    # Easter — Anonymous Gregorian computus
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    from datetime import timedelta
    fixed.append({"date": easter - timedelta(days=2), "name": "Good Friday"})
    fixed.append({"date": easter + timedelta(days=1), "name": "Easter Monday"})
    out = [{"date": h["date"].isoformat(), "name": h["name"], "country": "UG"} for h in fixed]
    # Muslim
    if year in _UG_MUSLIM:
        d1, d2 = _UG_MUSLIM[year]["eid_fitr"]
        out.append({"date": d1, "name": "Eid al-Fitr", "country": "UG"})
        out.append({"date": d2, "name": "Eid al-Fitr (Day 2)", "country": "UG"})
        out.append({"date": _UG_MUSLIM[year]["eid_adha"], "name": "Eid al-Adha", "country": "UG"})
    return sorted(out, key=lambda x: x["date"])


@router.get("")
async def list_holidays(
    year: int = Query(..., ge=2020, le=2035),
    country: str = Query("all", regex="^(US|UG|all)$"),
    year_to: int = Query(0, ge=0, le=2035),
):
    """Return holidays for a year (or year..year_to range)."""
    start = year
    end = year_to if year_to and year_to >= year else year
    all_h = []
    for y in range(start, end + 1):
        if country in ("US", "all"):
            all_h.extend(_us_holidays(y))
        if country in ("UG", "all"):
            all_h.extend(_ug_holidays(y))
    return sorted(all_h, key=lambda x: (x["date"], x["country"]))
