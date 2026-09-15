"""iter355 — reversing a journal entry in an OPEN period voids it instead of
posting a mirror line, and the entry stops counting everywhere.

Covers: void (no new JE), balances/P&L drop it, it hides from the journal but
shows with include_reversed, restore brings it back, double-void is refused,
and the line-edit path voids-and-reposts (one live line, no contra).
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

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        r = await c.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        coa = (await c.get("/api/finance/chart-of-accounts", headers=H)).json()
        accounts = coa if isinstance(coa, list) else (coa.get("accounts") or [])
        expense = next(a for a in accounts if a.get("type") == "expense")
        cash = next(a for a in accounts if a.get("is_cash"))
        locs = (await c.get("/api/locations", headers=H)).json()
        loc_id = (locs if isinstance(locs, list) else locs.get("locations"))[0]["id"]

        def lines(amount):
            return [
                {"account_id": expense["id"], "debit": amount, "credit": 0},
                {"account_id": cash["id"], "debit": 0, "credit": amount},
            ]

        async def account_balance():
            rep = await c.get(f"/api/finance/chart-of-accounts/{expense['id']}/ledger",
                              headers=H)
            if rep.status_code != 200:
                rep = await c.get("/api/finance/reports/pnl?date_from=2026-01-01&date_to=2030-12-31", headers=H)
                return float(rep.json().get("total_expenses") or 0)
            body = rep.json()
            return float(body.get("closing_balance") if isinstance(body, dict) else 0)

        before = await account_balance()

        # post an entry
        r = await c.post("/api/finance/journal", headers=H, json={
            "date": "2026-06-10", "description": "iter355 void test",
            "lines": lines(4000), "location_id": loc_id})
        check("entry posted", r.status_code == 200, r.text[:200])
        je_id = r.json()["id"]
        after_post = await account_balance()
        check("entry counts", round(after_post - before, 2) == 4000.0, f"{before} -> {after_post}")

        je_count_before = len((await c.get("/api/finance/journal?include_reversed=true&limit=1000", headers=H)).json())

        # reverse it — open period, so it should VOID with no contra line
        r = await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H,
                         json={"reason": "iter355 wrong account"})
        body = r.json()
        check("reverse returns the voided entry", r.status_code == 200 and body.get("voided") is True
              and body.get("id") == je_id, f"{r.status_code} {str(body)[:200]}")

        rows = (await c.get("/api/finance/journal?include_reversed=true&limit=1000", headers=H)).json()
        check("no contra line was posted", len(rows) == je_count_before,
              f"{je_count_before} -> {len(rows)}")
        check("no reversal JE references it", not any(x.get("reference") == je_id and x.get("source") == "reversal" for x in rows))

        after_void = await account_balance()
        check("voided entry stops counting", round(after_void - before, 2) == 0.0,
              f"{before} -> {after_void}")

        live = (await c.get("/api/finance/journal?limit=1000", headers=H)).json()
        check("hidden from the journal by default", not any(x["id"] == je_id for x in live))
        check("visible with include_reversed", any(x["id"] == je_id and x.get("voided") for x in rows))

        # double void refused
        r = await c.post(f"/api/finance/journal/{je_id}/reverse", headers=H, json={"reason": "again"})
        check("second reverse refused", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # restore
        r = await c.post(f"/api/finance/journal/{je_id}/restore", headers=H)
        check("restore works", r.status_code == 200 and not r.json().get("voided"), r.text[:200])
        check("restored entry counts again", round(await account_balance() - before, 2) == 4000.0)
        r = await c.post(f"/api/finance/journal/{je_id}/restore", headers=H)
        check("restoring a live entry refused", r.status_code == 400, str(r.status_code))

        # line edit → void + repost, exactly one live line
        expense2 = next(a for a in accounts if a.get("type") == "expense" and a["id"] != expense["id"])
        r = await c.put(f"/api/finance/journal/{je_id}", headers=H, json={
            "description": "iter355 reclassified",
            "lines": [{"account_id": expense2["id"], "debit": 4000, "credit": 0},
                      {"account_id": cash["id"], "debit": 0, "credit": 4000}]})
        check("line edit accepted", r.status_code == 200, r.text[:200])
        new_id = r.json().get("id")
        check("replacement supersedes the old entry", r.json().get("supersedes") == je_id, str(r.json())[:200])
        rows = (await c.get("/api/finance/journal?include_reversed=true&limit=1000", headers=H)).json()
        old = next(x for x in rows if x["id"] == je_id)
        check("edited-away entry is voided", old.get("voided") is True)
        check("edit posted no contra", not any(x.get("source") == "reversal" and x.get("reference") == je_id for x in rows))
        check("only the corrected line is live",
              round(await account_balance() - before, 2) == 0.0, "original account back to baseline")

        # tidy up so the ledger isn't left with test money in it
        await c.post(f"/api/finance/journal/{new_id}/reverse", headers=H, json={"reason": "iter355 cleanup"})

        # LOCKED period → the classic contra entry, and both sides must stay in
        # the totals so they net to zero (the old code excluded the original and
        # kept its mirror, which is what skewed the reports).
        r = await c.post("/api/finance/journal", headers=H, json={
            "date": "2025-03-10", "description": "iter355 locked-period entry",
            "lines": lines(6000), "location_id": loc_id})
        locked_je = r.json()["id"]
        p = await c.post("/api/finance/fiscal-periods", headers=H, json={
            "name": "iter355 locked", "start_date": "2025-03-01", "end_date": "2025-03-31",
            "location_id": loc_id})
        period_id = p.json()["id"]
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "locked"})
        r = await c.post(f"/api/finance/journal/{locked_je}/reverse", headers=H,
                         json={"reason": "iter355 closed month"})
        contra = r.json()
        check("locked period posts a contra", r.status_code == 200 and contra.get("source") == "reversal"
              and contra.get("reference") == locked_je, f"{r.status_code} {str(contra)[:200]}")
        netted = await account_balance()
        check("contra nets the original to zero", round(netted - before, 2) == 0.0,
              f"baseline {before}, now {netted}")
        r = await c.post(f"/api/finance/journal/{locked_je}/restore", headers=H)
        check("a contra'd entry is not restorable", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
        # clean up: unlock, delete the contra, then void the original
        await c.put(f"/api/finance/fiscal-periods/{period_id}", headers=H, json={"status": "open"})
        await c.delete(f"/api/finance/journal/{contra['id']}", headers=H)
        await c.post(f"/api/finance/journal/{locked_je}/reverse", headers=H, json={"reason": "iter355 cleanup"})
        await c.delete(f"/api/finance/fiscal-periods/{period_id}", headers=H)
        final = await account_balance()
        check("ledger back to baseline after cleanup", round(final - before, 2) == 0.0, f"{before} vs {final}")

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
