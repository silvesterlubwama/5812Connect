"""
Iteration 15 backend tests:
- POST /api/admin/users - create user, temp_password returned
- POST /api/admin/users/import - bulk user import
- POST /api/auth/visitor-register - visitor/parent guest registration with PIN
- GET /api/tasks/archived?board_id - archived tasks
- GET /api/boards/{id}/lists/archived - archived lists
- GET /api/admin/users - has_member_profile enrichment
- Locations API - timezone field persistence
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ---- Auth fixtures ----

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": "admin@5812uganda.org", "password": "Admin@5812"})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["token"]

@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

# ---- Test Board fixture ----

@pytest.fixture(scope="module")
def test_board_id(auth_headers):
    """Create a board for testing archive endpoints, clean up after module."""
    r = requests.post(f"{BASE_URL}/api/boards", json={"name": "TEST_Iter15_Board", "background": "#3b82f6"}, headers=auth_headers)
    assert r.status_code == 200, f"Board creation failed: {r.text}"
    board_id = r.json()["id"]
    yield board_id
    # Cleanup
    requests.delete(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)


# ---- AUTH TESTS ----

class TestVisitorRegister:
    """Test POST /api/auth/visitor-register"""

    def test_visitor_register_creates_user_with_pin(self):
        """Visitor register should create user and return PIN"""
        import uuid
        unique_phone = f"+25670{uuid.uuid4().hex[:7]}"
        payload = {"name": "TEST_Visitor_Jane", "phone": unique_phone, "role": "visitor"}
        r = requests.post(f"{BASE_URL}/api/auth/visitor-register", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "user" in data, "Response should have 'user'"
        assert "pin" in data, "Response should have 'pin' for new registrations"
        assert data["user"]["name"] == "TEST_Visitor_Jane"
        assert data["user"]["role"] == "visitor"
        assert len(data["pin"]) >= 4, f"PIN should be at least 4 chars, got: {data['pin']}"
        # Also has member_id (linked member record)
        assert "member_id" in data, "Response should have member_id"
        # Save phone for reuse
        TestVisitorRegister._test_phone = unique_phone

    def test_parent_register_creates_parent(self):
        """Parent guest registration should create parent role user"""
        import uuid
        unique_phone = f"+25671{uuid.uuid4().hex[:7]}"
        payload = {"name": "TEST_Parent_John", "phone": unique_phone, "role": "parent"}
        r = requests.post(f"{BASE_URL}/api/auth/visitor-register", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["user"]["role"] == "parent"
        assert "pin" in data

    def test_visitor_register_missing_name_returns_400(self):
        """Missing name should return 400"""
        r = requests.post(f"{BASE_URL}/api/auth/visitor-register", json={"phone": "+256700333777"})
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    def test_existing_phone_returns_existing_user(self):
        """Second registration with same phone should return existing user"""
        phone = getattr(TestVisitorRegister, '_test_phone', "+256700111999")
        payload = {"name": "TEST_Visitor_Repeat", "phone": phone, "role": "visitor"}
        r = requests.post(f"{BASE_URL}/api/auth/visitor-register", json=payload)
        assert r.status_code == 200
        data = r.json()
        # Should say existing=True
        assert data.get("existing") is True


# ---- ADMIN USER TESTS ----

class TestAdminCreateUser:
    """Test POST /api/admin/users"""

    def test_create_user_returns_temp_password(self, auth_headers):
        """Admin create user should return temp_password"""
        payload = {
            "name": "TEST_NewUser_Alice",
            "email": "TEST_alice_iter15@5812test.com",
            "role": "Staff",
            "phone": "+256700101010",
            "also_create_member": True
        }
        r = requests.post(f"{BASE_URL}/api/admin/users", json=payload, headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "id" in data, "Response should have 'id'"
        assert "temp_password" in data, "Response should have 'temp_password' - critical for admin to share"
        assert data["name"] == "TEST_NewUser_Alice"
        assert data["email"] == "test_alice_iter15@5812test.com"  # backend lowercases email
        assert data["role"] == "Staff"
        assert isinstance(data["temp_password"], str) and len(data["temp_password"]) > 0

    def test_create_user_with_member_profile(self, auth_headers):
        """With also_create_member=True, response should have has_member_profile=True"""
        payload = {
            "name": "TEST_NewUser_Bob",
            "email": "TEST_bob_iter15@5812test.com",
            "role": "Volunteer",
            "also_create_member": True
        }
        r = requests.post(f"{BASE_URL}/api/admin/users", json=payload, headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("has_member_profile") is True, "has_member_profile should be True when also_create_member=True"
        assert "member_id" in data, "member_id should be present"

    def test_create_user_duplicate_email_returns_400(self, auth_headers):
        """Duplicate email should return 400"""
        payload = {"name": "TEST Dupe", "email": "TEST_alice_iter15@5812test.com"}
        r = requests.post(f"{BASE_URL}/api/admin/users", json=payload, headers=auth_headers)
        assert r.status_code == 400, f"Expected 400 for duplicate, got {r.status_code}"

    def test_create_user_missing_fields_returns_400(self, auth_headers):
        """Missing name/email should return 400"""
        r = requests.post(f"{BASE_URL}/api/admin/users", json={"name": "OnlyName"}, headers=auth_headers)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"


class TestAdminImportUsers:
    """Test POST /api/admin/users/import"""

    def test_import_users_bulk(self, auth_headers):
        """Bulk import should create users and return created/skipped counts"""
        import uuid
        suffix = uuid.uuid4().hex[:6]
        users = [
            {"name": "TEST_Import_Carol", "email": f"TEST_carol_{suffix}@5812test.com", "role": "Staff"},
            {"name": "TEST_Import_Dave", "email": f"TEST_dave_{suffix}@5812test.com", "role": "Volunteer"},
        ]
        TestAdminImportUsers._import_emails = [u["email"] for u in users]
        r = requests.post(f"{BASE_URL}/api/admin/users/import", json={"users": users}, headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "created" in data, "Response should have 'created'"
        assert "skipped" in data, "Response should have 'skipped'"
        assert data["created"] >= 2, f"Expected at least 2 created, got {data['created']}"
        assert data["skipped"] == 0

    def test_import_duplicate_users_skipped(self, auth_headers):
        """Re-importing same emails should skip them"""
        emails = getattr(TestAdminImportUsers, '_import_emails', [])
        if not emails:
            pytest.skip("No import emails to test duplicate")
        users = [{"name": "TEST_Import_Carol", "email": emails[0], "role": "Staff"}]
        r = requests.post(f"{BASE_URL}/api/admin/users/import", json={"users": users}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["skipped"] >= 1, f"Expected at least 1 skipped for duplicate, got {data['skipped']}"

    def test_import_missing_name_creates_error(self, auth_headers):
        """Row without name/email should be listed in errors"""
        users = [{"name": "", "email": ""}]  # missing both
        r = requests.post(f"{BASE_URL}/api/admin/users/import", json={"users": users}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["skipped"] >= 1, "Should skip invalid row"
        assert len(data.get("errors", [])) > 0

    def test_import_no_users_returns_400(self, auth_headers):
        """Empty import should return 400"""
        r = requests.post(f"{BASE_URL}/api/admin/users/import", json={"users": []}, headers=auth_headers)
        assert r.status_code == 400, f"Expected 400 for empty import, got {r.status_code}"


class TestAdminUserList:
    """Test GET /api/admin/users - includes has_member_profile enrichment"""

    def test_list_users_returns_array(self, auth_headers):
        """Admin users list should return array with user objects"""
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Should have at least one user"

    def test_users_have_has_member_profile_field(self, auth_headers):
        """Users should have has_member_profile field for 'People' badge"""
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        # Every user should have has_member_profile field
        for u in data[:5]:  # Check first 5 users
            assert "has_member_profile" in u, f"User {u.get('name')} missing has_member_profile field"
            assert isinstance(u["has_member_profile"], bool), "has_member_profile should be boolean"

    def test_created_user_has_member_profile_true(self, auth_headers):
        """User created with also_create_member=True should show has_member_profile=True in list"""
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers, params={"search": "TEST_NewUser_Alice"})
        assert r.status_code == 200
        data = r.json()
        if data:
            user = data[0]
            assert user.get("has_member_profile") is True, "User created with also_create_member should have has_member_profile=True"


# ---- ARCHIVE/BOARDS TESTS ----

class TestArchivedTasks:
    """Test GET /api/tasks/archived?board_id"""

    def test_get_archived_tasks_for_board(self, auth_headers, test_board_id):
        """Should return archived tasks list for board"""
        r = requests.get(f"{BASE_URL}/api/tasks/archived", params={"board_id": test_board_id}, headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"

    def test_archived_tasks_are_archived(self, auth_headers, test_board_id):
        """Create a task, archive it, then verify it shows in archived endpoint"""
        # Create a task
        task_r = requests.post(f"{BASE_URL}/api/tasks", json={
            "title": "TEST_Archive_Task_Iter15",
            "board_id": test_board_id,
            "status": "todo"
        }, headers=auth_headers)
        assert task_r.status_code == 200, f"Task creation failed: {task_r.text}"
        task_id = task_r.json()["id"]

        # Archive it
        archive_r = requests.post(f"{BASE_URL}/api/tasks/{task_id}/archive", headers=auth_headers)
        assert archive_r.status_code == 200, f"Archive failed: {archive_r.text}"
        # Archive endpoint returns {'message': 'Card archived'} - verify task is now in archived list

        # Verify it's in archived list
        archived_r = requests.get(f"{BASE_URL}/api/tasks/archived", params={"board_id": test_board_id}, headers=auth_headers)
        assert archived_r.status_code == 200
        archived = archived_r.json()
        archived_ids = [t["id"] for t in archived]
        assert task_id in archived_ids, f"Archived task {task_id} not found in archived list"


class TestArchivedLists:
    """Test GET /api/boards/{id}/lists/archived"""

    def test_get_archived_lists_for_board(self, auth_headers, test_board_id):
        """Should return archived lists for board"""
        r = requests.get(f"{BASE_URL}/api/boards/{test_board_id}/lists/archived", headers=auth_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"

    def test_archived_list_shows_in_archived_endpoint(self, auth_headers, test_board_id):
        """Create a list, archive it, verify it shows in archived lists"""
        # Add a list
        list_r = requests.post(f"{BASE_URL}/api/boards/{test_board_id}/lists",
                                json={"name": "TEST_Archive_List_Iter15"}, headers=auth_headers)
        assert list_r.status_code == 200, f"List creation failed: {list_r.text}"
        list_id = list_r.json()["id"]

        # Archive the list
        archive_r = requests.post(f"{BASE_URL}/api/boards/{test_board_id}/lists/{list_id}/archive", headers=auth_headers)
        assert archive_r.status_code == 200, f"Archive list failed: {archive_r.text}"

        # Verify in archived
        archived_r = requests.get(f"{BASE_URL}/api/boards/{test_board_id}/lists/archived", headers=auth_headers)
        assert archived_r.status_code == 200
        archived = archived_r.json()
        archived_ids = [l["id"] for l in archived]
        assert list_id in archived_ids, f"Archived list {list_id} not in archived lists"


# ---- LOCATION TIMEZONE TEST ----

class TestLocationTimezone:
    """Test that timezone field is persisted in location create/update"""

    def test_create_location_with_timezone(self, auth_headers):
        """Creating a location with timezone should persist it"""
        payload = {
            "name": "TEST_Timezone_Location",
            "code": "TZL",
            "type": "compass",
            "currency": "UGX",
            "timezone": "Africa/Kampala"
        }
        r = requests.post(f"{BASE_URL}/api/locations", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"
        data = r.json()
        # Check timezone is returned
        assert data.get("timezone") == "Africa/Kampala", f"timezone not persisted: {data}"
        # Cleanup
        loc_id = data.get("id")
        if loc_id:
            requests.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers)


# ---- CLEANUP ----

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_users(auth_headers):
    yield
    # Delete test users created during tests
    test_emails = [
        "TEST_alice_iter15@5812test.com",
        "TEST_bob_iter15@5812test.com",
        "TEST_carol_import@5812test.com",
        "TEST_dave_import@5812test.com",
    ]
    for email in test_emails:
        r = requests.get(f"{BASE_URL}/api/admin/users", params={"search": email}, headers=auth_headers)
        if r.status_code == 200:
            for u in r.json():
                if u.get("email") == email:
                    requests.delete(f"{BASE_URL}/api/admin/users/{u['id']}", headers=auth_headers)
