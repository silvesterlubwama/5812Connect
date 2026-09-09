# ROADMAP — 58:12 Global Connect CRM

## P0 — none open
- ~~Rate limiter global, not per user~~ → fixed in iter318 (per-user JWT
  buckets, real client IP for anonymous, tight per-IP bucket on auth routes).

## Awaiting user decision — 2 dead screens left (was 13 paths, iter318 audit)
Fixed in iter319: member document download/archive, member bulk export, POS
store settings, Invoices tab (+ accounts-receivable and public quote accept,
which came back with it). Still dead, need a decision — rebuild or remove:
- **CampusReportsPage** — in the nav, but `/api/reports/campus/{loc}` never existed
- **Public product ordering** (PublicBookingsPage) — `/api/public/products`
  and `/api/public/orders` never existed; is the public page events-only?

## Resolved this iteration
- Holiday policy screen (HR → Holidays) — shipped iter318b.
- Dashboard campus flip — user chose "follow the sidebar switcher"; shipped
  (scope badge only, no second control).

## Previously awaiting user decision
- **Dashboard campus flip** — explained to the user in iter318, not built.
  Proposal: a scope selector on the dashboard header with "All campuses I can
  see" vs one specific campus, driving `dashboardApi.stats`,
  `dashboardApi.actionItems` and `/reports/summary` (which already accept
  `campus_id` / `location_id`). Independent of the global campus switcher in
  the sidebar; resets on reload unless we persist it.

## P2 — nice-to-have hardening (not requested)
- `server.py` imports all routers in one try/except logged as WARNING; one bad
  import silently unregisters every router after it.
- `fare_alerts` collection still exists though the feature was wiped (iter326).

## Approved backlog (user-requested only)

_(no items currently open)_

Deferred, not requested — do NOT start without the user asking:
- `routers/events.py` split (2,726 lines / 71 endpoints: events, checkins,
  kiosk, venues, public bookings). Kept whole in iter316 on purpose.
- `CalendarPage.jsx` is ~880 lines; dialogs could be extracted further.

## Explicit user boundaries

> "Never suggest Wave H5 SDK again unless I call for it. Do not suggest
> unrequested enhancements moving forward."

> "P1 and P2 items were never requested — removed from roadmap"
> (iter 302). Wallet .pkpass, kiosk badge full-screen mode, and portal
> everything-synced pill are all OUT of scope unless the user explicitly
> asks again.

> **Multi-language translation files** on hold until explicitly requested.
