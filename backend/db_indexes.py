"""MongoDB hot-path index setup.

Extracted from server.py in iter302; split by domain in iter348 (the single
303-line function was unmaintainable, and worse: one failing `create_index`
aborted every index after it — a pre-existing non-TTL index on `audit_log`
could silently cost you the whole finance set). Each group now runs in its own
try/except, so a conflict in one domain can't starve the rest.

All calls are idempotent — safe on every startup.
"""
from deps import db, logger

_DAY = 86400
_YEAR = 31536000


async def _ensure_people_indexes():
    """Users, members, children, guests, families, and auth/session records."""
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index([("role", 1), ("status", 1)])
    await db.users.create_index([("location_id", 1), ("status", 1)])
    await db.users.create_index("location_ids")

    await db.members.create_index("id", unique=True)
    await db.members.create_index("email")
    await db.members.create_index("pin")
    await db.members.create_index([("location_id", 1), ("status", 1)])
    await db.members.create_index("user_id")
    await db.members.create_index("date_of_birth")
    # RBAC reads this combo constantly
    await db.members.create_index([("role", 1), ("active_campus_id", 1), ("status", 1)])
    await db.members.create_index([("kind", 1), ("status", 1)])
    await db.members.create_index("resident_location_id")

    await db.children.create_index("id", unique=True)
    await db.children.create_index([("location_id", 1), ("status", 1)])
    await db.children.create_index("family_id")
    await db.children.create_index("resident_location_id")

    # Heavy read collection: dedup by email/phone, kiosk pin, campus scoping
    await db.guests.create_index("id", unique=True)
    await db.guests.create_index([("location_id", 1), ("status", 1)])
    await db.guests.create_index("family_id")
    await db.guests.create_index("user_id")
    await db.guests.create_index("email")
    await db.guests.create_index("phone")
    await db.guests.create_index("pin")
    await db.guests.create_index([("is_parent", 1), ("family_id", 1)])

    await db.families.create_index("id", unique=True)
    await db.families.create_index([("location_id", 1), ("family_name", 1)])

    await db.password_resets.create_index("token")
    await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
    await db.sessions.create_index("user_id")
    await db.sessions.create_index("jti", unique=True)
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    # Login throttle — per-IP recent-failure scan, 30-day TTL
    await db.login_attempts.create_index([("ip", 1), ("ok", 1), ("at", -1)])
    await db.login_attempts.create_index("at", expireAfterSeconds=30 * _DAY)


async def _ensure_scheduling_indexes():
    """Events, check-ins, resources, venues, bookings, registrations."""
    await db.events.create_index("id", unique=True)
    await db.events.create_index([("date", 1), ("status", 1)])
    await db.events.create_index([("location_id", 1), ("date", 1)])

    await db.checkins.create_index("id", unique=True)
    await db.checkins.create_index([("event_id", 1), ("check_in_time", -1)])
    await db.checkins.create_index([("date", 1), ("location_id", 1)])

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

    await db.event_registrations.create_index([("event_id", 1), ("status", 1)])
    await db.event_registrations.create_index("member_id")
    await db.enrollments.create_index([("location_id", 1), ("status", 1)])
    await db.enrollments.create_index("member_id")
    await db.conferences.create_index("id", unique=True)
    await db.conferences.create_index([("location_id", 1), ("start_date", -1)])


async def _ensure_task_indexes():
    """Tasks, boards (both collection names), and the director digest."""
    await db.tasks.create_index("id", unique=True)
    await db.tasks.create_index([("board_id", 1), ("list_id", 1), ("position", 1)])
    await db.tasks.create_index([("assignees", 1), ("due_date", 1)])
    await db.tasks.create_index([("due_date", 1), ("is_archived", 1), ("status", 1)])
    await db.boards.create_index("id", unique=True)
    await db.boards.create_index([("location_id", 1), ("is_global", 1)])
    # Some code paths use kanban_boards, some boards
    await db.kanban_boards.create_index("id", unique=True)
    await db.kanban_boards.create_index([("location_id", 1), ("is_global", 1)])
    # One digest row per user per date, 90-day TTL
    await db.task_director_digests.create_index(
        [("user_id", 1), ("date", 1)], unique=True, name="tdd_user_date"
    )
    await db.task_director_digests.create_index("date", expireAfterSeconds=90 * _DAY)


