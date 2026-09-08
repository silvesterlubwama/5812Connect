# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations, covering unified
comms, campus-scoped tasks/calendar/events, double-entry finance with
strict location enforcement, HR/payroll with weekly & multi-cadence pay,
kiosk check-ins, NFC badge issuance + PWA Wallet passes, guest passes,
social work, sales/POS/shipments, and self-service user portal.

## Current status (as of iter 331)

### iter 331 — Social Work merge · Payer filter · Seed 4005
- **Social Work tab merge**: `CaseDetailDialog` tabs `medical`, `notes`,
  and `school_reviews` were folded into their parents. Labels now read
  **Education & School**, **Family & Medical**, **Goals & Notes**.
  Radix renders both `TabsContent` blocks with the same active value,
  so no content was lost — each secondary section shows below a
  `border-t` divider with a section heading.
- **Donation payer filter**: `GET /api/financial/donations` accepts
  `?payer_type=sponsor|parent|org|external`. Legacy rows without
  `payer_type` are matched by mirror `type` fallback so historical
  data slots into the right bucket without a migration.
- **Seed COA `4005 Parent Contributions Income`**: added to the
  default seed list in `finance/_common.py` so new campuses ship
  with parent vs sponsor split reporting out of the box.

## Current status (as of iter 330)

### iter 330 — Sponsor↔Parent payment routing, Slot picker, Scanner deep-link
- **Social-work payments** now classify the payer via `source`
  (`sponsor` / `parent` / `guardian` / `org_fund` / …) into a `payer_type`
  field. Parent/guardian contributions route to the *child's*
  campus + sublocation and post to account `4005` (Parent
  Contributions Income; falls back to `4000` if not yet seeded).
  Sponsor gifts still hit `4000` and stay tagged as external.
- **POS cart slot picker**: for resource-linked line items, cashiers
  can now edit date / start / end inline before completing the sale.
  Defaults remain today 14:00–15:00 so the common case is still
  one-click.
- **Ticket scanner deep-link**: the result card now shows the event
  date/time and venue/location so door staff at multi-day events can
  spot wrong-day scans at a glance.

## Current status (as of iter 329)

### iter 329 — Ticket Scanner + Marketplace product pickers
- **Ticket Scanner page** (`/ticket-scanner`): camera QR scan (via
  `html5-qrcode`) + manual `tkt_...` entry. Redeems via
  `POST /api/tickets/{id}/redeem` (new endpoint) and shows a persistent
  green/amber/red result card so door staff can double-check the last
  scan. Behind `COORDINATOR_PLUS` role guard.
- **Product editor** in the Sales Portal gained two mutually-exclusive
  dropdowns: **Link resource** (bookable, non-consumable) and
  **Link event** (public, non-cancelled). Picking either sets the
  matching product field so sales auto-book the resource or auto-issue
  a ticket. Cart items on resource-linked products auto-carry a
  booking slot (today 2–3pm default) that `create_sale` uses to write
  the booking row.
- Verified end-to-end via curl: lookup → redeem → double-redeem 409 →
  bogus id 404, all correct.

## Current status (as of iter 328)

### iter 328 — Marketplace → Resource bookings & event tickets
- Products can now carry `resource_id` and/or `event_id` — turning a POS
  line into either a locked resource booking or a scannable event ticket.
- **Sale flow**: after inserting the sale, `create_sale` iterates each
  line item. If the linked product has `resource_id` and the item ships
  `booking_date/start_time/end_time`, it calls `check_booking_conflict`
  (skips gracefully on conflict) then inserts a `bookings` row tagged
  `source="marketplace_sale"`. If the product has `event_id`, it
  inserts one `event_tickets` row per unit sold. Both id lists are
  written back onto the sale as `linked_booking_ids` / `linked_ticket_ids`.
- **Two-way lock**: since marketplace-created bookings live in the
  same `db.bookings` collection, the existing staff booking-dialog
  conflict check (`check_booking_conflict`) automatically blocks
  overlapping staff bookings. Verified end-to-end via curl.

## Current status (as of iter 327)

### iter 327 — Resources kind tabs + select-all
- **Kind filter tabs** on the Resources page: **All** (default),
  **Bookable**, **Consumable**, **Unbookable** each with a live count.
  Filter combines with the existing search + type stat-card selector.
- **Select all** checkbox next to the tab strip: selects every currently
  filtered row (respects both search and kind), supports indeterminate
  state when a partial selection exists. Feeds straight into the
  existing `BulkActionBar` (export / delete / print barcodes).
- **Booking conflict guard** was already enforced across `POST
  /api/bookings` via `check_booking_conflict` with a 1-hour buffer, so
  double-booking is prevented regardless of whether the booking
  originates from the staff booking dialog or a public booking flow.
  The marketplace/store side has no resource_id tie-in yet, so a full
  two-way marketplace lock is deferred until the marketplace is wired
  to reference resources.

