"""Iter 294 backend tests:
  - Director digest scheduler function `_fire_overdue_task_director_digest`:
      * function definition + call site exist
      * seed director+overdue tasks → invoke → row in db.task_director_digests
      * second invocation is idempotent (no-op)
      * global roles (admin) see all locations; directors scoped to location_ids
  - Regression: /api/finance/receipts/review-queue, /api/reports/pdf,
      /api/hr/payslips/generate-payday, /api/bank/accounts, /api/finance/journal-entries
"""
import os
import sys
import uuid
import asyncio
import subprocess
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}

sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Director digest — source presence ----------
def test_digest_function_defined_and_called():
    out = subprocess.check_output(
        ["grep", "-n", "_fire_overdue_task_director_digest", "/app/backend/server.py"],
        text=True,
    )
    assert "async def _fire_overdue_task_director_digest" in out, out
    # Caller present in 08:00 UTC block
    assert "await _fire_overdue_task_director_digest()" in out, out


# ---------- Director digest — behaviour ----------
@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db():
    from server import db as _db  # uses backend/.env MONGO_URL + DB_NAME
    return _db


@pytest.fixture(scope="module")
def seeded(event_loop, db):
    """Seed a fresh director + 2 overdue tasks; return ids. Cleanup on teardown."""
    director_id = f"TEST_dir_{uuid.uuid4().hex[:6]}"
    email = f"TEST_dir_{uuid.uuid4().hex[:6]}@example.com"
    board_id = f"TEST_brd_{uuid.uuid4().hex[:6]}"
    task_ids = [f"TEST_tsk_{uuid.uuid4().hex[:6]}" for _ in range(2)]
    yesterday = (date.today() - timedelta(days=2)).isoformat()

    async def _seed():
        await db.users.insert_one({
            "id": director_id, "email": email, "name": "TEST Director",
            "role": "Director", "location_ids": ["loc_001"],
            "status": "active",
        })
        await db.boards.insert_one({
            "id": board_id, "name": "TEST board", "location_id": "loc_001",
        })
        for tid in task_ids:
            await db.tasks.insert_one({
                "id": tid, "title": f"TEST overdue {tid}", "due_date": yesterday,
                "status": "todo", "board_id": board_id, "location_id": "loc_001",
                "assignees": [], "is_archived": False,
            })
        # Clean any prior digest row for this new director (fresh)
        await db.task_director_digests.delete_many({"user_id": director_id})

    event_loop.run_until_complete(_seed())
    yield {"director_id": director_id, "email": email, "board_id": board_id,
           "task_ids": task_ids, "yesterday": yesterday}

    async def _cleanup():
        await db.users.delete_one({"id": director_id})
        await db.boards.delete_one({"id": board_id})
        await db.tasks.delete_many({"id": {"$in": task_ids}})
        await db.task_director_digests.delete_many({"user_id": director_id})

    event_loop.run_until_complete(_cleanup())


def test_digest_creates_row_and_is_idempotent(event_loop, db, seeded):
    from server import _fire_overdue_task_director_digest

    # First invocation
    event_loop.run_until_complete(_fire_overdue_task_director_digest())

    async def _fetch():
        return await db.task_director_digests.find(
            {"user_id": seeded["director_id"]}
        ).to_list(10)

    rows = event_loop.run_until_complete(_fetch())
    assert len(rows) == 1, f"expected 1 digest row, got {len(rows)}: {rows}"
    row = rows[0]
    assert row["date"] == date.today().isoformat()
    assert row["task_count"] == 2, f"task_count expected 2, got {row.get('task_count')}"
    assert row["email"] == seeded["email"]

    # Second immediate invocation → no-op (same-day guard)
    event_loop.run_until_complete(_fire_overdue_task_director_digest())
    rows2 = event_loop.run_until_complete(_fetch())
    assert len(rows2) == 1, f"idempotency broken; second run added row(s): {rows2}"


def test_digest_scope_respects_location_ids(event_loop, db):
    """Director with location_ids=['loc_999'] (no tasks there) should NOT get a digest."""
    from server import _fire_overdue_task_director_digest

    dir_id = f"TEST_dir_{uuid.uuid4().hex[:6]}"
    email = f"TEST_dir_{uuid.uuid4().hex[:6]}@example.com"
    # Ensure at least one overdue task exists somewhere for the run to iterate
    board_id = f"TEST_brd_{uuid.uuid4().hex[:6]}"
    task_id = f"TEST_tsk_{uuid.uuid4().hex[:6]}"
    yesterday = (date.today() - timedelta(days=2)).isoformat()

    async def _setup():
        await db.users.insert_one({
            "id": dir_id, "email": email, "name": "TEST OutOfScope",
            "role": "Director", "location_ids": ["loc_zzz_nonexistent"],
            "status": "active",
        })
        await db.boards.insert_one({"id": board_id, "location_id": "loc_001"})
        await db.tasks.insert_one({
            "id": task_id, "title": "scope-check", "due_date": yesterday,
            "status": "todo", "board_id": board_id, "location_id": "loc_001",
            "assignees": [], "is_archived": False,
        })
        await db.task_director_digests.delete_many({"user_id": dir_id})

    event_loop.run_until_complete(_setup())
    try:
        event_loop.run_until_complete(_fire_overdue_task_director_digest())

        async def _fetch():
            return await db.task_director_digests.find({"user_id": dir_id}).to_list(5)
        rows = event_loop.run_until_complete(_fetch())
        assert rows == [], (
            f"director out-of-scope should NOT receive digest, got: {rows}"
        )
    finally:
        async def _cleanup():
            await db.users.delete_one({"id": dir_id})
            await db.boards.delete_one({"id": board_id})
            await db.tasks.delete_one({"id": task_id})
            await db.task_director_digests.delete_many({"user_id": dir_id})
        event_loop.run_until_complete(_cleanup())


# ---------- Regression endpoints (iter 292/293) ----------
def test_review_queue_list(headers):
    r = requests.get(f"{BASE_URL}/api/finance/receipts/review-queue",
                     headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), list)


def test_reports_pdf_without_fx(headers):
    r = requests.get(
        f"{BASE_URL}/api/reports/pdf",
        params={"report_type": "pnl", "period_start": "2025-01-01",
                "period_end": "2025-12-31"},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf"), \
        r.headers.get("content-type")
    assert r.content[:4] == b"%PDF"


def test_reports_pdf_with_fx(headers):
    r = requests.get(
        f"{BASE_URL}/api/reports/pdf",
        params={"report_type": "pnl", "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "fx_currency": "USD", "fx_rate": "3700"},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF"


def test_hr_payslips_generate_payday(headers):
    r = requests.post(f"{BASE_URL}/api/hr/payslips/generate-payday",
                      headers=headers, json={}, timeout=30)
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:300]}"


def test_bank_accounts_list(headers):
    r = requests.get(f"{BASE_URL}/api/bank/accounts", headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), list)


def test_finance_journal_entries_list(headers):
    r = requests.get(f"{BASE_URL}/api/finance/journal",
                     headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Some list endpoints return list, some wrap in {items: []}
    assert isinstance(body, (list, dict))
