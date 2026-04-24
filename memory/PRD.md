# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with internal WebRTC calling, unified communications, and optional PBX integration.

## Calling Architecture (Simplified)
- **Internal Calls**: Pure WebRTC peer-to-peer (no PBX needed)
- **External Calls**: Optional — connect a local PBX for SIP trunking
- **SIP.js**: Available but dormant — only activates when PBX is configured

## Latest Changes (Iteration 51 - Feb 2026)
- [x] Badge country watermark: faint SVG outline of the country map (Uganda, Kenya, Haiti, Thailand, USA) based on user's campus location
- [x] Badge footer: "www.5812-Global.org" centered, "58:12 GLOBAL - {year}" (replaced "58:12 GLOBAL CONNECT")
- [x] NFC symbol on staff/director/volunteer badges only
- [x] NFC tag storage: backend CRUD endpoints (GET/POST/DELETE /api/members/{id}/nfc-tags) with serial uniqueness check
- [x] NFC Tags tab added to UserEditDialog with add/remove/scan functionality
- [x] PrintableBadges (StaffBadge, ParentBadge, ChildTag) use white backgrounds for kiosk ink saving

## Changes (Iteration 50)
- [x] CallContext.js refactored into 3 files: CallContext + useMediaControls + usePeerConnections hooks
- [x] Return type hints added to 67 backend functions (auth, members, events, tasks, admin, locations)
- [x] Nested ternaries cleaned up using lookup objects

## Changes (Iteration 49)
- [x] Kiosk QR Camera Scan fixed — html5-qrcode library with Dialog-based scanner
- [x] Backend: admin_update_user and import_trello_board decomposed into helpers
- [x] Frontend: 6 dialog components extracted from CommsPage, CheckInsPage, AccessPage

## Architecture Notes
- **Route Ordering**: Static routes MUST be placed BEFORE dynamic routes (`/{id}`)
- **Auth Storage**: Tokens via `secureStorage.js`, NOT direct `localStorage`
- **Production Build**: Use relative paths (NOT `@/` alias) for component imports
- **Campus Isolation**: "All Locations" reserved for System Admin, Admin, Executive Director, Adviser
- **CallContext**: Split into CallContext.js + useMediaControls.js + usePeerConnections.js
- **NFC Tags**: Stored as array on member/user records. Unique serial per member.

## Test Reports
- Iteration 49: 100% (12/12 backend + all frontend)
- Iteration 50: 100% (16/16 backend + all frontend)
- Iteration 51: 100% (8/8 backend + all frontend)

## Pending Tasks
- Future: Upgrade to native Wave H5 Embedded SDK when fully released
- Future: `server.py` modularization
