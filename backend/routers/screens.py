"""Screens on the wall: the kitchen's ticket board and the customer's display.

A screen is a device, not a person. A cook should not have to find a password
to see what to cook, and a customer-facing display has no business holding a
staff session at all. So a manager at the store pairs the device once; the
link it gets back IS the credential, and it only ever shows that store's
kitchen or that till's running total (iter420).

The pairing link is created by someone signed in to that store, can be
revoked, and gives no access to anything else in the app.
"""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, require_manager, require_staff
from routers.kitchen import STAGES, STAGE_LABELS, _roll_up, _next_stage
from store_access import is_store_member

router = APIRouter(prefix="/api", tags=["screens"])

KINDS = {"kitchen": "Kitchen screen", "sales": "Customer display"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScreenCreate(BaseModel):
    kind: str
    location_id: str
    name: Optional[str] = ""
    till_id: Optional[str] = "main"


class LiveSale(BaseModel):
    location_id: str
    till_id: Optional[str] = "main"
    lines: list = []
    subtotal: float = 0
    discount: float = 0
    total: float = 0
    currency: Optional[str] = "UGX"
    state: str = "selling"              # selling | paid | idle
    customer_name: Optional[str] = ""
    change_due: Optional[float] = None
    receipt_number: Optional[str] = ""
    store_name: Optional[str] = ""
    cashier: Optional[str] = ""
    model_config = {"extra": "allow"}


def _key(location_id: str, till_id: Optional[str]) -> str:
    return f"{location_id}|{(till_id or 'main').strip() or 'main'}"


async def _screen(token: str) -> dict:
    row = await db.device_screens.find_one({"token": token, "revoked": {"$ne": True}}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="This screen link is not valid any more — ask for a new one")
    await db.device_screens.update_one({"token": token}, {"$set": {"last_seen_at": _now()}})
    return row


# ============================ PAIRING (staff) ============================

@router.get("/screens")
async def list_screens(location_id: Optional[str] = None,
                       current_user: dict = Depends(require_staff)):
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store and not await is_store_member(current_user, store):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    query = {"revoked": {"$ne": True}}
    if store:
        query["location_id"] = store
    return await db.device_screens.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/screens")
async def pair_screen(data: ScreenCreate, current_user: dict = Depends(require_manager)):
    if data.kind not in KINDS:
        raise HTTPException(status_code=400, detail="A screen is either a kitchen screen or a customer display")
    if not data.location_id:
        raise HTTPException(status_code=400, detail="Which store is this screen in?")
    if not await is_store_member(current_user, data.location_id):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    doc = {
        "id": f"scr_{uuid.uuid4().hex[:10]}",
        "token": secrets.token_urlsafe(12),
        "kind": data.kind,
        "location_id": data.location_id,
        "till_id": (data.till_id or "main").strip() or "main",
        "name": (data.name or "").strip()[:80] or KINDS[data.kind],
        "revoked": False,
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.device_screens.insert_one(dict(doc))
    return {"message": f"{doc['name']} paired — open the link on that screen once and leave it there",
            "screen": doc}


@router.delete("/screens/{screen_id}")
async def revoke_screen(screen_id: str, current_user: dict = Depends(require_manager)):
    row = await db.device_screens.find_one({"id": screen_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Screen not found")
    if not await is_store_member(current_user, row.get("location_id") or ""):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    await db.device_screens.update_one({"id": screen_id}, {"$set": {
        "revoked": True, "revoked_at": _now(), "revoked_by": current_user.get("name", "")}})
    return {"message": f"{row.get('name')} unpaired — that link no longer opens", "id": screen_id}


# ======================= THE TILL PUSHES (staff) =======================

@router.post("/screens/live-sale")
async def push_live_sale(data: LiveSale, current_user: dict = Depends(require_staff)):
    """What the customer is watching: the basket as it is being rung up."""
    if not data.location_id:
        raise HTTPException(status_code=400, detail="Which till is this?")
    doc = data.model_dump()
    doc["key"] = _key(data.location_id, data.till_id)
    doc["updated_at"] = _now()
    await db.live_sales.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    return {"ok": True, "key": doc["key"]}


# ====================== THE SCREEN READS (no login) ======================

@router.get("/screens/{token}")
async def screen_info(token: str):
    row = await _screen(token)
    loc = await db.locations.find_one({"id": row.get("location_id")}, {"_id": 0, "name": 1})
    settings = await db.store_settings.find_one({"location_id": row.get("location_id")},
                                                {"_id": 0, "store_name": 1, "currency": 1})
    return {
        "kind": row["kind"], "name": row.get("name"), "till_id": row.get("till_id"),
        "location_id": row.get("location_id"),
        "store_name": (settings or {}).get("store_name") or (loc or {}).get("name") or "",
        "currency": (settings or {}).get("currency") or "UGX",
    }


@router.get("/screens/{token}/orders")
async def screen_orders(token: str, limit: int = 60):
    """The kitchen board. Read-only to anyone without the link."""
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen is a customer display, not a kitchen screen")
    orders = await db.kitchen_orders.find(
        {"location_id": row["location_id"], "cancelled": {"$ne": True}, "status": {"$ne": "served"}},
        {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)
    for order in orders:
        order["total"] = round(sum(float(i.get("price") or 0) * float(i.get("qty") or 0)
                                   for i in (order.get("items") or []) if not i.get("cancelled")), 2)
    return orders


@router.patch("/screens/{token}/orders/{order_id}/items/{line_id}")
async def screen_advance_item(token: str, order_id: str, line_id: str, data: dict = None):
    """A cook taps a dish as it comes up. The link is the kitchen's credential."""
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen cannot change tickets")
    order = await db.kitchen_orders.find_one({"id": order_id, "location_id": row["location_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="That ticket is not on this screen")
    items = order.get("items") or []
    item = next((i for i in items if i.get("line_id") == line_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="That dish is not on this ticket")
    status = (data or {}).get("status") or _next_stage(item.get("status") or "new")
    if status not in STAGES:
        raise HTTPException(status_code=400, detail="Unknown stage")
    now = _now()
    item["status"] = status
    item.setdefault("status_at", {})[status] = now
    rolled = _roll_up(items)
    await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "items": items, "status": rolled, "updated_at": now}})
    return {"message": f"{item.get('name')} — {STAGE_LABELS[status]}", "status": status,
            "order_status": rolled}


@router.patch("/screens/{token}/orders/{order_id}")
async def screen_advance_order(token: str, order_id: str, data: dict = None):
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen cannot change tickets")
    order = await db.kitchen_orders.find_one({"id": order_id, "location_id": row["location_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="That ticket is not on this screen")
    status = (data or {}).get("status") or _next_stage(order.get("status") or "new")
    if status not in STAGES:
        raise HTTPException(status_code=400, detail="Unknown stage")
    now = _now()
    items = order.get("items") or []
    for item in items:
        if item.get("cancelled"):
            continue
        item["status"] = status
        item.setdefault("status_at", {})[status] = now
    await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "items": items, "status": status, "updated_at": now, f"status_at.{status}": now}})
    return {"message": f"Ticket {order.get('ticket_number')} — {STAGE_LABELS[status]}", "status": status}


@router.get("/screens/{token}/sale")
async def screen_sale(token: str):
    """The customer display: what has been scanned and what it comes to."""
    row = await _screen(token)
    if row["kind"] != "sales":
        raise HTTPException(status_code=400, detail="This screen is a kitchen screen, not a customer display")
    live = await db.live_sales.find_one({"key": _key(row["location_id"], row.get("till_id"))}, {"_id": 0})
    if not live:
        return {"state": "idle", "lines": [], "total": 0, "currency": "UGX"}
    return live
