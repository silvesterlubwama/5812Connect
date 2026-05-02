# 58:12 Connect — Changelog

## Iteration 82 (May 2, 2026) — Mark-as-Paid + Boards Admin Filter
**Verified 14/14 backend tests PASS + frontend 100%.**
- **Mark-as-Paid toggle for non-cash sales**:
  - `POST /api/sales` auto-sets `payment_status='paid'` for cash, `'pending'` for mobile_money/card/bank_transfer/cheque
  - New `PUT /api/sales/{id}/payment-status` endpoint — flips paid↔pending; reverting clears `paid_at` + `payment_reference`
  - Sales History table shows orange "Mark as Paid" button on pending rows + green "Paid" badge when settled
  - Admin-only ↺ revert button to flip paid→pending if recorded in error
  - Payment reference (transaction ID) captured via prompt on mark-paid
  - "UNPAID" label shown on POS receipt, customer profile history, AND public `/receipt/{rn}` verification page
- **Boards filter for admins** (breaking change, per user request):
  - `list_boards` + `_can_access_board` rewritten — admins now follow the same rules as regular users
  - Visible only if: user tagged, user created, user has task on board, board in user's campus scope (active_campus + location_ids + sub-locations), OR board is_global AND not restricted/private
  - Restricted/private boards require explicit tagging — even admins can't see them unless tagged

## Iteration 81 (May 2, 2026) — Refactor + Polish
**Verified 13/13 backend tests PASS + frontend 100%.**
- **financial.py split (1458→1003 lines)** + 3 new focused routers:
  - `routers/sales.py` (227 lines) — Sale CRUD, drafts/parked, /sales/by-receipt
  - `routers/products.py` (154 lines) — Product CRUD + variant management + barcode generation
  - `routers/sheet_import.py` (111 lines) — Google Sheet financial importer
- **Customer profile receipt-tracking UI** — clickable customer rows in Sales → Customers tab open a profile dialog showing Total Spent / Transactions / Last Visit cards + full receipt history with mono-font receipt numbers and "View" buttons that open `/receipt/{number}` in new tab
- **Auto-detect printer paper size** — Receipt component uses `window.matchMedia('(max-width: 60mm/90mm/160mm)')` heuristic to pick 58mm/80mm/A5; falls back to 80mm if no match. Manual override via Store Settings still wins.
- **Inline approve/decline on expense list** — pending expenses now show `✓ Approve` and `✕ Reject` buttons inline (visible only to finance admins). Reject prompts for reason. No more dedicated tab needed.

## Iteration 80 (May 2, 2026) — Critical Bug Fixes + Receipt Overhaul + Sheet Import
**Verified 12/12 backend tests PASS + frontend confirmed.**
- **Bug fixes (P0):**
  - Starting balance "no account id" — `/financial/accounts` now auto-creates and returns account `id` + `starting_balance`
  - Expense workflow status-based — pending expenses excluded from monthly_expenses & cashflow_out totals; new `pending_expenses_total/count` fields on summary; visual badge in expense list
  - Variant edits not saving — `ProductUpdate` model now accepts `variants`; main `stock` auto-recomputed from variant totals
  - HR & Payroll nav hidden — `setCampusFeatures` now reads `hr_enabled`; `canAccess` no longer requires explicit campus selection
  - Restricted locations leak — `GET /api/locations` filters non-admins to their assigned locations + non-restricted children only
  - Chat org structure — Organization sidebar expanded by default with role count badges, presence dots, sorted Adviser→ED→Director→Manager→Leader→Coordinator→Staff→Volunteer
  - Expense deletion lag — explicit `fetchAll()` after delete to refresh totals
- **Receipt overhaul (P1):**
  - Traceable receipt number `INV-YYYYMMDD-NNNN` via atomic `db.counters` (no race conditions)
  - 58:12 logo + tracking QR code on receipt (configurable per kiosk)
  - Per-kiosk receipt paper size: 58mm / 80mm / A5 / A4
  - New `Receipt.jsx` component with full salesperson/customer/items/total breakdown
  - Public `/receipt/:receiptNumber` page (no auth) — QR target for verification
  - Variant stock decrements when sold (variant qty + main stock together)
  - WhatsApp share button when customer phone available
- **Park / Parked Sales (P1):**
  - "Park Sale" button saves cart as draft (shared per campus)
  - "Parked (N)" dialog lists drafts with Reopen/Discard buttons
  - New endpoints: `GET/POST /api/sales/drafts`, `DELETE /api/sales/drafts/{id}`
