"""Member profile PDF download — uses WeasyPrint with HTML fallback."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from deps import db, require_staff, logger
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/members/{member_id}/profile-pdf")
async def download_member_profile_pdf(member_id: str, current_user: dict = Depends(require_staff)):
    """Generate a PDF with the member's full profile and attached documents."""
    member = await db.members.find_one({"id": member_id}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return await render_member_profile_pdf(member)


async def render_member_profile_pdf(member: dict):
    """Shared renderer — also used by the portal's own self-service download."""
    member_id = member.get("id", "")
    # Get linked user info
    user_info = None
    if member.get("user_id"):
        user_info = await db.users.find_one({"id": member["user_id"]}, {"_id": 0, "password_hash": 0})
    # Get documents
    docs = await db.documents.find({"member_id": member_id}, {"_id": 0}).to_list(50)
    # Get NFC tags
    nfc_tags = member.get("nfc_tags", [])
    # Get location
    loc = await db.locations.find_one({"id": member.get("location_id", "")}, {"_id": 0, "name": 1}) if member.get("location_id") else None

    # Build HTML for PDF
    name = member.get("name", "Unknown")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; color: #1a1a2e; }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #fbbf24; padding-bottom: 8px; font-size: 22px; }}
h2 {{ color: #334155; font-size: 15px; margin-top: 24px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }}
.header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
.logo {{ color: #fbbf24; font-weight: bold; font-size: 16px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
td {{ padding: 6px 12px; border-bottom: 1px solid #f3f4f6; font-size: 13px; }}
td:first-child {{ font-weight: 600; color: #475569; width: 35%; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #f0f9ff; color: #0369a1; margin: 2px; }}
.footer {{ text-align: center; margin-top: 30px; font-size: 10px; color: #94a3b8; border-top: 1px solid #e5e7eb; padding-top: 10px; }}
</style></head><body>
<div class="header"><span class="logo">58:12 GLOBAL</span><span style="font-size:11px;color:#64748b">Profile Report — Generated {datetime.now(timezone.utc).strftime('%d %b %Y')}</span></div>
<h1>{name}</h1>
<h2>Personal Information</h2>
<table>
<tr><td>Name</td><td>{name}</td></tr>
<tr><td>Email</td><td>{member.get('email', '-')}</td></tr>
<tr><td>Phone</td><td>{member.get('phone', '-')}</td></tr>
<tr><td>Role</td><td>{member.get('role', member.get('membership_type', '-'))}</td></tr>
<tr><td>ID Number</td><td>{member.get('national_id', '-')}</td></tr>
<tr><td>Gender</td><td>{member.get('gender', '-')}</td></tr>
<tr><td>Date of Birth</td><td>{member.get('date_of_birth', '-')}</td></tr>
<tr><td>Address</td><td>{member.get('address', '-')}</td></tr>
<tr><td>Department</td><td>{member.get('department', '-')}</td></tr>
<tr><td>Campus</td><td>{loc.get('name') if loc else member.get('location_id', '-')}</td></tr>
<tr><td>Title</td><td>{member.get('title', '-')}</td></tr>
<tr><td>Status</td><td>{member.get('status', '-')}</td></tr>
<tr><td>Emergency Contact</td><td>{member.get('emergency_contact', '-')}</td></tr>
</table>"""

    if user_info:
        html += f"""
<h2>Account Details</h2>
<table>
<tr><td>User ID</td><td>{user_info.get('id', '-')}</td></tr>
<tr><td>Account Status</td><td>{user_info.get('status', '-')}</td></tr>
<tr><td>Extension</td><td>{user_info.get('extension', '-')}</td></tr>
<tr><td>Created At</td><td>{user_info.get('created_at', '-')[:10] if user_info.get('created_at') else '-'}</td></tr>
</table>"""

    if nfc_tags:
        html += "<h2>NFC Tags</h2><table>"
        for tag in nfc_tags:
            html += f"<tr><td>{tag.get('serial_number', '-')}</td><td>{tag.get('label', '')} — Added {tag.get('added_at', '')[:10]}</td></tr>"
        html += "</table>"

    if docs:
        html += "<h2>Documents</h2><table>"
        for doc in docs:
            html += f"<tr><td>{doc.get('doc_type', 'document')}</td><td>{doc.get('filename', doc.get('name', '-'))} — {doc.get('created_at', '')[:10]}</td></tr>"
        html += "</table>"

    html += f"""
<div class="footer">
www.5812-Global.org &middot; 58:12 GLOBAL &middot; {datetime.now().year}<br>
This document was auto-generated. Member ID: {member_id}
</div>
</body></html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="profile-{name.replace(" ", "_")}.pdf"'}
        )
    except Exception as e:
        logger.warning(f"PDF generation failed, falling back to HTML: {e}")
        return Response(content=html.encode(), media_type="text/html",
                       headers={"Content-Disposition": f'attachment; filename="profile-{name.replace(" ", "_")}.html"'})
