"""Consumable manual tracking sheets.

Caregivers at shelters can't always open the CRM, so they fill a printed sheet:
one row per usage line (date, description, initials). At the end of the period
a coordinator uploads the sheet with the total number of servings dispensed —
we convert servings → base unit using the resource's `serving_conversions`
map, then post an "out" movement so on-hand stays in sync with reality.

Default serving conversions are seeded on-demand for common Ugandan pantry
items (rice, posho, beans, sugar, salt, cooking oil, soap). Admins can edit
`resource.serving_conversions` freely via PUT /resources/{id}.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from html import escape as h
import uuid

from deps import db, get_current_user

router = APIRouter(prefix="/api", tags=["consumable-sheets"])


# ── Default serving → base-unit conversions ────────────────────────────
# Ugandan cup ≈ 250 mL (metric cup); Ugandan grocery habits sit closer to a
# handful-cup, so we lean on rough field-observed defaults. Admin can override
# per-resource via the `serving_conversions` field.
DEFAULT_CONVERSIONS = {
    "rice":       [{"unit": "Ugandan cup", "per_base": 0.500, "base": "kg"}],
    "posho":      [{"unit": "Ugandan cup", "per_base": 0.333, "base": "kg"}],  # ~3 cups per kg
    "maize":      [{"unit": "Ugandan cup", "per_base": 0.333, "base": "kg"}],
    "beans":      [{"unit": "Ugandan cup", "per_base": 0.400, "base": "kg"}],
    "sugar":      [{"unit": "Ugandan cup", "per_base": 0.250, "base": "kg"}],
    "salt":       [{"unit": "Ugandan cup", "per_base": 0.200, "base": "kg"}],
    "cooking oil":[{"unit": "Ugandan cup", "per_base": 0.250, "base": "liter"}],
    "oil":        [{"unit": "Ugandan cup", "per_base": 0.250, "base": "liter"}],
    "soap":       [{"unit": "full bar",    "per_base": 1.000, "base": "bar"},
                   {"unit": "quarter bar", "per_base": 0.250, "base": "bar"}],
}


def _guess_conversions(name: str) -> list:
    """Best-effort default conversions from resource name keywords."""
    n = (name or "").strip().lower()
    for k, v in DEFAULT_CONVERSIONS.items():
        if k in n:
            return v
    return []


@router.get("/resources/{res_id}/tracking-sheet")
async def download_tracking_sheet(
    res_id: str,
    month: str = "",
    current_user: dict = Depends(get_current_user),
):
    """Return a printable HTML sheet for the given resource + month.
    Caregivers fill in date, servings dispensed, description, initials.
    Prints two-up on A4 as a functional worksheet; no cover page or footer
    that would waste ink in a rural clinic.
    """
    res = await db.resources.find_one({"id": res_id}, {"_id": 0})
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not res.get("is_consumable"):
        raise HTTPException(status_code=400, detail="Sheets are for consumable resources only")
    from datetime import date as _d
    today = _d.today()
    month_iso = (month or "").strip() or today.strftime("%Y-%m")
    try:
        yr, mo = map(int, month_iso.split("-"))
        title_month = _d(yr, mo, 1).strftime("%B %Y")
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    convs = res.get("serving_conversions") or _guess_conversions(res.get("name"))
    unit_base = res.get("unit") or "unit"
    rows_html = "".join(
        f"<tr><td>{i:02d}</td><td></td><td></td><td></td><td></td></tr>"
        for i in range(1, 32)
    )
    conv_html = "".join(
        f"<li><strong>1 {h(str(c.get('unit')))}</strong> ≈ {c.get('per_base')} {h(str(c.get('base') or unit_base))}</li>"
        for c in convs
    ) or f"<li>No serving conversions configured — admin can add them under Resources → Edit → Serving conversions.</li>"

    html_doc = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Tracking Sheet · {h(res.get('name') or '')}</title>
<style>
  @page {{ size: A4 portrait; margin: 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:#111; margin:0; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  .meta {{ font-size: 11px; color:#444; margin-bottom: 6px; }}
  .box {{ border:1px solid #333; padding:6px 8px; border-radius:4px; margin-bottom:8px; font-size:11px; }}
  .box ul {{ margin: 4px 0 0 18px; padding:0; font-size: 11px; }}
  table {{ width:100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ border:1px solid #444; padding: 4px 6px; text-align:left; height: 22px; }}
  th {{ background:#f2f2f2; font-size: 11px; }}
  td.n {{ width: 30px; text-align:center; font-weight:600; }}
  .foot {{ font-size:10px; color:#555; margin-top:6px; }}
  .print-btn {{ background:#111; color:#fff; padding:6px 12px; border:none; border-radius:4px; cursor:pointer; font-size:12px; }}
  @media print {{ .print-btn {{ display:none; }} }}
</style>
</head><body>
<div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;'>
  <div>
    <h1>{h(res.get('name') or 'Consumable')}</h1>
    <div class='meta'>{h(res.get('location_name') or res.get('location_id') or '58:12 Global')} · Month: <strong>{h(title_month)}</strong> · Base unit: <strong>{h(unit_base)}</strong></div>
  </div>
  <button class='print-btn' onclick='window.print()'>Print sheet</button>
</div>

<div class='box'>
  <div><strong>Serving conversions</strong> (for base-unit accounting):</div>
  <ul>{conv_html}</ul>
</div>

<table>
  <thead><tr><th class='n'>Day</th><th>Servings dispensed</th><th>Description / who it was for</th><th>Time</th><th>Initials</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>

<p class='foot'>Coordinator: upload this sheet on Resources → Consumables → "Upload sheet" and enter the total servings for the month.  We'll convert servings → {h(unit_base)} using the table above and log the movement automatically.</p>
</body></html>"""
    from fastapi.responses import Response
    return Response(content=html_doc, media_type="text/html; charset=utf-8")


