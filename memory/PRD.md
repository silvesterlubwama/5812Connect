# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Completed Features (Iterations 49-78)
All features documented in /app/ADMIN_GUIDE.md and /app/memory/CHANGELOG.md.

## Recently Resolved — Iteration 111 (May 20, 2026)
**Full backlog single-pass: P1 follow-ups + P3/P4 frontend + cross-module integrations + Calendar/Discuss/Docs polish.**

### P1 follow-ups
- ✅ **Sales auto-post journal entry** — when a sale is created and a sales-kind journal exists at its location, `_auto_post_sale_journal_entry` automatically writes a balanced posted entry (Cash/AR debit, Revenue credit), tagged `auto_generated_from='sale'`. Curl-verified: cash sale 500 → JE `SAL/202605/0003` posted.
- ✅ **Asset depreciation schedules** — `GET /accounting/assets/{id}/depreciation-schedule?method=straight_line|declining_balance` returns full monthly schedule with rounding-correct last month; `POST /accounting/assets/{id}/depreciate/{period}` posts a balanced JE for one period (Dep Expense Dr / Accum Dep Cr) — idempotent per asset+period. Curl-verified: $2,400 / 36 months → $66.67/mo straight-line.

### P3 frontend
- ✅ **Task time-tracking widget** in `CardDetailDialog` — Play/Stop button with live HH:MM:SS timer, manual "Log minutes" form, per-task entries list with delete, total hours summary.

### P4 frontend
- ✅ **Approvals page** (`/approvals`) with 4 tabs: Inbox (pending my action), My Requests, All, Workflows. New-Workflow dialog supports multi-step roles + min_approvals; New-Request dialog selects workflow + amount/currency. View-request dialog shows full approval chain with per-step status, approvals log, and inline Approve/Reject buttons with decision-note input.
- ✅ Sidebar nav (Finance > Approvals) + route registered.

### Cross-module integration (suggested improvement)
- ✅ **HR Reimbursement ≥ $100 auto-spawns approval request** against any `kind:expense` workflow for the campus. Links `approval_request_id` back on the expense. Curl-verified: $350 expense → automatic `areq_*` created and surfaces in the admin's Inbox.

### Calendar / Discuss / Docs polish
- ✅ **Chat @mentions** — `POST /chat/conversations/{id}/messages` now parses `@username` tokens, resolves them against conversation participants, stores on the message, and fires individual `chat_mention` notifications (DB + WebSocket).
- ✅ **Document versioning** — uploading a new doc with the same `(member_id, doc_type, label)` auto-increments `version`, sets `version_chain_id`, and marks the prior as `superseded_by`. New `GET /documents/{id}/versions` returns the full chain.
- ✅ **Calendar RRULE-style recurrence** — verified existing recurrence_pattern + recurrence_days_of_week + recurrence_week_of_month already covers all common Odoo recurrence cases (weekly, biweekly, monthly date, monthly nth-weekday, quarterly, yearly).

## Recently Resolved — Iteration 110 (May 20, 2026)
**P1 Accounting depth + P3 task time-tracking + P4 multi-step approval workflows.**

### P1 — Full double-entry Accounting module (new `/api/accounting` router + `/accounting` page)
- ✅ **Chart of Accounts** — 16 standard account types (asset/liability/equity/income/expense subtypes with category + normal_balance) + 21-account default CoA seed (`POST /accounting/seed`) covering Cash/Bank/AR/Inventory/Fixed/Equity/Revenue/COGS/Expenses.
- ✅ **Journals** — Sales/Purchases/Bank/Cash/Misc with default debit/credit accounts; protective deactivate-instead-of-delete when entries exist.
- ✅ **Double-entry ledger** — `POST /accounting/entries` enforces balanced debits/credits, ≥2 lines, valid accounts; `/post` flips draft → posted (immutable), `/cancel` (drafts only), `/reverse` (posted only — creates inverse draft).
- ✅ **Tax codes** — name/rate/kind(sales|purchase)/inclusive flag, with account_id pointing to a tax-payable account.
- ✅ **Fiscal periods** — open/closed/locked statuses; locked periods block any entry create/post in their date range.
- ✅ **Reports** — `/reports/trial-balance` (debit=credit reconciliation), `/reports/profit-loss` (income − expense = net profit), `/reports/balance-sheet` (assets vs liabilities+equity+retained net profit), `/accounts/{id}/ledger` (per-account chronological postings with running balance).
- ✅ New **`/accounting` page** with summary cards (TB/Income/Expense/Net Profit), 6 tabs (Entries/CoA/Journals/Taxes/Fiscal/Reports), full create/post/reverse/cancel workflow, drill-into-ledger from any account, and balance-sheet display. Curl-verified: balanced TB, P&L 1000/0/1000, BS 1000=0+1000.

