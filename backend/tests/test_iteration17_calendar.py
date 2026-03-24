"""
Iteration 17 Tests: Team Calendar, Edit Member, Admin Import
Tests for:
1. People page: Edit member works (editMember useState fix)
2. Admin page: Import Users dialog and Create user
3. Tasks page: Calendar view with due_date support
4. Backend: GET /api/tasks returns tasks with due_date field
5. Backend: PUT /api/tasks/{id} supports due_date and assignees
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_admin(self):
        """Test admin login with identifier field"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        print(f"✓ Admin login successful, role: {data['user'].get('role')}")
        return data["token"]


class TestMembersEdit:
    """Test member editing functionality (critical fix verification)"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_list_members(self, auth_token):
        """GET /api/members returns members list"""
        response = requests.get(
            f"{BASE_URL}/api/members",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        members = data.get("members", data) if isinstance(data, dict) else data
        assert len(members) > 0, "No members found"
        print(f"✓ Members list: {len(members)} members")
        return members[0]
    
    def test_create_member(self, auth_token):
        """POST /api/members creates new member"""
        response = requests.post(
            f"{BASE_URL}/api/members",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "TEST_Calendar_User",
                "email": "test_calendar@example.com",
                "phone": "+256 700 999888",
                "role": "Staff",
                "group": "Youth",
                "gender": "male",
                "status": "active"
            }
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert data.get("name") == "TEST_Calendar_User"
        print(f"✓ Member created: {data.get('id')}")
        return data
    
    def test_update_member(self, auth_token):
        """PUT /api/members/{id} updates member (CRITICAL FIX)"""
        # First create a test member
        create_resp = requests.post(
            f"{BASE_URL}/api/members",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "TEST_Edit_Member",
                "email": "test_edit@example.com",
                "role": "Staff",
                "gender": "female"
            }
        )
        assert create_resp.status_code in [200, 201]
        member = create_resp.json()
        member_id = member["id"]
        
        # Update the member
        update_resp = requests.put(
            f"{BASE_URL}/api/members/{member_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "TEST_Edit_Member_Updated",
                "phone": "+256 700 111222",
                "notes": "Updated via test"
            }
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("name") == "TEST_Edit_Member_Updated"
        print(f"✓ Member updated successfully: {member_id}")
        
        # Verify persistence with GET
        get_resp = requests.get(
            f"{BASE_URL}/api/members/{member_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched.get("name") == "TEST_Edit_Member_Updated"
        print(f"✓ Member update persisted correctly")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/members/{member_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        return updated


class TestAdminUsers:
    """Test admin user management"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_list_admin_users(self, auth_token):
        """GET /api/admin/users returns users list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        users = response.json()
        assert len(users) > 0, "No users found"
        print(f"✓ Admin users list: {len(users)} users")
        return users
    
    def test_create_admin_user(self, auth_token):
        """POST /api/admin/users creates user with temp_password"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "TEST_Admin_User",
                "email": "test_admin_user@example.com",
                "phone": "+256 700 888777",
                "role": "Staff",
                "department": "Operations",
                "also_create_member": True
            }
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert "temp_password" in data, "No temp_password returned"
        assert data.get("name") == "TEST_Admin_User"
        print(f"✓ Admin user created: {data.get('id')}, temp_password provided")
        
        # Cleanup
        if data.get("id"):
            requests.delete(
                f"{BASE_URL}/api/admin/users/{data['id']}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
        return data
    
    def test_import_users(self, auth_token):
        """POST /api/admin/users/import imports users (CRITICAL FEATURE)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/import",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "users": [
                    {"name": "TEST_Import_User1", "email": "test_import1@example.com", "role": "Staff"},
                    {"name": "TEST_Import_User2", "email": "test_import2@example.com", "role": "Volunteer"}
                ]
            }
        )
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        assert "created" in data
        print(f"✓ Import users: created={data.get('created')}, skipped={data.get('skipped')}")
        
        # Cleanup imported users
        for email in ["test_import1@example.com", "test_import2@example.com"]:
            users = requests.get(
                f"{BASE_URL}/api/admin/users?search={email}",
                headers={"Authorization": f"Bearer {auth_token}"}
            ).json()
            for u in users:
                if u.get("email") == email:
                    requests.delete(
                        f"{BASE_URL}/api/admin/users/{u['id']}",
                        headers={"Authorization": f"Bearer {auth_token}"}
                    )
        return data


class TestTasksCalendar:
    """Test tasks with due_date for Team Calendar feature"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_list_tasks(self, auth_token):
        """GET /api/tasks returns tasks list"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        tasks = response.json()
        print(f"✓ Tasks list: {len(tasks)} tasks")
        return tasks
    
    def test_create_task_with_due_date(self, auth_token):
        """POST /api/tasks creates task with due_date"""
        response = requests.post(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "title": "TEST_Calendar_Task",
                "description": "Task for calendar testing",
                "status": "todo",
                "priority": "high",
                "due_date": "2026-03-25",
                "assignees": [],
                "labels": [{"name": "test", "color": "#3b82f6"}],
                "checklist": [],
                "attachments": []
            }
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        data = response.json()
        assert data.get("title") == "TEST_Calendar_Task"
        assert data.get("due_date") == "2026-03-25"
        print(f"✓ Task created with due_date: {data.get('id')}")
        return data
    
    def test_update_task_due_date(self, auth_token):
        """PUT /api/tasks/{id} updates due_date and assignees"""
        # First create a task
        create_resp = requests.post(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "title": "TEST_Update_Due_Date",
                "status": "todo",
                "priority": "medium"
            }
        )
        assert create_resp.status_code in [200, 201]
        task = create_resp.json()
        task_id = task["id"]
        
        # Update with due_date and assignees
        update_resp = requests.put(
            f"{BASE_URL}/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "due_date": "2026-03-28",
                "assignees": ["user_123", "user_456"],
                "priority": "high"
            }
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("due_date") == "2026-03-28"
        assert "user_123" in updated.get("assignees", [])
        print(f"✓ Task due_date updated: {task_id}")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        return updated
    
    def test_tasks_have_due_date_field(self, auth_token):
        """Verify tasks API returns due_date field for calendar"""
        # Create task with due_date
        create_resp = requests.post(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "title": "TEST_Due_Date_Field",
                "status": "in-progress",
                "due_date": "2026-03-30"
            }
        )
        task = create_resp.json()
        task_id = task["id"]
        
        # List all tasks and verify due_date is present
        list_resp = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        tasks = list_resp.json()
        test_task = next((t for t in tasks if t.get("id") == task_id), None)
        assert test_task is not None, "Created task not found in list"
        assert "due_date" in test_task, "due_date field missing from task"
        assert test_task["due_date"] == "2026-03-30"
        print(f"✓ Tasks API returns due_date field correctly")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )


class TestBoardsKanban:
    """Test boards/kanban functionality"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_list_boards(self, auth_token):
        """GET /api/boards returns boards list"""
        response = requests.get(
            f"{BASE_URL}/api/boards",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        boards = response.json()
        print(f"✓ Boards list: {len(boards)} boards")
        return boards


class TestDashboard:
    """Test dashboard functionality"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_dashboard_stats(self, auth_token):
        """GET /api/dashboard/stats returns statistics"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_members" in data
        assert "upcoming_events" in data
        print(f"✓ Dashboard stats: {data.get('total_members')} members, {data.get('upcoming_events')} upcoming events")
        return data


class TestEvents:
    """Test events functionality"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_list_events(self, auth_token):
        """GET /api/events returns events list"""
        response = requests.get(
            f"{BASE_URL}/api/events",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        events = response.json()
        print(f"✓ Events list: {len(events)} events")
        return events


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return response.json()["token"]
    
    def test_cleanup_test_members(self, auth_token):
        """Clean up TEST_ prefixed members"""
        response = requests.get(
            f"{BASE_URL}/api/members?search=TEST_",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if response.status_code == 200:
            data = response.json()
            members = data.get("members", data) if isinstance(data, dict) else data
            for m in members:
                if m.get("name", "").startswith("TEST_"):
                    requests.delete(
                        f"{BASE_URL}/api/members/{m['id']}",
                        headers={"Authorization": f"Bearer {auth_token}"}
                    )
        print("✓ Test members cleaned up")
    
    def test_cleanup_test_tasks(self, auth_token):
        """Clean up TEST_ prefixed tasks"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if response.status_code == 200:
            tasks = response.json()
            for t in tasks:
                if t.get("title", "").startswith("TEST_"):
                    requests.delete(
                        f"{BASE_URL}/api/tasks/{t['id']}",
                        headers={"Authorization": f"Bearer {auth_token}"}
                    )
        print("✓ Test tasks cleaned up")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
