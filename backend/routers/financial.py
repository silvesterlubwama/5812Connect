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
    date: Optional[str] = None; notes: str = ""; member_id: Optional[str] = None
    location_id: Optional[str] = None; sublocation_id: Optional[str] = None

class ExpenseCreate(BaseModel):
    title: str; amount: float; currency: str = "UGX"; category: str = "general"
    date: Optional[str] = None; notes: str = ""; submitted_by: Optional[str] = None
    location_id: Optional[str] = None; sublocation_id: Optional[str] = None

class ProductCreate(BaseModel):
    name: str; description: Optional[str] = None; price: float = 0; currency: str = "UGX"; stock: int = 0
    category: Optional[str] = None; sku: Optional[str] = None; reorder_level: int = 5; location_id: Optional[str] = None
    has_variants: bool = False; product_type: Optional[str] = None; variants: Optional[List[dict]] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; price: Optional[float] = None
    stock: Optional[int] = None; category: Optional[str] = None; reorder_level: Optional[int] = None; location_id: Optional[str] = None
    has_variants: Optional[bool] = None; product_type: Optional[str] = None

class SaleCreate(BaseModel):
    items: List[dict]; customer_name: Optional[str] = "Walk-in Customer"; customer_phone: Optional[str] = None
    customer_id: Optional[str] = None
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
    doc = {"id": f"don_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"], "entered_by": current_user.get("name", "")}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if doc.get("sublocation_id") and not doc.get("location_id"):
        doc["location_id"] = doc["sublocation_id"]
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
    doc = {"id": f"exp_{str(uuid.uuid4())[:8]}", **data.model_dump(), "date": data.date or datetime.now(timezone.utc).isoformat()[:10], "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"], "entered_by": current_user.get("name", "")}
    if not doc.get("location_id"):
        doc["location_id"] = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if doc.get("sublocation_id") and not doc.get("location_id"):
        doc["location_id"] = doc["sublocation_id"]
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
    # Update customer account totals if linked
    customer_id = doc.get("customer_id")
    if customer_id:
        await db.customer_accounts.update_one(
            {"id": customer_id},
            {"$inc": {"total_purchases": 1, "total_spent": doc.get("total", 0)}}
        )
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
    # Restore stock for sold items
    for item in (sale.get("items") or []):
        if item.get("product_id"):
            await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": item.get("qty", 1)}})
    await _audit(current_user["id"], "delete", "sale", sale_id)
    return {"message": "Sale entry deleted, stock restored"}


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



# ========== SUB-LOCATION ACCOUNTS (unified at campus) ==========

