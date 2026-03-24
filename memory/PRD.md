# 58:12 Global Connect Uganda — CRM PRD

## Original Problem Statement
Clone and rewrite the 58:12 Global Connect Uganda CRM with ALL features. Make the app production-ready.

## Product Requirements
- Unified "People" UI with API-level RBAC enforcement
- Offline/PWA support with background sync and mobile-optimized kiosk mode
- Push notification delivery via pywebpush
- Staff/Member self-service portal (Tasks, Chat, Expenses, etc.)
- Advanced reporting dashboard
- Admin capability to edit user profiles, manage passwords, and expense workflows
- WebAuthn Biometric authentication and Real NFC Web API
- Trello Kanban import, PIN-based check-in, recurring events, and bulk edit features
- Document scanning/upload via Web APIs, and networked Badge Printing

## Architecture

```
/app/
├── backend/
│   ├── deps.py              — DB, JWT, audit logger
│   ├── models.py            — Pydantic models (TaskCreate/Update now has assignees, is_archived, attachments)
│   ├── server.py            — FastAPI app, all routers registered
│   ├── storage.py           — Emergent object storage
│   └── routers/
│       ├── access.py, admin.py, auth.py, bookings.py, chat.py
│       ├── boards.py        — Kanban boards, lists (archive/restore), Trello import
│       ├── documents.py     — Document upload/workflow
│       ├── events.py, financial.py, import_csv.py, members.py
│       ├── misc.py, notifications.py, portal.py, programmes.py
│       ├── reports.py, tasks.py    — Cards (archive/restore, assignees, attachments, WS)
│       ├── webauthn.py      — Passkey auth
│       └── websocket.py     — WS manager + board room join/leave
└── frontend/
    └── src/
        ├── components/ui/   — Shadcn components
        ├── context/
        │   ├── AuthContext.js
        │   └── WebSocketContext.js   — joinBoard / leaveBoard added
        ├── pages/
        │   ├── TasksPage.jsx         — Full Kanban rebuild (dark navy, sidebar, archive, assignments)
        │   ├── AdminPage.jsx         — BadgePrintView with Bluetooth + ZPL support
        │   ├── UnifiedPeoplePage.jsx
        │   └── (all other pages)
        └── services/api.js  — boardsApi (archiveList/restoreList/archivedLists), tasksExtApi
```

## Key DB Schema
- `members`, `users`, `families` (uses `family_name`), `children`
- `boards`: id, name, location_id, background, is_global, created_by
- `board_lists`: id, board_id, name, position, is_archived, archived_at
- `tasks` (Cards): id, title, board_id, list_id, status, assignees[], is_archived, attachments[], checklist[], labels[]
- `webauthn_credentials`: id, user_id, credential_id, public_key

## 3rd Party Integrations
- Emergent LLM Key — Gemini (AI Assistant in Comms)
- Resend (Emails) — requires user API key
- Object Storage (Documents, Card Attachments) — Emergent LLM Key
- WebAuthn (Passkeys) — browser native
- NFC (NDEFReader) — browser native

## Test Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Local: admin@5812global.org / Admin@1234

---

## What's Been Implemented (Changelog Summary)

### Session 1 (Previous forks)
- [x] Full app scaffold (React + FastAPI + MongoDB)
- [x] Authentication (JWT, WebAuthn Passkeys, Google OAuth)
- [x] Unified People page (members + users, RBAC)
- [x] Events & Calendar with recurring events
- [x] Check-ins with PIN-based kiosk mode
- [x] Financial module (donations, expenses, products/POS)
- [x] Communications (chat, AI assistant via Gemini)
- [x] Reports & PDF export
- [x] PWA/offline support + push notifications
- [x] Document upload workflow
- [x] Badge printing (browser print, CR80 template)
- [x] NFC real check-ins via NDEFReader
- [x] Admin Full Profile Edit (4-tab dialog, all users/members)
- [x] Family/Children data fix (family_name migration)

### Session 2 (Previous fork — Kanban foundations)
- [x] Complete Trello-like Kanban UI rebuild (boards per location)
- [x] Drag-and-drop card movement
- [x] Trello JSON board import
- [x] WebSocket infrastructure (board rooms)
- [x] Iteration 13: 100% pass rate

### Session 3 (Current — 2026-03-24)
- [x] TasksPage.jsx: Full redesign — dark navy canvas, left sidebar board navigation, improved readability
- [x] Card memberships/assignments — multi-user staff selection in card detail
- [x] Archive cards — soft delete, accessible via hover icon + card detail button
- [x] Restore cards — from Archive panel
- [x] Archive lists — via list ... menu dropdown
- [x] Restore lists — from Archive panel
- [x] Hard delete for cards and lists with confirmation
- [x] Archive panel — opens from board header, tabs for Cards/Lists
- [x] Trello JSON attachment import — parses attachment metadata + attempts object storage copy
- [x] Card attachments — upload files to cards, view/delete
- [x] Real-time WebSocket sync — join_board/leave_board, board_presence, broadcast all mutations
- [x] Badge Printing: Bluetooth (Web Bluetooth API), ZPL code generation for Zebra printers
- [x] Iteration 14: 100% pass rate (21/21 backend, 27/27 frontend)

---

## Prioritized Backlog

### P0 — Critical / In Progress
- None (all current P0s resolved)

### P1 — High Priority
- [x] Badge printing via Web Bluetooth + ZPL (DONE in Session 3)
- [ ] File attachment storage: currently falls back to local filesystem if object storage fails; wire up properly

### P2 — Medium Priority
- [ ] SMS notification integration via Twilio
- [ ] Replace native date input in card detail with shadcn DatePicker
- [ ] Split TasksPage.jsx (1316 lines) into KanbanCard.jsx, KanbanList.jsx, ArchivePanel.jsx

### P3 — Low Priority / Future
- [ ] Card due-date reminders via push notifications
- [ ] Board sharing / external guest access
- [ ] Recurring task cards
- [ ] Bulk card operations (multi-select, bulk archive/move)
