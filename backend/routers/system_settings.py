"""System Settings — admin-configurable integrations stored in the DB so they
travel between deployments (via the backup feature) and can be updated without
redeploying. Currently powers:
  • Email (Resend now; SMTP fallback shape is supported but unused)
  • Sentry DSN (frontend + backend error tracking)
  • Org primary country/currency (used by /financial fallback)

Secrets are stored cleartext in Mongo (you already trust Mongo with everything
else); the read endpoints mask the API key bodies — only the last 4 chars + length
are returned so an admin can confirm what's set without exposing the secret. The
operator must re-enter the full key to change it.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from deps import db, require_admin, _audit, logger
from datetime import datetime, timezone
from typing import Optional

router = APIRouter(prefix="/api/admin/system-settings", tags=["system_settings"])

SETTINGS_ID = "default"

# Default skeleton used on first read so downstream code never sees an empty doc.
_DEFAULTS = {
    "id": SETTINGS_ID,
    "email": {
        "provider": "resend",          # resend | smtp | none
        "resend_api_key": "",          # cleartext; masked on read
        "sender_email": "",            # e.g. "noreply@5812connect.app"
        "sender_name": "58:12 Connect",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_tls": True,
    },
    "sentry": {
        "enabled": False,
        "dsn": "",
        "environment": "production",
        "traces_sample_rate": 0.1,
    },
    "org": {
        "primary_country": "Uganda",
        "primary_currency": "UGX",
    },
    "payments": {
        # Online checkout for the public shop. Keys are entered in the app
        # (System Console → Integrations) so no redeploy is needed.
        "provider": "flutterwave",
        "enabled": False,
        "mode": "test",                # test | live
        "public_key": "",              # FLWPUBK... (safe-ish, still masked)
        "secret_key": "",              # FLWSECK... — backend only
        "webhook_hash": "",            # Flutterwave dashboard "Secret hash"
        "currency": "UGX",
        "allow_card": True,            # hosted checkout (card / bank / MoMo)
        "allow_mobile_money": True,    # explicit MTN / Airtel Uganda charge
        "allow_pay_on_collection": True,
        "checkout_title": "58:12 Global Shop",
    },
    "branding": {
        # App-wide white-labelling. `nav_overrides` is a flat map from route path
        # → {label, hidden, order} so admins can rename / hide / reorder sidebar
        # entries without code changes. Travels with the backup tarball.
        "app_name": "58:12 Connect",
        "tagline": "",
        "logo_url": "",
        "primary_color": "",        # e.g. "#10b981" — empty = keep theme default
        "nav_overrides": {},        # { "/path": {label?, hidden?, order?} }
        "section_overrides": {},    # { "Operations": {label?, hidden?, order?} }
    },
}


def _mask(value: str) -> str:
    """Return a masked version of a secret — ••••XXXX (last 4) + length suffix."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


async def _load_raw() -> dict:
    """Internal: returns the unmasked settings doc (cleartext secrets included).
    Used by helpers like get_resend_config() — NEVER returned over HTTP directly."""
    doc = await db.system_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        doc = dict(_DEFAULTS)
    # Merge missing keys onto defaults to handle schema additions
    for k, v in _DEFAULTS.items():
        if k == "id":
            continue
        if k not in doc:
            doc[k] = v
        elif isinstance(v, dict):
            for sub, subv in v.items():
                if sub not in doc[k]:
                    doc[k][sub] = subv
    return doc


