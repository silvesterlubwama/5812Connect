# 58:12 Global Connect — Complete Application Documentation

## Purpose

58:12 Global Connect is a comprehensive multi-campus management platform built for 58:12 Global, a faith-based non-profit organization operating across multiple countries (Uganda, Kenya, Haiti, Thailand, USA). The platform unifies child welfare tracking, staff management, campus operations, communications, financial management, access control, and HR/payroll into a single integrated system.

The name "58:12" references Isaiah 58:12 — "Your people will rebuild ancient ruins and will raise up the age-old foundations; you will be called Repairer of Broken Walls, Restorer of Streets with Dwellings."

---

## Core Architecture

- **Frontend**: React (CRA) + Shadcn/UI + Tailwind CSS
- **Backend**: FastAPI (Python) with 500+ API endpoints
- **Database**: MongoDB (Motor async driver)
- **Real-time**: WebSocket for chat, presence, notifications
- **Calling**: WebRTC peer-to-peer (optional SIP/PBX integration)
- **Storage**: Object storage with local fallback
- **Auth**: JWT + bcrypt + Google OAuth + 2FA (TOTP)
- **Email**: Resend API

---

## Feature Tree

### 1. Multi-Campus Management
```
Campuses & Locations
├── Campus hierarchy (Main → Campus → Sub-location)
├── Country code (ISO) + timezone per campus
├── Feature toggles per campus (Financial, Marketplace, HR)
├── Venue management (internal + external venues)
├── Admin-configurable group types
├── Campus switcher in navigation
│   ├── Admins see "All Locations" + all campuses
│   ├── Directors see their campus + sub-locations
│   └── Staff locked to their assigned campus
└── Data isolation (RBAC-enforced per campus)
```

### 2. People Management
```
Staff & Members
├── User profiles (name, email, phone, ID number, photo, departments)
├── Role-Based Access Control (System Admin → Admin → Director → Manager → Coordinator → Staff → Volunteer)
├── Profile photo upload (object storage + local fallback)
├── Profile PDF download (auto-generated with all info + documents)
├── NFC tag management (add/remove/write tags)
├── Badge issuance (QR code, country watermark, NFC symbol)
├── Wallet badge (shareable URL at /badge/:token)
├── Bulk operations (select all, CSV export, multi-edit, bulk delete with type-to-confirm)
├── Template CSV downloads for imports
└── Staff auto-marked as guest for their campus

Children
├── Profiles (name, DOB, gender, class/group, school, medical notes, allergies)
├── Photo upload
├── Parent linking (typed search across staff + guests)
├── Sponsor tracking (sponsor first name, staff-only visibility)
├── Residency at restricted locations
├── Badge issuance (NFC enabled, parents + campus contact on badge)
│   ├── Children at restricted locations get badges
│   ├── Children of staff with access get badges
│   └── Sponsored children get badges
└── Import with auto-parent + campus resolution

Families
├── Family grouping with primary contact
├── Children linked to families
├── Guardians management
└── Bulk operations

Guests & Parents
├── Guest profiles (name, phone, email, purpose)
├── Parent profiles linked to children
├── Guest editing dialog
├── Staff-guest profile linking (user_id bidirectional)
├── Customer account linking
├── Type-ahead search
└── Individual + bulk delete
```

### 3. Access Control & Restricted Locations
```
Restricted Access
├── Sub-location residency toggle (allows_residents)
├── Resident assignment (batch, members + children + guests)
├── Auto-badge issuance for new residents
├── Kiosk access validation (QR, NFC, fingerprint)
├── Public guest access request (no auth link)
│   ├── Auto-creates guest profile
│   ├── Pending approval or auto-approved
│   └── Temporary access badge (7-day default)
├── Convert guest pass to permanent residency (director+)
├── Fingerprint database (WebAuthn credential CRUD)
├── NFC encrypted tags (HMAC-SHA256 signed, read-only locked)
└── Access validation endpoint (checks resident/staff/guest passes)
```

### 4. Check-In System
```
Kiosk Mode
├── Staff login (email/password)
├── Check-in methods
│   ├── PIN check-in
│   ├── Phone last-4 digits check-in
│   ├── QR code scan (html5-qrcode camera)
│   ├── NFC tag scan
│   ├── Biometric/fingerprint
│   └── ID/email lookup
├── Parent check-in (lookup by phone/email, select children)
├── Visitor quick signup
├── Device lock mode (admin password only to unlock, no exit points)
├── Peripheral detection (camera, NFC, biometric)
├── 2FA support (TOTP)
└── Google Auth support

Check-In Records
├── Event-based check-in/out
├── PIN + phone-last-4 fallback
├── Parent email notification on child check-in
└── Daily stats (check-ins, visitors, scans)
```

