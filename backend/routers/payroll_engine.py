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
      bands?: [{up_to: float|None, rate: float}],  # progressive (PAYE)
      account_code?: str,            # expense account (employer side)
      liability_account_code?: str,  # what is owed to the authority
      notes?: str,
    }

Per-employee override (hr_salaries.statutory_overrides):
    { "<key>": {enabled: bool, amount: float, is_percentage: bool} }
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


def _resolve(line: dict, override: Optional[dict]) -> Optional[dict]:
    """Apply an employee's override on top of the campus line. Returns None when
    the employee is opted out."""
    merged = dict(line)
    if override:
        if override.get("enabled") is False:
            return None
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
        return _from_bands(gross, bands)
    amount = float(line.get("amount") or 0)
    if line.get("is_percentage"):
        return round(gross * amount / 100.0, 2), f"{amount:g}% of {gross:,.0f}"
    return round(amount, 2), "fixed"


def apply_statutory_lines(compliance_lines: list, salary: dict, gross: float) -> dict:
    """Turn the campus compliance lines into payslip line items for one person.

    Returns
    -------
    {
      items: [...],                # payslip line_items to append
      employee_deductions: float,  # withheld from pay
      pay_additions: float,        # employer contribution paid WITH the salary
      employer_cost: float,        # employer contribution NOT paid to staff
      withheld_liability: float,   # employee deductions owed to an authority
    }
    """
    overrides = (salary or {}).get("statutory_overrides") or {}
    out = {"items": [], "employee_deductions": 0.0, "pay_additions": 0.0,
           "employer_cost": 0.0, "withheld_liability": 0.0}
    for raw in (compliance_lines or []):
        key = line_key(raw)
        line = _resolve(raw, overrides.get(key))
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
        if ltype == EMPLOYER_TYPE:
            mode = (line.get("mode") or "employer_cost").lower()
            item.update({"type": EMPLOYER_TYPE, "scope": "employer", "mode": mode,
                         "account_code": line.get("account_code") or DEFAULT_EMPLOYER_EXPENSE_CODE})
            if mode == "add_to_pay":
                out["pay_additions"] += amount
            else:
                out["employer_cost"] += amount
        elif ltype == "deduction":
            item.update({"type": "deduction", "scope": "employee"})
            out["employee_deductions"] += amount
            out["withheld_liability"] += amount
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
