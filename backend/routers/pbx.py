"""In-app PBX management — Phase 1.

Builds and exposes a full PBX management layer on top of an Asterisk sidecar.
The Asterisk container lives in the self-hosted docker-compose appliance; this
FastAPI router is the *control plane* — it stores the canonical config in
MongoDB and renders Asterisk-flavoured `.conf` files on demand.

Object model
────────────
  extensions     — internal users (softphone, hardphone, WebRTC)
  trunks         — outbound + inbound SIP carriers
  inbound_routes — DID/pattern → extension|hunt_group|ivr|voicemail
  outbound_routes— pattern + priority → trunk (with strip/prepend)
  hunt_groups    — ringall|hunt|random|least-recent across N extensions
  ivrs           — DTMF menu: prompt → option N → destination
  voicemails     — per-extension mailbox (auto-created with extension)

Each entity has an `is_enabled` flag so admins can disable without delete.
Passwords / SIP secrets are generated with `secrets.token_urlsafe(18)` and
stored in cleartext — Asterisk needs the plaintext to authenticate REGISTER
requests. This is the standard PBX trade-off; mitigate by scoping `pbx_admin`
strictly via the `require_admin` dependency.

Live runtime control (AMI/ARI reload, hangup, originate) lands in Phase 2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Optional, List
import secrets
import uuid
import re
import os

from deps import db, require_admin

router = APIRouter(prefix="/api/pbx", tags=["pbx"])


# ============================================================
# Helpers
# ============================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_secret() -> str:
    """SIP auth secret — Asterisk-safe base64-url, 24 chars."""
    return secrets.token_urlsafe(18)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _validate_extension_number(num: str) -> str:
    """Internal extension — 2-6 digits, no leading zero."""
    if not re.fullmatch(r"[1-9][0-9]{1,5}", num or ""):
        raise HTTPException(status_code=400, detail="Extension must be 2-6 digits and not start with 0")
    return num


def _validate_pattern(pat: str) -> str:
    """Asterisk dialplan pattern: `_NXXNXXXXXX`, `_X.`, `_+1NXXNXXXXXX`, or literal digits."""
    p = (pat or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="Dial pattern required")
    # Allow literal digits + asterisk pattern syntax (underscore + N/X/Z/0-9/./[]/+)
    if not re.fullmatch(r"_?\+?[0-9NXZ\.\[\]\-]+", p):
        raise HTTPException(status_code=400, detail="Invalid dial pattern")
    return p


async def _next_extension_number(start: int = 100) -> str:
    """Find the next available extension number for the 'auto-pick' UI flow."""
    used = set()
    async for e in db.pbx_extensions.find({}, {"_id": 0, "number": 1}):
        used.add(e["number"])
    n = start
    while str(n) in used and n < 9999:
        n += 1
    return str(n)


# ============================================================
# EXTENSIONS — internal users (softphone / hardphone / WebRTC)
# ============================================================

@router.get("/extensions")
async def list_extensions(current_user: dict = Depends(require_admin)):
    """List all extensions (PIN + secret are returned — only admins can call this)."""
    out: List[dict] = []
    async for e in db.pbx_extensions.find({}, {"_id": 0}).sort("number", 1):
        out.append(e)
    return out


@router.post("/extensions")
async def create_extension(data: dict, current_user: dict = Depends(require_admin)):
    number = data.get("number") or await _next_extension_number()
    _validate_extension_number(number)
    if await db.pbx_extensions.find_one({"number": number}):
        raise HTTPException(status_code=400, detail=f"Extension {number} already exists")
    ext = {
        "id": _id("ext"),
        "number": number,
        "display_name": (data.get("display_name") or f"Extension {number}")[:80],
        "user_id": data.get("user_id") or None,
        "secret": _gen_secret(),                  # SIP auth — softphone uses this
        "transport": data.get("transport") or "transport-udp",
        "allowed_codecs": data.get("allowed_codecs") or ["ulaw", "alaw", "opus"],
        "max_contacts": int(data.get("max_contacts") or 3),
        "voicemail_enabled": bool(data.get("voicemail_enabled", True)),
        "voicemail_pin": str(data.get("voicemail_pin") or "".join([str(secrets.randbelow(10)) for _ in range(4)])),
        "voicemail_email": data.get("voicemail_email") or "",
        "outbound_caller_id": data.get("outbound_caller_id") or "",
        "is_enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pbx_extensions.insert_one(ext)
    return {k: v for k, v in ext.items() if k != "_id"}


@router.put("/extensions/{ext_id}")
async def update_extension(ext_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"display_name", "user_id", "transport", "allowed_codecs", "max_contacts",
               "voicemail_enabled", "voicemail_pin", "voicemail_email",
               "outbound_caller_id", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "number" in data:
        _validate_extension_number(data["number"])
        # uniqueness
        clash = await db.pbx_extensions.find_one({"number": data["number"], "id": {"$ne": ext_id}})
        if clash:
            raise HTTPException(status_code=400, detail=f"Extension {data['number']} already exists")
        update["number"] = data["number"]
    update["updated_at"] = _now()
    r = await db.pbx_extensions.update_one({"id": ext_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"updated": True}


@router.post("/extensions/{ext_id}/rotate-secret")
async def rotate_extension_secret(ext_id: str, current_user: dict = Depends(require_admin)):
    """Issue a fresh SIP secret — invalidates the user's existing softphone registration."""
    new_secret = _gen_secret()
    r = await db.pbx_extensions.update_one(
        {"id": ext_id}, {"$set": {"secret": new_secret, "updated_at": _now()}}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"secret": new_secret}