## Current status (as of iter 326)

### iter 326 — COA bulk import + Fair Alerts wipe
- **COA bulk import**: New `POST /api/finance/chart-of-accounts/bulk-import`
  accepts an array of `{code, name, type, bank_subtype?, is_cash?}` and
  returns `{created, skipped, invalid}` counts + per-row reasons.
  Existing codes are skipped so re-uploading the same file is safe.
- **CoA panel** gained an "Import CSV/XLSX" button that opens a dialog
  parsing files client-side via `papaparse` (CSV) and `xlsx` (XLSX),
  previews rows, and calls the bulk endpoint. Includes a "Download
  template" button.
- **Fair Alerts wiped**: `routers/fare_alerts.py`, `pages/FareAlertsPage.jsx`,
  scheduler loop, indexes, App.js route, and Layout sidebar entry all
  removed.

## Current status (as of iter 325)

### iter 325 — Finance entry campus + department
- Quick expense/income dialog on Finance → Overview now includes a
  required **Campus / sub-location** picker and an optional
  **Department** picker. Both auto-prefill from the current user
  (`active_campus_id` / `department_ids[0]`) so the common case stays
  one-click. Backend `/finance/transactions/expense` and `/income`
  accept `department_id`, and `post_journal_entry` now persists it on
  the JE doc so Dept P&L rollups pick it up automatically.

## Current status (as of iter 324)

### iter 324 — Reliability sweep (production redeploy required)
- **React error #31 on boards** — `CardDetailDialog` & `KanbanCard` label
  rendering safely handles both legacy string colours and `{name, color}`
  objects (was rendering the object as a React child).
- **Tasks disappearing after creation** — removed the 300 ms `setTimeout`
  refetch in `TasksPage.addCard` that raced with the optimistic swap.
- **Tasks missing from calendar** — `CalendarPage` default `taskScope`
  changed from `mine` to `campus` so a due date is enough to see the
  task without needing to be assigned.
- **Cleared notifications returning after re-login / redeploy** —
  `GET /api/notifications` now filters out anything the user has read
  by default (pass `?include_read=true` for the full history).
- **Admin/Boards timeouts** — `GET /api/boards` no longer does N+1
  `count_documents` per board; two aggregation pipelines replace 2×N
  round-trips.
- **Legacy `FinancialPage.jsx` deleted** — Finance surface is now
  exclusively `FinancePage.jsx`.

## Current status (as of iter 323)

### iter 323 — Sub-location budget UI + Dept P&L drill-down
- **Sub-location budget UI (P0)**: Finance page gained a **Budgets** tab
  hosting `SublocationBudgetsPanel` — inline editable hard-cap input for
  every sub-location in the admin's scope. Blank + Save clears the cap
  and falls back to the auto-rolled department sum on the Dept P&L
  rollup strip. Wired to `sublocationsApi.setBudget` → `PUT
  /api/sublocations/{id}/budget`.
- **Dept P&L drill-down (P1)**: Clicking any department card in the
  **Dept P&L** tab now opens a drill-down modal listing every
  contributing entry — direct expenses, payroll allocations (with
  staff name + %), and tagged donations — in the selected window.
  Backend: new `GET /api/reports-department/{department_id}/entries`
  returning `{department, period, entries, totals: {revenue,
  expense, net}}`. Client hook: `departmentsApi.entries(id, params)`.
- Wired both tabs into the active `FinancePage.jsx` (`/financial`
  route). Previous `FinancialPage.jsx` is now dead code but left
  intact until a follow-up cleanup pass.

## Current status (as of iter 322)

### iter 322 — Middleware fix + Dept P&L tab + Payroll allocation strip + Sublocation budget
- Middleware quirk (`RuntimeError: No response returned` / intermittent
  307s) fixed by rewriting `SecurityHeadersASGI` + `RateLimitMiddleware`
  as pure ASGI classes. 8/8 sequential requests confirmed HTTP 200 on
  preview after the rewrite.
- **Financial → Dept P&L** tab wired with rollup cards + per-dept budget
  bars + expand-to-see run-rate.
- **Payroll allocation info-strip** on paid-payslip history dialog:
  `GET /api/hr/payslips/{id}/allocations` returns split rows enriched
  with dept name + colour; HR page shows green "Department funding split"
  strip so accountants can trace the split without extra clicks.
- **Sub-location budget editor**: `PUT /api/sublocations/{id}/budget`
  supports hard-cap override; null clears back to auto-rolled-up
  department-sum. UI toggle is a small follow-up.

## Current status (as of iter 321)

### iter 321 — Split-Aware Payroll + Dept Guard + Bulk Tag + Dept P&L
- `hr.pay_batch_payslips` writes per-department `expense_allocations`
  rows for every paid payslip's split. Aggregate expense JE unchanged.
