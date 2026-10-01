"""Expenditure detail — exactly what was spent, and why (iter374).

Every other finance report stops at the account total, so "Programme costs
12,400,000" could never be defended in an audit. This one lists each payment:
date, paid to, purpose, category, amount, campus, who paid it out, who keyed
it in and the receipt/reference number — with subtotals by category and then
by campus.

Two sources, union'd:
  • `finance_journal_entries` — the real double-entry ledger (every debit to an
    expense account), and
  • `expenses` — the staff-portal / cash-request rows, which never reach the
    ledger until approved and were therefore invisible in every report. They
    are flagged `source: "portal"` with their approval status so nobody
    mistakes a pending request for money that has left the account.
"""
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from deps import db, require_staff

router = APIRouter(prefix="/api/finance/reports", tags=["finance"])


def _clean(v) -> str:
    return (str(v).strip() if v is not None else "")


async def _location_names() -> dict:
    names = {}
    for coll in ("locations", "sublocations"):
        async for row in db[coll].find({}, {"_id": 0, "id": 1, "name": 1}):
            names[row["id"]] = row.get("name") or ""
    return names


async def _expense_accounts() -> dict:
    return {a["id"]: a async for a in
            db.finance_chart_of_accounts.find({"type": "expense"}, {"_id": 0})}


async def _ledger_rows(date_from, date_to, location_id, account_code) -> list:
    accounts = await _expense_accounts()
    by_code = {a["code"]: a for a in accounts.values()}
    query: dict = {}
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    if location_id:
        query["location_id"] = location_id
    query["reversed"] = {"$ne": True}

    rows = []
    async for je in db.finance_journal_entries.find(query, {"_id": 0}):
        for line in je.get("lines") or []:
            debit = float(line.get("debit") or 0)
            if debit <= 0:
                continue
            acct = accounts.get(line.get("account_id")) or by_code.get(line.get("account_code"))
            if not acct:
                continue            # not an expense line
            if account_code and acct["code"] != account_code:
                continue
            rows.append({
                "id": je["id"],
                "date": _clean(je.get("date")),
                "amount": round(debit, 2),
                "category": f"{acct['code']} {acct['name']}".strip(),
                "category_code": acct["code"],
                "payee": _clean(je.get("payee")) or _clean(je.get("vendor")) or _clean(je.get("receipt_vendor")),
                "purpose": _clean(je.get("purpose")) or _clean(line.get("memo")) or _clean(je.get("description")),
                "description": _clean(je.get("description")),
                "reference": _clean(je.get("receipt_number")) or _clean(je.get("reference")),
                "paid_by": _clean(je.get("paid_by_name")),
                "recorded_by": _clean(je.get("created_by_name")),
                "location_id": _clean(je.get("location_id")),
                "source": "ledger",
                "status": "posted",
            })
    return rows


async def _portal_rows(date_from, date_to, location_id) -> list:
    query: dict = {"journal_entry_id": {"$in": [None, ""]}}
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    if location_id:
        query["location_id"] = location_id

    rows = []
    async for e in db.expenses.find(query, {"_id": 0}):
        cat = _clean(e.get("budget_category")) or _clean(e.get("category")) or "Uncategorised"
        rows.append({
            "id": e["id"],
            "date": _clean(e.get("date"))[:10],
            "amount": round(float(e.get("amount") or 0), 2),
            "category": cat,
            "category_code": "",
            "payee": _clean(e.get("vendor")),
            "purpose": _clean(e.get("purpose")) or _clean(e.get("notes")) or _clean(e.get("title")),
            "description": _clean(e.get("title")),
            "reference": _clean(e.get("receipt_number")),
            "paid_by": _clean(e.get("paid_by_name")),
            "recorded_by": _clean(e.get("entered_by")),
            "location_id": _clean(e.get("location_id")),
            "source": "portal",
            "status": _clean(e.get("status")) or "pending",
        })
    return rows


async def _build(date_from, date_to, location_id, account_code, include_portal) -> dict:
    rows = await _ledger_rows(date_from, date_to, location_id, account_code)
    # A category filter means "the lines behind this ledger account", so portal
    # rows (which have no account) are out of that drill-down by definition.
    if include_portal and not account_code:
        rows += await _portal_rows(date_from, date_to, location_id)

    names = await _location_names()
    for r in rows:
        r["location_name"] = names.get(r["location_id"]) or ("—" if not r["location_id"] else r["location_id"])
    rows.sort(key=lambda r: (r["date"], r["category"]), reverse=True)

    # Subtotal by category, then by campus inside each category.
    cats: dict = {}
    for r in rows:
        c = cats.setdefault(r["category"], {"category": r["category"], "category_code": r["category_code"],
                                           "total": 0.0, "count": 0, "campuses": {}})
        c["total"] += r["amount"]
        c["count"] += 1
        camp = c["campuses"].setdefault(r["location_name"], {"location_name": r["location_name"], "total": 0.0, "count": 0})
        camp["total"] += r["amount"]
        camp["count"] += 1
    by_category = []
    for c in sorted(cats.values(), key=lambda x: -x["total"]):
        by_category.append({
            "category": c["category"], "category_code": c["category_code"],
            "total": round(c["total"], 2), "count": c["count"],
            "campuses": sorted(({"location_name": v["location_name"], "total": round(v["total"], 2), "count": v["count"]}
                                for v in c["campuses"].values()), key=lambda x: -x["total"]),
        })

    posted = round(sum(r["amount"] for r in rows if r["status"] == "posted"), 2)
    pending = round(sum(r["amount"] for r in rows if r["status"] != "posted"), 2)
    return {
        "rows": rows, "by_category": by_category,
        "total": round(posted + pending, 2), "total_posted": posted, "total_pending": pending,
        "count": len(rows),
        "date_from": date_from or "", "date_to": date_to or "",
        "location_id": location_id or "", "account_code": account_code or "",
    }


