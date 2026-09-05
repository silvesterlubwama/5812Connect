# CHANGELOG

## iter 297 — 2026-02 — PWA offline data · Wallet cache · Digest Snooze

**PWA offline data cache** — `sw.js` bumped to `5812-crm-v4` and grew a
third named cache `5812-offline-data-v1`. New `isOfflineDataRequest()`
allow-list covers `/api/auth/me`, `/api/dashboard/stats`, `/api/locations`,
`/api/tasks`, `/api/events*`, `/api/access/checkpoints`, and the
director-digest-preview — all served stale-while-revalidate so today's
roster + user dashboard render immediately with zero signal. On login a
new `prefetch-offline-set` message tells the SW to preload the entire
bundle (auth token forwarded so the SW can authenticate the preload).

**Wallet pass cache on login** — The same offline-prefetch hook also
preloads the current user's `/api/members/<id>/qr-code` and
`/profile-photo`, so their badge scans at the checkpoint even when the
signal is out. Existing per-badge `prefetch-wallet-pass` from
`WalletBadgePage` still works and now piggybacks on the same cache.

**Digest Snooze** — `DirectorDigestWidget` rows gained a small
snooze icon (`MoonStar`, `data-testid="digest-snooze-<id>"`). One click
POSTs to the existing `/api/tasks/<id>/snooze` with `days=1` — the task
drops out of tomorrow's digest. Optimistic UI + background reload keep
the widget count in sync. Directors are already in the endpoint's
`privileged` role set (`routers/tasks.py:373-375`), so no backend changes
needed.

**Verification**
- Curl end-to-end: seeded overdue task → digest count=1 → snooze POST →
  digest count=0 → cleanup. All 200.
- Testing agent iter 230: full regression pass.

---

## iter 296 — 2026-02 — Finance/AP/HR/access MongoDB indexes + bcrypt pin verify
(previous, unchanged)

## iter 295 — 2026-02 — Digest widget · Mobile tabs on People/HR/Sales
(previous, unchanged)

## iter 294 — 2026-02 — Bulk barcodes · Director digest · Mobile Finance
(previous, unchanged)

## iter 293 — 2026-02 — Review Queue UI · PDF FX · nested sublocations
(previous, unchanged)

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration
(previous, unchanged)
