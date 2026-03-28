# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC, full PBX-capable calling, unified communications with threading/conferencing, and self-service portal.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC with phone/email login
- **Global Access**: Admin + System Admin + Executive Director
- **Campus Switcher**: Admin + ED + Adviser
- **Calling**: WebRTC + WebSocket + PBX (auto-attendant, call queues, forwarding)
- **Presence**: In-memory with WebSocket broadcasts

## All Completed Features

### Core (Phase 1-7)
- [x] Auth, Dashboard, People, Events, Calendar, Boards, Check-ins, Outreach, Comms, Resources, Access Control, Financial, Sales, Attendance, 14 Major Enhancements, Full Calling System, Portal

### Phase 8-9 - Bug Fixes, Unified Comms, Refactoring
- [x] Location filtering, Data isolation, Calendar editing, Staff tasks, Presence, Reactions, Threading, Conferencing, AdminPage split (319 lines), server.py modularization (879 lines)

### Phase 10 - Application Overhaul
- [x] Data isolation overhaul (Admin+ED global only), Collapsible nav, Campus switcher, Role-based visibility, Renamed app/location, Admin-only API/PBX, Default password, Events ordering, Year navigation

### Phase 11 - Phase D+E Features (2026-03-27)
- [x] **Adviser Campus Switcher**: Advisers get location switcher via `has_campus_switcher` and `CAMPUS_SWITCHER_ROLES`
- [x] **Chat Auto-Detect Type**: New conversation defaults to direct (1 user), auto-switches to group when 2+ participants, auto-names direct messages
- [x] **GDPR Accessible to All**: 'My Privacy' nav link visible to all roles, not just admins
- [x] **Venue Offsite + Non-Bookable**: `is_offsite`, `is_bookable`, `country`, `address` fields on venue model
- [x] **Extension in Staff Profile**: Extension and call forward fields in UserEditDialog Account tab
- [x] **QR Code Check-In**: `POST /api/checkins/qr-scan` looks up members by ID, national_id, email, or PIN
- [x] **Public Calendar by Country**: Auto-detects user country from timezone for location-relevant events
- [x] **Outreach Auto-Events**: Creating/updating recurring programmes auto-generates calendar events. Deleting programme auto-deletes associated events
- [x] **Auto-Attendant**: `GET/PUT /api/calling/auto-attendant` with greeting, menu options, business hours, after-hours config
- [x] **Call Queues**: CRUD `/api/calling/queues` with ring_all, round_robin, least_recent, random strategies
- [x] **Call Forwarding**: `GET/PUT /api/calling/forwarding/{user_id}` with always/busy/no-answer/offline rules
- [x] **Outgoing Call Rules**: CRUD `/api/calling/outgoing-rules` with pattern matching, allow/block/prefix actions
- [x] **Portal Enhancement**: Unified portal with "Events & RSVP", renamed to "58:12 Connect Portal"

## Navigation Structure
- Dashboard + My Portal + My Privacy
- Ministry: Outreach, Events, Check-ins
- Operations: Boards, Resources, Calendar, People, Scheduling, Access Control
- Comms: Chat, History
- Finance: Financial, Sales & Products
- Analytics: Attendance, Sales, Location, Advanced, Reports, Report Builder
- Admin: Staff Management, Campuses, Financial APIs, PBX & Extensions, Email Templates, Settings, Audit, GDPR

## Test Reports
- Iterations 1-33: All passed
- Iteration 34: 100% (26/26 - Phase D+E features)

## Remaining Backlog
- [ ] Full WebRTC audio/video calling end-to-end testing and fixes
- [ ] Redis-backed presence for production horizontal scaling
- [ ] Further server.py extraction (remaining seed, notifications, OAuth sections)
