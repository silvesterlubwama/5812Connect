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
from store_access import is_store_member

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
    variant_id: Optional[str] = None   # which stage of a produce item came in
    add_stock: bool = False            # produce intake books the stock in too
    location_id: Optional[str] = None
    received_at: Optional[str] = None
    note: Optional[str] = ""
    supplier: Optional[str] = ""        # which hatchery this run came from


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit_value(product: dict, store_id: str, variant: dict = None) -> float:
    """What one unit was worth. A variant's own price wins: a 4-week broiler and
    a day-old chick are not the same loss (iter424)."""
    if variant and variant.get("price") not in (None, ""):
        try:
            return float(variant["price"])
        except (TypeError, ValueError):
            pass
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


async def _take_from_batch(batch_id: str, qty: float, note: str) -> list:
    """Take the loss off the batch the user named. Guessing which batch lost a
    bird is how a weak hatchery run ends up looking clean (iter424)."""
    batch = await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="That batch no longer exists")
    if float(batch.get("remaining") or 0) < qty:
        raise HTTPException(status_code=400,
                            detail=f"That batch only has {float(batch.get('remaining') or 0):g} left")
    await db.stock_batches.update_one(
        {"id": batch_id},
        {"$inc": {"remaining": -qty, "lost": qty},
         "$push": {"events": {"at": _now(), "qty": qty, "what": note}}})
    return [{"batch_id": batch_id, "qty": qty,
             "received_at": batch.get("received_at"), "supplier": batch.get("supplier")}]


async def open_batches_for(product_id: str, store_id: str, variant_id: str = None) -> list:
    """Batches still carrying stock, for the shop to choose from."""
    query: dict = {"product_id": product_id, "status": "growing", "remaining": {"$gt": 0}}
    if store_id:
        query["location_id"] = store_id
    if variant_id:
        query["variant_id"] = variant_id
    return await db.stock_batches.find(query, {"_id": 0}).sort("received_at", 1).to_list(100)


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

    # An item kept as variants has no single pile of stock to take from, so the
    # shop has to say which one was lost (iter424).
    variant = None
    if product.get("variants"):
        if not data.variant_id:
            raise HTTPException(status_code=400,
                                detail=f"Which {product.get('name')} was lost? Pick the variant")
        variant = next((v for v in product["variants"] if v.get("id") == data.variant_id), None)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")
        before = float(variant.get("stock") or 0)
    elif data.variant_id:
        raise HTTPException(status_code=400, detail="This item is not kept as variants")
    else:
        before = float(stock_at(product, store_id))
    if before < qty:
        what = f"{product.get('name')} — {variant['name']}" if variant else product.get("name")
        raise HTTPException(status_code=400, detail=f"Only {before:g} of {what} on hand here")

    note = f"{LOSS_REASONS[data.reason]} ({qty:g})"
    open_batches = await open_batches_for(product["id"], store_id, data.variant_id)
    if open_batches and not data.batch_id:
        raise HTTPException(
            status_code=400,
            detail="Say which batch the loss came from — otherwise a weak run looks clean")
    if data.batch_id:
        batches = await _take_from_batch(data.batch_id, qty, note)
    else:
        batches = []

    if data.variant_id:
        await db.products.update_one({"id": product["id"], "variants.id": data.variant_id},
                                     {"$inc": {"variants.$.stock": -qty}})
        fresh = await db.products.find_one({"id": product["id"]}, {"_id": 0})
        total = sum(float(v.get("stock") or 0) for v in (fresh.get("variants") or []))
        await db.products.update_one({"id": product["id"]}, {"$set": {"stock": total}})
    else:
        await db.products.update_one({"id": product["id"]},
                                     {"$inc": {stock_field(product, store_id): -qty}})

    unit_value = _unit_value(product, store_id, variant)
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


