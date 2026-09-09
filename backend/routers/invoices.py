"""Marketplace Invoices — editable, printable, convertible to sales.

Workflow:
  draft  → editable; can be printed/sent
  sent   → editable but flagged (customer has been notified)
  converted → linked to a real sale receipt; final
  cancelled → cannot be revived
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, require_staff, _audit, get_campus_filter, is_system_admin, logger
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api", tags=["invoices"])


class InvoiceItem(BaseModel):
    name: str
    qty: float = 1
    unit_price: float = 0
    product_id: Optional[str] = None
    variant_id: Optional[str] = None
    discount: Optional[float] = 0
    tax: Optional[float] = 0


class InvoiceCreate(BaseModel):
    customer_name: str = "Walk-in Customer"
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_id: Optional[str] = None
    items: List[InvoiceItem] = []
    notes: Optional[str] = ""
    due_date: Optional[str] = None
    payment_method: Optional[str] = "cash"
    location_id: Optional[str] = None
    discount: Optional[float] = 0
    tax_amount: Optional[float] = 0


def _calc_total(items, discount=0, tax_amount=0):
    subtotal = sum((i.get("qty", 0) or 0) * (i.get("unit_price", 0) or 0) - (i.get("discount", 0) or 0) for i in items)
    return max(0, subtotal - (discount or 0) + (tax_amount or 0))


async def _next_invoice_number(is_quote: bool = False):
    today = datetime.now(timezone.utc)
    date_tag = today.strftime("%Y%m%d")
    counter_key = f"quotes_{date_tag}" if is_quote else f"invoices_{date_tag}"
    counter = await db.counters.find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    prefix = "QUOTE" if is_quote else "INV-DRAFT"
    return f"{prefix}-{date_tag}-{seq:04d}"


@router.get("/invoices")
async def list_invoices(status: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """List invoices visible to user. Filter by status (draft/sent/converted/cancelled)."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    if status:
        query["status"] = status
    return await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/invoices")