### P3 — Task time-tracking
- ✅ `POST /tasks/{id}/time/start` (idempotent timer) → `/stop` (auto-duration), `/log` (manual minutes for past work, max 24h/entry), `/time` (list + total hours), `/time/me/active` (current running timer), DELETE (owner-only).

### P4 — Multi-step approval workflows (new `/api/approvals` router)
- ✅ **Workflows** template: kind + ordered steps (each with `approver_role` OR `approver_user_id` + `min_approvals`).
- ✅ **Requests** lifecycle: submit (snapshots the workflow template) → act (approve/reject the current step) → auto-advance when min_approvals hit → finalize on last step OR on any rejection.
- ✅ **Role hierarchy** authorization — Director can approve Manager-level steps; admin/Executive Director can override any step.
- ✅ **Delegation** — current approver can delegate the active step to another user (e.g. while on leave).
- ✅ Anti-double-vote per step, submitter-only cancel, immutable after finalize.

## Recently Resolved — Iteration 109 (May 20, 2026)
**Attendance / Clock-in-out + per-staff Compensation Summary PDF.**

### Attendance / Time-tracking
- ✅ `POST /api/hr/attendance/clock-in` (idempotent), `POST /api/hr/attendance/clock-out` (duration calc), `GET /api/hr/attendance/me/active`, `GET /api/hr/attendance` (own or scoped HR), `PUT /attendance/{id}` (HR correction), `DELETE`, `GET /attendance/summary?period=YYYY-MM` (per-staff total minutes, days_present).
- ✅ HR page **Attendance tab** with live HH:MM:SS timer, big Clock In/Out card, my recent entries, HR-scoped team summary cards per month, team activity feed.

### Compensation Summary PDF
- ✅ `GET /api/hr/staff/{id}/compensation-summary?year=YYYY&format=pdf|json` aggregates salary on file, intra-year salary changes, payslips (gross/net/deductions), leave taken by type, reimbursements paid → renders branded WeasyPrint PDF with totals block + 4 detail tables. Self-only access for non-HR; HR sees anyone.
- ✅ Download button (FileText icon) added to each salary card on the HR page.

## Recently Resolved — Iteration 108 (May 20, 2026)
**Suggested improvement: auto unpaid-leave payroll proration + Employee Expense Reimbursement.**

### Auto unpaid-leave proration (HR ↔ Payroll loop)
- ✅ Payslip generation (`_generate_payslips_for`) now consults `hr_leave_requests` per staff/period. Any approved leave whose type is `paid=false` (default `unpaid` + campus-customized non-paid types) prorates gross by `(unpaid_business_days / total_business_days_in_period)`.
- ✅ Auto-generated `"Unpaid leave proration"` deduction line item is added with `auto_generated: true` and human-readable details — fully transparent for staff review.
- ✅ Payslip now exposes `unpaid_leave_days`, `working_days`, `unpaid_leave_proration` fields for reporting.

### Employee Expense Reimbursement
- ✅ `POST /api/hr/expenses` (employee submits) → `PUT /api/hr/expenses/{id}` (owner edits while pending OR HR approve/reject/mark-reimbursed) → `DELETE` (with state-aware guards).
- ✅ `GET /api/hr/expenses/summary?period=YYYY-MM` returns totals + by-status + by-category + by-staff breakdowns.
- ✅ Categories: travel, meals, supplies, training, fuel, accommodation, other.
- ✅ HR page has a **Reimbursements tab** with status filters (all/pending/approved/reimbursed/rejected), submit/edit dialogs, Decide/Mark-Paid actions, and receipt URL link.

## Recently Resolved — Iteration 107 (May 20, 2026)
**P0 wire-ups (reorder dashboard + POS pricelist) + P2 HR Leave/Time-off Management.**

