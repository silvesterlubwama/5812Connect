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
        │   ├── TasksPage, UnifiedPeoplePage, AdminPage, CalendarPage, AuditPage, etc.
        └── services/api.js
```

## Key DB Collections
- `boards`, `tasks` (includes `due_date`)
- `users`, `members` (linked via `user_id` or `email`)
- `events` (includes outreach-generated events)
- `documents`, `document_requests`
- `outreach_programs`, `outreach_sessions`
- `locations` (type: main, campus, sub-location)
- `families`, `children`, `guests`
- `deleted_items` (soft-delete recycle bin, 30-day retention)

## Credentials
- Admin: `admin@5812uganda.org` / `Admin@5812`
- System Admin: `silvester@lubwamas.org` / `Admin@5812`

## Completed Features (All Verified)
- Full Kanban board with WebSocket real-time updates
- Team Calendar view for workload management
- Kiosk mode for guest registration
- Comprehensive admin controls (user editing, manual creation)
- WebAuthn passkey authentication
- Network badge printing (NFC)
- Due-date reminder notifications
- People/Members management with bulk operations
- Family, Children, Guest management with FULL CRUD
- Events, Check-ins, Venues management
- Financial management (donations, expenses)
- Outreach programmes with recurring event generation
- AI Assistant (Gemini)
- CSV import/export
- Public booking system
- Document upload (works with both user_id and member_id)
- Enhanced event recurrence (Nth week/month patterns)
- Calendar shows outreach sessions
- "Compasses" renamed to "Campus" globally
- Duplicate prevention on all entity creation
- Soft-delete with 30-day recycle bin + restore
- Parents import as guests (not members)
- Auto-admin promotion for silvester@lubwamas.org

## Session 2026-03-25 Changes

### P0 Bug Fix: Document Upload "Member not found"
- Backend resolves user_id → member_id via users → members collection fallback
- Status: VERIFIED (iteration_18)

### P2: Rename "Compasses" → "Campus" + Nav tab → "Locations"
- Status: VERIFIED (iteration_18)

### P1: Enhanced Event Recurrence
- 5 recurrence patterns: Weekly, Bi-weekly, Monthly, Nth Weekday of Month, Nth Day of Month
- Status: VERIFIED (iteration_18)

### Calendar Shows Outreach Events
- Calendar fetches both events and outreach sessions
- Status: VERIFIED (iteration_18)

### Family & Child Editing
- Added family edit dialog (edit button + form)
- Child editing already existed, verified working
- Status: VERIFIED (iteration_19)

### Duplicate Prevention
- Members: 409 on duplicate email/phone/national_id
- Families: 409 on duplicate family_name
- Children: 409 on duplicate name+family_id
- Guests: 409 on duplicate name+email
- Status: VERIFIED (iteration_19)

### Soft-Delete & Recycle Bin
- All deletes (members, families, children, guests, users) move to `deleted_items` collection
- Recycle bin tab in Audit Trail page with restore + permanent delete
- 30-day retention window
- Status: VERIFIED (iteration_19)

### Parents Import as Guests
- Children/Parents CSV import now creates parents in `guests` collection with `is_parent: true`
- Status: VERIFIED (iteration_19)

### silvester@lubwamas.org Auto-Admin
- Auto-created/promoted to admin on server startup
- Status: VERIFIED (iteration_19)

## Pending / Not Yet Started

### P1: Unify People & User Administration UIs
- Staff marked in People UI should appear in User Admin
- All users from both UIs should be visible in People UI

## Future/Backlog
- Card due-date reminders via push notifications (enhancement)
- Team Calendar drag-and-drop rescheduling
- Board sharing / external guest access
- Recurring task cards
- Bulk card operations (multi-select, bulk archive/move)
