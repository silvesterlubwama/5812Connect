# CHANGELOG

## 2026-09-09 — iter 344e (routing/filtering hardening + finance list refresh)
- **CRITICAL FIX — Transfer missing location**: `TransferDialog` (in `FinancePage.jsx`) had no campus/sub-location picker but the backend `POST /api/finance/transfers` rejects payloads without `location_id`. Every transfer 400'd silently: users saw the "Post transfer" click, no toast (because we swallowed the error), no ledger row. Added Campus/sub-location control (prefilled from active campus) and sub-location resolution mirroring `QuickPostDialog`.
- **FIX — Missing transactions post-deploy**: `JournalPanel` and `OverviewPanel` did not refetch when a JE was posted from anywhere else (split dialog, transfer dialog, JE edit, reversal, delete). Wired `dataEvents.emit('finance-changed', ...)` on every mutation and subscribed both panels — the ledger stays in sync across tabs without a page reload.
- **FIX — Split JE lines had empty account_code/name**: `post_journal_entry` (`_common.py`) now hydrates `account_code` + `account_name` from `finance_chart_of_accounts` when the caller forgot to include them (previously the JE stored `""` for both, so expanded rows rendered " — " and users thought the split was corrupt).
- **CRITICAL FIX — Task assignee cross-campus leak**: `CardDetailDialog` (task detail) was passing `include_all: true` on the extended search box. That flag bypasses `get_campus_filter` for system admins on the backend — so system-admin users saw every user in every campus in the picker. Dropped `include_all` (the base `/admin/users/directory` endpoint is already staff-role-only + campus-scoped).
- **FIX — Chat ghost-user filter**: `get_conversations` used `status != "deleted"` which let `inactive`/`suspended`/missing-status accounts leak through as sidebar rows. Tightened to `status == "active"`.
- **FIX — Admins invisible in chat directory**: `chat/users` applied `get_campus_filter` which excludes users with no `location_id`/`location_ids` — but admins/EDs have exactly that (global scope). Unioned an explicit "global-role" branch so admins/EDs/Advisers stay visible in every campus's chat directory. Same union applied to `/admin/users/directory` so board/task pickers surface admins too.


## 2026-09-09 — iter 344d (task edit board_id wipe fix + prod prefetch cleanup)
- **CRITICAL FIX**: `PUT /api/tasks/{id}` was overwriting `board_id`, `list_id`, `position`, and `is_archived` with `None` on every edit because `model_dump()` populated the missing Optional fields as `None` and the update loop wrote them back. Result: edited cards lost their parent board and vanished from the UI. Switched to `model_dump(exclude_unset=True)` so only client-sent fields are touched. Explicit clears for `due_date` / `description` / `assignee` still work.
- Removed `/api/access/checkpoints`, `/api/members/{id}/qr-code`, `/api/members/{id}/profile-photo` from the PWA offline prefetch set (all three were 404-spamming production).

## 2026-09-09 — iter 344c (finance edits · ticket wallet · family audit · delegation)
- Fix: Finance edits fired reverse-and-repost even for cosmetic changes. `FinancePage.jsx` now tracks a `linesDirty` flag and only sends `lines` when accounts/memos actually changed.
- Feat: `DELETE /api/finance/journal/{je_id}` for reversal entries (source='reversal') while the period is open — un-marks the original entry so it posts again. UI shows a "Delete reversal" button on reversal rows.
- Feat: Ticket wallet — `GET /api/portal/tickets` returns flattened passes (event context + redemption status). New `PortalTickets.jsx` renders scannable QR passes via `react-qrcode-logo`. Nav entries added to both staff & guest portal.
- Feat: Family audit trail — new `family_audit` collection, `_log_family_event` helper writes on every submission/approval/rejection, `GET /api/families/{family_id}/audit` exposes the trail. **Change history** button on People → Family Approvals opens a per-family-or-global timeline dialog.
- Feat: Approval delegation — Managers can name a delegate when filing leave. On approve, backend stamps `approval_delegate_to/from/until` on their user row. `/hr/pending-count` folds delegated items into the delegate's queue and returns `delegated_from[]`. `PortalTimeOff.jsx` shows the delegate picker for approver roles only.

## 2026-09-09 — iter 344b (approval bell · family queue · pending-guest checkout)
- Feat: `GET /api/hr/pending-count` (scoped to approver, self-excluded). `Layout.jsx` polls it and paints a red numeric pip on the HR sidebar icon.
- Feat: Family approval queue. `GET /api/families/pending-approvals` + `POST .../child/{id}/decide` + `POST .../guardian/{family_id}/{guardian_id}/decide`. Parents get an in-app notification when their submission is approved or rejected. New **Family Approvals** tab on `UnifiedPeoplePage` (only visible when the queue is non-empty).
- Feat: `PendingApprovalScreen` — every public event row now has a **Buy ticket** / **RSVP** button that deep-links to `/marketplace?event=<id>` so pending guests can complete checkout before admin approval.
- Route: `/tickets` alias → PublicBookingsPage.

## 2026-09-09 — iter 344 (guest portal lockdown · time-off self-service · HR crash fix)
- Fix: `HRPage.jsx` — `FileDown` was used on Timesheets tab but never imported (`ReferenceError` on tab click). Added to lucide-react import.
- Fix: Tasks weren't broadcasting to newly-assigned users on creation. `routers/tasks.create_task` now fires in-app notification + email (previously only edits notified).
- Feat: Guest portal security. `RouteGuards.jsx` gates pending accounts behind a new `PendingApprovalScreen` (public events browse + logout only). `STAFF_ROLES` set added so staff who happen to be parents never land on `/portal` by mistake. `PortalRoute` protects `/portal`. `PortalLayout` splits Staff vs Guest nav — guests can't reach Tasks/Chat/Expenses/Sales admin/Documents/Time-Off.
- Feat: `PortalFamily.jsx` — pending guests see a read-only banner + disabled buttons; approved guests get a review-notice banner. Backend `parent_add_child` / `parent_add_guardian` require approval, stamp `approval_status='pending'`, notify admins.
- Feat: HR — delete draft payslip. `DELETE /api/hr/payslips/{id}` restricted to `status=draft`. Red trash icon on draft rows.
- Feat: Time-off self-service. New `PortalTimeOff.jsx` (portal). `/hr/leave/types` opened to any authenticated user. `/hr/leave/requests POST` dispatches in-app notifications to Manager+/HR at the requester's location. `LeavePanel` in HR page: "Manage types" dialog (add/edit/delete leave types, colour, paid flag, default days) + "Set allocations…" (per-staff override).
- Feat: Calendar event edit restored `type`, `capacity`, `is_free` toggle + `price` (regression from events/calendar unification).
- Feat: Dashboard action items deep-link (`/tasks?filter=overdue`, `/tasks?filter=unassigned`, `/people?tab=pending`, `/access?filter=expiring`).


## iter 341 — 2026-02 — Badge QR clarity · Guest portal security

### Badges — QR + photo split (print-safe)
- `components/PrintableBadges.jsx`: `StaffBadge` and `ChildTag` no
  longer embed the photo INSIDE the QR. Both render two siblings:
  QR left, photo right. QR uses `qrStyle="squares"`, `ecLevel="M"`,
  solid `bgColor="#ffffff"` / `fgColor="#000000"` so it reads on any
  badge stock. Canvas size doubled (192/168 source) then scaled to
  display size with `image-rendering: pixelated` so 300 dpi print
  stays crisp.
- `ParentBadge` also switched to squares + white bg for consistency.
- `components/UnifiedBadge.jsx`: photo shrunk by ~2mm (108→100 wide
  and 148→140 tall on large; 76→68 wide and 108→100 tall on small).
  QR now white-bg/black-fg with pixel-perfect scaling. Prevents QR
  ever covering the face.

### Guest portal security hardening
- `routers/access.py::submit_guest_access_request` completely
  rewritten:
  * **Removed** the duplicate v2 route that shadowed v1 (both at the
    same path — dead code + extra attack surface).
  * **Rate limit**: 5 requests / IP / rolling 10 min (via
    `count_documents` on `client_ip`).
  * **Input validation**: name 2–120 chars; email regex + 254 cap;
    phone `[+\-\d\s()]` regex + 32 cap; purpose 500 cap; visit_date
    `^\d{4}-\d{2}-\d{2}$`.
  * **Atomic uses guard**: `$inc` with a `uses < max_uses` filter
    kills the TOCTOU race that previously let parallel submits
    overshoot the link's use cap.
  * **Idempotent guest lookup**: matches by email → phone before
    creating a new profile.
  * `client_ip` persisted on every request for audit.

### Tests
- `backend/tests/test_iter341_guest_access_hardening.py` — 1 test,
  4 scenarios: missing name → 400, bad email → 400, 6th submit
  from same IP → 429, and 8 parallel submits against max_uses=3 →
  exactly 3 succeed (no race overshoot).

## iter 339-340 — 2026-02 — Punch corrections · Period-based financial edit gate

### Punch corrections
- `PUT /api/hr/timesheets/{id}/entries/{index}` — edits a single
  kiosk punch's arrival/exit with a required `reason`. Rejects
  reversed timestamps.
- `DELETE /api/hr/timesheets/{id}/entries/{index}?reason=<>` —
  removes a bad punch. Reason required.
- Both endpoints re-roll `hours_worked` + `days_worked` from
  remaining entries and append to `punch_corrections[]` (capped at
  last 50) with before/after payloads + who/when.
- Frontend: TimesheetsPanel "Punches" button opens an entries table
  with inline Edit/Delete + correction log accordion.

### Financial edit gate is now period-based
- `routers/financial.py::_within_self_edit_window` no longer denies
  after 7 days.
- New async helper `_period_open_or_admin(doc, user)` layers
  `finance.setup.period_is_locked` on top of the creator check.
  Donations / expenses / their delete variants all use it, so a
  creator can amend or delete an entry any time BEFORE the fiscal
  period covering the entry's date is closed.
- Admins still bypass every gate.

### Tests
- `backend/tests/test_iter339_punch_and_period_edit.py` — 2
  scenarios: punch edit + delete rolls up hours; financial gate
  allows on open period, denies on locked, admin bypass.

## iter 338 — 2026-02 — Kiosk autofill · Per-day XLSX Daily Log

### Badge Autofill on Kiosk
- New `sync_kiosk_to_timesheet(staff_id, action, when_iso,
  location_id)` in `backend/routers/hr.py`.
- Hooked into `kiosk_checkin` + `kiosk_pin_checkin` in
  `routers/events.py`: any staff (with active `hr_salaries`) who
  scans in at a kiosk gets an entry appended to the current pay
  period's timesheet; scan-out closes it, hours + days auto-roll.
- Non-payroll members silently skipped. Stale open punches (>12h
  idle) are auto-closed at +8h so forgotten checkouts don't wreck
  the week. Timesheet marked `source='kiosk_autofill'`,
  `status='draft'` awaiting HR review at period end.