async def create_invoice(data: InvoiceCreate, status: Optional[str] = "draft", current_user: dict = Depends(require_staff)):
    """Create an invoice. status='quote' issues a QUOTE-* number for estimate mode."""
    is_quote = (status or "").lower() == "quote"
    items = [i.model_dump() for i in data.items]
    invoice_number = await _next_invoice_number(is_quote=is_quote)
    doc = {
        "id": invoice_number,
        "invoice_number": invoice_number,
        "status": "quote" if is_quote else "draft",
        "is_quote": is_quote,
        "customer_name": data.customer_name,
        "customer_phone": data.customer_phone,
        "customer_email": data.customer_email,
        "customer_id": data.customer_id,
        "items": items,
        "notes": data.notes or "",
        "due_date": data.due_date,
        "payment_method": data.payment_method or "cash",
        "discount": data.discount or 0,
        "tax_amount": data.tax_amount or 0,
        "subtotal": sum((i.get("qty", 0) or 0) * (i.get("unit_price", 0) or 0) for i in items),
        "total": _calc_total(items, data.discount, data.tax_amount),
        "location_id": data.location_id or current_user.get("active_campus_id") or current_user.get("location_id") or "",
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", "Unknown"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "invoice", invoice_number)
    return doc


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: dict = Depends(require_staff)):
    inv = await db.invoices.find_one({"$or": [{"id": invoice_id}, {"invoice_number": invoice_id}]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Edit a draft/sent invoice. Cannot edit converted/cancelled invoices."""
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") in {"converted", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit a {inv.get('status')} invoice")
    allowed = {"customer_name", "customer_phone", "customer_email", "customer_id",
               "items", "notes", "due_date", "payment_method", "discount", "tax_amount", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "status" in update and update["status"] not in {"draft", "sent", "cancelled", "quote"}:
        raise HTTPException(status_code=400, detail="Status must be draft / sent / quote / cancelled (use convert endpoint for sale)")
    if "items" in update:
        update["subtotal"] = sum((i.get("qty", 0) or 0) * (i.get("unit_price", 0) or 0) for i in update["items"])
        update["total"] = _calc_total(update["items"], update.get("discount", inv.get("discount", 0)), update.get("tax_amount", inv.get("tax_amount", 0)))
    elif "discount" in update or "tax_amount" in update:
        update["total"] = _calc_total(inv.get("items") or [], update.get("discount", inv.get("discount", 0)), update.get("tax_amount", inv.get("tax_amount", 0)))
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.invoices.update_one({"id": invoice_id}, {"$set": update})
    await _audit(current_user["id"], "update", "invoice", invoice_id)
    return await db.invoices.find_one({"id": invoice_id}, {"_id": 0})


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, current_user: dict = Depends(require_staff)):
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0, "status": 1})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") == "converted":
        raise HTTPException(status_code=400, detail="Cannot delete a converted invoice")
    await db.invoices.delete_one({"id": invoice_id})
    return {"message": "Invoice deleted"}


@router.post("/invoices/{invoice_id}/convert")
async def convert_invoice_to_sale(invoice_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Convert an invoice into a real sale (decrements stock, generates receipt).
    Optional body: {items: [...], discount, tax_amount, payment_method, customer_name}
    — overrides allow last-minute adjustments before commit."""
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") == "converted":
        raise HTTPException(status_code=400, detail="Invoice already converted")
    if inv.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot convert a cancelled invoice")

    overrides = data or {}
    items = overrides.get("items") or inv.get("items") or []
    discount = overrides.get("discount", inv.get("discount", 0))
    tax_amount = overrides.get("tax_amount", inv.get("tax_amount", 0))
    payment_method = overrides.get("payment_method", inv.get("payment_method", "cash"))
    customer_name = overrides.get("customer_name", inv.get("customer_name", "Walk-in Customer"))
    total = _calc_total(items, discount, tax_amount)

    # Stock guard — atomically pre-check that every item has enough stock before we commit
    insufficient = []
    for item in items:
        if not item.get("product_id"):
            continue
        qty = item.get("qty", 0)
        units_per_pack = int(item.get("units_per_pack", 1) or 1)
        base_units = qty * max(1, units_per_pack)
        prod = await db.products.find_one({"id": item["product_id"]}, {"_id": 0, "stock": 1, "variants": 1, "name": 1})
        if not prod:
            continue
        if item.get("variant_id"):
            v = next((v for v in (prod.get("variants") or []) if v.get("id") == item["variant_id"]), None)
            if v and (v.get("stock", 0) or 0) < qty:
                insufficient.append(f"{prod.get('name')} ({item.get('name')}): need {qty}, have {v.get('stock', 0)}")
        else:
            if (prod.get("stock", 0) or 0) < base_units:
                insufficient.append(f"{prod.get('name')}: need {base_units}, have {prod.get('stock', 0)}")
    if insufficient:
        raise HTTPException(status_code=409, detail={"error": "Insufficient stock", "items": insufficient})

    # Generate sale receipt number atomically
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
    pm = (payment_method or "cash").lower()
    payment_status = "paid" if pm == "cash" else "pending"
    sale = {
        "id": receipt_number,
        "receipt_number": receipt_number,
        "items": items,
        "subtotal": sum((i.get("qty", 0) or 0) * (i.get("unit_price", 0) or 0) for i in items),
        "discount": discount,
        "tax_amount": tax_amount,
        "total": total,
        "customer_name": customer_name,
        "customer_phone": inv.get("customer_phone"),
        "customer_id": inv.get("customer_id"),
        "payment_method": pm,
        "payment_status": payment_status,
        "paid_at": now.isoformat() if payment_status == "paid" else None,
        "location_id": inv.get("location_id", ""),
        "from_invoice": inv.get("invoice_number"),
        "created_at": now.isoformat(),
        "created_by": current_user["id"],
        "cashier": current_user.get("name", "Unknown"),
        "cashier_id": current_user.get("id"),
    }
    await db.sales.insert_one(sale)

    # Decrement stock for each item (uses units_per_pack)
    for item in items:
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
                await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": -base_units}})

    # Mark invoice as converted
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "status": "converted",
            "converted_at": now.isoformat(),
            "converted_by": current_user["id"],
            "receipt_number": receipt_number,
            "final_items": items,
            "final_total": total,
            "updated_at": now.isoformat(),
        }}
    )
    sale.pop("_id", None)

    # iter319: an invoice-born sale must not become a second source of truth.
    # Run the SAME side-effects the POS path runs — customer account link and
    # the one balanced ledger posting (which itself only posts when the sale is
    # actually settled, and is idempotent by sale id).
    try:
        from routers.sales import _ensure_customer_account, _auto_post_sale_journal_entry
        if not sale.get("customer_id"):
            cust_id = await _ensure_customer_account(sale, current_user)
            if cust_id:
                await db.sales.update_one({"id": receipt_number}, {"$set": {"customer_id": cust_id}})
                sale["customer_id"] = cust_id
        await _auto_post_sale_journal_entry(sale, current_user)
    except Exception as ex:
        logger.warning(f"invoice→sale side-effects skipped for {receipt_number}: {ex}")

    await _audit(current_user["id"], "convert", "invoice_to_sale", f"{invoice_id}→{receipt_number}")
    return {"invoice_id": invoice_id, "sale": sale, "receipt_number": receipt_number}


