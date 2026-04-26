# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, HR/payroll, and PBX integration.

## Latest Changes (Iteration 66 - Feb 2026)
- [x] Sale deletion restores product stock via $inc
- [x] Finance nav/dashboard hidden on "All Locations" 
- [x] Campus switcher: non-admin directors see sub-locations within their campus
- [x] Resident assignment: searchable input with members + children results
- [x] Residency toggle (allows_residents) on sub-locations
- [x] Sponsored children tracking (GET /api/hr/sponsored-children)
- [x] **Full HR Module**: Salaries (CRUD + line items), Payslips (generate + approve), Contract Templates (CRUD + variable replacement), Contract Issuing (email notification), Document Requests (email), Per-campus HR Settings (hr_enabled toggle)
- [x] HRPage with 4 tabs: Salaries, Payslips, Contracts, Documents

## Architecture
- **HR Module**: /api/hr/ with require_hr (HR role, finance dept, or director+)
- **HR Settings**: Per-campus via hr_settings collection (hr_enabled, pay_frequency, currency, pay_day)
- **Payslips**: Generated from active salary records, calculates allowances/deductions, approve workflow
- **Contracts**: Template variables ({{staff_name}}, {{role}}, etc.), issue with email notification

## Test Reports: Iterations 49-66 all passed (Iteration 66: 22/22 backend, 100% frontend)

## Completed Feature Set
Multi-campus RBAC, Financial management, Dashboard actions, Email notifications, Import/export, NFC badges, Wallet badges, Profile photos, Cascade deletions, Error boundary, WebRTC calling, Chat/AI, Kiosk check-in, Programme/Outreach, Venue management, Group types, HR/Payroll module.
