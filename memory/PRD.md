# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Recently Resolved — Iteration 208c (Feb 2026)
**Mobile responsiveness audit across admin pages.**

- Hardened global mobile CSS in `index.css`: every `<table>` now scrolls horizontally below 640px (no more clipped columns); `grid-cols-3` collapses to single column unless a `sm:/md:/lg:` variant is explicitly set; `grid-cols-12` allows horizontal scroll; dialog padding tightened; `role=tablist` scrolls horizontally; card headers wrap.
- **Tasks/Kanban page** was completely unusable on phones (224px sidebar ate over half the viewport). Refactored to a slide-in drawer: hidden by default on `<sm`, opened via new `mobile-boards-toggle` button in the board header, closes automatically when a board is selected. Backdrop click dismisses.
- Verified fix visually on `/financial`, `/hr`, `/accounting`, `/tasks`, `/admin`, `/dashboard` at iPhone-13 viewport (390×844). All pages usable with no horizontal page-level overflow.

## Recently Resolved — Iteration 208 (Feb 2026)
**Finance ↔ Accounting Trial Balance drift fixed + Chart-account balance cache + hot-path indexes.**

- **Drift fix**: delete handlers in `financial.py` (`delete_donation`, `delete_expense`, bulk variants) now cascade-reverse the auto-posted journal entry via `_reverse_auto_posted_je`. Audit trail preserved; net ledger effect = 0.
- **Retroactive repair**: `POST /api/financial/repair-orphaned-journals` (admin-only, idempotent) reverses every auto-posted JE whose source donation/expense was deleted. Dev DB run reversed 186 pre-existing orphans; second run 0 (idempotent ✓). UI: `acc-repair-orphans-btn` on Accounting page.
- **Hot-path indexes** (in `server.py::_ensure_indexes`): `chart_accounts.id/location_id/assigned_user_ids`, `donations.deposit_to_account_id`, `expenses.paid_from_account_id + status`, `sales.deposit_to_account_id`, `chart_account_transfers.{from,to}_account_id`, `accounting_entries.{auto_generated_from,source_id}` + `{status,is_reversed}`. Eliminates full-collection-scans on every balance read.
- **In-process TTL cache** (5s) for `_batch_compute_balances` in `chart_accounts.py`. Invalidated on: donation/expense create+delete+approve+reject, sale insert, transfer, bulk-delete.
- **Tested**: iter207 (9/9) + iter208 (8/8) backend regression. Trial balance still balanced. No regressions.

## Recently Resolved — Iteration 207 (Feb 2026)
**Payslip PDF export + HR Onboarding Checklist.**

- Server-rendered payslip PDFs at `/api/hr/payslips/{id}/pdf` (WeasyPrint, branded, A4). PortalProfile now downloads instead of browser-printing.
- `/api/hr/onboarding/checklist` — 5-check completeness matrix per staff (dept, location, contract, salary, chart-account) + summary counters.
- New HRPage "Onboarding" tab shows gaps at a glance so new hires can be brought to payslip-ready state fast.

## Recently Resolved — Iteration 206 (Feb 2026)
**Reversal line-status bug fix + HR Payslip self-service workflow.**

- Fixed the "reversed transactions still counted as income" bug (`reverse_entry` was leaving `accounting_entry_lines.status='draft'`).
- Added `/api/accounting/entries/repair-reversal-lines` (one-time backfill for existing data — production needs this) + `/entries/bulk-reverse` alongside bulk-delete.
- HR: `days_worked_override` + `pto_days_override` on payslip generate; approved timesheets auto-feed generation; staff-submitted timesheets with manager approval; `/hr/payslips/mine` self-service.
- Payroll expense on mark-paid auto-tags `paid_from_account_id` from `store_settings.default_cash_account_id` so cash account balances update automatically.
- PortalProfile: "My Payslips" (Review + Print/PDF) + "My Timesheets" (submit + track status).
- HRPage: "Timesheets" tab for manager approve/reject with status + period filters.
- **14/14** iter 206 pytest pass (regression from missing decorator flagged by tester → fixed).

## Recently Resolved — Iteration 204 (Feb 2026)
**Finance edit/delete UI restored + POS auto-tag + batch balance perf.**

- CoA / Journals / Taxes tabs on Accounting page now expose Edit + Delete icons (backend endpoints already existed).
- POS sales auto-tag `deposit_to_account_id` from `store_settings.default_cash/bank/momo_account_id`. Explicit callers override. Products page → store settings dialog surfaces the 3 pickers.
- `_batch_compute_balances` reduces list-view balance queries from O(6·N) to O(5) constant.
- `test_iter204_finance_edit_delete_and_pos_autotag.py` → **16/16 pass**.

## Recently Resolved — Iteration 203 (Feb 2026)
**Chart cash accounts with per-user assignments (cash / bank / mobile money accountability).**

### User Request
> "In finances, allow admin to assign certain accounts (balances) to a user, such that when that user is entering an expense or donation, they can choose between the balances they are assigned to whether cash, mobile money or another, then a deduction is made according to that balance. […] users can see balances/funds they are assigned to under accounting so they can stay accountable. Keeps accounts restricted except for that purpose or explicit permission as before."

### Delivered
- **NEW router** `chart_accounts.py` at `/api/financial/chart-accounts/*` — CRUD, list (auto-scoped), `mine`, transactions/ledger, transfers, assignees.
- Account fields: name, kind (`cash|bank|mobile_money|credit|petty_cash|other`), currency, starting_balance, location_id, campus_id, assigned_user_ids, notes, active.
- Live balance = starting_balance + inflows (donations, sales, transfers-in) − outflows (approved expenses, transfers-out). Pending expenses do NOT affect balance.
- Access rule: **non-admin can only reference an account if their user id is in `assigned_user_ids`.** Admins bypass. `create_donation` / `create_expense` enforce this at 403.
- `SaleCreate.deposit_to_account_id` + `DonationCreate.deposit_to_account_id` added (mirror of `ExpenseCreate.paid_from_account_id`).
- Frontend Accounting page: new "Cash Accounts" tab with admin CRUD, assign-users, transfer, ledger view. Non-admins see only their assigned accounts.
- Frontend Financial page: expense + donation forms picker fed by `chartAccountsApi.mine`.

### Testing
- `test_iter203_chart_accounts.py` → **22/22 pass** via testing_agent_v3_fork iter 203.

## Recently Resolved — Iteration 202 (Feb 2026)
**Finance bulk delete + expense "Paid From" account picker.**

### Delivered
- `ExpenseCreate.paid_from_account_id` added — expenses can now be tagged with the funding account.
- Bulk-delete endpoints for donations, expenses, assets, budgets (financial.py) and journal entries (accounting.py, posted entries skipped — must reverse instead).
- FinancialPage.jsx: bulk select + BulkActionBar on donations, expenses, budgets, and assets tabs; expense form gained a "Paid From" account picker showing live balances and "balance after this expense" preview.
- AccountingPage.jsx: multi-select on entries with bulk-delete + skipped-count feedback.

### Testing
- `test_iter202_finance_bulk_delete_and_paid_from.py` → **15/15 pytest pass** (testing_agent_v3_fork iter 202).

## Recently Resolved — Iteration 201 (Feb 2026)
**Accounting reversal correctness + hide-by-default UI.**

### Bug (three-part user report)
1. "Reversal creates the reversal entry but original still shows as active" ← original wasn't being marked
2. "Reversal button does nothing / errors" ← reversal entry was left as `draft` so it never affected the ledger
3. "Some worked and others duplicate when reversed" ← no guard against double-reverse

### Fix (`routers/accounting.py`)
- `POST /entries/{id}/reverse` now:
  1. **Marks the original** with `is_reversed=true`, `reversed_by=<new_id>`, `reversed_at`, `reversed_by_user`
  2. **Auto-posts the reversal** (not draft) so the ledger actually cancels the original
  3. **Idempotent**: second reverse on the same entry returns the existing reversal instead of creating a duplicate
  4. **Links** the reversal back with a `reverses=<original_id>` field
- `GET /entries` gained an `include_reversed=false` default query param. Hides both the original AND its reversal by default. Pass `?include_reversed=true` to see both.

### Sales visibility
- `GET /api/sales` gained `include_voided=false` default. Voided sales no longer show in the sales list unless the caller opts in.

### Frontend (`AccountingPage.jsx`)
- New "Show reversed entries" checkbox in the Journal Entries tab. Off by default — passes `include_reversed=true` when checked.
- When shown, reversed pairs render at 60% opacity + strike-through on the entry number, with an inline "reversed" / "reversal" badge showing the link.
- The Reverse action button is now hidden on entries that are either already reversed OR are themselves reversals — no more "some duplicated on reverse" symptom.

### Testing
- New `test_iter201_accounting_reversal.py` → **4/4 pytest pass**:
  - Reversal marks the original with `is_reversed` + `reversed_by`
  - Second reverse returns the same reversal (idempotent)
  - Default list hides both original and reversal
  - `include_reversed=true` shows them again

### Explicit deferrals (scoped for next session)
1. **Bulk delete on all finance sub-pages** — user asked for Transactions, Journal, Sales, Reversals, Accounts, Budgets, Assets. This touches 4 route files + 4 page files + safety rules (drafts vs posted, orphaned lines, cash reconciliation). Deferred so the reversal fix isn't blocked behind a much larger surface.
2. **"Paid from" account picker on expense entry** — needs a UI change on the expense form + a `paid_from_account_id` field on expenses + a balance-summary query per account. Straightforward but medium scope.

Both are queued as the next iteration's focus.

## Recently Resolved — Iteration 200 (Feb 2026)
**Acquired vs Packed vs Transport-mode split — the shipment now separates "what's donated" from "what's actually going on the container".**

### Data model
- Items grew two new fields: `qty_packed` (int, default 0) and `transport_mode` (enum: `container` / `suitcase` / `holdback`, default `container`).
- `qty_acquired` and `qty_packed` are **independent counters**. Packing 15 units of a 20-acquired item leaves acquired at 20; the delta represents held-back stock.
- `_normalise_item` accepts + validates both new fields; unknown modes fall back to `container`.

### New endpoints
- **`POST /api/shipments/{id}/items/{item_id}/pack`** (admin) — body `{qty, mode}`. Increments `qty_packed` by `qty`, sets `transport_mode` to `mode`. Response includes `over_packed: bool`.
- **`POST /api/public/shipments/{token}/items/{item_id}/pack`** (PIN editor) — same behaviour, gated by the shipment edit-token.
- `public_update_item` allowed set extended with `qty_packed` and `transport_mode` so PIN editors can also correct these directly.

### Two-tier public visibility on `GET /api/public/shipments/{token}`
- **No PIN (anonymous browser)** → returns a **stripped wishlist** payload. Each item exposes ONLY: `id, name, category, qty_needed, qty_acquired, photo_url, priority, source_url, source_retailer`. Weight, dims, pallet placement, image_urls, ISBN/UPC, container_type, transport_mode, qty_packed are ALL stripped. `container_dims_cm`, `pallets`, `ai_packing_text` are also hidden. Container weight totals only count `container`-mode items so the public gauge doesn't leak suitcase counts.
- **With `?edit_token=X` (PIN unlocked) OR admin JWT** → full manifest with everything the admin sees.
- Response includes `unlocked: bool` so the frontend can toggle its own UI.

### Frontend
- **Admin (`ShipmentsAdminPage.jsx`):** each item row now shows a `🚢/🧳/⏸ Packed N/M` badge (red when over-packed, blue when partially packed, grey when nothing packed) + a 📦 button. Clicking 📦 opens a **Pack dialog** with quantity + mode dropdown. On submit → toast + list refresh.
- **Donor (`ShipmentDonorPage.jsx`):** `refresh()` now passes `?edit_token=X` to the public GET whenever the editor is unlocked, so the packing manifest actually renders after PIN.

### Testing
- New `test_iter200_pack_and_visibility.py` → **9/9 pytest pass**:
  - Pack action increments `qty_packed` without touching `qty_acquired`
  - Over-packed flag fires when packed > acquired
  - Invalid mode rejected (400)
  - Anonymous public view strips `weight_kg`, `dims_cm`, `pallet_id`, `qty_packed`, `transport_mode`, `image_urls`, `isbn`, `upc`
  - Anonymous view hides `container_dims_cm`, `pallets`, `ai_packing_text`
  - Unlocked view (with edit_token) shows everything including `weight_kg` + `qty_packed`
  - New items default to `qty_packed=0`, `transport_mode='container'`
  - Suitcase mode accepted on create
  - Unknown modes fall back to container

## Recently Resolved — Iteration 199 (Feb 2026)
**Bulk "Find links (AI)" button — one-tap link every un-purchased wishlist item.**

### Frontend (`ShipmentsAdminPage.jsx`)
- New **🤖 Find links (N)** button in the items header, visible only when there are items with `source_url` empty AND `qty_acquired < qty_needed` (i.e. still on the wishlist).
- Runs sequentially through the missing set so the AI backend isn't hammered in parallel. Progress spinner + failure count shown in the closing toast (`Linked 8 · 2 failed`).
- Confirm dialog before running so a coordinator with a 200-row CSV doesn't accidentally fire 200 Gemini calls.
- Refreshes the item list after — 🛒 Buy badges appear on every newly-linked row.

### Also: pushed back on the "code quality report"
Reviewed each item against actual code — most items were false positives (e.g. `htmlEscape.js` doesn't call `document.write`, it's the mitigation) or intentional (`/* ignore */` on hardware-cleanup catches). Documented the triage instead of applying blind sweeps that would degrade the codebase.

