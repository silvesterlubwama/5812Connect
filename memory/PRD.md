# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 59 - Feb 2026)
- [x] Error Boundary: wraps entire App + AppRoutes, prevents white screens, shows retry + dashboard buttons
- [x] Bulk Delete Safeguard: BulkDeleteConfirm dialog requires typing 'DELETE' before bulk operations proceed
- [x] Delete confirmations: added window.confirm to all previously unprotected delete operations
- [x] Unsaved Form Warning: useUnsavedWarning hook in UserEditDialog, warns on page navigation with dirty form

## Changes (Iteration 58)
- [x] Wallet badge shareable URL system (POST create, GET public, mobile page at /badge/:token)
- [x] Cascade deletion cleanup on all delete endpoints (members, families, guests, children, users)
- [x] Frontend dataEvents.js event bus for cross-component data refresh

## Previous (Iterations 49-57)
- All badge improvements, import fixes, photo upload, country outlines, venue CRUD, group types
- User directory, outreach features, recurrence, portal fix, kiosk lock, staff-guest linking

## Architecture
- **Error Boundary**: components/ErrorBoundary.jsx (class component)
- **Bulk Delete**: components/BulkDeleteConfirm.jsx (type-to-confirm dialog)
- **Unsaved Warning**: hooks/useUnsavedWarning.js (beforeunload + form dirty tracking)
- **Data Events**: services/dataEvents.js (cross-page refresh)
- **Wallet Badges**: wallet_badges collection, /badge/:token public route

## Test Reports: Iterations 49-59 all 100%

## Pending
- Action-driving dashboard widgets (overdue tasks, pending approvals, expiring passes)
- Email notifications for task assignments and check-ins
- Future: Wave H5 SDK, server.py modularization
