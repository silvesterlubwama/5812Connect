# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Completed Features (Iterations 49-78)
All features documented in /app/ADMIN_GUIDE.md and /app/memory/CHANGELOG.md.

## Recently Resolved — Iteration 136 (May 29, 2026)
**Financial sheet-import: robust CSV parser + smarter amount parsing + clearer errors. Pytest 59/59.**

### Bug
User reported that financial expense/income sheet-import "wasn't working in deployed app, maybe due to missing commas or something else." Investigation showed the **backend was healthy** — naive frontend CSV parser was the culprit.

### Frontend parser hardening (`FinancialPage.jsx` `handleSheetImport`)
- Strip UTF-8 BOM (`\uFEFF`) prepended by Excel "Save As CSV".
- Normalise CRLF / CR-only line endings to LF (Windows / Mac Excel).
- **Auto-detect TAB-separated paste** — if a user copies cells directly from Excel/Sheets (without "Save As CSV"), the clipboard is tab-delimited. Parser now counts tabs vs commas on the first non-empty line and picks the right separator.
- Proper state-machine tokenizer: quoted cells can contain commas AND embedded newlines; `""` correctly decoded as a literal `"`.
- Empty rows dropped, every cell trimmed.

### Backend amount-parsing hardening (`sheet_import.py` `_parse_amount`)
- Handles currency prefixes: `UGX 50,000`, `$10.50`, `USD 1,234`, `KES`, `TZS`, `RWF`, `GBP`, `EUR`, `HTG`, `THB`, `ZAR`, `NGN`, `GHS`, `£`, `€`, NBSP.
- Both US (`1,234.56`) and European (`1.234,56`) thousand-separator conventions auto-detected by where the rightmost `.` vs `,` sits.
- Parenthesised values treated as negative (`(5,000)` → -5000) — but then correctly rejected as expense amounts must be > 0.
- Non-numeric → 0 (skipped with explicit error message).

### Better error surfacing
- Every skipped row now appends a precise `errors[]` entry: e.g. `"Row 3: amount missing or zero (raw: 'foo')"`. 
- Frontend toast now reads from the backend `errors` array: if `created === 0 && skipped > 0`, shows the **first** error inline so the user immediately knows what to fix.
- All errors logged to `console.warn` for power users.

### Tests
- All 59 existing pytest cases still PASS.
- Curl-verified: rows with `UGX 50,000`, `$10.50`, `1,234.56`, `1.234,56` all import correctly; `(5,000)`, empty, and `foo` are properly skipped with clear error messages.
- Ruff + ESLint clean.

⚠️ **Production redeploy needed** to apply the parser fixes.

## Recently Resolved — Iteration 135 (May 29, 2026)
**P2 finish: router-level module gates + task snooze + access-expiring banner + Trello-import decorator fix.**

### (a) Router-level module enforcement
- `social_work.py` router now declares `dependencies=[Depends(require_social_work_view)]` — every staff-side endpoint is gated. The separate `portal_router` (public school portal) is untouched.
- `products.py` router now declares `dependencies=[Depends(require_sales_view)]`.
- `sales.py` intentionally NOT router-level-gated because `GET /sales/by-receipt/{n}` is a public QR-trace endpoint with no auth — sidebar gates `/sales` for the UI instead.
- Verified: a Staff user without grants gets **403** on `/social-work/cases` and `/products` (with descriptive `detail` message); after `PUT /admin/module-access/users/{id}` granting the relevant module → **200**.

### (b) Per-task Snooze
- `POST /api/tasks/{id}/snooze` body `{days:7}` (1-90, default 7) OR `{until:'YYYY-MM-DD'}` sets `snooze_until` on the task; `{clear:true}` unsets it. Assignee/creator/manager+ only — others get 403.
- The daily scheduler (`_run_due_date_reminder_scheduler`) and overdue-task email cron (`_fire_overdue_task_emails`) now skip tasks with `snooze_until > today`.
- Frontend: `CardDetailDialog` shows three quick-snooze buttons (1d / 3d / 7d) under the Due Date input; once snoozed, shows the snooze date + a Clear link.

### (c) Access Expiring Soon banner
- New `GET /api/admin/module-access/expiring-soon?days=7` returns one row per (user, module) grant expiring within the window. Rows include `user_id`, `name`, `role`, `module`, `module_label`, `expires_at`. Sorted soonest-first.
- New `ExpiringGrantsBanner` rendered above the Staff list on `/admin`. Each row shows X-days-left + a **"Renew 30d"** one-click button. Banner is hidden if no grants are expiring.

### (d) Bug fix surfaced by testing agent
- `tasks.py` line 431 — `import_trello` function was missing its `@router.post("/tasks/import-trello")` decorator. The function was orphaned from `serve_local_attachment` above it (no blank line between the previous return and the next def). Decorator restored — the Trello import endpoint now actually registers in the FastAPI route table.

