# 58:12 Connect — Administrator Guide

## What is 58:12 Connect?

**58:12 Connect** is a comprehensive multi-tenant CRM and operations platform built for **58:12 Global**, a Christ-centered nonprofit organization serving the most vulnerable across **USA (Ohio), Uganda, Kenya, Thailand, and Haiti**. Named after Isaiah 58:12 — *"Repairer of Broken Walls, Restorer of Streets with Dwellings"*.

The platform manages everything from member check-ins and event coordination to financial tracking, access control, and unified communications across all campuses.

---

## Quick Facts

| Item | Details |
|------|---------|
| **App Name** | 58:12 Connect |
| **Organization** | 58:12 Global |
| **Countries** | USA, Uganda, Kenya, Thailand, Haiti |
| **Main Campus** | 58:12 Global (Central) |
| **Tech Stack** | React + FastAPI + MongoDB |
| **Total API Endpoints** | 200+ across 31 backend routers |
| **Frontend Pages** | 49 pages + 58 components |
| **Authentication** | JWT + Google OAuth + 2FA (TOTP) |
| **Default Password** | `User@58:12` (for new accounts) |

---

## User Roles (Hierarchy)

| Role | Access Level |
|------|-------------|
| **System Admin** | Full cross-campus access to everything |
| **Executive Director** | Full cross-campus access + campus switcher |
| **Adviser** | Cross-campus visibility with campus switcher |
| **Director** | Their campus + sub-locations only |
| **Manager** | Their campus, financial access |
| **Coordinator** | Their campus, operational access |
| **Staff** | Their campus, basic operational access |
| **HR** | Their campus, people management |
| **Volunteer** | Limited access, task boards |
| **Member** | Portal access, events, profile |
| **Parent** | Portal access, children profiles |

**New signups** start as **Members** with **pending** status (requires admin approval).

---

## Navigation Structure

### Always Visible
- **Dashboard** — Overview stats, upcoming events, tasks, financial summary
- **My Portal** — Personal dashboard with tasks, expenses, events, documents
- **My Privacy** — GDPR data export, privacy settings

### Ministry
- **Outreach** — Program management, sessions, recurring outreach scheduling
- **Events** — Create/manage events, recurrence (daily/weekly/biweekly/monthly/bimonthly/quarterly/custom), check-ins, iCal export
- **Check-ins** — Attendance tracking, kiosk mode, QR/NFC scanning, visitor registration

