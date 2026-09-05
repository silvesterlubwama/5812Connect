"""Notifications + Web Push — consolidated in iter304.

Previously split across `server.py` (list/unread/mark/create/delete) and this
file (VAPID + subscribe helpers). The two disagreed on schema and the routers
were registered in different orders, so which version answered `/api/notifications`
depended on include-order. Now a single router owns every `/api/notifications/*`
path.

Frontend contract (see `frontend/src/services/api.js`):
- GET  /api/notifications          → list, role-scoped, with computed `read`
- GET  /api/notifications/unread-count
- POST /api/notifications          → create (admin/staff use)
- PUT  /api/notifications/read-all
- PUT  /api/notifications/{id}/read
- DEL  /api/notifications/{id}
- GET  /api/notifications/vapid-key
- POST /api/notifications/subscribe
- DEL  /api/notifications/subscribe

`/api/push/*` remains in `routers/push.py` — the PWA calls both surfaces.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, get_current_user

router = APIRouter(prefix="/api")

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")


class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"
    target_role: Optional[str] = None
    link: Optional[str] = None


# ─── Web Push subscription ───────────────────────────────────

@router.get("/notifications/vapid-key")
async def get_vapid_key():
    # Return both keys so old + new clients both keep working.
    return {"public_key": VAPID_PUBLIC, "publicKey": VAPID_PUBLIC}


@router.post("/notifications/subscribe")
async def subscribe(data: dict, current_user: dict = Depends(get_current_user)):
    subscription = data.get("subscription") or data
    if not subscription or not subscription.get("endpoint"):
        raise HTTPException(status_code=400, detail="No subscription data")
    await db.push_subscriptions.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"user_id": current_user["id"], "subscription": subscription,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"message": "Subscribed"}


@router.delete("/notifications/subscribe")
async def unsubscribe(current_user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_many({"user_id": current_user["id"]})
    return {"message": "Unsubscribed"}


# ─── In-app notification feed ────────────────────────────────

@router.get("/notifications")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    """Return the last 50 notifications visible to this user. Role-scoped
    (`target_role`) with the user-specific `read` flag computed from `read_by`."""
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    notifs = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    user_id = current_user["id"]
    for n in notifs:
        n["read"] = user_id in n.get("read_by", [])
    return notifs


@router.get("/notifications/unread-count")
async def unread_notification_count(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}], "read_by": {"$ne": user_id}}
    return {"count": await db.notifications.count_documents(query)}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$or": [{"target_role": None}, {"target_role": role}]}
    await db.notifications.update_many(query, {"$addToSet": {"read_by": user_id}})
    return {"message": "All marked as read"}


@router.put("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": notif_id}, {"$addToSet": {"read_by": current_user["id"]}})
    return {"message": "Marked as read"}


@router.post("/notifications")
async def create_notification_endpoint(data: NotificationCreate, current_user: dict = Depends(get_current_user)):
    doc = {"id": f"notif_{str(uuid.uuid4())[:8]}", **data.model_dump(),
           "read_by": [], "created_at": datetime.now(timezone.utc).isoformat(),
           "created_by": current_user["id"]}
    await db.notifications.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, current_user: dict = Depends(get_current_user)):
    await db.notifications.delete_one({"id": notif_id})
    return {"message": "Notification deleted"}


# ─── Internal helper (called from other routers, e.g. financial.py) ─
# `financial.py` currently imports `_create_notification`; expose both
# names so a rename doesn't have to ripple through every caller.

async def create_notification(title: str, message: str, user_id: str,
                              notif_type: str = "info", link: str = "/",
                              target_role: Optional[str] = None):
    """Insert a notification. Argument order matches existing callers in
    `financial.py`: (title, message, user_id, type, link)."""
    doc = {
        "id": f"notif_{str(uuid.uuid4())[:8]}",
        "title": title, "message": message,
        "type": notif_type, "link": link,
        "target_role": target_role,
        # `user_id` is stored so the notification can be filtered per user
        # even when `target_role` is None (e.g. "your expense was approved").
        "user_id": user_id,
        "read_by": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one(doc)


# Legacy alias — several routers still import this name.
_create_notification = create_notification