### 5. Communications (Unified Comms)
```
Chat System
├── Direct messages (1:1 between staff)
├── Group conversations (multi-participant)
│   ├── Create group with name
│   ├── Add/remove members (system messages)
│   └── Edit group dialog
├── Message features
│   ├── Reply to messages
│   ├── Emoji reactions
│   ├── Thread conversations
│   ├── Read receipts (double-check marks)
│   ├── Typing indicators
│   ├── Delete message (own, before read only)
│   └── WebSocket real-time delivery
├── Conversation management
│   ├── Hide/delete conversation (user-side only)
│   ├── Search conversations
│   └── Presence indicators (online/away/busy/offline)
├── Announcements (no-reply channel)
├── AI Assistant (Gemini-powered)
└── Offline message queue with REST fallback

Calling (WebRTC)
├── Voice calls (peer-to-peer)
├── Video calls
├── Screen sharing
├── Group calls
├── Call recording toggle
├── Call hold/transfer
├── Optional PBX integration (SIP.js, Wave CloudUCM)
└── Dialer with staff contacts
```

### 6. Events & Calendar
```
Events
├── Event CRUD with types (service, meeting, outreach, etc.)
├── Recurrence patterns
│   ├── Daily, Weekly, Bi-weekly
│   ├── Monthly, Bi-monthly, Quarterly
│   ├── Yearly, Nth weekday of month
│   └── Custom interval
├── Venue selection (campus + external venues)
├── Location/country auto-resolution
├── Public events booking page
├── WebCal subscription
├── Check-in integration
└── Bulk operations + CSV export

Calendar
├── Month/week/day views
├── Event editing from calendar
├── Recurring event visualization
└── Campus-filtered events
```

### 7. Task Management (Kanban)
```
Boards & Tasks
├── Kanban boards with lists
├── Task cards (title, description, assignees, due date, labels, checklists)
├── Drag-and-drop reordering
├── Trello board import (full JSON with attachments)
├── Board sharing (public share links)
├── Email notification on task assignment
├── User directory for assignee resolution (cross-campus)
├── Task attachments
└── Real-time updates via WebSocket
```

### 8. Programmes & Outreach
```
Programmes
├── Programme CRUD with categories
├── Campus/location + venue selectors
├── Session tracking
├── Recurring outreach events
│   ├── All recurrence patterns (bi-monthly, quarterly)
│   └── Schedule configuration
├── Target populations
└── Category management

Outreach Sessions
├── Session CRUD
├── Attendance tracking
└── Impact reporting
```

### 9. Financial Management
```
Finances (campus-dependent)
├── Donations tracking (donor, amount, date, location)
├── Expenses tracking (with approval workflow)
│   ├── Submit → Pending → Approved/Rejected
│   └── Receipt attachment
├── Sales & Products (marketplace)
│   ├── Product CRUD with stock management
│   ├── Sale creation (cart system)
│   ├── Sale deletion restores stock
│   └── Customer account linking
├── Sub-location accounts (unified at campus level)
│   ├── Per-location income/expenses/balance
│   └── Campus-level totals
├── Balance sheet
├── Asset tracking (depreciation)
├── Cashflow charts (monthly, campus-filtered)
├── Fund distribution between locations
├── Financial APIs configuration
└── Hidden on "All Locations" (requires campus context)

Customer Accounts
├── Customer CRUD with auto-guest linking
├── Purchase history tracking
├── Total purchases + total spent (auto-updated)
├── Search by name/phone/email
└── Sales portal integration
```

### 10. HR & Payroll
```
HR Module (per-campus, director+ access)
├── HR Settings per campus (enabled toggle, pay frequency, currency, pay day)
├── Salary Management
│   ├── Staff salary records
│   ├── Line items (allowances + deductions, fixed or percentage)
│   └── Currency + pay frequency
├── Payslips
│   ├── Generate for pay period
│   ├── Auto-calculate gross/net from line items
│   └── Approve workflow (draft → approved)
├── Contract Templates
│   ├── Editable templates with {{variables}}
│   ├── Variable replacement (staff_name, role, salary, etc.)
│   └── Issue to staff with email notification
├── Document Requests
│   ├── Request resume, ID, passport, tax ID, etc.
│   └── Email notification to staff
└── Sponsored Children Tracking (count per campus)
```

