# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Architecture
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI + Recharts + qrcode.react
- **Backend**: FastAPI + Motor (Async MongoDB) + Resend (Email)
- **Auth**: JWT-based, role-based access control (RBAC)
- **DB**: MongoDB (users, members, families, children, guests, events, checkins, tasks, boards, donations, expenses, products, sales, locations, conversations, messages, deleted_items, email_log)

## Core Features (All Complete)
- Dashboard with campus-scoped stats & Campus Switcher
- People Management (Members, Families, Children, Guests)
- Events & Calendar with recurrence
- Kanban Task Boards with Team Calendar
- Check-In System (QR-based)
- Chat/Communications with AI Assistant
- Financial Management (Donations, Expenses, Sales, Products)
- Badge/Tag Printing (Staff, Parent, Child) with QR codes & campus names
- Self-Service Portal for families
- Audit Trail with Soft-Delete (Recycle Bin)
- Access Control with restricted locations
- Reports & PDF generation
- Import/Export (CSV/JSON)
- PWA support
- Mobile-optimized responsive views

## Campus-Based Data Isolation (RBAC) — IMPLEMENTED
- System Admins (admin, system_admin, Director, Executive Director): See ALL data
- Non-admin users: See only their campus data
- Restricted sub-locations: Extra privacy for children
- Helpers: `is_system_admin()`, `get_campus_filter()` in deps.py
- Applied across ALL endpoints

## Campus Dashboard Switcher — IMPLEMENTED
- System admins see dropdown to filter dashboard by specific campus
- "Viewing: [campus]" indicator with "Show All" reset button
- Non-admins always see their campus only

## Advanced Campus Reports — IMPLEMENTED
- `/campus-reports` page with comparison view
- Bar charts comparing members/children across campuses
- Campus detail drilldown with pie charts & 6-month financial trends
- Date range filtering, PDF export, Email report
- Backend: `/api/reports/campus-comparison`, `/api/reports/campus/{id}`

## Email Integration (Resend) — IMPLEMENTED
- Templates: Welcome, Event Invite, Password Reset, Report, Custom
- Non-blocking async sending via `asyncio.to_thread`
- Email log stored in DB
- API: `/api/email/send`, `/api/email/templates`, `/api/email/log`

## Mobile Optimization — IMPLEMENTED
- Responsive grids (2-col mobile, 4-col desktop)
- Hamburger sidebar menu on mobile
- Touch-friendly targets (min 36px)
- No horizontal overflow
- Compact search icon on mobile
- 16px font-size for inputs (prevents iOS zoom)

## Staff Auto-Sync — IMPLEMENTED
## Badge Location Names — IMPLEMENTED
## Nav: "Locations" → "Campuses" — IMPLEMENTED

## 3rd Party Integrations
- Emergent LLM Key (Gemini AI Assistant)
- Resend (Email) — Key: re_4zD1Movm... (configured)

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Admin2: admin@5812global.org / Admin@1234

## Test Reports
- Iterations 18-24 all passed (100%)
