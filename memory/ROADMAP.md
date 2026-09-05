# ROADMAP — 58:12 Global Connect CRM

## P0 (blockers) — none open

The last P0 (bank.py shim retirement) landed in iter 292.

## P1 — Next up

### Receipt Review Queue UI
- Backend already exposes `GET /api/finance/receipts/review-queue` and
  `POST /api/finance/receipts/{id}/approve`.
- Build a panel on `/app/frontend/src/pages/FinancePage.jsx` that lists
  draft/needs_review receipts, lets a reviewer see the OCR fields, reclassify
  the account, and click Approve.
- After approve, the receipt should call `post_journal_entry` and disappear
  from the queue.

### HR auto-payslip cron on payday
- Endpoint `/api/hr/payslips/generate-payday` is idempotent.
- Wire it into a scheduled hook (`webhook-crond.sh` daily, or an
  APScheduler job in `deps.py`'s scheduler) that fires on payday and no-ops
  the rest of the month.

## P2 — Polish

- PDF export templates in `routers/finance/reports.py` must consume the
  `fx_target` / `fx_rate` params (verify current template does the conversion).
- Sublocations in the Finance Reports location dropdown render as flat "(sub)"
  entries — visually nest them or indent children under their parent.
- Full variant barcode printing page (layout + bulk print).
- Mobile responsiveness audit across all pages.

## Backlog / Future

- `server.py` modularization (currently ~1600 lines).
- PWA offline mode + service worker for Wallet passes.
- Multi-language translation files.
- Bcrypt version pinning; MongoDB index optimization pass.
- Scheduled cron jobs for overdue-task email digests.

## Explicit user boundary

> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

Do not propose Wave H5 or unrequested enhancements. Stick to P1 / P2 / Backlog
above.
