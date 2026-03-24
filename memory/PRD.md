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
- **3rd Party**: Emergent LLM Key (Gemini Flash for AI assistant), Local File Storage (documents at /app/backend/uploads/)

## Architecture
```
/app/backend/
  server.py          — Core (events, tasks, financial, push, biometric, NFC, kiosk, chat, search, analytics)
  deps.py            — Shared auth, RBAC, DB, helpers
  models.py          — Shared Pydantic models
  storage.py         — Legacy object storage (not used for documents)
  uploads/           — LOCAL document file storage (per-member subdirs)
  routers/
    auth.py          — Auth (login, register, password reset, Google SSO)
    admin.py         — Admin user management, full profile edit (users+members merged), bulk ops, audit
    members.py       — Members, families, children, guests, badges, approvals
    import_csv.py    — CSV file upload import
    portal.py        — Staff/Member Self-Service Portal endpoints
    access.py        — Access control (locations, guest requests, scan)
    bookings.py      — Public bookings, space bookings
    documents.py     — Document storage (local fs), document requests, ID types
    notifications.py — Email notifications, in-app notifications
    reports.py       — PDF report generation
    websocket.py     — WebSocket chat/messaging
/app/frontend/
  public/sw.js, manifest.json  — PWA service worker
  src/
    context/         — AuthContext, WebSocketContext, I18nContext
    i18n/            — Translation JSON files (en, lg, sw, th, ht, es, fr)
    components/      — Layout, PortalLayout, UI components
    pages/
      AdminPage.jsx  — Full user+member profile edit (4 tabs: Profile/Account/Flags/Documents), badge print, scanner
      PortalDocuments.jsx — Self-upload, pending requests from admin, fulfill requests
    services/api.js  — API client with portalApi, documentsApi, adminApi
```

## DB Collections
users, members, families, children, guests, events, tasks, checkins, donations, expenses,
sales, products, venues, badges, locations, access_logs, guest_requests, nfc_tags,
biometric_credentials, chat_messages, conversations, notifications, push_subscriptions,
files, document_requests, audit_log, password_resets, outreach_programs, app_settings

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
- [x] **Document storage (local filesystem)** — member upload, admin requests, 11 ID types, serve & download
- [x] PDF report generation
- [x] Real CSV file upload (members, children-parents, staff)
- [x] PWA/Offline support with background sync
- [x] Multi-language support (7 languages: EN, LG, SW, TH, HT, ES, FR)
- [x] Web Push notifications via pywebpush (VAPID keys generated)
- [x] Biometric/NFC scanning UI (Kiosk + Access pages)
- [x] Push notification toggle in Settings
- [x] **Backend fully modular** (all routes in dedicated routers)
- [x] **Staff/Member Self-Service Portal** with Dashboard, Tasks, Chat, Expenses, Events, Sales, Documents, Profile
- [x] Trello kanban board import
- [x] PIN code check-in / checkout
- [x] Bulk select for mass edit/delete (People + Admin)
- [x] Expense approval workflow
- [x] Resource type management
- [x] Event type management, duplication, recurring, internal/external, free/paid
- [x] **Admin full profile edit** — merged users+members in one 4-tab dialog (Profile/Account/Flags/Documents)
- [x] **Document workflow** — self-upload by member (portal), admin/HR requests docs from members, 11 ID types
- [x] **Badge printing** — CR80 badge with company logo, print via window.open()
- [x] **Scanner integration** — Web Bluetooth/USB Serial with graceful fallback to file upload
- [x] Footer updated to "Central System" (was "Uganda CRM System")

## Backlog (P0 — High Priority)
- [ ] Real WebAuthn Biometric API (Passkey/FIDO2) for passwordless login
- [ ] Real NDEFReader NFC Web API for physical NFC tag reads

## Backlog (P2 — Low Priority)
- [ ] SMS notification integration via Twilio
