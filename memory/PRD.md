# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
A multi-tenant CRM for 58:12 Global Connect Uganda, managing campuses, members, events, check-ins, finances, sales, outreach, and resources with deep RBAC rules.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Database**: MongoDB (collections: users, members, locations, events, families, check_ins, donations, expenses, products, sales, outreach_programs, outreach_sessions, tasks, boards, resources, guest_requests, app_settings, store_settings, financial_settings, audit_log, deleted_items)
- **Auth**: JWT with role-based access
- **Integrations**: Resend (email), Gemini AI (assistant via Emergent LLM Key)

## Roles & RBAC
- System Admin (full access, all campuses)
- Executive Director, Adviser (org-wide view)
- Director, Manager (campus-level management)
- Coordinator (location-level, can edit people in their location)
- Staff, Volunteer, Member (limited access)
- Admin is a toggle, not a separate role

## Completed Features (as of 2026-03-27)

### Phase 1 — Core
- [x] Authentication (JWT login/register)
- [x] Dashboard with campus switcher
- [x] People/Members management with families & children
- [x] Events with CRUD, check-ins, QR attendance
- [x] Calendar with iCal export/import
- [x] Task Boards (Kanban) with campus tagging
- [x] Check-in system with stats
- [x] Outreach programmes & sessions
- [x] Communications (announcements, email via Resend)
- [x] Resources management
- [x] Access Control with guest passes
- [x] Financial module (donations, expenses, approval workflows)
- [x] Sales & Products (POS, inventory, receipts)
- [x] Attendance tracking
- [x] Location management with sublocations

### Phase 2 — Advanced
- [x] Mobile-optimized responsive views
- [x] Advanced reporting by campus + PDF export
- [x] Campus Dashboard Switcher for system admins
- [x] "Enable Admin Access" toggle (not dropdown role)
- [x] Adviser role added
- [x] Multi-location staff assignment
- [x] Sublocation → campus user inheritance
- [x] Automatic staff title generation (e.g., "Operations Manager of 58:12 Uganda")
- [x] Global App Settings (app name, currency, footer, contact info)
- [x] Audit Trail with bulk select & delete

### Phase 3 — Sales & Outreach Enhancements (NEW)
- [x] Location-scoped products (location_id on products)
- [x] Location filter on Sales & Products page
- [x] Store Settings per location (payment methods, tax rate, currency, receipt footer, API integrations)
- [x] Sales Import/Export (JSON format)
- [x] Outreach sessions auto-create calendar events
- [x] Recurring outreach programmes auto-generate future events
- [x] Customer directory from sales data

## Upcoming / Backlog
- [ ] Financial live import/export API
- [ ] Calendar live import/export for regular users
- [ ] Restricted residents & guest pass QR enhancements
- [ ] Event recurrence customizations (monthly, yearly, weekly)
- [ ] AdminPage.jsx component splitting (refactoring)
- [ ] server.py modular router refactoring

## Key API Endpoints
- POST /api/auth/login — Login
- GET/PUT /api/global-settings — App settings
- GET/PUT /api/store-settings/{location_id} — Store config per location
- GET /api/sales/export — Export sales JSON
- POST /api/sales/import — Import sales JSON
- POST /api/outreach/sessions — Create session (auto-creates calendar event)
- PUT /api/admin/users/{id} — Staff editing with auto-titles
- DELETE /api/admin/deleted-items — Bulk delete from audit trail

## Test Reports
- Iterations 1-25: All passed (previous sessions)
- Iteration 26: 100% pass (28/28 backend, all frontend flows)
