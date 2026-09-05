# 58:12 Connect — Changelog

## Iteration 291 (Feb 2026) — Session #2 continuation: Loss audit + Cash & Bank fix + Reports overhaul

### 🔍 Loss audit
Verified what survived vs the pre-wipe handoff. **Genuinely lost**: Cash & Bank `is_cash` aggregation (fixed here), HR Payroll → `finance_journal_entries` (todo), Auto-Issue Tickets Dialog (todo), stale `accounting.py`/`AccountingPage.jsx` cleanup (todo). Everything else from iter 279-285 survived in GitHub.

### 🟢 Cash & Bank aggregation regression
- `FinancePage.jsx` Overview `cashOnHand` now includes `a.is_cash` in addition to `10xx`-code accounts. Mobile Money + Savings + any bank flagged via `bank_subtype` now count. This is a re-apply of the lost iter 289 fix.

### 🟢 ReportsPage.jsx overhaul
- **5 report types in one page** — Summary, Trial Balance, P&L, Balance Sheet, Cash Flow. Switch via `/api/finance/reports/*` under the hood.
- **Optional FX conversion at export** — target currency + rate inputs; all numbers passed through `applyFx()` when target set. Empty target → base currency (no conversion).
- **CSV export** — client-side generator, per-report-type column layout, FX suffix on headers.
- **PDF export** — passes `fx_target`/`fx_rate` params to `/api/reports/pdf` (backend PDF already embeds org logo).
- **Location dropdown scoped by role** — "All Locations" hidden for non-admin users; restricted users auto-pinned to their assigned campus. Sublocations render with "(sub)" suffix. Empty state now says "No locations found".

## Iteration 291 (Feb 2026) — Env rebuild + 6 P0 fixes

Preview `/app` wiped mid-session; user provided GitHub repo, container bootstrapped from scratch (mongod + supervisord + backend/frontend), Iter 290 work re-applied, then new batch layered on.

### 🔴 P0
- **Resource types** — create dropdown + stat cards + card badges wired to state (merged with defaults). Backend seed expanded to 12 types.
- **Finance transfers** — `POST /api/finance/transfers` + FinancePage → Overview "Record transfer" button. Optional inline **transaction fee** posts a 3-line JE (Dr destination, Dr fee-expense, Cr source (amount+fee)). Optional **reference / receipt #** attached.
- **Expense/income reference** — `QuickPostDialog` gained a `Reference / receipt #` input passed through to the ledger.
- **Events "created but not showing"** — `create_event` now defaults `location_id` to the creator's `active_campus_id` before insert. Was inserting nulls that `get_campus_filter` excluded on list.
- **UnifiedBadge layout** — left column has fixed height matching photo, `justify-content: space-between` flush-aligns info top with photo top and QR bottom with photo bottom.
- **Notifications dismiss on click** — `markRead` now removes the notif from the panel; `markAllRead` empties it. Panel drains instead of piling up read entries.
- **Bank accounts CRUD UI** — Edit / Close / Delete buttons on each account card. Dialog reused for edit mode. Delete gracefully degrades to close when transactions exist.

### 🧪 Curl-verified
- New event without `location_id` now defaults to admin's `loc_001` and is visible in list
- Transfer JE lines: Dr destination `amount`, Dr fee-expense `fee`, Cr source `amount+fee`, `source='transfer'`, reference attached
- Notification `mark_read` decreases unread count and frontend removes it from list

## Iteration 290 (Feb 2026) — LOST during preview pod wipe; re-applied in 291.

## Iteration 256 (Feb 2026) — HS-only classifier + Prune removal + Cloudflare 520 hardening

### 🔴 P0 — HS-only classification (PVoC removed)
- `_classify_hs_with_ai` slimmed down to return just `{hs_code, reason}`. PVoC rules + `requires_pvoc` / `pvoc_reason` output removed. Halves the tokens Gemini has to reason over per call.
- Added a **35s hard timeout** (`asyncio.wait_for`) around the Gemini call — if the LLM stalls we return a retryable 504 instead of hanging the worker past 120s.
- `POST /api/shipments/{id}/classify-hs-bulk` chunk default reduced from 5 → 3, cap 10. Every branch now returns a valid JSON body (even unexpected exceptions wrap into `{classified:0, failed:[...]}`) so Cloudflare never surfaces "could not parse origin response".
- Single-item `POST /items/{id}/classify-hs` returns the trimmed payload.

### 🔴 Removed "Prune over-pledged" feature
- Deleted `POST /api/shipments/{id}/prune-over-pledged` (backend) and the toolbar button + `pruneOverPledged` handler (frontend). Legacy Scissors icon still imported elsewhere; harmless.

### 🟢 UI cleanup — PVoC removed from admin surface
- Per-item PVoC pill removed, `togglePvoc` handler deleted, `requires_pvoc`/`pvoc_reason` no longer sent from the edit dialog PUT.
- Manifest PDF drops the "PVoC required: N" total, the `pvoc_footnote`, and the per-row PVoC badge.
- Invoice PDF drops the PVoC signature-block footnote and per-row PVoC badge.
- AI HS button label + tooltips updated ("AI HS codes" instead of "AI HS + PVoC").
- Item list on admin page now sorts **by box name → line value → weight** (was PVoC → value → weight). Consistent with the manifest/invoice sort.

### Verified
- `classify-hs-bulk` returns `{"classified":3,"failed":[],"remaining":0,"total_untagged":3}` · HTTP 200 with no PVoC field · lint clean.
- `POST /prune-over-pledged` → 404 (endpoint gone).
- Manifest 16 KB · Invoice 17 KB · HTTP 200.



## Iteration 255c (Feb 2026) — Scan-draft autosave + single-photo-per-box

### 🟢 Scan-draft autosave (survives refresh / signal loss)
- `POST /api/shipments/{id}/scan-boxes` now persists the full result set on the shipment as `scan_draft` (scan_run_id, counters, per-photo `results[]` with item_ids, errors, timestamps).
- New `DELETE /api/shipments/{id}/scan-draft` endpoint clears the draft; called on the frontend by the **Done**, **Scan more**, and **Undo this scan** buttons.
- Frontend has a `useEffect` that re-hydrates `boxScanResult` from `selected.scan_draft` whenever a shipment loads without a live result, and re-opens the dialog automatically. Refreshing the page, switching tabs, or losing signal in the middle of a 20-photo review no longer wipes it — the review is exactly where the packer left it.

### 🟢 Single photo per matched box (unless photos are genuinely different)
- When the same box is photographed multiple times in one scan run (front / side / list), only the **first** photo is retained; subsequent uploads for the same matched box are discarded (file removed from `/api/uploads/`, no `$addToSet` on `packing_units.photos`).
- Different boxes still each get their own photo — dedup is scoped by box match, not by scan run. Packers can still attach multiple angles manually via the per-box gallery if they need them.



## Iteration 255b (Feb 2026) — Box scan dialog UX: persistent results + inline edits

### 🟢 Scan results persist until explicit "Done"
- Outside-click and Esc-key no longer discard the box-scan result panel. `DialogContent` now stops those events (`onPointerDownOutside` + `onEscapeKeyDown`) when `boxScanResult` is set. Only the header X, the "Done" button, and the "Scan more" / "Undo this scan" buttons close the results.
- Fixes the "scan 20 photos, tap outside, lose everything" regression the user was hitting.

