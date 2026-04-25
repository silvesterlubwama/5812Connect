# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with internal WebRTC calling, unified communications, NFC badge management, and optional PBX integration.

## Latest Changes (Iteration 53 - Feb 2026)
- [x] Badge bg: dark by default, white ONLY for kiosk check-in prints (ink saving)
- [x] Real country map outlines using `world-map-country-shapes` NPM package (ISO codes: UG, KE, HT, TH, US)
- [x] `country_code` (ISO) field added to Location models
- [x] CSV template downloads: GET /api/import/template/{children|staff|guests} with all fields including campus
- [x] Children import enhanced: auto-creates parents even without email, resolves campus names, creates both father/mother, merges existing data
- [x] Profile photo upload: POST /api/members/{id}/photo and /api/children/{id}/photo with object storage + local fallback
- [x] Photos served at GET /api/uploads/photos/{filename}
- [x] Badge components show profile photos when available

## Previous Changes (Iterations 49-52)
- [x] Kiosk QR Camera fix, backend function decomposition, frontend component splitting
- [x] CallContext hooks refactor, backend type hints, nested ternary cleanup
- [x] Badge country watermark, NFC symbol, footer redesign, NFC tag CRUD
- [x] NFC tag writing (director+ only) with audit logging

## Architecture Notes
- **Route Ordering**: Static routes BEFORE dynamic routes
- **Auth Storage**: Tokens via `secureStorage.js`
- **Campus Isolation**: "All Locations" reserved for System Admin, Admin, ED, Adviser
- **NFC Tags**: Stored on member/user records. Write requires director+. Audit in nfc_write_log.
- **Photos**: Object storage primary, local /app/backend/uploads/photos/ fallback
- **Country Outlines**: world-map-country-shapes package, mapped via COUNTRY_TO_CODE in countryOutlines.js

## Test Reports
- Iteration 49-52: All 100%
- Iteration 53: 100% (10/11 backend + all frontend)

## Pending / In Progress
- Profile photo UI on member/child edit forms (backend ready, frontend wiring needed)
- Child edit: typed parent search  
- Children at restricted locations: auto-issue badges for tracking
- Staff auto-marked as guests for their campus on creation
- Wallet integration improvement (currently downloads PNG)
- Future: Upgrade to native Wave H5 SDK
