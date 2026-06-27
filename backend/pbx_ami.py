"""Asterisk Manager Interface (AMI) client — lightweight, dependency-free.

Talks to Asterisk's AMI TCP socket (default 5038) to issue live commands:
  • `Reload`              — apply config changes without dropping calls
  • `PJSIPShowContacts`   — list registered SIP contacts (live status)
  • `PJSIPShowRegistrationOutbound` — list trunk registrations
  • `Originate`           — place an outbound call (the click-to-call backbone)

Connection details live in env vars:
  AMI_HOST       (default 'asterisk' — the docker-compose service hostname)
  AMI_PORT       (default 5038)
  AMI_USERNAME   (default 'connect-app')
  AMI_SECRET

If AMI is not configured / reachable, every call raises `AMIError` which the
router converts to a 503 — keeps the management UI usable even when the
appliance Asterisk isn't running (e.g. in the preview environment).
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional


class AMIError(Exception):
    pass


def _cfg_present() -> bool:
    """Whether AMI is fully configured in the environment."""
    return bool(os.environ.get("AMI_SECRET"))


def _host() -> str: return os.environ.get("AMI_HOST", "asterisk")
def _port() -> int: return int(os.environ.get("AMI_PORT", "5038"))
def _user() -> str: return os.environ.get("AMI_USERNAME", "connect-app")
def _secret() -> str: return os.environ.get("AMI_SECRET", "")


class AMIClient:
    """One-shot AMI client: connect → login → action(s) → logoff → close.

    AMI is line-protocol, key:value with blank-line terminators. We avoid
    keeping a long-lived connection because Asterisk drops idle ones and
    we'd rather pay 50 ms per request than juggle reconnection. For the
    Phase-2 surface (reload + status + originate) this is plenty.
    """
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

    async def __aenter__(self):
        if not _cfg_present():
            raise AMIError("AMI not configured — set AMI_SECRET (and AMI_HOST if not 'asterisk').")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(_host(), _port()),
                timeout=self.timeout,
            )
        except (asyncio.TimeoutError, OSError) as e:
            raise AMIError(f"Cannot reach Asterisk AMI at {_host()}:{_port()} — {e}") from e
        # Banner line, e.g. "Asterisk Call Manager/9.0.0"
        await self._read_until_blank()
        await self._login()
        return self

    async def __aexit__(self, *exc):
        try:
            await self._action({"Action": "Logoff"})
        except Exception:
            pass
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass

    async def _read_until_blank(self) -> str:
        """Read until we hit \\r\\n\\r\\n (AMI message terminator)."""
        chunks = []
        while True:
            try:
                line = await asyncio.wait_for(self.reader.readline(), timeout=self.timeout)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            chunks.append(line.decode(errors="replace"))
            if line in (b"\r\n", b"\n"):
                break
        return "".join(chunks)

    async def _read_event_stream(self, end_event: str, timeout: float = 8.0) -> list[dict]:
        """Read AMI events until we see EventList=Complete OR `end_event`.
        Returns a list of parsed events (each event = dict of headers)."""
        events: list[dict] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            block = await self._read_until_blank()
            if not block:
                break
            ev = _parse_block(block)
            if not ev:
                continue
            events.append(ev)
            if ev.get("EventList") == "Complete":
                break
            if ev.get("Event") == end_event and ev.get("EventList") == "Complete":
                break
        return events

    async def _action(self, fields: dict) -> dict:
        """Send a single action, read ONE response block."""
        payload = "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
        self.writer.write(payload.encode())
        await self.writer.drain()
        block = await self._read_until_blank()
        return _parse_block(block)

    async def _login(self):
        resp = await self._action({
            "Action": "Login",
            "Username": _user(),
            "Secret": _secret(),
            "Events": "off",     # we'll opt-in per action that needs events
        })
        if resp.get("Response") != "Success":
            raise AMIError(f"AMI login failed: {resp.get('Message', resp)}")

    # ── Public actions ────────────────────────────────────────────
    async def reload(self) -> dict:
        """`Reload` — re-read all conf files & apply. Safe mid-call."""
        return await self._action({"Action": "Reload"})

    async def pjsip_contacts(self) -> list[dict]:
        """Returns the live PJSIP contact (registration) list. One contact per
        endpoint AOR — empty for endpoints that haven't registered."""
        # Send action then read events until ContactStatusDetailComplete
        self.writer.write(b"Action: PJSIPShowContacts\r\nEvents: on\r\n\r\n")
        await self.writer.drain()
        events = await self._read_event_stream(end_event="ContactList", timeout=6.0)
        # Each ContactList event has fields: AOR, URI, Status, RoundtripUsec, etc.
        return [e for e in events if e.get("Event") == "ContactList"]

    async def pjsip_registrations(self) -> list[dict]:
        """Outbound trunk registrations (we register to the carrier)."""
        self.writer.write(b"Action: PJSIPShowRegistrationsOutbound\r\nEvents: on\r\n\r\n")
        await self.writer.drain()
        events = await self._read_event_stream(end_event="OutboundRegistrationDetail", timeout=6.0)
        return [e for e in events if e.get("Event") == "OutboundRegistrationDetail"]

    async def originate(self, channel: str, exten: str, context: str,
                        caller_id: str = "", priority: int = 1,
                        timeout_ms: int = 30000, variables: Optional[dict] = None) -> dict:
        """Place a call.
        Typical usage (click-to-call):  channel="PJSIP/101", exten="+15551234567",
                                        context="from-internal", caller_id="Op <101>".
        Asterisk first dials `channel` (rings the operator), and on answer drops
        them into `context,exten,priority` — which fires the outbound route.
        """
        fields = {
            "Action": "Originate",
            "Channel": channel,
            "Exten": exten,
            "Context": context,
            "Priority": str(priority),
            "CallerID": caller_id or "",
            "Timeout": str(timeout_ms),
            "Async": "true",
        }
        if variables:
            fields["Variable"] = ",".join(f"{k}={v}" for k, v in variables.items())
        return await self._action(fields)