- `_current_period_for_location(location_id)` picks the right
  period label from HR settings (monthly / biweekly / weekly).

### Per-day XLSX Daily Log
- `backend/routers/hr_timesheet_templates.py::timesheet_template`
  now creates a second sheet "Daily Log" with per-staff × per-day
  rows (14 days for biweekly, full month for monthly). Columns:
  Staff Name | Badge | Date | Arrival | Exit | Hours | Notes.
- Hours cell is an Excel formula: `=IF(AND(D<>"",E<>""),
  IF(E<D,(E-D+1)*24,(E-D)*24),"")` — handles overnight wrap.
- `timesheet_upload` now reads the Daily Log sheet, sums hours +
  days per badge, and uses them as fallback when the Summary
  Hours Worked / Days Worked cells are blank. Notes get a
  `[hours from Daily Log]` tag so directors know which source
  fed the number.

### Tests
- `backend/tests/test_iter338_kiosk_and_daily_log.py` — 5
  scenarios in one asyncio.run: kiosk create timesheet on check-in,
  close-and-rollup on check-out, non-payroll silent skip, XLSX
  template contains Daily Log sheet, upload falls back to Daily
  Log when Summary is blank.

## iter 337 — 2026-02 — Overtime · Hours-on-Timesheet · XLSX template · Payslip wage breakdown