### 🟢 Per-item Remove and Qty edit inline in the results
- Each scanned line now has:
  - Editable `qty` input — persists the delta immediately via `PUT /items/{item_id}` so the dialog stays authoritative.
  - Rose-red X button — for `added` lines, deletes the item this scan created; for `linked` lines, subtracts the qty this scan added from the pre-existing item's `qty_acquired`. Confirmation prompt before any destructive action.
  - Optimistic local state update + `refreshDetail()` after each mutation so counters, packing totals, and the item list stay consistent.
- Test IDs `box-scan-qty-<i>-<j>` and `box-scan-remove-item-<i>-<j>` for automated coverage.



## Iteration 255 (Feb 2026) — Box scanning: individual items + weight estimates + manifest/invoice sort

### 🟢 Box scan lists every item individually (even for "Personal" boxes)
- Removed the collapse-into-one-`Household Personal Item`-row logic from `POST /api/shipments/{id}/scan-boxes`. Personal / household boxes now list every item they contain (shampoo, towels, plates, ...) exactly like a regular box so the customs manifest + commercial invoice show real line items.
- `SYS_PROMPT` updated to explicitly forbid the collapse and to ask for `estimated_weight_kg` alongside `estimated_value_usd` for each item.
- Fallback: if the AI returns zero items for a personal box (rare), we still add one `Household Personal Item` line so the box isn't lost.

### 🟢 AI weight estimation for scanned items
- New `_estimate_weight_kg(name, category, provided)` helper mirroring `_estimate_value_usd`. Uses the AI-supplied weight when present, otherwise falls back to a category preset (0.4 kg clothing, 0.6 kg book, 1.5 kg kitchen appliance, ...) with a safe 0.8 kg default. Container weight totals now include scanned items instead of showing zero.

### 🟢 Manifest sorted by box number
- New `_sort_items_by_box(items, packing_units)` in `_common.py` — natural-order sort ("Box 2" < "Box 10" < "Box 12A") with un-boxed items pushed to the end.
- `GET /api/shipments/{id}/manifest.pdf` now sorts by box → packers can walk down the container ticking off a full box at a time.
- `_loc_str` extended to accept `packing_units` so the "Loc" column shows the human-readable box name ("Box 12 – Kitchen") instead of just a pallet-id fragment.

### 🟢 Invoice sorted by value then box
- New `_sort_items_for_invoice(items, packing_units)` — highest line-value first (unit_value × qty), then by box number, then item name.
- `GET /api/shipments/{id}/commercial-invoice.pdf` uses the new sort — the customs officer sees the biggest-value lines up top.



## Iteration 254d (Feb 2026) — Retry Failed Shapes

### 🟢 Per-item "Retry" pill for failed shape derivations
- **Backend**: `_derive_shape3d_for_item` now `$unset`s `shape3d_error` on success. Both the single (`POST /items/{id}/derive-shape`) and batch (`derive-shapes-batch`) endpoints catch failures and persist the error message onto `items.$.shape3d_error` (140-char cap). So the failure survives page reloads.
- **Frontend**: `ShipmentsAdminPage` item card pill now has three states based on `it.shape3d`/`it.shape3d_error`:
  - **Derived** → indigo pill showing shape kind (`box`/`cylinder`/`sphere`/`compound`), click to re-derive.
  - **Failed** → 🔴 rose "Retry" pill with tooltip showing the exact error, click to retry just this one item.
  - **Not yet derived** → grey dashed "3D?" pill.
- Test: forcing a failure on a photo-less item persists `shape3d_error: "Item has no photo yet"` on the record, ready to render the Retry pill on next page load.


## Iteration 254c (Feb 2026) — Production hardening: chunked bulk AI, file picker fixes, donor page crash protection

### 🔴 P0 — Chunked bulk AI (removes the untracked-background-task footgun)
- Production symptom: users saw the batch AI kick off but progress silently stalled — the previous `asyncio.create_task(...)` pattern loses work when a worker recycles. Cloudflare 524s were also reported.
- `POST /api/shipments/{id}/classify-hs-bulk?limit=5` and `POST /api/shipments/{id}/items/derive-shapes-batch?limit=3` now process a small chunk **synchronously** and return `{classified/succeeded, failed:[...], remaining, total_untagged, ...}`. No background tasks.
- Frontend `bulkClassifyHs` and `bulkDeriveShapes` loop the endpoint until `remaining === 0`, refreshing state and updating the progress toast after every chunk. Each call finishes in ~30-50s well under the 120s proxy timeout.

### 🔴 P0 — Donor page crash protection
- The public `/donate/shipment/<token>` page was blowing up on 3D texture-load failures. Wrapped the `ContainerVisualizer` in an `ErrorBoundary` with an inline fallback (small muted-grey box + refresh hint) so a WebGL / texture problem no longer takes down the entire donor page. Same protection added inside `ShipmentsAdminPage`.
- Donor page now defaults `ContainerVisualizer` to `2d` mode (was `3d`) so we don't render textures + WebGL for anonymous visitors before they've even asked for it.
- `ErrorBoundary` extended with an optional `fallback` prop (element or function) so small widgets can be wrapped without the full-page fallback.

### 🟢 Photo picker across all shipment scan flows
- `capture="environment"` removed from the **Admin AI Scan** dialog — was forcing camera-only on mobile. Users can now pick from library OR camera on both desktop and mobile.
- Confirmed **Box Scan** (`ship-box-scan-btn`) and the **Donor Scan** already allow multi-select from gallery.



## Iteration 254b (Feb 2026) — Shipping visualizer: no auto-snap, full-screen edit, rotation, non-blocking bulk AI

### 🔴 P0 — Fix Cloudflare 120s Proxy Read Timeout on bulk AI endpoints
- Production hit `524 Origin Timeout` when clicking **AI HS + PVoC · Re-classify** on a 45-item shipment (~5-15s per Gemini call × 45 items = 3-11min blocking POST).
- `POST /api/shipments/{id}/classify-hs-bulk` and `POST /api/shipments/{id}/items/derive-shapes-batch` now fire the Gemini loop as `asyncio.create_task(...)` and return immediately with `{status:"started", targets, ...}` well under 10s.
- Frontend `bulkClassifyHs` and `bulkDeriveShapes` poll `/shipments/{id}` every 4s, refresh `selected` so item pills update live, and update the toast (`AI classifying 12 / 45 items…`). 20-min safety cap.

### 🔴 P0 — Kill auto-snap everywhere (pallets, packing units, items)
- `_add_or_merge_item` no longer calls `auto_place_on_pallet` — new items land wherever the caller specifies, or unassigned/loose. Manual pallet assignment + manual stacking.
- `computeLayout` (`ContainerVisualizer`) dropped the greedy 120×100 grid for un-positioned pallets/units and the wall-clamping `Math.max(0, Math.min(...))` in the drag handler. Items land exactly where dropped.
- Backend `PUT /pallets/{pid}` and `PUT /packing-units/{uid}` no longer floor-clamp `x_cm/y_cm/floor_x_cm/floor_y_cm` to `>= 0` or `<= container.length/width` — negative coords persist so items can sit past the walls.
- `PUT /items/{id}` also allows negative `floor_x_cm/floor_y_cm`.

### 🟢 Full-screen editable layout
- New `Full screen` toggle in the visualizer toolbar (`data-testid="ship-viz-fullscreen-btn"`). Opens a fixed `z-50` overlay with a wider `viewBox` (~2× container length + 60% each side of vertical padding) so admins can stage / edit items past the container's physical footprint.
- 3D canvas grows to `75vh` in full-screen.
- Esc closes.

