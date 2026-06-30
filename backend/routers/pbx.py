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
#
# The pure (no-DB) validation / id-generation helpers live in
# `pbx_helpers.py`. We import + alias them under the older underscore
# names so the rest of this router file doesn't need to be touched.

from pbx_helpers import (  # noqa: E402  -- intentional re-exports
    pbx_now as _now,
    gen_pbx_secret as _gen_secret,
    pbx_id as _id,
    validate_extension_number as _validate_extension_number,
    validate_pattern as _validate_pattern,
)


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
    # max_contacts: how many concurrent SIP registrations are allowed. The
    # browser softphone counts as one; desk phone, mobile JsSIP, etc. each add
    # one. -1 means unlimited (use sparingly — Asterisk caps at ~10 in practice).
    mc = data.get("max_contacts")
    max_contacts = -1 if (mc == -1 or str(mc).strip() in ("", "-1", "unlimited")) else int(mc or 5)
    ext = {
        "id": _id("ext"),
        "number": number,
        "display_name": (data.get("display_name") or f"Extension {number}")[:80],
        "user_id": data.get("user_id") or None,
        "secret": _gen_secret(),                  # SIP auth — softphone uses this
        "transport": data.get("transport") or "transport-udp",
        "allowed_codecs": data.get("allowed_codecs") or ["ulaw", "alaw", "opus"],
        "max_contacts": max_contacts,
        "voicemail_enabled": bool(data.get("voicemail_enabled", True)),
        "voicemail_pin": str(data.get("voicemail_pin") or "".join([str(secrets.randbelow(10)) for _ in range(4)])),
        "voicemail_email": data.get("voicemail_email") or "",
        "outbound_caller_id": data.get("outbound_caller_id") or "",
        # Per-extension call recording. Renders MixMonitor() in the dialplan.
        "recording_enabled": bool(data.get("recording_enabled", False)),
        # Skill tags for queue routing. Free-form strings, e.g. ["spanish","tier-2"].
        "skills": list(data.get("skills") or []),
        # Forwarding: dial this PSTN number through the configured trunk when ext doesn't answer.
        "forwarding_number": (data.get("forwarding_number") or "").strip(),
        # Fax-enabled extensions accept fax media (T.38) and email PDF to voicemail_email
        "is_fax_extension": bool(data.get("is_fax_extension", False)),
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
               "outbound_caller_id", "recording_enabled", "skills",
               "forwarding_number", "is_fax_extension", "is_enabled"}
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
        # trunk_type: 'sip' (default — VoIP carrier) | 'fxo' (analog line via ATA gateway)
        "trunk_type": data.get("trunk_type") or "sip",
        "host": host[:200],
        # SIP registrar domain — many carriers expose `register => proxy.example.com`
        # but require Auth-Realm + From-URI to use `sip.example.com`. When set,
        # pjsip.conf uses this for the registrar; falls back to `host` when empty.
        "registrar": (data.get("registrar") or "")[:200],
        "port": int(data.get("port") or 5060),
        "transport": data.get("transport") or "transport-udp",
        "username": (data.get("username") or "")[:80],
        "secret": (data.get("secret") or "")[:200],
        "auth_username": (data.get("auth_username") or data.get("username") or "")[:80],
        "from_user": (data.get("from_user") or data.get("username") or "")[:80],
        "from_domain": (data.get("from_domain") or host)[:200],
        # FXO-specific: number of analog lines (channels) and the ATA gateway host:port
        "fxo_lines": int(data.get("fxo_lines") or 0),
        "fxo_gateway": (data.get("fxo_gateway") or "")[:200],
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
    allowed = {"name", "trunk_type", "host", "registrar", "port", "transport", "username", "secret", "auth_username",
               "from_user", "from_domain", "fxo_lines", "fxo_gateway", "register", "did_numbers", "outbound_caller_id",
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
    if dt not in {"extension", "hunt_group", "ivr", "queue", "voicemail", "trunk", "hangup"}:
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
        # member_priorities: {ext_id: priority_int}. Lower = rings first.
        # Used by the dialplan to order members within a 'hunt' strategy and
        # to group concurrent rings (band 1, then band 2, etc) for 'ringall'.
        "member_priorities": data.get("member_priorities") or {},
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
    allowed = {"name", "strategy", "member_extension_ids", "member_priorities",
               "ring_timeout", "fallback_type", "fallback_id", "is_enabled"}
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
# QUEUES — skill-based call routing
# ============================================================
# A queue rings a set of agents (extensions) according to a strategy. Optionally
# requires callers to match one or more skills; only agents whose `skills` list
# includes ALL required skills will be rung. Falls back to a configurable
# destination on timeout / no-agents-available.

_QUEUE_STRATEGIES = {"ringall", "leastrecent", "fewestcalls", "random", "rrmemory", "linear"}


@router.get("/queues")
async def list_queues(current_user: dict = Depends(require_admin)):
    out: List[dict] = []
    async for q in db.pbx_queues.find({}, {"_id": 0}).sort("name", 1):
        out.append(q)
    return out


@router.post("/queues")
async def create_queue(data: dict, current_user: dict = Depends(require_admin)):
    strategy = (data.get("strategy") or "ringall").strip()
    if strategy not in _QUEUE_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Invalid strategy. Use one of: {sorted(_QUEUE_STRATEGIES)}")
    q = {
        "id": _id("q"),
        "name": (data.get("name") or "").strip()[:80] or "Queue",
        "extension_number": (data.get("extension_number") or "").strip() or None,  # Optional internal dial
        "strategy": strategy,
        "agent_extension_ids": list(data.get("agent_extension_ids") or []),
        # agent_priorities: {ext_id: priority_int}. Lower priority numbers ring
        # first; agents in the same band ring concurrently (per strategy).
        "agent_priorities": data.get("agent_priorities") or {},
        "required_skills": list(data.get("required_skills") or []),
        "ring_timeout": int(data.get("ring_timeout") or 20),
        "wrapup_time": int(data.get("wrapup_time") or 5),
        "max_wait": int(data.get("max_wait") or 120),
        "moh_class": (data.get("moh_class") or "default").strip()[:40],
        "announce_position": bool(data.get("announce_position", False)),
        "announce_holdtime": bool(data.get("announce_holdtime", False)),
        "fallback_type": data.get("fallback_type") or "voicemail",
        "fallback_id": data.get("fallback_id") or None,
        "is_enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    if q["extension_number"]:
        _validate_extension_number(q["extension_number"])
        clash = await db.pbx_extensions.find_one({"number": q["extension_number"]})
        if clash:
            raise HTTPException(status_code=400, detail=f"Extension {q['extension_number']} is already a phone")
    await db.pbx_queues.insert_one(q)
    return {k: v for k, v in q.items() if k != "_id"}


@router.put("/queues/{q_id}")
async def update_queue(q_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "extension_number", "strategy", "agent_extension_ids", "agent_priorities", "required_skills",
               "ring_timeout", "wrapup_time", "max_wait", "moh_class",
               "announce_position", "announce_holdtime", "fallback_type", "fallback_id", "is_enabled"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "strategy" in update and update["strategy"] not in _QUEUE_STRATEGIES:
        raise HTTPException(status_code=400, detail="Invalid strategy")
    if "extension_number" in update and update["extension_number"]:
        _validate_extension_number(update["extension_number"])
    update["updated_at"] = _now()
    r = await db.pbx_queues.update_one({"id": q_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Queue not found")
    return {"updated": True}


@router.delete("/queues/{q_id}")
async def delete_queue(q_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_queues.delete_one({"id": q_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Queue not found")
    # Detach from inbound routes
    await db.pbx_inbound_routes.update_many(
        {"destination_type": "queue", "destination_id": q_id},
        {"$set": {"destination_type": "hangup", "destination_id": None}}
    )
    return {"deleted": True}


# ============================================================
# RECORDING SETTINGS — global retention policy
# ============================================================

@router.get("/recording-settings")
async def get_recording_settings(current_user: dict = Depends(require_admin)):
    doc = await db.pbx_settings.find_one({"id": "recording"}, {"_id": 0}) or {}
    return {
        "retention_days": int(doc.get("retention_days") or 30),
        "storage_path": doc.get("storage_path") or "/var/spool/asterisk/monitor",
        "format": doc.get("format") or "wav",
        "stereo": bool(doc.get("stereo", True)),
        "announce_recording": bool(doc.get("announce_recording", False)),
    }


@router.put("/recording-settings")
async def set_recording_settings(data: dict, current_user: dict = Depends(require_admin)):
    update = {
        "id": "recording",
        "retention_days": int(data.get("retention_days") or 30),
        "storage_path": (data.get("storage_path") or "/var/spool/asterisk/monitor").strip()[:200],
        "format": data.get("format") or "wav",
        "stereo": bool(data.get("stereo", True)),
        "announce_recording": bool(data.get("announce_recording", False)),
        "updated_at": _now(),
    }
    if update["format"] not in ("wav", "wav49", "gsm", "g722"):
        raise HTTPException(status_code=400, detail="Format must be wav, wav49, gsm, or g722")
    await db.pbx_settings.update_one({"id": "recording"}, {"$set": update}, upsert=True)
    return {"updated": True, **{k: v for k, v in update.items() if k not in ("id", "updated_at")}}


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
ASTERISK_OUTBOUND_CONTEXT = "from-internal"   # outbound routes live in the same context


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
            # max_contacts: -1 (unlimited in our model) maps to a very large
            # number for Asterisk; otherwise pass through verbatim.
            f"max_contacts={50 if int(ext.get('max_contacts', 5)) == -1 else int(ext.get('max_contacts', 5))}",
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
            # Use the separate registrar domain if set, otherwise fall back to host
            registrar = (tr.get("registrar") or "").strip() or host
            lines += [
                f"[trunk-{tid}-reg]",
                "type=registration",
                f"transport={transport}",
                f"outbound_auth=trunk-{tid}-auth",
                f"server_uri=sip:{registrar}:{port}",
                f"client_uri=sip:{tr.get('username')}@{registrar}",
                "retry_interval=60",
                "",
            ]
    return "\n".join(ln for ln in lines if ln is not None) + "\n"


def _render_extensions(extensions: List[dict], trunks: List[dict],
                        inbound: List[dict], outbound: List[dict],
                        hunt_groups: List[dict], ivrs: List[dict],
                        queues: Optional[List[dict]] = None,
                        recording_settings: Optional[dict] = None) -> str:
    """Render `extensions.conf` (dialplan)."""
    by_ext_id = {e["id"]: e for e in extensions}
    by_hg_id = {h["id"]: h for h in hunt_groups}
    by_q_id = {q["id"]: q for q in (queues or [])}
    rec_fmt = (recording_settings or {}).get("format", "wav")
    rec_announce = (recording_settings or {}).get("announce_recording", False)

    def _maybe_record(ext: dict) -> List[str]:
        """If the extension has recording_enabled, prefix the Dial with a
        MixMonitor() that writes <call_id>.<fmt> into the spool. The CDR row's
        `call_id` is also derived from CALLID so the recording can be linked
        back to the CDR entry on the analytics page."""
        if not ext.get("recording_enabled"):
            return []
        out = []
        if rec_announce:
            out.append("    same => n,Playback(beep)")
        out.append(f"    same => n,MixMonitor(${{UNIQUEID}}.{rec_fmt},b)")
        return out

    def dest_dial(dt: str, did: str | None) -> List[str]:
        """Return Asterisk dialplan lines that route to the destination."""
        if dt == "extension":
            e = by_ext_id.get(did or "")
            if not e:
                return ["    exten => _X.,n,Hangup()"]
            # Fax-enabled extensions: route the call into ReceiveFAX, then email
            # the resulting TIFF/PDF to the extension's voicemail_email.
            if e.get("is_fax_extension"):
                fax_email = e.get("voicemail_email") or ""
                fax_lines = [
                    "    same => n,Set(FAXOPT(ecm)=yes)",
                    f"    same => n,Set(FAXOPT(headerinfo)=Fax for {e.get('display_name', e['number'])})",
                    "    same => n,ReceiveFAX(/var/spool/asterisk/fax/${UNIQUEID}.tif)",
                ]
                if fax_email:
                    # Email shellout — Asterisk includes the file via the
                    # MailMessage System() helper. Production may swap for an
                    # async worker that uses our /api/* email helpers instead.
                    fax_lines.append(
                        f"    same => n,System(/usr/local/bin/fax2email.sh ${{UNIQUEID}} {fax_email})"
                    )
                fax_lines.append("    same => n,Hangup()")
                return fax_lines
            lines = _maybe_record(e)
            lines.append(f"    same => n,Dial(PJSIP/{e['number']},25)")
            # Forwarding fallback when the extension doesn't answer
            forwarding = (e.get("forwarding_number") or "").strip()
            if forwarding:
                # Dial out via the first enabled trunk; if none, fall through to VM
                lines.append(f"    same => n,Dial(Local/{forwarding}@{ASTERISK_OUTBOUND_CONTEXT},25)")
            lines.append(f"    same => n,Voicemail({e['number']}@default,u)" if e.get("voicemail_enabled") else "    same => n,Hangup()")
            return lines
        if dt == "hunt_group":
            h = by_hg_id.get(did or "")
            if not h:
                return ["    same => n,Hangup()"]
            # Order members by priority bands. ringall: all bands ring at once.
            # hunt/linear: bands ring in sequence, all in the same band ring concurrently.
            priorities = h.get("member_priorities") or {}
            members_with_p = [(by_ext_id[m]["number"], priorities.get(m, 99))
                              for m in (h.get("member_extension_ids") or []) if m in by_ext_id]
            if not members_with_p:
                return ["    same => n,Hangup()"]
            members_with_p.sort(key=lambda x: x[1])
            timeout = h.get("ring_timeout", 20)
            if h["strategy"] == "ringall":
                # All members rung simultaneously regardless of priority band
                dial_str = "&".join(f"PJSIP/{n}" for n, _ in members_with_p)
                return [f"    same => n,Dial({dial_str},{timeout})"]
            # Sequential bands: ring each band of equal-priority members, then next band
            out: List[str] = []
            from itertools import groupby
            for _, group in groupby(members_with_p, key=lambda x: x[1]):
                band = list(group)
                dial_str = "&".join(f"PJSIP/{n}" for n, _ in band)
                out.append(f"    same => n,Dial({dial_str},{timeout})")
            return out
        if dt == "ivr":
            return [f"    same => n,Goto(ivr-{did},s,1)"]
        if dt == "queue":
            q = by_q_id.get(did or "")
            if not q:
                return ["    same => n,Hangup()"]
            # Append fallback after the Queue() call so callers exit cleanly when
            # all agents are unavailable or the wait timer expires.
            out_lines = [f"    same => n,Queue(q-{q['id']},t,,,{q.get('max_wait', 120)})"]
            fb_type = q.get("fallback_type")
            fb_id = q.get("fallback_id")
            if fb_type and fb_type != "hangup":
                # Recurse into dest_dial for the fallback target. Guards against
                # cyclic queue→queue chains by short-circuiting to hangup.
                if fb_type != "queue":
                    out_lines.extend(dest_dial(fb_type, fb_id))
                else:
                    out_lines.append("    same => n,Hangup()")
            out_lines.append("    same => n,Hangup()")
            return out_lines
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


def _render_queues(queues: List[dict], extensions: List[dict]) -> str:
    """Render `queues.conf`. Each queue maps to a `[q-<id>]` section. Members
    that don't carry every required skill are silently skipped — this is the
    backbone of skill-based routing in Asterisk app_queue."""
    by_ext_id = {e["id"]: e for e in extensions}
    lines = [
        ";==============================================================",
        "; queues.conf — auto-generated by 58:12 Global Connect PBX",
        f"; Generated:  {_now()}",
        ";==============================================================",
        "",
        "[general]",
        "persistentmembers = yes",
        "monitor-type = MixMonitor",
        "",
    ]
    for q in [x for x in queues if x.get("is_enabled", True)]:
        required = set(q.get("required_skills") or [])
        priorities = q.get("agent_priorities") or {}
        agents = []
        for ext_id in (q.get("agent_extension_ids") or []):
            e = by_ext_id.get(ext_id)
            if not e or not e.get("is_enabled", True):
                continue
            skills = set(e.get("skills") or [])
            if required and not required.issubset(skills):
                continue
            agents.append((e, int(priorities.get(ext_id, 0))))
        lines += [
            f"; Queue: {q['name']} (strategy={q['strategy']})",
            f"[q-{q['id']}]",
            f"strategy = {q['strategy']}",
            f"timeout = {q.get('ring_timeout', 20)}",
            f"wrapuptime = {q.get('wrapup_time', 5)}",
            f"musicclass = {q.get('moh_class') or 'default'}",
            f"announce-frequency = {30 if q.get('announce_position') else 0}",
            f"announce-holdtime = {'yes' if q.get('announce_holdtime') else 'no'}",
            "ringinuse = no",
        ]
        for a, penalty in agents:
            # Asterisk's `penalty` is queue terminology for priority — lower
            # numbers ring first. Same penalty rings concurrently.
            lines.append(f"member => PJSIP/{a['number']},{penalty},{a.get('display_name') or a['number']}")
        if not agents:
            lines.append("; (no agents match required skills — calls will fall through to fallback)")
        lines.append("")
    return "\n".join(lines) + "\n"


async def _get_all_pbx_state() -> dict:
    """Fetch the canonical PBX state from MongoDB."""
    rec = await db.pbx_settings.find_one({"id": "recording"}, {"_id": 0}) or {}
    return {
        "extensions": [e async for e in db.pbx_extensions.find({}, {"_id": 0})],
        "trunks": [t async for t in db.pbx_trunks.find({}, {"_id": 0})],
        "inbound": [i async for i in db.pbx_inbound_routes.find({}, {"_id": 0})],
        "outbound": [o async for o in db.pbx_outbound_routes.find({}, {"_id": 0})],
        "hunt_groups": [h async for h in db.pbx_hunt_groups.find({}, {"_id": 0})],
        "ivrs": [v async for v in db.pbx_ivrs.find({}, {"_id": 0})],
        "queues": [q async for q in db.pbx_queues.find({}, {"_id": 0})],
        "recording": rec,
    }


@router.get("/config/{filename}")
async def get_config_file(filename: str, current_user: dict = Depends(require_admin)):
    """Render and return a single Asterisk config file as plain text.
    Supported filenames: pjsip.conf, extensions.conf, voicemail.conf, queues.conf.
    Asterisk on the appliance pulls these via the same admin token over the
    self-hosted REST URL — no extra secret to manage."""
    state = await _get_all_pbx_state()
    if filename == "pjsip.conf":
        body = _render_pjsip(state["extensions"], state["trunks"])
    elif filename == "extensions.conf":
        body = _render_extensions(state["extensions"], state["trunks"], state["inbound"],
                                  state["outbound"], state["hunt_groups"], state["ivrs"],
                                  state["queues"], state["recording"])
    elif filename == "voicemail.conf":
        body = _render_voicemail(state["extensions"])
    elif filename == "queues.conf":
        body = _render_queues(state["queues"], state["extensions"])
    else:
        raise HTTPException(status_code=404, detail="Unknown config file")
    return Response(content=body, media_type="text/plain",
                    headers={"Content-Disposition": f"inline; filename={filename}"})


@router.get("/config-bundle")
async def get_config_bundle(current_user: dict = Depends(require_admin)):
    """Return all config files in one JSON blob — useful for the FE preview."""
    state = await _get_all_pbx_state()
    return {
        "pjsip.conf": _render_pjsip(state["extensions"], state["trunks"]),
        "extensions.conf": _render_extensions(state["extensions"], state["trunks"], state["inbound"],
                                              state["outbound"], state["hunt_groups"], state["ivrs"],
                                              state["queues"], state["recording"]),
        "voicemail.conf": _render_voicemail(state["extensions"]),
        "queues.conf": _render_queues(state["queues"], state["extensions"]),
        "generated_at": _now(),
        "counts": {
            "extensions": len(state["extensions"]),
            "trunks": len(state["trunks"]),
            "inbound": len(state["inbound"]),
            "outbound": len(state["outbound"]),
            "hunt_groups": len(state["hunt_groups"]),
            "ivrs": len(state["ivrs"]),
            "queues": len(state["queues"]),
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
        ("members", "member", "people"),
        ("users", "user", "admin/users"),
        ("guests", "guest", "people"),
        ("families", "family", "people"),
    ]
    for coll, kind, route in candidates:
        hit = await first_match(coll, route, name_field="name", id_field="id")
        if hit:
            hit["kind"] = kind
            return hit
    # Children: their parents' phone is on the family record — already covered above.
    return {"kind": None, "name": "Unknown", "phone": digits, "link": None}


# ============================================================
# CALL DETAIL RECORDS (CDR) — browser-softphone-logged
# ============================================================
# Asterisk has its own CDR via the AMI but in the preview environment the SIP
# layer is mocked, so we let the browser softphone log every call it places /
# receives. Each row stores the matched CRM record (if any) so the user can
# jump back to it from history. Indexed on (user_id, started_at) for fast
# "last 20 calls" queries.

@router.post("/cdr/log")
async def log_cdr(
    data: dict,
    current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user),
):
    """Append a Call Detail Record from the browser softphone (or any other
    SIP client we add later). Idempotent on `call_id` so retries from flaky
    networks don't duplicate the row."""
    call_id = (data.get("call_id") or "").strip() or _id("call")
    doc = {
        "id": call_id,
        "user_id": current_user["id"],
        "extension": data.get("extension") or "",
        "direction": data.get("direction") or "outgoing",  # outgoing|incoming|missed
        "peer": (data.get("peer") or "").strip()[:80],
        "peer_digits": "".join(c for c in (data.get("peer") or "") if c.isdigit())[-15:],
        "started_at": data.get("started_at") or _now(),
        "duration_sec": int(data.get("duration_sec") or 0),
        "status": data.get("status") or "completed",  # completed|missed|failed|declined
        # CRM match snapshot — store so the row keeps working even if the record is later deleted
        "matched_kind": data.get("matched_kind"),
        "matched_id": data.get("matched_id"),
        "matched_name": data.get("matched_name"),
        "matched_link": data.get("matched_link"),
        # Recording URL — emitted by Asterisk MixMonitor on the appliance and POSTed
        # back here when the recording finalises. Optional; null when recording is off.
        "recording_url": data.get("recording_url"),
        "logged_at": _now(),
    }
    await db.pbx_cdr.update_one({"id": call_id, "user_id": current_user["id"]},
                                 {"$set": doc}, upsert=True)
    return {"logged": True, "id": call_id}


@router.get("/cdr/me")
async def my_cdr(
    limit: int = 20,
    current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user),
):
    """Return the calling user's most recent CDR rows for the softphone history panel."""
    limit = max(1, min(int(limit or 20), 100))
    rows = await db.pbx_cdr.find(
        {"user_id": current_user["id"]},
        {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)
    return rows



@router.get("/cdr/analytics")
async def cdr_analytics(
    days: int = 30,
    user_id: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Admin-only call analytics dashboard data.

    Aggregates calls in the trailing `days` window into:
      * `summary`       — totals, avg duration, missed-call ratio
      * `daily`         — per-day call counts split by direction
      * `top_numbers`   — most-called/most-receiving peer digits
      * `top_contacts`  — most-touched matched CRM records
      * `top_staff`     — busiest extensions/users (when no user_id filter)
      * `busiest_hour`  — call counts by hour-of-day (0..23)

    Optional `user_id` narrows everything to a single staff member.
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    days = max(1, min(int(days or 30), 365))
    cutoff = (_dt.now(_tz.utc) - _td(days=days)).isoformat()
    match: dict = {"started_at": {"$gte": cutoff}}
    if user_id:
        match["user_id"] = user_id

    # ── Summary ──────────────────────────────────────────────
    summary_pipe = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "total_duration": {"$sum": "$duration_sec"},
            "missed": {"$sum": {"$cond": [{"$eq": ["$direction", "missed"]}, 1, 0]}},
            "incoming": {"$sum": {"$cond": [{"$eq": ["$direction", "incoming"]}, 1, 0]}},
            "outgoing": {"$sum": {"$cond": [{"$eq": ["$direction", "outgoing"]}, 1, 0]}},
            "answered": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }},
    ]
    summary_rows = await db.pbx_cdr.aggregate(summary_pipe).to_list(1)
    s = summary_rows[0] if summary_rows else {}
    total = s.get("total", 0) or 0
    answered = s.get("answered", 0) or 0
    summary = {
        "total": total,
        "incoming": s.get("incoming", 0) or 0,
        "outgoing": s.get("outgoing", 0) or 0,
        "missed": s.get("missed", 0) or 0,
        "answered": answered,
        "avg_duration_sec": int((s.get("total_duration", 0) or 0) / answered) if answered else 0,
        "missed_ratio": round((s.get("missed", 0) or 0) / total, 3) if total else 0.0,
    }

    # ── Daily breakdown ──────────────────────────────────────
    daily_pipe = [
        {"$match": match},
        {"$group": {
            "_id": {"$substr": ["$started_at", 0, 10]},
            "total": {"$sum": 1},
            "incoming": {"$sum": {"$cond": [{"$eq": ["$direction", "incoming"]}, 1, 0]}},
            "outgoing": {"$sum": {"$cond": [{"$eq": ["$direction", "outgoing"]}, 1, 0]}},
            "missed": {"$sum": {"$cond": [{"$eq": ["$direction", "missed"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    daily = [{"date": r["_id"], "total": r["total"],
              "incoming": r["incoming"], "outgoing": r["outgoing"], "missed": r["missed"]}
             async for r in db.pbx_cdr.aggregate(daily_pipe)]

    # ── Top numbers (raw digits) ─────────────────────────────
    top_nums_pipe = [
        {"$match": {**match, "peer_digits": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$peer_digits", "count": {"$sum": 1},
                    "duration": {"$sum": "$duration_sec"},
                    "name_sample": {"$first": "$matched_name"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_numbers = [{"digits": r["_id"], "count": r["count"],
                    "total_duration_sec": r["duration"], "name": r["name_sample"]}
                   async for r in db.pbx_cdr.aggregate(top_nums_pipe)]

    # ── Top matched CRM contacts ─────────────────────────────
    top_contacts_pipe = [
        {"$match": {**match, "matched_id": {"$nin": [None, ""]}}},
        {"$group": {"_id": {"id": "$matched_id", "kind": "$matched_kind", "name": "$matched_name"},
                    "count": {"$sum": 1}, "duration": {"$sum": "$duration_sec"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_contacts = []
    async for r in db.pbx_cdr.aggregate(top_contacts_pipe):
        k = r["_id"] or {}
        top_contacts.append({
            "id": k.get("id"), "kind": k.get("kind"), "name": k.get("name"),
            "count": r["count"], "total_duration_sec": r["duration"],
        })

    # ── Busiest hour-of-day ──────────────────────────────────
    hour_pipe = [
        {"$match": match},
        {"$project": {"hour": {"$toInt": {"$substr": ["$started_at", 11, 2]}}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    by_hour = {r["_id"]: r["count"] async for r in db.pbx_cdr.aggregate(hour_pipe)}
    busiest_hour = [{"hour": h, "count": by_hour.get(h, 0)} for h in range(24)]

    # ── Top staff (only when not filtering to a single user) ──
    top_staff: list = []
    if not user_id:
        staff_pipe = [
            {"$match": match},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1},
                        "duration": {"$sum": "$duration_sec"}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        rows = [r async for r in db.pbx_cdr.aggregate(staff_pipe)]
        # Resolve user names in one query
        ids = [r["_id"] for r in rows if r.get("_id")]
        name_by_id = {}
        if ids:
            async for u in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "role": 1}):
                name_by_id[u["id"]] = u
        for r in rows:
            u = name_by_id.get(r["_id"]) or {}
            top_staff.append({
                "user_id": r["_id"],
                "name": u.get("name") or "—",
                "role": u.get("role") or "",
                "count": r["count"],
                "total_duration_sec": r["duration"],
            })

    return {
        "range_days": days,
        "summary": summary,
        "daily": daily,
        "top_numbers": top_numbers,
        "top_contacts": top_contacts,
        "busiest_hour": busiest_hour,
        "top_staff": top_staff,
    }



# ============================================================
# CALL RECORDINGS — link to CDR + retention enforcement
# ============================================================

@router.post("/cdr/{call_id}/recording")
async def attach_recording(
    call_id: str,
    data: dict,
    current_user: dict = Depends(require_admin),
):
    """Asterisk (or the operator) calls this when MixMonitor finalises a recording.
    The CDR row gets `recording_url` stamped — admins / staff with access then
    see a play/download affordance on the analytics dashboard."""
    url = (data.get("recording_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="recording_url is required")
    r = await db.pbx_cdr.update_one({"id": call_id}, {"$set": {"recording_url": url, "recording_attached_at": _now()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="CDR row not found")
    return {"attached": True}


@router.post("/recording-retention/purge")
async def purge_old_recordings(current_user: dict = Depends(require_admin)):
    """Apply the configured retention policy: clear `recording_url` from CDR
    rows older than `retention_days`. The actual file deletion happens on the
    appliance — we just unlink the URL so the dashboard stops surfacing it."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    settings = await db.pbx_settings.find_one({"id": "recording"}, {"_id": 0}) or {}
    days = int(settings.get("retention_days") or 30)
    cutoff = (_dt.now(_tz.utc) - _td(days=days)).isoformat()
    r = await db.pbx_cdr.update_many(
        {"recording_url": {"$nin": [None, ""]}, "started_at": {"$lt": cutoff}},
        {"$unset": {"recording_url": "", "recording_attached_at": ""},
         "$set": {"recording_purged_at": _now()}}
    )
    return {"purged": r.modified_count, "cutoff": cutoff, "retention_days": days}



# ============================================================
# AUTO-SYNC FROM STAFF PROFILE
# ============================================================
# When an admin saves a user with `extension`, `extension_pin` and/or
# `forward_to` set, the corresponding PBX extension is created/updated
# automatically. Only Staff / Volunteer / leadership roles are eligible —
# we never auto-provision SIP credentials for members/customers/guests.

_AUTOSYNC_ROLES = {
    "admin", "system_admin", "Executive Director", "Adviser", "Director",
    "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer",
}


async def sync_pbx_extension_from_user(user: dict) -> Optional[dict]:
    """Create or update the PBX extension that mirrors this user's profile.

    Returns the synced extension dict (with the password) so callers can show
    it to the admin if they want. No-ops (returns None) when:
      - the user has no `extension` field
      - the user's role is outside _AUTOSYNC_ROLES
    """
    if not user:
        return None
    role = (user.get("role") or "").strip()
    if role not in _AUTOSYNC_ROLES:
        return None
    number = str(user.get("extension") or "").strip()
    if not number:
        return None
    try:
        _validate_extension_number(number)
    except HTTPException:
        return None

    pin = str(user.get("extension_pin") or "").strip() or None
    forwarding = (user.get("forward_to") or "").strip()
    display_name = user.get("name") or f"Extension {number}"
    email = user.get("email") or ""

    existing = await db.pbx_extensions.find_one({"number": number})
    if existing:
        # Update: only patch the user-driven fields; preserve secret/skills/etc.
        update = {
            "user_id": user.get("id"),
            "display_name": display_name,
            "voicemail_email": email,
            "forwarding_number": forwarding,
            "updated_at": _now(),
        }
        if pin:
            update["voicemail_pin"] = pin
        await db.pbx_extensions.update_one({"id": existing["id"]}, {"$set": update})
        merged = {**existing, **update}
        merged.pop("_id", None)
        return merged

    # Create — generate a SIP secret (rotated only on explicit rotate request).
    # Default to WSS transport so the user's browser softphone Just Works.
    # max_contacts defaults to 5 (browser + desk + mobile + 2 spare).
    ext = {
        "id": _id("ext"),
        "number": number,
        "display_name": display_name,
        "user_id": user.get("id"),
        "secret": _gen_secret(),
        "transport": "transport-wss",
        "allowed_codecs": ["ulaw", "alaw", "opus"],
        "max_contacts": 5,
        "voicemail_enabled": True,
        "voicemail_pin": pin or "".join([str(secrets.randbelow(10)) for _ in range(4)]),
        "voicemail_email": email,
        "outbound_caller_id": "",
        "recording_enabled": False,
        "skills": [],
        "forwarding_number": forwarding,
        "is_fax_extension": False,
        "is_enabled": True,
        "auto_provisioned": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pbx_extensions.insert_one(ext)
    ext.pop("_id", None)
    return ext


# ============================================================
# REGISTERED CONTACTS (live from Asterisk via AMI)
# ============================================================


# ============================================================
# CONTACT GROUPS — campus-scoped shared address books
# ============================================================
# A contact group is a campus-scoped list of phone numbers + names. Extension
# groups (or individual extensions) can subscribe to a contact group to get
# shared dialing entries and BLF subscription targets.

@router.get("/contact-groups")
async def list_contact_groups(current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user)):
    """Campus-scoped contact group list. Non-admins only see groups in their active campus."""
    from deps import get_campus_filter
    campus = await get_campus_filter(current_user)
    query = campus or {}
    out = [g async for g in db.pbx_contact_groups.find(query, {"_id": 0}).sort("name", 1)]
    return out


@router.post("/contact-groups")
async def create_contact_group(data: dict, current_user: dict = Depends(require_admin)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    # Default to the admin's active campus if not explicitly set
    location_id = (data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id") or "").strip()
    g = {
        "id": _id("cg"),
        "name": name[:80],
        "description": (data.get("description") or "")[:300],
        "location_id": location_id,
        "contacts": [
            {"name": (c.get("name") or "").strip()[:80],
             "phone": (c.get("phone") or "").strip()[:30],
             "extension": (c.get("extension") or "").strip()[:10],
             "notes": (c.get("notes") or "")[:200]}
            for c in (data.get("contacts") or [])
        ],
        "shared_with_extension_group_ids": data.get("shared_with_extension_group_ids") or [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pbx_contact_groups.insert_one(g)
    return {k: v for k, v in g.items() if k != "_id"}


@router.put("/contact-groups/{cg_id}")
async def update_contact_group(cg_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "description", "contacts", "shared_with_extension_group_ids"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = _now()
    r = await db.pbx_contact_groups.update_one({"id": cg_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact group not found")
    return {"updated": True}


@router.delete("/contact-groups/{cg_id}")
async def delete_contact_group(cg_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_contact_groups.delete_one({"id": cg_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contact group not found")
    return {"deleted": True}


# ============================================================
# EXTENSION GROUPS — group extensions for permissions / BLF subscriptions
# ============================================================

@router.get("/extension-groups")
async def list_extension_groups(current_user: dict = Depends(require_admin)):
    return [g async for g in db.pbx_extension_groups.find({}, {"_id": 0}).sort("name", 1)]


@router.post("/extension-groups")
async def create_extension_group(data: dict, current_user: dict = Depends(require_admin)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    g = {
        "id": _id("eg"),
        "name": name[:80],
        "description": (data.get("description") or "")[:300],
        "extension_ids": list(data.get("extension_ids") or []),
        "subscribed_contact_group_ids": list(data.get("subscribed_contact_group_ids") or []),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pbx_extension_groups.insert_one(g)
    return {k: v for k, v in g.items() if k != "_id"}


@router.put("/extension-groups/{eg_id}")
async def update_extension_group(eg_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "description", "extension_ids", "subscribed_contact_group_ids"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = _now()
    r = await db.pbx_extension_groups.update_one({"id": eg_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Extension group not found")
    return {"updated": True}


@router.delete("/extension-groups/{eg_id}")
async def delete_extension_group(eg_id: str, current_user: dict = Depends(require_admin)):
    r = await db.pbx_extension_groups.delete_one({"id": eg_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Extension group not found")
    return {"deleted": True}


@router.get("/me/contact-groups")
async def my_contact_groups(current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user)):
    """Contact groups the current user can dial from. Returns merged list of:
       - groups in their active campus (any extension group they're in subscribes to)
       - groups directly shared with the user's extension group(s)
    """
    user_id = current_user["id"]
    # Find the user's PBX extension(s)
    my_exts = [e["id"] async for e in db.pbx_extensions.find({"user_id": user_id}, {"_id": 0, "id": 1})]
    if not my_exts:
        return []
    # Extension groups that contain any of my extensions
    my_groups = [g async for g in db.pbx_extension_groups.find(
        {"extension_ids": {"$in": my_exts}}, {"_id": 0, "subscribed_contact_group_ids": 1}
    )]
    subscribed_ids = list({cid for g in my_groups for cid in g.get("subscribed_contact_group_ids", [])})
    if not subscribed_ids:
        return []
    return [c async for c in db.pbx_contact_groups.find({"id": {"$in": subscribed_ids}}, {"_id": 0})]


# ============================================================
# BLF — Busy Lamp Field subscription helper
# ============================================================
@router.get("/blf/peers")
async def blf_peers(current_user: dict = Depends(__import__("deps", fromlist=["get_current_user"]).get_current_user)):
    """Return the list of extension numbers the current user is allowed to
    BLF-subscribe to. Driven by extension-group membership: extensions in the
    same extension group can monitor each other. Admins can monitor anyone in
    their active campus."""
    user_id = current_user["id"]
    is_admin_role = (current_user.get("role") or "") in ("admin", "system_admin", "Executive Director")
    if is_admin_role:
        from deps import get_campus_filter
        campus = await get_campus_filter(current_user)
        # Admins: monitor every enabled extension in scope
        query = {"is_enabled": True, **(campus or {})}
        return [
            {"number": e["number"], "name": e.get("display_name", e["number"])}
            async for e in db.pbx_extensions.find(query, {"_id": 0, "number": 1, "display_name": 1})
        ]
    # Non-admin: only extensions in shared extension groups
    my_exts = [e["id"] async for e in db.pbx_extensions.find({"user_id": user_id}, {"_id": 0, "id": 1})]
    if not my_exts:
        return []
    my_groups = [g["extension_ids"] async for g in db.pbx_extension_groups.find(
        {"extension_ids": {"$in": my_exts}}, {"_id": 0, "extension_ids": 1}
    )]
    peer_ids = list({e for grp in my_groups for e in grp if e not in my_exts})
    if not peer_ids:
        return []
    return [
        {"number": e["number"], "name": e.get("display_name", e["number"])}
        async for e in db.pbx_extensions.find({"id": {"$in": peer_ids}, "is_enabled": True},
                                                {"_id": 0, "number": 1, "display_name": 1})
    ]


@router.get("/extensions/{ext_id}/contacts")
async def get_extension_contacts(ext_id: str, current_user: dict = Depends(require_admin)):
    """List live SIP contacts registered to this extension. Pulls from the AMI
    bridge if available, otherwise returns an empty list (preview env, etc)."""
    ext = await db.pbx_extensions.find_one({"id": ext_id}, {"_id": 0})
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    contacts: List[dict] = []
    try:
        from pbx_ami import ami_bridge  # type: ignore
        if ami_bridge and getattr(ami_bridge, "connected", False):
            raw = await ami_bridge.list_contacts_for(ext["number"])
            for c in raw or []:
                contacts.append({
                    "uri": c.get("Uri"),
                    "user_agent": c.get("UserAgent"),
                    "status": c.get("Status"),
                    "transport": c.get("Transport"),
                    "registered_at": c.get("RegisteredAt"),
                })
    except Exception:
        # AMI not configured in preview — return empty
        pass
    return {"extension_number": ext["number"], "max_contacts": ext.get("max_contacts", 5),
            "registered": contacts, "count": len(contacts)}
