"""Envelope encryption for VoIP SIP passwords.

Each staff member stores their SIP extension password in
`users.pbx.sip_password_enc` — encrypted with Fernet (AES-128-CBC + HMAC).
The key is derived from `VOIP_SECRET_KEY` in the backend `.env`. When not set
we auto-generate one on first use and persist it to `db.voip_config.crypto_key`
so restarts don't lose access to previously-encrypted passwords. In production
you should set VOIP_SECRET_KEY explicitly and back it up alongside JWT_SECRET.
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_FERNET: Optional[Fernet] = None


def _key_from_secret(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret string."""
    h = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


async def _load_fernet(db) -> Fernet:
    """Lazily construct the Fernet cipher, persisting an auto-generated key
    if the env var isn't set. Idempotent — safe to call from every request."""
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    secret = os.environ.get("VOIP_SECRET_KEY", "").strip()
    if not secret:
        # Fall back to (or provision) a DB-stored key so we don't lose
        # already-encrypted values across restarts.
        cfg = await db.voip_config.find_one({"id": "singleton"}, {"_id": 0, "crypto_key": 1}) or {}
        if cfg.get("crypto_key"):
            secret = cfg["crypto_key"]
        else:
            secret = Fernet.generate_key().decode("utf-8")
            await db.voip_config.update_one(
                {"id": "singleton"},
                {"$set": {"id": "singleton", "crypto_key": secret}},
                upsert=True,
            )
    # Accept both raw Fernet keys and arbitrary secrets.
    try:
        _FERNET = Fernet(secret.encode("utf-8") if isinstance(secret, str) else secret)
    except Exception:
        _FERNET = Fernet(_key_from_secret(secret))
    return _FERNET


async def encrypt_password(db, plaintext: str) -> str:
    if not plaintext:
        return ""
    f = await _load_fernet(db)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


async def decrypt_password(db, ciphertext: str) -> str:
    if not ciphertext:
        return ""
    f = await _load_fernet(db)
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Legacy plaintext value or wrong key — return empty rather than crashing.
        return ""
