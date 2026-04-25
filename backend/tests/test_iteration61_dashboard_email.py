"""
Iteration 61 - Dashboard Action Items & Email Notifications Tests
Tests for:
1. GET /api/dashboard/action-items - returns overdue_tasks, pending_approvals, expiring_passes, unassigned_tasks
2. Task assignment email notification trigger (code path execution)
3. Parent check-in email notification (email_sent field)
4. email_helpers.py module functions exist
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://comms-hub-57.preview.emergentagent.com').rstrip('/')

class TestDashboardActionItems:
    """Tests for GET /api/dashboard/action-items endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_action_items_endpoint_returns_200(self):
        """Test that action items endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_action_items_returns_required_fields(self):
        """Test that action items returns all required fields"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields are present
        assert "overdue_tasks" in data, "Missing overdue_tasks field"
        assert "pending_approvals" in data, "Missing pending_approvals field"
        assert "expiring_passes" in data, "Missing expiring_passes field"
        assert "unassigned_tasks" in data, "Missing unassigned_tasks field"
    
    def test_action_items_returns_integers(self):
        """Test that action items returns integer counts"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data["overdue_tasks"], int), "overdue_tasks should be an integer"
        assert isinstance(data["pending_approvals"], int), "pending_approvals should be an integer"
        assert isinstance(data["expiring_passes"], int), "expiring_passes should be an integer"
        assert isinstance(data["unassigned_tasks"], int), "unassigned_tasks should be an integer"
    
    def test_action_items_counts_are_non_negative(self):
        """Test that all counts are non-negative"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data["overdue_tasks"] >= 0, "overdue_tasks should be non-negative"
        assert data["pending_approvals"] >= 0, "pending_approvals should be non-negative"
        assert data["expiring_passes"] >= 0, "expiring_passes should be non-negative"
        assert data["unassigned_tasks"] >= 0, "unassigned_tasks should be non-negative"
    
    def test_action_items_with_campus_filter(self):
        """Test action items with campus_id parameter"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", 
                               headers=self.headers, 
                               params={"campus_id": "loc_001"})
        assert response.status_code == 200
        data = response.json()
        assert "overdue_tasks" in data
    
    def test_action_items_requires_auth(self):
        """Test that action items endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items")
        assert response.status_code == 401, "Should require authentication"


class TestTaskAssignmentEmailNotification:
    """Tests for task assignment email notification trigger"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.created_task_ids = []
    
    def teardown_method(self):
        """Cleanup created test tasks"""
        for task_id in self.created_task_ids:
            try:
                requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=self.headers)
            except:
                pass
    
    def test_create_task_and_assign_user(self):
        """Test creating a task and assigning a user (triggers email notification code path)"""
        # Create a task
        create_response = requests.post(f"{BASE_URL}/api/tasks", headers=self.headers, json={
            "title": "TEST_EmailNotify_Task_61",
            "description": "Testing email notification on assignment",
            "status": "todo",
            "priority": "high"
        })
        assert create_response.status_code == 200, f"Failed to create task: {create_response.text}"
        task = create_response.json()
        self.created_task_ids.append(task["id"])
        
        # Update task with assignees (this should trigger email notification code path)
        update_response = requests.put(f"{BASE_URL}/api/tasks/{task['id']}", headers=self.headers, json={
            "assignees": [self.user["id"]]
        })
        assert update_response.status_code == 200, f"Failed to update task: {update_response.text}"
        updated_task = update_response.json()
        
        # Verify assignees were set
        assert self.user["id"] in updated_task.get("assignees", []), "User should be in assignees"
    
    def test_task_update_with_new_assignees_succeeds(self):
        """Test that task update with new assignees completes without error"""
        # Create task without assignees
        create_response = requests.post(f"{BASE_URL}/api/tasks", headers=self.headers, json={
            "title": "TEST_EmailNotify_Task_61_v2",
            "status": "todo",
            "priority": "medium",
            "assignees": []
        })
        assert create_response.status_code == 200
        task = create_response.json()
        self.created_task_ids.append(task["id"])
        
        # Add assignees (triggers email notification)
        update_response = requests.put(f"{BASE_URL}/api/tasks/{task['id']}", headers=self.headers, json={
            "assignees": [self.user["id"]]
        })
        assert update_response.status_code == 200, "Task update should succeed even if email fails"


class TestParentCheckinEmailNotification:
    """Tests for parent check-in email notification"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_parent_lookup_endpoint_exists(self):
        """Test that parent lookup endpoint exists and accepts requests"""
        response = requests.post(f"{BASE_URL}/api/checkins/parent-lookup", 
                                headers=self.headers,
                                json={"lookup": "nonexistent@test.com", "checkin": False})
        # Should return 404 for non-existent parent, not 500 or 405
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
    
    def test_parent_lookup_with_checkin_flag(self):
        """Test parent lookup with checkin=true flag"""
        response = requests.post(f"{BASE_URL}/api/checkins/parent-lookup",
                                headers=self.headers,
                                json={"lookup": "test@example.com", "checkin": True})
        # Should return 404 for non-existent parent
        assert response.status_code in [200, 404]
    
    def test_parent_lookup_requires_lookup_field(self):
        """Test that parent lookup requires lookup field"""
        response = requests.post(f"{BASE_URL}/api/checkins/parent-lookup",
                                headers=self.headers,
                                json={"checkin": False})
        assert response.status_code == 400, "Should require lookup field"


class TestEmailHelpersModule:
    """Tests to verify email_helpers.py module exists and has required functions"""
    
    def test_email_helpers_module_exists(self):
        """Test that email_helpers.py module exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        try:
            import email_helpers
            assert True, "email_helpers module imported successfully"
        except ImportError as e:
            pytest.fail(f"email_helpers module not found: {e}")
    
    def test_notify_task_assigned_function_exists(self):
        """Test that notify_task_assigned function exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        from email_helpers import notify_task_assigned
        assert callable(notify_task_assigned), "notify_task_assigned should be callable"
    
    def test_notify_checkin_function_exists(self):
        """Test that notify_checkin function exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        from email_helpers import notify_checkin
        assert callable(notify_checkin), "notify_checkin should be callable"
    
    def test_notify_task_overdue_function_exists(self):
        """Test that notify_task_overdue function exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        from email_helpers import notify_task_overdue
        assert callable(notify_task_overdue), "notify_task_overdue should be callable"


class TestDashboardStatsIntegration:
    """Tests for dashboard stats endpoint integration"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats_returns_tasks_overdue(self):
        """Test that dashboard stats includes tasks_overdue field"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "tasks_overdue" in data, "Dashboard stats should include tasks_overdue"
    
    def test_dashboard_stats_and_action_items_consistency(self):
        """Test that tasks_overdue in stats matches overdue_tasks in action items"""
        stats_response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        action_response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        
        assert stats_response.status_code == 200
        assert action_response.status_code == 200
        
        stats = stats_response.json()
        actions = action_response.json()
        
        # Both should report the same overdue task count
        assert stats["tasks_overdue"] == actions["overdue_tasks"], \
            f"Mismatch: stats.tasks_overdue={stats['tasks_overdue']} vs actions.overdue_tasks={actions['overdue_tasks']}"


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
