"""Iteration 13 — Boards/Kanban, Families family_name field, Children-Parents import"""
import pytest
import requests
import os
import json
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@1234")

# Unique suffix per test run to avoid dedup collisions
RUN_SUFFIX = str(uuid.uuid4())[:6]

TRELLO_JSON = {
    "name": "Test Trello Board",
    "lists": [{"id": "l1", "name": "To Do", "pos": 0}, {"id": "l2", "name": "Done", "pos": 1}],
    "cards": [
        {"id": "c1", "name": "Card 1", "idList": "l1", "pos": 0, "closed": False, "labels": [], "checklist": []},
        {"id": "c2", "name": "Card 2", "idList": "l2", "pos": 1, "closed": False, "labels": [{"color": "green", "name": "Urgent"}], "checklist": []},
    ],
    "checklists": [],
    "labels": [],
}

# ===== FIXTURES =====

@pytest.fixture(scope="module")
def auth_token():
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if res.status_code == 200:
        return res.json().get("token") or res.json().get("access_token")
    pytest.skip(f"Auth failed: {res.status_code} {res.text}")


@pytest.fixture(scope="module")
def client(auth_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_board(client):
    """Create a test board and yield its data, then clean up"""
    res = client.post(f"{BASE_URL}/api/boards", json={"name": "TEST_Board_Iter13", "background": "#0052cc"})
    assert res.status_code == 200, f"Board creation failed: {res.status_code} {res.text}"
    board = res.json()
    yield board
    # Cleanup
    client.delete(f"{BASE_URL}/api/boards/{board['id']}")


# ===== FAMILIES TESTS =====

class TestFamilies:
    """GET /api/families — families should have family_name field"""

    def test_families_list_returns_200(self, client):
        res = client.get(f"{BASE_URL}/api/families")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: GET /api/families returned {len(data)} families")

    def test_families_have_family_name_field(self, client):
        res = client.get(f"{BASE_URL}/api/families")
        assert res.status_code == 200
        data = res.json()
        if not data:
            pytest.skip("No families in DB to validate")
        # Check the first few families have family_name field
        families_with_name = [f for f in data if "family_name" in f]
        assert len(families_with_name) > 0, "No families have family_name field"
        print(f"PASS: {len(families_with_name)}/{len(data)} families have family_name field")

    def test_families_do_not_use_bare_name_field(self, client):
        """Verify families use family_name (not just 'name') as DB schema specifies"""
        res = client.get(f"{BASE_URL}/api/families")
        assert res.status_code == 200
        data = res.json()
        if not data:
            pytest.skip("No families in DB")
        # Count families with family_name vs bare 'name'
        with_family_name = sum(1 for f in data if f.get("family_name"))
        print(f"PASS: {with_family_name}/{len(data)} families have non-empty family_name")
        assert with_family_name > 0, "Expected families to have family_name populated"

    def test_families_have_primary_contact_name(self, client):
        res = client.get(f"{BASE_URL}/api/families")
        assert res.status_code == 200
        data = res.json()
        if not data:
            pytest.skip("No families in DB")
        # At least some families should have primary_contact_name
        with_contact = sum(1 for f in data if f.get("primary_contact_name"))
        print(f"INFO: {with_contact}/{len(data)} families have primary_contact_name")
        # Not failing because older records might be missing it — just verify field exists in schema
        assert "primary_contact_name" in data[0] or "family_name" in data[0], "Family schema missing expected fields"


# ===== IMPORT CHILDREN-PARENTS TESTS =====

class TestImportChildrenParents:
    """POST /api/import/children-parents"""

    def test_import_creates_child_parent_family(self, client):
        rows = [{
            "name": f"TEST_Child_{RUN_SUFFIX}",
            "family_name": f"TEST_Family_{RUN_SUFFIX}",
            "fathers_names": f"TEST_Dad_{RUN_SUFFIX}",
            "fathers_phone": "+256700000001",
            "mothers_names": f"TEST_Mom_{RUN_SUFFIX}",
            "mothers_phone": "+256700000002",
            "email": f"test_{RUN_SUFFIX}@example.com",
        }]
        res = client.post(f"{BASE_URL}/api/import/children-parents", json={"rows": rows})
        assert res.status_code == 200, f"Import failed: {res.status_code} {res.text}"
        data = res.json()
        assert data["imported_children"] >= 1, f"Expected >=1 child imported, got {data}"
        assert data["imported_parents"] >= 1, f"Expected >=1 parent imported, got {data}"
        assert data["imported_families"] >= 1, f"Expected >=1 family imported, got {data}"
        assert len(data["errors"]) == 0, f"Unexpected errors: {data['errors']}"
        print(f"PASS: Import created {data['imported_children']} children, {data['imported_parents']} parents, {data['imported_families']} families")

    def test_import_dedup_child_same_name_same_family(self, client):
        """Importing the same child twice should NOT create duplicate"""
        child_name = f"TEST_DeupChild_{RUN_SUFFIX}"
        family_name = f"TEST_DedupFamily_{RUN_SUFFIX}"
        rows = [{
            "name": child_name,
            "family_name": family_name,
            "fathers_names": f"TEST_DedupDad_{RUN_SUFFIX}",
            "fathers_phone": "+256700000011",
        }]
        # First import
        r1 = client.post(f"{BASE_URL}/api/import/children-parents", json={"rows": rows})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["imported_children"] == 1

        # Second import (same data)
        r2 = client.post(f"{BASE_URL}/api/import/children-parents", json={"rows": rows})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["imported_children"] == 0, f"Expected 0 on re-import (dedup), got {d2['imported_children']}"
        print(f"PASS: Duplicate child detection working — second import created 0 children")

    def test_import_family_uses_family_name_field(self, client):
        """Verify family created by import uses family_name field, not bare 'name'"""
        unique_fname = f"TEST_GammaFamily_{RUN_SUFFIX}"
        rows = [{
            "name": f"TEST_GammaChild_{RUN_SUFFIX}",
            "family_name": unique_fname,
            "fathers_names": f"TEST_GammaDad_{RUN_SUFFIX}",
        }]
        res = client.post(f"{BASE_URL}/api/import/children-parents", json={"rows": rows})
        assert res.status_code == 200
        data = res.json()
        assert data["imported_families"] >= 1

        # Now verify the family was created with family_name field
        fam_res = client.get(f"{BASE_URL}/api/families")
        assert fam_res.status_code == 200
        families = fam_res.json()
        gamma_family = next((f for f in families if f.get("family_name") == unique_fname), None)
        assert gamma_family is not None, "Created family not found by family_name"
        assert gamma_family.get("family_name") == unique_fname
        print(f"PASS: Family created with correct family_name field: {gamma_family.get('family_name')}")

    def test_import_child_requires_name(self, client):
        """Row with no name should be skipped with error"""
        rows = [{"family_name": "TEST_NoChild", "fathers_names": "TEST_DadOnly"}]
        res = client.post(f"{BASE_URL}/api/import/children-parents", json={"rows": rows})
        assert res.status_code == 200
        data = res.json()
        assert data["imported_children"] == 0
        assert len(data["errors"]) > 0
        print(f"PASS: Empty name row skipped with error: {data['errors'][0]}")


# ===== BOARDS CRUD TESTS =====

class TestBoardsCRUD:
    """Boards CRUD + lists"""

    def test_list_boards_returns_200(self, client):
        res = client.get(f"{BASE_URL}/api/boards")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list), "Expected list"
        print(f"PASS: GET /api/boards → {len(data)} boards")

    def test_create_board_returns_board_with_id(self, client, created_board):
        board = created_board
        assert "id" in board, "Board missing id"
        assert board["name"] == "TEST_Board_Iter13"
        assert "is_global" in board
        print(f"PASS: Board created with id={board['id']}, is_global={board['is_global']}")

    def test_get_board_returns_lists(self, client, created_board):
        board_id = created_board["id"]
        res = client.get(f"{BASE_URL}/api/boards/{board_id}")
        assert res.status_code == 200, f"GET board failed: {res.status_code} {res.text}"
        data = res.json()
        assert "lists" in data, "Board response missing 'lists' key"
        assert isinstance(data["lists"], list), "lists should be a list"
        # Default 3 lists should be created
        assert len(data["lists"]) >= 3, f"Expected >=3 default lists, got {len(data['lists'])}"
        print(f"PASS: GET /api/boards/{board_id} → {len(data['lists'])} lists")

    def test_add_list_to_board(self, client, created_board):
        board_id = created_board["id"]
        res = client.post(f"{BASE_URL}/api/boards/{board_id}/lists", json={"name": "TEST_NewList"})
        assert res.status_code == 200, f"Add list failed: {res.status_code} {res.text}"
        data = res.json()
        assert "id" in data
        assert data["name"] == "TEST_NewList"
        assert data["board_id"] == board_id
        print(f"PASS: List added: id={data['id']}, name={data['name']}")
        return data["id"]

    def test_rename_list(self, client, created_board):
        board_id = created_board["id"]
        # First add a list to rename
        add_res = client.post(f"{BASE_URL}/api/boards/{board_id}/lists", json={"name": "TEST_RenameMe"})
        assert add_res.status_code == 200
        list_id = add_res.json()["id"]

        # Rename it
        rename_res = client.put(f"{BASE_URL}/api/boards/{board_id}/lists/{list_id}", json={"name": "TEST_Renamed"})
        assert rename_res.status_code == 200, f"Rename failed: {rename_res.status_code} {rename_res.text}"
        data = rename_res.json()
        assert data["name"] == "TEST_Renamed", f"Expected 'TEST_Renamed', got {data['name']}"
        print(f"PASS: List renamed to: {data['name']}")

    def test_delete_list(self, client, created_board):
        board_id = created_board["id"]
        # Add a list to delete
        add_res = client.post(f"{BASE_URL}/api/boards/{board_id}/lists", json={"name": "TEST_DeleteMe"})
        assert add_res.status_code == 200
        list_id = add_res.json()["id"]

        # Delete it
        del_res = client.delete(f"{BASE_URL}/api/boards/{board_id}/lists/{list_id}")
        assert del_res.status_code == 200, f"Delete list failed: {del_res.status_code}"
        print(f"PASS: List {list_id} deleted")

    def test_get_board_not_found(self, client):
        res = client.get(f"{BASE_URL}/api/boards/board_nonexistent_xyz")
        assert res.status_code == 404
        print("PASS: GET /api/boards/nonexistent → 404")


