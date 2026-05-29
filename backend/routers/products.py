"""Product CRUD + variant management — extracted from financial.py"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, get_campus_filter, is_system_admin, require_sales_view
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api", tags=["products"], dependencies=[Depends(require_sales_view)])


# ---------- Helpers ----------
COUNTRY_TO_CODE = {
    "uganda": "UG", "kenya": "KE", "usa": "US", "united states": "US",
    "haiti": "HT", "thailand": "TH",
}


def _country_code(country: str) -> str:
    if not country:
        return "XX"
    return COUNTRY_TO_CODE.get(country.strip().lower(), country[:2].upper())


def _abbr(name: str) -> str:
    if not name:
        return "XXX"
    words = [w for w in name.replace(":", " ").replace("/", " ").split() if w and not w.isdigit()]
    if not words:
        return "XXX"
    if len(words) == 1:
        return words[0][:3].upper()
    return ("".join(w[0] for w in words[:3]) + words[-1][:1]).upper()[:3] or "XXX"


def _can_issue_barcodes(user: dict) -> bool:
    """Admins, directors, and managers may issue / change product barcodes."""
    if is_system_admin(user):
        return True
    role = (user.get("role") or "").lower()
    return role in {"admin", "system_admin", "executive director", "director", "adviser",
                    "manager", "leader", "coordinator"}


async def _generate_variant_barcode(product_location_id: str, variant_num: int) -> str:
    """Generate a 58:12-prefixed barcode for a variant.
    Format: 5812-{COUNTRY}{ABBR}-{DDMMYY}-V{NN}-{NNNN}
    Uses an atomic per-day-per-product-location counter for uniqueness."""
    loc = None
    if product_location_id:
        loc = await db.locations.find_one(
            {"id": product_location_id},
            {"_id": 0, "country": 1, "code": 1, "name": 1}
        )
    country_code = _country_code(loc.get("country") if loc else "")
    if loc and loc.get("code"):
        abbr = _abbr(loc["code"])
    elif loc and loc.get("name"):
        abbr = _abbr(loc["name"])
    else:
        abbr = "XXX"
    today = datetime.now(timezone.utc)
    date_tag = today.strftime("%d%m%y")
    counter_key = f"variant_barcode_{product_location_id or 'NOLOC'}_{date_tag}"
    counter = await db.counters.find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = (counter or {}).get("seq", 1)
    return f"5812-{country_code}{abbr}-{date_tag}-V{variant_num:02d}-{seq:04d}"


class ProductCreate(BaseModel):
    name: str; description: Optional[str] = None; price: float = 0; currency: str = "UGX"; stock: int = 0
    category: Optional[str] = None; sku: Optional[str] = None; reorder_level: int = 5; location_id: Optional[str] = None
    has_variants: bool = False; product_type: Optional[str] = None; variants: Optional[List[dict]] = None
    # Bulk discount tiers — list of {min_qty, discount_pct} sorted by min_qty asc
    qty_discount_tiers: Optional[List[dict]] = None
    max_discount_pct: Optional[float] = 20

class ProductUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; price: Optional[float] = None
    currency: Optional[str] = None; sku: Optional[str] = None
    stock: Optional[int] = None; category: Optional[str] = None; reorder_level: Optional[int] = None; location_id: Optional[str] = None
    has_variants: Optional[bool] = None; product_type: Optional[str] = None
    variants: Optional[List[dict]] = None
    qty_discount_tiers: Optional[List[dict]] = None
    max_discount_pct: Optional[float] = None

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
    # If product has variants, main stock is derived from variant totals
    if update_data.get("has_variants") and update_data.get("variants"):
        update_data["stock"] = sum(int(v.get("stock", 0) or 0) for v in update_data["variants"])
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    return await db.products.find_one({"id": product_id}, {"_id": 0})

@router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    await db.products.delete_one({"id": product_id}); return {"message": "Product deleted"}

# ========== PRODUCT VARIANTS + BARCODES ==========

@router.post("/products/{product_id}/variants")
async def add_product_variant(product_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a variant to a product (size, color, etc.)."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.get("variants") is None:
        await db.products.update_one({"id": product_id}, {"$set": {"variants": []}})
    variant_num = len(product.get("variants") or []) + 1
    # Use manually entered barcode if provided, else auto-generate 5812-* prefixed
    manual_barcode = (data.get("barcode") or "").strip()
    if manual_barcode:
        if not _can_issue_barcodes(current_user):
            raise HTTPException(status_code=403, detail="Only admins, directors, and managers can set product barcodes manually")
        barcode = manual_barcode
    else:
        barcode = await _generate_variant_barcode(product.get("location_id", ""), variant_num)
    variant = {
        "id": f"var_{uuid.uuid4().hex[:6]}",
        "name": data.get("name", ""),
        "type": data.get("type", ""),
        "value": data.get("value", ""),
        "price": float(data.get("price", 0)),
        "stock": int(data.get("stock", 0)),
        "sku": data.get("sku", ""),
        "barcode": barcode,
        "barcode_auto_generated": not bool(manual_barcode),
        # Pack conversion: 1 variant = N base units (e.g. 1 tray of 30 eggs)
        "units_per_pack": int(data.get("units_per_pack", 1)) or 1,
        # Optional packaging cost (e.g. physical egg tray = UGX 500)
        "packaging_cost": float(data.get("packaging_cost", 0) or 0),
        "packaging_label": data.get("packaging_label", "") or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.products.update_one({"id": product_id}, {
        "$push": {"variants": variant},
        "$set": {"has_variants": True, "updated_at": datetime.now(timezone.utc).isoformat()},
    })
    return variant


@router.put("/products/{product_id}/variants/{variant_id}")
async def update_product_variant(product_id: str, variant_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a variant. Barcode changes require admin/director/manager."""
    allowed = {"name", "type", "value", "price", "stock", "sku", "barcode",
               "units_per_pack", "packaging_cost", "packaging_label"}
    if "barcode" in data and not _can_issue_barcodes(current_user):
        raise HTTPException(status_code=403, detail="Only admins, directors, and managers can change product barcodes")
    update_fields = {f"variants.$.{k}": v for k, v in data.items() if k in allowed}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields")
    if "barcode" in data:
        update_fields["variants.$.barcode_auto_generated"] = False
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
    """Auto-generate 5812-* barcodes for all variants of a product that don't have one.
    Only admins, directors, and managers may issue barcodes."""
    if not _can_issue_barcodes(current_user):
        raise HTTPException(status_code=403, detail="Only admins, directors, and managers can issue product barcodes")
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.get("location_id"):
        raise HTTPException(status_code=400, detail="Set product location/campus first — the barcode prefix derives from it.")
    updated = 0
    for i, v in enumerate(product.get("variants") or []):
        if not v.get("barcode") or not str(v.get("barcode")).startswith("5812-"):
            barcode = await _generate_variant_barcode(product["location_id"], i + 1)
            await db.products.update_one(
                {"id": product_id, "variants.id": v["id"]},
                {"$set": {"variants.$.barcode": barcode, "variants.$.barcode_auto_generated": True}}
            )
            updated += 1
    return {"message": f"Generated {updated} barcodes", "format": "5812-{COUNTRY}{ABBR}-{DDMMYY}-V{NN}-{NNNN}"}