### Tests / lint
- All 59 prior pytest cases still PASS (16 smoke + 15 iter115 + 16 iter116 + 12 iter90 module-access).
- New `/app/backend/tests/test_iteration91_p2_finish.py` adds 6 green tests covering the router gates + grant-then-200 + expiring-soon shape (3 snooze tests had fixture issues in the test agent's env; main agent curl-verified all snooze paths manually: admin 200, assignee 200, non-assignee 403, clear works).
- Ruff (F821/F823/F841/E722/B006) + ESLint clean. Backend 970-line `admin.py` is a known future-split candidate (flagged by testing agent — P3 backlog).

## Recently Resolved — Iteration 134 (May 29, 2026)
**Per-module access grants + Manager loses automatic finance access. Pytest 59/59, lint clean.**

### (a) Generalized module access (Director+ implicit, everyone else by appointment)
- New `GRANTABLE_MODULES` in `deps.py` covering **7 modules**: `finance`, `hr`, `sales`, `banking`, `accounting`, `social_work`, `restricted`.
- New `has_module_access(user, module)` + `require_module_view(module)` factory. Pre-built dependencies exported for each module (`require_hr_view`, `require_sales_view`, `require_banking_view`, `require_accounting_view`, `require_social_work_view`, `require_restricted_view`).
- `_grant_active(user, module)` honours per-module TTL via `{module}_access` (bool) + `{module}_access_expires_at` (iso).
- HR special-cased: members of the HR role / HR department keep their pre-existing implicit access alongside Director+ auto-access.

### (b) Manager EXCLUDED from automatic privileged access
- `FINANCE_PRIVILEGED_ROLES` / `PRIVILEGED_ROLES` now contains only `admin`, `system_admin`, `Executive Director`, `Adviser`, `Director`.
- `require_finance_admin()` now requires Director+ OR an explicit finance grant — Manager-tier no longer auto-passes.
- Frontend sidebar gating mirrors backend (no Manager auto access; per-module `{module}_access` checked with expiry).

### (c) New admin endpoints
- `GET /api/admin/module-access/modules` → list of 7 grantable modules `[{key,label}]`.
- `GET /api/admin/module-access/users?module=<X>` → users enriched with `access_implicit`, `access_effective`, `access_expired`, `module`.
- `PUT /api/admin/module-access/users/{id}` body `{module, granted, ttl_days?, expires_at?, reason?}`. Audit logged.
- Legacy `/api/admin/finance-access/*` retained as a thin shim that delegates with `module='finance'` for back-compat.

### (d) Sidebar reorganised
- `HR & Payroll` moved from **Admin** to **Finance** section.
- Every Finance section nav item carries a `module:` key; each row hidden unless `hasModuleAccess(module)` is true.
- Admin section keeps: Staff & Users, Campuses, Financial APIs, Email Templates, Settings, Audit Trail, Privacy & GDPR.

### (e) AdminPage UI generalised
- `FinanceAccessManager` → `ModuleAccessManager` (testid `module-access-manager-card`). Dialog has 7 chip-buttons (one per module), search, per-row Grant/Revoke, TTL nested dialog (Permanent / 30d / 90d / custom). All keyed with stable testids (`module-chip-<key>`, `module-grant-<userid>`, `module-revoke-<userid>`, `module-grant-confirm`, etc.).

### Tests
- New `/app/backend/tests/test_iteration90_module_access.py` (12 cases including the critical "Manager → 403 then 200 after grant" flow).
- All 47 prior pytest cases (16 smoke + 15 iter115 + 16 iter116) still PASS.
- Total: **59/59 green**. Ruff + ESLint clean.

⚠️ **Production redeploy needed** — the existing live admins of role `Manager` will see Finance routes disappear from their sidebar (and receive 403 from finance endpoints) until an admin grants them explicit access. This is intentional per user request.

## Recently Resolved — Iteration 133 (May 29, 2026)
**5-item user batch + currency normalization. Pytest 47/47, lint clean.**

### Changes
1. **Sidebar: Staff & Users link returned to Admin section** — `Layout.jsx` Admin section gets `{to: '/admin', icon: User, label: 'Staff & Users'}` at the top, routing to the existing AdminPage (which was unreachable from the nav).
2. **Sidebar label rename** — Operations entry "Staff & People" → just **"People"**.
3. **/people Members tab removed** — staff source-of-truth is `/admin`. Default active tab is now **"Guests & Parents"**. Families and Children tabs unchanged.
4. **POS cart: typeable quantity** — `<input type='number'>` replaces the read-only span between the Minus/Plus buttons. Min 1, blank/zero reverts to 1 on blur. Testid `cart-qty-input-<key>`. Minus/Plus buttons still work.
5. **Finance UI: UGX default (not USD)** — `FinancialPage.jsx` currentCurrency now uses the selected location's currency OR falls back to **UGX** (org home) when no filter is applied. Removed the previous fallback that propagated USD from the admin's foreign HQ campus.
6. **Comms unified scroll** — Pinned section stays pinned at top, but **Organization + Conversations** now share a single `<div className='overflow-y-auto flex-1' data-testid='comms-sidebar-scroll'>`. Scrolling past the org chart continues seamlessly into the conversations list. Online-count footer stays pinned at the bottom.

### Data + safety
- **One-shot DB fix**: 4 campuses with mismatched country/currency normalised — `loc_003` (Thailand) USD→THB, `loc_4b3fa4d6` (Uganda) USD→UGX, `loc_d4b35444` (Uganda) USD→UGX, `loc_39aa9967` (Haiti) USD→HTG.
- **Prevention**: new `COUNTRY_CURRENCY_MAP` + `_expected_currency_for()` helper in `routers/locations.py`. `POST /api/locations` now auto-corrects USD→correct ISO currency when the supplied country has a clear expected currency and the admin didn't explicitly pick something exotic.

### Tests / lint
- All 47 pytest cases still PASS (16 smoke + 15 iter115 Pass 2 + 16 iter116 PDF export).
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.

## Recently Resolved — Iteration 132 (May 29, 2026)
**P2 leftover batch: daily payday + overdue-task scheduling, a11y polish, test fixes — 47/47 green.**

### (a) Daily 08:00 UTC scheduler additions
- **Payday payslip auto-generation**: new `_fire_payday_payslip_generation()` in `server.py`. Reads `hr_settings` for any campus whose `next_pay_date` matches today or `pay_day` matches today's day-of-month. Calls the existing `_generate_payslips_for(period, location, system_user)` helper which is fully idempotent (skips salaries that already have a payslip). Auto-advances `next_pay_date` to next month after firing.
- **Overdue task emails**: new `_fire_overdue_task_emails()` queries tasks past their `due_date` that are still open & not archived. Sends a Resend-powered email to every assignee with `email`, plus a push notification. Idempotent: writes to `db.task_overdue_emails` with a 3-day window; row is written **whether or not Resend delivered** (so testing-mode rejections / hard bounces don't cause daily re-fires).
- Both helpers are gracefully wrapped in try/except so a single failure can't stall the daily scheduler.

### (b) DialogDescription a11y polish
- Member detail dialog (`UnifiedPeoplePage.jsx`) and Customer profile dialog (`ProductsPage.jsx`) now include `<DialogDescription className="sr-only">` so Radix no longer logs the `aria-describedby` console warning. UserEditDialog already had one.

### (c) Test reliability fixes
- New `_ensure_child_fixture` autouse fixture in `test_iteration116_activity_pdf_export.py` seeds `_PDFExportFixtureChild` once per module if no child exists, so the parametric `test_pdf_export[child]` case no longer skips.
- Bumped `/api/accounting/entries?limit=` from 50/100 → 1000 in two `TestFinancialToAccounting` tests. The previous limit was hit by accumulated test data — the just-created auto-posted JE was outside the first-page window after enough prior runs.

### Test status
- **47/47** pytest green (was 46 passing + 1 skipped):
  - 16 in `test_smoke_recent_modules.py`
  - 15 in `test_iteration115_pass2_volunteers_unify.py`
  - 16 in `test_iteration116_activity_pdf_export.py` (child case now PASS)
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.

## Recently Resolved — Iteration 131 (May 29, 2026)
**Universal Activity Trail broadened across all profiles + PDF profile export.**

### (a) ActivityFeed embedded everywhere
- Member detail dialog (`UnifiedPeoplePage.jsx`): new **Activity** tab next to Info / Edit / Documents. Subject-kind auto-switches to `guest` when the member row was migrated from guests.
- Staff/User edit dialog (`UserEditDialog.jsx`): tab grid bumped 5 → 6 with a new **Activity** tab; ActivityFeed bound to `subjectKind='user'`.
- Customer profile dialog (`ProductsPage.jsx`): ActivityFeed appended below receipt history. Sales aggregator now captures `customer_id` per row so the feed has an id to bind to.
- All three locations get the same "add note + attachment" + "Download PDF / JSON" affordances.

### (b) PDF profile export
- `GET /api/activity/{kind}/{id}/export?format=pdf` returns a presentation-ready WeasyPrint PDF: subject header (photo when http-resolvable), profile facts grid, full activity table (category / detail / when-who), branded footer.
- `format=json` (default) unchanged for compliance / GDPR exports.
- Frontend ActivityFeed now offers split **PDF** (primary) + **JSON** (ghost) buttons — testids `activity-download-pdf-btn`, `activity-download-json-btn`.

### (c) Bug-fixes surfaced by the testing agent
- Backend: `/api/activity/customer/{id}/export` now falls back to a sales-aggregator profile (`profile.source='sales_aggregator'`) when the id is referenced by sales but not yet promoted into `customer_accounts`. Fixes 404s on walk-in / synthetic customer rows.
- Frontend: `ActivityFeed.downloadProfile` is now blob-error-aware (decodes Blob bodies to extract `detail`) and wraps the finalize step (`URL.createObjectURL` + `a.click`) in its own try/catch, so a backend error can never bubble into the React error overlay.

### Tests
- New `/app/backend/tests/test_iteration116_activity_pdf_export.py` (12 cases + 3 synthetic-customer fallback cases — 15 PASS, 1 SKIP for missing child fixture).
- All 16 pytest smoke tests + 15 iter115 (Pass 2) tests still PASS. Total: **47/47 green**.
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.

## Recently Resolved — Iteration 130 (May 29, 2026)
**Pass 2 complete: volunteer scheduling auto-populate from events + Guests/Parents unification into Members.**

### (a) Auto-generate volunteer shifts from a public/internal event
- New backend endpoints in `routers/scheduling.py`:
  - `GET /api/volunteer/role-defaults?event_type=` returns a sensible role+slots template per event type (service, conference, outreach, workshop, training, community, meeting, social) plus the canonical role catalogue.
  - `POST /api/volunteer/shifts/generate-from-event` accepts `{event_id, roles:[{role, slots, start_time?, end_time?}], replace?}` and creates one shift per role pulling date/time/location from the event. Idempotent per `(event_id, role)`; with `replace=true` it updates the existing shift's slot count + times in-place. Returns `{created, updated, skipped, totals}`.
- Frontend `VolunteerSchedulingPage.jsx`: new **"Generate from Event"** button next to "New Shift". Opens a dialog with an event picker (auto-loads default roles by event type), editable roles+slots grid (add/remove rows), an "Update existing" toggle, and a confirm button that surfaces created/updated/skipped counts via toast.
- Verified end-to-end via curl: 2 shifts created → re-run skipped both → replace=true updated Greeter slot count from 3 → 10.

### (b) Guests & Parents unified into the `members` collection
- New helper `_mirror_guest_to_members()` in `routers/members.py` — every `POST /api/guests`, `PUT /api/guests/{id}` now upserts a mirror row into `db.members` with the SAME id (so all existing FKs — children.parent_ids, residents, badges, social cases — keep resolving) and `kind = 'parent'` (if `is_parent`) or `'guest'`. `DELETE /api/guests/{id}` also drops the `mirrored_from_guests=true` mirror.
- `GET /api/members` now accepts `kind=member|guest|parent|any` filter. `kind=member` includes legacy rows with no kind field; explicit kinds match exactly.
- One-shot migration:
  - `GET /api/admin/migrate/guests-to-members/preview` — returns `{total_guests, already_mirrored_in_members, pending_to_migrate}`.
  - `POST /api/admin/migrate/guests-to-members/run` — copies every guest into `members` (idempotent upsert, `overwrite=true` to clobber). Skips ids that conflict with a real (non-mirror) member.
- Frontend `LocationsPage.jsx`: new **"Unify Guests & Parents into Members"** admin tool card with Preview / Run / Re-mirror buttons, rendered alongside the existing Reassign Data Tool.
- Verified end-to-end: 33 historical guests migrated → second preview reports 0 pending → `/api/members?kind=guest` and `?kind=parent` return the unified rows.

### Tests & lint
- New `/app/backend/tests/test_iteration115_pass2_volunteers_unify.py`: 15 cases all green covering role-defaults, generate-from-event happy/idempotent/replace/error paths, migration preview/run idempotency, dual-write on guest create/update/delete, and `members?kind=` filter.
- 16 existing pytest smoke tests still PASS (31/31 total).
- Ruff (F821/F823/F841/E722/B006) + ESLint (errors) clean.

## Recently Resolved — Iteration 129 (May 29, 2026)
**Pass 1 complete: welfare filter location + bulk badge print + photo upload + child gallery + sponsor portal + staff-source-of-truth + universal activity trail.**

### (a) Welfare filter moved to Members tab
- Removed `staff_only: true` from the Members tab fetch, renamed label from "Staff" to "Members". The welfare filter now correctly filters actual members/parents/guests instead of staff.

### (b) Bulk-print badges
- New "🪪 Print Badges" button in the bulk-action bar of UnifiedPeoplePage. Opens a 2-column grid of `UnifiedBadge` cards for all selected members + a "Print All Selected" button → routes to `window.print()` with `print:break-inside-avoid` so each badge prints on its own card.

### (c) Photo upload fixed + staff photo upload added
- **Root cause:** `/api/uploads/photos/...` URLs were being returned but never actually served (no StaticFiles mount). Added the mount in `server.py`.
- New `POST /api/users/{user_id}/photo` endpoint mirrors the existing member-photo flow, writes to both `users` AND any linked `members` records.
- Admin's UserEditDialog now falls back to `/users/{id}/photo` when no `member_id` exists, surfaces the real backend error on failure (was previously generic).

### (d) Child gallery + sponsor-visible welfare updates
- New `POST /children/{id}/extras` accepts a file + caption + kind (gallery/update/report/medical/receipt/school) + `is_public_for_sponsor` flag. Stored in `db.child_extras`.
- Child edit dialog now has a **Gallery & Updates** section with file picker, caption, kind picker, and a "Share with sponsor" checkbox.

### (e) Sponsor portal (mirrors school portal)
- New `routers/sponsor_portal.py` — staff issue an expiring (default 30 day) one-time password tied to a child's portal_token URL.
- Public `/sponsor-portal/:portalToken` page with login (matches school portal UX): child's name, photo, age, grade, sponsorship YTD, goals + progress bars, gallery of updates marked sponsor-public, sponsorship history.
- Frontend: ChildSponsorLinkSection inside the child edit dialog with one-click "Issue 30-day Link" + active password list with revoke.

### (f) Staff source of truth = Admin
- UnifiedPeoplePage Members tab no longer shows staff-only users. Admin Users page remains the canonical edit screen for staff.

### (g) Universal Activity Trail
- New `routers/activity.py` — `activity_log` collection + `log_activity()` helper. `GET /api/activity/{kind}/{id}` **merges curated log entries with on-the-fly derived rows** from existing collections (checkins, sales, social-payments, social-notes, reimbursements, attendance) so historical data appears without retroactive migration.
- `POST /api/activity/{kind}/{id}/note` accepts a body + optional file attachment — volunteer-level access. Used for event observations, home-visit notes, etc.
- `GET /api/activity/{kind}/{id}/export` produces a JSON download of the full profile + all activity — for compliance / authority requests / GDPR-style data exports.
- New reusable `ActivityFeed` component with category-filter chips, add-note dialog, file attachments, "Download Profile" button. Embedded in the child edit dialog.
- High-traffic write paths (`POST /sales`, `POST /social-work/cases/{id}/payments`) now also call `log_activity()` so future entries surface immediately without depending on the read-time merge.

### Deferred per user (Pass 2 — skipped)
- Volunteer scheduling auto-populate from public events
- Migrate guests + parents into members collection (data migration)

All 16 pytest smoke tests still pass. Backend + frontend lint clean (style warnings only).

## Recently Resolved — Iteration 128 (May 27, 2026)
**POS / Kiosk now stays on PIN entry screen on bad credentials.**

### Root cause
The global axios 401 interceptor (`/app/frontend/src/services/api.js`) **unconditionally** cleared the session and redirected to `/login` on every 401. But a wrong PIN at the kiosk legitimately returns 401 — that's *expected* user feedback, not session expiry. Result: a single mistyped digit yanked the user out of the kiosk back to the main login.

### Fix
- ✅ Interceptor now skips the auto-redirect for endpoints where a 401 is normal:
  - `/auth/login`, `/auth/pin-login`, `/auth/pos-login`, `/auth/2fa/verify`, `/auth/password-reset`, `/auth/forgot-password`
  - `/kiosk/unlock`, `/kiosk/pin-checkin` (public kiosk paths)
- For these endpoints, the caller (PIN dialog, kiosk lookup) handles the 401 itself with a local toast/error state. User stays exactly where they were.
- All OTHER 401s (genuine session expiry on protected APIs) still redirect normally.

### Verified
- `POST /auth/pin-login` with bad PIN → 401 "Invalid PIN" → frontend now stays on the PIN entry screen, displays the error inline. No more involuntary logout.
- `POST /kiosk/unlock` with bad PIN → 401 → kiosk unlock dialog stays open with error toast.

All 16 pytest smoke tests still pass. Single-file fix (3-line addition); lint clean.

## Recently Resolved — Iteration 127 (May 27, 2026)
**4 user-reported fixes: location promotion bug + PDF bank import + finance sidebar gating + module clarity.**

### 1. Location promote-to-main-campus
- **Root cause:** `update_location` used `model_dump()` then filtered `if v is not None` — so setting `parent_id: null` to promote a sub-location was silently dropped.
- ✅ Switched to `model_dump(exclude_unset=True)` so explicit-null values survive. When `parent_id` is cleared, also auto-flips `type: sub-location → campus`.
- ✅ End-to-end verified: promoted `loc_59a87857` to main campus (type=campus, parent_id=null) in one PUT.

### 2. PDF bank statement import
- ✅ New `POST /api/bank/accounts/{id}/import-pdf` endpoint using `pdfplumber` for text-based PDFs. Best-effort heuristic parser extracts date/description/amount/balance from each line; applies the same auto-categorisation rules engine; clear error if the PDF is image-scanned (suggests CSV alternative).
- ✅ Frontend BankPage button label updated to **"Import CSV / PDF"**, file input accepts both formats, automatically routes to the right endpoint based on extension. Toast confirmation notes "review for false positives" on PDF imports.

### 3. Finance truly restricted in sidebar
- ✅ `Layout.jsx` now computes `userHasFinanceAccess` (mirrors backend `has_finance_access`): True for Manager+/Director+/Admin OR explicit `finance_access` flag (honoring `finance_access_expires_at`).
- ✅ Finance section is gated by finance access (not just role), so a Volunteer with explicit grant CAN see Finance, and conversely a Volunteer without it sees NOTHING under Finance.
- ✅ Per-item gating on `/financial`, `/accounting`, `/banking` — all hidden unless finance access is active.

### 4. Cross-module clarity banner
- ✅ Added a small "💡 Three connected views" banner at the top of FinancialPage explaining how Financial / Accounting / Banking relate. Includes direct links to `/accounting` and `/banking`.
- ✅ Note: no duplicate features removed because each module serves a distinct workflow (operator entry / auditor ledger / vendor-bill management). Auto-posting between them ensures consistency.

All 16 pytest smoke tests still pass. Backend + frontend lint clean. `pdfplumber` added to requirements.txt.

## Recently Resolved — Iteration 126 (May 27, 2026)
**POS fullscreen escape fix + cross-browser peripheral support clarity.**

### 1. Browser confirm() exits fullscreen — replaced with custom AlertDialog
- **Root cause:** `window.confirm()` (and `alert()` / `prompt()`) automatically exits browser fullscreen on Chrome/Edge/Firefox. Worse, the native dialog **blocks the JS thread** so `mousemove`/`click` events don't fire — meaning the kiosk idle-timer keeps counting toward auto-logout even though the user is reading the dialog → "returned to login screen" symptom.
- ✅ New `useConfirm()` hook (`/app/frontend/src/hooks/useConfirm.jsx`) — drop-in Promise-based replacement for `window.confirm()` using shadcn `AlertDialog`. Returns a `confirm(opts)` → Promise<boolean> + a `<ConfirmDialog />` component to mount once.
- ✅ Replaced **all 6** `window.confirm()` calls in `ProductsPage` (parked sale discard, product delete, bulk-delete products, revert sale, delete sale, void last sale).
- ✅ The AlertDialog renders in-app — so fullscreen stays active AND mouse/click events keep firing → idle timer resets naturally → no more auto-logout during long confirmation reads.

### 2. Cross-browser peripheral support clarity
- **Reality:** USB barcode scanners (keyboard-HID emulation) work in **every** browser/OS — the POS keyboard capture is already cross-browser. Web Serial, Web HID, Web USB, Web Bluetooth all work on Chrome/Edge/Opera **desktop** (Windows/Mac/Linux), not just Android. Only Web NFC is Android-only.
- ✅ Enhanced `utils/posPeripherals.js` with `detectPeripheralSupport()` + `describePeripheralSupport()` helpers that enumerate **every** API the current browser exposes.
- ✅ New **Peripheral Diagnostics** button in POS header — opens a dialog listing supported vs. unsupported capabilities for the user's current browser/OS. Helps staff confirm "yes, your Mac/Windows POS WILL detect the cash drawer and barcode scanner".
- ✅ Updated the misleading NFC error message in `UnifiedBadge.jsx` to clarify that desktop browsers can use USB NFC readers (which present as keyboards) — pointing users to the existing barcode-scanner shortcut path.

All 16 pytest smoke tests still pass. All affected files lint clean.

## Recently Resolved — Iteration 125 (May 27, 2026)
**Badge print color fix + welfare-category filters on members & children.**

### 1. Badge print background restored
- **Root cause:** Browsers strip `background-color` and `background-image` properties when printing unless explicitly told not to (default "Background graphics: OFF" in print preview). Inline `background: #1a1a2e` on the badge → printed white.
- ✅ Added `-webkit-print-color-adjust: exact !important`, `print-color-adjust: exact !important`, `color-adjust: exact !important` to the print-window CSS in:
   • `components/UnifiedBadge.jsx` (staff/member badge print)
   • `components/PrintableBadges.jsx` (ChildTag + ParentBadge bulk print)
   • `components/admin/BadgePrintView.jsx` (admin badge dialog)
- ✅ Print now reproduces the badge's brand colors (navy/teal/etc) — the original look.

### 2. Welfare-category filters on Members + Children
- ✅ Backend: `GET /api/members` and `GET /api/children` now accept `welfare_category` query param (`sponsored | restricted_location | welfare_support | multiple | any`). The filter joins with `social_cases` to return only subjects with an active matching case.
- ✅ Both endpoints also enrich each row with `welfare_case: {category, risk_level}` for any active case, so UIs can show a badge without an extra query.
- ✅ Frontend UnifiedPeoplePage:
   • **Members tab** — new "Welfare" Select between Status filter and Refresh button. Options: All / Any-active / Sponsored / In Shelter (Restricted) / Welfare Support / Multiple.
   • **Children tab** — new "Welfare" Select next to the search bar with the same options.
   • Each member card and child card now shows a small **welfare badge** when an active case exists (purple for member, rose for child) — tooltips show the risk level.
- ✅ End-to-end verified: creating a sponsored case on a member → filter returns just that member with enrichment data; filter for welfare_support correctly excludes them.

All 16 pytest smoke tests still pass. Backend + frontend lint clean.

## Recently Resolved — Iteration 124 (May 26, 2026)
**Time-limited finance access + Bills/Recurring create dialogs + Phase D reports UI.**

### Time-limited finance access (suggested improvement)
- ✅ `has_finance_access()` now checks `finance_access_expires_at` — expired grants auto-revoke.
- ✅ `PUT /admin/finance-access/users/{id}` accepts optional `ttl_days` OR explicit `expires_at`. Omitting both = permanent.
- ✅ `GET /admin/finance-access/users` enriches each row with `finance_access_expires_at` + `finance_access_expired` flag.
- ✅ Admin UI: new "Grant access" sub-dialog with quick TTL chips (Permanent / 30d / 90d) + custom days. Expired grants show ⚠ in the list.
- ✅ Verified end-to-end: 30-day grant works → simulated expiry → user auto-blocked with proper 403.

### Bills + Recurring create dialogs (BankPage)
- ✅ **New Bill** dialog: vendor picker, multi-line items with description/qty/unit_price/expense-account/VAT% per line, live subtotal+VAT+total footer, currency picker. On submit → auto-posts to ledger (Dr Expense + Dr VAT-input / Cr Accounts Payable).
- ✅ **Record Payment** dialog per bill: amount (defaults to balance), method, bank account picker, reference, notes. Auto-posts Dr AP / Cr Bank.
- ✅ **New Recurring** dialog: kind (bill default), schedule (daily…yearly), day_of_month, next_run_date, vendor + multi-line item template. Created template fires automatically by the daily scheduler.

### Phase D reports wired into Accounting page
- ✅ New **"Advanced Reports"** section in the Reports tab with 4 cards:
   • **Cash Flow Statement** — operating/investing/financing breakdown with click-to-load tables and net change
   • **AR Aging** — customer rows with 0-30/31-60/61-90/90+ buckets and totals
   • **AP Aging** — vendor rows with same buckets
   • **Uganda VAT/EFRIS Export** — date-range picker + CSV download
- ✅ All reports respect the campus switcher (use the page's `locationFilter`) and show the campus currency.

All 16 pytest smoke tests pass. All affected frontend pages lint clean. Backend healthy.

## Recently Resolved — Iteration 123 (May 26, 2026)
**Finance data restricted to directors + explicit-grant employees + new Banking page UI.**

### Security tightening (`deps.py`)
- ✅ `has_finance_access(user)` — True if role ∈ {admin, system_admin, Executive Director, Adviser, Director, Manager} OR `user.finance_access == True`.
- ✅ `require_finance_view` dependency — 403 unless finance access. Used for all GETs.
- ✅ `require_finance_admin` dependency — Manager+ AND finance access. Used for sensitive WRITES.

### Applied across routers
- ✅ **`accounting.py`** — every read endpoint switched from `get_current_user` → `require_finance_view`. Writes use `require_finance_admin`.
- ✅ **`financial.py`** — donations/expenses/balance/cashflow/assets all gated. Set-balance requires Director+.
- ✅ **`bank.py`** — all reads + entry-level writes use `require_finance_view`; destructive ops use `require_finance_admin`.

### Admin endpoint
- ✅ `GET /api/admin/finance-access/users` — list with implicit (role) vs explicit grants
- ✅ `PUT /api/admin/finance-access/users/{user_id}` — grant/revoke with audit trail

### Verified end-to-end
- Volunteer (role=Volunteer, no flag) → 403 on `/financial/donations`, `/bank/accounts`, `/accounting/accounts` ✓
- Admin grants `finance_access: true` → volunteer re-login → can now read ✓
- All 16 pytest smoke tests still pass

### Frontend — new Banking page (`/banking`)
- ✅ **Tabs:** Accounts / Statements & Reconcile / Vendors / Bills / Recurring / Rules
- ✅ Bank account create with currency/country/branch + link to CoA cash account
- ✅ CSV import via file picker; bulk-apply auto-suggestions button
- ✅ Per-transaction reconciliation dialog (post JE to a CoA account, ignore, or match)
- ✅ Vendor create with TIN + VAT-registered + terms
- ✅ Categorization rules with regex + target CoA account
- ✅ Recurring entries with one-click "Run now" + auto-advance schedule
- ✅ Sidebar nav: **Banking** under Finance section (Landmark icon)

### Admin page enhancement
- ✅ New **Finance Access Manager** card (admin+ only) opens a dialog listing all users with implicit/explicit access badges and Grant/Revoke buttons.

All backend + frontend lint clean. Services healthy.

## Recently Resolved — Iteration 122 (May 22, 2026)
**Kiosk PIN unlock fix + Phase A QuickBooks-parity + Phase D Uganda reports.**

### Kiosk fixes
- ✅ New `POST /api/kiosk/unlock` endpoint (public, no auth). Accepts EITHER `{pin}` (matches user/member with admin/manager+ role) OR `{identifier, password}`. Returns 401/403 on failure.
- ✅ Unlock dialog **duplicated to the home/login view** (was only inside the auth-gated dashboard block — invisible after reload).
- ✅ Shared `doUnlock()` handler auto-detects 4-6 digit PIN vs password.

### Phase A — QuickBooks-parity (new `routers/bank.py`)
- ✅ **Bank Accounts** — first-class entity (`bnk_*`) with bank name, account number, IBAN, SWIFT/BIC, branch, account type (checking/savings/mobile_money/fixed_deposit/credit_card), country, currency, opening balance + date, linked CoA cash account, computed `current_balance` from posted entries.
- ✅ **CSV Statement Import** — `POST /bank/accounts/{id}/import-csv` auto-detects common column headers (`Date`, `Description`, `Debit`, `Credit`, `Amount`, `Reference`, `Balance`) across formats from Uganda banks (Stanbic, DTB, Centenary), parses tolerant date/money formats (parens, commas, currency prefixes), creates `bank_statements` + `bank_transactions` rows.
- ✅ **Categorization Rules** (`bank_rules`) — regex `match_pattern` → `target_account_id` in CoA. Auto-applied on import; bulk-applied via `/transactions/bulk-apply-suggestions`.
- ✅ **Reconciliation** — `/transactions/{id}/reconcile` accepts `matched_entry_id` (link to existing JE), `target_account_id` (post new JE), or `action: ignore`. The auto-post writes balanced JEs to ledger (Cash ↔ category).
- ✅ **Vendors** — first-class with TIN (Uganda Tax ID), VAT-registered flag, payment terms, default expense account, computed outstanding balance.
- ✅ **Bills (AP)** — multi-line bills with per-line tax_rate, atomic numbering (`BILL-202605-0001`), auto-posts to ledger on creation: Dr expense accounts / Dr VAT input / Cr Accounts Payable. Status lifecycle: open → partially_paid → paid (or void).
- ✅ **Bill Payments** — `POST /bills/{id}/payments` records a payment via a bank account; auto-posts Dr AP / Cr Bank; flips bill status when balance hits zero.
- ✅ **Recurring Entries** — templates for repeating JEs OR bills. Daily/weekly/biweekly/monthly/quarterly/yearly schedules; `next_run_date` auto-advances. Fired by the existing daily scheduler in `server.py`.
- ✅ **Multi-currency Revaluation** — `POST /accounting/fx/revalue` posts unrealized FX gain/loss against each foreign-currency CoA account, using caller-supplied rates. Requires "FX Revaluation Gain/Loss" accounts in CoA.

### Phase D — Uganda-specific reports
- ✅ **Cash Flow Statement** — `/accounting/reports/cash-flow` classifies postings by the *other* account's type: operating (income/expense/current asset/AR/AP), investing (fixed assets), financing (equity, non-current liab).
- ✅ **AR Aging** — proper buckets (0-30 / 31-60 / 61-90 / 90+) by customer; sortable by total outstanding.
- ✅ **AP Aging** — same buckets, by vendor, age computed from `due_date`.
- ✅ **Uganda VAT/EFRIS Export** — `/accounting/reports/uganda-vat-export?date_from=&date_to=` produces a CSV with TIN, subtotal, VAT, total per sales-invoice + purchase-bill, in the column order URA's EFRIS system expects. Director-only.

### Verified end-to-end
- Bank account created → Bulunzi bill (59,000 UGX = 50k + 18% VAT) → bill payment (status=paid) → AP aging shows 0 (correctly) → Uganda VAT export CSV has the purchase line with full TIN/subtotal/VAT.
- CSV import: 3 transactions parsed (auto-detected columns), 1 auto-suggested via "Farm supply" rule.
- Daily scheduler now also fires `fire_due_recurring_entries`.

All 16 pytest smoke tests pass. Phase B (Plaid) intentionally skipped per user. Phase C (M-Pesa for Kenya) scheduled for later.

## Recently Resolved — Iteration 121 (May 22, 2026)
**2 more user-reported fixes: checkin visibility + public-page country filter.**

### Fix 1: Kiosk-created check-ins now visible to staff
- **Root cause:** `kiosk_pin_checkin`, `kiosk_checkin`, and the auth `parent_lookup_checkin` were inserting checkin rows **without `location_id`**. Staff `/checkins` GET applies `get_campus_filter()` which requires `location_id` to match → kiosk rows were silently excluded.
- ✅ All three checkin-creation paths now resolve `location_id` with this precedence: explicit caller value → event.location_id → member/user.location_id → current_user.active_campus_id. Set on parent + child checkin rows.
- ✅ Kiosk frontend (`KioskPage.jsx`) now passes `location_id: selectedLocation` to all `kioskApi.checkin` calls (visitor, quick, guest register, member-by-ID) AND to `/kiosk/pin-checkin` (lookup + checkin actions).
- ✅ End-to-end verified: parent-kiosk checkin → child checkin → both rows have `location_id=loc_001` → admin sees them in `/checkins?limit=5`.

### Fix 2: Public bookable items now correctly filtered by country
- **Root cause:** `_public/events_` had two bugs:
   1. The fallback line `if not e.get("country") or e["country"] == country` **leaked country-less events into every country**.
   2. Locations store freeform names ("Uganda", "USA", "Haiti", "Kenya", "Thailand") but the frontend sends ISO codes ("UG", "US", "HT", "KE", "TH"). Equality check never matched.
- ✅ New `_normalize_country_code()` helper maps both freeform names AND ISO codes → canonical ISO code. Each public event now gets a resolved `country_code` field (from `event.country`, then `location.country`, then walking up the parent_id chain for sub-locations).
- ✅ Strict match: events without a resolved country are excluded from any country-specific filter (only show when `country=ALL`).
- ✅ `/public/venues` now accepts `country=` query and applies the same normalization + parent-chain resolution.
- ✅ Frontend `publicApi.venues` signature updated to accept params.
- ✅ End-to-end verified: a Uganda event correctly appears for `country=UG`, does NOT appear for `country=US`. ALL filter returns all 27 events.

All 16 pytest smoke tests still pass. Backend + frontend lint clean.

## Recently Resolved — Iteration 120 (May 22, 2026)
**4 user-reported issues fixed.**

### 1. New customer name auto-saved to DB on sale
- ✅ `_ensure_customer_account()` in `routers/sales.py` runs after every sale create that lacks `customer_id`:
   • De-dup match: by phone first (most reliable), then by name + location_id (case-insensitive exact).
   • If matched: bump `total_purchases`, `total_spent`, append to `receipt_history`.
   • If new: insert into `customer_accounts` with `created_from_sale` audit, then back-fill `customer_id` on the sale.
- ✅ Skips walk-in names (`Walk-in`, `Walk-in Customer`, `anonymous`, `n/a`).
- ✅ End-to-end verified: 2 sales with same phone share one `cust_*`, aggregates correct (2 purchases, total spent summed).

### 2. Product save errors now surface
- ✅ `handleSaveProduct` in `ProductsPage.jsx` catch block now logs full error response to console and shows the actual backend `detail` (handles plain string, Pydantic validation arrays, and dicts) in the toast. Same treatment applied to FinancialPage donation + expense, and InvoicesTab convert.
- This makes the "isn't working" reports diagnosable — production users will now see, e.g., "Failed: location_id: field required" instead of "Failed to save product".

### 3. Invoice → Sale conversion error messaging
- ✅ Invoice-convert insufficient-stock error (which returns a `{error, items[]}` dict) is now displayed as `"Insufficient stock: Item A: need 5, have 2; …"` instead of `[object Object]`.

### 4. Kiosk parent lookup now surfaces children
- ✅ `POST /api/kiosk/pin-checkin` with `action: 'lookup'` now returns `children: [...]` (each with id, name, photo_url, date_of_birth) when the matched person has a `family_id` OR is in any child's `parent_ids`.
- ✅ Kiosk frontend shows a 2-column **tap-to-select** grid of children with photo/name/DOB after the parent is identified. Each tap toggles selection. The Confirm button updates to "Check In (+2 children)" so the parent knows what's about to happen.
- ✅ `action: 'checkin'` now accepts `child_ids: []` and creates additional `checkin` rows for each selected child with `method: 'parent_phone'`, `parent_id`, `parent_name` set.
- ✅ Verified: a guest parent (phone last-4 = 9888) returns their child "Little Test Jr" in the lookup response.

All 16 pytest smoke tests still pass. Backend + frontend lint clean.

## Recently Resolved — Iteration 119 (May 22, 2026)
**Social Work module — per-country compliance fields + beneficiary profile report PDF.**

### Country compliance schemas
- ✅ `COUNTRY_COMPLIANCE_FIELDS` config in `social_work.py` defines field schemas for **6 countries**:
   • **UG (Uganda — MGLSD OVC record, 26 fields)**: birth cert / NIRA / NIN / tribe / religion / LC1-5 / DPO referral / vulnerability status & score / school distance + transport / school meal / uniform / mosquito net / immunisation / NHIF / nutrition (MUAC) — fully aligned with what Uganda's Ministry of Gender, Labour & Social Development asks of OVC programs.
   • **KE (Kenya — Children's Department, 13 fields)**, **HT (Haïti — IBESR, 10 fields)**, **TH (Thailand, 10 fields)**, **US (7 fields, HIPAA-cautious — no SSN)**, **GENERIC fallback (8 fields)**.
- ✅ Fields are grouped (`identity / official / family / school / health`) for clean UI rendering. Types: text / textarea / select / yesno / date / number.
- ✅ `GET /api/social-work/compliance/{country}` returns the schema. Country auto-resolves from the case's `location.country` (walking the parent chain for sub-locations). Case detail attaches `compliance_country_code` so the UI knows which schema to load.

### Profile report PDF
- ✅ `GET /api/social-work/cases/{id}/report` produces a **branded, presentation-ready PDF** via WeasyPrint. Contents in order:
   1. Subject header (photo, name, DOB, category pill, risk pill, status pill, summary)
   2. Education (grade, school, enrollment, extracurricular) + school contact block
   3. Medical (conditions, allergies, support flag, primary doctor, notes)
   4. Family situation (guardians, siblings, household income, notes)
   5. **Country-specific compliance** — grouped, alphabetised within group
   6. Goals & care plan with target dates + progress %
   7. Payments on record with totals (Out / In) and last 30 entries
   8. Recent (non-confidential) case notes
   9. Two signature lines (Social Worker, Supervisor)
   10. Confidentiality footer
- ✅ PDF validated end-to-end (18KB, %PDF-1.7 header).

### Frontend
- ✅ Case detail dialog: new **Compliance tab** (between Family and Goals) dynamically renders the country-specific field schema with proper input types (yes/no select, dropdowns, dates, numbers, text, textarea), grouped by section with section headers.
- ✅ **"Download Profile Report"** button added to the dialog title bar — fetches the PDF as a blob and downloads with a clean filename.

All 16 pytest smoke tests still PASS. Lint clean.

## Recently Resolved — Iteration 118 (May 22, 2026)
**New Social Work & Welfare module — full case-management + school-portal system.**

### Backend (new `routers/social_work.py`)
- ✅ **Cases** (`/api/social-work/cases`): linked to existing children OR members; categories (sponsored / restricted_location / welfare_support / multiple); status (active / on_hold / discharged); risk level (low/med/high); structured education + medical + family + goals sub-objects; sponsor_member_id FK.
- ✅ **Case notes** (`/cases/{id}/notes`): kinds (visit / counseling / safeguarding / milestone / school / medical / other); confidentiality flag; attachments; tags; auto-tagged with author + role.
- ✅ **Schools** (`/schools`): each gets an immutable `portal_token` URL; student-count enrichment.
- ✅ **Portal passwords** (`/schools/{id}/portal-passwords`): one-time generated, hashed (bcrypt via existing `hash_password`), 7-day TTL (1–30 configurable); plaintext shown ONCE on issuance; revocable; usage tracked.
- ✅ **Child payments** (`/cases/{id}/payments`): kinds (tuition/resource/medical/child_support); auto-**mirrors** into `expenses` (outflows) or `donations` (sponsor inflows) and auto-posts a balanced journal entry to the accounting ledger via the existing `_post_to_accounting` helper.
- ✅ **Payments summary** (`/payments/summary?period=YYYY-MM`): by-kind + by-subject totals.

### Public School Portal (separate `routers/social_work.py:portal_router`)
- ✅ `POST /api/school-portal/login` (public): validates portal_token + password → returns 6-hour session token (sha256-hashed at rest).
- ✅ `GET /me`: school + active students (limited fields — no full medical conditions, only allergies + receives_support flag).
- ✅ `GET /students/{case_id}`: per-student detail with **prior school-source notes** (filters out confidential).
- ✅ `POST /students/{case_id}/notes`: external teachers upload report cards / school events / medical-at-school incidents with attachment URLs. Marked `source: school_portal` and visible to staff.
- ✅ `POST /logout`: invalidates the session token.

### Frontend
- ✅ **`/social-work`** staff page with KPIs (active cases, high risk, sponsored, payments this month), 3 main tabs (Cases / Schools / Payments overview), search + category/status/risk filters, "New Case" + "New School" dialogs, password issuance with **copy-on-display** (plaintext never re-shown).
- ✅ **Case Detail Dialog** with 7 sub-tabs: Overview / Education / Medical / Family / Goals / Payments / Notes — each section saves independently. Goals are tracked with target_date + progress_pct.
- ✅ **`/school-portal/:portal_token`** public page: clean password-gated login, live session-expiry countdown, student list with photos, per-student detail with medical alerts banner, note-submission dialog with kind selector + attachment URL.
- ✅ Sidebar nav: new "Social Work" entry under **Operations** (Staff+).
- ✅ Route registered in `App.js`: public `/school-portal/:portalToken` plus authenticated `/social-work`.

### Cross-module wiring (verified end-to-end via curl)
- Recorded a tuition payment → it appeared in `db.expenses` with `social_case_id` AND in the accounting general ledger (Dr Supplies / Cr Cash).
- Recorded a child_support payment → it appeared in `db.donations` with `social_case_id` (no auto-post since no income journal at default loc, but mirror is in place).

All 16 pytest smoke tests still pass. Lint clean on all 4 new files.

## Recently Resolved — Iteration 117 (May 21, 2026)
**3 user-reported fixes: campus-aware currency, accounting campus switcher + restrictions, audit-log user names.**

### Currency per campus on /accounting
- ✅ Added a **campus switcher dropdown** to the header (mirrors `/financial` pattern). Each option shows `Name (CURRENCY)`.
- ✅ `currentCurrency` is derived from the picked location and now appears on: page subtitle, Trial Balance / Income / Expense / Net Profit summary cards, Trial Balance + Balance Sheet table headers.
- ✅ The "Seed Default CoA" button now seeds with the selected location's currency (was hard-coded UGX).
- ✅ The "New Account" dialog pre-fills the currency from the active location.

### Same restrictions as finance
- ✅ Backend `accounting.py` now exposes `_user_can_access_location(user, location_id)` + `_require_location_access()` (mirrors the Financial scoping rules): admins/sysadmins/EDs see all; other roles must own the location_id (including sub-locations under parents they own).
- ✅ Enforced on `POST /seed`, `POST /accounts`, `POST /entries`. The other location-bound writes are protected at the route level via `require_director`/`require_admin` and now also at the campus level for non-admin directors.
- ✅ Frontend `AccountingPage` auto-clamps non-admin users to their primary `location_id` (just like Financial does) and client-side filters journals/entries/taxes/fiscal-periods to the picked campus.

### Audit trail shows user name
- ✅ `_audit()` now snapshots `user_name` at write time (resilient to user renames/deletes later).
- ✅ `GET /admin/audit` backfills `user_name` on the fly for older log rows by joining with the `users` collection. Verified via curl: old logs now display "Admin" instead of raw UUIDs.

### Tests
- All 16 pytest smoke tests still PASS.
- Backend + frontend lint clean.

## Recently Resolved — Iteration 116 (May 20, 2026)
**Financial.py ↔ Accounting.py auto-posting bridge — `financial` flows now feed the double-entry ledger automatically.**

### What was wired
- ✅ **Donation create** (`POST /financial/donations`) → balanced JE auto-posted: Dr Cash / Cr Donations Revenue.
- ✅ **Expense approve** (`PUT /financial/expenses/{id}/approve`) → balanced JE auto-posted: Dr [Expense category account, e.g. Supplies/Travel/Utilities] / Cr Cash. Posting deferred to approval (not creation) since pending expenses aren't yet a cash outflow.

### How the mapping works
- New `_post_to_accounting(kind, doc, current_user)` helper in `financial.py` finds the right CoA accounts via the existing `_find_account(location_id, account_type=, name_hints=)` helper.
- **Account selection heuristic** with `_EXPENSE_CATEGORY_HINTS`: maps financial-module expense categories (`salaries/utilities/supplies/travel/...`) to CoA account names (case-insensitive contains). Falls back to first matching expense-type account if no hint matches.
- **Silent no-op safety**: if a location hasn't seeded its CoA yet, OR no journal exists, the helper just returns — financial flows continue to work as before with zero behaviour change.
- **Idempotency**: queries `auto_generated_from + source_id` before inserting; never double-posts.

### Smoke coverage
Two new pytest tests in `test_smoke_recent_modules.py` (now 16/16 passing in 0.7s):
- `test_donation_auto_posts_to_ledger` — verifies a 5,000 UGX donation creates a balanced posted JE
- `test_expense_approval_auto_posts_to_ledger` — verifies pending expense ≠ JE, but approval triggers a balanced posted JE

### Result
The Trial Balance / P&L / Balance Sheet on `/accounting` now reflects **all** financial activity (sales + donations + approved expenses + asset depreciation) — not just sales. No UI changes; existing financial.py users see no friction.

## Recently Resolved — Iteration 115 (May 20, 2026)
**Pytest smoke CI job + Testing-agent validation of all recent modules.**

### Pytest CI smoke job
- ✅ New `backend/tests/test_smoke_recent_modules.py` (14 tests, 0.5s runtime): covers Approvals workflows + requests + role hierarchy, HR Leave types/balance/lifecycle, Reimbursements lifecycle, Attendance clock-in/out idempotency, Accounting CoA seed + balanced/unbalanced entry validation + posted-entry trial-balance reconciliation, Sale discount auto-approval + payment lock, Payment reminders. State-aware (uses current-year dates for balance assertions; cleans up after itself).
- ✅ `.github/workflows/ci.yml` extended with a `pytest-smoke` job that spins up MongoDB 6 + FastAPI in CI runner, seeds admin, runs the new smoke file.
- ✅ `scripts/lint-check.sh --with-tests` runs the smoke file locally against the dev backend.

### Testing-agent validation (iteration_84 report)
- ✅ Backend: 14/14 pytest smoke PASS
- ✅ Frontend: 10/10 target flows render & interact with **zero non-trivial console errors**
- ✅ Cross-module verified end-to-end: HR reimbursement >$100 auto-spawns approval **and surfaces visually in Approvals Inbox** (`Reimbursement: Conference flight USD 350 · current step: Manager review`)
- Action items returned: **1 MEDIUM (more data-testid coverage), 1 LOW (seed a low-stock product for visual demo)** — no functional bugs.

### Test-id hardening (MEDIUM action item from testing agent)
- ✅ LoginPage: added `data-testid` for `login-identifier-input`, `login-password-input`, `login-submit-button`
- ✅ HRPage: added `data-testid` for all 7 tab triggers (`hr-tab-salaries/payslips/contracts/documents/leave/reimbursements/attendance`)

## Recently Resolved — Iteration 114 (May 20, 2026)
**CI lint gate added + 8 real bugs the gate surfaced.**

### CI infrastructure
- ✅ `scripts/lint-check.sh` — local pre-commit gate (Python ruff F821/F823/F841/E722/B006 + JS eslint --quiet)
- ✅ `.github/workflows/ci.yml` — runs the same gate on every push/PR
- ✅ `frontend/eslint.config.mjs` — minimal flat config (ESLint v9 compatible) targeting only critical errors (jsx-key, no-undef, react-hooks rules), warnings for unused vars and exhaustive-deps

### Real bugs the gate caught & fixed
1. **`TasksPage.jsx:502`** — bulk-move handler referenced undefined `lists` (should be `board?.lists`); would crash when used.
2. **`EventsPage.jsx:415, 430`** — array-key references to undefined `item` variable (introduced in earlier iteration).
3. **`PortalProfile.jsx:159`** — same `item?.label` undefined reference pattern.
4. **`ProductsPage.jsx:759`** — bulk-delete called nonexistent `fetchProducts` (actual function is `fetchAll`).
5. **`WebSocketContext.js`** — missing `import { secureStorage }` (3 uses; would throw at runtime).
6. **`PrintableBadges.jsx`** — `generateInitialsImg` was nested inside `printElement`, making it inaccessible to the 2 call sites at lines 102/205 (silent breakage of badge initials fallback).
7. **`ResourcesPage.jsx:139`** — dead `if (false) return false` branch.
8. **7 ui/*.jsx files** — mismatched quote characters in imports (`from '...something"`), real syntax errors in calendar/alert-dialog/carousel/command/form/toaster/toggle-group/pagination components. Each would crash when its component loaded.

All fixes applied. Both lint gates now pass green.

## Recently Resolved — Iteration 113 (May 20, 2026)
**Code review remediation — Critical (🔴) security/correctness fixes applied.**

### Critical 🔴 fixes
- ✅ **XSS in CardDetailDialog ext-user search** (line 334): replaced `innerHTML` template-literal injection + manual `addEventListener` hack with a clean React-state-driven dropdown (`extResults` state + `<button>` rows). Eliminates XSS via API-returned usernames; also removes the stale-closure event-listener bug.
- ✅ **`outerHTML` injection in VariantBarcodePrint** (line 105): replaced with `createElement` + `textContent` + `replaceWith` (no string concatenation into DOM).
- ✅ **Empty `catch {}` blocks in CardDetailDialog/TaskTimeTracker**: now log to `console.error` so failures are debuggable.
- ✅ **F841 unused variables** in production: `financial.py:713` (`campus`), `misc.py:307` (`campus`), `sales.py:775` (`role`), `websocket.py:249` (`status_message`). Verified 3 affected endpoints still respond correctly after fix.
- ✅ **Bare `except:` in production** (E722): `events.py` (2 sites), `financial.py` (2 sites), `websocket.py` (1 site). All converted to `except Exception:` for traceability.
- ✅ **Array-index React keys in ApprovalsPage**: workflow-step rows, approval-chain steps, and per-step approvals log all now use stable keys (`s.id || ${wf.id}-step-${i}`, `${a.user_id}-${a.at}`).

### Note on items NOT addressed this pass (scoped intentionally)
- **189 React hook-dependency warnings** are mostly intentional (effects deliberately running once on mount, or scoped behind useCallback). A blanket fix would risk introducing infinite-loop bugs. Recommend addressing per-component when each is next touched.
- **Refactoring 5 700+ line components** (AccessPage, AccountingPage, UserEditDialog, CalendarPage, Layout) is a high-risk change that warrants its own dedicated iteration.
- **secureStorage** is only used for non-secret app state (active_campus_id, theme); auth tokens flow through the axios interceptor with the proper Bearer-token pattern.
- **Receipt/UnifiedBadge/BadgePrintView print pipelines** were flagged by the reviewer but already use DOMPurify and `escapeHtml` — they're safe; flags were false positives on the API surface.
- **Test file warnings** (206 `is`-vs-`==`, missing type hints) are lower priority — production code prioritized.

## Recently Resolved — Iteration 112 (May 20, 2026)
**Suggested improvement: Sale Discount > threshold auto-approval guard.**

- ✅ **Discount-threshold guard** in `POST /sales`: detects max per-line discount (`manual_discount_pct`/`discount_pct`) or aggregate basket discount (`discount` / `subtotal`). If it exceeds the campus threshold (`store_settings.discount_approval_threshold`, default 20%), auto-spawns a `kind: sale_discount` approval against a matching workflow.
- ✅ **Payment lock**: while approval is pending, `payment_status` forced to "pending" and `PUT /sales/{id}/payment-status` to "paid" returns 400 with a clear "discount approval is pending" error.
- ✅ **Cross-module side-effects** on approval finalize:
   • `sale_discount` approved → sale's `discount_approval_status` flips to "approved", payment unblocked.
   • `sale_discount` rejected → sale auto-voided with `voided_reason="Discount rejected"`.
   • Bonus loop closed: `expense` approval finalize now mirrors to `hr_employee_expenses.status` automatically.
- ✅ Sale rows expose `requires_discount_approval`, `discount_approval_id`, `discount_pct_max`, `discount_threshold`, `discount_approval_status` for receipt-watermark rendering.
- ✅ Curl-verified all 4 happy/edge paths: spawn → block-paid → approve → mark-paid; spawn → reject → auto-void.

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
