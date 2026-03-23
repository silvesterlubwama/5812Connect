# 58:12 Global Connect CRM — PRD

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features from the original app, including backend.

## Target Users
- System Admins: Full access to all features + audit trail + locations management
- Admins: Member management, financial management, events, tasks, sales
- Staff: Check-ins, task management, basic member access
- Volunteers: Limited check-in and task access

## Core Requirements

### Authentication
- JWT-based auth with role-based access control
- Role-based default passwords (Admin@5812 / Staff@5812)
- Admin-only access for Audit Trail

### People Management
- Members: Full CRUD with search, filter, approve/reject
- Families: Family unit management with primary contact
- Children: Age/class tracking, medical notes
- Guests: Visitor log with referral tracking

### Ministry Operations
- Events: CRUD with public booking, iCal export
- Calendar: Monthly view with event dots, iCal export
- Tasks: Kanban board (Todo / In Progress / Done) with drag-and-drop
- Check-Ins: Venue-based check-in system

### Financial Management
- Donations: Record tithe, offering, donation, pledge with date
- Expenses: Categorized expenses (salaries, utilities, supplies, etc.)
- Financial Summary: Monthly stats (donations, expenses, sales, net balance)
- CSV Export for financial records

### Sales & Products (POS)
- Product catalog with stock tracking and reorder levels
- Full-screen POS interface: product grid + cart + checkout
- Receipt generation with invoice ID
- Sales history with payment method tracking

### Locations & Sub-locations
- Hierarchical structure: Main > Branch > Sub-location
- Per-location contact info and status

### Notifications
- Real-time bell icon with unread count polling (30s)
- Dropdown with notification types (info, warning, error, success)
- Mark individual or all as read
- Admin can create targeted notifications

### Global Search
- Ctrl+K or click to open search dialog
- Debounced search across members, events, tasks, products
- Quick navigation shortcuts

### Data Export
- CSV: Members, Events, Financial records
- iCal: Events export (.ics)

### Audit Trail
- Admin-only access
- Paginated log of all create/update/delete/login actions

## Technical Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI + React Router
- **Backend**: FastAPI + Motor (async MongoDB)
- **Auth**: JWT (local)
- **DB**: MongoDB (Motor async driver)

## What's Been Implemented

### ✅ Phase 1 (Complete)
- JWT Authentication, Login, Register, Reset Password
- Dashboard with stats + financial summary cards
- Members page with CRUD, search, approve/reject
- Events page with CRUD, public booking link
- Calendar with monthly view + iCal export
- Tasks with Kanban drag-and-drop
- Check-ins system with venue tracking
- Settings page (profile, password, preferences)
- Kiosk page (public check-in)
- Public Bookings page

### ✅ Phase 2 (Complete - 2026-03-23)
- Financial Management page (donations + expenses + summary cards + CSV export)
- Sales & Products POS (product catalog CRUD + full POS interface + receipt + sales history)
- Families & People page (families cards + children table + guests log)
- Audit Trail page (admin-only, paginated, role-guarded)
- Locations page (hierarchical: Main > Branch > Sub-location, CRUD)
- Notification center (bell badge + dropdown + mark read + polling)
- Global search (Ctrl+K dialog, debounced, cross-collection)
- CSV/iCal export endpoints
- Dashboard enhanced with financial summary row
- Sidebar organized into sections (People, Ministry, Finance, Admin)
- Role-based nav (Audit Trail admin-only)

## Backlog (P2)
- Multi-location filtered dashboards (staff sees their location's data only)
- Web Push Notifications (VAPID service worker)
- "View as" role simulation for admins
- Refactor server.py into modular routers
- Trello-style board with JSON import/export
- Advanced recurring events (Nth-weekday recurrence)
- Email invoice delivery (PDF attachment)
- Barcode scanner integration in POS

## Key API Endpoints
- `POST /api/auth/login` — JWT login
- `GET /api/dashboard/stats` — Dashboard stats
- `GET /api/financial/summary` — Monthly financial summary
- `GET /api/locations` — All locations (hierarchical via parent_id)
- `GET /api/notifications` — User notifications (role-filtered)
- `GET /api/notifications/unread-count` — Badge count
- `PUT /api/notifications/read-all` — Mark all read
- `GET /api/search?q=...` — Global search
- `GET /api/export/members` — CSV members export
- `GET /api/export/financial` — CSV financial export
- `GET /api/export/events` — CSV events export
- `GET /api/export/events.ics` — iCal events export
- `GET /api/families` / `POST /api/families` — Families CRUD
- `GET /api/children` / `POST /api/children` — Children CRUD
- `GET /api/guests` / `POST /api/guests` — Guests CRUD
- `GET /api/audit` — Audit trail (admin only)

## Default Credentials
- Admin: `admin@5812global.org` / `Admin@1234`
- Admin (live): `admin@5812uganda.org` / `Admin@5812`

## Files of Reference
- `/app/backend/server.py` — Monolithic FastAPI backend (all routes)
- `/app/frontend/src/App.js` — Routes
- `/app/frontend/src/components/Layout.jsx` — Shell with nav, notifications, search
- `/app/frontend/src/services/api.js` — All API calls
- `/app/frontend/src/pages/FinancialPage.jsx` — Financial management
- `/app/frontend/src/pages/ProductsPage.jsx` — Sales & POS
- `/app/frontend/src/pages/PeoplePage.jsx` — Families/Children/Guests
- `/app/frontend/src/pages/AuditPage.jsx` — Audit trail
- `/app/frontend/src/pages/LocationsPage.jsx` — Location management
