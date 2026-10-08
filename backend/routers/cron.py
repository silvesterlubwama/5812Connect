"""Platform cron endpoints (iter384).

Two scheduled jobs live here:
  * event reminders — email ticket holders the day before,
  * calendar sync — re-pull subscribed webcal/.ics calendars so they stay fresh.

Both ack immediately and do the real work in a background task: the dispatcher
only waits for the status line (~5s) and never retries.
"""
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from deps import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cron", tags=["cron"])

REMINDER_LEAD_DAYS = 1
SYNC_STALE_MINUTES = 30


def _authorize(authorization: str) -> None:
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not secret or not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _seen_before(run_id: str, job: str) -> bool:
    """One run does its work once, however many times it is delivered."""
    if not run_id:
        return False
    existing = await db.cron_runs.find_one({"run_id": run_id, "job": job}, {"_id": 0, "run_id": 1})
    if existing:
        return True
    await db.cron_runs.insert_one({"run_id": run_id, "job": job,
                                   "at": datetime.now(timezone.utc).isoformat()})
    return False


# ---------- event reminders ----------

async def send_event_reminders() -> dict:
    """Email everyone holding a ticket for an event happening tomorrow."""
    target = (datetime.now(timezone.utc) + timedelta(days=REMINDER_LEAD_DAYS)).date().isoformat()
    sent, failed = 0, 0
    from email_helpers import send_notification_email
    async for ev in db.events.find({"date": target, "status": {"$ne": "cancelled"}}, {"_id": 0}):
        bookings = await db.public_bookings.find({
            "event_id": ev["id"],
            # Anyone holding a ticket gets the nudge — including the ones who
            # still owe money (their status is `pending_payment`).
            "status": {"$nin": ["cancelled", "refunded", "declined"]},
            "reminder_sent_at": {"$in": [None, ""]},
        }, {"_id": 0}).to_list(500)
        for b in bookings:
            email = (b.get("email") or "").strip()
            if not email:
                continue
            when = f"{ev.get('date')}" + (f" at {ev['time']}" if ev.get("time") else "")
            where = ev.get("venue_name") or ev.get("location") or ""
            body = (
                f"<p>Hi {b.get('name') or 'there'},</p>"
                f"<p>This is a reminder that <strong>{ev.get('title')}</strong> is tomorrow — {when}."
                + (f" Venue: {where}." if where else "") + "</p>"
                f"<p>Tickets booked: <strong>{b.get('num_tickets') or 1}</strong>"
                + (f" · Reference: {b.get('id')}" if b.get("id") else "") + "</p>"
                + ("<p><strong>Payment is still outstanding</strong> — please settle it at the door.</p>"
                   if b.get("payment_status") not in ("paid", None, "") and float(b.get("total") or 0) > 0 else "")
                + "<p>See you there.</p>"
            )
            ok = await send_notification_email(email, f"Reminder: {ev.get('title')} is tomorrow", body)
            await db.public_bookings.update_one({"id": b["id"]}, {"$set": {
                "reminder_sent_at": datetime.now(timezone.utc).isoformat() if ok else None,
                "reminder_error": "" if ok else "Email was not accepted",
            }})
            sent += 1 if ok else 0
            failed += 0 if ok else 1
    logger.info(f"event reminders for {target}: sent={sent} failed={failed}")
    return {"date": target, "sent": sent, "failed": failed}


@router.post("/event-reminders")
async def cron_event_reminders(
    request: Request, background: BackgroundTasks,
    authorization: str = Header(None), x_webhook_id: str = Header(None),
):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _authorize(authorization)
    try:
        envelope = await request.json()
    except Exception:
        envelope = {}
    run_id = x_webhook_id or envelope.get("run_id") or ""
    if await _seen_before(run_id, "event-reminders"):
        return {"accepted": True, "duplicate": True}
    background.add_task(send_event_reminders)
    return {"accepted": True}


# ---------- subscribed calendar sync ----------

async def sync_subscribed_calendars(stale_minutes: int = SYNC_STALE_MINUTES, owner_id: str = None) -> dict:
    """Re-pull every subscribed calendar that hasn't been checked recently."""
    from routers.events import _fetch_ical, _parse_ical_events
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    q = {"source_url": {"$nin": [None, ""]},
         "$or": [{"last_synced_at": {"$lt": cutoff}}, {"last_synced_at": {"$in": [None, ""]}}]}
    if owner_id:
        q["owner_id"] = owner_id
    refreshed, events_total, errors = 0, 0, []
    for cal in await db.imported_calendars.find(q, {"_id": 0}).to_list(100):
        try:
            text = await _fetch_ical(cal["source_url"])
            owner = await db.users.find_one({"id": cal["owner_id"]}, {"_id": 0, "id": 1, "location_id": 1}) or {"id": cal["owner_id"]}
            events = await _parse_ical_events(text, owner, cal["id"])
            await db.events.delete_many({"calendar_id": cal["id"]})
            if events:
                await db.events.insert_many(events)
                if cal.get("visible_to_users"):
                    await db.events.update_many({"calendar_id": cal["id"]},
                                                {"$set": {"visible_to": cal["visible_to_users"]}})
            await db.imported_calendars.update_one({"id": cal["id"]}, {"$set": {
                "event_count": len(events),
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
                "last_sync_error": "",
            }})
            refreshed += 1
            events_total += len(events)
        except Exception as ex:
            errors.append({"calendar": cal.get("name"), "error": str(ex)[:160]})
            await db.imported_calendars.update_one({"id": cal["id"]}, {"$set": {
                "last_sync_error": str(ex)[:200],
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }})
    logger.info(f"calendar sync: refreshed={refreshed} events={events_total} errors={len(errors)}")
    return {"refreshed": refreshed, "events": events_total, "errors": errors}


@router.post("/calendar-sync")
async def cron_calendar_sync(
    request: Request, background: BackgroundTasks,
    authorization: str = Header(None), x_webhook_id: str = Header(None),
):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _authorize(authorization)
    try:
        envelope = await request.json()
    except Exception:
        envelope = {}
    run_id = x_webhook_id or envelope.get("run_id") or ""
    if await _seen_before(run_id, "calendar-sync"):
        return {"accepted": True, "duplicate": True}
    background.add_task(sync_subscribed_calendars)
    return {"accepted": True}
