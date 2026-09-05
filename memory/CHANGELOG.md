# CHANGELOG

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
