# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Architecture
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI + qrcode.react
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT-based, role-based access control (RBAC)
- **DB**: MongoDB (collections: users, members, families, children, guests, events, checkins, tasks, boards, donations, expenses, products, sales, locations, conversations, messages, deleted_items, etc.)

## Core Features (All Complete)
- Dashboard with campus-scoped stats
- People Management (Members, Families, Children, Guests)
- Events & Calendar with recurrence
- Kanban Task Boards with Team Calendar
- Check-In System (QR-based)
- Chat/Communications with AI Assistant
- Financial Management (Donations, Expenses, Sales, Products)
- Badge/Tag Printing (Staff, Parent, Child) with QR codes
- Self-Service Portal for families
- Audit Trail with Soft-Delete (Recycle Bin)
- Access Control with restricted locations
- Reports & PDF generation
- Import/Export (CSV/JSON)
- PWA support

## Campus-Based Data Isolation (RBAC) — IMPLEMENTED
- **System Admins** (admin, system_admin, Director, Executive Director): See ALL data across all campuses
- **Non-admin users** (Staff, Volunteer, Coordinator, Manager, etc.): See only data within their assigned campus (location_id filter)
- **Restricted sub-locations**: Children in restricted sub-locations only visible to staff assigned to that exact location
- **Campus filter applied to**: members, children, families, guests, events, checkins, dashboard stats, financial data, resources, reports, chat users, products, sales
- **Helpers**: `is_system_admin()`, `get_campus_filter()` in deps.py

## Staff Auto-Sync — IMPLEMENTED
- Creating a user in Staff Admin automatically creates a linked member record
- Updating a user also updates their linked member, auto-creates member if missing
- `location_id` saved to both users and members collections

## Badge Location Name — IMPLEMENTED
- Badges show campus/location name instead of "Central System"
- StaffBadge, ParentBadge, ChildTag components use `locationName` prop
- AdminPage badge preview shows `user.location_name`

## Nav Rename — IMPLEMENTED
- "Locations" renamed to "Campuses" in sidebar navigation and i18n

## 3rd Party Integrations
- Emergent LLM Key (Gemini AI Assistant)
- Resend (Emails - requires user API key)

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Admin2: admin@5812global.org / Admin@1234

## Test Reports
- Iterations 18-23 all passed (100% backend, frontend verified)
