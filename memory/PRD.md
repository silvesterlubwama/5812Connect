# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations, covering unified
comms, campus-scoped tasks/calendar/events, double-entry finance with
strict location enforcement, HR/payroll with weekly & multi-cadence pay,
kiosk check-ins, NFC badge issuance + PWA Wallet passes, guest passes,
social work, sales/POS/shipments, and self-service user portal.


## iter346 — Sub-location boards · Consumable sheet printing · Flutterwave online payments (2026-06)

### DONE (tested — `/app/test_reports/iteration_106.json`, `backend/tests/test_iter346_flutterwave.py`)
- **Leftover Phase-3 UI verified**: Banking account cards each render the
  **Transactions** ledger drill-down (8/8 accounts, all with `linked_account_id`);
  Universal Upload shows `universal-upload-error` for missing person / missing pay period.
- **Sub-location boards were invisible**: sub-locations live in BOTH `db.locations`
  (`parent_id`) and `db.sublocations` (`location_id`), but `deps.expand_descendants`
  only walked the first — so any board/task/event bound to a finance-native
  sub-location (e.g. "Test Kitchen") fell outside every campus scope. The walk now
  unions both collections, and `boards._can_access_board` got the same fallback.
  Verified: a board at a `db.sublocations`-only sub-location is now listed and
  openable by an admin who did not create it.
- **Consumables tracking sheet never printed**: `ResourcesPage` dynamically imported
  `secureStorage` as a *default* export (the module only has a named export), so
  `ss.getToken()` threw and the fetch never ran; even when it did, the
  post-fetch `window.open` was outside the click gesture and got popup-blocked.
  New `utils/printHtml.js` (`fetchAndPrint` → hidden iframe → `print()`), wired
  into the Print Sheet button. Verified: HTML fetched, iframe spawned, no console errors.
- **Flutterwave online payments (public shop)** — keys entered IN the app:
  * `system_settings.payments` block (provider, enabled, mode, public/secret key,
    webhook secret hash, currency, allow_card / allow_mobile_money /
    allow_pay_on_collection). Masked on read exactly like the Resend key; the
    non-secret subset is exposed on `GET /api/admin/system-settings/public` so the
    public shop knows which buttons to show. Admin UI: System Console → Integrations
    → **Online payments · Flutterwave** (shows the webhook URL to paste at Flutterwave).
  * `routers/payments_flutterwave.py` — hosted Standard checkout (`POST /v3/payments`)
    for card/bank and the Uganda MoMo charge (`POST /v3/charges?type=mobile_money_uganda`,
    network MTN|AIRTEL). Callback params are never trusted: every settlement re-verifies
    via `/v3/transactions/{id}/verify` and matches status + tx_ref + currency + amount.
    Signed webhook (`flutterwave-signature` HMAC-SHA256 base64, legacy `verif-hash`
    fallback) with per-event dedupe in `db.payment_webhook_events`.
  * `POST /api/public/orders` takes `payment_option: online|collection`,
    `online_method: card|mobile_money`, `network`. Online orders return a
    `payment_url`; a failed provider handshake rolls the reservation back
    (`_release_order` restores stock) so nothing is held hostage.
  * A settled sale stays `payment_status: pending` on purpose and is flagged
    `online_payment_status: paid` → Sales shows **"Paid online — awaiting staff
    confirmation"** with a Confirm button; confirming is still what posts to the ledger.
    Buyer gets a paid receipt, staff get an email + in-app notification.
  * Shop cart UI: Pay now (card / mobile money + MTN/Airtel picker) vs Pay on
    collection, inline error text, and a paid/failed banner after the redirect back.
- **Still needed from the user**: paste real Flutterwave keys (test first) in
  Integrations and set the webhook URL + secret hash in the Flutterwave dashboard.
  Resend domain `5812-global.org` is still unverified, so order emails bounce.

