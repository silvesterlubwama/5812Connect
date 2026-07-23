"""Grandstream UCM 63xx HTTPS API client.

Handles login (challenge/response with MD5), cookie-based session persistence,
and the voicemail + CDR endpoints we surface to the app.

Docs reference: UCM63xx API Guide v1.0.20 (Grandstream). We hit these actions:

    * challenge / login       — bootstrap the session cookie
    * listVoicemail           — list voicemails for a target extension
    * downloadVoicemail       — download a voicemail WAV as base64
    * markVoicemailRead       — flip the read flag (moves file from INBOX → Old)
    * deleteVoicemail         — permanent delete
    * cdrapi                  — call detail records (JSON)

The whole client is lazy-instantiated per-tenant. `UCMClient.get()` returns a
memoised client keyed on (host, username) so we don't churn sessions.

Errors: raise `UCMError` with a human-readable message. Callers turn these
into HTTP 502 responses so the FE can show "UCM unreachable" cleanly.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class UCMError(Exception):
    """Raised for any UCM API failure (network, auth, non-zero status)."""


# Grandstream error codes we deliberately surface
_UCM_STATUS_MSG = {
    -1: "Unknown error",
    -6: "Session expired — will retry",
    -7: "Invalid parameter",
    -8: "Not permitted",
    -19: "Login failed",
    -37: "Not found",
}


class UCMClient:
    """One instance per (base_url, username) pair. Reuses the login cookie."""

    _instances: Dict[str, "UCMClient"] = {}
    _lock = asyncio.Lock()

    def __init__(self, base_url: str, username: str, password: str, verify_tls: bool = True):
        # Normalize base_url so it always ends without a trailing slash and
        # includes the /api endpoint.
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/api"):
            base_url = f"{base_url}/api"
        self.base_url = base_url
        self.username = username
        self._password = password
        self._cookie: Optional[str] = None
        self._cookie_expiry = 0.0
        self._client = httpx.AsyncClient(timeout=15.0, verify=verify_tls)

    @classmethod
    async def get(cls, base_url: str, username: str, password: str, verify_tls: bool = True) -> "UCMClient":
        """Return a memoised client. First-access performs the login."""
        key = f"{base_url}::{username}"
        async with cls._lock:
            inst = cls._instances.get(key)
            if inst is None or inst._password != password:
                if inst is not None:
                    await inst.close()
                inst = cls(base_url, username, password, verify_tls=verify_tls)
                cls._instances[key] = inst
        return inst

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass

    # ── low-level ───────────────────────────────────────────────

    async def _login(self) -> None:
        """Two-step login: challenge → MD5(challenge + password) → login."""
        try:
            r = await self._client.post(self.base_url, json={
                "request": {"action": "challenge", "user": self.username, "version": "1.0.20.24"}
            })
        except httpx.HTTPError as e:
            raise UCMError(f"UCM unreachable ({e.__class__.__name__})")
        try:
            body = r.json()
        except Exception:
            raise UCMError(f"UCM returned non-JSON on challenge (HTTP {r.status_code})")
        if body.get("status") != 0:
            raise UCMError(f"challenge failed: {_UCM_STATUS_MSG.get(body.get('status'), body)}")
        challenge = (body.get("response") or {}).get("challenge") or ""
        token = hashlib.md5((challenge + self._password).encode("utf-8")).hexdigest()
        r = await self._client.post(self.base_url, json={
            "request": {"action": "login", "token": token, "url": "", "user": self.username}
        })
        try:
            body = r.json()
        except Exception:
            raise UCMError(f"UCM returned non-JSON on login (HTTP {r.status_code})")
        if body.get("status") != 0:
            raise UCMError(f"login failed: {_UCM_STATUS_MSG.get(body.get('status'), body)}")
        cookie = (body.get("response") or {}).get("cookie")
        if not cookie:
            raise UCMError("UCM returned no cookie on login")
        self._cookie = cookie
        # Grandstream sessions default to ~30 min; renew 60 s early.
        self._cookie_expiry = time.time() + 25 * 60

    async def _ensure_session(self) -> None:
        if not self._cookie or time.time() >= self._cookie_expiry:
            await self._login()

    async def _call(self, action: str, params: Optional[Dict[str, Any]] = None, retry: bool = True) -> Dict[str, Any]:
        await self._ensure_session()
        payload = {"request": {"action": action, "cookie": self._cookie, **(params or {})}}
        try:
            r = await self._client.post(self.base_url, json=payload)
        except httpx.HTTPError as e:
            raise UCMError(f"UCM unreachable during {action} ({e.__class__.__name__})")
        try:
            body = r.json()
        except Exception:
            raise UCMError(f"UCM returned non-JSON on {action} (HTTP {r.status_code})")
        status = body.get("status")
        if status == -6 and retry:
            # Session expired — force re-login once and retry.
            self._cookie = None
            return await self._call(action, params, retry=False)
        if status != 0:
            raise UCMError(f"{action} failed: {_UCM_STATUS_MSG.get(status, status)}")
        return body.get("response") or {}

    # ── voicemail ───────────────────────────────────────────────

    async def list_voicemail(self, extension: str) -> List[Dict[str, Any]]:
        """List voicemails for an extension. Returns a normalised list with
        `id`, `from`, `caller_id`, `duration`, `is_read`, `folder`, `date`."""
        # The Grandstream action name varies slightly across firmwares.
        # `listVoicemail` is the current 1.0.20 name; older builds used
        # `voicemail_list`. Try the primary, fall back to legacy.
        try:
            res = await self._call("listVoicemail", {"extension": extension})
        except UCMError:
            res = await self._call("voicemail_list", {"extension": extension})
        items = res.get("voicemail") or res.get("data") or []
        out: List[Dict[str, Any]] = []
        for v in items:
            out.append({
                "id": str(v.get("msg_id") or v.get("id") or v.get("uid") or ""),
                "extension": extension,
                "from_number": v.get("caller_id_num") or v.get("caller_number") or v.get("from") or "",
                "from_name": v.get("caller_id_name") or v.get("caller_name") or "",
                "duration_sec": int(v.get("duration") or 0),
                "is_read": (v.get("folder") or v.get("box") or "INBOX").upper() != "INBOX",
                "folder": v.get("folder") or v.get("box") or "INBOX",
                "received_at": v.get("date") or v.get("origtime") or "",
            })
        return out

    async def download_voicemail(self, extension: str, msg_id: str) -> bytes:
        """Download the voicemail audio. UCM returns base64 in a JSON blob."""
        try:
            res = await self._call("downloadVoicemail", {"extension": extension, "msg_id": msg_id})
        except UCMError:
            res = await self._call("voicemail_get", {"extension": extension, "id": msg_id})
        import base64
        b64 = res.get("audio") or res.get("data") or res.get("file") or ""
        try:
            return base64.b64decode(b64)
        except Exception:
            raise UCMError("UCM returned invalid audio payload")

    async def mark_voicemail_read(self, extension: str, msg_id: str) -> None:
        """Move the message from INBOX to Old (marks it as heard)."""
        try:
            await self._call("markVoicemailRead", {"extension": extension, "msg_id": msg_id})
        except UCMError:
            # Legacy action name
            await self._call("voicemail_mark_read", {"extension": extension, "id": msg_id})

    async def delete_voicemail(self, extension: str, msg_id: str) -> None:
        try:
            await self._call("deleteVoicemail", {"extension": extension, "msg_id": msg_id})
        except UCMError:
            await self._call("voicemail_delete", {"extension": extension, "id": msg_id})

    # ── CDR (call detail records) ───────────────────────────────

    async def list_cdr(self, extension: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent CDR rows for a given extension. Grandstream's cdrapi
        supports filtering by src or dst — we OR them so both outbound and
        inbound show up for the user."""
        try:
            res = await self._call("cdrapi", {
                "format": "json",
                "caller": extension,
                "callee": extension,
                "numRecords": str(limit),
            })
        except UCMError:
            return []
        rows = res.get("cdr") or res.get("data") or []
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": str(r.get("uniqueid") or r.get("id") or ""),
                "direction": "outgoing" if (r.get("src") or "") == extension else "incoming",
                "peer": r.get("dst") if (r.get("src") or "") == extension else r.get("src"),
                "duration_sec": int(r.get("billsec") or 0),
                "status": r.get("disposition") or "",
                "started_at": r.get("start") or r.get("calldate") or "",
                "recording_url": r.get("recordingfile") or None,
            })
        return out


async def get_client_for_config(cfg: Dict[str, Any], password: str) -> UCMClient:
    """Convenience shortcut used by the router. `cfg` is the tenant voip_config;
    `password` is the freshly-decrypted admin API password."""
    return await UCMClient.get(
        base_url=cfg.get("ucm_api_url") or "",
        username=cfg.get("ucm_api_username") or "",
        password=password,
        verify_tls=bool(cfg.get("ucm_verify_tls", True)),
    )