### 🟢 Rotate items in 3D (and 2D)
- New `rotation_deg` field on items, pallets, and packing units (degrees around the vertical axis, normalised 0-360). Persisted via existing PUT endpoints.
- Double-click a pallet / item on the 2D floor plan → rotates 90°. Persists through `onPalletRotate` callback.
- 3D scene applies `mesh.rotation.y` (and edge wireframe rotation) for boxes, cylinders, and compound (mixer) meshes so the rotation is visible from every angle.

### 🟢 Fixed over-sized AI 3D shapes
- `computeLayout` now prefers the item's stored `dims_cm` over `shape3d.primary` for L/W/H. AI-derived shape only overrides the **kind** (`cylinder | sphere | compound`), not the size. Blenders/mixers whose Gemini-estimated dims came back at ~60cm wide now render at their real dims.

### 🟢 Auto-refresh shipment list card
- New `useEffect` on `selectedId === null` re-fetches `/shipments` list so item edits done inside a detail view are immediately reflected in the count/weight/progress bar on the tile without a manual `RefreshCw` click.



## Iteration 254 (Feb 2026) — Shipping visualizer polish (no snapping, photo-textured faces, batch shape derivation)

### 🟢 Photo-textured box faces on the 3D container visualizer
- `ContainerVisualizer.jsx` now maps each loose item's primary photo onto the door-facing (+X) face of its 3D block, so packers can identify items visually without hovering for the label.
- BoxGeometry material array `[+X, -X, +Y, -Y, +Z, -Z]` — photo lives on +X (the door end per the 2D floor labels); other faces stay a solid item color.
- Skipped for cylinders, spheres, compound meshes (shape itself conveys identity), pallets (wood texture retained), and items with no photo.
- Textures loaded via `THREE.TextureLoader` with `crossOrigin` + sRGB colorSpace; relative `/api/uploads/*` URLs are prefixed with `REACT_APP_BACKEND_URL` so it works in both preview and prod.
- Photo materials are opaque (transparency dropped) so the photo reads clearly at any orbit angle.

### 🟢 One-tap "Derive shapes for every un-analysed item"
- New endpoint `POST /api/shipments/{shipment_id}/items/derive-shapes-batch` (admin-only) walks every item that has a photo but no `shape3d` and runs the existing Gemini classifier on each. Returns `{attempted, succeeded, failed:[{item_id,name,error}], skipped_no_photo, already_analysed}` so the UI can toast a single summary.
- Refactored the single-item classifier into a shared helper `_derive_shape3d_for_item(...)` so both endpoints call the exact same Gemini prompt + persistence path.
- Runs sequentially (respects Gemini rate limits, and if the browser tab closes the server still finishes cleanly).
- New toolbar button `Derive shapes (N)` on `ShipmentsAdminPage.jsx` — only shown when N > 0. Confirms before running (one Gemini call per item), shows a `Loader2` spinner while working, and refreshes the detail so new shape pills appear on each item card.

### 🟢 No snap on 2D/3D
- Confirmed no snap-to-neighbours logic exists on either the SVG floor plan or the 3D visualizer. Items land exactly where dropped; only wall-clamping (`Math.max/min` against container bounds) is applied. No changes were needed — snapping is now explicitly excluded from the roadmap.



## Iteration 228 (Feb 2026) — Shipping consolidation + AI-scan bug fix

### 🔴 P0 — Fixed "Scan failed" on the donor-page AI item scanner
- **Root cause**: `/app/backend/routers/shipments_pkg/public.py` (post iter-224 split) still held a stale `from routers.shipments import _persist_shipment_image` inside the image-persistence loop. Since `routers/shipments.py` was deleted when we broke it into `shipments_pkg/`, this import raised `ImportError` before every photo scan could complete — the frontend saw a 500 and toast'd "Scan failed".
- **Fix**: removed the stale import — `_persist_shipment_image` is already imported from `._common` at the top of the file. Scan now completes end-to-end.

### 🔴 P0 — Admin-side AI Scan (was donor-only before)
- **New endpoint** `POST /api/shipments/{shipment_id}/scan-item` (admin-only via `require_admin`). Mirrors the public `/public/shipments/{token}/scan-item` UX (up to 3 photos + ISBN/UPC → Gemini vision) but with no PIN gate so back-office staff can bulk-scan items from the admin page.
- **New UI**: purple "AI Scan" button on the shipment items toolbar (next to "Item" and "Import CSV") opens a mobile-friendly dialog with photo upload + "Identify with AI" → review card → "Add to shipment" one-click.

### 🔴 P0 — Consolidated the two pallet surfaces
- Deleted the OLD dedicated "Pallets" row + "Pallet" button + `editingPallet` dialog on ShipmentsAdminPage. There is now ONE surface: the "Packing units" section inside `ShipmentPackingPanel` which handles pallets, boxes, totes and crates uniformly.
- Existing legacy `pallets` docs still render fine — `ContainerVisualizer` merges them with `packing_units` into a single unified layout via a helper that normalises `L_cm/W_cm/H_cm` ↔ `length_cm/width_cm/height_cm`.

### 🔴 P0 — Consolidated the two floor-plan / 3D views
- Removed the standalone `FloorPlanSVG` inside `ShipmentPackingPanel` (2D-only). The top-level `ContainerVisualizer` (2D + 3D) already covers this and now consumes both legacy `pallets` AND new `packing_units` in one merged layout.
- Drag-move on the visualizer auto-detects whether the moved id is a pallet or a packing unit and routes to the right PUT endpoint.

### 🔴 P0 — Public donor page: hide everything unless PIN-authed
- **Un-authed donors** now only see: shipment header + progress bar + "Still needed" list with "I'll donate" buttons. That's it. Cleaner, more focused, more donation-friendly.
- **PIN-authed editors** still see the full experience: 3D container, "Already on the truck", editor toolbar, detailed stats grid, donor leaderboard.
- **Backend**: `/api/public/shipments/{token}` now exposes `packing_units` too when unlocked, so admin/editor visualizer renders the same unified layout as the admin page.

### Testing
- Backend: curl end-to-end verified `/scan-item` (admin) and `/public/shipments/.../scan-item` both return HTTP 200 with structured JSON (Google Books quota is exhausted so ISBN returns "Unidentified" fallback, but the endpoint itself no longer throws). Route table intact (57 shipment routes).
- Frontend: smoke screenshots confirmed:
  - Public donor URL (no PIN) shows ONLY progress bar + "Still needed" list — no container/pallets/acquired/stats
  - Admin shipment page has "AI Scan" button, unified packing-unit section, no duplicate pallets row
  - `admin-scan-dialog` opens with photo picker + "Identify with AI"


## Iteration 227 (Feb 2026) — Boarding-pass OCR · Fare Alerts · Passenger Portal

### 🔴 P0 — Boarding-pass OCR (Gemini vision)
- Backend: `POST /api/shipments/{sid}/passengers/{pid}/tickets/{tid}/scan-boarding-pass` — accepts image or PDF, calls Gemini 3 Flash with vision, returns STRICT JSON with `passenger_name`, `airline`, `flight_no`, `pnr`, `seat`, `gate`, `boarding_time`, `departure_time`, `origin`, `destination`, `ticket_no`, `boarding_group`, `cabin`, `confidence`. Uses `emergentintegrations` `ImageContent` for images and `FileContentWithMimeType` for PDFs.
- Frontend: "AI scan" button in the check-in dialog runs OCR on the picked file, previews extracted fields in a purple review panel, and auto-fills the seat input. On check-in, extracted PNR is also patched onto the ticket.