### Overtime tier
- `routers/hr.py::_compute_base_gross` for `wage_type='hourly'`
  splits hours at `ot_threshold_hours` (weekly, scales with the
  period's week-count) into regular + OT slices, paying OT at
  `rate × ot_multiplier` (default 1.5). Details string shows the
  split (`10,000 × 80h reg + 10,000 × 1.5× × 10h OT`).
- `create_salary` accepts `ot_threshold_hours` + `ot_multiplier`;
  `update_salary` allowed-list expanded.

### Hours on Timesheet
- `submit_timesheet` accepts optional `hours_worked` (0-1000). Doc
  now persists it. `generate_payslips` and `preview_payslips` merge
  hours from approved timesheets and forward them to
  `_compute_base_gross`, replacing the days × 8h fallback.

### XLSX template + upload
- New `backend/routers/hr_timesheet_templates.py`:
  * `GET /api/hr/timesheets/template?period=<>` — returns an XLSX
    seeded with every active salary (name, badge, wage type, rate)
    plus 5 blank rows for casual workers and a signature/HR-approval
    line. Instructions sheet included.
  * `POST /api/hr/timesheets/upload?period=<>` — parses the same
    format, matches rows by badge_number (fallback: case-insensitive
    name), creates timesheet drafts with `status='submitted'` +
    `source='xlsx_upload'`. Idempotent re-uploads reuse the existing
    draft for the same staff+period.
- Router registered in `server.py` right after the main HR router.

### Payslip PDF wage breakdown
- `hr_payslips` docs persist `wage_type` + `wage_details` at
  generation time. `_generate_payslip_pdf_bytes` prints a "Wage
  breakdown: …" line under the header for anyone with the field
  populated. Rate type also shown in the meta grid.

### Frontend
- HR Salary form (`HRPage.jsx`) gains Rate Type picker (already in
  iter 336) plus OT threshold + multiplier fields shown only when
  `wage_type='hourly'`.
- TimesheetsPanel: Log-for-Staff dialog adds an "Hours worked"
  field. New "Sheet up/download" toolbar button opens an XLSX
  dialog: pick a period, download the pre-filled blank sheet, hand
  it out on paper, then re-upload the completed file — HR sees a
  per-row created/skipped report inline.

### Tests
- `backend/tests/test_iter337_ot_hours_xlsx.py` — end-to-end: OT
  math (with & without threshold), hours-worked timesheet →
  preview → OT-adjusted gross, XLSX template contents, XLSX upload
  matching by badge_number.

## iter 336 — 2026-02 — Per-salary wage types

### `_compute_base_gross(sal, period, working_days, days_worked, hours_worked)`
- New helper in `backend/routers/hr.py` that picks the right math
  based on the salary's `wage_type`:
  * salary / monthly → monthly_base × pay_frequency proration
  * daily    → daily_rate × days_worked
  * hourly   → hourly_rate × hours_worked (days × 8h fallback)
  * weekly   → weekly_rate × (period_days / 7)
  * biweekly → biweekly_rate × (period_days / 14)
- Returns `(gross, human_details_string)` so the preview table can
  show `60,000 × 10 days` under the number.
- Also exposes `_period_span_days(period)` for weeks-in-period math.

### `_generate_payslips_for` + `preview_payslips`
- Both endpoints call `_compute_base_gross` instead of the previous
  `monthly_base × proration_factor` shortcut.
- Unpaid-leave proration and days-worked shortfall blocks are skipped
  when `wage_type` ∈ {daily, hourly} — the base_gross already reflects
  actual units, so re-applying would double-deduct.
- Preview response gains `wage_type` and `wage_details` fields.

### `update_salary` allowed list
- Adds `wage_type`, `hourly_rate`, `daily_rate`, `weekly_rate`,
  `biweekly_rate` so directors can tweak rate type / rate on
  existing salaries (with full audit-history capture).

### Salary form UI
- `HRPage.jsx` salary form gains a Rate Type picker (Monthly Salary /
  Hourly / Daily / Weekly / Biweekly) alongside Pay Frequency.
- Amount label auto-updates ("Hourly Rate *", "Daily Rate *", etc.)
  with a contextual helper line explaining how the number is applied
  per period.
- Save handler now writes the correct `hourly_rate` / `daily_rate` /
  `weekly_rate` / `biweekly_rate` field alongside `base_salary` so
  legacy code reading `base_salary` still sees a value.

### Preview dialog
- Gross column now shows the wage breakdown below the amount
  (e.g. `60,000 × 10 days`) so directors can eyeball proration
  correctness at a glance.

### Tests
- `backend/tests/test_iter336_wage_types.py` — 6 scenarios: daily,
  hourly, weekly, biweekly, monthly (regression), and a live preview
  integration check confirming a daily 60,000 UGX × 10 days === 600,000.

## iter 335 — 2026-02 — Payroll preview · Anchor nudge · PDF coverage line

### `/hr/payslips/preview` dry-run
- `backend/routers/hr.py` adds `POST /hr/payslips/preview` that returns
  every staffer's computed gross / allowances / deductions / net for the
  picked period WITHOUT persisting. Reuses the identical math from
  `_generate_payslips_for` so preview never drifts from generate.
- Response also flags `already_generated: true` for anyone whose
  payslip already exists in that period, so the UI can grey-out
  "will skip" rows.

### Generate dialog gains a Preview step
- `pages/HRPage.jsx` Generate Payslips dialog is now two-step:
  Preview → Draft. Preview surfaces a table with gross/net per
  staffer plus a totals footer ("Total net pay (N new payslips)").
  Existing payslips render at 50% opacity with a "Skipped" chip.

### Anchor nudge for biweekly / weekly
- Switching HR Settings frequency to weekly/biweekly with no
  `next_pay_date` pre-fills the coming Wednesday (or the configured
  `payday_weekday`) and toasts the admin the picked date so they can
  fine-tune.

### Payslip PDF coverage line
- `_generate_payslip_pdf_bytes` now parses the canonical period label
  and prints "Covers work from <start> to <end> (<N weeks/1 month>)"
  under the payslip header. Works for both `YYYY-MM` (monthly) and
  `YYYY-MM-DD_YYYY-MM-DD (Www-Www)` (biweekly/weekly) formats.

### Tests
- `backend/tests/test_iter335_preview_and_pdf.py` — asserts the
  preview endpoint returns the correct gross/net WITHOUT writing to
  `hr_payslips`, and verifies the payslip PDF HTML contains the
  coverage line for a biweekly period.

## iter 334 — 2026-02 — Biweekly payroll UX cleanup

### Period labels reflect the real span
- `routers/hr.py::_biweekly_period` now emits `(Www-Www)` for windows
  that straddle two ISO weeks. Every biweekly period does — so staff
  will always see the correct span instead of a lone `(W38)` that
  reads as a single week's pay.

### Settings UI removes the confusing day-of-month picker
- `pages/HRPage.jsx` hides "Payday (day of month)" whenever pay
  frequency is anything other than `monthly`. A dashed placeholder
  clarifies that biweekly/weekly cadences are anchor-driven from
  Next Pay Date. Next Pay Date shows a red required hint if left
  blank on non-monthly setups.

### Backend guardrail prevents silent fall-through
- `/hr/payslips/upcoming-paydays` now raises 400 with an actionable
  message if a weekly/biweekly campus is missing `next_pay_date`.
  Previously it silently defaulted to a stale day-of-month anchor
  and produced wrong periods.

### Payday picker window explainer
- Generate Payslips dialog surfaces "Covers work performed from
  <start> to <end> (2 weeks)" next to the picked biweekly payday so
  the window/amount relationship is obvious.

### Tests
- `backend/tests/test_iter334_biweekly_period_label.py` — verifies
  the new label format and re-checks the screenshot amounts
  (600k → 276,923.08; 400k → 184,615.38; 75k → 34,615.38) match
  the 12/26 biweekly proration.

## iter 333 — 2026-02 — Role persistence · Live call ringing · Console departments · Sponsor directory hygiene

### Role edits persist
- `components/admin/UserEditDialog.jsx`: primary-role Select clears the
  `is_admin` toggle on change. Previously the admin-tier fold-back in
  `AdminPage.saveEdit` kept overwriting the picked role with
  `'admin'` because `is_admin` was stuck true from hydration.

### Live incoming-call ringing
- New `components/IncomingCallModal.jsx` mounted from `Layout.jsx`.
  Subscribes to the existing `incoming_call` WS broadcast, plays a
  soft ringtone, and pops Answer / Reject over any page.
- Answering navigates to `/comms?call=<id>&caller=<id>&answer=1` so
  the RTCPeerConnection plumbing on the Comms page picks up the offer
  without renegotiating.

### Console departments in Location editor
- `pages/LocationsPage.jsx` now imports `departmentsApi` and, when
  editing an existing location, fetches its console-managed
  departments (`location_id=<loc.id>`) into a read-only chip list.
- Legacy free-text departments still render below with an amber
  "migrate these" banner. New locations show a hint asking the admin
  to save first, then reopen to manage cost centres from the Admin
  console.
- Added `data-testid="manage-departments-link"` linking to
  `/admin?tab=departments`.

### Sponsor directory hygiene
- `routers/social_work.py::_upsert_external_sponsor_guest` no longer
  auto-creates guest rows. Lookup order now: `db.users` (by email) →
  `db.members` (by email or phone) → `db.guests` (any kind, by email
  → phone → name).
- Match found → backfill `is_sponsor`, phone, notes, updated_at
  without touching `kind` or `name`.
- No match → return None and let the sponsor stay purely on the
  case's `sponsor_manual` object. People/Guests directory stays
  clean.

### Tests
- `backend/tests/test_iter299_sponsor_no_autopeople.py` — asserts
  no-match / user-match / guest-match branches behave correctly and
  no stray guest rows leak into the directory.

## iter 332 — 2026-02 — Social Work auto-populate + Notes chronology

### Auto-populate case Family/Education/Medical from reviews
- `routers/social_review_forms/child_sync.py` gains
  `_apply_review_to_case(child_id, kind, data, fields, review_id)`
  called from `_apply_review_to_child` after the child doc updates.
- Mirrors the latest review's structured fields onto the active
  `db.social_cases` document so the `CaseDetailDialog` reads fresh
  values without staff retyping.
- Writes a `_field_sources[fieldName] = {review_id, review_date, kind,
  at}` map + a rolling `_change_log[]` (last 20 entries) on each
  section so counsellors can audit exactly which review overwrote
  which value.
- welfare_visit → family; school_progress → education (with
  prev→new pairs); medical_exam → medical.
- Idempotent — re-saving the same review updates the source stamp but
  never DELETES existing fields.

### Frontend source pills + change-log dialog
- `pages/SocialWorkPage.jsx` renders `SourceBadge` (`from home visit
  YYYY-MM-DD`) inline next to every auto-populated Family / Education
  / Medical field. `ChangeLogButton` opens a per-section audit dialog.
- A one-line emerald banner appears at the top of Family / Education
  when at least one auto-populated field is present, telling
  counsellors "edit and Save to overwrite".

### Notes chronology "New" pill
- Notes remain newest-first (existing behaviour). Unseen notes get an
  animated green `New` pill + emerald ring + light shadow to visibly
  rise above the chronology.
- Seen state stored per case in `localStorage`
  (`sw:seen_notes:<caseId>`). Clicking a note marks it seen; the pill
  clears immediately.

### Tests
- `backend/tests/test_iter298_case_autopop.py` — direct calls to
  `_apply_review_to_case` verify welfare / school / medical +
  idempotent re-runs (all four scenarios in a single test to share
  the motor event loop).

## iter 331 — 2026-02 — Social Work merge · Donation payer filter · Seed COA 4005

### Social Work tabs merged
- `pages/SocialWorkPage.jsx` `CaseDetailDialog` tabs collapsed from 11
  to 8 by folding `medical` → **Family & Medical**, `notes` → **Goals &
  Notes**, `school_reviews` → **Education & School**.
- Achieved by re-tagging the secondary `TabsContent` blocks with the
  parent's `value` — Radix mounts every matching content section,
  giving one continuous canvas per subject. Each secondary block shows
  under a `border-t` divider with a `Heart` / `ClipboardList` /
  `GraduationCap` section heading so counsellors keep their bearings.
- No content was deleted or moved; all existing state hooks and
  actions keep working unchanged.

### Donation payer-type filter
- `GET /api/financial/donations` now accepts `?payer_type=` (`sponsor` |
  `parent` | `org` | `external`). Backwards-compatible: legacy rows
  without `payer_type` are matched by mirror `type` (`sponsorship` →
  sponsor, `parent_contribution` → parent) so historical data slots
  in without a migration.
- Verified end-to-end via curl: `?payer_type=parent` returns the
  parent-contribution row from iter 330 tests; `?payer_type=sponsor`
  returns the sponsor row.

### Seed COA `4005 Parent Contributions Income`
- Added to `SEED_ACCOUNTS` in `routers/finance/_common.py` so new
  campuses ship with the parent-vs-sponsor income split without a
  manual step. `add_case_payment` already prefers 4005 with a
  fallback to 4000, so this closes the loop.

## iter 330 — 2026-02 — Sponsor↔Parent payments · Slot picker · Scanner deep-link

### Sponsor vs Parent payment routing (backend)
- `POST /api/social-work/cases/{id}/payments` now inspects `source`
  and derives a `payer_type` (`parent` / `sponsor` / `org` / `external`).
- **Parent / guardian contributions** are classed as `child_support`
  income and posted to `4005 Parent Contributions Income` (fall back
  to `4000` if 4005 hasn't been seeded), so campus P&L cleanly
  separates external sponsor gifts from family contributions.
- Every entry now carries the child's `location_id` AND
  `sublocation_id` on the payment row + mirror row + JE so campus
  GL and sublocation rollups both pick it up.
- Mirror donation row's `type` becomes `parent_contribution` (vs
  `sponsorship`) for parent payers; JE `source` becomes
  `parent_contribution`.
- Verified via curl: parent JE tagged `source=parent_contribution`,
  sponsor JE tagged `source=social_donation`, both on `loc_001`.

### POS cart slot picker (frontend)
- `SalesPortalPage.jsx` cart line items now render a date + start-time
  + end-time trio when the product carries `resource_id`. Editing any
  field updates the cart state so the sale POST ships the operator's
  picked slot instead of the default 14:00–15:00.

### Ticket scanner deep-link (frontend)
- `TicketScannerPage.jsx` result card now surfaces `event.event_date`
  (localised) and `event.location_name / venue / location_id` beneath
  the admit banner. Test IDs `ticket-scan-event-date` and
  `ticket-scan-event-venue` for automation.

## iter 329 — 2026-02 — Ticket Scanner page + marketplace product pickers

### Backend — ticket redemption endpoints
- `routers/event_tickets.py` gained a second `APIRouter`
  (`tickets_router` at `/api/tickets`) exposing:
  - `GET /api/tickets/{id}` → returns `{ticket, event}` with a minimal
    event summary so the scanner UI can label the door.
  - `POST /api/tickets/{id}/redeem` → marks the ticket `status="used"`
    and stamps `used_at / used_by / used_by_name`. 409 with the
    original redemption timestamp if already used; 410 if voided.
- Registered in `server.py`.

### Frontend — `/ticket-scanner` page
- New `pages/TicketScannerPage.jsx` (behind `COORDINATOR_PLUS` guard):
  - Camera QR scan via `html5-qrcode` (extracts a `tkt_[a-zA-Z0-9]+`
    from any decoded string so both bare ids and URLs work).
  - Manual `tkt_...` input for keyboard-only workflows.
  - Persistent result card (green / amber / red / red) that summarises
    the outcome (`Admit one`, `Already used at …`, `Void`, `Not a
    valid ticket`) so door staff can double-check before waving the
    next family in.
- App.js route + Layout sidebar entry + route-guard rule added.

### Frontend — marketplace product linkage
- `SalesPortalPage.jsx` product-manage dialog gained two dropdowns:
  **Link resource** (bookable, non-consumable) and **Link event**
  (public, non-cancelled). They're mutually exclusive — picking one
  clears the other. Helper text confirms what will happen at sale time.
- `addToCart` now, when a product carries `resource_id`, attaches a
  default booking slot (today, 14:00–15:00) to the cart line item so
  the sale POST passes the fields the auto-booking code in
  `create_sale` needs.
- Verified end-to-end via curl: lookup / redeem / double-redeem 409 /
  bogus id 404.

## iter 328 — 2026-02 — Marketplace ↔ resource bookings + event tickets

### Product model
- Extended `ProductCreate` / `ProductUpdate` (`routers/products.py`) with
  two optional links:
  - `resource_id` → any sold unit of this product auto-creates a
    booking on the linked resource.
  - `event_id` → each sold unit auto-issues one `event_tickets` row
    tied to the sale.

### Sale flow
- `create_sale` (`routers/sales.py`) now, after the sale doc is
  persisted and stock decremented:
  1. Fetches every referenced product in a single query.
  2. For `resource_id` products: reads `booking_date / booking_start_time /
     booking_end_time` off the line item, runs `check_booking_conflict`
     (skips gracefully on conflict, logged) and writes a `bookings` row
     tagged `source="marketplace_sale"`.
  3. For `event_id` products: writes one `event_tickets` row per unit
     sold, tagged `source="marketplace_sale"`.
  4. Writes both id arrays back onto the sale as `linked_booking_ids` /
     `linked_ticket_ids` so the receipt UI can deep-link.
- Failures at this step are logged but never roll back the sale —
  the sale record is already committed.

### Two-way lock (staff booking ↔ marketplace)
- Because marketplace-created bookings share the `db.bookings`
  collection with staff-created ones, the existing staff booking
  dialog's `check_booking_conflict` naturally blocks overlapping
  slots. Verified end-to-end via curl: sale-created booking at
  14:00–16:00 blocks a subsequent staff POST at 15:00–17:00 with a
  409 that references the sale's window.

## iter 327 — 2026-02 — Resources kind tabs + select-all

### Kind filter tabs
- Added a segmented control on `pages/ResourcesPage.jsx` above the grid:
  **All** (default), **Bookable**, **Consumable**, **Unbookable**. Each
  tab shows a live count and combines with the existing search box and
  type stat-card selector for compound filtering.
- Logic:
  - `bookable` = `is_bookable && !is_consumable`
  - `consumable` = `is_consumable`
  - `unbookable` = `!is_bookable && !is_consumable`

### Select all
- New `Select all (N)` checkbox next to the tabs. Selects every row in
  the current filter view (respects search + kind + type). Supports the
  indeterminate visual state via `ref.indeterminate` when only some
  filtered rows are selected. Feeds straight into the existing
  `BulkActionBar` (export / delete / bulk barcode print).

### Booking lock (staff + public)
- Verified: `POST /api/bookings` already runs `check_booking_conflict`
  with a 1-hour buffer for *every* incoming request — staff dialog, the
  public bookings page, and the `ResourceViewPage`. No additional
  changes required at that layer.
- Marketplace side: the `sales` / marketplace flow does not currently
  carry a `resource_id`, so wiring a two-way marketplace ↔ resource
  lock needs the marketplace itself to first reference resources.
  Deferred to a follow-up turn.

## iter 326 — 2026-02 — COA bulk import + Fair Alerts wipe

### Chart of Accounts — CSV / XLSX bulk import
- **Backend**: `POST /api/finance/chart-of-accounts/bulk-import` accepts
  `{accounts: [{code, name, type, bank_subtype?, is_cash?}]}` and returns
  `{created_count, skipped_count, invalid_count, created, skipped, invalid}`.
  Existing codes (in the DB or duplicated within the payload) are skipped
  so re-uploading the same file is safe. Max 500 rows per request.
- **Frontend**: `CoaImportDialog` on the CoA panel parses `.csv` via
  `papaparse` and `.xlsx` via `xlsx` client-side, normalises header casing,
  previews up to 200 rows in a table, then POSTs to the bulk endpoint.
  Shows a diff-style result summary with expandable "invalid" and
  "skipped" details. Ships with a "Download template" button.
- Verified via curl: 3/4 rows created on first upload, all 2 skipped on
  re-upload (idempotency confirmed).

### Fair Alerts feature wiped
- Deleted `backend/routers/fare_alerts.py` and `frontend/src/pages/FareAlertsPage.jsx`.
- Removed `_run_fare_alerts_loop` from `scheduler.py` and its `create_task`
  in `server.py` startup.
- Removed `fare_alerts` collection indexes from `db_indexes.py`.
- Removed `/fare-alerts` route from `App.js` and the sidebar entry from
  `Layout.jsx` (both nav item and route-guard rule).

## iter 325 — 2026-02 — Finance entry: campus + department fields (auto-prefill)

### Backend
- `post_journal_entry` (`routers/finance/_common.py`) now accepts
  `department_id`. Persisted on `finance_journal_entries.department_id`
  so Dept P&L rollups pick manual JEs up alongside expense allocations.
- `/api/finance/transactions/expense` and `/income`
  (`routers/finance/transactions.py`) both accept `department_id`
  optional in the body and forward it to the JE.

### Frontend
- `QuickPostDialog` on `pages/FinancePage.jsx` gained two new fields:
  required **Campus / sub-location** and optional **Department**.
  Sub-locations for the picked campus are shown indented under it.
  Departments refresh whenever the campus changes.
- Both fields auto-prefill from the current user (`active_campus_id` +
  first entry in `department_ids`). Small helper text shows
  "Prefilled from your active campus / primary department" whenever
  the current value matches the default so users know why it's set.
- Verified end-to-end via curl: POST returns a JE with
  `department_id` set; the value survives round-trip through
  `/api/finance/journal`. Backend now returns 400 when `location_id`
  is missing, matching the pre-existing enforcement.

## iter 324 — 2026-02 — Reliability sweep (React #31, task persistence, notifications, boards perf)

### React error #31 (`{name, color}` rendered as child)
- Fixed label rendering in `pages/kanban/CardDetailDialog.jsx` and
  `pages/kanban/KanbanCard.jsx` — a label can be either a legacy string
  colour (`"#3b82f6"`) or the newer `{name, color}` object. The old
  `{lbl.name || lbl}` fallback rendered the object when `name` was an
  empty string (the shape produced by toggling a colour without typing
  a name), which is what triggered the crash on production /boards.

### Tasks disappearing after creation
- `TasksPage.addCard` used to schedule `setTimeout(() =>
  fetchBoardDetail(), 300)` after POST. That refetch raced against the
  local optimistic swap and, in most attempts, wiped the just-added
  card off the UI. Removed the delayed refetch — server response is
  already merged into state.

### Calendar
- Default `taskScope` in `CalendarPage.jsx` changed from `'mine'` to
  `'campus'` so tasks with a due date show up without the user having
  to be in `assignees` / `created_by`. Users can still toggle back.

### Notifications persistence
- `GET /api/notifications` now defaults to unread-only. Explicit
  `?include_read=true` reveals the full history. Cleared notifications
  no longer resurface after re-login or redeploy.

### Admin/Boards page timeouts
- `GET /api/boards` was doing N+1 `count_documents` calls (one for
  lists, one for cards, per board). Replaced with two
  `aggregate($group)` pipelines so latency is O(1) round-trips rather
  than O(N).

### Cleanup
- Deleted the unreached legacy `FinancialPage.jsx`; `FinancePage.jsx`
  is now the single Finance surface.

## iter 323 — 2026-02 — Sub-location budget UI + Dept P&L drill-down

### Sub-location budget UI (last-working-item P0)
- New **Budgets** tab on Finance (`/financial`) with
  `SublocationBudgetsPanel`: inline editable hard-cap input per
  sub-location; blank + Save clears the cap, otherwise the value
  overrides the auto-rolled department sum on Dept P&L rollup strip.
- Uses `sublocationsApi.setBudget` → `PUT /api/sublocations/{id}/budget`
  (already wired last iter). Verified full flow via browser: panel
  renders 1 row (`Test Kitchen`) with `Auto-rollup` placeholder, save
  button toggles between Saved/Save on input change.

### Dept P&L drill-down (P1)
- Backend: `GET /api/reports-department/{department_id}/entries` — one
  audit view of every entry that rolled into a department's totals in
  the given window. Sources: `expenses.department_id`,
  `expense_allocations` (payroll splits, joined to staff name), and
  `donations.department_id` (optional revenue dimension). Response
  includes `entries` (sorted by date DESC) and `totals: {revenue,
  expense, net}`.
- Frontend: cards on `DepartmentPnlTab` are now clickable; a dialog
  opens with rev/exp/net summary strip and a scrollable table of
  contributing entries, each tagged with a coloured `Badge`
  (`donation` / `payroll` / `expense`). Test IDs: `dept-drill-modal`,
  `drill-entry-*`, `drill-total-{revenue,expense,net}`,
  `drill-close-btn`.
- Client hook: `departmentsApi.entries(id, {date_from, date_to})`.

### Housekeeping
- Fixed a stale `departmentsApi` import in `AdminPage.jsx` (lint
  blocker introduced last iter).
- Added Budgets + Dept P&L as tabs on the ACTIVE `FinancePage.jsx`
  (route `/financial`). Prior iter's edits landed on the legacy
  `FinancialPage.jsx` which is unreached; left intact for now.

## iter 322 — 2026-02 — ASGI middleware fix + Dept P&L tab + Payroll allocation strip + Sub-location budget

### Middleware Fix (ROOT CAUSE OF ALL PREVIOUS 307 / RuntimeError FLAKES)
- Rewrote `SecurityHeadersASGI` + `RateLimitMiddleware` as pure ASGI
  classes (`__call__(scope, receive, send)`) — bypasses Starlette's
  `BaseHTTPMiddleware` `dispatch_func` wrapper that was raising
  `RuntimeError: No response returned` under load in the preview
  container. Verified 8/8 sequential requests → HTTP 200, security
  headers preserved (`x-frame-options`, `x-content-type-options`,
  `referrer-policy`).
- Kept `kiosk_role_guard` as `@app.middleware("http")` because it
  needs the parsed `Request` and always returns a Response cleanly
  (never hits the buggy code path).

### Department P&L Tab (Financial → Dept P&L)
- `components/DepartmentPnlTab.jsx` — date-range picker + campus/sublocation
  rollup cards + per-department grid with budget-progress bars, revenue /
  expense / net triad, and expand-to-see-details (run-rate + budget headroom).
- Wired into `FinancialPage.jsx` as the last tab (`data-testid="tab-dept-pnl"`).
- Reads `GET /api/reports-department/pnl?date_from&date_to`.

### Payroll Allocation Info-Strip
- New backend endpoint `GET /api/hr/payslips/{id}/allocations` — returns
  the split rows enriched with department name + colour.
- `HRPage` payslip history dialog opens with a single Promise.all: the
  history + allocations. Renders a green "Department funding split"
  strip on paid payslips showing each department's amount, currency,
  and percentage. Read-only visual, doesn't touch the aggregate JE.

### Sub-location Budget Editor
- New router `sublocations_budget.py`:
  - `GET /api/sublocations` — lightweight list (id, name, location_id, budget).
  - `PUT /api/sublocations/{id}/budget` — `{budget: number | null}`.
    Passing null clears the hard cap and falls back to the auto-rolled-up
    department-sum on Department P&L.
- Frontend client `sublocationsApi.setBudget(id, budget)` added.
- UI editor is a small follow-up (Finance → Budgets tab).

### Verified end-to-end
- `GET /api/reports-department/pnl` × 8 → 200/200/200/200/200/200/200/200
- Security headers survive middleware rewrite.
- Payslip allocations endpoint returns 404 on unknown id, 200 on real.
- Sub-locations endpoint returns `[]` on empty collection.
- All frontend files parse under `@babel/parser`.


## iter 321 — 2026-02 — Split-aware payroll + Dept guard + Bulk tag + Dept P&L

### Split-Aware Payroll
- `hr.pay_batch_payslips` now fans each paid payslip's net across the
  staff's active-salary `department_splits`. Rows land in a new
  `expense_allocations` collection: `{id, source: 'payslip', payslip_id,
  staff_id, department_id, location_id, amount, currency, pct, date}`.
- Aggregate expense JE still posts as a single line so cash-flow and
  bank reconciliation stay unchanged; departmental P&L reads the
  allocation table separately.

### Dept Deactivation Guard
- `PUT /api/departments/{id}` with `active: false` now returns HTTP 409
  with structured detail `{users_tagged, active_salaries, unpaid_expenses}`
  when live references exist. Set `force: true` on the payload to bypass
  after the admin has confirmed via the warning dialog.
- New `GET /api/departments/{id}/usage` returns counts + `safe_to_deactivate` flag.
- New `POST /api/departments/{id}/reassign` `{target_id}` migrates
  users' `department_ids`, salaries' `department_ids` + `department_splits`,
  expenses' `department_id`, and `expense_allocations.department_id`.
- Frontend `DepartmentsManager.remove` now peeks at usage before
  confirming, catches 409, and prompts for a reassign target.

### Bulk Tag Users
- `POST /api/admin/users/bulk-department` `{user_ids[], department_id, mode: 'add'|'replace'}`.
- Frontend bulk dialog gains an "Assign Department" action + mode
  toggle (Add keeps existing tags, Replace clobbers).

### Department P&L Report
- New `routers/reports_departments.py`
  `GET /api/reports-department/pnl?date_from=&date_to=&location_id=`.
  Aggregates:
  - `expenses.department_id` (direct tags)
  - `expense_allocations` (split-aware payroll)
  - `donations.department_id` (revenue side)
  Returns per-department revenue, expense, budget, net, `run_rate_monthly`
  (extrapolated to 30 days), and `budget_used_pct`. Also `rollups.by_sublocation`
  and `rollups.by_location` — sub-location & location budgets and expenses
  are automatically summed from their child departments.
- `departmentsApi.pnl(params)` client added.

### Verified end-to-end
- `GET /api/reports-department/pnl` → HTTP 200 with structured
  `{ period, departments, rollups: { by_sublocation, by_location } }`
- `POST /api/admin/users/bulk-department` → 400 on empty body with clear
  `user_ids and department_id required` message; valid body tags N users.
- `GET /api/departments/{id}/usage` returns tagged / salaries / unpaid counts.
- Deactivate with refs → HTTP 409 with structured detail; `force: true` → 200.

### Deferred for future turns
- Reports Departments tab UI (endpoint ready; component wire-up next slice).
- Sub-location `budget` field editor UI (backend rollup already computes
  from child departments; admin-editable budget field on sub-locations is
  a small follow-up).


## iter 320 — 2026-02 — Departments as cost centres (Option B) + Cross-Campus Move

### Backend
- New `routers/departments.py` (`GET/POST/PUT/DELETE /api/departments`).
  Model: `{id, name, description, location_id (req), sublocation_id?,
  color, budget, active}`. Campus-scoped list via `get_campus_filter`.
  Manager+ can create in own campuses; system_admin bypasses. Hard-delete
  refused while any user is tagged.
- `deps.default_creation_location(user, provided)` — main-first policy
  helper. Wired into `events.create_event`, `products.create_product` +
  pricelists, `approvals` workflows + requests, `funds` requests, and
  `scheduling` shifts. Multi-campus records now land at the user's MAIN
  campus by default, never scattered across whichever campus they've
  switched to.
- `admin.py ACCOUNT_FIELDS` now whitelists `department_ids` — multi-dept
  tagging on users (parallels `location_ids`).
- `hr.create_salary` + `update_salary` accept `department_ids` and
  `department_splits` `[{department_id, pct}]`. Splits validated to sum
  to 100 client-side + server-side (400 on mismatch). Static per salary
  record; freely re-editable, each new payslip inherits current split.
- `financial.ExpenseCreate` now takes structured `department_id` /
  `department_ids` / `department_splits`; legacy `department` string
  preserved for spreadsheet importer + old reports.

### Frontend
- **New reusable** `CrossCampusMoveDialog` (Events / Boards / Products
  via `location_id`; Tasks via board-picker grouped by campus). Admin
  action wired into EventsPage detail, ProductsPage row menu, TasksPage
  board header, and CardDetailDialog "Move to another board / campus".
- **New** `components/admin/DepartmentsManager` — chip-based CRUD living
  in Admin → System Console → Departments tab. Colour swatch, optional
  sub-location, budget, active toggle, soft/hard delete.
- `UserEditDialog` — new `UserDepartmentPicker` sub-component replaces
  the free-text Department field with a chip-based multi-select filtered
  to the user's assigned campuses; keeps legacy `department` string in
  sync with first pick. Hydration bug also fixed: `is_medical`,
  `is_resident`, `has_restricted_access`, `resident_location_id`,
  `is_guest`, `extension`, `security_*`, `badge_id`, `photo_url` now
  seed into `editForm` on open, and hidden `underlying_role` preserves
  system_admin across admin-tier toggles.
- `HRPage` salary form — multi-dept chip picker + funding-splits editor
  (Split-evenly button + per-department % input + live total validator
  turns red/green on 100). Hydrates on edit, resets to `{ department_ids:
  [], department_splits: [] }` on close.
- `FinancialPage` expense form — Department dropdown pulled from the
  real `departmentsApi` (falls back to legacy text input when no
  departments exist yet). Stores `department_id` (id) alongside legacy
  `department` (name string) so reports keep working.
- `TasksPage` — board header chip now reads "Board lives in: <campus>"
  with a `MapPin` glyph; Create Board dialog shows a live "Creating in:
  X" pill. `addCard` fully optimistic (temp id → swap on server response
  → rollback + toast on failure).
