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
- Director overdue-task morning digest email + in-app preview widget.
- Sales portal, POS, Shipments tracking, consumable resources tracking.
- Bulk variant barcode printing.
- NFC badge issuance with HMAC-SHA256 signatures; Wallet passes.
- Kiosk check-in via phone-last-4, QR, and NFC — with lockdowns on restricted
  locations.
- Guest Pass / Checkpoint scanning at security perimeters.
- Social Work case management.

## Current status (as of iter 296)

### DONE
- Unified finance ledger — sole source of truth.
- Receipt Review Queue UI + PDF FX + nested sublocation picker.
- Bulk variant barcode printing + director digest email.
- Director digest preview widget on Dashboard + mobile tab strips on
  People / HR / Sales.
- **MongoDB hot-path indexes on every collection introduced since iter 285**
  (iter 296). Bcrypt/passlib pinning verified.

### Remaining backlog (agreed with user)
- **Next (d)** PWA offline support + Service Worker for Wallet passes.
- **After that (c)** `server.py` modularization (~1750 lines).

## Boundaries from user
> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

> Iter 296: **Multi-language translation files** (option e) are on hold until
> the user explicitly requests them.

## Architecture (post iter 296)
```
FastAPI (server.py)
  ├─ routers/finance/*  ← unified ledger (finance_journal_entries)
  ├─ routers/tasks.py   ← includes /tasks/director-digest-preview
  ├─ routers/bank.py    ← bills / bank recon / recurring
  ├─ routers/hr.py      ← payslips → post_journal_entry
  ├─ routers/reports.py ← /reports/pdf (with fx_target + fx_rate)
  └─ routers/financial.py ← UNMOUNTED. Legacy helpers inlined.

MongoDB indexes (server.py:_ensure_indexes) now cover 40+ hot paths across
users, members, events, tasks, boards, checkins, chat, notifications,
guest_passes, guest_access_requests, checkpoint_events, files,
password_resets/sessions (TTL), locations, push_subscriptions,
audit_log(s), wallet_badges, deleted_items (TTL), security_checkpoint_*,
sales, login_attempts (TTL), children, chart_accounts, donations, expenses,
chart_account_transfers, accounting_entries, fare_alerts, shipments,
finance_journal_entries (incl. partial-unique idempotency_key),
finance_chart_of_accounts, bank_accounts, bank_transactions, vendors, bills,
recurring_entries, reconciliation_rules, task_director_digests (unique +
90-day TTL), payslips, hr_employees, hr_contracts, kanban_boards.

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
