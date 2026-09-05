# PRD — 58:12 Global Connect CRM

## Original problem statement (source of truth)
Multi-tenant CRM for 58:12 Global's Uganda operations. Needs:
- Unified comms (WebRTC calling + WebSockets chat), campus-scoped.
- Kanban tasks, calendar, events with due-task overlay, volunteer/shift
  scheduling — all campus-scoped.
- Full double-entry Finance & Accounting on `finance_journal_entries`, strict
  location enforcement, PDF reports (with FX), receipt OCR + reviewer
  approval queue, bank statement import, vendors / bills (AP), recurring
  JEs, bank reconciliation. All hot paths must be indexed.
- HR / Payroll with auto-posted double-entry JEs + payday scheduler at
  08:00 UTC.
- Director overdue-task morning digest email + in-app preview widget with
  inline snooze.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- Bulk variant barcode printing.
- NFC badge issuance with HMAC-SHA256 signatures; Wallet passes cached
  offline in a Service Worker so checkpoint scans work with no signal.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 297)

### DONE
- Unified finance ledger — sole source of truth.
- Receipt Review Queue UI + PDF FX + nested sublocation picker.
- Bulk variant barcode printing + director digest email + digest preview
  widget with inline snooze (iter 297).
- MongoDB hot-path indexes on every collection introduced since iter 285.
- **PWA offline data + wallet pass cache** — sw.js `5812-crm-v4` +
  `5812-offline-data-v1` caches; `usePwaOfflinePrefetch` hook preloads
  today's roster and the caller's own badge on login.

### Remaining backlog (agreed with user)
- **Next (c)** `server.py` modularization (~1750 lines → smaller routers).

## Boundaries from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

> Iter 296+: **Multi-language translation files** (option e) are on hold
> until the user explicitly requests them.

## Architecture (post iter 297)
```
Browser
  ├─ Service Worker (public/sw.js)
  │   ├─ CACHE_NAME = 5812-crm-v4       ← app shell + static assets
  │   ├─ WALLET_CACHE = 5812-wallet-v1  ← wallet passes (cache-first)
  │   └─ OFFLINE_DATA_CACHE = 5812-offline-data-v1
  │                                    ← today's roster + user dashboard
  │                                    (stale-while-revalidate)
  └─ App
      └─ usePwaOfflinePrefetch on login → prefetch-offline-set message

FastAPI (server.py)
  ├─ routers/finance/*  ← unified ledger (finance_journal_entries)
  ├─ routers/tasks.py   ← includes /tasks/director-digest-preview
  ├─ routers/bank.py    ← bills / bank recon / recurring
  ├─ routers/hr.py      ← payslips → post_journal_entry
  ├─ routers/reports.py ← /reports/pdf (with fx_target + fx_rate)
  └─ routers/financial.py ← UNMOUNTED. Legacy helpers inlined.

Daily 08:00 UTC scheduler:
  - birthday / anniversary
  - customer statements
  - overdue payment reminders
  - overdue task per-assignee emails
  - overdue task DIRECTOR DIGEST
  - payday payslip auto-generation
  - recurring journal entries / bills
```

## Credentials
See `/app/memory/test_credentials.md`.
