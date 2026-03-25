# 58:12 Global Connect Uganda CRM - Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Tech Stack
- **Frontend**: React, Tailwind CSS, Shadcn/UI, WebAuthn, NFC, WebSockets, PWA
- **Backend**: FastAPI, Motor (Async MongoDB), modular APIRouters
- **Database**: MongoDB
- **Integrations**: Emergent LLM Key (Gemini AI), Resend (Emails), Object Storage

## Key DB Collections
- `boards`, `tasks` (Kanban + Team Calendar)
- `users`, `members` (linked via user_id or email)
- `events` (includes outreach events)
- `documents`, `document_requests`
- `outreach_programs`, `outreach_sessions`
- `locations` (type: main, campus, sub-location)
- `families` (parent_ids, guardians[], linked to children & guests)
- `children` (family_id, parent_ids[] — linkage for check-in)
- `guests` (is_parent, family_id flags)
- `deleted_items` (soft-delete recycle bin, 30-day retention)
- `checkins` (type: member/staff/visitor/child, method: parent_id/qr/nfc/pin)

## Credentials
- Admin: `admin@5812uganda.org` / `Admin@5812`
- System Admin: `silvester@lubwamas.org` / `Admin@5812`

## All Completed Features

### Core CRM
- Full Kanban board with WebSocket real-time updates
- Team Calendar view for workload management
- Kiosk mode for guest registration
- Admin controls (user CRUD, manual creation, import)
- WebAuthn passkey authentication, NFC badge printing
- Due-date reminders, CSV import/export
- Public booking system, AI Assistant (Gemini)

### People Management
- Members, Families, Children, Guests — full CRUD with duplicate prevention
- Family editing + guardian management (add/edit/remove)
- Soft-delete with 30-day recycle bin + admin restore
- Parents import as guests via CSV

### Family Self-Service (Portal)
- "My Family" portal page — parents view/edit family, add children + guardians
- Guardian relationship types (Guardian, Grandparent, Aunt/Uncle, Sibling, Nanny)

### Parent-Child Check-In System (NEW - Session 2026-03-25)
- **Child → Parent association**: `parent_ids` field on children links them to specific parent guests
- **Parent Check-In flow**: Staff enter parent phone/email/ID/name or scan QR → see linked children → check in
- **QR code scanning**: BarcodeDetector API integration for camera-based QR lookup
- **Flexible lookup**: Searches by phone, email, guest ID, or name in guests + members
- **Check-in records**: type=child, method=parent_id, parent_name, parent_id fields
- **Stats**: Check-in stats include children count
- **Admin UI**: Child edit dialog has "Linked Parents" checkboxes for parent association

### Events & Calendar
- Enhanced recurrence (5 patterns: weekly, biweekly, monthly, nth_week, nth_month)
- Calendar shows outreach sessions alongside regular events

### Data Integrity
- Duplicate prevention on all entity creation
- Soft-delete with 30-day recycle bin + admin restore
- Audit trail with paginated log + recycle bin UI
- "Compasses" renamed to "Campus" globally

## Verified via Testing Iterations 17-21 (All 100% pass)

## Pending
### P1: Unify People & User Admin UIs
- Staff in People should appear in User Admin; all users visible in People UI

## Future/Backlog
- Card due-date push notifications (enhancement)
- Team Calendar drag-and-drop rescheduling
- Board sharing / external guest access
- Recurring task cards, Bulk card operations
