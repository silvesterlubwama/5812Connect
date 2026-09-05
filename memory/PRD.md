# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations. Needs:
- Unified comms (WebRTC calling + WebSockets chat), campus-scoped.
- Kanban tasks, calendar, events with due-task overlay, volunteer/shift
  scheduling — all campus-scoped.
- Full double-entry Finance & Accounting on a unified ledger
  (`finance_journal_entries`), strict location enforcement, PDF reports
  (with FX), receipt OCR + reviewer approval queue, bank statement import
  (CSV / PDF), vendors / bills (AP), recurring JEs, bank reconciliation.
- HR / Payroll wired to auto-post double-entry JEs; payday scheduler at
  08:00 UTC.
- Director overdue-task morning digest.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- Bulk variant barcode printing to a physical label printer.
- NFC badge issuance with HMAC-SHA256 signatures; profile PDF + Wallet passes.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 294)

### DONE
- Unified finance ledger — sole source of truth. Legacy `accounting.py` and
  `accounting_shim.py` both deleted; bank.py migrated (iter 292).
- Receipt Review Queue UI + PDF FX + nested sublocation picker (iter 293).
- Bulk variant barcode printing + director digest + mobile Finance layout
  fixes (iter 294).
- Payday scheduler + overdue-task per-assignee emails + director digest all
  fire from the daily 08:00 UTC branch.

### Remaining backlog
- **P2** Mobile responsiveness — Finance done; remaining pages (People,
  Reports, Calendar, HR, Sales) not yet audited at 390×844.
- **Future** `server.py` modularization (~1614 lines).
- **Future** PWA offline support + Service Worker for Wallet passes.
- **Future** Multi-language translation files.
- **Future** Bcrypt version pinning + MongoDB index optimization pass.

## Boundary from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

## Architecture (finance + scheduler) — post iter 294
```
FastAPI (server.py)
  ├─ routers/finance/*   ← unified ledger (finance_journal_entries)
  │      _common.post_journal_entry(...)   ← ONE write path
  ├─ routers/bank.py     ← bills / bank recon / recurring → post_journal_entry
  ├─ routers/hr.py       ← payslips → post_journal_entry
  ├─ routers/reports.py  ← /reports/pdf (with fx_target + fx_rate)
  └─ routers/financial.py ← UNMOUNTED. Legacy helpers inlined for HR's
                            `/repair-payslip-journals` endpoint.

Daily scheduler loop (server.py:731+) at 08:00 UTC fires:
  - birthday / anniversary notifications
  - scheduled customer statements
  - overdue payment reminders
  - overdue task per-assignee emails
  - overdue task DIRECTOR DIGEST (iter 294)
  - payday payslip auto-generation
  - recurring journal entries / bills
```

## Credentials
See `/app/memory/test_credentials.md`.