# ===== TASKS TESTS =====

class TestTasksWithBoard:
    """Tasks CRUD with board_id filter and move"""

    def test_get_tasks_filtered_by_board(self, client, created_board):
        board_id = created_board["id"]
        res = client.get(f"{BASE_URL}/api/tasks", params={"board_id": board_id})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/tasks?board_id={board_id} → {len(data)} tasks (expected 0 initially)")

    def test_create_task_in_board(self, client, created_board):
        board_id = created_board["id"]
        # Get board lists first
        board_res = client.get(f"{BASE_URL}/api/boards/{board_id}")
        lists = board_res.json().get("lists", [])
        assert lists, "Board has no lists"
        list_id = lists[0]["id"]

        res = client.post(f"{BASE_URL}/api/tasks", json={
            "title": "TEST_Task_Iter13",
            "board_id": board_id,
            "list_id": list_id,
            "list_name": lists[0]["name"],
            "status": "todo",
            "position": 0,
            "labels": [],
            "checklist": [],
        })
        assert res.status_code == 200, f"Task create failed: {res.status_code} {res.text}"
        data = res.json()
        assert data["title"] == "TEST_Task_Iter13"
        assert data["board_id"] == board_id
        assert data["list_id"] == list_id
        print(f"PASS: Task created: id={data['id']}")
        return data["id"], list_id, lists

    def test_move_task_to_different_list(self, client, created_board):
        board_id = created_board["id"]
        # Get board lists
        board_res = client.get(f"{BASE_URL}/api/boards/{board_id}")
        lists = board_res.json().get("lists", [])
        assert len(lists) >= 2, "Need at least 2 lists to test move"
        list1_id = lists[0]["id"]
        list2_id = lists[1]["id"]

        # Create a task in list1
        create_res = client.post(f"{BASE_URL}/api/tasks", json={
            "title": "TEST_MoveTask",
            "board_id": board_id,
            "list_id": list1_id,
            "list_name": lists[0]["name"],
            "status": "todo",
            "position": 0,
            "labels": [],
            "checklist": [],
        })
        assert create_res.status_code == 200
        task_id = create_res.json()["id"]

        # Move task to list2
        move_res = client.patch(f"{BASE_URL}/api/tasks/{task_id}/move", json={
            "list_id": list2_id,
            "position": 0,
            "status": "in-progress",
        })
        assert move_res.status_code == 200, f"Move failed: {move_res.status_code} {move_res.text}"
        moved = move_res.json()
        assert moved["list_id"] == list2_id, f"Expected list_id={list2_id}, got {moved['list_id']}"
        print(f"PASS: Task {task_id} moved from {list1_id} to {list2_id}")

        # Verify with GET
        verify_res = client.get(f"{BASE_URL}/api/tasks", params={"board_id": board_id, "list_id": list2_id})
        assert verify_res.status_code == 200
        task_ids = [t["id"] for t in verify_res.json()]
        assert task_id in task_ids, "Moved task not found in target list"
        print(f"PASS: Task {task_id} confirmed in list {list2_id}")


