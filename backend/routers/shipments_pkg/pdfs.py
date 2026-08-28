"""iter 263 — Printable PDF endpoints for a shipment.

Split out of `items.py` (which was 2000+ lines) so the CRUD path stays
readable and the PDF templates live in one dedicated module. Registered
by `__init__.py` alongside the other shipments submodules — all
`/api/shipments/{id}/…pdf` paths are unchanged.

Endpoints:
- GET /shipments/{id}/manifest.pdf           — customs manifest (WeasyPrint)
- GET /shipments/{id}/schematic.pdf          — A3 3-view container schematic
- GET /shipments/{id}/commercial-invoice.pdf — customs invoice
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime, timezone
import re
from deps import db, logger, require_admin
from ._common import (
    _sort_items_by_box,
    _sort_items_for_invoice,
    _loc_str,
    _resolve_group,
    _PDF_STYLES,
)

router = APIRouter(prefix="/api", tags=["shipments"])


@router.get("/shipments/{shipment_id}/manifest.pdf")
async def shipment_manifest_pdf(shipment_id: str, group: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """Server-rendered printable customs manifest PDF.

    Optional query param `group=<manifest_group_id>` scopes the PDF to a single
    sub-consignment (e.g. "Lubwama Household Relocation").  Use `group=unassigned`
    for items not tagged with any group.  No `group` = the whole container.

    Items are sorted by box number (Box 1 → Box 10 → un-boxed) so packers
    can walk down the container and check off one full box at a time.
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items, group_meta = _resolve_group(s, group)
    # iter 255 — manifest sorted by box number (Box 1 → Box 2 → Box 10 → …
    # then un-boxed) so packers can walk down the container and check off
    # a full box at a time.
    items = _sort_items_by_box(items, s.get("packing_units") or [])
    packing_units = s.get("packing_units") or []
    shipment_title = s.get("name", "")
    heading = shipment_title
    if group_meta:
        heading = f"{shipment_title} · {group_meta.get('name', '')}"
    rows_html = ""
    for i, it in enumerate(items, 1):
        rows_html += (
            f"<tr>"
            f"<td class='n'>{i}</td>"
            f"<td>{(it.get('name') or '')[:80]}</td>"
            f"<td class='hs'>{(it.get('hs_code') or '—')}</td>"
            f"<td class='loc'>{_loc_str(it, packing_units)}</td>"
            f"<td class='c'><span class='cond {it.get('condition','used')}'>{(it.get('condition') or 'used').upper()}</span></td>"
            f"<td class='n'>{it.get('qty_acquired', 0)}</td>"
            f"</tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='6' style='text-align:center;color:#94a3b8;padding:24px'>No items in this manifest</td></tr>"
    total_items = sum(int(it.get("qty_acquired") or 0) for it in items)
    total_weight = sum(float(it.get("weight_kg") or 0) * int(it.get("qty_acquired") or 0) for it in items)
    total_value = sum(float(it.get("value_usd") or 0) * int(it.get("qty_acquired") or 0) for it in items)
    # iter 256 — PVoC classification removed from bulk endpoint.
    consignee_html = ""
    if group_meta and (group_meta.get("consignee_name") or group_meta.get("consignee_address")):
        consignee_html = (
            f"<div class='consignee'><strong>Consignee:</strong> "
            f"{group_meta.get('consignee_name', '')}"
            f"{' — ' + group_meta.get('consignee_address', '') if group_meta.get('consignee_address') else ''}"
            f"</div>"
        )
    html = f"""<html><head><meta charset='utf-8' /><style>{_PDF_STYLES}</style></head><body>
  <div class='head'>
    <div>
      <h1>Container Manifest — {heading}</h1>
      <p class='meta'>Shipment ID: {s.get('id', '')} · Destination: {s.get('dest_country', '—')} · Target ship: {s.get('target_ship_date', '—')}</p>
      <div class='totals'>
        <div><span>Line items:</span> <strong>{len(items)}</strong></div>
        <div><span>Units:</span> <strong>{total_items:,}</strong></div>
        <div><span>Total weight:</span> <strong>{total_weight:,.1f} kg</strong></div>
        <div><span>Declared value:</span> <strong>USD {total_value:,.2f}</strong></div>
      </div>
    </div>
    <div style='text-align:right'>
      <p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p class='meta'>Customs manifest · HS-6 · Sorted by box number</p>
    </div>
  </div>
  {consignee_html}
  <table>
    <thead><tr><th class='n' style='width:32px'>#</th><th>Item</th><th style='width:80px'>HS Code</th><th style='width:180px'>Location</th><th class='c' style='width:70px'>Condition</th><th class='n' style='width:60px'>Qty</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p class='meta' style='margin-top:8mm; text-align:center'>HS codes are 6-digit WCO Harmonized System classifications. Country-specific 8/10-digit suffixes must be applied at destination customs.</p>
</body></html>"""
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Manifest PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (heading or "manifest"))[:60]
    filename = f"manifest_{safe_name}_{shipment_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# iter 262 — Printable 3-view container schematic PDF. Renders the top,
