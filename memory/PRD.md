# 58:12 Connect (58:12 Global) - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC, full-featured calling, unified communications with threading and conferencing.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC - Admin/System Admin > Executive Director > Adviser > Director > Manager > Coordinator > Staff > Volunteer > Member > Parent
- **Global Access**: Only Admin + System Admin + Executive Director have cross-campus visibility
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key), Google OAuth (Emergent-managed)
- **Calling**: WebRTC + WebSocket + optional PBX
- **Presence**: In-memory with WebSocket broadcasts (Green/Yellow/Blue/Red)

## Completed Features (All Phases)

### Core (Phase 1-6)
- [x] Auth, Dashboard, People, Events, Calendar, Boards (Kanban), Check-ins
- [x] Outreach, Communications, Resources, Access Control, Financial, Sales
- [x] 14 Major Enhancements, Calling System, Portal

### Phase 8 - Bug Fixes & Unified Comms
- [x] Location filtering (async get_campus_filter with sub-location expansion)
- [x] Data isolation, Calendar editing, Staff task creation, Presence, Reactions

### Phase 9 - Refactoring & Advanced Comms
- [x] AdminPage split (1037->319 lines), server.py modularized (1100->879 lines)
- [x] Group conferencing, Thread support, Conference scheduling/email invites

### Phase 10 - Application Overhaul (2026-03-27)
- [x] **Data Isolation Overhaul**: Only Admin + ED have global access. Directors/Advisers now campus-scoped
- [x] **Campus Switcher**: Persistent dropdown for Admin/ED users, stored on user record, filters ALL data via get_campus_filter
- [x] **Navigation Overhaul**: Collapsible sections with auto-expand. New structure: Ministry (Outreach, Events, Check-ins), Operations (Boards, Resources, Calendar, People, Scheduling, Access), Comms (Chat, History), Finance, Analytics, Admin
- [x] **Role-Based Nav Visibility**: Users only see sections/pages they can access
- [x] **Renamed**: Tasks -> Boards, Main location -> "58:12 Global (Central)", App name -> "58:12 Connect"
- [x] **Admin-Only Lock**: Financial APIs + PBX Settings restricted to admin role
- [x] **Default Password**: New users get "User@58:12"
- [x] **Events Ordering**: Upcoming first, then by date
- [x] **Calendar Year Navigation**: Prev/next year buttons
- [x] **Close Dialog on Save**: Admin edit dialog auto-closes on successful save

## Navigation Structure
- **Dashboard** + My Portal
- **Ministry**: Outreach, Events, Check-ins
- **Operations**: Boards, Resources, Calendar, People, Scheduling, Access Control
- **Comms**: Chat, History
- **Finance**: Financial, Sales & Products (Manager+)
- **Analytics**: Attendance, Sales, Location, Advanced, Reports, Report Builder (Manager+)
- **Admin**: Staff Management, Campuses, Financial APIs, PBX & Extensions, Email Templates, Settings, Audit, GDPR (Admin only)

## Test Reports
- Iterations 1-32: All passed
- Iteration 33: 100% (15/15 - Phase 10 overhaul)

## Upcoming / Backlog (Phase D-E from user request)
- [ ] Chat defaults to 1 user, group only if 2+ selected
- [ ] Merge board calendar with main calendar
- [ ] Public calendar by country on bookings page
- [ ] Outreach auto-creates/deletes events with enhanced recurrence
- [ ] Unified parent + member portal (phone login, profile edit, staff chat, RSVP, volunteer, docs)
- [ ] GDPR settings accessible to all users
- [ ] Boards assigned to campus/sub-location
- [ ] Venue setup moved to Campus page with offsite/non-bookable options
- [ ] Auto-attendants, call queues, call forwarding (advanced PBX)
- [ ] WebRTC calling fixes
- [ ] QR code scanning for faster check-in
- [ ] Extension management in staff profile (admin-only)
- [ ] Multi-role/multi-location user switching
- [ ] Redis-backed presence for production scaling
