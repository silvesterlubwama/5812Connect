# CHANGELOG

## iter 298 — 2026-02 — Portal self-service · weekly timesheets · wage types · offline pill

**Portal self-service badges** — Two new endpoints under `/api/portal/`:
- `POST /portal/my-wallet-badge` — issues (or returns) the caller's own badge
  token so they can view + Add-to-Wallet from `/badge/<token>`. Idempotent.
- `POST /portal/children/{child_id}/wallet-badge` — parent-only endpoint that
  issues a child's badge as long as `current_user.id` is in `child.parent_ids`
  (falls back to `members.id` lookup for members-linked parents).

Frontend hookups:
- `PortalProfile` — new "My Wallet Badge" card with `View & Download`
  (`data-testid="portal-open-my-badge"`); opens `/badge/<token>` in a new tab
  where existing Add-to-Wallet / auto-print / save-image works.
- `PortalFamily` — every child row now shows a `Badge` button
  (`data-testid="child-badge-<id>"`).

**Weekly Mon–Sun timesheet grid** — `PortalProfile` timesheet dialog replaced
with a 7-cell button grid (M/T/W/T/F/S/S) that auto-computes `days_worked`
from checked days, sends the ISO-week identifier as `period` (`YYYY-Www`),
and includes an `entries[]` daily breakdown so payroll can spot short weeks
and daily-wage staff get accurate gross. Verified via curl:
`POST /hr/timesheets {period:'2026-W09', days_worked:3, entries:[3 dates]}`
→ status=submitted.

**Wage types** — `hr_salaries` now has `wage_type` (one of
salary/hourly/daily/weekly/biweekly/monthly), `hourly_rate`, `daily_rate`.
`_proration_factor` extended: daily → 1/22, hourly → 1/(22×8). Payroll
generation still respects `pay_frequency` for cadence; wage_type describes
how the base amount is expressed.

**Offline pill** — Existing offline detection copy updated: pill now reads
"Offline · Cached" with a hover title explaining the SW is serving the last
online snapshot. `data-testid="offline-pill"`.

**Verification (curl end-to-end)**
- `POST /portal/my-wallet-badge` → token issued, status=active.
- `POST /hr/timesheets` weekly → period=2026-W09, days_worked=3, entries=3.
- `POST /hr/salaries wage_type=daily daily_rate=50000` → fields persist.
- All test rows cleaned up.

---
(prior iter 292–297 entries unchanged)