- **Google Sheet financial integration (P2):**
  - Extended `expenses` schema with `vendor`, `purpose`, `receipt_number`, `account`, `department`, `budget_category`, `usd_equivalent`
  - Add Expense form has expandable "Advanced" section for these fields
  - New `POST /api/financial/import-sheet` accepts CSV-paste with the 58:12 spreadsheet column headers; auto-normalizes DD/MM dates and currency-prefixed amounts
  - Import dialog on Financial page

## Iteration 79 (May 1, 2026) — Performance + Admin + Refactor
- **MongoDB indexes audit**: `_ensure_indexes()` runs on every startup (idempotent). Adds 40+ indexes including `sessions.jti` (unique), TTL on `password_resets.expires_at`, `sessions.expires_at`, and `deleted_items.deleted_at` (30d auto-cleanup). Unique `push_subscriptions.subscription.endpoint`.
- **Session manager**: JWTs now include `jti`. Login persists a session record (user_agent, ip, expires_at) in `db.sessions`. New endpoints: `GET /api/auth/sessions` (list + `is_current` flag), `DELETE /api/auth/sessions/{jti}`, `POST /api/auth/sessions/revoke-others`. Logout now revokes the current jti. Settings → Security page has an "Active Sessions" card with "Sign out other devices" button.
- **Push notifications wired up**: `WebSocketContext.js` auto-calls `subscribePush()` 2s after WebSocket connect. VAPID keys already configured.
- **Birthday / anniversary reminders**: Daily scheduler (08:00 UTC) inserts in-app notifications for members whose `date_of_birth` or `join_date` matches today's MM-DD. Idempotent (skips if already fired today). Staff accounts get "Work anniversary"; others get "Member anniversary".
- **`server.py` split**: 1151 → 782 lines (-32%). New routers:
  - `routers/seed.py` (4 seed endpoints)
  - `routers/dashboard.py` (dashboard + people stats + parent portal)
  - `routers/i18n.py` (translations + webcal feed)
- **`UnifiedPeoplePage.jsx` extraction**: `MemberForm` (~90 lines) moved to `components/people/MemberForm.jsx` — now reusable.

## Iteration 78 (May 1, 2026) — Continuation: HR + UI Polish + PWA
- **HR auto-payday payslip**: `POST /api/hr/payslips/generate-payday` — finds campuses with `pay_day` matching today, generates missing payslips for current period. Idempotent. "Run Payday Now" button added to HR → Payslips tab.
- **Multi-campus user creation**: `POST /api/admin/users` now accepts `location_ids` array; mirrors to member record; auto-expands with parent campuses via `resolve_parent_campus`.
- **Finance dialogs**: replaced 4 `window.prompt()` call sites with proper shadcn Dialog forms — Transfer (From/To/Amount/Currency/Notes), Budget (Department/Period/Amount/Category), Revalue Asset (Value/Method/Notes), Set Starting Balance.
- **Variant barcode printing**: new `VariantBarcodePrint` component (JsBarcode CODE128) with 4 layouts (4×6, 3×8, 2×5 grid, single/page), copies multiplier, show-name/show-price toggles, print-preview + `window.open` print. Button on product card + inside Edit dialog's Variants section.
- **PWA Wallet Passes offline**: `sw.js` now has dedicated `WALLET_CACHE` with cache-first + stale-while-revalidate for `/api/wallet-badge/*` and `/badge/:token`. `prefetch-wallet-pass` message handler pre-caches pass URLs on demand. `WalletBadgePage` automatically posts prefetch message when badge loads.

## Iteration 78 (May 1, 2026) — Routing/Filtering Fixes
- Task assignee dropdown: now campus-scoped & staff-only (excludes Guest/Parent/Member)
- `get_campus_filter` in deps.py: excludes restricted sub-locations for non-admins
- Campus switcher: multi-campus non-admins can now switch among their assigned campuses (was admin/ED only)
- Chat: `/chat/users` used everywhere (no more ghost users from /members)
- Volunteer scheduling: staff list scoped to active campus; Linked Event auto-fills title/date/start/end/location
- Calendar: tasks with `due_date` now render as blue "task" events and click-navigate to board
- Admin-tier role guard: only system_admin can assign admin/system_admin/Executive Director roles (create_user, admin_update_user, bulk_update_users)

## Iteration 77 (Apr 30, 2026)
- Reports page fully rewritten to match API response format
- Financial transfers + budgets UI tabs added
- Asset valuation: appreciation default, revalue button, method badge
- HR auto-payslip generation on payday

