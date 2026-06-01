# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Completed Features (Iterations 49-78)
All features documented in /app/ADMIN_GUIDE.md and /app/memory/CHANGELOG.md.

## Recently Resolved — Iteration 161 (Jun 1, 2026)
**CI lint gate adds EmptyState check + license requirement removed.**

### Changes
1. **`scripts/lint-check.sh` now runs 3 gates** (was 2): ruff → eslint → check-empty-states. Any new `<EmptyState>` JSX call without a `testid` prop fails CI. The smoke pytest stage is now `[4/4]` when invoked with `--with-tests`.
2. **License + telemetry stack removed** per user direction. Deleted:
   - `backend/routers/telemetry.py`
   - `backend/tests/test_iteration160_telemetry_license.py`
   - `frontend/src/components/LicenseManager.jsx`
   - `frontend/src/components/LicenseStatusBanner.jsx`
   - `_fire_telemetry_heartbeat` cron + `_last_heartbeat_date` global from `server.py`
   - License manager card from `/admin`, banner from `App.js`
   - Heartbeat clauses from EULA (section 3 now states "no telemetry transmitted")
3. **Pre-existing bug fixed** in `RegisterPage.jsx` — was missing the `useBranding` import (would have been a runtime error on register flow). Caught by the new lint gate. Smoke regression confirms register page renders.

### Kept (independent of license stack)
- **EULA** (`desktop/eula/EULA.txt` + `.md`) — still wired into Tauri DMG/NSIS installers for legal acceptance at install time.
- **Auto-updater scaffold** — `tauri-plugin-updater` in Cargo.toml, plugin block in `tauri.conf.json` with `active:false`. Recipe in README. Flip when release server is available.
- **Code-signing scaffold** — env-var-driven (`APPLE_SIGNING_IDENTITY`, `WINDOWS_CERT_THUMBPRINT`, `TAURI_SIGNING_PRIVATE_KEY`). No-op without env vars.
- **Cloudflare Tunnel admin UI** (`RemoteAccessManager`) — Tauri-only card.
- **EmptyState lint script** (`scripts/check-empty-states.sh`).

### Tests / lint
- `bash /app/scripts/lint-check.sh` → all 3 gates pass.
- 29/29 backend pytest green (smoke + branding + p2_finish).
- Curl confirms `/api/telemetry/*` and `/api/license/*` endpoints return 404 (cleanly removed).
- Admin page screenshot: license card absent, all other admin cards intact.

⚠️ **Production redeploy needed** to pick up the changes. License feature was never active on production; removal is purely a code/cleanup change.

### Continuing per your plan
- **Release server** — when available, generate signing keys with `cargo tauri signer generate`, paste pubkey into `tauri.conf.json` `plugins.updater.pubkey`, flip `active:true`, set `endpoints` to your real release JSON URL.
- Future features can land without ever needing a license/heartbeat layer.

## Recently Resolved — Iteration 160 (Jun 1, 2026)
**License + Telemetry + EULA + auto-updater + code-signing + EmptyState lint.**

### 1. Telemetry & License Backend (`routers/telemetry.py`)
- `POST /api/telemetry/heartbeat` — public, anonymous beacon: `{install_id, license_key, org_id, version, user_count, env}`. Returns license status. Per-install 8-hour rate-limit dedup.
- `GET /api/license/self` — public, returns this install's persisted status.
- `POST /api/license/configure` — admin only, persists license_key + hq_url + telemetry opt-in. Auto-generates UUID4 install_id on first config.
- `POST/GET/PUT/DELETE /api/admin/licenses` — admin license CRUD (32-char URL-safe keys, optional expiry, plan, block/unblock with reason).
- `GET /api/admin/telemetry/installs` — admin install roster with annotated `license_status_obj` + `days_since_last_seen`.
- License statuses: `valid` / `unlicensed` / `invalid` / `expired` / `blocked` (soft enforcement — never blocks usage).
- Daily cron at 02:00 UTC (`_fire_telemetry_heartbeat`) sends the beacon to the configured HQ endpoint, persists the server's verdict locally.

### 2. License + Telemetry Admin UI
- New `/admin → License & Telemetry` card (testid `license-card`) with 3-tab dialog:
  - **This install** — paste license key + HQ URL, opt-in telemetry, see current status + last heartbeat.
  - **HQ** — issue/list/block/delete licenses (system admins only — non-admins see graceful empty list).
  - **Installs** — live roster of every install that's heartbeat'd, with status + version + user_count.
- New `<LicenseStatusBanner>` mounted globally — shows amber/rose banner above the app shell when self.license_status is `blocked`/`expired`/`invalid`. Dismissible via session-storage. **Never** blocks login or features.

### 3. End User License Agreement (EULA)
- `/app/desktop/eula/EULA.txt` (+ Markdown copy) — 9-section agreement covering license grant, restrictions, data privacy, updates, warranty, liability, termination, governing law.
- Wired into `tauri.conf.json`:
  - `bundle.macOS.license` → DMG installer shows the agreement, user must accept before drag-to-install.
  - `bundle.windows.nsis.license` → NSIS .exe installer shows mandatory "I accept" radio.
  - `bundle.windows.wix.license` → WiX .msi shows .rtf version (operator runs `unoconv -f rtf` once).
- The privacy disclosure (section 3) explicitly mentions the heartbeat + opt-out path, satisfying GDPR-style transparency.

### 4. Auto-updater scaffold
- `tauri-plugin-updater` added to Cargo.toml + initialized in `src/lib.rs`.
- `tauri.conf.json` has the plugin block with `active:false` (off by default), endpoint placeholder `https://hq.5812-global.org/releases/{{target}}/{{current_version}}`, pubkey placeholder.
- README has the full recipe: `cargo tauri signer generate` → paste pubkey → set `TAURI_SIGNING_PRIVATE_KEY` env vars at build time → release JSON shape spec.

### 5. Code-signing scaffold (no-op by default)
- `tauri.conf.json`:
  - `bundle.macOS.signingIdentity: null` — set via `APPLE_SIGNING_IDENTITY` env var.
  - `bundle.windows.certificateThumbprint: null` — set via `WINDOWS_CERT_THUMBPRINT` env var.
- `desktop/scripts/build-bundle.sh` detects the env vars and exports the matching Tauri bundling vars (`TAURI_BUNDLE_WINDOWS_CERTIFICATE_THUMBPRINT`, etc.). Without them: builds run unsigned (Gatekeeper / SmartScreen warnings on first launch).
- README documents Apple Developer ID + Windows EV cert acquisition + the full env-var matrix for both.

### 6. EmptyState consistency lint
- New `/app/scripts/check-empty-states.sh` — fails the build if any `<EmptyState>` JSX call lacks a `testid=` prop. Skips the EmptyState component definition itself (its JSDoc has a usage example). Currently clean across all 8 pages.

### Tests / lint
- New `tests/test_iteration160_telemetry_license.py` — **11/11 PASS** (heartbeat status branches × 4, rate-limit dedup, license CRUD roundtrip, expired status, admin-gating, install roster, self-status, configure-auth).
- 31/31 pytest green (16 smoke + 4 branding + 11 telemetry).
- `check-empty-states.sh` exits 0.
- ESLint + Ruff clean for all modified files.
- Testing agent (`iteration_160.json`): **backend 100% / frontend 100%, no critical bugs**. Verified end-to-end on the live preview.

⚠️ **Production redeploy needed** for the License & Telemetry admin UI to land. Tauri changes are scaffold-only — separate desktop build pipeline.

### Continuing per your plan
- **HQ deployment** — pick the cloud install you want to act as HQ, run it, then issue keys via `/admin → License & Telemetry → HQ`. Hand the keys to partner orgs to paste into their desktop installs.
- **Release server endpoint** — when you have one, flip `plugins.updater.active=true` in `tauri.conf.json`, generate the signing keypair, and update the placeholder URL.
- **CI integration** — wire `bash /app/scripts/check-empty-states.sh` into your existing lint-check.sh so future PRs don't drift.

## Recently Resolved — Iteration 159 (Jun 1, 2026)
**Option Z scaffold (Tauri + Cloudflare Tunnel) + EmptyState sweep round 2.**

### 1. Tauri desktop wrapper scaffold (`/app/desktop/`)
A complete scaffold for self-hosted desktop bundles (`.exe` / `.dmg` / `.AppImage`):

- **`src-tauri/Cargo.toml`** — Tauri v2 with `tauri-plugin-shell` + reqwest for backend health checks.
- **`src-tauri/tauri.conf.json`** — declares the bundle resources (backend / mongo / cloudflared) and the bundle target matrix (msi/nsis/deb/appimage/dmg).
- **`src-tauri/src/lib.rs`** — Rust shell that on launch:
  1. Spawns portable `mongod` listening on `127.0.0.1:27017`
  2. Spawns the PyInstaller-bundled FastAPI backend on `127.0.0.1:8001`
  3. Waits for `/api/health` (20 s timeout), then opens the Tauri webview
  4. Exposes Tauri commands `services_status`, `start_cloudflare_tunnel(config_yaml)`, `stop_cloudflare_tunnel`
  5. Cleanly kills child processes (cloudflared → backend → mongod) on quit
- **`scripts/build-bundle.sh`** — host-side build helper: PyInstaller-bundles the backend, runs `yarn build`, validates `mongod` + `cloudflared` resources are present, then runs `cargo tauri build`.
- **`README.md`** — full setup recipe (install prereqs, drop platform binaries, build, install, configure Cloudflare Tunnel via the admin UI).

### 2. Cloudflare Tunnel admin UI (`RemoteAccessManager.jsx`)
- New admin card on `/admin` (testid `remote-access-card`).
- **Auto-hides on cloud builds** — the card returns `null` when `window.__TAURI__` is absent, so the production preview is unaffected.
- Inside Tauri: dialog with a YAML textarea for the cloudflared config + service-status row (mongo / backend / tunnel) + start/stop buttons. Persists last-used config to `localStorage` and to `${app_data_dir}/cloudflared/config.yml` on save.
- Status polled every 4 s via the `services_status` Tauri command.

