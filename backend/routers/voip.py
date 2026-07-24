"""VoIP / SIP integration with Grandstream UCM 63xx.

The application acts as a JsSIP-based softphone that registers directly into
the customer's Grandstream UCM as another endpoint on each staff member's
extension. No local Asterisk PBX runs — the UCM owns trunks, dialplan, IVR,
DID mapping, voicemail, and CDR.

Endpoints (all under /api/voip):

    Tenant-level (admin)
    --------------------
    GET    /tenant/config              — read the shared UCM connection info
    PUT    /tenant/config              — update it (+ rotate encrypted API pw)
    POST   /tenant/test                — issue a challenge/login against UCM

    Per-user (admin)
    ----------------
    PUT    /users/{user_id}/sip        — set extension + password + display name
    DELETE /users/{user_id}/sip        — clear the SIP config for that user
    GET    /users                      — list users + whether they have SIP configured

    Per-user (self-service)
    -----------------------
    GET    /me/sip-config              — full connection info for THIS user's browser softphone
    GET    /me/directory               — list of colleagues + extensions for intra-office dial
    GET    /me/voicemails              — list voicemails from the UCM
    GET    /me/voicemails/{id}/audio   — stream the WAV
    POST   /me/voicemails/{id}/mark-read
    DELETE /me/voicemails/{id}
    GET    /me/call-history            — CDR rows for THIS extension
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from deps import db, get_current_user, require_admin
from voip_crypto import decrypt_password, encrypt_password
from ucm_client import UCMClient, UCMError, get_client_for_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voip", tags=["voip"])


# ============================================================
# MODELS
# ============================================================


class TenantConfigIn(BaseModel):
    """Tenant-level UCM connection settings. Stored as a single doc in
    `db.voip_config` (id='singleton')."""
    ucm_host: str = Field("", description="Hostname or IP for SIP + WebSocket, e.g. pbx.example.org")
    sip_domain: str = Field("", description="SIP realm — usually same as ucm_host")
    ws_url: str = Field("", description="wss:// URL that JsSIP registers over, e.g. wss://pbx.example.org:8089/ws")
    stun_urls: List[str] = Field(default_factory=lambda: ["stun:stun.l.google.com:19302"])
    turn_urls: List[str] = Field(default_factory=list)
    turn_username: str = ""
    turn_password: str = ""
    ucm_api_url: str = Field("", description="Base URL of the UCM HTTPS API, e.g. https://pbx.example.org:8089")
    ucm_api_username: str = Field("", description="Super Admin (or apiuser) account name")
    ucm_api_password: Optional[str] = Field(None, description="Only send when rotating; omit to keep existing")
    ucm_verify_tls: bool = True


def _clean_host(raw: str) -> str:
    """Strip protocol prefix, trailing slashes, and any inline path — this
    field is meant to be a bare hostname for use inside SIP URIs. Users
    frequently paste in a full https:// URL by mistake, which then makes
    JsSIP build invalid SIP URIs like `sip:1042@https://pbx.example.org`."""
    if not raw:
        return ""
    v = raw.strip()
    for prefix in ("https://", "http://", "wss://", "ws://", "sip:", "sips:"):
        if v.lower().startswith(prefix):
            v = v[len(prefix):]
            break
    # Drop anything after the first '/' — the host doesn't own a path.
    v = v.split("/", 1)[0]
    # Preserve :port because SIP realms sometimes include it, but strip a
    # dangling colon.
    return v.rstrip(":").strip()


def _clean_api_url(raw: str) -> str:
    """The API URL DOES need a protocol. Normalise: default to https:// if
    missing, strip trailing slashes, and reject obviously wrong values."""
    if not raw:
        return ""
    v = raw.strip().rstrip("/")
    if not v.lower().startswith(("http://", "https://")):
        v = "https://" + v
    return v


def _clean_ws_url(raw: str) -> str:
    """Must be wss:// (or ws:// for insecure local dev)."""
    if not raw:
        return ""
    v = raw.strip().rstrip("/")
    if not v.lower().startswith(("wss://", "ws://")):
        # Assume they typed a bare host — default to wss on 8089/ws (Grandstream default)
        host = _clean_host(v)
        if host:
            v = f"wss://{host}:8089/ws"
    return v


class UserSipIn(BaseModel):
    extension: str = Field(..., min_length=2, max_length=10)
    sip_password: str = Field(..., min_length=1)
    display_name: str = ""


# ============================================================
# INTERNAL HELPERS
# ============================================================


