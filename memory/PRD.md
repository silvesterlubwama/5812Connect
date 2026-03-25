# 58:12 Global Connect Uganda CRM - Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Tech Stack
- **Frontend**: React, Tailwind CSS, Shadcn/UI, WebAuthn, NFC, WebSockets, PWA
- **Backend**: FastAPI, Motor (Async MongoDB), modular APIRouters
- **Database**: MongoDB
- **Integrations**: Emergent LLM Key (Gemini AI Assistant), Resend (Emails), Object Storage

## Architecture
```
/app/
├── backend/
│   ├── deps.py, models.py, server.py, storage.py
│   ├── routers/ (all API route modules)
└── frontend/
    └── src/
        ├── components/
        ├── context/
        ├── pages/
        │   ├── kanban/ (KanbanCard, KanbanList, ArchivePanel, CardDetailDialog, TeamCalendar)
        │   ├── TasksPage, UnifiedPeoplePage, AdminPage, CalendarPage, etc.
        └── services/api.js
```

## Key DB Collections
- `boards`, `tasks` (includes `due_date`)
- `users`, `members` (linked via `user_id` or `email`)
- `events` (includes outreach-generated events)
- `documents`, `document_requests`
- `outreach_programs`, `outreach_sessions`
- `locations` (type: main, campus, sub-location)

## Credentials
- Admin: `admin@5812uganda.org` / `Admin@5812`

## Completed Features (All Verified)
- Full Kanban board with WebSocket real-time updates
- Team Calendar view for workload management
- Kiosk mode for guest registration
- Comprehensive admin controls (user editing, manual creation)
- WebAuthn passkey authentication
- Network badge printing (NFC)
- Due-date reminder notifications
- People/Members management with bulk operations
- Family, Children, Guest management
- Events, Check-ins, Venues management
- Financial management (donations, expenses)
- Outreach programmes with recurring event generation
- AI Assistant (Gemini)
- CSV import/export
- Public booking system

## Recently Completed (Session 2026-03-25)

### P0 Bug Fix: Document Upload "Member not found"
- **Root cause**: Admin page sent `user_id` to endpoint that only accepted `member_id`
- **Fix**: Backend now resolves user_id → member_id via `users` → `members` collection fallback
- **Files**: `/app/backend/routers/documents.py`, `/app/backend/routers/admin.py`
- **Status**: VERIFIED (iteration_18, 100% pass)

### P2: Rename "Compasses" → "Campus"
- Renamed all UI text, type labels, seed data, and i18n strings
- Navigation tab renamed from "Compasses & Locations" to "Locations"
- Backend handles both "campus" and "compass" types for backward compatibility
- **Files**: LocationsPage.jsx, AccessPage.jsx, en.json, server.py
- **Status**: VERIFIED (iteration_18, 100% pass)

### P1: Enhanced Event Recurrence
- Added 5 recurrence patterns: Weekly, Bi-weekly, Monthly, Nth Weekday of Month, Nth Day of Month
- Nth Week: pick which week (1st-4th/Last) + day of week + interval
- Nth Month: pick day of month number + interval
- All patterns support custom interval multiplier
- **Files**: CalendarPage.jsx
- **Status**: VERIFIED (iteration_18, 100% pass)

### Calendar Shows Outreach Events
- Calendar now fetches both events AND outreach sessions
- Outreach sessions displayed as event-like objects with type "outreach" (pink)
- Legend includes: Service, Conference, Meeting, Community, Outreach, Workshop, Training, Social
- **Files**: CalendarPage.jsx
- **Status**: VERIFIED (iteration_18, 100% pass)

## Pending / Not Yet Started

### P1: Unify People & User Administration UIs
- Staff marked in People UI should appear in User Admin
- All users from both UIs should be visible in People UI
- Requires backend + frontend refactoring of users/members data models

## Future/Backlog
- Card due-date reminders via push notifications (enhancement)
- Team Calendar drag-and-drop rescheduling
- Board sharing / external guest access
- Recurring task cards
- Bulk card operations (multi-select, bulk archive/move)