## iter345 — Portal/member experience + notification & dashboard truth (2026-06)
Phased execution of the user's 21-item mega-list (full list: `/app/memory/BACKLOG_iter345.md`).
Agreed order: 1 Portal/member → 2 Notifications+Dashboard → 3 Finance → 4 Badges →
5 Uploads → 6 Tasks/Boards → 7 Flutterwave online payments.

### Phase 1 — DONE (tested, `/app/test_reports/iteration_104.json`)
- **Family/household for everyone**: `_resolve_my_family_id` now resolves via the user
  doc, guests, members, `parent_ids`, primary-contact email and guardian email — staff and
  plain members no longer get "No family found". New self-service
  `POST /api/portal/family` creates a household (user becomes primary contact +
  `users.family_id`), and `PUT/DELETE /api/portal/family/guardians/{id}` let people edit
  their own household only. Relationship list now includes **Spouse**.
- **Staff profile household**: `/profile` in the main app renders the same family UI
  (`profile-household-section`), and the avatar menu gained **My Member Portal**
  (`profile-menu-my-portal`).
- **Non-staff portal filter**: `PortalLayout` splits STAFF_NAV vs MEMBER_NAV (members see
  Dashboard, Events & Tickets, My Tickets, My Family, Statement, My Badge, Profile only).
  New `StaffOnlyPortalRoute` guard blocks members from /portal/{chat,tasks,expenses,
  time-off,documents,sales} by URL. Member dashboard tiles are now member-relevant
  (tickets / month charged / outstanding).
- **Tickets actually exist**: every path now writes the canonical `event_tickets` row via
  new `ensure_ticket_row` (portal RSVP, admin auto-issue, POS sale). `portal_tickets`
  unions bookings + ticket rows; `_resolve_ticket` backfills legacy booking-only tickets so
  door scan/redeem no longer 404s.
- **Badge carries tickets**: `ticket_flags_for()` + `GET /api/tickets/flags`. Ticket flags are
  returned by `GET /api/wallet-badge/{token}`, kiosk pin-checkin (lookup + check-in) and
  `POST /api/access/scan` — a badge scan alone shows "ticketed". New `/portal/badge` page.
- **Monthly statement**: `GET /api/portal/statement?month=YYYY-MM` (purchases + tickets,
  live, with totals) and printable `/portal/statement` page with month paging.

### Phase 2 — DONE (self-tested via curl + screenshots)
- **Cleared notifications never come back**: `list_notifications` never filtered on
  `user_id`, so everyone saw everyone's personal notifications. Now scoped per user, plus
  `deleted_by` tombstones, a new `DELETE /api/notifications/clear-all` (hard-delete own
  rows) and per-row delete instead of mark-read. Verified: admin clear-all → 0 rows, member
  untouched.
- **Stale links purged**: `_prune_stale` deletes notifications deep-linking to a task/event
  that is gone, done, archived or cancelled (verified: ghost task notif vanished, live one kept).
- **One overdue truth**: new `overdue_task_filter()` in `routers/tasks.py` (excludes done in
  any casing, archived, snoozed, dateless AND orphaned tasks whose board was deleted) is now
  used by dashboard stats, action-items, the assignee overdue emails and the director digest —
  so the email and the dashboard can't disagree. Fixed `unassigned_tasks` silently clobbering
  the snooze `$or`.
- **Dashboard money is ledger-truth**: `/api/reports/summary` (what the dashboard actually
  calls) and `/api/financial/summary` now read `finance_journal_entries` via
  `_balances_by_account`, honour date_from/date_to and break down per account. Verified equal
  to `/api/finance/reports/pnl` (Sept 2026: income 160,000 / expenses 278,288 / net -118,288).
  Dashboard labels renamed to Income/Expenses/Net this month.

### Phase 3-7 — NOT STARTED (see BACKLOG_iter345.md)


