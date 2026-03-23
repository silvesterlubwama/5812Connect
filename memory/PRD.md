# 58:12 Global Connect Uganda CRM — Product Requirements

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready, downloadable on any device with offline support.

## Technical Stack
- Frontend: React, Tailwind CSS, Shadcn/UI, Recharts
- Backend: FastAPI, Motor (Async MongoDB), ReportLab (PDFs)
- Auth: JWT + Google Social Login
- Storage: Emergent Object Storage (ID document scans)
- AI: Gemini 2.0 Flash (Communications assistant)
- Email: Resend
- Real-time: WebSocket (chat, notifications, online status)
- PWA: Service Worker, manifest.json, offline-first, background sync

## Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Alt Admin: admin@5812global.org / Admin@1234

## RBAC Levels
| Level | Roles |
|-------|-------|
| 10 | system_admin, admin |
| 9 | Executive Director |
| 8 | Director |
| 7 | Manager |
| 6 | Coordinator |
| 5 | Staff |
| 4 | Volunteer |
| 3 | Member |
| 2 | Parent |
| 1 | Customer, Guest |

## What's Implemented (as of 2026-03-23)

### Core CRM
- [x] Full authentication (JWT + Google OAuth)
- [x] Working password reset flow via Resend email
- [x] Unified People page (Members + Families + Children + Guests in tabbed UI)
- [x] Shared MemberForm component (consolidated form logic)
- [x] Gender restricted to Male/Female
- [x] Department dropdown based on location
- [x] Children/Parents/Guests bypass department
- [x] Document storage (ID scan upload, JPG/PNG)
- [x] Events with check-ins, Calendar view
- [x] Task management
- [x] Financial management (donations, expenses, fund transfers)
- [x] Sales & products, Outreach programs

### Communications
- [x] AI-assisted chat (Gemini), WebSocket real-time messaging
- [x] Online/offline status, Typing indicators, Read receipts
- [x] Reply to specific messages, Announcements channel

### Access & Security
- [x] Restricted Access Control (residents, staff passes, guest requests, scan in/out)
- [x] Real-time notification bell (WebSocket broadcast)
- [x] API-level RBAC enforcement (financial=Manager+, delete=Coordinator+, admin=Admin, imports=Manager+)
- [x] RBAC navigation sidebar (role-based page visibility)
- [x] Audit trail

### Reporting & Import
- [x] Reports Dashboard with PDF export
- [x] Real CSV file upload (members, children/parents, staff)

### PWA & Offline
- [x] Service Worker with background sync (message queue)
- [x] PWA manifest (installable on any device)
- [x] Network-first API caching with offline fallback
- [x] Online/offline detection in header
- [x] Web Push notification subscription (VAPID)
- [x] Offline message sync endpoint (/api/sync/messages)

### Mobile Kiosk
- [x] Mobile-optimized field kiosk mode (/kiosk)
- [x] Quick visitor check-in (no auth required)
- [x] ID lookup check-in
- [x] Access scan in/out for restricted locations
- [x] Staff authentication for full kiosk features
- [x] Large touch targets, offline indicator

### Infrastructure
- [x] MongoDB indexes (15+ performance indexes)
- [x] Health check endpoint (/api/health)
- [x] WebSocket with auto-reconnect

## Architecture
```
/app/backend/
  server.py, deps.py (RBAC), storage.py
  routers/ (documents, access, reports, notifications, websocket, bookings)
/app/frontend/src/
  context/ (AuthContext, WebSocketContext)
  pages/ (UnifiedPeoplePage, CommsPage, AccessPage, ReportsPage, KioskPage, ...)
  components/ (Layout with RBAC nav, ui/)
  services/api.js (accessApi, reportsApi, pushApi, syncApi, csvUploadApi)
/app/frontend/public/
  sw.js (background sync), manifest.json, logo192/512.png
```

## All Features Complete
No P0/P1 items remaining. Application is production-ready.

## P2 / Future Enhancement Ideas
- Push notification delivery via WebPush library (pywebpush)
- Biometric/NFC scanning for access control
- Offline data editing with conflict resolution
- Multi-language support (Luganda, Swahili)
- SMS notifications via Twilio
