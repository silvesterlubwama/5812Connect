"""Grandstream UCM 63xx **New API v2.0** client.

Used specifically for voicemail retrieval — the Old API on port 8443
(challenge/response MD5, see `ucm_client.py`) doesn't expose voicemail
endpoints. The New API uses OAuth2-style auth over the main HTTPS port
(usually 8089) with a separate API user.

Auth flow:
    1. POST /api/v2.0/oauth/authorize with Basic auth(user:pass)
       → {access_token, refresh_token, expires_in}
    2. Include `Authorization: Bearer <access_token>` on every call
    3. Refresh 60 s before expiry via /api/v2.0/oauth/refresh

Voicemail actions on 6304 firmware 1.0.20+ live at:
    GET    /api/v2.0/voicemail/list?extension=<ext>
    GET    /api/v2.0/voicemail/download?extension=<ext>&msg_id=<id>
    PUT    /api/v2.0/voicemail/mark_as_read (JSON body)
    DELETE /api/v2.0/voicemail/delete (JSON body)

Endpoint names vary across firmware minor versions — we try the primary
path first, then a couple of documented aliases before giving up. On any
UCM protocol change we just add another alias here; no callers change.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ucm_client import UCMError

logger = logging.getLogger(__name__)


class UCMApiV2Client:
    """One instance per (base_url, username) pair. Reuses the OAuth token."""

    _instances: Dict[str, "UCMApiV2Client"] = {}
    _lock = asyncio.Lock()

    def __init__(self, base_url: str, username: str, password: str, verify_tls: bool = True):
        base_url = base_url.rstrip("/")
        # Trim any /api or /api/v2.0 suffix — we add the versioned path per call.
        for suffix in ("/api/v2.0", "/api/v2", "/api"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        self.base_url = base_url
        self.username = username
        self._password = password
        self._access: Optional[str] = None
        self._refresh: Optional[str] = None
        self._expiry = 0.0
        self._client = httpx.AsyncClient(timeout=15.0, verify=verify_tls)

    @classmethod
    async def get(cls, base_url: str, username: str, password: str, verify_tls: bool = True) -> "UCMApiV2Client":
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

    # ── auth ────────────────────────────────────────────────────

    async def _authorize(self) -> None:
        """Fetch a fresh access + refresh token via Basic auth."""
        cred = base64.b64encode(f"{self.username}:{self._password}".encode()).decode()
        headers = {"Authorization": f"Basic {cred}", "Accept": "application/json"}
        # Two documented paths across firmwares — try both.
        for path in ("/api/v2.0/oauth/authorize", "/api/v2.0/oauth/token"):
            url = f"{self.base_url}{path}"
            try:
                r = await self._client.post(url, headers=headers, json={"grant_type": "password"})
            except httpx.HTTPError as e:
                continue
            if r.status_code == 404:
                continue
            try:
                body = r.json()
            except Exception:
                continue
            token = (body.get("data") or body).get("access_token") or body.get("access_token")
            if token:
                self._access = token
                self._refresh = (body.get("data") or body).get("refresh_token") or body.get("refresh_token")
                # Grandstream sends `expires_in` in seconds; be defensive on missing.
                expires_in = int((body.get("data") or body).get("expires_in") or 3600)
                self._expiry = time.time() + max(60, expires_in - 60)
                return
        raise UCMError("V2 API auth failed — check username/password and that the New API user exists")

    async def _ensure_token(self) -> None:
        if not self._access or time.time() >= self._expiry:
            await self._authorize()

    async def _call(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                    json_body: Optional[Dict[str, Any]] = None, retry_on_401: bool = True,
                    raw: bool = False) -> Any:
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self._access}", "Accept": "application/json"}
        try:
            r = await self._client.request(method, url, headers=headers, params=params, json=json_body)
        except httpx.HTTPError as e:
            raise UCMError(f"V2 API unreachable ({e.__class__.__name__})")
        if r.status_code == 401 and retry_on_401:
            # Token expired mid-flight — reauth once.
            self._access = None
            return await self._call(method, path, params, json_body, retry_on_401=False, raw=raw)
        if r.status_code == 404:
            raise UCMError(f"V2 API 404: {path} — this firmware may name the endpoint differently")
        if r.status_code >= 400:
            raise UCMError(f"V2 API {r.status_code} on {path}: {r.text[:200]}")
        if raw:
            return r.content
        try:
            return r.json()
        except Exception:
            raise UCMError(f"V2 API returned non-JSON on {path}")

    # ── voicemail ───────────────────────────────────────────────

    async def _first_ok(self, method: str, paths: List[str], **kw) -> Any:
        """Try each candidate path — first one that isn't 404 wins."""
        last: Optional[Exception] = None
        for p in paths:
            try:
                return await self._call(method, p, **kw)
            except UCMError as e:
                if "404" in str(e):
                    last = e
                    continue
                raise
        raise last or UCMError("No V2 voicemail endpoint responded")

    async def list_voicemail(self, extension: str) -> List[Dict[str, Any]]:
        body = await self._first_ok("GET", [
            "/api/v2.0/voicemail/list",
            "/api/v2.0/voicemail/query",
            "/api/v2.0/vmail/list",
        ], params={"extension": extension})
        items = body.get("data") or body.get("voicemail") or body.get("list") or []
        if isinstance(items, dict):
            items = items.get("voicemail") or items.get("list") or []
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
                "received_at": v.get("date") or v.get("origtime") or v.get("timestamp") or "",
            })
        return out

    async def download_voicemail(self, extension: str, msg_id: str) -> bytes:
        # Some firmwares return raw binary; others return base64 in JSON.
        try:
            raw = await self._first_ok("GET", [
                "/api/v2.0/voicemail/download",
            ], params={"extension": extension, "msg_id": msg_id}, raw=True)
            # Sniff: if it starts with 'RIFF' it's already a WAV; if it's
            # JSON with a base64 payload we decode.
            if raw[:4] == b"RIFF":
                return raw
            try:
                import json as _j
                parsed = _j.loads(raw.decode("utf-8", "ignore"))
                b64 = (parsed.get("data") or parsed).get("audio") or (parsed.get("data") or parsed).get("file") or ""
                return base64.b64decode(b64)
            except Exception:
                return raw
        except UCMError as e:
            raise UCMError(f"voicemail download failed: {e}")

    async def mark_voicemail_read(self, extension: str, msg_id: str) -> None:
        await self._first_ok("PUT", [
            "/api/v2.0/voicemail/mark_as_read",
            "/api/v2.0/voicemail/mark_read",
        ], json_body={"extension": extension, "msg_id": msg_id})

    async def delete_voicemail(self, extension: str, msg_id: str) -> None:
        await self._first_ok("DELETE", [
            "/api/v2.0/voicemail/delete",
        ], json_body={"extension": extension, "msg_id": msg_id})