## Recently Resolved — Iteration 198 (Feb 2026)
**Find-link AI + buy-link surfacing for not-yet-acquired items.**

### Backend (`routers/shipments.py`)
- **NEW** `POST /api/shipments/{id}/items/{item_id}/find-link` (admin) — given an item with no `source_url`, asks Gemini-3-flash to pick the best retailer for its category and returns a **guaranteed-working search URL** (not a deep ASIN/SKU which would 404). 19 retailers supported: Amazon, Walmart, Target, eBay, Home Depot, Lowe's, Harbor Freight, Best Buy, IKEA, Wayfair, **MAC.bid**, AbeBooks, Better World Books, Tractor Supply, Buy Buy Baby, Dick's, Decathlon, Henry Schein, AliExpress.
- Smart fallback: if the item has an ISBN and the picked retailer is book-friendly, the query uses the ISBN (more specific). If the item has a UPC, the query uses the UPC. Saves `source_url`, `source_retailer`, `source_found_at` on the item.
- `public_update_item` allowed-set extended with `source_url` so PIN editors can also paste a manual link they sourced.

### Frontend (`ShipmentsAdminPage.jsx`)
- The existing **Estimate from URL** dialog now has a second action: **🤖 Find link** — calls the new endpoint, fills the URL field, persists `source_url` in one click.
- Every wishlist item that has a `source_url` now shows a **🛒 Buy [retailer] ↗** inline link. Volunteers click straight from the items list to the retailer's pre-filled search.

### Testing
- New `test_iter198_find_link.py` → **4/4 pytest pass**:
  - Find-link returns a real search URL with retailer + query
  - Find-link persists `source_url` + `source_retailer` on the item
  - PIN editors can save a manual `source_url` via the public update endpoint
  - Admin items endpoint accepts placeholder items correctly
- Combined regression: **54+ tests still green** across iter 186 / 189 / 194 / 195 / 197 / 198.

## Recently Resolved — Iteration 197 (Feb 2026)
**Imperial/metric per-shipment toggle + smart input parser + retail-aware AI prompt.**

### New modules
- `backend/shipment_units.py` — pure parsers + formatters for dimensions and weight.
  - `parse_dim_to_cm(value, units)` — accepts `33`, `33"`, `2'9"`, `2ft 9in`, `0.84m`, `84cm`, `200mm`, etc. Bare numbers fall back to the shipment's unit preference.
  - `parse_weight_to_kg(value, units)` — accepts `5`, `5lb`, `5 lbs`, `5lb 8oz`, `8oz`, `2.3kg`, `2300g`.
  - `format_dim_cm(cm, units)`, `format_weight_kg(kg, units)` for display.
- `frontend/src/services/shipmentUnits.js` — JS mirror so input/display round-trips client-side too.

### Storage stays canonical (cm + kg)
- Shipments have a new `units` field (`"metric"` default, `"imperial"` opt-in). `POST /api/shipments` accepts `units` on create; `PUT /api/shipments/{id}` allows `units` swap.
- `_normalise_item(data, units)` runs all weight/dim/x/y/z inputs through the unit parser. So a packer can type `2'9"` and the backend stores `83.82`. Round-tripping `83.82 → "2'9""` on display gives the same string back.

### Frontend (`ShipmentsAdminPage.jsx`)
- New **cm/kg ↔ ft·in/lb·oz** toggle in the totals card. Flipping it PUTs `units` and re-renders all dim/weight strings instantly.
- Item editor dimensions + weight changed from `<input type="number">` to `<input type="text">` with smart placeholders (`e.g. 2'9" or 33in`). The value renders via the formatter so reopening the dialog shows the same human string the user typed.
- All inline item rows + pallet badges + totals card use the formatters — units flip immediately propagates to the whole UI.

### AI prompt upgrade
The Gemini scan prompt now explicitly references **Amazon, Walmart, eBay, Target, Home Depot, Lowe's, AbeBooks, MAC.bid, Costco, IKEA, AliExpress, and Alibaba** as the cross-reference sources for description / dimensions / weight / price. Response schema gained a new `source` field so the UI can later show "verified via Amazon" / "estimated from eBay" provenance.

### Testing
- `test_iter197_units.py` (pure-fn, 19/19 pass) covers every parse + format case.
- `test_iter197_units_endpoint.py` (live API, 10/10 pass) verifies imperial inputs survive the full POST→Mongo→GET round-trip — including the hero `2'9"` → 83.82cm and `5lb 8oz` → 2.494kg cases.
- Combined backend regression: **50/50 pytest pass** (units 19 + units endpoint 10 + dedupe 14 + helpers 8).
- Lint clean across all changed files.

## Recently Resolved — Iteration 196 (Feb 2026)
**Modularization, single pass — shipments security + PBX helpers carved out.**

### `backend/shipment_security.py` (NEW)
Extracts the entire shipment PIN / edit-token security layer out of `routers/shipments.py`:
- Constants: `_PIN_SECRET`, `_PIN_SALT`, `EDIT_TOKEN_TTL_HOURS`
- `hash_pin(pin)` — SHA-256 salted PIN hash
- `make_edit_token(shipment_id, ttl_hours=12)` — HMAC-signed session token (1–24h)
- `verify_edit_token(token)` — returns `shipment_id` or `None`
- `require_shipment_editor(request, token)` — FastAPI dependency that accepts a logged-in admin JWT, header `X-Shipment-Edit-Token`, or query-param `?edit_token=…`
- Lazy `from deps import db, _decode_jwt` keeps the module leaf-importable.
- `routers/shipments.py` now imports + re-exports under the old `_hash_pin`/`_make_edit_token`/`_verify_edit_token`/`require_shipment_editor` names, so all call sites + route signatures stay untouched.

### `backend/pbx_helpers.py` (NEW)
Pure (no-DB) validators + id helpers from `routers/pbx.py`:
- `pbx_now()`, `gen_pbx_secret()`, `pbx_id(prefix)`
- `validate_extension_number(num)` — regex `[1-9][0-9]{1,5}`
- `validate_pattern(pat)` — Asterisk dialplan grammar
- `routers/pbx.py` imports + aliases as `_now`, `_gen_secret`, `_id`, `_validate_extension_number`, `_validate_pattern`. `_next_extension_number` stays in `pbx.py` because it queries `db`.

### Combined effect
- `shipments.py` shed ~80 lines of security code.
- `pbx.py` shed ~25 lines of pure helpers.
- Three helper modules in `backend/` now form a stable, testable foundation: `shipment_helpers.py` (placement), `shipment_security.py` (PIN/token), `pbx_helpers.py` (validation/id).
- No route paths changed. No HTTP behaviour changed. Re-export shims preserve all old internal names.

### Testing
- **22/22 pytest pass** in the unit + integration suites I exercised post-refactor:
  - `test_iter186_dedupe.py` (14 — dedupe, prune, autostack, TTL)
  - `test_iter195_shipment_helpers.py` (8 — pure placement)
- **5/5 pytest pass** for `test_iter194_kiosk_warmup.py` + `test_iter189_scan_photo_ai.py`
- Live curl on `GET /api/pbx/extensions` returns 200 — PBX router boot is clean.
- Backend lint clean across all 4 touched files.

### Explicit deferral — `server.py` scheduler
`_run_due_date_reminder_scheduler`, `_fire_overdue_task_emails`, `_fire_scheduled_customer_statements`, etc. reference ~10 module-level names in `server.py` (`logger`, `db`, `_send_push_to_user`, `_fire_birthday_anniversary_notifications`, `_fire_overdue_payment_reminders`, `_fire_payday_payslip_generation`, `_fire_auto_backup`, `_last_auto_backup_date`). Extracting these cleanly needs dependency injection, not a copy-paste — that's a dedicated session.

## Recently Resolved — Iteration 195 (Feb 2026)
**First safe modularization carve-out + mobile fix on the donor photo previews.**

### Mobile fix (`ShipmentDonorPage.jsx`)
- The X-to-remove button on each scan photo preview used `opacity-0 group-hover:opacity-100` — invisible on touch devices where hover doesn't exist, so phone donors couldn't remove a bad photo. Now `opacity-100 sm:opacity-0 group-hover:opacity-100`: always visible on mobile, hover-only on desktop. Button bumped from 5×5 to 6×6 with a slightly darker background for better contact on small screens.

### Modularization (slice 1 of N)
- New `backend/shipment_helpers.py` — pure (no-DB) helpers extracted from `routers/shipments.py`. First extraction: `auto_place_on_pallet(item, existing_items, pallets)`. Same algorithm, now unit-testable in isolation.
- `routers/shipments.py` imports `auto_place_on_pallet` from the new module and delegates. A back-compat `_auto_place_on_pallet` shim stays so any straggler call sites keep working.
- **Pattern proven safe** — module imports, route paths, MongoDB writes all untouched. This is the template for further carve-outs.

### Testing
- New `test_iter195_shipment_helpers.py` — **8/8 pytest pass** (loose untouched, unknown ctype untouched, lightest pallet picked, respects caller's pallet_id, stacks lighter-on-heavier with z_cm, similar weights stay side-by-side, never stacks on already-stacked, brand-new shipment still gets assigned). Runs in 0.02s — no DB, no HTTP.
- Integration suite still **17/17 pass** (iter186 dedupe + iter194 warmup). Lint clean.

### Deferred (explicit)
- Remaining shipments.py carve-outs (PIN/HMAC helpers, scan-item endpoint, persistence helper) — proven pattern, can roll forward in next session.
- `pbx.py` / `server.py` modularization — separate sessions.
- Multi-language i18n — out of scope per your direction.
- Surplus redistribute picker — out of scope per your direction.

## Recently Resolved — Iteration 194 (Feb 2026)
**Proactive kiosk cache warming — turn cold mornings into instant offline-ready check-ins.**

### Backend (`routers/events.py`)
- New `GET /api/checkins/kiosk-warmup?event_id=...&limit=500` (auth required). Returns a thin directory of `{parent, children}` entries scoped to the event's campus (or the operator's active campus when no event is selected). Cap 50–1000, default 500.
- Implementation pulls `db.guests` where `is_parent=True` and the matching `db.children` rows (by `family_id` or `parent_ids`). Keeps payload minimal — id/name/phone/email/photo_url only.

### Frontend (`CheckInsPage.jsx`)
- New `useEffect` watching `parentEventId`: on each event selection, fires the warmup endpoint and seeds `kioskCache` against every key a kiosk operator might tap or scan (parent id, phone, email, name). Best-effort — failures are silently ignored since the next manual lookup still works.

### Testing
- New `test_iter194_kiosk_warmup.py` → **3/3 pytest pass**: directory shape, limit respected, auth required. Combined backend regression still 17/17 (14 iter186 + 3 iter194).

## Recently Resolved — Iteration 193 (Feb 2026)
**P2 sweep: offline kiosk QR caching + verified pre-existing PWA/barcode infra.**

### Offline QR scanning for kiosk (NEW)
- New `services/kioskCache.js` — small localStorage-backed LRU (max 200, TTL 12h) for kiosk lookups. Stores by lookup key (QR code / phone / member id) scoped per use-case (e.g. `parent:<lookup>`).
- `CheckInsPage.jsx` now caches every **successful** `parentLookup` (both QR scanner branch + manual form). On API failure that smells like a network drop (`err.response` missing OR 5xx 502–504), falls back to the cached match and shows `toast.warning('Offline — showing cached match')`.
- Cached only on success — never poisons the cache with 404s. Read only as a fallback so the canonical online path stays authoritative.
- Cleaned up a pre-existing dangling orphan JSX block at the bottom of `CheckInsPage.jsx` that was triggering a parser-error blocker.

### Verified already-shipped P2 items
- **PWA service worker** — `frontend/public/sw.js` exists (wallet-pass caching, prefetch message handler) and is registered in `src/index.js`. `WalletBadgePage` already messages the SW to prefetch on load. ✓ done.
- **Bulk barcode printing UI** — `BulkBarcodeLabelDialog` and `VariantBarcodePrint` both exist and are wired into Resources + Products pages. ✓ done.

### Deferred (genuinely require dedicated sessions)
- `server.py` / `pbx.py` / `shipments.py` modularization — too risky for a single pass per the user's "watch out for existing paths" guidance.
- Multi-language i18n — every page touches user-facing text; needs a coordinated translation effort, not a one-shot.
- Mobile responsiveness audit — broad scope, needs per-page review with a real device.

## Recently Resolved — Iteration 192 (Feb 2026)
**P1 polish pass: flashlight torch, auto-placement explainer badge, 24h editor session.**

### 1. Flashlight torch in live barcode scanner (`ShipmentDonorPage.jsx`)
- New `scanStreamRef` keeps the MediaStream we acquire via `getUserMedia` so we can call `track.applyConstraints({advanced:[{torch:bool}]})` to toggle the flashlight.
- Capability probe via `track.getCapabilities().torch` — button only renders on devices that actually support it (most modern Android phones, Chrome only). Hidden on iOS Safari which doesn't expose torch.
- 💡 / 🔦 icon button overlays the top-right of the video feed. Amber background when on.

### 2. Auto-placement explainer badge (`ShipmentsAdminPage.jsx`)
- Each item card now shows a **🤖 Auto-placed** indigo badge when the row carries `auto_placed` or `auto_stacked` flags.
- Native `title=` tooltip explains the placement: e.g. *"Auto-assigned to 'Pallet B' (lightest pallet at the time). Stacked on top of 'Toolbox' (heavier, sturdier base) at z=25cm"*. Looks up the parent item by id from the live items array.
- `data-testid` on the badge for testing.

