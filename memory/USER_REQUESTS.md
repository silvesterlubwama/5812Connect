# Master list of user requests — 58:12 Global Connect CRM

Compiled from PRD.md, CHANGELOG.md, ROADMAP.md and every handoff summary.
Excludes anything the user asked to delete or declared out of scope (see the
last two sections). Iteration numbers are the build in which it shipped.

Legend: ✅ built · 🔁 built then revised later · ⛔ removed on request

---

## 1. Calendar & Events
- ✅ Merge the split `/events` + `/calendar` into one Calendar canvas (events + tasks, month/week/day, task-scope toggle, detail drawer, quick create)
- ✅ Restore the fields lost in that merge: event **type**, **capacity**, **free vs paid** toggle + **price**, visibility switch (iter 344, re-fixed for the create dialog in iter 315)
- ✅ **Ticket tiers** builder (Early Bird / Regular / VIP — own price, capacity) on create *and* edit (iter 316)
- ✅ Delete the orphaned Events page; migrate its live features into the Calendar drawer — registrations (mark-paid + CSV export), check-ins, tier summary, waitlist promote/cancel, Duplicate event (iter 316)
- ✅ **Venue-first location picker**: our venues (restricted campuses excluded) → external venues used before → add a new venue inline → one-off typed address (iter 316)
- ✅ Shareable calendar feeds — global, per-campus and personal share links (JSON + iCal), iCal import/export, webcal subscribe
- ✅ Fix: board tasks with a due date never reached the Google/Apple `.ics` feed (iter 316)
- ✅ Fix: tasks missing from the calendar — default task scope changed from "mine" to "campus" so a due date alone is enough (iter 324)
- ✅ Recurring events dialog
- ✅ Public holidays on the calendar (US federal + Uganda public, server-computed, auto-updating)
- ✅ **Holiday pay policies** — admin marks each holiday Paid / Optional paid day off / Unpaid / Not observed; stored per holiday *name* so it sticks every future year (iter 316)
- ✅ Cross-campus **Move** action for events
- ✅ Public event page + public booking / RSVP / waitlist flow
- ✅ Event & conference notifications actually firing (were silently broken) (iter 310)
- ✅ Event bell deep-link → `/calendar?event=<id>` auto-opens the drawer (iter 311)

## 2. HR, Payroll & Timesheets
- ✅ Per-salary **wage types**: monthly salary / hourly / daily / weekly / biweekly — canonical case "60,000 daily × 10 days = 600,000" (iter 336)
- ✅ **Overtime tier** for hourly staff — weekly threshold (scales with pay window) × multiplier, default 1.5× (iter 337)
- ✅ Hours-worked on timesheets feeding payroll (no more days × 8h guessing) (iter 337)
- ✅ **Holiday pay wired into payroll** (iter 316): hourly get their per-staff holiday hours (default 8) credited on a paid holiday and **stacked on top** of hours actually worked; daily-wage get the day whether they work or not, so working it is **double pay**; optional-paid credits only when not worked; salaried unaffected
- ✅ Holiday markers + explainer in the Portal weekly timesheet grid; holiday credit shown on payslips (iter 316)
- ✅ Payday-driven payslip generation (frequency + weekday snap) + `upcoming-paydays` picker (iter 319)
- ✅ **Payday weekday** setting for weekly/biweekly cadences (iter 309)
- ✅ Biweekly UX cleanup — period labels show the real span `(W38-W39)`, day-of-month picker hidden for non-monthly, Next Pay Date required, backend 400 instead of silent wrong periods (iter 334)
- ✅ **Payroll preview** dry-run before drafting anything (iter 335)
- ✅ Payslip PDF: wage breakdown line + "covers work from … to …" coverage line (iter 335, 337)
- ✅ Delete a **draft** payslip (iter 344)
- ✅ Manual payslip shortcut
- ✅ Weekly Mon–Sun timesheet in the portal (iter 298)
- ✅ **XLSX timesheet template** download (pre-filled with staff + badge + rate) and upload back, matched by badge number (iter 337)
- ✅ **Per-day "Daily Log"** sheet in that template with live hour formulas incl. overnight wraps (iter 338)
- ✅ **Kiosk badge scans autofill timesheets** — punches roll up hours/days, stale punches auto-close after 12h (iter 338)
- ✅ **Punch corrections** — directors edit/delete a bad punch with a required reason, full correction log for audit (iter 339-340)
- ✅ Punches dialog per timesheet row (iter 339-340; crash fixed iter 316)
- ✅ **Time-off self-service** — portal request flow (type, range, half-day, partial hours, notes), live balances, cancel own pending; manager notified (iter 344)
- ✅ HR-managed **leave types** (paid/unpaid, default days, colour) + per-staff allocation overrides (iter 344)
- ✅ **Approval delegation** — a manager filing their own leave names a delegate; delegate's queue and bell include the delegated items (iter 344c)
- ✅ **Manager approval bell** — red numeric pip on the HR icon for pending leave + reimbursements, campus-scoped, excludes own requests (iter 344b)
- ✅ Split-funded salaries by department + per-department expense allocations on paid payslips (iter 320, 321)
- ✅ Payroll allocation strip on the paid-payslip dialog so accountants can trace the split (iter 322)
- ✅ Staff & user admin moved out of `/admin` into HR as a **Staff & Users** tab (iter 306)
- ✅ HR reset moved to System Console → Data & Backup (iter 319)

