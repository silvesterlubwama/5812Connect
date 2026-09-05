# CHANGELOG

## iter 296 — 2026-02 — Finance/AP/HR/access MongoDB indexes + bcrypt pin verify

**MongoDB hot-path indexes** — Every collection introduced/heavily used since
iter 285 (finance ledger, AP, HR, guest passes, director digest) was still
running on a single `_id_` index. `_ensure_indexes()` in `server.py` now
creates 40+ additional indexes on:
- `finance_journal_entries` — id, `(location_id, reversed, date)`,
  `(source, reference)`, `lines.account_id`, `date`, plus a partial-unique
  `idempotency_key` index scoped to `reversed=false` so replays after
  reversal remain safe.
- `finance_chart_of_accounts` — `id`, `code` (unique), `(type, active)`.
- `bank_accounts`, `vendors`, `bills`, `bank_transactions`,
  `recurring_entries`, `reconciliation_rules`.
- `task_director_digests` — `(user_id, date)` unique for once-per-day
  idempotency; 90-day TTL on `date`.
- `payslips`, `hr_employees`, `hr_contracts`.
- `guest_passes`, `guest_access_requests`, `checkpoint_events`.
- `kanban_boards` (alias collection).

**Bcrypt pinning — verified** — `bcrypt==3.2.2` + `passlib==1.7.4` already
locked to exact versions in `requirements.txt`; installed versions match.
Login end-to-end validated after the index rollout.

**Header-button "overflow" on People / HR / Sales — false positive** — The
buttons flagged in the previous audit are `TabsTrigger` elements inside the
horizontally-scrolling `TabsList` that iter 295 introduced. They are
accessible via scroll (visually and functionally correct); no fix needed.

**Verification**
- New pytest `tests/test_iter296_indexes.py`: 21 parametrised assertions
  covering every index plus the partial-unique + TTL guards.
- Bank/finance migration regression pytest re-run and still green.
- Curl smoke: `/api/finance/journal`, `/api/finance/chart-of-accounts`,
  `/api/bank/{accounts,bills,vendors}`, `/api/tasks/director-digest-preview`,
  `/api/health` — all 200.

---

## iter 295 — 2026-02 — Digest widget · Mobile tabs on People/HR/Sales
(previous, unchanged)

## iter 294 — 2026-02 — Bulk barcodes · Director digest · Mobile Finance
(previous, unchanged)

## iter 293 — 2026-02 — Review Queue UI · PDF FX · nested sublocations
(previous, unchanged)

## iter 292 — 2026-02 — Accounting-shim retirement / bank.py migration
(previous, unchanged)
