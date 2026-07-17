"""Public (token-based) endpoints: donor view + editor + kiosk scanning."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import base64
import hmac
import hashlib
import os as _os
import re
import json
from deps import db, logger, _audit, require_admin
from ._common import (
    _normalise_item,
    _shipment_units,
    _add_or_merge_item,
    _normalise_pallet,
    _persist_shipment_image,
    _waybill_html,
    _hash_pin,
    _make_edit_token,
    _verify_edit_token,
    require_shipment_editor,
    EDIT_TOKEN_TTL_HOURS,
    VALID_STATUSES,
    VALID_PRIORITIES,
    VALID_TRANSPORT_MODES,
    CONTAINER_40FT_HC,
    PUBLIC_ITEM_WISHLIST_FIELDS,
)

router = APIRouter(prefix="/api", tags=["shipments"])

@router.get("/public/shipments/{token}")
async def public_shipment(token: str, request: Request):
    """Public view. Two modes:

    - **No edit-token** (default) → wishlist-only. Each item exposes just
      `name / category / photo / priority / qty_needed / qty_acquired /
      source_url`. Everything else (weight, dims, pallet placement,
      transport_mode, qty_packed, image_urls, ISBN/UPC) is stripped so
      random link-clickers can't see what's actually going on the container
      or which items are travelling by suitcase.
    - **Valid `?edit_token=...`** query param OR admin JWT → full manifest
      with packing state, transport mode, and pallet layout. Same shape
      the admin sees.
    """
    s = await db.shipments.find_one({"token": token}, {"_id": 0})
    if not s or s.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Detect whether the caller is unlocked (PIN or admin JWT). We do it
    # here rather than as a Depends so that the endpoint stays fully open
    # in the wishlist case (no 401 for anonymous callers).
    unlocked = False
    edit_token = (request.query_params.get("edit_token") or "").strip()
    if edit_token:
        _v = _verify_edit_token(edit_token)
        if _v and _v.get("shipment_id") == s["id"]:
            unlocked = True
    if not unlocked:
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            try:
                from deps import _decode_jwt  # type: ignore
                payload = _decode_jwt(auth.split(" ", 1)[1])
                user = await db.users.find_one({"id": payload.get("user_id") or payload.get("id")}, {"_id": 0, "role": 1})
                if user and user.get("role") in ("admin", "super_admin"):
                    unlocked = True
            except Exception:
                pass

    items = s.get("items") or []
    still_needed = []
    already_acquired = []
    for i in items:
        if unlocked:
            snap = {k: v for k, v in i.items() if k not in ("donations", "created_at", "updated_at")}
        else:
            snap = {k: i.get(k) for k in PUBLIC_ITEM_WISHLIST_FIELDS if k in i}
        snap["qty_remaining"] = max(0, int(i.get("qty_needed") or 0) - int(i.get("qty_acquired") or 0))
        if snap["qty_remaining"] > 0:
            still_needed.append(snap)
        else:
            already_acquired.append(snap)
    pri_rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    still_needed.sort(key=lambda x: (pri_rank.get(x.get("priority", "normal"), 2), x.get("name", "").lower()))
    already_acquired.sort(key=lambda x: x.get("name", "").lower())

    # Totals are ALWAYS derived from the FULL item list so the public
    # wishlist progress bar stays accurate — we just don't reveal HOW that
    # weight is distributed unless unlocked. For anonymous callers we
    # count container-bound items only; suitcase + holdback items shouldn't
    # bump the container weight the donor sees.
    def _counts_for_container(items_):
        return sum(float(x.get("weight_kg") or 0) * int(x.get("qty_acquired") or 0)
                   for x in items_ if (x.get("transport_mode") or "container") == "container")
    total_weight = sum(float(i.get("weight_kg") or 0) * int(i.get("qty_acquired") or 0) for i in items) if unlocked else _counts_for_container(items)
    total_value = sum(float(i.get("value_usd") or 0) * int(i.get("qty_acquired") or 0) for i in items)
    cap = float(s.get("max_payload_kg") or 26000)
    pallets_lite = ([{
        "id": p.get("id"), "label": p.get("label"),
        "length_cm": p.get("length_cm") or 120,
        "width_cm":  p.get("width_cm")  or 80,
        "height_cm": p.get("height_cm") or 150,
        "x_cm": p.get("x_cm") or 0,
        "y_cm": p.get("y_cm") or 0,
        "color": p.get("color") or "",
    } for p in (s.get("pallets") or [])]) if unlocked else []
    donor_totals: dict[str, int] = {}
    donor_set = set()
    for it in items:
        for d in (it.get("donations") or []):
            name = (d.get("donor_name") or "Anonymous").strip() or "Anonymous"
            donor_set.add(name)
            if name.lower() != "anonymous":
                donor_totals[name] = donor_totals.get(name, 0) + int(d.get("qty") or 0)
    leaderboard = sorted(
        [{"donor_name": n, "total_qty": q} for n, q in donor_totals.items()],
        key=lambda x: x["total_qty"], reverse=True,
    )[:5]
    return {
        "id": s["id"],
        "name": s.get("name"),
        "dest_country": s.get("dest_country"),
        "description": s.get("description"),
        "target_ship_date": s.get("target_ship_date"),
        "status": s.get("status"),
        "units": s.get("units") or "metric",
        "unlocked": unlocked,
        "max_payload_kg": cap,
        "container_dims_cm": (s.get("container_dims_cm") or CONTAINER_40FT_HC) if unlocked else None,
        "still_needed": still_needed,
        "already_acquired": already_acquired,
        "pallets": pallets_lite,
        "totals": {
            "weight_kg": round(total_weight, 1),
            "weight_pct": round(min(100, (total_weight / cap) * 100), 1) if cap else 0,
            "value_usd": round(total_value, 2),
            "items_needed": len(still_needed),
            "items_acquired": len(already_acquired),
            "pallet_count": len(pallets_lite),
            "donor_count": len(donor_set),
            "leaderboard": leaderboard,
        },
        "ai_packing_text": (s.get("ai_packing_text") or "") if unlocked else "",
        "ai_packing_generated_at": s.get("ai_packing_generated_at") if unlocked else None,
        "pin_required": bool(s.get("access_pin_hash")),
    }


@router.post("/shipments/{shipment_id}/items/{item_id}/pack")
async def pack_item(shipment_id: str, item_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Move N units of an item into packed state. `mode` selects the transport
    channel — container / suitcase / holdback. Independent counter — never
    touches qty_acquired."""
    qty = max(1, int(data.get("qty") or 1))
    mode = (data.get("mode") or "container").lower()
    if mode not in VALID_TRANSPORT_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(VALID_TRANSPORT_MODES)}")
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {
            "$inc": {"items.$.qty_packed": qty},
            "$set": {
                "items.$.transport_mode": mode,
                "items.$.updated_at": now_iso,
            },
        },
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    s = await db.shipments.find_one(
        {"id": shipment_id, "items.id": item_id},
        {"_id": 0, "items.$": 1},
    )
    it = (s or {}).get("items", [{}])[0]
    return {
        "qty_packed": it.get("qty_packed") or 0,
        "qty_acquired": it.get("qty_acquired") or 0,
        "transport_mode": it.get("transport_mode") or "container",
        "over_packed": (it.get("qty_packed") or 0) > (it.get("qty_acquired") or 0),
    }