### 3. EmptyState rollout — round 2 (10 more placeholders)
- **CommsPage** — announcements / messages / conversations sidebar / thread replies (4)
- **TasksPage** — boards sidebar with "New board" CTA
- **SettingsPage** — venues tab with "Add your first venue" CTA
- **SponsorPortalPage** — updates list
- **FinancialPage** — transfers table (kept as table-row variant since table context)
- Plus iter-158 stragglers (already shipped in this iteration's commit chain)

### Build / cloud impact
- **Cloud bundle is unaffected.** No webpack imports of `/app/desktop/`, RemoteAccessManager hides itself, no Tauri APIs statically imported.
- **Production redeploy needed** for the EmptyState rollout to be visible.
- Desktop bundle build is **NOT** runnable in the K8s preview — it requires a real Windows / macOS / Linux host with Rust + PyInstaller installed plus the platform-matching `mongod` + `cloudflared` binaries dropped into `desktop/resources/`. The recipe is in `desktop/README.md`.

### Tests / lint
- 20/20 regression green (4/4 branding + 16/16 smoke).
- ESLint clean for all 7 modified frontend files + RemoteAccessManager.
- Testing agent (`iteration_159.json`): backend 100% / frontend 100%, no bugs. Verified `remote-access-card` is correctly absent in cloud DOM. All pre-existing admin cards still render intact.

⚠️ **Production redeploy needed** for the EmptyState changes. The Tauri bundle is a parallel artifact — built separately on a desktop OS and installed by partner orgs.

### Continuing per your plan
- **Per-platform build runs**: when you have a Mac/Windows/Linux host ready, drop the `mongod` + `cloudflared` binaries into `desktop/resources/{mongo,cloudflared}/` and run `bash desktop/scripts/build-bundle.sh`. The recipe will produce installers ready for code-signing.
- **Tauri code signing** (Apple Developer ID, Windows EV cert) — organisational decisions, scaffolded as no-op for now.
- **Tauri auto-updater** — recipe is in the README; wire up `tauri-plugin-updater` once you have a release server URL.

## Recently Resolved — Iteration 158 (Jun 1, 2026)
**Triple polish: EmptyState rollout + members.py modularization + overdue-task cron upgrade.**

### 1. EmptyState rollout (continuation of iter 156)
- Wired the reusable `<EmptyState>` component into 11 placeholder slots across 5 high-traffic pages:
  - **AccountingPage** — Entries / Accounts / Ledger empty states (with "New entry" / "New account" CTAs)
  - **BankPage** — Vendors / Bills empty states
  - **ApprovalsPage** — Inbox / Mine / All / Workflows empty states
  - **OutreachPage** — Programmes / Sessions empty states
  - **SocialWorkPage** — Schools tab + case-detail Notes empty state
- SecurityCheckpointPage + HRPage got friendlier copy + testids on their existing text-only placeholders.
- Pattern is now well-established; remaining pages can be swapped on-touch.

### 2. `routers/members.py` modularization (1973 → 8 sub-modules)
- The 1973-line monolith was split into a `routers/members/` package with 8 focused sub-modules:
  - `__init__.py` (39 LOC) — aggregates 8 sub-routers via `include_router`
  - `core.py` (233 LOC) — members CRUD + approve/reject
  - `families.py` (303 LOC) — families CRUD + guardians + portal/family + family-members linking
  - `children.py` (417 LOC) — children CRUD + education + residency + extras + photos + move-to-guest
  - `guests.py` (176 LOC) — guests CRUD + members-mirror helper + move-to-staff
  - `badges.py` (372 LOC) — badge templates + wallet badges + auto-issue + invalidate / reactivate
  - `nfc.py` (168 LOC) — NFC tag CRUD + signed payload + verify
  - `bulk_import.py` (192 LOC) — bulk import for members + children (auto-parent + auto-family)
  - `pdf.py` (101 LOC) — member profile PDF download
- **Zero behavioural change** — every endpoint preserves its exact path, method, deps, and body. server.py imports unchanged: `from routers.members import router`.
- Bonus: extracted shared photo-save helper `_save_photo()` deduplicating member/child/user photo upload paths in `children.py`.

### 3. Overdue-task email cron (`server.py:_fire_overdue_task_emails`)
- Cron itself was already implemented (daily 08:00 UTC, idempotent via `task_overdue_emails` collection, 3-day window per task+assignee).
- Upgraded to use the dynamic email config via `email_helpers.send_notification_email` — admin can now switch Resend / SMTP via the Integrations UI without redeploying. Falls back to env vars when config is empty.

### Tests / lint
- New `tests/test_iteration158_members_refactor.py` — 15 cases covering CRUD across every sub-module. All PASS.
- `tests/test_iteration157_branding.py` — 4/4 still PASS (regression).
- `tests/test_smoke_recent_modules.py` — 16/16 still PASS.
- Frontend testing agent confirmed: backend startup clean, all moved endpoints respond correctly, EmptyState renders for empty tabs (vendors/bills/approvals/outreach), branding still applies. **iteration_158.json: backend 100% / frontend 100%, no bugs.**
- Ruff + ESLint clean for all modified files.

⚠️ **Production redeploy needed**. Post-deploy: behaviour identical from the user's perspective, but the codebase is now meaningfully easier to navigate (no more 1900-line file) and emptier tabs are friendlier with proper CTAs.

### Continuing per your plan
- **Z** next: Tauri desktop wrapper + Cloudflare Tunnel for self-hosted `.exe/.dmg`.
- Optional polish: continued EmptyState rollout to remaining pages on-touch; manual `POST /api/cron/run-overdue-task-emails` admin endpoint for QA testing the cron without waiting for 08:00 UTC.

## Recently Resolved — Iteration 157 (Jun 1, 2026)
**Option Y — UI Customization MVP fully wired end-to-end.**

### What was already in place (iter 150-156)
- `db.system_settings.branding` field + `BrandingContext` + `BrandingEditor` admin dialog (rename / hide / reorder sidebar items, edit app name + tagline + logo URL + primary colour). Travelled with the backup tarball.
- Layout sidebar already applied `nav_overrides` + `section_overrides`.

### What this iteration finished
**1. `primary_color` actually applies app-wide**
- `BrandingContext` now hex→HSL converts the brand color and overrides the Tailwind `--primary` / `--ring` / `--brand-teal` CSS variables (was only setting an unused `--brand-primary`). Every Tailwind primary-coloured element (Sign In button, focus rings, badges, primary CTAs, sidebar active state) picks up the brand color automatically with zero per-component changes.
- Bonus: `--primary-foreground` auto-flips between black/white based on the brand's HSL lightness so text on the primary button stays readable for any hue.

**2. `logo_url` + `app_name` actually apply**
- Layout sidebar logo (testid `sidebar-logo`) reads `branding.logo_url` with a graceful `onError` fallback to the default 58:12 Global logo.
- Login page (testid `login-logo`, `login-app-name`), Register page, Reset Password page all read `branding.logo_url` + `branding.app_name` + `branding.tagline`.
- Document `<title>` already updates via the BrandingContext useEffect.

**3. Backend caching**
- `GET /api/admin/system-settings/public` now sets `Cache-Control: public, max-age=30` since it's called by every anonymous page load.

### Tests / lint
- New `tests/test_iteration157_branding.py` — 4 cases: public endpoint exposes branding, admin PUT persists + flows through, non-admin write returns 401/403, partial update preserves untouched fields. All PASS.
- Smoke 16/16 + branding 4/4 = 20/20 green.
- Frontend testing agent verified e2e: logged in admin, opened `branding-editor-dialog`, changed app_name + primary_color + nav_overrides, saved. Confirmed `document.title` updated, `--primary` CSS var became HSL `142 71% 45%` (correct hex→HSL conversion from `#22c55e`), Sign In button background rendered the brand color, sidebar relabeled `/dashboard` to "Home Base", `/tasks` hidden, login page `login-app-name` shows custom name. Cleanup PUT restored defaults.

⚠️ **Production redeploy needed**. Post-deploy: `/admin → Branding & Navigation → Customise` lets ops:
- Rename the app + add a tagline
- Drop in a custom logo URL (with auto-fallback if it 404s)
- Pick a brand colour that re-themes every primary CTA + focus ring app-wide
- Rename / hide / reorder any sidebar item or whole section
- Settings persist in `system_settings.branding` and travel with the iter-150 backup tarball.

### Continuing per your plan
- **Z** next: Tauri desktop bundle + Cloudflare Tunnel for self-hosted `.exe/.dmg`.
- Polish backlog: continue rolling EmptyState across pages on-touch, page-by-page mobile audit sweep, modularize `members.py` (1900+ lines).

## Recently Resolved — Iteration 156 (Jun 1, 2026)
**Batch F — reusable EmptyState component + mobile-responsiveness baseline.**

### Shipped

**1. `<EmptyState>` component (P2-17)**
- New `components/EmptyState.jsx` — friendly "nothing here yet" panel with floating-dot illustration, title + description + optional primary/secondary CTAs. Compact + full-size variants. Stable testid contract for tests.
- First wired-up locations in `UnifiedPeoplePage.jsx`: Families tab empty state (with "Add Family" CTA) + Guests tab empty state (with search-aware copy).
- Pattern adopt-on-touch: every other "No X yet" placeholder across the app can be swapped to `<EmptyState>` in passing as files get edited — no big-bang rewrite needed.

**2. Mobile-responsiveness baseline (P2-18)**
- Audited `Layout.jsx`: already has the right pattern (mobile hamburger via `mobile-menu-btn`, drawer overlay, `lg:` breakpoints for the static sidebar). Nothing to change there.
- Added global CSS catch-alls in `index.css`:
  - Tables inside Card content scroll horizontally below 640px (saves the long tail of unwrapped tables across the app)
  - Dialog `max-height: 92vh` on mobile so they fit on phone screens
  - Grid `min-width: 0` resets to stop wide grids from forcing horizontal scroll
  - Tap-target minimum 36px on coarse-pointer (touch) devices
- The page-by-page mobile audit + EmptyState rollout can be a long-running polish sweep — the foundations are now ready.

### Tests / lint
- 39/39 sample pytest still green.
- Ruff + ESLint clean.

⚠️ **Production redeploy needed**. Post-deploy: tables, dialogs, and tap-targets all behave sensibly on phones automatically.

### Continuing per your plan
- **Y** next: UI customisation — rename nav items, reorder, edit links, brand colour. Powered by the `branding` collection that the iter 150 backup feature was designed to carry.
- **Z** after Y: Tauri desktop bundle + Cloudflare Tunnel for the remote-access URL.

## Recently Resolved — Iteration 155 (Jun 1, 2026)
**Batch E — PWA offline UX + code-split heavy pages.**

### Shipped

**1. OfflineBanner component (P2-15)**
- New `components/OfflineBanner.jsx` — pinned amber banner at the top of the app whenever `navigator.onLine === false`. Pairs with the existing service worker (`public/sw.js`) which already serves cached pages + queues writes when offline.
- On recovery, briefly shows a green "Back online — syncing…" confirmation for 4s.
- Mounted globally in `App.js` so every route (incl. kiosks) gets it.
- Visually confirmed in Playwright: dispatching `offline` event shows the banner; Financial page still renders fully from cache.

**2. Code-split heavy pages (P2-16)**
- `App.js` now uses `React.lazy()` + `<Suspense>` to load these 5 pages on-demand:
  - `UnifiedPeoplePage` (1,500 lines)
  - `ProductsPage` (1,910 lines — POS + Products + Sales History + Customers)
  - `FinancialPage` (1,335 lines)
  - `AccountingPage` (799 lines)
  - `SocialWorkPage` (950 lines)
- Total deferred: ~6,500 LOC + their transitive deps (recharts, qrcode-logo, html5-qrcode, etc.). First-load bundle shrinks substantially; pages load on first navigation with a clean spinner fallback.

### Tests / lint
- 57/57 pytest still green.
- Ruff + ESLint clean.
- Visual smoke: Offline banner renders correctly when `navigator.onLine` is forced false; Financial page renders fully after lazy chunk loads.

⚠️ **Production redeploy needed**. After redeploy:
- First page-load is noticeably lighter (chunks load on-demand).
- Kiosks that go offline show the clear amber banner — users + operators know the state instantly.
- Service Worker already handles offline fetch fallback (cached pages, queued POSTs).

### Continuing per your plan
- **Batch F** (next): empty-state illustrations across the app + mobile-responsiveness audit on staff pages.
- Then **Y** (UI customisation: nav rename + reorder + brand), then **Z** (Tauri + Cloudflare Tunnel).

## Recently Resolved — Iteration 154 (Jun 1, 2026)
**Batch D — centralised print stylesheet + security_checkpoint sub-module split.**

### Shipped

**1. Centralised `print.css` (P2-14)**
- New `/app/frontend/src/styles/print.css` — single source of truth for every printable surface (receipts, badges, payslips, invoices, profile PDFs).
- Defines reusable utility classes: `.print-area`, `.no-print`, `.page-break-before/after`, `.keep-together`, paper-size presets `.print-58mm / .print-80mm / .print-A6 / .print-A5 / .print-A4` + page-rule names `receipt-58mm/receipt-80mm/badge-A6/doc-A4-clean`.
- Forces `-webkit-print-color-adjust: exact` (so receipts/badges keep their colors), kills animations during print, prints links' hrefs in inline text (skippable with `.no-href`).
- Imported from `index.js` so it loads globally. Component-local `@media print` blocks (Receipt.jsx etc.) keep working — the global rules give designers a consistent baseline.

**2. `security_checkpoint/__init__.py` further split (P2-13)**
- Extracted the **logbook + household-lookup + batch-check-in** endpoints (~187 lines) into `security_checkpoint/logbook_lookup.py`.
- Pattern: each sub-module exports a `register(router)` function that attaches its endpoints to the shared router from `__init__.py`. Imports + path prefixes unchanged → external callers see no difference.
- New file sizes:
  - `__init__.py` — **767 lines** (was 949, was 1304 pre-iter146)
  - `logbook_lookup.py` — 177 lines
  - `_common.py` — 271 lines
  - `ocr.py` — 115 lines
- `members.py` left untouched this iteration — it's 1900 lines but every endpoint is tightly coupled to local helpers; a clean split needs its own refactor pass.

### Tests / lint
- 57/57 pytest still green.
- Ruff + ESLint clean.
- Curl-verified `/api/security/checkpoints` and the moved logbook + lookup endpoints still respond.

⚠️ **Production redeploy needed** to pick up the print stylesheet + refactor. Behaviour unchanged from the user's perspective.

### Continuing per your plan
- **Batch E** (next): PWA offline shell + React.lazy code-splitting on the heavy pages.
- Then **Batch F** (empty states + mobile audit).
- Then **Y** (UI customisation), then **Z** (Tauri).

## Recently Resolved — Iteration 153 (Jun 1, 2026)
**Batch C — Org country/currency setting + uniform kiosk peripheral treatment.**

### Built per user request

**1. Org country/currency configurable from the Integrations dialog**
- New `GET /api/admin/system-settings/public` (no auth) returns `{org: {primary_country, primary_currency}, email_provider}` so any frontend page can pick up the org default without an admin auth round-trip.
- `IntegrationsManager` gains a new **Organisation** section (testid `integrations-org-section`) with country + currency dropdowns covering Uganda/Kenya/Tanzania/Rwanda/Burundi/Haiti/Thailand/USA/UK/SA/Nigeria/Ghana/Ethiopia. Save button (`org-save-btn`) persists to `db.system_settings`.
- `FinancialPage.jsx` reads the public endpoint on mount — when no specific location is filtered ("All Locations"), it uses the org's `primary_currency` instead of the hard-coded UGX. Verified end-to-end: switching org to Kenya/KES via the API made the public endpoint return KES; reverted to UGX cleanly.

**2. Batch C — uniform peripheral treatment for Check-in Kiosk + POS**

*Check-in Kiosk (`KioskPage.jsx`)*:
- Already had `PeripheralPermissionBanner` from iter 143.
- NEW: **📷 Camera Scan** button (testid `kiosk-camera-scan-btn`) → opens `BarcodeScanDialog` → submits to the existing `handleIdScan` flow.
- NEW: **🔧 Diagnostics** button (testid `kiosk-diagnostics-btn`) → opens the full `DeviceDiagnosticsDialog` from iter 149.

*POS (`ProductsPage.jsx` POS tab)*:
- Already had `PeripheralPermissionBanner` from iter 143 + `BarcodeScanDialog` wired for product scans.
- NEW: explicit **📷 Camera Scan** toolbar button (testid `pos-camera-scan-btn`) so cashiers without an attached barcode scanner can hit the camera path with one tap.
- NEW: **🔧 Diagnostics** button (testid `pos-diagnostics-btn`) — same dialog as the other kiosks.

### Tests / lint
- 57/57 pytest still green.
- Ruff + ESLint clean.
- Curl-verified public endpoint → Org Kenya/KES round-trip.

⚠️ **Production redeploy needed**. Post-deploy:
- `/admin → Integrations → Organisation` lets you change country+currency without touching code.
- `/kiosk` (after staff sign-in) + `/sales` POS tab now both have camera-scan + diagnostics buttons matching the Security Checkpoint experience.

### Continuing per your plan
- **Batches D-F** next: file split / print styles / PWA / code-split / empty states / mobile audit.
- Then **Y** (UI customisation), then **Z** (Tauri).

## Recently Resolved — Iteration 152 (Jun 1, 2026)
**Batch B — P1 hardening: security headers + Mongo indexes + inactivity logout + Integrations admin UI (Resend/SMTP/Sentry).**

### Shipped
1. **Security headers middleware** — every response now carries `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (allow-listing self for camera/mic/serial/HID/USB/BT/geo), `X-XSS-Protection`, and HSTS over HTTPS only. Verified via `curl -I` on `/api/health`.
2. **Mongo hot-path indexes audited** (`_ensure_indexes`):
   - `security_checkpoint_events`: `(checkpoint_id, created_at desc)`, `(checkpoint_id, clear_at desc)`, `(checkpoint_id, subject.id, direction, created_at desc)` — visitor-log + state + entry/exit pairing now covered
   - `sales`: `(location_id, created_at desc)` + `receipt_number` + `customer_id`
   - `login_attempts` (iter151): `(ip, ok, at desc)` + TTL on `at` (30 days)
   - `members`: `(role, active_campus_id, status)` + `(kind, status)` + `resident_location_id`
   - `children`: + `resident_location_id`
   - `audits` / `audit_log`: 1-year TTL on `created_at`/`timestamp`
   - `wallet_badges.resident_location_id` (supports the iter151 campus-filter fix)
3. **Inactivity logout** for staff — `useIdleTimeout` wired into `Layout.jsx`. Privileged roles (Director+) → 15 min; everyone else → 30 min; Security Contractor / Guest kiosks → disabled (they have their own lock screens). Toast warns on auto-logout.
4. **SystemSettings collection + admin Integrations UI**:
   - New `routers/system_settings.py`: `GET/PUT /api/admin/system-settings`, `POST /test-email`. Stores Resend / SMTP / Sentry config in `db.system_settings` (single doc, id="default"). Secrets are masked on read (`••••XXXX` + `_set` flag); operator types to replace. Travels with the backup tarball.
   - `email_helpers.py` now reads from `get_email_config()` on every send — config changes apply instantly without redeploying. Falls back to env vars when DB is empty.
   - **Sentry init at boot** reads `get_sentry_config()` and initialises `sentry-sdk[fastapi]` if a DSN is set. Added `sentry-sdk==2.61.0` to `requirements.txt` (via pip-freeze).
   - New `IntegrationsManager` admin card on `/admin` (testid `integrations-card`) → dialog with Email section (Provider / Sender / API key / Send test) + Sentry section (Enable / DSN / Environment / Sample rate).

### Tests / lint
- 69/69 pytest still green.
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.
- Curl-verified security headers present, system-settings endpoint returns masked config.
- Screenshot-confirmed the Integrations dialog renders with provider switcher, masked API key field, Sentry config + test-email button.

⚠️ **Production redeploy needed**. Post-deploy:
- Admin → **Integrations & Email** to paste a Resend API key (or SMTP creds) → **Send test email** to verify.
- Admin → same dialog → tick **Enable Sentry**, paste your DSN, save, restart backend.
- Inactivity logout fires after 15 min (admin) or 30 min (everyone else) — adjust in `Layout.jsx` if too aggressive.

## Recently Resolved — Iteration 151 (Jun 1, 2026)
**Batch A — P0 hardening + daily auto-backup. Pytest 69/69.**

### Shipped
1. **Rich `/api/health`** — replaced the 1-line stub with a full subsystem probe: db ping with latency, uploads-dir writability test (touches a canary file), LLM key configured flag, Resend configured flag, scheduler heartbeat, uptime, app version. Returns `status` ∈ {healthy, degraded, unhealthy} so load balancers + uptime monitors can act on it.
2. **`/auth/login` rate limit** — per-IP counter in new `login_attempts` collection. 6+ failures within 60s returns `429 "Too many failed sign-in attempts"`. 0.4s tarpit on every failure regardless of count to slow blind brute-forcing. Success inserts a positive marker; old failures naturally expire from the 60s window.
3. **`/badges/list` campus filter fix** — now matches on EITHER `location_id` OR `resident_location_id` so bulk-issued resident badges show up regardless of which campus the admin is currently viewing. System admins see every badge.
4. **Daily auto-backup at midnight UTC** — new `_fire_auto_backup()` helper hooked into the existing scheduler loop. Writes `/app/backend/backups/auto-daily-<stamp>.tar.gz` (audit-included for cold-store completeness). Prunes anything older than 30 days. Manually invocable for testing — verified writes a 255KB tarball.

### Tests / lint
- 69/69 pytest still green (smoke + iter91 + iter141 + iter90).
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.

⚠️ **Production redeploy needed**. Post-deploy:
- Wire your uptime monitor at `https://5812.lubwamas.org/api/health` — alert on status != healthy.
- The auto-backup runs every midnight UTC — `/admin → Backup & Restore → Pre-restore Snapshots` shows them automatically.
- Login brute-force is now blocked at 6 attempts/IP/60s.

### Next batches
- **Batch B** — security headers + inactivity logout + Sentry + Mongo indexes
- **Batch C** — uniform iter148/149 treatment for Check-in Kiosk + POS
- **Batches D-F** — P2 polish (file split, print, PWA, code-split, empty states, mobile)
- Then **Y** (UI customization), then **Z** (Tauri).

## Recently Resolved — Iteration 150 (Jun 1, 2026)
**Configuration Backup & Restore — admin only. 78/78 tests green (13 new + 57 regression + 8 e2e).**

### Why
Operators need to move data between deployments — preview ↔ production, cloud ↔ self-hosted Tauri, disaster-recovery rollback. Single `.tar.gz` they can hand off / store off-site / re-import.

### Backend (`routers/backup.py`)
- `GET /api/admin/backup/preview` — per-collection doc counts + uploads size for the export sizing UI.
- `POST /api/admin/backup/export` — streams a single `.tar.gz`:
  - `manifest.json` (version + exporter + collection list + counts)
  - `collections/<name>.jsonl` for every user collection (one JSON doc per line — safe for huge collections)
  - `uploads/<path>` — every file under `/app/backend/uploads/`
- `POST /api/admin/backup/import` (multipart) — body: `file, mode='merge'|'replace', admin_password, include_audit, dry_run`:
  - **Re-asks for the admin password** and re-verifies via bcrypt (`verify_password`) — guards against stolen-token misuse.
  - **`merge` mode** upserts each doc by its `id` field.
  - **`replace` mode** drops the target collection before re-inserting — verified semantics by sentinel insertion test.
  - **`dry_run`** parses + counts but does not write.
  - Returns per-collection `{read, inserted, updated, errors}` + the first 30 error messages + `snapshot_path`.
- **Pre-restore snapshot**: every non-dry-run import auto-saves a fresh tarball to `/app/backend/backups/` so the operator can roll back.
- `GET /api/admin/backup/snapshots` + `GET /api/admin/backup/snapshots/{fn}/download` for that rollback.
- **`_NEVER_BACKUP`** excludes `sessions`, `push_subscriptions`, `notifications`, `security_pair_attempts`, `fingerprint_data`, `fs.*` — runtime state that shouldn't (and can't safely) travel.
- **`_AUDIT_COLLECTIONS`** opt-in via the `include_audit` flag (audits, task_overdue_emails, checkin_logs).

