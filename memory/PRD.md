# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global serving USA (Ohio), Uganda, Kenya, Thailand, Haiti. Full-featured nonprofit management platform.

## All Completed (Phases 1-12 + Fixes)

### Core: Auth, Dashboard, People, Events, Calendar, Boards, Check-ins, Outreach, Comms, Resources, Access, Financial, Sales, Portal, Calling

### Key Fixes Applied (Iteration 36)
- [x] **Chat Fixed**: WebSocket URL path corrected from `/ws/` to `/api/ws/` (K8s ingress routing)
- [x] **Calling Fixed**: CallContext rewired to use `send`/`addListener` instead of non-existent `sendMessage`/`lastMessage`
- [x] **Calling Contacts Fixed**: Now returns all staff users (not just those with extensions)
- [x] **Reports Fixed**: `db.check_ins` → `db.checkins` collection name
- [x] **Director Filtering**: Directors now campus-scoped (only Admin+ED have global access)

### Phase 12 Features
- [x] Public Bookings with payment flow (Card/MTN/Airtel/Venmo/Cash)
- [x] Unified policies (US/EU/Uganda/Kenya/Thailand/Haiti/Mexico)
- [x] Country-based event filtering, QR check-in, Kiosk enhancements
- [x] New signups as Members with pending approval

## Test Reports
- Iterations 1-35: All passed
- Iteration 36: 100% (22/22 - Chat, WebSocket, Calling, Contacts fixes)

## MOCKED: Payment gateway processing (bookings track status, no real charges)

## Remaining
- [ ] Connect real payment gateways (Stripe/MTN/Airtel)
- [ ] Redis-backed presence for production
