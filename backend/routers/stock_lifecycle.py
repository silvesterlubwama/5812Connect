"""Losses and lifecycle: what died, spoiled or walked off — and what grew up.

Two jobs that share a shelf (iter417):

* **Losses.** Stock leaves without being sold. Each one is written down with a
  reason, a value and a printable slip. Only negligence touches money: it is
  booked against the employee so payroll can take it off their pay. A donation
  gets its own receipt so the shop can show where it went.
* **Batches.** Livestock does not sit still. A product can carry a growing-on
  rule — "Brooder Chicks become 4 Week Broilers after 28 days" — and each
  intake becomes a dated batch. A nightly cron matures the ones that are due,
  moving the count (and therefore the price) onto the grown product.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, get_current_user, require_staff, logger
from routers.product_scope import is_shared, stock_at, stock_field

router = APIRouter(prefix="/api", tags=["stock-lifecycle"])

# What the loss form offers. `money` means it is recoverable from someone.
LOSS_REASONS = {
    "spoiled": "Spoiled or damaged",
    "died": "Died",
    "stolen": "Stolen or missing",
    "used_by_farm": "Eaten or used by the farm",
    "negligence": "Employee negligence",
    "donated": "Donated",
    "other": "Other",
}


class LossCreate(BaseModel):
    product_id: str
    qty: float
    reason: str
    location_id: Optional[str] = None
    variant_id: Optional[str] = None
    note: Optional[str] = ""
    employee_id: Optional[str] = None      # required for negligence
    donated_to: Optional[str] = None       # required for donated
    batch_id: Optional[str] = None


class BatchCreate(BaseModel):
    product_id: str
    qty: float
    location_id: Optional[str] = None
    received_at: Optional[str] = None
    note: Optional[str] = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit_value(product: dict, store_id: str) -> float:
    prices = product.get("store_prices") or {}
    if store_id and prices.get(store_id) not in (None, ""):
        try:
            return float(prices[store_id])
        except (TypeError, ValueError):
            pass
    try:
        return float(product.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


async def _next_slip_number(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = await db.stock_losses.count_documents({"slip_number": {"$regex": f"^{prefix}-{stamp}"}})
    return f"{prefix}-{stamp}-{seq + 1:04d}"


async def _take_from_batches(product_id: str, store_id: str, qty: float, note: str) -> list:
    """Oldest batch first, so a loss comes off the birds that have been here longest."""
    taken, left = [], qty
    cursor = db.stock_batches.find(
        {"product_id": product_id, "status": "growing", "remaining": {"$gt": 0},
         **({"location_id": store_id} if store_id else {})},
        {"_id": 0},
    ).sort("received_at", 1)
    async for batch in cursor:
        if left <= 0:
            break
        use = min(float(batch.get("remaining") or 0), left)
        if use <= 0:
            continue
        left -= use
        await db.stock_batches.update_one(
            {"id": batch["id"]},
            {"$inc": {"remaining": -use, "lost": use},
             "$push": {"events": {"at": _now(), "qty": use, "what": note}}},
        )
        taken.append({"batch_id": batch["id"], "qty": use})
    return taken


# ============================== LOSSES ==============================

@router.get("/stock-losses")
async def list_stock_losses(location_id: Optional[str] = None, limit: int = 100,
                            reason: Optional[str] = None,
                            current_user: dict = Depends(get_current_user)):
    query: dict = {}
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store:
        query["location_id"] = store
    if reason:
        query["reason"] = reason
    return await db.stock_losses.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.post("/stock-losses")
async def record_stock_loss(data: LossCreate, current_user: dict = Depends(require_staff)):
    qty = float(data.qty or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Say how many were lost")
    if data.reason not in LOSS_REASONS:
        raise HTTPException(status_code=400, detail="Pick a reason for the loss")
    if data.reason == "negligence" and not data.employee_id:
        raise HTTPException(status_code=400, detail="Say whose negligence it was — it comes off their pay")
    if data.reason == "donated" and not (data.donated_to or "").strip():
        raise HTTPException(status_code=400, detail="Say who the donation went to")

    product = await db.products.find_one({"id": data.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    store_id = (data.location_id or current_user.get("active_campus_id")
                or current_user.get("location_id") or product.get("location_id") or "")
    if is_shared(product) and not store_id:
        raise HTTPException(status_code=400, detail="Say which store the stock was lost at")

    if data.variant_id:
        variant = next((v for v in (product.get("variants") or []) if v.get("id") == data.variant_id), None)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        before = float(variant.get("stock") or 0)
    else:
        before = float(stock_at(product, store_id))
    if before < qty:
        raise HTTPException(status_code=400, detail=f"Only {before:g} of {product.get('name')} on hand here")

    if data.variant_id:
        await db.products.update_one({"id": product["id"], "variants.id": data.variant_id},
                                     {"$inc": {"variants.$.stock": -qty}})
        fresh = await db.products.find_one({"id": product["id"]}, {"_id": 0})
        total = sum(float(v.get("stock") or 0) for v in (fresh.get("variants") or []))
        await db.products.update_one({"id": product["id"]}, {"$set": {"stock": total}})
    else:
        await db.products.update_one({"id": product["id"]},
                                     {"$inc": {stock_field(product, store_id): -qty}})

    batches = await _take_from_batches(product["id"], store_id, qty,
                                       f"{LOSS_REASONS[data.reason]} ({qty:g})")

    unit_value = _unit_value(product, store_id)
    value = round(unit_value * qty, 2)
    donation = data.reason == "donated"
    slip = await _next_slip_number("DON" if donation else "LOSS")

    employee = None
    if data.employee_id:
        employee = await db.users.find_one({"id": data.employee_id}, {"_id": 0, "id": 1, "name": 1})
        if not employee:
            raise HTTPException(status_code=404, detail="That staff member was not found")

    doc = {
        "id": f"loss_{uuid.uuid4().hex[:10]}",
        "slip_number": slip,
        "product_id": product["id"],
        "product_name": product.get("name"),
        "variant_id": data.variant_id,
        "qty": qty,
        "unit_value": unit_value,
        "value": value,
        "reason": data.reason,
        "reason_label": LOSS_REASONS[data.reason],
        "note": (data.note or "").strip()[:500],
        "location_id": store_id,
        "donated_to": (data.donated_to or "").strip() or None,
        "employee_id": data.employee_id or None,
        "employee_name": (employee or {}).get("name") if employee else None,
        # Only negligence moves money: it is owed back by the person responsible.
        "recoverable": data.reason == "negligence",
        "recovery_status": "pending" if data.reason == "negligence" else None,
        "batches": batches,
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.stock_losses.insert_one(dict(doc))
    await db.stock_movements.insert_one({
        "id": f"sm_{uuid.uuid4().hex[:10]}",
        "product_id": product["id"], "product_name": product.get("name"),
        "variant_id": data.variant_id, "delta": -qty,
        "before": before, "after": before - qty,
        "reason": "loss", "notes": f"{LOSS_REASONS[data.reason]}: {doc['note']}"[:500],
        "reference": slip, "location_id": store_id, "created_at": doc["created_at"],
        "created_by": current_user["id"], "created_by_name": current_user.get("name", ""),
    })

    message = f"{qty:g} {product.get('name')} written off — {LOSS_REASONS[data.reason].lower()}"
    if donation:
        message = f"{qty:g} {product.get('name')} donated to {doc['donated_to']}"
    elif doc["recoverable"]:
        message = (f"{qty:g} {product.get('name')} charged to {doc['employee_name']} "
                   f"— {value:,.0f} to come off their pay")
    return {"message": message, "loss": doc}


@router.patch("/stock-losses/{loss_id}/recovery")
async def update_loss_recovery(loss_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Mark what the shop got back: recovered (deducted), waived, or still pending."""
    status = (data.get("status") or "").strip()
    if status not in {"pending", "recovered", "waived"}:
        raise HTTPException(status_code=400, detail="Status must be pending, recovered or waived")
    loss = await db.stock_losses.find_one({"id": loss_id}, {"_id": 0})
    if not loss:
        raise HTTPException(status_code=404, detail="Loss not found")
    if not loss.get("recoverable"):
        raise HTTPException(status_code=400, detail="Only a negligence loss comes off someone's pay")
    await db.stock_losses.update_one({"id": loss_id}, {"$set": {
        "recovery_status": status,
        "recovery_note": (data.get("note") or "").strip()[:300],
        "recovery_updated_at": _now(),
        "recovery_updated_by": current_user.get("name", ""),
    }})
    return {"message": f"Marked {status}", "id": loss_id, "status": status}


