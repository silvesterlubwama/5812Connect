"""Payment gateway layer — provider-agnostic (iter354).

Flutterwave turned out to be unavailable to this organisation, so payments are
no longer hard-wired to one provider. Everything now goes through a registry:

    manual        — no online provider. The buyer is shown the org's bank /
                    MTN / Airtel details plus a unique reference, and finance
                    matches the money when it lands (Payments Inbox).
    pesapal       — Pesapal API 3.0 (card + MoMo aggregator, Uganda/Kenya).
    mtn_momo      — MTN MoMo Collections (requestToPay).
    airtel_money  — Airtel Africa Collection (merchant payment).
    flutterwave   — kept working for anyone who already has keys.
    generic       — any bank / PSP that can POST a signed JSON webhook.

Adapters are thin on purpose: ask the provider to start a payment, then treat
the **webhook/IPN** as the only source of truth. Every inbound notification —
matched or not — lands in `payment_inbox` so finance can see money that
arrived without a matching order instead of it silently vanishing.

Nothing here posts to the ledger. A settled payment marks the sale
`online_payment_status: paid`; a human still runs Mark-as-Paid, exactly as
before.
"""
from datetime import datetime, timezone
from typing import Optional
import hashlib
import hmac
import os
import secrets
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from deps import db, logger, require_staff, require_manager, _audit

router = APIRouter(prefix="/api/payments", tags=["payments"])

# ── Provider registry ────────────────────────────────────────────────────────
# `fields` are what an admin must fill in; `secret_fields` get masked on read.
PROVIDERS = {
    "manual": {
        "label": "Manual / bank transfer only",
        "kind": "offline",
        "fields": [],
        "secret_fields": [],
        "note": "No online gateway. Buyers get your bank / mobile money details and a reference.",
    },
    "pesapal": {
        "label": "Pesapal (card + mobile money)",
        "kind": "hosted_checkout",
        "fields": ["consumer_key", "consumer_secret", "ipn_id"],
        "secret_fields": ["consumer_secret"],
        "note": "Pesapal API 3.0. Register the IPN URL below, then paste the notification_id as ipn_id.",
    },
    "mtn_momo": {
        "label": "MTN MoMo Collections",
        "kind": "push_request",
        "fields": ["subscription_key", "api_user", "api_key", "target_env"],
        "secret_fields": ["subscription_key", "api_key"],
        "note": "MTN requestToPay — the payer approves a prompt on their phone.",
    },
    "airtel_money": {
        "label": "Airtel Money Collections",
        "kind": "push_request",
        "fields": ["client_id", "client_secret", "country", "currency_code"],
        "secret_fields": ["client_secret"],
        "note": "Airtel Africa Collection API — the payer approves a USSD prompt.",
    },
    "flutterwave": {
        "label": "Flutterwave",
        "kind": "hosted_checkout",
        "fields": ["public_key", "secret_key", "webhook_hash"],
        "secret_fields": ["secret_key", "webhook_hash"],
        "note": "Existing integration, unchanged.",
    },
    "generic": {
        "label": "Other bank / PSP (signed webhook)",
        "kind": "webhook_only",
        "fields": ["base_url", "api_key", "webhook_secret", "webhook_header"],
        "secret_fields": ["api_key", "webhook_secret"],
        "note": "For banks that can POST a JSON webhook signed with HMAC-SHA256 over the raw body.",
    },
}

# Endpoints per provider, sandbox vs live.
_ENDPOINTS = {
    "pesapal": {
        "test": "https://cybqa.pesapal.com/pesapalv3/api",
        "live": "https://pay.pesapal.com/v3/api",
    },
    "mtn_momo": {
        "test": "https://sandbox.momodeveloper.mtn.com",
        "live": "https://proxy.momoapi.mtn.com",
    },
    "airtel_money": {
        "test": "https://openapiuat.airtel.africa",
        "live": "https://openapi.airtel.africa",
    },
}


async def get_config(require_online: bool = False) -> dict:
    from routers.system_settings import _load_raw
    pay = (await _load_raw()).get("payments") or {}
    if require_online:
        if not pay.get("enabled") or (pay.get("provider") or "manual") == "manual":
            raise HTTPException(status_code=503, detail="Online payment is not switched on yet")
    return pay


