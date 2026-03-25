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
        ├── components/ (Layout, PortalLayout, ui/)
        ├── context/
        ├── pages/
        │   ├── kanban/
        │   ├── Portal pages (PortalDashboard, PortalFamily, PortalTasks, etc.)
        │   ├── Admin pages (AdminPage, AuditPage, UnifiedPeoplePage, etc.)
        └── services/api.js
```

## Key DB Collections
- `boards`, `tasks` (Kanban + Team Calendar)
- `users`, `members` (linked via user_id or email)
- `events` (includes outreach events)
- `documents`, `document_requests`
- `outreach_programs`, `outreach_sessions`
- `locations` (type: main, campus, sub-location)
- `families` (parent_ids, guardians[], linked to children & guests)
- `children` (linked to families via family_id)
- `guests` (is_parent flag for parent-guests)
- `deleted_items` (soft-delete recycle bin, 30-day retention)

## Credentials
- Admin: `admin@5812uganda.org` / `Admin@5812`
- System Admin: `silvester@lubwamas.org` / `Admin@5812`

## Completed Features (All Verified)
### Core CRM
- Full Kanban board with WebSocket real-time updates
- Team Calendar view for workload management
- Kiosk mode for guest registration
- Admin controls (user CRUD, manual creation, import)
- WebAuthn passkey authentication
- Network badge printing (NFC)
- Due-date reminder notifications
- CSV import/export
- Public booking system
- AI Assistant (Gemini)

### People Management
- Members CRUD with duplicate prevention (email/phone/national_id)
- Family management with parents, children, AND guardians
- Family editing from admin People page
- Child editing from admin People page
- Guest CRUD with duplicate prevention
- Parents import as guests (via CSV)
- Soft-delete + 30-day recycle bin for all entities

### Family Self-Service (Portal)
- "My Family" page in staff/member portal
- Parents view their own family details
- Parents add/edit children
- Parents add/remove guardians (with relationship types)
- Parents update family info (name, phone, address)
- Guardian CRUD: add, update, remove from families
- Family detail endpoint returns parents + children + guardians

### Events & Calendar
- Events CRUD with enhanced recurrence (Nth week/month patterns)
- Calendar shows outreach sessions alongside regular events
- Outreach programme event generation

### Data Integrity
- Duplicate prevention on all entity creation endpoints
- Soft-delete with 30-day recycle bin + admin restore
- Audit trail with paginated log viewing
- Auto-promote silvester@lubwamas.org to admin

### UI Fixes
- "Compasses" renamed to "Campus" globally
- Nav tab renamed to "Locations"
- Document upload works with both user_id and member_id

## Session 2026-03-25 Changes (Verified via iterations 18-20)
1. P0: Document upload "Member not found" fix
2. P2: Compasses → Campus rename + Locations nav tab
3. P1: Enhanced event recurrence (5 patterns)
4. Calendar shows outreach events
5. Family & child editing
6. Duplicate prevention on all entities
7. Soft-delete + recycle bin + restore
8. Parents import as guests
9. silvester@lubwamas.org auto-admin
10. **Family self-service portal (parents manage families with children + guardians)**

## Pending / Not Yet Started
### P1: Unify People & User Administration UIs
- Staff marked in People UI should appear in User Admin
- All users from both UIs should be visible in People UI

## Future/Backlog
- Card due-date push notification enhancements
- Team Calendar drag-and-drop rescheduling
- Board sharing / external guest access
- Recurring task cards
- Bulk card operations (multi-select, bulk archive/move)
