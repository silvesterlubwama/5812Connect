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
async def list_notifications(include_read: bool = False, current_user: dict = Depends(get_current_user)):
    """Return notifications for this user.

    iter345 — three bugs fixed here:
      1. The query never filtered on `user_id`, so a notification addressed to
         ONE person showed up in everybody's bell. That's why "cleared"
         notifications appeared to come back: they were somebody else's.
      2. Cleared/deleted notifications are now excluded via `deleted_by`
         (role-broadcast rows) or hard-deleted (personal rows).
      3. Rows deep-linking to a task/event that no longer exists (or is done /
         archived) are pruned on read, so no more stale links.
    """
    role = current_user.get("role", "volunteer")
    user_id = current_user["id"]
    conds = [
        {"$or": [{"target_role": None}, {"target_role": role}]},
        {"$or": [{"user_id": {"$exists": False}}, {"user_id": None}, {"user_id": user_id}]},
        {"deleted_by": {"$ne": user_id}},
    ]
    if not include_read:
        conds.append({"read_by": {"$ne": user_id}})
    notifs = await db.notifications.find({"$and": conds}, {"_id": 0}).sort("created_at", -1).limit(80).to_list(80)
    notifs = await _prune_stale(notifs)
    for n in notifs:
        n["read"] = user_id in n.get("read_by", [])
    return notifs[:50]


async def _prune_stale(notifs: list) -> list:
    """Drop (and permanently delete) notifications whose deep-link target is
    gone or closed — e.g. a task that was completed, archived or deleted."""
    import re as _re

    task_ids, event_ids = set(), set()
    for n in notifs:
        link = n.get("link") or ""
        m = _re.search(r"[?&]task=([\w-]+)", link)
        if m:
            task_ids.add(m.group(1))
        m = _re.search(r"[?&]event=([\w-]+)", link)
        if m:
            event_ids.add(m.group(1))
    live_tasks, live_events = set(), set()
    if task_ids:
        live_tasks = {
            t["id"] async for t in db.tasks.find(
                {"id": {"$in": list(task_ids)}, "is_archived": {"$ne": True}, "status": {"$ne": "done"}},
                {"_id": 0, "id": 1},
            )
        }
    if event_ids:
        live_events = {
            e["id"] async for e in db.events.find(
                {"id": {"$in": list(event_ids)}, "status": {"$ne": "cancelled"}}, {"_id": 0, "id": 1},
            )
        }
    keep, drop = [], []
    for n in notifs:
        link = n.get("link") or ""
        m = _re.search(r"[?&]task=([\w-]+)", link)
        if m and m.group(1) not in live_tasks:
            drop.append(n["id"])
            continue
        m = _re.search(r"[?&]event=([\w-]+)", link)
        if m and m.group(1) not in live_events:
            drop.append(n["id"])
            continue
        keep.append(n)
    if drop:
        try:
            await db.notifications.delete_many({"id": {"$in": drop}})
        except Exception:
            pass
    return keep


@router.get("/notifications/unread-count")
async def unread_notification_count(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$and": [
        {"$or": [{"target_role": None}, {"target_role": role}]},
        {"$or": [{"user_id": {"$exists": False}}, {"user_id": None}, {"user_id": user_id}]},
        {"deleted_by": {"$ne": user_id}},
        {"read_by": {"$ne": user_id}},
    ]}
    return {"count": await db.notifications.count_documents(query)}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    query = {"$and": [
        {"$or": [{"target_role": None}, {"target_role": role}]},
        {"$or": [{"user_id": {"$exists": False}}, {"user_id": None}, {"user_id": user_id}]},
    ]}
    await db.notifications.update_many(query, {"$addToSet": {"read_by": user_id}})
    return {"message": "All marked as read"}


@router.delete("/notifications/clear-all")
async def clear_all_notifications(current_user: dict = Depends(get_current_user)):
    """Erase the caller's notifications for good. Personal rows are deleted;
    role-broadcast rows (shared documents) are tombstoned per user so they
    never reappear for this account either."""
    user_id = current_user["id"]
    role = current_user.get("role", "volunteer")
    personal = await db.notifications.delete_many({"user_id": user_id})
    shared = await db.notifications.update_many(
        {"$and": [
            {"$or": [{"target_role": None}, {"target_role": role}]},
            {"$or": [{"user_id": {"$exists": False}}, {"user_id": None}]},
        ]},
        {"$addToSet": {"deleted_by": user_id}},
    )
    return {"deleted": personal.deleted_count, "hidden": shared.modified_count}


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
    """Erase one notification. A personal row is deleted outright; a shared
    role-broadcast row is tombstoned for this user only (deleting it would
    yank it out of everyone else's bell)."""
    doc = await db.notifications.find_one({"id": notif_id}, {"_id": 0, "user_id": 1})
    if doc and doc.get("user_id"):
        await db.notifications.delete_one({"id": notif_id})
    else:
        await db.notifications.update_one({"id": notif_id}, {"$addToSet": {"deleted_by": current_user["id"]}})
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
