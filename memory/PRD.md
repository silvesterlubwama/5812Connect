# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
A multi-tenant CRM for 58:12 Global Connect Uganda, managing campuses, members, events, check-ins, finances, sales, outreach, and resources with deep RBAC rules.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Database**: MongoDB
- **Auth**: JWT with role-based access
- **Integrations**: Resend (email), Gemini AI (assistant via Emergent LLM Key)

## Roles & RBAC
System Admin > Executive Director/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member. Admin is a toggle, not a role.

## Completed Features

### Phase 1 — Core
- [x] Auth, Dashboard, People/Members, Events, Calendar, Tasks (Kanban), Check-ins
- [x] Outreach, Communications, Resources, Access Control, Financial, Sales/Products
- [x] Attendance, Location management with sublocations

### Phase 2 — Advanced
- [x] Mobile-responsive views, Campus reports + PDF, Campus switcher
- [x] Admin toggle, Adviser role, Multi-location staff, Auto-titles
- [x] Global App Settings, Audit Trail bulk delete

### Phase 3 — Sales & Outreach (2026-03-27)
- [x] Location-scoped products & store settings per location
- [x] Sales Import/Export (JSON), Customer directory
- [x] Outreach sessions auto-create calendar events
- [x] Recurring outreach programmes auto-generate events

### Phase 4 — Financial, Calendar, Access, Recurrence (2026-03-27)
- [x] Financial live import/export API (donations + expenses JSON with date/location filtering)
- [x] Calendar iCal import (file upload + paste) for all users
- [x] Calendar iCal export for all users
- [x] Recurring event generator (backend): daily, weekly, biweekly, monthly, yearly, nth_week, nth_month
- [x] End date support for recurring events
- [x] Guest pass QR codes with time bounds (valid_from_time, valid_until_time)
- [x] Guest pass validation endpoint (scan QR → check validity)
- [x] Guest pass extension (extend by N days)
- [x] "allows_residents" toggle on restricted locations
- [x] Event recurrence UI: daily, weekly, biweekly, monthly, nth_weekday, yearly + end date

## Upcoming / Backlog
- [ ] AdminPage.jsx component splitting (refactoring — 1000+ lines)
- [ ] server.py modular router refactoring

## Key API Endpoints
- POST /api/auth/login
- GET/PUT /api/global-settings
- GET/PUT /api/store-settings/{location_id}
- GET /api/sales/export, POST /api/sales/import
- GET /api/financial/export, POST /api/financial/import
- POST /api/events/generate-recurring
- POST /api/events/import/ical, GET /api/events/export/ical
- GET /api/access/guest-passes/{id}/validate
- PUT /api/access/guest-passes/{id}/extend
- PUT /api/admin/users/{id}
- DELETE /api/admin/deleted-items (bulk)

## Test Reports
- Iterations 1-25: All passed (previous sessions)
- Iteration 26: 100% (28/28 backend — sales/outreach features)
- Iteration 27: 100% (20/20 backend — financial/calendar/access/recurrence features)