@router.get("/stock-losses/pending-deductions")
async def pending_deductions(staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """What payroll still has to take off, per person."""
    query: dict = {"recoverable": True, "recovery_status": "pending"}
    if staff_id:
        query["employee_id"] = staff_id
    rows = await db.stock_losses.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_staff: dict = {}
    for row in rows:
        entry = by_staff.setdefault(row.get("employee_id"), {
            "employee_id": row.get("employee_id"),
            "employee_name": row.get("employee_name"),
            "total": 0.0, "items": [],
        })
        entry["total"] = round(entry["total"] + float(row.get("value") or 0), 2)
        entry["items"].append({"id": row["id"], "slip_number": row.get("slip_number"),
                               "product_name": row.get("product_name"), "qty": row.get("qty"),
                               "value": row.get("value"), "created_at": row.get("created_at")})
    return {"staff": sorted(by_staff.values(), key=lambda s: -s["total"]),
            "total": round(sum(s["total"] for s in by_staff.values()), 2)}


@router.get("/stock-losses/report")
async def loss_report(start: Optional[str] = None, end: Optional[str] = None,
                      location_id: Optional[str] = None,
                      current_user: dict = Depends(get_current_user)):
    """What the shop is losing, by reason and by product."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (start or today)[:10]
    end = (end or today)[:10]
    query: dict = {"created_at": {"$gte": f"{start}T00:00:00", "$lte": f"{end}T23:59:59.999999"}}
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store:
        query["location_id"] = store

    by_reason: dict = {}
    by_product: dict = {}
    total_value = 0.0
    total_qty = 0.0
    recoverable = 0.0
    donated = 0.0
    rows = await db.stock_losses.find(query, {"_id": 0}).to_list(5000)
    for row in rows:
        qty = float(row.get("qty") or 0)
        value = float(row.get("value") or 0)
        total_qty += qty
        total_value += value
        if row.get("recoverable") and row.get("recovery_status") == "pending":
            recoverable += value
        if row.get("reason") == "donated":
            donated += value
        r = by_reason.setdefault(row.get("reason"), {
            "reason": row.get("reason"), "label": row.get("reason_label") or row.get("reason"),
            "count": 0, "qty": 0.0, "value": 0.0})
        r["count"] += 1
        r["qty"] = round(r["qty"] + qty, 2)
        r["value"] = round(r["value"] + value, 2)
        key = row.get("product_id") or row.get("product_name")
        p = by_product.setdefault(key, {"product_id": row.get("product_id"),
                                        "name": row.get("product_name") or "Item",
                                        "qty": 0.0, "value": 0.0, "count": 0, "reasons": {}})
        p["qty"] = round(p["qty"] + qty, 2)
        p["value"] = round(p["value"] + value, 2)
        p["count"] += 1
        label = row.get("reason_label") or row.get("reason")
        p["reasons"][label] = round(p["reasons"].get(label, 0) + qty, 2)

    products = sorted(by_product.values(), key=lambda r: -r["value"])
    store_name = ""
    if store:
        loc = await db.locations.find_one({"id": store}, {"_id": 0, "name": 1})
        store_name = (loc or {}).get("name", "")
    return {
        "start": start, "end": end, "location_id": store, "store_name": store_name,
        "losses_count": len(rows),
        "items_lost": round(total_qty, 2),
        "value_lost": round(total_value, 2),
        "to_recover": round(recoverable, 2),
        "donated_value": round(donated, 2),
        "by_reason": sorted(by_reason.values(), key=lambda r: -r["value"]),
        "by_product": products,
        "worst": products[0] if products else None,
    }


# ============================== BATCHES ==============================

def _grow_rule(product: dict) -> Optional[dict]:
    target = product.get("grows_into_product_id")
    days = product.get("grow_after_days")
    if not target or not days:
        return None
    try:
        days = int(days)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return {"to": target, "days": days, "ratio": float(product.get("grow_ratio") or 1)}


@router.get("/stock-batches")
async def list_batches(location_id: Optional[str] = None, product_id: Optional[str] = None,
                       status: str = "growing", limit: int = 200,
                       current_user: dict = Depends(get_current_user)):
    query: dict = {}
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store:
        query["location_id"] = store
    if product_id:
        query["product_id"] = product_id
    if status and status != "all":
        query["status"] = status
    rows = await db.stock_batches.find(query, {"_id": 0}).sort("matures_at", 1).limit(limit).to_list(limit)
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            due = datetime.fromisoformat(str(row.get("matures_at")).replace("Z", "+00:00"))
            # Round UP: a batch booked in today with 28 days to run has 28 days
            # to go, not 27 (iter418 fix).
            secs = (due - now).total_seconds()
            row["days_to_go"] = max(0, -(-secs // 86400)) if secs > 0 else 0
            row["days_to_go"] = int(row["days_to_go"])
            row["due"] = due <= now
        except (TypeError, ValueError):
            row["days_to_go"] = None
            row["due"] = False
    return rows


@router.post("/stock-batches")
async def create_batch(data: BatchCreate, current_user: dict = Depends(require_staff)):
    """Record an intake so it can grow on. Does NOT move stock — the stock is
    already there; this only starts the clock on it."""
    qty = float(data.qty or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Say how many came in")
    product = await db.products.find_one({"id": data.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    rule = _grow_rule(product)
    if not rule:
        raise HTTPException(
            status_code=400,
            detail=f"{product.get('name')} has no growing-on rule — set what it becomes, and after how long, on the product first",
        )
    store_id = (data.location_id or current_user.get("active_campus_id")
                or current_user.get("location_id") or product.get("location_id") or "")
    received = (data.received_at or _now())[:19]
    try:
        received_dt = datetime.fromisoformat(received)
    except ValueError:
        received_dt = datetime.now(timezone.utc)
    if received_dt.tzinfo is None:
        received_dt = received_dt.replace(tzinfo=timezone.utc)
    target = await db.products.find_one({"id": rule["to"]}, {"_id": 0, "id": 1, "name": 1})

    batch = {
        "id": f"batch_{uuid.uuid4().hex[:10]}",
        "product_id": product["id"],
        "product_name": product.get("name"),
        "location_id": store_id,
        "qty": qty,
        "remaining": qty,
        "lost": 0.0,
        "status": "growing",
        "received_at": received_dt.isoformat(),
        "matures_at": (received_dt + timedelta(days=rule["days"])).isoformat(),
        "becomes_product_id": rule["to"],
        "becomes_product_name": (target or {}).get("name"),
        "grow_after_days": rule["days"],
        "note": (data.note or "").strip()[:300],
        "events": [],
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.stock_batches.insert_one(dict(batch))
    return {"message": f"{qty:g} {product.get('name')} will become {batch['becomes_product_name']} "
                       f"on {batch['matures_at'][:10]}",
            "batch": batch}


async def mature_batch(batch: dict, actor: Optional[dict] = None, qty_override: Optional[float] = None) -> dict:
    """Move a batch onto the grown product. The count, and therefore the price,
    changes. Anything that died on the way is recorded against the batch, never
    silently dropped."""
    qty = float(qty_override if qty_override is not None else (batch.get("remaining") or 0))
    source = await db.products.find_one({"id": batch["product_id"]}, {"_id": 0})
    target = await db.products.find_one({"id": batch.get("becomes_product_id")}, {"_id": 0})
    if not source or not target:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "blocked", "blocked_reason": "The product it should become no longer exists"}})
        return {"ok": False, "reason": "missing_product", "batch_id": batch["id"]}
    if qty <= 0:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {"status": "matured",
                                                                        "matured_at": _now()}})
        return {"ok": True, "qty": 0, "batch_id": batch["id"]}

    store_id = batch.get("location_id") or ""
    on_hand = float(stock_at(source, store_id))
    moved = min(qty, on_hand)
    if moved <= 0:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "blocked",
            "blocked_reason": f"No {source.get('name')} left at this store to grow on"}})
        return {"ok": False, "reason": "no_stock", "batch_id": batch["id"]}

    await db.products.update_one({"id": source["id"]}, {"$inc": {stock_field(source, store_id): -moved}})
    await db.products.update_one({"id": target["id"]}, {"$inc": {stock_field(target, store_id): moved}})

    now = _now()
    record = {
        "id": f"grow_{uuid.uuid4().hex[:10]}",
        "batch_id": batch["id"],
        "from_product_id": source["id"], "from_product_name": source.get("name"),
        "to_product_id": target["id"], "to_product_name": target.get("name"),
        "qty": moved,
        "location_id": store_id,
        "from_value": round(_unit_value(source, store_id) * moved, 2),
        "to_value": round(_unit_value(target, store_id) * moved, 2),
        "lost_on_the_way": float(batch.get("lost") or 0),
        "needs_loss_check": True,
        "created_at": now,
        "created_by": (actor or {}).get("id", "cron"),
        "created_by_name": (actor or {}).get("name", "Automatic"),
    }
    await db.stock_transformations.insert_one(dict(record))
    for product, delta in ((source, -moved), (target, moved)):
        await db.stock_movements.insert_one({
            "id": f"sm_{uuid.uuid4().hex[:10]}",
            "product_id": product["id"], "product_name": product.get("name"),
            "delta": delta, "reason": "adjustment",
            "notes": f"Grew on: {source.get('name')} → {target.get('name')}",
            "reference": batch["id"], "location_id": store_id, "created_at": now,
            "created_by": record["created_by"], "created_by_name": record["created_by_name"],
        })
    await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
        "status": "matured", "matured_at": now, "matured_qty": moved,
        "transformation_id": record["id"]}})

    # The grown product may itself grow on — start its clock.
    next_rule = _grow_rule(target)
    if next_rule:
        nxt = await db.products.find_one({"id": next_rule["to"]}, {"_id": 0, "id": 1, "name": 1})
        await db.stock_batches.insert_one({
            "id": f"batch_{uuid.uuid4().hex[:10]}",
            "product_id": target["id"], "product_name": target.get("name"),
            "location_id": store_id, "qty": moved, "remaining": moved, "lost": 0.0,
            "status": "growing", "received_at": now,
            "matures_at": (datetime.now(timezone.utc) + timedelta(days=next_rule["days"])).isoformat(),
            "becomes_product_id": next_rule["to"], "becomes_product_name": (nxt or {}).get("name"),
            "grow_after_days": next_rule["days"], "note": f"Grew on from {source.get('name')}",
            "events": [], "created_at": now, "created_by": record["created_by"],
            "created_by_name": record["created_by_name"],
        })
    return {"ok": True, "qty": moved, "batch_id": batch["id"], "transformation": record["id"]}


@router.post("/stock-batches/{batch_id}/mature")
async def mature_batch_now(batch_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Move a batch on early (or confirm one by hand)."""
    batch = await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.get("status") != "growing":
        raise HTTPException(status_code=400, detail=f"This batch is already {batch.get('status')}")
    lost = float((data or {}).get("lost") or 0)
    if lost > 0:
        remaining = float(batch.get("remaining") or 0)
        if lost > remaining:
            raise HTTPException(status_code=400, detail=f"Only {remaining:g} in this batch")
        # Birds that died must leave stock too, not just the batch — otherwise
        # the shelf keeps counting phantom chicks (iter417).
        await record_stock_loss(LossCreate(
            product_id=batch["product_id"], qty=lost, reason="died",
            location_id=batch.get("location_id"), batch_id=batch_id,
            note="Died before growing on",
        ), current_user)
        batch = await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})
    res = await mature_batch(batch, current_user)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail={
            "missing_product": "The product it should become no longer exists",
            "no_stock": "There is none of it left at this store to grow on",
        }.get(res.get("reason"), "Could not grow this batch on"))
    return {"message": f"{res['qty']:g} {batch.get('product_name')} became "
                       f"{batch.get('becomes_product_name')}", **res}