### P0 wire-ups
- ✅ **Dashboard reorder-alerts card** now uses `/api/products/reorder-alerts` (supports per-variant alerts, not just product-level stock).
- ✅ **POS pricelist auto-apply** — new 👤 customer picker on the POS cart sidebar; selecting a registered customer fetches their pricelist and shows an emerald "Pricelist: VIP Tier · -10%" banner. `addToCart` then resolves the effective price via `/api/pricelists/resolve` (override OR blanket %); toast shows "custom price/discount applied".

### P2 HR Leave / Time-off Management
- ✅ **6 default leave types** (Annual 21d, Sick 10d, Unpaid, Maternity 60d, Paternity 7d, Bereavement 5d) — campus-overridable via `PUT /api/hr/leave/types`.
- ✅ **Personal balances** — `GET /api/hr/leave/balance` returns allocated/used/remaining per type for the current year. Per-user allocation overrides via `PUT /api/hr/leave/allocation/{staff_id}` (director+).
- ✅ **Request lifecycle** — submit (`POST /leave/requests` — business-day count, half-day support, end ≥ start guard) → approve/decline by HR or cancel by owner (`PUT /leave/requests/{id}`). HR-only filing on behalf of others.
- ✅ **Calendar view** — `GET /api/hr/leave/calendar?month=YYYY-MM` returns all approved leaves overlapping the month for the HR planning view.
- ✅ **HR page** has a new "Leave" tab with balance pills, requests list, decision dialog, and a "New Request" dialog.

## Recently Resolved — Iteration 106 (May 12, 2026)
**Events 2.0 (multi-tier tickets + waitlist + CSV export) + P0 Inventory: stock movements, reorder alerts, customer pricelists.**

### Events 2.0
- ✅ **Multi-tier tickets** — `ticket_tiers[]` on Event (id/name/price/capacity/sold/description). Public registration accepts `tier_id`; per-tier sold counter updates atomically. Admin tier editor in EventsPage Add/Edit dialog.
- ✅ **Waitlist** — `POST /api/public/events/{id}/waitlist` (no auth), `GET/POST/DELETE /api/events/{id}/waitlist[/{wl_id}[/promote]]`. PublicBookingsPage prompts to join waitlist on 409 "sold out". EventsPage detail dialog has a Waitlist tab with one-click Promote/Cancel.
- ✅ **Attendee CSV export** — `GET /api/events/{id}/attendees/export` with Export CSV button in event detail.

### P0 Inventory upgrades (Odoo-parity)
- ✅ **Stock movements log** — `POST /api/products/{id}/stock-movement` (delta/reason/notes/reference, with insufficient-stock guard). `GET /api/products/{id}/stock-movements` per-product log + `GET /api/stock-movements` warehouse-wide log.
- ✅ **Reorder alerts** — `GET /api/products/reorder-alerts` returns products (and per-variant entries) at or below their `reorder_level`.
- ✅ **Customer pricelists** — `pricelists` collection with optional explicit `product_prices[]` overrides + blanket `discount_pct`. `GET /api/pricelists/resolve?customer_id=&product_id=&variant_id=` returns effective price with source attribution.

## Recently Resolved — Iteration 105 (May 12, 2026)
**Salary-change audit timeline + Tiered dunning escalation ladder + Payment Promises.**
- ✅ **Salary History** — every `PUT /api/hr/salaries/{id}` now writes a diff record to `db.hr_salary_history` (from→to per field, reason, who/when/role). New `GET /api/hr/salaries/history?staff_id=…` endpoint. HR page Salaries tab now shows a clock-history icon on each card that opens a timeline dialog. Edit dialog accepts an optional "Reason" field.
- ✅ **Tiered dunning ladder** — `_fire_overdue_payment_reminders()` rewritten with 3 tiers: T1 gentle (≥14d), T2 firmer + 5% late-fee preview (≥30d), T3 final notice w/ auto-CC to a manager/director email (≥60d). Tier-keyed idempotency means each tier sends at most once per customer.
- ✅ **Payment Promises** — `POST /api/accounts-receivable/promise` + `DELETE /api/accounts-receivable/promise/{customer_key}`. AR endpoint enriched with `last_reminder.tier` & `payment_promise`. AR cards now show a tier badge and "Promised YYYY-MM-DD" badge in emerald; promised customers are auto-paused from dunning until their date elapses.

