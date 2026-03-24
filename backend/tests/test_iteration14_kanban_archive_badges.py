"""
Iteration 14 — Tests for new Kanban features:
- Archive/Restore for tasks (cards) and lists
- GET /api/tasks/archived
- POST /api/tasks/{id}/archive
- POST /api/tasks/{id}/restore
- POST /api/boards/{id}/lists/{id}/archive
- POST /api/boards/{id}/lists/{id}/restore
- GET /api/boards/{id}/lists/archived
- CRUD: GET /api/boards, POST /api/boards, GET /api/tasks?board_id
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": "Admin@5812"
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} - {resp.text[:200]}")
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in response: {data}")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# =================== AUTH ===================

class TestAuth:
    """Authentication tests"""

    def test_login_success(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert resp.status_code == 200, f"Login failed: {resp.text[:300]}"
        data = resp.json()
        assert "access_token" in data or "token" in data, f"No token in: {data}"
        print("PASS: Login success")

    def test_get_me(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        print(f"PASS: /auth/me => user id={data.get('id')}, role={data.get('role')}")


# =================== BOARDS ===================

class TestBoards:
    """Board CRUD and archive features"""

    board_id = None
    list_id = None
    task_id = None
    archived_list_id = None

    def test_list_boards(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert resp.status_code == 200, f"GET /api/boards failed: {resp.text[:200]}"
        data = resp.json()
        assert isinstance(data, list), "Boards should be a list"
        print(f"PASS: GET /api/boards => {len(data)} boards found")

    def test_create_board(self, auth_headers):
        unique = str(uuid.uuid4())[:8]
        resp = requests.post(f"{BASE_URL}/api/boards", headers=auth_headers, json={
            "name": f"TEST_Board_Iter14_{unique}",
            "background": "#3b82f6",
            "default_lists": ["To Do", "In Progress", "Done"]
        })
        assert resp.status_code == 200, f"POST /api/boards failed: {resp.text[:300]}"
        data = resp.json()
        assert "id" in data
        assert data["name"].startswith("TEST_Board_Iter14")
        TestBoards.board_id = data["id"]
        print(f"PASS: Board created: {data['id']}")

    def test_get_board(self, auth_headers):
        assert TestBoards.board_id, "Need board_id from create test"
        resp = requests.get(f"{BASE_URL}/api/boards/{TestBoards.board_id}", headers=auth_headers)
        assert resp.status_code == 200, f"GET board failed: {resp.text[:200]}"
        data = resp.json()
        assert "lists" in data, "Board should have lists array"
        assert len(data["lists"]) == 3, f"Expected 3 default lists, got {len(data['lists'])}"
        TestBoards.list_id = data["lists"][0]["id"]
        print(f"PASS: GET board => {len(data['lists'])} lists, first list_id={TestBoards.list_id}")

    def test_add_list_to_board(self, auth_headers):
        assert TestBoards.board_id, "Need board_id"
        unique = str(uuid.uuid4())[:8]
        resp = requests.post(f"{BASE_URL}/api/boards/{TestBoards.board_id}/lists",
                             headers=auth_headers,
                             json={"name": f"TEST_List_{unique}"})
        assert resp.status_code == 200, f"Add list failed: {resp.text[:200]}"
        data = resp.json()
        assert "id" in data
        # Save for archive test
        TestBoards.archived_list_id = data["id"]
        print(f"PASS: List added: {data['id']}")

    def test_create_task_on_board(self, auth_headers):
        assert TestBoards.board_id and TestBoards.list_id, "Need board and list"
        resp = requests.post(f"{BASE_URL}/api/tasks", headers=auth_headers, json={
            "title": "TEST_Card_Iter14",
            "board_id": TestBoards.board_id,
            "list_id": TestBoards.list_id,
            "list_name": "To Do",
            "status": "todo",
            "position": 0,
            "assignees": [],
            "labels": [],
            "checklist": [],
            "attachments": [],
        })
        assert resp.status_code == 200, f"Create task failed: {resp.text[:300]}"
        data = resp.json()
        assert "id" in data
        TestBoards.task_id = data["id"]
        print(f"PASS: Task created: {data['id']}")

    def test_get_tasks_by_board_id(self, auth_headers):
        assert TestBoards.board_id and TestBoards.task_id, "Need board and task"
        resp = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers,
                            params={"board_id": TestBoards.board_id})
        assert resp.status_code == 200, f"GET tasks by board_id failed: {resp.text[:200]}"
        data = resp.json()
        assert isinstance(data, list)
        ids = [t["id"] for t in data]
        assert TestBoards.task_id in ids, f"Created task {TestBoards.task_id} not found in board tasks"
        print(f"PASS: GET /api/tasks?board_id => {len(data)} tasks, contains our test task")


# =================== ARCHIVE/RESTORE TASKS ===================

class TestTaskArchiveRestore:
    """Archive and restore task (card) flows"""

    def test_archive_task(self, auth_headers):
        assert TestBoards.task_id, "Need task_id"
        resp = requests.post(f"{BASE_URL}/api/tasks/{TestBoards.task_id}/archive",
                             headers=auth_headers)
        assert resp.status_code == 200, f"Archive task failed: {resp.text[:300]}"
        data = resp.json()
        assert "message" in data or data.get("is_archived") == True
        print(f"PASS: Task {TestBoards.task_id} archived")

    def test_task_not_in_active_list_after_archive(self, auth_headers):
        assert TestBoards.board_id and TestBoards.task_id, "Need board and task"
        resp = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers,
                            params={"board_id": TestBoards.board_id})
        assert resp.status_code == 200
        data = resp.json()
        ids = [t["id"] for t in data]
        assert TestBoards.task_id not in ids, "Archived task should not appear in active task list"
        print("PASS: Archived task not in active task list")

    def test_get_archived_tasks(self, auth_headers):
        assert TestBoards.board_id and TestBoards.task_id, "Need board and task"
        resp = requests.get(f"{BASE_URL}/api/tasks/archived", headers=auth_headers,
                            params={"board_id": TestBoards.board_id})
        assert resp.status_code == 200, f"GET archived tasks failed: {resp.text[:300]}"
        data = resp.json()
        assert isinstance(data, list)
        ids = [t["id"] for t in data]
        assert TestBoards.task_id in ids, f"Task {TestBoards.task_id} should be in archived list"
        print(f"PASS: GET /api/tasks/archived => {len(data)} archived tasks, contains our test task")

    def test_restore_task(self, auth_headers):
        assert TestBoards.task_id, "Need task_id"
        resp = requests.post(f"{BASE_URL}/api/tasks/{TestBoards.task_id}/restore",
                             headers=auth_headers)
        assert resp.status_code == 200, f"Restore task failed: {resp.text[:300]}"
        data = resp.json()
        assert data.get("is_archived") == False, f"Restored task should have is_archived=False, got: {data}"
        print(f"PASS: Task {TestBoards.task_id} restored")

    def test_task_back_in_active_list_after_restore(self, auth_headers):
        assert TestBoards.board_id and TestBoards.task_id, "Need board and task"
        resp = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers,
                            params={"board_id": TestBoards.board_id})
        assert resp.status_code == 200
        data = resp.json()
        ids = [t["id"] for t in data]
        assert TestBoards.task_id in ids, "Restored task should be back in active tasks"
        print("PASS: Restored task is back in active task list")

    def test_archive_nonexistent_task_returns_404(self, auth_headers):
        fake_id = "task_00000000"
        resp = requests.post(f"{BASE_URL}/api/tasks/{fake_id}/archive",
                             headers=auth_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:200]}"
        print("PASS: Archive nonexistent task returns 404")


# =================== ARCHIVE/RESTORE LISTS ===================

class TestListArchiveRestore:
    """Archive and restore list flows"""

    def test_archive_list(self, auth_headers):
        board_id = TestBoards.board_id
        list_id = TestBoards.archived_list_id
        assert board_id and list_id, "Need board_id and archived_list_id"
        resp = requests.post(f"{BASE_URL}/api/boards/{board_id}/lists/{list_id}/archive",
                             headers=auth_headers)
        assert resp.status_code == 200, f"Archive list failed: {resp.text[:300]}"
        data = resp.json()
        assert "message" in data
        print(f"PASS: List {list_id} archived")

    def test_archived_list_not_in_board_lists(self, auth_headers):
        board_id = TestBoards.board_id
        list_id = TestBoards.archived_list_id
        assert board_id and list_id
        resp = requests.get(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        active_list_ids = [l["id"] for l in data.get("lists", [])]
        assert list_id not in active_list_ids, "Archived list should not appear in active board lists"
        print("PASS: Archived list not in active board lists")

    def test_get_archived_lists(self, auth_headers):
        board_id = TestBoards.board_id
        list_id = TestBoards.archived_list_id
        assert board_id and list_id
        resp = requests.get(f"{BASE_URL}/api/boards/{board_id}/lists/archived",
                            headers=auth_headers)
        assert resp.status_code == 200, f"GET archived lists failed: {resp.text[:300]}"
        data = resp.json()
        assert isinstance(data, list)
        ids = [l["id"] for l in data]
        assert list_id in ids, f"List {list_id} should be in archived lists"
        print(f"PASS: GET /api/boards/{{id}}/lists/archived => {len(data)} archived lists")

    def test_restore_list(self, auth_headers):
        board_id = TestBoards.board_id
        list_id = TestBoards.archived_list_id
        assert board_id and list_id
        resp = requests.post(f"{BASE_URL}/api/boards/{board_id}/lists/{list_id}/restore",
                             headers=auth_headers)
        assert resp.status_code == 200, f"Restore list failed: {resp.text[:300]}"
        data = resp.json()
        assert data.get("is_archived") == False, f"Restored list should have is_archived=False, got: {data}"
        print(f"PASS: List {list_id} restored")

    def test_restored_list_in_board_lists(self, auth_headers):
        board_id = TestBoards.board_id
        list_id = TestBoards.archived_list_id
        assert board_id and list_id
        resp = requests.get(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        active_list_ids = [l["id"] for l in data.get("lists", [])]
        assert list_id in active_list_ids, "Restored list should be back in board lists"
        print("PASS: Restored list is back in active board lists")


# =================== CLEANUP ===================

class TestCleanup:
    """Cleanup test data"""

    def test_delete_task(self, auth_headers):
        if not TestBoards.task_id:
            pytest.skip("No task to delete")
        resp = requests.delete(f"{BASE_URL}/api/tasks/{TestBoards.task_id}",
                               headers=auth_headers)
        assert resp.status_code in [200, 404], f"Delete task failed: {resp.text[:200]}"
        print(f"PASS: Task {TestBoards.task_id} deleted")

    def test_delete_board(self, auth_headers):
        if not TestBoards.board_id:
            pytest.skip("No board to delete")
        resp = requests.delete(f"{BASE_URL}/api/boards/{TestBoards.board_id}",
                               headers=auth_headers)
        assert resp.status_code == 200, f"Delete board failed: {resp.text[:200]}"
        print(f"PASS: Board {TestBoards.board_id} deleted")