async def _get_config_doc() -> Dict[str, Any]:
    doc = await db.voip_config.find_one({"id": "singleton"}, {"_id": 0}) or {}
    # One-shot self-heal: if legacy data still has a protocol prefix in the
    # host, silently clean it on read. Prevents stale bad values from breaking
    # JsSIP for users who saved before the sanitiser was added.
    if doc:
        cleaned_host = _clean_host(doc.get("ucm_host", ""))
        cleaned_realm = _clean_host(doc.get("sip_domain", ""))
        cleaned_ws = _clean_ws_url(doc.get("ws_url", ""))
        cleaned_api = _clean_api_url(doc.get("ucm_api_url", ""))
        if (cleaned_host != doc.get("ucm_host", "")
                or cleaned_realm != doc.get("sip_domain", "")
                or cleaned_ws != doc.get("ws_url", "")
                or cleaned_api != doc.get("ucm_api_url", "")):
            doc.update({
                "ucm_host": cleaned_host,
                "sip_domain": cleaned_realm or cleaned_host,
                "ws_url": cleaned_ws,
                "ucm_api_url": cleaned_api,
            })
            await db.voip_config.update_one({"id": "singleton"}, {"$set": {
                "ucm_host": cleaned_host,
                "sip_domain": cleaned_realm or cleaned_host,
                "ws_url": cleaned_ws,
                "ucm_api_url": cleaned_api,
            }})
    return doc