## Recently Resolved — Iteration 104 (May 12, 2026)
**Director salary editing + Reassign Location Data tool + Finance prompt() cleanup.**
- ✅ **Edit Salaries** — pencil icon on each salary card in HR opens the same dialog prefilled; calls `PUT /api/hr/salaries/{id}` (Directors+ already authorized server-side). Staff cannot be changed when editing.
- ✅ **Reassign Location Data** — new admin tool on Locations page: `GET /api/admin/reassign/preview` shows counts across 12 collections (events/tasks/boards/members/users/financial/sales/products/resources/hr_*); `POST /api/admin/reassign/run` bulk-moves records + patches `location_ids[]` arrays. Validates differing source/target, verifies target exists, audits the action.
- ✅ **Finance prompt() cleanup** — last `window.prompt()` (receipt URL upload) replaced with a proper Dialog.

## Recently Resolved — Iteration 103 (May 12, 2026)
**Payment Reminder Email Automation — verified via curl + UI screenshot.**
- ✅ `POST /api/payment-reminders/send` (manual trigger, 7-day idempotency, `force=true` override)
- ✅ `GET /api/payment-reminders/history` (audit log)
- ✅ `_fire_overdue_payment_reminders()` daily scheduler at 08:00 UTC — auto-detects AR ≥14 days old, generates Customer Statement PDF, emails via Resend
- ✅ AR page "Email Reminder" button + WhatsApp deep-link (gracefully handles "sent in last 7 days" with confirm-to-force prompt)

## Recently Resolved — Iteration 82 (May 2, 2026)
**Verified 14/14 backend tests PASS + frontend 100%.**
- ✅ **Mark-as-Paid toggle** — `PUT /api/sales/{id}/payment-status`; cash auto-paid, non-cash default pending; UI buttons in Sales History; UNPAID shown on receipt/profile/public page; revert clears metadata
- ✅ **Boards admin-filter** — breaking change; admins now follow same access rules as regular users (tagged/created/tasked/in-scope/global-not-restricted)

## Recently Resolved — Iteration 81 (May 2, 2026)
**Verified 13/13 backend tests PASS + frontend 100%.**
- ✅ **financial.py split** 1458→1003 lines + new `sales.py` (227) + `products.py` (154) + `sheet_import.py` (111)
- ✅ **Customer profile receipt-tracking UI** — clickable rows in Sales → Customers open a dialog with Total Spent / Transactions / Last Visit + full receipt history + view-receipt buttons
- ✅ **Auto-detect printer paper size** — `window.matchMedia` heuristic picks 58/80/A5/A4; manual override wins
- ✅ **Inline approve/decline on expenses** — pending rows show ✓ Approve and ✕ Reject directly (finance admins only); reject prompts for reason

## Recently Resolved — Iteration 80 (May 2, 2026)
**Verified 12/12 backend tests PASS + frontend confirmed.**

**P0 Bugs Fixed:** starting balance account-id, expense workflow (status-based), variant save, HR nav visibility, restricted locations UI, chat org structure, expense delete lag.

**Receipt Overhaul:** atomic `INV-YYYYMMDD-NNNN`, 58:12 logo, tracking QR, per-kiosk paper sizes (58mm/80mm/A5/A4), public verification page at `/receipt/:number`, WhatsApp share, variant-aware stock decrement.

**Park / Parked Sales:** shared per-campus drafts with reopen/discard.

**Google Sheet Financial Integration:** extended expense schema (vendor/account/department/budget_category/usd_equivalent), Advanced section in Add Expense, CSV-paste importer auto-normalizing DD/MM dates and currency-prefixed amounts.

## Recently Resolved — Iteration 79 (May 1, 2026)
Verified 20/20 backend tests PASS + frontend 100%.

- ✅ **MongoDB indexes audit** (40+ indexes, idempotent) — `sessions.jti` unique, TTL on password_resets/sessions/deleted_items (30d auto-cleanup)
- ✅ **Session manager** — JWT jti + `GET/DELETE /api/auth/sessions`, "Active Sessions" card on Settings → Security
- ✅ **Push notifications** — auto-subscribe 2s after WebSocket connect
- ✅ **Birthday/anniversary reminders** — daily 08:00 UTC scheduler, idempotent (skips if already fired today)
- ✅ **server.py split** — 1151 → 782 lines; new `routers/{seed,dashboard,i18n}.py`
- ✅ **MemberForm extracted** — `components/people/MemberForm.jsx`

