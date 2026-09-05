"""iter296 — verify hot-path MongoDB indexes exist after `_ensure_indexes()`
runs on startup. Uses sync pymongo to avoid pytest-asyncio config.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    try:
        yield c[DB_NAME]
    finally:
        c.close()


def _key_specs(coll):
    return {tuple(spec["key"].items()): spec for spec in coll.list_indexes()}


@pytest.mark.parametrize("coll_name,key", [
    ("finance_journal_entries", (("id", 1),)),
    ("finance_journal_entries", (("location_id", 1), ("reversed", 1), ("date", -1))),
    ("finance_journal_entries", (("source", 1), ("reference", 1))),
    ("finance_journal_entries", (("lines.account_id", 1),)),
    ("finance_chart_of_accounts", (("id", 1),)),
    ("finance_chart_of_accounts", (("code", 1),)),
    ("bank_accounts", (("id", 1),)),
    ("bank_accounts", (("location_id", 1), ("closed", 1))),
    ("bank_accounts", (("linked_account_id", 1),)),
    ("vendors", (("id", 1),)),
    ("vendors", (("location_id", 1), ("name", 1))),
    ("bills", (("id", 1),)),
    ("bills", (("location_id", 1), ("status", 1), ("bill_date", -1))),
    ("bills", (("vendor_id", 1),)),
    ("recurring_entries", (("active", 1), ("next_run_date", 1))),
    ("task_director_digests", (("user_id", 1), ("date", 1))),
    ("hr_employees", (("location_id", 1), ("status", 1))),
    ("guest_passes", (("location_id", 1), ("status", 1), ("valid_from", -1))),
    # iter301 — hot-path index optimization pass
    ("guests", (("id", 1),)),
    ("guests", (("location_id", 1), ("status", 1))),
    ("guests", (("family_id", 1),)),
    ("families", (("id", 1),)),
    ("families", (("location_id", 1), ("family_name", 1))),
    ("shipments", (("id", 1),)),
    ("shipments", (("status", 1), ("created_at", -1))),
    ("social_cases", (("id", 1),)),
    ("social_cases", (("subject_id", 1),)),
    ("social_cases", (("location_id", 1), ("status", 1), ("created_at", -1))),
    ("social_review_forms", (("child_id", 1), ("review_date", -1))),
    ("products", (("id", 1),)),
    ("products", (("location_id", 1), ("name", 1))),
    ("products", (("barcode", 1),)),
    ("hr_payslips", (("id", 1),)),
    ("hr_payslips", (("staff_id", 1), ("period", -1))),
    ("hr_payslips", (("location_id", 1), ("period", -1))),
    ("hr_timesheets", (("staff_id", 1), ("period", -1))),
    ("hr_salaries", (("staff_id", 1), ("active", 1))),
    ("hr_time_off", (("staff_id", 1), ("start_date", -1))),
    ("resources", (("id", 1),)),
    ("venues", (("id", 1),)),
    ("bookings", (("resource_id", 1), ("start_time", 1))),
    ("public_bookings", (("token", 1),)),
    ("approval_requests", (("id", 1),)),
    ("approval_requests", (("subject_kind", 1), ("status", 1), ("created_at", -1))),
    ("customer_accounts", (("id", 1),)),
    ("customer_accounts", (("user_id", 1),)),
    ("event_registrations", (("event_id", 1), ("status", 1))),
    ("enrollments", (("location_id", 1), ("status", 1))),
    ("donors", (("location_id", 1), ("name", 1))),
    ("announcements", (("location_id", 1), ("created_at", -1))),
    ("call_logs", (("user_id", 1), ("start_time", -1))),
])
def test_index_present(db, coll_name, key):
    specs = _key_specs(db[coll_name])
    assert key in specs, f"{coll_name}: missing index on {key} (have {list(specs.keys())})"


def test_idempotency_key_is_partial_unique(db):
    specs = _key_specs(db.finance_journal_entries)
    ik = specs.get((("idempotency_key", 1),))
    assert ik is not None, "finance_journal_entries idempotency_key index missing"
    assert ik.get("unique") is True, "idempotency_key must be unique"
    assert "partialFilterExpression" in ik, "idempotency_key must be partial (active-only)"


def test_task_director_digest_unique(db):
    specs = _key_specs(db.task_director_digests)
    tdd = specs.get((("user_id", 1), ("date", 1)))
    assert tdd is not None and tdd.get("unique") is True


def test_task_director_digest_ttl(db):
    specs = _key_specs(db.task_director_digests)
    ttl = specs.get((("date", 1),))
    assert ttl is not None and "expireAfterSeconds" in ttl
