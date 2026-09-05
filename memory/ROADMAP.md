# ROADMAP — 58:12 Global Connect CRM

## P0 — none open
## P1 — none open

## P2 — Remaining polish

- **Mobile responsiveness audit — remaining pages**. Finance is done (iter
  294). Still to walk at 390×844: People / Members, Reports, Calendar, HR
  Payroll, Sales / POS, Kiosk. Fix overflow tables + fixed grids the same way
  Finance was fixed (horizontally scroll tabs, wrap tables in
  `overflow-x-auto -mx-4 md:mx-0`).

## Future / Backlog

- `server.py` modularization (split into smaller routers).
- PWA offline mode + service worker for Wallet passes.
- Multi-language translation files.
- Bcrypt version pinning; MongoDB index optimization pass.

## Explicit user boundary

> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."