async def pending_loss_lines(staff_id: str, available: float, exclude: Optional[set] = None) -> tuple:
    """Negligence charges still owed by one person, as payslip deduction lines.

    Returns `(lines, applications)`. Nothing is written — the caller marks them
    only when a real payslip is saved, so a preview never swallows a charge.
    A charge bigger than what is left of the pay is taken in instalments rather
    than pushing someone's net pay below zero (iter419).
    """
    rows = await db.stock_losses.find(
        {"employee_id": staff_id, "recoverable": True, "recovery_status": "pending"},
        {"_id": 0}).sort("created_at", 1).to_list(200)
    lines, applications = [], []
    left = max(0.0, float(available))
    for row in rows:
        # A dry run over several salary rows for the same person must not show
        # the same charge twice (iter419).
        if exclude and row["id"] in exclude:
            continue
        owed = round(float(row.get("value") or 0) - float(row.get("recovered_amount") or 0), 2)
        if owed <= 0:
            continue
        if left <= 0:
            break
        take = round(min(owed, left), 2)
        left = round(left - take, 2)
        part = take < owed
        # The staff member's own copy has to say what this money is for, in
        # words, or a deduction looks like the shop helping itself (iter420).
        note = (f"{float(row.get('qty') or 0):g} × {row.get('product_name')} written off on "
                f"{str(row.get('created_at'))[:10]} — {str(row.get('reason_label') or 'loss').lower()}"
                f", recorded by {row.get('created_by_name') or 'the shop'}.")
        if (row.get("note") or "").strip():
            note += f" “{row['note'].strip()}”"
        note += f" Charged {float(row.get('value') or 0):,.0f}"
        note += (f"; {take:,.0f} off this payslip, {owed - take:,.0f} still to come."
                 if part else f", taken in full on this payslip.")
        lines.append({
            "name": f"Stock loss {row.get('slip_number')} — {row.get('product_name')}"
                    + (" (part)" if part else ""),
            "type": "deduction",
            "amount": take,
            "calculated_amount": take,
            "is_percentage": False,
            "auto_generated": True,
            "source": "stock_loss",
            "scope": "employee",
            "note": note,
            "details": {"loss_id": row["id"], "slip_number": row.get("slip_number"),
                        "product_name": row.get("product_name"),
                        "qty": row.get("qty"), "reason": row.get("reason_label"),
                        "recorded_on": str(row.get("created_at"))[:10],
                        "recorded_by": row.get("created_by_name") or "",
                        "charged": float(row.get("value") or 0),
                        "owed": owed, "part_payment": part, "note": note},
        })
        applications.append({"loss_id": row["id"], "amount": take, "owed": owed})
    return lines, applications


async def mark_loss_deductions(applications: list, payslip_id: str, period: str = "") -> None:
    """A payslip has been drafted — the charge is now coming off that pay."""
    for app in applications:
        row = await db.stock_losses.find_one({"id": app["loss_id"]}, {"_id": 0})
        if not row:
            continue
        recovered = round(float(row.get("recovered_amount") or 0) + float(app["amount"]), 2)
        done = recovered >= round(float(row.get("value") or 0), 2) - 0.01
        await db.stock_losses.update_one({"id": app["loss_id"]}, {"$set": {
            "recovered_amount": recovered,
            "recovery_status": "recovered" if done else "pending",
            "recovery_updated_at": _now(),
            "recovery_note": f"Deducted on payslip {payslip_id}{f' ({period})' if period else ''}",
        }, "$push": {"deductions": {"payslip_id": payslip_id, "period": period,
                                    "amount": float(app["amount"]), "at": _now()}}})


async def unmark_loss_deductions(payslip_id: str) -> int:
    """That payslip was deleted — the charge goes back on the owed list."""
    undone = 0
    async for row in db.stock_losses.find({"deductions.payslip_id": payslip_id}, {"_id": 0}):
        back = sum(float(d.get("amount") or 0) for d in (row.get("deductions") or [])
                   if d.get("payslip_id") == payslip_id)
        if back <= 0:
            continue
        await db.stock_losses.update_one({"id": row["id"]}, {
            "$set": {"recovered_amount": max(0.0, round(float(row.get("recovered_amount") or 0) - back, 2)),
                     "recovery_status": "pending",
                     "recovery_updated_at": _now(),
                     "recovery_note": f"Payslip {payslip_id} was deleted — still owed"},
            "$pull": {"deductions": {"payslip_id": payslip_id}},
        })
        undone += 1
    return undone