def provider_cfg(pay: dict, provider: Optional[str] = None) -> dict:
    prov = provider or (pay.get("provider") or "manual")
    cfg = dict(((pay.get("providers") or {}).get(prov)) or {})
    # Flutterwave keys pre-date the registry and live at the top level.
    if prov == "flutterwave":
        for k in ("public_key", "secret_key", "webhook_hash"):
            cfg.setdefault(k, pay.get(k) or "")
    return cfg


def _base_url(provider: str, pay: dict) -> str:
    cfg = provider_cfg(pay, provider)
    if cfg.get("base_url"):
        return str(cfg["base_url"]).rstrip("/")
    mode = "live" if (pay.get("mode") or "test") == "live" else "test"
    return (_ENDPOINTS.get(provider) or {}).get(mode, "")


def public_base(origin: str = "", request: Optional[Request] = None) -> str:
    base = os.environ.get("PUBLIC_APP_URL") or origin or ""
    if not base and request is not None:
        # Behind the ingress the app is reached on its public host, which only
        # the forwarded headers know about.
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if host:
            scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
            base = f"{scheme}://{host}"
    return base.rstrip("/")


def offline_instructions(pay: dict, reference: str, amount: float, currency: str) -> dict:
    """What a buyer needs in order to send money manually. Every field is
    admin-entered (System Console → Integrations) — nothing is invented here,
    so an empty config yields an empty list rather than fake account numbers."""
    off = pay.get("offline") or {}
    methods = []
    if off.get("account_number") or off.get("bank_name"):
        methods.append({
            "kind": "bank_transfer",
            "label": "Bank transfer",
            "details": [d for d in [
                ("Bank", off.get("bank_name")),
                ("Account name", off.get("account_name")),
                ("Account number", off.get("account_number")),
                ("Branch", off.get("branch")),
                ("SWIFT / BIC", off.get("swift")),
            ] if d[1]],
        })
    for key, label in (("mtn", "MTN Mobile Money"), ("airtel", "Airtel Money")):
        number = off.get(f"{key}_number")
        if number:
            methods.append({
                "kind": f"{key}_momo",
                "label": label,
                "details": [d for d in [
                    ("Number", number),
                    ("Registered name", off.get(f"{key}_name")),
                    ("Type", "Merchant / till" if off.get(f"{key}_is_merchant") else "Mobile number"),
                ] if d[1]],
            })
    return {
        "reference": reference,
        "amount": amount,
        "currency": currency,
        "methods": methods,
        "instructions": off.get("instructions") or "",
        "configured": bool(methods),
    }


# ── Adapters ─────────────────────────────────────────────────────────────────

async def _pesapal_token(pay: dict) -> str:
    cfg = provider_cfg(pay, "pesapal")
    if not (cfg.get("consumer_key") and cfg.get("consumer_secret")):
        raise HTTPException(status_code=503, detail="Pesapal keys are not configured yet")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{_base_url('pesapal', pay)}/Auth/RequestToken",
            json={"consumer_key": cfg["consumer_key"], "consumer_secret": cfg["consumer_secret"]},
            headers={"Accept": "application/json"},
        )
    if r.status_code >= 400:
        logger.warning(f"pesapal auth -> {r.status_code} {r.text[:200]}")
        raise HTTPException(status_code=502, detail="Pesapal rejected those credentials")
    token = (r.json() or {}).get("token")
    if not token:
        raise HTTPException(status_code=502, detail="Pesapal did not return a token")
    return token