### iter 344e — Routing/filtering hardening (2026-09-09)
- **Transfer missing location**: `TransferDialog` had no campus/sub-location picker so every transfer POST failed silently. Added the required control (prefilled from active campus).
- **Missing transactions post-deploy**: `JournalPanel` + `OverviewPanel` were stale after posts from `QuickPostDialog` (split), `TransferDialog`, JE edit/reversal/delete. Wired `dataEvents.emit('finance-changed', …)` on every mutation and subscribed both panels.
- **Split JEs stored empty account_code/name**: `post_journal_entry` now hydrates missing fields from `finance_chart_of_accounts` so expanded rows always render a readable account label.
- **Task assignee cross-campus leak**: `CardDetailDialog` was passing `include_all: true` to `/admin/users/directory`, which system admins used to bypass `get_campus_filter`. Dropped the flag — extended search remains inside the caller's campus.
- **Chat ghost users**: `get_conversations` was matching `status != "deleted"`, letting `inactive`/`suspended`/missing-status accounts leak into the sidebar. Tightened to `status == "active"`.
- **Admins invisible in chat/user directory**: `chat/users` and `/admin/users/directory` apply `get_campus_filter`, which excludes users with no `location_id`/`location_ids` — i.e. admins/EDs/Advisers (global scope). Unioned an explicit "global-role" branch so admins remain visible everywhere.


### iter 344c — Finance edits · Ticket wallet · Family audit · Approval delegation
- **Finance editing**: The frontend was sending the full `lines[]` on every save which triggered a reverse-and-repost even for cosmetic edits. Added a `linesDirty` flag in `FinancePage.jsx` — only sends `lines` when an account swap or memo actually changed, so a description typo no longer produces two extra JEs.
- **Delete a reversal**: New `DELETE /api/finance/journal/{je_id}` restricted to `source='reversal'` entries and refuses when the period is locked. Un-marks the original entry so it posts again cleanly. UI shows a "Delete reversal" button on reversal rows.
- **Ticket wallet**: `GET /api/portal/tickets` flattens every ticket the caller owns (public bookings + admin auto-issues) into passes with event context and redemption status. New `PortalTickets.jsx` renders a QR pass per ticket via `react-qrcode-logo` — door staff can scan and redeem through the existing `POST /api/tickets/{id}/redeem`. Nav item added to both staff and guest portals.
- **Family change history**: New `GET /api/families/{id}/audit` returns a chronological trail. Every submission / approval / rejection now writes a `family_audit` doc via `_log_family_event`. The People page **Family Approvals** tab gained a **Change history** button that opens a per-family-or-global timeline dialog.
- **Approval delegation**: Managers can now name a delegate when filing their own leave. On approval the backend stamps `approval_delegate_to/from/until` on their user record. `GET /hr/pending-count` bundles delegated items on top of the delegate's own queue and returns a `delegated_from` list. `PortalTimeOff.jsx` renders the delegate picker for approver-role users only. The delegate gets a notification when the delegation activates.


- **Manager approval bell**: new `GET /api/hr/pending-count` returns `{leave, reimbursements, total}` scoped to the approver's campus and excluding their own requests. `Layout.jsx` polls it every 60s for manager+ / HR and paints a red numeric pip on the HR sidebar icon so pending decisions can't hide.
- **Family approval queue** (parent-submitted children + guardians):
  * New endpoints in `routers/members/families.py`:
    * `GET /api/families/pending-approvals` — flattened queue of pending children + pending guardians (with family_name enrichment).
    * `POST /api/families/pending-approvals/child/{child_id}/decide` — approve (unlocks the record) or reject (soft-deletes to `deleted_items`); notifies the parent either way.
    * `POST /api/families/pending-approvals/guardian/{family_id}/{guardian_id}/decide` — approve (flips `approval_status`) or reject (`$pull` from array); notifies the parent.
  * `UnifiedPeoplePage.jsx` — new **Family Approvals** tab, only visible when the queue is non-empty; shows child/guardian cards with Approve + Reject (with optional reason) actions.
- **Public event checkout** — `PendingApprovalScreen.jsx` now renders a **Buy ticket** / **RSVP** action next to each public event that opens `/marketplace?event=<id>`, so pending guests can complete the purchase flow before an admin approves their profile.
- **Route**: `/tickets` alias added for the marketplace page so the new call-to-action reads cleanly.



