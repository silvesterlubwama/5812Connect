"""Customer statements — branded PDF listing all sales/payments/balance for a customer + period.
Auto-emailed (Resend) or downloaded by admin. Available to customers in their portal too.
"""
from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse
from deps import db, get_current_user, require_staff, logger
from datetime import datetime, timezone, timedelta
from typing import Optional
import io
import os
import uuid

router = APIRouter(prefix="/api", tags=["statements"])


def _render_statement_html(customer: dict, sales: list, period_from: str, period_to: str,
                           location_name: str = "58:12 Global") -> str:
    """Branded customer statement HTML — used as input to WeasyPrint PDF generation."""
    total_billed = sum(float(s.get("total") or 0) for s in sales)
    paid_sales = [s for s in sales if s.get("payment_status", "paid") != "pending"]
    pending_sales = [s for s in sales if s.get("payment_status") == "pending"]
    total_paid = sum(float(s.get("total") or 0) for s in paid_sales)
    total_outstanding = sum(float(s.get("total") or 0) for s in pending_sales)
    currency = sales[0].get("items", [{}])[0].get("currency") if sales and sales[0].get("items") else "UGX"
    rows = "".join([
        f"""
        <tr>
            <td>{s.get('created_at', '')[:10]}</td>
            <td><code>{s.get('receipt_number') or s.get('id')}</code></td>
            <td>{len(s.get('items') or [])} item(s)</td>
            <td>{(s.get('payment_method') or 'cash').replace('_', ' ').title()}</td>
            <td>{'<span style="color:#b45309">PENDING</span>' if s.get('payment_status') == 'pending' else '<span style="color:#047857">PAID</span>'}</td>
            <td style="text-align:right">{currency} {(s.get('total') or 0):,.2f}</td>
        </tr>
        """ for s in sales
    ])
    name = customer.get("name") or customer.get("customer_name") or "Customer"
    phone = customer.get("phone") or customer.get("customer_phone") or ""
    email = customer.get("email") or customer.get("customer_email") or ""
    return f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Customer Statement</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 0; padding: 20mm; color: #1a1a2e; font-size: 11px; }}
  h1 {{ color: #1a1a2e; font-size: 22px; margin: 0; }}
  .accent {{ color: #48a9c5; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #1a1a2e; padding-bottom: 8px; }}
  .logo {{ height: 40px; }}
  .summary {{ background: #f5f7f9; padding: 10px; border-radius: 6px; margin: 12px 0; }}
  .summary-row {{ display: flex; justify-content: space-between; padding: 2px 0; }}
  .summary-row.outstanding {{ font-weight: 700; color: #b45309; font-size: 13px; border-top: 1px solid #cbd5e1; padding-top: 6px; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
  th {{ background: #1a1a2e; color: #fff; padding: 6px; text-align: left; }}
  td {{ padding: 5px 6px; border-bottom: 1px solid #e2e8f0; }}
  .footer {{ margin-top: 20mm; font-size: 9px; color: #64748b; text-align: center; }}
</style></head>
<body>
  <div class="header">
    <div>
      <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1" class="logo" />
      <p style="margin: 2px 0; font-size: 10px; color: #64748b">{location_name}</p>
    </div>
    <div style="text-align: right">
      <h1>Customer Statement</h1>
      <p style="margin: 4px 0 0 0; font-size: 11px">Period: {period_from} → {period_to}</p>
      <p style="margin: 0; font-size: 10px; color: #64748b">Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
  </div>

  <div style="margin-top: 12px">
    <p style="margin: 0; font-size: 13px; font-weight: 700">{name}</p>
    {f'<p style="margin: 2px 0; color: #64748b">{phone}</p>' if phone else ''}
    {f'<p style="margin: 2px 0; color: #64748b">{email}</p>' if email else ''}
  </div>

  <div class="summary">
    <div class="summary-row"><span>Total transactions</span><span>{len(sales)}</span></div>
    <div class="summary-row"><span>Total billed</span><span>{currency} {total_billed:,.2f}</span></div>
    <div class="summary-row"><span>Total paid</span><span style="color: #047857">{currency} {total_paid:,.2f}</span></div>
    <div class="summary-row outstanding"><span>Outstanding balance</span><span>{currency} {total_outstanding:,.2f}</span></div>
  </div>

  <table>
    <thead><tr><th>Date</th><th>Receipt</th><th>Items</th><th>Payment</th><th>Status</th><th style="text-align:right">Amount</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:20px">No transactions in this period.</td></tr>'}</tbody>
  </table>

  <div class="footer">
    Thank you for your business · 58:12 Global<br/>
    Questions? Reply to this email or visit your customer portal.
  </div>
</body></html>
    """


def _html_to_pdf(html: str) -> bytes:
    """Render HTML → PDF bytes. Uses WeasyPrint."""
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"WeasyPrint failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")


@router.get("/customer-statements/{customer_id_or_name}")
async def generate_customer_statement(
    customer_id_or_name: str,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    format: str = "pdf",
    current_user: dict = Depends(get_current_user),
):
    """Generate a customer statement. ?format=pdf (default) or json.
    period_from / period_to default to the current month."""
    if not period_to:
        period_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not period_from:
        first_day = datetime.now(timezone.utc).replace(day=1)
        period_from = first_day.strftime("%Y-%m-%d")
    # Find customer record (by id or name match)
    customer = await db.customer_accounts.find_one(
        {"$or": [{"id": customer_id_or_name}, {"name": customer_id_or_name}]},
        {"_id": 0}
    ) or {}
    # Sales in this period for this customer (match by id or name)
    sale_q = {
        "$or": [{"customer_id": customer_id_or_name}, {"customer_name": customer.get("name") or customer_id_or_name}],
        "voided": {"$ne": True},
        "created_at": {"$gte": period_from + "T00:00:00", "$lte": period_to + "T23:59:59.999"},
    }
    sales = await db.sales.find(sale_q, {"_id": 0}).sort("created_at", 1).to_list(2000)
    customer_view = customer or {"name": customer_id_or_name}
    # Try to fill in phone/email from first sale if missing
    if sales:
        if not customer_view.get("phone") and sales[0].get("customer_phone"):
            customer_view["phone"] = sales[0]["customer_phone"]
        if not customer_view.get("email") and sales[0].get("customer_email"):
            customer_view["email"] = sales[0]["customer_email"]
    if format == "json":
        total_billed = sum(float(s.get("total") or 0) for s in sales)
        total_outstanding = sum(float(s.get("total") or 0) for s in sales if s.get("payment_status") == "pending")
        return {
            "customer": customer_view,
            "period_from": period_from,
            "period_to": period_to,
            "sales": sales,
            "total_billed": total_billed,
            "total_outstanding": total_outstanding,
        }
    html = _render_statement_html(customer_view, sales, period_from, period_to)
    pdf = _html_to_pdf(html)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="statement-{customer_id_or_name}-{period_from}-{period_to}.pdf"'},
    )


@router.post("/customer-statements/{customer_id_or_name}/email")
async def email_customer_statement(
    customer_id_or_name: str,
    data: dict,
    current_user: dict = Depends(require_staff),
):
    """Email the customer statement PDF via Resend.
    Body: { period_from?, period_to?, to_email (override) }"""
    period_from = data.get("period_from")
    period_to = data.get("period_to")
    to_email = (data.get("to_email") or "").strip()
    if not period_to:
        period_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not period_from:
        period_from = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")
    # Resolve customer + recipient
    customer = await db.customer_accounts.find_one(
        {"$or": [{"id": customer_id_or_name}, {"name": customer_id_or_name}]},
        {"_id": 0}
    ) or {}
    sale_q = {
        "$or": [{"customer_id": customer_id_or_name}, {"customer_name": customer.get("name") or customer_id_or_name}],
        "voided": {"$ne": True},
        "created_at": {"$gte": period_from + "T00:00:00", "$lte": period_to + "T23:59:59.999"},
    }
    sales = await db.sales.find(sale_q, {"_id": 0}).sort("created_at", 1).to_list(2000)
    if not to_email:
        to_email = customer.get("email") or (sales[0].get("customer_email") if sales else None)
    if not to_email:
        raise HTTPException(status_code=400, detail="No email on file for this customer — supply to_email")
    html = _render_statement_html(customer, sales, period_from, period_to)
    pdf = _html_to_pdf(html)
    # Send via Resend
    try:
        import resend
        api_key = os.environ.get("RESEND_API_KEY", "")
        sender = os.environ.get("SENDER_EMAIL", "no-reply@5812global.org")
        if not api_key:
            raise HTTPException(status_code=500, detail="RESEND_API_KEY not configured")
        resend.api_key = api_key
        import base64
        name = customer.get("name") or customer_id_or_name
        resend.Emails.send({
            "from": sender,
            "to": to_email,
            "subject": f"Your 58:12 statement for {period_from} → {period_to}",
            "html": f"<p>Hi {name},</p><p>Attached is your account statement for the period {period_from} to {period_to}.</p><p>Thank you,<br/>58:12 Global</p>",
            "attachments": [{
                "filename": f"statement-{period_from}-{period_to}.pdf",
                "content": list(pdf),
            }]
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Statement email failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email failed: {e}")
    # Audit
    await db.statement_emails.insert_one({
        "id": f"stmt_{uuid.uuid4().hex[:8]}",
        "customer_id": customer.get("id"),
        "customer_name": customer.get("name") or customer_id_or_name,
        "to_email": to_email,
        "period_from": period_from,
        "period_to": period_to,
        "sales_count": len(sales),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "sent_by": current_user["id"],
        "sent_by_name": current_user.get("name", ""),
    })
    return {"message": "Statement emailed", "to": to_email, "sales_count": len(sales)}


# ========== AUTOMATIC SCHEDULED STATEMENTS (weekly / monthly) ==========

@router.post("/customer-statements/schedule")
async def schedule_statements(data: dict, current_user: dict = Depends(require_staff)):
    """Configure auto-emailed statements per customer.
    Body: { customer_id, cadence: 'weekly'|'monthly', day_of_week?: 0-6, day_of_month?: 1-28, email? }"""
    cust_id = data.get("customer_id")
    cadence = data.get("cadence")
    if not cust_id or cadence not in {"weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="customer_id + cadence (weekly|monthly) required")
    doc = {
        "id": f"sched_{uuid.uuid4().hex[:8]}",
        "customer_id": cust_id,
        "cadence": cadence,
        "day_of_week": data.get("day_of_week", 0) if cadence == "weekly" else None,
        "day_of_month": data.get("day_of_month", 1) if cadence == "monthly" else None,
        "email_override": data.get("email"),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.statement_schedules.replace_one(
        {"customer_id": cust_id},
        doc,
        upsert=True,
    )
    return doc


@router.get("/customer-statements/schedule/list")
async def list_statement_schedules(current_user: dict = Depends(require_staff)):
    return await db.statement_schedules.find({"active": True}, {"_id": 0}).to_list(500)
