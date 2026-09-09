"""Public online shop — product list + order placement for anonymous visitors.

Staff decide what the public may buy by ticking `sell_online` on a product
(Sales → Products). Nothing is exposed by default.

Orders deliberately run through `routers.sales.create_sale`, the SAME code
path the POS uses, so stock decrement, resource bookings, event tickets,
customer accounts and ledger posting all behave identically — an online order
is just a sale whose cashier happens to be the website. Prices and totals are
ALWAYS recomputed from the database; the basket the browser posts is treated as
untrusted input.

Online orders land as `payment_status: pending` for staff to confirm, so no
money hits the ledger until someone actually collects it.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone

from deps import db, logger

router = APIRouter(prefix="/api/public", tags=["public-shop"])

MAX_LINE_QTY = 50
MAX_LINES = 20


async def _country_of_location(location_id: str) -> str:
    """ISO-ish country code for a location, walking up to the parent campus
    (sub-locations often don't carry a country of their own)."""
    seen = set()
    loc_id = location_id
    while loc_id and loc_id not in seen:
        seen.add(loc_id)
        loc = await db.locations.find_one({"id": loc_id}, {"_id": 0, "country": 1, "parent_id": 1})
        if not loc:
            return ""
        country = (loc.get("country") or "").strip()
        if country:
            c = country.lower()
            if c in ("uganda", "ug"):
                return "UG"
            if c in ("united states", "usa", "us", "united states of america"):
                return "US"
            return country.upper()[:2]
        loc_id = loc.get("parent_id")
    return ""


@router.get("/products")
async def public_products(country: Optional[str] = Query(None)):
    """In-stock products a staffer has flagged `sell_online`."""
    products = await db.products.find(
        {"sell_online": True, "is_archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "description": 1, "price": 1, "currency": 1,
         "stock": 1, "image_url": 1, "category": 1, "location_id": 1, "track_stock": 1},
    ).sort("name", 1).to_list(200)

    out = []
    country_cache: dict = {}
    for p in products:
        if p.get("track_stock") is not False and float(p.get("stock") or 0) <= 0:
            continue  # sold out
        loc = p.get("location_id") or ""
        if loc not in country_cache:
            country_cache[loc] = await _country_of_location(loc) if loc else ""
        p["country"] = country_cache[loc]
        if country and p["country"] and p["country"] != country.upper():
            continue
        out.append(p)
    return out


@router.post("/orders")
async def public_create_order(data: dict):
    """Place an online order. Totals are recomputed server-side."""
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    items = data.get("items") or []
    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required")
    if "@" not in email or len(email) > 200:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if not items or not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Your basket is empty")
    if len(items) > MAX_LINES:
        raise HTTPException(status_code=400, detail=f"Too many different items (max {MAX_LINES})")

    # Re-price everything from the database — never trust the basket's prices.
    wanted: dict = {}
    for it in items:
        pid = (it.get("product_id") or "").strip()
        qty = int(it.get("quantity") or it.get("qty") or 1)
        if not pid:
            raise HTTPException(status_code=400, detail="A basket line is missing its product")
        if qty < 1 or qty > MAX_LINE_QTY:
            raise HTTPException(status_code=400, detail=f"Quantity must be between 1 and {MAX_LINE_QTY}")
        wanted[pid] = wanted.get(pid, 0) + qty

    products = {
        p["id"]: p
        async for p in db.products.find({"id": {"$in": list(wanted)}}, {"_id": 0})
    }
    sale_items = []
    total = 0.0
    location_id = ""
    currency = ""
    for pid, qty in wanted.items():
        prod = products.get(pid)
        if not prod or not prod.get("sell_online"):
            raise HTTPException(status_code=400, detail="One of those items is no longer available online")
        if prod.get("track_stock") is not False and float(prod.get("stock") or 0) < qty:
            raise HTTPException(status_code=409, detail=f"Only {int(prod.get('stock') or 0)} × {prod.get('name')} left")
        price = float(prod.get("price") or 0)
        total += price * qty
        location_id = location_id or (prod.get("location_id") or "")
        currency = currency or (prod.get("currency") or "")
        sale_items.append({
            "product_id": pid, "name": prod.get("name"), "price": price,
            "qty": qty, "units_per_pack": int(prod.get("units_per_pack") or 1),
        })

    # Reuse the POS path so an online order is a first-class sale.
    from routers.sales import SaleCreate, create_sale
    payload = SaleCreate(
        items=sale_items, total=round(total, 2), payment_method="online",
        customer_name=name, customer_phone=phone, location_id=location_id,
        notes=f"Online order · {email}" + (f" · {data.get('notes')}" if data.get("notes") else ""),
    )
    website_user = {
        "id": "public_web", "name": "Website order", "role": "system",
        "location_id": location_id, "location_ids": [location_id] if location_id else [],
    }
    sale = await create_sale(payload, website_user)
    try:
        await db.sales.update_one(
            {"id": sale["id"]},
            {"$set": {"channel": "online", "customer_email": email,
                      "online_order_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception as ex:
        logger.warning(f"online order {sale.get('id')} tagging skipped: {ex}")

    return {
        "id": sale["id"], "receipt_number": sale.get("receipt_number"),
        "total": sale.get("total"), "currency": currency or "UGX",
        "payment_status": sale.get("payment_status"),
        "message": "Order received — we'll email you to arrange payment and collection.",
    }
