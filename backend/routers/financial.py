"""Financial routes: donations, expenses, products, sales, cashflow, balance, approval workflow"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, require_staff, require_manager, require_director, require_admin, _audit, logger, is_system_admin, get_campus_filter, get_role_level
from datetime import datetime, timezone
from typing import Optional, List
import uuid

async def _financial_campus_filter(user: dict) -> dict:
    """Financial data access: finance department staff or managers+ in the location.
    Advisers/EDs/admins see everything."""
    if is_system_admin(user):
        return {}
    depts = user.get("departments") or []
    dept = user.get("department") or ""
    is_finance = "finance" in [d.lower() for d in depts] or "finance" in dept.lower()
    role_level = {"Manager": 7, "Coordinator": 6, "Staff": 5, "Volunteer": 4}.get(user.get("role"), 0)
    if role_level >= 7 or is_finance:
        return await get_campus_filter(user)
    # Staff without finance dept: no financial visibility
    return {"location_id": "__no_access__"}


router = APIRouter(prefix="/api", tags=["financial"])


class DonationCreate(BaseModel):
    donor_name: str; amount: float; currency: str = "UGX"; type: str = "tithe"
    date: Optional[str] = None; notes: Optional[str] = None; member_id: Optional[str] = None; location_id: Optional[str] = None

class ExpenseCreate(BaseModel):
    title: str; amount: float; currency: str = "UGX"; category: str = "general"
    date: Optional[str] = None; notes: Optional[str] = None; submitted_by: Optional[str] = None; location_id: Optional[str] = None

class ProductCreate(BaseModel):
    name: str; description: Optional[str] = None; price: float; currency: str = "UGX"; stock: int = 0
    category: Optional[str] = None; sku: Optional[str] = None; reorder_level: int = 5; location_id: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; price: Optional[float] = None
    stock: Optional[int] = None; category: Optional[str] = None; reorder_level: Optional[int] = None; location_id: Optional[str] = None

class SaleCreate(BaseModel):
    items: List[dict]; customer_name: Optional[str] = "Walk-in Customer"; customer_phone: Optional[str] = None
    total: float; payment_method: str = "cash"; notes: Optional[str] = None; location_id: Optional[str] = None


# ========== FINANCIAL SUMMARY ==========

@router.get("/financial/summary")
async def financial_summary(location_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1).isoformat()[:7]
    # Build location filter from campus context
    campus = await get_campus_filter(current_user)
    if location_id:
        loc_match = {"location_id": location_id}
    elif campus:
        loc_match = campus
    else:
        loc_match = {}
    donations_result = await db.donations.aggregate([{"$match": {**loc_match, "date": {"$regex": f"^{month_start}"}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    expenses_result = await db.expenses.aggregate([{"$match": {**loc_match, "date": {"$regex": f"^{month_start}"}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    sales_result = await db.sales.aggregate([{"$match": {**loc_match, "created_at": {"$regex": f"^{month_start}"}}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    monthly_donations = donations_result[0]["total"] if donations_result else 0
    monthly_expenses = expenses_result[0]["total"] if expenses_result else 0
    monthly_sales = sales_result[0]["total"] if sales_result else 0
    all_donations = await db.donations.aggregate([{"$match": loc_match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_expenses = await db.expenses.aggregate([{"$match": loc_match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
    all_sales = await db.sales.aggregate([{"$match": loc_match}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
    total_in = (all_donations[0]["total"] if all_donations else 0) + (all_sales[0]["total"] if all_sales else 0)
    total_out = all_expenses[0]["total"] if all_expenses else 0
    return {"monthly_donations": monthly_donations, "monthly_expenses": monthly_expenses, "monthly_sales": monthly_sales, "cashflow_in": total_in, "cashflow_out": total_out, "net_balance": total_in - total_out}


@router.post("/financial/distribute-funds")
async def distribute_funds(data: dict, current_user: dict = Depends(require_director)):
    from_location_id = data.get("from_location_id"); to_location_id = data.get("to_location_id")
    amount = float(data.get("amount", 0)); currency = data.get("currency", "UGX"); notes = data.get("notes", "")
    exchange_rate = float(data.get("exchange_rate", 1.0))
    receiving_currency = data.get("receiving_currency", currency)
    if amount <= 0: raise HTTPException(status_code=400, detail="Amount must be > 0")
    receiving_amount = round(amount * exchange_rate, 2) if exchange_rate != 1.0 else amount
    transfer_id = f"tfr_{str(uuid.uuid4())[:8]}"; now = datetime.now(timezone.utc).isoformat()
    rate_note = f" (Rate: {exchange_rate} {currency}→{receiving_currency})" if exchange_rate != 1.0 else ""
    await db.expenses.insert_one({"id": f"exp_{str(uuid.uuid4())[:8]}", "title": f"Fund transfer to {to_location_id}", "amount": amount, "currency": currency, "category": "transfer", "date": now[:10], "notes": f"Transfer {transfer_id}: {notes}{rate_note}", "location_id": from_location_id, "transfer_id": transfer_id, "exchange_rate": exchange_rate, "created_at": now, "created_by": current_user["id"]})
    await db.donations.insert_one({"id": f"don_{str(uuid.uuid4())[:8]}", "donor_name": "Internal Transfer", "amount": receiving_amount, "currency": receiving_currency, "type": "transfer", "date": now[:10], "notes": f"Transfer {transfer_id} from {from_location_id}: {notes}{rate_note}", "location_id": to_location_id, "transfer_id": transfer_id, "exchange_rate": exchange_rate, "original_amount": amount, "original_currency": currency, "created_at": now, "created_by": current_user["id"]})
    await _audit(current_user["id"], "create", "fund_transfer", transfer_id)
    return {"transfer_id": transfer_id, "amount": amount, "receiving_amount": receiving_amount, "exchange_rate": exchange_rate, "from": from_location_id, "to": to_location_id}


# ========== DONATIONS ==========

@router.get("/financial/donations")
async def list_donations(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**await _financial_campus_filter(current_user)}
    if location_id: query["location_id"] = location_id
    if date_from or date_to:
        query["date"] = {}
        if date_from: query["date"]["$gte"] = date_from
        if date_to: query["date"]["$lte"] = date_to
    return await db.donations.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/financial/donations")
async def create_donation(data: DonationCreate, current_user: dict = Depends(require_staff)):
    doc = {"id": f"don_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    await db.donations.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "donation", doc["id"])
    return doc


# ========== EXPENSES ==========

@router.get("/financial/expenses")
async def list_expenses(skip: int = 0, limit: int = 100, location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {**await _financial_campus_filter(current_user)}
    if location_id: query["location_id"] = location_id
    if status: query["status"] = status
    if date_from or date_to:
        query["date"] = {}
        if date_from: query["date"]["$gte"] = date_from
        if date_to: query["date"]["$lte"] = date_to
    return await db.expenses.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/financial/expenses")
async def create_expense(data: ExpenseCreate, current_user: dict = Depends(require_staff)):
    doc = {"id": f"exp_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    await db.expenses.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "expense", doc["id"])
    return doc


@router.delete("/financial/donations/{donation_id}")
async def delete_donation(donation_id: str, current_user: dict = Depends(require_admin)):
    """Admin delete a donation entry"""
    await db.donations.delete_one({"id": donation_id})
    await _audit(current_user["id"], "delete", "donation", donation_id)
    return {"message": "Donation deleted"}


@router.delete("/financial/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(require_admin)):
    """Admin delete an expense entry"""
    await db.expenses.delete_one({"id": expense_id})
    await _audit(current_user["id"], "delete", "expense", expense_id)
    return {"message": "Expense deleted"}


@router.put("/financial/donations/{donation_id}")
async def update_donation(donation_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Admin edit a donation entry"""
    allowed = {"donor_name", "amount", "currency", "type", "date", "notes", "location_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.donations.update_one({"id": donation_id}, {"$set": update})
    await _audit(current_user["id"], "update", "donation", donation_id)
    return await db.donations.find_one({"id": donation_id}, {"_id": 0})




# ========== EXPENSE APPROVAL WORKFLOW ==========

@router.get("/financial/expenses/pending")
async def list_pending_expenses(current_user: dict = Depends(require_manager)):
    expenses = await db.expenses.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return expenses


@router.put("/financial/expenses/{expense_id}/approve")
async def approve_expense(expense_id: str, data: dict = None, current_user: dict = Depends(require_director)):
    data = data or {}
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense: raise HTTPException(status_code=404, detail="Expense not found")
    update = {"status": "approved", "approved_by": current_user["id"], "approved_by_name": current_user.get("name", ""), "approved_at": datetime.now(timezone.utc).isoformat(), "approval_comment": data.get("comment", "")}
    await db.expenses.update_one({"id": expense_id}, {"$set": update})
    await _audit(current_user["id"], "update", "expense_approval", expense_id)
    if expense.get("created_by"):
        try:
            from routers.notifications import _create_notification
            await _create_notification(f"Expense Approved", f"Your expense '{expense.get('title')}' ({expense.get('amount', 0):,.0f} {expense.get('currency', 'UGX')}) has been approved by {current_user.get('name', 'admin')}.", expense.get("created_by"), "success", "/portal/expenses")
        except: pass
    return {**expense, **update}


@router.put("/financial/expenses/{expense_id}/reject")
async def reject_expense(expense_id: str, data: dict = None, current_user: dict = Depends(require_manager)):
    data = data or {}
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense: raise HTTPException(status_code=404, detail="Expense not found")
    update = {"status": "rejected", "rejected_by": current_user["id"], "rejected_by_name": current_user.get("name", ""), "rejected_at": datetime.now(timezone.utc).isoformat(), "rejection_comment": data.get("comment", "")}
    await db.expenses.update_one({"id": expense_id}, {"$set": update})
    await _audit(current_user["id"], "update", "expense_rejection", expense_id)
    if expense.get("created_by"):
        try:
            from routers.notifications import _create_notification
            await _create_notification(f"Expense Rejected", f"Your expense '{expense.get('title')}' was rejected. Reason: {data.get('comment', 'No reason given')}", expense.get("created_by"), "error", "/portal/expenses")
        except: pass
    return {**expense, **update}


# ========== PRODUCTS ==========

@router.get("/products")
async def list_products(current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    return await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(500)

@router.post("/products")
async def create_product(data: ProductCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"prod_{str(uuid.uuid4())[:8]}", **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    await db.products.insert_one(doc); doc.pop("_id", None); return doc

@router.put("/products/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    return await db.products.find_one({"id": product_id}, {"_id": 0})

@router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    await db.products.delete_one({"id": product_id}); return {"message": "Product deleted"}


# ========== SALES ==========

@router.get("/sales")
async def list_sales(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    return await db.sales.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

@router.post("/sales")
async def create_sale(data: SaleCreate, current_user: dict = Depends(get_current_user)):
    sale_id = f"inv_{str(uuid.uuid4())[:8].upper()}"
    doc = {"id": sale_id, **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"], "cashier": current_user.get("name", "Unknown")}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    await db.sales.insert_one(doc)
    for item in data.items:
        if item.get("product_id"):
            await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": -item.get("qty", 1)}})
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "sale", sale_id)
    return doc


# ========== CASHFLOW & BALANCE ==========

@router.get("/financial/cashflow")
async def financial_cashflow(months: int = 6, current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    campus = await get_campus_filter(current_user)
    now = datetime.now(timezone.utc); monthly = []
    for i in range(months - 1, -1, -1):
        month_dt = now.replace(day=1) - timedelta(days=i * 28)
        month_start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        month_end = (month_dt.replace(year=month_dt.year + 1, month=1, day=1) if month_dt.month == 12 else month_dt.replace(month=month_dt.month + 1, day=1)).isoformat()
        don_q = {"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}
        exp_q = {"date": {"$gte": month_start[:7], "$lte": month_end[:7]}}
        sale_q = {"created_at": {"$gte": month_start, "$lt": month_end}}
        if campus:
            don_q.update(campus); exp_q.update(campus); sale_q.update(campus)
        donations = await db.donations.find(don_q, {"_id": 0, "amount": 1}).to_list(5000)
        expenses_list = await db.expenses.find(exp_q, {"_id": 0, "amount": 1}).to_list(5000)
        sales = await db.sales.find(sale_q, {"_id": 0, "total": 1}).to_list(5000)
        inflow = sum(d.get("amount", 0) for d in donations) + sum(s.get("total", 0) for s in sales)
        outflow = sum(e.get("amount", 0) for e in expenses_list)
        monthly.append({"month": month_dt.strftime("%b"), "inflow": inflow, "outflow": outflow, "net": inflow - outflow})
    return {"monthly": monthly}

@router.get("/financial/balance")
async def get_financial_balance(current_user: dict = Depends(get_current_user)):
    doc = await db.financial_settings.find_one({}, {"_id": 0})
    return doc or {"opening_balance": 0, "current_balance": 0, "set_at": None}

@router.put("/financial/balance")
async def set_financial_balance(opening_balance: float, current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    await db.financial_settings.update_one({}, {"$set": {"opening_balance": opening_balance, "set_at": now, "set_by": current_user["id"]}}, upsert=True)
    return {"opening_balance": opening_balance, "set_at": now}


# ========== STORE SETTINGS PER LOCATION ==========

@router.get("/store-settings/{location_id}")
async def get_store_settings(location_id: str, current_user: dict = Depends(get_current_user)):
    """Get store configuration for a specific location."""
    doc = await db.store_settings.find_one({"location_id": location_id}, {"_id": 0})
    return doc or {
        "location_id": location_id,
        "store_name": "",
        "payment_methods": ["cash", "mobile_money"],
        "mobile_money_providers": [],
        "tax_rate": 0,
        "receipt_footer": "",
        "api_integrations": [],
        "currency": "UGX",
    }


@router.put("/store-settings/{location_id}")
async def update_store_settings(location_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Update store configuration for a specific location."""
    data.pop("_id", None)
    data["location_id"] = location_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = current_user["id"]
    await db.store_settings.update_one(
        {"location_id": location_id},
        {"$set": data},
        upsert=True
    )
    await _audit(current_user["id"], "update", "store_settings", location_id)
    return data


@router.get("/store-settings")
async def list_all_store_settings(current_user: dict = Depends(get_current_user)):
    """List store settings for all locations."""
    return await db.store_settings.find({}, {"_id": 0}).to_list(100)




@router.delete("/sales/{sale_id}")
async def delete_sale(sale_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a sale entry with time-based approval tiers:
    - Within 5 min: user can delete own entry
    - 5-30 min: manager approval needed
    - 7+ days: director approval needed
    - 30+ days: admin only"""
    sale = await db.sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    
    created = sale.get("created_at", "")
    role = (current_user.get("role") or "").lower()
    role_level = get_role_level(current_user.get("role", ""))
    is_owner = sale.get("created_by") == current_user["id"]
    
    minutes_old = 999999
    if created:
        try:
            from dateutil.parser import parse as dt_parse
            age = datetime.now(timezone.utc) - dt_parse(created).replace(tzinfo=timezone.utc)
            minutes_old = age.total_seconds() / 60
        except: pass
    
    can_delete = False
    if role_level >= 10:  # Admin — always
        can_delete = True
    elif minutes_old <= 5 and is_owner:  # Own entry within 5 min
        can_delete = True
    elif minutes_old <= 30 and role_level >= 7:  # Manager+ within 30 min
        can_delete = True
    elif minutes_old <= (7 * 24 * 60) and role_level >= 8:  # Director+ within 7 days
        can_delete = True
    elif minutes_old <= (30 * 24 * 60) and role_level >= 8:  # Director+ within 30 days
        can_delete = True
    
    if not can_delete:
        if minutes_old <= 30:
            raise HTTPException(status_code=403, detail="Manager approval required to delete entries older than 5 minutes")
        elif minutes_old <= (7 * 24 * 60):
            raise HTTPException(status_code=403, detail="Director approval required to delete entries older than 30 minutes")
        else:
            raise HTTPException(status_code=403, detail="Only administrators can delete entries older than 30 days")
    
    await db.sales.delete_one({"id": sale_id})
    await _audit(current_user["id"], "delete", "sale", sale_id)
    return {"message": "Sale entry deleted"}


# ========== SALES EXPORT / IMPORT ==========

@router.get("/sales/export")
async def export_sales(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Export sales data as JSON for the given location/date range."""
    query = {**await get_campus_filter(current_user)}
    if location_id:
        query["location_id"] = location_id
    if date_from or date_to:
        query["created_at"] = {}
        if date_from:
            query["created_at"]["$gte"] = date_from
        if date_to:
            query["created_at"]["$lte"] = date_to + "T23:59:59"
    sales = await db.sales.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return {"sales": sales, "count": len(sales)}


@router.post("/sales/import")
async def import_sales(data: dict, current_user: dict = Depends(require_manager)):
    """Import sales data from JSON array."""
    sales_data = data.get("sales", [])
    if not sales_data:
        raise HTTPException(status_code=400, detail="No sales data provided")
    imported = 0
    for sale in sales_data:
        sale_id = f"inv_{str(uuid.uuid4())[:8].upper()}"
        doc = {
            "id": sale_id,
            "items": sale.get("items", []),
            "customer_name": sale.get("customer_name", "Imported"),
            "total": float(sale.get("total", 0)),
            "payment_method": sale.get("payment_method", "cash"),
            "location_id": sale.get("location_id", current_user.get("location_id", "")),
            "notes": sale.get("notes", "Imported"),
            "created_at": sale.get("created_at", datetime.now(timezone.utc).isoformat()),
            "created_by": current_user["id"],
            "cashier": current_user.get("name", "Import"),
        }
        await db.sales.insert_one(doc)
        imported += 1
    await _audit(current_user["id"], "create", "sales_import", None, {"count": imported})
    return {"imported": imported}


# ========== FINANCIAL EXPORT / IMPORT ==========

@router.get("/financial/export")
async def export_financial_data(
    location_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Export donations and expenses as JSON."""
    query = {**await _financial_campus_filter(current_user)}
    if location_id:
        query["location_id"] = location_id
    date_filter = {}
    if date_from:
        date_filter["$gte"] = date_from
    if date_to:
        date_filter["$lte"] = date_to
    don_q = {**query}
    exp_q = {**query}
    if date_filter:
        don_q["date"] = date_filter
        exp_q["date"] = date_filter
    donations = await db.donations.find(don_q, {"_id": 0}).sort("date", -1).to_list(5000)
    expenses = await db.expenses.find(exp_q, {"_id": 0}).sort("date", -1).to_list(5000)
    return {
        "donations": donations,
        "expenses": expenses,
        "donations_count": len(donations),
        "expenses_count": len(expenses),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/financial/import")
async def import_financial_data(data: dict, current_user: dict = Depends(require_manager)):
    """Import donations and/or expenses from JSON."""
    don_data = data.get("donations", [])
    exp_data = data.get("expenses", [])
    if not don_data and not exp_data:
        raise HTTPException(status_code=400, detail="No financial data provided")
    don_imported = 0
    for d in don_data:
        doc = {
            "id": f"don_{str(uuid.uuid4())[:8]}",
            "donor_name": d.get("donor_name", "Imported"),
            "amount": float(d.get("amount", 0)),
            "currency": d.get("currency", "UGX"),
            "type": d.get("type", "donation"),
            "date": d.get("date", datetime.now(timezone.utc).isoformat()[:10]),
            "notes": d.get("notes", "Imported"),
            "location_id": d.get("location_id", current_user.get("location_id", "")),
            "member_id": d.get("member_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.donations.insert_one(doc)
        don_imported += 1
    exp_imported = 0
    for e in exp_data:
        doc = {
            "id": f"exp_{str(uuid.uuid4())[:8]}",
            "title": e.get("title", "Imported"),
            "amount": float(e.get("amount", 0)),
            "currency": e.get("currency", "UGX"),
            "category": e.get("category", "general"),
            "date": e.get("date", datetime.now(timezone.utc).isoformat()[:10]),
            "notes": e.get("notes", "Imported"),
            "status": "approved",
            "location_id": e.get("location_id", current_user.get("location_id", "")),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.expenses.insert_one(doc)
        exp_imported += 1
    await _audit(current_user["id"], "create", "financial_import", None, {"donations": don_imported, "expenses": exp_imported})
    return {"donations_imported": don_imported, "expenses_imported": exp_imported}



# ========== BALANCE SHEET ==========

@router.get("/financial/balance-sheet")
async def get_balance_sheet(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(require_manager)):
    """Generate a balance sheet (income vs expenses) for a campus"""
    campus = await _financial_campus_filter(current_user)
    query = {**campus}
    if location_id:
        query["location_id"] = location_id

    date_q = {}
    if date_from: date_q["$gte"] = date_from
    if date_to: date_q["$lte"] = date_to

    don_query = {**query}
    exp_query = {**query}
    if date_q:
        don_query["date"] = date_q
        exp_query["date"] = date_q

    # Income
    donations = await db.donations.find(don_query, {"_id": 0}).to_list(2000)
    total_income = sum(d.get("amount", 0) for d in donations)
    income_by_type = {}
    for d in donations:
        t = d.get("type", "general")
        income_by_type[t] = income_by_type.get(t, 0) + d.get("amount", 0)

    # Expenses
    exp_query["status"] = {"$ne": "rejected"}
    expenses = await db.expenses.find(exp_query, {"_id": 0}).to_list(2000)
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    expense_by_category = {}
    for e in expenses:
        c = e.get("category", "general")
        expense_by_category[c] = expense_by_category.get(c, 0) + e.get("amount", 0)

    # Sales income
    sale_query = {**query}
    if date_q: sale_query["date"] = date_q
    sales = await db.sales.find(sale_query, {"_id": 0}).to_list(2000)
    total_sales = sum(s.get("total", 0) for s in sales)

    net = total_income + total_sales - total_expenses

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_sales": total_sales,
        "net_balance": net,
        "income_by_type": income_by_type,
        "expense_by_category": expense_by_category,
        "donation_count": len(donations),
        "expense_count": len(expenses),
        "sale_count": len(sales),
        "period": {"from": date_from, "to": date_to},
        "location_id": location_id,
    }



# ========== ASSETS ==========

@router.get("/financial/assets")
async def list_assets(location_id: Optional[str] = None, current_user: dict = Depends(require_staff)):
    campus = await _financial_campus_filter(current_user)
    query = {**campus} if campus else {}
    if location_id: query["location_id"] = location_id
    return await db.assets.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/financial/assets")
async def create_asset(data: dict, current_user: dict = Depends(require_manager)):
    doc = {
        "id": f"ast_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "value": float(data.get("value", 0)),
        "category": data.get("category", "equipment"),
        "purchase_date": data.get("purchase_date", ""),
        "depreciation_years": int(data.get("depreciation_years", 5)),
        "serial_number": data.get("serial_number", ""),
        "condition": data.get("condition", "good"),
        "location_id": data.get("location_id", current_user.get("location_id", "")),
        "notes": data.get("notes", ""),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.assets.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/financial/assets/{asset_id}")
async def update_asset(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    allowed = {"name", "value", "category", "purchase_date", "depreciation_years", "serial_number", "condition", "location_id", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.assets.update_one({"id": asset_id}, {"$set": update})
    return await db.assets.find_one({"id": asset_id}, {"_id": 0})


@router.delete("/financial/assets/{asset_id}")
async def delete_asset(asset_id: str, current_user: dict = Depends(require_admin)):
    await db.assets.delete_one({"id": asset_id})
    return {"message": "Asset deleted"}



# ========== RECEIPT SCANNING ==========

@router.post("/financial/expenses/{expense_id}/receipt")
async def upload_receipt(expense_id: str, current_user: dict = Depends(require_staff)):
    """Upload receipt image for an expense"""
    from fastapi import UploadFile, File, Form
    # This endpoint accepts multipart form data
    # For now, store receipt reference on the expense
    return {"message": "Receipt endpoint ready — use multipart upload"}


@router.put("/financial/expenses/{expense_id}/receipt-url")
async def set_receipt_url(expense_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Set receipt URL/reference for an expense"""
    url = data.get("receipt_url", "")
    notes = data.get("receipt_notes", "")
    await db.expenses.update_one({"id": expense_id}, {"$set": {
        "receipt_url": url, "receipt_notes": notes,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"message": "Receipt attached"}


# ========== PUBLIC PRODUCTS / SHOP ==========

@router.get("/public/products")
async def public_products(location_id: Optional[str] = None, category: Optional[str] = None):
    """Public product listing for online shop"""
    query = {"stock": {"$gt": 0}, "is_public": {"$ne": False}}
    if location_id: query["location_id"] = location_id
    if category: query["category"] = category
    products = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(200)
    return products


@router.post("/public/orders")
async def create_public_order(data: dict):
    """Create a public order"""
    items = data.get("items", [])
    if not items: raise HTTPException(status_code=400, detail="No items in order")
    order_id = f"ord_{str(uuid.uuid4())[:8]}"
    total = 0
    order_items = []
    for item in items:
        product = await db.products.find_one({"id": item.get("product_id")}, {"_id": 0})
        if not product: continue
        qty = int(item.get("quantity", 1))
        line_total = (product.get("price", 0)) * qty
        total += line_total
        order_items.append({
            "product_id": product["id"], "name": product.get("name"),
            "price": product.get("price", 0), "quantity": qty, "total": line_total,
        })
    order = {
        "id": order_id,
        "customer_name": data.get("name", ""),
        "customer_email": data.get("email", ""),
        "customer_phone": data.get("phone", ""),
        "items": order_items,
        "total": total,
        "payment_method": data.get("payment_method", "card"),
        "payment_status": "pending",
        "status": "pending",
        "location_id": data.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_orders.insert_one(order)
    order.pop("_id", None)
    return order



# ========== CHILD SPONSORSHIP ==========

@router.get("/financial/sponsors")
async def list_sponsors(location_id: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """List child sponsors, filtered by campus"""
    campus = await _financial_campus_filter(current_user)
    query = {**campus}
    if location_id:
        query["location_id"] = location_id
    sponsors = await db.sponsors.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # For each sponsor, only show sponsor first name in child's context
    for s in sponsors:
        s["sponsor_display_name"] = s.get("name", "").split(" ")[0] if s.get("name") else "Anonymous"
    return sponsors


@router.post("/financial/sponsors")
async def create_sponsor(data: dict, current_user: dict = Depends(require_staff)):
    """Create a child sponsor. Auto-creates child profile if child doesn't exist."""
    sponsor_id = f"spon_{str(uuid.uuid4())[:8]}"
    child_id = data.get("child_id")
    child_name = data.get("child_name", "")
    location_id = data.get("location_id", "")

    # If no child_id but child_name provided, find or create child
    if not child_id and child_name:
        existing_child = await db.children.find_one({"name": {"$regex": f"^{child_name}$", "$options": "i"}})
        if existing_child:
            child_id = existing_child["id"]
        else:
            child_id = f"chd_{str(uuid.uuid4())[:8]}"
            await db.children.insert_one({
                "id": child_id, "name": child_name, "location_id": location_id,
                "is_sponsored": True, "sponsor_id": sponsor_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    doc = {
        "id": sponsor_id,
        "name": data.get("name", ""),
        "first_name": data.get("name", "").split(" ")[0] if data.get("name") else "",
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "address": data.get("address", ""),
        "child_id": child_id,
        "child_name": child_name or "",
        "amount": float(data.get("amount", 0)),
        "currency": data.get("currency", "USD"),
        "frequency": data.get("frequency", "monthly"),  # monthly, quarterly, yearly, one_time
        "location_id": location_id,
        "status": "active",
        "notes": data.get("notes", ""),
        "visibility": data.get("visibility", "restricted"),  # restricted = need-to-know
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sponsors.insert_one(doc)
    doc.pop("_id", None)

    # Tag child as sponsored (only first name visible to authorized staff)
    if child_id:
        await db.children.update_one({"id": child_id}, {"$set": {
            "is_sponsored": True, "sponsor_id": sponsor_id,
            "sponsor_first_name": doc["first_name"],
        }})

    return doc


@router.put("/financial/sponsors/{sponsor_id}")
async def update_sponsor(sponsor_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "email", "phone", "address", "amount", "currency", "frequency", "status", "notes", "child_id", "child_name", "visibility"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "name" in update:
        update["first_name"] = update["name"].split(" ")[0] if update["name"] else ""
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sponsors.update_one({"id": sponsor_id}, {"$set": update})
    # Update child's sponsor first name if name changed
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if sponsor and sponsor.get("child_id"):
        await db.children.update_one({"id": sponsor["child_id"]}, {"$set": {"sponsor_first_name": update.get("first_name", sponsor.get("first_name", ""))}})
    return sponsor


@router.delete("/financial/sponsors/{sponsor_id}")
async def delete_sponsor(sponsor_id: str, current_user: dict = Depends(require_admin)):
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if sponsor and sponsor.get("child_id"):
        await db.children.update_one({"id": sponsor["child_id"]}, {"$unset": {"is_sponsored": "", "sponsor_id": "", "sponsor_first_name": ""}})
    await db.sponsors.delete_one({"id": sponsor_id})
    return {"message": "Sponsor removed"}


@router.get("/financial/sponsors/{sponsor_id}")
async def get_sponsor(sponsor_id: str, current_user: dict = Depends(require_staff)):
    """Get full sponsor details — need-to-know access based on user's location"""
    sponsor = await db.sponsors.find_one({"id": sponsor_id}, {"_id": 0})
    if not sponsor:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    # Check access: director of the child's location, campus director, or ED/admin
    user_role = (current_user.get("role") or "").lower()
    if user_role not in {"admin", "system_admin", "executive director"}:
        user_locs = current_user.get("location_ids") or []
        user_loc = current_user.get("location_id", "")
        if user_loc and user_loc not in user_locs:
            user_locs.append(user_loc)
        sponsor_loc = sponsor.get("location_id", "")
        if sponsor_loc not in user_locs:
            # Hide sensitive info
            sponsor = {k: v for k, v in sponsor.items() if k in {"id", "child_id", "child_name", "first_name", "status", "frequency"}}
    return sponsor
