"""One branded, convertible PDF per financial report (iter375).

The Reports page had a single PDF button that always downloaded the *summary*
PDF, whichever report was on screen — so a trial balance, P&L, balance sheet or
cash flow could never be printed at all. Each now has its own endpoint, on the
organisation's letterhead, and each honours `fx_target` (+ optional `fx_rate`)
using the rates saved in Settings → Exchange rates.
"""
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from deps import require_staff

from .fx import converter, resolve_fx
from .reports import balance_sheet, cashflow, profit_and_loss, trial_balance

router = APIRouter(prefix="/api/finance/reports", tags=["finance"])

_STYLE = """
  @page { size: A4; margin: 16mm; }
  body { font-family: 'Helvetica','Arial',sans-serif; color:#0f172a; font-size: 9.5pt; }
  table.data { width:100%; border-collapse: collapse; margin-top: 4px; }
  table.data th { text-align:left; font-size:7.5pt; text-transform:uppercase; color:#64748b;
                  border-bottom:1px solid #cbd5e1; padding:5px 4px; }
  table.data td { padding:4px; border-bottom:1px solid #f1f5f9; }
  .r { text-align:right; font-variant-numeric: tabular-nums; }
  h2 { font-size:10.5pt; margin:16px 0 2px; }
  tr.tot td { background:#f8fafc; font-weight:700; border-top:1px solid #cbd5e1; }
  .empty { text-align:center; color:#94a3b8; padding:14px; }
  .note { font-size:8pt; color:#475569; margin-top:10px; }
"""


def _rows_table(rows, fx, cols=("code", "name", "amount")) -> str:
    money = converter(fx)
    body = "".join(
        f'<tr><td style="width:60px" class="mono">{r.get("code","")}</td><td>{r.get("name","")}</td>'
        f'<td class="r">{money(r.get("amount")):,.2f}</td></tr>' for r in rows
    ) or '<tr><td colspan="3" class="empty">Nothing in this period.</td></tr>'
    return (f'<table class="data"><thead><tr><th>Code</th><th>Account</th>'
            f'<th class="r">Amount</th></tr></thead><tbody>{body}</tbody></table>')


def _total_row(label, value, fx) -> str:
    money = converter(fx)
    return (f'<table class="data"><tbody><tr class="tot"><td>{label}</td>'
            f'<td class="r">{money(value):,.2f}</td></tr></tbody></table>')


async def _render(title: str, body_html: str, loc_name: str, meta: dict, fx: dict, user: dict, kind: str):
    from routers.reports import branded_filename, report_header_html

    header = await report_header_html(title, loc_name, meta, user, fx=fx)
    html = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{_STYLE}</style></head><body>{header}{body_html}</body></html>")
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"WeasyPrint failed for {kind}: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    filename = await branded_filename(kind)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


async def _loc_name(location_id: Optional[str]) -> str:
    if not location_id:
        return "All campuses"
    from deps import db
    for coll in ("locations", "sublocations"):
        row = await db[coll].find_one({"id": location_id}, {"_id": 0, "name": 1})
        if row:
            return row.get("name") or location_id
    return location_id


@router.get("/trial-balance.pdf")
async def trial_balance_pdf(location_id: Optional[str] = None, date_from: Optional[str] = None,
                            date_to: Optional[str] = None, fx_target: Optional[str] = None,
                            fx_rate: Optional[float] = Query(None),
                            current_user: dict = Depends(require_staff)):
    data = await trial_balance(location_id=location_id, date_from=date_from, date_to=date_to,
                               current_user=current_user)
    fx = await resolve_fx(fx_target, fx_rate)
    money = converter(fx)
    body = "".join(
        f'<tr><td style="width:60px">{r["code"]}</td><td>{r["name"]}</td><td>{r["type"]}</td>'
        f'<td class="r">{money(r["debit"]):,.2f}</td><td class="r">{money(r["credit"]):,.2f}</td>'
        f'<td class="r">{money(r["balance"]):,.2f}</td></tr>' for r in data.get("rows", [])
    ) or '<tr><td colspan="6" class="empty">No postings in this period.</td></tr>'
    html = (f'<table class="data"><thead><tr><th>Code</th><th>Account</th><th>Type</th>'
            f'<th class="r">Debit</th><th class="r">Credit</th><th class="r">Balance</th></tr></thead>'
            f'<tbody>{body}<tr class="tot"><td colspan="3">Total</td>'
            f'<td class="r">{money(data.get("total_debit")):,.2f}</td>'
            f'<td class="r">{money(data.get("total_credit")):,.2f}</td>'
            f'<td class="r">{"balanced" if data.get("balanced") else "OFF"}</td></tr></tbody></table>')
    return await _render("Trial Balance", html, await _loc_name(location_id),
                         {"date_from": date_from, "date_to": date_to}, fx, current_user, "trial-balance")


