"""Web Push subscription endpoints — moved out of server.py in iter303.

The `/api/push/*` surface used by the PWA. Distinct from the older
`/api/notifications/subscribe` variant in `routers/notifications.py`; both
paths are kept live because different frontend versions call each.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user

router = APIRouter(prefix="/api")


@router.post("/push/subscribe")
async def subscribe_push(data: dict, current_user: dict = Depends(get_current_user)):
    subscription = data.get("subscription")
    if not subscription or not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="Invalid push subscription")
    await db.push_subscriptions.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"user_id": current_user["id"], "subscription": subscription,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"message": "Push subscription saved"}


@router.delete("/push/subscribe")
async def unsubscribe_push(current_user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": current_user["id"]})
    return {"message": "Push subscription removed"}


@router.get("/push/vapid-key")
async def get_vapid_key():
    return {"publicKey": os.environ.get("VAPID_PUBLIC_KEY", "")}