@router.get("/stock-transformations")
async def list_transformations(location_id: Optional[str] = None, limit: int = 50,
                               current_user: dict = Depends(get_current_user)):
    query: dict = {}
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store:
        query["location_id"] = store
    return await db.stock_transformations.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.patch("/stock-transformations/{grow_id}/acknowledge")
async def acknowledge_transformation(grow_id: str, current_user: dict = Depends(require_staff)):
    """The farm has looked at it and recorded any deaths — stop nagging."""
    res = await db.stock_transformations.update_one({"id": grow_id}, {"$set": {
        "needs_loss_check": False, "acknowledged_at": _now(),
        "acknowledged_by": current_user.get("name", "")}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Noted", "id": grow_id}


async def run_due_maturations() -> dict:
    """Everything whose day has come. Safe to run twice — a matured batch is
    never matured again."""
    now = _now()
    done, failed = [], []
    cursor = db.stock_batches.find({"status": "growing", "matures_at": {"$lte": now}}, {"_id": 0})
    async for batch in cursor:
        try:
            res = await mature_batch(batch)
            (done if res.get("ok") else failed).append(res)
        except Exception as ex:      # one bad batch must not stop the rest
            logger.error(f"[grow] batch {batch.get('id')} failed: {ex}")
            failed.append({"batch_id": batch.get("id"), "error": str(ex)})
    return {"matured": len(done), "failed": len(failed), "details": done + failed}
