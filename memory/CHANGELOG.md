# CHANGELOG

## iter 294 — 2026-02 — Bulk barcodes · Director digest · Mobile Finance

**Bulk variant barcode printing** — `VariantBarcodePrint` now accepts an
optional `products` prop (array). When supplied, it aggregates every variant
across every selected product into a single labelled print job, hides the
"Regenerate all" button (which is inherently single-product), and swaps the
header to *"Bulk barcodes — N products · M variants"*. A new bulk-action on
`BulkActionBar` (`data-testid="bulk-print-barcodes-btn"`) opens the dialog
against the current selection on `ProductsPage`, so staff can select 20+
products in the grid and send every one of their variants to the label
printer in one job.

**Director overdue-task digest** — New async
`_fire_overdue_task_director_digest()` at `server.py:992`. Wired into the
daily 08:00 UTC scheduler at `server.py:783`. Each director+ user (Director,
Regional Director, admin, system_admin, Executive Director, Adviser) gets a
single email listing every overdue task in their scope
(admins/EDs/Advisers see everything; other roles are filtered by
`location_ids ∪ active_campus_id`). Idempotent via `db.task_director_digests`
(one row per user per day). Complements the existing per-assignee
`_fire_overdue_task_emails`.

**Mobile Finance layout audit** — At 390×844 the Finance tab strip was
overlapping (5 tabs squeezed into a fixed grid). Fixed by switching
`TabsList` to `w-full flex overflow-x-auto no-scrollbar md:grid md:grid-cols-5
md:max-w-3xl` — mobile scrolls the strip horizontally, desktop keeps the
grid layout. All four Finance tables (Recent activity, Journal, Review
Queue, Chart of Accounts) now wrap in `overflow-x-auto -mx-4 md:mx-0` so
long rows scroll cleanly instead of pushing the page.

**Verification**
- Testing agent iter 228: 9/9 backend pass, digest idempotency + scope
  guards verified end-to-end, mobile Finance layout confirmed clean.

---

## iter 293 — 2026-02 — Review Queue UI · PDF FX · nested sublocations
(previous, unchanged)

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration
(previous, unchanged)
