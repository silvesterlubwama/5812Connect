# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 54 - Feb 2026)
- [x] Profile photo upload UI: circular avatar with hover overlay on UserEditDialog + child edit dialog
- [x] Members/children list avatars show photo_url when available
- [x] Child edit: typed parent search (Input filters by name/phone, selected parents shown as removable badges)
- [x] Children at restricted locations show "Tracked" badge + Print Badge button for tracking
- [x] Staff auto-guest: creating staff users auto-creates guest record for their campus (is_staff_guest=true)

## Changes (Iteration 53)
- [x] Badge bg: dark default, white ONLY for kiosk. Real country outlines (world-map-country-shapes). CSV templates. Children import enhanced. Profile photo upload API.

## Changes (Iterations 49-52)
- [x] Kiosk QR fix, backend decomposition, component splitting, CallContext hooks, type hints, ternary cleanup
- [x] Badge watermark, NFC symbol/CRUD/writing (director+), footer redesign

## Architecture Notes
- **Route Ordering**: Static routes BEFORE dynamic routes
- **Auth Storage**: `secureStorage.js`
- **Campus Isolation**: "All Locations" for System Admin/Admin/ED/Adviser only
- **Photos**: Object storage primary, /app/backend/uploads/photos/ fallback
- **NFC**: Stored on member/user records. Write=director+. Audit in nfc_write_log
- **Country Outlines**: world-map-country-shapes, mapped via COUNTRY_TO_CODE in countryOutlines.js

## Test Reports
- Iterations 49-54: All 100%

## Pending
- Wallet pass improvement (currently downloads PNG)
- Future: Wave H5 SDK upgrade, server.py modularization
