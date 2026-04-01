"""
Iteration 16 Backend Tests - Edit Member & Admin Import Features
Tests for:
- GET /api/members - list members
- PUT /api/members/{id} - edit member (critical fix test)
- POST /api/admin/users/import - import users
- POST /api/admin/users - create user
- GET /api/admin/users/{id}/profile - full profile
- GET /api/boards - kanban boards
- GET /api/events - events list
- Auth login flow
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthLogin:
    """Test authentication flow"""
    
    def test_login_success(self):
        """Test login with valid admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        print(f"Login successful: {data['user']['name']}")
        return data["token"]


class TestMembersAPI:
    """Test Members CRUD operations - critical for edit member fix"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_list_members(self, auth_headers):
        """GET /api/members - list all members"""
        response = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
        assert response.status_code == 200, f"List members failed: {response.text}"
        data = response.json()
        assert "members" in data, "No members key in response"
        assert "total" in data, "No total key in response"
        print(f"Found {data['total']} members")
    
    def test_create_member(self, auth_headers):
        """POST /api/members - create a test member"""
        test_name = f"TEST_Iter16_Member_{uuid.uuid4().hex[:6]}"
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": test_name,
            "email": f"test_iter16_{uuid.uuid4().hex[:6]}@test.com",
            "phone": "+256700000016",
            "role": "Staff",
            "group": "Youth",
            "gender": "male"
        })
        assert response.status_code == 200, f"Create member failed: {response.text}"
        data = response.json()
        assert data["name"] == test_name, "Name mismatch"
        assert "id" in data, "No id in response"
        print(f"Created member: {data['id']}")
        return data["id"]
    
    def test_edit_member_critical(self, auth_headers):
        """PUT /api/members/{id} - CRITICAL: Test edit member functionality
        This is the main bug fix being tested - editing people produced an error
        """
        # First create a member to edit
        test_name = f"TEST_Edit_Iter16_{uuid.uuid4().hex[:6]}"
        create_response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": test_name,
            "email": f"edit_test_{uuid.uuid4().hex[:6]}@test.com",
            "phone": "+256700000017",
            "role": "Staff",
            "group": "Youth",
            "gender": "male"
        })
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"
        member_id = create_response.json()["id"]
        
        # Now edit the member - this is the critical test
        updated_name = f"UPDATED_{test_name}"
        edit_response = requests.put(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers, json={
            "name": updated_name,
            "phone": "+256700000018",
            "role": "Coordinator",
            "notes": "Updated via iteration 16 test"
        })
        assert edit_response.status_code == 200, f"CRITICAL: Edit member failed: {edit_response.text}"
        
        # Verify the update persisted
        get_response = requests.get(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        assert get_response.status_code == 200, f"Get member failed: {get_response.text}"
        data = get_response.json()
        assert data["name"] == updated_name, f"Name not updated: expected {updated_name}, got {data['name']}"
        assert data["role"] == "Coordinator", f"Role not updated: expected Coordinator, got {data['role']}"
        print(f"CRITICAL TEST PASSED: Edit member works correctly for {member_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        return member_id
    
    def test_get_member_detail(self, auth_headers):
        """GET /api/members/{id} - get member detail with checkin history"""
        # First get list to find a member
        list_response = requests.get(f"{BASE_URL}/api/members?limit=1", headers=auth_headers)
        assert list_response.status_code == 200
        members = list_response.json().get("members", [])
        if not members:
            pytest.skip("No members to test")
        
        member_id = members[0]["id"]
        response = requests.get(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        assert response.status_code == 200, f"Get member failed: {response.text}"
        data = response.json()
        assert "name" in data, "No name in response"
        assert "checkin_history" in data, "No checkin_history in response"
        print(f"Got member detail: {data['name']}")


class TestAdminAPI:
    """Test Admin user management - import users feature"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_list_users(self, auth_headers):
        """GET /api/admin/users - list all users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200, f"List users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} users")
    
    def test_create_user(self, auth_headers):
        """POST /api/admin/users - create new user"""
        test_email = f"test_create_iter16_{uuid.uuid4().hex[:6]}@test.com"
        response = requests.post(f"{BASE_URL}/api/admin/users", headers=auth_headers, json={
            "name": "TEST_Create_User_Iter16",
            "email": test_email,
            "phone": "+256700000019",
            "role": "Staff",
            "also_create_member": True
        })
        assert response.status_code == 200, f"Create user failed: {response.text}"
        data = response.json()
        assert "id" in data, "No id in response"
        assert "temp_password" in data, "No temp_password in response"
        assert data.get("has_member_profile") == True, "Member profile not created"
        print(f"Created user: {data['id']} with temp password")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/users/{data['id']}", headers=auth_headers)
        return data["id"]
    
    def test_import_users_critical(self, auth_headers):
        """POST /api/admin/users/import - CRITICAL: Test import users functionality
        This is the second main feature being tested - importation in User Administration
        """
        test_users = [
            {
                "name": f"TEST_Import_User1_Iter16_{uuid.uuid4().hex[:4]}",
                "email": f"import1_iter16_{uuid.uuid4().hex[:6]}@test.com",
                "role": "Staff",
                "phone": "+256700000020"
            },
            {
                "name": f"TEST_Import_User2_Iter16_{uuid.uuid4().hex[:4]}",
                "email": f"import2_iter16_{uuid.uuid4().hex[:6]}@test.com",
                "role": "Volunteer",
                "phone": "+256700000021"
            }
        ]
        
        response = requests.post(f"{BASE_URL}/api/admin/users/import", headers=auth_headers, json={
            "users": test_users
        })
        assert response.status_code == 200, f"CRITICAL: Import users failed: {response.text}"
        data = response.json()
        assert "created" in data, "No created count in response"
        assert "skipped" in data, "No skipped count in response"
        assert data["created"] >= 1, f"Expected at least 1 user created, got {data['created']}"
        print(f"CRITICAL TEST PASSED: Import users works - created: {data['created']}, skipped: {data['skipped']}")
        
        # Cleanup - find and delete test users
        users_response = requests.get(f"{BASE_URL}/api/admin/users?search=TEST_Import", headers=auth_headers)
        if users_response.status_code == 200:
            for user in users_response.json():
                if "TEST_Import" in user.get("name", ""):
                    requests.delete(f"{BASE_URL}/api/admin/users/{user['id']}", headers=auth_headers)
    
    def test_get_user_full_profile(self, auth_headers):
        """GET /api/admin/users/{id}/profile - get full user profile"""
        # First get list to find a user
        list_response = requests.get(f"{BASE_URL}/api/admin/users?limit=1", headers=auth_headers)
        assert list_response.status_code == 200
        users = list_response.json()
        if not users:
            pytest.skip("No users to test")
        
        user_id = users[0]["id"]
        response = requests.get(f"{BASE_URL}/api/admin/users/{user_id}/profile", headers=auth_headers)
        assert response.status_code == 200, f"Get user profile failed: {response.text}"
        data = response.json()
        assert "name" in data, "No name in response"
        print(f"Got user profile: {data['name']}")


class TestBoardsAPI:
    """Test Kanban boards API"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_list_boards(self, auth_headers):
        """GET /api/boards - list all boards"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert response.status_code == 200, f"List boards failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} boards")


class TestEventsAPI:
    """Test Events API"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_list_events(self, auth_headers):
        """GET /api/events - list all events"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        assert response.status_code == 200, f"List events failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} events")


class TestDashboardAPI:
    """Test Dashboard API"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_dashboard_stats(self, auth_headers):
        """GET /api/dashboard/stats - get dashboard statistics"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        print(f"Dashboard stats: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
