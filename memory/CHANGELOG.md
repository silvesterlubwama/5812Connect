# CHANGELOG

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
