"""Fixed assets register — purchase cost, capitalised improvements, repairs.

The distinction auditors and customs ask about: money that extends an asset's
life or capacity (new roof, deeper borehole, replacement engine) is CAPITALISED
— it becomes part of what the asset cost. Money that merely keeps it working
(servicing, paint, tyres) is a repairs & maintenance EXPENSE and never changes
the asset's value. Both are logged against the asset so its history lives in
one place; only improvements move the carried cost.

Depreciation postings to the ledger are deliberately out of scope for now —
this is the register and the improvement/repair split only.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException

from deps import db, require_staff, require_manager, _audit, get_campus_filter

router = APIRouter(prefix="/api/finance/assets", tags=["finance"])

COLL = db.finance_assets
SPEND_KINDS = {"improvement", "repair"}
CATEGORIES = {"equipment", "vehicle", "building", "land", "furniture", "livestock", "IT", "other"}
EDITABLE = {"name", "category", "purchase_date", "depreciation_years", "serial_number",
            "condition", "location_id", "sublocation_id", "department_id", "notes", "currency"}


async def _post_expense(payload: dict, actor: dict) -> Optional[str]:
    """Book real money out through the normal expense entry.

    Deliberately reuses `POST /api/finance/transactions/expense` rather than
    writing a parallel record, so the cash account is drawn down and the
    double-entry posting is identical to any other expense.
    """
    if not payload.get("location_id"):
        raise HTTPException(
            status_code=400,
            detail="Pick the campus on the asset before recording the expense — every ledger entry needs one")
    try:
        from routers.finance.transactions import record_expense
        je = await record_expense(payload, actor)
        return (je or {}).get("id")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"The expense could not be recorded: {e}")


def _totals(asset: dict) -> dict:
    rows = asset.get("spend") or []
    improvements = round(sum(float(r.get("amount") or 0) for r in rows if r.get("kind") == "improvement"), 2)
    repairs = round(sum(float(r.get("amount") or 0) for r in rows if r.get("kind") == "repair"), 2)
    cost = round(float(asset.get("value") or 0) + improvements, 2)
    return {
        "improvements_total": improvements,
        "repairs_total": repairs,
        "total_cost": cost,
        "carried_value": round(float(asset.get("current_value") or 0) or cost, 2),
    }


def _amount(raw, field="amount") -> float:
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")


@router.get("")
async def list_assets(location_id: Optional[str] = None, category: Optional[str] = None,
                      current_user: dict = Depends(require_staff)):
    """The asset register plus roll-ups of purchase, improvement and repair spend."""
    campus = await get_campus_filter(current_user)
    query = {}
    if campus:
        # An asset with no campus recorded must still be listed — otherwise it
        # silently vanishes from the register and looks deleted.
        query["$and"] = [{"$or": [campus, {"location_id": {"$in": [None, ""]}},
                                  {"location_id": {"$exists": False}}]}]
    if location_id:
        query["location_id"] = location_id
    if category:
        query["category"] = category
    rows = await COLL.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    out = [{**r, **_totals(r)} for r in rows]
    return {
        "assets": out,
        "count": len(out),
        "purchase_total": round(sum(float(r.get("value") or 0) for r in out), 2),
        "improvements_total": round(sum(r["improvements_total"] for r in out), 2),
        "repairs_total": round(sum(r["repairs_total"] for r in out), 2),
        "total_cost": round(sum(r["total_cost"] for r in out), 2),
    }


@router.post("/merge")
async def merge_assets(data: dict, current_user: dict = Depends(require_manager)):
    """Fold duplicate records into one asset.

    Body: { target_id, source_ids: [], combine_values?: bool }
    The target keeps its own name and details; every improvement, repair and
    revaluation from the sources moves across (tagged with where it came from),
    and by default the sources' purchase costs are added to the target's so the
    total the organisation paid is preserved. Sources are soft-deleted.
    """
    target_id = (data.get("target_id") or "").strip()
    source_ids = [s for s in (data.get("source_ids") or []) if s and s != target_id]
    if not target_id or not source_ids:
        raise HTTPException(status_code=400, detail="Pick the asset to keep and at least one to merge into it")
    target = await COLL.find_one({"id": target_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Asset not found")
    combine = data.get("combine_values") is not False

    spend, valuations, merged, added_value = [], [], [], 0.0
    for sid in source_ids:
        src = await COLL.find_one({"id": sid}, {"_id": 0})
        if not src:
            continue
        for r in (src.get("spend") or []):
            spend.append({**r, "merged_from": sid, "merged_from_name": src.get("name", "")})
        for v in (src.get("valuations") or []):
            valuations.append({**v, "merged_from": sid})
        if combine:
            added_value += float(src.get("value") or 0)
        merged.append({"id": sid, "name": src.get("name", ""), "value": float(src.get("value") or 0),
                       "merged_at": datetime.now(timezone.utc).isoformat(),
                       "merged_by": current_user["id"]})
        await db.deleted_items.insert_one({**src, "_deleted_from": "finance_assets",
                                           "deleted_at": datetime.now(timezone.utc).isoformat(),
                                           "deleted_by": current_user["id"],
                                           "delete_reason": f"merged into {target_id}"})
        await COLL.delete_one({"id": sid})
    if not merged:
        raise HTTPException(status_code=404, detail="None of those assets could be found")

    ops = {"$set": {"value": round(float(target.get("value") or 0) + added_value, 2),
                    "updated_at": datetime.now(timezone.utc).isoformat()},
           "$push": {"merged_assets": {"$each": merged}}}
    if spend:
        ops["$push"]["spend"] = {"$each": spend}
    if valuations:
        ops["$push"]["valuations"] = {"$each": valuations}
    await COLL.update_one({"id": target_id}, ops)
    fresh = await COLL.find_one({"id": target_id}, {"_id": 0})
    await _audit(current_user["id"], "update", "asset_merge", target_id,
                 {"merged": [m["id"] for m in merged], "entries_moved": len(spend)})
    return {"asset": {**fresh, **_totals(fresh)}, "merged": merged, "entries_moved": len(spend)}


@router.get("/{asset_id}")
async def get_asset(asset_id: str, current_user: dict = Depends(require_staff)):
    asset = await COLL.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {**asset, **_totals(asset)}


@router.post("")
async def create_asset(data: dict, current_user: dict = Depends(require_manager)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="What is the asset called?")
    category = (data.get("category") or "equipment").strip()
    if category not in CATEGORIES:
        category = "other"
    doc = {
        "id": f"ast_{uuid.uuid4().hex[:8]}",
        "name": name[:160],
        "category": category,
        "value": _amount(data.get("value") or 0, "value"),
        "currency": (data.get("currency") or "UGX").strip().upper()[:4],
        "purchase_date": (data.get("purchase_date") or "")[:10],
        "depreciation_years": _amount(data.get("depreciation_years") or 5, "depreciation_years"),
        "serial_number": (data.get("serial_number") or "").strip()[:80],
        "condition": (data.get("condition") or "good").strip()[:40],
        "location_id": data.get("location_id") or current_user.get("location_id", ""),
        "sublocation_id": data.get("sublocation_id") or "",
        "department_id": data.get("department_id") or "",
        "notes": (data.get("notes") or "").strip()[:500],
        "spend": [],
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.get("post_expense") and doc["value"] > 0:
        vendor = (data.get("vendor") or "").strip()
        doc["purchase_expense_id"] = await _post_expense({
            "amount": doc["value"],
            "description": f"Asset purchase — {doc['name']}" + (f" ({vendor})" if vendor else ""),
            "date": doc["purchase_date"] or datetime.now(timezone.utc).date().isoformat(),
            "expense_account_id": data.get("expense_account_id"),
            "expense_account_code": data.get("expense_account_code") or "5000",
            "paid_from_account_id": data.get("paid_from_account_id"),
            "reference": (data.get("reference") or "").strip() or doc["id"],
            "location_id": doc["sublocation_id"] or doc["location_id"],
            "department_id": doc["department_id"],
        }, current_user)
    await COLL.insert_one(dict(doc))
    await _audit(current_user["id"], "create", "asset", doc["id"], {"name": doc["name"], "value": doc["value"]})
    return {**doc, **_totals(doc)}


@router.put("/{asset_id}")
async def update_asset(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    update = {k: v for k, v in data.items() if k in EDITABLE}
    if "value" in data:
        update["value"] = _amount(data["value"], "value")
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await COLL.update_one({"id": asset_id}, {"$set": update})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Asset not found")
    fresh = await COLL.find_one({"id": asset_id}, {"_id": 0})
    return {**fresh, **_totals(fresh)}


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, current_user: dict = Depends(require_manager)):
    asset = await COLL.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.deleted_items.insert_one({**asset, "_deleted_from": "finance_assets",
                                      "deleted_at": datetime.now(timezone.utc).isoformat(),
                                      "deleted_by": current_user["id"]})
    await COLL.delete_one({"id": asset_id})
    await _audit(current_user["id"], "delete", "asset", asset_id, {"name": asset.get("name")})
    return {"deleted": True}


@router.post("/{asset_id}/spend")
async def log_asset_spend(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Log money spent on an asset.

    Body: {kind: 'improvement'|'repair', amount, date?, description,
           vendor?, reference?, extends_life_years?, transaction_id?}
    Only `improvement` changes the carried cost.
    """
    asset = await COLL.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    kind = (data.get("kind") or "improvement").lower()
    if kind not in SPEND_KINDS:
        raise HTTPException(status_code=400, detail="kind must be improvement or repair")
    amount = _amount(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Enter how much was spent")
    description = (data.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Describe what the money was spent on")
    extra_life = _amount(data.get("extends_life_years") or 0, "extends_life_years") if kind == "improvement" else 0
    row = {
        "id": f"asp_{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "amount": amount,
        "date": (data.get("date") or datetime.now(timezone.utc).date().isoformat())[:10],
        "description": description[:300],
        "vendor": (data.get("vendor") or "").strip()[:160],
        "reference": (data.get("reference") or "").strip()[:80],
        "extends_life_years": extra_life,
        "currency": (data.get("currency") or asset.get("currency") or "UGX").strip().upper()[:4],
        "transaction_id": data.get("transaction_id") or "",
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.get("post_expense"):
        row["expense_id"] = await _post_expense({
            "amount": amount,
            "description": f"{asset.get('name', 'Asset')} — {row['description']}"
                           + (f" ({row['vendor']})" if row["vendor"] else ""),
            "date": row["date"],
            "expense_account_id": data.get("expense_account_id"),
            "expense_account_code": data.get("expense_account_code") or "5000",
            "paid_from_account_id": data.get("paid_from_account_id"),
            "reference": row["reference"] or row["id"],
            "location_id": (data.get("location_id") or asset.get("sublocation_id")
                            or asset.get("location_id") or ""),
            "department_id": data.get("department_id") or asset.get("department_id") or "",
        }, current_user)
    ops = {"$push": {"spend": row}, "$set": {"updated_at": row["created_at"]}}
    if extra_life:
        ops["$inc"] = {"depreciation_years": extra_life}
    await COLL.update_one({"id": asset_id}, ops)
    fresh = await COLL.find_one({"id": asset_id}, {"_id": 0})
    await _audit(current_user["id"], "create", "asset_spend", asset_id,
                 {"kind": kind, "amount": amount, "description": row["description"]})
    return {"entry": row, "asset": {**fresh, **_totals(fresh)}}


@router.delete("/{asset_id}/spend/{entry_id}")
async def delete_asset_spend(asset_id: str, entry_id: str, current_user: dict = Depends(require_manager)):
    asset = await COLL.find_one({"id": asset_id}, {"_id": 0, "spend": 1})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    row = next((r for r in (asset.get("spend") or []) if r.get("id") == entry_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    ops = {"$pull": {"spend": {"id": entry_id}}}
    if row.get("kind") == "improvement" and row.get("extends_life_years"):
        ops["$inc"] = {"depreciation_years": -float(row["extends_life_years"])}
    await COLL.update_one({"id": asset_id}, ops)
    fresh = await COLL.find_one({"id": asset_id}, {"_id": 0})
    await _audit(current_user["id"], "delete", "asset_spend", asset_id, {"entry": entry_id})
    return {"removed": entry_id, "asset": {**fresh, **_totals(fresh)}}


@router.put("/{asset_id}/valuation")
async def revalue_asset(asset_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Record a revaluation — kept separate from cost so both are visible."""
    asset = await COLL.find_one({"id": asset_id}, {"_id": 0, "id": 1})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    value = _amount(data.get("current_value"), "current_value")
    entry = {
        "id": f"val_{uuid.uuid4().hex[:8]}",
        "current_value": value,
        "valued_on": (data.get("valued_on") or datetime.now(timezone.utc).date().isoformat())[:10],
        "basis": (data.get("basis") or "").strip()[:120],
        "notes": (data.get("notes") or "").strip()[:300],
        "by": current_user["id"], "by_name": current_user.get("name", ""),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await COLL.update_one({"id": asset_id}, {
        "$set": {"current_value": value, "valued_on": entry["valued_on"], "updated_at": entry["at"]},
        "$push": {"valuations": entry},
    })
    fresh = await COLL.find_one({"id": asset_id}, {"_id": 0})
    return {**fresh, **_totals(fresh)}
