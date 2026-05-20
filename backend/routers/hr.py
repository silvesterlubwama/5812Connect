"""HR Module: contracts, salaries, payslips, document requests, per-campus settings"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_staff, require_manager, require_director, require_admin, _audit, logger, get_campus_filter, get_role_level
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/hr", tags=["hr"])


def _require_hr_access(user: dict):
    """Check if user has HR access: HR role, finance dept, or director+"""
    role = user.get("role", "")
    dept = (user.get("department") or "").lower()
    depts = [d.lower() for d in (user.get("departments") or [])]
    if role in ("HR", "hr"):
        return True
    if "hr" in depts or "human resources" in depts or "finance" in depts or dept in ("hr", "human resources", "finance"):
        return True
    if get_role_level(role) >= 8:  # Director+
        return True
    return False


async def require_hr(current_user: dict = Depends(get_current_user)):
    if not _require_hr_access(current_user):
        raise HTTPException(status_code=403, detail="HR access required")
    return current_user


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
async def list_payslips(staff_id: Optional[str] = None, period: Optional[str] = None, current_user: dict = Depends(require_hr)):
    query = {}
    if staff_id:
        query["staff_id"] = staff_id
    if period:
        query["period"] = period
    campus = await get_campus_filter(current_user)
    if campus:
        query.update(campus)
    return await db.hr_payslips.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/payslips/generate")
async def generate_payslips(data: dict, current_user: dict = Depends(require_director)):
    """Generate payslips for a pay period. Body: {period: '2026-02', location_id?}"""
    period = data.get("period", "")
    location_id = data.get("location_id") or current_user.get("active_campus_id", "")
    if not period:
        raise HTTPException(status_code=400, detail="Pay period required (e.g. 2026-02)")
    return await _generate_payslips_for(period, location_id, current_user)


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


async def _generate_payslips_for(period: str, location_id: str, current_user: dict) -> dict:
    """Shared helper: generate missing payslips for a period + optional location.
    Applies automatic unpaid-leave proration: gross is reduced by (unpaid_days / working_days)
    and a transparent line-item 'Unpaid leave proration' is added so payslip math is auditable."""
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
        # ---- Unpaid leave proration (NEW) ----
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
        # (deductions already includes the unpaid-leave proration)
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
    """Update a payslip status / notes / mark-paid. When status becomes 'paid', the system
    aggregates this payment into a SINGLE daily expense line for the location (NO individual
    staff names exposed in the financial expense — only the total + count of staff)."""
    payslip = await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found")
    allowed = {"status", "notes", "approved_by", "paid_at", "paid_by"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("status") == "approved":
        update["approved_by"] = current_user["id"]
        update["approved_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("status") == "paid":
        update["paid_by"] = current_user["id"]
        update["paid_at"] = datetime.now(timezone.utc).isoformat()
        # Aggregate into a daily payroll expense for the location (no staff names)
        await _aggregate_payroll_expense(payslip, current_user)
    await db.hr_payslips.update_one({"id": payslip_id}, {"$set": update})
    return await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})


async def _aggregate_payroll_expense(payslip: dict, current_user: dict):
    """Upsert ONE expense line per (location, date) that totals all paid payslips that day.
    Notes show "Payroll for N staff, period YYYY-MM" — no individual staff names."""
    loc_id = payslip.get("location_id") or current_user.get("active_campus_id") or ""
    if not loc_id:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    period = payslip.get("period", "")
    expense_id = f"payroll_{loc_id}_{today}"
    net = float(payslip.get("net_salary") or 0)
    # Check if today's payroll expense already exists
    existing = await db.expenses.find_one({"id": expense_id})
    if existing:
        new_total = float(existing.get("amount", 0)) + net
        new_count = int(existing.get("payroll_count", 0)) + 1
        await db.expenses.update_one({"id": expense_id}, {"$set": {
            "amount": new_total,
            "payroll_count": new_count,
            "notes": f"Payroll for {new_count} staff, period {period}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
    else:
        await db.expenses.insert_one({
            "id": expense_id,
            "title": "Payroll (Wages & Salaries)",
            "amount": net,
            "currency": payslip.get("currency") or "UGX",
            "category": "Wages & Salaries",
            "department": "HR",
            "budget_category": "Wages & Salaries",
            "date": today,
            "notes": f"Payroll for 1 staff, period {period}",
            "location_id": loc_id,
            "status": "approved",
            "source": "hr_payroll_aggregate",
            "payroll_count": 1,
            "payroll_period": period,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        })


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
    return doc


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