@router.get("/expenditure")
async def expenditure_detail(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    location_id: Optional[str] = None,
    account_code: Optional[str] = None,
    include_portal: bool = True,
    current_user: dict = Depends(require_staff),
):
    """Line-by-line expenditure with category → campus subtotals."""
    return await _build(date_from, date_to, location_id, account_code, include_portal)


@router.get("/expenditure.pdf")
async def expenditure_pdf(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    location_id: Optional[str] = None,
    account_code: Optional[str] = None,
    include_portal: bool = True,
    current_user: dict = Depends(require_staff),
):
    from routers.reports import report_header_html, branded_filename

    data = await _build(date_from, date_to, location_id, account_code, include_portal)
    loc_name = "All campuses"
    if location_id:
        names = await _location_names()
        loc_name = names.get(location_id, location_id)

    def money(v):
        return f"{float(v or 0):,.2f}"

    lines = "".join(
        f'<tr><td>{r["date"]}</td><td>{r["payee"] or "—"}</td><td>{r["purpose"] or "—"}</td>'
        f'<td>{r["category"]}</td><td>{r["location_name"]}</td><td>{r["paid_by"] or "—"}</td>'
        f'<td>{r["recorded_by"] or "—"}</td><td>{r["reference"] or "—"}</td>'
        f'<td class="r">{money(r["amount"])}</td>'
        f'<td>{"" if r["status"] == "posted" else r["status"]}</td></tr>'
        for r in data["rows"]
    ) or '<tr><td colspan="10" class="empty">No expenditure in this period.</td></tr>'

    subtotals = "".join(
        f'<tr class="cat"><td colspan="2"><strong>{c["category"]}</strong></td>'
        f'<td class="r">{c["count"]}</td><td class="r"><strong>{money(c["total"])}</strong></td></tr>'
        + "".join(f'<tr><td></td><td>{camp["location_name"]}</td><td class="r">{camp["count"]}</td>'
                  f'<td class="r">{money(camp["total"])}</td></tr>' for camp in c["campuses"])
        for c in data["by_category"]
    ) or '<tr><td colspan="4" class="empty">Nothing to subtotal.</td></tr>'

    header = await report_header_html("Expenditure Detail", loc_name, data, current_user)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Expenditure Detail</title>
<style>
  @page {{ size: A4 landscape; margin: 14mm; }}
  body {{ font-family: 'Helvetica','Arial',sans-serif; color:#0f172a; font-size: 8.5pt; }}
  table {{ width:100%; border-collapse: collapse; }}
  th {{ text-align:left; font-size:7.5pt; text-transform:uppercase; color:#64748b; border-bottom:1px solid #cbd5e1; padding:4px; }}
  td {{ padding:3px 4px; border-bottom:1px solid #f1f5f9; vertical-align:top; }}
  .r {{ text-align:right; font-variant-numeric: tabular-nums; }}
  .empty {{ text-align:center; color:#94a3b8; padding:14px; }}
  h2 {{ font-size:10pt; margin:16px 0 6px; }}
  tr.cat td {{ background:#f8fafc; }}
  .totals {{ margin-top:10px; font-size:9.5pt; }}
</style></head><body>
{header}
<h2>Every payment</h2>
<table><thead><tr><th>Date</th><th>Paid to</th><th>Purpose</th><th>Category</th><th>Campus</th>
<th>Paid by</th><th>Recorded by</th><th>Ref / receipt</th><th class="r">Amount</th><th>Status</th></tr></thead>
<tbody>{lines}</tbody></table>
<div class="totals">
  <strong>Posted to the ledger:</strong> {money(data["total_posted"])} &nbsp;·&nbsp;
  <strong>Awaiting approval:</strong> {money(data["total_pending"])} &nbsp;·&nbsp;
  <strong>Total:</strong> {money(data["total"])} ({data["count"]} payments)
</div>
<h2>Subtotals — by category, then campus</h2>
<table><thead><tr><th>Category</th><th>Campus</th><th class="r">Payments</th><th class="r">Amount</th></tr></thead>
<tbody>{subtotals}</tbody></table>
</body></html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"WeasyPrint failed for expenditure.pdf: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    filename = await branded_filename("expenditure")
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/expenditure/meta")
async def expenditure_meta(current_user: dict = Depends(require_staff)):
    """Generated-at stamp, so the on-screen report can show the same audit line."""
    return {"printed_on": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "prepared_by": current_user.get("name") or ""}
