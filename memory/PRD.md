# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 61 - Feb 2026)
- [x] Dashboard action-driving widgets: Overdue Tasks (red), Pending Approvals (amber), Expiring Passes (orange), Unassigned Tasks (blue)
- [x] GET /api/dashboard/action-items endpoint with campus filter support
- [x] Email notifications: notify_task_assigned (on task assignee change), notify_checkin (parent notified on child check-in), notify_task_overdue
- [x] email_helpers.py shared module using Resend API (graceful degradation if key not set)
- [x] Task update triggers email to newly assigned users
- [x] Parent check-in triggers email to parent with child names and event

## Previous (Iterations 49-60)
- Template downloads, safety features (ErrorBoundary, BulkDeleteConfirm, unsaved warnings)
- Wallet badges, cascade deletion, data events, venue/group CRUD
- Import fixes, badge improvements, photos, country outlines, user directory

## Architecture
- **Action Items**: /api/dashboard/action-items — overdue tasks, pending approvals, expiring passes, unassigned tasks
- **Email**: email_helpers.py — fire-and-forget via Resend (RESEND_API_KEY env var)
- **Error Boundary**: components/ErrorBoundary.jsx
- **Data Events**: services/dataEvents.js
- **Wallet Badges**: /badge/:token public route

## Test Reports: Iterations 49-61 all 100%

## Completed Feature Set
The application now includes: multi-campus RBAC, WebRTC calling, unified comms, NFC badges, kiosk check-in, financial management, programme/outreach tracking, import/export, profile photos, cascade deletions, action-driving dashboard, and email notifications.