### Frontend (`components/BackupRestoreManager.jsx`)
- New **Backup & Restore** card on `/admin` (testid `backup-restore-card`).
- Dialog (`backup-restore-dialog`) shows:
  - **Preview summary**: collections / docs / uploads-bytes
  - **Export section**: include-audit checkbox + Download backup
  - **Restore section**: file picker + Mode (Merge / Replace) + Admin password + Dry-run checkbox
  - **Pre-restore Snapshots**: list of auto-saved snapshots with one-click Download
- Replace+non-dry-run prompts a `confirm()` before submission. Dry-run renders an inline report panel showing read / inserted / updated / errors.

### Verified end-to-end
- Backend round-trip: export → 236KB tarball with 122 collections + 5 upload files; merge re-import returned `{read:4930, updated:4783, inserted:147, errors:0}`.
- Testing agent: 13/13 backend cases (auth, password gate, dry-run, merge, replace with sentinel verification, snapshots, corrupted tarball → 400, future-version manifest → 400) + 8/8 e2e (UI flow including download trigger).
- 57/57 regression still green.
- Ruff + ESLint clean.

⚠️ **Production redeploy needed**. Post-deploy:
- `/admin → Backup & Restore → Download backup` whenever you want a portable copy. Recommended weekly + before major changes.
- To move data: download from one deployment, upload to the other, dry-run first, then real merge or replace.

