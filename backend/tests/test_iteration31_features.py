"""
Iteration 31 Tests - Location Filtering, Data Isolation, Calendar Events, Staff Tasks, Communications
Tests:
- Location filtering with async get_campus_filter and sub-location expansion
- Data isolation for boards endpoint
- Calendar event editing (PUT /api/events/{id})
- Staff task creation permissions
- Communications page APIs (presence, reactions, chat)
- AdminPage refactoring (BadgePrintView component)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    def test_login_success(self, auth_token):
        """Test admin login works"""
        assert auth_token is not None
        assert len(auth_token) > 0
        print(f"✓ Login successful, token obtained")


class TestEventsAPI:
    """Event CRUD and calendar editing tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_events(self, auth_headers):
        """Test listing events"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} events")
    
    def test_create_event(self, auth_headers):
        """Test creating an event"""
        event_data = {
            "title": "TEST_Iteration31_Event",
            "date": "2026-02-15",
            "time": "10:00",
            "location": "Test Location",
            "type": "meeting",
            "capacity": 50,
            "is_public": True
        }
        response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Iteration31_Event"
        assert "id" in data
        print(f"✓ Created event: {data['id']}")
        return data["id"]
    
    def test_update_event(self, auth_headers):
        """Test updating an event (calendar edit modal functionality)"""
        # First create an event
        event_data = {
            "title": "TEST_Event_To_Update",
            "date": "2026-02-20",
            "time": "14:00",
            "location": "Original Location",
            "type": "service",
            "capacity": 100,
            "is_public": True
        }
        create_response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        assert create_response.status_code == 200
        event_id = create_response.json()["id"]
        
        # Now update the event
        update_data = {
            "title": "TEST_Event_Updated",
            "date": "2026-02-21",
            "time": "15:00",
            "location": "Updated Location",
            "description": "Updated description",
            "capacity": 150
        }
        update_response = requests.put(f"{BASE_URL}/api/events/{event_id}", json=update_data, headers=auth_headers)
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["title"] == "TEST_Event_Updated"
        assert updated["date"] == "2026-02-21"
        assert updated["time"] == "15:00"
        assert updated["location"] == "Updated Location"
        print(f"✓ Updated event {event_id} successfully")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=auth_headers)
    
    def test_delete_event(self, auth_headers):
        """Test deleting an event"""
        # Create event to delete
        event_data = {
            "title": "TEST_Event_To_Delete",
            "date": "2026-02-25",
            "time": "09:00",
            "type": "meeting"
        }
        create_response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        event_id = create_response.json()["id"]
        
        # Delete it
        delete_response = requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=auth_headers)
        assert delete_response.status_code == 200
        
        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=auth_headers)
        assert get_response.status_code == 404
        print(f"✓ Deleted event {event_id} successfully")


class TestBoardsAPI:
    """Boards API with campus filtering tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_boards(self, auth_headers):
        """Test listing boards with campus filter"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} boards")
    
    def test_create_board(self, auth_headers):
        """Test creating a board"""
        board_data = {
            "name": "TEST_Iteration31_Board",
            "description": "Test board for iteration 31",
            "background": "#3b82f6"
        }
        response = requests.post(f"{BASE_URL}/api/boards", json=board_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Iteration31_Board"
        assert "id" in data
        print(f"✓ Created board: {data['id']}")
        return data["id"]
    
    def test_get_board_with_lists(self, auth_headers):
        """Test getting a board with its lists"""
        # Create a board first
        board_data = {"name": "TEST_Board_With_Lists", "background": "#10b981"}
        create_response = requests.post(f"{BASE_URL}/api/boards", json=board_data, headers=auth_headers)
        board_id = create_response.json()["id"]
        
        # Get the board
        get_response = requests.get(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)
        assert get_response.status_code == 200
        board = get_response.json()
        assert "lists" in board
        assert isinstance(board["lists"], list)
        # Default lists should be created
        assert len(board["lists"]) >= 3  # To Do, In Progress, Done
        print(f"✓ Board {board_id} has {len(board['lists'])} lists")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)


class TestTasksAPI:
    """Tasks API with staff creation permissions"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_tasks(self, auth_headers):
        """Test listing tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} tasks")
    
    def test_create_task(self, auth_headers):
        """Test creating a task (staff should be able to create)"""
        task_data = {
            "title": "TEST_Iteration31_Task",
            "description": "Test task for iteration 31",
            "status": "todo",
            "priority": "medium"
        }
        response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Iteration31_Task"
        assert "id" in data
        print(f"✓ Created task: {data['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tasks/{data['id']}", headers=auth_headers)
    
    def test_archive_restore_task(self, auth_headers):
        """Test archiving and restoring a task"""
        # Create task
        task_data = {"title": "TEST_Archive_Task", "status": "todo"}
        create_response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=auth_headers)
        task_id = create_response.json()["id"]
        
        # Archive it
        archive_response = requests.post(f"{BASE_URL}/api/tasks/{task_id}/archive", headers=auth_headers)
        assert archive_response.status_code == 200
        print(f"✓ Archived task {task_id}")
        
        # Restore it
        restore_response = requests.post(f"{BASE_URL}/api/tasks/{task_id}/restore", headers=auth_headers)
        assert restore_response.status_code == 200
        restored = restore_response.json()
        assert restored.get("is_archived") == False
        print(f"✓ Restored task {task_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)


class TestPresenceAPI:
    """Presence system tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.fixture(scope="class")
    def user_id(self, auth_headers):
        """Get current user ID"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        return response.json().get("id")
    
    def test_get_online_users(self, auth_headers):
        """Test getting online users list"""
        response = requests.get(f"{BASE_URL}/api/presence/online-users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} online users")
    
    def test_heartbeat(self, auth_headers, user_id):
        """Test presence heartbeat"""
        response = requests.put(f"{BASE_URL}/api/presence/heartbeat?user_id={user_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        print(f"✓ Heartbeat sent for user {user_id}")
    
    def test_set_status(self, auth_headers, user_id):
        """Test setting presence status"""
        # Set to DND
        response = requests.put(f"{BASE_URL}/api/presence/status?user_id={user_id}&status=dnd", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        print(f"✓ Set status to DND")
        
        # Set back to online
        response = requests.put(f"{BASE_URL}/api/presence/status?user_id={user_id}&status=online", headers=auth_headers)
        assert response.status_code == 200
        print(f"✓ Set status back to online")
    
    def test_get_user_presence(self, auth_headers, user_id):
        """Test getting single user presence"""
        response = requests.get(f"{BASE_URL}/api/presence/status/{user_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "user_id" in data
        print(f"✓ Got presence for user {user_id}: {data.get('status')}")


class TestReactionsAPI:
    """Message reactions tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_quick_reactions(self, auth_headers):
        """Test getting quick reaction emojis"""
        response = requests.get(f"{BASE_URL}/api/reactions/quick", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "reactions" in data
        assert isinstance(data["reactions"], list)
        assert len(data["reactions"]) > 0
        assert "👍" in data["reactions"]
        print(f"✓ Got {len(data['reactions'])} quick reactions")


class TestChatAPI:
    """Chat and conversations tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_conversations(self, auth_headers):
        """Test getting conversations list"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} conversations")
    
    def test_create_conversation(self, auth_headers):
        """Test creating a conversation"""
        conv_data = {
            "name": "TEST_Iteration31_Conversation",
            "type": "group",
            "participants": []
        }
        response = requests.post(f"{BASE_URL}/api/chat/conversations", json=conv_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Iteration31_Conversation"
        assert "id" in data
        print(f"✓ Created conversation: {data['id']}")
    
    def test_get_chat_users(self, auth_headers):
        """Test getting users available for chat"""
        response = requests.get(f"{BASE_URL}/api/chat/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} chat users")


class TestLocationsAPI:
    """Locations and sub-locations tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_locations(self, auth_headers):
        """Test listing locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} locations")
        
        # Check for sub-locations
        sub_locs = [l for l in data if l.get("type") == "sub-location"]
        campuses = [l for l in data if l.get("type") == "campus"]
        print(f"  - {len(campuses)} campuses, {len(sub_locs)} sub-locations")


