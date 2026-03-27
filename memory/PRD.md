# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global Connect Uganda: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC, full-featured audio/video calling, and unified communications with threading and conferencing.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC -- System Admin > ED/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key), Google OAuth (Emergent-managed)
- **Calling**: WebRTC + WebSocket signaling with optional PBX integration
- **Presence**: In-memory presence system (Green/Yellow/Blue/Red status dots) with WebSocket broadcasts

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

### Phase 7 -- Calling System (2026-03-27)
- [x] WebRTC Audio/Video, PBX Integration, Extensions, Dialer, Call History, Voicemail

### Phase 8 -- Bug Fixes & Unified Comms (2026-03-27)
- [x] Location filtering fix (async get_campus_filter with sub-location expansion)
- [x] Data isolation fix (boards campus-filtered, bidirectional location expansion)
- [x] Calendar event editing (click to edit with pre-filled modal)
- [x] Staff task creation (canEdit includes staff role)
- [x] Enhanced Communications (presence indicators, reactions, calling buttons)
- [x] AdminPage refactoring (BadgePrintView extracted)
- [x] server.py modularization (locations router extracted)

### Phase 9 -- Full Refactoring & Advanced Comms (2026-03-27)
- [x] **AdminPage Full Refactoring**: UserCreateDialog, UserImportDialog, UserEditDialog, BadgePrintView extracted to `/components/admin/`. AdminPage reduced from 1037 to 319 lines
- [x] **server.py Full Modularization**: Settings router extracted handling currencies, global/app settings, GDPR, financial APIs, inventory alerts. server.py reduced from 1100 to 879 lines
- [x] **Group Video Conferencing**: Schedule Conference dialog with title, datetime, duration, participant invites, external email invites, password, video toggle, calendar event creation, email invite sending
- [x] **Conference Email Invites**: Backend sends email invites to both internal users and external non-users via notifications system
- [x] **Slack-Style Thread Support**: Messages show thread count indicator, clicking opens thread panel on right side with original message + threaded replies, can send replies in thread context
- [x] **Conference Calendar Scheduling**: Conferences auto-create calendar events when scheduled, integrated datetime picker and duration
- [x] **Real-Time Presence Improvements**: WebSocket broadcasts presence changes to all connected clients, 30s heartbeat, status selector (Available/Away/DND/Offline)

## Component Architecture

### Backend Routers (extracted from server.py)
- `routers/locations.py` -- Location CRUD, staff assignment, director, exchange rates, venues
- `routers/settings.py` -- Currencies, global/app settings, GDPR, financial APIs, inventory alerts
- `routers/chat.py` -- Conversations, messages (with thread support), AI assistant, offline sync
- `routers/conferences.py` -- Conference CRUD, scheduling, joining, recording, email invites
- `routers/presence.py` -- User presence tracking, heartbeat, status management

### Frontend Admin Components
- `components/admin/BadgePrintView.jsx` -- Badge preview + print (browser/bluetooth/ZPL)
- `components/admin/UserCreateDialog.jsx` -- New user creation dialog
- `components/admin/UserImportDialog.jsx` -- CSV/JSON user import dialog
- `components/admin/UserEditDialog.jsx` -- Full profile edit (4 tabs: Profile, Account, Flags, Documents) + scanner + doc request sub-dialogs

## Test Reports
- Iterations 1-30: All passed
- Iteration 31: 100% (25/25 -- Phase 8: location filtering, data isolation, calendar editing, staff tasks, comms)
- Iteration 32: 100% (30/30 -- Phase 9: admin refactoring, server modularization, conferencing, threads, presence)

## Upcoming / Backlog
- [ ] Redis-backed presence for production horizontal scaling
- [ ] Further server.py extraction (seed endpoints, notifications, OAuth/2FA sections)
- [ ] Conference recording playback and download
- [ ] Push notification integration for conference reminders
