"""Advanced reporting with PDF export"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone
import io
from deps import db, get_current_user, is_system_admin, get_campus_filter

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports/summary")
async def report_summary(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Generate a comprehensive summary report"""
    # Enforce campus filter for non-system-admins
    campus = get_campus_filter(current_user)
    if campus and not location_id:
        location_id = current_user.get("location_id")
    loc_filter = {"location_id": location_id} if location_id else {}
    date_filter = {}
    if date_from:
        date_filter["$gte"] = date_from
    if date_to:
        date_filter["$lte"] = date_to

    # Member stats
    member_query = {**loc_filter}
    total_members = await db.members.count_documents(member_query)
    active_members = await db.members.count_documents({**member_query, "status": "active"})

    # Financial stats
    don_query = {**loc_filter}
    if date_filter:
        don_query["date"] = date_filter
    donations_pipeline = [{"$match": don_query}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    expenses_pipeline = [{"$match": don_query}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    don_result = await db.donations.aggregate(donations_pipeline).to_list(1)
    exp_result = await db.expenses.aggregate(expenses_pipeline).to_list(1)
    total_donations = don_result[0]["total"] if don_result else 0
    total_expenses = exp_result[0]["total"] if exp_result else 0

    # Event stats
    total_events = await db.events.count_documents({})
    total_checkins = await db.checkins.count_documents({})

    # Location stats
    total_locations = await db.locations.count_documents({})

    # Attendance
    total_bookings = await db.bookings.count_documents({})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location_id": location_id,
        "date_range": {"from": date_from, "to": date_to},
        "members": {"total": total_members, "active": active_members},
        "financial": {"total_donations": total_donations, "total_expenses": total_expenses, "net": total_donations - total_expenses},
        "events": {"total": total_events, "checkins": total_checkins},
        "locations": {"total": total_locations},
        "bookings": {"total": total_bookings},
    }


@router.get("/reports/pdf")
async def export_pdf_report(location_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Generate and download a PDF report"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    # Get report data
    data = await report_summary(location_id, date_from, date_to, current_user)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=20, spaceAfter=6, textColor=colors.HexColor('#1c1917'))
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#78716c'), spaceAfter=20)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=13, spaceBefore=16, spaceAfter=8, textColor=colors.HexColor('#e97316'))

    elements.append(Paragraph("58:12 Global Connect", title_style))
    loc_name = "All Locations"
    if location_id:
        loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1})
        loc_name = loc.get("name", location_id) if loc else location_id
    period = f"{date_from or 'Start'} to {date_to or 'Now'}"
    elements.append(Paragraph(f"Report for {loc_name} | {period} | Generated: {data['generated_at'][:10]}", subtitle_style))

    # Members Section
    elements.append(Paragraph("Members", section_style))
    members_data = [
        ["Metric", "Value"],
        ["Total Members", str(data["members"]["total"])],
        ["Active Members", str(data["members"]["active"])],
    ]
    t = Table(members_data, colWidths=[3*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1c1917')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e7e5e4')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafaf9')]),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)

    # Financial Section
    elements.append(Paragraph("Financial Summary", section_style))
    fin_data = [
        ["Metric", "Amount"],
        ["Total Donations", f"{data['financial']['total_donations']:,.0f}"],
        ["Total Expenses", f"{data['financial']['total_expenses']:,.0f}"],
        ["Net Balance", f"{data['financial']['net']:,.0f}"],
    ]
    t2 = Table(fin_data, colWidths=[3*inch, 2*inch])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1c1917')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e7e5e4')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafaf9')]),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t2)

    # Operations Section
    elements.append(Paragraph("Operations", section_style))
    ops_data = [
        ["Metric", "Value"],
        ["Total Events", str(data["events"]["total"])],
        ["Total Check-ins", str(data["events"]["checkins"])],
        ["Active Locations", str(data["locations"]["total"])],
        ["Bookings", str(data["bookings"]["total"])],
    ]
    t3 = Table(ops_data, colWidths=[3*inch, 2*inch])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1c1917')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e7e5e4')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafaf9')]),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t3)

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=5812_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"}
    )
