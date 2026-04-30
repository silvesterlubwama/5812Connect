# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Completed Features (Iterations 49-77)
- Multi-campus RBAC with data isolation
- Financial management: donations, expenses, accounts, transfers, budgets, categories, assets (appreciation/depreciation)
- Dashboard action widgets
- Email notifications (task assignment, check-in, password reset)
- Import/export with CSV templates
- NFC badges (encrypted HMAC-SHA256, read-only lock)
- Wallet badges (shareable URL)
- Profile photos + PDF download
- Cascade deletions + orphan cleanup
- Error boundary + bulk delete safeguards
- WebRTC calling + chat (group management, message delete)
- Kiosk check-in (QR/NFC/PIN/phone-last-4/fingerprint)
- Programme/Outreach with recurrence
- Venue management + group types
- HR/Payroll (salaries, payslips, contracts, doc requests, auto-generate)
- Sales portal with customer accounts
- Restricted access control with fingerprint database
- Product variants with auto-barcodes
- Reports page with summary

## Architecture
See /app/ADMIN_GUIDE.md for full feature tree.
See /app/memory/ROADMAP.md for backlog.
See /app/memory/CHANGELOG.md for iteration history.

## Test Reports: Iterations 49-77 all passed
