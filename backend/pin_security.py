"""Kiosk / check-in PIN protection (iter353).

PINs used to sit in Mongo in plain text (`users.pin`, `members.pin`,
`users.guest_pin`), so a copy of the database was enough to unlock a kiosk
terminal, check anyone in, or sign in as a visitor (their PIN is also their
password).

PINs are only 4–8 digits, so a per-row bcrypt hash buys very little on its own
and can't be queried (the kiosk looks a person UP by the PIN they typed).
Instead every PIN is stored as a keyed digest:

    pin_lookup = HMAC-SHA256(PIN_PEPPER, normalised_pin)

* The pepper lives in the backend environment, never in Mongo — a stolen
  database dump alone is useless.
* Being deterministic, it is indexable, so lookup stays a single indexed query.
* `secrets.compare_digest` is used for the final comparison.

Set `PIN_PEPPER` in backend/.env. It falls back to SECRET_KEY so an existing
deployment can't break, but a dedicated value is strongly preferred.
"""
import hashlib
import hmac
import os
import re
import secrets
from typing import Optional

from dotenv import load_dotenv

from deps import db, logger

load_dotenv()

_PEPPER = (os.environ.get("PIN_PEPPER") or os.environ.get("SECRET_KEY") or "").encode()
if not _PEPPER:
    raise RuntimeError("PIN_PEPPER (or SECRET_KEY) must be set to protect kiosk PINs")

# Fields that used to hold a plaintext PIN, mapped to the hashed field.
PIN_FIELDS = {
    "pin": "pin_lookup",
    "guest_pin": "guest_pin_lookup",
}


def normalise_pin(pin: str) -> str:
    """PINs are typed on a numpad or a phone keyboard — trim, drop spaces and
    uppercase so 'a1b2 ' and 'A1B2' resolve to the same person."""
    return re.sub(r"\s+", "", str(pin or "")).upper()


def pin_digest(pin: str) -> str:
    p = normalise_pin(pin)
    if not p:
        return ""
    return hmac.new(_PEPPER, p.encode(), hashlib.sha256).hexdigest()


def pin_matches(pin: str, doc: dict, field: str = "pin") -> bool:
    """Constant-time check of a typed PIN against a stored digest."""
    stored = (doc or {}).get(PIN_FIELDS.get(field, "pin_lookup")) or ""
    if not stored:
        return False
    return secrets.compare_digest(str(stored), pin_digest(pin))


def pin_query(pin: str, field: str = "pin") -> dict:
    """Mongo filter fragment matching the person who owns this PIN."""
    return {PIN_FIELDS.get(field, "pin_lookup"): pin_digest(pin)}


def apply_pin_fields(payload: dict, field: str = "pin") -> dict:
    """Turn an inbound plaintext `pin` into its digest, in place.

    Empty string / None means "leave the existing PIN alone" (the admin UI shows
    a blank box because it can no longer read the PIN back). Pass
    `clear_pin: true` alongside to actually remove someone's PIN.
    """
    if not isinstance(payload, dict):
        return payload
    hashed_field = PIN_FIELDS.get(field, "pin_lookup")
    raw = payload.pop(field, None)
    if payload.pop("clear_pin", False):
        payload[hashed_field] = ""
        return payload
    if raw is None or str(raw).strip() == "":
        payload.pop(hashed_field, None)  # never write an empty digest by accident
        return payload
    payload[hashed_field] = pin_digest(str(raw))
    return payload


async def migrate_plaintext_pins() -> dict:
    """Idempotent startup migration: digest every remaining plaintext PIN and
    delete the cleartext. Safe to run on every boot — once converted there is
    nothing left to find."""
    moved = {"users": 0, "members": 0, "guest_pins": 0}
    try:
        for coll_name, field in (("users", "pin"), ("members", "pin"), ("users", "guest_pin")):
            coll = db[coll_name]
            cursor = coll.find(
                {field: {"$nin": [None, ""]}},
                {"_id": 0, "id": 1, field: 1},
            )
            key = "guest_pins" if field == "guest_pin" else coll_name
            async for doc in cursor:
                digest = pin_digest(doc.get(field) or "")
                if not digest:
                    continue
                await coll.update_one(
                    {"id": doc["id"]},
                    {"$set": {PIN_FIELDS[field]: digest}, "$unset": {field: ""}},
                )
                moved[key] += 1
        if any(moved.values()):
            logger.info(f"PIN migration: hashed and removed plaintext PINs {moved}")
    except Exception as e:
        logger.error(f"PIN migration failed: {e}")
    return moved


async def find_person_by_pin(pin: str, collection: str = "members", extra: Optional[dict] = None,
                             projection: Optional[dict] = None) -> Optional[dict]:
    """Resolve the person who owns `pin` in `members` or `users`."""
    digest = pin_digest(pin)
    if not digest:
        return None
    query = {PIN_FIELDS["pin"]: digest}
    if extra:
        query.update(extra)
    return await db[collection].find_one(query, projection or {"_id": 0})