- `PUT /api/departments/{id}` blocks silent deactivation when live refs
  exist (users/salaries/expenses) — returns HTTP 409 with counts;
  `force: true` bypasses. New `GET /{id}/usage` + `POST /{id}/reassign`.
- `POST /api/admin/users/bulk-department` — assign N users to a
  department, add or replace mode. Wired into AdminPage bulk dialog.
- `GET /api/reports-department/pnl` — per-department revenue vs expense
  vs budget, `run_rate_monthly`, plus `rollups.by_sublocation` and
  `rollups.by_location` computed by summing child-department budgets +
  expenses. Client hook: `departmentsApi.pnl(params)`.

## Current status (as of iter 320)

### iter 320 — Departments (Option B — cost-centre dimension)
- **New collection `departments`** — per-campus/sub-location cost centres.
  Not a physical location. Modelled to solve three linked problems:
  (a) tag staff who serve multiple functions, (b) split-funded salaries
  (e.g., social worker paid 60% HR / 40% Social Work), (c) department
  P&L reporting without polluting the location tree.
- **Users** now carry `department_ids: []` (multi-department tag), in
  parallel with `location_ids: []` (multi-campus tag). Legacy singular
  `department` string kept in sync with first pick.
- **Salaries** carry `department_ids` + `department_splits` (static per
  record, freely editable). Splits validated to sum to 100 both sides.
- **Expenses** carry `department_id` (single) + optional `department_ids`
  / `department_splits` for cross-charging.
- **Frontend** — Admin → System Console → Departments tab (CRUD),
  UserEditDialog chip picker, HR salary form chip picker + splits UI
  (Split-evenly button + live total validator), FinancialPage expense
  form dept dropdown from real API.
- **Reusable `CrossCampusMoveDialog`** — Events / Boards / Products
  move via `location_id`; Tasks move via board picker (grouped by
  campus). Admin-only action on each surface.

### iter 319 additions
- Payslip generation is payday-driven (respects HR settings frequency
  + weekday snap). New `GET /api/hr/payslips/upcoming-paydays` feeds a
  Select of upcoming paydays.
- HR reset moved to Admin → System Console → Data & Backup; reset
  filter now catches `payroll_location_id` in addition to `location_id`.
- `main-location` policy: `deps.default_creation_location(user, provided)`
  is now wired into events / products / approvals / funds / scheduling
  creation. Multi-campus users' records land at their MAIN campus by
  default, not their switched-active campus.

## Current status (as of iter 298)

### DONE
- Unified finance ledger (JEs) + AP + bank reconcile + Receipt Review Queue.
- MongoDB hot-path indexes across finance/HR/access collections.
- PWA offline data + wallet pass cache + prefetch on login + offline pill.
- Director digest email + preview widget with inline snooze.
- Portal self-service badges (own + child), weekly Mon–Sun timesheet,
  wage_type on salaries.
- **iter 299:** Badge PNG download (html2canvas capture — photo + QR
  actually saved) + proper Print flow with print-only CSS. Portal profile
  now edits DOB + gender (whitelisted server-side, verified end-to-end).
  Portal `Scan a receipt` card wired to the existing Finance OCR
  pipeline. Manual Payslip UI shortcut confirmed present.

### iter 301 additions
- Bcrypt/passlib pin locked with documented compat shim.
- MongoDB hot-path index sweep: guests, families, shipments, social_cases,
  social_review_forms, products, hr_payslips/timesheets/salaries/time_off,
  resources/venues/bookings/public_bookings, approval_requests,
  customer_accounts, event_registrations/enrollments/conferences, donors,
  announcements, documents, case_notes, call_logs.
- Portal Receipt Scan UI confirmed already live in `PortalProfile.jsx`
  (iter 299) — camera-capture card posting multipart to
  `/api/finance/receipts/scan`.

### iter 302 additions
- `server.py` split from 1910 → 777 lines. Extracted to `scheduler.py`
  (background cron + push helpers), `db_indexes.py` (`_ensure_indexes`),
  and `seed_data.py` (`_seed_initial_data`). All function names still
  re-exported from `server` so external imports stay green.

### iter 303 additions
- Route split part 2: campus switcher, 2FA, biometric+NFC, Google auth,
  and push subscribe endpoints moved into their own router files.
  `server.py` now 535 lines (was 1910 before iter302).

### iter 304 additions
- Notifications routers consolidated into `routers/notifications.py`.
  Every `/api/notifications/*` path now lives in one file with the
  role-scoped schema. Fixed the silently-broken
  `_create_notification` import in `routers/financial.py` by exposing
  it as an alias. `server.py` now 488 lines.