def _redact_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return everything the FE needs, but never the encrypted UCM admin password
    or the internal crypto_key. `turn_password` is safely returned because it's
    needed client-side for WebRTC ICE."""
    return {
        "ucm_host": cfg.get("ucm_host") or "",
        "sip_domain": cfg.get("sip_domain") or "",
        "ws_url": cfg.get("ws_url") or "",
        "stun_urls": cfg.get("stun_urls") or [],
        "turn_urls": cfg.get("turn_urls") or [],
        "turn_username": cfg.get("turn_username") or "",
        "turn_password": cfg.get("turn_password") or "",
        "ucm_api_url": cfg.get("ucm_api_url") or "",
        "ucm_api_username": cfg.get("ucm_api_username") or "",
        "ucm_api_configured": bool(cfg.get("ucm_api_password_enc")),
        "ucm_verify_tls": bool(cfg.get("ucm_verify_tls", True)),
    }


async def _current_user_ext(current_user: Dict[str, Any]) -> Optional[str]:
    """Return the SIP extension for the current user, if configured."""
    pbx = current_user.get("pbx") or {}
    if pbx.get("extension"):
        return str(pbx["extension"])
    fresh = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "pbx": 1}) or {}
    return (fresh.get("pbx") or {}).get("extension")


async def _ucm_from_config() -> UCMClient:
    """Load tenant config and return a live UCM client. 502s if unconfigured."""
    cfg = await _get_config_doc()
    if not cfg.get("ucm_api_url") or not cfg.get("ucm_api_username") or not cfg.get("ucm_api_password_enc"):
        raise HTTPException(status_code=502, detail="UCM API is not configured. Ask an admin to set it up under VoIP settings.")
    password = await decrypt_password(db, cfg["ucm_api_password_enc"])
    return await get_client_for_config(cfg, password)


# ============================================================
# TENANT CONFIG (admin)
# ============================================================


@router.get("/tenant/config")
async def get_tenant_config(current_user: dict = Depends(require_admin)):
    return _redact_config(await _get_config_doc())


@router.put("/tenant/config")
async def set_tenant_config(data: TenantConfigIn, current_user: dict = Depends(require_admin)):
    existing = await _get_config_doc()
    # Auto-strip protocol prefixes from host fields — otherwise JsSIP will
    # build malformed SIP URIs like sip:1042@https://pbx.example.org and the
    # WebSocket will silently refuse to open.
    clean_host = _clean_host(data.ucm_host)
    clean_realm = _clean_host(data.sip_domain) or clean_host
    update: Dict[str, Any] = {
        "id": "singleton",
        "ucm_host": clean_host,
        "sip_domain": clean_realm,
        "ws_url": _clean_ws_url(data.ws_url),
        "stun_urls": [u.strip() for u in data.stun_urls if u.strip()],
        "turn_urls": [u.strip() for u in data.turn_urls if u.strip()],
        "turn_username": (data.turn_username or "").strip(),
        "turn_password": (data.turn_password or "").strip(),
        "ucm_api_url": _clean_api_url(data.ucm_api_url),
        "ucm_api_username": data.ucm_api_username.strip(),
        "ucm_verify_tls": bool(data.ucm_verify_tls),
    }
    if data.ucm_api_password is not None and data.ucm_api_password != "":
        update["ucm_api_password_enc"] = await encrypt_password(db, data.ucm_api_password)
    elif "ucm_api_password_enc" in existing:
        update["ucm_api_password_enc"] = existing["ucm_api_password_enc"]
    await db.voip_config.update_one({"id": "singleton"}, {"$set": update}, upsert=True)
    return _redact_config(await _get_config_doc())


@router.post("/tenant/test")
async def test_ucm_connection(current_user: dict = Depends(require_admin)):
    """Attempt a challenge/login against the UCM to verify credentials."""
    try:
        client = await _ucm_from_config()
        await client._ensure_session()  # noqa: SLF001 — internal for this specific probe
    except HTTPException:
        raise
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")
    return {"connected": True}


# ============================================================
# USER SIP PROVISIONING (admin)
# ============================================================


@router.get("/users")
async def list_users_with_sip(current_user: dict = Depends(require_admin)):
    """List all staff users + whether they have SIP creds set."""
    users_out: List[Dict[str, Any]] = []
    async for u in db.users.find({"status": {"$ne": "archived"}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "pbx": 1}):
        pbx = u.get("pbx") or {}
        users_out.append({
            "id": u["id"], "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role"),
            "extension": pbx.get("extension") or "",
            "display_name": pbx.get("display_name") or u.get("name") or "",
            "has_password": bool(pbx.get("sip_password_enc")),
        })
    users_out.sort(key=lambda r: (r.get("extension") or "zzz", r.get("name") or ""))
    return users_out


@router.put("/users/{user_id}/sip")
async def set_user_sip(user_id: str, data: UserSipIn, current_user: dict = Depends(require_admin)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "name": 1})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    # Uniqueness: an extension can only be assigned to one user (matches UCM reality).
    clash = await db.users.find_one({"id": {"$ne": user_id}, "pbx.extension": data.extension}, {"_id": 0, "id": 1})
    if clash:
        raise HTTPException(status_code=409, detail=f"Extension {data.extension} is already assigned to another user.")
    enc = await encrypt_password(db, data.sip_password)
    await db.users.update_one({"id": user_id}, {"$set": {"pbx": {
        "extension": data.extension.strip(),
        "sip_password_enc": enc,
        "display_name": (data.display_name or u.get("name") or "").strip(),
    }}})
    return {"updated": True}


@router.delete("/users/{user_id}/sip")
async def clear_user_sip(user_id: str, current_user: dict = Depends(require_admin)):
    r = await db.users.update_one({"id": user_id}, {"$unset": {"pbx": ""}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"cleared": True}


# ============================================================
# SELF-SERVICE (any authenticated user)
# ============================================================


@router.get("/me/sip-config")
async def my_sip_config(current_user: dict = Depends(get_current_user)):
    """Return the SIP creds + tenant WSS URL for THIS user's browser softphone."""
    u = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "pbx": 1, "name": 1}) or {}
    pbx = u.get("pbx") or {}
    if not pbx.get("extension") or not pbx.get("sip_password_enc"):
        return Response(status_code=204)
    cfg = await _get_config_doc()
    if not cfg.get("ws_url"):
        raise HTTPException(status_code=502, detail="VoIP is not configured for this tenant. Ask an admin to set up the UCM connection.")
    sip_password = await decrypt_password(db, pbx["sip_password_enc"])
    return {
        "extension": pbx["extension"],
        "sip_password": sip_password,
        "display_name": pbx.get("display_name") or u.get("name") or pbx["extension"],
        "sip_domain": cfg.get("sip_domain") or cfg.get("ucm_host") or "",
        "ws_url": cfg["ws_url"],
        "stun_urls": cfg.get("stun_urls") or [],
        "turn_urls": cfg.get("turn_urls") or [],
        "turn_username": cfg.get("turn_username") or "",
        "turn_password": cfg.get("turn_password") or "",
    }


@router.get("/me/directory")
async def my_directory(current_user: dict = Depends(get_current_user)):
    """Colleagues + their extensions for intra-office click-to-dial + presence."""
    rows: List[Dict[str, Any]] = []
    async for u in db.users.find({"status": {"$ne": "archived"}, "pbx.extension": {"$exists": True, "$ne": ""}},
                                  {"_id": 0, "id": 1, "name": 1, "role": 1, "avatar": 1, "pbx.extension": 1, "pbx.display_name": 1}):
        if u["id"] == current_user["id"]:
            continue
        pbx = u.get("pbx") or {}
        rows.append({
            "user_id": u["id"], "name": u.get("name") or "",
            "role": u.get("role") or "",
            "avatar": u.get("avatar") or "",
            "extension": pbx.get("extension") or "",
            "display_name": pbx.get("display_name") or u.get("name") or "",
        })
    rows.sort(key=lambda r: (r.get("name") or "").lower())
    return rows


