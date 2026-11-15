"""Restaurant service: tabs on tables, tickets to the cooks, dishes tracked.

A store is a restaurant when Store Settings says so; an item goes to the kitchen
when the product says so. Both are honoured, so a shop that sells one hot item
can still send that one item to a cook (iter418).

An order is the kitchen's copy of the work. A TAB is an order that has not been
paid yet — the basket parked under a table until the customer is ready. A
pay-first store creates the sale and then the order; a tab store creates the
order and settles it later. Either way the kitchen sees the same ticket.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, get_current_user, require_staff

router = APIRouter(prefix="/api", tags=["kitchen"])

# A dish moves: in the queue → on the stove → ready to carry → on the table.
STAGES = ["new", "cooking", "ready", "served"]
STAGE_LABELS = {"new": "New", "cooking": "Cooking", "ready": "Ready", "served": "Served"}


class TicketItem(BaseModel):
    product_id: Optional[str] = None
    name: str
    qty: float = 1
    price: Optional[float] = 0
    notes: Optional[str] = ""          # "no onions, well done"
    station: Optional[str] = None      # Kitchen, Bar, Grill…
    model_config = {"extra": "allow"}


class OrderCreate(BaseModel):
    items: List[TicketItem]
    location_id: Optional[str] = None
    table_label: Optional[str] = None
    order_type: str = "dine_in"        # dine_in | takeaway
    customer_name: Optional[str] = None
    sale_id: Optional[str] = None      # set when the money was taken first
    note: Optional[str] = ""
    model_config = {"extra": "allow"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_stage(stage: str) -> str:
    idx = STAGES.index(stage) if stage in STAGES else 0
    return STAGES[min(idx + 1, len(STAGES) - 1)]


def _roll_up(items: list) -> str:
    """The order is only as far along as its slowest dish."""
    stages = [it.get("status") or "new" for it in items if not it.get("cancelled")]
    if not stages:
        return "served"
    return min(stages, key=lambda s: STAGES.index(s) if s in STAGES else 0)


def _ticket_line(item: dict, seq: int) -> dict:
    return {
        "line_id": f"ln_{uuid.uuid4().hex[:8]}",
        "seq": seq,
        "product_id": item.get("product_id"),
        "name": item.get("name") or "Item",
        "qty": float(item.get("qty") or 1),
        "price": float(item.get("price") or 0),
        "notes": (item.get("notes") or "").strip()[:200],
        "station": (item.get("station") or "").strip() or None,
        "status": "new",
        "status_at": {"new": _now()},
    }


async def _store_id(current_user: dict, given: Optional[str]) -> str:
    return (given or current_user.get("active_campus_id")
            or current_user.get("location_id") or "")


@router.get("/kitchen/orders")
async def list_orders(location_id: Optional[str] = None, scope: str = "open",
                      limit: int = 100, current_user: dict = Depends(get_current_user)):
    """The kitchen screen. `scope=open` hides anything finished and paid."""
    query: dict = {}
    store = await _store_id(current_user, location_id)
    if store:
        query["location_id"] = store
    if scope == "open":
        query["cancelled"] = {"$ne": True}
        query["status"] = {"$ne": "served"}
    elif scope == "tabs":
        query["cancelled"] = {"$ne": True}
        query["paid"] = {"$ne": True}
    rows = await db.kitchen_orders.find(query, {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)
    for row in rows:
        row["total"] = round(sum(float(i.get("price") or 0) * float(i.get("qty") or 0)
                                 for i in (row.get("items") or []) if not i.get("cancelled")), 2)
    return rows


@router.post("/kitchen/orders")
async def create_order(data: OrderCreate, current_user: dict = Depends(require_staff)):
    if not data.items:
        raise HTTPException(status_code=400, detail="Put something on the ticket first")
    store = await _store_id(current_user, data.location_id)
    items = [_ticket_line(i.model_dump(), n + 1) for n, i in enumerate(data.items)]
    seq = await db.kitchen_orders.count_documents({"location_id": store}) + 1
    order = {
        "id": f"ord_{uuid.uuid4().hex[:10]}",
        "ticket_number": f"K{datetime.now(timezone.utc).strftime('%d%m')}-{seq:03d}",
        "location_id": store,
        "table_label": (data.table_label or "").strip() or None,
        "order_type": data.order_type if data.order_type in {"dine_in", "takeaway"} else "dine_in",
        "customer_name": (data.customer_name or "").strip() or None,
        "items": items,
        "status": "new",
        "note": (data.note or "").strip()[:300],
        "sale_id": data.sale_id,
        "paid": bool(data.sale_id),
        "cancelled": False,
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
        "server_name": current_user.get("name", ""),
    }
    await db.kitchen_orders.insert_one(dict(order))
    order["total"] = round(sum(i["price"] * i["qty"] for i in items), 2)
    where = f"table {order['table_label']}" if order["table_label"] else "takeaway"
    return {"message": f"Ticket {order['ticket_number']} sent to the kitchen — {where}",
            "order": order}


@router.post("/kitchen/orders/{order_id}/items")
async def add_items(order_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """A second round on the same tab."""
    order = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if order.get("paid") or order.get("cancelled"):
        raise HTTPException(status_code=400, detail="This tab is already closed")
    raw = data.get("items") or []
    if not raw:
        raise HTTPException(status_code=400, detail="Nothing to add")
    start = len(order.get("items") or [])
    new_items = [_ticket_line(i, start + n + 1) for n, i in enumerate(raw)]
    await db.kitchen_orders.update_one({"id": order_id}, {
        "$push": {"items": {"$each": new_items}},
        "$set": {"status": "new", "updated_at": _now()},
    })
    fresh = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    return {"message": f"{len(new_items)} more sent to the kitchen", "order": fresh,
            "added": new_items}


@router.patch("/kitchen/orders/{order_id}/status")
async def set_order_status(order_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Move the whole ticket on — or straight to a named stage."""
    order = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ticket not found")
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
        "items": items, "status": status, "updated_at": now,
        f"status_at.{status}": now,
    }})
    return {"message": f"Ticket {order.get('ticket_number')} — {STAGE_LABELS[status]}",
            "id": order_id, "status": status}


@router.patch("/kitchen/orders/{order_id}/items/{line_id}/status")
async def set_item_status(order_id: str, line_id: str, data: dict,
                          current_user: dict = Depends(require_staff)):
    """One dish at a time — the chips are up before the chicken."""
    order = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ticket not found")
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
    return {"message": f"{item.get('name')} — {STAGE_LABELS[status]}",
            "id": order_id, "line_id": line_id, "status": status, "order_status": rolled}


@router.patch("/kitchen/orders/{order_id}/settle")
async def settle_order(order_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """The tab has been paid — tie it to the sale that took the money."""
    sale_id = (data or {}).get("sale_id")
    if not sale_id:
        raise HTTPException(status_code=400, detail="Which sale paid it?")
    res = await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "paid": True, "sale_id": sale_id, "settled_at": _now(),
        "settled_by": current_user.get("name", "")}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"message": "Tab settled", "id": order_id, "sale_id": sale_id}


@router.delete("/kitchen/orders/{order_id}")
async def cancel_order(order_id: str, current_user: dict = Depends(require_staff)):
    order = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if order.get("paid"):
        raise HTTPException(status_code=400, detail="This one was paid for — refund it on the receipt instead")
    await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "cancelled": True, "cancelled_at": _now(), "cancelled_by": current_user.get("name", "")}})
    return {"message": f"Ticket {order.get('ticket_number')} cancelled", "id": order_id}