def _parse_block(block: str) -> dict:
    """Parse an AMI message block ('Key: Value\\r\\n' lines) into a dict."""
    out: dict = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


# ── High-level helpers used by the router ────────────────────────

async def safe_reload() -> dict:
    """Reload Asterisk if AMI is configured + reachable; otherwise return a
    'skipped' result so the router can still 200 cleanly."""
    if not _cfg_present():
        return {"reloaded": False, "skipped": "AMI not configured"}
    try:
        async with AMIClient() as ami:
            r = await ami.reload()
        return {"reloaded": r.get("Response") == "Success", "message": r.get("Message", "")}
    except AMIError as e:
        return {"reloaded": False, "error": str(e)}


async def safe_list_registrations() -> dict:
    """Live registration roster. Returns DB state with live=False on AMI miss."""
    if not _cfg_present():
        return {"live": False, "reason": "AMI not configured", "contacts": [], "trunk_regs": []}
    try:
        async with AMIClient() as ami:
            contacts = await ami.pjsip_contacts()
            trunks = await ami.pjsip_registrations()
        return {"live": True, "contacts": contacts, "trunk_regs": trunks}
    except AMIError as e:
        return {"live": False, "reason": str(e), "contacts": [], "trunk_regs": []}


async def safe_originate(channel: str, exten: str, context: str,
                         caller_id: str = "", variables: Optional[dict] = None) -> dict:
    """Originate; raises if AMI not configured (click-to-call needs it)."""
    if not _cfg_present():
        raise AMIError("Click-to-call needs an Asterisk appliance reachable from this pod (AMI_SECRET unset).")
    async with AMIClient() as ami:
        r = await ami.originate(channel=channel, exten=exten, context=context,
                                 caller_id=caller_id, variables=variables)
    if r.get("Response") != "Success":
        raise AMIError(r.get("Message") or "Originate failed")
    return r
