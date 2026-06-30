"""Shipment PIN / edit-token security primitives.

Extracted from `routers/shipments.py` so the route file stays focused on
HTTP shapes and the security helpers stay easy to unit-test and audit.

What lives here:
    - `_PIN_SECRET`, `_PIN_SALT`        ← env-derived secrets
    - `EDIT_TOKEN_TTL_HOURS`            ← session lifetime constant (12h default)
    - `hash_pin(pin)`                   ← SHA-256(salt + pin) hex
    - `make_edit_token(shipment_id, ttl_hours=12)`  ← HMAC-signed session
    - `verify_edit_token(token)`        ← returns shipment_id or None
    - `require_shipment_editor(...)`    ← FastAPI dependency for /public edit routes

Imports of `db` / `_decode_jwt` stay lazy inside `require_shipment_editor`
so this module remains a leaf — importable from any route without circular
dependency risk.
"""
import os
import hmac
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request

# ─── secrets ───────────────────────────────────────────────────────────
_PIN_SECRET = os.environ.get("JWT_SECRET", "dev-secret-fallback").encode()
_PIN_SALT = b"shipment-edit-v1"

EDIT_TOKEN_TTL_HOURS = 12


def hash_pin(pin: str) -> str:
    """SHA-256(salt + pin) → hex. Plenty for low-stakes, non-PII gating."""
    return hashlib.sha256(_PIN_SALT + pin.encode("utf-8")).hexdigest()


def make_edit_token(shipment_id: str, ttl_hours: int = EDIT_TOKEN_TTL_HOURS) -> str:
    """HMAC-signed 'shipment_id:expires_iso' token. Base64-url encoded.
    `ttl_hours` lets the caller request a longer session (capped to 24h)."""
    ttl = max(1, min(24, int(ttl_hours or EDIT_TOKEN_TTL_HOURS)))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl)).isoformat()
    payload = f"{shipment_id}|{expires_at}"
    sig = hmac.new(_PIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode().rstrip("=")


def verify_edit_token(token: str) -> Optional[str]:
    """Return the shipment_id if the token is valid + unexpired, else None."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        shipment_id, expires_at, sig = raw.rsplit("|", 2)
    except Exception:
        return None
    payload = f"{shipment_id}|{expires_at}"
    expected = hmac.new(_PIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return None
    except Exception:
        return None
    return shipment_id


async def require_shipment_editor(request: Request, token: str):
    """Dependency for public-edit endpoints.

    Accepts EITHER:
      • a logged-in admin (via the normal Authorization: Bearer JWT)
      • an X-Shipment-Edit-Token header that decodes to THIS shipment's id
      • a `?edit_token=…` query param fallback (for browser-native GETs)
    """
    # Lazy import avoids a circular: `deps.py` itself does NOT depend on us.
    from deps import db
    s = await db.shipments.find_one({"token": token}, {"_id": 0, "id": 1, "status": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if s.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="Shipment not found")
    # 1) admin path: try the standard JWT auth, if present
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        try:
            from deps import _decode_jwt  # type: ignore
        except Exception:
            _decode_jwt = None
        if _decode_jwt:
            try:
                payload = _decode_jwt(auth.split(" ", 1)[1])
                user_id = payload.get("user_id") or payload.get("id")
                user = await db.users.find_one({"id": user_id}, {"_id": 0})
                if user and user.get("role") in ("admin", "super_admin"):
                    return {"shipment_id": s["id"], "actor": "admin", "user": user}
            except Exception:
                pass
    # 2) edit-token path — header (POST/PUT) or query (?edit_token= for GETs)
    edit_token = (request.headers.get("X-Shipment-Edit-Token") or "").strip()
    if not edit_token:
        edit_token = (request.query_params.get("edit_token") or "").strip()
    if edit_token:
        sid = verify_edit_token(edit_token)
        if sid == s["id"]:
            return {"shipment_id": s["id"], "actor": "pin"}
    raise HTTPException(status_code=401, detail="Edit-PIN required for this shipment")
