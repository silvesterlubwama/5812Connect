# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global Connect Uganda: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC — System Admin > ED/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key)

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

## Upcoming / Backlog
- [ ] AdminPage.jsx component splitting (1000+ lines)
- [ ] server.py modular router refactoring

## Key API Endpoints
- POST /api/auth/login
- GET /api/members?location_id=xxx — Filter members by location
- GET /api/events?type=imported — User-scoped imported events
- PUT /api/events/{id}/share — Share imported events
- DELETE /api/events/{id} — Delete any event
- POST /api/events/generate-recurring — All recurrence patterns
- GET /api/access/guest-passes/{id}/validate — QR pass validation
- PUT /api/access/guest-passes/{id}/extend — Extend pass

## Test Reports
- Iterations 1-25: All passed
- Iteration 26: 100% (28/28 — sales/outreach)
- Iteration 27: 100% (20/20 — financial/calendar/access/recurrence)
- Iteration 28: 100% (19/19 — badges/people filter/outreach recurrence/imported events scoping/styling)