@router.get("/products/{product_id}/barcode-labels")
async def get_barcode_labels(product_id: str, current_user: dict = Depends(get_current_user)):
    """Generate printable barcode SVGs for product variants."""
    import barcode
    from barcode.writer import SVGWriter
    import io
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    labels = []
    for v in (product.get("variants") or []):
        code = v.get("barcode") or v.get("sku") or v.get("id", "")
        try:
            bc = barcode.get("code128", code, writer=SVGWriter())
            buf = io.BytesIO()
            bc.write(buf)
            svg = buf.getvalue().decode()
            labels.append({"variant_id": v["id"], "name": v.get("name", ""), "barcode": code, "price": v.get("price", 0), "svg": svg})
        except Exception as e:
            labels.append({"variant_id": v.get("id", ""), "name": v.get("name", ""), "barcode": code, "error": str(e)})
    # Also generate for the main product if no variants
    if not product.get("variants"):
        code = product.get("sku") or product["id"]
        try:
            bc = barcode.get("code128", code, writer=SVGWriter())
            buf = io.BytesIO(); bc.write(buf)
            labels.append({"variant_id": "main", "name": product["name"], "barcode": code, "price": product.get("price", 0), "svg": buf.getvalue().decode()})
        except Exception as e:
            labels.append({"variant_id": "main", "name": product["name"], "barcode": code, "error": str(e)})
    return {"product_name": product["name"], "labels": labels}



