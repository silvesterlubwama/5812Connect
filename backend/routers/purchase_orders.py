"""Purchase Orders — draft → submit → approve → receive → billed → closed.

Lightweight PO module: header + line items on `purchase_orders` collection.
Status transitions gated to prevent skipping (e.g. can't receive an unapproved PO).
Approving posts nothing to the ledger — that only happens when the PO is billed
via /api/finance/transactions/expense with `purchase_order_id`.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user, get_campus_filter, require_manager, require_director

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

STATUSES = {"draft", "submitted", "approved", "received", "billed", "closed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"approved", "draft", "cancelled"},
    "approved": {"received", "cancelled"},
    "received": {"billed", "closed"},
    "billed": {"closed"},
    "closed": set(),
    "cancelled": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_totals(lines: list) -> dict:
    subtotal = 0.0
    for ln in lines:
        try:
            qty = float(ln.get("qty") or 0)
            price = float(ln.get("unit_price") or 0)
        except (TypeError, ValueError):
            qty, price = 0.0, 0.0
        ln["line_total"] = round(qty * price, 2)
        subtotal += ln["line_total"]
    return {"subtotal": round(subtotal, 2)}


async def _next_po_number(location_id: Optional[str]) -> str:
    """Simple per-year sequence — PO-2026-000042."""
    year = datetime.now(timezone.utc).strftime("%Y")
    prefix = f"PO-{year}-"
    last = await db.purchase_orders.find_one(
        {"po_number": {"$regex": f"^{prefix}"}},
        {"_id": 0, "po_number": 1},
        sort=[("po_number", -1)],
    )
    n = 1
    if last:
        try:
            n = int((last.get("po_number") or "").rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    return f"{prefix}{n:06d}"


@router.get("")
async def list_pos(
    status: Optional[str] = None,
    vendor_id: Optional[str] = None,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    scope = await get_campus_filter(current_user)
    q = {**(scope or {})}
    if status and status != "all":
        q["status"] = status
    if vendor_id:
        q["vendor_id"] = vendor_id
    return await db.purchase_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 500))


@router.get("/{po_id}")
async def get_po(po_id: str, current_user: dict = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.post("")
async def create_po(data: dict, current_user: dict = Depends(require_manager)):
    lines = data.get("lines") or []
    if not lines:
        raise HTTPException(status_code=400, detail="At least one line item required")
    for i, ln in enumerate(lines):
        if not (ln.get("description") or "").strip():
            raise HTTPException(status_code=400, detail=f"Line {i + 1}: description required")
        try:
            qty = float(ln.get("qty") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Line {i + 1}: qty must be numeric")
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"Line {i + 1}: qty must be > 0")
        ln["received_qty"] = 0
    totals = _compute_totals(lines)
    loc = data.get("location_id") or current_user.get("active_campus_id")
    po = {
        "id": f"po_{uuid.uuid4().hex[:10]}",
        "po_number": await _next_po_number(loc),
        "vendor_id": data.get("vendor_id"),
        "vendor_name": (data.get("vendor_name") or "").strip()[:120],
        "location_id": loc,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "status": "draft",
        "requested_by": current_user["id"],
        "requested_by_name": current_user.get("name") or "",
        "requested_date": data.get("requested_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "delivery_date": data.get("delivery_date") or "",
        "notes": (data.get("notes") or "")[:500],
        "lines": lines,
        "subtotal": totals["subtotal"],
        "tax": float(data.get("tax") or 0),
        "total": round(totals["subtotal"] + float(data.get("tax") or 0), 2),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.purchase_orders.insert_one(po); po.pop("_id", None)
    return po


@router.put("/{po_id}")
async def update_po(po_id: str, data: dict, current_user: dict = Depends(require_manager)):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po["status"] not in {"draft", "submitted"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit PO in status '{po['status']}'")
    allowed = {"vendor_id", "vendor_name", "delivery_date", "notes", "currency", "lines", "tax"}
    upd = {k: v for k, v in data.items() if k in allowed}
    if "lines" in upd:
        for ln in upd["lines"]:
            ln["received_qty"] = ln.get("received_qty", 0)
        totals = _compute_totals(upd["lines"])
        upd["subtotal"] = totals["subtotal"]
        upd["total"] = round(totals["subtotal"] + float(upd.get("tax") or po.get("tax") or 0), 2)
    elif "tax" in upd:
        upd["total"] = round(po["subtotal"] + float(upd["tax"] or 0), 2)
    upd["updated_at"] = _now()
    await db.purchase_orders.update_one({"id": po_id}, {"$set": upd})
    return await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})


@router.post("/{po_id}/transition")
async def transition(po_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Body: { to: 'submitted'|'approved'|'received'|'billed'|'closed'|'cancelled', receive_lines?: [{line_index, qty}] }"""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    target = (data.get("to") or "").strip().lower()
    if target not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{target}'")
    if target not in ALLOWED_TRANSITIONS.get(po["status"], set()):
        raise HTTPException(status_code=400, detail=f"Cannot go from '{po['status']}' → '{target}'")
    # Approve requires director+; anyone with manager can submit/receive/cancel.
    if target == "approved":
        role = (current_user.get("role") or "").lower()
        if role not in {"admin", "system_admin", "executive director", "adviser", "director"}:
            raise HTTPException(status_code=403, detail="Only Director+ can approve POs")
    upd = {"status": target, "updated_at": _now()}
    stamp_fields = {
        "submitted": "submitted",
        "approved": "approved",
        "received": "received",
        "billed": "billed",
        "closed": "closed",
        "cancelled": "cancelled",
    }
    if target in stamp_fields:
        upd[f"{stamp_fields[target]}_at"] = _now()
        upd[f"{stamp_fields[target]}_by"] = current_user["id"]
    # Handle partial receipts
    if target == "received":
        lines = list(po.get("lines") or [])
        rcv = data.get("receive_lines") or []
        if rcv:
            for r in rcv:
                idx = int(r.get("line_index", -1))
                if 0 <= idx < len(lines):
                    try:
                        lines[idx]["received_qty"] = max(0.0, float(r.get("qty") or 0))
                    except (TypeError, ValueError):
                        pass
        else:
            # Default: mark everything fully received
            for ln in lines:
                ln["received_qty"] = float(ln.get("qty") or 0)
        upd["lines"] = lines
    await db.purchase_orders.update_one({"id": po_id}, {"$set": upd})
    return await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})


