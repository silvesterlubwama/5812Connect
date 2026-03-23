"""Email notification service via Resend"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import asyncio
import os
import logging
import uuid
import resend
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["notifications"])

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
resend.api_key = RESEND_API_KEY


async def send_email(to: str, subject: str, html: str):
    """Non-blocking email send"""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set, skipping email")
        return None
    try:
        params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to}: {subject}")
        return result
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return None


def _email_template(title: str, body: str, action_url: str = "", action_text: str = ""):
    action_btn = ""
    if action_url and action_text:
        action_btn = f'<tr><td style="padding:16px 0 0"><a href="{action_url}" style="background:#e97316;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-block">{action_text}</a></td></tr>'
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:520px;margin:0 auto;background:#fafaf9;border-radius:12px;overflow:hidden">
      <div style="background:#1c1917;padding:20px 24px"><h1 style="margin:0;color:#fff;font-size:18px">58:12 Global Connect</h1></div>
      <div style="padding:24px">
        <h2 style="margin:0 0 12px;color:#1c1917;font-size:16px">{title}</h2>
        <div style="color:#44403c;font-size:14px;line-height:1.6">{body}</div>
        <table>{action_btn}</table>
      </div>
      <div style="padding:16px 24px;background:#f5f5f4;font-size:11px;color:#a8a29e;text-align:center">58:12 Global Connect Uganda</div>
    </div>"""


class NotifyRequest(BaseModel):
    type: str  # event_reminder, approval_needed, fund_transfer, announcement, checkin_alert
    recipient_email: str
    recipient_name: Optional[str] = ""
    data: Optional[dict] = {}


@router.post("/notifications/send")
async def send_notification(req: NotifyRequest):
    """Send an email notification based on type"""
    t = req.type
    d = req.data or {}
    name = req.recipient_name or "there"

    if t == "event_reminder":
        subject = f"Upcoming Event: {d.get('event_title', 'Event')}"
        body = f"<p>Hi {name},</p><p>This is a reminder for <strong>{d.get('event_title')}</strong> on {d.get('date', '')} at {d.get('time', '')}.</p><p>Location: {d.get('location', 'TBD')}</p>"
        html = _email_template("Event Reminder", body)

    elif t == "approval_needed":
        subject = f"Approval Required: {d.get('member_name', 'New Member')}"
        body = f"<p>Hi {name},</p><p><strong>{d.get('member_name')}</strong> has requested to join. Please review and approve or reject.</p>"
        html = _email_template("Approval Needed", body, d.get("action_url", ""), "Review Now")

    elif t == "fund_transfer":
        subject = f"Fund Transfer: {d.get('currency', 'UGX')} {d.get('amount', '0')}"
        body = f"<p>Hi {name},</p><p>A fund transfer of <strong>{d.get('currency', 'UGX')} {d.get('amount', '0')}</strong> has been made from {d.get('from_location', '')} to {d.get('to_location', '')}.</p><p>Notes: {d.get('notes', '-')}</p>"
        html = _email_template("Fund Transfer Notification", body)

    elif t == "announcement":
        subject = f"Announcement: {d.get('title', '')}"
        body = f"<p>Hi {name},</p><p><strong>{d.get('title')}</strong></p><p>{d.get('content', '')}</p>"
        html = _email_template("New Announcement", body)

    elif t == "checkin_alert":
        subject = f"Check-In Alert: {d.get('person_name', '')}"
        body = f"<p>Hi {name},</p><p><strong>{d.get('person_name')}</strong> has {'checked in to' if d.get('action') == 'in' else 'checked out of'} <strong>{d.get('location_name', '')}</strong> at {d.get('time', '')}.</p>"
        html = _email_template("Check-In Alert", body)

    elif t == "approval_status":
        status_label = d.get("status", "approved")
        subject = f"Membership {status_label.title()}: {d.get('member_name', '')}"
        body = f"<p>Hi {name},</p><p>Your membership request has been <strong>{status_label}</strong>.</p>"
        html = _email_template("Membership Update", body)

    elif t == "guest_approval":
        subject = f"Guest Visit Request: {d.get('guest_name', '')}"
        body = f"<p>Hi {name},</p><p><strong>{d.get('guest_name')}</strong> is requesting to visit <strong>{d.get('location_name', '')}</strong> (restricted) on {d.get('date', '')}.</p><p>Purpose: {d.get('purpose', '-')}</p>"
        html = _email_template("Guest Approval Required", body, d.get("action_url", ""), "Review Request")

    else:
        subject = d.get("subject", "Notification from 58:12")
        body = f"<p>{d.get('message', '')}</p>"
        html = _email_template("Notification", body)

    result = await send_email(req.recipient_email, subject, html)
    return {"sent": result is not None, "email_id": result.get("id") if result else None}


@router.post("/notifications/bulk")
async def send_bulk_notifications(data: dict):
    """Send same notification to multiple recipients"""
    recipients = data.get("recipients", [])  # [{email, name}]
    notification_type = data.get("type", "")
    notification_data = data.get("data", {})
    sent = 0
    for r in recipients:
        req = NotifyRequest(
            type=notification_type,
            recipient_email=r.get("email", ""),
            recipient_name=r.get("name", ""),
            data=notification_data,
        )
        if req.recipient_email:
            try:
                await send_notification(req)
                sent += 1
            except Exception as e:
                logger.error(f"Bulk notification failed for {req.recipient_email}: {e}")
    return {"sent": sent, "total": len(recipients)}
