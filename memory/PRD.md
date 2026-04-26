# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badges, HR/payroll, sales portal, customer accounts, and PBX integration.

## Latest Changes (Iteration 69 - Feb 2026)
- [x] Customer Accounts: CRUD at /api/customers with auto-guest linking (email/phone match)
- [x] Customer search by name/phone/email
- [x] Customer purchase history tracking (total_purchases, total_spent auto-updated on sale)
- [x] Sales linked to customers via customer_id on SaleCreate model
- [x] Sales portal customer lookup in cart section
- [x] customersApi frontend bindings

## Previous (Iteration 68)
- Security: Google Auth pending status, StaffRoute guard, guest portal restriction
- Sales Portal: PIN+last name login, product grid, cart, lock mode
- Portal: badge + PDF self-service

## Completed Feature Set (Iterations 49-69)
Multi-campus RBAC, Financial management (sub-location accounts, customer accounts), Dashboard actions, Email notifications, Import/export with templates, NFC badges (read/write), Wallet badges, Profile photos + PDF, Cascade deletions, Error boundary, Bulk delete safeguards, WebRTC calling, Chat/AI, Kiosk check-in (QR/NFC/PIN), Programme/Outreach, Venue management, Group types, HR/Payroll (salaries/payslips/contracts/docs), Sales Portal, Customer Accounts, Route Guards.

## Test Reports: Iterations 49-69 all passed (69: 17/17 backend, 100% frontend)