- `EventsPage` — Add Event dialog carries a "Creating in: <campus>" pill;
  `handleAdd` now inserts optimistically before `fetchEvents()`.
- **HR reset** moved out of HRPage and into Admin → System Console →
  Data & Backup (`HrResetCard`), sitting next to `FinanceResetCard`.
  Reset filter for `hr_payslips` now catches records stamped with
  either `location_id` or `payroll_location_id` (`$or`).
- **Payslip generation** is now payday-driven — new backend endpoint
  `GET /api/hr/payslips/upcoming-paydays` returns the next N paydays
  computed from `hr_settings` (frequency + anchor + weekday snap). The
  Generate dialog is a Select of those paydays instead of a plain month
  input, so weekly / bi-weekly cadences work end-to-end.
- **HR settings Pay Run Weekday** `<Select.Item value="">` crash fixed
  (Radix forbids empty-string values) — sentinel `__none__` mapped back
  to `null`.
- **Tasks-on-Calendar** — `list_tasks` no longer drops the "own boards /
  tagged boards / assigned-task boards" escapes when an active campus
  is pinned. Multi-campus admins now see their due-dated tasks on the
  Calendar again.

### End-to-end verified on preview
- 60/40 salary split created, persisted, and re-edited to 70/30 via
  `PUT /api/hr/salaries/{id}` — round-trip proven on live DB.