### 🔴 P0 — Fare Alerts (daily AI fare-watch + Resend email)
- New collection `fare_alerts` and router `/api/fare-alerts` (`GET/POST/PUT/DELETE`, plus `POST /{id}/check-now`).
- Fields: `{origin, destination, date, target_usd, cabin, passengers, alert_email, active, last_check_at, last_min_price_usd, last_result, notify_count}`.
- Background asyncio loop `_run_fare_alerts_loop` in `server.py` — every 24h iterates active, non-past alerts and calls Gemini for the current cheapest fare. If `min_price_usd <= target_usd`, sends a "fare drop" email via `send_notification_email` (Resend) with route + price + "Book now" link. Increments `notify_count`.
- Frontend: new `/fare-alerts` route with a full CRUD page — cards show target, last-found price with delta %, notify count, cheapest booking link, pause/resume toggle, "Check now" trigger.
- Sidebar nav entry added under Operations (director+ visibility).

### 🔴 P0 — Passenger Portal (public token-based self-service)
- Each passenger now has a `portal_token` (auto-generated on create; backfilled for existing passengers via startup migration).
- Admin CRUD extended: `POST /api/shipments/{sid}/passengers/{pid}/rotate-portal-token` to invalidate & re-issue.
- Public endpoints (no auth): `GET /api/passenger-portal/{token}` (returns shipment + passenger + their tickets + relevant flights + their suitcases), `POST /api/passenger-portal/{token}/tickets/{tid}/check-in` (self-check-in with boarding-pass file upload), `POST /api/passenger-portal/{token}/tickets/{tid}/scan-boarding-pass` (public OCR mirror).
- Frontend new route `/p/passenger/:token` — clean single-page view with the passenger's flights, tickets, suitcases; "Check in ✓" button per ticket opens a mobile-friendly modal with file input + AI scan button + seat field + submit.
- Admin UI: new "Portal" button on each passenger card copies the unique link to clipboard.