async def _ensure_comms_indexes():
    """Chat, notifications, announcements, calls, push."""
    await db.chat_messages.create_index("conversation_id")
    await db.chat_messages.create_index([("conversation_id", 1), ("created_at", -1)])
    await db.chat_messages.create_index("thread_id")
    await db.conversations.create_index("participants")
    await db.conversations.create_index([("participants", 1), ("updated_at", -1)])

    await db.notifications.create_index([("target_role", 1), ("created_at", -1)])
    await db.notifications.create_index("read_by")
    await db.announcements.create_index([("location_id", 1), ("created_at", -1)])

    await db.call_logs.create_index([("user_id", 1), ("start_time", -1)])
    await db.call_logs.create_index([("location_id", 1), ("start_time", -1)])
    # iter347 missed-call log: per-user unhandled list + 90s dedupe probe
    await db.missed_calls.create_index([("user_id", 1), ("handled", 1), ("ts", -1)])

    await db.push_subscriptions.create_index("user_id")
    await db.push_subscriptions.create_index("subscription.endpoint", unique=True)


async def _ensure_access_indexes():
    """Access control, guest passes, checkpoints, badges."""
    await db.guest_requests.create_index([("location_id", 1), ("status", 1)])
    await db.access_logs.create_index([("location_id", 1), ("timestamp", -1)])
    await db.residents.create_index([("member_id", 1), ("status", 1)])
    await db.residents.create_index([("location_id", 1), ("status", 1)])

    await db.guest_passes.create_index("id", unique=True)
    await db.guest_passes.create_index([("location_id", 1), ("status", 1), ("valid_from", -1)])
    await db.guest_passes.create_index("code")
    await db.guest_access_requests.create_index("id", unique=True)
    await db.guest_access_requests.create_index([("location_id", 1), ("status", 1), ("created_at", -1)])
    # Rate-limit window scan
    await db.guest_access_requests.create_index([("client_ip", 1), ("created_at", -1)])
    await db.guest_access_requests.create_index([("proxy_ip", 1), ("created_at", -1)])
    # iter347 rejected-request log: admin list + the same rate-limit window
    await db.access_request_rejections.create_index([("created_at", -1)])
    await db.access_request_rejections.create_index([("client_ip", 1), ("created_at", -1)])
    await db.access_request_rejections.create_index([("proxy_ip", 1), ("created_at", -1)])
    await db.access_request_rejections.create_index([("reason", 1), ("created_at", -1)])

    await db.security_checkpoint_events.create_index(
        [("checkpoint_id", 1), ("created_at", -1)], name="cpe_cp_date")
    await db.security_checkpoint_events.create_index(
        [("checkpoint_id", 1), ("clear_at", -1)], name="cpe_cp_clear")
    # Entry/exit pairing for a subject
    await db.security_checkpoint_events.create_index(
        [("checkpoint_id", 1), ("subject.id", 1), ("direction", 1), ("created_at", -1)],
        name="cpe_pair")
    await db.security_checkpoint_sessions.create_index("token_hash", unique=True)
    await db.security_checkpoint_sessions.create_index([("checkpoint_id", 1), ("expires_at", 1)])
    await db.security_pair_attempts.create_index([("ip", 1), ("ok", 1), ("at", -1)])
    await db.security_pair_attempts.create_index("at", expireAfterSeconds=30 * _DAY)
    # Secondary checkpoint_events collection — some code paths write here
    await db.checkpoint_events.create_index([("checkpoint_id", 1), ("created_at", -1)])

    await db.wallet_badges.create_index("token", unique=True)
    await db.wallet_badges.create_index("member_id")
    await db.wallet_badges.create_index("resident_location_id")


