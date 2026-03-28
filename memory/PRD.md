# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global serving USA (Ohio), Uganda, Kenya, Thailand, Haiti. Full-featured: members, events, check-ins, finances, sales, outreach, resources, RBAC, PBX calling, unified comms, public bookings with payments, self-service portal, kiosk check-in.

## Architecture
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (Async MongoDB)
- **Auth**: JWT RBAC with phone/email login, pending approval for new signups
- **Global Access**: Admin + System Admin + Executive Director
- **Campus Switcher**: Admin + ED + Adviser
- **Calling**: WebRTC + WebSocket + PBX (auto-attendant, call queues, forwarding)
- **Payments**: Card, MTN Mobile Money, Airtel Money, Venmo, Cash (with cutoff rules)

## All Completed Features

### Phase 1-10 (Core through Overhaul)
All previously completed features intact.

### Phase 11 - D+E Features
Adviser campus switcher, chat auto-detect, GDPR for all, venue offsite/non-bookable, extensions in profile, QR check-in, public calendar by country, outreach auto-events, auto-attendant, call queues, forwarding, outgoing rules.

### Phase 12 - Public Bookings, Payments, Kiosk, Policies (2026-03-27)
- [x] **Public Bookings Overhaul**: 58:12 mission hero section, country-based event filtering with auto-detection, event search, events grouped by type in columns, free vs paid badges, 1-year event limit
- [x] **Payment Flow**: Card, MTN Mobile Money, Airtel Money, Venmo, Cash methods. Cash blocked within 3 days of event. Cash/Venmo get 2-day or 7-day payment deadlines. Terms agreement required
- [x] **Mark-as-Paid**: Staff+ can mark bookings as paid with transaction reference (PUT /api/public/bookings/{id}/mark-paid)
- [x] **Unified Policies**: Privacy, Terms, Refund, Employee Onboarding, Data Retention, Cookie policies compliant with US, EU, Uganda, Kenya, Thailand, Haiti, Mexico laws
- [x] **Footer Redesign**: Staff login moved to footer, user portal login top-right, 5812-Global.org link, policy links
- [x] **Report Generation Fix**: Fixed db.check_ins -> db.checkins collection name
- [x] **New Signups as Members**: Registration defaults to role='Member' with status='pending' (approval required)
- [x] **Kiosk Enhancements**: Company logo, lock mode, quick signup during check-in, checkout button, QR/ID scan with success/fail sounds
- [x] **Portal Renamed**: Parent Portal -> User Portal (58:12 Connect)

## Test Reports
- Iterations 1-34: All passed
- Iteration 35: 100% (19/19 - Phase 12 public bookings, payments, kiosk, policies)

## MOCKED APIs
- Payment gateway processing (Stripe/MTN/Airtel/Venmo) - bookings created with pending status, no actual charges

## Remaining Backlog
- [ ] Connect real payment gateways (Stripe for cards, MTN/Airtel API for mobile money)
- [ ] Full WebRTC audio/video calling end-to-end testing
- [ ] Redis-backed presence for production scaling
- [ ] Further server.py extraction
