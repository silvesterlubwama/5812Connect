"""Statutory payroll lines — the one place that decides what comes off a payslip.

Campus-wide lines live on `hr_settings.compliance_lines` (HR → Settings →
Compliance). Every payslip in that campus gets them automatically; an employee
can override the rate or switch a line off through
`hr_salaries.statutory_overrides`, and their own salary `line_items` still
apply on top.

Line shape (hr_settings.compliance_lines):
    {
      key?: str,                     # stable id; derived from name when absent
      name: str,
      type: "deduction" | "allowance" | "employer_contribution",
      mode: "add_to_pay" | "employer_cost",   # employer_contribution only
      is_percentage: bool,
      amount: float,                 # rate (%) or fixed amount
      applies_to?: "everyone" | "opt_in",   # default "everyone"
      active_months?: [int],         # 1-12; empty/absent = every month (LST = Jul-Oct)
      band_mode?: "progressive" | "bracket_amount",   # default "progressive"
      bands?: [{up_to: float|None, rate: float, amount: float}],
      account_code?: str,            # expense account (employer side)
      liability_account_code?: str,  # what is owed to the authority
      notes?: str,
    }

Per-employee override (hr_salaries.statutory_overrides):
    { "<key>": {enabled: bool, amount: float, is_percentage: bool,
                employer_pays: bool,        # employer covers it for the first cycle
                employer_share: float,      # % the employer covers, default 100
                employer_pays_cycle: str}}  # stamped once used, locks it to one cycle
"""
from typing import Optional
import re

from deps import db

# Credit side for anything withheld from staff or owed by the employer.
DEFAULT_LIABILITY_CODE = "2200"      # Taxes Payable (PAYE / NSSF)
# Debit side for an employer contribution when the line doesn't name one.
DEFAULT_EMPLOYER_EXPENSE_CODE = "5002"   # Wages & Salaries
# Debit side for staff earnings.
WAGE_EXPENSE_CODES = ("5002", "5000")

EMPLOYER_TYPE = "employer_contribution"


def line_key(line: dict) -> str:
    """Stable id for a compliance line so per-employee overrides survive renames
    of everything except the name itself."""
    if line.get("key"):
        return str(line["key"])
    return re.sub(r"[^a-z0-9]+", "_", (line.get("name") or "").strip().lower()).strip("_")


def _from_bands(gross: float, bands: list) -> tuple:
    """Progressive tax: each band's rate applies only to the slice inside it."""
    total = 0.0
    lower = 0.0
    parts = []
    for b in bands:
        up_to = b.get("up_to")
        cap = float(up_to) if up_to not in (None, "", 0) else None
        rate = float(b.get("rate") or 0)
        top = gross if cap is None else min(gross, cap)
        if top > lower:
            slice_amt = top - lower
            tax = slice_amt * rate / 100.0
            total += tax
            if rate:
                parts.append(f"{rate:g}% of {slice_amt:,.0f}")
            lower = top
        if cap is not None and gross <= cap:
            break
        if cap is not None:
            lower = max(lower, cap)
    return round(total, 2), " + ".join(parts)


def _from_bracket(gross: float, bands: list) -> tuple:
    """Fixed-amount brackets: earn up to a band's limit and you pay that band's
    flat amount. Unlike PAYE this is a lookup — exactly one band ever applies.
    A band with a blank limit is the "and above" catch-all; without one, pay
    above the top bracket attracts nothing."""
    ordered = sorted(bands, key=lambda b: (b.get("up_to") in (None, ""), float(b.get("up_to") or 0)))
    for b in ordered:
        cap = b.get("up_to")
        amount = round(float(b.get("amount") or 0), 2)
        if cap in (None, ""):
            return amount, "top bracket"
        if gross <= float(cap):
            return amount, f"bracket up to {float(cap):,.0f}"
    return 0.0, "above every bracket"


def months_of(line: dict) -> list:
    """Months a line is collected in. Empty means every month. Payroll is run
    per calendar month, so a month list is as fine-grained as a date range can
    ever be here."""
    raw = line.get("active_months") or []
    return sorted({int(m) for m in raw if str(m).strip().isdigit() and 1 <= int(m) <= 12})


