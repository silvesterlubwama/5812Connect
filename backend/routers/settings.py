"""App settings, global settings, currencies, GDPR/privacy — extracted from server.py"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin
from datetime import datetime, timezone
import os

router = APIRouter(prefix="/api", tags=["settings"])

CURRENCIES = [
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "UGX"},
    {"code": "USD", "name": "US Dollar", "symbol": "$"},
    {"code": "EUR", "name": "Euro", "symbol": "\u20ac"},
    {"code": "GBP", "name": "British Pound", "symbol": "\u00a3"},
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KES"},
    {"code": "TZS", "name": "Tanzanian Shilling", "symbol": "TZS"},
    {"code": "RWF", "name": "Rwandan Franc", "symbol": "RWF"},
    {"code": "ZAR", "name": "South African Rand", "symbol": "R"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "\u20a6"},
    {"code": "GHS", "name": "Ghanaian Cedi", "symbol": "GH\u20b5"},
    {"code": "CAD", "name": "Canadian Dollar", "symbol": "CA$"},
    {"code": "AUD", "name": "Australian Dollar", "symbol": "A$"},
    {"code": "INR", "name": "Indian Rupee", "symbol": "\u20b9"},
    {"code": "HTG", "name": "Haitian Gourde", "symbol": "G"},
]

@router.get("/currencies")
async def get_currencies():
    return CURRENCIES

@router.get("/global-settings")
async def get_global_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.global_settings.find_one({"_key": "global"}, {"_id": 0})
    return doc or {"_key": "global", "app_name": "58:12 Connect", "org_name": "58:12 Global", "currency": "UGX", "main_currency": "USD", "footer_text": "58:12 Global", "contact_email": "", "contact_phone": "", "contact_address": "", "logo_url": ""}

@router.put("/global-settings")
async def update_global_settings(settings: dict, current_user: dict = Depends(require_admin)):
    settings.pop("_id", None)
    settings["_key"] = "global"
    settings["updated_by"] = current_user["id"]
    settings["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.global_settings.update_one({"_key": "global"}, {"$set": settings}, upsert=True)
    return settings

@router.get("/app-settings")
async def get_app_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.app_settings.find_one({"user_id": current_user["id"]}, {"_id": 0})
    return doc or {"user_id": current_user["id"], "dark_mode": False, "language": "en"}

@router.put("/app-settings")
async def update_app_settings(settings: dict, current_user: dict = Depends(get_current_user)):
    settings.pop("_id", None)
    settings["user_id"] = current_user["id"]
    await db.app_settings.update_one({"user_id": current_user["id"]}, {"$set": settings}, upsert=True)
    return settings

# ========== GDPR / DATA RETENTION ==========

@router.get("/gdpr/settings")
async def get_gdpr_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.gdpr_settings.find_one({}, {"_id": 0})
    return doc or {"retention_months": 36, "auto_archive": False, "anonymize_inactive": False, "consent_required": True, "data_export_enabled": True}

@router.put("/gdpr/settings")
async def update_gdpr_settings(data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None)
    data["updated_by"] = current_user["id"]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.gdpr_settings.update_one({}, {"$set": data}, upsert=True)
    return data

@router.post("/gdpr/export-my-data")
async def export_my_data(current_user: dict = Depends(get_current_user)):
    uid = current_user["id"]
    user = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0, "totp_secret": 0})
    members = await db.members.find({"created_by": uid}, {"_id": 0}).to_list(100)
    checkins = await db.check_ins.find({"user_id": uid}, {"_id": 0}).to_list(500)
    donations = await db.donations.find({"created_by": uid}, {"_id": 0}).to_list(500)
    return {"user": user, "members_created": members, "check_ins": checkins, "donations": donations, "exported_at": datetime.now(timezone.utc).isoformat()}

@router.post("/gdpr/anonymize/{user_id}")
async def anonymize_user(user_id: str, current_user: dict = Depends(require_admin)):
    anon = {"name": "Anonymized User", "email": f"anon_{user_id[:8]}@removed.local", "phone": "", "avatar": "", "status": "anonymized", "anonymized_at": datetime.now(timezone.utc).isoformat()}
    await db.users.update_one({"id": user_id}, {"$set": anon})
    return {"message": "User anonymized"}

# ========== FINANCIAL API MANAGEMENT ==========

@router.get("/financial-apis")
async def list_financial_apis(current_user: dict = Depends(get_current_user)):
    return await db.financial_apis.find({}, {"_id": 0}).to_list(50)

@router.post("/financial-apis")
async def add_financial_api(data: dict, current_user: dict = Depends(require_admin)):
    import uuid
    api_id = f"fapi_{str(uuid.uuid4())[:8]}"
    doc = {"id": api_id, "name": data.get("name", ""), "type": data.get("type", "payment"), "provider": data.get("provider", ""), "api_url": data.get("api_url", ""), "api_key": data.get("api_key", ""), "webhook_url": data.get("webhook_url", ""), "location_id": data.get("location_id"), "enabled": data.get("enabled", True), "config": data.get("config", {}), "created_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.financial_apis.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/financial-apis/{api_id}")
async def update_financial_api(api_id: str, data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.financial_apis.update_one({"id": api_id}, {"$set": data})
    return {"id": api_id, **data}

@router.delete("/financial-apis/{api_id}")
async def delete_financial_api(api_id: str, current_user: dict = Depends(require_admin)):
    await db.financial_apis.delete_one({"id": api_id})
    return {"message": "API removed"}

# ========== INVENTORY ALERTS ==========

@router.get("/inventory/alerts")
async def inventory_alerts(current_user: dict = Depends(get_current_user)):
    products = await db.products.find({"$expr": {"$lte": ["$stock", "$reorder_level"]}}, {"_id": 0}).to_list(100)
    if not products:
        products = await db.products.find({"stock": {"$lte": 5}}, {"_id": 0}).to_list(100)
    return {"alerts": products, "count": len(products)}
