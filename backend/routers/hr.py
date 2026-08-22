"""HR Module: contracts, salaries, payslips, document requests, per-campus settings"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_staff, require_manager, require_director, require_admin, _audit, logger, get_campus_filter, get_role_level, require_hr_view
from datetime import datetime, timezone, date as dt_date, timedelta as td
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/hr", tags=["hr"])


# Legacy local helper kept as an alias to the centralised `has_module_access(user, 'hr')` —
# all HR endpoints now go through `require_hr` which delegates to the standard module guard.
def _require_hr_access(user: dict):
    from deps import has_module_access
    return has_module_access(user, "hr")


# `require_hr` is the dependency historically used by every endpoint in this file —
# it now simply re-exports the shared `require_hr_view` (Director+ implicit, HR role
# implicit, all others by explicit admin-granted TTL access).
require_hr = require_hr_view


# ============================================================
#  HR SCOPE HELPER (iter214)
#  Admin/system_admin: full access.
#  Director/HR/manager: filter by `location_id in current_user.location_ids`.
#  Regular staff: filter to own `staff_id` only.
#  Returns a Mongo query dict to be merged into base query.
# ============================================================
def _hr_scope(current_user: dict, user_field: str = "staff_id", loc_field: str = "location_id") -> dict:
    role = (current_user.get("role") or "").lower()
    if role in {"admin", "system_admin"}:
        return {}
    if role in {"hr", "director", "executive director", "regional director", "manager"}:
        loc_ids = current_user.get("location_ids") or []
        if not loc_ids and current_user.get("active_campus_id"):
            loc_ids = [current_user["active_campus_id"]]
        if loc_ids:
            return {loc_field: {"$in": loc_ids}}
        return {loc_field: "__NO_LOCATION__"}
    return {user_field: current_user["id"]}


def _is_hr_or_above(current_user: dict) -> bool:
    return (current_user.get("role") or "").lower() in {
        "admin", "system_admin", "hr", "director", "executive director", "regional director", "manager"
    }


# ========== HR SETTINGS PER CAMPUS ==========

@router.get("/settings/{location_id}")
async def get_hr_settings(location_id: str, current_user: dict = Depends(require_hr)):
    doc = await db.hr_settings.find_one({"location_id": location_id}, {"_id": 0})
    return doc or {"location_id": location_id, "hr_enabled": False, "pay_frequency": "monthly", "currency": "UGX", "country": "", "tax_rules": []}


@router.put("/settings/{location_id}")
async def update_hr_settings(location_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"hr_enabled", "pay_frequency", "currency", "country", "tax_rules", "benefits",
               "deduction_types", "pay_day", "next_pay_date", "compliance_lines",
               "aggregated_payroll_expense", "payslip_message"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_settings.update_one({"location_id": location_id}, {"$set": update}, upsert=True)
    return await db.hr_settings.find_one({"location_id": location_id}, {"_id": 0})


# ========== COMPLIANCE OPTIONS (per-country common deductions/additions) ==========

# Researched defaults per country. Admins pick from dropdown then can edit rates.
COMPLIANCE_OPTIONS = {
    "Uganda": [
        {"name": "PAYE (Pay-As-You-Earn)", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Progressive: 0% up to UGX 235k, 10-40% above. Set band per employee or use simplified rate."},
        {"name": "NSSF Employee", "type": "deduction", "is_percentage": True, "amount": 5,
         "notes": "5% employee contribution to National Social Security Fund."},
        {"name": "NSSF Employer", "type": "deduction", "is_percentage": True, "amount": 10,
         "notes": "10% employer contribution (paid by org, not deducted from staff)."},
        {"name": "LST (Local Service Tax)", "type": "deduction", "is_percentage": False, "amount": 5000,
         "notes": "Local Service Tax — annual, varies by income band UGX 5k-100k."},
    ],
    "Kenya": [
        {"name": "PAYE", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Graduated 10-35% per KRA bands."},
        {"name": "NHIF", "type": "deduction", "is_percentage": False, "amount": 1700,
         "notes": "Graduated; ~KES 1,700 for KES 100k earner."},
        {"name": "NSSF", "type": "deduction", "is_percentage": True, "amount": 6,
         "notes": "6% of pensionable pay (capped)."},
        {"name": "Affordable Housing Levy", "type": "deduction", "is_percentage": True, "amount": 1.5,
         "notes": "1.5% of gross pay (since 2024)."},
    ],
    "USA": [
        {"name": "Federal Income Tax Withholding", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Per W-4 + tax tables. Set per employee."},
        {"name": "Social Security (FICA)", "type": "deduction", "is_percentage": True, "amount": 6.2,
         "notes": "6.2% up to wage base limit."},
        {"name": "Medicare (FICA)", "type": "deduction", "is_percentage": True, "amount": 1.45,
         "notes": "1.45% with no cap; +0.9% over $200k."},
        {"name": "State Income Tax", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Varies by state (0% in TX, FL, etc.)."},
    ],
    "Haiti": [
        {"name": "Income Tax (Impot sur le Revenu)", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Progressive bands."},
        {"name": "ONA (Office National d'Assurance Vieillesse)", "type": "deduction", "is_percentage": True, "amount": 3,
         "notes": "3% employee contribution to pension."},
        {"name": "OFATMA (Health insurance)", "type": "deduction", "is_percentage": True, "amount": 1,
         "notes": "1% workers' health & maternity insurance."},
    ],
    "Thailand": [
        {"name": "Personal Income Tax (PIT)", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Progressive 0-35%."},
        {"name": "Social Security Fund", "type": "deduction", "is_percentage": True, "amount": 5,
         "notes": "5% of wage, capped at THB 750/month."},
        {"name": "Provident Fund", "type": "deduction", "is_percentage": True, "amount": 0,
         "notes": "Optional 2-15% employee contribution."},
    ],
}


@router.get("/compliance-options/{country}")
async def get_compliance_options(country: str, current_user: dict = Depends(require_hr)):
    """Return common compliance deductions / additions for a given country.
    Admins can pick from this list when configuring a campus's payroll compliance lines."""
    options = COMPLIANCE_OPTIONS.get(country, [])
    return {"country": country, "options": options}


@router.get("/compliance-options")
async def list_compliance_country_options(current_user: dict = Depends(require_hr)):
    """List all countries that have seeded compliance options."""
    return {"countries": list(COMPLIANCE_OPTIONS.keys())}


# ========== SALARY MANAGEMENT ==========

