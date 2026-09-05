# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations. Needs:
- Unified comms (WebRTC calling + WebSockets chat) with campus-scoped user
  directory and no ghost users.
- Kanban tasks, calendar, events with due-task overlay, volunteer/shift
  scheduling — all campus-scoped.
- Full double-entry Finance & Accounting on a single unified ledger
  (`finance_journal_entries`), with strict location enforcement, PDF reports,
  FX conversion, receipt OCR (Tesseract), bank statement import (CSV / PDF),
  vendors / bills (AP), recurring JEs, bank reconciliation.
- HR / Payroll wired to auto-post double-entry JEs.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- NFC badge issuance with HMAC-SHA256 signatures; profile PDF + Wallet passes.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 292)

### DONE
- Whole finance stack unified onto `finance_journal_entries`.
- `routers.accounting` deleted; `accounting_shim.py` deleted; bank.py fully
  migrated to `post_journal_entry` (bills, bill payments, bank reconciliation,
  recurring JEs, bank-balance aggregation, linked-account validation).
- HR payroll double-entry integration, restricted-location kiosk lockdown,
  Guest Pass ↔ checkpoint validation, JE inline editing with reversal chain,
  Report Table view + CSV/PDF/FX exports, seed COA guarded, locked-period UI.
- Receipt OCR (Tesseract) end-to-end with mobile camera capture.
- Unified badge (QR + photo merged), profile PDFs, NFC HMAC signing.
- Regression pytest `test_iter292_bank_finance_migration.py` passing.

### P0 / P1 remaining
- **P1 — Receipt Review Queue UI** — backend `/api/finance/receipts/review-queue`
  + `/approve` exist; needs a panel on `FinancePage.jsx` for reviewers.
- **P1 — HR auto-payslip cron** — endpoint `/hr/payslips/generate-payday` exists;
  needs a scheduled hook (`webhook-crond.sh` or internal APScheduler job).
- **P2 — Verify PDF export templates** consume `fx_target` / `fx_rate` params in
  `routers/finance/reports.py`.
- **P2 — Sublocations nested visual in Reports location dropdown**
  (`ReportsPage.jsx`).

### Backlog
- Full variant barcode printing UI.
- Mobile responsiveness audit.
- `server.py` modularization (1600+ lines).
- PWA offline / service worker for Wallet passes.
- Multi-language translation files.
- Bcrypt version pinning + MongoDB index optimization.

## Boundary from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

Stick to the P0/P1 items above. No new libraries, no AI features, no
enhancements the user didn't ask for.

## Architecture (finance) — post iter 292
```
Client
  │
  ▼
FastAPI (server.py)
  ├─ routers/finance/*  ← unified ledger (finance_journal_entries)
  │      _common.post_journal_entry(...)   ← ONE write path
  │      reports.py, journal.py, setup.py, transactions.py, receipts.py
  ├─ routers/bank.py           ← bills, bank recon, recurring → post_journal_entry
  ├─ routers/hr.py             ← payslips → post_journal_entry
  └─ routers/financial.py      ← UNMOUNTED. Legacy shim helpers inlined here for
                                 HR's `repair-payslip-journals` repair endpoint.
```

Legacy `accounting_*` collections still exist for historical data + repair
endpoints, but no new writes go there.

## Credentials
See `/app/memory/test_credentials.md`.