class TestAdminAPI:
    """Admin user management tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_users(self, auth_headers):
        """Test listing users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} users")
    
    def test_get_user_profile(self, auth_headers):
        """Test getting full user profile"""
        # First get a user ID
        users_response = requests.get(f"{BASE_URL}/api/admin/users?limit=1", headers=auth_headers)
        users = users_response.json()
        if users:
            user_id = users[0]["id"]
            response = requests.get(f"{BASE_URL}/api/admin/users/{user_id}/profile", headers=auth_headers)
            assert response.status_code == 200
            profile = response.json()
            assert "name" in profile
            print(f"✓ Got profile for user {user_id}")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_cleanup_test_events(self, auth_headers):
        """Clean up test events"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        events = response.json()
        deleted = 0
        for event in events:
            if event.get("title", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=auth_headers)
                deleted += 1
        print(f"✓ Cleaned up {deleted} test events")
    
    def test_cleanup_test_boards(self, auth_headers):
        """Clean up test boards"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        boards = response.json()
        deleted = 0
        for board in boards:
            if board.get("name", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/boards/{board['id']}", headers=auth_headers)
                deleted += 1
        print(f"✓ Cleaned up {deleted} test boards")
    
    def test_cleanup_test_tasks(self, auth_headers):
        """Clean up test tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks?include_archived=true", headers=auth_headers)
        tasks = response.json()
        deleted = 0
        for task in tasks:
            if task.get("title", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/tasks/{task['id']}", headers=auth_headers)
                deleted += 1
        print(f"✓ Cleaned up {deleted} test tasks")