- Bad split (55/40) rejected server-side with a clear 400 detail.
- User `department_ids` tag round-trips through `PUT /api/admin/users/{id}`
  and `GET /api/admin/users/{id}`.
- Cross-campus move round-trips for Events, Boards, Products, Tasks
  (task moves via `board_id + list_id` swap on `PUT /api/tasks/{id}`).

### Recommended next slice (deferred, not yet built)
1. **Split-aware payroll auto-expense**: when a paid payslip auto-posts
   its expense JE, split the amount across the salary's
   `department_splits` so each department's P&L takes its share.
2. **Department P&L report**: budget vs actual, run-rate, drill-down.
3. **Bulk tag** action on user list (assign N users to a department).
4. **Warning on department deactivation** when live salaries or expenses
   still reference it.


## iter 314 — 2026-02 — Badge QR: nudged down + shrunk one step

Screenshot iteration feedback: the QR at 108 × 108 was too wide, chopping
the tail of long first names ("Silvester" → "Silvest…"). It also sat
vertically centred, which meant the QR floated above the photo's bottom
edge instead of feeling anchored to it.

- QR shrunk **108 → 92 (large)** and **78 → 68 (small)** so the left
  column gets ~16 px more breathing room. Long first names now fit
  without the ellipsis.
- QR alignment moved from `center` to `flex-end` with a small
  `marginBottom`, so it lands **flush with the photo's bottom** —
  reads as anchored to the badge rather than floating.
- Screenshot-verified: "Admin" first name now shows in full, QR sits
  lower next to the photo.

## iter 313 — 2026-02 — Expense deep-links + badge polish (crown → star, QR cleaner)

### Expense bell deep-links
- `routers/financial.py` — approve + reject writes now use link
  `/portal/expenses?expense=<id>` (was bare `/portal/expenses`).
- `PortalExpenses.jsx` reads `?expense=<id>` via `useSearchParams`,
  scrolls that expense row into view (`scrollIntoView` centered), and
  briefly ring-highlights it (3.5 s amber ring + amber-50 bg) so the
  user sees exactly what changed. Query param cleared once consumed.
- **Verified end-to-end**: approving an expense fires notification
  with link `/portal/expenses?expense=exp_xxxxxx`.

### Badge polish
- **Crown replaced with a friendly 5-point Star** in
  `BadgeTypeIcon('director')` — the coronet outline read as "king" on
  admin badges, which people found intimidating for what is really a
  team-lead role.
- **QR now sits on the badge background** (no white card, no accent
  border, no shadow). Uses `bgColor={bgColor}` + `fgColor="#ffffff"`
  in normal mode so the QR pixels look like part of the badge, not a
  sticker. Kiosk mode still uses white bg + dark pixels because the
  kiosk header is light.
- **QR vertically centred** in the right column (`alignItems: 'center'`)
  so it no longer rides high against the top edge.
- **QR bigger + higher redundancy**: 108 × 108 (large) / 78 × 78 (small)
  with `ecLevel="H"` (~30 % pixel redundancy) so it stays scannable
  even after photocopy at reduced size — every mobile scanner and the
  existing kiosk hardware picks it up.

## iter 312 — 2026-02 — Badge photo right-most + task bell deep-links

### Badge layout — final pass
- Right column order flipped to **[QR | Photo]** so the photo is the
  right-most element on the badge (matching user request).
- Photo now uses `object-fit: contain` on an accent-tinted background so
  the face is always visible in full — no cropping, no letterbox gaps
  showing an unrelated colour. Container widened for legibility (108 px
  on the large badge, 76 px on small).
- QR bumped to `ecLevel="Q"` and a slightly larger tile (88 × 88 large /
  64 × 64 small) so it still scans reliably after photocopy/print
  reduction. Still plain squares — every scanner in the field reads it.

### Task bell deep-links
- `scheduler.py`: every task-related push + in-app write now points at
  `/tasks?task=<task_id>` (previously bare `/tasks`).
  - `_run_due_date_reminder_scheduler` (Task Due Tomorrow + Task Due
    Today) — push URL deep-linked.
  - `_fire_overdue_task_emails` — push URL deep-linked, and each
    recipient now also gets a bell-row via `create_notification` (was
    push+email only; the bell had nothing for overdue tasks). Uses the
    existing `task_overdue_emails` 3-day idempotency window so no
    duplicates.
- `TasksPage.jsx` reads `?task=<id>` via `useSearchParams`, finds the
  task across `allTasks` + per-list `tasks`, switches boards if needed,
  and opens the card detail dialog automatically. Query param is
  cleaned after the drawer opens so browser-back doesn't loop-open.
- **Verified end-to-end**: overdue task fired → notification row
  `link: "/tasks?task=task_iter312"`, type `warning`.

## iter 311 — 2026-02 — Event bell deep-links + badge photo/QR side-by-side (printable)

### Event bell deep-links
- `routers/events.py` now writes the new-event bell link as
  `/calendar?event=<event_id>` instead of the generic `/calendar` root.
- `CalendarPage.jsx` gained a `useSearchParams` effect: on first render
  (and once `rawEvents` is populated) it looks for `?event=<id>`, finds
  the matching event, sets `selected` (auto-opening the drawer), jumps
  the cursor to the event's month, and cleans the query param via
  `setSearchParams(..., { replace: true })` so browser-back doesn't
  loop-open.
- **Verified**: creating an event now produces a notification whose
  link ends `/calendar?event=evt_xxxxxxxx`, and clicking it opens the
  event drawer directly.

### Badge photo + QR side-by-side (and it now prints)
User feedback was clear: the QR should NOT embed the photo — it should
sit next to the photo as its own thing. Also, the previous separate-
image approach was rendering on screen but coming out blank in
Save-as-PNG / Print because html2canvas can't fetch cross-origin
images at render time.

**Fix**
- Rewrote the right column as **photo (portrait) + QR (square, slightly
  smaller) side by side**. Large badge: photo 96×148, QR 84×84. Small
  badge: photo 68×108, QR 60×60.
- QR is now **plain** (no embedded logo, `ecLevel="M"`, `qrStyle="squares"`)
  so any scanner reads it reliably.
- Added a `photoDataUrl` state + `useEffect` in `UnifiedBadge` that
  fetches the profile photo, converts it to a base64 data URL, and
  feeds it as the `<img>` src. That makes the pixel bytes available
  on the same origin as the render context, so **html2canvas exports
  and `window.print()` now include both the QR and the photo**. Falls
  back to the generated initials image if the fetch fails.

## iter 310 — 2026-02 — Fix silently-broken event & conference notifications

`routers/events.py` and `routers/conferences.py` both had a background-
task import of `send_bulk_notifications` from `routers.notifications` —
but that function has never existed. The `ImportError` was swallowed by
the surrounding `try/except`, so **no in-app notifications were ever
fired when an event or conference was created**. Users saw nothing in
their bell icon.

**Fix**
- Swapped `send_bulk_notifications` for a per-user loop over the
  existing `create_notification(title, message, user_id, notif_type,
  link)` helper — the same one already used by `financial.py` and
  `notifications.py`'s own POST endpoint. Real signature, real callers.
- Added `"id": 1` to the recipient projection so the per-user loop has
  a `user_id` to pass into `create_notification`. External emails
  (conferences only) still land in `recipients` for downstream email
  senders but are skipped by the in-app loop when they carry no `id`.
- Preserved the background-task structure (`asyncio.create_task` +
  outer/inner try-except) and the recipient role filter
  (admin/system_admin/Executive Director/Director/Manager).