async def pesapal_register_ipn(pay: dict, url: str) -> dict:
    """Register the IPN URL and hand back the notification_id Pesapal requires
    on every order. Called from the admin settings screen."""
    token = await _pesapal_token(pay)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{_base_url('pesapal', pay)}/URLSetup/RegisterIPN",
            json={"url": url, "ipn_notification_type": "POST"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Pesapal IPN registration failed: {r.text[:200]}")
    return r.json() or {}


async def _pesapal_submit(sale: dict, pay: dict, *, email: str, name: str, phone: str,
                          currency: str, origin: str) -> dict:
    cfg = provider_cfg(pay, "pesapal")
    if not cfg.get("ipn_id"):
        raise HTTPException(status_code=503, detail="Pesapal IPN is not registered yet — do it in System Console → Integrations")
    token = await _pesapal_token(pay)
    tx_ref = f"{sale.get('receipt_number') or sale['id']}-{secrets.token_hex(3)}"
    base = public_base(origin)
    first, _, last = (name or "Customer").partition(" ")
    body = {
        "id": tx_ref,
        "currency": currency,
        "amount": float(sale.get("total") or 0),
        "description": (pay.get("checkout_title") or "Order")[:100],
        "callback_url": f"{base}/api/payments/pesapal/callback",
        "notification_id": cfg["ipn_id"],
        "billing_address": {
            "email_address": email,
            "phone_number": phone or "",
            "first_name": first or "Customer",
            "last_name": last or "",
        },
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{_base_url('pesapal', pay)}/Transactions/SubmitOrderRequest",
            json=body, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if r.status_code >= 400:
        logger.warning(f"pesapal submit -> {r.status_code} {r.text[:300]}")
        raise HTTPException(status_code=502, detail="Pesapal could not start that payment")
    out = r.json() or {}
    if not out.get("redirect_url"):
        raise HTTPException(status_code=502, detail="Pesapal did not return a checkout link")
    await db.sales.update_one({"id": sale["id"]}, {"$set": {
        "payment_provider": "pesapal", "payment_tx_ref": tx_ref,
        "payment_tracking_id": out.get("order_tracking_id"),
        "online_payment_status": "pending",
    }})
    return {"payment_url": out["redirect_url"], "tx_ref": tx_ref, "currency": currency,
            "provider": "pesapal", "kind": "hosted_checkout"}


async def _momo_request(sale: dict, pay: dict, provider: str, *, phone: str,
                        currency: str) -> dict:
    """MTN MoMo / Airtel Money collection request.

    Both providers push a prompt to the payer's handset and confirm through a
    callback, so there is no redirect URL. Written to their published request
    shapes; disabled until an admin supplies credentials.
    """
    cfg = provider_cfg(pay, provider)
    required = [f for f in PROVIDERS[provider]["fields"] if not cfg.get(f)]
    if required:
        raise HTTPException(
            status_code=503,
            detail=f"{PROVIDERS[provider]['label']} is missing: {', '.join(required)}",
        )
    if not phone:
        raise HTTPException(status_code=400, detail="Enter the mobile money number")
    tx_ref = f"{sale.get('receipt_number') or sale['id']}-{secrets.token_hex(3)}"
    amount = float(sale.get("total") or 0)
    base = _base_url(provider, pay)
    try:
        if provider == "mtn_momo":
            async with httpx.AsyncClient(timeout=30) as c:
                tok = await c.post(
                    f"{base}/collection/token/",
                    headers={"Ocp-Apim-Subscription-Key": cfg["subscription_key"]},
                    auth=(cfg["api_user"], cfg["api_key"]),
                )
                if tok.status_code >= 400:
                    raise HTTPException(status_code=502, detail="MTN rejected those credentials")
                access = (tok.json() or {}).get("access_token")
                r = await c.post(
                    f"{base}/collection/v1_0/requesttopay",
                    headers={
                        "Authorization": f"Bearer {access}",
                        "X-Reference-Id": str(uuid.uuid4()),
                        "X-Target-Environment": cfg.get("target_env") or "sandbox",
                        "Ocp-Apim-Subscription-Key": cfg["subscription_key"],
                        "Content-Type": "application/json",
                    },
                    json={
                        "amount": f"{amount:.0f}", "currency": currency,
                        "externalId": tx_ref,
                        "payer": {"partyIdType": "MSISDN", "partyId": phone.lstrip("+")},
                        "payerMessage": (pay.get("checkout_title") or "Order")[:60],
                        "payeeNote": tx_ref,
                    },
                )
        else:  # airtel_money
            async with httpx.AsyncClient(timeout=30) as c:
                tok = await c.post(
                    f"{base}/auth/oauth2/token",
                    json={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                          "grant_type": "client_credentials"},
                )
                if tok.status_code >= 400:
                    raise HTTPException(status_code=502, detail="Airtel rejected those credentials")
                access = (tok.json() or {}).get("access_token")
                r = await c.post(
                    f"{base}/merchant/v1/payments/",
                    headers={
                        "Authorization": f"Bearer {access}",
                        "X-Country": cfg.get("country") or "UG",
                        "X-Currency": cfg.get("currency_code") or currency,
                        "Content-Type": "application/json",
                    },
                    json={
                        "reference": tx_ref,
                        "subscriber": {"country": cfg.get("country") or "UG",
                                       "currency": cfg.get("currency_code") or currency,
                                       "msisdn": phone.lstrip("+")[-9:]},
                        "transaction": {"amount": amount, "country": cfg.get("country") or "UG",
                                        "currency": cfg.get("currency_code") or currency,
                                        "id": tx_ref},
                    },
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"{provider} request failed: {e}")
        raise HTTPException(status_code=502, detail="The mobile money provider could not be reached")
    if r.status_code >= 400:
        logger.warning(f"{provider} requesttopay -> {r.status_code} {r.text[:300]}")
        raise HTTPException(status_code=502, detail="The mobile money provider rejected that request")
    await db.sales.update_one({"id": sale["id"]}, {"$set": {
        "payment_provider": provider, "payment_tx_ref": tx_ref,
        "online_payment_status": "pending",
    }})
    return {"payment_url": None, "tx_ref": tx_ref, "currency": currency, "provider": provider,
            "kind": "push_request",
            "message": "Approve the payment prompt on your phone — we'll confirm automatically."}


async def start_payment(sale: dict, *, email: str, name: str, phone: str, method: str,
                        network: str, origin: str) -> dict:
    """Begin an online payment with whichever provider is configured."""
    pay = await get_config(require_online=True)
    provider = pay.get("provider") or "manual"
    currency = pay.get("currency") or sale.get("currency") or "UGX"
    if provider == "flutterwave":
        from routers.payments_flutterwave import init_payment
        out = await init_payment(sale, email=email, name=name, phone=phone,
                                 method=method, network=network, origin=origin)
        out.setdefault("provider", "flutterwave")
        out.setdefault("kind", "hosted_checkout")
        return out
    if provider == "pesapal":
        return await _pesapal_submit(sale, pay, email=email, name=name, phone=phone,
                                     currency=currency, origin=origin)
    if provider in ("mtn_momo", "airtel_money"):
        return await _momo_request(sale, pay, provider, phone=phone, currency=currency)
    raise HTTPException(status_code=503, detail="The configured provider cannot take online payments")


# ── Inbox + reconciliation ───────────────────────────────────────────────────

async def record_inbox_entry(*, provider: str, reference: str, amount: float, currency: str,
                             payer: str = "", external_id: str = "", raw: dict = None,
                             source: str = "webhook") -> dict:
    """Log an incoming payment and try to match it to a sale by reference.

    Matching is deliberately dumb and auditable: exact sale id / receipt number
    / tx_ref. Anything else is left `unmatched` for finance to resolve by hand —
    better a visible queue than a wrong automatic match.
    """
    ref = (reference or "").strip()
    sale = None
    if ref:
        sale = await db.sales.find_one(
            {"$or": [{"id": ref}, {"receipt_number": ref}, {"payment_tx_ref": ref}]},
            {"_id": 0, "id": 1, "receipt_number": 1, "total": 1, "customer_name": 1},
        )
        if not sale and "-" in ref:
            stem = ref.rsplit("-", 1)[0]
            sale = await db.sales.find_one(
                {"$or": [{"id": stem}, {"receipt_number": stem}]},
                {"_id": 0, "id": 1, "receipt_number": 1, "total": 1, "customer_name": 1},
            )
    entry = {
        "id": f"pin_{uuid.uuid4().hex[:8]}",
        "provider": provider,
        "source": source,
        "reference": ref,
        "external_id": external_id,
        "amount": float(amount or 0),
        "currency": currency or "UGX",
        "payer": payer,
        "sale_id": (sale or {}).get("id"),
        "status": "matched" if sale else "unmatched",
        "amount_matches": (abs(float(amount or 0) - float((sale or {}).get("total") or 0)) < 0.01) if sale else None,
        "raw": raw or {},
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.payment_inbox.insert_one(entry)
    entry.pop("_id", None)
    if sale:
        await _mark_sale_paid_online(sale["id"], provider, ref)
    return entry


async def _mark_sale_paid_online(sale_id: str, provider: str, reference: str):
    """Flag the sale as paid online. Cash still isn't counted — a human runs
    Mark-as-Paid, which is what posts to the ledger."""
    await db.sales.update_one(
        {"id": sale_id, "online_payment_status": {"$ne": "paid"}},
        {"$set": {
            "online_payment_status": "paid",
            "payment_provider": provider,
            "payment_reference": reference,
            "online_paid_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


def verify_signature(raw: bytes, request: Request, secret: str, header: str = "") -> bool:
    """HMAC-SHA256 over the raw body, compared in constant time. Accepts hex or
    base64 digests, and a plain shared secret (what several banks still send)."""
    if not secret:
        return False
    candidates = []
    for h in filter(None, [header, "x-signature", "x-webhook-signature", "signature",
                           "verif-hash", "x-hub-signature-256"]):
        v = request.headers.get(h)
        if v:
            candidates.append(v.split("=")[-1].strip())
    if not candidates:
        return False
    import base64 as _b64
    digest = hmac.new(secret.encode(), raw, hashlib.sha256)
    expected = {digest.hexdigest(), _b64.b64encode(digest.digest()).decode(), secret}
    return any(hmac.compare_digest(c, e) for c in candidates for e in expected)


@router.post("/{provider}/inbound")
async def inbound_webhook(provider: str, request: Request):
    """Generic signed webhook / IPN for every non-Flutterwave provider.

    Flutterwave keeps its own route. Notifications are deduplicated on the
    provider's event id so a retry can't double-settle an order.
    """
    if provider not in PROVIDERS or provider == "flutterwave":
        raise HTTPException(status_code=404, detail="Unknown payment provider")
    raw = await request.body()
    pay = await get_config()
    cfg = provider_cfg(pay, provider)
    secret = cfg.get("webhook_secret") or cfg.get("consumer_secret") or cfg.get("api_key") or ""
    if secret and not verify_signature(raw, request, secret, cfg.get("webhook_header") or ""):
        logger.warning(f"{provider} webhook rejected: bad signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {"payload": body}

    event_id = str(
        body.get("event_id") or body.get("OrderTrackingId") or body.get("order_tracking_id")
        or body.get("transaction_id") or body.get("id") or hashlib.sha256(raw).hexdigest()
    )
    dedupe_key = f"{provider}:{event_id}"
    # `payment_webhook_events.id` is uniquely indexed — let the database be the
    # dedupe, so two concurrent retries can't both settle the order.
    try:
        await db.payment_webhook_events.insert_one({
            "id": dedupe_key, "key": dedupe_key, "provider": provider,
            "at": datetime.now(timezone.utc).isoformat(), "body": body,
        })
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}

    reference = str(
        body.get("reference") or body.get("merchant_reference") or body.get("externalId")
        or body.get("tx_ref") or body.get("OrderMerchantReference") or ""
    )
    amount = body.get("amount") or (body.get("transaction") or {}).get("amount") or 0
    currency = body.get("currency") or (body.get("transaction") or {}).get("currency") or pay.get("currency") or "UGX"
    status = str(body.get("status") or body.get("payment_status_description")
                 or (body.get("transaction") or {}).get("status") or "").lower()
    if status and status not in ("completed", "success", "successful", "ts", "paid", "200"):
        logger.info(f"{provider} webhook: non-success status '{status}' for {reference}")
        return {"received": True, "settled": False, "status": status}

    entry = await record_inbox_entry(
        provider=provider, reference=reference, amount=float(amount or 0),
        currency=currency, payer=str(body.get("msisdn") or body.get("payer") or ""),
        external_id=event_id, raw=body,
    )
    return {"received": True, "settled": entry["status"] == "matched", "inbox_id": entry["id"]}


@router.get("/providers")
async def list_providers(request: Request, current_user: dict = Depends(require_manager)):
    """Provider catalogue + which one is live, for the admin settings screen."""
    pay = await get_config()
    prov = pay.get("provider") or "manual"
    out = []
    for pid, meta in PROVIDERS.items():
        cfg = provider_cfg(pay, pid)
        missing = [f for f in meta["fields"] if not cfg.get(f)]
        out.append({
            "id": pid, "label": meta["label"], "kind": meta["kind"], "note": meta["note"],
            "fields": meta["fields"], "secret_fields": meta["secret_fields"],
            "configured": not missing, "missing": missing, "active": pid == prov,
        })
    base = public_base(request=request)
    return {
        "active": prov,
        "enabled": bool(pay.get("enabled")),
        "mode": pay.get("mode") or "test",
        "providers": out,
        "webhook_urls": {pid: f"{base}/api/payments/{pid}/inbound"
                         for pid in PROVIDERS if pid not in ("flutterwave", "manual")},
    }


@router.post("/pesapal/register-ipn")
async def register_pesapal_ipn(request: Request, current_user: dict = Depends(require_manager)):
    """One-click IPN registration — stores the returned notification_id."""
    pay = await get_config()
    base = public_base(request=request)
    if not base:
        raise HTTPException(status_code=400, detail="Could not work out this app's public URL — set PUBLIC_APP_URL on the backend")
    res = await pesapal_register_ipn(pay, f"{base}/api/payments/pesapal/inbound")
    ipn_id = res.get("ipn_id") or res.get("ipn_id".upper()) or res.get("notification_id")
    if not ipn_id:
        raise HTTPException(status_code=502, detail=f"Pesapal did not return a notification id: {str(res)[:200]}")
    providers = dict(pay.get("providers") or {})
    providers.setdefault("pesapal", {})
    providers["pesapal"] = {**providers["pesapal"], "ipn_id": ipn_id}
    await db.system_settings.update_one({"id": "default"}, {"$set": {"payments.providers": providers}}, upsert=True)
    await _audit(current_user["id"], "register", "payment_ipn", "pesapal", {"ipn_id": ipn_id})
    return {"ipn_id": ipn_id, "url": f"{base}/api/payments/pesapal/inbound"}


@router.get("/inbox")
async def payment_inbox(status: Optional[str] = None, limit: int = 100,
                        current_user: dict = Depends(require_staff)):
    """Payments finance can see: every provider notification plus anything
    recorded by hand. `status=unmatched` is the work queue."""
    query = {}
    if status in ("matched", "unmatched", "ignored"):
        query["status"] = status
    rows = await db.payment_inbox.find(query, {"_id": 0, "raw": 0}).sort("received_at", -1).to_list(min(limit, 500))
    unmatched = await db.payment_inbox.count_documents({"status": "unmatched"})
    return {"payments": rows, "unmatched": unmatched, "total": len(rows)}


@router.post("/inbox/manual")
async def record_manual_payment(data: dict, current_user: dict = Depends(require_staff)):
    """Finance logs money that arrived by bank transfer or mobile money.
    Body: { reference, amount, currency?, payer?, method?, sale_id? }"""
    try:
        amount = float(data.get("amount") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be a number")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than zero")
    pay = await get_config()
    entry = await record_inbox_entry(
        provider=(data.get("method") or "manual"),
        reference=(data.get("reference") or "").strip(),
        amount=amount,
        currency=(data.get("currency") or pay.get("currency") or "UGX"),
        payer=(data.get("payer") or "").strip(),
        source="manual",
        raw={"logged_by": current_user.get("name", ""), "note": (data.get("note") or "")[:300]},
    )
    if data.get("sale_id") and entry["status"] == "unmatched":
        return await match_payment(entry["id"], {"sale_id": data["sale_id"]}, current_user)
    await _audit(current_user["id"], "create", "payment_inbox", entry["id"],
                 {"amount": amount, "reference": entry["reference"]})
    return entry


@router.post("/inbox/{entry_id}/match")
async def match_payment(entry_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Attach a received payment to an order. Body: { sale_id } or { ignore: true }"""
    entry = await db.payment_inbox.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Payment not found")
    if data.get("ignore"):
        await db.payment_inbox.update_one({"id": entry_id}, {"$set": {
            "status": "ignored", "ignored_by_name": current_user.get("name", ""),
            "note": (data.get("note") or "")[:300],
        }})
        return {"id": entry_id, "status": "ignored"}
    sale_id = (data.get("sale_id") or "").strip()
    sale = await db.sales.find_one(
        {"$or": [{"id": sale_id}, {"receipt_number": sale_id}]},
        {"_id": 0, "id": 1, "total": 1, "receipt_number": 1},
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.payment_inbox.update_one({"id": entry_id}, {"$set": {
        "sale_id": sale["id"],
        "status": "matched",
        "amount_matches": abs(float(entry.get("amount") or 0) - float(sale.get("total") or 0)) < 0.01,
        "matched_by": current_user["id"],
        "matched_by_name": current_user.get("name", ""),
        "matched_at": datetime.now(timezone.utc).isoformat(),
    }})
    await _mark_sale_paid_online(sale["id"], entry.get("provider") or "manual", entry.get("reference") or "")
    await _audit(current_user["id"], "match", "payment_inbox", entry_id, {"sale_id": sale["id"]})
    return {"id": entry_id, "status": "matched", "sale_id": sale["id"]}