def in_collection_window(line: dict, period: Optional[str]) -> bool:
    months = months_of(line)
    if not months or not period:
        return True
    try:
        return int(str(period)[5:7]) in months
    except (ValueError, IndexError):
        return True


def _window_start(months: list) -> Optional[int]:
    """First month of the collection run. Found by rotating to the month that
    follows the biggest gap, so a window that wraps the year end (Nov-Feb)
    reports November rather than January."""
    if not months:
        return None
    best_gap, start = -1, months[0]
    for i, m in enumerate(months):
        gap = (m - months[i - 1]) % 12
        if gap > best_gap:
            best_gap, start = gap, m
    return start


def cycle_label(line: dict, period: Optional[str]) -> str:
    """Identifies one collection run, so "the employer covers the first cycle"
    means every instalment in that run and nothing after it. A window that wraps
    the year end (e.g. Nov-Feb) is labelled by the year it started in."""
    if not period:
        return ""
    year, month = int(str(period)[:4]), int(str(period)[5:7])
    start = _window_start(months_of(line))
    if start and month < start:
        # Jan-Feb 2027 belongs to the cycle that opened in Nov 2026.
        year -= 1
    return f"{year}:{line_key(line)}"


def _resolve(line: dict, override: Optional[dict]) -> Optional[dict]:
    """Apply an employee's override on top of the campus line. Returns None when
    the line doesn't apply to this person — either they're opted out, or the
    line is opt-in and nobody switched it on for them."""
    opt_in = (line.get("applies_to") or "everyone") == "opt_in"
    if override:
        if override.get("enabled") is False:
            return None
        if opt_in and override.get("enabled") is not True:
            return None
    elif opt_in:
        return None
    merged = dict(line)
    if override:
        if override.get("amount") is not None:
            merged["amount"] = override["amount"]
            merged["bands"] = None          # a flat override replaces the bands
        if override.get("is_percentage") is not None:
            merged["is_percentage"] = override["is_percentage"]
        merged["overridden"] = True
    return merged


def _calc(line: dict, gross: float) -> tuple:
    bands = line.get("bands")
    if bands:
        if (line.get("band_mode") or "progressive") == "bracket_amount":
            return _from_bracket(gross, bands)
        return _from_bands(gross, bands)
    amount = float(line.get("amount") or 0)
    if line.get("is_percentage"):
        return round(gross * amount / 100.0, 2), f"{amount:g}% of {gross:,.0f}"
    return round(amount, 2), "fixed"


def _employer_cover(line: dict, override: Optional[dict], period: Optional[str]) -> float:
    """How much of a deduction the employer picks up for this person, as a
    percentage. The gesture only covers their FIRST collection cycle: once a
    payslip has used it the cycle is stamped on the override, and anything in a
    later cycle goes back to the employee."""
    ov = override or {}
    if not ov.get("employer_pays"):
        return 0.0
    stamped = ov.get("employer_pays_cycle")
    if stamped and stamped != cycle_label(line, period):
        return 0.0
    share = ov.get("employer_share")
    share = 100.0 if share is None else float(share)
    return max(0.0, min(100.0, share))