### iter 344 — HR crash · Guest portal lockdown · Time-off self-service · Cron deep-links
- **HR page crash fix**: `HRPage.jsx` imported `FileDown` from `lucide-react` only implicitly — the Timesheets tab immediately threw `ReferenceError: FileDown is not defined`. Added `FileDown` to the lucide-react import.
- **Guest portal security overhaul (iter344)**:
  * `RouteGuards.jsx` — pending users now land on a brand-new `PendingApprovalScreen` (public events browse + logout; NO family/tasks/expenses/badge). Explicit `STAFF_ROLES` set stops staff (with `is_parent=true` accidentally) from being redirected to `/portal`.
  * New `PortalRoute` guard applied to `/portal`; pending guests get the same PendingApprovalScreen instead of the sidebar full portal.
  * `PortalLayout` splits `STAFF_NAV` vs `GUEST_NAV` — guests only see Dashboard / Events & Tickets / My Purchases / My Family / Profile (Tasks/Chat/Expenses/Sales-admin/Documents/Time-Off hidden).
  * `PortalFamily.jsx` — pending guests see a read-only banner + all edit/add buttons disabled; approved guests see a review-notice banner explaining that new children/guardians land in pending state.
  * Backend `routers/members/families.py` — `parent_add_child` / `parent_add_guardian` gated on `status != 'pending'`; new records tagged `approval_status='pending'`, `submitted_by_parent=true`; admins get an in-app notification with deep-link to review.
- **Tasks not posted when created (fix)**: `routers/tasks.create_task` now fires the same in-app notification + email chain that `update_task` already had — assignees learn about new cards immediately.
- **HR delete draft payslip**: New `DELETE /api/hr/payslips/{payslip_id}` restricted to draft status; UI shows a red trash icon next to draft rows only.
- **Time-off self-service (portal + admin)**:
  * `PortalTimeOff.jsx` — full staff self-service: pick type, date range, half-day toggle + partial-day start/end times, notes; submit → manager notified. Live balance cards. Cancel / delete own pending requests.
  * `GET /hr/leave/types` opened up to any authenticated user (was HR-only) so the portal can render the picker.
  * `POST /hr/leave/requests` now dispatches an in-app notification to Manager+/HR at the requester's location — no manual polling needed.
  * `LeavePanel` in HR page: "Manage types" dialog for HR/admins to add/rename/recolour leave types + set paid vs unpaid + default days; "Set allocations…" dropdown lets an admin override any staff member's per-year budget. Approve/decline UI already existed; added pending-count badge.
- **Calendar event edit** — `CalendarPage.jsx` edit form restored the fields lost in the events/calendar unification: **type** picker, **capacity**, **is_free** toggle with a **price** field, plus visibility switch.
- **Dashboard action-items deep-links**: overdue tasks → `/tasks?filter=overdue`, unassigned → `/tasks?filter=unassigned`, pending approvals → `/people?tab=pending`, expiring passes → `/access?filter=expiring`.

### iter 341 — Badge QR clarity · Guest portal security hardening
- **Badges (`PrintableBadges.jsx` + `UnifiedBadge.jsx`)**: StaffBadge
  and ChildTag no longer embed the photo INSIDE the QR (previous
  `qrStyle="dots"` + logoImage produced a jumbled unreadable code
  and covered the face). Both variants now render QR + photo as
  siblings — QR uses `qrStyle="squares"`, solid white bg + black fg
  (reads on any badge stock), higher-density canvas (192px source
  scaled to 84px CSS with `image-rendering: pixelated`) so print at
  300dpi stays crisp. Photo shrunk by ~2mm (108→100 large, 76→68
  small). ParentBadge also switched to squares + white bg.
