# ROADMAP — 58:12 Global Connect CRM

## P0 / P1 — none open

## Approved backlog

- **Server split** — break the ~1750-line `server.py` into smaller router files.
- **Portal receipt scan from own portal** — user asked to defer (took defaults).
  Once revisited: add a mobile-camera `Scan Receipt` button on `/portal/profile`
  or a new `/portal/expenses` action that hits the existing `/api/finance/receipts/scan` endpoint.
- **Portal audit sweep** — spot-check every existing Portal page (Family,
  Documents, Events, Expenses, Sales, Tasks) to confirm profile-fix flows
  (name/DOB/phone/address) end-to-end.

## Explicit user boundaries

> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

> Iter 296+: **Multi-language translation files** (option e) are on hold
> until the user explicitly requests them.
