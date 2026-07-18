"""Group Fare Alerts — daily AI-powered fare watch with email notifications.

An operator creates a fare alert for a route + date + target price. A background
loop runs once every 24h (with manual trigger available) that calls Gemini
Flight Search for each active alert; if the returned min price drops at or
below the target, we email the alert owner via Resend.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Optional
import os as _os
import uuid
import logging

from deps import db, get_current_user, require_admin

router = APIRouter(prefix="/api/fare-alerts", tags=["fare-alerts"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_fare_alerts(current_user: dict = Depends(get_current_user)):
    """List fare alerts I own (or all alerts if admin)."""
    q: dict = {}
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "system_admin"}:
        q["created_by"] = current_user["id"]
    out = []
    async for a in db.fare_alerts.find(q, {"_id": 0}).sort("created_at", -1):
        out.append(a)
    return out


@router.post("")
async def create_fare_alert(data: dict, current_user: dict = Depends(get_current_user)):
    """Body: {origin, destination, date, target_usd, cabin?, passengers?, alert_email?, name?}"""
    origin = (data.get("origin") or "").strip()
    dest = (data.get("destination") or "").strip()
    date = (data.get("date") or "").strip()
    if not (origin and dest and date):
        raise HTTPException(status_code=400, detail="origin, destination, date required")
    try:
        target = float(data.get("target_usd") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="target_usd must be a number")
    if target <= 0:
        raise HTTPException(status_code=400, detail="target_usd must be > 0")
    alert = {
        "id": f"fa_{uuid.uuid4().hex[:10]}",
        "name": (data.get("name") or f"{origin}→{dest} {date}")[:120],
        "origin": origin[:120],
        "destination": dest[:120],
        "date": date[:20],
        "target_usd": target,
        "cabin": (data.get("cabin") or "economy")[:20],
        "passengers": int(data.get("passengers") or 1),
        "alert_email": (data.get("alert_email") or current_user.get("email") or "")[:200],
        "active": True,
        "last_check_at": None,
        "last_min_price_usd": None,
        "last_result": None,
        "notify_count": 0,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fare_alerts.insert_one(alert)
    alert.pop("_id", None)
    return alert


@router.put("/{alert_id}")
async def update_fare_alert(alert_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    a = await db.fare_alerts.find_one({"id": alert_id})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.get("created_by") != current_user["id"] and (current_user.get("role") or "").lower() not in {"admin", "system_admin"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    allowed = {"name", "target_usd", "cabin", "passengers", "alert_email", "active"}
    set_ops = {k: v for k, v in data.items() if k in allowed}
    if not set_ops:
        return {"updated": False}
    if "target_usd" in set_ops:
        set_ops["target_usd"] = float(set_ops["target_usd"])
    await db.fare_alerts.update_one({"id": alert_id}, {"$set": set_ops})
    return {"updated": True}


@router.delete("/{alert_id}")
async def delete_fare_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    a = await db.fare_alerts.find_one({"id": alert_id})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.get("created_by") != current_user["id"] and (current_user.get("role") or "").lower() not in {"admin", "system_admin"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.fare_alerts.delete_one({"id": alert_id})
    return {"deleted": True}


# ============================================================
# Core check function — used by both manual trigger + daily loop
# ============================================================

async def _check_single_alert(alert: dict) -> dict:
    """Run one AI flight search for this alert, update the alert doc, and
    send an email if the min price is at/below target. Returns a summary dict."""
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        return {"ok": False, "error": "no LLM key"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as ex:
        return {"ok": False, "error": f"AI import failed: {ex}"}

    system_prompt = (
        "You are a flight fare-watch assistant. Given origin, destination, date, "
        "passengers and cabin, search live flight-booking sources (Google Flights, "
        "Skyscanner, Kayak, airline sites) and return STRICT JSON: "
        '{"min_price_usd":0,"currency":"USD","cheapest":{"airline":"","flight_no":"","depart":"","arrive":"","booking_url":""},"top_offers":[{"airline":"","flight_no":"","price_usd":0,"booking_url":""}],"note":""}. '
        "No markdown fences."
    )
    user_msg = (
        f"Origin: {alert['origin']}\nDestination: {alert['destination']}\n"
        f"Date: {alert['date']}\nPassengers: {alert.get('passengers', 1)}\n"
        f"Cabin: {alert.get('cabin', 'economy')}\n"
        "Return JSON with today's cheapest fare."
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"fare_alert_{alert['id']}",
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(text=user_msg))
    except Exception as ex:
        logger.warning(f"Fare-alert AI call failed for {alert['id']}: {ex}")
        return {"ok": False, "error": str(ex)}

    text = (raw or "").strip().strip("`")
    if text.startswith("json"):
        text = text[4:].strip()
    import json as _json
    try:
        parsed = _json.loads(text)
    except Exception:
        return {"ok": False, "error": "invalid JSON from AI", "raw": text[:400]}

    min_price = float(parsed.get("min_price_usd") or 0)
    now = datetime.now(timezone.utc).isoformat()
    triggered = min_price > 0 and min_price <= alert["target_usd"]
    update = {
        "last_check_at": now,
        "last_min_price_usd": min_price,
        "last_result": parsed,
    }
    if triggered:
        update["notify_count"] = alert.get("notify_count", 0) + 1
        update["last_notified_at"] = now
        # Fire email (non-blocking best-effort)
        try:
            from email_helpers import send_notification_email
            subject = f"✈️ Fare drop: {alert['origin']}→{alert['destination']} now ${min_price:.0f} (target ${alert['target_usd']:.0f})"
            cheapest = parsed.get("cheapest") or {}
            body_html = (
                f"<h2>Fare alert triggered</h2>"
                f"<p><strong>{alert['name']}</strong></p>"
                f"<p>Route: <b>{alert['origin']} → {alert['destination']}</b> on <b>{alert['date']}</b></p>"
                f"<p>Cabin: {alert.get('cabin', 'economy')} · Passengers: {alert.get('passengers', 1)}</p>"
                f"<p>Target: <b>${alert['target_usd']:.0f}</b> · Found: <b>${min_price:.0f}</b></p>"
                f"<hr/><p><b>Cheapest option</b>: {cheapest.get('airline', '')} {cheapest.get('flight_no', '')} — {cheapest.get('depart', '')} → {cheapest.get('arrive', '')}</p>"
                f"<p><a href='{cheapest.get('booking_url', '#')}' style='background:#0ea5e9;color:white;padding:8px 14px;text-decoration:none;border-radius:6px'>Book now</a></p>"
                f"<p style='color:#64748b;font-size:12px'>{parsed.get('note', '')}</p>"
                f"<p style='color:#94a3b8;font-size:11px'>You created this alert; disable it from Fare Alerts if unwanted.</p>"
            )
            await send_notification_email(alert["alert_email"], subject, body_html)
        except Exception as ex:
            logger.warning(f"Fare-alert email failed for {alert['id']}: {ex}")

    await db.fare_alerts.update_one({"id": alert["id"]}, {"$set": update})
    return {"ok": True, "min_price_usd": min_price, "triggered": triggered}


@router.post("/{alert_id}/check-now")
async def check_now(alert_id: str, current_user: dict = Depends(require_admin)):
    """Manually trigger a check on this alert (bypass the 24h cadence)."""
    a = await db.fare_alerts.find_one({"id": alert_id})
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    result = await _check_single_alert(a)
    return result