- **Guest portal security**: `submit_guest_access_request` in
  `routers/access.py` hardened:
  * Removed the duplicate v2 route that silently shadowed the v1
    (both were registered at the same path — dead code plus attack
    surface).
  * Rate-limited to 5 requests/IP/10 min via `count_documents` on
    `client_ip` — stops fake-guest spam.
  * Name (2–120 chars), email (regex + 254 cap), phone (regex + 32
    cap), purpose (500 cap), visit_date (YYYY-MM-DD) all validated.
  * `max_uses` guard now uses an atomic `$inc` with a `uses < max`
    filter, killing the previous TOCTOU race where parallel submits
    could overshoot the limit.
  * Idempotent guest lookup — never creates a duplicate profile for
    a returning submitter.
  * `client_ip` persisted on every request for audit / abuse tracing.
- Tests: `backend/tests/test_iter341_guest_access_hardening.py`
  covers missing-name / bad-email / rate-limit / parallel-race.

## Current status (as of iter 339-340)

### iter 339-340 — Punch correction log · Period-based financial edit gate
- **Punch Corrections**: two new HR endpoints allow directors to
  repair bad kiosk scans without discarding a timesheet:
  * `PUT /api/hr/timesheets/{id}/entries/{index}` — edit arrival/exit
    with a required `reason`. Records `punch_corrections[]` with
    before/after payloads + who/when.
  * `DELETE /api/hr/timesheets/{id}/entries/{index}?reason=<>` —
    delete a bad punch (required reason).
  Both re-roll `hours_worked` + `days_worked` after the change so
  payroll picks up the corrected total automatically. Reject 400 on
  missing reason or reversed timestamps.
- **Frontend Punches dialog**: TimesheetsPanel gains a "Punches"
  button on any row with `entries[]`. Opens a table of arrival/exit
  pairs with per-row Edit + Delete buttons. Edit dialog captures
  the required reason and calls the new endpoints. Correction log
  is exposed at the bottom for audit.
- **Financial edit gate now period-based**: `_within_self_edit_window`
  in `routers/financial.py` no longer denies after 7 days. New
  `_period_open_or_admin(doc, user)` layers `period_is_locked` over
  the creator check — so donations/expenses are editable by the
  creator any time BEFORE the fiscal period covering the entry's
  date is closed. Admins still bypass everything.
- Tests: `backend/tests/test_iter339_punch_and_period_edit.py`
  covers both features end-to-end.

## Current status (as of iter 338)

### iter 338 — Kiosk autofill + Per-day XLSX Daily Log
- **Badge Autofill on Kiosk**: new `sync_kiosk_to_timesheet(staff_id,
  action, when_iso, location_id)` in `routers/hr.py`. Called from
  `kiosk_checkin` and `kiosk_pin_checkin` in `routers/events.py`
  whenever a staff (with an active `hr_salaries` row) scans in/out.
  Appends punch entries to `hr_timesheets.entries[]` for the current
  pay period, closes matching entries on checkout, rolls up
  `hours_worked` + `days_worked` automatically. Silent no-op for
  non-payroll members. Auto-closes stale open punches (>12h idle)
  at +8h so a forgotten checkout doesn't corrupt the week.
- **Per-Day XLSX Rows**: the downloadable template gains a "Daily
  Log" sheet with per-staff × per-day rows (14 days for biweekly,
  full month for monthly). Columns: Staff Name | Badge | Date |
  Arrival | Exit | Hours | Notes. Hours cell is a live Excel
  formula that handles overnight shift wraps. Upload endpoint sums
  Daily Log hours + days per badge and uses them as the fallback
  when the Summary sheet's Hours Worked / Days Worked cells are
  left blank — so paper time-cards flow through with zero HR
  retyping.
- Tests: `backend/tests/test_iter338_kiosk_and_daily_log.py` covers
  end-to-end kiosk sync (check-in → check-out → rollup), non-payroll
  short-circuit, XLSX template contains Daily Log sheet, and upload
  falls back to Daily Log totals when Summary is blank.

## Current status (as of iter 337)

### iter 337 — Overtime tier · Hours-on-Timesheet · XLSX template · Wage-breakdown on PDF
- **Overtime tier**: `_compute_base_gross` for `wage_type=hourly` now
  honours `ot_threshold_hours` (weekly, scales with period) and
  `ot_multiplier` (default 1.5). Hours above threshold are split into
  regular + OT slices. Example: hourly 10,000 UGX, 40h/week threshold,
  90 hours over a biweekly period → 80h reg + 10h × 1.5 = 950,000 UGX.
