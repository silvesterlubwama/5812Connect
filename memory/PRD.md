# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badges, HR/payroll, sales portal, restricted access control, and PBX integration.

## Latest Changes (Iteration 71 - Feb 2026)
- [x] Resident assignment: batch add (member_ids array), resolves from members/children/guests, auto-issues access badge
- [x] Eligible residents: includes guests + search by name parameter
- [x] Public guest access request: no auth, creates guest profile, auto-issues temp badge on approval
- [x] Convert guest pass to resident: director+ converts temp pass to permanent residency
- [x] Kiosk access validation: POST /api/access/validate checks QR/NFC/fingerprint against resident/staff/guest access
- [x] Fingerprint database: CRUD at /api/access/fingerprints for WebAuthn credential storage

## Completed Feature Set (Iterations 49-71)
Multi-campus RBAC, Financial management (sub-location accounts, customer accounts), Dashboard actions, Email notifications, Import/export, NFC badges (read/write), Wallet badges, Profile photos + PDF, Cascade deletions, Error boundary, WebRTC calling, Chat/AI, Kiosk (QR/NFC/PIN/phone-last-4/fingerprint), Programme/Outreach, Venue management, Group types, HR/Payroll, Sales Portal, Customer Accounts, Route Guards, Restricted Access Control with fingerprint database.

## Test Reports: Iterations 49-71 all passed (71: 21/21 backend, 100% frontend)
