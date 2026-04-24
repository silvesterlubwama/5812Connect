# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with internal WebRTC calling, unified communications, and optional PBX integration.

## Calling Architecture (Simplified)
- **Internal Calls**: Pure WebRTC peer-to-peer (no PBX needed) — unlimited audio, video, screen sharing, group calls
- **External Calls**: Optional — connect a local PBX (FreePBX/Asterisk) for SIP trunking to real phone numbers
- **SIP.js**: Available but dormant — only activates when PBX is configured with WebSocket URL

## Latest Changes (Iteration 50 - Feb 2026)
- [x] CallContext.js refactored into 3 files: `CallContext.js` + `hooks/useMediaControls.js` + `hooks/usePeerConnections.js`
- [x] Return type hints added to 67 backend functions across auth, members, events, tasks, admin, locations routers (12% coverage)
- [x] Nested ternaries cleaned up in AccessPage, KioskPage, EventsPage, CalendarPage using lookup objects

## Changes (Iteration 49)
- [x] Kiosk QR Camera Scan fixed — uses `html5-qrcode` library with Dialog-based scanner UI
- [x] Backend refactoring: `admin_update_user` decomposed into `_expand_user_locations` + `_sync_member_profile` helpers
- [x] Backend refactoring: `import_trello_board` decomposed into 4 helpers
- [x] Frontend component splitting: 6 dialog components extracted from CommsPage, CheckInsPage, AccessPage

## Previous Changes (Iteration 43-48)
- [x] CallContext rewritten — pure WebRTC focus, clean code, SIP lazy-loaded
- [x] Chat + Calling merged — phone/video buttons in chat header initiate calls
- [x] Campus data isolation — sub-locations don't bleed upward
- [x] Bulk selection, CSV export, multi-edit across all data pages
- [x] Wave Add-in built & embedded; old PBX removed
- [x] Financial balance sheet, asset tracking, marketplace
- [x] XSS fixed (DOMPurify), localStorage migrated (secureStorage.js)
- [x] Kiosk Google Auth, 2FA, device locking, peripheral detection
- [x] Unified badges with QR codes for Staff/Children/Guests

## Architecture Notes
- **Route Ordering**: Static routes (`/bulk-update`, `/webcal-subscribe`) MUST be placed BEFORE dynamic routes (`/{id}`)
- **Auth Storage**: Tokens via `secureStorage.js`, NOT direct `localStorage`
- **Production Build**: Use relative paths (NOT `@/` alias) for component imports
- **Campus Isolation**: "All Locations" reserved for System Admin, Admin, Executive Director, Adviser only
- **CallContext**: Now split into `CallContext.js` (provider), `useMediaControls.js` (mute/video/screen), `usePeerConnections.js` (WebRTC peers)

## Test Reports
- Iteration 43: 100% (17/17 backend + all frontend)
- Iteration 48: All passed
- Iteration 49: 100% (12/12 backend + all frontend)
- Iteration 50: 100% (16/16 backend + all frontend)

## Pending Tasks
- Future: Upgrade to native Wave H5 Embedded SDK when fully released
- Future: `server.py` modularization (Backlog)
