"""Stock moving between shops — one count down, the other up, with a paper trail.

Before this, the only way to "move" a product was CrossCampusMoveDialog, which
just re-homed the catalogue entry (`location_id`) and left the on-hand count
sitting with it. Shelves never reconciled (iter416).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, get_current_user, require_staff
from routers.product_scope import is_shared, stock_at, stock_field

router = APIRouter(prefix="/api", tags=["stock-transfers"])


class TransferCreate(BaseModel):
    product_id: str
    from_location_id: str
    to_location_id: str
    qty: float
    note: Optional[str] = ""


@router.get("/stock-transfers")
async def list_stock_transfers(location_id: Optional[str] = None, limit: int = 50,
                               current_user: dict = Depends(get_current_user)):
    """Transfers touching a store — sent or received.

    A transfer has no `location_id` of its own (it has two), so the usual campus
    filter never matched and the list came back empty for anyone pinned to a
    campus. Scope on the two ends instead; organisation isolation is handled by
    the db wrapper (iter416).
    """
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    query: dict = {}
    if store:
        query = {"$or": [{"from_location_id": store}, {"to_location_id": store}]}
    return await db.stock_transfers.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.post("/stock-transfers")
async def create_stock_transfer(data: TransferCreate, current_user: dict = Depends(require_staff)):
    qty = float(data.qty or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Say how many are going across")
    if data.from_location_id == data.to_location_id:
        raise HTTPException(status_code=400, detail="Pick a different store to send to")

    product = await db.products.find_one({"id": data.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.get("has_variants"):
        raise HTTPException(
            status_code=400,
            detail="This product has variants, which can't be shared between stores yet — "
                   "move it with the stock adjustment at each shop instead.",
        )

    locs = await db.locations.find({"id": {"$in": [data.from_location_id, data.to_location_id]}},
                                   {"_id": 0, "id": 1, "name": 1}).to_list(2)
    names = {loc["id"]: loc.get("name") or loc["id"] for loc in locs}
    for loc_id in (data.from_location_id, data.to_location_id):
        if loc_id not in names:
            raise HTTPException(status_code=400, detail="That store doesn't exist")

    on_hand = stock_at(product, data.from_location_id)
    if on_hand < qty:
        raise HTTPException(
            status_code=400,
            detail=f"{names[data.from_location_id]} only has {on_hand:g} of {product.get('name')} to send",
        )

    # A product only kept one count until now. Giving it a column per store (and
    # moving the existing count into its home store) is what lets both ends move.
    if not is_shared(product):
        store_ids = sorted({data.from_location_id, data.to_location_id,
                            *(product.get("store_ids") or []),
                            *([product["location_id"]] if product.get("location_id") else [])})
        per_store = dict(product.get("store_stock") or {})
        home = product.get("location_id") or data.from_location_id
        if not per_store:
            per_store[home] = int(product.get("stock") or 0)
        await db.products.update_one({"id": product["id"]},
                                     {"$set": {"store_ids": store_ids, "store_stock": per_store}})
        product = await db.products.find_one({"id": product["id"]}, {"_id": 0})
    elif not product.get("is_universal") and data.to_location_id not in (product.get("store_ids") or []):
        await db.products.update_one({"id": product["id"]},
                                     {"$addToSet": {"store_ids": data.to_location_id}})
        product = await db.products.find_one({"id": product["id"]}, {"_id": 0})

    from_field = stock_field(product, data.from_location_id)
    to_field = stock_field(product, data.to_location_id)
    # Conditional on the source still holding enough, so two tills sending the
    # last box at the same moment can't both win.
    res = await db.products.update_one(
        {"id": product["id"], from_field: {"$gte": qty}},
        {"$inc": {from_field: -qty, to_field: qty}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=409, detail="That stock just moved — check the count and try again")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"trf_{uuid.uuid4().hex[:10]}",
        "product_id": product["id"],
        "product_name": product.get("name"),
        "qty": qty,
        "unit": product.get("unit") or "",
        "from_location_id": data.from_location_id,
        "from_location_name": names[data.from_location_id],
        "to_location_id": data.to_location_id,
        "to_location_name": names[data.to_location_id],
        "note": (data.note or "").strip(),
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.stock_transfers.insert_one(dict(doc))

    fresh = await db.products.find_one({"id": product["id"]}, {"_id": 0})
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()), "user_id": current_user["id"], "action": "transfer",
        "entity_type": "product", "entity_id": product["id"], "timestamp": now,
        "details": {"qty": qty, "from": data.from_location_id, "to": data.to_location_id},
    })
    return {
        "message": f"{qty:g} {product.get('name')} sent from {doc['from_location_name']} "
                   f"to {doc['to_location_name']}",
        "transfer": doc,
        "from_stock": stock_at(fresh, data.from_location_id),
        "to_stock": stock_at(fresh, data.to_location_id),
    }