## 3. Finance & Accounting
- ✅ One unified Finance page (ledger, chart of accounts, reports) — legacy Financial page removed (iter 246, 324)
- ✅ Double-entry journal entries with strict campus/location enforcement
- ✅ **Split (multi-line) transactions**
- ✅ Fix: transactions posted after the split-transactions deploy didn't appear in the UI — every mutation now emits `finance-changed` and the panels subscribe (iter 344e)
- ✅ Fix: split JEs saved empty account code/name (iter 344e)
- ✅ Fix: Transfer dialog had no campus / sub-location field, so transfers silently failed (iter 344e)
- ✅ Cosmetic edits no longer trigger a reverse-and-repost (only real line changes do) (iter 344c)
- ✅ **Delete a reversal** entry (blocked when the period is locked) (iter 344c)
- ✅ Financial edit gate is **period-based**, not a 7-day timer — creator can edit until the fiscal period closes (iter 339-340)
- ✅ Campus / sub-location + department pickers on the quick expense/income dialog, auto-prefilled (iter 325)
- ✅ **Chart of Accounts bulk import** (CSV/XLSX) with template download, skip-existing (iter 326)
- ✅ Receipt Review Queue + receipt OCR scan from the portal (iter 298, 299)
- ✅ AP / bills, bank reconciliation, recurring entries
- ✅ **Sub-location budgets** — hard-cap editor, blank falls back to the auto-rolled department sum (iter 322, 323)
- ✅ **Department P&L** tab — rollup cards, budget bars, run-rate, drill-down to every contributing entry (iter 321, 322, 323)
- ✅ Donation **payer-type** filter (sponsor / parent / org / external) with legacy fallback (iter 331)
- ✅ Sponsor vs parent payment routing — parent contributions post to `4005` at the child's campus, sponsor gifts to `4000` (iter 330, 331)

