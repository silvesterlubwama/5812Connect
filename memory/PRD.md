# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 55 - Feb 2026)
- [x] Staff-guest profile linking: staff creation auto-creates linked guest record with user_id
- [x] Guest/Parent Portal button now navigates to /portal (was non-functional)
- [x] Country Code (ISO) field added to location forms for accurate badge map outlines
- [x] Individual guest delete button on each guest card (was bulk-only)
- [x] "National ID" renamed to "ID Number" across the app
- [x] Group field removed from staff profiles (kept in guest/member add forms)
- [x] Donor tag removed from user flags
- [x] Kiosk locked mode: all exit options hidden (Exit link, Setup, Logout) — only Unlock visible

## Previous Changes
- Iterations 49-54: QR camera, backend decomposition, CallContext hooks, type hints, badge improvements (country watermark, NFC, footer), CSV templates, children import, photo upload, parent search, tracked children, staff auto-guest

## Architecture Notes
- **Route Ordering**: Static before dynamic
- **Auth**: secureStorage.js
- **Campus Isolation**: "All Locations" for admin/ED/adviser only
- **NFC**: Member/user records, write=director+, audit in nfc_write_log
- **Photos**: Object storage primary, local fallback
- **Country Outlines**: world-map-country-shapes (ISO codes via country_code on locations)
- **Staff-Guest Linking**: Guest records carry user_id for bidirectional link

## Test Reports: Iterations 49-55 all 100%

## Pending
- Wallet pass improvement
- Admin-configurable group types (currently hardcoded MOCK_GROUPS)
- Future: Wave H5 SDK, server.py modularization
