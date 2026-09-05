# CHANGELOG

## iter 293 — 2026-02 — Review Queue UI · PDF FX · nested sublocations

**Receipt Review Queue UI** — FinancePage now has a 5th tab **Review Queue**
(`data-testid="finance-tab-review"`) that renders the `ReviewQueuePanel`
component (FinancePage.jsx:151). The panel:
- lists all draft JEs from `GET /api/finance/receipts/review-queue`,
- shows each line's Dr/Cr + account code/name,
- **Reclassify** button swaps a line's account inline (Select dropdown of the
  full COA), then **Save & repost** hits `PUT /api/finance/journal/{id}` with
  the new lines (backend reverses the original and posts a replacement),
- **Approve** button hits `PUT /api/finance/receipts/{id}/approve` and clears
  `needs_review`.

**PDF report FX conversion** — `GET /api/reports/pdf` now accepts optional
`fx_target` + `fx_rate` query params. When both are supplied and rate>0,
every money figure in the PDF (totals, breakdown rows) is multiplied by the
rate, and a note is rendered at the top: *"All amounts converted to
&lt;target&gt; at rate &lt;rate&gt;."* Column headers carry a `(<CCY> @
<rate>)` suffix. Absent/zero rate → PDF renders in the base currency
untouched.

**Nested sublocation picker** — Reports location dropdown now sorts
sublocations directly under their parent and prefixes them with a `└` glyph
+ `pl-4` padding (`ReportsPage.jsx:200-220`). Each option carries
`data-testid="report-location-option-<id>"`.

**HR payday scheduler — verified** — Confirmed that
`_fire_payday_payslip_generation()` is invoked from
`server.py:783` inside the daily 08:00 UTC branch. The manual endpoint
`POST /api/hr/payslips/generate-payday` responds 200 in all scenarios (no-op
when no campus has payday today).

**Verification**
- Backend pytest (iter 293): 10/10 pass.
- Testing agent iter 227 (final): full UI + backend regression **GREEN**.
- Prior iter 98 flagged a missing `ReviewQueuePanel` definition — root
  cause was a search_replace edit that errored silently. Definition
  re-inserted and verified on disk.

---

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration

**bank.py migrated fully off the deleted `routers.accounting` module** —
every cash movement now flows through the unified `finance_journal_entries`
ledger via `routers.finance._common.post_journal_entry`.

- `_post_bill_to_ledger`, `_post_bill_payment_to_ledger` — rewritten to
  resolve AP (code 2000), tax (code 2200), and item expense accounts against
  `finance_chart_of_accounts` and post one balanced JE per event with an
  `idempotency_key` (`bill:<id>`, `bill_payment:<id>`).
- `create_bank_account` — `linked_account_id` validated against the NEW COA.
- `list_bank_accounts` — `current_balance` aggregation now unwinds
  `finance_journal_entries.lines`.
- `reconcile_transaction` — `matched_entry_id` lookup switched to
  `finance_journal_entries`.
- `accounting_shim.py` deleted; the two helpers it exposed inlined into
  unmounted `routers/financial.py` so HR's `/repair-payslip-journals`
  endpoint still resolves.

Regression pytest `test_iter292_bank_finance_migration.py`: 2/2 pass.

---

## Prior work

Iter 285–291 · Finance/Tesseract-OCR/HR-payroll double-entry integration,
Restricted Access lockdown, Guest Pass checkpoint scanning, JE inline
editing, Report Table view with CSV/PDF exports + FX conversion, seed COA
guarded, locked periods surfaced in Settings.

Iter 1–285 · full multi-tenant CRM buildout (RBAC, unified comms, events,
kiosk, HR, sales/POS, NFC badges, marketplace).
