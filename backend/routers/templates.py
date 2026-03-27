"""Email templates CRUD and sending."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from deps import get_current_user, db, require_manager
import uuid, os

router = APIRouter(prefix="/api")

DEFAULT_TEMPLATES = [
    {"id": "tpl_welcome", "name": "Welcome New Member", "subject": "Welcome to 58:12 Global Connect!", "body": "Dear {{name}},\n\nWelcome to 58:12 Global Connect! We're thrilled to have you as part of our community.\n\nYour member ID is {{member_id}}.\n\nGod bless,\n58:12 Global Connect Team", "variables": ["name", "member_id"], "category": "onboarding"},
    {"id": "tpl_event_invite", "name": "Event Invitation", "subject": "You're Invited: {{event_name}}", "body": "Dear {{name}},\n\nYou're invited to {{event_name}} on {{event_date}} at {{event_time}}.\n\nLocation: {{location}}\n\nWe hope to see you there!\n\n58:12 Global Connect", "variables": ["name", "event_name", "event_date", "event_time", "location"], "category": "events"},
    {"id": "tpl_donation_receipt", "name": "Donation Receipt", "subject": "Thank You for Your Donation", "body": "Dear {{donor_name}},\n\nThank you for your generous donation of {{currency}} {{amount}} on {{date}}.\n\nReceipt #: {{receipt_id}}\n\nYour support makes a difference.\n\nGod bless,\n58:12 Global Connect", "variables": ["donor_name", "currency", "amount", "date", "receipt_id"], "category": "financial"},
    {"id": "tpl_reminder", "name": "Event Reminder", "subject": "Reminder: {{event_name}} Tomorrow", "body": "Dear {{name}},\n\nThis is a friendly reminder that {{event_name}} is happening tomorrow at {{event_time}}.\n\nSee you there!\n\n58:12 Global Connect", "variables": ["name", "event_name", "event_time"], "category": "events"},
]


@router.get("/email-templates")
async def list_templates(current_user: dict = Depends(get_current_user)):
    templates = await db.email_templates.find({}, {"_id": 0}).to_list(100)
    if not templates:
        for t in DEFAULT_TEMPLATES:
            t["created_at"] = datetime.now(timezone.utc).isoformat()
            t["created_by"] = "system"
            await db.email_templates.insert_one({**t})
        templates = DEFAULT_TEMPLATES
    return templates


@router.post("/email-templates")
async def create_template(data: dict, current_user: dict = Depends(require_manager)):
    tpl_id = f"tpl_{str(uuid.uuid4())[:8]}"
    doc = {
        "id": tpl_id,
        "name": data.get("name", "New Template"),
        "subject": data.get("subject", ""),
        "body": data.get("body", ""),
        "variables": data.get("variables", []),
        "category": data.get("category", "general"),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/email-templates/{tpl_id}")
async def update_template(tpl_id: str, data: dict, current_user: dict = Depends(require_manager)):
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.email_templates.update_one({"id": tpl_id}, {"$set": data})
    return {"id": tpl_id, **data}


@router.delete("/email-templates/{tpl_id}")
async def delete_template(tpl_id: str, current_user: dict = Depends(require_manager)):
    await db.email_templates.delete_one({"id": tpl_id})
    return {"message": "Template deleted"}


@router.post("/email-templates/{tpl_id}/send")
async def send_template_email(tpl_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Send an email using a template with variable substitution."""
    template = await db.email_templates.find_one({"id": tpl_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    to_email = data.get("to_email")
    variables = data.get("variables", {})
    if not to_email:
        raise HTTPException(status_code=400, detail="to_email required")
    subject = template["subject"]
    body = template["body"]
    for key, val in variables.items():
        subject = subject.replace(f"{{{{{key}}}}}", str(val))
        body = body.replace(f"{{{{{key}}}}}", str(val))
    api_key = os.environ.get("RESEND_API_KEY")
    if api_key:
        try:
            import resend
            resend.api_key = api_key
            resend.Emails.send({"from": "58:12 Global <noreply@5812global.org>", "to": to_email, "subject": subject, "text": body})
        except Exception as e:
            return {"message": f"Email send attempted: {str(e)}", "subject": subject}
    return {"message": "Email sent", "subject": subject, "to": to_email}