def _mask_for_read(doc: dict) -> dict:
    """Apply masking to every secret field so admins can VIEW the doc without
    leaking cleartext keys. The 'set' field tells the UI whether something is configured."""
    out = {"id": doc.get("id", SETTINGS_ID), "updated_at": doc.get("updated_at"), "updated_by_name": doc.get("updated_by_name")}
    e = doc.get("email", {}) or {}
    out["email"] = {
        "provider": e.get("provider", "resend"),
        "resend_api_key_masked": _mask(e.get("resend_api_key", "")),
        "resend_api_key_set": bool(e.get("resend_api_key")),
        "sender_email": e.get("sender_email", ""),
        "sender_name": e.get("sender_name", "58:12 Connect"),
        "smtp_host": e.get("smtp_host", ""),
        "smtp_port": e.get("smtp_port", 587),
        "smtp_user": e.get("smtp_user", ""),
        "smtp_password_masked": _mask(e.get("smtp_password", "")),
        "smtp_password_set": bool(e.get("smtp_password")),
        "smtp_tls": e.get("smtp_tls", True),
    }
    s = doc.get("sentry", {}) or {}
    out["sentry"] = {
        "enabled": s.get("enabled", False),
        "dsn_masked": _mask(s.get("dsn", "")),
        "dsn_set": bool(s.get("dsn")),
        "environment": s.get("environment", "production"),
        "traces_sample_rate": s.get("traces_sample_rate", 0.1),
    }
    out["org"] = doc.get("org") or {}
    out["branding"] = doc.get("branding") or {}
    p = doc.get("payments", {}) or {}
    out["payments"] = {
        "provider": p.get("provider", "flutterwave"),
        "enabled": p.get("enabled", False),
        "mode": p.get("mode", "test"),
        "public_key_masked": _mask(p.get("public_key", "")),
        "public_key_set": bool(p.get("public_key")),
        "secret_key_masked": _mask(p.get("secret_key", "")),
        "secret_key_set": bool(p.get("secret_key")),
        "webhook_hash_masked": _mask(p.get("webhook_hash", "")),
        "webhook_hash_set": bool(p.get("webhook_hash")),
        "currency": p.get("currency", "UGX"),
        "allow_card": p.get("allow_card", True),
        "allow_mobile_money": p.get("allow_mobile_money", True),
        "allow_pay_on_collection": p.get("allow_pay_on_collection", True),
        "checkout_title": p.get("checkout_title", "58:12 Global Shop"),
    }
    return out


@router.get("/public")
async def public_system_settings(response: Response):
    """Non-secret, public-readable subset of system settings — used by the app shell
    to pick the org's primary country/currency + branding overrides without an
    admin auth round-trip. Cached for 30 s on the client to avoid hammering the
    DB on every anonymous page load."""
    response.headers["Cache-Control"] = "public, max-age=30"
    raw = await _load_raw()
    org = raw.get("org") or {}
    branding = raw.get("branding") or {}
    pay = raw.get("payments") or {}
    return {
        "org": {
            "primary_country": org.get("primary_country") or "Uganda",
            "primary_currency": org.get("primary_currency") or "UGX",
        },
        "branding": {
            "app_name": branding.get("app_name") or "58:12 Connect",
            "tagline": branding.get("tagline") or "",
            "logo_url": branding.get("logo_url") or "",
            "primary_color": branding.get("primary_color") or "",
            "nav_overrides": branding.get("nav_overrides") or {},
            "section_overrides": branding.get("section_overrides") or {},
        },
        "email_provider": (raw.get("email") or {}).get("provider", "resend"),
        "payments": {
            # Non-secret: tells the public shop which checkout buttons to show.
            "online_enabled": bool(pay.get("enabled") and pay.get("secret_key")),
            "allow_card": pay.get("allow_card", True),
            "allow_mobile_money": pay.get("allow_mobile_money", True),
            "allow_pay_on_collection": pay.get("allow_pay_on_collection", True),
            "currency": pay.get("currency") or org.get("primary_currency") or "UGX",
        },
    }


@router.get("")
async def get_system_settings(current_user: dict = Depends(require_admin)):
    """Returns the (masked) current settings doc."""
    doc = await _load_raw()
    return _mask_for_read(doc)


