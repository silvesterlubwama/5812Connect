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
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from datetime import datetime, timezone

import os

from deps import db, logger

router = APIRouter(prefix="/api/public", tags=["public-shop"])

ORDER_ALERT_EMAIL = os.environ.get("ORDER_ALERT_EMAIL", "")

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
         "stock": 1, "image_url": 1, "images": 1, "category": 1, "location_id": 1,
         "track_stock": 1},
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
async def public_create_order(data: dict, request: Request):
    """Place an online order. Totals are recomputed server-side.

    `payment_option`:
      • `collection` (default) — order lands pending, staff arrange payment.
      • `online` — same sale, then a Flutterwave checkout URL is returned for
        the buyer to pay immediately (`online_method`: card | mobile_money).
    """
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    items = data.get("items") or []
    payment_option = (data.get("payment_option") or "collection").strip().lower()
    online_method = (data.get("online_method") or "card").strip().lower()
    network = (data.get("network") or "").strip().upper()
    if payment_option not in ("collection", "online"):
        raise HTTPException(status_code=400, detail="Choose pay now or pay on collection")
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

    # Fail BEFORE we reserve stock if the buyer picked a method we can't take.
    if payment_option == "collection":
        from routers.payments_flutterwave import _cfg as _pay_cfg
        if not (await _pay_cfg(require_keys=False)).get("allow_pay_on_collection", True):
            raise HTTPException(status_code=400, detail="Orders must be paid online")
    if payment_option == "online":
        if online_method not in ("card", "mobile_money"):
            raise HTTPException(status_code=400, detail="Choose card or mobile money")
        from routers.payments_flutterwave import _cfg as _pay_cfg
        pay_cfg = await _pay_cfg()
        if online_method == "card" and not pay_cfg.get("allow_card", True):
            raise HTTPException(status_code=400, detail="Card payment is switched off")
        if online_method == "mobile_money":
            if not pay_cfg.get("allow_mobile_money", True):
                raise HTTPException(status_code=400, detail="Mobile money is switched off")
            if not phone or network not in ("MTN", "AIRTEL"):
                raise HTTPException(status_code=400, detail="Enter your mobile money number and pick MTN or Airtel")

    # Reuse the POS path so an online order is a first-class sale.
    from routers.sales import SaleCreate, create_sale
    payload = SaleCreate(
        items=sale_items, total=round(total, 2),
        payment_method="mobile_money" if (payment_option == "online" and online_method == "mobile_money") else "online",
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
                      "online_order_at": datetime.now(timezone.utc).isoformat(),
                      "payment_option": payment_option}},
        )
    except Exception as ex:
        logger.warning(f"online order {sale.get('id')} tagging skipped: {ex}")

    if payment_option == "online":
        from routers.payments_flutterwave import init_payment
        origin = (request.headers.get("origin") or "").rstrip("/")
        if not origin:
            ref_hdr = request.headers.get("referer") or ""
            origin = "/".join(ref_hdr.split("/")[:3]) if ref_hdr.startswith("http") else ""
        try:
            init = await init_payment(
                sale, email=email, name=name, phone=phone,
                method=online_method, network=network, origin=origin,
            )
        except HTTPException:
            # The provider never gave us a checkout link — drop the reservation
            # so stock isn't held hostage by a failed handshake.
            await _release_order(sale)
            raise
        return {
            "id": sale["id"], "receipt_number": sale.get("receipt_number"),
            "total": sale.get("total"), "currency": init["currency"],
            "payment_status": sale.get("payment_status"),
            "payment_url": init["payment_url"], "tx_ref": init["tx_ref"],
            "message": "Redirecting you to a secure payment page…",
        }

    await _notify_order(sale, name, email, phone, sale_items, currency or "UGX")

    return {
        "id": sale["id"], "receipt_number": sale.get("receipt_number"),
        "total": sale.get("total"), "currency": currency or "UGX",
        "payment_status": sale.get("payment_status"),
        "message": "Order received — we'll email you to arrange payment and collection.",
    }


async def _release_order(sale: dict):
    """Undo a reservation: delete the sale row and hand the stock back."""
    try:
        await db.sales.delete_one({"id": sale["id"]})
        for item in (sale.get("items") or []):
            pid = item.get("product_id")
            if not pid:
                continue
            qty = int(item.get("qty") or 1)
            base_units = qty * max(1, int(item.get("units_per_pack") or 1))
            if item.get("variant_id"):
                await db.products.update_one(
                    {"id": pid, "variants.id": item["variant_id"]},
                    {"$inc": {"variants.$.stock": qty, "stock": base_units}},
                )
            else:
                await db.products.update_one({"id": pid}, {"$inc": {"stock": base_units}})
    except Exception as ex:
        logger.warning(f"failed to release order {sale.get('id')}: {ex}")


def _money(currency: str, amount) -> str:    return f"{currency} {float(amount or 0):,.0f}"


async def _notify_order(sale: dict, name: str, email: str, phone: str, items: list, currency: str):
    """Tell the team an order landed, and tell the buyer how to pay.

    Both are courtesy emails — `send_email_internal` swallows its own errors so
    a mail problem can never lose somebody's order.
    """
    from routers.email import send_email_internal, _base_html

    rows = "".join(
        f"<tr><td style='padding:6px 0'>{i['name']} × {i['qty']}</td>"
        f"<td style='padding:6px 0;text-align:right'>{_money(currency, i['price'] * i['qty'])}</td></tr>"
        for i in items
    )
    total_row = (
        f"<tr><td style='padding:8px 0;border-top:1px solid #e5e7eb'><strong>Total</strong></td>"
        f"<td style='padding:8px 0;border-top:1px solid #e5e7eb;text-align:right'>"
        f"<strong>{_money(currency, sale.get('total'))}</strong></td></tr>"
    )
    table = f"<table style='width:100%;font-size:14px;color:#444'>{rows}{total_row}</table>"
    ref = sale.get("receipt_number") or sale.get("id")

    if ORDER_ALERT_EMAIL:
        await send_email_internal(
            [ORDER_ALERT_EMAIL],
            f"New online order {ref} — {_money(currency, sale.get('total'))}",
            _base_html(
                f"<h2 style='color:#1a1a2e;margin:0 0 8px'>New online order</h2>"
                f"<p style='color:#444'><strong>{name}</strong> · {email}{' · ' + phone if phone else ''}</p>"
                f"{table}"
                f"<p style='color:#444;font-size:13px;margin-top:16px'>It's waiting in Sales as "
                f"<strong>pending payment</strong> — confirm it there once the money arrives and it will "
                f"post to the ledger automatically.</p>"
            ),
            kind="online_order_alert",
        )

    await send_email_internal(
        [email],
        f"We got your order ({ref})",
        _base_html(
            f"<h2 style='color:#1a1a2e;margin:0 0 8px'>Thanks, {name}!</h2>"
            f"<p style='color:#444;line-height:1.6'>Your order <strong>{ref}</strong> is reserved. "
            f"Here's what you asked for:</p>"
            f"{table}"
            f"<p style='color:#444;line-height:1.6;margin-top:16px'>We'll be in touch shortly to arrange "
            f"payment and collection. Reply to this email if anything needs changing.</p>"
        ),
        kind="online_order_receipt",
    )
