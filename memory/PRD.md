# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badges, HR/payroll, sales portal, and PBX integration.

## Latest Changes (Iteration 68 - Feb 2026)
- [x] **Security Fix**: Google Auth new signups get pending status + pending_approval flag, auto-create guest record. Suspended users blocked (403).
- [x] **Guest/Pending Route Guard**: StaffRoute redirects Guest/pending users to /portal. Full app only accessible to staff+.
- [x] **Sales Portal**: /sales-portal with PIN+last name login, product grid, cart, sale completion, device lock (admin-password-only unlock)
- [x] **Portal Self-Service**: Badge display + PDF download on portal dashboard for all users
- [x] **Portal Bug Fixes**: Variable names corrected (t→c, ev→e in PortalDashboard)
- [x] **Kiosk Lock**: No exit points when locked (Setup/Logout/Exit hidden)

## Previous (Iterations 49-67)
Profile PDF, sub-location accounts, HR module, financial campus isolation, dashboard actions, email notifications, safety features, import fixes, badges, venue/group management.

## Architecture
- **Route Guards**: StaffRoute (redirects guests to portal), AdminRoute (admin-only pages)
- **Sales Portal**: Standalone page at /sales-portal with PIN+last name auth via /api/auth/sales-portal-login
- **Google Auth Security**: New users → Guest role, pending status, auto guest record

## Test Reports: Iterations 49-68 all passed (68: 17/17 backend, 100% frontend)