@router.post("/public/shipments/{token}/items/{item_id}/pack")
async def public_pack_item(token: str, item_id: str, data: dict, request: Request):
    """PIN-gated packing action — same shape as the admin route."""
    ctx = await require_shipment_editor(request, token)
    qty = max(1, int(data.get("qty") or 1))
    mode = (data.get("mode") or "container").lower()
    if mode not in VALID_TRANSPORT_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(VALID_TRANSPORT_MODES)}")
    now_iso = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one(
        {"id": ctx["shipment_id"], "items.id": item_id},
        {
            "$inc": {"items.$.qty_packed": qty},
            "$set": {
                "items.$.transport_mode": mode,
                "items.$.updated_at": now_iso,
            },
        },
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    s = await db.shipments.find_one(
        {"id": ctx["shipment_id"], "items.id": item_id},
        {"_id": 0, "items.$": 1},
    )
    it = (s or {}).get("items", [{}])[0]
    return {
        "qty_packed": it.get("qty_packed") or 0,
        "qty_acquired": it.get("qty_acquired") or 0,
        "transport_mode": it.get("transport_mode") or "container",
        "over_packed": (it.get("qty_packed") or 0) > (it.get("qty_acquired") or 0),
    }


@router.post("/public/shipments/{token}/items/{item_id}/donate")
async def public_donate(token: str, item_id: str, data: dict):
    """Anyone with the token marks an item as (partially) donated.
    Body: { qty: int, donor_name?: str (no email required) }
    Idempotency: each call appends to the donations log AND increments
    qty_acquired. No "undo donate" from the public side — that requires admin.
    """
    qty = int(data.get("qty") or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")
    donor_name = (data.get("donor_name") or "Anonymous").strip()[:60] or "Anonymous"
    s = await db.shipments.find_one({"token": token, "items.id": item_id}, {"_id": 0, "id": 1, "items.$": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Item not found on this shipment")
    item = (s.get("items") or [None])[0]
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    remaining = max(0, int(item.get("qty_needed") or 0) - int(item.get("qty_acquired") or 0))
    if qty > remaining:
        qty = remaining          # silently clamp — donor can't over-pledge past what's needed
    if qty <= 0:
        return {"item_id": item_id, "qty_recorded": 0, "message": "This item is already fully covered."}
    donation = {
        "id": f"don_{uuid.uuid4().hex[:8]}",
        "qty": qty,
        "donor_name": donor_name,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await db.shipments.update_one(
        {"id": s["id"], "items.id": item_id},
        {
            "$inc": {"items.$.qty_acquired": qty},
            "$push": {"items.$.donations": donation},
        },
    )
    return {
        "item_id": item_id, "qty_recorded": qty, "donor_name": donor_name,
        "message": f"Thank you{', ' + donor_name if donor_name != 'Anonymous' else ''}!",
    }


# ============================================================
# Public PIN login + scoped-edit endpoints
# These let trusted non-admin volunteers log in with a shipment-specific PIN
# and manage that ONE shipment's manifest. Pure subset of the admin endpoints.
# ============================================================

@router.post("/public/shipments/{token}/login")
async def public_login(token: str, data: dict):
    """Trade a PIN + editor name for an edit_token.  `editor_name` is now
    REQUIRED (iter224) so every downstream edit is audit-traceable to a real
    person.  Default TTL 12h; caller may pass ttl_hours ≤ 24."""
    pin = (data.get("pin") or "").strip()
    editor_name = (data.get("editor_name") or "").strip()
    if not pin:
        raise HTTPException(status_code=400, detail="PIN required")
    if not editor_name or len(editor_name) < 2:
        raise HTTPException(status_code=400, detail="Your name is required (min 2 characters)")
    s = await db.shipments.find_one(
        {"token": token}, {"_id": 0, "id": 1, "access_pin_hash": 1, "status": 1},
    )
    if not s or s.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="Shipment not found")
    if not s.get("access_pin_hash"):
        raise HTTPException(status_code=403, detail="No PIN is set on this shipment. Ask the admin to set one.")
    if not hmac.compare_digest(s["access_pin_hash"], _hash_pin(pin)):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    ttl = max(1, min(24, int(data.get("ttl_hours") or EDIT_TOKEN_TTL_HOURS)))
    # Log the login for audit
    await db.shipment_editor_logins.insert_one({
        "shipment_id": s["id"],
        "editor_name": editor_name[:80],
        "at": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": ttl,
    })
    return {
        "edit_token": _make_edit_token(s["id"], ttl_hours=ttl, editor_name=editor_name),
        "ttl_hours": ttl,
        "shipment_id": s["id"],
        "editor_name": editor_name[:80],
    }


@router.put("/public/shipments/{token}/container")
async def public_update_container(token: str, data: dict, request: Request):
    """Editor: change container dimensions + max payload."""
    ctx = await require_shipment_editor(request, token)
    c = data or {}
    container = {
        "length_cm": max(50, float(c.get("length_cm") or CONTAINER_40FT_HC["length_cm"])),
        "width_cm":  max(50, float(c.get("width_cm")  or CONTAINER_40FT_HC["width_cm"])),
        "height_cm": max(50, float(c.get("height_cm") or CONTAINER_40FT_HC["height_cm"])),
        "max_payload_kg": float(c.get("max_payload_kg") or CONTAINER_40FT_HC["max_payload_kg"]),
    }
    await db.shipments.update_one(
        {"id": ctx["shipment_id"]},
        {"$set": {
            "container_dims_cm": container,
            "max_payload_kg": container["max_payload_kg"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"updated": True, "container_dims_cm": container}


@router.post("/public/shipments/{token}/items")
async def public_add_item(token: str, data: dict, request: Request):
    """Editor: add an item to this shipment. Items with the same ISBN/UPC on
    the same pallet are merged (qty_acquired incremented) instead of duplicated."""
    ctx = await require_shipment_editor(request, token)
    units = await _shipment_units(ctx["shipment_id"])
    item = _normalise_item(data, units)
    return await _add_or_merge_item(ctx["shipment_id"], item)


@router.put("/public/shipments/{token}/items/{item_id}")
async def public_update_item(token: str, item_id: str, data: dict, request: Request):
    """Editor: edit any item field (name, dims, weight, pallet_id, position)."""
    ctx = await require_shipment_editor(request, token)
    allowed = {"name", "category", "qty_needed", "qty_acquired", "qty_packed",
               "weight_kg", "dims_cm", "photo_url", "image_urls", "value_usd",
               "notes", "priority", "pallet_id", "parent_id", "container_type",
               "transport_mode", "isbn", "upc",
               "author", "publisher", "ai_identified", "source_url",
               "x_cm", "y_cm", "z_cm"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k in ("qty_needed",):
            set_ops[f"items.$.{k}"] = max(1, int(v or 1))
        elif k in ("qty_acquired",):
            set_ops[f"items.$.{k}"] = max(0, int(v or 0))
        elif k in ("weight_kg", "value_usd", "x_cm", "y_cm", "z_cm"):
            set_ops[f"items.$.{k}"] = max(0, float(v or 0))
        elif k == "priority":
            p = (v or "normal").lower()
            set_ops[f"items.$.{k}"] = p if p in VALID_PRIORITIES else "normal"
        else:
            set_ops[f"items.$.{k}"] = v
    set_ops["items.$.updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one(
        {"id": ctx["shipment_id"], "items.id": item_id},
        {"$set": set_ops},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"updated": True}


@router.delete("/public/shipments/{token}/items/{item_id}")
async def public_delete_item(token: str, item_id: str, request: Request):
    ctx = await require_shipment_editor(request, token)
    r = await db.shipments.update_one(
        {"id": ctx["shipment_id"]}, {"$pull": {"items": {"id": item_id}}},
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True}


@router.post("/public/shipments/{token}/pallets")
async def public_add_pallet(token: str, data: dict, request: Request):
    ctx = await require_shipment_editor(request, token)
    pallet = _normalise_pallet(data)
    await db.shipments.update_one({"id": ctx["shipment_id"]}, {"$push": {"pallets": pallet}})
    return pallet


@router.put("/public/shipments/{token}/pallets/{pallet_id}")
async def public_update_pallet(token: str, pallet_id: str, data: dict, request: Request):
    ctx = await require_shipment_editor(request, token)
    allowed = {"label", "notes", "length_cm", "width_cm", "height_cm", "x_cm", "y_cm", "color"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k in ("length_cm", "width_cm", "height_cm"):
            set_ops[f"pallets.$.{k}"] = max(5, float(v or 0))
        elif k in ("x_cm", "y_cm"):
            set_ops[f"pallets.$.{k}"] = max(0, float(v or 0))
        else:
            set_ops[f"pallets.$.{k}"] = v
    if not set_ops:
        return {"updated": False}
    set_ops["pallets.$.updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one(
        {"id": ctx["shipment_id"], "pallets.id": pallet_id},
        {"$set": set_ops},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pallet not found")
    return {"updated": True}


@router.delete("/public/shipments/{token}/pallets/{pallet_id}")
async def public_delete_pallet(token: str, pallet_id: str, request: Request):
    ctx = await require_shipment_editor(request, token)
    await db.shipments.update_one(
        {"id": ctx["shipment_id"], "items.pallet_id": pallet_id},
        {"$set": {"items.$[el].pallet_id": None}},
        array_filters=[{"el.pallet_id": pallet_id}],
    )
    r = await db.shipments.update_one(
        {"id": ctx["shipment_id"]}, {"$pull": {"pallets": {"id": pallet_id}}},
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pallet not found")
    return {"deleted": True}


@router.post("/public/shipments/{token}/scan-item")
async def public_scan_item(
    token: str,
    request: Request,
    images: List[UploadFile] = File(default=[]),
    isbn: Optional[str] = None,
    upc: Optional[str] = None,
):
    """Identify a shipment item from up to 3 photos and/or a scanned barcode.

    Returns a candidate item dict (NOT yet persisted) — the volunteer reviews,
    edits, then POSTs to /items to actually add it to the shipment.
    """
    ctx = await require_shipment_editor(request, token)
    pin_hint = (ctx.get("pin_used") or "")[-4:] if ctx.get("pin_used") else ""

    # Sanity: at least one signal must be present
    if not images and not isbn and not upc:
        raise HTTPException(status_code=400, detail="Provide at least one image, ISBN, or UPC")

    # 1) Try external catalogues first — they're definitive when we have a barcode
    enriched: dict = {}
    if isbn:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6) as cli:
                r = await cli.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn.strip()}")
                if r.status_code == 200:
                    js = r.json()
                    if js.get("totalItems", 0) > 0:
                        v = js["items"][0]["volumeInfo"]
                        enriched = {
                            "name": v.get("title") or "",
                            "author": ", ".join(v.get("authors") or []),
                            "publisher": v.get("publisher") or "",
                            "category": (v.get("categories") or ["Books"])[0],
                            "isbn": isbn.strip(),
                            "photo_url": ((v.get("imageLinks") or {}).get("thumbnail") or "").replace("http://", "https://"),
                            "weight_kg": 0.3,    # typical paperback
                            "dims_cm": {"length": 20, "width": 13, "height": 2},
                            "value_usd": float(((js["items"][0].get("saleInfo") or {}).get("listPrice") or {}).get("amount") or 12.0),
                            "ai_identified": False,
                            "source": "google_books",
                        }
        except Exception as e:
            logger.warning(f"google books lookup failed: {e}")

    if upc and not enriched:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6) as cli:
                r = await cli.get(f"https://world.openfoodfacts.org/api/v2/product/{upc.strip()}.json")
                if r.status_code == 200:
                    js = r.json()
                    if js.get("status") == 1:
                        p = js.get("product") or {}
                        enriched = {
                            "name": p.get("product_name") or p.get("generic_name") or "",
                            "category": (p.get("categories", "").split(",") or ["Food"])[0].strip()[:60],
                            "upc": upc.strip(),
                            "photo_url": p.get("image_front_url") or "",
                            "weight_kg": 0.5,
                            "dims_cm": {"length": 10, "width": 10, "height": 20},
                            "value_usd": 4.0,
                            "ai_identified": False,
                            "source": "openfoodfacts",
                        }
        except Exception as e:
            logger.warning(f"openfoodfacts lookup failed: {e}")

    # 2) If still empty (no barcode hit), invoke AI vision with the photos
    image_urls: List[str] = []
    image_bytes_list: List[bytes] = []  # keep raw bytes for AI — avoids broken re-download from relative URLs in production
    if images:
        # Persist photos for audit + so the waybill can reference them later
        for img in images[:3]:
            data = await img.read()
            if not data or len(data) > 8_000_000:
                continue
            image_bytes_list.append(data)
            from routers.shipments import _persist_shipment_image  # type: ignore
            try:
                url = await _persist_shipment_image(ctx["shipment_id"], data, img.content_type or "image/jpeg")
                image_urls.append(url)
            except Exception:
                pass

    if not enriched and image_bytes_list:
        api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
        if api_key:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
                # Write the first photo straight to a temp file — no httpx
                # round-trip. The previous version re-fetched image_urls[0]
                # which silently failed when storage fell back to disk
                # (relative `/uploads/...` URL), giving the AI an empty file
                # and producing "Unknown" + low confidence on every scan.
                import tempfile
                fd, tmp = tempfile.mkstemp(suffix=".jpg")
                with _os.fdopen(fd, "wb") as fh:
                    fh.write(image_bytes_list[0])
                sys_msg = (
                    "You identify physical items from photos for a charity shipment inventory. "
                    "Items can be ANYTHING a humanitarian container carries — books, clothing, "
                    "shoes, food (canned/dry/baby formula), toys, medical supplies (gauze, "
                    "syringes, crutches, wheelchairs), electronics, household goods (kitchenware, "
                    "linens, soap, mosquito nets), furniture (chairs, tables, beds, mattresses), "
                    "tools and construction equipment (hammers, drills, wheelbarrows, cement bags, "
                    "rebar, PVC pipes, paint cans, solar panels), school/stationery supplies, "
                    "agricultural inputs (seeds, fertilizer, hand tools), sports equipment, "
                    "personal-care/toiletries, baby gear (strollers, car seats), and bicycles. "
                    "Read any barcodes, ISBNs, titles, or text on the item. "
                    "\n\nUSE YOUR KNOWLEDGE OF MAJOR ECOMMERCE LISTINGS: cross-reference what "
                    "Amazon, Walmart, eBay, Target, Home Depot, Lowe's, AbeBooks, MAC.bid, "
                    "Costco, IKEA, AliExpress, and Alibaba would list this exact item as. Pick "
                    "the description + dimensions + weight + retail price that matches the most "
                    "authoritative listing. If multiple variants exist (size/color), default to "
                    "the most common SKU. Use the MEDIAN current US retail price in USD as "
                    "value_usd; if not sold in the US, use the nearest comparable. "
                    "\n\nOutput STRICT JSON: "
                    "{\"name\": str, \"category\": str (one of: Books, Clothing, Food, Toys, "
                    "Medical, Electronics, Household, Furniture, Tools, Construction, School, "
                    "Agriculture, Sports, Toiletries, BabyGear, Bicycle, Other), "
                    "\"author\": str, \"publisher\": str, \"isbn\": str, \"upc\": str, "
                    "\"weight_kg\": float, \"dims_cm\": {\"length\": float, \"width\": float, \"height\": float}, "
                    "\"value_usd\": float, \"source\": str (the retailer or listing site you "
                    "primarily drew the data from, e.g. 'amazon', 'walmart', 'ebay', "
                    "'home_depot', 'abebooks', 'macbid', 'inferred'), "
                    "\"confidence\": \"high\"|\"medium\"|\"low\"}. "
                    "Empty string for unknown fields. Round-number conservative estimates for "
                    "dims/weight/value. For heavy/bulky items (furniture, construction, tools) "
                    "give realistic weights — a wheelbarrow is ~15kg, a chair ~5kg, a cement bag "
                    "~25kg. Confidence reflects how certain you are of the IDENTIFICATION, not "
                    "the dimensions."
                )
                # Primary: Gemini 3 Flash
                chat = LlmChat(
                    api_key=api_key,
                    session_id=f"shipment_scan_{uuid.uuid4().hex[:6]}",
                    system_message=sys_msg,
                ).with_model("gemini", "gemini-3-flash-preview")
                msg = UserMessage(
                    text="Identify this item. Read barcodes / ISBNs / titles. Return strict JSON.",
                    file_contents=[FileContentWithMimeType(file_path=tmp, mime_type="image/jpeg")],
                )
                raw = await chat.send_message(msg)
                s = (raw or "").strip()
                if s.startswith("```"):
                    s = s.strip("`")
                    if s.lower().startswith("json"):
                        s = s[4:].strip()
                first, last = s.find("{"), s.rfind("}")
                if first >= 0 and last > first:
                    s = s[first:last + 1]
                import json as _json
                parsed = _json.loads(s)
                confidence = (parsed.get("confidence") or "low").lower()
                # GPT-4o fallback if Gemini was low confidence
                if confidence == "low":
                    chat2 = LlmChat(
                        api_key=api_key,
                        session_id=f"shipment_scan_gpt_{uuid.uuid4().hex[:6]}",
                        system_message=sys_msg,
                    ).with_model("openai", "gpt-4o")
                    raw2 = await chat2.send_message(msg)
                    s2 = (raw2 or "").strip()
                    if s2.startswith("```"):
                        s2 = s2.strip("`")
                        if s2.lower().startswith("json"):
                            s2 = s2[4:].strip()
                    f2, l2 = s2.find("{"), s2.rfind("}")
                    if f2 >= 0 and l2 > f2:
                        parsed = _json.loads(s2[f2:l2 + 1])
                enriched = {
                    "name": parsed.get("name") or "",
                    "category": parsed.get("category") or "Other",
                    "author": parsed.get("author") or "",
                    "publisher": parsed.get("publisher") or "",
                    "isbn": parsed.get("isbn") or "",
                    "upc": parsed.get("upc") or "",
                    "weight_kg": float(parsed.get("weight_kg") or 0.5),
                    "dims_cm": parsed.get("dims_cm") or {"length": 20, "width": 13, "height": 5},
                    "value_usd": float(parsed.get("value_usd") or 5.0),
                    "ai_identified": True,
                    "ai_confidence": parsed.get("confidence") or "low",
                    "source": "ai_vision",
                }
                # If AI extracted an ISBN, try one more time to enrich via Google Books
                if parsed.get("isbn") and not enriched.get("publisher"):
                    try:
                        import httpx as _httpx
                        async with _httpx.AsyncClient(timeout=4) as cli:
                            gr = await cli.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{parsed['isbn']}")
                            if gr.status_code == 200 and gr.json().get("totalItems", 0) > 0:
                                v = gr.json()["items"][0]["volumeInfo"]
                                enriched["publisher"] = v.get("publisher") or enriched["publisher"]
                                enriched["author"] = ", ".join(v.get("authors") or []) or enriched["author"]
                    except Exception:
                        pass
                try:
                    _os.remove(tmp)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"AI scan failed: {e}")

    # 3) Final shape — always returns SOMETHING the client can show + edit
    if not enriched:
        enriched = {
            "name": "Unidentified item",
            "category": "Other",
            "ai_identified": False,
            "ai_confidence": "low",
            "source": "manual",
            "weight_kg": 0.5,
            "dims_cm": {"length": 20, "width": 20, "height": 10},
            "value_usd": 5.0,
        }
    enriched["image_urls"] = image_urls
    enriched["photo_url"] = enriched.get("photo_url") or (image_urls[0] if image_urls else "")
    enriched["scanned_by_pin_hint"] = pin_hint
    enriched["scanned_at"] = datetime.now(timezone.utc).isoformat()
    return enriched


@router.get("/public/shipments/{token}/waybill")
async def public_waybill_html(token: str, request: Request):
    """Public PIN-gated waybill. Editor token accepted either via the
    X-Shipment-Edit-Token header (XHR/fetch) or as ?edit_token=... in the URL
    (so `window.open()` can pop it in a new tab for printing)."""
    ctx = await require_shipment_editor(request, token)
    s = await db.shipments.find_one({"id": ctx["shipment_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return Response(content=_waybill_html(s), media_type="text/html")


