"""iter 257c / iteration 93 — dashboard task counter scoping tests.

Covers:
  * GET /api/dashboard/action-items  (overdue_tasks, unassigned_tasks, pending_approvals, expiring_passes)
  * GET /api/dashboard/stats         (tasks_overdue must match action-items scope)
Expected values are derived independently from MongoDB using the same
campus/board scoping rules as deps.get_campus_filter.
"""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

import creds  # env-backed logins, see tests/creds.py

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(backend_env["MONGO_URL"])
    yield client[backend_env["DB_NAME"]]
    client.close()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token")
    if not token:
        pytest.fail(f"login returned no token: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def campus_filter(db, user, field="location_id"):
    """Sync mirror of deps.get_campus_filter for admin/system users."""
    user_loc_ids = set(user.get("location_ids") or [])
    if user.get("location_id"):
        user_loc_ids.add(user["location_id"])
    if user_loc_ids:
        for p in db.locations.find({"id": {"$in": list(user_loc_ids)},
                                    "parent_id": {"$exists": True, "$nin": [None, ""]}}, {"_id": 0, "parent_id": 1}):
            if p.get("parent_id"):
                user_loc_ids.add(p["parent_id"])
    active = user.get("active_campus_id")
    if active:
        subs = [s["id"] for s in db.locations.find({"parent_id": active, "type": "sub-location"}, {"_id": 0, "id": 1})]
        all_locs = [active] + subs
        if len(all_locs) == 1:
            return {"$or": [{field: active}, {"location_ids": active}]}
        return {"$or": [{field: {"$in": all_locs}}, {"location_ids": {"$in": all_locs}}]}
    return {}


@pytest.fixture(scope="module")
def expected(mongo):
    user = mongo.users.find_one({"email": ADMIN_EMAIL})
    assert user, "admin user missing from DB"
    campus = campus_filter(mongo, user)
    now = datetime.now(timezone.utc)
    today = now.isoformat()[:10]
    board_ids = mongo.boards.distinct("id", {"is_archived": {"$ne": True}, **campus})
    scope = {"status": {"$nin": ["done"]}, "is_archived": {"$ne": True}, "board_id": {"$in": board_ids}}
    overdue = 0 if not board_ids else mongo.tasks.count_documents(
        {**scope, "due_date": {"$lt": today, "$ne": "", "$exists": True}})
    unassigned = 0 if not board_ids else mongo.tasks.count_documents(
        {**scope, "$or": [{"assignees": {"$size": 0}}, {"assignees": {"$exists": False}}]})
    week = (now + timedelta(days=7)).isoformat()[:10]
    passes = mongo.guests.count_documents({"expires_at": {"$lte": week, "$gte": today, "$exists": True, "$ne": ""}, **campus})
    passes += mongo.access_guest_passes.count_documents({"valid_until": {"$lte": week, "$gte": today}, "status": "active"})
    return {
        "campus": campus,
        "board_ids": board_ids,
        "overdue_tasks": overdue,
        "unassigned_tasks": unassigned,
        "pending_approvals": mongo.users.count_documents({"status": "pending", **campus}),
        "expiring_passes": passes,
        "global_overdue": mongo.tasks.count_documents({"status": {"$nin": ["done"]}, "is_archived": {"$ne": True},
                                                      "due_date": {"$lt": today, "$ne": "", "$exists": True}}),
    }


# ---------- action-items ----------
class TestActionItems:
    def test_action_items_200_and_shape(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("overdue_tasks", "pending_approvals", "expiring_passes", "unassigned_tasks"):
            assert k in d, f"missing {k}"
            assert isinstance(d[k], int), f"{k} not int: {d[k]!r}"
            assert d[k] >= 0

    def test_overdue_tasks_scoped_to_visible_boards(self, client, expected):
        d = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        assert d["overdue_tasks"] == expected["overdue_tasks"], (
            f"API overdue={d['overdue_tasks']} expected(scoped)={expected['overdue_tasks']} "
            f"global(pre-fix)={expected['global_overdue']}")

    def test_unassigned_tasks_scoped_to_visible_boards(self, client, expected):
        d = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        assert d["unassigned_tasks"] == expected["unassigned_tasks"]

    def test_counters_never_exceed_open_tasks_on_visible_boards(self, client, expected, mongo):
        d = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        open_in_scope = 0 if not expected["board_ids"] else mongo.tasks.count_documents(
            {"status": {"$nin": ["done"]}, "is_archived": {"$ne": True},
             "board_id": {"$in": expected["board_ids"]}})
        assert d["overdue_tasks"] <= open_in_scope
        assert d["unassigned_tasks"] <= open_in_scope

    # regression — non-task counters
    def test_pending_approvals_and_expiring_passes(self, client, expected):
        d = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        assert d["pending_approvals"] == expected["pending_approvals"]
        assert d["expiring_passes"] == expected["expiring_passes"]


# ---------- stats ----------
class TestDashboardStats:
    def test_stats_200(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json().get("tasks_overdue"), int)

    def test_stats_overdue_matches_action_items(self, client):
        stats = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=60).json()
        items = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        assert stats["tasks_overdue"] == items["overdue_tasks"], (
            f"stats.tasks_overdue={stats['tasks_overdue']} != action-items.overdue_tasks={items['overdue_tasks']}")

    def test_stats_overdue_matches_db_scope(self, client, expected):
        stats = client.get(f"{BASE_URL}/api/dashboard/stats", timeout=60).json()
        assert stats["tasks_overdue"] == expected["overdue_tasks"]


# ---------- zero-board campus ----------
class TestEmptyBoardScope:
    """Scoping to a campus with no boards must return 0, not 500."""

    def test_campus_with_no_boards_returns_zero(self, client, mongo):
        empty_campus = None
        for loc in mongo.locations.find({}, {"_id": 0, "id": 1}):
            if mongo.boards.count_documents({"location_id": loc["id"], "is_archived": {"$ne": True}}) == 0:
                empty_campus = loc["id"]
                break
        if not empty_campus:
            pytest.skip("every location has at least one non-archived board")
        r = client.get(f"{BASE_URL}/api/dashboard/action-items", params={"campus_id": empty_campus}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["overdue_tasks"] == 0, d
        assert d["unassigned_tasks"] == 0, d
        s = client.get(f"{BASE_URL}/api/dashboard/stats", params={"campus_id": empty_campus}, timeout=60)
        assert s.status_code == 200, s.text[:300]
        assert s.json()["tasks_overdue"] == 0

    def test_nonexistent_campus_id_returns_zero(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/action-items",
                       params={"campus_id": "loc_does_not_exist_qa"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["overdue_tasks"] == 0 and d["unassigned_tasks"] == 0, d

    def test_unauthenticated_is_rejected(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60)
        assert r.status_code in (401, 403), f"expected auth error, got {r.status_code}"


# ---------- archived-board isolation ----------
class TestArchivedBoardIsolation:
    def test_archived_board_tasks_not_counted(self, client, mongo, expected):
        """Create a temp archived board + overdue unassigned task; counters must not move."""
        before = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        campus_loc = (mongo.users.find_one({"email": ADMIN_EMAIL}) or {}).get("active_campus_id") or "loc_001"
        board_id = "TEST_QA_board_iter93"
        task_id = "TEST_QA_task_iter93"
        mongo.boards.insert_one({"id": board_id, "name": "TEST_QA Archived Board", "location_id": campus_loc,
                                 "is_archived": True})
        mongo.tasks.insert_one({"id": task_id, "board_id": board_id, "title": "TEST_QA overdue orphan",
                                "status": "todo", "due_date": "2020-01-01", "assignees": []})
        try:
            after = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
            assert after["overdue_tasks"] == before["overdue_tasks"], (
                f"archived-board task leaked into overdue count: {before} -> {after}")
            assert after["unassigned_tasks"] == before["unassigned_tasks"], (
                f"archived-board task leaked into unassigned count: {before} -> {after}")
        finally:
            mongo.tasks.delete_one({"id": task_id})
            mongo.boards.delete_one({"id": board_id})

    def test_restricted_board_tasks_not_counted(self, client, mongo):
        """KNOWN GAP (iter 93): a restricted/private board is hidden by GET /api/boards,
        but its tasks still feed the dashboard overdue/unassigned counters."""
        before = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        campus_loc = (mongo.users.find_one({"email": ADMIN_EMAIL}) or {}).get("active_campus_id") or "loc_001"
        board_id = "TEST_QA_restricted_iter93"
        task_id = "TEST_QA_task_restricted_iter93"
        mongo.boards.insert_one({"id": board_id, "name": "TEST_QA Restricted Board", "location_id": campus_loc,
                                 "is_archived": False, "is_restricted": True, "tagged_members": [],
                                 "created_by": "not_the_admin"})
        mongo.tasks.insert_one({"id": task_id, "board_id": board_id, "title": "TEST_QA restricted overdue",
                                "status": "todo", "due_date": "2020-01-01", "assignees": []})
        try:
            visible = [b["id"] for b in client.get(f"{BASE_URL}/api/boards", timeout=60).json()]
            assert board_id not in visible, "restricted board unexpectedly visible via /api/boards"
            after = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
            assert after["overdue_tasks"] == before["overdue_tasks"], (
                f"task on a board hidden by /api/boards leaked into overdue count: {before} -> {after}")
            assert after["unassigned_tasks"] == before["unassigned_tasks"], (
                f"task on a board hidden by /api/boards leaked into unassigned count: {before} -> {after}")
        finally:
            mongo.tasks.delete_one({"id": task_id})
            mongo.boards.delete_one({"id": board_id})

    def test_other_campus_board_tasks_not_counted(self, client, mongo):
        """Active board on a different campus must not affect the current campus counters."""
        before = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
        board_id = "TEST_QA_board_iter93_other"
        task_id = "TEST_QA_task_iter93_other"
        mongo.boards.insert_one({"id": board_id, "name": "TEST_QA Other Campus Board",
                                 "location_id": "loc_qa_other_campus_iter93", "is_archived": False})
        mongo.tasks.insert_one({"id": task_id, "board_id": board_id, "title": "TEST_QA other campus overdue",
                                "status": "todo", "due_date": "2020-01-01", "assignees": []})
        try:
            after = client.get(f"{BASE_URL}/api/dashboard/action-items", timeout=60).json()
            assert after["overdue_tasks"] == before["overdue_tasks"], (
                f"other-campus task leaked into overdue count: {before} -> {after}")
            assert after["unassigned_tasks"] == before["unassigned_tasks"], (
                f"other-campus task leaked into unassigned count: {before} -> {after}")
        finally:
            mongo.tasks.delete_one({"id": task_id})
            mongo.boards.delete_one({"id": board_id})
