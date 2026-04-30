# 58:12 Global Connect — Remaining Backlog

## From User Requests (Not Yet Implemented)

### Finance RBAC (Need-to-Know)
- Sub-location managers should ONLY see their sub-location's financial data
- Department managers only see their department's expenses
- Currently all finance-accessible staff can see all campus data
- Need: per-sublocation + per-department query filters on all financial endpoints

### Finance Categories Management Dialog
- Backend CRUD exists at /api/financial/categories
- Frontend currently uses prompt() for add — needs proper dialog
- Admin should be able to rename, reorder, set type (income/expense/both)

### Full Variant Barcode Printing UI
- Backend generates barcodes (country_code-productId-V01 format)
- Need: printable barcode labels page, bulk print, barcode scanner integration
- Include: barcode image generation (Code128/EAN format), print layout

### Finance Sub-Location Selection on Entry Forms
- Backend supports sublocation_id on donations/expenses
- Frontend donation/expense forms need sublocation dropdown (cascading from campus)

### Admin People Editor
- User asked to "bring back" the admin people editor
- Currently: Admin page has full UserEditDialog, People page has inline MemberForm
- Option: Add "Full Edit" link from People page to Admin page, or embed UserEditDialog in People page

### Sales Kiosk Dedicated Lock
- Sales portal has lock mode but user mentioned "dedicated devices"
- Need: auto-lock after inactivity timeout, fullscreen mode, prevent browser back/navigation

### Wave H5 SDK Upgrade
- Currently using iframe/popup fallback for Grandstream Wave
- Upgrade when native embedded SDK is released

### server.py Modularization
- 900+ line server.py needs splitting into focused modules
- Dashboard, seeding, public endpoints should be separate files

## Cosmetic / Polish

### Invalid Date on Reports
- FIXED in iteration 77 (rewrote ReportsPage)

### Barcode Printing for Variants
- Visual barcode rendering (Code128 SVG) on product detail/print pages

### Mobile Responsiveness Audit
- Several dialogs and tables may not render well on small screens
- Badge printing assumes desktop viewport

## Nice-to-Have Enhancements

### Scheduled Overdue Task Reminders
- email_helpers.notify_task_overdue exists but no cron/scheduler
- Need: background task runner (celery/APScheduler) for daily overdue check

### Offline QR Scanning
- html5-qrcode supports offline — cache member data for kiosk
- Sync when back online

### PWA Service Worker for Wallet Badge
- /badge/:token could work offline with service worker
- Cache the badge page for true wallet-like experience

### Background Check Integration Framework
- User requested internet background checks (arrest warrants, criminal records)
- Skipped per user instruction — framework placeholder could be added later
- Would need Checkr/GoodHire/Sterling API subscription

### Multi-Language Support
- I18nProvider exists but translations are minimal
- Need: full translation files for key languages (English, French, Swahili)

## Technical Debt

### Route Ordering Vigilance
- Known recurring issue: bulk/special routes must be BEFORE /{id} routes
- Documented but needs automated testing

### Test Coverage
- Backend: 77 iterations all passed but no persistent test suite
- Need: pytest test files at /app/backend/tests/ for regression
- Frontend: no unit tests — component tests with React Testing Library

### MongoDB Index Optimization
- No indexes beyond _id
- Need: compound indexes on frequently queried fields (location_id, status, email, etc.)

### Bcrypt Version Warning
- passlib + bcrypt version mismatch causes AttributeError warning
- Functional but should pin compatible versions