## 4. People, Families & Guests
- ✅ Unified People page (members, staff, guests) with campus scoping
- ✅ **Family approvals queue** — parent-submitted children and guardians land pending; approve/reject with reason, parent notified either way (iter 344b)
- ✅ **Family change history** — full audit trail per family, plus a global timeline (iter 344c)
- ✅ Guest portal lockdown — pending guests get a restricted screen (browse public events + logout only), guest nav trimmed, family edits disabled until approved (iter 344)
- ✅ Guest access request hardening — rate limit 5/IP/10min, full field validation, atomic max-uses guard, idempotent guest lookup, client IP stored for audit (iter 341)
- ✅ Pending guests can still buy a ticket / RSVP before approval (iter 344b)
- ✅ Sponsors no longer auto-create People rows (iter 333)
- ✅ Bulk-assign users to a department (add or replace) (iter 321)
- ✅ Fix: role edits not persisting when demoting an admin (iter 333)
- ✅ Fix: chat/user directory hid admins, EDs and advisers (global-scope users) (iter 344e)
- ✅ Fix: chat sidebar showed ghost (inactive/suspended) users (iter 344e)
- ✅ Fix: task assignee picker leaked users from other campuses (iter 344e)

## 5. Badges, Kiosk & Access
- ✅ NFC badge issuance + printable badges + bulk sheets
- ✅ Self-service badges in the portal — own badge and each child's (iter 298)
- ✅ PWA **Wallet passes** with offline cache
- ✅ One `UnifiedBadge` component behind every badge surface (wallet, print, bulk, kiosk) (iter 309)
- 🔁 Badge layout, iterated on request: QR to the right column → embed photo in the QR → split them side by side → final order **[Info | QR | Photo]** with photo right-most and no cropping → crown replaced with a star → QR sits on the badge background, no white card → QR resized so long names don't clip (iters 308, 311, 312, 313, 314, 341)
- ✅ Badge PNG download and a proper print flow that actually captures photo + QR (iter 299)
- ✅ Kiosk check-ins — QR scan, PIN check-in, parent lookup, device unlock, warm-up
- ✅ **Ticket scanner page** with camera QR + manual entry, redeem endpoint, persistent result card (iter 329)
- ✅ Ticket scanner shows event date/time + venue so wrong-day scans are obvious (iter 330)
- ✅ **Ticket wallet** in the portal — a QR pass per ticket, door staff redeem it (iter 344c)

## 6. Tasks & Boards
- ✅ Kanban boards with drag & drop, archive/restore, assignees, attachments, live WebSocket board updates
- ✅ Notify assignees when a task is **created** (not just updated) (iter 344)
- ✅ Task bell deep-link → `/tasks?task=<id>` opens that task (iter 312)
- ✅ Overdue-task **director digest** email + in-app preview widget with inline snooze
- ✅ Cross-campus Move for boards/tasks (via board picker) (iter 320)
- ✅ Fix: React error #31 crash on boards (label objects rendered as children) (iter 324)
- ✅ Fix: tasks disappearing right after creation (optimistic-swap race) (iter 324)
- ✅ Fix: editing a task wiped its `board_id` (iter 344d)
- ✅ Fix: boards/admin page timeouts — N+1 counts replaced with aggregations (iter 324)

## 7. Comms
- ✅ Unified comms (chat + calls) with WebRTC calling, Wave CloudUCM integration
- ✅ **Live incoming-call overlay** — global ringing modal with Answer / Reject over any page (iter 333)
- ✅ Notifications consolidated into one router with a role-scoped schema (iter 304)
- ✅ Cleared notifications stay cleared after re-login / redeploy (iter 324)
- ✅ Expense bell deep-link → `/portal/expenses?expense=<id>` scrolls to and highlights the row (iter 313)
- ✅ Dashboard action-item deep-links (overdue tasks, unassigned, pending approvals, expiring passes) (iter 344)
- ✅ Email sending + log + templates (Resend)

## 8. Social Work
- ✅ Case management with family / education / medical / goals sub-records and case notes
- ✅ Review forms (welfare visit, school progress, medical exam) that **auto-populate** the case record, with per-field source pills and a change log (iter 332)
- ✅ Case tabs merged into Education & School / Family & Medical / Goals & Notes (iter 331)
- ✅ Notes newest-first with a "New" pill until read (iter 332)

