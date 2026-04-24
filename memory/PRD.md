# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with internal WebRTC calling, unified communications, and optional PBX integration.

## Latest Changes (Iteration 52 - Feb 2026)
- [x] NFC Tag Writing: Directors+ can write member IDs to blank NFC cards directly from badge dialogs
- [x] Backend POST /api/members/{id}/nfc-write — requires director+ role, auto-adds tag to profile, logs to nfc_write_log
- [x] UnifiedBadge "Write NFC" button visible only for director+ users on staff badge types
- [x] UserEditDialog NFC tab: "Write NFC Tag" section for director+ with Web NFC API integration
- [x] Role restriction: Staff can add tag serials manually, only directors+ can write to physical NFC cards

## Changes (Iteration 51)
- [x] Badge country watermark, footer redesign, NFC symbol for staff, NFC tag CRUD, kiosk white backgrounds

## Changes (Iteration 50)
- [x] CallContext.js refactored into hooks, backend type hints, nested ternary cleanup

## Changes (Iteration 49)
- [x] Kiosk QR Camera fix, backend function decomposition, frontend component splitting

## Architecture Notes
- **Route Ordering**: Static routes MUST be placed BEFORE dynamic routes
- **Auth Storage**: Tokens via `secureStorage.js`
- **Campus Isolation**: "All Locations" reserved for System Admin, Admin, ED, Adviser
- **NFC Tags**: Stored as array on member/user records. Unique serial per member. Write requires director+ role.
- **NFC Write Log**: All write events stored in nfc_write_log collection for audit

## Test Reports
- Iteration 49: 100% | Iteration 50: 100% | Iteration 51: 100% | Iteration 52: 100%

## Pending Tasks
- Future: Upgrade to native Wave H5 Embedded SDK
- Future: `server.py` modularization