### 11. Sales Portal
```
Sales Portal (/sales-portal)
├── PIN + last name authentication
├── Product grid with search
├── Cart system (add, quantity, remove)
├── Customer lookup (search by name/phone)
├── Sale completion with customer linking
├── Product management (add products)
├── Device lock mode (admin password only to unlock)
└── Standalone page (no main app auth required)
```

### 12. Badges & NFC
```
Badge System
├── UnifiedBadge component (dark bg default, white for kiosk)
├── Badge types: Staff, Director, Volunteer, Guest, Parent, Child, Member
├── Features on badge
│   ├── Real country map outline (world-map-country-shapes, 200+ countries)
│   ├── QR code
│   ├── NFC symbol (staff + children)
│   ├── Profile photo
│   ├── Parent names + phones (child badges)
│   ├── Campus name + contact phone (child badges)
│   └── Footer: ID, www.5812-Global.org, 58:12 GLOBAL - year
├── PrintableBadges (StaffBadge, ParentBadge, ChildTag)
├── Wallet badge (shareable URL, mobile-optimized page)
├── Print / Download PNG / Add to Wallet actions
├── NFC tag writing (director+ only)
│   ├── HMAC-SHA256 encrypted payload
│   ├── Read-only lock after write (ndef.makeReadOnly)
│   └── Verification endpoint (/api/nfc/verify)
└── Write NFC button on both staff and child badges
```

### 13. Portal (Self-Service)
```
Staff/Guest Portal (/portal)
├── Dashboard with stats (tasks, expenses, events, messages)
├── Badge display (UnifiedBadge)
├── Profile PDF download
├── Tasks management
├── Expenses submission
├── Events viewing
├── Chat access
└── Route guard (guests/pending users redirected here from main app)
```

### 14. Admin & Settings
```
Administration
├── User management (CRUD, bulk operations)
├── Password reset (auto-activates pending users, shows password if email fails)
├── User edit dialog (5 tabs: Profile, Account, Flags, NFC Tags, Documents)
├── Campus settings (locations, venues, group types, timezones)
├── Audit trail
├── GDPR/Privacy settings
├── Email templates
├── Orphan cleanup (removes breadcrumbs of deleted profiles)
└── Analytics & reporting

Settings
├── Group types (admin-configurable)
├── HR settings per campus
├── Access control API connections (Kisi, Salto, etc.)
├── Wave CloudUCM integration
└── Financial APIs
```

### 15. Safety & Reliability
```
Safety Features
├── Error boundary (prevents white screens, retry + dashboard buttons)
├── Bulk delete safeguard (type "DELETE" to confirm)
├── Delete confirmations on all destructive actions
├── Unsaved form warning (beforeunload)
├── Cascade deletion (removes references across all collections)
├── Data events bus (cross-page refresh after mutations)
├── XSS prevention (DOMPurify)
├── Secure storage (sessionStorage, not localStorage)
└── Route ordering (static before dynamic to prevent conflicts)
```

---

## Data Flow

```
User Action → React Frontend → API Call (axios + auth interceptor)
  → FastAPI Backend → MongoDB (Motor async)
  → Response → React state update → UI re-render

Real-time: WebSocket (chat, presence, typing, board updates)
  → WebSocketContext → Component listeners

Deletion: API delete → Cascade cleanup → dataEvents.emit()
  → Listening pages auto-refresh
```

## Security Model

- **Authentication**: JWT (24h expiry) + bcrypt password hashing
- **Google OAuth**: Emergent-managed, new users get Guest/pending status
- **2FA**: TOTP (Google Authenticator compatible)
- **Authorization**: Role hierarchy (10 levels) + campus isolation
- **NFC**: HMAC-SHA256 signed payloads + permanent read-only lock
- **Storage**: secureStorage.js (sessionStorage, not localStorage)
- **XSS**: DOMPurify on all user-generated HTML

## Test History

Iterations 49-74: All passed (100% backend, 100% frontend)
Total endpoints: 500+
Total frontend lines: 22,000+
Total backend lines: 13,000+