### 3. Configurable editor session length (`routers/shipments.py` + donor login dialog)
- `_make_edit_token` now accepts optional `ttl_hours` (capped between 1 and 24).
- `POST /api/public/shipments/{token}/login` reads `ttl_hours` from request body — defaults to 12, validates and clamps to 24. Response includes the actual `ttl_hours` used.
- PIN login dialog has a new "Stay signed in for 24 hours (long pack day)" checkbox. Submit sends the appropriate `ttl_hours`.

### Testing
- Extended `test_iter186_dedupe.py` with `TestEditTokenTTL` → **14/14 pytest pass**: default 12h, opt-in 24h, capped at 24h when caller asks for 999. Frontend lint clean for changed code.

## Recently Resolved — Iteration 191 (Feb 2026)
**Live barcode camera now opens reliably; photo mode supports true multi-shot capture.**

### Bug A — Live barcode "Camera not available" on production
- `ShipmentDonorPage.jsx` was calling `BrowserMultiFormatReader.listVideoInputDevices()` BEFORE the browser had asked for camera permission. On Safari + most Chrome builds, that returns devices with empty labels and frequently empty `deviceId` values → no device picked → "Camera not available" toast → forced switch to photo mode.
- **Fix:** Run `navigator.mediaDevices.getUserMedia({video: {facingMode: { ideal: 'environment' }}})` FIRST. This triggers the permission prompt, immediately populates device labels, AND gives us a working MediaStream we attach to the `<video>` element so the user sees the feed instantly. ZXing then decodes against that already-running stream. Tracks are stopped on dialog close so the camera light goes off.
- Secure-context guard added: if `navigator.mediaDevices.getUserMedia` is undefined (HTTP / unsupported browser), gracefully fall back to photo mode.

### Bug B — Photo mode could only pick one image at a time
- The combined `<input type="file" multiple capture="environment">` is broken on mobile: `capture` forces single-shot camera mode in iOS Safari and most Android browsers, so `multiple` was ignored.
- **Fix:** Split into two input pickers side-by-side:
  - 📷 **"Take photo"** — `capture="environment"`, single-shot, **appends** to `scanImages` so a donor can snap front → back → spine in three taps.
  - 🖼️ **"Pick from gallery"** — no `capture`, `multiple` works → Ctrl/⌘-click in the OS file picker. Appends too.
- Up to 3 photos total. Removed-on-hover X button per preview thumbnail. Counter shows `N/3 photos`. Input `value` is reset after each pick so the same file can be re-selected if the donor changes their mind.

## Recently Resolved — Iteration 190 (Feb 2026)
**Broader AI item vocabulary + automatic pallet placement & stacking.**

### Expanded AI categories (`routers/shipments.py`, scan-item prompt)
- Gemini's allowed categories grew from the original 9 to: **Books, Clothing, Food, Toys, Medical, Electronics, Household, Furniture, Tools, Construction, School, Agriculture, Sports, Toiletries, BabyGear, Bicycle, Other.**
- Prompt explicitly names construction/agricultural inputs (cement bags, rebar, PVC pipes, solar panels, seeds, fertilizer), tools (hammers, drills, wheelbarrows), furniture (chairs, tables, mattresses), baby gear (strollers, car seats), bicycles, and gives realistic weight anchors for heavy/bulky items.

### Auto-placement (`_auto_place_on_pallet` in `_add_or_merge_item`)
- When a new item's `container_type` is **pallet/box/tote** AND `pallet_id` is missing → assigned to the **lightest** pallet by current total weight. Response sets `auto_placed: true` so the UI can show a "placed on pallet X" toast.
- When a `pallet_id` is set but `parent_id` is missing → auto-stacks on the **heaviest existing bottom-layer item** on that pallet, IF our item is < 90% of the heaviest's weight (otherwise stays side-by-side). Sets `parent_id`, `z_cm` (= bottom item height), and `auto_stacked: true`.
- Loose floor items (`container_type='container'`) are never auto-placed.

### Testing
- Extended `test_iter186_dedupe.py` with `TestAutoStack` → 4 new tests, **all 11/11 pytest pass**: lightest-pallet selection, loose container not re-assigned, lighter-on-heavier stacking with correct z_cm, similar-weight items stay side-by-side.

## Recently Resolved — Iteration 189 (Feb 2026)
**Photo+AI shipment scanner failed in production — always returned "Unknown" / low confidence.**

### Bug (two layers)
1. `_persist_shipment_image` called `await upload_bytes(...)` from `storage.py`, but that module only exposes a SYNC `put_object()`. The await raised an exception, so **every** photo silently fell through to the disk fallback.
2. The disk fallback returned a relative URL (`/uploads/shipments/{name}`) with no `/api/` prefix, and the AI scan code then re-downloaded the photo via `httpx.get(image_urls[0])` — which obviously fails on a relative URL. The exception was swallowed, the AI got an empty file, and the response always became `name="Unidentified item"`, `ai_confidence="low"`.

### Fix (`routers/shipments.py`)
- AI path no longer re-downloads anything. Raw bytes are captured during upload and written straight to the temp file Gemini reads.
- `_persist_shipment_image` now correctly calls the sync `put_object` via `asyncio.to_thread`, returning the cloud-storage URL when available.
- Disk fallback URL is now `/api/uploads/shipments/{name}` (was missing the `/api/` prefix, would have been unreachable from the frontend through the kubernetes ingress).