## Recently Resolved — Iteration 149 (May 31, 2026)
**Comprehensive Device Diagnostics + Kiosk PIN-unlock via QR.**

### What the user asked for
*"Yes, and allow to detect other attached or usable hardware."* — plus implementing the iter-148 suggestion (kiosk PIN-unlock via QR).

### Built

**1. `DeviceDiagnosticsDialog` — full hardware/runtime panel**
- New component `frontend/src/components/DeviceDiagnosticsDialog.jsx` (~210 lines).
- Detects + reports:
  - **Media**: cameras (count + labels + permission state), microphones, speakers
  - **Wireless**: NFC (NDEFReader), Bluetooth (paired devices via `bluetooth.getDevices()`)
  - **USB/Serial**: Web Serial paired ports, Web HID paired devices (with vendor/product IDs + product names), Web USB paired devices (with manufacturer/product strings)
  - **Runtime**: Geolocation, Battery (level + charging), Network (online/effectiveType/downlink/RTT/saveData), Storage quota (used / total MB), Screen size + DPI + touch capability + standalone-PWA flag, Wake Lock support, Service Worker availability, Clipboard availability, HTTPS context
- One-click **Pair port / Pair HID / Pair USB / Pair Bluetooth** buttons that trigger the browser's native picker (user-gesture required) and re-probe after pairing.
- One-click **Enable** buttons for camera / NFC / geolocation to fire the standard permission prompts.

**2. `peripheralPermissions.js` greatly expanded**
- New `detectFullDiagnostics()` — one-shot probe of all of the above into a single object.
- New `requestGeoAccess()` — geolocation permission helper.
- Private helpers for `serial.getPorts()`, `hid.getDevices()`, `usb.getDevices()`, `bluetooth.getDevices()`, `getBattery()`, `navigator.connection`, `navigator.storage.estimate()`, `screen`.
- Backwards-compatible — existing `PeripheralPermissionBanner` keeps working unchanged.

**3. Diagnostics wired into the kiosks**
- **Security Console** — new 🔧 Diagnostics icon button (testid `cp-diagnostics-open`) next to Lock + Logout in the header. Opens the full panel.
- **Admin /admin → Kiosk Links** — new **Device diagnostics** button in the dialog toolbar (testid `kiosk-links-diagnostics-btn`). Admins can pre-flight a device from the same place they get the URLs.

**4. Kiosk PIN-unlock via QR** (iter-148 suggested improvement)
- **LockScreen** gains a camera-icon button next to the Unlock button — opens `BarcodeScanDialog` (camera or keyboard-wedge). Accepts both `CPK_UNLOCK:<6-digit>` payloads and bare 6-digit PINs. Successful scan re-uses the existing pair endpoint to unlock.
- **KioskLinksManager** now renders a small QR next to each checkpoint's pairing PIN when "Show pairing PINs" is on. The QR encodes `CPK_UNLOCK:<pin>` so a locked kiosk can scan it directly to unlock.

### Tests / lint
- ESLint clean. No backend changes — entirely client-side.
- Visual smoke-confirmed in headless Playwright: Device Diagnostics dialog renders all six sections (Media / Wireless / USB-Serial / Runtime / sub-rows), shows `Unsupported`/`Unknown` correctly when running headless without hardware, **Pair** buttons present, **Refresh** button present.

⚠️ **Production redeploy needed**. Post-deploy on a real device:
- `/admin → Kiosk Links → Device diagnostics` lets you check what cameras / printers / scanners are visible to the browser before deploying a kiosk.
- `/security-checkpoint` (paired) → 🔧 icon in the header opens the same diagnostics on the kiosk itself.
- Locked kiosk: tap the camera icon next to Unlock → scan the QR from `/admin → Kiosk Links` → instant unlock without typing.

## Recently Resolved — Iteration 148 (May 31, 2026)
**Built-in camera scanning + hardened ID camera errors.**

### Reported issues (on production)
1. The built-in camera doesn't open when uploading an ID (One-Time Entry → Use Camera).
2. There's no way to use the built-in camera for regular QR scans — only USB barcode scanners + NFC.

### Fixed
- **New "📷 Camera Scan" button** on the Security Console toolbar (top-left, emerald) + **"Scan with this device's camera"** button on the Guest view's idle state. Opens the existing `BarcodeScanDialog` which handles QR/barcode detection via `html5-qrcode` plus a manual-entry fallback for keyboard-wedge scanners.
   - Smart routing on the security side: payloads starting with `INV-`, `RCPT-`, or `sale_` are auto-routed to the receipt exit-scan endpoint; everything else hits the standard scan endpoint.
