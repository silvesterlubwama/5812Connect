"""iter357 — undelete a journal entry from its stored copy, and the
payday-vs-ledger report.

A. Undelete: a director can put a deleted entry back exactly as it was; it
   counts again, the trail row is marked restored, and it can't be restored
   twice, into a closed period, or when the row has no stored copy.
B. Posting report: each pay period shows paid total vs what reached the ledger,
   names the payslips behind any gap, and balances once they post.
"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from tests.creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")


async def main():
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(f"{name} {extra}".strip())
        print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))

    async with httpx.AsyncClient(base_url=BASE, timeout=90) as c:
        r = await c.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        coa = (await c.get("/api/finance/chart-of-accounts", headers=H)).json()
        accounts = coa if isinstance(coa, list) else (coa.get("accounts") or [])
        expense = next(a for a in accounts if a.get("type") == "expense")
        cash = next(a for a in accounts if a.get("is_cash"))
        locs = (await c.get("/api/locations", headers=H)).json()
        loc_id = (locs if isinstance(locs, list) else locs.get("locations"))[0]["id"]

        def lines(amount):
            return [{"account_id": expense["id"], "debit": amount, "credit": 0},
                    {"account_id": cash["id"], "debit": 0, "credit": amount}]

        async def expenses_total():
            rep = await c.get("/api/finance/reports/pnl?date_from=2020-01-01&date_to=2030-12-31", headers=H)
            return float(rep.json().get("total_expenses") or 0)

        # ── A. undelete ──────────────────────────────────────────────────
        before = await expenses_total()
        r = await c.post("/api/finance/journal", headers=H, json={
            "date": "2026-06-12", "description": "iter357 undelete me",
            "reference": "REF-357", "lines": lines(5500), "location_id": loc_id})
        je_id = r.json()["id"]
        await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H,
                     json={"reason": "iter357 deleted on purpose"})
        check("deleted and no longer counting", round(await expenses_total() - before, 2) == 0.0)

        trail = (await c.get("/api/finance/journal/deleted/list", headers=H)).json()["deleted"]
        row = next((t for t in trail if t["je_id"] == je_id), None)
        check("trail row offers a restore", row is not None and row.get("can_restore") is True,
              str(row and row.get("can_restore")))
        check("trail response hides the raw copy", row is not None and "entry" not in row)

        r = await c.post(f"/api/finance/journal/deleted/{row['id']}/restore", headers=H)
        check("undelete works", r.status_code == 200 and r.json().get("restored") == je_id, r.text[:200])
        check("entry counts again", round(await expenses_total() - before, 2) == 5500.0)

        back = (await c.get(f"/api/finance/journal/{je_id}", headers=H)).json()
        check("restored entry is identical", back.get("total") == 5500.0
              and back.get("reference") == "REF-357" and len(back.get("lines") or []) == 2,
              str({k: back.get(k) for k in ('total', 'reference')}))
        check("restored entry is not marked reversed", not back.get("reversed") and not back.get("voided"))
        check("restored entry records who brought it back", bool(back.get("restored_by_name")),
              str(back.get("restored_by_name")))

        r = await c.post(f"/api/finance/journal/deleted/{row['id']}/restore", headers=H)
        check("second undelete refused", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
        trail = (await c.get("/api/finance/journal/deleted/list", headers=H)).json()["deleted"]
        row2 = next((t for t in trail if t["je_id"] == je_id), None)
        check("trail row marked restored", bool(row2 and row2.get("restored_at")) and row2.get("can_restore") is False,
              str(row2 and {k: row2.get(k) for k in ('restored_at', 'can_restore')}))

        r = await c.post("/api/finance/journal/deleted/nope_357/restore", headers=H)
        check("unknown trail row 404s", r.status_code == 404, str(r.status_code))

        # a row with no stored copy (like the rows rebuilt from the audit log)
        no_copy = next((t for t in trail if t.get("can_restore") is False and not t.get("restored_at")), None)
        if no_copy:
            r = await c.post(f"/api/finance/journal/deleted/{no_copy['id']}/restore", headers=H)
            check("row without a copy is refused clearly",
                  r.status_code == 400 and "line detail" in r.text, f"{r.status_code} {r.text[:140]}")

        # closed period blocks the restore
        await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H, json={"reason": "iter357 for the locked test"})
        trail = (await c.get("/api/finance/journal/deleted/list", headers=H)).json()["deleted"]
        row3 = next(t for t in trail if t["je_id"] == je_id and t.get("can_restore"))
        p = await c.post("/api/finance/fiscal-periods", headers=H, json={
            "name": "iter357 locked", "start_date": "2026-06-01", "end_date": "2026-06-30",
            "location_id": loc_id})
        period_id = p.json()["id"]
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "locked"})
        r = await c.post(f"/api/finance/journal/deleted/{row3['id']}/restore", headers=H)
        check("closed period blocks the undelete", r.status_code == 400 and "clos" in r.text.lower(),
              f"{r.status_code} {r.text[:140]}")
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "open"})
        await c.delete(f"/api/finance/fiscal-periods/{period_id}", headers=H)
        check("ledger back to baseline", round(await expenses_total() - before, 2) == 0.0)

        # ── B. payday vs ledger ──────────────────────────────────────────
        rep = await c.get("/api/hr/payroll/posting-report", headers=H)
        check("report answers", rep.status_code == 200 and "periods" in rep.json(), rep.text[:150])

        staff = (await c.get("/api/hr/salaries", headers=H)).json()
        staff_rows = staff if isinstance(staff, list) else (staff.get("salaries") or [])
        if not staff_rows:
            print("SKIP payroll report checks — no salary records here")
        else:
            s = staff_rows[0]
            r = await c.post("/api/hr/payslips/manual", headers=H, json={
                "staff_id": s.get("staff_id"), "gross_salary": 700000, "allowances": 0,
                "deductions": 0, "period": "2026-07-15", "notes": "iter357 report test",
                "location_id": s.get("location_id") or loc_id})
            pid = r.json()["id"]
            net = float(r.json().get("net_salary") or 0)
            canonical_period = r.json().get("period")
            await c.put(f"/api/hr/payslips/{pid}", headers=H, json={"status": "approved", "reason": "iter357"})
            await c.put(f"/api/hr/payslips/{pid}", headers=H, json={"status": "paid", "reason": "iter357"})

            rep = (await c.get("/api/hr/payroll/posting-report", headers=H)).json()
            mine = next((p for p in rep["periods"] if p["period"] == canonical_period), None)
            check("the pay period is reported", mine is not None,
                  f"{canonical_period} not in {[p['period'] for p in rep['periods']][:5]}")
            if mine:
                # other payslips may share the period, so compare deltas
                check("paid total includes the payslip", mine["paid_total"] >= net - 0.01,
                      f"{mine['paid_total']} vs {net}")
                check("nothing missing once it posted", mine["balanced"] is True and mine["gap"] == 0.0,
                      f"gap {mine['gap']}, unposted {mine['unposted']}")

            # now delete its journal entry — the report must show the gap by name
            je = (await c.get("/api/finance/journal?source=payroll&limit=200", headers=H)).json()
            payroll_je = next(x for x in je if x.get("reference") == pid)
            await c.delete(f"/api/finance/journal/{payroll_je['id']}?reason=iter357 simulate a gap", headers=H)
            rep = (await c.get("/api/hr/payroll/posting-report", headers=H)).json()
            gapped = next((p for p in rep["periods"] if any(u["payslip_id"] == pid for u in p["unposted"])), None)
            check("gap is reported", gapped is not None, str([p['period'] for p in rep['periods']][:5]))
            if gapped:
                check("gap equals the missing pay", abs(gapped["gap"] - net) < 0.01,
                      f"{gapped['gap']} vs {net}")
                check("gap is flagged unbalanced", gapped["balanced"] is False)
                check("gap names the staff member",
                      any(u["payslip_id"] == pid and u.get("staff_name") for u in gapped["unposted"]),
                      str(gapped["unposted"][:1]))
            check("headline totals carry the gap", abs(float(rep["totals"]["gap"])) >= net - 0.01,
                  str(rep["totals"]))

            # the banner's button closes the gap again
            r = await c.post("/api/hr/payslips/post-to-finance", headers=H, json={"payslip_ids": [pid]})
            check("posting closes the gap", r.status_code == 200 and r.json()["posted"] == 1, r.text[:150])
            rep = (await c.get("/api/hr/payroll/posting-report", headers=H)).json()
            fixed = next((p for p in rep["periods"] if p["period"] == (gapped or {}).get("period")), None)
            check("report balances after posting", fixed is not None and fixed["balanced"] is True,
                  str(fixed and fixed.get("gap")))

            # tidy up
            je = (await c.get("/api/finance/journal?source=payroll&limit=200", headers=H)).json()
            for x in [y for y in je if y.get("reference") == pid]:
                await c.delete(f"/api/finance/journal/{x['id']}?reason=iter357 cleanup", headers=H)
            # Paid payslips are audit-locked against the API by design, so this
            # test's own fixture is removed straight from the collection —
            # otherwise every run leaves money in the live payday report.
            mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            mdb.hr_payslips.delete_one({"id": pid})
            mdb.finance_deleted_entries.delete_many({"reason": {"$regex": "iter357"}})

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