@router.put("")
async def update_system_settings(data: dict, current_user: dict = Depends(require_admin)):
    """Partial-update the settings doc. Pass only the keys you want to change.

    For secret fields you have THREE shapes per request:
      • omit the field entirely → keep current value
      • set to '' (empty string) → clear the secret
      • set to a non-empty string → replace with that value
    Anything else (whole-block updates like { email: { sender_email: 'x@y' } })
    merges into the current nested doc.
    """
    raw = await _load_raw()
    # Top-level keys we accept
    for top in ("email", "sentry", "org", "branding", "payments"):
        if top in data and isinstance(data[top], dict):
            current_block = raw.get(top) or {}
            for k, v in data[top].items():
                # `*_masked` keys are READ-only — refuse to write them
                if k.endswith("_masked") or k.endswith("_set"):
                    continue
                current_block[k] = v
            raw[top] = current_block
    raw["updated_at"] = datetime.now(timezone.utc).isoformat()
    raw["updated_by"] = current_user["id"]
    raw["updated_by_name"] = current_user.get("name") or current_user.get("email", "")
    raw["id"] = SETTINGS_ID
    await db.system_settings.update_one({"id": SETTINGS_ID}, {"$set": raw}, upsert=True)
    await _audit(
        current_user["id"], "update", "system_settings", SETTINGS_ID,
        {"keys_changed": sorted(set(data.keys()) & {"email", "sentry", "org", "branding", "payments"})},
    )
    return _mask_for_read(raw)


@router.post("/test-email")
async def send_test_email(data: dict, current_user: dict = Depends(require_admin)):
    """Send a one-off test email to verify the Resend / SMTP config works.
    Body: { to: 'admin@example.com' } — defaults to the caller's email."""
    target = (data.get("to") or current_user.get("email") or "").strip()
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Recipient email required")
    raw = await _load_raw()
    e = raw.get("email") or {}
    provider = e.get("provider") or "resend"
    sender = (e.get("sender_email") or "").strip()
    sender_name = e.get("sender_name") or "58:12 Connect"
    if not sender:
        raise HTTPException(status_code=400, detail="Sender email is not configured")
    subject = f"Test email from {sender_name} — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    body_html = (
        f"<p>Hi {(current_user.get('name') or 'admin').split()[0]},</p>"
        f"<p>This is a test email from your <strong>58:12 Connect</strong> deployment confirming"
        f" that the <strong>{provider}</strong> integration is configured correctly.</p>"
        f"<p>If you received this, you're good to go.</p>"
        f"<p>— Automated test</p>"
    )
    try:
        if provider == "resend":
            api_key = (e.get("resend_api_key") or "").strip()
            if not api_key:
                raise HTTPException(status_code=400, detail="Resend API key is not configured")
            import resend as _resend
            _resend.api_key = api_key
            res = _resend.Emails.send({
                "from": f"{sender_name} <{sender}>",
                "to": target,
                "subject": subject,
                "html": body_html,
            })
            return {"sent": True, "provider": provider, "to": target, "message_id": (res or {}).get("id")}
        elif provider == "smtp":
            host = e.get("smtp_host"); port = e.get("smtp_port") or 587
            user = e.get("smtp_user"); password = e.get("smtp_password"); use_tls = e.get("smtp_tls", True)
            if not host:
                raise HTTPException(status_code=400, detail="SMTP host not configured")
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender}>"
            msg["To"] = target
            msg.set_content("This is a test email. View HTML version.")
            msg.add_alternative(body_html, subtype="html")
            with smtplib.SMTP(host, port, timeout=15) as srv:
                if use_tls:
                    srv.starttls()
                if user and password:
                    srv.login(user, password)
                srv.send_message(msg)
            return {"sent": True, "provider": "smtp", "to": target}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported email provider: {provider}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"test email failed: {e}")
        raise HTTPException(status_code=500, detail=f"Send failed: {e}")


# ============================================================
# RUNTIME HELPERS — used by other routers to read the live config
# ============================================================

async def get_email_config() -> dict:
    """Returns the email-config dict (cleartext). Used by email_helpers.py +
    server.py scheduler tasks. Falls back to env vars when DB is empty so
    existing deployments don't break before an admin opens the settings UI."""
    import os as _os
    raw = await _load_raw()
    e = raw.get("email") or {}
    # Env-var fallbacks for the bootstrap case
    if not e.get("resend_api_key"):
        e["resend_api_key"] = _os.environ.get("RESEND_API_KEY", "")
    if not e.get("sender_email"):
        e["sender_email"] = _os.environ.get("SENDER_EMAIL", "")
    return e


async def get_sentry_config() -> dict:
    import os as _os
    raw = await _load_raw()
    s = raw.get("sentry") or {}
    if not s.get("dsn"):
        s["dsn"] = _os.environ.get("SENTRY_DSN", "")
    return s
