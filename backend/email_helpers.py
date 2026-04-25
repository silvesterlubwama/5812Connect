"""Shared email notification helpers — used by tasks, checkins, and other routers."""
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
ORG = "58:12 Global Connect"

def _base_html(body: str) -> str:
    from datetime import datetime
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff">
  <div style="background:#1a1a2e;padding:18px 24px;text-align:center">
    <span style="color:#fbbf24;font-size:18px;font-weight:700;letter-spacing:1px">{ORG}</span>
  </div>
  <div style="padding:24px">{body}</div>
  <div style="background:#f5f5f4;padding:12px 24px;text-align:center;font-size:11px;color:#888">
    &copy; {datetime.now().year} {ORG}. All rights reserved.<br>
    <a href="https://5812-global.org" style="color:#888">www.5812-Global.org</a>
  </div>
</div>"""


async def send_notification_email(to_email: str, subject: str, body_html: str) -> bool:
    """Send an email notification via Resend. Returns True on success."""
    if not RESEND_API_KEY or not to_email:
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        params = {
            "from": f"{ORG} <{SENDER_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": _base_html(body_html),
        }
        await asyncio.to_thread(resend.Emails.send, params)
        return True
    except Exception as e:
        logger.warning(f"Email notification failed to {to_email}: {e}")
        return False


async def notify_task_assigned(assignee_email: str, assignee_name: str, task_title: str, assigned_by: str, board_name: str = ""):
    """Send email when a task is assigned to someone."""
    body = f"""
    <h2 style="color:#1a1a2e;margin:0 0 12px">New Task Assigned</h2>
    <p>Hi {assignee_name},</p>
    <p>You have been assigned a new task:</p>
    <div style="background:#f8f9fa;border-left:4px solid #fbbf24;padding:12px 16px;margin:16px 0;border-radius:4px">
      <p style="font-size:16px;font-weight:600;margin:0 0 4px">{task_title}</p>
      {f'<p style="font-size:12px;color:#666;margin:0">Board: {board_name}</p>' if board_name else ''}
    </div>
    <p style="font-size:13px;color:#666">Assigned by: {assigned_by}</p>
    <p style="margin-top:16px">
      <a href="https://5812-global.org" style="background:#1a1a2e;color:#fbbf24;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-block">View Task</a>
    </p>
    """
    await send_notification_email(assignee_email, f"Task Assigned: {task_title}", body)


async def notify_checkin(parent_email: str, parent_name: str, child_name: str, event_name: str = "", location: str = ""):
    """Send email when a child is checked in (parent notification)."""
    body = f"""
    <h2 style="color:#1a1a2e;margin:0 0 12px">Check-In Confirmation</h2>
    <p>Hi {parent_name},</p>
    <p><strong>{child_name}</strong> has been checked in{'  to ' + event_name if event_name else ''}{' at ' + location if location else ''}.</p>
    <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;margin:16px 0;border-radius:4px">
      <p style="font-size:14px;font-weight:600;color:#166534;margin:0">Checked in at {__import__('datetime').datetime.now().strftime('%I:%M %p')}</p>
    </div>
    <p style="font-size:13px;color:#666">This is an automated notification from {ORG}.</p>
    """
    await send_notification_email(parent_email, f"Check-In: {child_name} checked in", body)


async def notify_task_overdue(assignee_email: str, assignee_name: str, task_title: str, due_date: str):
    """Send email when a task is overdue."""
    body = f"""
    <h2 style="color:#dc2626;margin:0 0 12px">Overdue Task Reminder</h2>
    <p>Hi {assignee_name},</p>
    <p>The following task is past its due date:</p>
    <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:12px 16px;margin:16px 0;border-radius:4px">
      <p style="font-size:16px;font-weight:600;margin:0 0 4px">{task_title}</p>
      <p style="font-size:12px;color:#666;margin:0">Due: {due_date}</p>
    </div>
    <p style="margin-top:16px">
      <a href="https://5812-global.org" style="background:#dc2626;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600;display:inline-block">Update Task</a>
    </p>
    """
    await send_notification_email(assignee_email, f"Overdue: {task_title}", body)
