# 58:12 Global Connect Uganda CRM - Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Tech Stack
- Frontend: React, Tailwind CSS, Shadcn/UI, WebAuthn, NFC, WebSockets, PWA, qrcode.react
- Backend: FastAPI, Motor (Async MongoDB), modular APIRouters
- Database: MongoDB
- Integrations: Emergent LLM Key (Gemini AI), Resend (Emails), Object Storage

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- System Admin: silvester@lubwamas.org / Admin@5812

## All Completed Features

### Core CRM
- Full Kanban board with WebSocket real-time updates
- Kiosk mode, WebAuthn passkey auth, NFC badge printing
- Due-date reminders, CSV import/export, Public booking system
- AI Assistant (Gemini)

### Kanban Backlog (COMPLETE)
- Recurring tasks: is_recurring, recurrence_pattern, recurrence_interval on task model + UI
- Bulk card operations: Multi-select, bulk archive, bulk move, bulk delete
- Board sharing: is_shared toggle generates share_token, /shared/{token} read-only public view
- Team Calendar drag-and-drop: Drag tasks between dates to reschedule

### People Management
- Members, Families, Children, Guests — full CRUD with duplicate prevention
- Family editing + guardian management (CRUD with relationship types)
- Soft-delete + 30-day recycle bin + admin restore
- Parents import as guests (via CSV)

### Family Self-Service (Portal)
- "My Family" portal page
- Parents add/edit children, add/remove guardians, update family info

### Parent-Child Check-In
- parent_ids field on children for direct linkage
- Parent Check-In flow: phone/email/ID/QR → see children → check in
- QR scanning via BarcodeDetector API
- Auto-print child tags on check-in

### Badge & Tag Printing System
- StaffBadge: company logo, initials, QR code, name, role, department, ID
- ParentBadge: company logo, QR code (for check-in), name, phone, children list
- ChildTag: company logo, QR, first name, class/grade, event name, parent last 4 digits
- ZPL output for Zebra thermal printers + Bluetooth pairing

### P1: Staff Administration
- Admin UI renamed to "Staff Administration" / "Staff Management"
- Only staff managed in User Admin UI

### Events & Calendar
- Enhanced recurrence (5 patterns: weekly, biweekly, monthly, nth_week, nth_month)
- Calendar shows outreach sessions alongside events

### Data Integrity
- Duplicate prevention, soft-delete + recycle bin, audit trail
- Auto-promote silvester@lubwamas.org to admin
- "Compasses" → "Campus" rename, document upload user_id resolution

## Testing: Iterations 18-22 all 100% pass rate

## No Pending Tasks - Full Backlog Complete
