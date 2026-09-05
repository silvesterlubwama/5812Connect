# CHANGELOG

## iter 300 — 2026-02 — Portal audit sweep — verified & one dead-state cleanup

Walked every Portal page end-to-end and confirmed both the frontend and
backend endpoints are wired correctly.

**Endpoint parity (all 200 as admin)**
- `GET /api/portal/dashboard` · `GET/PUT /api/portal/profile`
- `POST /api/portal/my-wallet-badge` · `POST /api/portal/children/{id}/wallet-badge`
- `GET /api/portal/tasks` · `PUT /api/portal/tasks/{id}/status`
- `GET/POST /api/portal/expenses` · `POST /api/portal/cash-request`
- `GET /api/portal/events` · `POST /api/portal/events/{id}/rsvp`
- `GET /api/portal/checkins` · `GET /api/portal/documents` · `POST /api/portal/documents/upload`
- `GET /api/portal/sales`
- `GET/PUT /api/portal/family` · `POST /api/portal/family/children` · `POST /api/portal/family/guardians`
  (last three return 404 "No family found" when the caller has no family — expected).

**Frontend parity per page**
- `PortalProfile` — edits name/phone/address/emergency/DOB/gender (iter 299), scans receipts (iter 299), issues own Wallet badge (iter 298), submits weekly Mon–Sun timesheet (iter 298), requests PTO. All wired.
- `PortalFamily` — CRUD works: add child, edit child (`childrenApi.update`), issue child badge, add guardian, remove guardian, update family. All wired.
- `PortalDocuments` — list + upload + fulfil requests (`documentsApi` + `portalApi.documents`). Wired.
- `PortalEvents` — list + RSVP. Wired.
- `PortalExpenses` — list + create expense + cash-request dialog (`reason` field already correctly named). Wired.
- `PortalSales` — read-only sales history. Wired.
- `PortalTasks` — list + status transitions via `portalApi.updateTaskStatus`. Wired.

**Cleanup**
- Removed unused `tsForm` state from `PortalProfile.jsx` — leftover from
  the iter 298 refactor to the `tsWeek` Mon–Sun grid.

**No functional bugs found. No new features required — all Portal edits stick end-to-end.**

---
(prior entries iter 292–299 unchanged)
