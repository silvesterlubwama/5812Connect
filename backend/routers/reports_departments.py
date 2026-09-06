"""Department P&L report — revenue vs expense per cost centre, with
budget bars and run-rate. Reads from three sources:

  1) `expenses.department_id`                  — direct expense tags
  2) `expense_allocations` (payroll splits)    — split-aware payroll
  3) `donations.department_id` (optional)      — revenue by dept, if tagged

Locations & sub-locations roll up: their `budget` totals the child
departments' budgets. Extend as more revenue sources tag departments.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from deps import db, require_manager, get_campus_filter

router = APIRouter(prefix="/api/reports-department", tags=["reports-department"])


@router.get("/pnl")
async def department_pnl(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_manager),
):
    """Per-department revenue, expense, budget, net, and run-rate.

    Response: {
      period: { from, to, days },
      departments: [{
        id, name, color, budget,
        location_id, location_name, sublocation_id, sublocation_name,
        revenue, expense, net,
        run_rate_monthly, budget_used_pct
      }],
      rollups: {
        by_sublocation: [{ sublocation_id, name, budget, expense }],
        by_location: [{ location_id, name, budget, expense }],
      }
    }
    """
    campus = await get_campus_filter(current_user)
    q_dept: dict = {**campus}
    if location_id:
        q_dept["location_id"] = location_id
    departments = await db.departments.find(q_dept, {"_id": 0}).to_list(500)

    # Period defaults: last 30 days if unbounded
    today = datetime.now(timezone.utc).date()
    dt_from = date_from or (today - timedelta(days=30)).isoformat()
    dt_to = date_to or today.isoformat()
    try:
        d_from = datetime.fromisoformat(dt_from).date()
        d_to = datetime.fromisoformat(dt_to).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date_from/date_to")
    days = max(1, (d_to - d_from).days + 1)

    # Expenses tagged directly by department_id
    exp_q = {"department_id": {"$in": [d["id"] for d in departments]},
             "date": {"$gte": dt_from, "$lte": dt_to}}
    exp_by_dept: dict = {}
    async for e in db.expenses.find(exp_q, {"_id": 0, "department_id": 1, "amount": 1}):
        did = e.get("department_id")
        exp_by_dept[did] = exp_by_dept.get(did, 0) + float(e.get("amount") or 0)

    # Payroll allocations (split-aware)
    alloc_q = {"department_id": {"$in": [d["id"] for d in departments]},
               "date": {"$gte": dt_from, "$lte": dt_to}}
    async for a in db.expense_allocations.find(alloc_q, {"_id": 0, "department_id": 1, "amount": 1}):
        did = a.get("department_id")
        exp_by_dept[did] = exp_by_dept.get(did, 0) + float(a.get("amount") or 0)

    # Revenue: donations tagged by department_id (optional dimension)
    rev_q = {"department_id": {"$in": [d["id"] for d in departments]},
             "date": {"$gte": dt_from, "$lte": dt_to}}
    rev_by_dept: dict = {}
    async for r in db.donations.find(rev_q, {"_id": 0, "department_id": 1, "amount": 1}):
        did = r.get("department_id")
        rev_by_dept[did] = rev_by_dept.get(did, 0) + float(r.get("amount") or 0)

    # Location + sublocation names for the rollup
    loc_ids = list({d.get("location_id") for d in departments if d.get("location_id")})
    subloc_ids = list({d.get("sublocation_id") for d in departments if d.get("sublocation_id")})
    locs = {}
    async for l in db.locations.find({"id": {"$in": loc_ids}}, {"_id": 0, "id": 1, "name": 1, "budget": 1}):
        locs[l["id"]] = l
    sublocs = {}
    async for s in db.sublocations.find({"id": {"$in": subloc_ids}}, {"_id": 0, "id": 1, "name": 1, "budget": 1}):
        sublocs[s["id"]] = s

    dept_rows = []
    subloc_agg: dict = {}
    loc_agg: dict = {}
    monthly_factor = 30.0 / days  # projected monthly
    for d in departments:
        did = d["id"]
        expense = round(exp_by_dept.get(did, 0), 2)
        revenue = round(rev_by_dept.get(did, 0), 2)
        budget = float(d.get("budget") or 0)
        used_pct = round((expense / budget * 100), 1) if budget else None
        row = {
            "id": did,
            "name": d.get("name"),
            "color": d.get("color"),
            "location_id": d.get("location_id"),
            "location_name": locs.get(d.get("location_id"), {}).get("name"),
            "sublocation_id": d.get("sublocation_id"),
            "sublocation_name": sublocs.get(d.get("sublocation_id"), {}).get("name"),
            "budget": budget,
            "revenue": revenue,
            "expense": expense,
            "net": round(revenue - expense, 2),
            "run_rate_monthly": round(expense * monthly_factor, 2),
            "budget_used_pct": used_pct,
        }
        dept_rows.append(row)
        # Sub-location rollup: sum department budgets & expenses
        if d.get("sublocation_id"):
            agg = subloc_agg.setdefault(d["sublocation_id"], {"budget": 0.0, "expense": 0.0})
            agg["budget"] += budget
            agg["expense"] += expense
        # Location rollup
        if d.get("location_id"):
            agg = loc_agg.setdefault(d["location_id"], {"budget": 0.0, "expense": 0.0})
            agg["budget"] += budget
            agg["expense"] += expense

    return {
        "period": {"from": dt_from, "to": dt_to, "days": days},
        "departments": sorted(dept_rows, key=lambda x: (x.get("location_name") or "", x["name"])),
        "rollups": {
            "by_sublocation": [
                {"sublocation_id": sid, "name": sublocs.get(sid, {}).get("name"),
                 "budget": round(agg["budget"], 2), "expense": round(agg["expense"], 2)}
                for sid, agg in subloc_agg.items()
            ],
            "by_location": [
                {"location_id": lid, "name": locs.get(lid, {}).get("name"),
                 "budget": round(agg["budget"], 2), "expense": round(agg["expense"], 2)}
                for lid, agg in loc_agg.items()
            ],
        },
    }


@router.get("/{department_id}/entries")
async def department_entries(
    department_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: dict = Depends(require_manager),
):
    """Drill-down for a single department: every expense + payroll
    allocation + tagged donation that contributed to its P&L in the
    given window. Used by the Dept P&L card drill-down modal so admins
    can audit exactly which entries rolled up into the totals.

    Response: { department, entries: [{ kind, id, date, amount, title, note }], totals: {revenue, expense} }
    """
    dept = await db.departments.find_one({"id": department_id}, {"_id": 0})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    # Enforce campus scope: managers can only see departments in their scope
    campus = await get_campus_filter(current_user)
    if campus.get("location_id") and dept.get("location_id") not in (
        campus["location_id"].get("$in") if isinstance(campus.get("location_id"), dict) else [campus.get("location_id")]
    ):
        # loose check: if department's location isn't in the user's scope, forbid
        raise HTTPException(status_code=403, detail="Department outside your campus scope")

    today = datetime.now(timezone.utc).date()
    dt_from = date_from or (today - timedelta(days=30)).isoformat()
    dt_to = date_to or today.isoformat()

    entries = []
    total_exp = 0.0
    total_rev = 0.0

    # 1) Direct expenses
    async for e in db.expenses.find(
        {"department_id": department_id, "date": {"$gte": dt_from, "$lte": dt_to}},
        {"_id": 0, "id": 1, "date": 1, "amount": 1, "title": 1, "notes": 1, "vendor": 1, "category": 1},
    ):
        amt = float(e.get("amount") or 0)
        total_exp += amt
        entries.append({
            "kind": "expense",
            "id": e.get("id"),
            "date": e.get("date"),
            "amount": amt,
            "title": e.get("title") or e.get("vendor") or "Expense",
            "note": e.get("notes") or e.get("category") or "",
        })

    # 2) Payroll allocations (with staff name lookup)
    staff_names: dict = {}
    async for a in db.expense_allocations.find(
        {"department_id": department_id, "date": {"$gte": dt_from, "$lte": dt_to}},
        {"_id": 0, "payslip_id": 1, "staff_id": 1, "amount": 1, "pct": 1, "date": 1},
    ):
        sid = a.get("staff_id")
        if sid and sid not in staff_names:
            u = await db.users.find_one({"id": sid}, {"_id": 0, "name": 1})
            staff_names[sid] = (u or {}).get("name") or "Staff"
        amt = float(a.get("amount") or 0)
        total_exp += amt
        entries.append({
            "kind": "payroll",
            "id": a.get("payslip_id"),
            "date": a.get("date"),
            "amount": amt,
            "title": f"Payroll · {staff_names.get(sid, 'Staff')}",
            "note": f"{a.get('pct') or 0}% allocation",
        })

    # 3) Donations tagged with this department (optional revenue dimension)
    async for r in db.donations.find(
        {"department_id": department_id, "date": {"$gte": dt_from, "$lte": dt_to}},
        {"_id": 0, "id": 1, "date": 1, "amount": 1, "donor_name": 1, "type": 1, "notes": 1},
    ):
        amt = float(r.get("amount") or 0)
        total_rev += amt
        entries.append({
            "kind": "donation",
            "id": r.get("id"),
            "date": r.get("date"),
            "amount": amt,
            "title": r.get("donor_name") or "Donation",
            "note": r.get("type") or r.get("notes") or "",
        })

    entries.sort(key=lambda x: (x.get("date") or "", x.get("kind")), reverse=True)
    return {
        "department": {"id": dept["id"], "name": dept.get("name"), "color": dept.get("color"), "budget": dept.get("budget")},
        "period": {"from": dt_from, "to": dt_to},
        "entries": entries,
        "totals": {"revenue": round(total_rev, 2), "expense": round(total_exp, 2), "net": round(total_rev - total_exp, 2)},
    }