@router.post("/resources/{res_id}/tracking-sheet/upload")
async def upload_tracking_sheet(
    res_id: str, data: dict,
    current_user: dict = Depends(get_current_user),
):
    """Coordinator uploads a filled sheet. Body:
      { month:'YYYY-MM', total_servings: number, serving_unit: str,
        note?: str, filled_by?: str, sheet_file_id?: str }
    We look up the resource's serving_conversions, convert to base unit,
    and post a single "out" movement + a `consumable_sheets` audit row.
    """
    res = await db.resources.find_one({"id": res_id}, {"_id": 0})
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not res.get("is_consumable"):
        raise HTTPException(status_code=400, detail="Sheets are for consumable resources only")
    month = (data.get("month") or "").strip()
    try:
        total = float(data.get("total_servings") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="total_servings must be numeric")
    if total <= 0:
        raise HTTPException(status_code=400, detail="total_servings must be > 0")
    serving_unit = (data.get("serving_unit") or "").strip()
    convs = res.get("serving_conversions") or _guess_conversions(res.get("name"))
    match = next((c for c in convs if (c.get("unit") or "").lower() == serving_unit.lower()), None)
    if not match:
        raise HTTPException(status_code=400, detail=f"Unknown serving unit '{serving_unit}' for this resource. Configure it under Resources → Edit → Serving conversions.")
    per_base = float(match.get("per_base") or 0)
    if per_base <= 0:
        raise HTTPException(status_code=400, detail="Serving conversion is misconfigured (per_base must be > 0)")
    base_qty = round(total * per_base, 3)
    # Sanity-check against current on-hand
    from routers.misc import _resource_on_hand
    on_hand = await _resource_on_hand(res_id, res.get("location_id"))
    if base_qty > on_hand + 1e-6:
        raise HTTPException(status_code=400, detail=f"Sheet reports {base_qty} {res.get('unit') or 'unit'} used but only {on_hand} on hand — check the total or restock first")
    now_iso = datetime.now(timezone.utc).isoformat()
    sheet_id = f"csheet_{uuid.uuid4().hex[:10]}"
    sheet = {
        "id": sheet_id,
        "resource_id": res_id,
        "resource_name": res.get("name"),
        "month": month,
        "total_servings": total,
        "serving_unit": serving_unit,
        "base_qty": base_qty,
        "base_unit": res.get("unit"),
        "note": (data.get("note") or "").strip()[:280],
        "filled_by": (data.get("filled_by") or "").strip()[:120],
        "sheet_file_id": (data.get("sheet_file_id") or "").strip()[:80] or None,
        "location_id": res.get("location_id"),
        "uploaded_by": current_user["id"],
        "uploaded_at": now_iso,
    }
    await db.consumable_sheets.insert_one(sheet)
    # Log an out-movement for the base qty (uses existing audit trail)
    movement = {
        "id": f"rmv_{uuid.uuid4().hex[:10]}",
        "resource_id": res_id, "type": "out", "qty": base_qty,
        "location_id": res.get("location_id"),
        "consumer_ref": {"kind": "sheet", "id": sheet_id, "label": f"Sheet · {month or 'manual'}"},
        "note": f"{total} × {serving_unit} (sheet upload)",
        "at": (month + "-01") if month else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "user_id": current_user["id"],
        "timestamp": now_iso,
    }
    await db.resource_movements.insert_one(movement)
    sheet.pop("_id", None); movement.pop("_id", None)
    new_on_hand = await _resource_on_hand(res_id, res.get("location_id"))
    return {"sheet": sheet, "movement": movement, "on_hand": new_on_hand}


@router.get("/resources/{res_id}/tracking-sheets")
async def list_tracking_sheets(
    res_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await db.consumable_sheets.find({"resource_id": res_id}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
