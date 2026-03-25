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


@router.get("/reports/campus-comparison")
async def campus_comparison(date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Advanced campus-by-campus comparison report for system admins."""
    campus_filter = {}
    if not is_system_admin(current_user):
        campus_filter = {"location_id": current_user.get("location_id")}

    locations = await db.locations.find({}, {"_id": 0}).to_list(100)
    date_match = {}
    if date_from:
        date_match["$gte"] = date_from
    if date_to:
        date_match["$lte"] = date_to

    results = []
    for loc in locations:
        lid = loc["id"]
        if campus_filter and campus_filter.get("location_id") != lid:
            continue
        lf = {"location_id": lid}

        members = await db.members.count_documents(lf)
        active = await db.members.count_documents({**lf, "status": "active"})
        children = await db.children.count_documents(lf)
        families = await db.families.count_documents(lf)
        guests = await db.guests.count_documents(lf)

        don_q = {**lf}
        exp_q = {**lf}
        if date_match:
            don_q["date"] = date_match
            exp_q["date"] = date_match

        don_r = await db.donations.aggregate([{"$match": don_q}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        exp_r = await db.expenses.aggregate([{"$match": exp_q}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        donations = don_r[0]["total"] if don_r else 0
        expenses = exp_r[0]["total"] if exp_r else 0

        ev_q = {**lf}
        checkins = await db.checkins.count_documents(lf)
        events = await db.events.count_documents(ev_q)

        results.append({
            "location_id": lid,
            "location_name": loc.get("name", lid),
            "location_type": loc.get("type", ""),
            "members": members,
            "active_members": active,
            "children": children,
            "families": families,
            "guests": guests,
            "donations": donations,
            "expenses": expenses,
            "net": donations - expenses,
            "events": events,
            "checkins": checkins,
        })

    results.sort(key=lambda x: x["members"], reverse=True)
    totals = {
        "members": sum(r["members"] for r in results),
        "children": sum(r["children"] for r in results),
        "families": sum(r["families"] for r in results),
        "donations": sum(r["donations"] for r in results),
        "expenses": sum(r["expenses"] for r in results),
        "net": sum(r["net"] for r in results),
        "events": sum(r["events"] for r in results),
        "checkins": sum(r["checkins"] for r in results),
    }

    return {"campuses": results, "totals": totals, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/reports/campus/{location_id}")
async def campus_detail_report(location_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Detailed report for a single campus."""
    if not is_system_admin(current_user) and current_user.get("location_id") != location_id:
        raise HTTPException(status_code=403, detail="No access to this campus")

    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="Campus not found")

    lf = {"location_id": location_id}
    date_match = {}
    if date_from:
        date_match["$gte"] = date_from
    if date_to:
        date_match["$lte"] = date_to

    members = await db.members.find(lf, {"_id": 0, "name": 1, "status": 1, "role": 1, "group": 1}).to_list(500)
    children = await db.children.find(lf, {"_id": 0, "name": 1, "class_group": 1}).to_list(500)

    # Group breakdown
    groups = {}
    for m in members:
        g = m.get("group") or m.get("role") or "Unassigned"
        groups[g] = groups.get(g, 0) + 1

    # Monthly trends (last 6 months)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    monthly = []
    for i in range(5, -1, -1):
        d = now - timedelta(days=i * 30)
        month_str = d.strftime("%Y-%m")
        don_q = {**lf, "date": {"$regex": f"^{month_str}"}}
        exp_q = {**lf, "date": {"$regex": f"^{month_str}"}}
        don_r = await db.donations.aggregate([{"$match": don_q}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        exp_r = await db.expenses.aggregate([{"$match": exp_q}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]).to_list(1)
        checkins_month = await db.checkins.count_documents({**lf, "check_in_time": {"$regex": f"^{month_str}"}})
        monthly.append({
            "month": month_str,
            "donations": don_r[0]["total"] if don_r else 0,
            "expenses": exp_r[0]["total"] if exp_r else 0,
            "checkins": checkins_month,
        })

    return {
        "campus": loc,
        "member_count": len(members),
        "children_count": len(children),
        "group_breakdown": groups,
        "monthly_trends": monthly,
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
