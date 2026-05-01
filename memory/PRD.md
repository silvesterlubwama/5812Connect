# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global — child welfare, campus ops, HR/payroll, comms, access control, financial management, sales portal.

## Completed Features (Iterations 49-79)
All features documented in /app/ADMIN_GUIDE.md and /app/memory/CHANGELOG.md

## CRITICAL BUGS FOR NEXT SESSION (Priority Order)

### Bug 1: Tasks showing all users globally (P0)
- Task assignment dropdown shows ALL users including non-staff and other campuses
- Fix: TasksPage uses `adminApi.userDirectory()` which returns ALL users
- Need: Filter by active campus + staff roles only in task assignment
- Files: `/app/frontend/src/pages/TasksPage.jsx` (line 71 fetchBoards), `/app/frontend/src/pages/kanban/CardDetailDialog.jsx` (assignee select)

### Bug 2: Chat showing non-existent users + not delivering (P0)
- Chat conversations reference deleted/non-existent user IDs
- Messages not reaching actual users
- Need: Run orphan cleanup on conversations, fix WebSocket message delivery
- Files: `/app/backend/routers/chat.py`, `/app/backend/routers/websocket.py`, `/app/frontend/src/pages/CommsPage.jsx`

### Bug 3: Campus switcher broken for multi-campus users (P0)
- Users with multiple `location_ids` can't switch between their campuses
- Need: Check Layout.jsx campus switcher logic for multi-campus user handling
- Files: `/app/frontend/src/components/Layout.jsx` (lines 295-310), `/app/backend/deps.py`

### Bug 4: Restricted locations not filtering (P0)
- Restricted location data visible to everyone instead of only campus/sublocation staff
- Need: Enforce location-level access check on restricted sub-location endpoints
- Files: `/app/backend/routers/access.py`, `/app/backend/deps.py`

### Bug 5: Tasks due dates not on main Calendar (P1)
- Calendar page only shows events, not task due dates
- Need: Fetch tasks with due_date and render on CalendarPage
- Files: `/app/frontend/src/pages/CalendarPage.jsx`

### Bug 6: Non-admins can assign admin roles (P1)
- The System Admin toggle should only be visible to existing admins
- Files: `/app/frontend/src/pages/UnifiedPeoplePage.jsx` (MemberForm admin toggle)

### Bug 7: Shift scheduler showing wrong staff/locations (P1)
- Scheduler shows non-location staff and all locations
- Should scope to current campus and auto-set time from event
- Files: Check shift/scheduler pages and endpoints

## Architecture
See /app/ADMIN_GUIDE.md for full feature tree.
See /app/memory/ROADMAP.md for future backlog.
See /app/memory/CHANGELOG.md for iteration history (49-79).

## Test Reports: Iterations 49-79 all passed

## Credentials
See /app/memory/test_credentials.md
