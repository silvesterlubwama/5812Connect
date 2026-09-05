"""MongoDB hot-path index setup.

Extracted from server.py in iter302. `_ensure_indexes()` is idempotent —
safe to call on every startup. Behaviour is byte-for-byte the same as the
original in-server implementation; only its module home changed.
"""
from deps import db, logger


async def _ensure_indexes():
    """Idempotent index creation. Runs on every startup. Safe to call repeatedly."""
    try:
        # Users: lookups by email, id, role, location, status
        await db.users.create_index("email", unique=True)
        await db.users.create_index("id", unique=True)
        await db.users.create_index([("role", 1), ("status", 1)])
        await db.users.create_index([("location_id", 1), ("status", 1)])
        await db.users.create_index("location_ids")
        # Members
        await db.members.create_index("id", unique=True)
        await db.members.create_index("email")
        await db.members.create_index("pin")
        await db.members.create_index([("location_id", 1), ("status", 1)])
        await db.members.create_index("user_id")
        await db.members.create_index("date_of_birth")
        # Events — date-range queries are hot
        await db.events.create_index("id", unique=True)
        await db.events.create_index([("date", 1), ("status", 1)])
        await db.events.create_index([("location_id", 1), ("date", 1)])
        # Tasks / Boards
        await db.tasks.create_index("id", unique=True)
        await db.tasks.create_index([("board_id", 1), ("list_id", 1), ("position", 1)])
        await db.tasks.create_index([("assignees", 1), ("due_date", 1)])
        await db.tasks.create_index([("due_date", 1), ("is_archived", 1), ("status", 1)])
        await db.boards.create_index("id", unique=True)
        await db.boards.create_index([("location_id", 1), ("is_global", 1)])
        # Check-ins
        await db.checkins.create_index("id", unique=True)
        await db.checkins.create_index([("event_id", 1), ("check_in_time", -1)])
        await db.checkins.create_index([("date", 1), ("location_id", 1)])
        # Chat
        await db.chat_messages.create_index("conversation_id")
        await db.chat_messages.create_index([("conversation_id", 1), ("created_at", -1)])
        await db.chat_messages.create_index("thread_id")
        await db.conversations.create_index("participants")
        await db.conversations.create_index([("participants", 1), ("updated_at", -1)])
        # Notifications
        await db.notifications.create_index([("target_role", 1), ("created_at", -1)])
        await db.notifications.create_index("read_by")
        # Access / Residents
        await db.guest_requests.create_index([("location_id", 1), ("status", 1)])
        await db.access_logs.create_index([("location_id", 1), ("timestamp", -1)])
        await db.residents.create_index([("member_id", 1), ("status", 1)])
        await db.residents.create_index([("location_id", 1), ("status", 1)])
        # Files / Documents
        await db.files.create_index([("member_id", 1), ("is_deleted", 1)])
        # Auth
        await db.password_resets.create_index("token")
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
        await db.sessions.create_index("user_id")
        await db.sessions.create_index("jti", unique=True)
        await db.sessions.create_index("expires_at", expireAfterSeconds=0)
        # Financial
        await db.financial.create_index([("location_id", 1), ("date", -1)])
        await db.financial.create_index([("type", 1), ("date", -1)])
        # Locations
        await db.locations.create_index("id", unique=True)
        await db.locations.create_index([("parent_id", 1), ("type", 1)])
        # Push
        await db.push_subscriptions.create_index("user_id")
        await db.push_subscriptions.create_index("subscription.endpoint", unique=True)
        # Audit
        await db.audit_log.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_log.create_index("timestamp")
        # Wallet
        await db.wallet_badges.create_index("token", unique=True)
        await db.wallet_badges.create_index("member_id")
        await db.wallet_badges.create_index("resident_location_id")  # iter151 — campus filter fallback
        # Deleted items (recycle bin) — TTL cleanup after 30 days
        await db.deleted_items.create_index("deleted_at", expireAfterSeconds=2592000)
        # ===== iter152 hot-path indexes — explicit audit pass =====
        # Security Checkpoint events: visitor-log + state queries scan today's events for a checkpoint.
        await db.security_checkpoint_events.create_index(
            [("checkpoint_id", 1), ("created_at", -1)],
            name="cpe_cp_date",
        )
        await db.security_checkpoint_events.create_index(
            [("checkpoint_id", 1), ("clear_at", -1)],
            name="cpe_cp_clear",
        )
        # Subject lookup for entry/exit pairing
        await db.security_checkpoint_events.create_index(
            [("checkpoint_id", 1), ("subject.id", 1), ("direction", 1), ("created_at", -1)],
            name="cpe_pair",
        )
        await db.security_checkpoint_sessions.create_index("token_hash", unique=True)
        await db.security_checkpoint_sessions.create_index([("checkpoint_id", 1), ("expires_at", 1)])
        # Sales: location-scoped daily aggregates + customer history
        await db.sales.create_index([("location_id", 1), ("created_at", -1)])
        await db.sales.create_index("receipt_number")
        await db.sales.create_index("customer_id")
        # Login throttle (iter151) — per-IP recent-failure scan
        await db.login_attempts.create_index([("ip", 1), ("ok", 1), ("at", -1)])
        await db.login_attempts.create_index("at", expireAfterSeconds=2592000)  # TTL 30 days
        # Pair-attempts TTL (iter134) — same pattern
        await db.security_pair_attempts.create_index([("ip", 1), ("ok", 1), ("at", -1)])
        await db.security_pair_attempts.create_index("at", expireAfterSeconds=2592000)
        # Members hot path: role + active campus + status (RBAC widely uses this combo)
        await db.members.create_index([("role", 1), ("active_campus_id", 1), ("status", 1)])
        await db.members.create_index([("kind", 1), ("status", 1)])
        await db.members.create_index("resident_location_id")
        # Children
        await db.children.create_index("id", unique=True)
        await db.children.create_index([("location_id", 1), ("status", 1)])
        await db.children.create_index("family_id")
        await db.children.create_index("resident_location_id")
        # Audit (the canonical audit collection has multiple names — index both)
        await db.audits.create_index([("user_id", 1), ("created_at", -1)])
        await db.audits.create_index([("entity_type", 1), ("entity_id", 1)])
        # Audit TTL: 1-year retention (operators export before then)
        await db.audits.create_index("created_at", expireAfterSeconds=31536000)
        try:
            await db.audit_log.create_index("timestamp", expireAfterSeconds=31536000)
        except Exception as _e:
            # Pre-existing non-TTL index on audit_log.timestamp — leave it alone.
            pass
        # Chart-account balance hot path (iter208) — _batch_compute_balances runs 5
        # aggregations across donations/sales/expenses/transfers scoped by account_id.
        # Without these, each call was a full collection scan on every list view.
        await db.chart_accounts.create_index("id", unique=True)
        await db.chart_accounts.create_index([("location_id", 1), ("active", 1)])
        await db.chart_accounts.create_index("assigned_user_ids")
        await db.donations.create_index("deposit_to_account_id")
        await db.donations.create_index([("location_id", 1), ("date", -1)])
        await db.expenses.create_index("paid_from_account_id")
        await db.expenses.create_index([("status", 1), ("paid_from_account_id", 1)])
        await db.expenses.create_index([("location_id", 1), ("date", -1)])
        await db.sales.create_index([("deposit_to_account_id", 1), ("voided", 1)])
        await db.chart_account_transfers.create_index("from_account_id")
        await db.chart_account_transfers.create_index("to_account_id")
        # Auto-posted journal entry lookup by source (donation/expense delete cascade)
        await db.accounting_entries.create_index([("auto_generated_from", 1), ("source_id", 1)])
        await db.accounting_entries.create_index([("status", 1), ("is_reversed", 1)])
        # iter227 — fare alert lookup + passenger portal token lookup
        await db.fare_alerts.create_index("created_by")
        await db.fare_alerts.create_index([("active", 1), ("date", 1)])
        await db.shipments.create_index("passengers.portal_token")
        # ===== iter296 — unified finance ledger + AP/AR hot-path indexes =====
        # `finance_journal_entries` is queried by:
        #  - location_id + reversed (report scope filter),
        #  - source + reference (source-doc lookups + cascade reversal),
        #  - idempotency_key (unique among active JEs — prevents double posts),
        #  - lines.account_id (account-in-use check, balance rollup),
        #  - date (period + PnL windowing).
        await db.finance_journal_entries.create_index("id", unique=True)
        await db.finance_journal_entries.create_index([("location_id", 1), ("reversed", 1), ("date", -1)])
        await db.finance_journal_entries.create_index([("source", 1), ("reference", 1)])
        await db.finance_journal_entries.create_index("lines.account_id")
        await db.finance_journal_entries.create_index([("date", -1)])
        # Idempotency lookup: partial-unique on active rows only. MongoDB partial
        # filters don't support `$ne`, so we scope on `reversed: false` explicitly
        # (post_journal_entry always writes `reversed=false` on new rows). Reversal
        # marks the doc `reversed=true`, dropping it out of the unique constraint
        # so a subsequent replay with the same idempotency_key can succeed.
        try:
            await db.finance_journal_entries.create_index(
                "idempotency_key",
                unique=True,
                partialFilterExpression={
                    "idempotency_key": {"$exists": True, "$type": "string"},
                    "reversed": {"$eq": False},
                },
                name="fje_idempotency_active",
            )
        except Exception as _e:
            logger.info(f"finance_journal_entries idempotency index: {_e}")
        # Chart of Accounts: coded lookups + active filter
        await db.finance_chart_of_accounts.create_index("id", unique=True)
        await db.finance_chart_of_accounts.create_index("code", unique=True)
        await db.finance_chart_of_accounts.create_index([("type", 1), ("active", 1)])
        # Bank accounts / bills / vendors
        await db.bank_accounts.create_index("id", unique=True)
        await db.bank_accounts.create_index([("location_id", 1), ("closed", 1)])
        await db.bank_accounts.create_index("linked_account_id")
        await db.vendors.create_index("id", unique=True)
        await db.vendors.create_index([("location_id", 1), ("name", 1)])
        await db.vendors.create_index("email")
        await db.bills.create_index("id", unique=True)
        await db.bills.create_index([("location_id", 1), ("status", 1), ("bill_date", -1)])
        await db.bills.create_index("vendor_id")
        await db.bills.create_index("bill_number")
        # Bank transactions (statement import + reconciliation)
        await db.bank_transactions.create_index("id", unique=True)
        await db.bank_transactions.create_index([("bank_account_id", 1), ("date", -1)])
        await db.bank_transactions.create_index([("status", 1), ("date", -1)])
        # Recurring entries — scheduler ticks every hour, hot query is
        # {active: True, next_run_date: {$lte: today}}
        await db.recurring_entries.create_index("id", unique=True)
        await db.recurring_entries.create_index([("active", 1), ("next_run_date", 1)])
        await db.recurring_entries.create_index("location_id")
        # Reconciliation rules (bank-statement auto-match)
        await db.reconciliation_rules.create_index([("location_id", 1), ("active", 1), ("priority", 1)])
        # Director-digest idempotency — one row per user per date
        await db.task_director_digests.create_index(
            [("user_id", 1), ("date", 1)], unique=True, name="tdd_user_date"
        )
        await db.task_director_digests.create_index("date", expireAfterSeconds=7776000)  # 90d TTL
        # HR / payroll — location + period lookups.
        # iter305: the canonical collection is `hr_payslips` (see routers/hr.py).
        # The legacy `payslips` name was a ghost — no reads or writes ever
        # targeted it. Only its `hr_payslips` counterparts are indexed here.
        await db.hr_employees.create_index("id", unique=True)
        await db.hr_employees.create_index([("location_id", 1), ("status", 1)])
        await db.hr_employees.create_index("user_id")
        await db.hr_contracts.create_index([("employee_id", 1), ("start_date", -1)])
        # Guest passes / access requests / checkpoint events — hot at security desk
        await db.guest_passes.create_index("id", unique=True)
        await db.guest_passes.create_index([("location_id", 1), ("status", 1), ("valid_from", -1)])
        await db.guest_passes.create_index("code")
        await db.guest_access_requests.create_index("id", unique=True)
        await db.guest_access_requests.create_index([("location_id", 1), ("status", 1), ("created_at", -1)])
        # (secondary checkpoint_events collection — some code paths write here)
        try:
            await db.checkpoint_events.create_index([("checkpoint_id", 1), ("created_at", -1)])
        except Exception:
            pass
        # Kanban boards secondary collection (some code paths use kanban_boards, some boards)
        await db.kanban_boards.create_index("id", unique=True)
        await db.kanban_boards.create_index([("location_id", 1), ("is_global", 1)])
        # ===== iter301 — hot-path index optimization pass =====
        # `guests` — heavy read collection: id lookup, family scoping, dedup by email/phone,
        # kiosk pin lookup, campus scoping for admin dashboards.
        await db.guests.create_index("id", unique=True)
        await db.guests.create_index([("location_id", 1), ("status", 1)])
        await db.guests.create_index("family_id")
        await db.guests.create_index("user_id")
        await db.guests.create_index("email")
        await db.guests.create_index("phone")
        await db.guests.create_index("pin")
        await db.guests.create_index([("is_parent", 1), ("family_id", 1)])
        # `families` — id lookup + case-insensitive family_name dedup + campus scoping.
        await db.families.create_index("id", unique=True)
        await db.families.create_index([("location_id", 1), ("family_name", 1)])
        # `shipments` — id lookup, dashboard scoping, sub-doc token lookup already indexed above.
        await db.shipments.create_index("id", unique=True)
        await db.shipments.create_index([("status", 1), ("created_at", -1)])
        await db.shipments.create_index([("location_id", 1), ("created_at", -1)])
        # `social_cases` — subject-centric queries + case listing per location.
        await db.social_cases.create_index("id", unique=True)
        await db.social_cases.create_index("subject_id")
        await db.social_cases.create_index([("location_id", 1), ("status", 1), ("created_at", -1)])
        await db.social_review_forms.create_index("id", unique=True)
        await db.social_review_forms.create_index([("child_id", 1), ("review_date", -1)])
        await db.social_review_forms.create_index([("location_id", 1), ("review_date", -1)])
        # `products` — id lookup, campus scoping, search by name/barcode, low-stock aggregation.
        await db.products.create_index("id", unique=True)
        await db.products.create_index([("location_id", 1), ("name", 1)])
        await db.products.create_index("name")
        await db.products.create_index("barcode")
        await db.products.create_index("variants.barcode")
        # `hr_payslips` — payroll queries by staff_id+period, location+period, status.
        await db.hr_payslips.create_index("id", unique=True)
        await db.hr_payslips.create_index([("staff_id", 1), ("period", -1)])
        await db.hr_payslips.create_index([("location_id", 1), ("period", -1)])
        await db.hr_payslips.create_index([("status", 1), ("period", -1)])
        await db.hr_payslips.create_index("salary_id")
        # `hr_timesheets` / `hr_salaries` / `hr_time_off` — portal + payroll hot paths.
        await db.hr_timesheets.create_index([("staff_id", 1), ("period", -1)])
        await db.hr_timesheets.create_index([("location_id", 1), ("status", 1)])
        await db.hr_salaries.create_index([("staff_id", 1), ("active", 1)])
        await db.hr_salaries.create_index([("location_id", 1), ("active", 1)])
        await db.hr_time_off.create_index([("staff_id", 1), ("start_date", -1)])
        await db.hr_time_off.create_index([("location_id", 1), ("status", 1), ("start_date", -1)])
        # `resources` / `venues` / `bookings` / `public_bookings` — schedule lookups.
        await db.resources.create_index("id", unique=True)
        await db.resources.create_index([("location_id", 1), ("name", 1)])
        await db.venues.create_index("id", unique=True)
        await db.venues.create_index([("location_id", 1), ("name", 1)])
        await db.bookings.create_index("id", unique=True)
        await db.bookings.create_index([("resource_id", 1), ("start_time", 1)])
        await db.bookings.create_index([("location_id", 1), ("start_time", 1)])
        await db.public_bookings.create_index("id", unique=True)
        await db.public_bookings.create_index([("location_id", 1), ("date", -1)])
        await db.public_bookings.create_index("token")
        # `approval_requests` — subject-kind + status + campus, plus fund-request lookup.
        await db.approval_requests.create_index("id", unique=True)
        await db.approval_requests.create_index([("subject_kind", 1), ("status", 1), ("created_at", -1)])
        await db.approval_requests.create_index([("location_id", 1), ("status", 1)])
        # `customer_accounts` — statement + POS lookups.
        await db.customer_accounts.create_index("id", unique=True)
        await db.customer_accounts.create_index("user_id")
        await db.customer_accounts.create_index("customer_id")
        await db.customer_accounts.create_index([("location_id", 1), ("name", 1)])
        # `event_registrations` / `enrollments` / `conferences` — dashboard aggregates.
        await db.event_registrations.create_index([("event_id", 1), ("status", 1)])
        await db.event_registrations.create_index("member_id")
        await db.enrollments.create_index([("location_id", 1), ("status", 1)])
        await db.enrollments.create_index("member_id")
        await db.conferences.create_index("id", unique=True)
        await db.conferences.create_index([("location_id", 1), ("start_date", -1)])
        # `donors` — name search + campus scoping.
        await db.donors.create_index("id", unique=True)
        await db.donors.create_index([("location_id", 1), ("name", 1)])
        await db.donors.create_index("email")
        # `announcements` / `documents` — location-scoped feeds.
        await db.announcements.create_index([("location_id", 1), ("created_at", -1)])
        await db.documents.create_index([("owner_id", 1), ("created_at", -1)])
        await db.documents.create_index([("location_id", 1), ("created_at", -1)])
        # `case_notes` — reader lookup per case.
        await db.case_notes.create_index([("case_id", 1), ("created_at", -1)])
        # `call_logs` — per-user CDR view + date-range PBX report.
        await db.call_logs.create_index([("user_id", 1), ("start_time", -1)])
        await db.call_logs.create_index([("location_id", 1), ("start_time", -1)])
        logger.info("Indexes ensured (idempotent)")
    except Exception as e:
        logger.warning(f"Index ensure: {e}")
