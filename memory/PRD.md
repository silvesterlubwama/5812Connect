# 58:12 Global Connect Uganda CRM — Product Requirements Document

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready with:
- Unified "People" UI combining all roles with API-level RBAC enforcement
- Offline/PWA support with background sync and mobile-optimized kiosk mode
- Push notification delivery via pywebpush
- Biometric/NFC scanning for access control
- Multi-language support (English, Luganda, Swahili, Thai, Haitian, Spanish, French)
- Real CSV file upload functionality
- Internal document storage for ID scans
- Advanced reporting dashboard with exportable PDFs
- Staff/Member Self-Service Portal (tasks, expenses, chat, cash requests, events)

## Tech Stack
- **Frontend**: React, Tailwind CSS, Shadcn/UI, PWA (Service Workers, Background Sync), Context API
- **Backend**: FastAPI, Motor (Async MongoDB), PyWebPush (VAPID), ReportLab, WebSockets, JWT Auth
- **Database**: MongoDB
- **3rd Party**: Emergent LLM Key (Gemini Flash for AI assistant), Object Storage (documents)

## Architecture
```
/app/backend/
  server.py          — Core (events, tasks, financial, push, biometric, NFC, kiosk, chat, search, analytics)
  deps.py            — Shared auth, RBAC, DB, helpers
  models.py          — Shared Pydantic models
  storage.py         — File storage logic
  routers/
    auth.py          — Auth (login, register, password reset, Google SSO)
    members.py       — Members, families, children, guests, badges, approvals
    import_csv.py    — CSV file upload import
    portal.py        — Staff/Member Self-Service Portal endpoints
    access.py        — Access control (locations, guest requests, scan)
    bookings.py      — Public bookings, space bookings
    documents.py     — Internal document storage
    notifications.py — Email notifications, in-app notifications
    reports.py       — PDF report generation
    websocket.py     — WebSocket chat/messaging
/app/frontend/
  public/sw.js, manifest.json  — PWA service worker
  src/
    context/         — AuthContext, WebSocketContext, I18nContext
    i18n/            — Translation JSON files (en, lg, sw, th, ht, es, fr)
    components/      — Layout, PortalLayout, UI components
    pages/           — All pages including Portal (Dashboard, Tasks, Expenses, Events, Profile, Sales, Documents)
    services/api.js  — API client with portalApi
```

## DB Collections
users, members, families, children, guests, events, tasks, checkins, donations, expenses,
sales, products, venues, badges, locations, access_logs, guest_requests, nfc_tags,
biometric_credentials, chat_messages, conversations, notifications, push_subscriptions,
files, audit_log, password_resets, outreach_programs, app_settings

## Credentials
- Admin 1: admin@5812global.org / Admin@1234
- Admin 2: admin@5812uganda.org / Admin@5812

## What's Implemented (Complete)
- [x] JWT Authentication + Google SSO
- [x] RBAC enforcement (10-level role hierarchy)
- [x] Unified People UI (members, families, children, guests)
- [x] Member CRUD with approval workflow
- [x] Events CRUD with check-in tracking
- [x] Tasks (Kanban board)
- [x] Financial module (donations, expenses, products/sales, fund transfers)
- [x] Access control (locations, guest requests, scan in/out)
- [x] Kiosk mode (mobile-optimized, offline-capable)
- [x] WebSocket real-time chat
- [x] In-app notification system
- [x] Document storage for ID scans
- [x] PDF report generation
- [x] Real CSV file upload (members, children-parents, staff)
- [x] PWA/Offline support with background sync
- [x] Multi-language support (7 languages: EN, LG, SW, TH, HT, ES, FR)
- [x] Web Push notifications via pywebpush (VAPID keys generated)
- [x] Biometric/NFC scanning UI (Kiosk + Access pages)
- [x] Push notification toggle in Settings
- [x] Server refactoring (auth, members, imports extracted to routers)
- [x] **Staff/Member Self-Service Portal** with:
  - Portal Dashboard (overview stats: tasks, expenses, events, messages)
  - My Tasks (Kanban: view + update status of assigned tasks)
  - Chat (full messaging in portal context)
  - Expenses (submit expenses, view history, track status)
  - Cash Requests (submit via chat, auto-notify admins)
  - Events (view upcoming, RSVP)
  - My Sales (view sales created by user)
  - Documents (view own documents)
  - Profile (view/edit personal info, check-in history)

## Backlog (P2)
- [ ] SMS notification integration via Twilio
- [ ] Further server.py refactoring (extract events, tasks, financial, chat into routers)
- [ ] End-to-end WebAuthn biometric authentication
- [ ] Real NFC Web API integration for physical tag reads