# ========== STOCK MOVEMENTS (Odoo-style audit trail) ==========

@router.post("/products/{product_id}/stock-movement")
async def record_stock_movement(product_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Adjust stock with an audit-trail record.
    Body: { delta (int, +inbound/-outbound), reason (purchase|sale|adjustment|transfer|return|count|loss),
            variant_id?, notes?, reference? (e.g. sale_id, PO number) }"""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        delta = int(data.get("delta", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="delta must be an integer")
    if delta == 0:
        raise HTTPException(status_code=400, detail="delta cannot be 0")
    reason = (data.get("reason") or "adjustment").strip()
    if reason not in {"purchase", "sale", "adjustment", "transfer", "return", "count", "loss", "initial"}:
        raise HTTPException(status_code=400, detail="invalid reason")
    variant_id = data.get("variant_id")
    if variant_id:
        variant = next((v for v in (product.get("variants") or []) if v.get("id") == variant_id), None)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        before = int(variant.get("stock", 0) or 0)
        after = before + delta
        if after < 0:
            raise HTTPException(status_code=400, detail=f"Insufficient variant stock ({before} on hand)")
        await db.products.update_one(
            {"id": product_id, "variants.id": variant_id},
            {"$set": {"variants.$.stock": after}},
        )
        # Recompute parent product stock from variants
        product = await db.products.find_one({"id": product_id}, {"_id": 0})
        new_total = sum(int(v.get("stock", 0) or 0) for v in (product.get("variants") or []))
        await db.products.update_one({"id": product_id}, {"$set": {"stock": new_total}})
    else:
        before = int(product.get("stock", 0) or 0)
        after = before + delta
        if after < 0:
            raise HTTPException(status_code=400, detail=f"Insufficient stock ({before} on hand)")
        await db.products.update_one({"id": product_id}, {"$set": {"stock": after}})
    movement = {
        "id": f"sm_{uuid.uuid4().hex[:10]}",
        "product_id": product_id,
        "product_name": product.get("name"),
        "variant_id": variant_id,
        "delta": delta,
        "before": before,
        "after": after,
        "reason": reason,
        "notes": (data.get("notes") or "")[:500],
        "reference": (data.get("reference") or "")[:120],
        "location_id": product.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.stock_movements.insert_one(movement)
    movement.pop("_id", None)
    return movement


@router.get("/products/{product_id}/stock-movements")
async def list_stock_movements(product_id: str, limit: int = 100, current_user: dict = Depends(get_current_user)):
    return await db.stock_movements.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 500))


@router.get("/stock-movements")
async def list_all_stock_movements(reason: Optional[str] = None, limit: int = 200, current_user: dict = Depends(get_current_user)):
    """All recent stock movements across the user's scope (for the warehouse log view)."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    if reason:
        query["reason"] = reason
    return await db.stock_movements.find(query, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))


# ========== REORDER ALERTS ==========

