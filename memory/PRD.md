# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, HR/payroll, and PBX integration.

## Latest Changes (Iteration 67 - Feb 2026)
- [x] User profile PDF download: GET /api/members/{id}/profile-pdf generates PDF with personal info, account details, NFC tags, documents (via weasyprint)
- [x] PDF button in UserEditDialog header
- [x] Financial sub-location accounts: GET /api/financial/accounts aggregates per sub-location within campus
- [x] New "Accounts" tab in FinancialPage with campus income/expenses/balance cards + sub-location table

## Completed Feature Set (Iterations 49-67)
Multi-campus RBAC, Financial management (with sub-location accounts), Dashboard actions, Email notifications, Import/export with templates, NFC badges (read/write), Wallet badges, Profile photos, Profile PDF download, Cascade deletions, Error boundary, Bulk delete safeguards, Unsaved form warnings, WebRTC calling, Chat/AI, Kiosk check-in (QR/NFC/PIN), Programme/Outreach, Venue management, Group types, HR/Payroll module (salaries, payslips, contracts, document requests), Sponsored children tracking.

## Test Reports: Iterations 49-67 all passed
