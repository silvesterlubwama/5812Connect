# ROADMAP — 58:12 Global Connect CRM

## P0 — none open

Iter 292 (bank.py shim retirement) and iter 293 (Review Queue UI, PDF FX,
sublocation nesting, payday scheduler verify) both landed clean.

## P1 — none open

All P1 items from the previous fork were shipped in iter 293. If new P1s
come in, they belong at the top of this section.

## P2 — Polish

- **Full variant barcode printing** — new page with a printable layout and
  bulk-print button (product variants have `barcode` fields already).
- **Mobile responsiveness audit** — walk every page at 390×844 and fix
  overflow / cramped controls.

## Future / Backlog

- `server.py` modularization (currently ~1614 lines → split into smaller
  routers).
- PWA offline mode + service worker for Wallet passes.
- Multi-language translation files.
- Bcrypt version pinning; MongoDB index optimization pass.
- Scheduled cron jobs for overdue-task email digests (endpoint exists;
  wire it into the daily scheduler loop the same way payday was wired).

## Explicit user boundary

> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

Do not propose Wave H5 or unrequested enhancements. Stick to P2 / Backlog
above.