@router.delete("/extensions/{ext_id}")
async def delete_extension(ext_id: str, current_user: dict = Depends(require_admin)):
    # Detach any hunt-group membership referencing this extension
    await db.pbx_hunt_groups.update_many({}, {"$pull": {"member_extension_ids": ext_id}})
    r = await db.pbx_extensions.delete_one({"id": ext_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Extension not found")
    return {"deleted": True}


# ============================================================
# TRUNKS — outbound + inbound SIP carrier connections
# ============================================================

@router.get("/trunks")
async def list_trunks(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for t in db.pbx_trunks.find({}, {"_id": 0}).sort("created_at", 1):
        out.append(t)
    return out


@router.post("/trunks")
async def create_trunk(data: dict, current_user: dict = Depends(require_admin)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Trunk name required")
    host = (data.get("host") or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="SIP host required (e.g. sip.provider.com)")
    if data.get("register") and not (data.get("username") or "").strip():
        raise HTTPException(status_code=400, detail="register=true needs a SIP username (carrier requires AOR registration)")
    trunk = {
        "id": _id("trk"),
        "name": name[:60],
        "host": host[:200],
        "port": int(data.get("port") or 5060),
        "transport": data.get("transport") or "transport-udp",
        "username": (data.get("username") or "")[:80],
        "secret": (data.get("secret") or "")[:200],
        "auth_username": (data.get("auth_username") or data.get("username") or "")[:80],
        "from_user": (data.get("from_user") or data.get("username") or "")[:80],
        "from_domain": (data.get("from_domain") or host)[:200],
        "register": bool(data.get("register", True)),
        "did_numbers": data.get("did_numbers") or [],
        "outbound_caller_id": (data.get("outbound_caller_id") or "")[:80],
        "max_channels": int(data.get("max_channels") or 0),  # 0 = unlimited
        "allowed_codecs": data.get("allowed_codecs") or ["ulaw", "alaw"],
        "is_enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pbx_trunks.insert_one(trunk)
    return {k: v for k, v in trunk.items() if k != "_id"}


@router.put("/trunks/{trunk_id}")
async def update_trunk(trunk_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "host", "port", "transport", "username", "secret", "auth_username",
               "from_user", "from_domain", "register", "did_numbers", "outbound_caller_id",
               "max_channels", "allowed_codecs", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = _now()
    r = await db.pbx_trunks.update_one({"id": trunk_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Trunk not found")
    return {"updated": True}


@router.delete("/trunks/{trunk_id}")
async def delete_trunk(trunk_id: str, current_user: dict = Depends(require_admin)):
    # Detach any outbound routes pointing at this trunk
    await db.pbx_outbound_routes.update_many({"trunk_id": trunk_id}, {"$set": {"trunk_id": None}})
    await db.pbx_inbound_routes.delete_many({"trunk_id": trunk_id})
    r = await db.pbx_trunks.delete_one({"id": trunk_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trunk not found")
    return {"deleted": True}


# ============================================================
# INBOUND ROUTES — DID → destination
# ============================================================

@router.get("/inbound-routes")
async def list_inbound(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for r in db.pbx_inbound_routes.find({}, {"_id": 0}).sort("did_pattern", 1):
        out.append(r)
    return out


@router.post("/inbound-routes")
async def create_inbound(data: dict, current_user: dict = Depends(require_admin)):
    _validate_pattern(data.get("did_pattern"))
    dt = data.get("destination_type")
    if dt not in {"extension", "hunt_group", "ivr", "voicemail", "trunk", "hangup"}:
        raise HTTPException(status_code=400, detail="Invalid destination_type")
    route = {
        "id": _id("inb"),
        "name": (data.get("name") or "").strip()[:80] or f"Inbound {data['did_pattern']}",
        "did_pattern": data["did_pattern"],
        "trunk_id": data.get("trunk_id") or None,
        "destination_type": dt,
        "destination_id": data.get("destination_id") or None,
        # Time-of-day routing: list of {days, start, end, destination_type, destination_id}
        # Days are ISO 1..7 (Mon=1). Phase-2 will use this; Phase-1 just stores.
        "time_conditions": data.get("time_conditions") or [],
        "fallback_type": data.get("fallback_type") or "voicemail",
        "fallback_id": data.get("fallback_id") or None,
        "is_enabled": True,
        "created_at": _now(),
    }
    await db.pbx_inbound_routes.insert_one(route)
    return {k: v for k, v in route.items() if k != "_id"}


@router.put("/inbound-routes/{route_id}")
async def update_inbound(route_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "did_pattern", "trunk_id", "destination_type", "destination_id",
               "time_conditions", "fallback_type", "fallback_id", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "did_pattern" in update:
        _validate_pattern(update["did_pattern"])
    r = await db.pbx_inbound_routes.update_one({"id": route_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Inbound route not found")
    return {"updated": True}


@router.delete("/inbound-routes/{route_id}")
async def delete_inbound(route_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_inbound_routes.delete_one({"id": route_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Inbound route not found")
    return {"deleted": True}


# ============================================================
# OUTBOUND ROUTES — extension pattern → trunk
# ============================================================

@router.get("/outbound-routes")
async def list_outbound(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for r in db.pbx_outbound_routes.find({}, {"_id": 0}).sort("priority", 1):
        out.append(r)
    return out


@router.post("/outbound-routes")
async def create_outbound(data: dict, current_user: dict = Depends(require_admin)):
    _validate_pattern(data.get("pattern"))
    route = {
        "id": _id("out"),
        "name": (data.get("name") or "").strip()[:80] or f"Outbound {data['pattern']}",
        "pattern": data["pattern"],
        "trunk_id": data.get("trunk_id"),
        "priority": int(data.get("priority") or 100),
        # Manipulate digits before sending to trunk
        "strip": int(data.get("strip") or 0),          # Drop N leading digits from dialled string
        "prepend": (data.get("prepend") or "")[:20],  # Prefix to add
        "caller_id_override": (data.get("caller_id_override") or "")[:80],
        "allowed_extension_ids": data.get("allowed_extension_ids") or [],  # empty = all
        "is_enabled": True,
        "created_at": _now(),
    }
    if not route["trunk_id"]:
        raise HTTPException(status_code=400, detail="Outbound route needs a trunk")
    await db.pbx_outbound_routes.insert_one(route)
    return {k: v for k, v in route.items() if k != "_id"}


@router.put("/outbound-routes/{route_id}")
async def update_outbound(route_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "pattern", "trunk_id", "priority", "strip", "prepend",
               "caller_id_override", "allowed_extension_ids", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "pattern" in update:
        _validate_pattern(update["pattern"])
    r = await db.pbx_outbound_routes.update_one({"id": route_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Outbound route not found")
    return {"updated": True}


@router.delete("/outbound-routes/{route_id}")
async def delete_outbound(route_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_outbound_routes.delete_one({"id": route_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Outbound route not found")
    return {"deleted": True}


# ============================================================
# HUNT GROUPS — ring multiple extensions
# ============================================================

@router.get("/hunt-groups")
async def list_huntgroups(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for h in db.pbx_hunt_groups.find({}, {"_id": 0}).sort("name", 1):
        out.append(h)
    return out


@router.post("/hunt-groups")
async def create_huntgroup(data: dict, current_user: dict = Depends(require_admin)):
    if (data.get("strategy") or "ringall") not in {"ringall", "hunt", "random", "least_recent"}:
        raise HTTPException(status_code=400, detail="Invalid strategy")
    hg = {
        "id": _id("hg"),
        "name": (data.get("name") or "").strip()[:80] or "Hunt group",
        "strategy": data.get("strategy") or "ringall",
        "member_extension_ids": data.get("member_extension_ids") or [],
        "ring_timeout": int(data.get("ring_timeout") or 20),
        "fallback_type": data.get("fallback_type") or "voicemail",
        "fallback_id": data.get("fallback_id") or None,
        "is_enabled": True,
        "created_at": _now(),
    }
    await db.pbx_hunt_groups.insert_one(hg)
    return {k: v for k, v in hg.items() if k != "_id"}


@router.put("/hunt-groups/{hg_id}")
async def update_huntgroup(hg_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "strategy", "member_extension_ids", "ring_timeout",
               "fallback_type", "fallback_id", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    r = await db.pbx_hunt_groups.update_one({"id": hg_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hunt group not found")
    return {"updated": True}


@router.delete("/hunt-groups/{hg_id}")
async def delete_huntgroup(hg_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_hunt_groups.delete_one({"id": hg_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Hunt group not found")
    return {"deleted": True}


# ============================================================
# IVRs — DTMF menu
# ============================================================

@router.get("/ivrs")
async def list_ivrs(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for v in db.pbx_ivrs.find({}, {"_id": 0}).sort("name", 1):
        out.append(v)
    return out


@router.post("/ivrs")
async def create_ivr(data: dict, current_user: dict = Depends(require_admin)):
    ivr = {
        "id": _id("ivr"),
        "name": (data.get("name") or "").strip()[:80] or "IVR",
        "prompt_audio_url": data.get("prompt_audio_url") or "",
        "prompt_text": (data.get("prompt_text") or "")[:500],   # TTS fallback
        "options": data.get("options") or {},                   # {"1":{type:"extension",id:"..."}}
        "timeout_sec": int(data.get("timeout_sec") or 10),
        "max_retries": int(data.get("max_retries") or 2),
        "timeout_type": data.get("timeout_type") or "hangup",
        "timeout_id": data.get("timeout_id") or None,
        "invalid_type": data.get("invalid_type") or "hangup",
        "invalid_id": data.get("invalid_id") or None,
        "is_enabled": True,
        "created_at": _now(),
    }
    await db.pbx_ivrs.insert_one(ivr)
    return {k: v for k, v in ivr.items() if k != "_id"}


@router.put("/ivrs/{ivr_id}")
async def update_ivr(ivr_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "prompt_audio_url", "prompt_text", "options", "timeout_sec",
               "max_retries", "timeout_type", "timeout_id", "invalid_type", "invalid_id",
               "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    r = await db.pbx_ivrs.update_one({"id": ivr_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="IVR not found")
    return {"updated": True}


@router.delete("/ivrs/{ivr_id}")
async def delete_ivr(ivr_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_ivrs.delete_one({"id": ivr_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="IVR not found")
    return {"deleted": True}


# ============================================================
# Asterisk config rendering
# ============================================================

ASTERISK_INTERNAL_CONTEXT = "from-internal"
ASTERISK_INBOUND_CONTEXT = "from-trunk"


def _render_pjsip(extensions: List[dict], trunks: List[dict]) -> str:
    """Render `pjsip.conf` from extensions + trunks."""
    lines = [
        ";==============================================================",
        "; pjsip.conf — auto-generated by 58:12 Global Connect PBX",
        f"; Generated:  {_now()}",
        ";",
        "; DO NOT EDIT BY HAND. Regenerate via Admin → PBX → Apply config.",
        ";==============================================================",
        "",
        "[transport-udp]",
        "type=transport",
        "protocol=udp",
        "bind=0.0.0.0:5060",
        "",
        "[transport-tcp]",
        "type=transport",
        "protocol=tcp",
        "bind=0.0.0.0:5060",
        "",
        "[transport-wss]",
        "type=transport",
        "protocol=wss",
        "bind=0.0.0.0:8089",
        "",
    ]

    # Extensions (endpoints, aor, auth)
    for ext in extensions:
        if not ext.get("is_enabled", True):
            continue
        n = ext["number"]
        transport = ext.get("transport") or "transport-udp"
        codecs = ",".join(ext.get("allowed_codecs") or ["ulaw", "alaw"])
        webrtc = transport == "transport-wss"
        lines += [
            f"; --- Extension {n} ({ext.get('display_name', '')})  ---",
            f"[{n}]",
            "type=endpoint",
            f"transport={transport}",
            f"context={ASTERISK_INTERNAL_CONTEXT}",
            "disallow=all",
            f"allow={codecs}",
            f"aors={n}",
            f"auth={n}-auth",
            f"callerid={ext.get('display_name', n)} <{n}>",
        ]
        if webrtc:
            lines += [
                "webrtc=yes",
                "media_encryption=dtls",
                "dtls_auto_generate_cert=yes",
                "dtls_verify=fingerprint",
                "dtls_setup=actpass",
                "use_avpf=yes",
                "rtcp_mux=yes",
                "ice_support=yes",
            ]
        lines += [
            "",
            f"[{n}-auth]",
            "type=auth",
            "auth_type=userpass",
            f"username={n}",
            f"password={ext['secret']}",
            "",
            f"[{n}]",
            "type=aor",
            f"max_contacts={ext.get('max_contacts', 3)}",
            "qualify_frequency=60",
            "remove_existing=yes",
            "",
        ]

    # Trunks (one endpoint + aor + auth + registration block per trunk)
    for tr in trunks:
        if not tr.get("is_enabled", True):
            continue
        tid = tr["id"]
        host = tr["host"]
        port = tr.get("port", 5060)
        transport = tr.get("transport", "transport-udp")
        codecs = ",".join(tr.get("allowed_codecs") or ["ulaw", "alaw"])
        lines += [
            f"; --- Trunk {tr['name']} ({host}:{port}) ---",
            f"[trunk-{tid}]",
            "type=endpoint",
            f"transport={transport}",
            f"context={ASTERISK_INBOUND_CONTEXT}",
            "disallow=all",
            f"allow={codecs}",
            f"aors=trunk-{tid}",
        ]
        if tr.get("username"):
            lines += [
                f"auth=trunk-{tid}-auth",
                f"outbound_auth=trunk-{tid}-auth",
            ]
        lines += [
            f"from_user={tr.get('from_user') or tr.get('username', '')}",
            f"from_domain={tr.get('from_domain') or host}",
            "",
            f"[trunk-{tid}]",
            "type=aor",
            f"contact=sip:{host}:{port}",
            "qualify_frequency=60",
            "",
        ]
        if tr.get("username"):
            lines += [
                f"[trunk-{tid}-auth]",
                "type=auth",
                "auth_type=userpass",
                f"username={tr.get('auth_username') or tr['username']}",
                f"password={tr['secret']}",
                "",
            ]
        if tr.get("register") and tr.get("username"):
            lines += [
                f"[trunk-{tid}-reg]",
                "type=registration",
                f"transport={transport}",
                f"outbound_auth=trunk-{tid}-auth",
                f"server_uri=sip:{host}:{port}",
                f"client_uri=sip:{tr.get('username')}@{host}",
                "retry_interval=60",
                "",
            ]
    return "\n".join(ln for ln in lines if ln is not None) + "\n"


def _render_extensions(extensions: List[dict], trunks: List[dict],
                        inbound: List[dict], outbound: List[dict],
                        hunt_groups: List[dict], ivrs: List[dict]) -> str:
    """Render `extensions.conf` (dialplan)."""
    by_ext_id = {e["id"]: e for e in extensions}
    by_hg_id = {h["id"]: h for h in hunt_groups}

    def dest_dial(dt: str, did: str | None) -> List[str]:
        """Return Asterisk dialplan lines that route to the destination."""
        if dt == "extension":
            e = by_ext_id.get(did or "")
            if not e:
                return ["    exten => _X.,n,Hangup()"]
            return [f"    same => n,Dial(PJSIP/{e['number']},25)",
                    f"    same => n,Voicemail({e['number']}@default,u)" if e.get("voicemail_enabled") else "    same => n,Hangup()"]
        if dt == "hunt_group":
            h = by_hg_id.get(did or "")
            if not h:
                return ["    same => n,Hangup()"]
            members = [by_ext_id[m]["number"] for m in (h.get("member_extension_ids") or []) if m in by_ext_id]
            if not members:
                return ["    same => n,Hangup()"]
            dial_str = "&".join(f"PJSIP/{m}" for m in members) if h["strategy"] == "ringall" else "/".join(f"PJSIP/{m}" for m in members)
            return [f"    same => n,Dial({dial_str},{h.get('ring_timeout', 20)})"]
        if dt == "ivr":
            return [f"    same => n,Goto(ivr-{did},s,1)"]
        if dt == "voicemail":
            e = by_ext_id.get(did or "")
            if not e:
                return ["    same => n,Hangup()"]
            return [f"    same => n,Voicemail({e['number']}@default,u)"]
        if dt == "trunk":
            t = next((t for t in trunks if t["id"] == did), None)
            if not t:
                return ["    same => n,Hangup()"]
            return [f"    same => n,Dial(PJSIP/${{EXTEN}}@trunk-{t['id']},45)"]
        return ["    same => n,Hangup()"]

    lines = [
        ";==============================================================",
        "; extensions.conf — auto-generated by 58:12 Global Connect PBX",
        f"; Generated:  {_now()}",
        ";==============================================================",
        "",
        "[globals]",
        "",
        f"[{ASTERISK_INTERNAL_CONTEXT}]",
        "; ─── Internal extension-to-extension dialing ───",
    ]
    # Extension dial pattern: 2-6 digits
    enabled_exts = [e for e in extensions if e.get("is_enabled", True)]
    if enabled_exts:
        lines += [
            "exten => _XX.,1,NoOp(Internal call to ${EXTEN})",
            "    same => n,Set(CALLERID(name)=${CALLERID(num)})",
            "    same => n,Dial(PJSIP/${EXTEN},25)",
            "    same => n,Voicemail(${EXTEN}@default,u)",
            "    same => n,Hangup()",
            "",
        ]
    # Outbound routes (sorted by priority)
    for orte in sorted([o for o in outbound if o.get("is_enabled", True)], key=lambda x: x["priority"]):
        if not orte.get("trunk_id"):
            continue
        pat = orte["pattern"]
        strip = orte.get("strip", 0)
        prepend = orte.get("prepend", "")
        lines += [
            f"; Outbound route: {orte['name']}",
            f"exten => {pat},1,NoOp(Outbound via {orte['trunk_id']})",
        ]
        if orte.get("caller_id_override"):
            lines.append(f"    same => n,Set(CALLERID(all)={orte['caller_id_override']})")
        dial_target = "${EXTEN}"
        if strip:
            dial_target = "${EXTEN:" + str(strip) + "}"
        if prepend:
            dial_target = prepend + dial_target
        lines += [
            f"    same => n,Dial(PJSIP/{dial_target}@trunk-{orte['trunk_id']},60)",
            "    same => n,Hangup()",
            "",
        ]

    # Inbound context — match DID to inbound route destination
    lines += [
        "",
        f"[{ASTERISK_INBOUND_CONTEXT}]",
        "; ─── Inbound calls from carrier trunks ───",
    ]
    for ir in [i for i in inbound if i.get("is_enabled", True)]:
        lines += [
            f"; Inbound: {ir['name']}",
            f"exten => {ir['did_pattern']},1,NoOp(Inbound to {ir['destination_type']} {ir.get('destination_id')})",
            "    same => n,Answer()",
        ]
        # Time-of-day conditions: when the current time matches, route to the override
        # destination defined on the condition. Asterisk's GotoIfTime() makes this
        # native — we generate one check per condition, falling through to the
        # default destination at the end.
        for idx, cond in enumerate(ir.get("time_conditions") or []):
            try:
                start = (cond.get("start") or "00:00").strip()
                end = (cond.get("end") or "23:59").strip()
                # Days: ISO 1..7 Mon..Sun → Asterisk day-of-week tokens
                day_map = {1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat", 7: "sun"}
                days_iso = cond.get("days") or [1, 2, 3, 4, 5]
                days_tokens = [day_map[int(d)] for d in days_iso if int(d) in day_map]
                days_spec = "&".join(days_tokens) if days_tokens else "*"
                # Asterisk wants times as HH:MM-HH:MM and days as csv (mon&tue&...).
                label = f"tc{idx}"
                lines.append(f"    same => n,GotoIf($[\"${{DIALPLAN_EXIT}}\" = \"1\"]?:tc-{idx})")
                lines.append(f"    same => n({label}),GotoIfTime({start}-{end},{days_spec},*,*?tc-{idx}-active)")
                lines.append(f"    same => n,Goto(tc-{idx}-skip)")
                lines.append(f"    same => n(tc-{idx}-active),NoOp(Time condition {idx} matched)")
                for ln in dest_dial(cond.get("destination_type"), cond.get("destination_id")):
                    lines.append(ln)
                lines.append("    same => n,Hangup()")
                lines.append(f"    same => n(tc-{idx}-skip),NoOp(skipping)")
                lines.append(f"    same => n(tc-{idx}),NoOp(continue)")
            except Exception:
                continue
        lines += dest_dial(ir["destination_type"], ir.get("destination_id"))
        lines.append("    same => n,Hangup()")
        lines.append("")

    # IVR contexts
    for ivr in [i for i in ivrs if i.get("is_enabled", True)]:
        lines += [
            f"; ─── IVR: {ivr['name']} ───",
            f"[ivr-{ivr['id']}]",
            "exten => s,1,Answer()",
            f"    same => n,Set(IVR_RETRIES={ivr.get('max_retries', 2)})",
            "    same => n(menu),NoOp(IVR menu)",
        ]
        if ivr.get("prompt_audio_url"):
            lines.append(f"    same => n,Playback({ivr['prompt_audio_url']})")
        else:
            txt = (ivr.get("prompt_text") or "Please make a selection").replace('"', "'")
            lines.append(f"    same => n,Festival(\"{txt}\")")  # falls back to TTS
        lines.append(f"    same => n,WaitExten({ivr.get('timeout_sec', 10)})")
        lines.append("")
        for key, opt in (ivr.get("options") or {}).items():
            if not isinstance(opt, dict):
                continue
            lines.append(f"exten => {key},1,NoOp(IVR option {key})")
            lines += dest_dial(opt.get("type"), opt.get("id"))
            lines.append("    same => n,Hangup()")
            lines.append("")
        # invalid + timeout
        lines += [
            "exten => i,1,NoOp(Invalid IVR option)",
            "    same => n,Set(IVR_RETRIES=$[${IVR_RETRIES} - 1])",
            "    same => n,GotoIf($[${IVR_RETRIES} > 0]?s,menu)",
        ]
        lines += dest_dial(ivr.get("invalid_type") or "hangup", ivr.get("invalid_id"))
        lines += [
            "    same => n,Hangup()",
            "exten => t,1,NoOp(IVR timeout)",
        ]
        lines += dest_dial(ivr.get("timeout_type") or "hangup", ivr.get("timeout_id"))
        lines += ["    same => n,Hangup()", ""]

    return "\n".join(lines) + "\n"


def _render_voicemail(extensions: List[dict]) -> str:
    """Render `voicemail.conf`."""
    lines = [
        ";==============================================================",
        "; voicemail.conf — auto-generated by 58:12 Global Connect PBX",
        f"; Generated:  {_now()}",
        ";==============================================================",
        "",
        "[general]",
        "format=wav49|wav|gsm",
        "serveremail=pbx@5812.local",
        "attach=yes",
        "maxmsg=100",
        "maxsecs=300",
        "minsecs=2",
        "",
        "[default]",
    ]
    for ext in extensions:
        if not ext.get("voicemail_enabled", True):
            continue
        pin = ext.get("voicemail_pin", "1234")
        name = ext.get("display_name") or f"Extension {ext['number']}"
        email = ext.get("voicemail_email") or ""
        lines.append(f"{ext['number']} => {pin},{name},{email}")
    return "\n".join(lines) + "\n"


async def _get_all_pbx_state() -> dict:
    """Fetch the canonical PBX state from MongoDB."""
    return {
        "extensions": [e async for e in db.pbx_extensions.find({}, {"_id": 0})],
        "trunks": [t async for t in db.pbx_trunks.find({}, {"_id": 0})],
        "inbound": [i async for i in db.pbx_inbound_routes.find({}, {"_id": 0})],
        "outbound": [o async for o in db.pbx_outbound_routes.find({}, {"_id": 0})],
        "hunt_groups": [h async for h in db.pbx_hunt_groups.find({}, {"_id": 0})],
        "ivrs": [v async for v in db.pbx_ivrs.find({}, {"_id": 0})],
    }


@router.get("/config/{filename}")
async def get_config_file(filename: str, current_user: dict = Depends(require_admin)):
    """Render and return a single Asterisk config file as plain text.
    Supported filenames: pjsip.conf, extensions.conf, voicemail.conf, all.tar.
    Asterisk on the appliance pulls these via the same admin token over the
    self-hosted REST URL — no extra secret to manage."""
    state = await _get_all_pbx_state()
    if filename == "pjsip.conf":
        body = _render_pjsip(state["extensions"], state["trunks"])
    elif filename == "extensions.conf":
        body = _render_extensions(state["extensions"], state["trunks"], state["inbound"],
                                  state["outbound"], state["hunt_groups"], state["ivrs"])
    elif filename == "voicemail.conf":
        body = _render_voicemail(state["extensions"])
    else:
        raise HTTPException(status_code=404, detail="Unknown config file")
    return Response(content=body, media_type="text/plain",
                    headers={"Content-Disposition": f"inline; filename={filename}"})


@router.get("/config-bundle")
async def get_config_bundle(current_user: dict = Depends(require_admin)):
    """Return all three config files in one JSON blob — useful for the FE preview."""
    state = await _get_all_pbx_state()
    return {
        "pjsip.conf": _render_pjsip(state["extensions"], state["trunks"]),
        "extensions.conf": _render_extensions(state["extensions"], state["trunks"], state["inbound"],
                                              state["outbound"], state["hunt_groups"], state["ivrs"]),
        "voicemail.conf": _render_voicemail(state["extensions"]),
        "generated_at": _now(),
        "counts": {
            "extensions": len(state["extensions"]),
            "trunks": len(state["trunks"]),
            "inbound": len(state["inbound"]),
            "outbound": len(state["outbound"]),
            "hunt_groups": len(state["hunt_groups"]),
            "ivrs": len(state["ivrs"]),
        },
    }


@router.get("/registrations")
async def list_registrations(current_user: dict = Depends(require_admin)):
    """Live registration status from Asterisk AMI (when configured), merged
    with the DB roster so the UI always has *something* to render even when
    the appliance is unreachable.

    Each extension row will get `registered: true` + `user_agent: 'Yealink T48S'`
    when AMI returns a matching ContactList event for it. Trunks get
    `registered: true` from PJSIPShowRegistrationsOutbound.Status='Registered'.
    """
    from pbx_ami import safe_list_registrations
    state = await _get_all_pbx_state()
    live = await safe_list_registrations()
    contacts_by_aor: dict[str, dict] = {}
    for c in live.get("contacts") or []:
        # Each ContactList event has AOR like "endpoint/contactURI" — we only
        # care about the endpoint portion (i.e. the extension number).
        aor = (c.get("AOR") or "").split("/")[0]
        if aor:
            contacts_by_aor[aor] = c
    trunk_reg_by_id: dict[str, dict] = {}
    for tr in live.get("trunk_regs") or []:
        # Outbound registration event has ObjectName like 'trunk-trk_abc123-reg'
        obj = tr.get("ObjectName") or ""
        if obj.startswith("trunk-") and obj.endswith("-reg"):
            tid = obj[len("trunk-"):-len("-reg")]
            trunk_reg_by_id[tid] = tr
    extensions = [{
        "id": e["id"],
        "number": e["number"],
        "display_name": e.get("display_name"),
        "registered": e["number"] in contacts_by_aor,
        "user_agent": (contacts_by_aor.get(e["number"]) or {}).get("UserAgent", ""),
        "contact_uri": (contacts_by_aor.get(e["number"]) or {}).get("URI", ""),
        "roundtrip_ms": _to_ms((contacts_by_aor.get(e["number"]) or {}).get("RoundtripUsec")),
    } for e in state["extensions"]]
    trunks = [{
        "id": t["id"],
        "name": t["name"],
        "host": t["host"],
        "registered": (trunk_reg_by_id.get(t["id"]) or {}).get("Status") == "Registered",
        "status_text": (trunk_reg_by_id.get(t["id"]) or {}).get("Status", ""),
    } for t in state["trunks"]]
    return {
        "extensions": extensions,
        "trunks": trunks,
        "live": live.get("live", False),
        "reason": live.get("reason", ""),
    }


def _to_ms(usec: Optional[str]) -> Optional[int]:
    try:
        return int(int(usec) / 1000) if usec else None
    except Exception:
        return None


@router.post("/apply")
async def apply_config(current_user: dict = Depends(require_admin)):
    """Trigger a live `core reload` on the appliance Asterisk via AMI.
    Falls back to a 'skipped' status when AMI isn't configured (e.g. when
    you're running the management UI in a pod that can't reach the SIP host)."""
    from pbx_ami import safe_reload
    result = await safe_reload()
    return {
        "applied": result.get("reloaded", False),
        "ami_response": result,
        "config_urls": {
            "pjsip": "/api/pbx/config/pjsip.conf",
            "extensions": "/api/pbx/config/extensions.conf",
            "voicemail": "/api/pbx/config/voicemail.conf",
        },
    }


@router.post("/originate")
async def originate_call(data: dict, current_user: dict = Depends(require_admin)):
    """Click-to-call. AMI Originate rings the operator's extension first; on
    answer Asterisk bridges them to the target number through the matching
    outbound route.

    Body: { from_extension: '101', to_number: '+15551234567', caller_id?: 'Connect Op <+15551234567>' }
    """
    from pbx_ami import safe_originate, AMIError
    from_ext = (data.get("from_extension") or "").strip()
    to_num = (data.get("to_number") or "").strip()
    if not from_ext or not to_num:
        raise HTTPException(status_code=400, detail="from_extension + to_number required")
    e = await db.pbx_extensions.find_one({"number": from_ext}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail=f"Extension {from_ext} not found")
    caller_id = data.get("caller_id") or e.get("outbound_caller_id") or f"{e.get('display_name', from_ext)} <{from_ext}>"
    try:
        r = await safe_originate(
            channel=f"PJSIP/{from_ext}",
            exten=to_num,
            context=ASTERISK_INTERNAL_CONTEXT,    # outbound routes live here
            caller_id=caller_id,
            variables={"CONNECT_ORIGINATOR": current_user.get("id") or "system"},
        )
    except AMIError as ex:
        raise HTTPException(status_code=503, detail=str(ex))
    return {"originated": True, "ami_response": r}


# ============================================================
# Softphone helper endpoints (Phase 2)
# ============================================================

@router.get("/me/softphone")
async def get_my_softphone(
    current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user),
):
    """Return the calling user's SIP credentials for the in-browser softphone.

    The first WebRTC-transport extension assigned to this user (via
    pbx_extensions.user_id) wins. If the user has no extension, returns 204.
    """
    ext = await db.pbx_extensions.find_one(
        {"user_id": current_user["id"], "transport": "transport-wss", "is_enabled": True},
        {"_id": 0},
    )
    if not ext:
        return Response(status_code=204)
    return {
        "extension": ext["number"],
        "display_name": ext.get("display_name") or ext["number"],
        "secret": ext["secret"],
        # WebRTC connects to Asterisk over WSS — appliance Caddy proxies /ws → asterisk:8089
        "ws_url": os.environ.get("PBX_WS_URL", ""),
        "sip_uri": f"sip:{ext['number']}@{os.environ.get('PBX_SIP_DOMAIN', '5812.lubwamas.org')}",
        "sip_domain": os.environ.get("PBX_SIP_DOMAIN", "5812.lubwamas.org"),
        "stun_url": os.environ.get("PBX_STUN_URL", "stun:stun.l.google.com:19302"),
        "allowed_codecs": ext.get("allowed_codecs") or ["opus", "ulaw"],
    }


@router.get("/me/click-to-call-config")
async def get_my_call_config(
    current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user),
):
    """Lightweight: just the user's extension number for the call buttons.
    Returns 204 when the user has no extension."""
    ext = await db.pbx_extensions.find_one(
        {"user_id": current_user["id"], "is_enabled": True},
        {"_id": 0, "number": 1, "display_name": 1, "transport": 1},
    )
    if not ext:
        return Response(status_code=204)
    return {
        "extension": ext["number"],
        "display_name": ext.get("display_name") or ext["number"],
        "is_softphone": ext.get("transport") == "transport-wss",
    }


@router.get("/phone-lookup")
async def phone_lookup(
    number: str,
    current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user),
):
    """Reverse-lookup a phone number across CRM records — the backbone of the
    softphone "screen pop" feature.

    Strategy: strip non-digit characters from both sides and match on the last
    7 digits (handles country-code variance — '+1 555 010 0123' should match
    '555-010-0123' too). Searches in priority order: members → users → guests
    → families → children's parent phones. Returns the first hit so the
    softphone can route the user straight to that record on incoming calls.
    """
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) < 4:
        raise HTTPException(status_code=400, detail="Need at least 4 digits to match")
    suffix = digits[-7:] if len(digits) >= 7 else digits
    # Regex anchored at end-of-string, ignoring punctuation. Use the same suffix
    # for all collections so the cache is meaningful at the route level.
    suffix_pattern = re.compile(re.escape(suffix) + r"\D*$")

    async def first_match(coll: str, link_route: str, name_field: str = "name",
                          id_field: str = "id", extra_fields: Optional[list] = None) -> Optional[dict]:
        proj = {"_id": 0, id_field: 1, name_field: 1, "phone": 1}
        for f in (extra_fields or []):
            proj[f] = 1
        doc = await db[coll].find_one({"phone": {"$regex": suffix_pattern}}, proj)
        if not doc:
            return None
        return {
            "kind": link_route.strip("/").rstrip("s"),  # 'member' / 'guest' / etc
            "id": doc.get(id_field),
            "name": doc.get(name_field) or "—",
            "phone": doc.get("phone") or "",
            "link": f"/{link_route}/{doc.get(id_field)}",
            **{k: doc[k] for k in (extra_fields or []) if doc.get(k) is not None},
        }

    # Search order is deliberate: members > registered users > guests > families
    candidates = [
        ("members", "people"),
        ("users", "admin/users"),
        ("guests", "people"),
        ("families", "people"),
    ]
    for coll, route in candidates:
        hit = await first_match(coll, route)
        if hit:
            return hit
    # Children: their parents' phone is on the family record — already covered above.
    return {"kind": None, "name": "Unknown", "phone": digits, "link": None}