@router.get("/{po_id}/pdf")
async def po_pdf(po_id: str, current_user: dict = Depends(get_current_user)):
    """Printable PO on the organisation's letterhead — logo + org name + the
    campus/sub-location the order belongs to (e.g. "Zimba Farm")."""
    from fastapi.responses import Response

    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    settings = await db.global_settings.find_one({"_key": "global"}, {"_id": 0}) or {}
    sys_branding = (await db.system_settings.find_one({"_key": "branding"}, {"_id": 0}) or {})
    org_name = settings.get("org_name") or sys_branding.get("app_name") or "58:12 Global"
    logo_url = settings.get("logo_url") or sys_branding.get("logo_url") or ""
    contact = " · ".join([x for x in [settings.get("contact_address"), settings.get("contact_phone"), settings.get("contact_email")] if x])

    loc_name = ""
    if po.get("location_id"):
        loc = await db.locations.find_one({"id": po["location_id"]}, {"_id": 0, "name": 1})
        if not loc:
            loc = await db.sublocations.find_one({"id": po["location_id"]}, {"_id": 0, "name": 1})
        loc_name = (loc or {}).get("name") or ""

    cur = po.get("currency") or "UGX"

    def esc(v) -> str:
        return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = "".join(
        f"<tr><td>{esc(ln.get('description'))}</td>"
        f"<td class='r'>{float(ln.get('qty') or 0):,.2f} {esc(ln.get('unit'))}</td>"
        f"<td class='r'>{float(ln.get('unit_price') or 0):,.2f}</td>"
        f"<td class='r'>{float(ln.get('line_total') or 0):,.2f}</td></tr>"
        for ln in (po.get("lines") or [])
    ) or "<tr><td colspan='4' class='c muted'>No line items.</td></tr>"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{esc(po.get('po_number'))}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: 'Helvetica','Arial',sans-serif; color:#0f172a; font-size:10.5pt; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start;
           border-bottom:2px solid #0f172a; padding-bottom:10px; margin-bottom:18px; }}
  .org {{ font-size:16pt; font-weight:700; margin:0; }}
  .site {{ font-size:11pt; color:#334155; margin:2px 0 0; }}
  .contact {{ font-size:8pt; color:#64748b; margin-top:4px; }}
  .logo {{ height:58px; }}
  h1 {{ font-size:14pt; margin:0 0 2px; }}
  .meta td {{ font-size:9pt; padding:1px 0; color:#475569; }}
  table.items {{ width:100%; border-collapse:collapse; margin-top:16px; }}
  table.items th {{ background:#f1f5f9; font-size:8.5pt; text-transform:uppercase;
                    letter-spacing:.03em; text-align:left; padding:6px; }}
  table.items td {{ padding:6px; border-bottom:1px solid #e2e8f0; }}
  .r {{ text-align:right; }} .c {{ text-align:center; }} .muted {{ color:#94a3b8; }}
  .totals {{ width:45%; margin-left:55%; margin-top:10px; border-collapse:collapse; }}
  .totals td {{ padding:4px 6px; }}
  .totals tr.grand td {{ border-top:2px solid #0f172a; font-weight:700; font-size:11.5pt; }}
  .notes {{ margin-top:18px; font-size:9pt; color:#475569; border-top:1px solid #e2e8f0; padding-top:8px; }}
  .sign {{ margin-top:34px; display:flex; gap:40px; }}
  .sign div {{ flex:1; border-top:1px solid #94a3b8; padding-top:4px; font-size:8.5pt; color:#64748b; }}
</style></head><body>
  <div class="head">
    <div>
      <p class="org">{esc(org_name)}</p>
      {f'<p class="site">{esc(loc_name)}</p>' if loc_name else ''}
      <p class="contact">{esc(contact)}</p>
    </div>
    {f'<img class="logo" src="{esc(logo_url)}" />' if logo_url else ''}
  </div>
  <h1>Purchase Order {esc(po.get('po_number'))}</h1>
  <table class="meta">
    <tr><td><strong>Vendor:</strong> {esc(po.get('vendor_name'))}</td>
        <td><strong>Status:</strong> {esc((po.get('status') or '').title())}</td></tr>
    <tr><td><strong>Requested:</strong> {esc(po.get('requested_date'))} by {esc(po.get('requested_by_name'))}</td>
        <td><strong>Delivery by:</strong> {esc(po.get('delivery_date') or '—')}</td></tr>
  </table>
  <table class="items">
    <thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Line total</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <table class="totals">
    <tr><td>Subtotal</td><td class="r">{cur} {float(po.get('subtotal') or 0):,.2f}</td></tr>
    <tr><td>Tax</td><td class="r">{cur} {float(po.get('tax') or 0):,.2f}</td></tr>
    <tr class="grand"><td>Total</td><td class="r">{cur} {float(po.get('total') or 0):,.2f}</td></tr>
  </table>
  {f'<div class="notes"><strong>Notes:</strong> {esc(po.get("notes"))}</div>' if po.get('notes') else ''}
  <div class="sign"><div>Approved by</div><div>Received by</div><div>Date</div></div>
</body></html>"""

    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={po.get('po_number', 'purchase-order')}.pdf"},
        )
    except Exception:
        # WeasyPrint unavailable → hand back printable HTML rather than failing.
        return Response(content=html, media_type="text/html")


@router.delete("/{po_id}")
async def delete_po(po_id: str, current_user: dict = Depends(require_director)):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0, "status": 1})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po["status"] not in {"draft", "cancelled"}:
        raise HTTPException(status_code=400, detail="Only draft or cancelled POs can be deleted")
    await db.purchase_orders.delete_one({"id": po_id})
    return {"deleted": True}