@router.get("/stock-losses/pending-deductions")
async def pending_deductions(staff_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """What payroll still has to take off, per person."""
    query: dict = {"recoverable": True, "recovery_status": "pending"}
    if staff_id:
        query["employee_id"] = staff_id
    rows = await db.stock_losses.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_staff: dict = {}
    for row in rows:
        owed = round(float(row.get("value") or 0) - float(row.get("recovered_amount") or 0), 2)
        if owed <= 0:
            continue
        entry = by_staff.setdefault(row.get("employee_id"), {
            "employee_id": row.get("employee_id"),
            "employee_name": row.get("employee_name"),
            "total": 0.0, "items": [],
        })
        entry["total"] = round(entry["total"] + owed, 2)
        entry["items"].append({"id": row["id"], "slip_number": row.get("slip_number"),
                               "product_name": row.get("product_name"), "qty": row.get("qty"),
                               "value": row.get("value"), "owed": owed,
                               "recovered_amount": float(row.get("recovered_amount") or 0),
                               "created_at": row.get("created_at")})
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

def _stage_rule(product: dict, variant_id: str) -> Optional[dict]:
    """How a produce stage grows into the next one (iter424).

    A produce item keeps its own life stages as variants — Day-old chicks,
    4 Week Broilers — in order. A stage says how many days it runs for; what it
    becomes is the next stage down the list unless it names one. Nothing moves
    between products any more, so there is one item, one set of batches and one
    place to look.
    """
    variants = product.get("variants") or []
    current = next((v for v in variants if v.get("id") == variant_id), None)
    if not current:
        return None
    try:
        days = int(current.get("grow_after_days") or 0)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    nxt = None
    if current.get("grows_into_variant_id"):
        nxt = next((v for v in variants if v.get("id") == current["grows_into_variant_id"]), None)
    if not nxt:
        order = [v.get("id") for v in variants]
        at = order.index(variant_id)
        nxt = variants[at + 1] if at + 1 < len(variants) else None
    if not nxt:
        return None
    return {"to_variant": nxt["id"], "to_variant_name": nxt.get("name"), "days": days}


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
    variant = None
    stage = None
    if product.get("is_produce"):
        if not data.variant_id:
            raise HTTPException(status_code=400, detail="Which stage came in? Pick the variant")
        variant = next((v for v in (product.get("variants") or []) if v.get("id") == data.variant_id), None)
        if not variant:
            raise HTTPException(status_code=404, detail="That stage is not on this item")
        stage = _stage_rule(product, data.variant_id)
        if not stage:
            raise HTTPException(
                status_code=400,
                detail=f"{variant.get('name')} has no stage to grow into — set its days and the stage after it")
        rule = {"to": product["id"], "days": stage["days"]}
    else:
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
        # Produce grows through its own stages, so the batch carries the stage
        # it is at and the one it becomes (iter424).
        "variant_id": data.variant_id or None,
        "variant_name": (variant or {}).get("name"),
        "becomes_variant_id": (stage or {}).get("to_variant"),
        "becomes_variant_name": (stage or {}).get("to_variant_name"),
        "grow_after_days": rule["days"],
        "note": (data.note or "").strip()[:300],
        "supplier": (data.supplier or "").strip()[:120] or None,
        "events": [],
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.stock_batches.insert_one(dict(batch))
    # Booking a produce intake IS the stock entry: the shop should not have to
    # add stock and then start a batch over it (iter424).
    if data.add_stock and data.variant_id:
        await db.products.update_one({"id": product["id"], "variants.id": data.variant_id},
                                     {"$inc": {"variants.$.stock": qty}})
        fresh = await db.products.find_one({"id": product["id"]}, {"_id": 0, "variants": 1})
        await db.products.update_one({"id": product["id"]}, {"$set": {
            "stock": sum(float(v.get("stock") or 0) for v in (fresh.get("variants") or []))}})
        await db.stock_movements.insert_one({
            "id": f"mov_{uuid.uuid4().hex[:10]}", "product_id": product["id"],
            "product_name": product.get("name"), "variant_id": data.variant_id,
            "delta": qty, "reason": "purchase", "location_id": store_id,
            "notes": f"Batch intake — {(variant or {}).get('name')}",
            "supplier": batch["supplier"], "reference": batch["id"],
            "created_at": _now(), "created_by": current_user["id"],
            "created_by_name": current_user.get("name", "")})
    becomes = batch.get("becomes_variant_name") or batch["becomes_product_name"]
    return {"message": f"{qty:g} {(variant or {}).get('name') or product.get('name')} "
                       f"will become {becomes} on {batch['matures_at'][:10]}",
            "batch": batch}


async def mature_batch(batch: dict, actor: Optional[dict] = None, qty_override: Optional[float] = None) -> dict:
    """Move a batch onto the grown product. The count, and therefore the price,
    changes. Anything that died on the way is recorded against the batch, never
    silently dropped."""
    qty = float(qty_override if qty_override is not None else (batch.get("remaining") or 0))
    if batch.get("variant_id"):
        return await _mature_stage(batch, qty, actor)
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
            "supplier": batch.get("supplier"),
            "events": [], "created_at": now, "created_by": record["created_by"],
            "created_by_name": record["created_by_name"],
        })
    return {"ok": True, "qty": moved, "batch_id": batch["id"], "transformation": record["id"]}