# ========== PUBLIC QUOTE LOOKUP + ACCEPTANCE ==========

# ========== ACCOUNTS RECEIVABLE (pending non-cash sales per customer) ==========

@router.get("/accounts-receivable")
async def accounts_receivable(
    location_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Aggregate pending non-cash sales by customer for AR / collections.
    Returns: { total_outstanding, by_customer: [{name, phone, sales_count, total, oldest_date, latest_date, sales:[...]}] }"""
    query = {"payment_status": "pending", "voided": {"$ne": True}}
    if location_id:
        query["location_id"] = location_id
    else:
        scope = current_user.get("location_id") or current_user.get("active_campus_id")
        if scope:
            query["location_id"] = scope
    sales = await db.sales.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    by_customer = {}
    total_out = 0
    for s in sales:
        key = (s.get("customer_id") or s.get("customer_phone") or s.get("customer_name") or "Walk-in").strip().lower()
        if key not in by_customer:
            by_customer[key] = {
                "customer_id": s.get("customer_id"),
                "customer_name": s.get("customer_name") or "Walk-in",
                "customer_phone": s.get("customer_phone"),
                "sales_count": 0,
                "total": 0,
                "oldest_date": s.get("created_at"),
                "latest_date": s.get("created_at"),
                "sales": [],
            }
        c = by_customer[key]
        c["sales_count"] += 1
        c["total"] += float(s.get("total") or 0)
        c["sales"].append({
            "id": s.get("id"),
            "receipt_number": s.get("receipt_number") or s.get("id"),
            "total": s.get("total"),
            "created_at": s.get("created_at"),
            "payment_method": s.get("payment_method"),
        })
        if s.get("created_at") < c["oldest_date"]:
            c["oldest_date"] = s.get("created_at")
        if s.get("created_at") > c["latest_date"]:
            c["latest_date"] = s.get("created_at")
        total_out += float(s.get("total") or 0)
    rows = sorted(by_customer.values(), key=lambda x: -x["total"])
    # Enrich each row with last reminder tier + active payment promise
    cust_keys = [r.get("customer_id") or r.get("customer_name") for r in rows]
    reminders_map = {}
    promises_map = {}
    if cust_keys:
        async for r in db.payment_reminders.find({"customer_key": {"$in": cust_keys}}, {"_id": 0}).sort("sent_at", -1):
            k = r.get("customer_key")
            if k not in reminders_map:
                reminders_map[k] = {"tier": r.get("tier"), "sent_at": r.get("sent_at")}
        async for p in db.payment_promises.find({"customer_key": {"$in": cust_keys}, "status": "active"}, {"_id": 0}):
            promises_map[p.get("customer_key")] = {
                "promised_date": p.get("promised_date"),
                "promised_amount": p.get("promised_amount"),
                "note": p.get("note"),
            }
    for r in rows:
        k = r.get("customer_id") or r.get("customer_name")
        if k in reminders_map:
            r["last_reminder"] = reminders_map[k]
        if k in promises_map:
            r["payment_promise"] = promises_map[k]
    return {
        "total_outstanding": total_out,
        "customer_count": len(rows),
        "by_customer": rows,
    }


# ========== PAYMENT PROMISES (customer commits to pay by date) ==========

@router.post("/accounts-receivable/promise")
async def record_payment_promise(data: dict, current_user: dict = Depends(get_current_user)):
    """Record a customer's payment promise. Pauses dunning until promised_date passes.
    Body: { customer_key, promised_date (YYYY-MM-DD), promised_amount?, note? }"""
    key = (data.get("customer_key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="customer_key required")
    promised_date = (data.get("promised_date") or "").strip()
    if not promised_date or len(promised_date) < 10:
        raise HTTPException(status_code=400, detail="promised_date required (YYYY-MM-DD)")
    # Normalize to end-of-day so the promise is honored *through* that date
    iso_date = promised_date[:10] + "T23:59:59+00:00"
    doc = {
        "id": f"pp_{uuid.uuid4().hex[:8]}",
        "customer_key": key,
        "promised_date": iso_date,
        "promised_amount": float(data.get("promised_amount") or 0) or None,
        "note": (data.get("note") or "")[:500],
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    # Deactivate any existing active promise for this customer first
    await db.payment_promises.update_many(
        {"customer_key": key, "status": "active"},
        {"$set": {"status": "superseded", "superseded_at": doc["created_at"]}},
    )
    await db.payment_promises.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/accounts-receivable/promise/{customer_key}")
async def clear_payment_promise(customer_key: str, current_user: dict = Depends(get_current_user)):
    res = await db.payment_promises.update_many(
        {"customer_key": customer_key, "status": "active"},
        {"$set": {"status": "cleared", "cleared_at": datetime.now(timezone.utc).isoformat(), "cleared_by": current_user["id"]}},
    )
    return {"cleared": res.modified_count}


# ========== BULK BARCODE RE-ISSUE ==========

@router.post("/admin/reissue-barcodes")
async def reissue_legacy_barcodes(data: dict = None, current_user: dict = Depends(get_current_user)):
    """Migrate any non-5812-prefixed variant barcodes to the new 5812-* format.
    Admin/director only. Logs old↔new mapping in db.barcode_migrations for audit.
    Body: { dry_run?: bool, location_id?: str (filter scope) }"""
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "system_admin", "executive director", "adviser", "director", "manager"} and not is_system_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admin/director/manager can re-issue barcodes")
    dry_run = bool((data or {}).get("dry_run"))
    loc_filter = (data or {}).get("location_id")
    # Find all products with at least one variant whose barcode doesn't start with 5812-
    query = {"variants": {"$elemMatch": {"barcode": {"$not": {"$regex": "^5812-"}}}}}
    if loc_filter:
        query["location_id"] = loc_filter
    products = await db.products.find(query, {"_id": 0}).to_list(2000)
    mappings = []
    updated_count = 0
    # Local import to avoid circulars at top
    from routers.products import _generate_variant_barcode
    for p in products:
        if not p.get("location_id"):
            continue
        for i, v in enumerate(p.get("variants") or []):
            old = v.get("barcode") or ""
            if old.startswith("5812-"):
                continue
            new_barcode = await _generate_variant_barcode(p["location_id"], i + 1)
            mappings.append({"product_id": p["id"], "variant_id": v.get("id"), "old": old, "new": new_barcode, "product_name": p.get("name")})
            if not dry_run:
                await db.products.update_one(
                    {"id": p["id"], "variants.id": v["id"]},
                    {"$set": {"variants.$.barcode": new_barcode, "variants.$.barcode_auto_generated": True}}
                )
                updated_count += 1
    if not dry_run and mappings:
        await db.barcode_migrations.insert_one({
            "id": f"bcmig_{uuid.uuid4().hex[:8]}",
            "performed_by": current_user["id"],
            "performed_by_name": current_user.get("name", ""),
            "performed_at": datetime.now(timezone.utc).isoformat(),
            "mapping_count": len(mappings),
            "mappings": mappings,
        })
    return {"updated": updated_count, "candidates": len(mappings), "dry_run": dry_run, "mappings": mappings[:50]}


@router.get("/public/quotes/{quote_number}")
async def public_quote_lookup(quote_number: str):
    """Public lookup — used by the customer-facing quote-acceptance page.
    No auth required, but verify=phone OR email is needed before accept."""
    inv = await db.invoices.find_one(
        {"$or": [{"id": quote_number}, {"invoice_number": quote_number}], "is_quote": True},
        {"_id": 0}
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Quote not found")
    # Return sanitised public view (hide internal IDs / staff info)
    return {
        "invoice_number": inv.get("invoice_number"),
        "status": inv.get("status"),
        "customer_name": inv.get("customer_name"),
        "customer_phone": inv.get("customer_phone"),
        "customer_email": inv.get("customer_email"),
        "items": inv.get("items") or [],
        "subtotal": inv.get("subtotal"),
        "total": inv.get("total"),
        "discount": inv.get("discount"),
        "tax_amount": inv.get("tax_amount"),
        "due_date": inv.get("due_date"),
        "notes": inv.get("notes"),
        "issued_by_name": inv.get("issued_by_name"),
        "created_at": inv.get("created_at"),
        "accepted_at": inv.get("accepted_at"),
        "receipt_number": inv.get("receipt_number"),
    }


@router.post("/public/quotes/{quote_number}/accept")
async def public_accept_quote(quote_number: str, data: dict):
    """Customer-initiated quote acceptance (public, no auth).
    Verifies customer identity via phone OR email match against the original quote,
    then flips the quote to status='accepted' and creates a draft invoice ready for staff to convert.
    Body: { verification: <phone-last-4 OR email> }
    """
    inv = await db.invoices.find_one(
        {"$or": [{"id": quote_number}, {"invoice_number": quote_number}], "is_quote": True},
        {"_id": 0}
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Quote not found")
    if inv.get("status") == "accepted":
        return {"message": "Already accepted", "accepted_at": inv.get("accepted_at")}
    if inv.get("status") == "converted":
        raise HTTPException(status_code=400, detail="Quote was already converted to a sale")
    if inv.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Quote was cancelled and cannot be accepted")
    verification = (data or {}).get("verification", "").strip().lower()
    if not verification:
        raise HTTPException(status_code=400, detail="Verification required (your phone last 4 or email)")
    matches = False
    inv_phone = (inv.get("customer_phone") or "").replace(" ", "").replace("-", "").replace("+", "")
    inv_email = (inv.get("customer_email") or "").lower()
    if inv_email and verification == inv_email:
        matches = True
    elif inv_phone and (verification == inv_phone or inv_phone.endswith(verification.lstrip("+").replace(" ", "").replace("-", ""))):
        matches = True
    if not matches:
        raise HTTPException(status_code=403, detail="Verification did not match this quote's customer")
    now = datetime.now(timezone.utc)
    # Flip to accepted and convert to a draft invoice (staff still needs to finalise into a sale)
    new_inv_number = inv.get("invoice_number", "").replace("QUOTE-", "INV-DRAFT-") + "-A"
    await db.invoices.update_one(
        {"id": inv["id"]},
        {"$set": {
            "status": "accepted",
            "accepted_at": now.isoformat(),
            "linked_invoice_number": new_inv_number,
            "updated_at": now.isoformat(),
        }}
    )
    # Spawn a follow-on draft invoice ready for staff
    draft = {
        **{k: v for k, v in inv.items() if k not in ("id", "status", "is_quote", "_id")},
        "id": new_inv_number,
        "invoice_number": new_inv_number,
        "status": "draft",
        "is_quote": False,
        "spawned_from_quote": inv.get("invoice_number"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.invoices.insert_one(draft)
    return {"message": "Quote accepted", "accepted_at": now.isoformat(), "draft_invoice_number": new_inv_number}