### iter 305 additions
- Removed the ghost `db.payslips` collection + its three dead indexes.
  `db.hr_payslips` is now unambiguously the single payroll collection.

### iter 306 additions
- Staff/user admin (list, create, edit, reset-pw, badge, bulk) moved
  into HR & Payroll as a new **Staff & Users** tab. The `/admin` route
  now renders only system-level tools (integrations, backups, branding,
  security, module access, finance danger zone) under the new label
  **System Console**. Sidebar item + icon updated to match.

### iter 307 additions
- System Console grouped into 5 tabs — Access, Security, Data & Backup,
  Integrations, Branding — so scrolling through unrelated cards is a
  thing of the past.

### iter 308 additions
- Staff badge fixed: QR moved to the right column, rendered big and
  scannable (148 × 148 desktop), and now embeds the person's photo
  as the centre logo via `react-qrcode-logo`. Both QR pixels and the
  photo live on the same canvas, so every export throw (screen, PNG
  download, `window.print()`, kiosk PDF) captures both cleanly.
  Aligns `UnifiedBadge.jsx` with the already-correct
  `PrintableBadges.jsx` and `WalletBadgePage.jsx`.

### iter 309 additions
- HR pay-run weekday: `payday_weekday` (0=Mon…6=Sun) added to
  `hr_settings` for weekly/bi-weekly cadences. Every computed payday
  snaps to the next occurrence of that weekday (e.g. "bi-weekly + Wed"
  makes the last two Mon-Sun weeks pay on the following Wednesday).
  New weekday picker in the HR settings dialog, only shown for
  weekly / bi-weekly.
- Wallet badge now renders through `<UnifiedBadge />` so every badge
  surface (Wallet, print dialog, bulk sheet, kiosk display) uses the
  identical component. No more layout drift between surfaces.

### iter 310 additions
- Fixed silently-broken event & conference notifications: both routers
  were importing a `send_bulk_notifications` symbol that never existed,
  so ImportError was swallowed and no bell-icon rows ever appeared.
  Swapped for a per-user loop over the real `create_notification`
  helper; recipient projection now includes `id` so the loop has a
  user_id to insert against. Verified end-to-end.

### iter 311 additions
- Event-bell deep-links: new-event notification link is now
  `/calendar?event=<id>`; CalendarPage auto-opens the matching event
  drawer and cleans the query param.
- Badge photo + QR now sit **side by side** (photo portrait, QR
  slightly smaller square, plain — no embedded logo). Photo is
  preloaded into a base64 data URL so it survives html2canvas +
  `window.print()` exports (previously blank in downloads/prints).

### iter 312 additions
- Badge order finalised as **[Info | QR | Photo]** with photo
  right-most, `object-fit: contain` on tinted background (no crops),
  QR bumped to ecLevel Q for reliable print/scan.
- Task bell deep-links: every task-related push + in-app write now
  points at `/tasks?task=<id>`; TasksPage auto-opens the specific task
  drawer via `useSearchParams`.

### iter 313 additions
- Expense bell deep-links: approve/reject notifications now link to
  `/portal/expenses?expense=<id>`; PortalExpenses scrolls the row into
  view and briefly ring-highlights it.
- Badge polish: crown/coronet icon on director/admin badges replaced
  with a friendly 5-point Star (less monarchic). QR now sits on the
  badge background (no white card / border / shadow), vertically
  centred, larger (108 × 108 large / 78 × 78 small), and ecLevel H so
  it still scans after photocopy.

### iter 314 additions
- Badge QR shrunk one step (108 → 92 large / 78 → 68 small) so long
  first names no longer get ellipsised on the left column. Alignment
  flipped from `center` to `flex-end` with a small bottom margin so
  the QR sits flush with the photo's bottom edge — anchored, not
  floating.

### Remaining backlog (agreed with user)
- (nothing user-requested currently open)

## Boundaries from user
> No Wave H5 SDK unless explicitly called for.
> No unrequested enhancements.
> Multi-language translation files on hold.

## Architecture
```
FastAPI (server.py)
  ├─ routers/finance/*   ← unified ledger
  ├─ routers/tasks.py    ← includes director-digest-preview
  ├─ routers/bank.py     ← bills / bank recon / recurring
  ├─ routers/hr.py       ← payslips (wage_type-aware) + weekly timesheets
  ├─ routers/portal.py   ← self-service badges (iter298)
  └─ routers/members/badges.py

Browser
  ├─ Service Worker (public/sw.js — 5812-crm-v4 / wallet / offline caches)
  ├─ usePwaOfflinePrefetch on login
  ├─ Portal pages: /portal/profile, /portal/family, /portal/expenses,
  │                /portal/documents, /portal/events, /portal/tasks, /portal/sales
  └─ Offline pill in Layout header (iter298 copy update)
```

## Credentials
See `/app/memory/test_credentials.md`.
