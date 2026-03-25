"""Email integration via Resend — transactional emails for the CRM."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import asyncio, os, uuid, logging
import resend
from deps import db, get_current_user, require_staff, logger, is_system_admin

router = APIRouter(prefix="/api", tags=["email"])

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
resend.api_key = RESEND_API_KEY

ORG = "58:12 Global Connect"

# ---- helpers ----

def _base_html(body: str) -> str:
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff">
  <div style="background:#1a1a2e;padding:18px 24px;text-align:center">
    <span style="color:#fbbf24;font-size:18px;font-weight:700;letter-spacing:1px">{ORG}</span>
  </div>
  <div style="padding:24px">{body}</div>
  <div style="background:#f5f5f4;padding:12px 24px;text-align:center;font-size:11px;color:#888">
    &copy; {datetime.now().year} {ORG}. All rights reserved.
  </div>
</div>"""


# ---- models ----

class EmailSend(BaseModel):
    to: List[str]
    subject: str
    body_html: Optional[str] = None
    template: Optional[str] = None  # "welcome", "event_invite", "password_reset", "custom"
    context: Optional[dict] = {}


# ---- templates ----

TEMPLATES = {
    "welcome": lambda ctx: _base_html(f"""
        <h2 style="color:#1a1a2e;margin:0 0 8px">Welcome to {ORG}!</h2>
        <p style="color:#444;line-height:1.6">Hi <strong>{ctx.get('name','')}</strong>,</p>
        <p style="color:#444;line-height:1.6">Your account has been created. Here are your credentials:</p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0">
          <p style="margin:0;font-size:14px"><strong>Email:</strong> {ctx.get('email','')}</p>
          <p style="margin:4px 0 0;font-size:14px"><strong>Temporary Password:</strong> {ctx.get('password','')}</p>
        </div>
        <p style="color:#444;line-height:1.6">Please change your password after your first login.</p>
    """),
    "event_invite": lambda ctx: _base_html(f"""
        <h2 style="color:#1a1a2e;margin:0 0 8px">You're Invited!</h2>
        <p style="color:#444;line-height:1.6">Hi <strong>{ctx.get('name','')}</strong>,</p>
        <p style="color:#444;line-height:1.6">You are invited to <strong>{ctx.get('event_name','an event')}</strong>.</p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0">
          <p style="margin:0;font-size:14px"><strong>Date:</strong> {ctx.get('date','TBD')}</p>
          <p style="margin:4px 0 0;font-size:14px"><strong>Time:</strong> {ctx.get('time','TBD')}</p>
          <p style="margin:4px 0 0;font-size:14px"><strong>Location:</strong> {ctx.get('location','TBD')}</p>
        </div>
        <p style="color:#444;line-height:1.6">We look forward to seeing you!</p>
    """),
    "password_reset": lambda ctx: _base_html(f"""
        <h2 style="color:#1a1a2e;margin:0 0 8px">Password Reset</h2>
        <p style="color:#444;line-height:1.6">Hi <strong>{ctx.get('name','')}</strong>,</p>
        <p style="color:#444;line-height:1.6">Your password has been reset by an administrator.</p>
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0">
          <p style="margin:0;font-size:14px"><strong>New Password:</strong> {ctx.get('password','')}</p>
        </div>
        <p style="color:#444;line-height:1.6">Please change it after your next login.</p>
    """),
    "report": lambda ctx: _base_html(f"""
        <h2 style="color:#1a1a2e;margin:0 0 8px">Report: {ctx.get('title','Summary')}</h2>
        <p style="color:#444;line-height:1.6">{ctx.get('body','')}</p>
    """),
}


# ---- endpoints ----

@router.post("/email/send")
async def send_email(data: EmailSend, current_user: dict = Depends(require_staff)):
    """Send an email using Resend. Supports templates or raw HTML."""
    if not RESEND_API_KEY:
        raise HTTPException(status_code=500, detail="Email service not configured")

    html = data.body_html or ""
    if data.template and data.template in TEMPLATES:
        html = TEMPLATES[data.template](data.context or {})
    elif not html:
        html = _base_html(f"<p>{data.context.get('body', 'No content provided.')}</p>")

    try:
        params = {
            "from": SENDER_EMAIL,
            "to": data.to,
            "subject": data.subject,
            "html": html,
        }
        result = await asyncio.to_thread(resend.Emails.send, params)
        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", str(result))
        # Log to DB
        await db.email_log.insert_one({
            "id": str(uuid.uuid4()),
            "to": data.to,
            "subject": data.subject,
            "template": data.template,
            "resend_id": email_id,
            "sent_by": current_user["id"],
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "sent", "email_id": email_id, "recipients": data.to}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")


@router.get("/email/log")
async def email_log(skip: int = 0, limit: int = 50, current_user: dict = Depends(require_staff)):
    """Get email send history."""
    logs = await db.email_log.find({}, {"_id": 0}).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)
    return logs


@router.get("/email/templates")
async def list_templates(current_user: dict = Depends(get_current_user)):
    """List available email templates."""
    return [
        {"id": "welcome", "name": "Welcome Email", "description": "New user onboarding with credentials"},
        {"id": "event_invite", "name": "Event Invitation", "description": "Invite members to events"},
        {"id": "password_reset", "name": "Password Reset", "description": "Send new password to user"},
        {"id": "report", "name": "Report Email", "description": "Send report summary via email"},
        {"id": "custom", "name": "Custom Email", "description": "Free-form HTML email"},
    ]