@router.get("/salaries")
async def list_salaries(location_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    return await db.hr_salaries.find(query, {"_id": 0}).sort("staff_name", 1).to_list(500)


@router.post("/salaries")
async def create_salary(data: dict, current_user: dict = Depends(require_director)):
    staff_id = data.get("staff_id", "")
    if not staff_id:
        raise HTTPException(status_code=400, detail="staff_id required")
    staff = await db.users.find_one({"id": staff_id}, {"_id": 0, "name": 1, "role": 1, "location_id": 1, "department": 1})
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    doc = {
        "id": f"sal_{uuid.uuid4().hex[:8]}",
        "staff_id": staff_id,
        "staff_name": staff.get("name", ""),
        "staff_role": staff.get("role", ""),
        "department": staff.get("department", ""),
        "location_id": data.get("location_id") or staff.get("location_id") or current_user.get("active_campus_id", ""),
        "base_salary": float(data.get("base_salary", 0)),
        "currency": data.get("currency", "UGX"),
        "pay_frequency": data.get("pay_frequency", "monthly"),
        "effective_date": data.get("effective_date", datetime.now(timezone.utc).isoformat()[:10]),
        "line_items": data.get("line_items", []),  # [{name, type (allowance/deduction), amount, is_percentage}]
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.hr_salaries.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "salary", doc["id"], {"staff": staff.get("name")})
    return doc


@router.put("/salaries/{salary_id}")
async def update_salary(salary_id: str, data: dict, current_user: dict = Depends(require_director)):
    existing = await db.hr_salaries.find_one({"id": salary_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Salary not found")
    allowed = {"base_salary", "currency", "pay_frequency", "effective_date", "line_items", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "base_salary" in update:
        update["base_salary"] = float(update["base_salary"])
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Capture change diff for the audit timeline
    changes = {}
    for k, v in update.items():
        if k in {"updated_at"}:
            continue
        if existing.get(k) != v:
            changes[k] = {"from": existing.get(k), "to": v}
    await db.hr_salaries.update_one({"id": salary_id}, {"$set": update})
    if changes:
        await db.hr_salary_history.insert_one({
            "id": f"slh_{uuid.uuid4().hex[:8]}",
            "salary_id": salary_id,
            "staff_id": existing.get("staff_id"),
            "staff_name": existing.get("staff_name"),
            "location_id": existing.get("location_id"),
            "changes": changes,
            "changed_at": update["updated_at"],
            "changed_by": current_user["id"],
            "changed_by_name": current_user.get("name", ""),
            "changed_by_role": current_user.get("role", ""),
            "reason": (data.get("reason") or "").strip()[:500],
        })
        await _audit(current_user["id"], "update", "salary", salary_id, {"changes": changes, "staff": existing.get("staff_name")})
    return await db.hr_salaries.find_one({"id": salary_id}, {"_id": 0})


@router.get("/salaries/history")
async def list_salary_history(staff_id: Optional[str] = None, salary_id: Optional[str] = None, limit: int = 200, current_user: dict = Depends(require_hr)):
    """Salary-change audit timeline. Filter by staff_id or salary_id."""
    query = {}
    if staff_id:
        query["staff_id"] = staff_id
    if salary_id:
        query["salary_id"] = salary_id
    if not query:
        # Default: scope to current campus
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    return await db.hr_salary_history.find(query, {"_id": 0}).sort("changed_at", -1).to_list(min(limit, 1000))


@router.delete("/salaries/{salary_id}")
async def delete_salary(salary_id: str, current_user: dict = Depends(require_director)):
    await db.hr_salaries.delete_one({"id": salary_id})
    return {"message": "Salary record deleted"}


# ========== PAYSLIPS ==========

@router.get("/payslips")
async def list_payslips(staff_id: Optional[str] = None, period: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List payslips scoped by role (iter214):
    - Regular staff → only their own payslips
    - Director/HR/Manager → payslips at their assigned location_ids
    - Admin → all"""
    query = {}
    if staff_id:
        query["staff_id"] = staff_id
    if period:
        query["period"] = period
    # Apply role scope
    scope = _hr_scope(current_user, user_field="staff_id", loc_field="location_id")
    query.update(scope)
    # Retain campus filter for HR/director/manager only — admins see truly all
    # (fixes iter214 minor note: admin was previously scoped to active_campus).
    role = (current_user.get("role") or "").lower()
    if role in {"hr", "director", "executive director", "regional director", "manager"}:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    return await db.hr_payslips.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/payslips/generate")
async def generate_payslips(data: dict, current_user: dict = Depends(require_director)):
    """Generate payslips for a pay period. Body:
    { period: 'YYYY-MM',
      location_id?: str,
      days_worked_override?: {staff_id: days},
      pto_days_override?: {staff_id: days},
      use_timesheets?: bool  (default true — pulls approved timesheets for the period)
    }"""
    period = data.get("period") or datetime.now(timezone.utc).strftime("%Y-%m")
    location_id = data.get("location_id")
    days_worked = dict(data.get("days_worked_override") or {})
    pto_days = dict(data.get("pto_days_override") or {})
    use_timesheets = data.get("use_timesheets", True)
    # Merge in approved timesheets — explicit overrides win
    if use_timesheets:
        async for ts in db.hr_timesheets.find({"period": period, "status": "approved"}, {"_id": 0}):
            days_worked.setdefault(ts["staff_id"], ts.get("days_worked"))
            pto_days.setdefault(ts["staff_id"], ts.get("pto_days", 0))
    return await _generate_payslips_for(period, location_id, current_user, days_worked, pto_days)


@router.post("/payslips/manual")
async def manual_payslip(data: dict, current_user: dict = Depends(require_director)):
    """One-off payslip — HR types the amount + deductions directly, no recurring
    salary record needed. Use for casual workers, end-of-year bonuses, hardship
    payments, severance, etc.

    Body: {
        staff_id: str,             # users.id (or members.id) of the recipient
        period: 'YYYY-MM',
        gross_salary: number,      # base amount the payslip pays out
        currency?: str (default UGX),
        allowances?: [{ name, amount }],
        deductions?: [{ name, amount }],
        notes?: str,
    }
    """
    staff_id = (data.get("staff_id") or "").strip()
    if not staff_id:
        raise HTTPException(status_code=400, detail="staff_id required")
    period = (data.get("period") or "").strip()
    if not period:
        raise HTTPException(status_code=400, detail="period required (YYYY-MM)")
    try:
        gross = float(data.get("gross_salary") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="gross_salary must be a number")
    if gross <= 0:
        raise HTTPException(status_code=400, detail="gross_salary must be > 0")

    # Resolve staff record (users first, then members fallback)
    staff = await db.users.find_one({"id": staff_id}, {"_id": 0, "id": 1, "name": 1, "department": 1, "location_id": 1, "email": 1})
    if not staff:
        staff = await db.members.find_one({"id": staff_id}, {"_id": 0, "id": 1, "name": 1, "department": 1, "location_id": 1, "email": 1})
    if not staff:
        raise HTTPException(status_code=404, detail=f"Staff {staff_id} not found")

    # Sanitise line items
    line_items = []
    total_allowances = 0.0
    for li in (data.get("allowances") or []):
        try:
            amt = float(li.get("amount") or 0)
        except Exception:
            continue
        if amt <= 0:
            continue
        line_items.append({
            "name": (li.get("name") or "Allowance")[:60],
            "type": "allowance",
            "amount": amt,
            "calculated_amount": amt,
            "is_percentage": False,
        })
        total_allowances += amt
    total_deductions = 0.0
    for li in (data.get("deductions") or []):
        try:
            amt = float(li.get("amount") or 0)
        except Exception:
            continue
        if amt <= 0:
            continue
        line_items.append({
            "name": (li.get("name") or "Deduction")[:60],
            "type": "deduction",
            "amount": amt,
            "calculated_amount": amt,
            "is_percentage": False,
        })
        total_deductions += amt

    net = gross + total_allowances - total_deductions
    payslip = {
        "id": f"ps_{uuid.uuid4().hex[:8]}",
        "salary_id": None,             # null = manual one-off, not tied to a salary record
        "is_manual": True,
        "staff_id": staff_id,
        "staff_name": staff.get("name", ""),
        "department": staff.get("department", ""),
        "location_id": staff.get("location_id") or current_user.get("active_campus_id"),
        "period": period,
        "gross_salary": gross,
        "allowances": total_allowances,
        "deductions": total_deductions,
        "net_salary": net,
        "currency": (data.get("currency") or "UGX")[:8],
        "line_items": line_items,
        "notes": (data.get("notes") or "")[:500],
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.hr_payslips.insert_one(payslip)
    payslip.pop("_id", None)
    await _audit(
        current_user["id"], "create", "manual_payslip", payslip["id"],
        {"staff_id": staff_id, "period": period, "net": net, "currency": payslip["currency"]},
    )
    return payslip


async def _unpaid_leave_days_in_period(staff_id: str, period: str) -> tuple:
    """Return (unpaid_days, working_days_in_period) for a YYYY-MM period.
    Uses approved leave requests whose leave_type maps to a non-paid type (or id == 'unpaid')."""
    from datetime import date as dt_date, timedelta as td
    try:
        y, m = map(int, period.split("-"))
    except Exception:
        return (0.0, 0)
    first = dt_date(y, m, 1)
    nm_y, nm_m = (y, m + 1) if m < 12 else (y + 1, 1)
    last = dt_date(nm_y, nm_m, 1) - td(days=1)
    # Count working days in the period
    working = 0
    d = first
    while d <= last:
        if d.weekday() < 5:
            working += 1
        d += td(days=1)
    # Tally approved unpaid leave days that overlap the period
    unpaid_total = 0.0
    async for lr in db.hr_leave_requests.find({
        "staff_id": staff_id,
        "status": "approved",
        "start_date": {"$lte": last.isoformat()},
        "end_date": {"$gte": first.isoformat()},
    }, {"_id": 0}):
        # Resolve whether this leave_type is paid (campus-overridable)
        lt_id = lr.get("leave_type")
        is_paid = True
        if lt_id == "unpaid":
            is_paid = False
        else:
            loc_id = lr.get("location_id")
            settings = await db.hr_settings.find_one({"location_id": loc_id}, {"_id": 0, "leave_types": 1}) if loc_id else None
            types = (settings or {}).get("leave_types") or DEFAULT_LEAVE_TYPES
            t = next((t for t in types if t.get("id") == lt_id), None)
            if t and t.get("paid") is False:
                is_paid = False
        if is_paid:
            continue
        # Days within the period (business days only)
        try:
            sd = dt_date.fromisoformat(lr["start_date"][:10])
            ed = dt_date.fromisoformat(lr["end_date"][:10])
        except Exception:
            continue
        sd = max(sd, first); ed = min(ed, last)
        if ed < sd:
            continue
        biz = 0
        d = sd
        while d <= ed:
            if d.weekday() < 5:
                biz += 1
            d += td(days=1)
        if lr.get("half_day") and lr.get("days") == 0.5 and biz == 1:
            unpaid_total += 0.5
        else:
            unpaid_total += biz
    return (unpaid_total, working)


async def _generate_payslips_for(period: str, location_id: str, current_user: dict, days_worked_override: dict = None, pto_days_override: dict = None) -> dict:
    """Shared helper: generate missing payslips for a period + optional location.
    Applies automatic unpaid-leave proration: gross is reduced by (unpaid_days / working_days)
    and a transparent line-item 'Unpaid leave proration' is added so payslip math is auditable.

    New optional dicts:
    - days_worked_override: {staff_id: days} — override with an explicit day count
      (from an approved timesheet or manager input). Prorates gross by
      days_worked/working_days.
    - pto_days_override: {staff_id: days} — paid time off (does NOT reduce gross,
      informational only, printed on payslip).
    """
    days_worked_override = days_worked_override or {}
    pto_days_override = pto_days_override or {}
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    salaries = await db.hr_salaries.find(query, {"_id": 0}).to_list(500)
    generated = []
    for sal in salaries:
        existing = await db.hr_payslips.find_one({"salary_id": sal["id"], "period": period})
        if existing:
            continue
        base_gross = float(sal.get("base_salary", 0) or 0)
        deductions = 0
        allowances = 0
        items = []
        # ---- Unpaid leave proration (existing) ----
        unpaid_days, working_days = await _unpaid_leave_days_in_period(sal["staff_id"], period)
        proration_amount = 0.0
        effective_gross = base_gross
        if unpaid_days > 0 and working_days > 0 and base_gross > 0:
            proration_amount = round(base_gross * (unpaid_days / working_days), 2)
            effective_gross = max(0.0, base_gross - proration_amount)
            items.append({
                "name": "Unpaid leave proration",
                "type": "deduction",
                "amount": proration_amount,
                "is_percentage": False,
                "calculated_amount": proration_amount,
                "auto_generated": True,
                "details": f"{unpaid_days} unpaid day(s) ÷ {working_days} working days",
            })
            deductions += proration_amount

        # ---- Manual days_worked override (from timesheet or director) ----
        override_days = days_worked_override.get(sal["staff_id"])
        pto_days = pto_days_override.get(sal["staff_id"])
        if override_days is not None and working_days > 0 and base_gross > 0:
            # Recompute gross based on actual days worked
            wd_after_unpaid = max(0, working_days - unpaid_days)
            days_worked_val = float(override_days)
            if wd_after_unpaid > 0 and days_worked_val < wd_after_unpaid:
                short_days = wd_after_unpaid - days_worked_val
                short_amount = round(effective_gross * (short_days / wd_after_unpaid), 2)
                effective_gross = max(0.0, effective_gross - short_amount)
                items.append({
                    "name": "Days-worked adjustment",
                    "type": "deduction",
                    "amount": short_amount,
                    "is_percentage": False,
                    "calculated_amount": short_amount,
                    "auto_generated": True,
                    "details": f"{days_worked_val} of {wd_after_unpaid} days worked ({short_days} day(s) short)",
                })
                deductions += short_amount

        gross = effective_gross  # Allowances / % deductions compute against the post-proration gross
        for li in (sal.get("line_items") or []):
            amt = float(li.get("amount", 0))
            if li.get("is_percentage"):
                amt = gross * amt / 100
            if li.get("type") == "deduction":
                deductions += amt
                items.append({**li, "calculated_amount": amt})
            else:
                allowances += amt
                items.append({**li, "calculated_amount": amt})
        # Net is computed against original base for transparency: base + allowances - deductions
        # (deductions already includes the unpaid-leave proration + days-worked adjustment)
        net = base_gross + allowances - deductions
        payslip = {
            "id": f"ps_{uuid.uuid4().hex[:8]}",
            "salary_id": sal["id"],
            "staff_id": sal["staff_id"],
            "staff_name": sal.get("staff_name", ""),
            "department": sal.get("department", ""),
            "location_id": sal.get("location_id", ""),
            "period": period,
            "gross_salary": base_gross,
            "allowances": allowances,
            "deductions": deductions,
            "net_salary": net,
            "unpaid_leave_days": unpaid_days,
            "working_days": working_days,
            "days_worked": override_days if override_days is not None else (max(0, working_days - unpaid_days)),
            "pto_days": pto_days if pto_days is not None else 0,
            "unpaid_leave_proration": proration_amount,
            "currency": sal.get("currency", "UGX"),
            "line_items": items,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.hr_payslips.insert_one(payslip)
        payslip.pop("_id", None)
        generated.append(payslip)
    await _audit(current_user["id"], "create", "payslips", period, {"count": len(generated)})
    return {"generated": len(generated), "payslips": generated}


@router.post("/payslips/generate-payday")
async def generate_payday_payslips(current_user: dict = Depends(require_director)):
    """Generate payslips for all campuses whose payday matches today.
    A campus 'is on payday' if either: (a) next_pay_date == today (preferred), or
    (b) pay_day (legacy day-of-month) equals today's day-of-month. Period defaults to current YYYY-MM."""
    today = datetime.now(timezone.utc)
    today_iso = today.strftime("%Y-%m-%d")
    today_day = today.day
    period = f"{today.year:04d}-{today.month:02d}"
    campus_q = {"hr_enabled": True, "$or": [
        {"next_pay_date": today_iso},
        {"pay_day": today_day},
    ]}
    settings = await db.hr_settings.find(campus_q, {"_id": 0, "location_id": 1, "pay_day": 1, "next_pay_date": 1}).to_list(100)
    if not settings:
        return {"generated": 0, "payslips": [], "message": f"No campuses have payday today ({today_iso} or day-of-month={today_day})", "period": period}
    all_generated = []
    total_count = 0
    for s in settings:
        loc_id = s.get("location_id", "")
        if not loc_id:
            continue
        res = await _generate_payslips_for(period, loc_id, current_user)
        total_count += res["generated"]
        all_generated.extend(res["payslips"])
    return {
        "generated": total_count,
        "payslips": all_generated,
        "period": period,
        "day_of_month": today_day,
        "campuses_matched": [s.get("location_id") for s in settings],
    }


@router.post("/payslips/pay-batch")
async def pay_batch_payslips(data: dict, current_user: dict = Depends(require_director)):
    """Mark a batch of approved payslips as PAID in one go (bi-weekly / monthly payday).
    Body: {payslip_ids: [...] }  OR  {period: 'YYYY-MM', location_id?}
    Each marked-paid payslip contributes to a single aggregated daily expense line."""
    ids = data.get("payslip_ids") or []
    if not ids:
        # Build from period + optional location
        period = data.get("period")
        if not period:
            raise HTTPException(status_code=400, detail="Provide payslip_ids or period")
        query = {"period": period, "status": "approved"}
        if data.get("location_id"):
            query["location_id"] = data["location_id"]
        approved = await db.hr_payslips.find(query, {"_id": 0, "id": 1}).to_list(500)
        ids = [p["id"] for p in approved]
    if not ids:
        return {"paid_count": 0, "message": "No approved payslips matched"}
    paid_count = 0
    aggregated_total = 0
    for pid in ids:
        payslip = await db.hr_payslips.find_one({"id": pid, "status": {"$ne": "paid"}}, {"_id": 0})
        if not payslip:
            continue
        await _aggregate_payroll_expense(payslip, current_user)
        await db.hr_payslips.update_one({"id": pid}, {"$set": {
            "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "paid_by": current_user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        paid_count += 1
        aggregated_total += float(payslip.get("net_salary") or 0)
    await _audit(current_user["id"], "pay-batch", "hr_payslips", f"{paid_count} payslips", {"total": aggregated_total})
    return {"paid_count": paid_count, "total_paid": aggregated_total}


@router.put("/payslips/{payslip_id}")
async def update_payslip(payslip_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Update a payslip. Director+ can edit any field (gross, allowances, deductions,
    line_items, notes, status). Every change is recorded to `edit_history` (audit trail).

    When status transitions to 'paid', the system aggregates the payment into a SINGLE
    daily payroll expense line for the location (no individual staff names exposed)."""
    existing = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Payslip not found")
    allowed = {"status", "notes", "approved_by", "paid_at", "paid_by",
               "gross_salary", "allowances", "deductions", "net_salary",
               "line_items", "currency", "period",
               "paid_from_account_id", "payroll_location_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    # If line_items provided, recompute allowances/deductions/net from them
    if "line_items" in update and isinstance(update["line_items"], list):
        total_allw = 0.0
        total_ded = 0.0
        for li in update["line_items"]:
            amt = float(li.get("calculated_amount", li.get("amount", 0)) or 0)
            t = (li.get("type") or "").lower()
            if t == "deduction":
                total_ded += amt
            elif t in ("allowance", "addition", "bonus", "reimbursement"):
                total_allw += amt
        update["allowances"] = round(total_allw, 2)
        update["deductions"] = round(total_ded, 2)
        gross = float(update.get("gross_salary", existing.get("gross_salary", 0)) or 0)
        update["net_salary"] = round(gross + total_allw - total_ded, 2)
    elif any(k in update for k in ("gross_salary", "allowances", "deductions")):
        gross = float(update.get("gross_salary", existing.get("gross_salary", 0)) or 0)
        allw = float(update.get("allowances", existing.get("allowances", 0)) or 0)
        ded = float(update.get("deductions", existing.get("deductions", 0)) or 0)
        update["net_salary"] = round(gross + allw - ded, 2)
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    update["updated_by_name"] = current_user.get("name", "")
    if data.get("status") == "approved" and existing.get("status") != "approved":
        update["approved_by"] = current_user["id"]
        update["approved_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("status") == "paid" and existing.get("status") != "paid":
        update["paid_by"] = current_user["id"]
        update["paid_by_name"] = current_user.get("name", "")
        update["paid_at"] = datetime.now(timezone.utc).isoformat()
        # Aggregate into a daily payroll expense for the location (no staff names)
        await _aggregate_payroll_expense({**existing, **update}, current_user)
    elif existing.get("status") == "paid" and any(k in update for k in ("paid_from_account_id", "payroll_location_id", "net_salary", "gross_salary", "allowances", "deductions")):
        # Already-paid payslip is being edited — re-aggregate so the ledger
        # reflects the new totals or the new account/location tagging.
        await _aggregate_payroll_expense({**existing, **update}, current_user)
    # Build diff-based audit entry
    diff = {k: {"old": existing.get(k), "new": v} for k, v in update.items() if existing.get(k) != v and k not in ("updated_at", "updated_by", "updated_by_name")}
    audit_entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "by": current_user["id"],
        "by_name": current_user.get("name", ""),
        "changes": diff,
        "reason": (data.get("reason") or "")[:200],
    }
    await db.hr_payslips.update_one(
        {"id": payslip_id},
        {"$set": update, "$push": {"edit_history": audit_entry}},
    )
    await _audit(current_user["id"], "update", "payslip", payslip_id, {"changes": list(diff.keys())})
    return await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})


async def _aggregate_payroll_expense(payslip: dict, current_user: dict):
    """iter 246 (finance reset): every 'paid' payslip now posts a single
    balanced Journal Entry via the new `routers.finance.postings` module —
    Dr Salaries & Wages / Cr Bank. Idempotent by payslip.id so re-running
    the payday flow never doubles up the ledger.
    """
    from routers.finance.postings import post_payroll_payslip
    try:
        await post_payroll_payslip(payslip, current_user)
    except Exception as ex:
        logger.error(f"[finance] payroll JE post failed for {payslip.get('id')}: {ex}")


# ========== PAYROLL LEDGER REPAIR (iter219) ==========
# One-click backfill for HR processes that never made it to the ledger.
# Two categories of missing/broken postings this fixes:
#   (A) Payroll aggregate expense docs exist but have NO active journal
#       entry (or their JE was reversed and never re-posted).  This is the
#       pre-iter210b payslip → these payslips WERE aggregated at Finance
#       level but never hit Accounting.
#   (B) Paid payslips whose (location, paid_at date) has NO aggregate
#       expense doc at all — the pre-fix code path skipped aggregation
#       entirely.  These are reconstructed as fresh daily aggregates.
#   (C) JEs that WERE posted but landed in a SALES journal are handed off
#       to the existing `/financial/repair-wrong-journal` migrator.

@router.post("/repair-payslip-journals")
async def repair_payslip_journals(data: dict = None, current_user: dict = Depends(require_admin)):
    """One-click repair for payroll postings missing from Accounting.

    Body (all optional): {
      apply: bool = false            → default is dry-run preview
      include_wrong_journal: true    → also delegate to /financial/repair-wrong-journal
    }
    Idempotent; safe to run multiple times.
    """
    data = data or {}
    apply = bool(data.get("apply"))
    include_wrong_journal = bool(data.get("include_wrong_journal", True))
    from routers.financial import _post_to_accounting

    # ── Pass A: existing payroll expenses missing an active JE ───────────
    pass_a_fixes: list = []
    async for exp in db.expenses.find({"source": "hr_payroll_aggregate"}, {"_id": 0}):
        active_je = await db.accounting_entries.find_one(
            {"auto_generated_from": "payroll", "source_id": exp["id"], "is_reversed": {"$ne": True}, "status": "posted"},
            {"_id": 0, "id": 1},
        )
        if active_je:
            continue
        pass_a_fixes.append({
            "expense_id": exp["id"],
            "location_id": exp.get("location_id"),
            "amount": exp.get("amount"),
            "period": exp.get("payroll_period"),
            "staff_count": exp.get("payroll_count"),
            "action": "post_missing_je",
        })
        if apply:
            try:
                await _post_to_accounting("payroll", exp, current_user)
                # Verify the JE was actually created (may be silently skipped if
                # the location has no Wages/Salaries or Cash account in its CoA).
                je_check = await db.accounting_entries.find_one(
                    {"auto_generated_from": "payroll", "source_id": exp["id"],
                     "is_reversed": {"$ne": True}, "status": "posted"},
                    {"_id": 0, "id": 1},
                )
                if not je_check:
                    pass_a_fixes[-1]["skipped"] = "no_wages_or_cash_account_in_chart_of_accounts"
            except Exception as ex:
                logger.error(f"Repair pass-A post failed for {exp['id']}: {ex}")
                pass_a_fixes[-1]["error"] = str(ex)[:200]

    # ── Pass B: paid payslips with no aggregate at all ───────────────────
    # Group paid payslips by (payroll_location_id | location_id, paid_at date).
    # For each group, check if a payroll_{loc}_{date} expense exists; if not,
    # reconstruct it and post the JE.
    pass_b_fixes: list = []
    paid_payslips = await db.hr_payslips.find(
        {"status": "paid"},
        {"_id": 0, "id": 1, "staff_id": 1, "period": 1, "net_salary": 1, "currency": 1,
         "paid_at": 1, "paid_from_account_id": 1, "payroll_location_id": 1, "location_id": 1},
    ).to_list(50000)
    # Group into (loc, date)
    groups: dict = {}
    for p in paid_payslips:
        loc_id = p.get("payroll_location_id") or p.get("location_id")
        if not loc_id:
            continue
        paid_at = (p.get("paid_at") or "")[:10]
        if not paid_at:
            continue
        key = (loc_id, paid_at)
        g = groups.setdefault(key, {
            "loc_id": loc_id, "paid_at": paid_at, "count": 0, "total": 0.0,
            "currency": p.get("currency") or "UGX", "period": p.get("period", ""),
            "paid_from": p.get("paid_from_account_id"), "payslip_ids": [],
        })
        g["count"] += 1
        g["total"] += float(p.get("net_salary") or 0)
        g["payslip_ids"].append(p["id"])
        # Prefer any explicit paid_from_account_id from the group
        if not g["paid_from"] and p.get("paid_from_account_id"):
            g["paid_from"] = p["paid_from_account_id"]

    for (loc_id, paid_at), g in groups.items():
        expense_id = f"payroll_{loc_id}_{paid_at}"
        existing_exp = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
        if existing_exp:
            continue  # Pass A already covers it if the JE is missing
        pass_b_fixes.append({
            "expense_id": expense_id,
            "location_id": loc_id,
            "paid_at": paid_at,
            "period": g["period"],
            "staff_count": g["count"],
            "amount": round(g["total"], 2),
            "payslip_ids": g["payslip_ids"],
            "action": "reconstruct_expense_and_je",
        })
        if apply:
            # Determine paid_from — fall back to the store's default if not set
            paid_from = g["paid_from"]
            if not paid_from:
                store_setting = await db.store_settings.find_one(
                    {"location_id": loc_id}, {"_id": 0, "default_cash_account_id": 1}
                ) or {}
                paid_from = store_setting.get("default_cash_account_id") or ""
            expense_doc = {
                "id": expense_id,
                "title": "Payroll (Wages & Salaries)",
                "amount": round(g["total"], 2),
                "currency": g["currency"],
                "category": "Wages & Salaries",
                "department": "HR",
                "budget_category": "Wages & Salaries",
                "date": paid_at,
                "notes": f"Payroll for {g['count']} staff, period {g['period']} (retroactive repair)",
                "location_id": loc_id,
                "paid_from_account_id": paid_from,
                "status": "approved",
                "source": "hr_payroll_aggregate",
                "payroll_count": g["count"],
                "payroll_period": g["period"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": current_user["id"],
                "retroactive_repair": True,
                "repaired_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await db.expenses.insert_one(expense_doc)
                await _post_to_accounting("payroll", expense_doc, current_user)
                je_check = await db.accounting_entries.find_one(
                    {"auto_generated_from": "payroll", "source_id": expense_id,
                     "is_reversed": {"$ne": True}, "status": "posted"},
                    {"_id": 0, "id": 1},
                )
                if not je_check:
                    pass_b_fixes[-1]["skipped"] = "no_wages_or_cash_account_in_chart_of_accounts"
            except Exception as ex:
                logger.error(f"Repair pass-B failed for {expense_id}: {ex}")
                pass_b_fixes[-1]["error"] = str(ex)[:200]

    # ── Pass C: delegate to existing wrong-journal repair for payroll ────
    pass_c_result = None
    if include_wrong_journal:
        if apply:
            from routers.financial import repair_wrong_journal
            pass_c_result = await repair_wrong_journal(current_user)
        else:
            # Dry-run — just count the eligible entries
            sales_journal_ids = [j["id"] async for j in db.accounting_journals.find(
                {"kind": "sales"}, {"_id": 0, "id": 1}
            )]
            eligible = 0
            if sales_journal_ids:
                eligible = await db.accounting_entries.count_documents({
                    "journal_id": {"$in": sales_journal_ids},
                    "auto_generated_from": "payroll",
                })
            pass_c_result = {"scanned": eligible, "message": "would re-tag payroll JEs from sales to GL"}

    if apply:
        await _audit(current_user["id"], "repair", "payslip_journals", None, {
            "pass_a": len(pass_a_fixes),
            "pass_b": len(pass_b_fixes),
            "pass_c": pass_c_result,
        })
        logger.warning(
            f"HR PAYSLIP JOURNAL REPAIR by {current_user.get('email','?')} — "
            f"pass_a={len(pass_a_fixes)} pass_b={len(pass_b_fixes)} pass_c={pass_c_result}"
        )

    # Diagnostics — total state summary so the operator can compare
    # (aggregate expense total) vs (posted JE debit total) vs (paid payslip total).
    total_paid_payslips = await db.hr_payslips.count_documents({"status": "paid"})
    payslip_sum_agg = await db.hr_payslips.aggregate([
        {"$match": {"status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$net_salary"}}},
    ]).to_list(1)
    total_paid_sum = float((payslip_sum_agg or [{}])[0].get("total") or 0)
    total_aggregate_expenses = await db.expenses.count_documents({"source": "hr_payroll_aggregate"})
    expense_sum_agg = await db.expenses.aggregate([
        {"$match": {"source": "hr_payroll_aggregate"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_expense_sum = float((expense_sum_agg or [{}])[0].get("total") or 0)
    total_active_jes = await db.accounting_entries.count_documents({
        "auto_generated_from": "payroll",
        "is_reversed": {"$ne": True},
        "status": "posted",
    })
    je_sum_agg = await db.accounting_entries.aggregate([
        {"$match": {"auto_generated_from": "payroll", "is_reversed": {"$ne": True}, "status": "posted"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_debit"}}},
    ]).to_list(1)
    total_je_sum = float((je_sum_agg or [{}])[0].get("total") or 0)

    return {
        "dry_run": not apply,
        "pass_a_missing_je": {
            "count": len(pass_a_fixes),
            "sample": pass_a_fixes[:10],
            "total_amount": round(sum(f.get("amount") or 0 for f in pass_a_fixes), 2),
            "skipped_no_accounts": sum(1 for f in pass_a_fixes if f.get("skipped") == "no_wages_or_cash_account_in_chart_of_accounts"),
        },
        "pass_b_reconstruct": {
            "count": len(pass_b_fixes),
            "sample": pass_b_fixes[:10],
            "total_amount": round(sum(f.get("amount") or 0 for f in pass_b_fixes), 2),
            "skipped_no_accounts": sum(1 for f in pass_b_fixes if f.get("skipped") == "no_wages_or_cash_account_in_chart_of_accounts"),
        },
        "pass_c_wrong_journal": pass_c_result,
        "locations_missing_accounts": sorted(list({
            f.get("location_id") for f in (pass_a_fixes + pass_b_fixes)
            if f.get("skipped") == "no_wages_or_cash_account_in_chart_of_accounts" and f.get("location_id")
        })),
        "diagnostics": {
            "paid_payslips": total_paid_payslips,
            "paid_payslips_total_ugx": round(total_paid_sum, 2),
            "aggregate_expenses": total_aggregate_expenses,
            "aggregate_expenses_total_ugx": round(total_expense_sum, 2),
            "active_payroll_jes": total_active_jes,
            "active_payroll_jes_total_ugx": round(total_je_sum, 2),
            "in_sync": abs(total_expense_sum - total_je_sum) < 0.01 and total_aggregate_expenses > 0,
        },
        "message": (
            "Dry-run — POST again with {\"apply\": true} to persist changes."
            if not apply else
            "Applied.  Trial Balance & Chart-Account balances should now reflect all paid payslips."
        ),
    }


# ========== DANGER ZONE: HR MODULE RESET (iter225) ==========
# Admin-only nuclear button to wipe HR data. Two axes:
#   scope       = 'payslips' | 'all'
#   campus_scope= 'active'   | 'all'    (all requires system_admin)
#   ledger      = 'reverse'  | 'delete' (how to unwind payroll postings)
#
# Reverse: creates offsetting JEs (auditable, keeps ledger history)
# Delete : hard-removes the payroll expense + JE (no trail)
#
# Requires body { confirm: 'RESET-HR' } to actually apply. Otherwise dry-run.

HR_ALL_COLLECTIONS = [
    "hr_payslips",
    "hr_salaries",
    "hr_salary_history",
    "hr_contracts",
    "hr_contract_templates",
    "hr_doc_requests",
    "hr_timesheets",
    "hr_time_off",
    "hr_leave_requests",
    "hr_reimbursements",
    "hr_attendance",
]


@router.delete("/reset")
async def reset_hr_module(
    scope: str = "payslips",
    campus_scope: str = "active",
    ledger: str = "reverse",
    confirm: str = "",
    current_user: dict = Depends(require_admin),
):
    """DANGER: Reset HR data. Admin-only.

    Query params:
      scope        - 'payslips' (default) or 'all'
      campus_scope - 'active' (default) or 'all' (system_admin only)
      ledger       - 'reverse' (default: post offsetting JEs) or 'delete' (hard delete)
      confirm      - must equal 'RESET-HR' to actually delete; otherwise returns a dry-run count.
    """
    if scope not in {"payslips", "all"}:
        raise HTTPException(status_code=400, detail="scope must be 'payslips' or 'all'")
    if campus_scope not in {"active", "all"}:
        raise HTTPException(status_code=400, detail="campus_scope must be 'active' or 'all'")
    if ledger not in {"reverse", "delete"}:
        raise HTTPException(status_code=400, detail="ledger must be 'reverse' or 'delete'")

    # Build campus scope filter
    role = (current_user.get("role") or "").lower()
    if campus_scope == "all":
        if role != "system_admin":
            raise HTTPException(status_code=403, detail="Only system_admin can reset across all campuses")
        loc_filter: dict = {}
        loc_ids_for_expenses: list = []  # empty means all
    else:
        active = current_user.get("active_campus_id") or ""
        if not active:
            raise HTTPException(status_code=400, detail="No active campus set")
        loc_filter = {"location_id": active}
        loc_ids_for_expenses = [active]

    apply_changes = (confirm or "").strip() == "RESET-HR"

    # ── Preview: count what would be affected ────────────────────────────
    counts: dict = {}
    if scope == "payslips":
        counts["hr_payslips"] = await db.hr_payslips.count_documents(loc_filter)
    else:
        for coll in HR_ALL_COLLECTIONS:
            try:
                counts[coll] = await db[coll].count_documents(loc_filter)
            except Exception:
                counts[coll] = 0

    # Payroll aggregate expenses & JEs affected
    exp_query: dict = {"source": "hr_payroll_aggregate"}
    if loc_ids_for_expenses:
        exp_query["location_id"] = {"$in": loc_ids_for_expenses}
    payroll_expenses = await db.expenses.count_documents(exp_query)
    # Related JEs — find by source_id in matching expenses
    exp_ids = [e["id"] async for e in db.expenses.find(exp_query, {"_id": 0, "id": 1})]
    je_query: dict = {"auto_generated_from": "payroll", "source_id": {"$in": exp_ids}, "is_reversed": {"$ne": True}} if exp_ids else {"_no_match": True}
    payroll_jes = await db.accounting_entries.count_documents(je_query) if exp_ids else 0

    counts["payroll_expenses"] = payroll_expenses
    counts["payroll_journal_entries"] = payroll_jes

    if not apply_changes:
        return {
            "dry_run": True,
            "scope": scope,
            "campus_scope": campus_scope,
            "ledger": ledger,
            "counts": counts,
            "message": "Preview only. To apply, POST/DELETE again with confirm=RESET-HR",
        }

    # ── APPLY ────────────────────────────────────────────────────────────
    result: dict = {
        "dry_run": False,
        "scope": scope,
        "campus_scope": campus_scope,
        "ledger": ledger,
        "deleted": {},
        "ledger_unwound": {"reversed_jes": 0, "deleted_jes": 0, "deleted_expenses": 0},
    }

    # 1) Unwind payroll ledger postings first (so we can still find them)
    if exp_ids:
        if ledger == "reverse":
            try:
                from routers.financial import _reverse_auto_posted_je
                for eid in exp_ids:
                    try:
                        await _reverse_auto_posted_je("payroll", eid, current_user)
                        result["ledger_unwound"]["reversed_jes"] += 1
                    except Exception as ex:
                        logger.warning(f"Reverse JE failed for expense {eid}: {ex}")
            except Exception as ex:
                logger.error(f"Ledger reverse import failed: {ex}")
        else:  # delete
            del_jes = await db.accounting_entries.delete_many({
                "auto_generated_from": "payroll",
                "source_id": {"$in": exp_ids},
            })
            result["ledger_unwound"]["deleted_jes"] = del_jes.deleted_count

        # Delete or archive the payroll expenses themselves
        # Route through recycle bin for auditability
        async for exp in db.expenses.find(exp_query, {"_id": 0}):
            exp["_deleted_from"] = "expenses"
            exp["deleted_at"] = datetime.now(timezone.utc).isoformat()
            exp["deleted_by"] = current_user["id"]
            exp["_hr_reset"] = True
            try:
                await db.deleted_items.insert_one(exp)
            except Exception:
                pass
        del_exp = await db.expenses.delete_many(exp_query)
        result["ledger_unwound"]["deleted_expenses"] = del_exp.deleted_count

    # 2) Delete HR collection docs (payslips only, or everything)
    collections_to_wipe = ["hr_payslips"] if scope == "payslips" else HR_ALL_COLLECTIONS
    for coll in collections_to_wipe:
        try:
            # Recycle bin dump before delete so admins can recover if needed
            async for doc in db[coll].find(loc_filter, {"_id": 0}):
                doc["_deleted_from"] = coll
                doc["deleted_at"] = datetime.now(timezone.utc).isoformat()
                doc["deleted_by"] = current_user["id"]
                doc["_hr_reset"] = True
                try:
                    await db.deleted_items.insert_one(doc)
                except Exception:
                    pass
            r = await db[coll].delete_many(loc_filter)
            result["deleted"][coll] = r.deleted_count
        except Exception as ex:
            logger.error(f"HR reset failed to wipe {coll}: {ex}")
            result["deleted"][coll] = f"error: {ex}"

    await _audit(
        current_user["id"], "reset", "hr_module", None,
        {"scope": scope, "campus_scope": campus_scope, "ledger": ledger, "result": result["deleted"]},
    )
    logger.warning(
        f"HR MODULE RESET by {current_user.get('email','?')} — scope={scope} "
        f"campus_scope={campus_scope} ledger={ledger} result={result}"
    )
    return result


# ========== CONTRACT TEMPLATES ==========

@router.get("/contracts/templates")
async def list_contract_templates(location_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    return await db.hr_contract_templates.find(query, {"_id": 0}).sort("name", 1).to_list(100)


@router.post("/contracts/templates")
async def create_contract_template(data: dict, current_user: dict = Depends(require_director)):
    doc = {
        "id": f"ct_{uuid.uuid4().hex[:8]}",
        "name": data.get("name", "Employment Contract"),
        "content": data.get("content", ""),  # HTML/Markdown template with {{variables}}
        "location_id": data.get("location_id") or current_user.get("active_campus_id", ""),
        "variables": data.get("variables", ["staff_name", "role", "start_date", "salary", "department"]),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.hr_contract_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/contracts/templates/{template_id}")
async def update_contract_template(template_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "content", "variables"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_contract_templates.update_one({"id": template_id}, {"$set": update})
    return await db.hr_contract_templates.find_one({"id": template_id}, {"_id": 0})


@router.delete("/contracts/templates/{template_id}")
async def delete_contract_template(template_id: str, current_user: dict = Depends(require_director)):
    await db.hr_contract_templates.delete_one({"id": template_id})
    return {"message": "Template deleted"}


# ========== ISSUED CONTRACTS ==========

@router.post("/contracts/issue")
async def issue_contract(data: dict, current_user: dict = Depends(require_director)):
    """Issue a contract to a staff member from a template."""
    template_id = data.get("template_id")
    staff_id = data.get("staff_id")
    if not template_id or not staff_id:
        raise HTTPException(status_code=400, detail="template_id and staff_id required")
    template = await db.hr_contract_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    staff = await db.users.find_one({"id": staff_id}, {"_id": 0, "password_hash": 0})
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    # Replace variables in template content
    content = template.get("content", "")
    replacements = {"staff_name": staff.get("name", ""), "role": staff.get("role", ""), "department": staff.get("department", ""), "email": staff.get("email", ""), "start_date": data.get("start_date", datetime.now(timezone.utc).isoformat()[:10]), "salary": str(data.get("salary", "")), **data.get("custom_vars", {})}
    for k, v in replacements.items():
        content = content.replace(f"{{{{{k}}}}}", str(v))
    doc = {
        "id": f"con_{uuid.uuid4().hex[:8]}",
        "template_id": template_id,
        "template_name": template.get("name", ""),
        "staff_id": staff_id,
        "staff_name": staff.get("name", ""),
        "content": content,
        "location_id": template.get("location_id") or staff.get("location_id", ""),
        "status": "pending_signature",  # pending_signature, signed, expired
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "issued_by": current_user["id"],
    }
    await db.hr_contracts.insert_one(doc)
    doc.pop("_id", None)
    # Send email notification
    try:
        from email_helpers import send_notification_email
        if staff.get("email"):
            await send_notification_email(staff["email"], f"Contract: {template.get('name', 'Employment Contract')}", f"<h2>Contract Issued</h2><p>Hi {staff.get('name', '')},</p><p>A contract has been issued to you. Please review and sign.</p>")
    except Exception as e:
        logger.warning(f"Contract email failed: {e}")
    return doc


@router.get("/contracts")
async def list_contracts(staff_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    query = {}
    if staff_id:
        query["staff_id"] = staff_id
    campus = await get_campus_filter(current_user)
    if campus:
        query.update(campus)
    return await db.hr_contracts.find(query, {"_id": 0}).sort("issued_at", -1).to_list(200)


# ========== HR DOCUMENT REQUESTS ==========

@router.post("/document-requests")
async def create_hr_doc_request(data: dict, current_user: dict = Depends(require_hr)):
    staff_id = data.get("staff_id")
    doc_types = data.get("doc_types", ["resume", "id_document"])
    if not staff_id:
        raise HTTPException(status_code=400, detail="staff_id required")
    staff = await db.users.find_one({"id": staff_id}, {"_id": 0, "name": 1, "email": 1})
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    doc = {
        "id": f"hrdoc_{uuid.uuid4().hex[:8]}",
        "staff_id": staff_id,
        "staff_name": staff.get("name", ""),
        "doc_types": doc_types,
        "message": data.get("message", "Please submit the following documents."),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.hr_doc_requests.insert_one(doc)
    doc.pop("_id", None)
    try:
        from email_helpers import send_notification_email
        if staff.get("email"):
            docs_list = ", ".join(doc_types)
            await send_notification_email(staff["email"], "Document Request — 58:12 Global", f"<h2>Document Request</h2><p>Hi {staff.get('name', '')},</p><p>Please submit the following documents: <strong>{docs_list}</strong></p><p>{data.get('message', '')}</p>")
    except Exception as e:
        logger.warning(f"HR doc request email failed: {e}")
    return doc


@router.get("/document-requests")
async def list_hr_doc_requests(staff_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    query = {}
    if staff_id:
        query["staff_id"] = staff_id
    return await db.hr_doc_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


# ========== SPONSORED/SUPPORTED CHILDREN TRACKING ==========

@router.get("/sponsored-children")
async def get_sponsored_children_stats(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"is_sponsored": True}
    if location_id:
        query["location_id"] = location_id
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    sponsored = await db.children.count_documents(query)
    total = await db.children.count_documents({k: v for k, v in query.items() if k != "is_sponsored"})
    return {"sponsored": sponsored, "total": total, "percentage": round(sponsored / max(total, 1) * 100, 1)}



@router.post("/payslips/auto-generate")
async def auto_generate_payslips(current_user: dict = Depends(require_director)):
    """Auto-generate payslips for current pay period based on campus HR settings.
    Checks if today is payday, generates for all campuses where it's due."""
    today = datetime.now(timezone.utc)
    current_period = today.strftime("%Y-%m")
    generated_total = 0
    # Get all campuses with HR enabled
    campuses = await db.hr_settings.find({"hr_enabled": True}, {"_id": 0}).to_list(50)
    for campus_settings in campuses:
        pay_day = campus_settings.get("pay_day", 28)
        loc_id = campus_settings.get("location_id", "")
        # Check if already generated for this period
        existing = await db.hr_payslips.count_documents({"location_id": loc_id, "period": current_period})
        if existing > 0:
            continue
        # Check if today is on or after payday
        if today.day >= pay_day:
            salaries = await db.hr_salaries.find({"status": "active", "location_id": loc_id}, {"_id": 0}).to_list(500)
            for sal in salaries:
                gross = sal.get("base_salary", 0)
                deductions = 0; allowances = 0; items = []
                for li in (sal.get("line_items") or []):
                    amt = float(li.get("amount", 0))
                    if li.get("is_percentage"): amt = gross * amt / 100
                    if li.get("type") == "deduction": deductions += amt
                    else: allowances += amt
                    items.append({**li, "calculated_amount": amt})
                net = gross + allowances - deductions
                payslip = {
                    "id": f"ps_{uuid.uuid4().hex[:8]}", "salary_id": sal["id"], "staff_id": sal["staff_id"],
                    "staff_name": sal.get("staff_name", ""), "department": sal.get("department", ""),
                    "location_id": loc_id, "period": current_period,
                    "gross_salary": gross, "allowances": allowances, "deductions": deductions, "net_salary": net,
                    "currency": sal.get("currency", "UGX"), "line_items": items, "status": "draft",
                    "auto_generated": True, "pay_day": pay_day,
                    "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "system",
                }
                await db.hr_payslips.insert_one(payslip)
                generated_total += 1
    return {"message": f"Auto-generated {generated_total} payslips for {current_period}", "count": generated_total}


# ========== LEAVE / TIME-OFF MANAGEMENT (Odoo-style) ==========

# Default leave types per campus (can be overridden in hr_settings)
DEFAULT_LEAVE_TYPES = [
    {"id": "annual", "name": "Annual Leave", "default_days": 21, "paid": True, "color": "#3b82f6"},
    {"id": "sick", "name": "Sick Leave", "default_days": 10, "paid": True, "color": "#f97316"},
    {"id": "unpaid", "name": "Unpaid Leave", "default_days": 0, "paid": False, "color": "#6b7280"},
    {"id": "maternity", "name": "Maternity Leave", "default_days": 60, "paid": True, "color": "#ec4899"},
    {"id": "paternity", "name": "Paternity Leave", "default_days": 7, "paid": True, "color": "#0ea5e9"},
    {"id": "bereavement", "name": "Bereavement", "default_days": 5, "paid": True, "color": "#6366f1"},
]


def _count_business_days(start_iso: str, end_iso: str) -> int:
    """Count business days (Mon-Fri) between two YYYY-MM-DD dates inclusive."""
    from datetime import date as dt_date, timedelta as td
    try:
        sd = dt_date.fromisoformat(start_iso[:10])
        ed = dt_date.fromisoformat(end_iso[:10])
    except Exception:
        return 0
    if ed < sd:
        return 0
    n = 0
    d = sd
    while d <= ed:
        if d.weekday() < 5:  # 0..4 = Mon..Fri
            n += 1
        d += td(days=1)
    return n


@router.get("/leave/types")
async def list_leave_types(location_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    """Return leave types (campus-overridable). Falls back to defaults."""
    loc = location_id or current_user.get("active_campus_id") or current_user.get("location_id")
    settings = await db.hr_settings.find_one({"location_id": loc}, {"_id": 0, "leave_types": 1})
    if settings and settings.get("leave_types"):
        return settings["leave_types"]
    return DEFAULT_LEAVE_TYPES


@router.put("/leave/types")
async def set_leave_types(data: dict, current_user: dict = Depends(require_director)):
    """Set leave types for a campus. Body: { location_id, leave_types: [...] }"""
    loc = data.get("location_id") or current_user.get("active_campus_id")
    if not loc:
        raise HTTPException(status_code=400, detail="location_id required")
    await db.hr_settings.update_one(
        {"location_id": loc},
        {"$set": {"leave_types": data.get("leave_types") or []}},
        upsert=True,
    )
    return {"updated": True}


@router.get("/leave/balance")
async def leave_balance(staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get leave balance for a staff member.
    - Without staff_id: returns the current user's balance.
    - With staff_id: HR/director access required."""
    target_id = staff_id or current_user["id"]
    if staff_id and target_id != current_user["id"]:
        if not _require_hr_access(current_user):
            raise HTTPException(status_code=403, detail="HR access required to view other users' balances")
    user = await db.users.find_one({"id": target_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    types = await list_leave_types(location_id=user.get("location_id"), current_user=current_user)
    # Aggregate approved leave usage in the current calendar year
    year = datetime.now(timezone.utc).year
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"
    used_by_type = {}
    async for lr in db.hr_leave_requests.find({
        "staff_id": target_id,
        "status": "approved",
        "start_date": {"$lte": year_end},
        "end_date": {"$gte": year_start},
    }, {"_id": 0}):
        used_by_type[lr.get("leave_type")] = used_by_type.get(lr.get("leave_type"), 0) + (lr.get("days") or 0)
    # Per-user allocation override stored on the user record
    user_allocations = (await db.users.find_one({"id": target_id}, {"_id": 0, "leave_allocations": 1})) or {}
    overrides = user_allocations.get("leave_allocations") or {}
    return {
        "staff_id": target_id,
        "staff_name": user.get("name"),
        "year": year,
        "balances": [
            {
                "type": t["id"],
                "name": t["name"],
                "allocated": int(overrides.get(t["id"], t.get("default_days") or 0)),
                "used": int(used_by_type.get(t["id"], 0)),
                "remaining": int(overrides.get(t["id"], t.get("default_days") or 0)) - int(used_by_type.get(t["id"], 0)),
                "paid": t.get("paid", True),
                "color": t.get("color", "#6b7280"),
            }
            for t in types
        ],
    }


@router.put("/leave/allocation/{staff_id}")
async def set_leave_allocation(staff_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Override a staff member's annual allocation per leave type.
    Body: { allocations: {annual: 25, sick: 12, ...} }"""
    allocations = data.get("allocations") or {}
    if not isinstance(allocations, dict):
        raise HTTPException(status_code=400, detail="allocations must be an object")
    await db.users.update_one({"id": staff_id}, {"$set": {"leave_allocations": {k: int(v) for k, v in allocations.items()}}})
    return {"updated": True}


@router.get("/leave/requests")
async def list_leave_requests(status: Optional[str] = None, staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List leave requests. Non-HR users only see their own; HR sees campus-scoped."""
    query = {}
    if status:
        query["status"] = status
    if staff_id:
        query["staff_id"] = staff_id
    if not _require_hr_access(current_user):
        # Non-HR: only their own
        query["staff_id"] = current_user["id"]
    else:
        # HR scoped to campus
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    return await db.hr_leave_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/leave/requests")
async def create_leave_request(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a leave request.
    Body: { leave_type, start_date, end_date, half_day?: bool, notes? }"""
    leave_type = (data.get("leave_type") or "").strip()
    start_date = (data.get("start_date") or "").strip()[:10]
    end_date = (data.get("end_date") or "").strip()[:10]
    if not leave_type or not start_date or not end_date:
        raise HTTPException(status_code=400, detail="leave_type, start_date, end_date required")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be ≥ start_date")
    half_day = bool(data.get("half_day"))
    days = _count_business_days(start_date, end_date)
    if days == 0:
        raise HTTPException(status_code=400, detail="No business days in the selected range")
    if half_day and start_date == end_date:
        days = 0.5
    # Optional staff_id override (HR booking on someone's behalf)
    staff_id = data.get("staff_id") or current_user["id"]
    if staff_id != current_user["id"] and not _require_hr_access(current_user):
        raise HTTPException(status_code=403, detail="Cannot file leave for another user")
    staff = await db.users.find_one({"id": staff_id}, {"_id": 0, "name": 1, "role": 1, "department": 1, "location_id": 1, "email": 1})
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    doc = {
        "id": f"lvr_{uuid.uuid4().hex[:10]}",
        "staff_id": staff_id,
        "staff_name": staff.get("name"),
        "department": staff.get("department"),
        "location_id": staff.get("location_id"),
        "leave_type": leave_type,
        "start_date": start_date,
        "end_date": end_date,
        "half_day": half_day,
        "days": days,
        "notes": (data.get("notes") or "")[:500],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.hr_leave_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/leave/requests/{request_id}")
async def update_leave_request(request_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Approve/decline/cancel a leave request.
    Body: { status: 'approved'|'declined'|'cancelled', decision_note?: '' }"""
    lr = await db.hr_leave_requests.find_one({"id": request_id}, {"_id": 0})
    if not lr:
        raise HTTPException(status_code=404, detail="Request not found")
    status = (data.get("status") or "").strip()
    if status not in {"approved", "declined", "cancelled", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    # Cancel is allowed by the requester if still pending; approve/decline requires HR
    if status == "cancelled" and lr["staff_id"] == current_user["id"]:
        pass
    elif not _require_hr_access(current_user):
        raise HTTPException(status_code=403, detail="HR access required to change status")
    if lr.get("status") in {"approved", "declined"} and status != "cancelled":
        raise HTTPException(status_code=400, detail="Request is already finalized")
    update = {
        "status": status,
        "decision_at": datetime.now(timezone.utc).isoformat(),
        "decision_by": current_user["id"],
        "decision_by_name": current_user.get("name", ""),
        "decision_note": (data.get("decision_note") or "")[:500],
    }
    await db.hr_leave_requests.update_one({"id": request_id}, {"$set": update})
    return await db.hr_leave_requests.find_one({"id": request_id}, {"_id": 0})


@router.delete("/leave/requests/{request_id}")
async def delete_leave_request(request_id: str, current_user: dict = Depends(get_current_user)):
    lr = await db.hr_leave_requests.find_one({"id": request_id}, {"_id": 0})
    if not lr:
        raise HTTPException(status_code=404, detail="Request not found")
    # Only owner (still pending) or HR may delete
    if lr["staff_id"] != current_user["id"] and not _require_hr_access(current_user):
        raise HTTPException(status_code=403, detail="Not permitted")
    if lr.get("status") == "approved" and not _require_hr_access(current_user):
        raise HTTPException(status_code=400, detail="Cannot delete an approved request — cancel it instead")
    await db.hr_leave_requests.delete_one({"id": request_id})
    return {"deleted": True}


@router.get("/leave/calendar")
async def leave_calendar(month: Optional[str] = None, current_user: dict = Depends(require_hr)):
    """Approved leaves for the given YYYY-MM (or current month). Useful for an HR planning view."""
    now = datetime.now(timezone.utc)
    target = month or now.strftime("%Y-%m")
    start = f"{target}-01"
    # Next month start
    y, m = map(int, target.split("-"))
    nm = m + 1; ny = y
    if nm > 12:
        nm = 1; ny = y + 1
    nstart = f"{ny:04d}-{nm:02d}-01"
    query = {"status": "approved", "start_date": {"$lt": nstart}, "end_date": {"$gte": start}}
    campus = await get_campus_filter(current_user)
    if campus:
        query.update(campus)
    return await db.hr_leave_requests.find(query, {"_id": 0}).sort("start_date", 1).to_list(500)



# ========== EMPLOYEE EXPENSE REIMBURSEMENT (Odoo-style) ==========

EXPENSE_CATEGORIES = ["travel", "meals", "supplies", "training", "fuel", "accommodation", "other"]


@router.get("/expenses")
async def list_employee_expenses(status: Optional[str] = None, staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Employee expense submissions. Non-HR users see only their own."""
    query = {}
    if status:
        query["status"] = status
    if staff_id:
        query["staff_id"] = staff_id
    if not _require_hr_access(current_user):
        query["staff_id"] = current_user["id"]
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    return await db.hr_employee_expenses.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/expenses")
async def create_employee_expense(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a new employee expense.
    Body: { title, amount, currency?, category, date, receipt_url?, notes? }"""
    title = (data.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be numeric")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    category = (data.get("category") or "other").strip().lower()
    if category not in EXPENSE_CATEGORIES:
        category = "other"
    doc = {
        "id": f"eex_{uuid.uuid4().hex[:10]}",
        "staff_id": current_user["id"],
        "staff_name": current_user.get("name", ""),
        "department": current_user.get("department", ""),
        "location_id": current_user.get("location_id") or current_user.get("active_campus_id"),
        "title": title[:200],
        "amount": amount,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "category": category,
        "date": (data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10],
        "receipt_url": (data.get("receipt_url") or "").strip()[:500] or None,
        "notes": (data.get("notes") or "")[:500],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hr_employee_expenses.insert_one(doc)
    doc.pop("_id", None)
    # Cross-module: auto-spawn approval request if amount >= configured threshold
    try:
        await _maybe_spawn_reimbursement_approval(doc, current_user)
    except Exception as e:
        logger.warning(f"Auto approval-request spawn skipped: {e}")
    return doc


async def _maybe_spawn_reimbursement_approval(expense: dict, current_user: dict):
    """If a workflow with kind='expense' (or named after reimbursement) exists for this location
    and the amount exceeds the campus's approval threshold (default 100 in expense's currency),
    automatically submit an approval_request and link it on the expense."""
    threshold_amount = 100.0
    try:
        settings = await db.hr_settings.find_one({"location_id": expense.get("location_id")}, {"_id": 0, "reimbursement_approval_threshold": 1})
        if settings and settings.get("reimbursement_approval_threshold") is not None:
            threshold_amount = float(settings["reimbursement_approval_threshold"])
    except Exception:
        pass
    if float(expense.get("amount") or 0) < threshold_amount:
        return
    wf = await db.approval_workflows.find_one({
        "kind": "expense",
        "active": True,
        "$or": [{"location_id": expense.get("location_id")}, {"location_id": None}],
    }, {"_id": 0})
    if not wf:
        return
    steps = wf.get("steps") or []
    now = datetime.now(timezone.utc).isoformat()
    step_states = [{"step_index": i, "status": "pending", "approvals": [], "started_at": (now if i == 0 else None)} for i, _ in enumerate(steps)]
    req = {
        "id": f"areq_{uuid.uuid4().hex[:10]}",
        "workflow_id": wf["id"],
        "workflow_name": wf.get("name"),
        "workflow_snapshot": {"steps": steps, "kind": wf.get("kind")},
        "subject_kind": "expense",
        "subject_id": expense["id"],
        "title": f"Reimbursement: {expense.get('title','')}",
        "summary": f"{expense.get('staff_name')} requested {expense.get('currency')} {expense.get('amount')} — {expense.get('category')}",
        "amount": expense.get("amount"),
        "currency": expense.get("currency"),
        "metadata": {"expense_id": expense["id"]},
        "status": "in_progress",
        "current_step": 0,
        "step_states": step_states,
        "submitted_by": expense["staff_id"],
        "submitted_by_name": expense.get("staff_name", ""),
        "location_id": expense.get("location_id"),
        "auto_generated": True,
        "created_at": now,
    }
    await db.approval_requests.insert_one(req)
    # Link back on the expense
    await db.hr_employee_expenses.update_one({"id": expense["id"]}, {"$set": {"approval_request_id": req["id"]}})


@router.put("/expenses/{expense_id}")
async def update_employee_expense(expense_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Edit (owner, only while pending) OR approve/reject/reimburse (HR/director).
    Body for owner edit: { title?, amount?, category?, date?, receipt_url?, notes? }
    Body for status change: { status: 'approved'|'rejected'|'reimbursed', decision_note? }"""
    exp = await db.hr_employee_expenses.find_one({"id": expense_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    is_owner = exp["staff_id"] == current_user["id"]
    is_hr = _require_hr_access(current_user)
    # Status change branch
    if "status" in data:
        if not is_hr:
            raise HTTPException(status_code=403, detail="HR access required to change status")
        new_status = data["status"]
        if new_status not in {"approved", "rejected", "reimbursed", "pending"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        if exp.get("status") == "reimbursed" and new_status != "reimbursed":
            raise HTTPException(status_code=400, detail="Cannot change a reimbursed expense")
        update = {
            "status": new_status,
            "decision_at": datetime.now(timezone.utc).isoformat(),
            "decision_by": current_user["id"],
            "decision_by_name": current_user.get("name", ""),
            "decision_note": (data.get("decision_note") or "")[:500],
        }
        if new_status == "reimbursed":
            update["reimbursed_at"] = update["decision_at"]
        await db.hr_employee_expenses.update_one({"id": expense_id}, {"$set": update})
        return await db.hr_employee_expenses.find_one({"id": expense_id}, {"_id": 0})
    # Owner edit branch
    if not is_owner:
        raise HTTPException(status_code=403, detail="Only the owner can edit")
    if exp.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Can only edit pending expenses")
    allowed = {"title", "amount", "category", "date", "receipt_url", "notes", "currency"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "amount" in update:
        try:
            update["amount"] = float(update["amount"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="amount must be numeric")
        if update["amount"] <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive")
    if "category" in update and update["category"] not in EXPENSE_CATEGORIES:
        update["category"] = "other"
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_employee_expenses.update_one({"id": expense_id}, {"$set": update})
    return await db.hr_employee_expenses.find_one({"id": expense_id}, {"_id": 0})


@router.delete("/expenses/{expense_id}")
async def delete_employee_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    exp = await db.hr_employee_expenses.find_one({"id": expense_id}, {"_id": 0})
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    is_owner = exp["staff_id"] == current_user["id"]
    is_hr = _require_hr_access(current_user)
    if not (is_owner or is_hr):
        raise HTTPException(status_code=403, detail="Not permitted")
    if exp.get("status") in {"approved", "reimbursed"} and not is_hr:
        raise HTTPException(status_code=400, detail="Cannot delete approved/reimbursed expenses")
    await db.hr_employee_expenses.delete_one({"id": expense_id})
    return {"deleted": True}


@router.get("/expenses/summary")
async def employee_expenses_summary(period: Optional[str] = None, current_user: dict = Depends(require_hr)):
    """Reimbursement summary for a period (YYYY-MM, defaults to current month).
    Returns totals + by-staff and by-category breakdowns."""
    period = period or datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{period}-01"
    y, m = map(int, period.split("-"))
    nm_y, nm_m = (y, m + 1) if m < 12 else (y + 1, 1)
    end = f"{nm_y:04d}-{nm_m:02d}-01"
    query = {"date": {"$gte": start, "$lt": end}}
    campus = await get_campus_filter(current_user)
    if campus:
        query.update(campus)
    rows = await db.hr_employee_expenses.find(query, {"_id": 0}).to_list(2000)
    by_status = {}
    by_category = {}
    by_staff = {}
    for r in rows:
        s = r.get("status", "pending")
        by_status[s] = by_status.get(s, 0) + float(r.get("amount") or 0)
        c = r.get("category", "other")
        by_category[c] = by_category.get(c, 0) + float(r.get("amount") or 0)
        k = r.get("staff_id")
        if k:
            by_staff.setdefault(k, {"staff_name": r.get("staff_name"), "total": 0, "count": 0})
            by_staff[k]["total"] += float(r.get("amount") or 0)
            by_staff[k]["count"] += 1
    return {
        "period": period,
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_category": by_category,
        "by_staff": list(by_staff.values()),
        "count": len(rows),
    }



# ========== ATTENDANCE / CLOCK-IN-OUT (Odoo-style) ==========

@router.post("/attendance/clock-in")
async def attendance_clock_in(data: dict = None, current_user: dict = Depends(get_current_user)):
    """Clock the current user in. Idempotent: returns the active entry if one already exists.
    Optional body: { notes?, location_id? }"""
    data = data or {}
    open_entry = await db.hr_attendance.find_one({
        "staff_id": current_user["id"],
        "check_out_time": None,
    }, {"_id": 0})
    if open_entry:
        return {"already_clocked_in": True, "entry": open_entry}
    now = datetime.now(timezone.utc)
    entry = {
        "id": f"att_{uuid.uuid4().hex[:10]}",
        "staff_id": current_user["id"],
        "staff_name": current_user.get("name", ""),
        "department": current_user.get("department", ""),
        "location_id": data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id"),
        "check_in_time": now.isoformat(),
        "check_out_time": None,
        "duration_minutes": None,
        "notes": (data.get("notes") or "")[:300],
        "date": now.strftime("%Y-%m-%d"),
        "auto_closed": False,
    }
    await db.hr_attendance.insert_one(entry)
    entry.pop("_id", None)
    return {"already_clocked_in": False, "entry": entry}


@router.post("/attendance/clock-out")
async def attendance_clock_out(data: dict = None, current_user: dict = Depends(get_current_user)):
    """Close the user's open attendance entry. Returns 400 if no open entry exists."""
    data = data or {}
    open_entry = await db.hr_attendance.find_one({
        "staff_id": current_user["id"],
        "check_out_time": None,
    }, {"_id": 0})
    if not open_entry:
        raise HTTPException(status_code=400, detail="No active clock-in")
    now = datetime.now(timezone.utc)
    try:
        check_in = datetime.fromisoformat(open_entry["check_in_time"].replace("Z", "+00:00"))
        duration = int((now - check_in).total_seconds() / 60)
    except Exception:
        duration = 0
    update = {
        "check_out_time": now.isoformat(),
        "duration_minutes": max(0, duration),
    }
    if data.get("notes"):
        update["notes"] = ((open_entry.get("notes") or "") + " · " + data["notes"][:300]).strip(" ·")
    await db.hr_attendance.update_one({"id": open_entry["id"]}, {"$set": update})
    return await db.hr_attendance.find_one({"id": open_entry["id"]}, {"_id": 0})


@router.get("/attendance/me/active")
async def attendance_active(current_user: dict = Depends(get_current_user)):
    """Return the user's currently-open clock-in (or null)."""
    entry = await db.hr_attendance.find_one({
        "staff_id": current_user["id"],
        "check_out_time": None,
    }, {"_id": 0})
    return entry  # may be null


@router.get("/attendance")
async def list_attendance(
    staff_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """List attendance entries. Non-HR users see only their own."""
    query = {}
    if staff_id and _require_hr_access(current_user):
        query["staff_id"] = staff_id
    elif not _require_hr_access(current_user):
        query["staff_id"] = current_user["id"]
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    if date_from or date_to:
        date_q = {}
        if date_from:
            date_q["$gte"] = date_from[:10]
        if date_to:
            date_q["$lte"] = date_to[:10]
        query["date"] = date_q
    return await db.hr_attendance.find(query, {"_id": 0}).sort("check_in_time", -1).to_list(min(limit, 1000))


@router.put("/attendance/{entry_id}")
async def update_attendance(entry_id: str, data: dict, current_user: dict = Depends(require_director)):
    """HR/director correction of an attendance entry (e.g. forgotten clock-out).
    Body: { check_in_time?, check_out_time?, notes? }"""
    allowed = {"check_in_time", "check_out_time", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "check_in_time" in update and "check_out_time" in update:
        try:
            ci = datetime.fromisoformat(update["check_in_time"].replace("Z", "+00:00"))
            co = datetime.fromisoformat(update["check_out_time"].replace("Z", "+00:00"))
            update["duration_minutes"] = max(0, int((co - ci).total_seconds() / 60))
        except Exception:
            pass
    update["edited_by"] = current_user["id"]
    update["edited_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_attendance.update_one({"id": entry_id}, {"$set": update})
    return await db.hr_attendance.find_one({"id": entry_id}, {"_id": 0})


@router.delete("/attendance/{entry_id}")
async def delete_attendance(entry_id: str, current_user: dict = Depends(require_director)):
    await db.hr_attendance.delete_one({"id": entry_id})
    return {"deleted": True}


@router.get("/attendance/summary")
async def attendance_summary(period: Optional[str] = None, current_user: dict = Depends(require_hr)):
    """Per-staff hours summary for a YYYY-MM (defaults to current). Returns: [{staff_id, name, total_minutes, days_present, entries_count}]"""
    period = period or datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{period}-01"
    y, m = map(int, period.split("-"))
    nm_y, nm_m = (y, m + 1) if m < 12 else (y + 1, 1)
    end = f"{nm_y:04d}-{nm_m:02d}-01"
    query = {"date": {"$gte": start, "$lt": end}, "check_out_time": {"$ne": None}}
    campus = await get_campus_filter(current_user)
    if campus:
        query.update(campus)
    rows = await db.hr_attendance.find(query, {"_id": 0}).to_list(5000)
    by_staff = {}
    for r in rows:
        sid = r.get("staff_id")
        if not sid:
            continue
        d = by_staff.setdefault(sid, {"staff_id": sid, "staff_name": r.get("staff_name"), "total_minutes": 0, "days_present": set(), "entries_count": 0})
        d["total_minutes"] += int(r.get("duration_minutes") or 0)
        d["days_present"].add(r.get("date"))
        d["entries_count"] += 1
    return [
        {**v, "days_present": len(v["days_present"]), "total_hours": round(v["total_minutes"] / 60, 2)}
        for v in by_staff.values()
    ]



# ========== COMPENSATION SUMMARY PDF (year-end statement) ==========

@router.get("/staff/{staff_id}/compensation-summary")
async def compensation_summary(staff_id: str, year: Optional[int] = None, format: str = "pdf", current_user: dict = Depends(get_current_user)):
    """Per-staff year-end compensation statement aggregating:
      • salary on file & history (changes within the year)
      • payslips issued & total net paid
      • leave usage by type
      • reimbursements paid
    Self-only access for the staff member; HR/director for anyone.
    `format=json` for machine consumption, otherwise returns a PDF."""
    target_id = staff_id
    if target_id != current_user["id"] and not _require_hr_access(current_user):
        raise HTTPException(status_code=403, detail="Not permitted")
    user = await db.users.find_one({"id": target_id}, {"_id": 0, "id": 1, "name": 1, "role": 1, "department": 1, "location_id": 1, "email": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    yr = int(year or datetime.now(timezone.utc).year)
    y_start = f"{yr}-01-01"
    y_end = f"{yr}-12-31"
    # Salary current + history
    current_salary = await db.hr_salaries.find_one({"staff_id": target_id, "status": "active"}, {"_id": 0})
    history = await db.hr_salary_history.find({
        "staff_id": target_id,
        "changed_at": {"$gte": y_start + "T00:00:00", "$lte": y_end + "T23:59:59"},
    }, {"_id": 0}).sort("changed_at", 1).to_list(100)
    # Payslips
    payslips = await db.hr_payslips.find({
        "staff_id": target_id,
        "period": {"$gte": f"{yr}-01", "$lte": f"{yr}-12"},
    }, {"_id": 0}).sort("period", 1).to_list(50)
    total_net = sum(float(p.get("net_salary") or 0) for p in payslips)
    total_gross = sum(float(p.get("gross_salary") or 0) for p in payslips)
    total_deductions = sum(float(p.get("deductions") or 0) for p in payslips)
    # Leave usage
    leave_used = {}
    async for lr in db.hr_leave_requests.find({
        "staff_id": target_id,
        "status": "approved",
        "start_date": {"$lte": y_end},
        "end_date": {"$gte": y_start},
    }, {"_id": 0}):
        leave_used[lr.get("leave_type")] = leave_used.get(lr.get("leave_type"), 0) + (lr.get("days") or 0)
    # Reimbursements
    reimbursed = await db.hr_employee_expenses.find({
        "staff_id": target_id,
        "status": "reimbursed",
        "date": {"$gte": y_start, "$lte": y_end},
    }, {"_id": 0}).sort("date", 1).to_list(500)
    total_reimbursed = sum(float(r.get("amount") or 0) for r in reimbursed)
    summary = {
        "staff": user,
        "year": yr,
        "current_salary": current_salary,
        "salary_history": history,
        "payslips": payslips,
        "totals": {
            "gross_paid": total_gross,
            "deductions": total_deductions,
            "net_paid": total_net,
            "reimbursed": total_reimbursed,
            "total_compensation": total_net + total_reimbursed,
        },
        "leave_used": leave_used,
        "reimbursements": reimbursed,
    }
    if format == "json":
        return summary
    # ---- Render PDF ----
    rows_payslips = "".join(
        f"<tr><td>{p.get('period')}</td><td>{p.get('currency','UGX')} {float(p.get('gross_salary') or 0):,.2f}</td>"
        f"<td>{float(p.get('deductions') or 0):,.2f}</td>"
        f"<td style='font-weight:700'>{float(p.get('net_salary') or 0):,.2f}</td>"
        f"<td>{p.get('status','')}</td></tr>"
        for p in payslips
    ) or "<tr><td colspan='5' style='text-align:center;color:#64748b;padding:14px'>No payslips for this year.</td></tr>"
    rows_history = "".join(
        f"<tr><td>{h.get('changed_at','')[:10]}</td><td>{h.get('changed_by_name','')}</td><td>{', '.join(h.get('changes',{}).keys())}</td><td>{h.get('reason','') or '—'}</td></tr>"
        for h in history
    ) or "<tr><td colspan='4' style='text-align:center;color:#64748b;padding:10px'>No salary changes this year.</td></tr>"
    rows_leave = "".join(
        f"<tr><td>{lt}</td><td>{days}</td></tr>" for lt, days in leave_used.items()
    ) or "<tr><td colspan='2' style='text-align:center;color:#64748b;padding:10px'>No leave taken this year.</td></tr>"
    rows_reim = "".join(
        f"<tr><td>{r.get('date','')}</td><td>{r.get('title','')}</td><td>{r.get('category','')}</td>"
        f"<td style='text-align:right'>{r.get('currency','UGX')} {float(r.get('amount') or 0):,.2f}</td></tr>"
        for r in reimbursed
    ) or "<tr><td colspan='4' style='text-align:center;color:#64748b;padding:10px'>No reimbursements paid.</td></tr>"
    cur_sal_text = (
        f"{current_salary.get('currency','UGX')} {float(current_salary.get('base_salary') or 0):,.2f} / {current_salary.get('pay_frequency','monthly')}"
        if current_salary else "No active salary on file"
    )
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
  body {{ font-family: Arial, sans-serif; padding: 20mm; color: #1a1a2e; font-size: 11px; }}
  h1 {{ font-size: 20px; margin: 0; }}
  .accent {{ color: #48a9c5; }}
  .head {{ display:flex; justify-content:space-between; border-bottom:2px solid #1a1a2e; padding-bottom:8px; align-items:flex-start; }}
  .logo {{ height: 36px; }}
  h2 {{ font-size: 13px; margin: 20px 0 6px 0; padding-bottom: 4px; border-bottom: 1px solid #e2e8f0; color:#1a1a2e; }}
  .totals {{ background:#f5f7f9; padding:12px; border-radius:6px; margin:10px 0; display:grid; grid-template-columns:repeat(2,1fr); gap:4px 16px; }}
  .totals .label {{ color:#64748b; }}
  .totals .v {{ text-align:right; font-weight:600; }}
  .totals .grand {{ grid-column:1/3; border-top:1px solid #cbd5e1; padding-top:6px; margin-top:4px; display:flex; justify-content:space-between; font-size:13px; }}
  table {{ width:100%; border-collapse:collapse; font-size:10px; margin-top:6px; }}
  th {{ background:#1a1a2e; color:#fff; padding:5px; text-align:left; }}
  td {{ padding:4px 5px; border-bottom:1px solid #e2e8f0; }}
  .meta {{ font-size:10px; color:#64748b; }}
</style></head><body>
  <div class='head'>
    <div>
      <img src='https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1' class='logo' />
      <p class='meta' style='margin:4px 0 0 0'>58:12 Global · Confidential HR Document</p>
    </div>
    <div style='text-align:right'>
      <h1>Compensation Summary <span class='accent'>{yr}</span></h1>
      <p class='meta' style='margin:2px 0 0 0'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
  </div>
  <div style='margin-top:14px'>
    <p style='margin:0; font-size:14px; font-weight:700'>{user.get('name','')}</p>
    <p class='meta'>{user.get('role','')} · {user.get('department','') or '—'}{' · ' + user.get('email') if user.get('email') else ''}</p>
    <p class='meta'>Current salary: <strong>{cur_sal_text}</strong></p>
  </div>

  <div class='totals'>
    <div class='label'>Gross paid (year)</div><div class='v'>{total_gross:,.2f}</div>
    <div class='label'>Deductions</div><div class='v' style='color:#b45309'>−{total_deductions:,.2f}</div>
    <div class='label'>Net salary paid</div><div class='v'>{total_net:,.2f}</div>
    <div class='label'>Reimbursements paid</div><div class='v'>{total_reimbursed:,.2f}</div>
    <div class='grand'><span>Total compensation</span><span>{(total_net + total_reimbursed):,.2f}</span></div>
  </div>

  <h2>Payslips</h2>
  <table>
    <thead><tr><th>Period</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Status</th></tr></thead>
    <tbody>{rows_payslips}</tbody>
  </table>

  <h2>Salary Changes</h2>
  <table>
    <thead><tr><th>Date</th><th>Approved by</th><th>Fields</th><th>Reason</th></tr></thead>
    <tbody>{rows_history}</tbody>
  </table>

  <h2>Leave Taken (approved)</h2>
  <table>
    <thead><tr><th>Type</th><th>Days</th></tr></thead>
    <tbody>{rows_leave}</tbody>
  </table>

  <h2>Reimbursements Paid</h2>
  <table>
    <thead><tr><th>Date</th><th>Title</th><th>Category</th><th style='text-align:right'>Amount</th></tr></thead>
    <tbody>{rows_reim}</tbody>
  </table>

  <p class='meta' style='margin-top:20mm; text-align:center'>This is an automatically generated statement. For corrections contact HR.</p>
</body></html>"""
    # Use WeasyPrint (already a dependency)
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Compensation PDF render failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = (user.get('name') or 'staff').replace(' ', '_')[:30]
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="compensation-{safe_name}-{yr}.pdf"'},
    )



# ========== TIMESHEETS (staff-submitted, manager-approved) ==========
# Note: attendance/summary already exists above at line 1444 and returns a
# list of {staff_id, staff_name, total_minutes, days_present, ...}. The FE
# uses that endpoint to auto-populate days_worked in the payslip generation
# UI. This section adds staff-submitted timesheets for cases where clock-in
# data is missing or insufficient (e.g. remote work, ad-hoc contracts).

@router.get("/timesheets")
async def list_timesheets(period: Optional[str] = None, staff_id: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List timesheets scoped by role (iter214):
    - Staff → own only
    - Director/HR → limited to their location_ids
    - Admin → all"""
    q = {}
    if period:
        q["period"] = period
    if staff_id:
        q["staff_id"] = staff_id
    if status:
        q["status"] = status
    q.update(_hr_scope(current_user))
    return await db.hr_timesheets.find(q, {"_id": 0}).sort("submitted_at", -1).to_list(500)


@router.post("/timesheets")
async def submit_timesheet(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a timesheet for a pay period. Body:
    { period: 'YYYY-MM' | 'YYYY-Www', days_worked: int, pto_days?: int, notes?,
      location_id?, staff_id? (director+/admin only — submit on behalf of another user),
      entries?: [{date, hours?, day_worked?}] (optional daily breakdown) }"""
    period = (data.get("period") or "").strip()
    if not period:
        raise HTTPException(status_code=400, detail="period required")
    days_worked = float(data.get("days_worked") or 0)
    if days_worked < 0 or days_worked > 100:
        raise HTTPException(status_code=400, detail="days_worked out of range")
    # On-behalf submission — director+ can create timesheets for staff who
    # don't use the app (iter214). Regular staff always submit for themselves.
    on_behalf_of = (data.get("staff_id") or "").strip()
    if on_behalf_of and on_behalf_of != current_user["id"]:
        if not _is_hr_or_above(current_user):
            raise HTTPException(status_code=403, detail="Only director+/HR/admin can create timesheets on behalf of others")
        target = await db.users.find_one({"id": on_behalf_of}, {"_id": 0, "id": 1, "name": 1, "department": 1, "location_id": 1, "location_ids": 1, "active_campus_id": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Target staff not found")
        # Directors can only target their own location(s)
        role = (current_user.get("role") or "").lower()
        if role not in {"admin", "system_admin"}:
            allowed_locs = set(current_user.get("location_ids") or [])
            if current_user.get("active_campus_id"):
                allowed_locs.add(current_user["active_campus_id"])
            tgt_locs = set(target.get("location_ids") or [])
            if target.get("location_id"):
                tgt_locs.add(target["location_id"])
            if not allowed_locs.intersection(tgt_locs):
                raise HTTPException(status_code=403, detail="Target staff is outside your assigned locations")
        staff_id = on_behalf_of
        staff_name = target.get("name", "")
        department = target.get("department", "")
        default_loc = target.get("location_id") or (target.get("location_ids") or [""])[0]
    else:
        staff_id = current_user["id"]
        staff_name = current_user.get("name", "")
        department = current_user.get("department", "")
        default_loc = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    existing = await db.hr_timesheets.find_one({"staff_id": staff_id, "period": period, "status": {"$in": ["draft", "submitted", "rejected"]}})
    doc = {
        "id": existing["id"] if existing else f"ts_{uuid.uuid4().hex[:10]}",
        "staff_id": staff_id,
        "staff_name": staff_name,
        "department": department,
        "location_id": data.get("location_id") or default_loc,
        "period": period,
        "days_worked": days_worked,
        "pto_days": float(data.get("pto_days") or 0),
        "entries": data.get("entries") or [],  # optional daily breakdown (iter214)
        "notes": (data.get("notes") or "")[:1000],
        "status": "submitted",
        "submitted_by": current_user["id"],
        "submitted_by_name": current_user.get("name", ""),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db.hr_timesheets.update_one({"id": doc["id"]}, {"$set": doc})
    else:
        await db.hr_timesheets.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "submit" if not existing else "resubmit", "timesheet", doc["id"], {"period": period, "days_worked": days_worked})
    return doc


@router.put("/timesheets/{ts_id}/approve")
async def approve_timesheet(ts_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    ts = await db.hr_timesheets.find_one({"id": ts_id}, {"_id": 0})
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if ts.get("status") == "approved":
        return ts
    await db.hr_timesheets.update_one({"id": ts_id}, {"$set": {
        "status": "approved",
        "approved_by": current_user["id"],
        "approved_by_name": current_user.get("name", ""),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "review_notes": ((data or {}).get("notes") or "")[:500],
    }})
    await _audit(current_user["id"], "approve", "timesheet", ts_id, {"staff_id": ts["staff_id"], "period": ts["period"]})
    return await db.hr_timesheets.find_one({"id": ts_id}, {"_id": 0})


@router.put("/timesheets/{ts_id}/reject")
async def reject_timesheet(ts_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    ts = await db.hr_timesheets.find_one({"id": ts_id}, {"_id": 0})
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    await db.hr_timesheets.update_one({"id": ts_id}, {"$set": {
        "status": "rejected",
        "rejected_by": current_user["id"],
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "review_notes": ((data or {}).get("reason") or "Please revise")[:500],
    }})
    return await db.hr_timesheets.find_one({"id": ts_id}, {"_id": 0})


@router.delete("/timesheets/{ts_id}")
async def delete_timesheet(ts_id: str, current_user: dict = Depends(get_current_user)):
    ts = await db.hr_timesheets.find_one({"id": ts_id}, {"_id": 0})
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    # Staff can only delete their own drafts / rejected
    role = (current_user.get("role") or "").lower()
    is_hr = role in {"admin", "system_admin", "hr", "director", "executive director"}
    if not is_hr:
        if ts["staff_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not your timesheet")
        if ts.get("status") == "approved":
            raise HTTPException(status_code=400, detail="Approved timesheets cannot be deleted — contact HR")
    await db.hr_timesheets.delete_one({"id": ts_id})
    return {"deleted": True}


# ========== TIME-OFF REQUESTS (iter214) ==========
# Users request PTO; director+ approves.  Window rule: request date must be
# within ±7 days of the requested PTO date (either advance notice OR
# retroactive grace).  Admins can override with `admin_override=True`.

@router.get("/time-off")
async def list_time_off(status: Optional[str] = None, staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List PTO requests, scoped by role (same as timesheets)."""
    q = {}
    if status:
        q["status"] = status
    if staff_id:
        q["staff_id"] = staff_id
    q.update(_hr_scope(current_user))
    return await db.hr_time_off.find(q, {"_id": 0}).sort("submitted_at", -1).to_list(500)


@router.post("/time-off")
async def request_time_off(data: dict, current_user: dict = Depends(get_current_user)):
    """Request paid time-off. Body:
    { start_date: 'YYYY-MM-DD', end_date: 'YYYY-MM-DD', reason?, admin_override?, staff_id? }

    Window rule: without admin_override, the requested date must be within
    ±7 days of today (advance notice OR retroactive grace).  Admin can
    override in emergencies."""
    from datetime import date, timedelta
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or start_date).strip()
    if not start_date:
        raise HTTPException(status_code=400, detail="start_date required (YYYY-MM-DD)")
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format — use YYYY-MM-DD")
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    admin_override = bool(data.get("admin_override"))
    is_admin = (current_user.get("role") or "").lower() in {"admin", "system_admin"}
    if admin_override and not is_admin:
        raise HTTPException(status_code=403, detail="Only admins can use admin_override")
    # ±7-day window check unless overridden
    if not admin_override:
        today = date.today()
        # Fail if EITHER endpoint is more than 7 days away in either direction
        for check_date in (sd, ed):
            delta_days = abs((check_date - today).days)
            if delta_days > 7:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Time-off request for {check_date.isoformat()} is {delta_days} days from today. "
                        f"Must be within 7 days (advance notice or retroactive grace). "
                        f"Contact an admin for an override in emergencies."
                    ),
                )
    # On-behalf submission — director+ can request PTO for their location staff
    on_behalf_of = (data.get("staff_id") or "").strip()
    if on_behalf_of and on_behalf_of != current_user["id"]:
        if not _is_hr_or_above(current_user):
            raise HTTPException(status_code=403, detail="Only director+/HR/admin can request PTO on behalf of others")
        target = await db.users.find_one({"id": on_behalf_of}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "location_ids": 1})
        if not target:
            raise HTTPException(status_code=404, detail="Target staff not found")
        if not is_admin:
            allowed_locs = set(current_user.get("location_ids") or [])
            if current_user.get("active_campus_id"):
                allowed_locs.add(current_user["active_campus_id"])
            tgt_locs = set(target.get("location_ids") or [])
            if target.get("location_id"):
                tgt_locs.add(target["location_id"])
            if not allowed_locs.intersection(tgt_locs):
                raise HTTPException(status_code=403, detail="Target staff is outside your assigned locations")
        staff_id = on_behalf_of
        staff_name = target.get("name", "")
        default_loc = target.get("location_id") or (target.get("location_ids") or [""])[0]
    else:
        staff_id = current_user["id"]
        staff_name = current_user.get("name", "")
        default_loc = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    days = (ed - sd).days + 1
    doc = {
        "id": f"pto_{uuid.uuid4().hex[:10]}",
        "staff_id": staff_id,
        "staff_name": staff_name,
        "location_id": default_loc,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "reason": (data.get("reason") or "")[:500],
        "admin_override": admin_override,
        "status": "pending",
        "submitted_by": current_user["id"],
        "submitted_by_name": current_user.get("name", ""),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hr_time_off.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "request", "time_off", doc["id"], {"staff_id": staff_id, "days": days})
    return doc


@router.put("/time-off/{pto_id}/approve")
async def approve_time_off(pto_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    pto = await db.hr_time_off.find_one({"id": pto_id}, {"_id": 0})
    if not pto:
        raise HTTPException(status_code=404, detail="Time-off request not found")
    if pto.get("status") == "approved":
        return pto
    await db.hr_time_off.update_one({"id": pto_id}, {"$set": {
        "status": "approved",
        "approved_by": current_user["id"],
        "approved_by_name": current_user.get("name", ""),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "review_notes": ((data or {}).get("notes") or "")[:500],
    }})
    await _audit(current_user["id"], "approve", "time_off", pto_id, {"staff_id": pto["staff_id"], "days": pto.get("days")})
    return await db.hr_time_off.find_one({"id": pto_id}, {"_id": 0})


@router.put("/time-off/{pto_id}/reject")
async def reject_time_off(pto_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    pto = await db.hr_time_off.find_one({"id": pto_id}, {"_id": 0})
    if not pto:
        raise HTTPException(status_code=404, detail="Time-off request not found")
    await db.hr_time_off.update_one({"id": pto_id}, {"$set": {
        "status": "rejected",
        "rejected_by": current_user["id"],
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "review_notes": ((data or {}).get("reason") or "")[:500],
    }})
    await _audit(current_user["id"], "reject", "time_off", pto_id, {"staff_id": pto["staff_id"]})
    return await db.hr_time_off.find_one({"id": pto_id}, {"_id": 0})


@router.delete("/time-off/{pto_id}")
async def delete_time_off(pto_id: str, current_user: dict = Depends(get_current_user)):
    pto = await db.hr_time_off.find_one({"id": pto_id}, {"_id": 0})
    if not pto:
        raise HTTPException(status_code=404, detail="Time-off request not found")
    if not _is_hr_or_above(current_user) and pto["staff_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your request")
    if pto.get("status") == "approved" and not _is_hr_or_above(current_user):
        raise HTTPException(status_code=400, detail="Approved PTO cannot be deleted — contact HR")
    await db.hr_time_off.delete_one({"id": pto_id})
    return {"deleted": True}


# ========== MY PAYSLIPS (staff self-service) ==========

@router.get("/payslips/mine")
async def my_payslips(limit: int = 50, current_user: dict = Depends(get_current_user)):
    """Return payslips for the currently authenticated user (self-service)."""
    return await db.hr_payslips.find({"staff_id": current_user["id"]}, {"_id": 0}).sort("period", -1).limit(limit).to_list(limit)


# ========== PAYSLIP EDIT + AUDIT TRAIL (iter209b) ==========

@router.get("/payslips/{payslip_id}/history")
async def get_payslip_history(payslip_id: str, current_user: dict = Depends(require_hr)):
    """Fetch the edit history (audit trail) for a payslip."""
    p = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0, "edit_history": 1, "created_at": 1, "created_by_name": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Payslip not found")
    return {
        "created_at": p.get("created_at"),
        "created_by_name": p.get("created_by_name"),
        "history": p.get("edit_history") or [],
    }


# ========== PAYSLIP BULK EXPORT (ZIP of PDFs + CSV) ==========

@router.get("/payslips/export.csv")
async def export_payslips_csv(
    period: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Director+ can export all payslips for a given period (YYYY-MM) as CSV."""
    from fastapi.responses import Response
    import csv
    import io
    q: dict = {}
    if period:
        q["period"] = period
    if location_id:
        q["location_id"] = location_id
    docs = await db.hr_payslips.find(q, {"_id": 0}).sort([("period", -1), ("staff_name", 1)]).to_list(2000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Period", "Staff Name", "Department", "Location", "Currency",
        "Gross", "Allowances", "Deductions", "Net", "Status", "Paid At", "Notes", "Payslip ID",
    ])
    for p in docs:
        writer.writerow([
            p.get("period", ""), p.get("staff_name", ""), p.get("department", ""), p.get("location_id", ""),
            p.get("currency", ""),
            p.get("gross_salary", 0), p.get("allowances", 0), p.get("deductions", 0), p.get("net_salary", 0),
            p.get("status", ""), p.get("paid_at", ""), (p.get("notes") or "")[:200], p.get("id", ""),
        ])
    csv_data = buf.getvalue()
    fname = f"payslips_{period or 'all'}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/payslips/export.zip")
async def export_payslips_zip(
    period: Optional[str] = None,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_director),
):
    """Director+ can bundle every payslip PDF for a period into a single ZIP."""
    from fastapi.responses import Response
    import io
    import zipfile
    q: dict = {}
    if period:
        q["period"] = period
    if location_id:
        q["location_id"] = location_id
    docs = await db.hr_payslips.find(q, {"_id": 0, "id": 1, "staff_name": 1, "period": 1}).to_list(2000)
    if not docs:
        raise HTTPException(status_code=404, detail="No payslips found for the given filters")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in docs:
            try:
                pdf_bytes = await _generate_payslip_pdf_bytes(p["id"])
                safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (p.get("staff_name") or "unknown"))
                fname = f"{p.get('period','')}_{safe_name}_{p['id']}.pdf"
                z.writestr(fname, pdf_bytes)
            except Exception as e:
                logger.warning(f"Skipping payslip {p.get('id')} in ZIP export: {e}")
    zip_bytes = buf.getvalue()
    zip_name = f"payslips_{period or 'all'}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"},
    )


@router.get("/payslips/{payslip_id}/mine")
async def get_my_payslip(payslip_id: str, current_user: dict = Depends(get_current_user)):
    """Staff can fetch only their own payslip."""
    p = await db.hr_payslips.find_one({"id": payslip_id, "staff_id": current_user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payslip not found")
    return p



# ========== PAYSLIP PDF EXPORT ==========

async def _generate_payslip_pdf_bytes(payslip_id: str) -> bytes:
    """Render a payslip to PDF bytes.  Used by both the per-payslip endpoint
    and the director+ bulk-ZIP export.  Raises HTTPException if not found."""
    p = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payslip not found")
    loc_name = ""
    if p.get("location_id"):
        loc = await db.locations.find_one({"id": p["location_id"]}, {"_id": 0, "name": 1})
        if loc:
            loc_name = loc.get("name") or ""
    cur = p.get("currency") or "UGX"
    def fmt(x): return f"{cur} {(x or 0):,.2f}"
    line_rows = ""
    for li in (p.get("line_items") or []):
        sign = "&minus;" if li.get("type") == "deduction" else "+"
        color = "#b45309" if li.get("type") == "deduction" else "#047857"
        amt = li.get("calculated_amount", li.get("amount", 0)) or 0
        details = f" <span class='meta'>({li['details']})</span>" if li.get("details") else ""
        line_rows += f"<tr><td>{li.get('name','')}{details}</td><td style='text-align:right;color:{color}'>{sign}{amt:,.2f}</td></tr>"
    if not line_rows:
        line_rows = "<tr><td colspan='2' style='text-align:center;color:#94a3b8'>No adjustments</td></tr>"
    paid_note = ""
    if p.get("status") == "paid" and p.get("paid_at"):
        paid_note = f"<p class='meta' style='text-align:center;margin-top:14mm'>Paid on {p['paid_at'][:10]}</p>"
    html = f"""<html><head><meta charset='utf-8' /><style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color:#0f172a; }}
.head {{ display:flex; justify-content:space-between; align-items:flex-start; padding-bottom:10px; border-bottom:2px solid #0f172a; }}
.logo {{ height:38px; }}
h1 {{ font-size:22px; margin:0; }}
h2 {{ font-size:13px; margin:16px 0 6px 0; text-transform:uppercase; letter-spacing:0.4px; color:#334155; border-bottom:1px solid #e2e8f0; padding-bottom:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:11.5px; }}
th, td {{ padding:6px 8px; border-bottom:1px solid #e2e8f0; text-align:left; }}
th {{ font-size:10.5px; color:#64748b; background:#f8fafc; }}
.meta {{ font-size:10px; color:#64748b; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 20px; font-size:11px; margin-top:8px; }}
.grid .k {{ color:#64748b; }}
.summary {{ margin-top:14px; padding:10px 12px; background:#f1f5f9; border-radius:6px; }}
.row {{ display:flex; justify-content:space-between; padding:3px 0; font-size:12px; }}
.total {{ display:flex; justify-content:space-between; padding:8px 0 0; margin-top:8px; border-top:2px solid #0f172a; font-size:16px; font-weight:700; }}
.status {{ display:inline-block; padding:2px 8px; border-radius:99px; font-size:10px; font-weight:600; text-transform:uppercase; background:#e2e8f0; color:#0f172a; }}
.status.paid {{ background:#dcfce7; color:#166534; }}
.status.draft {{ background:#fef3c7; color:#92400e; }}
</style></head><body>
  <div class='head'>
    <div>
      <img src='https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1' class='logo' />
      <p class='meta' style='margin:6px 0 0 0'>58:12 Global &middot; Payslip</p>
    </div>
    <div style='text-align:right'>
      <h1>Payslip &middot; {p.get('period','')}</h1>
      <p class='meta' style='margin:2px 0 0 0'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p style='margin:6px 0 0 0'><span class='status {p.get("status","")}'>{p.get('status','draft')}</span></p>
    </div>
  </div>
  <div class='grid'>
    <div><span class='k'>Staff:</span> <strong>{p.get('staff_name','')}</strong></div>
    <div><span class='k'>Payslip ID:</span> {p.get('id','')}</div>
    <div><span class='k'>Department:</span> {p.get('department','') or '&mdash;'}</div>
    <div><span class='k'>Location:</span> {loc_name or p.get('location_id','') or '&mdash;'}</div>
    <div><span class='k'>Period:</span> {p.get('period','')}</div>
    <div><span class='k'>Currency:</span> {cur}</div>
    <div><span class='k'>Working days:</span> {p.get('working_days','&mdash;')}</div>
    <div><span class='k'>Days worked:</span> {p.get('days_worked','&mdash;')}</div>
    <div><span class='k'>Unpaid leave days:</span> {p.get('unpaid_leave_days',0)}</div>
    <div><span class='k'>PTO days:</span> {p.get('pto_days',0)}</div>
  </div>
  <h2>Line Items</h2>
  <table>
    <thead><tr><th>Description</th><th style='text-align:right'>Amount</th></tr></thead>
    <tbody>{line_rows}</tbody>
  </table>
  <div class='summary'>
    <div class='row'><span>Gross salary</span><span>{fmt(p.get('gross_salary'))}</span></div>
    <div class='row' style='color:#047857'><span>+ Allowances</span><span>{fmt(p.get('allowances'))}</span></div>
    <div class='row' style='color:#b45309'><span>&minus; Deductions</span><span>{fmt(p.get('deductions'))}</span></div>
    <div class='total'><span>Net Pay</span><span>{fmt(p.get('net_salary'))}</span></div>
  </div>
  {paid_note}
  <p class='meta' style='margin-top:18mm; text-align:center'>This payslip is automatically generated. For corrections contact HR.</p>
</body></html>"""
    from weasyprint import HTML
    try:
        return HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Payslip PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")


@router.get("/payslips/{payslip_id}/pdf")
async def payslip_pdf(payslip_id: str, current_user: dict = Depends(get_current_user)):
    """Server-rendered payslip PDF. Access: HR/Director+/Admin + the owning staff member."""
    p = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0, "staff_id": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Payslip not found")
    role = (current_user.get("role") or "").lower()
    is_hr = role in {"admin", "system_admin", "hr", "director", "executive director"}
    if not is_hr and p.get("staff_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your payslip")
    pdf = await _generate_payslip_pdf_bytes(payslip_id)
    p_full = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0, "staff_name": 1, "period": 1})
    from starlette.responses import StreamingResponse
    import io
    safe_name = ((p_full or {}).get("staff_name") or "staff").replace(" ", "_")[:30]
    filename = f"payslip-{safe_name}-{(p_full or {}).get('period','')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ========== ONBOARDING CHECKLIST ==========

@router.get("/onboarding/checklist")
async def onboarding_checklist(location_id: Optional[str] = None, current_user: dict = Depends(require_hr)):
    """Per-staff onboarding completeness (contract, salary, chart-account, dept, location)."""
    user_query = {"active": {"$ne": False}, "role": {"$ne": "system_admin"}}
    if location_id:
        user_query["$or"] = [{"location_id": location_id}, {"location_ids": location_id}, {"active_campus_id": location_id}]
    users = await db.users.find(user_query, {
        "_id": 0, "id": 1, "name": 1, "email": 1, "role": 1,
        "department": 1, "location_id": 1, "active_campus_id": 1, "location_ids": 1,
    }).to_list(2000)

    salaries_map = {}
    async for s in db.hr_salaries.find({"status": "active"}, {"_id": 0, "staff_id": 1, "base_salary": 1, "currency": 1, "pay_frequency": 1}):
        salaries_map[s["staff_id"]] = s

    contract_ids = set()
    async for c in db.hr_contracts.find({"status": {"$in": ["signed", "active"]}}, {"_id": 0, "staff_id": 1}):
        contract_ids.add(c["staff_id"])

    account_users = set()
    async for a in db.chart_accounts.find({"active": {"$ne": False}}, {"_id": 0, "assigned_user_ids": 1}):
        for uid in (a.get("assigned_user_ids") or []):
            account_users.add(uid)

    rows = []
    for u in users:
        checks = {
            "has_department": bool(u.get("department")),
            "has_location": bool(u.get("active_campus_id") or u.get("location_id") or (u.get("location_ids") or [])),
            "has_contract": u["id"] in contract_ids,
            "has_salary": u["id"] in salaries_map,
            "has_chart_account": u["id"] in account_users,
        }
        completion_pct = round(sum(1 for v in checks.values() if v) / len(checks) * 100)
        sal = salaries_map.get(u["id"])
        rows.append({
            "staff_id": u["id"],
            "staff_name": u.get("name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
            "department": u.get("department", ""),
            "location_id": u.get("active_campus_id") or u.get("location_id") or "",
            "checks": checks,
            "completion_pct": completion_pct,
            "salary_summary": f"{sal.get('currency','UGX')} {sal.get('base_salary',0):,.0f} / {sal.get('pay_frequency','monthly')}" if sal else "",
        })
    rows.sort(key=lambda r: (r["completion_pct"], r["staff_name"].lower()))
    return {
        "total": len(rows),
        "fully_onboarded": sum(1 for r in rows if r["completion_pct"] == 100),
        "needs_attention": sum(1 for r in rows if r["completion_pct"] < 100),
        "rows": rows,
    }
