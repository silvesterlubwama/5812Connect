"""Wave (Grandstream CloudUCM) server configuration and user credential management"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/wave", tags=["wave"])


@router.get("/servers")
async def list_wave_servers(current_user: dict = Depends(get_current_user)):
    """List configured Wave servers"""
    servers = await db.wave_servers.find({}, {"_id": 0}).sort("name", 1).to_list(50)
    return servers


@router.post("/servers")
async def add_wave_server(data: dict, current_user: dict = Depends(require_admin)):
    """Add a Wave server (admin only)"""
    doc = {
        "id": f"wave_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "url": data.get("url", "").rstrip("/"),
        "campus_id": data.get("campus_id"),
        "campus_name": data.get("campus_name", ""),
        "is_default": data.get("is_default", False),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if doc["is_default"]:
        await db.wave_servers.update_many({}, {"$set": {"is_default": False}})
    await db.wave_servers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/servers/{server_id}")
async def update_wave_server(server_id: str, data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("url"):
        data["url"] = data["url"].rstrip("/")
    if data.get("is_default"):
        await db.wave_servers.update_many({"id": {"$ne": server_id}}, {"$set": {"is_default": False}})
    await db.wave_servers.update_one({"id": server_id}, {"$set": data})
    return await db.wave_servers.find_one({"id": server_id}, {"_id": 0})


@router.delete("/servers/{server_id}")
async def delete_wave_server(server_id: str, current_user: dict = Depends(require_admin)):
    await db.wave_servers.delete_one({"id": server_id})
    return {"message": "Deleted"}


@router.get("/my-config")
async def get_my_wave_config(current_user: dict = Depends(get_current_user)):
    """Get the Wave server URL and auto-login credentials for the current user"""
    user_loc = current_user.get("location_id", "")
    user_locs = current_user.get("location_ids", [])
    # Try to find a server matching user's campus
    server = None
    if user_loc or user_locs:
        all_locs = list(set([user_loc] + user_locs)) if user_loc else user_locs
        server = await db.wave_servers.find_one({"campus_id": {"$in": all_locs}}, {"_id": 0})
    if not server:
        server = await db.wave_servers.find_one({"is_default": True}, {"_id": 0})
    if not server:
        server = await db.wave_servers.find_one({}, {"_id": 0})
    # Get user's Wave extension and password from their profile
    user_full = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "extension": 1, "wave_password": 1, "wave_server_id": 1, "name": 1})
    extension = user_full.get("extension") if user_full else None
    wave_password = user_full.get("wave_password") if user_full else None
    # Check for specific server override
    if user_full and user_full.get("wave_server_id"):
        override = await db.wave_servers.find_one({"id": user_full["wave_server_id"]}, {"_id": 0})
        if override:
            server = override
    return {
        "server": server,
        "extension": extension,
        "wave_password": wave_password,
        "display_name": current_user.get("name", ""),
        "auto_login": bool(extension and wave_password and server),
    }


@router.put("/my-credentials")
async def save_my_wave_credentials(data: dict, current_user: dict = Depends(get_current_user)):
    """Save user's Wave login credentials (extension, server preference)"""
    doc = {
        "user_id": current_user["id"],
        "wave_extension": data.get("wave_extension", ""),
        "wave_server_id": data.get("wave_server_id", ""),
        "auto_login": data.get("auto_login", True),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wave_user_creds.update_one(
        {"user_id": current_user["id"]}, {"$set": doc}, upsert=True
    )
    doc.pop("_id", None)
    return doc
