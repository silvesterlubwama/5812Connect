# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations, covering unified
comms, campus-scoped tasks/calendar/events, double-entry finance with
strict location enforcement, HR/payroll with weekly & multi-cadence pay,
kiosk check-ins, NFC badge issuance + PWA Wallet passes, guest passes,
social work, sales/POS/shipments, and self-service user portal.

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