async def _mature_stage(batch: dict, qty: float, actor: Optional[dict] = None) -> dict:
    """A produce batch grows through its OWN stages: the same item, the next
    variant, so a batch of chicks simply becomes a batch of broilers and keeps
    its history, its supplier and its losses (iter424)."""
    product = await db.products.find_one({"id": batch["product_id"]}, {"_id": 0})
    if not product:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "blocked", "blocked_reason": "That produce item no longer exists"}})
        return {"ok": False, "reason": "missing_product", "batch_id": batch["id"]}
    variants = product.get("variants") or []
    at = next((v for v in variants if v.get("id") == batch["variant_id"]), None)
    to = next((v for v in variants if v.get("id") == batch.get("becomes_variant_id")), None)
    if not at or not to:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "blocked", "blocked_reason": "The stage it should become is no longer on this item"}})
        return {"ok": False, "reason": "missing_stage", "batch_id": batch["id"]}
    if qty <= 0:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "matured", "matured_at": _now()}})
        return {"ok": True, "qty": 0, "batch_id": batch["id"]}

    store_id = batch.get("location_id") or ""
    moved = min(qty, float(at.get("stock") or 0))
    if moved <= 0:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "status": "blocked", "blocked_reason": f"No {at.get('name')} left to grow on"}})
        return {"ok": False, "reason": "no_stock", "batch_id": batch["id"]}

    await db.products.update_one({"id": product["id"], "variants.id": at["id"]},
                                 {"$inc": {"variants.$.stock": -moved}})
    await db.products.update_one({"id": product["id"], "variants.id": to["id"]},
                                 {"$inc": {"variants.$.stock": moved}})

    now = _now()
    record = {
        "id": f"grow_{uuid.uuid4().hex[:10]}",
        "batch_id": batch["id"],
        "from_product_id": product["id"], "from_product_name": f"{product.get('name')} — {at.get('name')}",
        "to_product_id": product["id"], "to_product_name": f"{product.get('name')} — {to.get('name')}",
        "from_variant_id": at["id"], "to_variant_id": to["id"],
        "qty": moved,
        "location_id": store_id,
        "from_value": round(_unit_value(product, store_id, at) * moved, 2),
        "to_value": round(_unit_value(product, store_id, to) * moved, 2),
        "lost_on_the_way": float(batch.get("lost") or 0),
        "needs_loss_check": True,
        "created_at": now,
        "created_by": (actor or {}).get("id", "cron"),
        "created_by_name": (actor or {}).get("name", "Automatic"),
    }
    await db.stock_transformations.insert_one(dict(record))
    await db.stock_movements.insert_one({
        "id": f"sm_{uuid.uuid4().hex[:10]}",
        "product_id": product["id"], "product_name": product.get("name"),
        "variant_id": to["id"], "delta": 0, "reason": "adjustment",
        "notes": f"Grew on: {at.get('name')} → {to.get('name')} ({moved:g})",
        "reference": batch["id"], "location_id": store_id, "created_at": now,
        "created_by": record["created_by"], "created_by_name": record["created_by_name"],
    })

    # The batch follows the birds: same batch, next stage, clock reset. Its
    # supplier and its deaths stay with it, which is what the mortality chart
    # and the run comparison read.
    nxt = _stage_rule(product, to["id"])
    if nxt:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "variant_id": to["id"], "variant_name": to.get("name"),
            "becomes_variant_id": nxt["to_variant"], "becomes_variant_name": nxt["to_variant_name"],
            "grow_after_days": nxt["days"], "remaining": moved,
            "matures_at": (datetime.now(timezone.utc) + timedelta(days=nxt["days"])).isoformat(),
            "transformation_id": record["id"],
        }, "$push": {"events": {"at": now, "qty": moved,
                                "what": f"Grew on to {to.get('name')}"}}})
    else:
        await db.stock_batches.update_one({"id": batch["id"]}, {"$set": {
            "variant_id": to["id"], "variant_name": to.get("name"),
            "becomes_variant_id": None, "becomes_variant_name": None,
            "status": "matured", "matured_at": now, "matured_qty": moved,
            "transformation_id": record["id"],
        }, "$push": {"events": {"at": now, "qty": moved,
                                "what": f"Grew on to {to.get('name')} — final stage"}}})
    return {"ok": True, "qty": moved, "batch_id": batch["id"], "transformation": record["id"],
            "stage": to.get("name")}


