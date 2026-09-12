"""Flutterwave online payments for the public shop (UGX · card + Uganda MoMo).

Flow (per Flutterwave Standard + Uganda mobile money):
  1. The shop creates the sale FIRST (stock reserved, ledger untouched) then
     calls `init_payment` here, which asks Flutterwave for a hosted checkout
     link (card / bank / MoMo) or an MTN/Airtel authorisation redirect.
  2. The buyer pays and Flutterwave bounces them to `/api/payments/flutterwave/callback`.
     Callback params are user-controllable, so they are NEVER trusted: we
     always re-verify with `GET /v3/transactions/{id}/verify`.
  3. A signed webhook covers the case where the buyer closes the browser
     before MoMo completes. Both paths funnel into `_settle`, which is
     idempotent on `online_payment_status != paid`.

A settled sale stays `payment_status: pending` on purpose — cash has not been
counted by a human yet. It is flagged `online_payment_status: paid` so Sales
shows "Paid online — awaiting staff confirmation" and the existing
Mark-as-Paid action is what actually posts to the ledger.

Keys are entered by an admin in the app (System Console → Integrations) and
live in `db.system_settings.payments`, masked on read — same pattern as the
Resend key.
"""
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
from typing import Optional
import base64
import hashlib
import hmac
import json
import os
import secrets

import httpx

from deps import db, logger

router = APIRouter(prefix="/api/payments/flutterwave", tags=["payments"])

FLW_API = "https://api.flutterwave.com/v3"
NETWORKS = {"MTN", "AIRTEL"}


async def _cfg(require_keys: bool = True) -> dict:
    from routers.system_settings import _load_raw
    raw = await _load_raw()
    pay = (raw.get("payments") or {})
    if require_keys:
        if not pay.get("enabled"):
            raise HTTPException(status_code=503, detail="Online payment is not switched on yet")
        if not pay.get("secret_key"):
            raise HTTPException(status_code=503, detail="Online payment is not configured yet")
    return pay


async def _flw(method: str, path: str, secret: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(
            method, FLW_API + path,
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            **kwargs,
        )
    if r.status_code >= 400:
        logger.warning(f"flutterwave {method} {path} -> {r.status_code} {r.text[:300]}")
        raise HTTPException(status_code=502, detail="The payment provider rejected that request")
    return r.json()


def _api_base(origin: str = "") -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or origin or "").rstrip("/")
    return base


async def init_payment(sale: dict, *, email: str, name: str, phone: str,
                       method: str, network: str, origin: str) -> dict:
    """Ask Flutterwave for a payment URL for an already-created sale."""
    cfg = await _cfg()
    amount = int(round(float(sale.get("total") or 0)))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Nothing to pay for")
    currency = (cfg.get("currency") or "UGX").upper()
    tx_ref = f"{sale['id']}_{secrets.token_urlsafe(8)}"
    base = _api_base(origin)
    redirect_url = f"{base}/api/payments/flutterwave/callback"

    await db.sales.update_one({"id": sale["id"]}, {"$set": {
        "online_payment_status": "initiated",
        "online_payment_provider": "flutterwave",
        "online_payment_method": method,
        "tx_ref": tx_ref,
        "online_payment_currency": currency,
        "online_payment_started_at": datetime.now(timezone.utc).isoformat(),
        "return_origin": origin,
    }})

    if method == "mobile_money":
        if not phone or network.upper() not in NETWORKS:
            raise HTTPException(status_code=400, detail="A phone number and MTN or AIRTEL are required")
        result = await _flw("POST", "/charges?type=mobile_money_uganda", cfg["secret_key"], json={
            "phone_number": phone, "network": network.upper(), "amount": amount,
            "currency": currency, "email": email, "tx_ref": tx_ref, "fullname": name,
            "redirect_url": redirect_url, "meta": {"sale_id": sale["id"]},
        })
        url = ((result.get("meta") or {}).get("authorization") or {}).get("redirect")
        if not url:
            raise HTTPException(status_code=502, detail="Mobile money is unavailable right now")
    else:
        result = await _flw("POST", "/payments", cfg["secret_key"], json={
            "tx_ref": tx_ref, "amount": amount, "currency": currency,
            "redirect_url": redirect_url,
            "customer": {"email": email, "name": name, "phonenumber": phone or None},
            "customizations": {"title": cfg.get("checkout_title") or "58:12 Global Shop"},
            "meta": {"sale_id": sale["id"]},
        })
        url = ((result.get("data") or {}).get("link"))
        if not url:
            raise HTTPException(status_code=502, detail="Checkout is unavailable right now")
    return {"payment_url": url, "tx_ref": tx_ref, "amount": amount, "currency": currency}


