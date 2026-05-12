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


async def _generate_payslips_for(period: str, location_id: str, current_user: dict) -> dict:
    """Shared helper: generate missing payslips for a period + optional location."""
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    salaries = await db.hr_salaries.find(query, {"_id": 0}).to_list(500)
    generated = []
    for sal in salaries:
        existing = await db.hr_payslips.find_one({"salary_id": sal["id"], "period": period})
        if existing:
            continue
        gross = sal.get("base_salary", 0)
        deductions = 0
        allowances = 0
        items = []
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
        net = gross + allowances - deductions
        payslip = {
            "id": f"ps_{uuid.uuid4().hex[:8]}",
            "salary_id": sal["id"],
            "staff_id": sal["staff_id"],
            "staff_name": sal.get("staff_name", ""),
            "department": sal.get("department", ""),
            "location_id": sal.get("location_id", ""),
            "period": period,
            "gross_salary": gross,
            "allowances": allowances,
            "deductions": deductions,
            "net_salary": net,
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
