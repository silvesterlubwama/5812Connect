"""iter356 — deleting ledger lines while the period is open, and payroll that
refuses to fail silently.

A. Journal: reverse in an open period DELETES the entry (gone from the journal,
   balances and reports) and writes an audit row naming the user + reason. A
   reason is mandatory. Locked period → contra entry instead, delete refused.
B. Payroll: a paid payslip that cannot post says so — the reason is stamped on
   the payslip, returned to the caller, listed by /hr/payslips/unposted and
   fixable with /hr/payslips/post-to-finance.
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
            # Wide window on purpose: a contra entry is dated TODAY while the
            # entry it reverses keeps its original (closed-period) date, so a
            # narrow window would only see one side of the pair.
            rep = await c.get("/api/finance/reports/pnl?date_from=2020-01-01&date_to=2030-12-31", headers=H)
            return float(rep.json().get("total_expenses") or 0)

        # ── A. delete while the period is open ───────────────────────────
        before = await expenses_total()
        r = await c.post("/api/finance/journal", headers=H, json={
            "date": "2026-06-11", "description": "iter356 delete me",
            "lines": lines(3300), "location_id": loc_id})
        je_id = r.json()["id"]
        check("entry counts once posted", round(await expenses_total() - before, 2) == 3300.0)

        r = await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H, json={"reason": ""})
        check("reason is mandatory", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        r = await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H,
                         json={"reason": "Duplicate — entered twice"})
        check("open period deletes", r.status_code == 200 and r.json().get("deleted") is True, r.text[:200])

        rows = (await c.get("/api/finance/journal?include_reversed=true&limit=1000", headers=H)).json()
        check("gone from the journal entirely", not any(x["id"] == je_id for x in rows))
        check("no contra line posted", not any(x.get("reference") == je_id for x in rows))
        check("stops counting", round(await expenses_total() - before, 2) == 0.0)
        r = await c.get(f"/api/finance/journal/{je_id}", headers=H)
        check("direct read 404s", r.status_code == 404, str(r.status_code))

        trail = (await c.get("/api/finance/journal/deleted/list", headers=H)).json()["deleted"]
        row = next((t for t in trail if t["je_id"] == je_id), None)
        check("audit trail row exists", row is not None)
        if row:
            check("trail names the user", bool(row.get("deleted_by_name")), str(row.get("deleted_by_name")))
            check("trail keeps the reason", row.get("reason") == "Duplicate — entered twice", str(row.get("reason")))
            check("trail keeps the amount", float(row.get("total") or 0) == 3300.0, str(row.get("total")))
            check("trail keeps the lines", len(row.get("lines") or []) == 2, str(len(row.get("lines") or [])))

        audit = await c.get("/api/admin/audit?limit=50", headers=H)
        check("admin audit endpoint answers", audit.status_code == 200, audit.text[:150])
        entries = (audit.json() or {}).get("logs") or []
        hit = next((a for a in entries if a.get("resource_id") == je_id), None)
        check("admin audit log records the delete", hit is not None, f"searched {len(entries)} rows")
        if hit:
            check("admin audit log names the user", bool(hit.get("user_name")), str(hit.get("user_name")))
            check("admin audit log keeps the reason",
                  (hit.get("details") or {}).get("reason") == "Duplicate — entered twice",
                  str(hit.get("details")))

        # ── locked period → contra, and delete refused ───────────────────
        r = await c.post("/api/finance/journal", headers=H, json={
            "date": "2025-04-10", "description": "iter356 locked entry",
            "lines": lines(2200), "location_id": loc_id})
        locked_je = r.json()["id"]
        p = await c.post("/api/finance/fiscal-periods", headers=H, json={
            "name": "iter356 locked", "start_date": "2025-04-01", "end_date": "2025-04-30",
            "location_id": loc_id})
        period_id = p.json()["id"]
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "locked"})

        r = await c.delete(f"/api/finance/journal/{locked_je}?reason=nope", headers=H)
        check("delete refused in a closed period", r.status_code == 400 and "clos" in r.text.lower(),
              f"{r.status_code} {r.text[:150]}")
        r = await c.post(f"/api/finance/journal/{locked_je}/reverse", headers=H,
                         json={"reason": "iter356 closed month"})
        contra = r.json()
        check("closed period posts a contra", r.status_code == 200 and contra.get("source") == "reversal",
              f"{r.status_code} {str(contra)[:150]}")
        check("contra nets to zero", round(await expenses_total() - before, 2) == 0.0)

        # clean up
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "open"})
        r = await c.delete(f"/api/finance/journal/{contra['id']}", headers=H)
        check("deleting a contra needs a reason too", r.status_code == 400, str(r.status_code))
        r = await c.delete(f"/api/finance/journal/{contra['id']}?reason=iter356 cleanup", headers=H)
        check("contra deleted and original released", r.status_code == 200
              and r.json().get("restored_original") == locked_je, r.text[:200])
        await c.post(f"/api/finance/journal/{locked_je}/reverse", headers=H, json={"reason": "iter356 cleanup"})
        await c.delete(f"/api/finance/fiscal-periods/{period_id}", headers=H)
        check("ledger back to baseline", round(await expenses_total() - before, 2) == 0.0)

        # ── B. payroll posts, or says why not ────────────────────────────
        unposted = await c.get("/api/hr/payslips/unposted", headers=H)
        check("unposted endpoint answers", unposted.status_code == 200 and "count" in unposted.json(),
              unposted.text[:150])
        baseline_unposted = unposted.json()["count"]

        staff = (await c.get("/api/hr/salaries", headers=H)).json()
        staff_rows = staff if isinstance(staff, list) else (staff.get("salaries") or [])
        if not staff_rows:
            print("SKIP payroll checks — no salary records in this environment")
        else:
            s = staff_rows[0]
            r = await c.post("/api/hr/payslips/manual", headers=H, json={
                "staff_id": s.get("staff_id"), "gross_salary": 500000, "allowances": 0,
                "deductions": 0, "notes": "iter356 payroll post test", "period": "2026-06-15",
                "location_id": s.get("location_id") or loc_id})
            check("manual payslip created", r.status_code == 200, r.text[:250])
            pid = (r.json() or {}).get("id") or (r.json() or {}).get("payslip", {}).get("id")
            if pid:
                await c.put(f"/api/hr/payslips/{pid}", headers=H,
                            json={"status": "approved", "reason": "iter356"})
                r = await c.put(f"/api/hr/payslips/{pid}", headers=H,
                                json={"status": "paid", "reason": "iter356"})
                paid = r.json()
                check("paid payslip reports its posting state",
                      paid.get("finance_posted") is True or bool(paid.get("finance_post_error")),
                      str({k: paid.get(k) for k in ('finance_posted', 'finance_je_id', 'finance_post_error')}))
                je = await c.get("/api/finance/journal?source=payroll&limit=200", headers=H)
                posted = [x for x in je.json() if x.get("reference") == pid]
                check("payroll landed in the ledger", len(posted) == 1, f"{len(posted)} JEs for {pid}")
                after = (await c.get("/api/hr/payslips/unposted", headers=H)).json()
                check("not listed as unposted", after["count"] == baseline_unposted,
                      f"{baseline_unposted} -> {after['count']}")
                # idempotent: re-posting must not double up
                r = await c.post("/api/hr/payslips/post-to-finance", headers=H, json={"payslip_ids": [pid]})
                check("re-post is a no-op", r.status_code == 200 and r.json()["posted"] == 0, r.text[:150])
                je = await c.get("/api/finance/journal?source=payroll&limit=200", headers=H)
                check("still exactly one payroll JE",
                      len([x for x in je.json() if x.get("reference") == pid]) == 1)
                # tidy: delete the payroll JE and the payslip
                if posted:
                    await c.delete(f"/api/finance/journal/{posted[0]['id']}?reason=iter356 cleanup", headers=H)
                await c.delete(f"/api/hr/payslips/{pid}", headers=H)

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