def apply_statutory_lines(compliance_lines: list, salary: dict, gross: float,
                          period: Optional[str] = None) -> dict:
    """Turn the campus compliance lines into payslip line items for one person.

    `period` is the payslip's YYYY-MM. It decides whether a line that only runs
    in certain months (LST: Jul-Oct) applies at all, and which collection cycle
    an employer-covered first instalment belongs to. Somebody who joins outside
    the window simply misses that collection.

    Returns
    -------
    {
      items: [...],                # payslip line_items to append
      employee_deductions: float,  # withheld from pay
      pay_additions: float,        # employer contribution paid WITH the salary
      employer_cost: float,        # employer contribution NOT paid to staff
      withheld_liability: float,   # employee deductions owed to an authority
      cycle_stamps: {key: cycle},  # first-cycle locks the caller should persist
    }
    """
    overrides = (salary or {}).get("statutory_overrides") or {}
    out = {"items": [], "employee_deductions": 0.0, "pay_additions": 0.0,
           "employer_cost": 0.0, "withheld_liability": 0.0, "cycle_stamps": {}}
    for raw in (compliance_lines or []):
        key = line_key(raw)
        if not in_collection_window(raw, period):
            continue
        override = overrides.get(key)
        line = _resolve(raw, override)
        if line is None:
            continue
        amount, detail = _calc(line, gross)
        if amount <= 0:
            continue
        ltype = (line.get("type") or "deduction").lower()
        item = {
            "key": key,
            "name": line.get("name") or key,
            "amount": line.get("amount") or 0,
            "is_percentage": bool(line.get("is_percentage")),
            "calculated_amount": amount,
            "source": "statutory",
            "auto_generated": True,
            "details": detail + (" · per-employee rate" if line.get("overridden") else ""),
            "liability_account_code": line.get("liability_account_code") or DEFAULT_LIABILITY_CODE,
        }
        if line.get("bands"):
            item["bands"] = line["bands"]
            item["band_mode"] = line.get("band_mode") or "progressive"
        if ltype == EMPLOYER_TYPE:
            mode = (line.get("mode") or "employer_cost").lower()
            item.update({"type": EMPLOYER_TYPE, "scope": "employer", "mode": mode,
                         "account_code": line.get("account_code") or DEFAULT_EMPLOYER_EXPENSE_CODE})
            if mode == "add_to_pay":
                out["pay_additions"] += amount
            else:
                out["employer_cost"] += amount
        elif ltype == "deduction":
            covered = _employer_cover(raw, override, period)
            employer_part = round(amount * covered / 100.0, 2) if covered else 0.0
            employee_part = round(amount - employer_part, 2)
            if employer_part:
                # The authority is still owed the full amount — the employer just
                # pays this slice instead of the employee, so it lands on the same
                # liability account as an employer cost. It is NOT added to gross,
                # so it stays outside PAYE.
                out["items"].append({**item, "type": EMPLOYER_TYPE, "scope": "employer",
                                     "mode": "employer_cost", "calculated_amount": employer_part,
                                     "covered_for_employee": True,
                                     "account_code": raw.get("account_code") or DEFAULT_EMPLOYER_EXPENSE_CODE,
                                     "details": f"{detail} · employer covers {covered:g}% (first cycle)"})
                out["employer_cost"] += employer_part
                out["withheld_liability"] += employer_part
                stamp = cycle_label(raw, period)
                if stamp and not (override or {}).get("employer_pays_cycle"):
                    out["cycle_stamps"][key] = stamp
            if employee_part <= 0:
                continue
            item.update({"type": "deduction", "scope": "employee", "calculated_amount": employee_part})
            if employer_part:
                item["details"] = f"{detail} · employee pays {100 - covered:g}%"
            out["employee_deductions"] += employee_part
            out["withheld_liability"] += employee_part
        else:
            item.update({"type": "allowance", "scope": "employee"})
            out["pay_additions"] += amount
        out["items"].append(item)
    for k in ("employee_deductions", "pay_additions", "employer_cost", "withheld_liability"):
        out[k] = round(out[k], 2)
    return out


async def compliance_lines_for(location_id: str) -> list:
    """Campus compliance lines, falling back to the parent campus so a
    sub-location (Shelter, Farm) inherits the statutory setup of its campus
    instead of silently running payroll with no deductions."""
    seen = set()
    loc = (location_id or "").strip()
    while loc and loc not in seen:
        seen.add(loc)
        s = await db.hr_settings.find_one({"location_id": loc}, {"_id": 0, "compliance_lines": 1})
        if s and s.get("compliance_lines"):
            return s["compliance_lines"]
        parent = await db.locations.find_one({"id": loc}, {"_id": 0, "parent_id": 1})
        loc = (parent or {}).get("parent_id") or ""
    return []


def employer_totals(line_items: list) -> dict:
    """Re-derive the employer figures from a payslip's stored line items — used
    when HR edits a payslip by hand."""
    cost = sum(float(li.get("calculated_amount") or li.get("amount") or 0)
               for li in (line_items or [])
               if li.get("type") == EMPLOYER_TYPE and (li.get("mode") or "employer_cost") == "employer_cost")
    withheld = sum(float(li.get("calculated_amount") or li.get("amount") or 0)
                   for li in (line_items or [])
                   if li.get("type") == "deduction" and li.get("source") == "statutory")
    return {"employer_contributions": round(cost, 2), "statutory_withheld": round(withheld, 2)}
