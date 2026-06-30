"""Pure validation + ID helpers extracted from `routers/pbx.py`.

These are deliberately tiny — they only know about strings, regex, and the
standard library — so they stay easy to unit-test and re-use from CLI
tooling, dial-plan renderers, or other routers without dragging the whole
PBX route file along.
"""
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


def pbx_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def gen_pbx_secret() -> str:
    """SIP auth secret — Asterisk-safe base64-url, 24 chars."""
    return secrets.token_urlsafe(18)


def pbx_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def validate_extension_number(num: str) -> str:
    """Internal extension — 2-6 digits, no leading zero."""
    if not re.fullmatch(r"[1-9][0-9]{1,5}", num or ""):
        raise HTTPException(status_code=400, detail="Extension must be 2-6 digits and not start with 0")
    return num


def validate_pattern(pat: str) -> str:
    """Asterisk dialplan pattern: `_NXXNXXXXXX`, `_X.`, `_+1NXXNXXXXXX`, or literal digits."""
    p = (pat or "").strip()
    if not p:
        raise HTTPException(status_code=400, detail="Dial pattern required")
    # Allow literal digits + asterisk pattern syntax (underscore + N/X/Z/0-9/./[]/+)
    if not re.fullmatch(r"_?\+?[0-9NXZ\.\[\]\-]+", p):
        raise HTTPException(status_code=400, detail="Invalid dial pattern")
    return p