async def _ensure_finance_indexes():
    """Ledger, chart of accounts, AP/AR, banking, POS, donors."""
    await db.financial.create_index([("location_id", 1), ("date", -1)])
    await db.financial.create_index([("type", 1), ("date", -1)])

    # Balance rollups aggregate across these five scoped by account_id
    await db.chart_accounts.create_index("id", unique=True)
    await db.chart_accounts.create_index([("location_id", 1), ("active", 1)])
    await db.chart_accounts.create_index("assigned_user_ids")
    await db.donations.create_index("deposit_to_account_id")
    await db.donations.create_index([("location_id", 1), ("date", -1)])
    await db.expenses.create_index("paid_from_account_id")
    await db.expenses.create_index([("status", 1), ("paid_from_account_id", 1)])
    await db.expenses.create_index([("location_id", 1), ("date", -1)])
    await db.chart_account_transfers.create_index("from_account_id")
    await db.chart_account_transfers.create_index("to_account_id")

    await db.sales.create_index([("location_id", 1), ("created_at", -1)])
    await db.sales.create_index("receipt_number")
    await db.sales.create_index("customer_id")
    await db.sales.create_index([("deposit_to_account_id", 1), ("voided", 1)])
    # iter346 online checkout: settlement looks a sale up by provider tx_ref
    await db.sales.create_index("tx_ref")
    await db.payment_webhook_events.create_index("id", unique=True)

    await db.accounting_entries.create_index([("auto_generated_from", 1), ("source_id", 1)])
    await db.accounting_entries.create_index([("status", 1), ("is_reversed", 1)])

    await db.finance_journal_entries.create_index("id", unique=True)
    await db.finance_journal_entries.create_index([("location_id", 1), ("reversed", 1), ("date", -1)])
    await db.finance_journal_entries.create_index([("source", 1), ("reference", 1)])
    await db.finance_journal_entries.create_index("lines.account_id")
    await db.finance_journal_entries.create_index([("date", -1)])

    await db.finance_chart_of_accounts.create_index("id", unique=True)
    await db.finance_chart_of_accounts.create_index("code", unique=True)
    await db.finance_chart_of_accounts.create_index([("type", 1), ("active", 1)])

    await db.bank_accounts.create_index("id", unique=True)
    await db.bank_accounts.create_index([("location_id", 1), ("closed", 1)])
    await db.bank_accounts.create_index("linked_account_id")
    await db.bank_transactions.create_index("id", unique=True)
    await db.bank_transactions.create_index([("bank_account_id", 1), ("date", -1)])
    await db.bank_transactions.create_index([("status", 1), ("date", -1)])
    await db.reconciliation_rules.create_index([("location_id", 1), ("active", 1), ("priority", 1)])

    await db.vendors.create_index("id", unique=True)
    await db.vendors.create_index([("location_id", 1), ("name", 1)])
    await db.vendors.create_index("email")
    await db.bills.create_index("id", unique=True)
    await db.bills.create_index([("location_id", 1), ("status", 1), ("bill_date", -1)])
    await db.bills.create_index("vendor_id")
    await db.bills.create_index("bill_number")

    # Scheduler ticks hourly on {active: True, next_run_date: {$lte: today}}
    await db.recurring_entries.create_index("id", unique=True)
    await db.recurring_entries.create_index([("active", 1), ("next_run_date", 1)])
    await db.recurring_entries.create_index("location_id")

    await db.customer_accounts.create_index("id", unique=True)
    await db.customer_accounts.create_index("user_id")
    await db.customer_accounts.create_index("customer_id")
    await db.customer_accounts.create_index([("location_id", 1), ("name", 1)])
    await db.donors.create_index("id", unique=True)
    await db.donors.create_index([("location_id", 1), ("name", 1)])
    await db.donors.create_index("email")


async def _ensure_journal_idempotency_index():
    """Partial-unique idempotency key on ACTIVE journal entries only.

    MongoDB partial filters don't support `$ne`, so the filter pins
    `reversed: false` (post_journal_entry always writes that on new rows).
    Reversal flips it to true, dropping the doc out of the constraint so a
    later replay with the same key can post again.
    """
    await db.finance_journal_entries.create_index(
        "idempotency_key",
        unique=True,
        partialFilterExpression={
            "idempotency_key": {"$exists": True, "$type": "string"},
            "reversed": {"$eq": False},
        },
        name="fje_idempotency_active",
    )


async def _ensure_hr_indexes():
    """Employees, contracts, payslips, timesheets, salaries, time off."""
    await db.hr_employees.create_index("id", unique=True)
    await db.hr_employees.create_index([("location_id", 1), ("status", 1)])
    await db.hr_employees.create_index("user_id")
    await db.hr_contracts.create_index([("employee_id", 1), ("start_date", -1)])
    # `hr_payslips` is canonical (routers/hr.py); the legacy `payslips` name
    # was never read or written, so it is deliberately not indexed.
    await db.hr_payslips.create_index("id", unique=True)
    await db.hr_payslips.create_index([("staff_id", 1), ("period", -1)])
    await db.hr_payslips.create_index([("location_id", 1), ("period", -1)])
    await db.hr_payslips.create_index([("status", 1), ("period", -1)])
    await db.hr_payslips.create_index("salary_id")
    await db.hr_timesheets.create_index([("staff_id", 1), ("period", -1)])
    await db.hr_timesheets.create_index([("location_id", 1), ("status", 1)])
    await db.hr_salaries.create_index([("staff_id", 1), ("active", 1)])
    await db.hr_salaries.create_index([("location_id", 1), ("active", 1)])
    await db.hr_time_off.create_index([("staff_id", 1), ("start_date", -1)])
    await db.hr_time_off.create_index([("location_id", 1), ("status", 1), ("start_date", -1)])


