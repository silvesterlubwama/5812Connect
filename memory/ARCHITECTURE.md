# Architecture & feature map — 58:12 Global Connect CRM
_Audited 2026-06 (iter 317). Numbers verified against the running app._

## Stack
| Layer | What |
|---|---|
| Frontend | React 19 (CRA), React Router, Tailwind + shadcn/ui, lucide-react, sonner, recharts, react-qrcode-logo, html5-qrcode, html2canvas, papaparse/xlsx |
| Backend | FastAPI (uvicorn), Motor (async MongoDB), Pydantic, WeasyPrint (PDF), openpyxl (XLSX) |
| Data | MongoDB — 94 collections |
| Realtime | WebSockets (`routers/websocket.py`) — chat, boards, presence, call signalling |
| PWA | Service worker (`public/sw.js`), offline prefetch on login, wallet-pass cache |
| Scale | 978 registered HTTP routes · 64 backend routers · 76 frontend pages |

## Request path
```
Browser (REACT_APP_BACKEND_URL)
   → Cloudflare → K8s ingress
   → /api/*  → uvicorn :8001
        RateLimitMiddleware (pure ASGI, 120 req/min per client key)
        SecurityHeadersASGI  (pure ASGI — replaced BaseHTTPMiddleware, which
                              caused intermittent "No response returned")
        CORS
        → router → deps.get_current_user (JWT)
                 → deps.get_campus_filter / expand_descendants  ← tenancy
                 → Motor → MongoDB
   → everything else → :3000 (React dev server / static build)
```

## Multi-tenancy & authorisation (the spine)
- **Locations tree**: campus → sub-location, with `is_restricted` flags.
  `locations.visible_locations(user)` is the single resolver (used by
  `/api/locations` and `/api/venues`).
- **`deps.get_campus_filter(user)`** injects the caller's location scope into
  queries; `expand_descendants()` walks the tree so a parent campus sees its
  children. Global-scope roles (admin / ED / Adviser) are unioned in
  explicitly — they carry no `location_id` and would otherwise vanish from
  directories and chat.
- **Campus switcher** (`routers/campus_switcher.py`) sets `active_campus_id`,
  which *narrows* scope for that session.
- **`deps.default_creation_location(user, provided)`** — new records land at
  the user's MAIN campus, not the switched one.
- **Boards, not tasks, carry location.** Task visibility resolves through
  `tasks.resolve_allowed_board_ids(user, restrict_to_locations)` — the shared
  resolver used by `/api/tasks` AND the shared-calendar feeds.
- **Roles** (`utils/access.js` mirrors `deps.py`): system_admin, admin,
  Executive Director, Adviser, Director → Manager → Leader/Coordinator/Staff/
  HR/Volunteer → parent/guest. Plus per-module grants (`hasModuleAccess`) with
  expiry.
- **Auth**: JWT (`routers/auth.py`) + 2FA + WebAuthn/passkeys + biometric/NFC +
  Emergent-managed Google OAuth. Password hashing via bcrypt/passlib (pinned).

## Module → router → page → collection map
| Module | Backend | Frontend | Key collections |
|---|---|---|---|
| Calendar & events | `events.py`, `holidays.py`, `event_tickets.py`, `bookings.py` | `CalendarPage`, `EventDetailTabs`, `TicketTiersEditor`, `EventVenuePicker`, `HolidayPolicyDialog` | events, event_tickets, public_bookings, venues, calendar_share_configs, holiday_policies |
| Tasks & boards | `tasks.py`, `boards.py` | `TasksPage`, `kanban/*` | boards, board_lists, tasks |
| Finance | `finance/{journal,transactions,transfers,receipts,reports,chart_of_accounts,setup,postings,admin}.py`, `financial.py`, `bank.py`, `invoices.py`, `purchase_orders.py`, `statements.py` | `FinancePage` (+ Journal/Overview/Budgets/Dept-P&L panels), `VendorsPage`, `DonorsPage` | finance_journal_entries, finance_chart_of_accounts, donations, expenses, bills, bank_*, accounting_fiscal_periods |
| HR & payroll | `hr.py`, `hr_timesheet_templates.py`, `funds.py`, `approvals.py` | `HRPage`, `PortalProfile`, `PortalTimeOff` | hr_salaries, hr_payslips, hr_timesheets, hr_leave_requests, hr_settings, departments |
| People / families / guests | `members/{core,children,families,guests,badges,nfc,pdf,bulk_import}.py` | `UnifiedPeoplePage`, `PortalFamily` | users, members, children, families, guests, guest_* |
| Access & kiosk | `access.py`, `access_eligible.py`, `security_checkpoint/*`, `biometric_nfc.py`, `webauthn.py` | `AccessAdminPage`, `KioskPage`, `SecurityCheckpointPage`, `WalletBadgePage` | guest_access_*, wallet_badges, checkins, access_logs, checkpoint_events |
| Comms | `chat.py`, `calling.py`, `voip.py`, `conferences.py`, `websocket.py`, `presence.py`, `notifications.py`, `email.py`, `push.py` | `CommsPage`, `IncomingCallModal`, `Dialer` | conversations, chat_messages, call_logs, notifications, push_subscriptions |
| Social work | `social_work.py`, `social_review_forms/*` | `SocialWorkPage`, `CaseDetailDialog` | social_cases, social_review_forms, case_notes, social_child_payments |
| Sales / POS / logistics | `sales.py`, `products.py`, `shipments_pkg/*`, `consumable_sheets.py` | `SalesPortalPage`, `PosKioskPage`, `ShipmentsPage`, `MarketplacePage` | sales, products, customer_accounts, shipments |
| Admin & platform | `admin.py`, `locations.py`, `sublocations_budget.py`, `departments.py`, `settings.py`, `system_settings.py`, `backup.py`, `seed.py`, `analytics.py`, `reports*.py`, `i18n.py`, `import_csv.py` | `AdminPage` (System Console), `LocationsPage`, `SettingsPage`, `ReportsPage` | locations, sublocations, departments, audit_log, activity_log, sessions |
| Portal (self-service) | `portal.py`, `sponsor_portal.py` | `PortalLayout` + `Portal*` pages | (reads across the above) |

## Background jobs (`backend/scheduler.py`)
- Overdue-task emails + director digest (08:00 UTC)
- **Payday payslip generation** (already automated)
- Overdue payment reminders · scheduled customer statements
- Birthday / anniversary notifications
- Auto backup
- Flight-status refresh loop (shipments/passengers)

## Integrations
| Service | Use | Credential |
|---|---|---|
| Wave CloudUCM (Grandstream) | softphone / PBX | user's own |
| Resend | transactional email | user's API key |
| Google OAuth | social login | Emergent-managed |
| Emergent object storage | file/photo/document uploads | platform |

## Cross-cutting frontend wiring
- `services/api.js` — one axios instance, JWT interceptor, ~60 typed API objects.
- `services/dataEvents.js` — pub/sub so sibling panels refresh after a mutation
  (`finance-changed`, `data-changed`) instead of forcing a page reload.
- `context/AuthContext` — session, role, active campus.
- Deep links everywhere: `/calendar?event=`, `/tasks?task=`,
  `/portal/expenses?expense=`, `/people?tab=pending`, `/access?filter=expiring`.
- `data-testid` on interactive + critical elements (automation contract).

## Known fragility (not a bug today)
`server.py` imports every router inside ONE `try/except` that logs a
**warning**. If one router fails to import, every router after it silently
never registers and the app still boots. Recommend per-router import with an
ERROR log.