**Verified end-to-end**
- `POST /api/events` → unread-count bumped from N → N+1.
- Latest `/api/notifications` row: title "New event: iter310 notify
  test", message "2026-02-15 • 10:00 • Kampala Central".

## iter 309 — 2026-02 — HR pay-run weekday + wallet badge parity

### HR pay-run weekday
Admins can now snap every weekly/bi-weekly pay run to a specific weekday.
Example use case from the field: "The last two Mon-Sun weeks always
pay on the following Wednesday."

- Backend `routers/hr.py`
  - New `_snap_to_weekday(d, weekday)` helper (0=Mon…6=Sun).
  - `_paydays_for_frequency(...)` and `_next_payday_after(...)` gained
    an optional `payday_weekday=` kwarg — when set, every computed
    payday is snapped forward to that weekday.
  - `payday_weekday` added to the allow-list of hr_settings fields.
  - Payday auto-fire (`generate-payday`) and back-fill both read the
    campus setting and forward it to the helpers.
- Frontend `HRPage.jsx`
  - Settings dialog now shows a **Pay Run Weekday** picker with
    Monday…Sunday options + an "Not set" default. Only visible when
    `pay_frequency` is weekly or bi-weekly (monthly still uses
    `pay_day` day-of-month).
- Verified: unit-tested the snap math (`biweekly + Wed` → 2025-02-05,
  2025-02-19; `weekly + Fri` from a Monday → 2025-02-14). Backend
  restarts clean, indexes ensured.

### Wallet badge parity
`WalletBadgePage.jsx` was still rendering its ad-hoc layout (initials
"SL" in the QR centre, small photo circle above the name) instead of
the new `UnifiedBadge` layout. Replaced the custom badge markup with
`<UnifiedBadge person={...} />` so every place a 58:12 badge renders
now uses the same component — Wallet, print dialog, PrintableBadges
bulk sheet, kiosk display. Future badge changes ripple everywhere
automatically.

## iter 308 — 2026-02 — Badge: QR moved to right, embeds photo, prints on every export

The staff badge was rendering a **tiny** ~58 px QR on the left and a
separate photo/initials block on the right. Two problems:

- **Unreadable**: 58 px is below the reliable scan threshold at print
  size; user reported it was too small to be useful.
- **Doesn't survive some export throws**: html2canvas + print splits
  QR pixels and the `<img>` photo across two paint layers, so certain
  export paths dropped one or the other.

**Fix (aligns UnifiedBadge with PrintableBadges + WalletBadgePage)**
- Removed the small left-side QR block entirely.
- Right column is now a **big square QR** (148 × 148 desktop /
  108 × 108 print-small) rendered via `react-qrcode-logo` with
  `logoImage = photo_url || generateInitialsImage(...)` embedded in
  the centre. QR pixels + the person's photo (or initials fallback)
  now live on the **same canvas**, so every export path (screen render,
  html2canvas PNG, `window.print()`, kiosk PDF) captures both.
- `ecLevel="H"` keeps the QR scannable even with the ~48 px logo
  overlay covering the middle third.
- `PrintableBadges.jsx` was already using this pattern (lines 102 for
  staff, 205 for child) — this brings the single-print dialog in line.

**Verified**
- No compile errors (`frontend.err.log` clean apart from unrelated
  webpack-dev-server deprecation notices).
- Sample screenshot from HR → Staff & Users → Staff & Users tab loads
  cleanly; badge dialog opens from any Print action.

## iter 307 — 2026-02 — System Console grouped into tabs

The `/admin` route (System Console) was a long vertical scroll of a dozen
different cards — module access, security checkpoints, security
companies, orphan-case repair, kiosk links, backup/restore, integrations,
branding, remote access, device pairing, finance danger zone. Finding a
specific setting meant scrolling through unrelated ones.

**What changed**
- `AdminPage.jsx` (`mode='system'`) now renders **5 tabs** using the
  existing shadcn `Tabs` primitive:
  - **Access** (default) — expiring-grants banner + Module Access
    manager.
  - **Security** — Security Checkpoints, Security Companies, Kiosk
    Links & Setup, Remote Access, Device Pairing (USB Devices & Roles).
  - **Data & Backup** — Backup/Restore Manager, Orphan Case Repair,
    Finance Reset (danger zone).
  - **Integrations** — 3rd-party API keys (Resend, Wave, Alpha
    Vantage, etc.).
  - **Branding** — logo, colours, sender name.
- Expiring-grants banner and the Finance danger-zone card were both
  moved off the top-level render into the appropriate tabs (Access
  and Data & Backup respectively).

**Verified** via desktop screenshots: header still reads "System
Console", 5 tabs render horizontally, tab-switching works (Access →
Module Access; Security → Checkpoints + Companies + Kiosk + USB
Devices). No compile errors.

## iter 306 — 2026-02 — Staff admin moved into HR; `/admin` renamed to System Console

The `/admin` route was labelled "Staff & Users" in the sidebar but the page
actually mixed two very different responsibilities: the day-to-day people
directory (add user, edit, reset password, print badge, bulk role change)
and platform infrastructure (integrations, backup, branding, security
companies, remote access, module access, finance danger zone). Day-to-day
admins living in HR & Payroll had to bounce out to a scary-looking Admin
page just to reset a password.

**What changed**
- `AdminPage.jsx` accepts a new `mode` prop:
  - `mode='system'` (default, used by the `/admin` route) — renders only
    the system-level cards, with header **"System Console"** and blurb
    "Platform-wide settings — integrations, backups, branding, security
    infrastructure, module access."
  - `mode='staff'` — renders only the staff directory + associated
    dialogs (Create, Edit, Reset Password, Badge, Bulk).
- `HRPage.jsx` gains a **Staff & Users** tab (admin/system_admin only)
  that renders `<AdminPage mode="staff" />`. HR & Payroll is now the
  one-stop shop for the people admin.
- Sidebar label under Admin group renamed from "Staff & Users" →
  **"System Console"** and its icon flipped from `User` to `Settings`
  to match what the page actually is.

**Verified via screenshots**
- `/admin` header renders "System Console" and shows Danger Zone,
  Module Access, Security Checkpoints, Security Companies, Unlinked
  Social Cases, Kiosk Links & Setup (system-only stack).
- `/hr` → **Staff & Users** tab renders "Staff & Users · 0 staff
  members" with search + role filter + Import + New User buttons
  intact.
- No compile errors after the mode-prop rewrite.

## iter 305 — 2026-02 — Ghost `payslips` collection removed

