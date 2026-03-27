"""Push notification endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from deps import get_current_user, db
import os, json, uuid

router = APIRouter(prefix="/api")

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@5812global.org")


@router.get("/notifications/vapid-key")
async def get_vapid_key():
    return {"public_key": VAPID_PUBLIC}


@router.post("/notifications/subscribe")
async def subscribe(data: dict, current_user: dict = Depends(get_current_user)):
    subscription = data.get("subscription")
    if not subscription:
        raise HTTPException(status_code=400, detail="No subscription data")
    await db.push_subscriptions.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"user_id": current_user["id"], "subscription": subscription, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"message": "Subscribed"}


@router.delete("/notifications/subscribe")
async def unsubscribe(current_user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": current_user["id"]})
    return {"message": "Unsubscribed"}


@router.get("/notifications")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    return await db.notifications.find(
        {"$or": [{"user_id": current_user["id"]}, {"user_id": None}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)


@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": notif_id}, {"$set": {"read": True}})
    return {"message": "Read"}


@router.put("/notifications/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": current_user["id"], "read": False}, {"$set": {"read": True}})
    return {"message": "All read"}


async def create_notification(user_id, title, body, url="/"):
    await db.notifications.insert_one({
        "id": f"notif_{str(uuid.uuid4())[:8]}", "user_id": user_id,
        "title": title, "body": body, "url": url,
        "read": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
