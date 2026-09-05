# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations. Needs:
- Unified comms (WebRTC calling + WebSockets chat), campus-scoped.
- Kanban tasks, calendar, events with due-task overlay, volunteer/shift
  scheduling — all campus-scoped.
- Full double-entry Finance & Accounting on `finance_journal_entries`, strict
  location enforcement, PDF reports (with FX), receipt OCR + reviewer
  approval queue, bank statement import (CSV / PDF), vendors / bills (AP),
  recurring JEs, bank reconciliation.
- HR / Payroll with auto-posted double-entry JEs + payday scheduler at
  08:00 UTC.
- Director overdue-task morning digest email + in-app preview widget.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- Bulk variant barcode printing to a physical label printer.
- NFC badge issuance with HMAC-SHA256 signatures; profile PDF + Wallet passes.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 295)

### DONE
- Unified finance ledger — sole source of truth. Legacy `accounting.py` and
  `accounting_shim.py` both deleted; bank.py migrated (iter 292).
- Receipt Review Queue UI + PDF FX + nested sublocation picker (iter 293).
- Bulk variant barcode printing + director digest email + Finance mobile
  tabs (iter 294).
- **Director digest preview widget** on Dashboard + mobile tab strips on
  People / HR / Sales (iter 295).
- Daily 08:00 UTC scheduler fires: birthdays, statements, overdue payment
  reminders, per-assignee overdue task emails, director digest, payday
  payslip generation, recurring JEs.

### Remaining backlog
- **P2** Fine-tune remaining ~5-px header-button overflows on People / HR /
  Sales at 390×844.
- **Future** `server.py` modularization (~1614 lines).
- **Future** PWA offline support + Service Worker for Wallet passes.
- **Future** Multi-language translation files.
- **Future** Bcrypt version pinning + MongoDB index optimization pass.

## Boundary from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

## Architecture (post iter 295)
```
FastAPI (server.py)
  ├─ routers/finance/*   ← unified ledger (finance_journal_entries)
  ├─ routers/tasks.py    ← includes /tasks/director-digest-preview (iter 295)
  ├─ routers/bank.py     ← bills / bank recon / recurring
  ├─ routers/hr.py       ← payslips
  ├─ routers/reports.py  ← /reports/pdf (with fx_target + fx_rate)
  └─ routers/financial.py ← UNMOUNTED. Legacy helpers inlined.

Daily 08:00 UTC scheduler (server.py:731+):
  - birthday / anniversary notifications
  - scheduled customer statements
  - overdue payment reminders
  - overdue task per-assignee emails
  - overdue task DIRECTOR DIGEST
  - payday payslip auto-generation
  - recurring journal entries / bills

Dashboard (iter 295):
  ├─ LiveCheckpointWidget (director+)
  └─ DirectorDigestWidget  (director+, hides on empty)
```

## Credentials
See `/app/memory/test_credentials.md`.