async def _settle(transaction_id: str, tx_ref: str) -> bool:
    """Verify with Flutterwave then flag the sale as paid online. Idempotent."""
    cfg = await _cfg()
    sale = await db.sales.find_one({"tx_ref": tx_ref}, {"_id": 0})
    if not sale:
        logger.warning(f"flutterwave settle: unknown tx_ref {tx_ref}")
        return False
    result = await _flw("GET", f"/transactions/{transaction_id}/verify", cfg["secret_key"])
    data = result.get("data") or {}
    expected = int(round(float(sale.get("total") or 0)))
    ok = (
        data.get("status") == "successful"
        and data.get("tx_ref") == tx_ref
        and (data.get("currency") or "").upper() == (sale.get("online_payment_currency") or "UGX").upper()
        and float(data.get("amount") or 0) >= expected
    )
    if not ok:
        await db.sales.update_one({"id": sale["id"], "online_payment_status": {"$ne": "paid"}}, {"$set": {
            "online_payment_status": "failed",
            "online_payment_failed_reason": str(data.get("status") or "verification failed")[:200],
        }})
        return False

    res = await db.sales.update_one(
        {"id": sale["id"], "online_payment_status": {"$ne": "paid"}},
        {"$set": {
            "online_payment_status": "paid",
            "online_paid_at": datetime.now(timezone.utc).isoformat(),
            "payment_reference": str(data.get("id")),
            "online_payment": {
                "provider": "flutterwave",
                "transaction_id": str(data.get("id")),
                "flw_ref": data.get("flw_ref"),
                "amount": float(data.get("amount") or 0),
                "currency": data.get("currency"),
                "channel": data.get("payment_type"),
                "customer": (data.get("customer") or {}).get("email"),
            },
        }},
    )
    if res.modified_count:
        await _notify_paid(sale, data)
    return True


async def _notify_paid(sale: dict, data: dict):
    """Email the buyer a paid confirmation and ping staff to confirm collection."""
    try:
        from routers.email import send_email_internal, _base_html
        from routers.notifications import create_notification
        ref = sale.get("receipt_number") or sale.get("id")
        cur = data.get("currency") or "UGX"
        amt = f"{cur} {float(data.get('amount') or 0):,.0f}"
        email = sale.get("customer_email") or (data.get("customer") or {}).get("email")
        if email:
            await send_email_internal(
                [email], f"Payment received — order {ref}",
                _base_html(
                    f"<h2 style='color:#1a1a2e;margin:0 0 8px'>Payment received</h2>"
                    f"<p style='color:#444;line-height:1.6'>Thanks {sale.get('customer_name') or ''}! We've received "
                    f"<strong>{amt}</strong> for order <strong>{ref}</strong>. Your items are reserved — "
                    f"our team will confirm your collection details shortly.</p>"
                ),
                kind="online_payment_receipt",
            )
        alert = os.environ.get("ORDER_ALERT_EMAIL", "")
        if alert:
            await send_email_internal(
                [alert], f"Paid online — order {ref} ({amt})",
                _base_html(
                    f"<h2 style='color:#1a1a2e;margin:0 0 8px'>Online payment received</h2>"
                    f"<p style='color:#444'>{sale.get('customer_name') or ''} paid <strong>{amt}</strong> "
                    f"for <strong>{ref}</strong> via Flutterwave (ref {data.get('id')}).</p>"
                    f"<p style='color:#444;font-size:13px'>It's in Sales flagged <strong>Paid online — awaiting "
                    f"staff confirmation</strong>. Confirm it there to post the money to the ledger.</p>"
                ),
                kind="online_payment_alert",
            )
        admins = await db.users.find(
            {"role": {"$in": ["admin", "system_admin", "director", "manager"]}, "status": "active"},
            {"_id": 0, "id": 1},
        ).to_list(50)
        for a in admins:
            await create_notification(
                title="Order paid online",
                message=f"{sale.get('customer_name') or 'A customer'} paid {amt} for {ref} — confirm collection in Sales.",
                user_id=a["id"], notif_type="sale", link="/products?tab=sales",
            )
    except Exception as ex:
        logger.warning(f"flutterwave paid notification skipped: {ex}")


