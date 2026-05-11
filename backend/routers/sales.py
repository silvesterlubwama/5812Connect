"""Sales / POS / draft (parked) sales / receipt lookup — extracted from financial.py"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, require_manager, _audit, get_campus_filter, get_role_level, is_system_admin
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api", tags=["sales"])


def _can_edit_sale(user: dict, sale: dict) -> bool:
    """Admins, EDs, Advisers, and Directors can edit a sale.
    Directors are restricted to sales in their assigned location_ids/active_campus."""
    if is_system_admin(user):
        return True
    role = (user.get("role") or "").lower()
    if role in {"admin", "system_admin", "executive director", "adviser"}:
        return True
    if role == "director":
        user_locs = set(user.get("location_ids") or [])
        if user.get("location_id"):
            user_locs.add(user["location_id"])
        if user.get("active_campus_id"):
            user_locs.add(user["active_campus_id"])
        sale_loc = sale.get("location_id", "")
        return sale_loc in user_locs
    return False


class SaleCreate(BaseModel):
    items: List[dict]; customer_name: Optional[str] = "Walk-in Customer"; customer_phone: Optional[str] = None
    customer_id: Optional[str] = None
    total: float; payment_method: str = "cash"; notes: Optional[str] = None; location_id: Optional[str] = None


# ========== FINANCIAL SUMMARY ==========

# ========== SALES ==========

@router.get("/sales")
async def list_sales(skip: int = 0, limit: int = 100, current_user: dict = Depends(get_current_user)):
    query = {**await get_campus_filter(current_user)}
    return await db.sales.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

@router.post("/sales")
async def create_sale(data: SaleCreate, current_user: dict = Depends(get_current_user)):
    # Traceable, human-readable receipt number: INV-YYYYMMDD-####
    # Atomic counter guarantees uniqueness even under concurrent POSTs on same day
    now = datetime.now(timezone.utc)
    date_tag = now.strftime("%Y%m%d")
    counter = await db.counters.find_one_and_update(
        {"_id": f"sales_{date_tag}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    receipt_number = f"INV-{date_tag}-{seq:04d}"
    sale_id = receipt_number  # id equals receipt number for traceability
    # Payment status: cash sales are paid immediately, others default to pending until confirmed
    pm = (data.payment_method or "cash").lower()
    payment_status = "paid" if pm == "cash" else "pending"
    doc = {
        "id": sale_id,
        "receipt_number": receipt_number,
        **data.model_dump(),
        "payment_status": payment_status,
        "paid_at": now.isoformat() if payment_status == "paid" else None,
        "created_at": now.isoformat(),
        "created_by": current_user["id"],
        "cashier": current_user.get("name", "Unknown"),
        "cashier_id": current_user.get("id"),
    }
    if not doc.get("location_id"):
        # Fall back: use the user's primary store location, NOT their active_campus
        # (active_campus may be a parent campus while sales happen at a specific sub-location)
        doc["location_id"] = current_user.get("location_id") or current_user.get("active_campus_id") or ""
    # Capture store name on the sale for the receipt header.
    # Priority: store_settings.store_name (custom branded name) → location.name → blank.
    if doc.get("location_id"):
        store_setting = await db.store_settings.find_one({"location_id": doc["location_id"]}, {"_id": 0, "store_name": 1})
        if store_setting and store_setting.get("store_name"):
            doc["store_name"] = store_setting["store_name"]
        else:
            loc = await db.locations.find_one({"id": doc["location_id"]}, {"_id": 0, "name": 1, "code": 1})
            if loc:
                doc["store_name"] = loc.get("name") or loc.get("code") or ""
    await db.sales.insert_one(doc)
    # Stock decrement: variant stock by qty AND main stock by qty * units_per_pack
    for item in data.items:
        if item.get("product_id"):
            qty = item.get("qty", 1)
            units_per_pack = int(item.get("units_per_pack", 1) or 1)
            base_units = qty * max(1, units_per_pack)
            if item.get("variant_id"):
                await db.products.update_one(
                    {"id": item["product_id"], "variants.id": item["variant_id"]},
                    {"$inc": {"variants.$.stock": -qty, "stock": -base_units}}
                )
            else:
                await db.products.update_one(
                    {"id": item["product_id"]},
                    {"$inc": {"stock": -base_units}}
                )
    # Update customer account totals if linked
    customer_id = doc.get("customer_id")
    if customer_id:
        await db.customer_accounts.update_one(
            {"id": customer_id},
            {"$inc": {"total_purchases": 1, "total_spent": doc.get("total", 0)},
             "$push": {"receipt_history": {"receipt_number": receipt_number, "total": doc.get("total", 0), "date": doc.get("created_at"), "payment_status": payment_status}}}
        )
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "sale", sale_id)
    return doc


@router.put("/sales/{sale_id}/payment-status")
async def update_sale_payment_status(sale_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Toggle a sale's payment_status (paid/pending) — used for non-cash sales awaiting confirmation."""
    sale = await db.sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    new_status = (data.get("payment_status") or "").lower()
    if new_status not in {"paid", "pending"}:
        raise HTTPException(status_code=400, detail="payment_status must be 'paid' or 'pending'")
    update = {
        "payment_status": new_status,
        "payment_updated_at": datetime.now(timezone.utc).isoformat(),
        "payment_updated_by": current_user["id"],
        "payment_updated_by_name": current_user.get("name", ""),
    }
    unset_fields = {}
    if new_status == "paid":
        update["paid_at"] = datetime.now(timezone.utc).isoformat()
        if data.get("payment_reference"):
            update["payment_reference"] = data["payment_reference"]
    else:
        # Reverting to pending — clear paid metadata
        unset_fields["paid_at"] = ""
        unset_fields["payment_reference"] = ""
    mongo_update = {"$set": update}
    if unset_fields:
        mongo_update["$unset"] = unset_fields
    await db.sales.update_one({"id": sale_id}, mongo_update)
    # Mirror to customer_accounts.receipt_history (if any)
    if sale.get("customer_id"):
        await db.customer_accounts.update_one(
            {"id": sale["customer_id"], "receipt_history.receipt_number": sale.get("receipt_number") or sale_id},
            {"$set": {"receipt_history.$.payment_status": new_status}}
        )
    await _audit(current_user["id"], "update", "sale_payment_status", sale_id, {"new_status": new_status})
    return {**sale, **update}


