# ROADMAP — 58:12 Global Connect CRM

## P0 — none open
- ~~Rate limiter global, not per user~~ → fixed in iter318 (per-user JWT
  buckets, real client IP for anonymous, tight per-IP bucket on auth routes).

## BLOCKED ON USER (iter320)
1. **Verify `5812-global.org` in Resend** → then set `SENDER_EMAIL` back to
   `uganda@5812-Global.org`. Until then email only reaches the Resend account
   owner. Everything else is wired.
2. **Online payments**: user said "something else you already use" but never
   named the provider. The API-key vault is now secure and reachable, but no
   code charges anything — a checkout needs provider-specific calls + a webhook
   receiver + transaction records. Blocked until they name the provider
   (Flutterwave would cover UGX + MTN/Airtel mobile money).

## Dead endpoints — CLEARED (iter319)
All resolved: public product sales BUILT, Campus Reports DROPPED, customers +
statements + reminders + single-resource GET reconnected, HR seed repointed.
Guard against regressions with `python3 /app/scripts/audit_api_paths.py`.

## (historical) Awaiting user decision — 2 dead screens left (was 13 paths, iter318 audit)
Both resolved in iter319b: CampusReportsPage deleted, public product ordering
built with server-side re-pricing.

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