@router.get("/me/voicemails")
async def my_voicemails(current_user: dict = Depends(get_current_user)):
    ext = await _current_user_ext(current_user)
    if not ext:
        return []
    try:
        client = await _ucm_from_config()
        return await client.list_voicemail(ext)
    except HTTPException:
        raise
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")


@router.get("/me/voicemails/{msg_id}/audio")
async def my_voicemail_audio(msg_id: str, current_user: dict = Depends(get_current_user)):
    ext = await _current_user_ext(current_user)
    if not ext:
        raise HTTPException(status_code=404, detail="You have no SIP extension configured.")
    try:
        client = await _ucm_from_config()
        audio = await client.download_voicemail(ext, msg_id)
        # Auto-mark as read once the browser has fetched the audio (matches
        # every other VOIP client's behaviour).
        try:
            await client.mark_voicemail_read(ext, msg_id)
        except UCMError:
            pass
        return Response(content=audio, media_type="audio/wav",
                        headers={"Content-Disposition": f'inline; filename="vm-{msg_id}.wav"'})
    except HTTPException:
        raise
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")


@router.post("/me/voicemails/{msg_id}/mark-read")
async def my_voicemail_mark_read(msg_id: str, current_user: dict = Depends(get_current_user)):
    ext = await _current_user_ext(current_user)
    if not ext:
        raise HTTPException(status_code=404, detail="You have no SIP extension configured.")
    try:
        client = await _ucm_from_config()
        await client.mark_voicemail_read(ext, msg_id)
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")
    return {"marked_read": True}


@router.delete("/me/voicemails/{msg_id}")
async def my_voicemail_delete(msg_id: str, current_user: dict = Depends(get_current_user)):
    ext = await _current_user_ext(current_user)
    if not ext:
        raise HTTPException(status_code=404, detail="You have no SIP extension configured.")
    try:
        client = await _ucm_from_config()
        await client.delete_voicemail(ext, msg_id)
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")
    return {"deleted": True}


@router.get("/me/call-history")
async def my_call_history(limit: int = 50, current_user: dict = Depends(get_current_user)):
    limit = max(1, min(int(limit or 50), 200))
    ext = await _current_user_ext(current_user)
    if not ext:
        return []
    try:
        client = await _ucm_from_config()
        return await client.list_cdr(ext, limit=limit)
    except HTTPException:
        raise
    except UCMError as e:
        raise HTTPException(status_code=502, detail=f"UCM: {e}")


# ============================================================
# BLF / PRESENCE (polled — sub-second SIP SUBSCRIBE happens client-side)
# ============================================================
# Cache the UCM listAccount response for a short window so N staff hitting
# /me/directory in the same 30 s don't fan out into N UCM calls.

_BLF_CACHE: Dict[str, Any] = {"at": 0.0, "rows": []}


@router.get("/blf")
async def blf_snapshot(current_user: dict = Depends(get_current_user)):
    """Return {extension: registered:bool} for every extension the UCM knows
    about. Cached 20 s. Used to draw green/red dots in the org directory —
    real-time on-call / ringing state comes from browser-side SIP SUBSCRIBE
    against the same UCM's dialog event package (see VoipContext.subscribeBlf)."""
    import time as _t
    now = _t.time()
    if now - _BLF_CACHE["at"] > 20:
        try:
            client = await _ucm_from_config()
            _BLF_CACHE["rows"] = await client.list_accounts()
            _BLF_CACHE["at"] = now
        except HTTPException:
            # Return the last successful snapshot (possibly empty) rather than
            # bubbling a 502 into every heartbeat call — the FE degrades gracefully.
            pass
        except UCMError:
            pass
    return {"registrations": _BLF_CACHE["rows"], "cached_age_sec": int(now - _BLF_CACHE["at"])}


@router.get("/me/voicemails/unread-count")
async def my_voicemail_unread_count(current_user: dict = Depends(get_current_user)):
    """Lightweight count for the sidebar badge. Falls back to 0 on any error."""
    ext = await _current_user_ext(current_user)
    if not ext:
        return {"unread": 0}
    try:
        client = await _ucm_from_config()
        items = await client.list_voicemail(ext)
        return {"unread": sum(1 for v in items if not v.get("is_read"))}
    except HTTPException:
        return {"unread": 0}
    except UCMError:
        return {"unread": 0}
