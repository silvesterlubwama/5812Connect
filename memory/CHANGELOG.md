# CHANGELOG

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration

**bank.py migrated fully off the deleted `routers.accounting` module** — every cash
movement now flows through the unified `finance_journal_entries` ledger via
`routers.finance._common.post_journal_entry`.

Changes:
- `_post_bill_to_ledger`, `_post_bill_payment_to_ledger` — rewritten to resolve AP
  (code 2000), tax (code 2200), and item expense accounts against
  `finance_chart_of_accounts` and post one balanced JE per event with an
  `idempotency_key` (`bill:<id>`, `bill_payment:<id>`).
- `create_bank_account` — `linked_account_id` now validated against the NEW COA
  (`finance_chart_of_accounts`, type must be `asset`).
- `list_bank_accounts` — `current_balance` aggregation now unwinds
  `finance_journal_entries.lines` (skips reversed JEs) instead of reading the
  legacy `accounting_entry_lines`.
- `reconcile_transaction` — `matched_entry_id` lookup switched to
  `finance_journal_entries`.
- Module-level docstring updated to reflect the new ledger path.

`accounting_shim.py` — **DELETED**. The two helpers it exposed (`_next_entry_number`,
`reverse_entry`) were inlined at the top of `routers/financial.py` so the still-
unmounted legacy repair endpoints there (called only from HR's
`/repair-payslip-journals`) continue to work.

Verification:
- `/app/backend/tests/test_iter292_bank_finance_migration.py` — 2/2 pass
- Testing agent regression (iter 97): 13/15 pass; the 2 flaky tests were both in
  the new test's balance assertion (pre-existing data pollution on shared COA
  1010, not a real bug).
- End-to-end curl: bill create → JE posted (Dr Office & Admin / Cr AP, balanced,
  location-scoped). Bill payment → JE posted (Dr AP / Cr Bank). Recurring JE
  run-now → JE posted with source="manual" via unified ledger.

---

## Prior work (from earlier forks)

- iter 291: `routers/accounting.py` deleted, `accounting_shim.py` created as a
  temporary bridge for `bank.py` and unmounted `financial.py`.
- iter 285–290: Finance/Tesseract-OCR/HR-payroll double-entry integration,
  Restricted Access lockdown, Guest Pass checkpoint scanning, JE inline
  editing, Report Table view with CSV/PDF exports + FX conversion, seed COA
  guarded and locked periods surfaced in Settings.
- Iterations 1–285: full multi-tenant CRM buildout (RBAC, unified comms,
  events, kiosk, HR, sales/POS, NFC badges, marketplace).