# side, and front elevations of every packing unit + pallet + loose item
# with shape3d, at a fixed scale, on a single A3 landscape page.
@router.get("/shipments/{shipment_id}/schematic.pdf")
async def shipment_schematic_pdf(shipment_id: str, current_user: dict = Depends(require_admin)):
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    cont = s.get("container_dims_cm") or {}
    cont_L = float(cont.get("length_cm") or 1203)
    cont_W = float(cont.get("width_cm") or 235)
    cont_H = float(cont.get("height_cm") or 239)

    # Collect every visible object (packing units + pallets + loose items
    # with shape3d) with its bounding box + shape descriptor for the SVG
    # views. We ignore items nested inside a box.
    objs: list[dict] = []
    for u in (s.get("packing_units") or []):
        L = float(u.get("L_cm") or u.get("length_cm") or 40)
        W = float(u.get("W_cm") or u.get("width_cm") or 40)
        H = float(u.get("H_cm") or u.get("height_cm") or 40)
        x = float(u.get("floor_x_cm") or 0)
        y = float(u.get("floor_y_cm") or 0)
        objs.append({
            "label": u.get("name") or "Box",
            "x": x, "y": y, "z": 0.0,
            "L": L, "W": W, "H": H,
            "shape": u.get("shape") or "box",
            "color": u.get("color") or "#94a3b8",
            "parent_id": u.get("parent_id"),
        })
    # Resolve stack towers: children inherit parent (x,y) and stack on Z.
    by_id = {u.get("id"): u for u in (s.get("packing_units") or [])}
    for i, o in enumerate(objs):
        pu = list(s.get("packing_units") or [])[i]
        pid = pu.get("parent_id")
        z = 0.0
        depth = 0
        while pid and by_id.get(pid) and depth < 20:
            parent = by_id[pid]
            z += float(parent.get("H_cm") or parent.get("height_cm") or 40)
            o["x"] = float(parent.get("floor_x_cm") or 0)
            o["y"] = float(parent.get("floor_y_cm") or 0)
            pid = parent.get("parent_id")
            depth += 1
        o["z"] = z
    for p in (s.get("pallets") or []):
        objs.append({
            "label": p.get("label") or "Pallet",
            "x": float(p.get("x_cm") or 0),
            "y": float(p.get("y_cm") or 0),
            "z": 0.0,
            "L": float(p.get("length_cm") or 120),
            "W": float(p.get("width_cm") or 100),
            "H": float(p.get("height_cm") or 15),
            "shape": "box",
            "color": p.get("color") or "#b38b5d",
            "parent_id": None,
        })
    for it in (s.get("items") or []):
        if it.get("pallet_id") or it.get("packing_unit_id"):
            continue
        sh = it.get("shape3d")
        if not sh:
            continue
        d = it.get("dims_cm") or sh.get("primary") or {}
        L = float(d.get("length") or (sh.get("primary") or {}).get("L_cm") or 30)
        W = float(d.get("width") or (sh.get("primary") or {}).get("W_cm") or 30)
        H = float(d.get("height") or (sh.get("primary") or {}).get("H_cm") or 30)
        objs.append({
            "label": it.get("name") or "Item",
            "x": float(it.get("floor_x_cm") or 0),
            "y": float(it.get("floor_y_cm") or 0),
            "z": 0.0,
            "L": L, "W": W, "H": H,
            "shape": sh.get("kind") or "box",
            "color": sh.get("primary_color") or "#94a3b8",
            "parent_id": None,
        })

    def _svg_rect(obj: dict, ax1: str, ax2: str, len1: str, len2: str, w_cm: float, h_cm: float, scale: float) -> str:
        x = obj[ax1] * scale
        y = (h_cm - obj[ax2] - obj[len2]) * scale
        w = obj[len1] * scale
        h = obj[len2] * scale
        label = (obj["label"] or "")[:22]
        if obj["shape"] in ("cylinder", "sphere") and ax1 == "x" and ax2 == "y":
            r = min(w, h) / 2
            cx = x + w / 2; cy = y + h / 2
            return (
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                f'fill="{obj["color"]}" fill-opacity="0.6" stroke="#1f2937" stroke-width="0.6" />'
                f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="6" text-anchor="middle" fill="#111827">{label}</text>'
            )
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="{obj["color"]}" fill-opacity="0.55" stroke="#1f2937" stroke-width="0.6" />'
            f'<text x="{x + 2:.1f}" y="{y + 8:.1f}" font-size="6" fill="#111827">{label}</text>'
        )

    def _make_view(title: str, ax1: str, ax2: str, len1: str, len2: str, w_cm: float, h_cm: float, view_w_mm: float) -> str:
        scale_mm = view_w_mm / w_cm
        scale = scale_mm
        view_h_mm = h_cm * scale
        rects = []
        rects.append(
            f'<rect x="0" y="0" width="{w_cm * scale:.1f}" height="{h_cm * scale:.1f}" '
            f'fill="#f8fafc" stroke="#334155" stroke-width="1" />'
        )
        for tick in range(0, int(w_cm) + 1, 100):
            xr = tick * scale
            rects.append(
                f'<line x1="{xr:.1f}" y1="0" x2="{xr:.1f}" y2="4" stroke="#94a3b8" stroke-width="0.4" />'
                f'<text x="{xr:.1f}" y="10" font-size="4" text-anchor="middle" fill="#64748b">{tick}</text>'
            )
        for o in sorted(objs, key=lambda o: (o.get("z", 0), o["y"], o["x"])):
            oo = dict(o)
            if ax2 == "z":
                oo["z"] = o["z"]
            rects.append(_svg_rect(oo, ax1, ax2, len1, len2, w_cm, h_cm, scale))
        return (
            f'<div class="view">'
            f'<div class="view-title">{title} — 1 : {int(1000 / scale_mm)} scale</div>'
            f'<svg viewBox="0 0 {w_cm * scale:.0f} {view_h_mm:.0f}" width="{view_w_mm:.0f}mm" height="{view_h_mm:.0f}mm" xmlns="http://www.w3.org/2000/svg">'
            f'{"".join(rects)}'
            f'</svg>'
            f'</div>'
        )

    view_w = 240
    top = _make_view("Top (Plan)", "x", "y", "L", "W", cont_L, cont_W, view_w)
    side = _make_view("Side elevation", "x", "z", "L", "H", cont_L, cont_H, view_w)
    front = _make_view("Front (Door)", "y", "z", "W", "H", cont_W, cont_H, view_w * 0.4)

    ship_name = s.get("name") or "Shipment"
    generated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
  @page {{ size: A3 landscape; margin: 10mm; }}
  body {{ font-family: Helvetica, Arial, sans-serif; color: #0f172a; }}
  h1 {{ font-size: 14pt; margin: 0 0 4mm 0; }}
  .meta {{ font-size: 9pt; color: #475569; margin-bottom: 6mm; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-gap: 6mm; }}
  .view {{ break-inside: avoid; }}
  .view-title {{ font-size: 10pt; font-weight: 600; margin-bottom: 2mm; color: #1e293b; }}
  svg {{ border: 1px solid #cbd5e1; background: white; }}
  .legend {{ margin-top: 4mm; font-size: 8pt; color: #475569; }}
</style></head><body>
  <h1>{ship_name} — Container schematic</h1>
  <div class='meta'>Generated {generated} · Container {int(cont_L)} × {int(cont_W)} × {int(cont_H)} cm · {len(objs)} objects</div>
  <div class='grid'>
    {top}
    <div style='display:flex; flex-direction:column; gap:6mm;'>
      {side}
      {front}
    </div>
  </div>
  <p class='legend'>Top view shows footprint on the container floor. Side and Front elevations show height and stacking. Ruler ticks every 100 cm. Circles denote cylindrical / spherical items; rectangles denote boxes, appliances and compound items.</p>
</body></html>"""

    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Schematic PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (ship_name or "schematic"))[:60]
    filename = f"schematic_{safe_name}_{shipment_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shipments/{shipment_id}/commercial-invoice.pdf")
async def shipment_commercial_invoice_pdf(shipment_id: str, group: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """Printable commercial invoice PDF (customs-grade).

    Columns: # · Item · HS · Origin · Qty · Unit Value · Line Total.
    Same `?group=<gid>` filter + sorted by value / box (see `_sort_items_for_invoice`).
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items, group_meta = _resolve_group(s, group)
    items = _sort_items_for_invoice(items, s.get("packing_units") or [])
    shipment_title = s.get("name", "")
    heading = shipment_title
    if group_meta:
        heading = f"{shipment_title} · {group_meta.get('name', '')}"
    rows_html = ""
    grand_qty = 0
    grand_total = 0.0
    for i, it in enumerate(items, 1):
        qty = int(it.get("qty_acquired") or 0)
        unit_val = float(it.get("value_usd") or 0)
        line_total = unit_val * qty
        grand_qty += qty
        grand_total += line_total
        origin = "USED" if it.get("condition") == "used" else (it.get("condition") or "used").upper()
        rows_html += (
            f"<tr>"
            f"<td class='n'>{i}</td>"
            f"<td>{(it.get('name') or '')[:80]}</td>"
            f"<td class='hs'>{(it.get('hs_code') or '—')}</td>"
            f"<td class='loc'>{origin}</td>"
            f"<td class='n'>{qty}</td>"
            f"<td class='n'>${unit_val:,.2f}</td>"
            f"<td class='n'>${line_total:,.2f}</td>"
            f"</tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='7' style='text-align:center;color:#94a3b8;padding:24px'>No items in this invoice</td></tr>"
    consignee_html = ""
    if group_meta and (group_meta.get("consignee_name") or group_meta.get("consignee_address")):
        consignee_html = (
            f"<div class='consignee'><strong>Consignee:</strong> "
            f"{group_meta.get('consignee_name', '')}"
            f"{' — ' + group_meta.get('consignee_address', '') if group_meta.get('consignee_address') else ''}"
            f"</div>"
        )
    html = f"""<html><head><meta charset='utf-8' /><style>{_PDF_STYLES}</style></head><body>
  <div class='head'>
    <div>
      <h1>Commercial Invoice — {heading}</h1>
      <p class='meta'>Invoice #: CI-{shipment_id[:8].upper()}{'-' + group[:6].upper() if group and group != 'unassigned' else ''} · Destination: {s.get('dest_country', '—')} · Target ship: {s.get('target_ship_date', '—')}</p>
      <p class='meta'>Currency: USD · Terms: Non-commercial personal effects unless marked NEW · Incoterms: as agreed</p>
    </div>
    <div style='text-align:right'>
      <p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p class='meta'>HS-6 · Sorted value ▸ box</p>
    </div>
  </div>
  {consignee_html}
  <table>
    <thead><tr>
      <th class='n' style='width:32px'>#</th>
      <th>Description of Goods</th>
      <th style='width:70px'>HS Code</th>
      <th style='width:170px'>Condition / Origin</th>
      <th class='n' style='width:50px'>Qty</th>
      <th class='n' style='width:75px'>Unit USD</th>
      <th class='n' style='width:85px'>Line Total</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    <tfoot><tr>
      <td colspan='4' style='text-align:right'>TOTAL</td>
      <td class='n'>{grand_qty:,}</td>
      <td></td>
      <td class='n'>${grand_total:,.2f}</td>
    </tr></tfoot>
  </table>
  <div style='margin-top:14mm; display:flex; justify-content:space-between; font-size:10px; color:#334155'>
    <div style='width:45%'>
      <p><strong>Declaration:</strong></p>
      <p>I declare that the information above is true and complete to the best of my knowledge. Items marked USED are donated goods with no commercial value; declared values are for customs valuation purposes only.</p>
      <div style='margin-top:14mm;border-top:1px solid #94a3b8;padding-top:4px'>Authorized signature / Date</div>
    </div>
    <div style='width:45%; text-align:right'>
      <p class='meta'>&nbsp;</p>
    </div>
  </div>
</body></html>"""
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Commercial invoice PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (heading or "invoice"))[:60]
    filename = f"invoice_{safe_name}_{shipment_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
