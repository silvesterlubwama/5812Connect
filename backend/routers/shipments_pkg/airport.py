"""Airport-mode: passengers + suitcases, waybill HTML, AI tracking summaries."""
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Optional
from datetime import datetime, timezone
import uuid
import os as _os
from deps import db, logger, _audit, require_admin
from ._common import _waybill_html, PACKING_PRESETS

router = APIRouter(prefix="/api", tags=["shipments"])

@router.get("/shipments/{shipment_id}/waybill")
async def waybill_html(shipment_id: str, current_user: dict = Depends(require_admin)):
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return Response(content=_waybill_html(s), media_type="text/html")



@router.post("/shipments/{shipment_id}/passengers")
async def add_passenger(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Body: {name, passport_no?, ticket_no?, flight_no?, suitcase_allowance_kg?, suitcase_count_allowance?}"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Passenger name required")
    passenger = {
        "id": f"pax_{uuid.uuid4().hex[:8]}",
        "name": name[:120],
        "passport_no": (data.get("passport_no") or "")[:40],
        "ticket_no": (data.get("ticket_no") or "")[:40],
        "flight_no": (data.get("flight_no") or "")[:20],
        "suitcase_allowance_kg": float(data.get("suitcase_allowance_kg") or 23),
        "suitcase_count_allowance": int(data.get("suitcase_count_allowance") or 2),
        "notes": (data.get("notes") or "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    r = await db.shipments.update_one({"id": shipment_id}, {"$push": {"passengers": passenger}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return passenger


@router.put("/shipments/{shipment_id}/passengers/{passenger_id}")
async def update_passenger(shipment_id: str, passenger_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "passport_no", "ticket_no", "flight_no",
               "suitcase_allowance_kg", "suitcase_count_allowance", "notes"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k == "suitcase_allowance_kg":
            set_ops[f"passengers.$.{k}"] = max(0, float(v or 0))
        elif k == "suitcase_count_allowance":
            set_ops[f"passengers.$.{k}"] = max(0, int(v or 0))
        else:
            set_ops[f"passengers.$.{k}"] = (v or "")[:300 if k == "notes" else 120]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id, "passengers.id": passenger_id}, {"$set": set_ops}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Passenger not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/passengers/{passenger_id}")
async def delete_passenger(shipment_id: str, passenger_id: str, current_user: dict = Depends(require_admin)):
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"items.$[itm].passenger_id": None, "items.$[itm].suitcase_id": None}},
        array_filters=[{"itm.passenger_id": passenger_id}],
    )
    # Remove any suitcases belonging to this passenger too
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$pull": {"suitcases": {"passenger_id": passenger_id}}},
    )
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"passengers": {"id": passenger_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Passenger not found")
    return {"deleted": True}


@router.post("/shipments/{shipment_id}/suitcases")
async def add_suitcase(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Body: {passenger_id, type?, preset_key?, name?, weight_kg?, weight_limit_kg?, tracking_no?}"""
    pid = data.get("passenger_id")
    if not pid:
        raise HTTPException(status_code=400, detail="passenger_id required")
    utype = (data.get("type") or "suitcase").lower()
    if utype not in {"suitcase", "carry_on", "duffel", "tote"}:
        utype = "suitcase"
    preset = PACKING_PRESETS.get(data.get("preset_key") or "", {})
    suitcase = {
        "id": f"sc_{uuid.uuid4().hex[:8]}",
        "passenger_id": pid,
        "type": utype,
        "name": (data.get("name") or preset.get("label") or utype.title())[:80],
        "preset_key": data.get("preset_key") or "",
        "L_cm": float(data.get("L_cm") or preset.get("L_cm") or 66),
        "W_cm": float(data.get("W_cm") or preset.get("W_cm") or 46),
        "H_cm": float(data.get("H_cm") or preset.get("H_cm") or 27),
        "weight_kg": max(0, float(data.get("weight_kg") or 0)),
        "weight_limit_kg": max(0, float(data.get("weight_limit_kg") or preset.get("cap_kg") or 23)),
        "tracking_no": (data.get("tracking_no") or "")[:40],  # bag tag number after check-in
        "color": (data.get("color") or "#334155")[:20],
        "notes": (data.get("notes") or "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    r = await db.shipments.update_one({"id": shipment_id}, {"$push": {"suitcases": suitcase}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return suitcase


@router.put("/shipments/{shipment_id}/suitcases/{suitcase_id}")
async def update_suitcase(shipment_id: str, suitcase_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "type", "L_cm", "W_cm", "H_cm", "weight_kg", "weight_limit_kg",
               "tracking_no", "color", "notes", "passenger_id"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k in ("L_cm", "W_cm", "H_cm", "weight_kg", "weight_limit_kg"):
            set_ops[f"suitcases.$.{k}"] = max(0, float(v or 0))
        else:
            set_ops[f"suitcases.$.{k}"] = (v or "")[:300 if k == "notes" else 120]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id, "suitcases.id": suitcase_id}, {"$set": set_ops}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Suitcase not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/suitcases/{suitcase_id}")
async def delete_suitcase(shipment_id: str, suitcase_id: str, current_user: dict = Depends(require_admin)):
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"items.$[itm].suitcase_id": None}},
        array_filters=[{"itm.suitcase_id": suitcase_id}],
    )
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"suitcases": {"id": suitcase_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Suitcase not found")
    return {"deleted": True}


@router.post("/shipments/{shipment_id}/ai-tracking")
async def ai_track_shipment(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Ask Gemini to interpret the waybill / flight numbers and generate a
    plain-language tracking summary. Returns {summary, hint, tracking_urls: []}.

    We DO NOT hit paid carrier APIs (Maersk, Emirates SkyCargo, etc.) because
    those all require B2B contracts. Instead we generate the correct public
    tracking URLs and a Gemini-crafted natural-language status hint from what's
    known so the operator can click through in one place."""
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI tracking unavailable (no LLM key configured)")
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    mode = s.get("mode") or "container"
    waybill = (s.get("waybill_no") or "").strip()
    flight = (s.get("flight_no") or "").strip()
    carrier = (s.get("carrier_name") or "").strip()
    dest = (s.get("dest_country") or "").strip()
    dep = (s.get("departure_date") or s.get("target_ship_date") or "").strip()
    arr = (s.get("arrival_date") or "").strip()

    # Build a set of tracking URLs the operator can click.
    tracking_urls = []
    if s.get("tracking_url"):
        tracking_urls.append({"label": "Direct tracking link", "url": s["tracking_url"]})
    if waybill:
        tracking_urls.append({"label": f"Google search: {waybill}",
                              "url": f"https://www.google.com/search?q={waybill}+tracking"})
    if flight:
        tracking_urls.append({"label": f"FlightAware: {flight}",
                              "url": f"https://flightaware.com/live/flight/{flight.replace(' ', '')}"})
    # Passenger + suitcase tracking numbers
    for sc in (s.get("suitcases") or []):
        if sc.get("tracking_no"):
            tracking_urls.append({
                "label": f"Bag tag {sc['tracking_no']} (Google)",
                "url": f"https://www.google.com/search?q={sc['tracking_no']}+baggage+tracking",
            })

    # Gemini natural-language status estimate
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        return {"summary": "AI client unavailable — use the direct tracking links below.",
                "hint": str(e), "tracking_urls": tracking_urls}

    context = (
        f"Mode: {mode}\n"
        f"Carrier: {carrier or '(unknown)'}\n"
        f"Waybill/BOL: {waybill or '(none)'}\n"
        f"Flight #: {flight or '(none)'}\n"
        f"Destination: {dest or '(unknown)'}\n"
        f"Departure planned: {dep or '(unknown)'}\n"
        f"Arrival planned: {arr or '(unknown)'}\n"
        f"Passengers: {len(s.get('passengers') or [])}\n"
        f"Suitcases with bag-tag: "
        f"{sum(1 for x in (s.get('suitcases') or []) if x.get('tracking_no'))}\n"
    )
    prompt = (
        "You are a logistics tracking assistant. Given the shipment facts above, "
        "produce a SHORT (max 90 words) plain-English status estimate for the operator: "
        "what stage the shipment is likely at based on the dates provided, what the "
        "operator should check next, and any known typical transit times to the "
        "destination country. If no meaningful data is available, say so plainly. "
        "No markdown fences — plain prose only."
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"ship_track_{uuid.uuid4().hex[:8]}",
            system_message=prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(text=context))
        summary = (raw or "").strip()[:600]
    except Exception as ex:
        logger.warning(f"AI tracking Gemini call failed: {ex}")
        summary = "AI status estimate unavailable right now — use the tracking links below."

    return {
        "summary": summary,
        "hint": "AI estimates are heuristic; use the tracking URLs to confirm.",
        "tracking_urls": tracking_urls,
        "waybill_no": waybill,
        "flight_no": flight,
        "carrier": carrier,
    }

