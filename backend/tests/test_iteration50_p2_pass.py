"""
Iteration 50 - P2 Pass Testing
Tests for code quality improvements:
1. Backend type hints verification (auth, members, events, tasks, admin, locations)
2. API endpoint functionality verification
"""
import pytest
import requests
import os

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


class TestAuthEndpoints:
    """Test auth endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_login_success(self):
        """POST /api/auth/login - returns dict with token and user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "user" in data, "Response should contain user"
        assert isinstance(data["token"], str)
        assert isinstance(data["user"], dict)
        assert data["user"]["email"] == ADMIN_EMAIL
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login - returns 401 for invalid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_auth_me(self):
        """GET /api/auth/me - returns dict with user info"""
        # First login
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json().get("token")
        
        # Then get me
        response = self.session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert data["email"] == ADMIN_EMAIL


class TestMembersEndpoints:
    """Test members endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login to get token
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_members(self):
        """GET /api/members - returns dict with members list"""
        response = self.session.get(f"{BASE_URL}/api/members")
        assert response.status_code == 200
        data = response.json()
        assert "members" in data, "Response should contain members key"
        assert "total" in data, "Response should contain total key"
        assert isinstance(data["members"], list)
        assert isinstance(data["total"], int)
    
    def test_create_and_get_member(self):
        """POST /api/members and GET /api/members/{id} - CRUD verification"""
        # Create member with unique identifiers
        unique_id = os.urandom(4).hex()
        create_payload = {
            "name": f"TEST_P2_Member_{unique_id}",
            "email": f"test_p2_{unique_id}@test.com",
            "phone": f"+256799{unique_id[:6]}",
            "role": "Member",
            "group": "General"
        }
        create_res = self.session.post(f"{BASE_URL}/api/members", json=create_payload)
        assert create_res.status_code == 200, f"Create failed: {create_res.text}"
        created = create_res.json()
        assert "id" in created
        assert created["name"] == create_payload["name"]
        
        member_id = created["id"]
        
        # Get member
        get_res = self.session.get(f"{BASE_URL}/api/members/{member_id}")
        assert get_res.status_code == 200
        fetched = get_res.json()
        assert fetched["id"] == member_id
        assert fetched["name"] == create_payload["name"]
        
        # Cleanup - delete member
        del_res = self.session.delete(f"{BASE_URL}/api/members/{member_id}")
        assert del_res.status_code == 200


class TestEventsEndpoints:
    """Test events endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_events(self):
        """GET /api/events - returns list of events"""
        response = self.session.get(f"{BASE_URL}/api/events")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Events should return a list"
    
    def test_list_event_types(self):
        """GET /api/event-types - returns list of event types"""
        response = self.session.get(f"{BASE_URL}/api/event-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_and_delete_event(self):
        """POST /api/events and DELETE /api/events/{id} - CRUD verification"""
        create_payload = {
            "title": "TEST_P2_Event",
            "type": "meeting",
            "date": "2026-02-15",
            "time": "10:00",
            "location": "Test Location",
            "capacity": 50,
            "is_public": False
        }
        create_res = self.session.post(f"{BASE_URL}/api/events", json=create_payload)
        assert create_res.status_code == 200, f"Create failed: {create_res.text}"
        created = create_res.json()
        assert "id" in created
        assert created["title"] == create_payload["title"]
        
        event_id = created["id"]
        
        # Get event
        get_res = self.session.get(f"{BASE_URL}/api/events/{event_id}")
        assert get_res.status_code == 200
        fetched = get_res.json()
        assert fetched["id"] == event_id
        
        # Delete event
        del_res = self.session.delete(f"{BASE_URL}/api/events/{event_id}")
        assert del_res.status_code == 200


class TestTasksEndpoints:
    """Test tasks endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_tasks(self):
        """GET /api/tasks - returns list of tasks"""
        response = self.session.get(f"{BASE_URL}/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Tasks should return a list"
    
    def test_create_update_delete_task(self):
        """POST, PUT, DELETE /api/tasks - CRUD verification"""
        # Create task
        create_payload = {
            "title": "TEST_P2_Task",
            "description": "Test task for P2 pass",
            "status": "todo",
            "priority": "medium"
        }
        create_res = self.session.post(f"{BASE_URL}/api/tasks", json=create_payload)
        assert create_res.status_code == 200, f"Create failed: {create_res.text}"
        created = create_res.json()
        assert "id" in created
        assert created["title"] == create_payload["title"]
        
        task_id = created["id"]
        
        # Update task
        update_res = self.session.put(f"{BASE_URL}/api/tasks/{task_id}", json={
            "title": "TEST_P2_Task_Updated",
            "status": "in-progress"
        })
        assert update_res.status_code == 200
        updated = update_res.json()
        assert updated["title"] == "TEST_P2_Task_Updated"
        
        # Delete task
        del_res = self.session.delete(f"{BASE_URL}/api/tasks/{task_id}")
        assert del_res.status_code == 200


class TestAdminEndpoints:
    """Test admin endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_admin_users(self):
        """GET /api/admin/users - returns list of users"""
        response = self.session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Admin users should return a list"
    
    def test_get_audit_log(self):
        """GET /api/admin/audit - returns dict with logs"""
        response = self.session.get(f"{BASE_URL}/api/admin/audit")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data


class TestLocationsEndpoints:
    """Test locations endpoints with type hints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_locations(self):
        """GET /api/locations - returns list of locations"""
        response = self.session.get(f"{BASE_URL}/api/locations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Locations should return a list"
    
    def test_exchange_rate(self):
        """GET /api/exchange-rate - returns exchange rate dict"""
        response = self.session.get(f"{BASE_URL}/api/exchange-rate?from_currency=UGX&to_currency=USD")
        assert response.status_code == 200
        data = response.json()
        assert "from" in data
        assert "to" in data
        assert "rate" in data


class TestCheckinsEndpoints:
    """Test checkins endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_list_checkins(self):
        """GET /api/checkins - returns list of checkins"""
        response = self.session.get(f"{BASE_URL}/api/checkins")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Checkins should return a list"
    
    def test_checkin_stats(self):
        """GET /api/checkins/stats - returns stats dict"""
        response = self.session.get(f"{BASE_URL}/api/checkins/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "today" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
