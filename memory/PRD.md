# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global Connect Uganda: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC, and **full-featured audio/video calling**.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC — System Admin > ED/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key), Google OAuth (Emergent-managed)
- **Calling**: WebRTC + WebSocket signaling with optional PBX integration

## Completed Features

### Core
- [x] Auth, Dashboard, People/Members, Events, Calendar, Tasks (Kanban), Check-ins
- [x] Outreach, Communications, Resources, Access Control, Financial, Sales/Products
- [x] Attendance, Location management, Mobile-responsive, Campus reports + PDF

### Advanced
- [x] Admin toggle, Adviser role, Multi-location staff, Auto-titles
- [x] Global App Settings, Audit Trail bulk delete, Campus switcher

### Phase 3 — Sales & Outreach (2026-03-27)
- [x] Location-scoped products, store settings per location, sales import/export
- [x] Outreach sessions → calendar events, recurring programme events

### Phase 4 — Financial, Calendar, Access, Recurrence (2026-03-27)
- [x] Financial import/export (JSON), iCal import/export for all users
- [x] Guest pass QR, validation, extension, time bounds, allows_residents
- [x] Event recurrence: daily, weekly, biweekly, monthly, yearly, nth_week, nth_month + end date

### Phase 5 — Polish & UX (2026-03-27)
- [x] 5812 Global logo on all badges, passes, QR codes
- [x] Existing badge/staff badge reuse for events and guest passes
- [x] People UI location filter (dropdown that queries backend by location_id)
- [x] Outreach recurrence matching Events (daily, weekly, monthly, yearly, nth patterns)
- [x] All events deletable
- [x] Imported iCal events user-scoped (only visible to importer unless shared)
- [x] Event sharing endpoint (PUT /events/{id}/share)
- [x] Imported calendar events lighter gray styling, no solid background

### Phase 6 — 14 Major Enhancements (2026-03-27)
- [x] **Financial API Connections** - Admin can add/remove payment gateway integrations
- [x] **Auto-updating Reports** - Reports with real-time data refresh capability
- [x] **Webcal Subscription** - iCal feed export for calendar subscriptions
- [x] **Push Notifications** - Web push notification infrastructure (VAPID keys)
- [x] **Offline Mode/PWA** - Service worker foundation for offline capabilities
- [x] **Multi-language Support** - Added Luganda (lg) and Thai (th) translations
- [x] **Advanced Analytics Dashboard** - Deep insights with charts
- [x] **Custom Report Builder** - Create/save custom reports with filters, schedules, auto-update
- [x] **Data Export to Excel** - XLSX export for reports
- [x] **Google OAuth Login** - Emergent-managed Google authentication
- [x] **Two-Factor Authentication (2FA)** - TOTP-based authenticator app support
- [x] **GDPR/Privacy Settings** - Data export, retention policies, consent management
- [x] **Member Portal** - Self-service portal for members
- [x] **Volunteer Scheduling** - Shift management, role-based scheduling
- [x] **Email Templates** - Reusable templates with variable substitution

### Phase 7 — Full-Featured Calling System (2026-03-27)
- [x] **WebRTC Audio/Video Calling** - Standalone calling without PBX
- [x] **PBX Integration** - Support for FreePBX, 3CX, Asterisk, Generic SIP
- [x] **Extension Management** - Admin assigns extensions to staff (3-6 digits)
- [x] **Dialer UI** - Zoom-like dialer with Contacts and Keypad tabs
- [x] **Call History** - Full call logs with search/filter, callback functionality
- [x] **Voicemail** - Voicemail inbox with read/unread, play, delete
- [x] **Call Recordings** - Recording playback and download
- [x] **Call Controls** - Mute, hold, transfer, conference, screen share
- [x] **Missed Call Notifications** - Missed call count and alerts
- [x] **User Status** - Available, Busy, DND, Offline, On Call
- [x] **ICE Servers** - STUN/TURN configuration for NAT traversal
- [x] **WebSocket Signaling** - Real-time call setup, ICE exchange, notifications

## Navigation Structure
- **People**: People
- **Ministry**: Events, Calendar, Tasks, Check-Ins, Outreach, Communications, Resources, Access Control
- **Finance**: Financial, Sales & Products
- **Analytics**: Attendance, Sales Analytics, Location Stats, Advanced Analytics, Reports & PDF, Report Builder, Campus Reports
- **Operations**: Volunteer Scheduling, Email Templates
- **Calling**: Call History, Extensions (admin), PBX Settings (admin)
- **Admin**: Staff Management, Campuses, Financial APIs, App Settings, Audit Trail, Privacy & GDPR, Settings

## Calling System Architecture

### Backend Routers
- `/app/backend/routers/calling.py` - Full calling API
- `/app/backend/routers/websocket.py` - Call signaling added

### Frontend Pages
- `/call-history` - CallHistoryPage.jsx - Call logs, voicemail, recordings
- `/extensions` - ExtensionsPage.jsx - Admin extension management
- `/pbx-settings` - PbxSettingsPage.jsx - PBX configuration

### Components
- `CallContext.js` - WebRTC state management, media handling
- `CallInterface.jsx` - Full-screen call UI (Zoom-like)
- `IncomingCallModal.jsx` - Incoming call notification
- `Dialer.jsx` - Dialer modal with contacts/keypad

### Key Calling API Endpoints
- GET/POST/PUT/DELETE `/api/calling/extensions` - Extension CRUD
- GET/POST/PUT/DELETE `/api/calling/pbx-configs` - PBX configuration
- POST `/api/calling/calls/initiate` - Start a call
- POST `/api/calling/calls/{id}/action` - Call actions (answer, reject, hangup, hold, transfer, etc.)
- GET `/api/calling/history` - Call logs
- GET `/api/calling/voicemail` - Voicemails
- GET `/api/calling/recordings` - Call recordings
- PUT `/api/calling/status` - Update user calling status
- GET `/api/calling/contacts` - Get callable contacts with extensions
- GET `/api/calling/ice-servers` - Get STUN/TURN servers

## Test Reports
- Iterations 1-25: All passed
- Iteration 26: 100% (28/28 — sales/outreach)
- Iteration 27: 100% (20/20 — financial/calendar/access/recurrence)
- Iteration 28: 100% (19/19 — badges/people filter/outreach recurrence)
- Iteration 29: 100% (35/35 — 14 major enhancements)
- Iteration 30: 100% (23/23 — calling feature: extensions, PBX, history, voicemail, recordings)

## Upcoming / Backlog
- [ ] AdminPage.jsx component splitting (1000+ lines)
- [ ] server.py modular router refactoring (remaining endpoints)
- [ ] SMS notifications integration