- **Hardened the ID-photo camera path** in `OneTimeGrantDialog`:
   - Pre-check `navigator.mediaDevices.getUserMedia` availability before attempting.
   - HTTPS-only enforcement (with a clear message, since production runs HTTPS but a local non-HTTPS environment would silently fail).
   - `enumerateDevices()` probe — if zero cameras are present, toast "No camera detected — upload an ID photo instead" instead of failing silently.
   - Translated `DOMException` names to operator-friendly copy: `NotAllowedError` → "Permission denied — tap the camera icon in your browser's address bar", `NotFoundError`/`OverconstrainedError` → retry without `facingMode='environment'` constraint, `NotReadableError`/`AbortError` → "Camera in use by another app".
   - `video.play()` wrapped in try/catch since some browsers reject it without a user gesture.

### Tests / lint
- ESLint clean. No backend changes.
- Visual smoke-confirmed in headless Playwright: Security Console shows the new Camera Scan button; clicking opens the dialog; "Requested device not found" message renders (correct for a no-camera environment); manual Type / Keyboard wedge tab is selectable as fallback.

⚠️ **Production redeploy needed**. Post-redeploy on production (HTTPS):
- Security operators can hit **Camera Scan** to use the device's webcam to scan any badge/QR/receipt without USB hardware.
- Guests can tap **Scan with this device's camera** on the visitor view if no NFC reader / USB scanner is attached.
- One-Time Entry ID camera now surfaces clear, actionable error messages when the camera can't open — every common failure mode is named.

## Recently Resolved — Iteration 147 (May 31, 2026)
**Kiosk Links & Setup admin tool — central index of every kiosk URL + pairing PIN.**

### What the user asked for
*"What and where is the link to set up security devices? Post a link finder page in the admin panel for all important kiosks and setup links."*

