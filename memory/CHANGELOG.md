# CHANGELOG

## iter 299 — 2026-02 — Portal receipt scan · profile audit · badge PNG · manual-payslip verify

**Badge PNG / Print fix** — `WalletBadgePage` rewritten. Old copy told users
to "Add to Home Screen" which only saved the URL — the QR + photo weren't
actually captured on the phone. Now:
- **Save to Photos** button captures the whole styled badge card (photo + QR
  pixels + country outline + logo) to a PNG via `html2canvas` at 2× scale and
  triggers a download so mobile browsers drop it straight into the camera roll.
- **Print** button opens the OS print dialog; a `@media print` block hides
  the action bar and slate background so only the card prints.
- Auto-print via `?print=1` still works untouched.
- Added `html2canvas@1.4.1` to `frontend/package.json`.
- `data-testid`s: `badge-card`, `badge-download-png`, `badge-print`.

**Portal audit — name/DOB/phone/address/gender end-to-end** — Backend
`PUT /api/portal/profile` whitelist grown to include `date_of_birth`, `dob`,
`birthday`, `gender`, `emergency_phone`, `address_line2`, `city`, `country`;
`dob` / `birthday` alias to `date_of_birth`. `PortalProfile` form now
carries `date_of_birth` (`profile-dob-input`) + `gender`
(`profile-gender-input`). Verified end-to-end via curl:
`PUT /portal/profile {dob:'1985-04-12', gender:'male'}` → response persists
both fields on the `users` row (and mirrors to the linked `members` row).

**Portal Receipt Scan** — new card on `PortalProfile` with a mobile-camera
`Scan` button (`portal-scan-receipt-input`) that POSTs the image to
`/api/finance/receipts/scan`. The existing OCR pipeline drafts a JE that
lands in the Finance Review Queue for approval — no new backend work
required.

**Manual Payslip UI shortcut — already exists** — Verified `HRPage.jsx:392`
already exposes a `Manual Payslip` button (`data-testid="manual-payslip-btn"`)
that opens the manual-payslip dialog at line 734 and posts to the existing
`/api/hr/payslips/manual`. No change needed.

---
(prior entries iter 292–298 unchanged)