@router.get("/callback")
async def flutterwave_callback(
    request: Request,
    status: str = "",
    tx_ref: str = "",
    transaction_id: str = "",
):
    paid = False
    if status == "successful" and transaction_id and tx_ref:
        try:
            paid = await _settle(transaction_id, tx_ref)
        except HTTPException as ex:
            logger.warning(f"flutterwave callback settle failed: {ex.detail}")
    sale = await db.sales.find_one({"tx_ref": tx_ref}, {"_id": 0, "id": 1, "receipt_number": 1, "return_origin": 1}) if tx_ref else None
    origin = (sale or {}).get("return_origin") or os.environ.get("PUBLIC_APP_URL", "") or str(request.base_url).rstrip("/")
    ref = (sale or {}).get("receipt_number") or (sale or {}).get("id") or ""
    dest = f"{origin.rstrip('/')}/marketplace?tab=shop&payment={'paid' if paid else 'failed'}&order={ref}"
    return RedirectResponse(dest, status_code=303)


def _valid_signature(raw: bytes, request: Request, secret_hash: str) -> bool:
    sig = request.headers.get("flutterwave-signature")
    if sig:
        expected = base64.b64encode(hmac.new(secret_hash.encode(), raw, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(expected, sig)
    legacy = request.headers.get("verif-hash") or request.headers.get("verifi-hash")
    return bool(legacy) and hmac.compare_digest(legacy, secret_hash)


@router.post("/webhook")
async def flutterwave_webhook(request: Request):
    raw = await request.body()
    cfg = await _cfg()
    secret_hash = cfg.get("webhook_hash") or ""
    if not secret_hash or not _valid_signature(raw, request, secret_hash):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload")
    data = payload.get("data") or {}
    event_id = str(payload.get("id") or data.get("id") or hashlib.sha256(raw).hexdigest())
    existing = await db.payment_webhook_events.find_one({"id": event_id})
    if existing:
        return {"ok": True, "duplicate": True}
    await db.payment_webhook_events.insert_one({
        "id": event_id, "provider": "flutterwave", "event": payload.get("event"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    })
    if payload.get("event") in ("charge.completed", "transfer.completed") and data.get("id") and data.get("tx_ref"):
        try:
            await _settle(str(data["id"]), data["tx_ref"])
        except HTTPException as ex:
            logger.warning(f"flutterwave webhook settle failed: {ex.detail}")
    return {"ok": True}


@router.get("/status")
async def payment_status(tx_ref: str = Query(...)):
    """Public poll — lets the shop's result screen show a live state for MoMo
    payments that complete after the browser has already come back."""
    sale = await db.sales.find_one(
        {"tx_ref": tx_ref},
        {"_id": 0, "id": 1, "receipt_number": 1, "total": 1,
         "online_payment_status": 1, "payment_status": 1},
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Order not found")
    return sale
