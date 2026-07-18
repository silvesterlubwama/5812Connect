"""Airport-mode: passengers + suitcases, waybill HTML, AI tracking summaries."""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import os as _os
import base64
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
        "tickets": [],  # iter226 — multi-leg tickets
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



# ============================================================
# iter226 — FLIGHTS (multi-airline / multi-leg per shipment)
# ============================================================

@router.post("/shipments/{shipment_id}/flights")
async def add_flight(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Body: {airline?, flight_no, origin?, destination?, departure_at?, arrival_at?,
    booking_url?, notes?}. Multiple flights allowed per shipment (connections, multiple airlines)."""
    fno = (data.get("flight_no") or "").strip()
    if not fno:
        raise HTTPException(status_code=400, detail="flight_no required")
    flight = {
        "id": f"flt_{uuid.uuid4().hex[:8]}",
        "airline": (data.get("airline") or "")[:60],
        "flight_no": fno[:20],
        "origin": (data.get("origin") or "")[:120],
        "destination": (data.get("destination") or "")[:120],
        "departure_at": (data.get("departure_at") or "")[:40],
        "arrival_at": (data.get("arrival_at") or "")[:40],
        "booking_url": (data.get("booking_url") or "")[:500],
        "status": (data.get("status") or "scheduled")[:20],  # scheduled | boarding | departed | in_air | landed | cancelled | delayed
        "last_ai_check_at": None,
        "ai_summary": "",
        "notes": (data.get("notes") or "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    r = await db.shipments.update_one({"id": shipment_id}, {"$push": {"flights": flight}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    await _audit(current_user["id"], "add", "flight", flight["id"], {"shipment": shipment_id, "flight_no": fno})
    return flight


@router.put("/shipments/{shipment_id}/flights/{flight_id}")
async def update_flight(shipment_id: str, flight_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"airline", "flight_no", "origin", "destination", "departure_at",
               "arrival_at", "booking_url", "status", "notes", "ai_summary"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        set_ops[f"flights.$.{k}"] = (v if isinstance(v, str) else str(v or ""))[:500]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id, "flights.id": flight_id}, {"$set": set_ops}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Flight not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/flights/{flight_id}")
async def delete_flight(shipment_id: str, flight_id: str, current_user: dict = Depends(require_admin)):
    # Detach any tickets pointing to this flight
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"passengers.$[pax].tickets.$[t].flight_id": None}},
        array_filters=[{"pax.tickets": {"$exists": True}}, {"t.flight_id": flight_id}],
    )
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"flights": {"id": flight_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Flight not found")
    return {"deleted": True}


# ============================================================
# iter226 — TICKETS (nested inside passengers)
# ============================================================

@router.post("/shipments/{shipment_id}/passengers/{passenger_id}/tickets")
async def add_ticket(shipment_id: str, passenger_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Body: {flight_id?, ticket_no, pnr?, seat?, notes?}. A passenger can hold
    multiple tickets — one per flight leg for connections."""
    tno = (data.get("ticket_no") or "").strip()
    if not tno:
        raise HTTPException(status_code=400, detail="ticket_no required")
    ticket = {
        "id": f"tkt_{uuid.uuid4().hex[:8]}",
        "flight_id": data.get("flight_id") or None,
        "ticket_no": tno[:40],
        "pnr": (data.get("pnr") or "")[:20],
        "seat": (data.get("seat") or "")[:10],
        "notes": (data.get("notes") or "")[:300],
        "checked_in": False,
        "checked_in_at": None,
        "boarding_pass_url": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    r = await db.shipments.update_one(
        {"id": shipment_id, "passengers.id": passenger_id},
        {"$push": {"passengers.$.tickets": ticket}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Passenger not found")
    return ticket


@router.put("/shipments/{shipment_id}/passengers/{passenger_id}/tickets/{ticket_id}")
async def update_ticket(shipment_id: str, passenger_id: str, ticket_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"flight_id", "ticket_no", "pnr", "seat", "notes"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        set_ops[f"passengers.$[pax].tickets.$[tkt].{k}"] = v if v is None else str(v)[:300]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": set_ops},
        array_filters=[{"pax.id": passenger_id}, {"tkt.id": ticket_id}],
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/passengers/{passenger_id}/tickets/{ticket_id}")
async def delete_ticket(shipment_id: str, passenger_id: str, ticket_id: str, current_user: dict = Depends(require_admin)):
    r = await db.shipments.update_one(
        {"id": shipment_id, "passengers.id": passenger_id},
        {"$pull": {"passengers.$.tickets": {"id": ticket_id}}},
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"deleted": True}


@router.post("/shipments/{shipment_id}/passengers/{passenger_id}/tickets/{ticket_id}/check-in")
async def check_in_ticket(
    shipment_id: str,
    passenger_id: str,
    ticket_id: str,
    boarding_pass: Optional[UploadFile] = File(default=None),
    checked_in: str = Form(default="true"),
    seat: str = Form(default=""),
    current_user: dict = Depends(require_admin),
):
    """Self-mark check-in with optional boarding-pass photo/PDF upload.
    The file is stored as a data URL on the ticket (small enough to inline for
    passport-size boarding passes). For larger files consider object storage."""
    now = datetime.now(timezone.utc).isoformat()
    bp_data_url = ""
    if boarding_pass is not None:
        raw = await boarding_pass.read()
        if len(raw) > 2_500_000:
            raise HTTPException(status_code=413, detail="Boarding pass too large (max 2.5 MB)")
        mime = boarding_pass.content_type or "application/octet-stream"
        b64 = base64.b64encode(raw).decode("ascii")
        bp_data_url = f"data:{mime};base64,{b64}"
    is_in = str(checked_in).lower() in ("true", "1", "yes")
    set_ops = {
        "passengers.$[pax].tickets.$[tkt].checked_in": is_in,
        "passengers.$[pax].tickets.$[tkt].checked_in_at": now if is_in else None,
        "passengers.$[pax].tickets.$[tkt].checked_in_by": current_user.get("name", ""),
    }
    if bp_data_url:
        set_ops["passengers.$[pax].tickets.$[tkt].boarding_pass_url"] = bp_data_url
    if seat:
        set_ops["passengers.$[pax].tickets.$[tkt].seat"] = seat[:10]
    r = await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": set_ops},
        array_filters=[{"pax.id": passenger_id}, {"tkt.id": ticket_id}],
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await _audit(current_user["id"], "check-in", "ticket", ticket_id, {"passenger": passenger_id, "in": is_in})
    return {"checked_in": is_in, "checked_in_at": now if is_in else None, "has_boarding_pass": bool(bp_data_url)}


# ============================================================
# iter226 — AI FLIGHT SEARCH (Gemini with Google Search grounding)
# ============================================================

@router.post("/shipments/{shipment_id}/ai-flight-search")
async def ai_flight_search(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """AI-powered flight search using Gemini 3 Flash with Google Search grounding.
    Body: {origin, destination, date, passengers?, cabin?}
    Returns a structured list of flight suggestions with airline, flight #, timings,
    estimated price, and booking URLs. Grounded on live web search — data recency
    depends on Google's crawl."""
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI unavailable (no LLM key configured)")
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "name": 1, "dest_country": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    origin = (data.get("origin") or "").strip()
    dest = (data.get("destination") or s.get("dest_country") or "").strip()
    date = (data.get("date") or "").strip()
    if not (origin and dest and date):
        raise HTTPException(status_code=400, detail="origin, destination, date all required")
    pax = int(data.get("passengers") or 1)
    cabin = (data.get("cabin") or "economy").strip()

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as ex:
        raise HTTPException(status_code=503, detail=f"AI client not installed: {ex}")

    system_prompt = (
        "You are a flight-search assistant. Given origin, destination, date, "
        "passengers and cabin, search current online flight-booking sources "
        "(Google Flights, Skyscanner, Kayak, airline sites) and return the top "
        "6 best options. For each: airline, flight_no (or code if unique), "
        "departure time, arrival time, duration, stops, cabin, estimated price "
        "(USD, single-adult), and a direct booking URL if you can identify one. "
        "Also add a `caveat` field warning that prices/times can change and to "
        "verify on the airline site before booking. "
        "Output STRICT JSON only: "
        '{"query":{...},"flights":[{"airline":"","flight_no":"","depart":"","arrive":"","duration":"","stops":0,"cabin":"","price_usd":0,"booking_url":"","caveat":""},...],"search_note":""}. '
        "No markdown fences."
    )
    user_msg = (
        f"Origin: {origin}\nDestination: {dest}\nDate: {date}\n"
        f"Passengers: {pax}\nCabin: {cabin}\n"
        "Search live sources and return the JSON now."
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"flight_search_{uuid.uuid4().hex[:8]}",
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(text=user_msg))
    except Exception as ex:
        logger.warning(f"AI flight search Gemini call failed: {ex}")
        raise HTTPException(status_code=503, detail=f"AI search failed: {ex}")

    # Strip markdown fences if the model included them despite instructions
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    import json as _json
    try:
        parsed = _json.loads(text)
    except Exception:
        return {"flights": [], "raw": text[:2000], "error": "AI did not return valid JSON"}
    parsed["searched_at"] = datetime.now(timezone.utc).isoformat()
    parsed["searched_by"] = current_user.get("name", "")
    return parsed


# ============================================================
# iter226 — Per-flight AI status refresh (auto-crawl every 15 min
# when shipment status = shipped/departed, wired from server.py)
# ============================================================

async def _refresh_flight_status_for(shipment: dict) -> int:
    """Refresh each flight's ai_summary + status via Gemini. Returns count of
    flights updated. Non-fatal — logs and continues on individual failures."""
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        return 0
    flights = shipment.get("flights") or []
    if not flights:
        return 0
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception:
        return 0
    updated = 0
    for f in flights:
        fno = (f.get("flight_no") or "").strip()
        if not fno:
            continue
        prompt = (
            "You are a flight status assistant. Search live sources (FlightAware, "
            "FlightRadar24, airline site) for the current status of this flight and "
            "reply with STRICT JSON: {\"status\":\"scheduled|boarding|departed|in_air|landed|cancelled|delayed\",\"summary\":\"<max 60 words>\"}. "
            "No markdown fences."
        )
        user_msg = (
            f"Airline: {f.get('airline', '')}\nFlight: {fno}\n"
            f"Origin: {f.get('origin', '')}\nDestination: {f.get('destination', '')}\n"
            f"Scheduled departure: {f.get('departure_at', '')}\n"
            "Return JSON now."
        )
        try:
            chat = LlmChat(
                api_key=api_key,
                session_id=f"flt_refresh_{f['id']}",
                system_message=prompt,
            ).with_model("gemini", "gemini-3-flash-preview")
            raw = await chat.send_message(UserMessage(text=user_msg))
            text = (raw or "").strip().strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
            import json as _json
            parsed = _json.loads(text)
            await db.shipments.update_one(
                {"id": shipment["id"], "flights.id": f["id"]},
                {"$set": {
                    "flights.$.status": (parsed.get("status") or f.get("status") or "scheduled")[:20],
                    "flights.$.ai_summary": (parsed.get("summary") or "")[:400],
                    "flights.$.last_ai_check_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            updated += 1
        except Exception as ex:
            logger.warning(f"Flight status refresh failed for {fno}: {ex}")
            continue
    return updated


@router.post("/shipments/{shipment_id}/refresh-flight-status")
async def manual_refresh_flight_status(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Manually trigger the flight-status refresh (same code path as the
    15-min background loop)."""
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    n = await _refresh_flight_status_for(s)
    return {"refreshed": n}


