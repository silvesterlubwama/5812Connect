# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Architecture
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI + Recharts + qrcode.react
- **Backend**: FastAPI + Motor (Async MongoDB) + Resend (Email)
- **Auth**: JWT-based, role-based access control (RBAC) with admin toggle
- **DB**: MongoDB (users, members, families, children, guests, events, checkins, tasks, boards, donations, expenses, products, sales, locations, conversations, messages, deleted_items, email_log)

## Role Hierarchy
1. System Admin (admin/system_admin) — toggle, not selectable role
2. Executive Director (level 9)
3. Adviser (level 8.5) — cross-campus visibility
4. Director (level 8) — cross-campus visibility
5. Manager (level 7)
6. Coordinator (level 6)
7. Staff (level 5)
8. HR, Volunteer, Member, Parent, Customer, Guest

## Campus-Based RBAC — IMPLEMENTED
- System admins (admin, Executive Director, Adviser, Director): see ALL data
- Non-admin users: see only their campus data
- Admin is a toggle (not a role in dropdown) — enables cross-campus admin access
- Campus switcher for system admins on Dashboard and Reports

## Features (All Complete)
- Dashboard with campus-scoped stats & Campus Switcher
- People Management (Members, Families, Children, Guests) with location assignment
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
- Advanced Campus Reports (comparison, detail, trends)
- Email Integration (Resend) with templates
- Import/Export (CSV/JSON)
- PWA support
- Mobile-optimized responsive views

## 3rd Party Integrations
- Emergent LLM Key (Gemini AI Assistant)
- Resend (Email) — configured

## Credentials
- Admin: admin@5812uganda.org / Admin@5812

## Test Reports
- Iterations 18-25 all passed (100%)
