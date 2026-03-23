# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## User Personas
- **Admin/Director**: Full access — manage all members, locations, finance, settings, access control
- **Coordinator/Manager**: Manage people in their compass, approve requests, run reports
- **Staff**: Check-in members, manage events, limited access
- **Parent**: View child info via parent portal
- **Guest/Visitor**: External, tracked via guest request system

## Core Requirements
1. Compass/Sub-location hierarchy with localized currencies
2. Member management with roles, groups, departments
3. Children/parent/family management with child safety features
4. Event management with check-ins
5. Financial tracking: donations, expenses, fund distribution
6. Communications (AI-assisted chat, WhatsApp-style messaging)
7. Resource/space booking
8. Task management
9. Sales & products tracking
10. Restricted access management with scan in/out
11. Reporting dashboard with PDF export
12. Real CSV file upload for bulk importing
13. Document storage (ID scans) for members
14. Email notifications (Resend)
15. WebSocket for live chat

## Technical Stack
- Frontend: React, Tailwind CSS, Shadcn/UI, Recharts
- Backend: FastAPI, Motor (Async MongoDB), ReportLab (PDFs)
- Auth: JWT + Google Social Login
- Storage: Emergent Object Storage (ID document scans)
- AI: Gemini 2.0 Flash (Communications assistant)
- Email: Resend

## Key Business Rules
- Gender: Strictly Male or Female only
- Department: Selected from available departments at user's location
- Children/Parents/Guests: No department required, use "programme" instead
- ID Documents: Required for all users except children (JPG/PNG)
- Access Control: Scan in/out for restricted spaces (shelters, special needs areas)

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Alt Admin: admin@5812global.org / Admin@1234

## Architecture
```
/app/
├── backend/
│   ├── server.py (Main FastAPI app)
│   ├── deps.py (Shared dependencies)
│   ├── storage.py (Object storage for document uploads)
│   ├── routers/
│   │   ├── documents.py (Document upload/list/download)
│   │   ├── access.py (Restricted access management)
│   │   ├── reports.py (Reporting & PDF export)
│   │   ├── notifications.py (Email via Resend)
│   │   ├── websocket.py (Live chat)
│   │   └── bookings.py (Resource booking)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.js (Routing)
        ├── components/Layout.jsx (Navigation)
        ├── pages/ (All page components)
        └── services/api.js (API methods)
```

## What's Implemented (as of 2026-03-23)
- [x] Full authentication (JWT + Google OAuth)
- [x] Dashboard with analytics
- [x] Member management (CRUD, filtering, search)
- [x] Gender restricted to Male/Female
- [x] Department dropdown based on location
- [x] Children/Parents/Guests bypass department
- [x] Document storage (ID scan upload, JPG/PNG)
- [x] Families & People management
- [x] Events with check-ins
- [x] Calendar view
- [x] Task management
- [x] Financial management (donations, expenses, fund transfers)
- [x] Communications (AI chat, conversations)
- [x] Resource & space booking
- [x] Sales & products
- [x] Restricted Access Control page (residents, staff passes, guest requests, scan in/out)
- [x] Reports Dashboard with PDF export
- [x] Real CSV file upload (members, children/parents, staff)
- [x] Scrollable modals throughout the app
- [x] Compasses & Locations management
- [x] Attendance analytics
- [x] Sales analytics
- [x] Location stats
- [x] Audit trail
- [x] Settings
- [x] Outreach
- [x] Notifications (Resend email)
- [x] WebSocket live chat

## P0 Remaining
- None

## P1 Remaining  
- Unified "People" UI with tabs combining all people management + strict RBAC (Directors/Execs vs Managers multi-user bulk edits)

## P2 / Future
- Consolidate duplicated logic between MembersPage.jsx and PeoplePage.jsx
- Enhanced RBAC enforcement across all pages
- Offline/PWA support for field workers