## 9. Sales, POS, Marketplace & Resources
- ✅ Sales portal, POS kiosk, shipments, customer accounts
- ✅ Products can link a **resource** (auto-books it) or an **event** (auto-issues tickets) (iter 328, 329)
- ✅ Two-way booking lock between staff bookings and marketplace sales (iter 328)
- ✅ POS cart slot picker — edit date/start/end inline before completing a sale (iter 330)
- ✅ Resources page: kind tabs (All / Bookable / Consumable / Unbookable) with live counts + select-all feeding bulk actions (iter 327)
- ✅ Booking conflict guard with a 1-hour buffer across staff and public flows (iter 327)
- ✅ Venues + availability, public venue/resource booking pages, pending-payment tracking

## 10. Admin, Platform & Multi-tenancy
- ✅ Multi-campus / multi-tenant with campus switcher and strict location scoping throughout
- ✅ **Departments as cost centres** (not locations) — multi-department tags on users, split-funded salaries, department-tagged expenses, department P&L (iter 320)
- ✅ Department deactivation guard (409 with live-reference counts, `force` to override) + usage + reassign (iter 321)
- ✅ Console departments shown in the Location editor with a "manage in console" link; legacy free-text departments flagged (iter 333)
- ✅ `/admin` split into **System Console** grouped in 5 tabs — Access, Security, Data & Backup, Integrations, Branding (iter 306, 307)
- ✅ Main-location policy — multi-campus users' new records land at their MAIN campus, not the switched one (iter 319)
- ✅ Reusable cross-campus move dialog (events / boards / products / tasks) (iter 320)
- ✅ 2FA, biometric + NFC login, Google auth, push subscriptions
- ✅ PWA offline data + prefetch on login + offline pill in the header
- ✅ MongoDB hot-path index sweeps across finance / HR / access / everything else (iter 296, 301)
- ✅ `server.py` modularisation 1910 → ~488 lines (schedulers, indexes, seed, route splits) (iter 302, 303, 304)
- ✅ Ghost `db.payslips` collection removed — `hr_payslips` is the only payroll collection (iter 305)
- ✅ Bcrypt/passlib pin locked with a documented compat shim (iter 301)
- ✅ ASGI middleware rewrite — root cause of the intermittent 307s / "No response returned" (iter 322)
- ✅ Repeated demand, now enforced: **no cross-campus data bleed** — restricted locations, campus switcher, shift assignment scoping, chat and directory scoping (iters 324, 344e; recurring theme across 6+ reports)

---

## Explicitly removed / retired on the user's instruction (excluded above)
- ⛔ **Fair Alerts** — router, page, scheduler loop, indexes, route and sidebar entry all wiped (iter 326)
- ⛔ **Legacy `FinancialPage.jsx`** — superseded by the unified Finance page (iter 324)
- ⛔ **`EventsPage.jsx`** — dead code, features migrated into the Calendar drawer (iter 316)
- ⛔ Duplicate v2 guest-access route that shadowed v1 (iter 341)
- ⛔ Ghost `db.payslips` collection (iter 305)

## Declared out of scope / on hold by the user
- Wave H5 SDK native upgrade — *"never suggest again unless I call for it"*
- Native Apple Wallet `.pkpass`
- Kiosk badge full-screen mode
- Portal "everything synced" pill
- Multi-language translation files — on hold until explicitly requested
- Standing instruction: **no unrequested enhancements**

## Mentioned in an old handoff but never confirmed as a user request
Kept here only so nothing is lost. The user removed these from the roadmap
in iter 302 saying they *"were never requested"*, so treat them as ideas, not
commitments: rejected-access-requests tab, missed-call log with call-back,
scheduled auto payslip generation on payday, 200% badge preview zoom,
"migrate to console" button for legacy free-text departments, cron for
overdue-task emails.

> Note: memory files only go back to ~iter 296. Requests from iterations 1–295
> (the original build of comms, finance, HR, kiosk, people, sales and the
> multi-tenant core) are represented by the shipped features listed above
> rather than as individual line items.