## Recently Resolved — Iteration 78 (May 1, 2026)

### Part B — P1 + Selected P2 (verified 5/5 backend PASS)
- ✅ **HR Auto-Payday Payslip** — `POST /api/hr/payslips/generate-payday` generates missing payslips for campuses whose `pay_day` matches today. Idempotent. "Run Payday Now" button on HR → Payslips tab.
- ✅ **Multi-campus user creation** — `POST /api/admin/users` now accepts `location_ids` array (mirrors to member record; expands parent campuses).
- ✅ **Finance Dialogs** — 4 `window.prompt()` call sites replaced with real Dialog forms: Transfer, Budget, Revalue Asset, Set Starting Balance.
- ✅ **Variant Barcode Printing UI** — new `VariantBarcodePrint` component (JsBarcode CODE128) with layouts 4×6 / 3×8 / 2×5 grid + single-per-page; copies multiplier; print-preview + `window.open` print.
- ✅ **PWA Wallet Passes Offline** — `sw.js` dedicated `WALLET_CACHE` with cache-first + stale-while-revalidate for `/api/wallet-badge/*` and `/badge/:token`; `prefetch-wallet-pass` message handler.

### Part A — Routing/Filtering Fixes (6 bugs) verified 9/9 backend PASS

- ✅ **Bug 1: Tasks Assignee Scope** — `/api/admin/users/directory` now returns only active staff roles (admin, system_admin, Executive Director, Adviser, Director, Manager, Leader, Coordinator, Staff, HR, Volunteer) scoped to `get_campus_filter`. `include_all=true` reserved for sysadmins. TasksPage `boardStaff` further filters by board location.
- ✅ **Bug 2: Restricted Location Filtering** — `get_campus_filter` in `/app/backend/deps.py` now excludes restricted sub-locations (`is_restricted: true`) for non-sysadmins unless the user's `location_ids` explicitly includes that sub-location.
- ✅ **Bug 3: Chat Ghost Users** — `CommsPage.jsx` now uses `chatApi.users()` (the scoped `/api/chat/users` endpoint) instead of `/api/members`, so only active in-scope users appear.
- ✅ **Bug 4: Multi-Campus Switcher** — `PUT /api/user/active-campus` now allows regular users to switch among campuses in their `location_ids`; admins/EDs retain global switch. 400 for missing id, 403 for campuses outside assignment.
- ✅ **Bug 5: Scheduler Scope + Auto-Time** — `VolunteerSchedulingPage.jsx` uses `adminApi.userDirectory()` (scoped). Selecting a Linked Event auto-populates title, date, start_time, end_time, location_id.
- ✅ **Bug 6: Tasks on Main Calendar** — `CalendarPage.jsx` fetches `tasksApi.list()` and renders tasks with `due_date` as blue "task" events. Clicking navigates to `/boards?board=<id>&task=<id>`.
- ✅ **Bonus: Admin Role Guard** — `create_user`, `admin_update_user`, `bulk_update_users` block non-sysadmins from assigning admin/system_admin/Executive Director roles.

## Pending / Backlog

### P1
- (Optional polish) Add `<DialogDescription>` to the 4 new Finance dialogs to clear radix a11y console warning.
- Verify/tune HR auto-payday against production scheduling preferences (cron on backend startup?).

### P2
- Finance `prompt()` cleanup: receipt URL upload in expense edit (line ~438 FinancialPage.jsx) still uses prompt — last holdout.
- `server.py` modularization (oversized)
- `UnifiedPeoplePage.jsx` split (~1400 lines)
- Full PWA offline beyond Wallet Passes (app shell + last-viewed pages)
- Wave H5 SDK native upgrade
- Scheduled cron jobs for overdue task emails

## Architecture
- Backend: FastAPI + MongoDB + Motor + JWT auth. Routers under `/app/backend/routers/`.
- Frontend: React + Vite + shadcn/ui + Tailwind. Pages under `/app/frontend/src/pages/`.
- Realtime: WebSockets for chat, board events, presence.
- Integrations: Resend (email), Wave CloudUCM (PBX), Emergent Google OAuth, Emergent LLM Key (Gemini for AI assistant).

See /app/ADMIN_GUIDE.md for full feature tree.
See /app/memory/ROADMAP.md for future backlog.
See /app/memory/CHANGELOG.md for iteration history.

## Credentials
See /app/memory/test_credentials.md.
