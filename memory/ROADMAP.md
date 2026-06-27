# 58:12 Global Connect — Remaining Backlog

## COMPLETED (Iteration 78)
- [x] Finance RBAC: sub-location managers restricted to their data, finance dept sees campus
- [x] Finance categories management dialog (proper UI with add/delete)
- [x] Barcode generation endpoint (Code128 SVG per variant)
- [x] Sub-location dropdown on donation/expense entry forms
- [x] Admin People editor link from People page (Shield icon → /admin?user=id)
- [x] Sales kiosk auto-lock (5min inactivity) + fullscreen mode

## Technical Debt (Future)
- server.py modularization (900+ lines)
- MongoDB index optimization
- Bcrypt version pinning
- Persistent pytest test suite
- Route ordering automated tests

## Nice-to-Have (Future)
- Scheduled overdue task email reminders (needs cron)
- Offline QR scanning (cache members for kiosk)
- PWA service worker for wallet badges
- Multi-language translation files
- Mobile responsiveness audit
- Full barcode printing page (layout, bulk print button)
