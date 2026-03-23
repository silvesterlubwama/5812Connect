# 58:12 Global Connect Uganda CRM — PRD

## Problem Statement
Full-featured multi-location CRM for 58:12 Global Connect with: Compass system (multi-country, multi-currency), role hierarchy, location-scoped financials with fund distribution, resource management with booking system (1hr buffer), real-time chat with Gemini AI assistant, CSV imports, Google OAuth, dark mode, rate limiting, and modular architecture.

## Architecture
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI + Recharts
- **Backend**: FastAPI + Motor (Async MongoDB) + Pydantic + Modular Routers
- **Auth**: JWT (email/password) + Google OAuth (Emergent Auth)
- **AI**: Gemini 2.5 Flash (emergentintegrations)
- **Real-time**: WebSocket (FastAPI native)
- **Database**: MongoDB
- **Security**: Rate limiting (120 req/min), CORS, JWT auth

## Key Systems

### Location Hierarchy (Compass System)
Main → Compass (regional, own currency) → Sub-Location (venues, bookable, restricted)
- Each tracks own: inventory, resources, staff, finances, departments
- Location Director selected from staff

### Role Hierarchy
Executive Director → Advisor → Director → Manager → Coordinator → Staff → Intern/Volunteer → Parent → Customer
- Multi-role: Staff can also be Parent/Customer/Donor

### Financial System (Location-Scoped)
- Per-location financials; Main sees all/breakdown
- Fund distribution: Main ↔ Compass ↔ Sub-locations
- Configurable currency; auto-exchange to USD

### Booking System (1-Hour Buffer)
- Resources and sub-locations can be bookable
- 1-hour buffer enforced between bookings
- Staff-only bookable resources
- Sub-location booking blocks child venue availability

### Communications
- Pinned rooms: AI Assistant (Gemini) + Announcements (no-reply)
- Staff conversations (direct, group)
- WebSocket for real-time updates

### Import System
- Children + Parents CSV import
- Staff CSV import
- Quick bulk member import

## All Pages (Tested ✅)
Dashboard, Members, Families, Events, Calendar, Tasks, Check-Ins, Financial, Sales/POS, Attendance Analytics, Sales Analytics, Location Analytics, Communications, Outreach, Resources, Locations, Audit Trail, Settings, Login

## Test Results
- Iteration 1: 98% (initial features)
- Iteration 2: 100% (mega batch)
- Iteration 3: 100% (compass overhaul + chat + AI)
- Iteration 4: 96%/100% (bookings, rate limiting, pinned rooms, WebSocket)

## File Structure
```
/app/backend/
├── server.py (main routes)
├── deps.py (shared dependencies)
├── routers/
│   ├── bookings.py (booking system + buffer)
│   └── websocket.py (real-time connections)
└── requirements.txt
/app/frontend/src/
├── pages/ (20 page components)
├── components/ (Layout, ui/)
├── services/api.js
└── context/AuthContext.js
```

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Alt: admin@5812global.org / Admin@1234