### Testing
- Backend: verified via curl end-to-end. Fare alert `check-now` returned live JFK→EBB min-price of $1764 from Gemini (didn't trigger since target=$900, correct). Passenger portal GET returned expected shape. Portal check-in flow independent of admin auth.
- Frontend: smoke screenshots confirm `/fare-alerts` page renders with two live-data alerts (Active badge, $900 target, $1920 last-found, +113% delta, "Check now" and "Pause" buttons) and `/p/passenger/{token}` portal shows passenger name, one flight, one ticket with "Update boarding pass" button and check-in timestamp. Ruff & ESLint clean.


## Iteration 226 (Feb 2026) — Airport-mode overhaul: multi-flight, tickets, check-in, AI flight search, 3D per-suitcase

### 🔴 P0 — Container layout hidden in airport mode
- `ShipmentsAdminPage.jsx` now gates the `<ContainerVisualizer>` 3D/2D render behind `mode !== 'airport'`. Airport shipments no longer show the container floor plan (which was confusing for luggage-only shipments).

### 🔴 P0 — Multi-airline / multi-flight per shipment
- New `flights[]` array on shipment docs. Fields: `{id, airline, flight_no, origin, destination, departure_at, arrival_at, booking_url, status, ai_summary, last_ai_check_at, notes}`.
- `POST/PUT/DELETE /api/shipments/{sid}/flights[/fid]` — full CRUD, admin-only.
- Frontend Flights section shows every leg with airline + flight # + route + AI status summary. Booking URL opens in a new tab.

### 🔴 P0 — Multi-ticket per passenger (connections supported)
- New `tickets[]` array nested inside each passenger. Fields: `{id, flight_id, ticket_no, pnr, seat, checked_in, checked_in_at, boarding_pass_url, notes}`. A single passenger can hold one ticket per flight leg (JFK→AMS + AMS→EBB).
- `POST/PUT/DELETE /api/shipments/{sid}/passengers/{pid}/tickets[/tid]`.
- UI: each passenger card shows a nested Tickets list with flight linkage, PNR, seat, and check-in status badge (e.g. "1/2 checked in").

### 🔴 P0 — Check-in log + boarding-pass upload
- `POST /api/shipments/{sid}/passengers/{pid}/tickets/{tid}/check-in` accepts multipart form: `checked_in`, `seat`, optional `boarding_pass` file (max 2.5 MB, stored as data-URL on the ticket).
- Frontend "Check in" button per ticket opens a dialog with seat + boarding-pass file picker. Existing boarding pass is viewable via a link.

### 🟠 P1 — AI Flight Search (Gemini 3 Flash grounded on Google Search)
- `POST /api/shipments/{sid}/ai-flight-search` — body `{origin, destination, date, passengers, cabin}` — returns a structured list of up to 6 flight suggestions with airline, flight #, times, duration, stops, cabin, USD price and booking URL. Uses Gemini 3 Flash + Google Search grounding via the Emergent LLM key.
- Frontend "AI Flight Search" button on the Flights section opens a dialog with search fields and result table. "Add to shipment" button on each result creates a `flight` record in one click.

### 🟠 P1 — Auto-refresh flight status every 15 minutes
- Background asyncio loop in `server.py` (`_run_flight_status_refresh_loop`) iterates every 15 min through airport-mode shipments with any flight in `boarding/departed/in_air` status (or where the overall shipment is `shipped`) and calls Gemini for each flight's current status. Updates `status`, `ai_summary`, `last_ai_check_at` in-place.
- Manual `POST /api/shipments/{sid}/refresh-flight-status` button available in the UI for immediate refresh.

### 🟠 P1 — Per-suitcase 3D pack view
- New `Suitcase3DScene.jsx` component (react-three-fiber + drei) — lazy-loaded to keep initial bundle small. Renders the suitcase as a transparent wireframe box with each of its assigned items positioned inside via a naive shelf-pack (row + wrap + layer) using each item's `dims_cm`. Orbit controls, ambient + directional lighting, item labels.
- "3D pack view" toggle button on each suitcase row opens the scene in a modal.

### Test coverage
- Backend: manual curl end-to-end verified for add flight, add ticket, check-in, AI flight search (returned live KQ/KLM/Brussels/Turkish Airlines results with realistic caveat about the 330-360-day booking window).
- Frontend: smoke screenshot confirms Airport panel visible, Flights section rendered, container visualizer hidden, tickets nested under passenger, "1/1 checked in" badge working.


## Iteration 225 (Feb 2026) — HR Reset Danger Zone + shipments.py Modular Split

### 🔴 P0 — HR Module Reset Button
- **Backend** `DELETE /api/hr/reset` (admin-only). Query params: `scope` (`payslips` | `all`), `campus_scope` (`active` | `all` — system_admin only), `ledger` (`reverse` | `delete`), `confirm` (must equal `RESET-HR` to actually delete; otherwise returns a dry-run preview).
- Deletes across up to 11 HR collections (`hr_payslips`, `hr_salaries`, `hr_salary_history`, `hr_contracts`, `hr_contract_templates`, `hr_doc_requests`, `hr_timesheets`, `hr_time_off`, `hr_leave_requests`, `hr_reimbursements`, `hr_attendance`) with the `_hr_reset=True` flag added to every recycled doc for later filtering.
- Unwinds payroll ledger postings: `ledger=reverse` posts offsetting JEs (auditable) via `_reverse_auto_posted_je`; `ledger=delete` hard-removes the payroll expenses + JEs.
- Recycle-bin dump — every deleted doc is snapshotted into `db.deleted_items` before hard-delete so admins can recover if needed.
- **Frontend** — new red "Reset" button in the HR page header (admin/system_admin only) opens a two-step confirmation dialog: pick scope + campus + ledger action → "Preview count" fetches the dry-run → user types `RESET-HR` → "Permanently reset" applies.
- 27/27 backend tests pass (1 destructive apply skipped for safety per test-agent policy).

### 🔴 P0 — `shipments.py` split into modular package
- Broke the 2737-line `/app/backend/routers/shipments.py` into `/app/backend/routers/shipments_pkg/` with 6 files (all ≤ 760 lines):
  - `__init__.py` (17 lines) — combined router.
  - `_common.py` (483 lines) — shared helpers, constants, PIN/security re-exports (`_normalise_item`, `_add_or_merge_item`, `_normalise_pallet`, `_classify_hs_with_ai`, `_sort_items_for_manifest`, `_loc_str`, `_resolve_group`, `_PDF_STYLES`, `_waybill_html`, `_persist_shipment_image`, `PACKING_PRESETS`, `PUBLIC_ITEM_WISHLIST_FIELDS`, `CONTAINER_40FT_HC`, `VALID_*` sets).
  - `core.py` (154 lines) — shipment CRUD, PIN, token rotation.
  - `items.py` (756 lines) — items CRUD, HS-code classification, manifest & commercial-invoice PDFs, photo upload, find-link, bulk import.
  - `pallets.py` (435 lines) — pallets CRUD, packing units (pallet/box/tote/crate presets), AI packing scenario + AI suggest packing + apply, QR labels PDF.
  - `public.py` (668 lines) — every `/api/public/shipments/*` endpoint (donor view, editor login, mirror mutations, kiosk scan-item).
  - `airport.py` (247 lines) — passengers, suitcases, admin waybill HTML, AI tracking summaries.
- All 55 original `@router.*` decorators preserved 1:1 (44 unique paths verified via FastAPI's route introspection). Server log confirms "All modular routers loaded" with zero errors.
- `server.py` updated: `from routers.shipments_pkg import router as shipments_router`.
- Old `shipments.py` file deleted.


## Iteration 210 (Feb 2026) — Reconcile: transfers included · Onboarding: inline Fix links
### 🟡 P2 — Reconcile now covers transfers
- `GET /api/financial/reconciliation` returns two new arrays:
  - `untagged_transfers` — `sublocation_transfers` at this location where neither `from_account_id` nor `to_account_id` is set (they shift cash but never touch chart-account balances).
  - `recent_transfers` — last 50 `chart_account_transfers` touching any cash account at this location (context / audit, not "untagged" since transfers require both endpoints).
- Reconcile panel adds a second collapsible "Recent chart-account transfers touching this location" and folds `untagged_transfers` into the "Show untagged rows" details view with a "sublocation transfer · from→to" line format.

### 🟠 P1 — Onboarding: inline Fix links
- Every red X in the Onboarding matrix is now a **clickable "Fix" button** that jumps to the right dialog:
  - `has_salary` → switches to Salaries tab + opens the Add Salary dialog pre-filled with the staff.
  - `has_contract` → switches to Contracts tab + opens Issue Contract dialog; staff-id hint saved to localStorage for the contract form to pick up.
  - `has_chart_account` → toast pointing to Accounting → Cash Accounts (cross-page).
  - `has_department` / `has_location` → toast pointing to People → Staff Directory (cross-page).
- `HRPage` tabs converted from `defaultValue` to controlled `value` so the callback can programmatically switch tabs. Preserves existing behavior for direct tab clicks.
- Hover reveals a small "Fix" label; keyboard-focus and screen-reader accessible via native `<button>` element.


## Iteration 209 (Feb 2026) — Finance ↔ Cash Accounts Reconciliation
- **Auto-tag on entry:** `create_donation` and `create_expense` now silently auto-tag `deposit_to_account_id` / `paid_from_account_id` to the location's `store_settings.default_cash_account_id` when caller leaves it blank. Sales already did this; now donations and expenses do too, so **Finance sub-location totals equal Chart cash-account activity by construction**.
- **Backend endpoint** `GET /api/financial/reconciliation?location_id=<loc>` — returns `{sublocation_net, chart_delta_sum, untagged_income, untagged_expenses, untagged_net, matches, drift, chart_accounts[], untagged_donations[], untagged_expenses_list[]}`. Uses `_batch_compute_balances` for perf.
- **Batch cleanup** `POST /api/financial/reconciliation/auto-tag` — one click tags every untagged donation + expense at a location to a picked (or default) chart account. Supports `only='donations'|'expenses'|'both'`.
- **Frontend:** new "Reconcile" tab on FinancialPage with per-location picker, 4-tile summary (Sub-location Net · Cash Accts Δ · Untagged · Drift ✓/⚠︎), per-account activity table, expandable untagged-rows list, and an "Auto-tag remaining" button when drift ≠ 0.
- **Verified curl-to-end:** loc_recon starts with drift=5000 (one pre-default donation untagged), auto-tag → drift=0, matches=true.


## Iteration 208 (Feb 2026) — Admin Reset Financial Module (testing safety net)
- **New endpoint** `POST /api/financial/reset` — strict admin-only. Requires `confirm: "RESET"` body. Wipes any subset of {donations, expenses, sales, accounting_entries, accounting_entry_lines, budgets, chart_account_transfers, assets, sublocation_transfers, hr_payslips} scoped by `location_id` + optional `date_from` / `date_to`.
- **Balances self-heal:** Chart account definitions and `starting_balance` are preserved by default. Since chart-account balances are computed live from the referencing transactions, deleting them causes balance to snap back to the starting value. Optional `reset_chart_account_starting_balances: true` also zeros the seed.
- **Journal entry lines cascade:** deleting accounting_entries collects their IDs first, then removes matching lines so no orphans linger.
- **Audit + warning log:** every reset is `_audit`ed and logged at WARNING level with scope, location, results.
- **Frontend:** Accounting → Cash Accounts tab gains an admin-only "Reset Finance" button that opens a guarded dialog: scope (one location / date range / everything), collections checklist, optional starting-balance zeroing, and a "type RESET" confirmation field. Balances refresh automatically after success.
- **Verified end-to-end:** created a chart account with starting_balance=50000 UGX, spent 5000 (balance→45000), reset scope=location → 1 expense deleted → balance snapped back to 50000. Also verified 400 responses on missing `confirm` and missing `location_id`.


## Iteration 207 (Feb 2026) — Payslip PDF Export + HR Onboarding Checklist
- **Server-side payslip PDF:** `GET /api/hr/payslips/{id}/pdf` renders a WeasyPrint-styled A4 PDF (58:12 branded header, staff meta grid, line-items table, summary + status). Access restricted to admins/HR + the payslip owner. Filename: `payslip-<Staff_Name>-<period>.pdf`.
- **Frontend PortalProfile:** payslip Download button and Review dialog now call the PDF endpoint via authenticated `api.get(..., {responseType:'blob'})` and trigger a browser download — no more browser-print workaround.
- **HR Onboarding Checklist:** `GET /api/hr/onboarding/checklist` returns per-staff completeness across 5 checks (department, location, contract, salary, chart-account). Response: `{total, fully_onboarded, needs_attention, rows[{staff_id, staff_name, email, role, checks:{...}, completion_pct, salary_summary}]}`. Rows sorted by completion_pct so gaps float to the top.
- **HR page Onboarding tab:** new `OnboardingPanel` renders a per-row grid of green-check/red-X across the 5 checks, salary summary, and completion badge. Refresh button + summary counters.


## Iteration 206 (Feb 2026) — Reversal Line-Status Fix + HR Payslip Workflow
### 🔴 P0 Bug fix — reversed transactions still counted in Income / P&L / Trial Balance
- **Root cause:** `reverse_entry` marked the reversal ENTRY as `posted` but forgot to update its `accounting_entry_lines` from `draft` to `posted`. Line-level report queries filter by `status='posted'`, so the reversal was invisible while the original still counted — user saw already-reversed amounts as income.
- **Fix:** `reverse_entry` now `update_many` flips reversal lines to `posted`.
- **Backfill:** `POST /api/accounting/entries/repair-reversal-lines` (admin) scans all posted entries with any draft-status lines and fixes them. Auto-audited. UI exposes a "Repair Reversals" button on the entries toolbar.

### 🟠 Delete UX — bulk-reverse alongside bulk-delete
- `POST /api/accounting/entries/bulk-reverse` — accepts `{ids:[...]}`, reverses each posted entry (idempotent — skips already-reversed and non-posted). Returns `{reversed, skipped_already_reversed, skipped_not_posted, errors[]}`.
- Toast copy improved: delete now says "…N posted skipped — click Bulk Reverse to reverse them instead."

### 🟢 HR Payslip module — self-service + timesheets + auto-expense
- **Payslip enhancements:** `_generate_payslips_for` accepts `days_worked_override` and `pto_days_override`. Approved timesheets auto-merge on generate (opt-out via `use_timesheets:false`). Payslip doc gains `days_worked` and `pto_days` fields plus a transparent `Days-worked adjustment` line-item when short.
- **Timesheets:** `POST/GET/PUT/DELETE /api/hr/timesheets` — staff submits, manager approves/rejects, staff can withdraw non-approved. Same-period resubmissions update the existing row (no duplicates). Non-HR users only see their own list.
- **Self-service payslips:** `GET /api/hr/payslips/mine` + `GET /api/hr/payslips/{id}/mine`. Cross-user access blocked at 404.
- **Auto-expense on paid:** `_aggregate_payroll_expense` now sets `paid_from_account_id` on the payroll expense from `store_settings.default_cash_account_id` for that location — draws the store's real cash account balance automatically. Preserves the field on subsequent same-day aggregations.
- **Frontend:**
  - `PortalProfile.jsx` — "My Payslips" card (Review + Print/PDF), "My Timesheets" card, submit-timesheet dialog with period/days_worked/PTO/notes.
  - `HRPage.jsx` — new "Timesheets" tab with status + period filter, approve/reject actions per row.

### Testing
- `testing_agent_v3_fork` iter 206 → **14/14 pytest pass** (`test_iter206_reversal_fix_and_hr_payslips.py`).
- Regression flagged by the tester (missing `@router.post` decorator on the pre-existing `bulk_delete_entries` after inserting new endpoints above it) — restored, re-verified (HTTP 400 with correct body).


## Iteration 205 (Feb 2026) — Extended POS Payment-Method → Account Mapping
- `sales.create_sale` now routes 12 payment-method variants to the correct default account:
  - `cash` → `default_cash_account_id`
  - `card` / `bank` / `bank_transfer` / `cheque` / `check` / `wire` → `default_bank_account_id`
  - `mobile_money` / `momo` / `airtel` / `airtel_money` / `mtn` / `mtn_momo` → `default_momo_account_id`
  - Any unrecognised method falls back to `default_cash_account_id` (unchanged safety default).
- All 12 mappings verified end-to-end via curl against the preview URL.


## Iteration 204 (Feb 2026) — Finance Edit/Delete Restoration + POS Auto-tag + Balance Perf
- **P0 Bug fix — Edit/Delete UI restored everywhere:** Chart of Accounts (CoA), Journals, and Taxes tabs in `AccountingPage.jsx` gained inline Edit + Delete icons for admins. Dialogs now handle both create and edit modes (title + button label switch on `form.id`). Backend endpoints (already existed at `PUT/DELETE /api/accounting/accounts|journals|taxes/{id}`) are now wired.
- **P1 — POS auto-tag to real cash accounts:** `store_settings` gained `default_cash_account_id`, `default_bank_account_id`, `default_momo_account_id`. `create_sale` auto-populates `deposit_to_account_id` based on the sale's `payment_method` (cash → default_cash; card/bank → default_bank; mobile_money → default_momo; with cash as fallback). Explicit `deposit_to_account_id` on the sale still wins. Sale gets `deposit_auto_tagged: true` for transparency. Products page store-settings dialog gained three new pickers so admins can wire the defaults.
- **P2 — Batch balance perf:** `_batch_compute_balances(account_ids)` — 5 aggregation round-trips regardless of N accounts. `list` and `mine` refactored to use it. Old O(6·N) hot path eliminated.
- **P2 — Store-settings default merge:** GET `/api/store-settings/{loc}` now merges the default schema over stored docs so legacy locations always see the new keys (`{**defaults, **doc}`).
- **Tests:** `test_iter204_finance_edit_delete_and_pos_autotag.py` → **16/16 pytest pass** via testing_agent_v3_fork iter 204.


## Iteration 203 (Feb 2026) — Chart Cash Accounts with User Assignments
- **NEW backend router:** `/api/financial/chart-accounts/*` (`chart_accounts.py`) — real-world cash / bank / mobile-money / credit / petty-cash accounts. Each account has assignable `assigned_user_ids`. Only admins bypass; regular users can only spend from or deposit to accounts they're assigned to.
- **Live balance:** `starting_balance + Σ donations(deposit_to_account_id) + Σ approved expenses(paid_from_account_id) [negative] + Σ non-voided sales(deposit_to_account_id) + Σ transfers(in/out)`. Pending expenses do not affect balance until approved.
- **New model fields:** `DonationCreate.deposit_to_account_id`, `SaleCreate.deposit_to_account_id`. `ExpenseCreate.paid_from_account_id` already existed.
- **Access enforcement:** `create_donation` and `create_expense` in `financial.py` now call `user_can_use_account` before persisting — non-admin without assignment returns 403 with `not assigned` message.
- **Transfers:** `POST /api/financial/chart-accounts/transfer` — validates from/to distinct, amount > 0, sufficient balance; recorded in `chart_account_transfers` collection.
- **Frontend Accounting:** New "Cash Accounts" tab (`data-testid='acc-tab-cash-accounts'`) with cards showing live balance, assignee count, ledger drilldown, admin CRUD + assign-users dialog + transfer dialog.
- **Frontend Financial:** Expense form + Donation form now use `chartAccountsApi.mine` to populate their pickers with the user's assigned accounts (with live balance display).
- **Soft-delete:** deleting an account with any referenced expense / donation / sale sets `active=false` (returns `archived: true, referenced_txns: N`). Accounts with no txns hard-delete.
- **Tests:** `test_iter203_chart_accounts.py` → **22/22 pytest pass** via testing_agent_v3_fork iter 203.


## Iteration 202 (Feb 2026) — Finance Bulk Delete + Expense "Paid From" Picker
- **Backend:** `ExpenseCreate.paid_from_account_id` field added (`financial.py`). Stored on the expense so future reconciliation can attribute the spend to a specific cash/bank account.
- **Backend:** Bulk-delete endpoints added — `POST /api/financial/donations/bulk-delete`, `/expenses/bulk-delete`, `/assets/bulk-delete`, `/budgets/bulk-delete`, and `/api/accounting/entries/bulk-delete` (skips posted entries — they must be reversed instead).
- **Frontend:** `FinancialPage.jsx` gains checkboxes + BulkActionBar on donations, expenses, budgets, and assets tabs. The expense entry dialog now shows a "Paid From" account picker with live balance display (and a low-balance warning + "balance after" preview).
- **Frontend:** `AccountingPage.jsx` gains multi-select on journal entries with a bulk-delete action that surfaces how many posted entries were skipped.
- **Tests:** 15/15 iter202 pass (`test_iter202_finance_bulk_delete_and_paid_from.py`).


## Iteration 201 (Feb 2026) — Accounting Reversal Fix + Hide-by-default
- **Bug fix:** `reverse_entry` now marks the original as `is_reversed`, auto-posts the reversal (was staying in draft), is idempotent (double-reverse returns same id, no more duplicates), and back-links via `reverses`.
- **Visibility:** `GET /entries` and `GET /sales` gained `include_reversed`/`include_voided` (default off) — reversed pairs hidden until opted-in. Shown pairs get strike-through + 60% opacity + inline badges.
- **Tests:** 4/4 iter201 pass.
- Bulk delete + expense "Paid from" picker explicitly deferred to iter 202 (larger scope).

## Iteration 200 (Feb 2026) — Acquired ≠ Packed + Two-tier Public Visibility
- Items gained `qty_packed` (independent counter) + `transport_mode` (container/suitcase/holdback).
- New endpoints: `POST /shipments/{id}/items/{item_id}/pack` and public PIN mirror.
- `GET /public/shipments/{token}` splits into stripped wishlist (anonymous) vs full manifest (with edit_token or admin JWT). Sensitive fields (weight, dims, pallet, packed, transport_mode, image_urls) are stripped for anonymous callers.
- Admin UI: per-item Packed badge (🚢/🧳/⏸) + 📦 dialog for quantity + mode.
- Donor page: refresh now passes edit_token when unlocked.
- **Tests:** 9/9 iter200 pass.

## Iteration 199 (Feb 2026) — Bulk Find-Links
- New "🤖 Find links (N)" button in shipment items header. Sequentially runs `find-link` on every wishlist item still missing `source_url`. Confirm dialog + progress toast.
- Code-review report triaged rather than blind-applied — most items were false positives; documented rationale.

## Iteration 198 (Feb 2026) — AI Find-Link + Buy Surface
- **NEW** `POST /api/shipments/{id}/items/{item_id}/find-link` — Gemini picks best retailer + builds search URL. 19 retailers supported including MAC.bid, Amazon, Walmart, eBay, Home Depot, AbeBooks, etc.
- Search-URL-only strategy (never deep ASIN/SKU guesses → no 404 link rot). ISBN/UPC short-circuit when available.
- "🛒 Buy at [retailer] ↗" link surfaces in admin item rows when `source_url` is set.
- "🤖 Find link" button added to the existing link dialog.
- PIN editors can now save `source_url` via the public update endpoint.
- **Tests:** 4/4 new pass + 54 regression still green.

## Iteration 197 (Feb 2026) — Imperial/Metric Toggle + Retail-aware AI
- **NEW** `backend/shipment_units.py` + `frontend/src/services/shipmentUnits.js` — parse `2'9"`, `5lb 8oz`, `0.84m`, etc.
- Shipments gained `units` field (metric|imperial). `_normalise_item` parses all dim/weight inputs through the parser.
- `ShipmentsAdminPage` has a units toggle + smart text inputs for dims/weight with imperial-friendly placeholders.
- Gemini scan prompt now cites Amazon/Walmart/eBay/MAC.bid/Home Depot/Lowe's/AbeBooks/Costco/IKEA/AliExpress as cross-reference sources + returns a `source` field.
- **Tests:** 50/50 backend pytest pass (19 unit + 10 endpoint + 14 dedupe + 8 helpers).

## Iteration 196 (Feb 2026) — Modularization Single Pass
- **`backend/shipment_security.py`** (NEW) — `_PIN_SECRET`, `_PIN_SALT`, `EDIT_TOKEN_TTL_HOURS`, `hash_pin`, `make_edit_token`, `verify_edit_token`, `require_shipment_editor`. `routers/shipments.py` re-exports under old names.
- **`backend/pbx_helpers.py`** (NEW) — `pbx_now`, `gen_pbx_secret`, `pbx_id`, `validate_extension_number`, `validate_pattern`. `routers/pbx.py` aliases under old `_now`/`_id`/etc.
- No route paths or HTTP behaviour changed. Backend lint clean.
- **Tests:** 22/22 unit+integration + 5/5 warmup/AI tests + live PBX curl smoke. All green.
- **Server.py scheduler:** explicitly deferred — too tightly coupled to module-local helpers for a safe single-pass extraction.

## Iteration 195 (Feb 2026) — Modularization Slice 1 + Mobile Photo Fix
- **Mobile fix:** photo-preview X button now visible on touch (`opacity-100 sm:opacity-0 group-hover:opacity-100`) — phone donors can now remove a bad scan.
- **Modularization:** new `backend/shipment_helpers.py` with pure `auto_place_on_pallet`. `routers/shipments.py` imports + delegates. Back-compat shim preserved.
- **Tests:** new `test_iter195_shipment_helpers.py` (pure-fn, 0.02s) → 8/8 pass. Integration regression 17/17.

## Iteration 194 (Feb 2026) — Kiosk Cache Warmup
- **Backend:** new `GET /api/checkins/kiosk-warmup` returns a thin directory of `{parent, children}` entries scoped to the event's campus.
- **Frontend:** `CheckInsPage` auto-fires warmup whenever the operator selects an event and seeds `kioskCache` against id/phone/email/name — first scans of the morning are already cache-hot.
- **Tests:** `test_iter194_kiosk_warmup.py` → 3/3 pass.

## Iteration 193 (Feb 2026) — Offline Kiosk QR + P2 Audit
- **NEW:** `services/kioskCache.js` — TTL-12h, max-200 LRU in localStorage for parent/QR/PIN lookups. Wired into both branches of `CheckInsPage`'s parent lookup. Network drop → cached match + amber "Offline" toast. Cached only on success.
- Cleaned dangling orphan JSX block in `CheckInsPage.jsx` (parser-error blocker).
- Audited remaining P2 items: PWA service worker (`sw.js` + register) and bulk barcode printing dialogs already exist. Modularization / i18n / mobile-audit explicitly deferred — too broad for single-pass safe execution.

## Iteration 192 (Feb 2026) — Torch, Auto-place Tooltip, 24h Session
- **Flashlight torch** in the donor barcode scanner: probes `track.getCapabilities().torch`; if supported, an overlay button toggles `applyConstraints({advanced:[{torch:bool}]})`. Mostly Android Chrome.
- **Auto-placed badge** on admin item cards: 🤖 indigo pill with native tooltip explaining which pallet/parent was auto-picked and why.
- **24h editor session toggle**: `_make_edit_token(ttl_hours=...)` capped to 24; `POST /api/public/shipments/{token}/login` accepts `ttl_hours` body field; PIN dialog has a "Stay signed in for 24 hours" checkbox.
- **Tests:** `TestEditTokenTTL` added (3 cases) → **14/14 pytest pass**.

## Iteration 191 (Feb 2026) — Donor Scanner: Camera + Multi-Photo Fixes
- **Live barcode bug:** `enumerateDevices()` ran before permission was granted → empty deviceId → "Camera not available" toast. Now triggers `getUserMedia({facingMode:'environment'})` first, attaches the stream to the video element, then runs ZXing decoding. Tracks stop on dialog close.
- **Photo bug:** mobile `capture` attribute disabled `multiple`. Split into separate "Take photo" (single, append) and "Pick from gallery" (multiple, append) tiles. Up to 3 photos with per-thumbnail remove button + counter.
- Lint clean for changed code (pre-existing apostrophe warnings on unchanged line 604 untouched).

## Iteration 190 (Feb 2026) — Broader AI Vocabulary + Auto-Stacking
- **AI categories expanded** from 9 → 17: added Furniture, Tools, Construction, School, Agriculture, Sports, Toiletries, BabyGear, Bicycle. Prompt now explicitly mentions cement bags, rebar, wheelchairs, wheelbarrows, mattresses, strollers, solar panels, etc. with realistic weight anchors.
- **Auto-placement helper `_auto_place_on_pallet`**: when a pallet-bound item arrives without `pallet_id`, picks the lightest pallet. When `parent_id` is empty, stacks lighter items on top of the heaviest bottom-layer item on that pallet (with proper `z_cm` offset). Returns `auto_placed`/`auto_stacked` flags so the UI can confirm to the donor.
- **Tests:** 4 new `TestAutoStack` cases in `test_iter186_dedupe.py` → **11/11 pytest pass**.

## Iteration 189 (Feb 2026) — Fix: Photo+AI Scanner Always Returned "Unknown"
- **Bug:** `_persist_shipment_image` awaited a non-existent `storage.upload_bytes`, so every photo fell to the disk fallback. AI scan then tried to re-download via `httpx.get(image_urls[0])` against a relative path → failed silently → AI got an empty file → always `name="Unidentified item"`, `ai_confidence="low"`.
- **Fix:** AI now uses raw bytes already in memory (no re-download). Storage uses the correct sync `put_object` via `asyncio.to_thread`. Disk fallback URL now correctly prefixed with `/api/`.
- **Tests:** new `test_iter189_scan_photo_ai.py` (2/2 pass). Combined regression suite **18/18 pass**.

## Iteration 188 (Feb 2026) — Fix Shipment PIN Login Redirect
- **Bug:** Wrong PIN on `/donate/shipment/{token}` redirected donors to the main app `/login` page instead of showing the "Incorrect PIN" toast. Cause: global axios 401-interceptor in `services/api.js` whitelisted `/auth/login`, `/kiosk/pin-checkin`, etc. but not `/public/shipments/`.
- **Fix:** Added `/public/shipments/` to `LOGIN_PATHS_SKIP_REDIRECT`. PIN failures and expired edit-token 401s now stay on the donor page and surface the existing toasts.
- **Verified:** production backend returns 200 + edit_token for the correct PIN; redirect was purely client-side.

## Iteration 187 (Feb 2026) — Auto-Prune Over-Pledged Donations
- New admin endpoint `POST /api/shipments/{id}/prune-over-pledged` trims any item whose `qty_acquired > qty_needed` back to the pledged cap and logs the surplus on `items[*].surplus_redistributed` (qty/at/by) for audit. Idempotent.
- New "Prune over-pledged (N)" button (amber, Scissors icon) on the admin shipment items list — appears only when at least one item is over-pledged.
- `test_iter186_dedupe.py` extended with 2 prune tests → **7/7 pytest pass**.

## Iteration 186 (Feb 2026) — Shipment Inventory Dedupe + Over-pledge Warning
- Backend: `_add_or_merge_item` in `routers/shipments.py` merges items with the same ISBN/UPC on the same pallet (increments `qty_acquired`) instead of inserting duplicates. Wired into both admin (`POST /api/shipments/{id}/items`) and PIN-gated public (`POST /api/public/shipments/{token}/items`) routes.
- Response now includes `merged: true` and `over_pledged: true` flags.
- Frontend `ShipmentDonorPage.jsx`: manual-add + scan-confirm paths both surface `toast.success("Merged…")` and `toast.warning("Over-pledged…")` reading the new flags.
- New `test_iter186_dedupe.py` — **5/5 pytest pass** (ISBN merge, UPC merge, over-pledge flag, cross-pallet stays separate, public endpoint dedupes).

## Iteration 86 (May 3, 2026) — Marketplace Invoices + Resource Barcodes
**Verified 14/14 backend tests PASS + frontend fix applied.**

### Marketplace Editable Invoices
- New `routers/invoices.py` — CRUD + atomic counter for `INV-DRAFT-YYYYMMDD-NNNN`
- Workflow: `draft` → `sent` → `converted` (linked to sale receipt) / `cancelled`
- `POST /api/invoices/{id}/convert` — creates real sale, decrements stock, assigns receipt `INV-YYYYMMDD-NNNN`, links `sale.from_invoice`; body overrides supported for last-minute adjustments
- New "Invoices" tab on `/sales` with full CRUD UI
- `InvoicePrintable` component — A4 or 80mm thermal, 58:12 logo header, status stamp, WhatsApp share

### Resource Tracking with 58:12 Barcodes
- Auto-issued serial format: `5812-{COUNTRY}{LOC_ABBR}-{DDMMYY}-{NNNN}` (e.g. `5812-UGUGA-030526-0001`)
- COUNTRY from `location.country`, LOC_ABBR from `location.code`/auto-derived, NNNN from atomic counter
- `POST /api/resources/{id}/generate-serial` — issue on demand
- Custom serials preserved; barcode mirrors serial_number (CODE128)
- Public `GET /api/resources/by-serial/{serial}` — no-auth scanner endpoint
- Public `/resource/:serial` page — shows name, location, condition, owner on scan
- `BarcodeLabelDialog` component — printable 60mm×30mm thermal labels

## Iteration 85 / 84 / 83 (May 2-3, 2026) — Net P&L on Balance Sheet / Favicon / 58:12 Brand Theme
- Net Profit/Loss card on Balance Sheet (hero placement, green/red with margin %)
- Accounts Receivable split out, Net Worth incl. assets
- Official 58:12 favicon set (favicon.ico + logo192/512 + apple-touch-icon)
- Brand teal `#48a9c5` + deep navy `#1a1a2e` applied app-wide via CSS variables

## Iteration 82 (May 2, 2026) — Mark-as-Paid + Boards Admin Filter
- **Primary color**: teal `#48a9c5` (hsl 193 51% 53%) — exact match with 5812-global.org site
- **Foreground / text**: deep navy `#1a1a2e` (hsl 240 24% 14%) — from the "58:12" logo text
- Full light + dark theme palettes updated in `src/index.css`
- New brand tokens: `--brand-teal`, `--brand-teal-dark`, `--brand-teal-soft`, `--brand-navy`
- Tailwind config extended with `brand.teal`, `brand.teal-dark`, `brand.teal-soft`, `brand.navy` color classes
- `manifest.json` and `index.html` `theme-color` meta → `#48a9c5`
- Selection colour, sidebar-active, shadows, scrollbar all re-tinted to teal/navy
- Board reassignment on production: Uganda→loc_419f5d5e, Kenya→loc_67886e61, Haiti→loc_39aa9967, Thailand→loc_7169eead (58:12 United)

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
