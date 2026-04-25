# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 56 - Feb 2026)
- [x] User directory endpoint: GET /api/admin/users/directory returns ALL users regardless of campus (fixes missing profiles on boards/tasks)
- [x] TasksPage, ExtensionsPage, PbxSettingsPage now use directory endpoint for user resolution
- [x] OutreachPage: programme form now has Campus/Location + Venue selectors with location-based venue loading
- [x] Bi-monthly and quarterly recurrence added to Events and Outreach pages
- [x] External venues included in venue selection (is_external or no location_id)
- [x] Outreach recurrence interval labels cleaned up with lookup objects

## Changes (Iteration 55)
- [x] Staff-guest linking with user_id, Portal button fix, Country Code field, Guest individual delete
- [x] ID Number rename, Group removed from staff profiles, Donor tag removed, Kiosk locked mode no exit

## Previous (Iterations 49-54)
- QR camera, backend decomposition, hooks, type hints, badges (country/NFC/footer), templates, import, photos, parent search, tracked children

## Architecture Notes
- **User Directory**: /api/admin/users/directory — bypasses campus for board/task assignee resolution
- **Route Ordering**: Static before dynamic
- **Venues**: External venues (is_external=true or no location_id) included in all location venue lists
- **Recurrence**: daily, weekly, biweekly, monthly, bimonthly, quarterly, yearly, nth_weekday, nth_week

## Test Reports: Iterations 49-56 all 100%

## Pending
- External venue CRUD management in Campus Settings
- Admin-configurable group types
- Wallet pass improvement
- Future: Wave H5 SDK, server.py modularization