`db.payslips` had three indexes registered in `db_indexes.py` but zero
readers or writers anywhere in the app — every real payslip write goes
to `db.hr_payslips` (see `routers/hr.py`, 30+ refs). The empty collection
plus its dead indexes made routine debugging noisier ("wait, which one
does HR use?").

**What changed**
- `db_indexes.py`: dropped the three `db.payslips.create_index(…)` calls,
  left an inline note so future readers know `hr_payslips` is canonical.
- `tests/test_iter296_indexes.py`: dropped the matching ghost assertion.
- Dropped the empty `payslips` collection from the running MongoDB.

**Verified**
- Test suite: 55/55 (down from 56 by one removed ghost check).
- `/api/hr/payslips` and `/api/hr/payslips/mine` still respond (empty
  lists, as before — no real payslips exist yet in the test DB).
- `hr_payslips` still carries its five `iter301` indexes intact.

## iter 304 — 2026-02 — Notifications consolidation

Merged the two overlapping notifications routers into a single canonical
file at `routers/notifications.py`.

**Before**: `server.py` owned the in-app feed (`list`, `unread-count`,
`mark-read`, `create`, `delete`) with role-scoped filtering, while
`routers/notifications.py` owned VAPID + push-subscribe with a **different**
notification schema (`user_id`/`body`/`read` vs `target_role`/`message`/
`read_by`). Which version answered `GET /api/notifications` depended on
FastAPI include-order — brittle and confusing.

**After**: one router owns every `/api/notifications/*` path, using the
role-scoped schema server.py had. Includes:
- `GET /api/notifications` (role-scoped list with computed `read` flag)
- `GET /api/notifications/unread-count`
- `POST /api/notifications` (create)
- `PUT /api/notifications/read-all`
- `PUT /api/notifications/{id}/read`
- `DELETE /api/notifications/{id}`
- `GET /api/notifications/vapid-key` (returns both `public_key` and
  `publicKey` keys so old + new clients keep working)
- `POST /api/notifications/subscribe`, `DELETE /api/notifications/subscribe`
- Internal helper `create_notification()` + `_create_notification` alias
  (the alias unblocks the previously-broken import in `routers/financial.py`
  that was importing `_create_notification` — now it actually resolves).

**server.py after this pass**: 488 lines (was 535 after iter303, 1910
originally). ~74% smaller than the pre-refactor monolith.

**Verified end-to-end** via HTTP:
- List returns 2 notifs with computed `read` boolean.
- Unread-count correct.
- VAPID key returns both key names.
- Create → mark-read → delete round-trip works cleanly.
- Test suite: 57/57.

## iter 303 — 2026-02 — Route split (part 2)

Continued the server.py trim by moving five endpoint groups out into
dedicated router files under `/app/backend/routers/`.

**What moved**
- `routers/campus_switcher.py` — `PUT /api/user/active-campus`,
  `PUT /api/user/active-campus/clear`.
- `routers/two_factor.py` — `POST /api/auth/2fa/setup|verify|validate`,
  `DELETE /api/auth/2fa`.
- `routers/biometric_nfc.py` — `POST /api/biometric/register|verify`,
  `POST /api/nfc/register|scan`.
- `routers/google_auth.py` — `POST /api/auth/google`.
- `routers/push.py` — `POST /api/push/subscribe`,
  `DELETE /api/push/subscribe`, `GET /api/push/vapid-key`.
- Deleted the legacy `send_push_to_user` helper (was unused after iter302).

**server.py after this pass**: 535 lines (was 777 after iter302, 1910
originally). ~72% smaller than the pre-refactor monolith.

**Verified**
- All 13 extracted routes resolve via `app.routes`.
- `/api/push/vapid-key`, `/api/auth/2fa/setup`, `/api/auth/2fa` (delete),
  `/api/user/active-campus[/clear]`, `/api/nfc/scan` — all return correct
  HTTP responses end-to-end via the preview URL.
- Test suite unchanged at 57/57.

## iter 302 — 2026-02 — server.py modularization

Split the monolithic `server.py` (1910 lines) into focused sibling modules
so future feature work stays fast to navigate.

**What moved**
- `scheduler.py` (786 lines) — every `_fire_*` cron helper, the hourly
  `_run_due_date_reminder_scheduler`, `_run_fare_alerts_loop`,
  `_run_flight_status_refresh_loop`, and `_send_push_to_user` +
  `_last_auto_backup_date` state. All 11 scheduler-adjacent functions.
- `db_indexes.py` (316 lines) — the entire `_ensure_indexes()` idempotent
  startup index-creation routine (~140 indexes across ~50 collections).
- `seed_data.py` (77 lines) — `_seed_initial_data()` default-admin,
  default-locations, default-notifications, silvester auto-promote logic.

**server.py after the split**: 777 lines (was 1910). Only wires app-level
concerns (routes, middleware, startup/shutdown, health probes, 2FA + NFC
+ biometric + google-oauth stubs, campus switcher, notifications/push).

**Compatibility**: `server.py` re-imports every extracted symbol so
`from server import _fire_overdue_task_director_digest` still resolves for
existing tests and any external callers. Only two grep-based tests
required a path bump (looking in `scheduler.py` alongside `server.py`).

**Verified**
- Backend restart: `Indexes ensured (idempotent)` on cold boot.
- `/api/health`: healthy, scheduler.running=true.
- Auth login: `admin@5812global.org / Admin@1234` returns JWT.
- Direct scheduler invocation: `_fire_overdue_task_emails` +
  `_fire_overdue_task_director_digest` execute without error.
- Test suite: 57/57 (index sweep + digest presence + birthday helper).

## iter 301 — 2026-02 — Bcrypt pin locked + MongoDB hot-path index sweep

**Bcrypt pinning**
- `bcrypt==3.2.2` and `passlib==1.7.4` remain the working combo (passlib 1.7.4
  introspects `bcrypt.__about__.__version__`; bcrypt 4.1+ removed that attr).
- Updated the compatibility shim comment in `server.py` so future agents know
  the pin is intentional. Auth verified end-to-end: `hash_password` /
  `verify_password` round-trip works and `POST /api/auth/login` returns a
  fresh JWT.

**Index sweep — collections gained hot-path indexes**
- `guests` — id (unique), (location_id,status), family_id, user_id, email,
  phone, pin, (is_parent,family_id).
- `families` — id (unique), (location_id,family_name).
- `shipments` — id (unique), (status,created_at desc), (location_id,created_at desc).
- `social_cases` — id (unique), subject_id, (location_id,status,created_at desc).
- `social_review_forms` — id (unique), (child_id,review_date desc),
  (location_id,review_date desc).
- `products` — id (unique), (location_id,name), name, barcode, variants.barcode.
- `hr_payslips` — id (unique), (staff_id,period desc), (location_id,period desc),
  (status,period desc), salary_id.
- `hr_timesheets` / `hr_salaries` / `hr_time_off` — staff & location scoped
  keys for portal + payroll queries.
- `resources` / `venues` / `bookings` / `public_bookings` — schedule + token lookups.
- `approval_requests` — id (unique), (subject_kind,status,created_at desc),
  (location_id,status).
- `customer_accounts` — id (unique), user_id, customer_id, (location_id,name).
- `event_registrations` / `enrollments` / `conferences` — dashboard aggregates.
- `donors` — id (unique), (location_id,name), email.
- `announcements` / `documents` — location-scoped feeds.
- `case_notes` — (case_id,created_at desc).
- `call_logs` — (user_id,start_time desc), (location_id,start_time desc).

**Tests**
- Extended `/app/backend/tests/test_iter296_indexes.py` with 36 new
  parametrised checks. Total: 55/55 passing (up from 19).

## iter 300 — 2026-02 — Portal audit sweep — verified & one dead-state cleanup

Walked every Portal page end-to-end and confirmed both the frontend and
backend endpoints are wired correctly.

**Endpoint parity (all 200 as admin)**
- `GET /api/portal/dashboard` · `GET/PUT /api/portal/profile`
- `POST /api/portal/my-wallet-badge` · `POST /api/portal/children/{id}/wallet-badge`
- `GET /api/portal/tasks` · `PUT /api/portal/tasks/{id}/status`
- `GET/POST /api/portal/expenses` · `POST /api/portal/cash-request`
- `GET /api/portal/events` · `POST /api/portal/events/{id}/rsvp`
- `GET /api/portal/checkins` · `GET /api/portal/documents` · `POST /api/portal/documents/upload`
- `GET /api/portal/sales`
- `GET/PUT /api/portal/family` · `POST /api/portal/family/children` · `POST /api/portal/family/guardians`
  (last three return 404 "No family found" when the caller has no family — expected).

**Frontend parity per page**
- `PortalProfile` — edits name/phone/address/emergency/DOB/gender (iter 299), scans receipts (iter 299), issues own Wallet badge (iter 298), submits weekly Mon–Sun timesheet (iter 298), requests PTO. All wired.
- `PortalFamily` — CRUD works: add child, edit child (`childrenApi.update`), issue child badge, add guardian, remove guardian, update family. All wired.
- `PortalDocuments` — list + upload + fulfil requests (`documentsApi` + `portalApi.documents`). Wired.
- `PortalEvents` — list + RSVP. Wired.
- `PortalExpenses` — list + create expense + cash-request dialog (`reason` field already correctly named). Wired.
- `PortalSales` — read-only sales history. Wired.
- `PortalTasks` — list + status transitions via `portalApi.updateTaskStatus`. Wired.

**Cleanup**
- Removed unused `tsForm` state from `PortalProfile.jsx` — leftover from
  the iter 298 refactor to the `tsWeek` Mon–Sun grid.

**No functional bugs found. No new features required — all Portal edits stick end-to-end.**

---
(prior entries iter 292–299 unchanged)

## iter 315 — 2026-06 — Calendar quick-create: pricing fields restored

- `CalendarPage.jsx` "New Event" dialog was missing **Capacity**, the
  **Free event** toggle and the **Ticket price** field — they existed on
  the edit drawer and on `EventsPage` but never on calendar quick-create,
  so events made from the calendar always saved as free.
- Added Capacity (beside Location), a Free-event checkbox and a
  conditional Ticket price (UGX) input; `submitCreate` now posts
  `is_free` + `price` (null when free). Reset state updated.
- testids: `create-event-capacity`, `create-event-is-free`, `create-event-price`.
- Verified in preview: dialog renders all fields, toggling free reveals price.

## iter 316 — 2026-06 — Calendar consolidation, shared-feed task fix, holiday pay policies

**1. Calendar event form — pricing restored + tiers**
- `New Event` had lost Capacity / Free-vs-paid / Ticket price; restored and
  added the full **Ticket Tiers** builder (new `components/TicketTiersEditor.jsx`)
  to BOTH create and edit forms.

**2. EventsPage deleted, features migrated**
- `pages/EventsPage.jsx` (1009 lines) was dead code — `/events` already
  redirected to `/calendar`. Deleted, import dropped from `App.js`, Layout
  quick-nav `/events` → `/calendar`.
- Its still-live features moved into the Calendar event drawer via new
  `components/EventDetailTabs.jsx`: Registered (with mark-paid + CSV export),
  Check-Ins (with check-out), Tiers summary, Waitlist (promote/cancel).
  Drawer also gained **Duplicate**. `openItem()` now hydrates the full event
  via `GET /api/events/{id}`.
- **`backend/routers/events.py` stays** — it powers public events, public
  bookings, kiosk, check-ins, venues and the calendar feeds (71 endpoints).

**3. BUG — board tasks missing from shared calendar feeds**
- `_fetch_tasks_for_config` filtered on `tasks.location_id`, a field tasks
  never carry (visibility is decided by the BOARD), so campus-scoped share
  links always returned zero tasks even with "include tasks" on.
- Extracted `resolve_allowed_board_ids(user, restrict_to_locations)` in
  `routers/tasks.py` (now the single source of truth, used by `/api/tasks`
  AND the feeds). `mine` scope `$or` widened with `assignee_id`/`reporter_id`;
  `due_date` now requires `$type: string` (null was slipping through).
- Verified: task appears in `/api/public/calendar/user/{token}` JSON and in
  the `.ics` as a `CATEGORIES:TASK` VEVENT; private boards stay hidden.

**4. NEW — public holiday pay policies (admin-set, payroll-wired)**
- `routers/holidays.py`: `holiday_policies` collection keyed by
  `COUNTRY:slug(name)` so a choice sticks for every future occurrence while
  dates keep auto-computing. Kinds: `paid`, `optional_paid`, `unpaid`
  (default), `hidden`. `GET /api/holidays` merges policy + hides `hidden`;
  `GET/PUT /api/holidays/policies`, `DELETE /api/holidays/policies/{key}`
  (admin only). `observed_holidays(start,end)` dedupes by date (paid wins).
- `routers/hr.py`: `_period_bounds()`, `_worked_dates()`, `_holiday_credit()`
  wired into `_generate_payslips_for` + `/api/hr/payslips/preview`.
  • hourly → `holiday_hours` (per-staff, default 8) credited on a PAID
    holiday even when worked, so worked hours stack; optional-paid credits
    only when NOT worked.
  • daily → +1 day for a paid holiday whether worked or not (working it =
    double pay); optional-paid only when not worked.
  • salary/weekly/biweekly → untouched.
  Credit is persisted as `payslip.holiday_credit` and appended to
  `wage_details` ("— incl. holiday credit 8h (1 holiday(s))").
- UI: `components/HolidayPolicyDialog.jsx` (click any holiday on the
  Calendar), `salary-holiday-hours` field in the HR salary dialog,
  amber holiday markers + explainer in the Portal weekly timesheet grid,
  holiday credit line on portal payslip rows.

**5. NEW — venue-first event location picker**
- `components/EventVenuePicker.jsx` used by create + edit: grouped select of
  **Our venues** (campus, restricted campuses excluded), **External venues
  used before**, then "+ Add a new venue…" (inline create, saved for reuse)
  and a "One-off — just type the place" fallback. Selecting a venue sets
  `venue_id` + `location` + `location_id` on the event.
- `GET /api/venues` is now scoped: campus venues limited to locations the
  caller can see (was returning every venue in the DB); external/off-site
  venues stay shared. `visible_locations(user)` extracted in
  `routers/locations.py` and reused.

**6. Fixes found along the way**
- HR → Timesheets "Punches" button referenced undefined `setPunchTs` →
  crashed the tab. Added the state + `ts-punches-dialog`.
- PortalProfile payslip row had a `<Badge>` (div) inside a `<p>` → HTML
  nesting console error. Now a `<div>`.

**Tests** — `backend/tests/test_iter316_holiday_events_tasks.py`: 16/16 pass
(`/app/test_reports/iteration_101.json`). Venue picker + edit hydration
verified via Playwright at 1920px and 390px (no overflow).

## iter 317 — 2026-06 — Full-app wiring audit + 2 fixes

**Audit performed** (evidence, not assertion)
- ESLint across all 76 pages + components: **0 errors** (391 style warnings).
- `python -m compileall` on all 64 routers: clean. Current boot logs
  "All modular routers loaded" with no warning.
- Route table introspected: **978 routes, 0 duplicate (method,path)
  registrations, 0 literal routes shadowed by a dynamic one**.
- ~50 live endpoint calls across every module: all 200 (the 404/405/422s in
  the first sweep were wrong guesses at paths, re-verified against `api.js`).
- All 23 main routes loaded in a real browser session: none blank, no
  React/pageerror exceptions.

**Found + fixed**
1. Dashboard money cards called `GET /api/financial/summary`, which does not
   exist → silent 404 (swallowed by `Promise.allSettled`). Repointed
   `financialApi.summary` to the real `/api/reports/summary` and passed
   month-to-date `date_from`/`date_to` + `location_id`.
2. Those same cards were gated on `selectedCampus !== 'all'`, but
   `setSelectedCampus` was **never called** anywhere — the campus picker had
   been removed at some point, so the gate was permanently false and the
   Donations / Expenses / Net cards had never rendered for anyone. Gate is now
   `hasDirectorAccess(user)` (keeps figures away from non-finance staff, since
   `/reports/summary` has no role guard of its own). Removed the dead
   `campuses` / `selectedCampus` / `campusName` state.
   Verified live: UGX 110,000 / 75,000 / 35,000 now render, 0 failed requests.

**Found, NOT fixed — needs a decision (P0 for multi-user use)**
- `RateLimitMiddleware(requests_per_minute=120)` keys the bucket on
  `scope["client"]`, which behind the K8s ingress is the **proxy pod IP**
  (observed: only `10.79.142.2` / `10.79.142.5` ever reach the app). So the
  120/min ceiling is effectively **shared by every user of the platform**, and
  `X-Forwarded-For` is ignored. A single page load fires 15–25 API calls, so a
  few staff browsing at once exhaust it; the UI then renders empty panels
  silently (429s are swallowed by `catch`/`allSettled`). Reproduced: 200
  sequential requests → 196×200 + 4×429, and a browser session collided with
  the same bucket.
  Recommended: key on authenticated `user.id` (fall back to the left-most
  `X-Forwarded-For` hop for anonymous traffic) and raise the authenticated
  ceiling; keep a tight per-IP limit on public/unauthenticated routes only.

**Docs**
- `/app/memory/ARCHITECTURE.md` — stack, request path, tenancy model,
  module→router→page→collection map, background jobs, integrations.
- `/app/memory/USER_REQUESTS.md` — every user request compiled from all
  handoffs, grouped by module, with removed/out-of-scope sections.

## iter 318 — 2026-06 — Rate limiter: per-user buckets (P0 from the iter317 audit)

`server.py::RateLimitMiddleware` rewritten (still pure ASGI).

**Before** — one bucket keyed on `scope["client"]`, which behind the K8s
ingress + Cloudflare is always the proxy pod IP → all users of the platform
shared a single 120 req/min ceiling.

**Now**
- Authenticated → own bucket keyed on the JWT `sub`. Signature IS verified
  (`jose.jwt.decode`, `verify_exp: False`) so a forged token can't mint itself
  a private bucket; expiry is ignored here because the endpoint's own
  dependency is what rejects expired tokens. Never raises, never leaks auth
  state from the limiter. Default **600/min**.
- Anonymous → bucket keyed on the real client IP: `CF-Connecting-IP` →
  left-most `X-Forwarded-For` hop → socket. Default **120/min**.
- `/api/auth/login|register|forgot-password|reset-password|verify-2fa` → tight
  per-IP bucket, default **20/min**, on top of the existing `login_attempts`
  brute-force lockout in `routers/auth.py` (which is untouched and remains the
  real protection).
- Exempt: websocket upgrades, CORS preflight `OPTIONS`, `/health`, `/readyz`.
- 429 now carries `Retry-After` + `RateLimit-Limit/Remaining/Reset` and a
  message stating the limit and the wait. (Cloudflare strips the RateLimit-*
  headers at the edge; verified present at origin.)
- Cold buckets pruned every 60s — the old dict grew unbounded (slow leak).
- Tunable via env without a code change: `RATE_LIMIT_AUTHENTICATED_PER_MIN`,
  `RATE_LIMIT_ANONYMOUS_PER_MIN`, `RATE_LIMIT_AUTH_ROUTES_PER_MIN`.

**Verified live**
- User A: 300 consecutive requests → 300×200.
- User B immediately after, same source IP → 40×200 (separate bucket).
- Auth-route burst of 32 parallel logins (bogus account) → 14×401 then 18×429.
- Authenticated request straight after that auth bucket was exhausted → 200
  (proves the buckets don't bleed into each other).
- Forged-signature token → no private bucket, endpoint returns 401.
- Browser sweep of 25 page loads: **0 × 429, 0 other failures** (the same
  sweep before the fix produced 237 console errors, nearly all 429s).

**Still open / discussed, NOT built**: dashboard campus flip (see ROADMAP).

## iter 318b — 2026-06 — Holiday policy screen + dashboard follows the sidebar switcher

**1. HR → Holidays tab (`components/HolidayPolicyPanel.jsx`)**
One screen listing every public holiday and how payroll treats it. Year picker
(prev/current/+2), country filter (All / US federal / Uganda public), four
summary cards each spelling out the payroll effect, and a per-row select of
Paid holiday / Optional paid day off / Unpaid day off / Not observed. Hidden
("not observed") holidays still show HERE (`include_hidden=true`) so an admin
can restore them, while staying off the calendar. Read-only for non-admins.
The per-holiday dialog on the Calendar now links across to this screen.

**2. Dashboard follows the sidebar campus switcher (user's choice)**
No dashboard-level campus dropdown — deliberately dropped. `get_campus_filter`
already honours `active_campus_id`, and the switcher reloads the page, so the
dashboard simply inherits the scope. Added a `dashboard-scope` badge naming the
current campus so the numbers' scope is explicit, and removed the dead
`campuses`/`selectedCampus`/`campusName` state left from the old picker.

**3. Fix — payslip "cash account to pay from" picker was always empty**
`HRPage` fetched `/financial/chart-accounts`, which doesn't exist (the router
was dropped in the iter246 finance reset). Payroll therefore could never choose
which account a payslip is paid from. Repointed to
`/finance/chart-of-accounts`, filtered to `is_cash`, labelled `code · name`.
`chartAccountsApi.list` (used by ProductsPage) repointed too.

**4. Fix — remaining `<Badge>` inside `<p>` in PortalProfile** (2 more spots;
timesheet + PTO rows) → hydration warning gone.

**Verified** — `/app/test_reports/iteration_102.json`: backend 11/11 pytest,
frontend 9/10 flows (the payslip picker couldn't be driven through the UI
because the tenant has 0 payslips; the endpoint returns the 3 expected cash
accounts). Critically confirmed through the UI: setting 2026 Thanksgiving to
Paid also reads Paid in 2027 and 2028. Test artefacts (policies + a test staff
user) cleaned out.

---

### AUDIT FINDING — 13 dead endpoint paths still called by live UI
An `api.js`-vs-route-table diff (71 of 627 declared paths are dead; 13 of them
are reachable from real screens). All are leftovers of the **iter246 finance
reset**, which deliberately dropped the old `invoices` / `statements` /
`accounting` / `chart_accounts` routers but left the frontend calling them.
Reported to the user; NOT fixed without direction.

| Broken feature | Screen | Calls | Real route (where one exists) |
|---|---|---|---|
| Invoices tab (list/create/update/delete/convert) | Products/Sales page | `/api/invoices*` | none — router intentionally dropped |
| POS store settings (read + write) | KioskPage, ProductsPage, PosKioskSetupPage | `/api/store-settings/{loc}` | none |
| Member document download | MembersPage | `/api/documents/{id}/download` | `/api/documents/{doc_id}/file` |
| Member document archive | MembersPage | `PUT /api/documents/{id}/archive` | `DELETE /api/documents/{doc_id}` |
| Member bulk CSV export | MembersPage | `/api/members/bulk-export` | `/api/admin/members/bulk-export` |
| Campus detail report | CampusReportsPage (routed + in nav) | `/api/reports/campus/{loc}` | none |
| Public product list + order | PublicBookingsPage | `/api/public/products`, `/api/public/orders` | none |

Four are one-line repoints; three (invoices, store-settings, campus report)
need a backend or the UI removing.

## iter 319 — 2026-06 — Reconnecting the dead endpoints (user-directed)

The iter246 finance reset dropped several routers but left the frontend
calling them. Answer to the user's question: **yes, the code already existed —
it just had no HTTP surface.** Nothing was rebuilt from scratch.

**1. Three one-line repoints (`services/api.js`) — user said "fix all three"**
- `membersApi.downloadDocument` → `/documents/{id}/file` (was `/download`)
- `membersApi.archiveDocument` → `DELETE /documents/{id}` (was `PUT …/archive`;
  the DELETE handler soft-marks `is_deleted`, which is what "archive" means here)
- `membersApi.bulkExport` → `/admin/members/bulk-export` (was `/members/…`)
  Verified: both document routes now answer with the app's own 404
  ("File not found") rather than FastAPI's route-missing 404; bulk-export → 200.
  Note: the tenant has 0 uploaded documents, so download/archive were verified
  at route level only.

**2. POS store settings — reconnected (`routers/store_settings.py`, NEW)**
The handlers were sitting inside the dead `routers/financial.py`. Lifted the
three of them (`GET /store-settings`, `GET/PUT /store-settings/{location_id}`)
into their own router and registered it. Nothing touches the ledger — it's shop
config (receipt layout, payment methods, tax rate, till/bank/momo account).
Defaults are merged OVER stored docs so locations saved before a key existed
still return the full schema. Verified: GET returns the schema, PUT persists,
Kiosk / Sales / POS-Setup pages load with zero failures.

**3. Invoices — router re-registered AND reworked so it can't fork the ledger**
`routers/invoices.py` (518 lines: invoice CRUD, convert-to-sale, accounts
receivable, payment promises/reminders, public quote lookup + acceptance) was
excluded in iter246. Re-registering it as-is would have been dangerous: its
`convert` wrote straight into `db.sales`, bypassing the POS path's
`_auto_post_sale_journal_entry`, so invoice-born sales would never have hit the
balanced ledger — exactly the double-truth the finance reset existed to kill.
Fixed by running the SAME side-effects as the POS path after the insert:
`_ensure_customer_account` + `_auto_post_sale_journal_entry` (which only posts
when the sale is settled and is idempotent by sale id).
Verified end to end: invoice for 10,000 → convert → sale marked paid, customer
account auto-created, and a balanced JE appeared (1010 Dr 10,000 / 4100 Cr
10,000, "Sale — invoice INV-20260909-0001"). All test data removed afterwards.
Also brought back to life by this registration: `/api/accounts-receivable`
(+ payment promises) and the public `/quote/:quoteNumber/accept` page, both of
which had live UI hitting nothing.

**Still undecided by the user (left dead, listed in ROADMAP)**
- `CampusReportsPage` → `/api/reports/campus/{loc}` never existed
- `PublicBookingsPage` product list + ordering → `/api/public/products`,
  `/api/public/orders` never existed

**Testing note for future agents**: `ProductsPage` is mounted at **`/sales`**,
not `/products`. App.js's catch-all sends unknown paths to `/login`, so a wrong
URL guess looks exactly like a session/auth bug. Wasted a cycle on that here.
