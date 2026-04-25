# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 57 - Feb 2026)
- [x] Children import: parent_cache skips repeated parents in batch, admin campus fallback for location_id
- [x] Badge bg restored to dark (color) by default; white only for kiosk non-badge-holder check-ins
- [x] Country outlines: ESM/CJS compatibility fix (rawCountriesData?.default fallback)
- [x] Timezones expanded: 50+ options (Asia/Bangkok, America/Port-au-Prince, etc.)
- [x] Venue CRUD in Campus Settings: add/delete venues with is_external flag, external venues in selection
- [x] Admin-configurable group types: CRUD at /api/group-types, defaults created on first load
- [x] VenueCreate/VenueUpdate models updated with is_external field

## Previous Changes (Iterations 49-56)
- User directory endpoint, outreach location/venue, bi-monthly/quarterly recurrence
- Staff-guest linking, portal fix, country code, guest delete, ID Number rename
- Badges (country/NFC/footer), templates, import, photos, parent search, tracked children
- QR camera, backend decomposition, hooks, type hints

## Architecture Notes
- **User Directory**: /api/admin/users/directory bypasses campus
- **Group Types**: /api/group-types — admin CRUD, defaults on first load
- **Venues**: is_external flag, external venues included in location venue lists
- **Badge Bg**: Dark default, white only via kioskMode=true prop
- **Import**: parent_cache dedup, admin campus fallback

## Test Reports: Iterations 49-57 all 100%

## Pending
- Wallet pass improvement (Apple/Google Wallet)
- Stale data after deletion (cascade refresh)
- Future: Wave H5 SDK, server.py modularization