@router.get("/pnl.pdf")
async def pnl_pdf(location_id: Optional[str] = None, date_from: Optional[str] = None,
                  date_to: Optional[str] = None, fx_target: Optional[str] = None,
                  fx_rate: Optional[float] = Query(None), department_id: Optional[str] = None,
                  current_user: dict = Depends(require_staff)):
    data = await profit_and_loss(location_id=location_id, date_from=date_from, date_to=date_to,
                                 current_user=current_user)
    fx = await resolve_fx(fx_target, fx_rate)
    money = converter(fx)

    # iter379 — each expense account prints WHERE the money went underneath it.
    def spend(rows) -> str:
        out = []
        for r in rows:
            b = r.get("breakdown") or {}
            cells = []
            for title, key in (("Paid to", "payees"), ("By campus", "campuses"),
                               ("By department", "departments")):
                items = b.get(key) or []
                lines = "".join(
                    f'<div style="display:flex;justify-content:space-between;gap:8px">'
                    f'<span>{x["label"]}</span><span>{money(x["amount"]):,.2f}</span></div>'
                    for x in items) or '<div style="color:#94a3b8">—</div>'
                cells.append(
                    f'<td style="vertical-align:top;width:33%;padding:4px 8px 8px 0;border:0">'
                    f'<div style="font-size:7pt;text-transform:uppercase;color:#64748b">{title}</div>'
                    f'{lines}</td>')
            out.append(
                f'<h2>{r["code"]} {r["name"]} — {money(r["amount"]):,.2f}'
                f'{f" ({b.get(chr(101)+chr(110)+chr(116)+chr(114)+chr(105)+chr(101)+chr(115))} payments)" if b.get("entries") else ""}</h2>'
                f'<table class="data" style="font-size:8pt"><tr>{"".join(cells)}</tr></table>')
        return "".join(out)

    html = (f'<h2>Revenue</h2>{_rows_table(data.get("revenue", []), fx)}'
            f'{_total_row("Total revenue", data.get("total_revenue"), fx)}'
            f'<h2>Expenses</h2>{_rows_table(data.get("expenses", []), fx)}'
            f'{_total_row("Total expenses", data.get("total_expenses"), fx)}'
            f'<h2>Result</h2>{_total_row("Net income", data.get("net_income"), fx)}'
            f'<h2 style="margin-top:18px">Where the money went</h2>'
            f'{spend(data.get("expenses", []))}')
    return await _render("Profit & Loss", html, await _loc_name(location_id),
                         {"date_from": date_from, "date_to": date_to}, fx, current_user, "profit-and-loss")


@router.get("/balance-sheet.pdf")
async def balance_sheet_pdf(location_id: Optional[str] = None, as_of: Optional[str] = None,
                            date_to: Optional[str] = None, fx_target: Optional[str] = None,
                            fx_rate: Optional[float] = Query(None),
                            current_user: dict = Depends(require_staff)):
    data = await balance_sheet(location_id=location_id, as_of=as_of or date_to, current_user=current_user)
    fx = await resolve_fx(fx_target, fx_rate)
    html = (f'<h2>Assets</h2>{_rows_table(data.get("assets", []), fx)}'
            f'{_total_row("Total assets", data.get("total_assets"), fx)}'
            f'<h2>Liabilities</h2>{_rows_table(data.get("liabilities", []), fx)}'
            f'{_total_row("Total liabilities", data.get("total_liabilities"), fx)}'
            f'<h2>Equity</h2>{_rows_table(data.get("equity", []), fx)}'
            f'{_total_row("Total equity", data.get("total_equity"), fx)}')
    return await _render("Balance Sheet", html, await _loc_name(location_id),
                         {"date_to": as_of or date_to}, fx, current_user, "balance-sheet")


@router.get("/cashflow.pdf")
async def cashflow_pdf(location_id: Optional[str] = None, date_from: Optional[str] = None,
                       date_to: Optional[str] = None, fx_target: Optional[str] = None,
                       fx_rate: Optional[float] = Query(None),
                       current_user: dict = Depends(require_staff)):
    data = await cashflow(location_id=location_id, date_from=date_from, date_to=date_to,
                          current_user=current_user)
    fx = await resolve_fx(fx_target, fx_rate)
    money = converter(fx)
    body = "".join(
        f'<tr><td>{r.get("code","")}</td><td>{r.get("name") or r.get("description","")}</td>'
        f'<td class="r">{money(r.get("inflow")):,.2f}</td>'
        f'<td class="r">{money(r.get("outflow")):,.2f}</td>'
        f'<td class="r">{money(r.get("net")):,.2f}</td></tr>' for r in data.get("lines", [])
    ) or '<tr><td colspan="5" class="empty">No cash movement in this period.</td></tr>'
    html = (f'<table class="data"><thead><tr><th>Code</th><th>Account</th><th class="r">In</th>'
            f'<th class="r">Out</th><th class="r">Net</th></tr></thead><tbody>{body}'
            f'<tr class="tot"><td colspan="4">Net change</td>'
            f'<td class="r">{money(data.get("net_change")):,.2f}</td></tr></tbody></table>')
    return await _render("Cash Flow", html, await _loc_name(location_id),
                         {"date_from": date_from, "date_to": date_to}, fx, current_user, "cash-flow")