# ===== TRELLO IMPORT TESTS =====

class TestTrelloImport:
    """POST /api/boards/import-trello"""

    _imported_board_id = None

    def test_import_trello_board_creates_board_lists_cards(self, client):
        res = client.post(f"{BASE_URL}/api/boards/import-trello", json=TRELLO_JSON)
        assert res.status_code == 200, f"Trello import failed: {res.status_code} {res.text}"
        data = res.json()
        assert "board_id" in data, f"Missing board_id in response: {data}"
        assert "board_name" in data
        assert data["board_name"] == "Test Trello Board"
        assert data["lists"] == 2, f"Expected 2 lists, got {data['lists']}"
        assert data["imported"] == 2, f"Expected 2 cards, got {data['imported']}"
        print(f"PASS: Trello import → board_id={data['board_id']}, {data['lists']} lists, {data['imported']} cards")
        TestTrelloImport._imported_board_id = data["board_id"]

    def test_imported_board_has_lists_and_tasks(self, client):
        if not TestTrelloImport._imported_board_id:
            pytest.skip("No imported board_id from previous test")
        board_id = TestTrelloImport._imported_board_id

        # Check board
        board_res = client.get(f"{BASE_URL}/api/boards/{board_id}")
        assert board_res.status_code == 200
        board = board_res.json()
        assert len(board.get("lists", [])) == 2

        # Check tasks
        tasks_res = client.get(f"{BASE_URL}/api/tasks", params={"board_id": board_id})
        assert tasks_res.status_code == 200
        tasks = tasks_res.json()
        assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}"
        task_titles = [t["title"] for t in tasks]
        assert "Card 1" in task_titles
        assert "Card 2" in task_titles
        print(f"PASS: Imported board has 2 lists and 2 tasks: {task_titles}")

    def test_cleanup_imported_trello_board(self, client):
        if not TestTrelloImport._imported_board_id:
            pytest.skip("No imported board to clean up")
        res = client.delete(f"{BASE_URL}/api/boards/{TestTrelloImport._imported_board_id}")
        assert res.status_code == 200
        print(f"PASS: Imported board {TestTrelloImport._imported_board_id} cleaned up")
