# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global Connect Uganda: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC, and full-featured audio/video calling + unified communications.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC — System Admin > ED/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key), Google OAuth (Emergent-managed)
- **Calling**: WebRTC + WebSocket signaling with optional PBX integration
- **Presence**: In-memory presence system (Green/Yellow/Blue/Red status dots)

## Completed Features

### Core
- [x] Auth, Dashboard, People/Members, Events, Calendar, Tasks (Kanban), Check-ins
- [x] Outreach, Communications, Resources, Access Control, Financial, Sales/Products
- [x] Attendance, Location management, Mobile-responsive, Campus reports + PDF

### Advanced
- [x] Admin toggle, Adviser role, Multi-location staff, Auto-titles
- [x] Global App Settings, Audit Trail bulk delete, Campus switcher

### Phase 3-6 (2026-03-27)
- [x] Sales & Outreach, Financial import/export, iCal, Guest passes, Recurrence
- [x] 14 Major Enhancements (APIs, Analytics, Reports, 2FA, GDPR, Portal, etc.)

### Phase 7 — Calling System (2026-03-27)
- [x] WebRTC Audio/Video, PBX Integration, Extensions, Dialer, Call History, Voicemail

### Phase 8 — Unified Comms, Bug Fixes, Refactoring (2026-03-27)
- [x] **Location Filtering Fix (P0)**: `get_campus_filter` made async with sub-location expansion — users assigned to a campus now automatically see data from all sub-locations
- [x] **Data Isolation Fix (P0)**: Boards endpoint now campus-filtered, admin user update expands locations both upward (sub→parent) and downward (parent→sub)
- [x] **Calendar Event Editing (P1)**: Click any event in CalendarPage to open edit modal with pre-filled form (title, date, time, end_time, type, location, description, capacity, is_public) + save/delete
- [x] **Staff Task Creation (P1)**: Staff role users can now create tasks (canEdit includes 'staff' in TasksPage)
- [x] **Enhanced Communications (P1)**: Presence indicators (Green/Yellow/Blue/Red dots), status selector (Available/Away/DND/Offline), message reactions (emoji picker with 12 quick emojis), call buttons for staff conversations, typing indicators, read receipts
- [x] **AdminPage Refactoring (P1)**: BadgePrintView extracted to `/components/admin/BadgePrintView.jsx` (reduced AdminPage from 1037→894 lines)
- [x] **server.py Modularization (P2)**: Locations router extracted to `/routers/locations.py` (reduced server.py from 1100→1009 lines)

## Navigation Structure
- **People**: People
- **Ministry**: Events, Calendar, Tasks, Check-Ins, Outreach, Communications, Resources, Access Control
- **Finance**: Financial, Sales & Products
- **Analytics**: Attendance, Sales Analytics, Location Stats, Advanced Analytics, Reports & PDF, Report Builder, Campus Reports
- **Operations**: Volunteer Scheduling, Email Templates
- **Calling**: Call History, Extensions (admin), PBX Settings (admin)
- **Admin**: Staff Management, Campuses, Financial APIs, App Settings, Audit Trail, Privacy & GDPR, Settings

## Key Architecture Changes (Phase 8)

### Backend
- `deps.py`: `get_campus_filter` is now async and includes sub-location expansion
- All 20+ call sites across routers updated to `await get_campus_filter()`
- `admin.py`: admin_update_user expands location_ids bidirectionally
- `boards.py`: list_boards uses expanded campus filter
- `routers/locations.py`: NEW — extracted from server.py

### Frontend
- `CalendarPage.jsx`: Event edit/delete modal added
- `TasksPage.jsx`: Staff permission for canEdit
- `CommsPage.jsx`: Presence indicators, reactions, status selector, call buttons
- `components/admin/BadgePrintView.jsx`: Extracted from AdminPage

## Test Reports
- Iterations 1-30: All passed
- Iteration 31: 100% (25/25 backend, all frontend UI tests passed — Phase 8 features)

## Upcoming / Backlog
- [ ] Further AdminPage component splitting (remaining dialogs ~600 lines each)
- [ ] Further server.py modularization (notifications, settings, seed endpoints)
- [ ] Group chat/video conferencing modals in CommsPage
- [ ] Non-user conference invites with email notifications
- [ ] Calendar scheduling for conferences