- **Hours on Timesheet**: `submit_timesheet` accepts an optional
  `hours_worked` field (0-1000). `generate_payslips` and
  `preview_payslips` merge it from approved timesheets and pass it
  into `_compute_base_gross` so hourly staff get the true rate × hours
  (no more days × 8h fallback when a real number is available).
- **XLSX template + upload**: new `routers/hr_timesheet_templates.py`
  ships two endpoints:
  * `GET /api/hr/timesheets/template?period=<>` — download an XLSX
    pre-filled with every active staff (name + badge + wage type +
    rate) plus 5 blank rows for casuals. Includes an Instructions
    sheet.
  * `POST /api/hr/timesheets/upload?period=<>` — HR uploads the
    completed file; rows are matched by badge_number (fallback: name)
    and land as `status='submitted'` awaiting director approval.
- **Wage breakdown on payslip PDF**: payslip docs now persist
  `wage_type` + `wage_details` and the downloadable PDF prints them
  under the header ("Wage breakdown: 60,000 × 10 days").
- **Salary form UI**: adds Rate Type + OT threshold/multiplier fields
  for hourly staff. TimesheetsPanel adds an Hours field to the
  Log-for-Staff dialog and a "Sheet up/download" button opening the
  XLSX flow.
- Tests: `backend/tests/test_iter337_ot_hours_xlsx.py` covers all
  four features end-to-end (OT math, hours-worked timesheet path,
  XLSX template contents, XLSX upload with badge match).

## Current status (as of iter 336)

### iter 336 — Per-salary wage types (hourly / daily / weekly / biweekly / monthly)
- Everyone still gets paid on the same campus schedule, but each
  salary record now carries a `wage_type` that changes how the base
  amount is interpreted. New helper `_compute_base_gross` in
  `backend/routers/hr.py`:
  * `salary` / `monthly`  → monthly_base × pay_frequency proration (existing).
  * `daily`   → daily_rate × days_worked (falls back to working days).
  * `hourly`  → hourly_rate × hours_worked (falls back to days × 8h).
  * `weekly`  → weekly_rate × (period_days / 7).
  * `biweekly`→ biweekly_rate × (period_days / 14).
- User's canonical case now works: **60,000 UGX daily × 10 working
  days in a biweekly period → 600,000 UGX payslip**.
- Unpaid-leave and days-worked proration blocks are automatically
  skipped when wage_type ∈ {daily, hourly}, since base_gross already
  reflects the units worked (prevents double-deduction).
- The Salary form gains a Rate Type picker (Monthly Salary / Hourly /
  Daily / Weekly / Biweekly) plus a contextual helper line explaining
  how the number is applied. The label auto-updates ("Hourly Rate *",
  "Daily Rate *", etc.) and Pay Frequency clarifies it's independent.
- Preview + generate endpoints report `wage_type` and a human
  `wage_details` string (e.g. `60,000 × 10 days`) surfaced under the
  gross column in the Preview dialog.
- Existing salary records default to `wage_type: "salary"` and behave
  exactly as before — zero regression path.
- Tests: `backend/tests/test_iter336_wage_types.py` covers all five
  wage types (including the exact 60k×10=600k user scenario) plus a
  live preview integration check.

## Current status (as of iter 335)

### iter 335 — Payroll Preview · Anchor Nudge · PDF coverage line
- **Payroll preview dry-run**: new `POST /hr/payslips/preview` mirrors
  the exact `_generate_payslips_for` math but returns rows instead of
  writing. The Generate Payslips dialog now shows a table of staff /
  gross / allowances / deductions / net (plus "Existing — skipped"
  chips for anyone already drafted) so directors catch surprises
  before touching the ledger.
