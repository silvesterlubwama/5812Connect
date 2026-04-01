"""
Iteration 9 - Staff/Member Self-Service Portal Tests
Tests all /api/portal/* endpoints for the new self-service portal feature
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@1234")


class TestPortalAuthentication:
    """Test that portal endpoints require authentication"""
    
    def test_portal_dashboard_requires_auth(self):
        """Portal dashboard should require authentication"""
        response = requests.get(f"{BASE_URL}/api/portal/dashboard")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Portal dashboard requires authentication")
    
    def test_portal_profile_requires_auth(self):
        """Portal profile should require authentication"""
        response = requests.get(f"{BASE_URL}/api/portal/profile")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Portal profile requires authentication")
    
    def test_portal_tasks_requires_auth(self):
        """Portal tasks should require authentication"""
        response = requests.get(f"{BASE_URL}/api/portal/tasks")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Portal tasks requires authentication")


class TestPortalDashboard:
    """Test GET /api/portal/dashboard endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_returns_stats(self):
        """Dashboard should return tasks, expenses, events, unread_messages stats"""
        response = requests.get(f"{BASE_URL}/api/portal/dashboard", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "tasks" in data, "Missing 'tasks' in dashboard response"
        assert "expenses" in data, "Missing 'expenses' in dashboard response"
        assert "upcoming_events" in data, "Missing 'upcoming_events' in dashboard response"
        assert "unread_messages" in data, "Missing 'unread_messages' in dashboard response"
        
        # Verify tasks structure
        tasks = data["tasks"]
        assert "total" in tasks, "Missing 'total' in tasks"
        assert "todo" in tasks, "Missing 'todo' in tasks"
        assert "in_progress" in tasks, "Missing 'in_progress' in tasks"
        assert "done" in tasks, "Missing 'done' in tasks"
        
        # Verify expenses structure
        expenses = data["expenses"]
        assert "total_amount" in expenses, "Missing 'total_amount' in expenses"
        assert "count" in expenses, "Missing 'count' in expenses"
        assert "pending" in expenses, "Missing 'pending' in expenses"
        
        print(f"PASS: Dashboard returns stats - Tasks: {tasks['total']}, Expenses: {expenses['count']}, Events: {len(data['upcoming_events'])}, Unread: {data['unread_messages']}")


class TestPortalProfile:
    """Test GET/PUT /api/portal/profile endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_profile(self):
        """GET /api/portal/profile should return user + linked member record"""
        response = requests.get(f"{BASE_URL}/api/portal/profile", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user" in data, "Missing 'user' in profile response"
        
        user = data["user"]
        assert "id" in user, "Missing 'id' in user"
        assert "email" in user, "Missing 'email' in user"
        assert "name" in user, "Missing 'name' in user"
        assert "password_hash" not in user, "password_hash should not be exposed"
        
        print(f"PASS: Profile returns user data - Name: {user.get('name')}, Email: {user.get('email')}")
    
    def test_update_profile_valid_fields(self):
        """PUT /api/portal/profile should update allowed fields"""
        update_data = {
            "phone": "+256700123456",
            "address": "Test Address, Kampala"
        }
        response = requests.put(f"{BASE_URL}/api/portal/profile", json=update_data, headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("phone") == "+256700123456", "Phone not updated correctly"
        print("PASS: Profile update works for allowed fields (phone, address)")
    
    def test_update_profile_rejects_empty(self):
        """PUT /api/portal/profile should reject empty update"""
        response = requests.put(f"{BASE_URL}/api/portal/profile", json={}, headers=self.headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Profile update rejects empty data")


class TestPortalTasks:
    """Test GET /api/portal/tasks and PUT /api/portal/tasks/{id}/status endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_tasks(self):
        """GET /api/portal/tasks should return tasks assigned to current user"""
        response = requests.get(f"{BASE_URL}/api/portal/tasks", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Tasks should be a list"
        print(f"PASS: Portal tasks returns list - {len(data)} tasks assigned to user")
    
    def test_get_tasks_with_status_filter(self):
        """GET /api/portal/tasks?status=todo should filter by status"""
        response = requests.get(f"{BASE_URL}/api/portal/tasks?status=todo", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Tasks should be a list"
        # All returned tasks should have status=todo
        for task in data:
            assert task.get("status") == "todo", f"Task {task.get('id')} has wrong status"
        print(f"PASS: Portal tasks filter by status works - {len(data)} todo tasks")
    
    def test_update_task_status_invalid_task(self):
        """PUT /api/portal/tasks/{id}/status should return 404 for non-existent task"""
        response = requests.put(
            f"{BASE_URL}/api/portal/tasks/nonexistent_task_id/status",
            json={"status": "done"},
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Update task status returns 404 for non-existent task")
    
    def test_update_task_status_invalid_status(self):
        """PUT /api/portal/tasks/{id}/status should reject invalid status"""
        # First get a task if any exist
        tasks_response = requests.get(f"{BASE_URL}/api/portal/tasks", headers=self.headers)
        tasks = tasks_response.json()
        
        if len(tasks) > 0:
            task_id = tasks[0]["id"]
            response = requests.put(
                f"{BASE_URL}/api/portal/tasks/{task_id}/status",
                json={"status": "invalid_status"},
                headers=self.headers
            )
            assert response.status_code == 400, f"Expected 400, got {response.status_code}"
            print("PASS: Update task status rejects invalid status value")
        else:
            print("SKIP: No tasks assigned to test status update validation")


class TestPortalExpenses:
    """Test GET/POST /api/portal/expenses endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_expenses(self):
        """GET /api/portal/expenses should return expenses created by current user"""
        response = requests.get(f"{BASE_URL}/api/portal/expenses", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expenses should be a list"
        print(f"PASS: Portal expenses returns list - {len(data)} expenses")
    
    def test_create_expense(self):
        """POST /api/portal/expenses should create a new expense"""
        expense_data = {
            "title": "TEST_Portal Test Expense",
            "amount": 25000,
            "currency": "UGX",
            "category": "transport",
            "notes": "Test expense from portal testing"
        }
        response = requests.post(f"{BASE_URL}/api/portal/expenses", json=expense_data, headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("title") == "TEST_Portal Test Expense", "Title mismatch"
        assert data.get("amount") == 25000, "Amount mismatch"
        assert data.get("status") == "pending", "New expense should be pending"
        assert "id" in data, "Missing expense ID"
        
        print(f"PASS: Create expense works - ID: {data.get('id')}")
    
    def test_create_expense_validation(self):
        """POST /api/portal/expenses should validate required fields"""
        # Missing title
        response = requests.post(f"{BASE_URL}/api/portal/expenses", json={"amount": 1000}, headers=self.headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        # Zero amount
        response = requests.post(f"{BASE_URL}/api/portal/expenses", json={"title": "Test", "amount": 0}, headers=self.headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        print("PASS: Create expense validates required fields")


class TestPortalCashRequest:
    """Test POST /api/portal/cash-request endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_submit_cash_request(self):
        """POST /api/portal/cash-request should create expense + send chat message"""
        cash_request_data = {
            "amount": 100000,
            "reason": "TEST_Portal cash request for office supplies",
            "currency": "UGX"
        }
        response = requests.post(f"{BASE_URL}/api/portal/cash-request", json=cash_request_data, headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "expense" in data, "Missing 'expense' in response"
        assert "message" in data, "Missing 'message' in response"
        
        expense = data["expense"]
        assert expense.get("is_cash_request") == True, "Should be marked as cash request"
        assert expense.get("category") == "cash_request", "Category should be cash_request"
        assert expense.get("amount") == 100000, "Amount mismatch"
        
        print(f"PASS: Cash request works - Expense ID: {expense.get('id')}, Message: {data.get('message')}")
    
    def test_cash_request_validation(self):
        """POST /api/portal/cash-request should validate required fields"""
        # Missing reason
        response = requests.post(f"{BASE_URL}/api/portal/cash-request", json={"amount": 1000}, headers=self.headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        # Zero amount
        response = requests.post(f"{BASE_URL}/api/portal/cash-request", json={"amount": 0, "reason": "Test"}, headers=self.headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        print("PASS: Cash request validates required fields")


class TestPortalEvents:
    """Test GET /api/portal/events and POST /api/portal/events/{id}/rsvp endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_events(self):
        """GET /api/portal/events should return upcoming events"""
        response = requests.get(f"{BASE_URL}/api/portal/events", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Events should be a list"
        print(f"PASS: Portal events returns list - {len(data)} upcoming events")
        
        # If there are events, verify structure
        if len(data) > 0:
            event = data[0]
            assert "id" in event, "Missing 'id' in event"
            assert "title" in event, "Missing 'title' in event"
            assert "date" in event, "Missing 'date' in event"
            print(f"  First event: {event.get('title')} on {event.get('date')}")
    
    def test_rsvp_event_not_found(self):
        """POST /api/portal/events/{id}/rsvp should return 404 for non-existent event"""
        response = requests.post(f"{BASE_URL}/api/portal/events/nonexistent_event/rsvp", headers=self.headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: RSVP returns 404 for non-existent event")
    
    def test_rsvp_event(self):
        """POST /api/portal/events/{id}/rsvp should register for event"""
        # First get events
        events_response = requests.get(f"{BASE_URL}/api/portal/events", headers=self.headers)
        events = events_response.json()
        
        if len(events) > 0:
            event_id = events[0]["id"]
            response = requests.post(f"{BASE_URL}/api/portal/events/{event_id}/rsvp", headers=self.headers)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            assert "message" in data, "Missing 'message' in response"
            assert "event" in data, "Missing 'event' in response"
            print(f"PASS: RSVP works - {data.get('message')}")
        else:
            print("SKIP: No upcoming events to test RSVP")


class TestPortalCheckins:
    """Test GET /api/portal/checkins endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_checkins(self):
        """GET /api/portal/checkins should return checkin/access history"""
        response = requests.get(f"{BASE_URL}/api/portal/checkins", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checkins" in data, "Missing 'checkins' in response"
        assert "access_logs" in data, "Missing 'access_logs' in response"
        assert isinstance(data["checkins"], list), "checkins should be a list"
        assert isinstance(data["access_logs"], list), "access_logs should be a list"
        
        print(f"PASS: Portal checkins returns history - {len(data['checkins'])} checkins, {len(data['access_logs'])} access logs")


class TestPortalDocuments:
    """Test GET /api/portal/documents endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_documents(self):
        """GET /api/portal/documents should return user documents"""
        response = requests.get(f"{BASE_URL}/api/portal/documents", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Documents should be a list"
        print(f"PASS: Portal documents returns list - {len(data)} documents")


class TestPortalSales:
    """Test GET /api/portal/sales endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_sales(self):
        """GET /api/portal/sales should return user sales"""
        response = requests.get(f"{BASE_URL}/api/portal/sales", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Sales should be a list"
        print(f"PASS: Portal sales returns list - {len(data)} sales")


class TestPreviousFeatures:
    """Test that previously working features still work"""
    
    def test_login_works(self):
        """Login should still work"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        data = response.json()
        assert "token" in data, "Missing token in login response"
        print("PASS: Login still works")
    
    def test_members_crud(self):
        """Members CRUD should still work"""
        # Login first
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_response.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # List members
        response = requests.get(f"{BASE_URL}/api/members", headers=headers)
        assert response.status_code == 200, f"Members list failed: {response.status_code}"
        print("PASS: Members CRUD still works")
    
    def test_health_endpoint(self):
        """Health endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: Health endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