### Testing
- New `test_iter189_scan_photo_ai.py` — **2/2 pytest pass**: photo-only scan returns 200 with properly-shaped image URLs (https:// or `/api/…`); ISBN+photo mode still hits Google Books fast path.
- Full regression: **18/18 pytest pass** across iter 183 (scanner+waybill), iter 186 (dedupe+prune), iter 189 (photo AI).

## Recently Resolved — Iteration 188 (Feb 2026)
**Shipment PIN login no longer kicks donors back to main login page.**

### Bug
- Donors entering the wrong PIN on `/donate/shipment/{token}` were getting redirected to the main app `/login` page instead of seeing an "Incorrect PIN" toast. Same behaviour any time an editor session expired and an API call returned 401.
- Root cause: the global axios 401-interceptor in `services/api.js` does `window.location.href = '/login'` on every 401 unless the URL matches an allowlist. `/public/shipments/{token}/login` and `/public/shipments/{token}/items` (with expired edit token) weren't in that list.

### Fix
- Added `/public/shipments/` to `LOGIN_PATHS_SKIP_REDIRECT` in `services/api.js`. Wrong-PIN now surfaces the existing toast in `submitLogin()` and stays on the donor page. Expired edit tokens trigger the existing `logoutEditor()` + "Session expired" toast flow already in `saveItemEdit()`.

### Verification
- Production curl confirmed backend accepts the PIN and returns `edit_token` (HTTP 200). The redirect was purely client-side.

## Recently Resolved — Iteration 187 (Feb 2026)
**Auto-prune over-pledged donations — closes the loop on the dedupe + warning work.**

### Backend (`routers/shipments.py`)
- `POST /api/shipments/{id}/prune-over-pledged` (admin only). Walks every item, finds rows where `qty_acquired > qty_needed`, trims `qty_acquired` back to the pledged cap, and appends `{qty, at, by}` to `items[*].surplus_redistributed` for audit so packers can reroute the surplus elsewhere.
- Returns `{ trimmed: [{item_id, name, surplus}], total_surplus }` — empty when no rows are over-pledged (idempotent no-op).

### Frontend (`ShipmentsAdminPage.jsx`)
- New amber **"Prune over-pledged (N)"** button (Scissors icon) appears next to "Import CSV" only when at least one item is over-pledged. Confirm dialog explains surplus is logged but qty drops.
- Counter `totals.overPledged` added to the existing totals memo so the button hides when N=0.

### Testing
- Extended `test_iter186_dedupe.py` → **7/7 pytest pass**: trim correctness, surplus log shape, non-over-pledged untouched, idempotent re-run, admin-required.

## Recently Resolved — Iteration 186 (Feb 2026)
**Shipment inventory deduplication + over-pledge warning — finishes the in-progress task from iter 185.**

### Backend (`routers/shipments.py`)
- `_add_or_merge_item(shipment_id, item)` helper centralises the dedupe path. Both `POST /api/shipments/{id}/items` (admin) and `POST /api/public/shipments/{token}/items` (PIN editor) call it.
- Dedupe key: same `isbn` OR same `upc` AND same `pallet_id` AND same `container_type` → merge by `$inc items.$.qty_acquired`; otherwise insert a new row.
- Response is annotated with `merged: true` when a row was merged and `over_pledged: true` whenever the resulting `qty_acquired > qty_needed`.
- Same-product items on **different pallets** stay as separate rows (intentional — they live in physically distinct locations).

### Frontend (`ShipmentDonorPage.jsx`)
- Both add paths (manual editor dialog + AI/ZXing scan-confirm) now read the API response and surface:
  - `toast.success("Merged with existing — qty now N")` when `body.merged`.
  - `toast.warning("Over-pledged: X/Y for \"name\"")` whenever `body.over_pledged`.
- No new state, no new API calls — purely a richer read of the existing response.

### Testing
- New `test_iter186_dedupe.py` — **5/5 pytest pass**: same-ISBN merge, same-UPC merge, over-pledge flag, different-pallet stays separate, public PIN endpoint dedupes.

## Recently Resolved — Iteration 185 (Feb 2026)
**Client-side ZXing barcode scanner — instant, AI-free ISBN/UPC reading.**

### Frontend
- Mode switcher inside scanner dialog: **Live barcode** (ZXing camera) ↔ **Photo + AI** (existing path).
- Barcode mode opens the rear camera, decodes any common product format (EAN-13, UPC-A, ISBN, Code128), parses ISBN by `978/979` prefix vs UPC/EAN, and POSTs to the existing `/scan-item?isbn=` or `?upc=` endpoint.
- Empty-devices and permission-denied paths both surface a "Camera not available — switch to photo mode" toast and auto-flip to photo mode.
- ZXing dynamically imported (`import('@zxing/browser')`) so it's only loaded when the dialog opens.

### Deps
- `@zxing/browser@0.2.0` + `@zxing/library@0.22.0` (peer dependency — tester caught the missing peer install on a clean tree and added it; now explicit in package.json).

### Testing
- Iteration 185 (testing agent): backend **9/9 pytest pass**, frontend **100% on in-scope UI surface**. Mode switcher renders, both buttons visible, barcode default selected, &lt;video&gt; renders in barcode pane, photo↔barcode switching works, no React hook-order errors, 0 console errors, waybill regression intact.
- One minor fallback edge case flagged + fixed in-iteration: when `listVideoInputDevices()` returns an empty array (vs throwing), explicit toast + auto-flip to photo mode.


**Shipment AI scanner + waybill + extended item model + 3D realism upgrade.**

### Scanner — PIN-gated
- `POST /api/public/shipments/{token}/scan-item` accepts up to 3 images + optional `?isbn` / `?upc`.
- Path priority: external lookup first (Google Books for ISBN, OpenFoodFacts for UPC) → Gemini 3 Flash vision → GPT-4o fallback if Gemini confidence is low.
- Extracted images are persisted to cloud storage with on-disk fallback; URLs returned in the response for audit.
- Auto-extracts ISBN/UPC from photos and re-enriches via Google Books if AI saw an ISBN.
- Returns a candidate item dict (not persisted) — volunteer reviews/edits, then POSTs to `/items` with optional `container_type` + `pallet_id` + `parent_id` (stacking).

### Extended item model
- `container_type` (container / pallet / box / tote), `parent_id` (stack-on-top), `isbn`, `upc`, `author`, `publisher`, `ai_identified`, `ai_confidence`, `image_urls`, `scanned_by_pin_hint`, `scanned_at`. All round-trip cleanly.

### Waybill
- `GET /api/shipments/{id}/waybill` (admin) and `GET /api/public/shipments/{token}/waybill` (PIN) render a printable HTML manifest grouped by pallet, including totals (count, value, weight).
- Public route accepts editor token EITHER via `X-Shipment-Edit-Token` header OR `?edit_token=` query param (so `window.open()` works).

### Frontend (`ShipmentDonorPage.jsx`)
- New 'Scan item' + 'Waybill' buttons appear in editor mode.
- Scanner dialog: camera capture (mobile) / multi-file upload, AI-identify, container_type + pallet + stack-on-parent pickers, Add-to-shipment.

### 3D realism (`ContainerVisualizer.jsx`)
- Hemisphere fill light, shadow-casting key light with bias, warehouse gradient background.
- Wood-coloured pallet material (roughness 0.85), cardboard-style box material with slight transparency.
- Subtle edge outlines on every box/pallet (LineSegments + EdgesGeometry).
- Honors z-offset for stacked items (`b.z`).

### Testing
- Iteration 183: **9/9 backend pytest pass** (`test_iter183_scanner_waybill.py`) — including live Google Books + OpenFoodFacts lookups.
- Iteration 183 (testing agent): backend 100% + frontend 90% — Waybill button bug flagged.
- Iteration 184 (re-test after fix): backend 100% + frontend 100% — bug fully resolved.


**PBX extension v2: auto-sync from staff profile, registrar/FXO trunks, priorities, contact groups, BLF.**

### Auto-sync
- Adding/updating a Staff/Volunteer/Director-tier user with `extension` + `extension_pin` + `forward_to` on their profile auto-creates/relinks a PBX extension (transport=wss, max_contacts=5, auto_provisioned=true). Members/Customers/Guests are skipped.
- The browser softphone (`BrowserSoftphone.jsx`) now always renders its launcher and shows an explicit "no extension assigned" state when the user has none yet.

### Trunks
- New `registrar` field separate from `host` — Asterisk register block uses registrar in `server_uri` / `client_uri`.
- New `trunk_type` (sip | fxo) + `fxo_lines` + `fxo_gateway` for analog lines via ATA gateways.

### Extensions
- `max_contacts` default bumped to 5; -1 (or "Unlimited" UI toggle) maps to Asterisk cap of 50.
- `forwarding_number` adds a second `Dial(Local/...)` leg in extensions.conf before voicemail fallback.
- `is_fax_extension` emits ReceiveFAX dialplan + email shellout to `voicemail_email`.
- Per-extension `skills` already existed; now also reflected in the auto-sync flow.

### Hunt groups + Queues
- Both gained `member_priorities` / `agent_priorities` dicts ({ext_id: int}). Hunt-group dialplan rings same-band concurrently then advances. Queue.conf emits priorities as Asterisk `penalty` so lower = first.
- Queue inbound destination now appends the configured `fallback` (voicemail / extension / hunt group / IVR) so callers exit cleanly on timeout or no-agents-available.

### Contact groups (campus-scoped) + extension groups
- `pbx_contact_groups` collection: name, description, contacts[{name, phone, extension, notes}], shared_with_extension_group_ids[]. Auto-scoped to caller's active campus.
- `pbx_extension_groups` collection: name, extension_ids[], subscribed_contact_group_ids[]. Used as the access boundary for BLF subscriptions.
- `GET /api/pbx/me/contact-groups` returns the union of every contact group the current user can dial from via their extension groups.

### BLF (Busy Lamp Field)
- `GET /api/pbx/blf/peers` returns the extensions a user is allowed to monitor (admins see all in-campus, others see only peers in shared extension groups).

### Registered devices
- `GET /api/pbx/extensions/{id}/contacts` queries the AMI bridge for live SIP contacts; returns empty list cleanly in preview (no Asterisk). Inline `RegisteredDevicesPanel` shows count + UA strings inside the extension dialog.

### Testing
- Iteration 182: **12/12 backend pytest pass** (`test_iter182_extensions_v2.py`). Testing agent run iter 182: backend 100% + frontend 100%, no critical issues. Combined PBX suite **41/41 green** (177+178+179+180+182).


**Call recording (per-extension toggle + retention) + Skill-based queues + Lost-6 verified.**

### Recording
- `GET/PUT /api/pbx/recording-settings` — global retention_days (1..3650), format (wav/wav49/gsm/g722), stereo, announce_recording, storage_path.
- Per-extension `recording_enabled` + `skills` fields on `pbx_extensions` (create + update).
- Dialplan renderer emits `MixMonitor(${UNIQUEID}.<fmt>,b)` before `Dial(PJSIP/...)` for any recording-enabled extension. Beep prefix when `announce_recording=true`.
- `POST /api/pbx/cdr/{call_id}/recording` stamps `recording_url` on the CDR row (Asterisk MixMonitor hits this on file finalisation).
- `POST /api/pbx/recording-retention/purge` unlinks `recording_url` from rows older than the retention window. File deletion happens on the appliance.

### Queues + Skill-based routing
- Full CRUD `/api/pbx/queues`: name, strategy (ringall/leastrecent/fewestcalls/random/rrmemory/linear), agent_extension_ids, required_skills, ring_timeout, wrapup_time, max_wait, MOH, announce flags, fallback.
- `queues.conf` generator emits one `[q-<id>]` section per queue with only those agents whose `skills` set is a SUPERSET of the queue's `required_skills`. Skill-gating happens at config-render time so Asterisk never even tries to ring an ineligible agent.
- Inbound routes accept `destination_type='queue'`; delete-queue cascade resets pointing inbound routes to `hangup`.

### Frontend
- New `Queues` tab with create/edit dialog (strategy, skills, agents with eligibility hint). New `Recording` tab with retention + format + storage path + beep flag + run-purge button.
- Extension dialog gains `recording_enabled` toggle and free-text skills field (comma-separated, with existing-skills hint).
- Inbound destination type now includes `Queue`. Config preview adds `queues.conf`.

### Lost-6 verification (testing agent iter 181)
- **Tasks assignee scope**: code-review verified (TasksPage `boardStaff` filters by STAFF_ROLES + board.location_id).
- **Calendar tasks-due**: visible — CalendarPage maps `tasksApi.list()` due-dates into events.
- **Scheduler scope + auto-time**: confirmed — event selection auto-populates start/end; campus-scoped staff only.
- **Chat ghost users**: backend tightened to STAFF_ROLES + active + exclude self (iter 177 + verified).
- **Campus switcher reset**: 'All My Campuses' option added for non-admin multi-campus users.
- **Restricted locations**: deps.py campus filter applied consistently — confirmed at routes that previously bypassed.

### Testing
- Iteration 180: **10/10 backend pytest pass** (`test_iter180_queues_recording.py`). Combined PBX suite **29/29 green** (iter 177+178+179+180).
- Iteration 181 (testing agent): backend 100% + frontend 100%, no critical issues. Only minor testid-naming cosmetic notes.


**PBX Call Analytics dashboard — admin-only insights from CDR.**

### Backend (`/api/pbx/cdr/analytics`)
- Single aggregate endpoint, `?days=` (1..365, default 30), optional `?user_id=` to scope to one staff member.
- Returns `summary` (total, incoming, outgoing, missed, answered, avg_duration_sec, missed_ratio), `daily` breakdown, `top_numbers` (10), `top_contacts` (10 matched CRM records), `top_staff` (10, omitted when filtering by user_id), and a 24-entry `busiest_hour` table.
- Pure MongoDB aggregation — no Python-side fan-out, scales with collection size.

### Frontend (`PBXAnalytics.jsx`)
- Mounted as the 7th tab in `PBXAdminPage`. KPI tiles (total / incoming / outgoing / missed+ratio / avg-duration), CSS sparkline for daily counts, a 24-square heatmap for hour-of-day, and three side-by-side tables (top numbers / top matched contacts / busiest staff).
- Range selector (7 / 14 / 30 / 60 / 90 / 180 days) + manual refresh. No charting lib — dependency-free.

### Testing
- Iteration 179: **6/6 backend pytest pass** (`test_iter179_analytics.py`) — summary totals, daily breakdown shape, top_numbers + top_contacts correctness, 24-entry busiest_hour with sum invariant, user_id filter zeroes top_staff, unauthenticated 401/403.
- Aggregate suite (iter 177 + 178 + 179): **19/19 green**.


**PBX softphone "Recent Calls" panel — mini-CRM in the floating widget.**

### Backend
- `POST /api/pbx/cdr/log` — idempotent CDR row insert (upsert on `{id, user_id}`). Persists direction, peer, duration, status, plus a snapshot of the matched CRM record (kind/id/name/link) so the row keeps working even if the record is later deleted.
- `GET /api/pbx/cdr/me?limit=20` — calling-user-scoped recent calls, newest first.

### Frontend (`BrowserSoftphone.jsx`)
- New Dial / Recent tab switcher (with count badge).
- `callMetaRef` tracks call lifecycle (call_id, direction, accepted flag, matched record) and `endCall` logs the CDR on every session end/failure.
- Recent list shows colored direction icons (outgoing/incoming/missed), CRM-resolved name (falls back to digits), timestamp + duration, and hover actions for "Call back" and "open record".
- Outgoing-call lookup mirrors the incoming-call screen-pop so outbound rows also get matched records in history.

### Testing
- Iteration 178: **4/4 backend pytest pass** (`test_iter178_cdr.py`) — log+retrieve round-trip, idempotency on duplicate call_id, user-scoping, missed-call status. Iteration 177 suite still 9/9 green.


**PBX Phase 3 (screen-pop + time-of-day routing) + chat/campus filtering hardening.**

### PBX Phase 3
- Browser softphone screen-pop on incoming calls: `newRTCSession` event fires `GET /api/pbx/phone-lookup`, resolves caller to member/user/guest/family, shows toast + "Open record" link in the incoming-call ringer.
- Time-of-day routing UI in `PBXAdminPage.jsx` inbound route dialog — per-window day picker (Mon..Sun), start/end HH:MM, override destination type+target. Multiple windows supported; first-match wins, falls through to default destination.
- `_render_extensions` honors `time_conditions`: emits Asterisk `GotoIfTime(HH:MM-HH:MM,day&day,*,*?tc-N-active)` labels per window plus the override `Dial(...)` line.
- `/api/pbx/phone-lookup` now returns a stable singular `kind` (member/user/guest/family) derived from the collection name (previously returned 'people' for members).

### Lost-6 follow-up fixes
- `/api/chat/users` tightened to STAFF_ROLES (admin..Volunteer + Security Contractor) AND `status="active"` AND `id != current_user`. No more Members/Customers/Guests/soft-deleted users showing up in chat.
- Layout campus switcher now offers "All My Campuses" reset to multi-campus non-admins (previously only system admins saw the reset).
- Backend lint fix in `pbx.py` (`_to_ms` one-line if/except → multi-line) — this had taken down backend startup at the fork point.

### Testing
- Iteration 177: **9/9 backend pytest pass** (`/app/backend/tests/test_iter177_phase3.py`). Covers phone-lookup (short input, unknown, member match), `/chat/users` staff-only scope, time-of-day dialplan render, campus switcher (admin any-campus, non-admin 403), admin directory filter.


## Recently Resolved — Iteration 176 (Feb 2026)
**In-app PBX — Phase 2 (live runtime + browser softphone + click-to-call).**

### AMI bridge (`/app/backend/pbx_ami.py`)
- Dependency-free async Asterisk Manager Interface client. One-shot socket per action (connect → login → action → logoff).
- High-level helpers: `safe_reload()`, `safe_list_registrations()` (PJSIPShowContacts + PJSIPShowRegistrationsOutbound), `safe_originate()`. All degrade gracefully when `AMI_SECRET` is unset (skipped/empty rather than 500).

### PBX router upgrades
- `POST /api/pbx/apply` — replaces Phase-1 stub. Calls `safe_reload()` to fire `Reload` on the live Asterisk.
- `GET /api/pbx/registrations` — merges DB roster with live AMI state. Each extension row now includes `registered`, `user_agent`, `contact_uri`, `roundtrip_ms`.
- `POST /api/pbx/originate` — click-to-call backbone. Rings the operator's extension first; on answer Asterisk bridges to the target via the matching outbound route.
- `GET /api/pbx/me/softphone` — returns the calling user's WSS extension + secret + WSS URL. 204 when no extension.
- `GET /api/pbx/me/click-to-call-config` — lightweight extension info for call buttons; 204 when no extension.

### Browser softphone (`BrowserSoftphone.jsx`)
- JsSIP-based WebRTC SIP UA. Global floating widget — self-mounts in Layout, renders nothing until the user has a WSS extension.
- Registration status pill (idle / registering / registered / failed / disconnected / **unconfigured**).
- Full dial pad with DTMF, paste-from-clipboard, mute / hold / hangup, incoming-call ringer, in-call duration timer.
- Listens for `window.dispatchEvent('softphone-dial', {detail:{number}})` so other components can trigger calls instantly with zero AMI roundtrip.
- Re-fetches credentials on `auth-changed` so signing-in users immediately get their widget without a page reload.

### Click-to-call (`ClickToCallButton.jsx` + UnifiedPeoplePage integration)
- Reusable button. Routes to softphone (WSS users) or AMI Originate (hardphone users) automatically.
- Module-level config cache shared across 100s of buttons; invalidates on logout via `auth-changed`.
- Wired into UnifiedPeoplePage Families tab next to `primary_contact_phone`.

### Appliance (`docker-compose.yml` + `pbx/entrypoint.sh`)
- New env vars: `AMI_USERNAME`, `AMI_SECRET`.
- Entrypoint writes `/etc/asterisk/manager.conf` from the env so Asterisk accepts AMI logins from the FastAPI pod over the docker bridge.

### Testing
- Iteration 176 test report: **15/15 backend pytest pass**, 100% frontend Playwright. Missing `import os` caught in static review pre-runtime; fixed. Two minor UX hints already addressed (unconfigured state for empty WSS URL; cache invalidation on logout).

### Phase 3 Roadmap
- CDR (call detail records) browser + outbound search/filter.
- Call recording with retention rules + per-extension toggle.
- Queues with skill-based routing.
- Conference rooms + meet-me.
- Time-of-day routing UI (storage already in place from Phase 1).

## Recently Resolved — Iteration 175 (Feb 2026)
**In-app PBX — Phase 1 (management layer).**

Built the foundation for replacing Wave CloudUCM with a self-hosted Asterisk PBX. This iteration ships the **control plane only** — the runtime SIP/RTP layer arrives in Phase 2.

### Backend (`/app/backend/routers/pbx.py`)
- Six entity types with full CRUD: **extensions** (softphone/hardphone/WebRTC), **trunks** (SIP carrier connections, register+inbound DIDs), **inbound_routes** (DID → extension/hunt/IVR/voicemail), **outbound_routes** (pattern → trunk, with strip/prepend/CID override), **hunt_groups** (ringall/hunt/random/least_recent), **ivrs** (DTMF auto-attendant).
- **Asterisk config renderer** — generates `pjsip.conf` (endpoints + auth + registration blocks), `extensions.conf` (dialplan with internal/inbound/outbound contexts + IVR sub-contexts), `voicemail.conf` (per-extension mailboxes).
- Endpoints `GET /api/pbx/config/{filename}` and `GET /api/pbx/config-bundle` so the appliance Asterisk can pull fresh config on a 60-second loop.
- Per-extension SIP secret generation (`secrets.token_urlsafe(18)`) + rotate-secret endpoint.
- Cascade behaviour: deleting a trunk removes referencing inbound routes; deleting an extension removes hunt-group memberships.
- Validation: extension numbers (`[1-9][0-9]{1,5}`), dial patterns (Asterisk syntax), strategy enums, and **register=true requires SIP username** (prevents bogus registration blocks).

### Frontend (`/app/frontend/src/pages/PBXAdminPage.jsx`)
- Single-page admin UI with 6 tabs (one per entity) + Asterisk-config-preview modal.
- Each entity has an inline list + create/edit dialog with proper Select / Checkbox / number inputs.
- SIP secret is shown in the extension dialog with copy + rotate buttons (admins only — RBAC gated end-to-end).
- Visible to admins only via `/pbx` route; sidebar entry under Comms section.

### Appliance (`/app/appliance/docker-compose.yml` + `pbx/entrypoint.sh`)
- New `asterisk` service (gated behind the `pbx` compose profile so non-PBX deployments aren't charged the image weight).
- Host-mode networking (required for RTP NAT), ports UDP 5060 + WSS 8089 + UDP 10000-10100 (RTP) exposed.
- Custom entrypoint polls `/api/pbx/config/*.conf` every 60s and HUP-reloads Asterisk when changes are detected.

### Testing
- Iteration 175 test report: **25/25 backend pytest pass**, 0 critical / 0 minor UI bugs. Frontend smoke + config-preview verified. Phase-1-specific fixes from review applied: empty `outbound_auth=` line bug (would have crashed Asterisk parser) + missing register-username validation.

### Known Limitations (Phase 2 roadmap)
- `/api/pbx/apply` returns a stub — live AMI reload arrives in Phase 2.
- `/api/pbx/registrations` returns DB state with `live=false` flag — real AMI `PJSIPShowContacts` arrives in Phase 2.
- No browser softphone yet — JsSIP integration arrives in Phase 2.
- Phase 3 backlog: CDR, call recording, queues with skill-based routing, time-of-day routing.

## Recently Resolved — Iteration 174 (Feb 2026)
**Social-Work Documents checklist + Shipments full editor + Public PIN gate.**

### Social Work Documents tab
- `CHILD_FILE_DOC_TYPES` now matches the customer's "LIST OF ITEMS IN A CHILD'S FILE" reference doc 1:1 (14 items incl. 'Other'). Two synthetic items derive their state automatically: **Child Photograph** (from `child.photo_url`) and **Welfare Review Form** (from `social_review_forms` count) — no separate upload needed.
- `ChildDocumentsPanel` shows a **progress header** "N of 13 items on file (NN%)" with red/amber/green bar and missing-items list. Synthetic rows display an "auto" badge instead of Upload (with a hint to where the source lives).

### Shipments — full admin editing
- **Container dims editor** — admin can override the 40' high-cube defaults per shipment (`ship-edit-container` → `ship-container-dialog`). Visualizer rescales to the new dims.
- **Pallet manager** — pallet now stores footprint (length×width×stack-height), position (x_cm/y_cm in the container), color tag, notes (`ship-pallet-dialog`).
- **Full-edit item dialog** — every item field is editable incl. dimensions, value, weight, pallet assignment, position within pallet, notes (`ship-edit-item-dialog`).
- **2D drag-to-place** — admins can pointer-drag pallet boxes on the 2D floor plan; positions persist via `PUT /shipments/{id}/pallets/{id}` with x_cm/y_cm.

### Shipments — Public PIN-gated editor
- `POST /shipments/{id}/set-pin` (admin) — store one-way `access_pin_hash` per shipment.
- `POST /public/shipments/{token}/login` — trade PIN for an HMAC-signed `edit_token` (12h TTL).
- Full mirror of admin endpoints under `/public/shipments/{token}/...` gated by `require_shipment_editor` dependency (accepts EITHER admin JWT OR `X-Shipment-Edit-Token` header).
- Donor page: PIN-login button (visible only when `pin_required=true`), editor toolbar with Item / Pallet / Container buttons, edit/delete icons per item row, token persists in `localStorage`.

### Public donor-page polish
- New 4-card stats row: **Pallets** · **Donors** · **Items in** · **Ship-in countdown** (turns red when target date is past or <7 days away).
- **Top contributors leaderboard** (top-5 named donors by qty donated, anonymous excluded).
- Visualizer now scales to the per-shipment container dims.

### Testing
- Iteration 174 test report: **12/12 backend pytest pass** (PIN security, container/pallet/item full-edit, doc-types catalogue). 0 critical issues, 0 minor issues. Admin /shipments + /social-work pages smoke-pass without runtime errors.

## Recently Resolved — Iteration 173 (Feb 2026)
**Variant barcode UI + Finance dialog polish backlog.**

### Variant barcodes (`VariantBarcodePrint.jsx` + `routers/products.py`)
- **Export CSV** button in the print dialog (`export-barcodes-csv-btn`) → downloads product/variant/barcode/price/currency/stock/units_per_pack/sku rows. Useful for stock-takes & supplier order sheets.
- **Regenerate all** button (`regenerate-barcodes-btn`) → POST `/api/products/{id}/generate-barcodes?force=true` reissues fresh `5812-*` barcodes for every variant (not just missing ones). Confirms via dialog before destructive action.
- Backend: existing endpoint now accepts `?force=true`; backward-compatible.

### Finance dialog polish (`FinancialPage.jsx` + `FundRequestsPanel.jsx`)
- **Expense rejection** dialog (`reject-expense-dialog`) replaces `window.prompt()`. Shows the expense summary (amount, category, submitter) and accepts an optional reason via Textarea.
- **Fund-request "Mark paid"** dialog (`fund-mark-paid-dialog`) replaces `window.prompt()`. Shows request summary + accepts payment notes (txn ID, payment method) before confirming. Creates the matching expense entry exactly as before.

### Testing
- Iteration 173 test report: 4/4 backend pytest pass (force=true semantics + RBAC), reject-expense dialog fully verified E2E in Playwright, barcode + mark-paid dialog wiring + CSV export verified via direct screenshot smoke test.

## Recently Resolved — Iteration 172 (Feb 2026)
**2D + 3D pallet/container visualization, per-item photo upload, AI URL→size estimate, CSV bulk import.**

### Frontend
- New `<ContainerVisualizer>` component with **2D top-down SVG** floor plan (color-coded boxes per pallet/loose) and **3D OrbitControls Three.js scene** (`@react-three/fiber@9` + `@react-three/drei@10` + `three@0.176`). Lazy-loaded — donor page defaults to 3D, admin page to 2D.
- **CSV bulk import** in `ShipmentsAdminPage`: Papaparse client-side, downloadable template, preview table, POST to `/items/bulk-import`.
- **Per-item photo upload** — click thumbnail tile beside each item, multipart upload to `/items/{id}/photo`.
- **AI estimate from product URL** — Gemini-3-flash analyses an Amazon/Walmart/etc. link and fills weight + dims + value + confidence badge.
- Public donor page now also renders the 3D visualizer (defaultMode='3d') so supporters see the container fill visually.

### Backend
- `/api/public/shipments/{token}` now also returns `pallets` (lite roster) + `container_dims_cm` so the public visualizer can label boxes correctly.

### Critical fix during implementation
- **R3F + visual-edits Babel plugin incompatibility**: `@emergentbase/visual-edits` injects `x-line-number` / `x-file-name` / `x-component` props on every JSX element; R3F's `applyProps` walker treats hyphenated names as Three.js property paths (`x-line-number` → tries to set `mesh.x.line.number`) and throws. **Fix**: in `ContainerVisualizer.jsx::ThreeCanvas`, use `React.createElement(Canvas/primitive/OrbitControls,...)` instead of JSX. The visual-edits plugin only walks JSX AST nodes — raw createElement calls stay clean. The 3D scene itself is built with vanilla `THREE.*` constructors and handed off via `<primitive object={...}>`.
- Defense-in-depth: `frontend/scripts/patch-r3f-reserved-props.js` runs on postinstall and adds `__source`/`__self` to R3F's RESERVED_PROPS array.

### Testing
- Iteration 172 test report: 11/11 backend pytest pass, 8/8 frontend Playwright pass on live preview. Only minor issue (duplicate `ship-donor-name` testid) fixed.

## Completed Features (Iterations 49-78)
All features documented in /app/ADMIN_GUIDE.md and /app/memory/CHANGELOG.md.

## Recently Resolved — Iteration 175 (Jun 20, 2026)
**Social-work tabs fix + Container Shipment tracker with AI packing.**

### Part A — Social work tab fix (production-affecting)
- **Two "Medical" tabs merged into one**. The new single Medical tab now contains both the quick-edit summary (conditions / allergies / doctor / notes) AND the full Medical Examinations history (SocialReviewsPanel for `kind='medical_exam'`). Auto-sync direction unchanged — the form writes to `child.medical.*` so the quick-edit fields stay populated.
- **Documents tab restored** — the `TabsContent` block had been dropped during an earlier dedup edit so the tab trigger existed but rendered nothing. Now wires `<ChildDocumentsPanel>` properly.

### Part B — Container Shipment tracker (NEW feature)

**Backend** — `routers/shipments.py` (~430 LOC):
- Admin-only CRUD: `GET/POST/PUT/DELETE /api/shipments`, items + pallets sub-resources, bulk-import.
- **Public token endpoint** — `GET /api/public/shipments/{token}` returns wishlist split into still-needed vs already-acquired (sorted urgent→low), totals, AI packing text. No auth, no PII in payload (donor logs stripped).
- **Public donation** — `POST /api/public/shipments/{token}/items/{item_id}/donate` accepts `{qty, donor_name?}`, no email required. Over-pledge silently clamps to remaining. Each donation appended to per-item log.
- **AI packing scenarios** — `POST /api/shipments/{id}/ai-packing` calls Gemini-3-flash with item/pallet/weight state; returns structured Markdown (weight summary, volume reality check, pallet plan, loading order, risks).
- **Token rotation** — `POST /api/shipments/{id}/rotate-token` invalidates the current public link.

**Frontend**:
- New `<ShipmentsAdminPage>` (admin-only at `/shipments`): list + detail views, item CRUD with priority/weight/dims/value/notes, pallet management with item assignment, AI scenario generation, copy-link button, container fill progress bar.
- New `<ShipmentDonorPage>` (public at `/donate/shipment/{token}`): branded header with org logo, fill-progress hero, "Still needed" list (sorted urgent first), "Already on the truck" list, AI packing plan (collapsible), one-click "I'll donate" with optional donor name.
- Sidebar nav: "Container Shipments" link visible to Director+.

### Verification
- E2E lifecycle confirmed end-to-end: create → 3 items → pallet → public view sorted by priority → anonymous donation → over-pledge clamp → fully-covered item moves to "acquired" list → admin sees donation log → Gemini packing scenario generated (2.3 KB text with weight + container-cap + loading order).
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** ships both the social-work fix (P0) AND the new shipment feature.
- **Appliance**: auto-update tonight OR `sudo docker compose pull && up -d`.
- After redeploy: open `/shipments` (admin), create your first shipment, click "Copy donor link" → share via WhatsApp/email/socials. Donors land on a branded public page, mark items donated in 2 clicks.

### Future / Backlog
- **2D pallet floorplan** — text scenarios are good; a top-down grid visual would help warehouse staff loading the actual container. ~80 LOC SVG.
- **Donor email opt-in** — optional, would let admins send "thanks + shipment progress" updates to donors who choose to share an email. Trivial to add to the donate dialog.
- **Item photos** — admins can upload but it's just a URL field today; add a real upload button like child-extras.
- **CSV bulk-import UI** — the backend `/items/bulk-import` exists; FE could expose a "paste from spreadsheet" textarea.

## Recently Resolved — Iteration 174 (Jun 20, 2026)
**Per-campus completeness leaderboard + finished `Promise.allSettled` sweep.**

### Shipped

**1. Per-campus completeness leaderboard**
- `GET /api/social-work/reviews/compliance/completeness?group_by=location_id` now also returns a `by_campus[]` rollup: `{location_id, location_name, total_active, above_threshold, below_threshold, avg_pct}` sorted by avg descending so the leading campus shows first.
- `<ProfileCompletenessWidget>` dialog now has TWO tabs: **By child** (existing drill-down, sorted least-complete-first) and **By campus** (new leaderboard with gold/silver/bronze rank chips for the top 3).
- Useful for monthly ops review + healthy peer comparison between social workers.

**2. Finished `Promise.allSettled` sweep** on remaining high-traffic pages:
- **LocationsPage** — locations + staff + venues + group-types. A 403 on the cross-campus members fetch no longer breaks the page.
- **ProductsPage** (POS) — products + sales + locations. Sales 403 (non-finance) no longer breaks the POS page.

Other pages reviewed (HRPage / TasksPage / CheckInsPage / AdminPage / PbxSettingsPage) already had per-promise `.catch()` and were already resilient. PosKioskSetup / Wave / SecurityCheckpoint left alone — those are admin-only and route-gated.

### Verification
- E2E confirmed leaderboard: 2 test cases across 2 campuses, partial reviews → `Central avg=14% (0/1 on file), Haiti avg=0% (0/1 on file)` ✓.
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** — bundles the iter-172/173/174 cluster (dashboard fix, expense form, medical exam, child file checklist, profile bundle ZIP, page resilience, child + campus completeness audits).
- **Appliance**: auto-update tonight OR `sudo docker compose pull && up -d`.

### Future / Backlog
- Email digest: "5 children's files dropped below 70% completeness this month" → social-work manager. Runs alongside the existing overdue-task email cron.
- Optional: surface the leaderboard widget on the Dashboard for system_admins as an org-wide health view.
- Backend pagination on `/sponsors/external` once a deploy crosses ~200 donors.

## Recently Resolved — Iteration 173 (Jun 20, 2026)
**`Promise.allSettled` rollout + Profile-Completeness audit widget.**

### Resilience rollout (preventing the iter-172 "all pages failed" regression)

Same root cause as iter-172 — any page using `Promise.all` for parallel fetches will blank when a single sub-fetch returns 403. Applied the `Promise.allSettled` pattern to the next-most-likely-to-break high-traffic pages:

- **OutreachPage** — `outreachApi.{programs,sessions,categories}` + `locationsApi.list()`. A 403 on any one no longer breaks the page.
- **FinancialPage** — `summary` + `donations` + `expenses` + `cashflow` — each can require different role levels (manager vs director). Now degrades independently.
- **VolunteerSchedulingPage** — 5 different modules' worth of fetches (shifts + my-shifts + locations + events + user-directory). Restricted users now see partial data instead of nothing.

HRPage / TasksPage / CheckInsPage were already using per-promise `.catch(()=>({data:[]}))` so they were already resilient — left alone.

### Profile-completeness audit widget (NEW)

Connects directly to iter-172's checklist + medical-exam work — gives field staff a single dashboard view of which kids have incomplete files for OVCMIS / donor audits.

- New `GET /api/social-work/reviews/compliance/completeness?threshold_pct=N` endpoint.
- For each active child case, computes 14 binary indicators: photo + 3 review kinds (welfare/school/medical) + 10 file-doc types.
- Returns `{total_active, above_threshold, below_threshold, list[]}` with each child's `{completeness_pct, present, total_indicators, indicators: {…}}`. Sorted by ascending completeness so the most-incomplete files surface first.
- Bulk-loads child photos + reviews + file_docs in 3 round-trips total → fast even with 500+ active cases.
- New `<ProfileCompletenessWidget>` on the Social Work hub KPI row — sits next to `<ReviewsDueWidget>` (KPI row is now 6 cards on sm: breakpoint). Click → drill-down dialog listing each child with missing-indicators highlighted; threshold picker (50/70/85/100%); click-row → open case detail.

### Verification
- E2E confirmed: TEST_COMP child seeded with `photo_url` set + 1 welfare review → endpoint returns `completeness_pct=14%, present=2/14, below_threshold=1` ✓.
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** — bundles all iter-172 fixes (dashboard / expense form / medical-exam / child-file checklist / profile bundle) AND iter-173 (page resilience + completeness widget). Should ship together.
- **Appliance** at `https://connect.lubwamas.org` — auto-update tonight OR `sudo docker compose pull && up -d`.

### Future / Backlog
- Apply `Promise.allSettled` to remaining `Promise.all` callers (LocationsPage, ProductsPage, AdminPage, ResourcesPage) on-touch.
- Per-campus completeness leaderboard for monthly ops review.
- Email digest: "5 children's files dropped below 70% completeness this month" to the social-work manager.

## Recently Resolved — Iteration 172 (Jun 20, 2026)
**Production-blocker fixes + Medical Exam form + Child File checklist + Profile bundle ZIP.**

### 🚨 Production-blockers (PRIORITY)

**1. "All pages failed to load" on production** — Root cause: `DashboardPage` used `Promise.all` for 8 parallel fetches; when `financialApi.summary` returned 403 for a user without finance access (after recent finance-UI restriction), the whole promise REJECTED and the dashboard fell into the catch-block "Failed to load" state. Many other places had the same pattern.
   - Fix: `Promise.all` → `Promise.allSettled` on Dashboard. Each section now degrades independently. Failed sub-fetches log to dev-console for debugging, not toasts.

**2. "Expense entry requires a number"** for non-admin users — Root cause: Pydantic v2's strict mode rejects empty string for `Optional[float]` fields with "input should be a valid number". When the FE blanks out unused expense fields (`usd_equivalent`, `exchange_rate`, etc.) rather than omitting them, Pydantic 422'd the entire submission.
   - Fix: Added `@field_validator(mode="before")` on `ExpenseCreate.amount/usd_equivalent/exchange_rate` and `DonationCreate.amount` that coerces empty / whitespace-only strings to None. Required `amount` still correctly raises "Field required" when fully blank. Live-verified: `{"amount":1000,"usd_equivalent":"","exchange_rate":""}` → 200.

### Medical Exam form (3rd kind in social_review_forms)
- Extended `VALID_KINDS = {school_progress, welfare_visit, medical_exam}` so the same upload-scan + OCR + auto-sync infrastructure handles medical examinations.
- New template at `backend/templates/social_reviews/medical_exam.html` matching the .docx form verbatim (11 sections: ID, Past Medical History, Physical, Nutritional, Disability, Mental/Psychosocial, Immunization, Diagnosis, Recommendations, Referral, Practitioner Certification).
- Gemini-3-flash OCR prompt added for medical extraction — handles past-medical checkboxes + disability flags + recommendations with conservative defaults to avoid false-positive condition flags.
- Auto-sync on save: writes `child.medical.{conditions, allergies, current_medication, nutritional_status, general_condition, immunization_status, diagnosis, has_disability, disability_flags, recommendations, practitioner, latest_exam}`. Existing report PDF picks them up.
- FE: SocialReviewsPanel now accepts `kind='medical_exam'` with a streamlined in-app form (past-medical Yes/No grid + condition/nutrition selects + disability multi-select + diagnosis textarea + recommendations checkboxes + practitioner info).

### Child File checklist (typed documents tab)
- New `db.child_extras` rows with `kind='file_doc'` + `doc_type` matching the 11 canonical items from the .docx checklist (OVCMIS 008, Sponsorship Assessment, LC1 Letter, School Reports, Guardian ID, Family Consent, Medical scan, Exit Form, Sponsor Letters in/out, Other).
- New endpoints: `GET /children/{id}/file-doc-types` (catalogue + counts), `POST /children/{id}/file-docs` (upload), `GET /children/{id}/file-docs` (list).
- New `<ChildDocumentsPanel>` rendering the checklist with green-tick/empty-circle coverage indicator + per-item upload + "Download profile bundle (ZIP)" button.

### Whole-profile bundle ZIP
- New `GET /api/children/{id}/profile-bundle` streams a ZIP containing:
  - `profile.json` (raw child record)
  - `photo.jpg` (main profile photo)
  - `reviews/*.json + *.pdf/jpg` (every school_progress + welfare_visit + medical_exam form, attached scans, visit photos)
  - `documents/*` (every typed file_doc)
  - `gallery/*` (every gallery photo)
  - `INDEX.md` (human-readable manifest + checklist coverage: ☐/☒ for each of the 11 items)
- Resilient: broken / missing file URLs land as `.error.txt` placeholders instead of crashing the whole zip.

### Verification
- E2E roundtrip: medical_exam saved → `child.medical.conditions=['asthma']`, `child.medical.diagnosis='Mild seasonal asthma'`, `child.medical.recommendations.fit_with_monitoring=true`, `child.medical.immunization_status='Fully Immunized'` ✓. LC1 letter uploaded → counted on docs catalogue → bundled into ZIP ✓.
- 20/20 smoke + branding regression green. All 3 lint gates pass.
- The dashboard Promise.allSettled fix is the most important deploy item — restores production for everyone.

### Action for the user
- **🚨 PRIORITY production redeploy** to `https://5812.lubwamas.org` — fixes the "all pages fail to load" + expense form errors. **This should ship same-day.**
- **Appliance** at `https://connect.lubwamas.org` — auto-update tonight OR `sudo docker compose pull && up -d` now.

### Future / Backlog
- Apply the `Promise.allSettled` pattern to other multi-fetch pages (`HRPage`, `FinancialPage`, `SocialWorkPage`) so they also degrade gracefully when a single sub-fetch 403s.
- PDF→image first-page conversion for medical scans so PDF uploads also get OCR'd (currently image-only).
- Auto-populate `child.medical.disability_flags` UI to surface on the badge / kiosk check-in for staff awareness.

## Recently Resolved — Iteration 171 (Jun 17, 2026)
**External sponsor autocomplete + in-system-user match prompt + cleanup endpoint.**

### Shipped

**1. ExternalSponsorAutocomplete typeahead** — new component replacing the plain "Sponsor name" input in the case-detail dialog's Manual Sponsor mode. As the social worker types (≥2 chars, debounced 250ms), hits `GET /api/social-work/sponsors/external?search=` and surfaces up to 8 matches inline. Each hit shows name + email/phone + active-cases badge. Picking a hit pre-fills the entire sponsor_manual block (name/email/phone/notes) in one click — no re-typing for repeat donors. Uses `onMouseDown` (not click) so the parent Input's blur doesn't kill the dropdown.

**2. In-system user match banner** — when the manual sponsor's email matches an existing app user (case-insensitive, debounced 400ms), an amber banner offers "Link [user]'s account instead?" with a one-click switch to Existing-user mode. Promotes data unification across the org so the same person isn't duplicated as a user AND an external sponsor.

**3. DELETE /api/social-work/sponsors/external/{guest_id}** (director only) — closes the cleanup gap noted by the iter-170 testing review. Refuses with clear error + active-case count when any active case still references the sponsor. Nulls out dangling FKs on discharged cases when delete succeeds.

**4. Post-test fixes from iter-171 review**
- Dropdown empty-state ("No existing sponsors match…") was dead code due to a contradictory render guard — fixed: outer condition now triggers on `value.length >= 2`, inner branches handle loading/list/empty.
- "Save name" → renamed to "Save sponsor" (it PUTs the full sponsor_manual block — label now matches behaviour).
- Autocomplete fetch errors now `console.warn` in dev (silent in production).

### Verification
- Testing agent (`iteration_171.json`): **backend 100%, frontend 11/12 (92%)** — the 1 failed item was the dead empty-state, now patched.
- Live E2E by main agent: DELETE refuses on active case with clear 400 message ("Cannot delete — N active case(s) still reference this sponsor") ✓ discharge → DELETE → 200 ✓.
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org`.
- **Appliance** at `https://connect.lubwamas.org` — auto-update at 03:30 UTC OR `sudo docker compose pull && up -d`.

### Future / Backlog
- Pagination on `/sponsors/external` (currently capped at 500 rows) — only matters once a deploy crosses ~200 donors.
- Re-test the empty-state path on the next iter to confirm the fix renders for `<2 char` AND `no-match` queries.
- Optional: surface "linked to N sponsors" on the Existing-user dropdown so reverse-direction unification is also obvious.

## Recently Resolved — Iteration 170 (Jun 17, 2026)
**Sponsor hardening — validation + Guest auto-dedup + PDF section + autocomplete endpoint.**

### Shipped

**1. Server-side `sponsor_manual` validation** (was FE-only discipline)
- Both POST `/cases` and PUT `/cases/{id}` now reject any `sponsor_manual` that isn't either `null` or `{name: <non-empty>, ...}` with HTTP 400.
- On save: name is trimmed, email lowercased, all fields length-capped (name≤120 / email≤120 / phone≤32 / notes≤500) so paste-garbage can't blow up the report PDF later.

**2. Auto-upsert into `db.guests` as `kind='external_sponsor'`**
- New helper `_upsert_external_sponsor_guest`: idempotent dedup priority **email → phone → name** (case-insensitive, `re.escape`d for names with metacharacters like `O'Brien (Jr.)`). When a sponsor_manual is filled on any case, the helper finds-or-creates a guest row and stamps `case.sponsor_guest_id` for FK linking.
- Result: the SAME external sponsor can back multiple kids without re-typing, and payments routed through the existing guest pipeline automatically light up.

**3. Sponsor section in profile-report PDF**
- `_render_case_report_html(..., sponsor_info=None)` now renders a `<h2>Sponsor</h2>` block (Name / Source / Email / Phone / Notes) between Family and Compliance.
- Source label is either "External donor" (manual_sponsor) or "In-system user" (sponsor_member_id lookup).
- Section is omitted entirely when neither pathway has data (no empty header).
- Manual sponsor wins when both are populated (defensive — the FE keeps them mutually exclusive).

**4. New `GET /api/social-work/sponsors/external` endpoint**
- Returns roster of all `kind='external_sponsor'` guests with `{id, name, email, phone, notes, active_cases}`. Supports `?search=` filter on name/email/phone. Sorted by name.
- `active_cases` counts rows in `db.social_cases` where `sponsor_guest_id = guest.id` AND `status='active'`.
- Enables the next iteration's FE autocomplete dropdown ("link existing external sponsor" mode).

### Verification
- Testing agent (`iteration_170.json`): **13/13 backend pytest + 3/3 HTML-render assertions PASS**. Frontend out-of-scope this round (autocomplete UI is next iter).
- E2E roundtrip confirmed end-to-end by main agent:
  - 400 on no-name `sponsor_manual` ✓
  - Whitespace trim + email lowercase ✓
  - Guest auto-created with `kind='external_sponsor'` ✓
  - Second case with same email **reused** the same `sponsor_guest_id` (dedup OK) ✓
  - `/sponsors/external` returned `active_cases=2` for the shared sponsor ✓
  - PDF generated (19 KB) with `<h2>Sponsor</h2>` + name + source verified via direct HTML render ✓
- Post-test polish applied: `re.escape()` on the name regex to handle names with regex metacharacters.
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org`.
- **Appliance** at `https://connect.lubwamas.org` — auto-update at 03:30 UTC OR `sudo docker compose pull && up -d` now.

### Future / Backlog (from testing review)
- **Next iter**: FE autocomplete in the case-detail Sponsor section — call `/sponsors/external?search=` while typing to pre-fill name/email/phone from an existing donor instead of re-typing.
- Split `social_work.py` (now 1483 LOC) into sub-modules (cases.py / sponsors.py / report.py / notes.py / payments.py).
- Add `?limit` + `?skip` pagination to `/sponsors/external` for large donor rosters.

## Recently Resolved — Iteration 169 (Jun 16, 2026)
**Social-work case detail dialog redesign: wider layout + editable risk/category + manual sponsor entry.**

### Shipped

**1. Case detail dialog no longer overlaps** — `max-w-3xl` → `max-w-5xl w-[96vw]`. TabsList now uses `flex flex-nowrap overflow-x-auto` instead of `flex-wrap`, so the 10 tabs render in a single horizontal-scrolling row instead of crowding into two cramped rows. Every TabsContent bumped from `space-y-3 mt-3` to `space-y-4 mt-4` for clearer section separation. Last two tab labels abbreviated to 'School' and 'Welfare' for compactness.

**2. Risk level + Support type now inline-editable**
- New 3-column row on Overview tab: **Support type** (sponsored / restricted_location / welfare_support / multiple) · **Risk level** (low / medium / high) · **Case status**. All 3 PUT immediately on change with optimistic UI + revert-on-error. Was display-only badges before.

**3. Manual sponsor entry** — sponsor section now has a 2-mode toggle:
- **Existing user** (default) — link an in-system user (unchanged).
- **Manual entry** — for external donors. Name + email + phone + organisation/notes inputs. Stored on `case.sponsor_manual`. Mutually exclusive with `sponsor_member_id` (saving one clears the other).
- "Clear manual sponsor" button appears once any manual data is filled.

**4. Side fixes from testing review**
- Welfare tab spacing now matches the other 9 (was the one tab still on old `space-y-3 mt-3`).
- DialogContent gets `aria-describedby={undefined}` to silence the Radix "Missing Description" console warning.
- Inline Selects (category/risk) wrap PUT in try/catch and revert local state on error so the UI doesn't drift from the server.

### Verification
- Testing agent (`iteration_169.json`): **7/7 backend pytest pass + frontend 95%** (only nit was the Welfare-tab spacing, now fixed). Verified all 10 TabsTriggers share the same Y coordinate (single horizontal row), the 3 inline editors trigger PUTs, the sponsor toggle switches modes cleanly, and `sponsor_manual` persists to MongoDB.
- 20/20 smoke + branding regression green. All 3 lint gates pass.
- E2E roundtrip: PUT with `{risk_level:'high', category:'sponsored', sponsor_manual:{...}}` returns 200 with all 3 reflected.

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org`.
- **Appliance** at `https://connect.lubwamas.org` — auto-update at 03:30 UTC OR `sudo docker compose pull && up -d` now.

### Future / Backlog (from testing review)
- Add a Pydantic model for `sponsor_manual` to lightly validate shape (require `name` when present) — currently relies on FE discipline.
- Show `sponsor_manual.name` on the case profile-report PDF alongside the existing `sponsor_member_id` pathway.

## Recently Resolved — Iteration 168 (Jun 16, 2026)
**Gemini OCR for review forms + template extraction + protection red dot + reviews-due widget.**

### Shipped

**1. Gemini-3-flash-preview OCR auto-fill on upload-scan**
The bottleneck was: social worker uploaded a filled paper form → it sat as `draft_scan_only` until someone manually transcribed it. Now: upload an image (JPEG/PNG/WEBP) → Gemini extracts the full structured `fields` schema → auto-syncs into the child profile → status flips to `submitted`. PDFs still go to `draft_scan_only` (image-only for MVP; PDF→image step is a future enhancement). OCR failures (no LLM key, bad image, etc.) degrade gracefully to draft mode with the error surfaced in `ocr.error`.

E2E verified: a synthetic JPEG with form-like content → Gemini extracted `school=Hope Primary, class=P4, term=Term 2 2026, academic.overall.rating=Good, strengths='Strong reader, asks questions', overall='Good Progress'` at `confidence=high`. ~10-15s per call.

**2. HTML templates extracted** to `/app/backend/templates/social_reviews/{school_progress,welfare_visit}.html` so the markup is editable without touching Python. `_load_template` re-reads on every request → ops can hot-edit the form layout in production without a restart.

**3. Protection red dot on the case list** — `GET /api/social-work/cases` now enriches each case with `case.protection.{has_active_concern, flags}` pulled from the child record. The Cases tab shows a rose-500 dot on the avatar of any flagged child with a tooltip + ARIA label listing the specific flags (e.g. "Active protection concern: neglect, physical abuse"). Screen-reader accessible.

**4. Reviews-due widget** — new `GET /api/social-work/reviews/compliance/due?days=N` endpoint + `ReviewsDueWidget` component. KPI row now has 5 cards. Last card shows count of children whose last welfare visit was >90 days ago (or never). Click → dialog with the overdue list, threshold selector (30/60/90/180), drill-into-case shortcut. Empty state when everyone's up to date.

### Verification
- Testing agent (`iteration_168.json`): **15/15 backend pytest pass + frontend 100%**. Aria-label nit fixed post-test.
- Gemini OCR: live-tested end-to-end by main agent (extraction confidence=high, all fields populated).
- 20/20 smoke + branding regression green. All 3 lint gates pass.
- Test fixtures: 25 stale test children + 1 case + 0 reviews cleaned during this iteration.

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org`.
- **Appliance** at `https://connect.lubwamas.org` — auto-update at 03:30 UTC OR `sudo docker compose pull && up -d` now.
- **EMERGENT_LLM_KEY** must be set in your prod env for OCR to actually run; without it, scans go to `draft_scan_only` (no failure, just no auto-fill).

### Future / Backlog
- Split `_ocr_review_form` + `_OCR_SYSTEM_PROMPTS` into a sibling `social_review_ocr.py` module (router file would drop ~150 LOC).
- Add a PDF→image first-page conversion step (pdf2image / poppler) so PDF scans also run through OCR.
- Cache rendered PDF templates keyed by template mtime if traffic warrants.
- Tighten `/compliance/due` aggregation: filter reviews aggregation by location_id when caller passes `?location_id=`. Currently child_id list is already campus-scoped so functionally fine; just a defence-in-depth improvement.

## Recently Resolved — Iteration 167 (Jun 16, 2026)
**Social Work Review Forms — School Progress + Welfare Home Visit.**

### What shipped

Productionised the two paper forms the field-team has been filling by hand. The forms collect data NOT currently in the codebase: termly academic ratings (Excellent/Good/Fair/Poor on overall, reading/writing, math, participation), attendance/discipline checks, social-emotional ratings, welfare indicators (physical health, nutrition, hygiene, emotional well-being, safety, family support, living conditions), protection concerns (neglect, physical abuse, emotional abuse, child labour, dropout risk, early marriage risk), child's voice (what's going well / challenges / support wanted), household assessment, and per-review action plans.

**1. Backend** — new `routers/social_review_forms.py` (~530 LOC):
- `POST /api/social-work/reviews/children/{child_id}` — submit filled review (school_progress or welfare_visit). Validates kind + child exists.
- `GET /api/social-work/reviews/children/{child_id}` — timeline of reviews, optional `?kind=` filter. Campus-scoped for non-privileged staff.
- `PUT /api/social-work/reviews/{id}` — edit, auto re-applies sync.
- `DELETE /api/social-work/reviews/{id}` — soft delete to db.deleted_items.
- `POST /api/social-work/reviews/children/{child_id}/upload-scan` — accepts PDF/image up to 15 MB, creates a draft review with `attached_scan_url`, also mirrors into `db.child_extras`.
- `GET /api/social-work/reviews/templates/{kind}.pdf` — generates a printable blank form (WeasyPrint) with org branding pulled from `system_settings`. Two layouts hand-built to mirror the original .docx visually (header bar, checkbox glyphs, signature blocks).

**2. Auto-sync into child profile** — `_apply_review_to_child`:
- school_progress saves → `child.education.{school_name, current_term, grade, latest_review}`.
- welfare_visit saves → `child.family.{primary_caregiver, caregiver_relationship, village_parish, district, household_assessment}` + `child.welfare.latest_review` + `child.protection.{flags, has_active_concern, last_assessed_at}`.
- Existing `/api/members/{id}/profile-pdf` report-generator picks up these fields automatically — no extra wiring.

**3. Frontend** (`SocialReviewsPanel.jsx`, ~450 LOC, plus 2 new tabs on SocialWorkPage):
- Two new tabs in the child detail dialog: **School Reviews** + **Welfare Visits**.
- Each tab has toolbar: Print blank · Upload scan · + New review · Refresh.
- Print blank downloads the PDF for paper use.
- Upload scan → creates a draft "transcribe later" row.
- + New review opens a dialog with the FULL form schema verbatim (4 rating tables, all checkbox groups, action-plan rows, overall-assessment dropdown, child's voice textareas).
- Timeline shows each filed review with overall-badge, social-worker name, protection-flag badge when applicable.

**4. Side fix** — React hydration warning: `DialogDescription` wraps `<p>` and cannot contain `<div>` (Badge). Replaced with a `<div>` sibling so the meta-line strip renders without console noise.

### Verification
- E2E roundtrip: school review saved → `child.education.latest_review.overall='Good Progress'`, welfare review saved with `protection_concerns.{neglect, child_labour}=true` → `child.protection.has_active_concern=true, flags={neglect:true, child_labour:true, ...}`. Both PDFs generate cleanly (200 + application/pdf).
- Testing agent (`iteration_164.json`): **14/14 backend pytest pass, frontend 100%**. All form-schema fields verified in both dialogs.
- 20/20 smoke + branding regression green. All 3 lint gates pass.

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org` so social-work staff get the new tabs + templates.
- **Appliance** at `https://connect.lubwamas.org` — auto-update tonight at 03:30 UTC OR `sudo docker compose pull && up -d` now.

### Future / Backlog (from testing agent + my review)
- Split the two long HTML templates out of `social_review_forms.py` into separate files so the router stays under ~250 LOC.
- Add Gemini OCR step to `upload-scan` so a filled paper form auto-extracts into structured `fields` — would close the only manual step in the flow.
- Wire the existing protection-flag onto the children list (sw-tab-cases) so a red dot appears next to flagged kids.

## Recently Resolved — Iteration 166 (Jun 11, 2026)
**Event signups visibility + Outreach recurring-event generation bug.**

### Bugs fixed

**1. Event signups not visible to staff (Registrations tab always empty)**
Root cause: `GET /api/events/{id}` was reading from `db.event_registrations`, but every public-signup endpoint (`/api/public/bookings/event`, waitlist, etc.) writes to `db.public_bookings`. Wrong collection → empty list.

Fix in `routers/events.py` L314+: merge both collections, dedup by `email+phone`, exclude `status='cancelled'`. Each attendee row now carries `name / email / phone / status / num_tickets / tier_name / total / created_at / source`. The legacy `event.registered` counter is auto-synced to `sum(num_tickets) + len(legacy_regs)` on every GET — so the event card always shows the real number.

UI in `EventsPage.jsx`: attendees tab now renders ticket count + tier + total + registered-at + payment status when present (was just name+email+badge).

**2. Recurring Outreach events: only 1 generated regardless of frequency**
Root cause was on the FRONTEND, not the backend. Line 204 of `OutreachPage.jsx` reset `recurForm` to a **completely different shape** (`{months_ahead, nth_day, day_of_week:'saturday', time, end_time}`) when the dialog opened. This wiped the proper fields (`pattern`, `occurrences`, `interval`, `start_date`, `end_date`). On submit, the form's blank fields produced undefined payload values; backend defaults kicked in unpredictably; an explicit `end_date` (which the user always sets) would frequently land just after the first iteration, terminating the generation loop at 1 event.

Fix: rewrote the click handler to reset `recurForm` to the proper schema, pre-filled from `programme.recurrence_*` fields. Added validation: end_date must be ≥ start_date; start_date required; warn-toast when only 1 event was created with `occurrences>1` (the bug's fingerprint).

**3. Bonus polish — Radix Select rendering blank on dialog open**
Found by the testing agent. The Pattern Select trigger rendered visually blank even though state was correct, because Radix's value→label mapping fails when `SelectItem`s register lazily after the value prop is set. Fix: explicit label fallback inside `SelectTrigger` (`{patternLabels[recurForm.pattern] || 'Weekly'}`) so the user always sees the current selection even if Radix's mapping hasn't kicked in yet.

### Verification
- Live E2E confirmed: public RSVP → staff event detail shows `attendee_count=1, registered=2, first_attendee='Alice Test'`. weekly×10 → 10 events. monthly×6 with 5-month end_date → 6 events. daily×5 → 5 events. end_date < start_date → 0 events (was the bug fingerprint).
- Pattern Select now shows "Weekly" on open (visual confirmation via screenshot).
- 20/20 smoke + branding regression green.
- All 3 lint gates pass.
- Test data cleaned (54 events + 19 bookings + 0 programmes deleted from DB).

### Action for the user
- **Production redeploy** to `https://5812.lubwamas.org` to ship both fixes.
- **Appliance** at `https://connect.lubwamas.org` — auto-update timer picks it up tonight at 03:30 UTC, OR `sudo docker compose pull && sudo docker compose up -d` to pull it now.

## Recently Resolved — Iteration 165 (Jun 8, 2026)
**🚨 Password-change security fix + Social-work schools + Fund Requests module + HR manual payslip + Approvals multi-role.**

### Security-critical fix (P0)
**Password change form on Settings → Security was a fake `setTimeout`** — users believed they rotated passwords but the request never reached the backend. Now wired to a real `POST /api/auth/change-password` with bcrypt verification of the current password, tarpit on wrong attempts, audit logging, and mirroring to the `members` collection when the account is linked.

### Shipped
1. **Social-work schools**: `GET /api/social-work/schools` broadens visibility — system admins + anyone with `social_work` module access see every school org-wide (schools are partner orgs, not campuses). Non-privileged users see campus + legacy un-tagged rows.
2. **Fund Requests module** (NEW): `routers/funds.py` wraps Approvals with `subject_kind='fund_request'`. Submit advance/reimbursement, upload receipt (10 MB image/PDF, cloud→disk fallback), finance marks paid → auto-creates `db.financial` expense with back-ref. Idempotent. New `/funds` route + sidebar link under Operations (STAFF_PLUS).
3. **HR manual payslip**: `POST /api/hr/payslips/manual` (director+): one-off payslip with arbitrary gross + allowances + deductions. Live net-preview in the dialog.
4. **Approvals multi-role engine**: `_can_act_on_step` now honors both `approver_role` (legacy singular) and `approver_roles` (new plural list). Unblocks the entire fund-request approval chain — without this, the auto-seeded workflow could never be approved.

### Verification
- New `tests/test_iteration162_funds_password_hr.py` — 19/20 PASS at first run (1 skipped due to approver_roles bug, now fixed).
- Live E2E roundtrip confirmed: create → approve via `/api/approvals/requests/{id}/act` → mark-paid → expense in `db.financial` → idempotent re-call returns same expense_id.
- 20/20 smoke + branding regression green. All 3 lint gates pass.
- Test fixtures cleaned (1 payslip + 6 fund requests deleted from DB).

### Action for the user
- **Production redeploy** — most important reason is the password-change security fix.
- **Appliance** — `sudo docker compose pull && sudo docker compose up -d` (or wait for nightly auto-update).

## Recently Resolved — Iteration 164 (Jun 1, 2026)
**Docker-compose appliance for self-hosted deployment.**

### Shipped

**1. `appliance/Dockerfile.backend`** — multi-stage Python 3.11-slim image bundling FastAPI + weasyprint/cairo native deps + the full backend code. Healthcheck on `/api/health`. Multi-arch (linux/amd64 + linux/arm64).

**2. `appliance/Dockerfile.frontend`** — multi-stage: Node 20 builds the React bundle with `REACT_APP_BACKEND_URL=''` (relative paths), Caddy 2-alpine serves it + reverse-proxies `/api/*` + `/ws/*` + auto-provisions Let's Encrypt TLS when `SITE_DOMAIN` is set.

**3. `appliance/Caddyfile`** — front-door config: TLS-aware HTTPS site (only when `SITE_DOMAIN` is set), plain HTTP fallback on `:80` for LAN-only deployments, WebSocket pass-through, SPA-fallback for client-side routes, security headers mirroring the backend middleware.

**4. `appliance/docker-compose.yml`** — 4 services: `mongo` (data in `./data/mongo/`), `backend` (uploads in `./data/uploads/`, backups in `./data/backups/`), `caddy` (TLS state in `./data/caddy/`), `cloudflared` (profile-gated, only spawned when `COMPOSE_PROFILES=tunnel` + token is set).

**5. `appliance/install.sh`** — one-line installer:
```bash
curl -fsSL https://raw.githubusercontent.com/5812-global/connect/main/appliance/install.sh | sudo bash
```
Installs Docker, clones the repo to `/opt/connect`, generates fresh JWT + NFC secrets, pulls images, brings up the stack, waits for `/healthz`, prints the LAN IP + login URL.

**6. `appliance/.env.example`** — fully-commented template covering required (JWT, NFC) + optional (SITE_DOMAIN, Cloudflare token, Resend, OCR key, VAPID, Sentry) config.

**7. `appliance/README.md`** — partner-org runbook: hardware sizing matrix, quickstart, manual install, Cloudflare Tunnel setup, public-TLS setup, ops cookbook, troubleshooting, architecture diagram, and a direct comparison with the Tauri desktop bundle.

**8. `.github/workflows/docker-publish.yml`** — multi-arch (amd64 + arm64) image build + push to GHCR on every `v*` tag and `main`/`master` push. Caches Buildx layers in GitHub Actions cache for fast incremental builds.

### How partner orgs deploy (the partner-side flow)

1. Buy any cheap Linux box (Intel N100 mini PC ~$200, or Pi 5 ~$120 for ≤200 members).
2. Install Ubuntu 22.04+ or Raspberry Pi OS.
3. Run the one-line installer.
4. LAN users browse to `http://<box-ip>` from any phone/Chromebook/laptop.
5. Optionally paste a Cloudflare Tunnel token for remote access.

The whole org operates from a single appliance regardless of staff device choices. No mac/win code-signing drama. No per-device installs.

### Verification
- Both YAML files parse cleanly (`yaml.safe_load`).
- Dockerfiles use the same proven patterns the existing K8s preview already uses (Python 3.11-slim + uvicorn + Node 20 + yarn build).
- Healthcheck hits the existing `/api/health` endpoint from iter 151.
- Persistent volumes mounted under `./data/` so existing in-app `/admin → Backup & Restore` still works inside the appliance.

⚠️ **Preview redeploy not required** — the appliance is a separate deployment artifact. To start using it: push to GitHub, let the docker-publish workflow publish the two images to GHCR, then run the install.sh on any Ubuntu box.

### Continuing per your plan
- **First image build** — push to GitHub + run `docker-publish.yml` workflow once. Images appear at `ghcr.io/<your-org>/connect-{backend,frontend}:latest`.
- **First partner pilot** — buy a $200 mini PC, run install.sh, hand over the LAN URL.
- **Then Path B** (pre-baked SD/USB image) — once the compose stack is proven with 2-3 pilots, layer a Packer/Ansible build on top so partners don't even need to install Ubuntu.

## Recently Resolved — Iteration 163 (Jun 1, 2026)
**GitHub Actions desktop release pipeline.**

### What shipped

**1. `.github/workflows/desktop-release.yml`** — matrix build across macOS, Windows, Ubuntu. Triggered by any `v*` tag push or manual `workflow_dispatch`.

Per platform the workflow:
- Installs Rust + Node 20 + Python 3.11.
- Linux: installs `libwebkit2gtk-4.1-dev` + GTK / appindicator dev headers.
- PyInstaller-bundles `backend/server.py` → `desktop/resources/backend/server[.exe]`.
- `yarn build`s the frontend → `desktop/dist/`.
- Downloads matching portable `mongod` from fastdl.mongodb.org.
- Downloads matching `cloudflared` from the official GitHub releases.
- Runs `tauri-apps/tauri-action@v0` → produces installers (.dmg / .msi / .nsis / .deb / .AppImage) + `latest.json` for the auto-updater + uploads them as a **draft release**.

Code-signing + auto-updater signing are env-var-driven, no-op without the secrets — same scaffold as the local `build-bundle.sh`. README lists the exact secret names for Apple Dev ID + Windows EV cert + Tauri updater key.

**2. `.github/workflows/ci.yml`** — added `EmptyState testid coverage` step calling `bash scripts/check-empty-states.sh` to keep the lint gate in sync with the local `lint-check.sh` (3 stages now: ruff → eslint → check-empty-states).

**3. `desktop/RELEASING.md`** — operator runbook: how to cut a release, what secrets to set, where the download link lives (GitHub Releases URL), troubleshooting matrix.

### Verification
- Both workflow YAML files parse cleanly (`python -c "import yaml; yaml.safe_load(open(p))"`).
- The local lint gate (`bash scripts/lint-check.sh`) already exercises identical steps to step 1-2 of CI.

### How partner orgs get the desktop binary

1. **You**: push `git tag -a v0.1.0 -m "..." && git push origin v0.1.0`.
2. **GitHub Actions**: ~15 min later, draft release appears with 5 installers + `latest.json`.
3. **You**: smoke-test on one box, click "Publish release" in the GitHub UI.
4. **Partner orgs**: download from `https://github.com/<your-org>/<repo>/releases/latest`.
5. **You**: drop that URL into your WordPress site, the cloud `/downloads` page, or hand it to ops directly.

⚠️ **Production redeploy not required for this iteration** — the workflow only runs in GitHub. Repo just needs to be pushed to GitHub (use the platform's "Save to Github" feature) and the secrets configured (or left blank for unsigned dev builds).

## Recently Resolved — Iteration 162 (Jun 1, 2026)
**USB device pairing with role assignment.**

### What shipped
Persistent device→role mapping for paired USB peripherals (Serial / HID / USB), so consumers can ask for "the receipt printer" / "the NFC reader" / "the scale" by name and get back a live handle without re-prompting the user on every page load.

**1. Device-role registry** (`utils/deviceRoles.js`)
- 8 canonical roles defined: `receipt_printer`, `label_printer`, `barcode_scanner`, `nfc_reader`, `signature_pad`, `cash_drawer`, `customer_display`, `scale`.
- Each role declares which transports it supports (`serial` / `hid` / `usb`), a human description, and a setup hint.
- `pairDeviceForRole(role, transport)` → opens the matching browser picker (`navigator.serial.requestPort` / `navigator.hid.requestDevice` / `navigator.usb.requestDevice`), persists vendor/product IDs + fingerprint to `localStorage` (`5812:device-role-pairings`).
- `getDeviceForRole(role)` → reads back the live device handle using the persisted fingerprint. Returns `null` if unpaired or unplugged. Survives page reloads as long as the browser permission cache is intact.
- `probeAllRoles()` → dashboard helper returning per-role `{paired, available, pairing?}`.

**2. Admin UI** (`components/DevicePairingDialog.jsx`)
- New `/admin → USB Devices & Roles` card (testid `device-pairing-card`).
- Dialog (testid `device-pairing-dialog`) lists all 8 roles. Each row shows:
  - Status badge: Not paired / Paired (unplugged) / Available.
  - Pair button per supported transport (`device-pair-{role}-{serial|hid|usb}`).
  - Unpair button when paired.
  - Hardware summary (transport, product name, vendor:product IDs, serial number).
- Cancel-detection robust to Chrome's three picker messages (NotFoundError, "No port selected by user", "No device selected") — shows friendly "Pairing cancelled" info toast instead of error.
- Amber banner when the browser exposes none of the three APIs (Safari, mobile browsers).

**3. POS receipt-printer integration** (`utils/printers.js` + `ProductsPage.jsx`)
- New `printers.js` exposes `printReceiptText(lines)` (ESC/POS over Serial) and `printLabelZpl(zpl)` (ZPL over USB) plus a `buildReceiptLines(sale)` helper.
- POS checkout auto-print path (when `store_settings.auto_print_receipt` is on):
  - **If `receipt_printer` is paired**: sends ESC/POS bytes directly to the printer (initialize → text → 3-line feed → partial cut).
  - **Otherwise**: falls back to the existing `window.print()` flow — zero regression for stores without a paired printer.
- Dynamic `import('../utils/printers')` so the device-roles bundle is code-split out of the main POS chunk for stores that don't use it.

### Tests / lint
- `bash /app/scripts/lint-check.sh` → all 3 gates pass (ruff + eslint + check-empty-states).
- 20/20 backend regression green (16 smoke + 4 branding).
- Testing agent (`iteration_161.json`): **frontend 100%**, backend N/A (no backend changes). Verified all 8 roles render with correct testids, 13 transport-matched pair buttons, paired-state simulation via localStorage, picker invocation, unpair UI, dynamic-import code-split.

### How partner orgs use this
1. Plug in the device (USB printer / USB NFC reader / etc.).
2. Open `/admin → USB Devices & Roles`.
3. Click "Pair Serial" / "Pair USB" next to the role (e.g. Receipt printer → Pair Serial). The browser shows its native device picker.
4. Pick the right device. The dialog flips to "Available" (green).
5. From now on, the POS auto-prints to that printer. Replug the cable later → still works (fingerprint match). Move to a new install → just re-pair once.

⚠️ **Production redeploy needed**. No real hardware can be tested in the K8s preview — the UI + lookup logic are verified via mocked pickers. Real hardware test should happen on a partner-org desktop after deploy.

### Continuing per your plan
- **More consumers can wire up the same way**: KioskPage (badge scan), Security Checkpoint (NFC reader), Sales Portal (signature pad, scale). Each just calls `getDeviceForRole('xyz')` and handles `null` gracefully.

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
