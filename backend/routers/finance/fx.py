"""Exchange rates, set once and reused by every report (iter375).

Reports used to make you type a rate by hand on every single export, and only
the summary PDF honoured it. Rates now live in one place (Settings → Exchange
rates) and any report can convert with `?fx_target=USD` alone — the saved rate
is looked up. A per-report `fx_rate` still wins, for the day the bank gives you
a different number.

Stored as a single document so the history of who changed a rate, and when, is
visible on the card itself.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, require_admin, require_staff, _audit

router = APIRouter(prefix="/api/finance/fx", tags=["finance"])

DOC_ID = "default"
DEFAULT_BASE = "UGX"


async def _doc() -> dict:
    doc = await db.finance_fx_rates.find_one({"id": DOC_ID}, {"_id": 0})
    if doc:
        return doc
    settings = await db.settings.find_one({}, {"_id": 0, "currency": 1}) or {}
    return {"id": DOC_ID, "base": settings.get("currency") or DEFAULT_BASE,
            "rates": {}, "updated_at": "", "updated_by": ""}


@router.get("/rates")
async def get_rates(current_user: dict = Depends(require_staff)) -> dict:
    """`{base: "UGX", rates: {"USD": 0.00027, ...}}` — 1 base = rate target."""
    return await _doc()


@router.put("/rates")
async def put_rates(data: dict, current_user: dict = Depends(require_admin)) -> dict:
    base = (data.get("base") or DEFAULT_BASE).strip().upper()[:4]
    if not base.isalpha():
        raise HTTPException(status_code=400, detail="Base currency must be a currency code, e.g. UGX")

    clean: dict = {}
    for code, rate in (data.get("rates") or {}).items():
        code = (code or "").strip().upper()[:4]
        if not code.isalpha() or code == base:
            continue                      # a base→base rate is always 1
        try:
            val = float(rate)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Rate for {code} is not a number")
        if val <= 0:
            continue                      # blank or zero means "not set"
        clean[code] = val

    doc = {"id": DOC_ID, "base": base, "rates": clean,
           "updated_at": datetime.now(timezone.utc).isoformat(),
           "updated_by": current_user.get("name") or ""}
    await db.finance_fx_rates.update_one({"id": DOC_ID}, {"$set": doc}, upsert=True)
    await _audit(current_user, "fx_rates_updated", "finance", DOC_ID,
                 {"base": base, "codes": sorted(clean)})
    return doc


async def resolve_fx(fx_target: Optional[str], fx_rate: Optional[float] = None) -> dict:
    """What a report should convert by.

    `{"active": bool, "code": "USD", "rate": 0.00027, "label": "in USD @ 0.00027"}`
    An explicit rate wins; otherwise the saved rate for that currency is used.
    Asking for the base currency (or a currency with no saved rate and no
    explicit one) converts nothing rather than silently printing wrong money.
    """
    off = {"active": False, "code": "", "rate": 1.0, "label": ""}
    code = (fx_target or "").strip().upper()
    if not code:
        return off

    doc = await _doc()
    if code == (doc.get("base") or DEFAULT_BASE):
        return off

    rate = None
    if fx_rate is not None:
        try:
            rate = float(fx_rate)
        except (TypeError, ValueError):
            rate = None
    if not rate or rate <= 0:
        rate = (doc.get("rates") or {}).get(code)
    if not rate or float(rate) <= 0:
        return off

    rate = float(rate)
    trimmed = f"{rate:.8f}".rstrip("0").rstrip(".")
    return {"active": True, "code": code, "rate": rate,
            "label": f"Amounts in {code} @ {trimmed} per {doc.get('base') or DEFAULT_BASE}"}


def converter(fx: dict):
    """`fx(value)` → converted float, rounded to 2dp."""
    if not fx.get("active"):
        return lambda v: round(float(v or 0), 2)
    rate = fx["rate"]
    return lambda v: round(float(v or 0) * rate, 2)
