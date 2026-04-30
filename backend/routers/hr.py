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
    allowed = {"hr_enabled", "pay_frequency", "currency", "country", "tax_rules", "benefits", "deduction_types", "pay_day"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["location_id"] = location_id
    await db.hr_settings.update_one({"location_id": location_id}, {"$set": update}, upsert=True)
    return await db.hr_settings.find_one({"location_id": location_id}, {"_id": 0})


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
    allowed = {"base_salary", "currency", "pay_frequency", "effective_date", "line_items", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_salaries.update_one({"id": salary_id}, {"$set": update})
    return await db.hr_salaries.find_one({"id": salary_id}, {"_id": 0})


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
    # Get active salaries for this location
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    salaries = await db.hr_salaries.find(query, {"_id": 0}).to_list(500)
    generated = []
    for sal in salaries:
        # Check if already generated
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


@router.put("/payslips/{payslip_id}")
async def update_payslip(payslip_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"status", "notes", "approved_by"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("status") == "approved":
        update["approved_by"] = current_user["id"]
        update["approved_at"] = datetime.now(timezone.utc).isoformat()
    await db.hr_payslips.update_one({"id": payslip_id}, {"$set": update})
    return await db.hr_payslips.find_one({"id": payslip_id}, {"_id": 0})


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