- **Anchor nudge**: switching HR Settings frequency to biweekly/weekly
  without a Next Pay Date now pre-fills the coming Wednesday (or the
  configured `payday_weekday`) and shows a toast telling the admin
  where to tweak it.
- **PDF coverage line**: payslip PDF now includes "Covers work from
  Sep 16, 2026 to Sep 29, 2026 (2 weeks)" derived from the canonical
  period label — biweekly and monthly variants both supported so
  paper matches the on-screen explainer added in iter 334.
- Tests: `backend/tests/test_iter335_preview_and_pdf.py` (2 scenarios
  in one asyncio.run) — verifies preview never persists AND the PDF
  HTML contains the coverage line.

## Current status (as of iter 334)

### iter 334 — Biweekly payroll UX cleanup
- **Period label now shows the full span**: `_biweekly_period` in
  `routers/hr.py` writes `(W38-W39)` when a 14-day window crosses two
  ISO weeks (i.e. every biweekly period in practice). Staff no longer
  read the single-week label and think the payslip amount is one
  week's pay. Single-ISO-week windows still show a plain `(Www)`.
- **Settings hygiene**: `pages/HRPage.jsx` hides the "Payday (day of
  month)" picker whenever `pay_frequency` is not `monthly`. Instead a
  dashed placeholder explains that future paydays are calculated from
  Next Pay Date every 14 or 7 days. Next Pay Date is now marked
  required (`*`) with an inline red hint if missing for non-monthly.
- **Backend guardrail**: `/hr/payslips/upcoming-paydays` now raises a
  400 with a plain-English message if a weekly/biweekly campus has no
  `next_pay_date` — no more silent fall-back to a stale day-of-month
  anchor that produced wrong periods.
- **Payday picker window explainer**: the Generate Payslips dialog
  now surfaces "Covers work performed from <start> to <end> (2 weeks)"
  next to the selected biweekly payday so HR sees the exact span.
- Tests: `backend/tests/test_iter334_biweekly_period_label.py` covers
  the label formatting and verifies the screenshot amounts
  (600k → 276,923.08; 400k → 184,615.38; 75k → 34,615.38) match the
  12/26 proration.

## Current status (as of iter 333)