### Operations
- **Boards** — Kanban-style project management (like Trello), assignees, attachments with inline preview, due dates, checklists, location-scoped, import from Trello
- **Resources** — Manage organizational resources by location
- **Calendar** — Visual calendar with year navigation, iCal sync subscription (webcal://), event editing
- **People** — Unified view: Members, Families, Children, Guests tabs with bulk select/edit/delete/export
- **Scheduling** — Volunteer shift management
- **Access Control** — Restricted space management, guest passes, resident management, door API connections (Kisi, Salto, Brivo, OpenPath, Unifi), shareable guest access links

### Communications
- **Wave** — Grandstream CloudUCM integration for enterprise calling, video meetings, and cross-campus chat. Wave Desktop add-in available for download
- **Internal Chat** — Real-time messaging with AI assistant (Gemini), announcements, message reactions, threads, typing indicators, read receipts
- **Call History** — WebRTC call logs

### Finance
- **Financial** — Donations, expenses with receipt scanning, balance sheets by campus, fund transfers with exchange rate conversion, cashflow charts, pending approvals
- **Marketplace** — Product catalog (internal POS + public online shop)

### Analytics
- **Attendance** — Check-in analytics and trends
- **Sales Analytics** — Revenue tracking
- **Location Stats** — Per-campus statistics
- **Advanced Analytics** — Cross-campus data analysis
- **Reports** — Generate custom reports with campus filtering
- **Report Builder** — Build custom reports from any data

### Admin (Admin role only)
- **Staff Management** — Create/edit/import users, bulk actions, badge printing (browser/Bluetooth/ZPL), extension assignment
- **Campuses** — Location hierarchy (campus → sub-location), venue management (bookable, offsite, restricted)
- **Financial APIs** — Payment gateway connections
- **Email Templates** — Customizable email templates
- **Settings** — Organization info, global settings, app preferences, venues
- **Audit Trail** — Activity logs with bulk management
- **Privacy & GDPR** — Data retention, anonymization, export

---

## Key Features in Detail

### Multi-Campus Data Isolation
- Each campus's data is isolated by default
- Sub-locations inherit visibility from parent campus
- **Campus Switcher** (Admin/ED/Adviser only) — persistent dropdown to filter all data across pages
- Directors see their campus only; Managers see their campus; Staff see their assigned location
- Financial data locked to user's campus (admins can switch)

### Check-in & Kiosk System
- **ID Check-in** — QR code scanning, national ID lookup
- **Visitor Flow** — Phone lookup → profile creation with ID scanning → badge generation
- **Under-18 Guests** — Up to 3 tagged to parent's check-in
- **Blocked Guests** — Admin can block guests from check-in (shows error + fail sound)
- **Restricted Area Alerts** — Unauthorized check-in sends notification to director + location manager
- **Kiosk Lock Mode** — Admin password required to unlock; restricts to scan-only mode
- **Quick Signup** — Collect basic info + issue temporary badge during check-in
- **Checkout** — Dedicated checkout button in kiosk
- **Badge Generation** — 58:12 Global logo, large first name, small last name, QR code

### Events & Calendar
- **Recurrence Options** — Daily, weekly, biweekly, monthly, bimonthly, quarterly, yearly, nth week/month, custom dates, custom weekly (multiple days)
- **Auto-Status** — Past events automatically marked as completed
- **Country-Based Filtering** — Events inherit country from location; public bookings filter by detected country
- **iCal Subscription** — `webcal://` live sync link for Google Calendar, Apple Calendar, Outlook
- **Year Navigation** — Browse calendar by year in addition to month
- **Edit from Calendar** — Click any event to open edit modal

### Boards (Kanban)
- **Trello-like** — Boards, lists, cards with drag-and-drop
- **Location Scoping** — Boards linked to campus/sub-location; restricted boards only visible to tagged members
- **Attachment Preview** — Images show inline thumbnail; PDFs show clickable preview
- **Bulk Actions** — Archive, move, delete, export multiple cards
- **Import from Trello** — Full board import with lists, cards, and attachments

### Communications
- **Wave Integration** — Grandstream CloudUCM with campus-based server selection, Wave Desktop add-in (downloadable ZIP)
- **Internal Chat** — Direct messages (auto-detect 1 user = DM, 2+ = group), AI assistant, announcements channel
- **AI Assistant** — Powered by Gemini, accesses live data, generates reports and summaries, suggests navigation
- **WebRTC Calling** — Internal audio/video calls, screen sharing, group calls (unlimited minutes, no PBX needed)
- **Presence** — Online status indicators (green/yellow/red dots)
- **Message Reactions** — 12 quick emoji reactions
- **Threads** — Reply in threads with thread panel

### Financial Management
- **Donations** — Track by type (tithe, offering, general, etc.) with location filtering
- **Expenses** — Track with receipt URL attachment, category breakdown
- **Balance Sheet** — Income vs expenses with type/category breakdown, campus-filtered
- **Fund Transfers** — Cross-campus with exchange rate input for international transfers
- **Receipt Scanning** — Attach receipt URL to any expense
- **Marketplace** — Internal POS + public online shop with cart and checkout

### Public-Facing Pages (No Login Required)
- **Marketplace** (`/marketplace` or `/public-bookings`) — Events, Shop, Book Space, My Orders
  - Events grouped by type with search, type filter, date range, country filter
  - Payment methods: Card, MTN Mobile Money, Airtel Money, Venmo, Cash (with deadline rules)
  - Cash blocked within 3 days of event
- **Guest Access Links** — Shareable URLs for restricted space access requests
- **Policies** — Privacy, Terms, Refund, Employee Onboarding, Data Retention, Cookie policies (US/EU/Uganda/Kenya/Thailand/Haiti/Mexico compliant)

### Security & Access Control
- **JWT Authentication** with token stored in sessionStorage (cleared on tab close)
- **Google OAuth** via Emergent-managed integration
- **Two-Factor Authentication (2FA)** — TOTP with QR code setup (Google Authenticator, Authy)
- **Role-Based Access Control (RBAC)** — 11 role levels with granular feature visibility
- **DOMPurify** sanitization on all HTML rendering
- **Door API Connections** — Kisi, Salto, Brivo, OpenPath, Unifi Access integration
- **Guest Blocking** — Admin can block specific guests from check-in

### Bulk Operations (All Data Types)
- **Select All** + individual checkboxes on: Members, Children, Families, Guests, Events, Tasks, Products, Resources, Outreach, Check-ins, Donations
- **Bulk Edit** — Change status, role, group, location, family for multiple items
- **Bulk Delete** — With confirmation dialog
- **Export CSV** — Download selected items as CSV file

### Import/Export
- **CSV/JSON Import** — Members, staff, children (with auto-parent/family creation and deduplication)
- **Country Selection** — Choose country during all imports
- **Trello Import** — Full board import
- **iCal Import/Export** — Calendar events
- **Data Export** — GDPR compliant personal data export

### Document Management
- **Upload** — National ID, passport, driver's license, birth certificate, and more
- **Expiry Tracking** — Already-uploaded valid documents hidden from upload options
- **ID Scanning** — QR/camera scanning for faster check-in and profile population
- **Document Requests** — Admin can request specific documents from members

---

## Technical Architecture

### Backend
- **FastAPI** (Python) — 31 router modules, 200+ endpoints
- **MongoDB** (Motor async driver) — Document-based storage
- **WebSocket** — Real-time chat, call signaling, presence
- **SIP.js** — Optional PBX integration (dormant until configured)

### Frontend
- **React 18** with Create React App
- **Tailwind CSS** + **Shadcn/UI** component library
- **WebRTC** — Peer-to-peer audio/video calling
- **DOMPurify** — XSS protection
- **JSZip** — Wave add-in download

### Integrations
- **Gemini AI** (via Emergent LLM Key) — AI assistant
- **Resend** — Email delivery
- **Google OAuth** — Managed via Emergent
- **Grandstream Wave** — CloudUCM calling/chat
- **Access Control APIs** — Kisi, Salto, Brivo, OpenPath, Unifi

---

## First-Time Admin Setup Checklist

1. **Login** — Use admin credentials (check with your IT team)
2. **Configure Campuses** — Go to Admin → Campuses. Set country on each location
3. **Set Up Staff** — Admin → Staff Management → New User. Assign role, location, extension
4. **Configure Wave** — Comms → Wave → Servers → Add your Grandstream CloudUCM URL per campus
5. **Set Wave Credentials** — Edit each staff member → Account → Wave/PBX section → Set extension + password
6. **Configure Financial APIs** — Admin → Financial APIs → Add payment gateways
7. **Set Up Access Control** — Operations → Access Control → Door APIs → Connect door systems
8. **Review Settings** — Admin → Settings → Organization info, currency, timezone
9. **Enable 2FA** — Settings → Security → Enable Two-Factor Authentication
10. **Create Events** — Ministry → Events → Schedule your first event with recurrence

---

## Support & Links

- **58:12 Global Website**: [5812-global.org](https://5812-global.org)
- **Wave Add-in Download**: Available on the Wave page within the app
- **Staff Login**: Footer of the public marketplace page
- **User Portal**: Top-right corner of the public marketplace page
- **Office Phone**: 330-521-1948

---

*58:12 Connect — Bringing hope and healing through technology.*
*"Your people will rebuild the ancient ruins and will raise up the age-old foundations." — Isaiah 58:12*