async def _mortality_rows(batches: list, weeks: int = 8) -> list:
    """One row per batch: what came in, what died, in which week of its life.

    The numbers come straight from recorded write-offs, which is the only place
    a death is ever entered (iter419).
    """
    ids = [b["id"] for b in batches]
    losses = await db.stock_losses.find({"batches.batch_id": {"$in": ids}}, {"_id": 0}).to_list(2000)
    span = max(1, min(int(weeks or 8), 26))
    rows = []
    for batch in batches:
        try:
            start = datetime.fromisoformat(str(batch.get("received_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        buckets: dict = {}
        detail: dict = {}
        for loss in losses:
            hit = next((b for b in (loss.get("batches") or []) if b.get("batch_id") == batch["id"]), None)
            if not hit:
                continue
            try:
                when = datetime.fromisoformat(str(loss.get("created_at")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            week = max(1, int((when - start).days // 7) + 1)
            qty = float(hit.get("qty") or 0)
            buckets[week] = round(buckets.get(week, 0) + qty, 2)
            label = loss.get("reason_label") or loss.get("reason") or "Lost"
            detail[label] = round(detail.get(label, 0) + qty, 2)
        started = float(batch.get("qty") or 0)
        lost = round(sum(buckets.values()), 2)
        rows.append({
            "batch_id": batch["id"],
            "product_name": batch.get("product_name"),
            "variant_name": batch.get("variant_name"),
            "becomes_product_name": batch.get("becomes_variant_name") or batch.get("becomes_product_name"),
            "supplier": batch.get("supplier"),
            "received_at": batch.get("received_at"),
            "status": batch.get("status"),
            "started_with": started,
            "remaining": float(batch.get("remaining") or 0),
            "lost": lost,
            "mortality_pct": round((lost / started) * 100, 1) if started else 0,
            "survival_pct": round(100 - (lost / started) * 100, 1) if started else 0,
            "by_reason": detail,
            "age_days": max(0, (datetime.now(timezone.utc) - start).days),
            "weeks": [{"week": w, "deaths": buckets.get(w, 0)} for w in range(1, span + 1)],
        })
    return rows


@router.get("/stock-batches/compare")
async def compare_batches(ids: str = "", weeks: int = 8,
                          current_user: dict = Depends(get_current_user)):
    """Two runs side by side, so a weak supplier shows itself.

    `ids` is a comma-separated list of batch ids (two is the useful number).
    """
    wanted = [i.strip() for i in (ids or "").split(",") if i.strip()][:4]
    if len(wanted) < 2:
        raise HTTPException(status_code=400, detail="Pick two runs to compare")
    batches = await db.stock_batches.find({"id": {"$in": wanted}}, {"_id": 0}).to_list(4)
    if len(batches) < 2:
        raise HTTPException(status_code=404, detail="One of those runs no longer exists")
    for batch in batches:
        if not await is_store_member(current_user, batch.get("location_id") or ""):
            raise HTTPException(status_code=403, detail="One of those runs is at another store")
    batches.sort(key=lambda b: wanted.index(b["id"]))
    rows = await _mortality_rows(batches, weeks)
    by_supplier: dict = {}
    for row in rows:
        key = row.get("supplier") or "Not recorded"
        agg = by_supplier.setdefault(key, {"supplier": key, "batches": 0, "started_with": 0.0, "lost": 0.0})
        agg["batches"] += 1
        agg["started_with"] = round(agg["started_with"] + row["started_with"], 2)
        agg["lost"] = round(agg["lost"] + row["lost"], 2)
    for agg in by_supplier.values():
        agg["mortality_pct"] = round((agg["lost"] / agg["started_with"]) * 100, 1) if agg["started_with"] else 0

    verdict = ""
    if len(rows) >= 2:
        best = min(rows, key=lambda r: r["mortality_pct"])
        worst = max(rows, key=lambda r: r["mortality_pct"])
        gap = round(worst["mortality_pct"] - best["mortality_pct"], 1)
        if gap <= 0:
            verdict = "Both runs lost the same share — nothing to choose between them."
        else:
            who = f" ({worst['supplier']})" if worst.get("supplier") else ""
            keeps = f" ({best['supplier']})" if best.get("supplier") else ""
            verdict = (f"The run booked in {str(worst['received_at'])[:10]}{who} lost "
                       f"{gap:g} percentage points more than the one from "
                       f"{str(best['received_at'])[:10]}{keeps} — "
                       f"{worst['lost']:g} of {worst['started_with']:g} against "
                       f"{best['lost']:g} of {best['started_with']:g}.")
        # Two runs of different ages are not a fair fight: the younger one has
        # had fewer weeks in which to lose anything (iter420).
        young, old = min(rows, key=lambda r: r["age_days"]), max(rows, key=lambda r: r["age_days"])
        if old["age_days"] - young["age_days"] >= 7:
            verdict += (f" Mind the ages though: the {str(young['received_at'])[:10]} run is only "
                        f"{young['age_days']} day(s) old against {old['age_days']}, so it has had "
                        f"less time to lose anything.")
    return {"batches": rows, "weeks": max(1, min(int(weeks or 8), 26)),
            "by_supplier": sorted(by_supplier.values(), key=lambda s: -s["mortality_pct"]),
            "verdict": verdict}


@router.patch("/stock-batches/{batch_id}")
async def update_batch(batch_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Name the hatchery a run came from — often known a day after it arrived."""
    batch = await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if not await is_store_member(current_user, batch.get("location_id") or ""):
        raise HTTPException(status_code=403, detail="That run is at another store")
    fields = {}
    if "supplier" in (data or {}):
        fields["supplier"] = (data.get("supplier") or "").strip()[:120] or None
    if "note" in (data or {}):
        fields["note"] = (data.get("note") or "").strip()[:300]
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to change")
    fields["updated_at"] = _now()
    fields["updated_by_name"] = current_user.get("name", "")
    await db.stock_batches.update_one({"id": batch_id}, {"$set": fields})
    return {"message": "Saved", "batch": await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})}


@router.get("/stock-batches/mortality")
async def batch_mortality(product_id: Optional[str] = None, location_id: Optional[str] = None,
                          weeks: int = 8, limit: int = 20,
                          current_user: dict = Depends(get_current_user)):
    """Deaths per batch, week by week — so a weak hatchery run shows itself.

    The numbers come straight from recorded write-offs, which is the only place
    a death is ever entered (iter419).
    """
    query: dict = {}
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store:
        query["location_id"] = store
    if product_id:
        query["product_id"] = product_id
    batches = await db.stock_batches.find(query, {"_id": 0}).sort("received_at", -1).limit(limit).to_list(limit)
    if not batches:
        return {"batches": [], "weeks": 0, "worst": None, "store_id": store}

    rows = await _mortality_rows(batches, weeks)
    worst = max(rows, key=lambda r: r["mortality_pct"], default=None)
    return {
        "store_id": store,
        "weeks": max(1, min(int(weeks or 8), 26)),
        "batches": rows,
        "worst": worst if worst and worst["lost"] > 0 else None,
    }


@router.post("/stock-batches/{batch_id}/mature")
async def mature_batch_now(batch_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Move a batch on early (or confirm one by hand).

    No deaths are entered here: the only place a death is ever recorded is a
    write-off, which has already taken it off this batch and off the shelf.
    Asking again would count the same bird twice (iter419).
    """
    batch = await db.stock_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.get("status") != "growing":
        raise HTTPException(status_code=400, detail=f"This batch is already {batch.get('status')}")
    res = await mature_batch(batch, current_user)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail={
            "missing_product": "The product it should become no longer exists",
            "missing_stage": "The stage it should become is no longer on this item",
            "no_stock": "There is none of it left at this store to grow on",
        }.get(res.get("reason"), "Could not grow this batch on"))
    # Produce moves between stages of one item, so the stage names are what the
    # farm wants to read — not the item's name twice (iter424).
    was = batch.get("variant_name") or batch.get("product_name")
    now_is = res.get("stage") or batch.get("becomes_variant_name") or batch.get("becomes_product_name")
    return {"message": f"{res['qty']:g} {was} became {now_is}", **res}


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