@router.put("/sales/{sale_id}")
async def update_sale(sale_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Edit a completed sale's metadata (cashier / location / customer).
    Restricted to admin / Executive Director / Adviser / Director (own campus)."""
    sale = await db.sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if not _can_edit_sale(current_user, sale):
        raise HTTPException(status_code=403, detail="Only admins, EDs, advisers, and the campus director can edit completed sales")
    allowed = {"cashier", "cashier_id", "location_id", "customer_name", "customer_phone", "customer_id", "notes"}
    update = {k: v for k, v in (data or {}).items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided")
    # If location is changing, refresh the captured store_name (custom store_settings name → location name)
    if "location_id" in update and update["location_id"]:
        store_setting = await db.store_settings.find_one({"location_id": update["location_id"]}, {"_id": 0, "store_name": 1})
        if store_setting and store_setting.get("store_name"):
            update["store_name"] = store_setting["store_name"]
        else:
            loc = await db.locations.find_one({"id": update["location_id"]}, {"_id": 0, "name": 1, "code": 1})
            if loc:
                update["store_name"] = loc.get("name") or loc.get("code") or ""
    update["edited_at"] = datetime.now(timezone.utc).isoformat()
    update["edited_by"] = current_user["id"]
    update["edited_by_name"] = current_user.get("name", "")
    await db.sales.update_one({"id": sale_id}, {"$set": update})
    await _audit(current_user["id"], "update", "sale_meta", sale_id, {"changed_keys": list(update.keys())})
    return await db.sales.find_one({"id": sale_id}, {"_id": 0})


@router.post("/sales/{sale_id}/undo")
async def undo_sale(sale_id: str, current_user: dict = Depends(get_current_user)):
    """Quick-undo a sale within 60 seconds of creation — typical "oops" flow at the till.
    Reverses stock decrements + marks sale as voided. After 60s, requires admin/director edit instead."""
    sale = await db.sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.get("voided"):
        raise HTTPException(status_code=400, detail="Sale already voided")
    # Time window check — the cashier who made the sale can undo within 60s
    try:
        created = datetime.fromisoformat(sale.get("created_at", "").replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Sale has invalid created_at")
    age_s = (datetime.now(timezone.utc) - created).total_seconds()
    is_owner = sale.get("created_by") == current_user["id"] or sale.get("cashier_id") == current_user["id"]
    can_force = _can_edit_sale(current_user, sale)
    if age_s > 60 and not can_force:
        raise HTTPException(status_code=403, detail="Undo window (60s) has passed. Ask a director to edit/refund.")
    if age_s <= 60 and not is_owner and not can_force:
        raise HTTPException(status_code=403, detail="Only the cashier who made this sale can undo it")
    # Reverse stock
    for item in (sale.get("items") or []):
        if item.get("product_id"):
            qty = item.get("qty", 1)
            units_per_pack = int(item.get("units_per_pack", 1) or 1)
            base_units = qty * max(1, units_per_pack)
            if item.get("variant_id"):
                await db.products.update_one(
                    {"id": item["product_id"], "variants.id": item["variant_id"]},
                    {"$inc": {"variants.$.stock": qty, "stock": base_units}}
                )
            else:
                await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": base_units}})
    # Reverse customer accounts totals
    if sale.get("customer_id"):
        await db.customer_accounts.update_one(
            {"id": sale["customer_id"]},
            {"$inc": {"total_purchases": -1, "total_spent": -(sale.get("total", 0))}}
        )
    # Mark voided rather than delete (audit trail)
    await db.sales.update_one({"id": sale_id}, {"$set": {
        "voided": True,
        "voided_at": datetime.now(timezone.utc).isoformat(),
        "voided_by": current_user["id"],
        "voided_by_name": current_user.get("name", ""),
    }})
    await _audit(current_user["id"], "void", "sale", sale_id, {"reason": "undo"})
    return {"message": "Sale voided and stock restored", "sale_id": sale_id}


# ========== DRAFT / PARKED SALES ==========

@router.get("/sales/drafts")
async def list_draft_sales(current_user: dict = Depends(get_current_user)):
    """List parked/draft sales for the current kiosk/location (shared with all staff at this campus)."""
    loc_id = current_user.get("active_campus_id") or current_user.get("location_id") or ""
    query = {"status": "draft"}
    if loc_id:
        query["location_id"] = loc_id
    drafts = await db.sale_drafts.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
    return drafts


# ========== CASH MANAGEMENT (drawer transfers to safe / bank) ==========

@router.post("/cash-drops")
async def create_cash_drop(data: dict, current_user: dict = Depends(get_current_user)):
    """Record a cash transfer from a POS drawer to a safe / bank / central account.
    Body: { amount, currency, location_id (drawer), destination ('safe' | 'bank' | account_id),
            notes?, attachments? }
    Creates an audit-loggable record + (optional) financial transfer if a target account_id is given."""
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    loc_id = data.get("location_id") or current_user.get("location_id") or current_user.get("active_campus_id") or ""
    dest = (data.get("destination") or "safe").strip()
    drop_id = f"drop_{uuid.uuid4().hex[:8]}"
    doc = {
        "id": drop_id,
        "amount": amount,
        "currency": data.get("currency") or "UGX",
        "location_id": loc_id,
        "destination": dest,
        "destination_account_id": data.get("destination_account_id"),
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.cash_drops.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "cash_drop", drop_id, {"amount": amount, "destination": dest})
    return doc


@router.get("/cash-drops")
async def list_cash_drops(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """List recent cash drops for the user's campus or a specific location."""
    query = {}
    if location_id:
        query["location_id"] = location_id
    else:
        loc = current_user.get("location_id") or current_user.get("active_campus_id")
        if loc:
            query["location_id"] = loc
    return await db.cash_drops.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


@router.get("/cash-drops/balance/{location_id}")
async def cash_drawer_balance(location_id: str, current_user: dict = Depends(get_current_user)):
    """Compute current cash-on-hand at a location: sum(cash sales) − sum(cash drops)."""
    # Sum of paid cash sales (not voided) at this location
    sales_agg = await db.sales.aggregate([
        {"$match": {"location_id": location_id, "payment_method": "cash", "voided": {"$ne": True}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]).to_list(1)
    total_in = sales_agg[0]["total"] if sales_agg else 0

    drops_agg = await db.cash_drops.aggregate([
        {"$match": {"location_id": location_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]).to_list(1)
    total_out = drops_agg[0]["total"] if drops_agg else 0

    return {
        "location_id": location_id,
        "cash_in": total_in,
        "cash_dropped": total_out,
        "cash_on_hand": total_in - total_out,
    }


@router.post("/sales/drafts")
async def create_draft_sale(data: dict, current_user: dict = Depends(get_current_user)):
    """Park/save an in-progress sale so it can be reopened later (by anyone at the same campus)."""
    draft_id = f"draft_{uuid.uuid4().hex[:8]}"
    loc_id = data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    doc = {
        "id": draft_id,
        "status": "draft",
        "items": data.get("items", []),
        "customer_name": data.get("customer_name", "Walk-in Customer"),
        "customer_id": data.get("customer_id"),
        "customer_phone": data.get("customer_phone"),
        "payment_method": data.get("payment_method", "cash"),
        "total": float(data.get("total", 0)),
        "notes": data.get("notes", ""),
        "location_id": loc_id,
        "parked_by": current_user["id"],
        "parked_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sale_drafts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/sales/drafts/{draft_id}")
async def delete_draft_sale(draft_id: str, current_user: dict = Depends(get_current_user)):
    """Discard a parked draft sale."""
    await db.sale_drafts.delete_one({"id": draft_id})
    return {"message": "Draft discarded"}


@router.get("/sales/by-receipt/{receipt_number}")
async def get_sale_by_receipt(receipt_number: str):
    """Public — look up a sale by its receipt number (used for QR code tracing)."""
    sale = await db.sales.find_one({"$or": [{"receipt_number": receipt_number}, {"id": receipt_number}]}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Receipt not found")
    # Return minimal, non-sensitive fields
    return {
        "receipt_number": sale.get("receipt_number", sale.get("id")),
        "created_at": sale.get("created_at"),
        "total": sale.get("total"),
        "customer_name": sale.get("customer_name"),
        "cashier": sale.get("cashier"),
        "items": [{"name": i.get("name"), "qty": i.get("qty"), "unit_price": i.get("unit_price")} for i in (sale.get("items") or [])],
        "payment_method": sale.get("payment_method"),
        "payment_status": sale.get("payment_status", "paid"),
        "location_id": sale.get("location_id"),
        "store_name": sale.get("store_name"),
    }

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
