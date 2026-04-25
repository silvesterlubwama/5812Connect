# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 60 - Feb 2026)
- [x] Template download buttons in Import dropdown (Children, Staff, Guests templates)
- [x] Template download links inside each import dialog (Members, Children & Parents, Staff)
- [x] Templates include all fields: campus, parent names/phones, location_id, etc.

## Previous (Iteration 59)
- Error Boundary, BulkDeleteConfirm, delete confirmations, unsaved form warnings

## Previous (Iteration 58)
- Wallet badge system, cascade deletion, frontend data events

## Previous (Iterations 49-57)
- Venue CRUD, group types, import fixes, badges, photos, parent search, country outlines, user directory, recurrence, portal, kiosk lock, safety features

## Architecture
- **Templates**: GET /api/import/template/{children|staff|guests} — CSV StreamingResponse
- **Error Boundary**: components/ErrorBoundary.jsx (wraps App + AppRoutes)
- **Bulk Delete**: components/BulkDeleteConfirm.jsx (type-to-confirm)
- **Wallet Badges**: wallet_badges collection, /badge/:token public route
- **Data Events**: services/dataEvents.js (cross-page refresh)

## Test Reports: Iterations 49-60 all 100%

## Pending
- Action-driving dashboard widgets
- Email notifications for assignments/check-ins
- Future: Wave H5 SDK, server.py modularization