@router.get("/financial/accounts")
async def list_sublocation_accounts(campus_id: Optional[str] = None, current_user: dict = Depends(require_manager)):
    """Get financial accounts per sub-location within a campus, unified at campus level."""
    campus = await get_campus_filter(current_user)
    target_campus = campus_id or current_user.get("active_campus_id") or ""
    if not target_campus:
        raise HTTPException(status_code=400, detail="Campus ID required")
    # Get all sub-locations under this campus
    subs = await db.locations.find(
        {"$or": [{"parent_id": target_campus}, {"id": target_campus}]},
        {"_id": 0, "id": 1, "name": 1, "type": 1}
    ).to_list(50)
    sub_ids = [s["id"] for s in subs]
    accounts = []
    campus_total_in = 0
    campus_total_out = 0
    for sub in subs:
        sid = sub["id"]
        donations = await db.donations.aggregate([{"$match": {"location_id": sid}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        expenses = await db.expenses.aggregate([{"$match": {"location_id": sid}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        sales = await db.sales.aggregate([{"$match": {"location_id": sid}}, {"$group": {"_id": None, "total": {"$sum": "$total"}}}]).to_list(1)
        total_in = (donations[0]["total"] if donations else 0) + (sales[0]["total"] if sales else 0)
        total_out = expenses[0]["total"] if expenses else 0
        campus_total_in += total_in
        campus_total_out += total_out
        accounts.append({
            "location_id": sid,
            "location_name": sub.get("name", ""),
            "location_type": sub.get("type", ""),
            "total_income": total_in,
            "total_expenses": total_out,
            "balance": total_in - total_out,
        })
    return {
        "campus_id": target_campus,
        "accounts": accounts,
        "campus_total_income": campus_total_in,
        "campus_total_expenses": campus_total_out,
        "campus_balance": campus_total_in - campus_total_out,
    }



# ========== CUSTOMER ACCOUNTS ==========

@router.get("/customers")
async def list_customers(location_id: Optional[str] = None, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List customer accounts. Each customer is linked to a guest and a location."""
    query = {}
    if location_id:
        query["location_id"] = location_id
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    return await db.customer_accounts.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/customers")
async def create_customer(data: dict, current_user: dict = Depends(require_staff)):
    """Create or link a customer account. Optionally link to existing guest."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    location_id = data.get("location_id") or current_user.get("active_campus_id") or ""
    guest_id = data.get("guest_id", "")
    # Auto-link to guest if email/phone matches
    if not guest_id:
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()
        if email or phone:
            q = []
            if email: q.append({"email": email})
            if phone: q.append({"phone": phone})
            guest = await db.guests.find_one({"$or": q}, {"_id": 0, "id": 1})
            if guest:
                guest_id = guest["id"]
    doc = {
        "id": f"cust_{uuid.uuid4().hex[:8]}",
        "name": name,
        "email": (data.get("email") or "").strip().lower(),
        "phone": (data.get("phone") or "").strip(),
        "guest_id": guest_id,
        "location_id": location_id,
        "notes": data.get("notes", ""),
        "total_purchases": 0,
        "total_spent": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.customer_accounts.insert_one(doc)
    doc.pop("_id", None)
    # Also mark the guest as customer
    if guest_id:
        await db.guests.update_one({"id": guest_id}, {"$set": {"is_customer": True, "customer_id": doc["id"]}})
    return doc


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Include purchase history
    purchases = await db.sales.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    customer["purchases"] = purchases
    return customer


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "email", "phone", "notes", "guest_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.customer_accounts.update_one({"id": customer_id}, {"$set": update})
    return await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(require_manager)):
    await db.customer_accounts.delete_one({"id": customer_id})
    return {"message": "Customer account deleted"}


@router.get("/customers/{customer_id}/purchases")
async def get_customer_purchases(customer_id: str, current_user: dict = Depends(get_current_user)):
    purchases = await db.sales.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    total = sum(p.get("total", 0) for p in purchases)
    return {"purchases": purchases, "total_count": len(purchases), "total_spent": total}



# ========== FINANCIAL ACCOUNTS (editable, with starting balance) ==========

@router.get("/financial/campus-accounts/{campus_id}")
async def list_campus_accounts(campus_id: str, current_user: dict = Depends(get_current_user)):
    """List financial accounts for a campus (each sub-location + savings)."""
    accounts = await db.financial_accounts.find({"campus_id": campus_id}, {"_id": 0}).sort("name", 1).to_list(50)
    if not accounts:
        # Auto-create accounts from sub-locations
        subs = await db.locations.find({"$or": [{"parent_id": campus_id}, {"id": campus_id}]}, {"_id": 0, "id": 1, "name": 1}).to_list(50)
        for sub in subs:
            doc = {"id": f"acct_{uuid.uuid4().hex[:8]}", "campus_id": campus_id, "location_id": sub["id"], "name": sub["name"], "type": "operational", "starting_balance": 0, "currency": "UGX", "created_at": datetime.now(timezone.utc).isoformat()}
            await db.financial_accounts.insert_one(doc); doc.pop("_id", None); accounts.append(doc)
        # Add savings account
        savings = {"id": f"acct_{uuid.uuid4().hex[:8]}", "campus_id": campus_id, "location_id": "", "name": "Savings", "type": "savings", "starting_balance": 0, "currency": "UGX", "created_at": datetime.now(timezone.utc).isoformat()}
        await db.financial_accounts.insert_one(savings); savings.pop("_id", None); accounts.append(savings)
    return accounts


@router.put("/financial/campus-accounts/{account_id}")
async def update_campus_account(account_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Update account details (name, starting_balance, currency). Director or Finance Manager."""
    allowed = {"name", "starting_balance", "currency", "type", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.financial_accounts.update_one({"id": account_id}, {"$set": update})
    return await db.financial_accounts.find_one({"id": account_id}, {"_id": 0})


# ========== INTER-ACCOUNT TRANSFERS ==========

@router.post("/financial/transfers")
async def create_transfer(data: dict, current_user: dict = Depends(require_manager)):
    """Transfer between accounts (recorded as expense from source, income to destination)."""
    from_account_id = data.get("from_account_id")
    to_account_id = data.get("to_account_id")
    amount = float(data.get("amount", 0))
    if not from_account_id or not to_account_id or amount <= 0:
        raise HTTPException(status_code=400, detail="from_account_id, to_account_id, and amount required")
    from_acct = await db.financial_accounts.find_one({"id": from_account_id}, {"_id": 0})
    to_acct = await db.financial_accounts.find_one({"id": to_account_id}, {"_id": 0})
    if not from_acct or not to_acct:
        raise HTTPException(status_code=404, detail="Account not found")
    transfer_id = f"txfr_{uuid.uuid4().hex[:8]}"
    # Record expense on source
    await db.expenses.insert_one({
        "id": f"exp_{uuid.uuid4().hex[:8]}", "category": "Transfer Out", "description": f"Transfer to {to_acct['name']}",
        "amount": amount, "date": datetime.now(timezone.utc).isoformat()[:10], "status": "approved",
        "location_id": from_acct.get("location_id", ""), "transfer_id": transfer_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    })
    # Record income on destination
    await db.donations.insert_one({
        "id": f"don_{uuid.uuid4().hex[:8]}", "donor_name": f"Transfer from {from_acct['name']}",
        "amount": amount, "date": datetime.now(timezone.utc).isoformat()[:10], "category": "Transfer In",
        "location_id": to_acct.get("location_id", ""), "transfer_id": transfer_id,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    })
    doc = {"id": transfer_id, "from_account_id": from_account_id, "to_account_id": to_account_id,
           "from_name": from_acct["name"], "to_name": to_acct["name"], "amount": amount,
           "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.financial_transfers.insert_one(doc); doc.pop("_id", None)
    await _audit(current_user["id"], "create", "transfer", transfer_id, {"amount": amount})
    return doc


@router.get("/financial/transfers")
async def list_transfers(campus_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if campus_id:
        acct_ids = [a["id"] for a in await db.financial_accounts.find({"campus_id": campus_id}, {"_id": 0, "id": 1}).to_list(50)]
        query = {"$or": [{"from_account_id": {"$in": acct_ids}}, {"to_account_id": {"$in": acct_ids}}]}
    return await db.financial_transfers.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)


# ========== BUDGETING ==========

@router.get("/financial/budgets")
async def list_budgets(campus_id: Optional[str] = None, period: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if campus_id: query["campus_id"] = campus_id
    if period: query["period"] = period
    return await db.financial_budgets.find(query, {"_id": 0}).sort("period", -1).to_list(100)


@router.post("/financial/budgets")
async def create_budget(data: dict, current_user: dict = Depends(require_manager)):
    """Create/update budget for a sub-location or department."""
    doc = {
        "id": f"bgt_{uuid.uuid4().hex[:8]}",
        "campus_id": data.get("campus_id") or current_user.get("active_campus_id", ""),
        "location_id": data.get("location_id", ""),
        "department": data.get("department", ""),
        "period": data.get("period", datetime.now(timezone.utc).strftime("%Y-%m")),
        "amount": float(data.get("amount", 0)),
        "category": data.get("category", "general"),
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
    }
    await db.financial_budgets.insert_one(doc); doc.pop("_id", None)
    return doc


@router.delete("/financial/budgets/{budget_id}")
async def delete_budget(budget_id: str, current_user: dict = Depends(require_manager)):
    await db.financial_budgets.delete_one({"id": budget_id})
    return {"message": "Budget deleted"}


# ========== CATEGORIES & INCOME SOURCES (admin-editable) ==========

@router.get("/financial/categories")
async def list_financial_categories(current_user: dict = Depends(get_current_user)):
    cats = await db.financial_categories.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    if not cats:
        defaults = [
            {"id": "fcat_tithe", "name": "Tithes", "type": "income"}, {"id": "fcat_offering", "name": "Offerings", "type": "income"},
            {"id": "fcat_donation", "name": "Donations", "type": "income"}, {"id": "fcat_grant", "name": "Grants", "type": "income"},
            {"id": "fcat_sales", "name": "Sales Revenue", "type": "income"}, {"id": "fcat_transfer_in", "name": "Transfer In", "type": "income"},
            {"id": "fcat_salary", "name": "Salaries", "type": "expense"}, {"id": "fcat_rent", "name": "Rent/Utilities", "type": "expense"},
            {"id": "fcat_supplies", "name": "Supplies", "type": "expense"}, {"id": "fcat_transport", "name": "Transport", "type": "expense"},
            {"id": "fcat_food", "name": "Food/Meals", "type": "expense"}, {"id": "fcat_maintenance", "name": "Maintenance", "type": "expense"},
            {"id": "fcat_transfer_out", "name": "Transfer Out", "type": "expense"}, {"id": "fcat_other", "name": "Other", "type": "both"},
        ]
        await db.financial_categories.insert_many(defaults)
        for d in defaults: d.pop("_id", None)
        return defaults
    return cats


@router.post("/financial/categories")
async def create_financial_category(data: dict, current_user: dict = Depends(require_admin)):
    doc = {"id": f"fcat_{uuid.uuid4().hex[:8]}", "name": data.get("name", ""), "type": data.get("type", "both"), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.financial_categories.insert_one(doc); doc.pop("_id", None)
    return doc


@router.delete("/financial/categories/{cat_id}")
async def delete_financial_category(cat_id: str, current_user: dict = Depends(require_admin)):
    await db.financial_categories.delete_one({"id": cat_id})
    return {"message": "Category deleted"}


# ========== ASSETS (appreciation default, manual depreciation) ==========

@router.put("/financial/assets/{asset_id}/valuation")
async def update_asset_valuation(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Manually update asset current value. Supports appreciation (default) or depreciation."""
    new_value = data.get("current_value")
    method = data.get("method", "appreciation")  # appreciation or depreciation
    if new_value is None:
        raise HTTPException(status_code=400, detail="current_value required")
    await db.assets.update_one({"id": asset_id}, {"$set": {
        "current_value": float(new_value), "valuation_method": method,
        "last_valued_at": datetime.now(timezone.utc).isoformat(), "valued_by": current_user["id"],
    }})
    return await db.assets.find_one({"id": asset_id}, {"_id": 0})


# ========== PRODUCT VARIANTS + BARCODES ==========

@router.post("/products/{product_id}/variants")
async def add_product_variant(product_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a variant to a product (size, color, etc.)."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # Ensure variants array exists
    if product.get("variants") is None:
        await db.products.update_one({"id": product_id}, {"$set": {"variants": []}})
    # Generate barcode
    loc = await db.locations.find_one({"id": product.get("location_id", "")}, {"_id": 0, "country_code": 1})
    country_prefix = (loc.get("country_code") or "XX") if loc else "XX"
    variant_num = len(product.get("variants") or []) + 1
    barcode = data.get("barcode") or f"{country_prefix}-{product_id[-6:]}-V{variant_num:02d}"
    variant = {
        "id": f"var_{uuid.uuid4().hex[:6]}",
        "name": data.get("name", ""),
        "type": data.get("type", ""),  # e.g. "size", "color"
        "value": data.get("value", ""),  # e.g. "Large", "Red"
        "price": float(data.get("price", 0)),
        "stock": int(data.get("stock", 0)),
        "sku": data.get("sku", ""),
        "barcode": barcode,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.products.update_one({"id": product_id}, {
        "$push": {"variants": variant},
        "$set": {"has_variants": True, "updated_at": datetime.now(timezone.utc).isoformat()},
    })
    return variant


@router.put("/products/{product_id}/variants/{variant_id}")
async def update_product_variant(product_id: str, variant_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a variant's price, stock, barcode, etc."""
    allowed = {"name", "type", "value", "price", "stock", "sku", "barcode"}
    update_fields = {f"variants.$.{k}": v for k, v in data.items() if k in allowed}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields")
    await db.products.update_one({"id": product_id, "variants.id": variant_id}, {"$set": update_fields})
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    return next((v for v in (product.get("variants") or []) if v["id"] == variant_id), None)


@router.delete("/products/{product_id}/variants/{variant_id}")
async def delete_product_variant(product_id: str, variant_id: str, current_user: dict = Depends(get_current_user)):
    await db.products.update_one({"id": product_id}, {"$pull": {"variants": {"id": variant_id}}})
    # Check if any variants remain
    product = await db.products.find_one({"id": product_id}, {"_id": 0, "variants": 1})
    if not product.get("variants"):
        await db.products.update_one({"id": product_id}, {"$set": {"has_variants": False}})
    return {"message": "Variant deleted"}


@router.post("/products/{product_id}/generate-barcodes")
async def generate_product_barcodes(product_id: str, current_user: dict = Depends(get_current_user)):
    """Auto-generate barcodes for all variants of a product."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    loc = await db.locations.find_one({"id": product.get("location_id", "")}, {"_id": 0, "country_code": 1})
    country_prefix = (loc.get("country_code") or "XX") if loc else "XX"
    updated = 0
    for i, v in enumerate(product.get("variants") or []):
        if not v.get("barcode"):
            barcode = f"{country_prefix}-{product_id[-6:]}-V{i+1:02d}"
            await db.products.update_one({"id": product_id, "variants.id": v["id"]}, {"$set": {"variants.$.barcode": barcode}})
            updated += 1
    return {"message": f"Generated {updated} barcodes", "prefix": country_prefix}
