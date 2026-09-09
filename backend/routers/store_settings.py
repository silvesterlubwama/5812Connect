"""Per-location store (POS) configuration.

Lifted out of the legacy `routers/financial.py` — that router lost its HTTP
surface in the iter246 finance reset, which silently took the POS store
settings with it (Kiosk, Products and POS Setup have been calling a 404 ever
since). Nothing here touches the ledger; it's shop config: receipt layout,
payment methods, tax rate and which chart-of-accounts row the till pays into.
"""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from deps import db, get_current_user, require_manager

router = APIRouter(prefix="/api", tags=["store-settings"])

DEFAULTS = {
    "store_name": "",
    "payment_methods": ["cash", "mobile_money"],
    "mobile_money_providers": [],
    "tax_rate": 0,
    "receipt_footer": "",
    "receipt_paper_size": "80mm",
    "receipt_show_logo": True,
    "receipt_show_qr": True,
    "api_integrations": [],
    "currency": "UGX",
    "default_cash_account_id": "",
    "default_bank_account_id": "",
    "default_momo_account_id": "",
}


@router.get("/store-settings")
async def list_all_store_settings(current_user: dict = Depends(get_current_user)):
    return await db.store_settings.find({}, {"_id": 0}).to_list(100)


@router.get("/store-settings/{location_id}")
async def get_store_settings(location_id: str, current_user: dict = Depends(get_current_user)):
    """Store config for one location. Stored values are merged OVER the
    defaults so a location saved before a new key existed still returns the
    full schema."""
    doc = await db.store_settings.find_one({"location_id": location_id}, {"_id": 0})
    return {**DEFAULTS, "location_id": location_id, **(doc or {})}


@router.put("/store-settings/{location_id}")
async def update_store_settings(location_id: str, data: dict, current_user: dict = Depends(require_manager)):
    data.pop("_id", None)
    data["location_id"] = location_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = current_user["id"]
    await db.store_settings.update_one({"location_id": location_id}, {"$set": data}, upsert=True)
    await db.audit_log.insert_one({
        "user_id": current_user["id"], "action": "update", "entity": "store_settings",
        "entity_id": location_id, "timestamp": data["updated_at"],
    })
    return {**DEFAULTS, **data}