async def _ensure_operations_indexes():
    """Locations, shipments, products, social work, approvals, documents."""
    await db.locations.create_index("id", unique=True)
    await db.locations.create_index([("parent_id", 1), ("type", 1)])

    await db.shipments.create_index("id", unique=True)
    await db.shipments.create_index([("status", 1), ("created_at", -1)])
    await db.shipments.create_index([("location_id", 1), ("created_at", -1)])
    await db.shipments.create_index("passengers.portal_token")

    await db.products.create_index("id", unique=True)
    await db.products.create_index([("location_id", 1), ("name", 1)])
    await db.products.create_index("name")
    await db.products.create_index("barcode")
    await db.products.create_index("variants.barcode")

    await db.social_cases.create_index("id", unique=True)
    await db.social_cases.create_index("subject_id")
    await db.social_cases.create_index([("location_id", 1), ("status", 1), ("created_at", -1)])
    await db.social_review_forms.create_index("id", unique=True)
    await db.social_review_forms.create_index([("child_id", 1), ("review_date", -1)])
    await db.social_review_forms.create_index([("location_id", 1), ("review_date", -1)])
    await db.case_notes.create_index([("case_id", 1), ("created_at", -1)])

    await db.approval_requests.create_index("id", unique=True)
    await db.approval_requests.create_index([("subject_kind", 1), ("status", 1), ("created_at", -1)])
    await db.approval_requests.create_index([("location_id", 1), ("status", 1)])

    await db.files.create_index([("member_id", 1), ("is_deleted", 1)])
    await db.documents.create_index([("owner_id", 1), ("created_at", -1)])
    await db.documents.create_index([("location_id", 1), ("created_at", -1)])
    # Recycle bin — TTL cleanup after 30 days
    await db.deleted_items.create_index("deleted_at", expireAfterSeconds=30 * _DAY)


async def _ensure_audit_indexes():
    """Audit trail — two historical collection names, both indexed."""
    await db.audit_log.create_index([("user_id", 1), ("timestamp", -1)])
    await db.audit_log.create_index("timestamp")
    await db.audits.create_index([("user_id", 1), ("created_at", -1)])
    await db.audits.create_index([("entity_type", 1), ("entity_id", 1)])
    # 1-year retention (operators export before then)
    await db.audits.create_index("created_at", expireAfterSeconds=_YEAR)


async def _ensure_audit_ttl_index():
    """Separate because a pre-existing non-TTL index on the same field makes
    this raise, and that must not take the rest of the audit set down."""
    try:
        await db.audit_log.create_index("timestamp", expireAfterSeconds=_YEAR)
    except Exception as e:
        # Legacy deployments already have a plain `timestamp_1`. Leave it be —
        # retention there is managed by the operator's own export/prune.
        logger.info(f"audit_log TTL left as-is (pre-existing index): {e.__class__.__name__}")


_INDEX_GROUPS = (
    ("people", _ensure_people_indexes),
    ("scheduling", _ensure_scheduling_indexes),
    ("tasks", _ensure_task_indexes),
    ("comms", _ensure_comms_indexes),
    ("access", _ensure_access_indexes),
    ("finance", _ensure_finance_indexes),
    ("finance.idempotency", _ensure_journal_idempotency_index),
    ("hr", _ensure_hr_indexes),
    ("operations", _ensure_operations_indexes),
    ("audit", _ensure_audit_indexes),
    ("audit.ttl", _ensure_audit_ttl_index),
)


async def _ensure_indexes():
    """Idempotent index creation. Runs on every startup, safe to repeat."""
    failed = []
    for name, fn in _INDEX_GROUPS:
        try:
            await fn()
        except Exception as e:
            failed.append(name)
            logger.warning(f"Index group '{name}': {e}")
    if failed:
        logger.warning(f"Indexes ensured with {len(failed)} group(s) skipped: {', '.join(failed)}")
    else:
        logger.info("Indexes ensured (idempotent)")