### Built
New `KioskLinksManager` card on `/admin` (alongside Module Access + Security Checkpoints + Expiring Grants Banner). Clicking **Open** reveals a dialog with five sections, each showing the QR code + copyable URL + open-in-new-tab button + setup notes:
1. **Security Checkpoint** — `/security-checkpoint` URL + a list of every configured checkpoint with its 6-digit pairing PIN (hidden behind a "Show pairing PINs" toggle so they don't leak when sharing the screen).
2. **Check-in Kiosk** — `/kiosk` URL + tablet setup notes (PIN-protected setup screen, campus binding, lock).
3. **POS Kiosk** — one card per location showing `/pos/<location_id>` — slim shell, no tabs.
4. **Public Surfaces** — `/marketplace` and `/sales-portal`.
5. **User Portals** — `/portal` for members/parents + an info card explaining the per-token Sponsor + School portals.

Every URL uses `window.location.origin` so when an admin opens this dialog on production it renders production URLs, and on preview it renders preview URLs — no env mismatch.

### Implementation
- New `components/KioskLinksManager.jsx` (single self-contained file, ~210 lines).
- Re-uses `react-qrcode-logo` (already in `package.json`) to render QR codes — kiosk operators scan the QR with the device camera to open the URL.
- Reuses `locationsApi.list()` for POS instances and `securityCheckpointApi.list()` for checkpoint PINs.
- Pulled in as a card on `/admin` (testid `kiosk-links-card`); dialog testid `kiosk-links-dialog`.

### Tests / lint
- ESLint clean. No backend changes — purely a new frontend admin tool.
- Visual smoke-confirmed: dialog opens, renders QR codes + URLs + 7 existing checkpoint PINs, "Show/Hide pairing PINs" toggle masks/unmasks the codes.

⚠️ **Production redeploy needed**. After redeploy, admins simply open `/admin → Kiosk Links & Setup` to get every device URL + every pairing PIN in one place.

## Recently Resolved — Iteration 146 (May 31, 2026)
**Separate Residents Log (blue-themed) + all 4 carry-over backlog items. Pytest 78/78.**

### Built per user request

1. **Separate Residents Log** (blue-themed, distinct from the Visitor Logbook)
   - Backend: `GET /api/security/checkpoint/residents-log` (device session) and `GET /api/security/checkpoints/{id}/residents-log` (admin Director+). Both reuse `_build_visitor_log()` with `residents_only=true`. Counts always include both visitor + resident totals.
   - Frontend Security Console: new blue **"Residents Log"** toolbar button (testid `cp-residents-log-open`) + dedicated `ResidentsLogDialog` (blue-tinted background, blue "Inside" badges).

### Backlog cleared

2. **Org-wide resident badges** — `POST /api/badges/auto-issue/residents` now accepts `location_id:'all'` to sweep every restricted location in one call. New header button `🪪 Issue all resident badges` on `/locations`.

3. **Resident badge payload** — `wallet_badges` now embed `is_resident`, `resident_location_id`, and `resident_location_name`. A checkpoint that doesn't know the member can still recognise them via the badge itself. Verified via direct DB query.

4. **Stray-resident indicator** — when a resident of location A scans at a checkpoint at location B, the scan event gets `stray_home: {id, name, is_restricted}`. The live security tile renders an amber `cp-stray-home` pill: **"Resident of <home location>"** so security knows where they should be.

5. **`security_checkpoint.py` refactor** — the 1,304-line monolith is now a Python package:
   - `security_checkpoint/__init__.py` (949 lines) — all endpoints + router/ocr_router exports.
   - `security_checkpoint/_common.py` (271 lines) — `_hash`, `_gen_pin`, `_resolve_session`, `_broadcast_to_checkpoint`, `_resolve_subject`, `_hydrate_subject`, `_shape_subject`, `_decide`, `_build_visitor_log`, `_checkpoint_rooms` + constants.
   - `security_checkpoint/ocr.py` (115 lines) — `_OCR_LANG_HINTS` + `_ocr_id_image`.
   - Server-side imports (`from routers.security_checkpoint import router, ocr_router`) are unchanged thanks to the package surface.

### Tests / lint
- New `/app/backend/tests/test_iteration146_residents_log.py` — 9 cases covering stray-home detection (local vs stray), residents-log endpoints (device + admin), org-wide bulk badge issue (idempotent), resident wallet_badge persistence (is_resident + resident_location_id+name).
- All 69 prior pytest cases still PASS after the refactor. Total: **78/78 green**.
- Ruff + ESLint clean.

⚠️ **Production redeploy needed**. After redeploy:
- `/security-checkpoint` paired console → click **Residents Log** for the blue-themed in/out roster.
- `/locations` admin → **Issue all resident badges** sweeps the whole org in one click.
- Any resident scanning at a checkpoint that isn't their home now triggers a clear amber tile telling security where they should be.

### Known carryover (P3)
- `security_checkpoint/__init__.py` is still 949 lines — better than 1,304 but worth a second pass to split into endpoint-group modules (admin, pairing, scan, grants, logbook, lookup, dashboard).
- `/badges/list` applies a campus filter that hides bulk-issued resident wallet_badges — observed in iter146 testing but data persistence is correct; only the admin listing is affected. Worth a follow-up.

## Recently Resolved — Iteration 145 (May 31, 2026)
**Resident vs visitor split + Inside-Now tile + bulk-issue resident badges. Pytest 57/57.**

### What the user asked for
1. **Improvement (iter 144 suggestion)**: live "Inside Now" tile on the Security Console header.
2. **NEW**: when a restricted-space resident scans at a checkpoint located IN their own residence, the system should recognise them as a returning/departing resident — NOT track them as a daily guest in the visitor log.
3. **NEW**: all residents (including children) get badges issued.

### Backend changes (`routers/security_checkpoint.py` + `routers/members.py` + `models.py`)
- **Subject classification**: scan handler now stamps `subject_type` on every event — `'resident'` when `subject.is_resident=true` AND `subject.resident_location_id === checkpoint.location_id`, else `'visitor'`. The reason text gets a `(resident)` suffix so the audit trail is unambiguous.
- **Visitor log envelope** changed shape from `[rows]` to `{date, rows, counts, include_residents}`. Counts split into `visitors_entered`, `visitors_inside`, `residents_entered`, `residents_inside` — always returned, regardless of filter. Default filter is `include_residents=false` so visitor-log rolls don't pollute with residents.
- **State endpoint** now returns `counts: {visitors_inside, residents_inside}` so the security console's Inside-Now tile updates every 1.5 s without a separate request.
- **`POST /api/badges/auto-issue/residents`** body `{location_id}` — bulk auto-issues wallet badges for every adult member AND child whose `resident_location_id` matches. Idempotent (already-badged subjects come back with `was_created=false`). Audited.
- **`MemberCreate` Pydantic model** now accepts `is_resident`, `resident_location_id`, `is_medical`, `has_restricted_access` (the create endpoint was previously stripping these — `MemberUpdate` did accept them, but new-resident creation needed it too).

### Frontend changes
- **Security Console header** (`SecurityCheckpointPage.jsx`) — new `cp-inside-now-tile` showing "INSIDE N visitor[s] · M resident[s]" in real time.
- **LogbookDialog + AdminLogbookDialog** — added an "Include residents" checkbox + counts pills (visitors / residents / inside now). Each row shows a **RESIDENT** badge when applicable.
- **LocationsPage.jsx** — restricted locations now show a 🪪 button on each row → confirms then calls `/api/badges/auto-issue/residents` and reports `{created, existing, errors, total_residents}`.

### Tests / lint
- Updated `test_iteration141_security_unification.py` to handle the new envelope shape on `/visitor-log`. Both tests that broke (`test_admin_visitor_log_shape`, `test_double_scan_creates_entry_then_exit`) now pass.
- All 57 prior pytest cases still PASS. Ruff + ESLint clean.
- Self-verified end-to-end: created a resident at `loc_59a87857`, scanned them → `subject_type='resident'`, default logbook returned 0 visitor rows + `residents_entered=1`. State counts showed `residents_inside=1`. Bulk badge issue created 1 badge.

### Carryovers / P3 backlog (deferred from this iteration)
- `routers/security_checkpoint.py` is now 1,260 lines — still well past the 700-line guideline. **Refactor needs its own iteration** (split subject/decision/logbook/lookup/batch into sub-modules + integration tests). Not done here to keep this iteration focused on user-visible behaviour.
- Auto-issue is per-location only; could be extended to per-campus / org-wide / "all residents missing badges" with a single click.
- Resident badge could embed `is_resident=true` so even a misconfigured checkpoint still recognises them via the badge payload itself.

⚠️ **Production redeploy needed**. After redeploy:
- Open `/admin → Security Checkpoints → 📋 Logbook` for any restricted-location checkpoint and verify the new "Include residents" toggle + counts pills.
- Go to `/locations`, find a restricted location (red shield), click the 🪪 button on its row → mass-issue badges.
- Open `/security-checkpoint` on a paired security device — the "INSIDE N visitor · M resident" tile appears next to the checkpoint name in the header.

## Recently Resolved — Iteration 144 (May 31, 2026)
**Unified Security Checkpoint + Check-in system. Pytest 57/57.**

### What the user asked for
1. Drop the guest-facing tablet — single-device mode where the visitor scans on the same reader the operator runs (kept dual-device available too).
2. Visitor logbook showing entry + exit times per person per day.
3. Slim standalone POS at `/pos/:storeId` — no surrounding app shell.
4. Admin can pick checkpoint **kind**: *strict* (current restricted-location gate), *hybrid* (also recognises event ticket QR codes and auto-checks attendees in), or *check_in_only* (no gate, just log presence).
5. Phone / first-name search → pulls up the household, multi-select for batch check-in by the security operator.

### Implementation

**Backend `security_checkpoint.py`**
- New checkpoint fields: `kind` (`strict|hybrid|check_in_only`) + `device_mode` (`dual_device|single_device`). Pair endpoint rejects `guest` mode on single-device with a clear 400.
- `_resolve_subject` now recognises **event-ticket payloads** (`TKT-XXXX`) by matching `public_bookings.ticket_ids`; returns `subject.kind='event_ticket'` with `event_id`, `event_title`, `booking_id`.
- `_decide` adds two branches: event_ticket→approved on hybrid/check_in_only; `check_in_only` kind approves any active subject without restricted-location check.
- Scan endpoint now stamps **direction** (`entry` / `exit`). Same subject scanned twice today → second scan is detected as exit and linked back to the entry row via `exit_event_id` + `exit_at` (uses `find_one_and_update(sort=…)` because motor's `update_one` doesn't accept sort).
- Hybrid event-ticket approved scans mirror into `db.checkins` so they show up on `/check-ins` and the event's attendee list.
- New `GET /api/security/checkpoint/visitor-log` (device session) + `GET /api/security/checkpoints/{id}/visitor-log` (admin) — one row per (subject, entry) with entry_at + exit_at + still_inside.
- New `POST /api/security/checkpoint/lookup` body `{q}` — searches members + children by name/phone/email/national_id and returns each match with its `household[]` siblings (resolved via `family_id`).
- New `POST /api/security/checkpoint/check-in-batch` body `{members:[{kind,id}]}` — creates one checkpoint event per person + mirrors to db.checkins; broadcasts the last event over the WebSocket.

**Frontend `SecurityCheckpointPage.jsx`**
- Two new toolbar buttons on the security console: **Lookup / Household** + **Logbook**.
- `LogbookDialog` — date picker + table of today's entries with In/Out columns + Inside/Departed badge.
- `LookupDialog` — search input + expanding result cards. Each match shows checkboxes for the matched person AND every household sibling. Submit fires `check-in-batch`.
- Empty-state copy switches based on `checkpoint.device_mode` — single-device shows "Scan a visitor's badge via the reader attached to this device" instead of "Guest device handles NFC/QR pickup".

**Frontend `AdminPage.jsx`**
- Create form gains **Checkpoint mode** + **Device layout** dropdowns.
- Checkpoint rows show pills for kind + device_mode and a new **📋 Logbook** button → `AdminLogbookDialog` with date picker + entry/exit table.
- Fixed minor React hydration warning (`<Badge>` was nested inside a `<p>` — switched the wrapper to a `<div>`).

**Frontend `ProductsPage.jsx`**
- `TabsList` hidden when `isPosKiosk === true` so `/pos/:storeId` URLs render a **POS-only slim shell**. Cashiers can't switch to Products / Invoices / Sales History / Customers tabs from a kiosk-bound device.

### Tests / lint
- New `/app/backend/tests/test_iteration141_security_unification.py` — 18 cases (mode validation, ticket-QR scan flow, hybrid auto-check-in, entry/exit pairing, visitor-log shape, household lookup, batch check-in, single-device pair-guest rejection, etc.). All PASS.
- Backend regression 51/51 still green (smoke + iter91). Combined: **57/57**.
- Ruff (F821/F823/F841/E722/B006) + ESLint clean.

⚠️ **Production redeploy needed**. After redeploy:
1. `/admin → Security Checkpoints` → either edit existing checkpoints (set `kind`/`device_mode`) or create new ones with the new dropdowns.
2. Single-device checkpoints: just open `/security-checkpoint` on the operator device, pair as "Security" — visitor scans via the connected reader.
3. Hybrid checkpoints: at events, simply scan attendee tickets — they're auto-checked into the event.
4. `/pos/:storeId` URLs render as slim POS-only kiosks.

### Carryovers (P3 backlog)
- `routers/security_checkpoint.py` is now 1201 lines — past the 700-line guideline. Worth a refactor pass splitting subject resolution / decision / logbook / lookup into sub-modules.
- ProductsPage isPosKiosk flag persists in localStorage globally — a user who first visits `/pos/loc_X` then goes back to `/sales` on the same device will still see the slim shell until they clear storage. Not a bug per se, just a UX nuance.

## Recently Resolved — Iteration 143 (May 31, 2026)
**Kiosk peripheral permission UX: silent probe + explicit "Enable" button. Lint clean, regression 16/16.**

### Reported issue
*"If scanner or camera is missing in security or kiosk, system should ask permission to use device peripherals if available like cameras etc built in."*

### Design — option `c` chosen by user
Silent probe on page load **+** explicit "Enable camera/NFC" button when permission isn't yet granted **+** subtle fallback when hardware is missing.

### New shared module
**`/app/frontend/src/utils/peripheralPermissions.js`** — covers the standard permissions model (camera, microphone, geolocation, NFC) — orthogonal to the existing `posPeripherals.js` which already handled user-initiated Web Serial / HID / USB / Bluetooth selection. Exports:
- `detectPeripheralAvailability()` — silently enumerates cameras + reports NFC/Serial/HID support
- `getPermissionState(name)` — wraps `navigator.permissions.query`
- `requestCameraAccess()` — fires `getUserMedia({video:true})` then releases the stream
- `requestNfcAccess()` — initialises `NDEFReader` (Android Chrome only)
- `wasAsked() / markAsked()` — `localStorage` flags so we never nag

**`/app/frontend/src/components/PeripheralPermissionBanner.jsx`** — reusable React component. Props: `needs: ['camera'|'nfc'|'scanner'], context, onCameraGranted, onNfcGranted, testid`. Renders 0..N stacked status cards:
- ✅ All peripherals ready → green dismissible "Peripherals ready"
- ℹ️ Camera available + permission `prompt` → blue card + **Enable camera** button
- ⚠️ Camera completely missing → amber "Connect a webcam or use phone" card
- 🛡️ Camera `denied` → rose card with re-enable instructions
- ℹ️ NFC supported on Chrome-Android only — subtle informational note on non-Android
- 🔍 No scanner detected → subtle fallback message pointing to manual entry

Listens to `navigator.permissions.query({name:'camera'}).onchange` so the banner auto-clears the moment the operator grants access via the browser's native prompt.

### Mounted into all three kiosks
- **Security Checkpoint Guest view** (`testid="cp-guest-perm-banner"`) — needs camera + NFC + scanner. Rendered above the "Tap your badge or scan your QR" main panel.
- **Security Checkpoint Security console** (`testid="cp-security-perm-banner"`) — needs camera (for the one-time-entry ID capture). Rendered above the Live Scan card.
- **Check-in Kiosk** (`testid="kiosk-perm-banner"`) — needs camera + NFC + scanner. Rendered between the stats row and the action buttons.
- **POS** (`testid="pos-perm-banner"`) — needs camera + scanner. Rendered above the POS grid.

### Tests / lint
- Backend regression sample 16/16 still green.
- Ruff + ESLint clean.
- Screenshot-confirmed end-to-end: paired a checkpoint as Guest in a headless browser with no camera → the banner correctly rendered the amber "No camera detected" card + the subtle "NFC only on Chrome Android" card, stacked above the main UI.

⚠️ **Production redeploy needed**. Behaviour after redeploy:
- On first visit, kiosks silently probe. If a camera is present but permission was never asked, a blue card appears with the **Enable camera** button — clicking fires the native browser permission prompt.
- Once granted, the banner auto-collapses (Chrome) or simply hides on next mount (other browsers).
- Hardware-missing copy is informational, not a blocker — operators can still use NFC tap, USB scanner, or the manual entry field below.

## Recently Resolved — Iteration 142 (May 31, 2026)
**Security hardening: closed URL-typing bypass + locked Security Contractors out of main app. Pytest 57/57 (regression).**

### Reported issues
1. *"Users are able to see pages they aren't allowed to see as long as they type in the right address."* — Sidebar gates were enforced but the React Router routes themselves had no role/module check. Anyone could deep-link `/financial`, `/hr`, `/admin`, etc. and at least see the page shell.
2. *"Security personnel should not be able to log into the main app."* — `Security Contractor` accounts could log in normally and see the standard staff layout, defeating the purpose of the dedicated checkpoint terminal.

### Fixes

**Route-level access guard (`components/Layout.jsx`)**
- New `routeRules` map built by flattening `NAV_SECTIONS` + a curated list of non-sidebar routes (`/sales-analytics`, `/pos-setup`, `/customer-statements`, `/accounts-receivable`, `/reconciliation`, `/location-analytics`, `/access`, etc.).
- New `useEffect` watches `location.pathname`. When the current path has a rule that fails (`roles` array doesn't include the user's role, OR `module` access missing), it `navigate('/dashboard', {replace:true})` and surfaces a toast. Reacts to changes in all 7 module-access flags (`finance_access`, `hr_access`, …, `restricted_access`).
- Fails OPEN for unlisted routes (since the parent `<StaffRoute>` already keeps guests/security-contractors out).

**Security Contractor pinned to checkpoint (`components/RouteGuards.jsx` + `App.js`)**
- New `KIOSK_ONLY_ROLES` set covering `Security Contractor` / `security_contractor`.
- `StaffRoute`, `AdminRoute`, AND the App-level `ProtectedRoute` (which wraps `/portal`) all redirect kiosk-only roles to `/security-checkpoint` — every entry point covered.
- Post-login `navigate('/dashboard')` is still issued, but the `StaffRoute` guard immediately bounces them; effect is the same as a direct redirect.

### Verification
- **Self-test**: created a Volunteer user via the live API, logged in as them, typed `/financial` in the address bar → redirected to `/dashboard` with toast "You do not have access to that page". Screenshot confirms the sidebar only shows Ministry/Operations/Comms.
- **Backend defence-in-depth**: a Security Contractor token still gets `403` from `/api/financial/donations`, `/api/hr/salaries`, etc. so the frontend redirect is purely UX — the API is the source of truth.
- Pytest regression 57/57 still green (sampled smoke + iter90 module access + iter91 security checkpoint + iter140 peripherals).
- Ruff + ESLint clean.

⚠️ **Production redeploy needed**. After redeploy:
- Any existing `Manager` user without explicit module grants will be redirected away from finance/hr/etc. URLs (already true at the API level since iter 134). Grant access via Admin → Module Access → per-user.
- Any `Security Contractor` user will be force-redirected to `/security-checkpoint` whenever they hit `/`, `/login`, `/portal`, or `/dashboard`.

### Known carryover
- `bank.py` (28 endpoints) and `accounting.py` (16 endpoints) still gate on `require_finance_view`/`admin` rather than the dedicated `require_banking_view` / `require_accounting_view`. This means a user with ONLY a `banking_access` grant (no finance) gets 403 on banking endpoints today. Per-module-only grants will need a follow-up that switches those routers to `require_finance_or_banking_view` helpers. Not a security hole — only restricts a fine-grained delegation pattern.

## Recently Resolved — Iteration 141 (May 30, 2026)
**Kiosk peripherals + auto-badge + dashboard backlog cleanups. Pytest 116/116.**

### (a) Backlog cleanups
- **`hasDirectorAccess()` / `hasManagerAccess()` / `hasStaffAccess()`** centralised in `/app/frontend/src/utils/access.js` — mirrors backend's PRIVILEGED_ROLES so future role-list changes only touch one place. DashboardPage migrated.
- **`useDocumentVisible()`** hook in the same module. `LiveCheckpointWidget` now pauses its 4 s poll when the tab is hidden (saves backend load on background tabs).

### (b) Kiosk peripherals — admin configurable
- New peripheral block in the POS Store Settings dialog (testid `peripheral-settings-block`):
  - `auto_print_receipt` — auto-fires `window.print()` 600 ms after a sale completes
  - `auto_issue_badge` — automatically issues + prints a kiosk/check-in/security badge for visitors without one
  - `badge_label_size` — business_card / lanyard / adhesive_label / A6
  - `print_mode` — browser dialog OR silent (requires `--kiosk-printing` Chrome flag)
- Persists in the existing `store_settings` collection (no schema migration — Mongo is permissive). Settable per-location.

### (c) Backend — unified auto-issue endpoint
- New `POST /api/badges/auto-issue` (require_staff). Body `{subject_kind: member|child|guest|user, subject_id}`.
- Idempotent: returns the existing badge with `was_created=false` if one exists; creates a fresh one with `was_created=true`, `issued_via='auto_kiosk'`, full audit otherwise. Resolves photo, role, location, country from the appropriate collection.

### (d) Frontend wiring
- **POS** (`ProductsPage.jsx`): post-sale `setTimeout(() => window.print(), 600)` when the store has `auto_print_receipt`.
- **Security Checkpoint** (`SecurityCheckpointPage.jsx`): security console gains an **"Issue + Print Badge"** button (testid `cp-issue-badge-btn`) on approved scans where the subject is a real person. Opens `/badge/<token>?print=1` in a popup → WalletBadgePage auto-fires `window.print()`.
- **Check-in Kiosk** (`KioskPage.jsx`): new `kioskAutoIssueBadge()` runs after a successful QR check-in, gated by the active location's `store_settings.auto_issue_badge`. Errors now toast clearly so kiosk staff can diagnose printer/auth issues.
- **WalletBadgePage**: `?print=1` query param triggers automatic `window.print()` 700 ms after render.

### Tests / lint
- New `/app/backend/tests/test_iteration140_peripherals_autobadge.py` — 6 cases: auth, missing/unsupported fields, unknown subject (404), first-call creates with audit shape, idempotent re-call, store-settings persistence (incl. toggle-off).
- All 110 prior pytest cases still PASS. Total: **116/116 green**. Ruff + ESLint clean.
- UI smoke-confirmed: Peripherals block renders with all 4 controls, badge auto-print triggers only with `?print=1`, visibility-API dispatch handled cleanly, /api/badges/auto-issue idempotent over the wire.

⚠️ **Production redeploy needed**. After redeploy:
1. /sales → **Store Settings** → tick *Auto-print receipt* and/or *Auto-issue + print kiosk badges* per location.
2. Silent printing requires running Chrome with `--kiosk-printing` on the kiosk device.
3. Auto-issued badges are stored in `wallet_badges` like any other — re-printable from the member's profile anytime.

### Known carryovers (P3 backlog)
- `routers/members.py` is now 1846 lines and `routers/security_checkpoint.py` is 913 — both flagged by the testing agent for a dedicated split-into-sub-routers iteration.
- WalletBadgePage fires `window.print()` twice in dev StrictMode (cosmetic — production unaffected). A `useRef` guard could clean this up.
- Auto-issue endpoint returns an existing badge even if the underlying member record was deleted (orphan); low priority.

## Recently Resolved — Iteration 140 (May 30, 2026)
**Phase 3 security-checkpoint follow-ups: staff OCR + supervisor override + dashboard widget + multi-language OCR. Pytest 110/110.**

### (a) Staff-auth OCR endpoint (`/api/ocr/id`)
- Refactored the Gemini-vision pipeline into `_ocr_id_image(image, language, log_id)` so both the security checkpoint AND any authenticated staff workflow can call it.
- New `POST /api/ocr/id` (Bearer auth) accepts multipart `{image, language?}` and returns the same envelope `{name, date_of_birth, id_number, raw_text, confidence, language_hint}`.
- Frontend `MemberForm` (used by `/people` Members tab → edit) gains a **"Scan ID"** button (`member-ocr-btn`). Uploading an ID photo pre-fills any empty name / date_of_birth / national_id fields — never overwrites typed values. Toast confirms with confidence + field count.

### (b) Multi-language OCR hint
- Optional `language` form field (`en|fr|es|pt|sw|lg|ar|ru|uk|zh|ja|ko|th|hi|am`) injects a script hint into Gemini's system prompt: e.g. `"The document is most likely in Arabic script (right-to-left)."` Improves accuracy on non-Latin IDs and asks the model to transliterate when a Latin variant is printed on the document.
- The response echoes the resolved `language_hint` so the UI can persist the operator's choice.

### (c) Supervisor override for denied exits
- New `POST /api/security/checkpoint/receipt-override` (security-mode session). Body `{event_id, supervisor_pin, reason?}`.
- Resolves the PIN against `users` where role ∈ {admin, system_admin, Executive Director, Adviser, Director, Manager} and status=active. Bad/non-supervisor PIN → 401.
- Flips the event decision `denied → approved`, appends a `supervisor_override` audit (supervisor_id/name/role + reason + original_decision/reason + timestamp), extends `clear_at` so the guest display flips to CLEARED for 15 s, broadcasts via the WebSocket.
- Frontend `ReceiptScanDialog` now shows a **"Supervisor override"** button whenever a scan returns denied. The reveal form takes a masked PIN + reason; on success the banner flips to CLEARED with a green supervisor-override note.

### (d) Live Checkpoint Widget on Dashboard
- New `GET /api/security/dashboard/checkpoints` (Director+) returns active checkpoints with `paired_devices`, `recent_events[≤5]`, `today_approved`, `today_denied`, `holding_ids`. **Pairing PIN is stripped from the response** so dashboard viewers can't memorise it.
- Frontend `LiveCheckpointWidget` on the Dashboard auto-polls every 4 s. Rendered only for Director+ (admin / system_admin / Executive Director / Adviser / Director). Hides itself when there are 0 active checkpoints.
- Each row shows location, paired-device count, today's totals, IDs being held, and the most-recent scan tile (color-coded by decision).

### Tests / lint
- New `/app/backend/tests/test_iteration139_ocr_override_dashboard.py` — 14 cases: TestStaffOcrId × 6 (auth + bad input + happy + language echo), TestReceiptOverride × 6 (auth + bad PIN + happy + audit shape + re-override 400 + unknown event 404), TestDashboardCheckpoints × 2 (auth + shape).
- All 96 prior pytest cases still PASS (16 smoke + 15 iter115 + 16 iter116 + 12 iter90 + 23 iter91 + 14 iter138).
- Total: **110/110 green**. Ruff + ESLint clean. No Mongo `_id` leakage.

### Testing-agent observations (informational, not blocking)
- `DashboardPage.jsx` role gate is a hard-coded array — fine for now but ripe for a `hasDirectorAccess()` helper if RBAC roles ever shift.
- `LiveCheckpointWidget` could pause polling when `document.visibilityState !== 'visible'` to save bandwidth on background tabs.
- `routers/security_checkpoint.py` is now ~896 lines — a future refactor candidate (OCR helpers + override + dashboard could split into sub-routers).

⚠️ **Production redeploy needed**. After redeploying:
1. Staff can scan IDs on member profiles via `/people` → edit → **Scan ID**.
2. Security can override denied exit-scans by entering any Manager+ supervisor PIN.
3. Directors see live checkpoint stats on the Dashboard automatically.

## Recently Resolved — Iteration 139 (May 30, 2026)
**Security Checkpoint Phase 2 — OCR + exit-restricted flag + WebSocket push. Pytest 96/96.**

### (a) Gemini-powered ID OCR
- New `POST /api/security/checkpoint/ocr-id` endpoint (security-mode session token required). Accepts JPEG/PNG/WEBP up to 8MB, falls back to magic-byte sniffing when MIME is `application/octet-stream` (common from camera blobs).
- Uses `emergentintegrations.llm.chat` + **gemini-3-flash-preview** vision model with strict-JSON system prompt; tolerates ```json fences and extracts the first `{ ... }` block defensively.
- Returns `{name, date_of_birth: YYYY-MM-DD, id_number, raw_text, confidence: high|medium|low}`. Empty fields when unreadable.
- Curl-verified with a PIL-rendered Uganda national ID: extracted "JOHN ALI MUKASA" / "1985-03-15" / "CM85031512345" / `confidence='high'`.
- Frontend `OneTimeGrantDialog` now runs OCR on both camera-snap AND file-upload paths. UI shows `cp-ocr-loading` then `cp-ocr-result` with confidence-coloured badge + extracted fields. **Auto-fill is soft** — only writes to empty form fields; operator's typed name always wins.
- Graceful **503** when `EMERGENT_LLM_KEY` is missing — operator can still grant manually.

### (b) `is_exit_restricted` product flag
- Added to `ProductCreate` / `ProductUpdate` models. Persists in `db.products`.
- Frontend product edit dialog: new amber-highlighted checkbox row (`product-exit-restricted-checkbox`) with explainer copy.
- `POST /api/sales` enriches every cart item with the flag from its product so historical sales retain the policy even if the product flag is later toggled.
- `POST /api/security/checkpoint/scan/receipt` now denies departure (`decision='denied'`) when any sale item carries the flag — end-to-end verified.

### (c) WebSocket real-time push for paired devices
- New `@router.websocket("/checkpoint/ws")` accepts `?session=<token>`, validates against `security_checkpoint_sessions`, joins a per-checkpoint in-memory room (`_checkpoint_rooms`).
- `_broadcast_to_checkpoint()` hooked into `scan`, `grant-one-time`, `scan/receipt`, and `finish` — every state change pushes `{type:'event', event:{...}}` or `{type:'clear'}` to both devices instantly.
- Frontend GuestView + SecurityView open a `wss://…/api/security/checkpoint/ws?session=…` socket alongside the existing 1.5s poll. **Polling kept as fallback** — if WS closes/errors, the page stays current silently.

### Tests / lint
- New `/app/backend/tests/test_iteration138_ocr_exit_ws.py` — 14 cases: OCR (auth + bad-input + happy path with `pytest.skip` if LLM key missing) + product flag persistence + sale enrichment + receipt-scan denial + WS joined/event/clear lifecycle + invalid-token rejection.
- All 82 prior pytest cases still PASS (16 smoke + 15 iter115 + 16 iter116 + 12 iter90 + 23 iter91).
- Total: **96/96 green**. Ruff + ESLint clean.

⚠️ **Production redeploy needed**. After redeploying:
- OCR will work automatically — `EMERGENT_LLM_KEY` is already in `backend/.env`.
- To use the exit-restriction flow, edit any product → tick **"Flag as exit-restricted"**, then run the security checkpoint receipt exit-scan.

## Recently Resolved — Iteration 138 (May 30, 2026)
**Security Checkpoint Kiosk MVP — paired dual-device gate access for restricted locations. Pytest 82/82.**

### Data model
- `security_checkpoints` — one per gate; carries `pairing_pin` (6-digit), `location_id`, `active`, `requires_id_for_one_time`.
- `security_checkpoint_sessions` — paired device session tokens (hashed), 12h TTL.
- `security_checkpoint_events` — every scan + decision audit row (entry_scan, exit_scan, one_time_grant).
- `security_one_time_entries` — physical-ID holds (name, phone, reason, id_image_url, granted_at, id_returned).
- `security_pair_attempts` — anti-brute-force log per IP.

### Backend — `routers/security_checkpoint.py`
- **Admin** (Director+): `POST/GET/PUT/DELETE /api/security/checkpoints` + `POST /{id}/rotate-pin` + `GET /{id}/events` + `GET /{id}/one-time`. Every mutating action audited.
- **Device pairing** (no auth): `POST /api/security/checkpoint/pair` body `{pin, mode:'guest|security', device_label?}` returns a session token; bad PIN → 401 (0.4s tarpit) → 6+ bad attempts/60s → 429.
- **Device session** (auth via `X-Checkpoint-Session` header):
  - `POST /scan` body `{scan_type:'nfc|qr|manual', payload}` — auto-resolves subject from `wallet_badges`, `users`, `members`, `children` (bare UUIDs, `mem_/chd_` ids, badge tokens all work), runs `_decide()` against checkpoint location, writes event with `clear_at = now + 15s`.
  - `GET /state` — poll endpoint for both devices; returns `current` event + history (security only).
  - `POST /finish` — manually clear the current event.
  - `POST /grant-one-time` (security only) — multipart form with `name, phone, reason, id_image`. Stores image in cloud (or `/api/uploads/checkpoint-ids/` local fallback), creates an event with `decision=approved kind=one_time_grant`.
  - `POST /one-time/{id}/return-id` — flips physical ID as handed back to guest.
  - `GET /one-time/open` — lists IDs currently being held.
  - `POST /scan/receipt` — exit-scan stub: looks up sale → returns items + `decision='denied'` if any item has `is_exit_restricted=true`.

### Decision engine (`_decide`)
- Director+ → implicit approval anywhere.
- Active resident of the restricted location → approved.
- Explicit `location_ids` membership → approved.
- `has_restricted_access=true` flag → approved.
- Else → denied with a clear reason.

### Frontend — `pages/SecurityCheckpointPage.jsx`
Single route `/security-checkpoint` (no Layout wrapper, public for paired devices) with three views:
- **Pair view** — 6-digit PIN entry + Guest/Security mode picker + optional device label.
- **Guest view** — full-screen approval display. Captures NFC via Web NDEFReader (Android Chrome) and keyboard-emulated barcode scanners (rapid keystrokes + Enter). Large green/red badge + subject photo + name + reason. Auto-clears 15s after a scan or on tap.
- **Security view** — operator console: Live Scan card, Recent Activity (last 20), Holding-N-IDs sidebar (with "Return ID" button per row), Receipt Exit-Scan dialog, One-Time Entry dialog (camera capture + image upload + name/phone/reason).
- **Lock screen** — temporary local lock (re-uses the pairing PIN as the unlock check).
- Polls `/state` every 1.5s.
- `securityCheckpointApi` in `services/api.js`. Axios interceptor exempts `/security/checkpoint/*` from auto-redirect to /login.

### New role
- `Security Contractor` added to `ROLE_LEVELS` (level 3.5, between Volunteer and Member) — they can be created via `/admin` (UserCreateDialog + UserEditDialog now expose the role) and PIN-login like POS cashiers. They never reach any privileged module.

### Admin UI — `pages/AdminPage.jsx`
- New **Security Checkpoints** card → dialog with create form + per-checkpoint list. PIN visible to admins (with tracking-widest font for readability), one-click **Rotate PIN** (revokes paired devices) and **Delete**.

### Tests / lint
- New `/app/backend/tests/test_iteration91_security_checkpoint.py` — 23 cases (admin CRUD + pair good/bad PIN + scan paths + state guest vs security + finish + one-time-grant happy/forbidden/missing-id + return-id + receipt 404 + audit + rotate-pin revocation). All PASS.
- All 59 prior pytest cases (16 smoke + 15 iter115 + 16 iter116 + 12 iter90) still PASS.
- Total: **82/82 green**. Ruff + ESLint clean.

### Phase 2 follow-ups (intentionally out of MVP scope)
- OCR auto-fill on the ID photo (currently a stub — security types name/phone manually; image stored as evidence).
- Per-line-item `is_exit_restricted` admin UI on products + full receipt approval flow (the data path is wired; admins just can't flag items yet).
- WebSocket-based device sync to replace the 1.5s HTTP poll.
- Strict per-IP rate limiting middleware (currently using a tarpit + per-IP counter; not a true sliding-window middleware).

⚠️ **Production redeploy needed**. Post-deploy steps:
1. Admin → `/admin` → **Security Checkpoints** card → Create one for each restricted location.
2. Create a `Security Contractor` user with a PIN (optional — paired devices don't need a user account thanks to the pairing-PIN flow).
3. On each device, open `/security-checkpoint` → enter PIN → pick Guest or Security mode.

## Recently Resolved — Iteration 137 (May 30, 2026)
**Public marketplace: Resource (asset) booking tab. Pytest 59/59, lint clean.**

### Backend
- New `GET /api/public/resources?country=` — returns only resources where `is_bookable=true`, `staff_only != true`, `available != false`, and not consumables. Country filter walks the location parent chain just like `/public/venues`.
- New `POST /api/public/bookings/resource` body `{name, email, phone?, resource_id, booking_date, start_time, end_time, purpose?}`:
  - Validates the resource exists + is publicly bookable.
  - Detects overlap conflicts on the same `resource_id + date` → **409** with friendly message.
  - Inserts into `public_bookings` with `type='resource', status='pending'` AND mirrors into `resource_bookings` (with `source: 'public'`) so staff see the hold immediately on `/resources`.
- Curl-verified: empty → bookable resource created → public list shows it → booking succeeds → overlapping booking returns 409.

### Frontend (`PublicBookingsPage.jsx`)
- New **"Book Resource"** TabsTrigger placed between Book Space and My Orders (testid `public-tab-resources`).
- Resource cards display name, type, category, capacity/quantity, hourly rate (when set).
- Resource booking dialog mirrors the venue flow: name/email/phone + date/start/end + purpose. Toast confirms with booking ID.
- New `publicApi.resources()` + `publicApi.bookResource()` in `services/api.js`.

### Why production "looked" missing
On production, **no resource has `is_bookable=true`** flagged on it (the 4 seed resources — Conference Room A, Main Auditorium, PA System, Youth Hall — all have `is_bookable=null`). The tab now renders the empty state "No bookable resources available." Once staff edit a resource and tick "Bookable" via `/resources`, it will appear on the public marketplace.

⚠️ **Production redeploy needed**. After redeploy:
1. Open `/resources` as admin/director.
2. Edit any resource you want publicly bookable → tick **"Bookable"** → Save.
3. Visit `/marketplace` → **Book Resource** tab will list it.

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
