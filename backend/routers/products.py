"""Product CRUD + variant management — extracted from financial.py"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import db, get_current_user, get_campus_filter
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api", tags=["products"])


class ProductCreate(BaseModel):
    name: str; description: Optional[str] = None; price: float = 0; currency: str = "UGX"; stock: int = 0
    category: Optional[str] = None; sku: Optional[str] = None; reorder_level: int = 5; location_id: Optional[str] = None
    has_variants: bool = False; product_type: Optional[str] = None; variants: Optional[List[dict]] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None; price: Optional[float] = None
    currency: Optional[str] = None; sku: Optional[str] = None
    stock: Optional[int] = None; category: Optional[str] = None; reorder_level: Optional[int] = None; location_id: Optional[str] = None
    has_variants: Optional[bool] = None; product_type: Optional[str] = None
    variants: Optional[List[dict]] = None

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
