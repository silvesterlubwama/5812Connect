# 58:12 Global Connect Uganda — PRD (Updated)

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
│   ├── models.py            — Pydantic models (TaskCreate/Update: assignees, is_archived, attachments)
│   ├── server.py            — FastAPI app, LocationCreate/Update with timezone, due-date scheduler (today+tomorrow)
│   ├── storage.py           — Emergent object storage
│   └── routers/
│       ├── access.py, auth.py (visitor-register), bookings.py, chat.py (AI w/ context)
│       ├── admin.py         — Users CRUD + POST /users (create) + POST /users/import
│       ├── boards.py        — Kanban boards, lists (archive/restore), Trello import
│       ├── tasks.py         — Cards (archive/restore, assignees, attachments, local file serve)
│       ├── webauthn.py, websocket.py (board rooms join/leave)
│       └── (all other routers)
└── frontend/
    └── src/
        ├── pages/
        │   ├── TasksPage.jsx         — Board/Calendar view toggle
        │   ├── kanban/               — Kanban component split
        │   │   ├── KanbanCard.jsx
        │   │   ├── KanbanList.jsx
        │   │   ├── ArchivePanel.jsx
        │   │   ├── CardDetailDialog.jsx
        │   │   └── TeamCalendar.jsx  — Monthly calendar with workload sidebar
        │   ├── DashboardPage.jsx     — Clickable stat/event/task/financial cards
        │   ├── LocationsPage.jsx     — Timezone field (27 timezone options)
        │   ├── AdminPage.jsx         — Create User + Import Users dialogs, People badge
        │   ├── KioskPage.jsx         — Guest registration, recent visitors memory
        │   └── CommsPage.jsx         — AI Assistant with live app context
        ├── context/
        │   ├── AuthContext.js
        │   └── WebSocketContext.js   — joinBoard / leaveBoard
        └── services/api.js
```

## Key DB Schema
- `members`, `users`, `families`, `children`
- `boards`: id, name, location_id, background, is_global
- `board_lists`: id, board_id, name, position, is_archived, archived_at
- `tasks`: id, title, board_id, list_id, due_date, assignees[], is_archived, attachments[], checklist[]
- `webauthn_credentials`: id, user_id, credential_id, public_key
- `locations`: id, name, currency, timezone, ...
- `push_subscriptions`: user_id, subscription (VAPID push subscriptions)

## 3rd Party Integrations
- Emergent LLM Key — Gemini AI Assistant (context-aware, live DB data)
- Resend (Emails) — requires user API key
- Object Storage (Documents, Card Attachments) — Emergent LLM Key
- WebAuthn (Passkeys), NFC (NDEFReader) — browser native
- pywebpush — VAPID push notifications for due-date reminders

## Test Credentials
- Admin: admin@5812uganda.org / Admin@5812
- Local: admin@5812global.org / Admin@1234

---

## CHANGELOG (What's Been Implemented)

### Session 1–2 (Previous forks)
- Full app scaffold, Auth (JWT, WebAuthn, Google OAuth), Unified People, Events, Check-ins, Financial, Communications (AI), Reports, PWA/offline, Document workflow, Badge printing (browser), NFC check-ins, Admin Profile Edit, Family/Children fix, Complete Trello-like Kanban (boards/lists/cards)

### Session 3 (2026-03-24 Fork A)
- TasksPage redesign: dark navy canvas, sidebar board nav
- Card memberships (multi-user staff assignment)
- Archive/restore cards & lists with panel
- Hard delete for cards & lists
- Trello JSON attachment import + card file uploads
- Real-time WebSocket sync (join_board/leave_board)
- Badge Printing via Web Bluetooth + ZPL code generation
- Iteration 14: 100% pass rate

### Session 3 (2026-03-24 Fork B)
- Dashboard stat/event/task/financial cards made clickable with navigation
- Timezone per location: 27 timezone options, persisted in DB
- Parent/Visitor guest users: /api/auth/visitor-register, guest PIN
- Kiosk visitor memory: localStorage recent visitors, quick check-in
- AI Assistant: live DB context filtered by RBAC
- Due-date push notification scheduler: hourly in server.py
- TasksPage split: KanbanCard, KanbanList, ArchivePanel, CardDetailDialog
- User Admin: Create New User + Import Users (CSV/JSON)
- Object storage: local file serve for card attachments
- Iteration 15: 100% backend, 95% frontend

### Session 3 (2026-03-24 Fork C — Current)
- **BUG FIX**: People page edit error — added missing `editMember` useState declaration
- **BUG FIX**: Confirmed Admin Import Users feature works (backend + frontend verified)
- **NEW**: Team Calendar view for Kanban — toggle Board/Calendar at bottom of sidebar
  - Monthly grid showing tasks with due dates color-coded by board/priority
  - Workload sidebar: assignee progress bars, overdue count
  - Filters: by board, by assignee
  - Today highlight, past-due coloring, unscheduled task badge
- **ENHANCED**: Due-date scheduler now sends push for same-day AND tomorrow tasks
- Iteration 16: 100%/100% (edit member + admin import fix)
- Iteration 17: 100%/100% (Team Calendar + all features verified)

---

## Prioritized Backlog

### P0 — None

### P1
- [ ] Wire object storage properly for production attachment uploads
- [ ] Replace native date input in card detail with shadcn DatePicker

### P2
- [ ] Verify kiosk recent-visitors section works end-to-end after check-in
- [ ] SMS notification integration via Twilio (user deprioritized)

### P3 — Future
- [ ] Board sharing / external guest access
- [ ] Recurring task cards
- [ ] Bulk card operations (multi-select, bulk archive/move)
- [ ] "Team Calendar" weekly/daily view modes
