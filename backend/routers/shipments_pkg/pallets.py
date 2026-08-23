"""Pallets, packing units, AI packing scenarios + suggestions, QR label PDFs."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime, timezone
import uuid
import re
import json
import os as _os
from deps import db, logger, _audit, require_admin
from ._common import (
    _normalise_pallet,
    CONTAINER_40FT_HC,
    PACKING_PRESETS,
    VALID_UNIT_TYPES,
    VALID_MODES,
)

router = APIRouter(prefix="/api", tags=["shipments"])

@router.post("/shipments/{shipment_id}/pallets")
async def add_pallet(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    pallet = _normalise_pallet(data)
    r = await db.shipments.update_one({"id": shipment_id}, {"$push": {"pallets": pallet}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return pallet


@router.put("/shipments/{shipment_id}/pallets/{pallet_id}")
async def update_pallet(shipment_id: str, pallet_id: str, data: dict, current_user: dict = Depends(require_admin)):
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
        {"id": shipment_id, "pallets.id": pallet_id}, {"$set": set_ops}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pallet not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/pallets/{pallet_id}")
async def delete_pallet(shipment_id: str, pallet_id: str, current_user: dict = Depends(require_admin)):
    # Also un-assign any items pointing at this pallet so they fall back to "unassigned"
    await db.shipments.update_one(
        {"id": shipment_id, "items.pallet_id": pallet_id},
        {"$set": {"items.$[el].pallet_id": None}},
        array_filters=[{"el.pallet_id": pallet_id}],
    )
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"pallets": {"id": pallet_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pallet not found")
    return {"deleted": True}



@router.post("/shipments/{shipment_id}/ai-packing")
async def generate_packing_scenario(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Generates a text packing scenario via Gemini-3-flash. Looks at the
    acquired items + pallets + 40' container dimensions and outputs a step-by-
    step plan: which pallets go where, total weight vs the cap, recommended
    grouping of remaining loose items, and any over-cap warnings.

    Persisted on the shipment doc so the FE can render it without re-spending
    tokens on every page load. Caller re-runs after material item changes.
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    import os as _os
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI packing unavailable (no LLM key configured)")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI client unavailable: {e}")

    acquired = [i for i in (s.get("items") or []) if int(i.get("qty_acquired") or 0) > 0]
    total_weight = sum(float(i.get("weight_kg") or 0) * int(i.get("qty_acquired") or 0) for i in acquired)
    cap = float(s.get("max_payload_kg") or 26000)
    over_cap = total_weight - cap

    # Compact, structured prompt so the model has everything it needs without
    # token-bloat from raw donation history.
    payload = {
        "shipment_name": s.get("name"),
        "dest_country": s.get("dest_country"),
        "container_internal_cm": s.get("container_dims_cm") or CONTAINER_40FT_HC,
        "max_payload_kg": cap,
        "current_total_weight_kg": round(total_weight, 1),
        "over_cap_kg": round(over_cap, 1),
        "pallets": [{"id": p["id"], "label": p["label"]} for p in (s.get("pallets") or [])],
        "items_acquired": [
            {
                "id": i["id"], "name": i["name"], "category": i.get("category", ""),
                "qty_acquired": i.get("qty_acquired", 0),
                "weight_kg_per_unit": i.get("weight_kg", 0),
                "dims_cm": i.get("dims_cm") or {},
                "pallet_id": i.get("pallet_id"),
                "priority": i.get("priority", "normal"),
                "value_usd": i.get("value_usd", 0),
            }
            for i in acquired
        ][:200],  # cap to keep prompt under Gemini's window
    }
    system = (
        "You are a shipping/logistics assistant for a 58:12 Global container shipment to Uganda. "
        "Given the JSON state below, output a CONCISE packing scenario in Markdown with these sections:\n"
        "## Weight summary\n"
        "  • State current acquired weight vs the 40' container payload cap; flag any over-cap by ≥500 kg.\n"
        "## Volume reality check\n"
        "  • Estimate volume usage given the 40' HC internal ~76 m³. Note any items missing dimensions.\n"
        "## Pallet plan\n"
        "  • For each existing pallet, list which items belong on it (group by category + priority).\n"
        "  • Suggest names for any new pallets needed.\n"
        "  • Place heavy/dense pallets at the bottom-front of the container; lighter ones on top.\n"
        "## Loading order\n"
        "  • Numbered 1..N — back-of-container first, door-side last.\n"
        "## Risks & recommendations\n"
        "  • Call out fragility (electronics, glass), cold-chain (medical), and bulk-density issues.\n"
        "Keep it under 700 words. No prose preamble; jump straight into the headings."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"shipment_pack_{shipment_id}_{uuid.uuid4().hex[:6]}",
        system_message=system,
    ).with_model("gemini", "gemini-3-flash-preview")
    import json as _json
    text = await chat.send_message(UserMessage(text=_json.dumps(payload, default=str)))
    ai_text = (text or "").strip()
    await db.shipments.update_one({"id": shipment_id}, {"$set": {
        "ai_packing_text": ai_text,
        "ai_packing_generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_packing_total_weight_kg": round(total_weight, 1),
    }})
    return {
        "text": ai_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_weight_kg": round(total_weight, 1),
        "over_cap_kg": round(over_cap, 1),
    }

@router.get("/shipments/presets/packing-units")
async def get_packing_presets(current_user: dict = Depends(require_admin)):
    return PACKING_PRESETS


@router.post("/shipments/{shipment_id}/packing-units")
async def add_packing_unit(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Create a physical packing unit (pallet / box / tote / crate) inside a shipment.
    Body: {type, name?, preset_key?, L_cm?, W_cm?, H_cm?, weight_capacity_kg?, color?, parent_id?}
    If `preset_key` is given, dims/capacity default from PACKING_PRESETS."""
    utype = (data.get("type") or "").lower()
    if utype not in VALID_UNIT_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(VALID_UNIT_TYPES)}")
    preset = PACKING_PRESETS.get(data.get("preset_key") or "", {})
    unit = {
        "id": f"pku_{uuid.uuid4().hex[:8]}",
        "type": utype,
        "name": (data.get("name") or preset.get("label") or utype.title())[:80],
        "preset_key": data.get("preset_key") or "",
        "L_cm": float(data.get("L_cm") or preset.get("L_cm") or 60),
        "W_cm": float(data.get("W_cm") or preset.get("W_cm") or 40),
        "H_cm": float(data.get("H_cm") or preset.get("H_cm") or 30),
        "weight_capacity_kg": float(data.get("weight_capacity_kg") or preset.get("cap_kg") or 20),
        "color": (data.get("color") or "#94a3b8")[:20],
        "parent_id": data.get("parent_id") or None,  # for stacking
        "floor_x_cm": float(data.get("floor_x_cm") or 0),  # position on container floor
        "floor_y_cm": float(data.get("floor_y_cm") or 0),
        "notes": (data.get("notes") or "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    r = await db.shipments.update_one({"id": shipment_id}, {"$push": {"packing_units": unit}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return unit


@router.put("/shipments/{shipment_id}/packing-units/{unit_id}")
async def update_packing_unit(shipment_id: str, unit_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "L_cm", "W_cm", "H_cm", "weight_capacity_kg", "color",
               "parent_id", "floor_x_cm", "floor_y_cm", "notes"}
    # Load shipment to clamp floor coords to the container's floor
    # (drag-drop from the UI would otherwise persist off-container positions).
    s = await db.shipments.find_one(
        {"id": shipment_id, "packing_units.id": unit_id},
        {"_id": 0, "container_dims_cm": 1, "packing_units.$": 1},
    )
    if not s:
        raise HTTPException(status_code=404, detail="Packing unit not found")
    dims = s.get("container_dims_cm") or {}
    max_x = float(dims.get("length_cm") or 1203)
    max_y = float(dims.get("width_cm") or 235)
    current_unit = (s.get("packing_units") or [{}])[0]
    unit_L = float(data.get("L_cm") or current_unit.get("L_cm") or 0)
    unit_W = float(data.get("W_cm") or current_unit.get("W_cm") or 0)
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k == "floor_x_cm":
            set_ops[f"packing_units.$.{k}"] = max(0.0, min(max(0.0, max_x - unit_L), float(v or 0)))
        elif k == "floor_y_cm":
            set_ops[f"packing_units.$.{k}"] = max(0.0, min(max(0.0, max_y - unit_W), float(v or 0)))
        elif k in ("L_cm", "W_cm", "H_cm", "weight_capacity_kg"):
            set_ops[f"packing_units.$.{k}"] = max(0, float(v or 0))
        elif k == "parent_id":
            set_ops[f"packing_units.$.{k}"] = v or None
        else:
            set_ops[f"packing_units.$.{k}"] = (v or "")[:300 if k == "notes" else 80]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id, "packing_units.id": unit_id}, {"$set": set_ops}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Packing unit not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/packing-units/{unit_id}")
async def delete_packing_unit(shipment_id: str, unit_id: str, current_user: dict = Depends(require_admin)):
    """Delete a packing unit.  Items in it move back to unassigned;
    child units (stacked on top) have their parent_id cleared."""
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"items.$[itm].packing_unit_id": None}},
        array_filters=[{"itm.packing_unit_id": unit_id}],
    )
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"packing_units.$[u].parent_id": None}},
        array_filters=[{"u.parent_id": unit_id}],
    )
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"packing_units": {"id": unit_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Packing unit not found")
    return {"deleted": True}

@router.get("/shipments/{shipment_id}/labels.pdf")
async def shipment_labels_pdf(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Printable per-packing-unit labels PDF (10 labels per A4 sheet).
    Each label carries a QR code encoding the unit's URL for warehouse check-in
    scanning, plus type/name/dims/weight-cap."""
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    units = s.get("packing_units") or []
    if not units:
        raise HTTPException(status_code=400, detail="No packing units to label")
    try:
        import qrcode
        import io as _io
        import base64 as _b64
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"QR library unavailable: {e}")
    base_url = _os.environ.get("PUBLIC_APP_URL", "").rstrip("/") or ""
    label_rows = ""
    for u in units:
        qr_url = f"{base_url}/public/packing-unit/{shipment_id}/{u['id']}" if base_url else f"pku:{shipment_id}:{u['id']}"
        img = qrcode.make(qr_url)
        buf = _io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        b64 = _b64.b64encode(buf.read()).decode()
        label_rows += (
            f"<div class='label'>"
            f"  <img src='data:image/png;base64,{b64}' />"
            f"  <div class='meta'>"
            f"    <div class='type'>{u['type'].upper()}</div>"
            f"    <div class='name'>{u.get('name','')[:40]}</div>"
            f"    <div class='dims'>{u.get('L_cm')}×{u.get('W_cm')}×{u.get('H_cm')}cm · {u.get('weight_capacity_kg')}kg</div>"
            f"    <div class='sid'>{u['id']}</div>"
            f"  </div>"
            f"</div>"
        )
    html = f"""<html><head><style>
@page {{ size: A4; margin: 8mm; }}
body {{ font-family: -apple-system, Arial, sans-serif; margin: 0; }}
.grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 6mm; }}
.label {{ border: 2px dashed #0f172a; padding: 6mm; display: flex; gap: 5mm; align-items: center; page-break-inside: avoid; min-height: 45mm; }}
.label img {{ width: 35mm; height: 35mm; }}
.meta {{ font-size: 10px; line-height: 1.3; }}
.type {{ font-size: 14px; font-weight: 800; letter-spacing: 1px; color: #0f172a; }}
.name {{ font-size: 12px; font-weight: 600; margin-top: 2mm; }}
.dims {{ font-family: monospace; color: #64748b; margin-top: 1mm; }}
.sid {{ font-family: monospace; font-size: 8px; color: #94a3b8; margin-top: 2mm; }}
</style></head><body><div class='grid'>{label_rows}</div></body></html>"""
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    pdf = HTML(string=html).write_pdf()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", s.get("name") or "shipment")[:40]
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="labels_{safe}_{shipment_id[:8]}.pdf"'},
    )


@router.post("/shipments/{shipment_id}/ai-suggest-packing")
async def ai_suggest_packing(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Ask Gemini to look at the shipment's items + available packing presets
    and propose an optimal breakdown into pallets/boxes/totes.  Returns a JSON
    list of proposed units (not persisted — user must click "Apply")."""
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI unavailable (no LLM key configured)")
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items = s.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="No items to plan for")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI client unavailable: {e}")

    # Summarise items for the prompt (cap at 40 to control token cost)
    items_desc = []
    total_wt = 0.0
    for i in items[:40]:
        qty = int(i.get("qty_acquired") or 0)
        wt = float(i.get("weight_kg") or 0) * qty
        total_wt += wt
        items_desc.append(f"- {i.get('name','?')[:60]} ({qty} units, {wt:.1f}kg total, category={i.get('category','?')}, condition={i.get('condition','used')})")
    presets_desc = "\n".join([
        f"- {k}: {p['L_cm']}×{p['W_cm']}×{p['H_cm']}cm, cap {p['cap_kg']}kg ({p['label']})"
        for k, p in PACKING_PRESETS.items() if k not in ("suitcase_lg","suitcase_md","carry_on","duffel")
    ])
    sys_msg = (
        "You are a container packing expert.  Given a list of shipment items "
        "and a menu of packing presets, propose an efficient breakdown into "
        "pallets/boxes/totes.  Output STRICT JSON only:\n"
        '{"units": [{"type":"pallet|box|tote|crate", "preset_key":"...", '
        '"name":"...", "reason":"<=60 chars", "est_weight_kg": 0}], '
        '"strategy": "<=200 chars summary"}\n'
        "Rules:\n"
        "- Group heavy items on pallets; light bulky items in totes; fragile in boxes.\n"
        "- Do NOT exceed each preset's cap_kg.\n"
        "- Provide roughly ceil(total_weight/1500) pallets when items are dense.\n"
        "- Return between 3 and 20 units — no more.\n"
        "- No markdown fences.  JSON only."
    )
    user_text = (
        f"Total items lines: {len(items)} · Total weight (top 40): {total_wt:.1f}kg\n\n"
        f"Items sample:\n" + "\n".join(items_desc) + "\n\n"
        f"Packing presets available:\n{presets_desc}"
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"pack_suggest_{uuid.uuid4().hex[:8]}",
            system_message=sys_msg,
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = (await chat.send_message(UserMessage(text=user_text)) or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
        parsed = json.loads(raw)
    except Exception as ex:
        logger.warning(f"AI suggest-packing failed: {ex}")
        raise HTTPException(status_code=502, detail=f"AI returned invalid response: {str(ex)[:120]}")
    proposals = parsed.get("units") or []
    # Enrich proposals with actual dims from PACKING_PRESETS for the UI to preview
    for p in proposals:
        preset = PACKING_PRESETS.get(p.get("preset_key") or "", {})
        if preset:
            p["L_cm"] = preset["L_cm"]; p["W_cm"] = preset["W_cm"]
            p["H_cm"] = preset["H_cm"]; p["weight_capacity_kg"] = preset["cap_kg"]
    return {
        "strategy": (parsed.get("strategy") or "")[:250],
        "units": proposals[:20],
        "items_analysed": min(len(items), 40),
        "total_weight_kg": round(total_wt, 1),
    }


@router.post("/shipments/{shipment_id}/apply-suggested-packing")
async def apply_suggested_packing(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Persist the AI-proposed packing units (from ai-suggest-packing).  Lays them
    out on the container floor in a simple left-to-right grid."""
    units_data = (data or {}).get("units") or []
    if not units_data:
        raise HTTPException(status_code=400, detail="No units provided")
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "container_dims_cm": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    container_L = (s.get("container_dims_cm") or {}).get("length_cm", 1203)
    x, y, row_h = 0, 0, 0
    created_units = []
    for u in units_data:
        preset = PACKING_PRESETS.get(u.get("preset_key") or "", {})
        L = float(u.get("L_cm") or preset.get("L_cm") or 60)
        W = float(u.get("W_cm") or preset.get("W_cm") or 40)
        # Simple shelf-packing: wrap when we hit container length
        if x + L > container_L:
            x = 0; y += row_h; row_h = 0
        unit = {
            "id": f"pku_{uuid.uuid4().hex[:8]}",
            "type": (u.get("type") or "box").lower(),
            "name": (u.get("name") or preset.get("label") or "Unit")[:80],
            "preset_key": u.get("preset_key") or "",
            "L_cm": L, "W_cm": W, "H_cm": float(u.get("H_cm") or preset.get("H_cm") or 30),
            "weight_capacity_kg": float(u.get("weight_capacity_kg") or preset.get("cap_kg") or 20),
            "color": (u.get("color") or "#94a3b8"),
            "parent_id": None,
            "floor_x_cm": float(x), "floor_y_cm": float(y),
            "notes": (u.get("reason") or "")[:200],
            "ai_suggested": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        created_units.append(unit)
        x += L; row_h = max(row_h, W)
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$push": {"packing_units": {"$each": created_units}}},
    )
    return {"created": len(created_units), "units": created_units}
