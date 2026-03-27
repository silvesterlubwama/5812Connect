# 58:12 Global Connect Uganda CRM - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global Connect Uganda: campuses, members, events, check-ins, finances, sales, outreach, resources with deep RBAC.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC — System Admin > ED/Adviser > Director > Manager > Coordinator > Staff/Volunteer/Member
- **Integrations**: Resend (email), Gemini AI (Emergent LLM Key), Google OAuth (Emergent-managed)

## Completed Features

### Core
- [x] Auth, Dashboard, People/Members, Events, Calendar, Tasks (Kanban), Check-ins
- [x] Outreach, Communications, Resources, Access Control, Financial, Sales/Products
- [x] Attendance, Location management, Mobile-responsive, Campus reports + PDF

### Advanced
- [x] Admin toggle, Adviser role, Multi-location staff, Auto-titles
- [x] Global App Settings, Audit Trail bulk delete, Campus switcher

### Phase 3 — Sales & Outreach (2026-03-27)
- [x] Location-scoped products, store settings per location, sales import/export
- [x] Outreach sessions → calendar events, recurring programme events

### Phase 4 — Financial, Calendar, Access, Recurrence (2026-03-27)
- [x] Financial import/export (JSON), iCal import/export for all users
- [x] Guest pass QR, validation, extension, time bounds, allows_residents
- [x] Event recurrence: daily, weekly, biweekly, monthly, yearly, nth_week, nth_month + end date

### Phase 5 — Polish & UX (2026-03-27)
- [x] 5812 Global logo on all badges, passes, QR codes
- [x] Existing badge/staff badge reuse for events and guest passes
- [x] People UI location filter (dropdown that queries backend by location_id)
- [x] Outreach recurrence matching Events (daily, weekly, monthly, yearly, nth patterns)
- [x] All events deletable
- [x] Imported iCal events user-scoped (only visible to importer unless shared)
- [x] Event sharing endpoint (PUT /events/{id}/share)
- [x] Imported calendar events lighter gray styling, no solid background

### Phase 6 — 14 Major Enhancements (2026-03-27)
- [x] **Financial API Connections** - Admin can add/remove payment gateway integrations (Stripe, PayPal, Flutterwave, MTN MoMo, Airtel Money, QuickBooks, Xero)
- [x] **Auto-updating Reports** - Reports with real-time data refresh capability
- [x] **Webcal Subscription** - iCal feed export for calendar subscriptions
- [x] **Push Notifications** - Web push notification infrastructure (VAPID keys)
- [x] **Offline Mode/PWA** - Service worker foundation for offline capabilities
- [x] **Multi-language Support** - Added Luganda (lg) and Thai (th) translations
- [x] **Advanced Analytics Dashboard** - Deep insights with charts: trends, member growth, location breakdown, outreach impact
- [x] **Custom Report Builder** - Create/save custom reports with filters, schedules, auto-update
- [x] **Data Export to Excel** - XLSX export for reports
- [x] **Google OAuth Login** - Emergent-managed Google authentication
- [x] **Two-Factor Authentication (2FA)** - TOTP-based authenticator app support with QR code setup
- [x] **GDPR/Privacy Settings** - Data export, retention policies, consent management, anonymization
- [x] **Member Portal** - Self-service portal for members (existing PortalDashboard enhanced)
- [x] **Volunteer Scheduling** - Shift management, role-based scheduling, volunteer assignment
- [x] **Email Templates** - Reusable templates with variable substitution ({{name}}, {{date}}, etc.)

## Backend Routers (Modular)
- `/app/backend/routers/analytics.py` - Advanced analytics endpoints
- `/app/backend/routers/reports.py` - Report builder CRUD + Excel export
- `/app/backend/routers/notifications.py` - Push notification management
- `/app/backend/routers/scheduling.py` - Volunteer shift scheduling
- `/app/backend/routers/templates.py` - Email template management

## Frontend Pages (New)
- `/analytics` - AnalyticsPage.jsx - Advanced analytics dashboard with Recharts
- `/report-builder` - ReportBuilderPage.jsx - Custom report creation
- `/volunteer-scheduling` - VolunteerSchedulingPage.jsx - Shift management
- `/email-templates` - EmailTemplatesPage.jsx - Template CRUD with send functionality
- `/financial-apis` - FinancialApisPage.jsx - Payment gateway management
- `/gdpr` - GdprSettingsPage.jsx - Privacy and compliance settings

## Navigation Structure
- **People**: People
- **Ministry**: Events, Calendar, Tasks, Check-Ins, Outreach, Communications, Resources, Access Control
- **Finance**: Financial, Sales & Products
- **Analytics**: Attendance, Sales Analytics, Location Stats, Advanced Analytics, Reports & PDF, Report Builder, Campus Reports
- **Operations**: Volunteer Scheduling, Email Templates
- **Admin**: Staff Management, Campuses, Financial APIs, App Settings, Audit Trail, Privacy & GDPR, Settings

## Upcoming / Backlog
- [ ] AdminPage.jsx component splitting (1000+ lines)
- [ ] server.py modular router refactoring (remaining endpoints)

## Key API Endpoints (New)
- GET /api/analytics/overview - Dashboard analytics summary
- GET /api/analytics/trends - Monthly trends with charts data
- GET /api/analytics/location-breakdown - Stats per location
- GET /api/analytics/member-growth - Member growth over time
- GET /api/analytics/outreach-impact - Outreach program metrics
- POST /api/reports - Create custom report
- POST /api/reports/{id}/generate - Generate report data
- GET /api/reports/{id}/export/xlsx - Export to Excel
- GET /api/volunteer/shifts - List shifts
- POST /api/volunteer/shifts - Create shift
- POST /api/volunteer/shifts/{id}/assign - Assign volunteer
- GET /api/email-templates - List templates
- POST /api/email-templates/{id}/send - Send templated email
- GET /api/financial-apis - List API connections
- GET /api/gdpr/settings - GDPR configuration
- GET /api/gdpr/export-my-data - Export user's personal data
- POST /api/2fa/setup - Generate 2FA secret and QR
- POST /api/2fa/verify - Verify TOTP code
- GET /api/webcal/{user_id}/calendar.ics - Webcal subscription feed
- GET /api/i18n/{lang} - Get translations for language

## Test Reports
- Iterations 1-25: All passed
- Iteration 26: 100% (28/28 — sales/outreach)
- Iteration 27: 100% (20/20 — financial/calendar/access/recurrence)
- Iteration 28: 100% (19/19 — badges/people filter/outreach recurrence/imported events scoping/styling)
- Iteration 29: 100% (35/35 — 14 major enhancements: analytics, reports, scheduling, templates, financial APIs, GDPR, 2FA, i18n)
