"""Similar-item consolidation for customs paperwork.

A 40ft container is packed over weeks by different volunteers, so the same
thing gets entered again and again — "Blankets", "blanket", "Blankets (used)" —
sometimes in the same box, more often spread across boxes 24 and 25. On a
customs manifest those read as separate consignment lines and invite questions.

This module finds those near-duplicates, shows what a single combined line
would look like (quantity and value added up, box numbers written "24 & 25"),
and lets an admin combine across boxes, combine only within one box, or delete
a repeated entry outright. Every combine keeps the original rows so it can be
undone.
"""
import re
import uuid
from difflib import SequenceMatcher
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from deps import db, _audit, require_admin

router = APIRouter(prefix="/api", tags=["shipments"])

SENSITIVITY = {"strict": 0.86, "normal": 0.72, "loose": 0.58}
# Words that say nothing about WHAT the item is.
NOISE = {
    "box", "boxes", "carton", "cartons", "bag", "bags", "pcs", "pc", "piece", "pieces",
    "set", "sets", "pack", "packs", "packet", "assorted", "mixed", "various", "misc",
    "new", "used", "second", "hand", "donated", "donation", "large", "small", "medium",
    "big", "size", "sized", "of", "the", "and", "with", "for", "in", "on", "a", "an",
    "x", "approx", "about", "pair", "pairs", "item", "items",
}


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and not word.endswith("ses"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(*parts) -> set:
    text = " ".join(str(p or "") for p in parts).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    out = set()
    for raw in text.split():
        if raw.isdigit() or raw in NOISE or len(raw) < 2:
            continue
        out.add(_singular(raw))
    return out


def _flat(*parts) -> str:
    text = " ".join(str(p or "") for p in parts).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _similarity(a: dict, b: dict) -> float:
    ta, tb = _tokens(a.get("name"), a.get("category")), _tokens(b.get("name"), b.get("category"))
    jac = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    seq = SequenceMatcher(None, _flat(a.get("name")), _flat(b.get("name"))).ratio()
    # Same barcode is the same product, whatever the description says.
    for key in ("isbn", "upc"):
        if a.get(key) and a.get(key) == b.get(key):
            return 1.0
    return max(jac, seq)


def _box_no(name: str):
    m = re.search(r"(\d+)", name or "")
    return int(m.group(1)) if m else None


def _box_of(item: dict, units_by_id: dict) -> dict:
    uid = item.get("packing_unit_id")
    unit = units_by_id.get(uid) if uid else None
    name = (unit or {}).get("name") or ""
    return {"id": uid or "", "name": name, "no": _box_no(name)}


def box_label(boxes: list) -> str:
    """'24 & 25' — the way a customs officer expects to read it."""
    numbered = sorted({b["no"] for b in boxes if b.get("no") is not None})
    named = sorted({b["name"] for b in boxes if b.get("no") is None and b.get("name")})
    parts = [str(n) for n in numbered] + named
    unboxed = any(not b.get("id") for b in boxes)
    if not parts:
        return "Not boxed yet"
    if len(parts) == 1:
        label = f"Box {parts[0]}" if numbered else parts[0]
    else:
        label = "Boxes " + (", ".join(parts[:-1]) + " & " + parts[-1])
    return label + (" + loose" if unboxed else "")


def _line_value(item: dict) -> float:
    return float(item.get("value_usd") or 0) * int(item.get("qty_acquired") or 0)


def _cluster(items: list, threshold: float) -> list:
    """Greedy clustering against each cluster's strongest member."""
    clusters = []
    for it in items:
        best, best_score = None, 0.0
        for cl in clusters:
            score = min(_similarity(it, other) for other in cl)
            if score >= threshold and score > best_score:
                best, best_score = cl, score
        if best is None:
            clusters.append([it])
        else:
            best.append(it)
    return [c for c in clusters if len(c) > 1]


def _group_payload(cluster: list, units_by_id: dict) -> dict:
    rows = []
    for it in cluster:
        box = _box_of(it, units_by_id)
        rows.append({
            "id": it["id"],
            "name": it.get("name") or "",
            "category": it.get("category") or "",
            "qty_acquired": int(it.get("qty_acquired") or 0),
            "qty_needed": int(it.get("qty_needed") or 0),
            "value_usd": float(it.get("value_usd") or 0),
            "line_value": round(_line_value(it), 2),
            "weight_kg": float(it.get("weight_kg") or 0),
            "hs_code": it.get("hs_code") or "",
            "condition": it.get("condition") or "",
            "manifest_group_id": it.get("manifest_group_id"),
            "consolidated": bool(it.get("consolidated")),
            "box_id": box["id"], "box_name": box["name"], "box_no": box["no"],
        })
    boxes = [{"id": r["box_id"], "name": r["box_name"], "no": r["box_no"]} for r in rows]
    distinct_boxes = {(b["id"] or "loose") for b in boxes}
    total_qty = sum(r["qty_acquired"] for r in rows)
    total_value = round(sum(r["line_value"] for r in rows), 2)
    total_weight = round(sum(r["weight_kg"] * r["qty_acquired"] for r in rows), 3)
    same_box = len(distinct_boxes) == 1
    names = {r["name"].strip().lower() for r in rows}
    unit_values = {r["value_usd"] for r in rows}
    exact_repeat = same_box and len(names) == 1 and len(unit_values) == 1
    # Keep the row with the most stock, then the lowest box number — that's
    # usually the "real" line a packer has been maintaining.
    keeper = sorted(rows, key=lambda r: (-r["qty_acquired"], r["box_no"] if r["box_no"] is not None else 9999))[0]
    longest_name = sorted(rows, key=lambda r: -len(r["name"]))[0]["name"]
    return {
        "id": f"sim_{uuid.uuid4().hex[:8]}",
        "label": longest_name,
        "same_box": same_box,
        "box_count": len(distinct_boxes),
        "box_label": box_label(boxes),
        "total_qty": total_qty,
        "total_value": total_value,
        "total_weight_kg": total_weight,
        "exact_repeat": exact_repeat,
        "suggested_keep": keeper["id"],
        "suggested_action": "delete_repeats" if exact_repeat else ("combine_same_box" if same_box else "combine_across_boxes"),
        "combined_preview": {
            "name": longest_name,
            "qty_acquired": total_qty,
            # Unit value re-derived so the line total is unchanged after combining.
            "value_usd": round(total_value / total_qty, 2) if total_qty else 0,
            "line_value": total_value,
            "box_label": box_label(boxes),
        },
        "items": rows,
    }


@router.get("/shipments/{shipment_id}/similar-items")
async def find_similar_items(shipment_id: str, sensitivity: str = "normal",
                             current_user: dict = Depends(require_admin)):
    """Groups of items that read as the same thing to a customs officer."""
    threshold = SENSITIVITY.get((sensitivity or "normal").lower(), SENSITIVITY["normal"])
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "items": 1, "packing_units": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items = s.get("items") or []
    units_by_id = {u["id"]: u for u in (s.get("packing_units") or []) if u.get("id")}
    groups = [_group_payload(c, units_by_id) for c in _cluster(items, threshold)]
    groups.sort(key=lambda g: (-g["total_value"], g["label"].lower()))
    return {
        "sensitivity": (sensitivity or "normal").lower(),
        "threshold": threshold,
        "items_scanned": len(items),
        "groups": groups,
        "duplicate_lines": sum(len(g["items"]) - 1 for g in groups),
        "across_boxes": sum(1 for g in groups if not g["same_box"]),
    }


@router.post("/shipments/{shipment_id}/items/consolidate")
async def consolidate_items(shipment_id: str, data: dict,
                            current_user: dict = Depends(require_admin)):
    """Body: {keep_id, merge_ids: [...], mode, name?}

    mode:
      • `combine`         — one line, quantities and values added up, box
                            numbers recorded as "Boxes 24 & 25"
      • `combine_same_box`— same, but only the rows sharing the keeper's box
      • `delete_repeats`  — drop the repeated rows, keeper untouched
    """
    keep_id = (data.get("keep_id") or "").strip()
    merge_ids = [i for i in (data.get("merge_ids") or []) if i and i != keep_id]
    mode = (data.get("mode") or "combine").lower()
    if mode not in {"combine", "combine_same_box", "delete_repeats"}:
        raise HTTPException(status_code=400, detail="mode must be combine, combine_same_box or delete_repeats")
    if not keep_id or not merge_ids:
        raise HTTPException(status_code=400, detail="Pick the line to keep and at least one duplicate")

    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "items": 1, "packing_units": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items = s.get("items") or []
    units_by_id = {u["id"]: u for u in (s.get("packing_units") or []) if u.get("id")}
    keeper = next((i for i in items if i.get("id") == keep_id), None)
    if not keeper:
        raise HTTPException(status_code=404, detail="The line you chose to keep no longer exists")
    merging = [i for i in items if i.get("id") in merge_ids]
    if mode == "combine_same_box":
        merging = [i for i in merging if (i.get("packing_unit_id") or "") == (keeper.get("packing_unit_id") or "")]
    if not merging:
        raise HTTPException(status_code=400, detail="Nothing to merge in that box")

    removed_ids = [i["id"] for i in merging]
    if mode == "delete_repeats":
        await db.shipments.update_one({"id": shipment_id}, {"$pull": {"items": {"id": {"$in": removed_ids}}}})
        await _audit(current_user["id"], "delete", "shipment_items", shipment_id,
                     {"removed": removed_ids, "kept": keep_id, "reason": "repeated customs line"})
        return {"mode": mode, "removed": len(removed_ids), "keep_id": keep_id}

    everyone = [keeper] + merging
    total_qty = sum(int(i.get("qty_acquired") or 0) for i in everyone)
    total_value = round(sum(_line_value(i) for i in everyone), 2)
    total_weight = sum(float(i.get("weight_kg") or 0) * int(i.get("qty_acquired") or 0) for i in everyone)
    boxes = [_box_of(i, units_by_id) for i in everyone]
    label = box_label(boxes)
    breakdown = [{
        "item_id": i["id"], "name": i.get("name"), "qty": int(i.get("qty_acquired") or 0),
        "value_usd": float(i.get("value_usd") or 0),
        "box_name": _box_of(i, units_by_id)["name"], "box_no": _box_of(i, units_by_id)["no"],
    } for i in merging]

    set_ops = {
        "items.$.name": (data.get("name") or keeper.get("name") or "")[:160],
        "items.$.qty_acquired": total_qty,
        "items.$.qty_needed": max(total_qty, sum(int(i.get("qty_needed") or 0) for i in everyone)),
        # Unit value re-derived so the customs line total is exactly what the
        # separate rows added up to.
        "items.$.value_usd": round(total_value / total_qty, 2) if total_qty else 0,
        "items.$.weight_kg": round(total_weight / total_qty, 3) if total_qty else 0,
        "items.$.consolidated": True,
        "items.$.consolidated_at": datetime.now(timezone.utc).isoformat(),
        "items.$.box_label": label,
        "items.$.combined_boxes": [b for b in boxes if b.get("id") or b.get("name")],
        # Full original rows so this can be undone.
        "items.$.consolidated_items": (keeper.get("consolidated_items") or []) + merging,
        "items.$.consolidated_from": (keeper.get("consolidated_from") or []) + breakdown,
        "items.$.updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.shipments.update_one({"id": shipment_id, "items.id": keep_id}, {"$set": set_ops})
    await db.shipments.update_one({"id": shipment_id}, {"$pull": {"items": {"id": {"$in": removed_ids}}}})
    await _audit(current_user["id"], "update", "shipment_items", shipment_id,
                 {"consolidated_into": keep_id, "merged": removed_ids,
                  "qty": total_qty, "value_usd": total_value, "boxes": label})
    return {
        "mode": mode, "keep_id": keep_id, "merged": len(removed_ids),
        "qty_acquired": total_qty, "line_value": total_value, "box_label": label,
    }


@router.post("/shipments/{shipment_id}/items/{item_id}/undo-consolidate")
async def undo_consolidate(shipment_id: str, item_id: str,
                           current_user: dict = Depends(require_admin)):
    """Put a consolidated line back the way the packers entered it."""
    s = await db.shipments.find_one({"id": shipment_id, "items.id": item_id},
                                    {"_id": 0, "items.$": 1})
    item = ((s or {}).get("items") or [None])[0]
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    originals = item.get("consolidated_items") or []
    if not originals:
        raise HTTPException(status_code=400, detail="This line was not combined here, so there is nothing to undo")
    keep_qty = int(item.get("qty_acquired") or 0) - sum(int(o.get("qty_acquired") or 0) for o in originals)
    restore_keeper = {
        "items.$.qty_acquired": max(0, keep_qty),
        "items.$.consolidated": False,
        "items.$.consolidated_items": [],
        "items.$.consolidated_from": [],
        "items.$.combined_boxes": [],
        "items.$.box_label": "",
        "items.$.updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.shipments.update_one({"id": shipment_id, "items.id": item_id}, {"$set": restore_keeper})
    await db.shipments.update_one({"id": shipment_id}, {"$push": {"items": {"$each": originals}}})
    await _audit(current_user["id"], "update", "shipment_items", shipment_id,
                 {"undo_consolidate": item_id, "restored": [o.get("id") for o in originals]})
    return {"restored": len(originals), "item_id": item_id}