## Iteration 76 (Apr 30, 2026)
- Sales portal customer creation inline
- Product variants frontend editing
- Reports endpoint /api/reports/summary added
- HR toggle on campus settings

## Iteration 75 (Apr 30, 2026)
- Financial accounts with starting balance
- Inter-account transfers (expense→income pair)
- Budgeting per sub-location/department
- Admin-editable financial categories (14 defaults)
- Asset appreciation/depreciation valuation
- Product variants + auto-barcodes (country_code prefix)

## Iteration 74 (Apr 27, 2026)
- Restricted access: children + guests checked as residents
- Chat: conversation delete, group member management, message delete (before read)
- Orphan cleanup endpoint

## Iteration 73 (Apr 27, 2026)
- Child sponsor toggle + sponsor name field
- Child badge: parents + campus info on front
- Children + guests type-ahead search

## Iteration 72 (Apr 27, 2026)
- Child edit: Add Parent button + typed search (staff + guests)
- Parent names shown on child cards
- ChildTag badge: parents with phones, campus contact

## Iteration 71 (Apr 26, 2026)
- Resident batch assignment (members + children + guests)
- Public guest access request (no auth, temp badge)
- Kiosk access validation (QR/NFC/fingerprint)
- Fingerprint database CRUD

## Iteration 70 (Apr 26, 2026)
- Phone number login (normalization)
- Phone-last-4 check-in at kiosk

## Iteration 69 (Apr 26, 2026)
- Customer accounts CRUD with auto-guest linking
- Purchase history tracking
- Sales portal customer search

## Iteration 68 (Apr 26, 2026)
- Google Auth security fix (pending status)
- StaffRoute guard (guests → portal)
- Sales portal (PIN + last name login, lock mode)
- Portal self-service (badge + PDF)

## Iteration 67 (Apr 25, 2026)
- Profile PDF download (weasyprint)
- Sub-location financial accounts

## Iteration 66 (Apr 25, 2026)
- Full HR module (salaries, payslips, contracts, document requests)
- Sale deletion restores stock
- Campus switcher for directors (sub-locations)
- Resident search includes guests + children
- Sponsored children tracking

## Iteration 65 (Apr 25, 2026)
- Default password Test@5812!
- Password reset email notification
- Guest profile editing dialog

## Iteration 64 (Apr 25, 2026)
- Finance delete buttons (assets, sales)
- Comprehensive testing (45/48 backend, 100% frontend)

## Iteration 63 (Apr 25, 2026)
- Children import fixed (correct endpoint, parent creation)

## Iteration 62 (Apr 25, 2026)
- Financial campus isolation (all endpoints filtered)

## Iteration 61 (Apr 25, 2026)
- Dashboard action widgets (overdue, pending, expiring, unassigned)
- Email notifications (task assignment, check-in)

## Iteration 60 (Apr 25, 2026)
- Template download buttons (authenticated fetch)

## Iteration 59 (Apr 25, 2026)
- Error boundary, bulk delete confirm, unsaved form warnings

## Iteration 58 (Apr 25, 2026)
- Wallet badge system (shareable URL)
- Cascade deletion on all endpoints
- Frontend data events bus

## Iteration 57 (Apr 25, 2026)
- Children import: parent cache dedup, admin campus fallback
- Badge bg restored (dark default, white kiosk only)
- Timezones expanded (50+)
- Venue CRUD + group types in campus settings

## Iteration 56 (Apr 25, 2026)
- User directory endpoint (cross-campus)
- Outreach location/venue selectors
- Bi-monthly + quarterly recurrence

## Iteration 55 (Apr 25, 2026)
- Staff-guest linking, portal button fix
- Country code field, guest individual delete
- ID Number rename, group removed from staff, donor tag removed
- Kiosk locked mode (no exit)

## Iteration 54 (Apr 25, 2026)
- Profile photo upload UI
- Child edit: typed parent search
- Children at restricted locations: tracked badge
- Staff auto-guest on creation

## Iteration 53 (Apr 24, 2026)
- Real country outlines (world-map-country-shapes)
- CSV template downloads
- Children import enhanced (parents without email)
- Photo upload API

## Iteration 52 (Apr 24, 2026)
- NFC tag writing (director+ only, encrypted)

## Iteration 51 (Apr 24, 2026)
- Badge country watermark, NFC symbol, footer redesign
- NFC tag CRUD

## Iteration 50 (Apr 24, 2026)
- CallContext hooks refactor
- Backend type hints
- Nested ternary cleanup

## Iteration 49 (Apr 24, 2026)
- Kiosk QR camera fix (html5-qrcode)
- Backend function decomposition
- Frontend component splitting
