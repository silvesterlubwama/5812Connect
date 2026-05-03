"""Marketplace Invoices — editable, printable, convertible to sales.

Workflow:
  draft  → editable; can be printed/sent
  sent   → editable but flagged (customer has been notified)
  converted → linked to a real sale receipt; final
  cancelled → cannot be revived
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, require_staff, _audit, get_campus_filter
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


async def _next_invoice_number():
    today = datetime.now(timezone.utc)
    date_tag = today.strftime("%Y%m%d")
    counter = await db.counters.find_one_and_update(
        {"_id": f"invoices_{date_tag}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    return f"INV-DRAFT-{date_tag}-{seq:04d}"


@router.get("/invoices")
async def list_invoices(status: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """List invoices visible to user. Filter by status (draft/sent/converted/cancelled)."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    if status:
        query["status"] = status
    return await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/invoices")
async def create_invoice(data: InvoiceCreate, current_user: dict = Depends(require_staff)):
    items = [i.model_dump() for i in data.items]
    invoice_number = await _next_invoice_number()
    doc = {
        "id": invoice_number,
        "invoice_number": invoice_number,
        "status": "draft",
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
    if "status" in update and update["status"] not in {"draft", "sent", "cancelled"}:
        raise HTTPException(status_code=400, detail="Status must be draft / sent / cancelled (use convert endpoint for sale)")
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

    # Decrement stock for each item
    for item in items:
        if item.get("product_id"):
            if item.get("variant_id"):
                await db.products.update_one(
                    {"id": item["product_id"], "variants.id": item["variant_id"]},
                    {"$inc": {"variants.$.stock": -item.get("qty", 1), "stock": -item.get("qty", 1)}}
                )
            else:
                await db.products.update_one({"id": item["product_id"]}, {"$inc": {"stock": -item.get("qty", 1)}})

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
    await _audit(current_user["id"], "convert", "invoice_to_sale", f"{invoice_id}→{receipt_number}")
    return {"invoice_id": invoice_id, "sale": sale, "receipt_number": receipt_number}
