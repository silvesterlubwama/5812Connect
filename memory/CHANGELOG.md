# CHANGELOG

## iter 295 — 2026-02 — Digest widget · Mobile tabs on People/HR/Sales

**Director digest preview widget** — New `GET /api/tasks/director-digest-preview`
endpoint (`routers/tasks.py`) mirrors the `_fire_overdue_task_director_digest`
scheduler logic exactly (same scope rules, same sort) but returns JSON
without sending an email. Response includes `eligible`, `task_count`,
`tasks[]` (capped at 50), `scope` ('global' / 'campus'),
`already_sent_today`, and `date`. New `DirectorDigestWidget` component
renders on the Dashboard for director+ users; hides itself when
`eligible=false` or `task_count=0`. Copy switches between "This is what your
08:00 UTC email will contain" and "Emailed to you at 08:00 UTC today" based
on `already_sent_today`.

**Mobile tab strips — People, HR, Sales** — Same treatment as Finance
(iter 294). TabsList now `w-full flex overflow-x-auto no-scrollbar
md:inline-flex md:w-auto` — mobile scrolls horizontally, desktop keeps the
inline layout. HR keeps `md:flex-wrap` since it has the most tabs.

**Remaining overflow at 390×844** — Only a few individual header buttons on
People / HR / Sales still exceed the viewport by 1-5px. Not a blocker; can
be tightened later if the user prioritises them.

---

## iter 294 — 2026-02 — Bulk barcodes · Director digest · Mobile Finance
(previous, unchanged)

## iter 293 — 2026-02 — Review Queue UI · PDF FX · nested sublocations
(previous, unchanged)

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration
(previous, unchanged)