### iter 333 — Role persistence · Live call ringing · Console departments · Sponsor directory hygiene
- **Role edits now persist**: `UserEditDialog.jsx` role select now clears
  the `is_admin` toggle on change. Previously, a hydrated admin who was
  demoted via the Role dropdown had `is_admin` stuck at true, so
  `saveEdit` kept forcing `payload.role='admin'`. Micro-help copy under
  the select explains the trade-off ("Turn admin back on below if you
  want to keep sysadmin").
- **Live incoming-call overlay**: new `components/IncomingCallModal.jsx`
  is mounted globally by `Layout.jsx`. It subscribes to the existing
  `incoming_call` broadcast (already emitted by
  `backend/routers/websocket.py` on any `call_offer`) and pops a
  ringing UI with Answer / Reject buttons over any page. Answer hands
  off to `/comms?call=<id>&caller=<id>&answer=1` where the existing
  RTCPeerConnection plumbing takes over. `call_answered` /
  `call_rejected` / `call_ended` / `call_cancelled` all auto-hide the
  overlay.
- **Console departments in Location editor**: `LocationsPage.jsx` now
  loads the campus's departments from `departmentsApi.list({ location_id
  })` and shows them as read-only chips. A "Manage in Admin console"
  link routes to `/admin?tab=departments`. Legacy free-text departments
  still render underneath with an amber warning banner so admins can
  migrate them.
- **Sponsors no longer pollute People**: `_upsert_external_sponsor_guest`
  in `routers/social_work.py` now ONLY matches existing users/members/
  guests. When no directory row exists, it returns None and the sponsor
  stays purely on `case.sponsor_manual`. Existing matches get contact
  fields backfilled without changing their `kind`.
- Tests: `backend/tests/test_iter299_sponsor_no_autopeople.py` covers
  the three matching branches (no-match, user-match, guest-match).

## Current status (as of iter 332)

### iter 332 — Social Work auto-populate (Family / Education / Medical) + Notes chronology
- **Auto-populate case sub-docs from reviews**: `_apply_review_to_child`
  in `routers/social_review_forms/child_sync.py` now also mirrors the
  latest review's structured fields onto the child's active
  `db.social_cases` document (which is what the `CaseDetailDialog`
  reads). New helper `_apply_review_to_case(child_id, kind, data,
  fields, review_id)` handles all three kinds:
  * `welfare_visit` → `case.family` (guardians, siblings,
    household_income, notes, primary_caregiver, caregiver_relationship,
    village_parish, district).
  * `school_progress` → `case.education` (grade, school_name,
    current_term, class_teacher, teacher_phone, attendance_pct,
    discipline, academic_performance, class_position) with a
    prev→new change log entry.
  * `medical_exam` → `case.medical` (conditions, allergies,
    current_medication, nutritional_status, notes, primary_doctor).
  Every populated field carries a `_field_sources[fieldName] =
  {review_id, review_date, kind, at}` marker + a rolling
  `_change_log[]` (last 20 entries) so counsellors can audit
  overwrites.
- **UI source pills**: `pages/SocialWorkPage.jsx` renders a
  `SourceBadge` (`from home visit YYYY-MM-DD` / `from school review …`
  / `from medical exam …`) next to every auto-populated field. A
  `ChangeLogButton` on Education/Family/Medical opens a dialog showing
  every historical overwrite with prev→new values.
- **Notes "New" chronology**: notes stay newest-first (existing
  behaviour). Unseen notes now get a green `New` pill + emerald ring
  until the user clicks them. Seen state is persisted per case in
  `localStorage` under `sw:seen_notes:<caseId>` so the pill clears
  once you've read the note but survives dialog re-opens for other
  notes.
- Tests: `backend/tests/test_iter298_case_autopop.py` covers all three
  kinds + idempotent re-runs.

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

### iter 316 additions
- Calendar `New Event` regained Capacity / Free-vs-paid / Ticket price and
  gained the Ticket Tiers builder (create + edit).
- `EventsPage.jsx` deleted (was dead code; `/events` already redirected).
  Registrations, check-ins, tiers summary, waitlist and Duplicate migrated
  into the Calendar event drawer. `backend/routers/events.py` stays — it
  powers public events, bookings, kiosk, check-ins and venues.
- Fixed: board tasks never reached the shared calendar (.ics) feeds — the
  feed filtered on `tasks.location_id`, which tasks don't have. Board
  permission resolution is now shared via `resolve_allowed_board_ids`.
- NEW: admin sets each public holiday to Paid / Optional paid / Unpaid /
  Not observed by clicking it on the Calendar. Stored per holiday NAME so it
  sticks every future year. Wired into payslips + timesheets: hourly staff
  get their `holiday_hours` (default 8, per-staff) credited on paid holidays
  and stacked on top of hours actually worked; daily-wage staff get the day
  regardless, i.e. double pay when they work it.
- NEW: event location is venue-first — our venues (restricted campuses
  excluded) → external venues used before → add a new venue inline →
  one-off typed address. `GET /api/venues` is now campus-scoped.

### iter 317-319 additions
- Rate limiter now per-user (was one shared bucket for the whole platform).
- HR → **Holidays** screen: every public holiday and how it's paid.
- Dashboard follows the sidebar campus switcher (no second control, by the
  user's explicit choice) + a scope badge.
- **Public online shop**: staff tick "Sell this online" per product; the public
  page lists them and can order. Server re-prices everything from the DB.
- Campus Reports page **removed** at the user's request.
- Fixed: non-cash sales (card/bank/mobile-money/online) never reached the
  ledger when confirmed — now posted on paid and reversed on un-paid.
- Reconnected dead-but-live features: customer directory, customer statements,
  payment reminders, POS store settings, Invoices tab, member document
  download/archive, member bulk export, single-resource fetch, HR account seed.
- `scripts/audit_api_paths.py` guards against UI-calls-a-dead-path regressions.

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
