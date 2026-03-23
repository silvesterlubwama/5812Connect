# 58:12 Global Connect Uganda CRM — PRD

## Problem Statement
Full-featured multi-location CRM for 58:12 Global Connect with complete feature parity: members, events, tasks, calendar, location-scoped financials, products/POS, families, locations (Compass system), audit trails, analytics, communications with AI chat, outreach, resources, Google OAuth, dark mode, CSV imports, and fund distribution.

## Architecture
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI + Recharts
- **Backend**: FastAPI + Motor (Async MongoDB) + Pydantic
- **Auth**: JWT (email/password) + Google OAuth (via Emergent Auth)
- **AI**: Gemini 2.5 Flash (via emergentintegrations)
- **Database**: MongoDB

## Location Hierarchy (Compass System)
- **Main** → Top-level organization (USD as reference currency)
- **Compass** → Regional branches (each with own currency, departments, staff, finances)
- **Sub-Location** → Venues/areas within a compass (can be bookable, restricted)
- Each location tracks its own: inventory, resources, users, finances
- Location Director = contact person selected from staff

## Role Hierarchy
Executive Director → Advisor → Director → Manager → Coordinator → Staff → Intern/Volunteer → Parent → Customer
- Staff can also be marked as Parent, Customer, and/or Donor (multi-role)
- Only system admins can change main org settings

## Financial System
- Each location tracks own finances; Main + system admins see all or breakdown
- Fund distribution: Main → Compass → Sub-locations (creates paired expense/donation)
- Each location has own currency with exchange rates to USD
- Sales revenue added to location's balance

## Resource Types
Sports Equipment, Venues, Media Equipment, Educational Material, Consumables, Rooms
- Bookable / Staff-Only / Not Bookable flags
- Each compass/sub-location tracks own resources

## CSV Import System
- Children + Parents: first_name, last_name, date_of_birth, grade, family_name, fathers_names, fathers_phone, mothers_names, mothers_phone, allergies, medical_notes, special_needs
- Staff: name, email, phone, national_id, role, department

## Communications
- Staff chat (within same compass, cross-director)
- AI chat assistant (Gemini)
- No-reply announcements channel
- Conversation types: direct, group, announcements

## All Pages & Features (Tested ✅)

| Page | Key Features | Status |
|------|-------------|--------|
| Dashboard | Stats, parent view, quick actions | ✅ |
| Members | CRUD, Approvals, Badges, Multi-role, CSV imports (children+parents, staff) | ✅ |
| Families & People | Family CRUD, member linking | ✅ |
| Events | CRUD, booking, capacity | ✅ |
| Calendar | Monthly view, recurring events, iCal export | ✅ |
| Tasks | CRUD, Kanban, priority | ✅ |
| Check-Ins | Manual/QR/ID, kiosk mode | ✅ |
| Financial | Location-scoped, Cashflow chart, Fund distribution, Date filter | ✅ |
| Sales & Products | POS, Products, Sales History, Customers tab | ✅ |
| Attendance Analytics | Trends, stats | ✅ |
| Sales Analytics | Revenue, payments, top products | ✅ |
| Location Analytics | Comparison, distribution | ✅ |
| Communications | Chat UI, AI Assistant (Gemini), Announcements | ✅ |
| Outreach | Programs, Sessions, Volunteers | ✅ |
| Resources | Types (Sports/Media/Educational/Consumable/Venue), Bookable/Staff-only | ✅ |
| Locations | Compass hierarchy, multi-currency, director, departments, venue/bookable/restricted | ✅ |
| Audit Trail | Activity log with filters | ✅ |
| Settings | Organization, Venues, Notifications, Security, Admin (system admin only) | ✅ |
| Login | Email/Password + Google OAuth + Parent Portal | ✅ |
| Dark Mode | Toggle in header, persisted | ✅ |

## Test Results
- Iteration 1: 98% pass (initial features)
- Iteration 2: 100% pass (17/17 - mega batch)
- Iteration 3: 100% pass (25/25 - compass overhaul + chat + AI)

## Tech Debt
- P0: Refactor `server.py` (2300+ lines) into modular routers

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Alt Admin: admin@5812global.org / Admin@1234