@router.get("/products/reorder-alerts")
async def reorder_alerts(current_user: dict = Depends(get_current_user)):
    """Products at or below their `reorder_level` (Odoo-style reorder rule)."""
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    all_products = await db.products.find(query, {"_id": 0}).to_list(2000)
    alerts = []
    for p in all_products:
        reorder = int(p.get("reorder_level") or 0)
        if reorder <= 0:
            continue
        # Per-variant alerts if has_variants
        if p.get("has_variants") and p.get("variants"):
            low_variants = [v for v in p["variants"] if int(v.get("stock", 0) or 0) <= reorder]
            if low_variants:
                alerts.append({
                    "product_id": p["id"],
                    "product_name": p.get("name"),
                    "reorder_level": reorder,
                    "location_id": p.get("location_id"),
                    "low_variants": [{"variant_id": v["id"], "name": v.get("name"), "stock": v.get("stock", 0)} for v in low_variants],
                })
        else:
            stock = int(p.get("stock", 0) or 0)
            if stock <= reorder:
                alerts.append({
                    "product_id": p["id"],
                    "product_name": p.get("name"),
                    "reorder_level": reorder,
                    "stock": stock,
                    "location_id": p.get("location_id"),
                })
    return alerts


# ========== CUSTOMER PRICELISTS (per-customer pricing/discount) ==========

@router.get("/pricelists")
async def list_pricelists(current_user: dict = Depends(get_current_user)):
    campus = await get_campus_filter(current_user)
    query = {**campus} if campus else {}
    return await db.pricelists.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/pricelists")
async def create_pricelist(data: dict, current_user: dict = Depends(get_current_user)):
    """Create a customer pricelist.
    Body: { name, customer_id? (single), customer_ids? (multi), discount_pct?, product_prices? [{product_id, variant_id?, price}] }"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    doc = {
        "id": f"pl_{uuid.uuid4().hex[:10]}",
        "name": name,
        "customer_id": data.get("customer_id"),
        "customer_ids": data.get("customer_ids") or ([data["customer_id"]] if data.get("customer_id") else []),
        "discount_pct": float(data.get("discount_pct") or 0),
        "product_prices": data.get("product_prices") or [],
        "active": True,
        "location_id": current_user.get("active_campus_id") or current_user.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.pricelists.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/pricelists/{pricelist_id}")
async def update_pricelist(pricelist_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "customer_id", "customer_ids", "discount_pct", "product_prices", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.pricelists.update_one({"id": pricelist_id}, {"$set": update})
    return await db.pricelists.find_one({"id": pricelist_id}, {"_id": 0})


@router.delete("/pricelists/{pricelist_id}")
async def delete_pricelist(pricelist_id: str, current_user: dict = Depends(get_current_user)):
    await db.pricelists.delete_one({"id": pricelist_id})
    return {"message": "Pricelist deleted"}


@router.get("/pricelists/resolve")
async def resolve_pricelist(customer_id: str, product_id: str, variant_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Return the effective price for a customer × product (variant optional).
    Looks up the customer's active pricelist; returns { price, source }."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    base_price = float(product.get("price") or 0)
    if variant_id:
        variant = next((v for v in (product.get("variants") or []) if v.get("id") == variant_id), None)
        if variant:
            base_price = float(variant.get("price") or 0) or base_price
    # Find active pricelist for this customer
    pl = await db.pricelists.find_one({
        "$or": [{"customer_id": customer_id}, {"customer_ids": customer_id}],
        "active": True,
    }, {"_id": 0})
    if not pl:
        return {"price": base_price, "source": "base", "currency": product.get("currency", "UGX")}
    # 1) Explicit product/variant override
    for entry in (pl.get("product_prices") or []):
        if entry.get("product_id") == product_id and (entry.get("variant_id") or None) == (variant_id or None):
            return {"price": float(entry.get("price") or base_price), "source": "pricelist_override", "pricelist_id": pl["id"], "pricelist_name": pl.get("name")}
    # 2) Blanket % discount
    pct = float(pl.get("discount_pct") or 0)
    if pct > 0:
        return {
            "price": round(base_price * (1 - pct / 100.0), 2),
            "source": "pricelist_discount",
            "discount_pct": pct,
            "pricelist_id": pl["id"], "pricelist_name": pl.get("name"),
        }
    return {"price": base_price, "source": "base", "currency": product.get("currency", "UGX")}
