# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready, downloadable on any device with offline support.

## User Personas
- **Admin/Director**: Full access — manage all members, locations, finance, settings, access control
- **Coordinator/Manager**: Manage people in their compass, approve requests, run reports
- **Staff**: Check-in members, manage events, limited access
- **Parent**: View child info via parent portal
- **Guest/Visitor**: External, tracked via guest request system

## Technical Stack
- Frontend: React, Tailwind CSS, Shadcn/UI, Recharts
- Backend: FastAPI, Motor (Async MongoDB), ReportLab (PDFs)
- Auth: JWT + Google Social Login
- Storage: Emergent Object Storage (ID document scans)
- AI: Gemini 2.0 Flash (Communications assistant)
- Email: Resend
- Real-time: WebSocket (chat, notifications, online status)
- PWA: Service Worker, manifest.json, offline-first caching

## Key Business Rules
- Gender: Strictly Male or Female only
- Department: Selected from available departments at user's location
- Children/Parents/Guests: No department required, use "programme" instead
- ID Documents: Required for all users except children (JPG/PNG)
- Access Control: Scan in/out for restricted spaces

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Alt Admin: admin@5812global.org / Admin@1234

## What's Implemented (as of 2026-03-23)

### Core CRM
- [x] Full authentication (JWT + Google OAuth)
- [x] Working password reset flow via Resend email
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
- [x] Sales & products
- [x] Outreach programs

### Communications
- [x] AI-assisted chat (Gemini)
- [x] WebSocket real-time messaging
- [x] Online/offline status indicators
- [x] Typing indicators
- [x] Read receipts (double blue check)
- [x] Reply to specific messages
- [x] Announcements channel

### Access & Security
- [x] Restricted Access Control (residents, staff passes, guest requests, scan in/out)
- [x] Real-time notification bell for guest approval alerts
- [x] RBAC enforcement in navigation sidebar
- [x] Role-based page visibility
- [x] Audit trail

### Reporting & Import
- [x] Reports Dashboard with PDF export
- [x] Real CSV file upload (members, children/parents, staff)
- [x] Scrollable modals throughout the app

### PWA & Offline
- [x] Service Worker for offline support
- [x] PWA manifest for installable app
- [x] Network-first API caching with offline fallback
- [x] Cache-first static asset strategy
- [x] Online/offline detection in header
- [x] App title: "58:12 Global Connect"

### Infrastructure
- [x] MongoDB index optimization (15+ indexes)
- [x] Health check endpoint (/api/health)
- [x] WebSocket connection manager with auto-reconnect
- [x] Comprehensive error handling

## Architecture
```
/app/
├── backend/
│   ├── server.py (Main FastAPI app)
│   ├── deps.py (Shared dependencies)
│   ├── storage.py (Object storage)
│   ├── routers/
│   │   ├── documents.py, access.py, reports.py
│   │   ├── notifications.py, websocket.py, bookings.py
│   └── requirements.txt
└── frontend/
    ├── public/ (manifest.json, sw.js, icons)
    └── src/
        ├── App.js, index.js
        ├── context/ (AuthContext, WebSocketContext)
        ├── components/ (Layout, ui/)
        ├── pages/ (20+ page components)
        └── services/api.js
```

## P1 Remaining
- Unified "People" UI: Single tabbed interface combining MembersPage + PeoplePage
- Consolidate duplicated logic between member/people forms

## P2 / Future
- Enhanced RBAC enforcement on API endpoints (not just nav)
- Push notifications (Web Push API)
- Background sync for offline message queuing
