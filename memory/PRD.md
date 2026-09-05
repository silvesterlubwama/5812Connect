# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations. Needs:
- Unified comms (WebRTC calling + WebSockets chat) with campus-scoped user
  directory and no ghost users.
- Kanban tasks, calendar, events with due-task overlay, volunteer/shift
  scheduling — all campus-scoped.
- Full double-entry Finance & Accounting on a single unified ledger
  (`finance_journal_entries`), with strict location enforcement, PDF reports
  (with FX conversion), receipt OCR (Tesseract) + reviewer approval queue,
  bank statement import (CSV / PDF), vendors / bills (AP), recurring JEs,
  bank reconciliation.
- HR / Payroll wired to auto-post double-entry JEs, with a payday scheduler
  that fires draft payslips at 08:00 UTC on each campus's payday.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- NFC badge issuance with HMAC-SHA256 signatures; profile PDF + Wallet passes.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 293)

### DONE
- Unified finance ledger (`finance_journal_entries`) is the single source of
  truth. `routers.accounting` and `accounting_shim.py` both deleted; bank.py
  fully migrated (iter 292).
- **Receipt Review Queue UI** on FinancePage (iter 293).
- **PDF report FX conversion** via `fx_target` + `fx_rate` query params
  on `/api/reports/pdf` (iter 293).
- **Nested sublocation picker** in ReportsPage location dropdown (iter 293).
- **HR payday scheduler** wired at `server.py:783` (verified iter 293).
- Restricted-location kiosk lockdown, Guest Pass ↔ checkpoint validation,
  JE inline editing with reversal chain, Report Table view + CSV/PDF/FX
  exports, seed COA guarded, locked-period UI, receipt OCR (Tesseract) with
  mobile camera capture.
- Unified badge (QR + photo merged), profile PDFs, NFC HMAC signing.

### Remaining backlog
- **P2** Full variant barcode printing UI (layout + bulk print).
- **P2** Mobile responsiveness audit across all pages.
- **Future** `server.py` modularization (currently ~1614 lines).
- **Future** PWA offline support + Service Worker for Wallet passes.
- **Future** Multi-language translation files.
- **Future** Bcrypt version pinning + MongoDB index optimization pass.
- **Future** Scheduled overdue-task email digests.

## Boundary from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

No Wave H5, no unrequested features. Stick to the backlog above.

## Architecture (finance) — post iter 293
```
Client
  │
  ▼
FastAPI (server.py)
  ├─ routers/finance/*  ← unified ledger (finance_journal_entries)
  │      _common.post_journal_entry(...)   ← ONE write path
  │      journal.py, setup.py, transactions.py, receipts.py, reports.py
  ├─ routers/bank.py           ← bills / bank recon / recurring → post_journal_entry
  ├─ routers/hr.py             ← payslips → post_journal_entry
  ├─ routers/reports.py        ← /reports/pdf (with fx_target + fx_rate)
  └─ routers/financial.py      ← UNMOUNTED. Legacy shim helpers inlined here
                                 for HR's `repair-payslip-journals` endpoint.
```

Daily scheduler loop (server.py:731+) fires at 08:00 UTC:
- birthday/anniversary notifications
- scheduled customer statements
- overdue payment reminders
- overdue task emails
- **payday payslip auto-generation** (`_fire_payday_payslip_generation`)
- recurring journal entries / bills (`fire_due_recurring_entries`)

## Credentials
See `/app/memory/test_credentials.md`.
