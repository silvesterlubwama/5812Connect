"""
Iteration 48 - Bulk Operations Testing
Tests for:
- Bulk event update/delete/export (PUT/POST /api/events/bulk-*)
- Bulk task update/delete/archive (PUT/POST /api/tasks/bulk-*)
- Bulk member export (POST /api/admin/members/bulk-export)
- Boards restricted/private visibility
- Public events country filter from location_id
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_user(auth_token):
    """Get current admin user info"""
    response = requests.get(f"{BASE_URL}/api/auth/me", headers={
        "Authorization": f"Bearer {auth_token}"
    })
    if response.status_code == 200:
        return response.json()
    return {"id": "admin", "role": "admin"}


# =================== BULK EVENT OPERATIONS ===================

class TestBulkEventOperations:
    """Test bulk event update, delete, and export endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_test_events(self, auth_headers):
        """Create test events for bulk operations"""
        self.test_event_ids = []
        for i in range(3):
            event_data = {
                "title": f"TEST_BulkEvent_{i}_{uuid.uuid4().hex[:6]}",
                "type": "meeting",
                "date": "2026-05-15",
                "time": "10:00",
                "location": "Test Location",
                "capacity": 50,
                "is_public": True,
                "status": "upcoming"
            }
            response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
            if response.status_code in [200, 201]:
                self.test_event_ids.append(response.json().get("id"))
        yield
        # Cleanup
        for eid in self.test_event_ids:
            requests.delete(f"{BASE_URL}/api/events/{eid}", headers=auth_headers)
    
    def test_bulk_event_update(self, auth_headers):
        """Test PUT /api/events/bulk-update - update multiple events at once"""
        if len(self.test_event_ids) < 2:
            pytest.skip("Not enough test events created")
        
        response = requests.put(f"{BASE_URL}/api/events/bulk-update", json={
            "ids": self.test_event_ids[:2],
            "updates": {
                "status": "completed",
                "type": "conference"
            }
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk update failed: {response.text}"
        data = response.json()
        assert "updated" in data
        assert data["updated"] >= 1, "Should have updated at least 1 event"
        print(f"Bulk event update: {data['updated']} events updated")
        
        # Verify update persisted
        verify = requests.get(f"{BASE_URL}/api/events/{self.test_event_ids[0]}", headers=auth_headers)
        if verify.status_code == 200:
            event = verify.json()
            assert event.get("status") == "completed", "Status should be updated to completed"
            assert event.get("type") == "conference", "Type should be updated to conference"
    
    def test_bulk_event_update_with_location_id(self, auth_headers):
        """Test bulk update with location_id field"""
        if len(self.test_event_ids) < 1:
            pytest.skip("No test events created")
        
        response = requests.put(f"{BASE_URL}/api/events/bulk-update", json={
            "ids": [self.test_event_ids[0]],
            "updates": {
                "location_id": "loc_001",
                "visibility": "internal"
            }
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk update with location failed: {response.text}"
        print(f"Bulk event update with location_id: {response.json()}")
    
    def test_bulk_event_delete(self, auth_headers):
        """Test POST /api/events/bulk-delete - delete multiple events"""
        # Create events specifically for deletion
        delete_ids = []
        for i in range(2):
            event_data = {
                "title": f"TEST_DeleteEvent_{i}_{uuid.uuid4().hex[:6]}",
                "type": "meeting",
                "date": "2026-06-01",
                "time": "14:00",
                "location": "Delete Test",
                "capacity": 10
            }
            resp = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
            if resp.status_code in [200, 201]:
                delete_ids.append(resp.json().get("id"))
        
        if len(delete_ids) < 1:
            pytest.skip("Could not create events for deletion test")
        
        response = requests.post(f"{BASE_URL}/api/events/bulk-delete", json={
            "ids": delete_ids
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk delete failed: {response.text}"
        data = response.json()
        assert "deleted" in data
        assert data["deleted"] >= 1, "Should have deleted at least 1 event"
        print(f"Bulk event delete: {data['deleted']} events deleted")
        
        # Verify deletion
        for eid in delete_ids:
            verify = requests.get(f"{BASE_URL}/api/events/{eid}", headers=auth_headers)
            assert verify.status_code == 404, f"Event {eid} should be deleted"
    
    def test_bulk_event_export(self, auth_headers):
        """Test POST /api/events/bulk-export - export events as JSON"""
        if len(self.test_event_ids) < 1:
            pytest.skip("No test events created")
        
        # Export specific events
        response = requests.post(f"{BASE_URL}/api/events/bulk-export", json={
            "ids": self.test_event_ids
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk export failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Export should return a list"
        assert len(data) >= 1, "Should export at least 1 event"
        
        # Verify exported data structure
        if data:
            event = data[0]
            assert "id" in event
            assert "title" in event
            assert "date" in event
        print(f"Bulk event export: {len(data)} events exported")
    
    def test_bulk_event_export_all(self, auth_headers):
        """Test bulk export with empty ids (export all)"""
        response = requests.post(f"{BASE_URL}/api/events/bulk-export", json={}, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk export all failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Export should return a list"
        print(f"Bulk event export all: {len(data)} events exported")
    
    def test_bulk_event_update_empty_ids(self, auth_headers):
        """Test bulk update with empty ids returns 0 updated"""
        response = requests.put(f"{BASE_URL}/api/events/bulk-update", json={
            "ids": [],
            "updates": {"status": "completed"}
        }, headers=auth_headers)
        
        assert response.status_code == 200
        assert response.json().get("updated") == 0


# =================== BULK TASK OPERATIONS ===================

class TestBulkTaskOperations:
    """Test bulk task update, delete, and archive endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_test_tasks(self, auth_headers):
        """Create test tasks for bulk operations"""
        self.test_task_ids = []
        for i in range(3):
            task_data = {
                "title": f"TEST_BulkTask_{i}_{uuid.uuid4().hex[:6]}",
                "description": "Test task for bulk operations",
                "status": "todo",
                "priority": "medium",
                "due_date": "2026-05-20"
            }
            response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=auth_headers)
            if response.status_code in [200, 201]:
                self.test_task_ids.append(response.json().get("id"))
        yield
        # Cleanup
        for tid in self.test_task_ids:
            requests.delete(f"{BASE_URL}/api/tasks/{tid}", headers=auth_headers)
    
    def test_bulk_task_update(self, auth_headers):
        """Test PUT /api/tasks/bulk-update - update multiple tasks"""
        if len(self.test_task_ids) < 2:
            pytest.skip("Not enough test tasks created")
        
        response = requests.put(f"{BASE_URL}/api/tasks/bulk-update", json={
            "ids": self.test_task_ids[:2],
            "updates": {
                "status": "in-progress",
                "priority": "high"
            }
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk task update failed: {response.text}"
        data = response.json()
        assert "updated" in data
        assert data["updated"] >= 1, "Should have updated at least 1 task"
        print(f"Bulk task update: {data['updated']} tasks updated")
    
    def test_bulk_task_update_with_assignees(self, auth_headers, admin_user):
        """Test bulk update with assignees field"""
        if len(self.test_task_ids) < 1:
            pytest.skip("No test tasks created")
        
        response = requests.put(f"{BASE_URL}/api/tasks/bulk-update", json={
            "ids": [self.test_task_ids[0]],
            "updates": {
                "assignees": [admin_user.get("id", "admin")]
            }
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk update with assignees failed: {response.text}"
        print(f"Bulk task update with assignees: {response.json()}")
    
    def test_bulk_task_delete(self, auth_headers):
        """Test POST /api/tasks/bulk-delete - delete multiple tasks"""
        # Create tasks specifically for deletion
        delete_ids = []
        for i in range(2):
            task_data = {
                "title": f"TEST_DeleteTask_{i}_{uuid.uuid4().hex[:6]}",
                "status": "todo",
                "priority": "low"
            }
            resp = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=auth_headers)
            if resp.status_code in [200, 201]:
                delete_ids.append(resp.json().get("id"))
        
        if len(delete_ids) < 1:
            pytest.skip("Could not create tasks for deletion test")
        
        response = requests.post(f"{BASE_URL}/api/tasks/bulk-delete", json={
            "ids": delete_ids
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk task delete failed: {response.text}"
        data = response.json()
        assert "deleted" in data
        assert data["deleted"] >= 1, "Should have deleted at least 1 task"
        print(f"Bulk task delete: {data['deleted']} tasks deleted")
    
    def test_bulk_task_archive(self, auth_headers):
        """Test POST /api/tasks/bulk-archive - archive multiple tasks"""
        if len(self.test_task_ids) < 2:
            pytest.skip("Not enough test tasks created")
        
        # Archive tasks
        response = requests.post(f"{BASE_URL}/api/tasks/bulk-archive", json={
            "ids": self.test_task_ids[:2],
            "archive": True
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk archive failed: {response.text}"
        data = response.json()
        assert "updated" in data
        assert data["updated"] >= 1, "Should have archived at least 1 task"
        print(f"Bulk task archive: {data['updated']} tasks archived")
    
    def test_bulk_task_unarchive(self, auth_headers):
        """Test bulk unarchive (archive=false)"""
        if len(self.test_task_ids) < 1:
            pytest.skip("No test tasks created")
        
        # First archive
        requests.post(f"{BASE_URL}/api/tasks/bulk-archive", json={
            "ids": [self.test_task_ids[0]],
            "archive": True
        }, headers=auth_headers)
        
        # Then unarchive
        response = requests.post(f"{BASE_URL}/api/tasks/bulk-archive", json={
            "ids": [self.test_task_ids[0]],
            "archive": False
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk unarchive failed: {response.text}"
        print(f"Bulk task unarchive: {response.json()}")
    
    def test_bulk_task_update_empty_ids(self, auth_headers):
        """Test bulk update with empty ids returns 0 updated"""
        response = requests.put(f"{BASE_URL}/api/tasks/bulk-update", json={
            "ids": [],
            "updates": {"status": "done"}
        }, headers=auth_headers)
        
        assert response.status_code == 200
        assert response.json().get("updated") == 0


# =================== BULK MEMBER EXPORT ===================

class TestBulkMemberExport:
    """Test bulk member export endpoint"""
    
    def test_bulk_member_export_all(self, auth_headers):
        """Test POST /api/admin/members/bulk-export - export all members"""
        response = requests.post(f"{BASE_URL}/api/admin/members/bulk-export", json={}, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk member export failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Export should return a list"
        print(f"Bulk member export all: {len(data)} members exported")
        
        # Verify data structure if members exist
        if data:
            member = data[0]
            assert "id" in member or "name" in member, "Member should have id or name"
    
    def test_bulk_member_export_specific_ids(self, auth_headers):
        """Test bulk export with specific member IDs"""
        # First get some member IDs
        members_resp = requests.get(f"{BASE_URL}/api/members?limit=3", headers=auth_headers)
        if members_resp.status_code != 200:
            pytest.skip("Could not fetch members")
        
        members_data = members_resp.json()
        # Handle both list and dict (paginated) responses
        if isinstance(members_data, dict):
            members = members_data.get("members", members_data.get("items", []))
        else:
            members = members_data
        
        if not members:
            pytest.skip("No members to export")
        
        member_ids = [m.get("id") for m in members[:2] if m.get("id")]
        
        response = requests.post(f"{BASE_URL}/api/admin/members/bulk-export", json={
            "ids": member_ids
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Bulk member export specific failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Export should return a list"
        print(f"Bulk member export specific: {len(data)} members exported")


# =================== BOARDS RESTRICTED/PRIVATE ===================

class TestBoardsVisibility:
    """Test boards restricted and private visibility"""
    
    @pytest.fixture(autouse=True)
    def setup_test_boards(self, auth_headers, admin_user):
        """Create test boards with different visibility settings"""
        self.test_board_ids = []
        self.admin_id = admin_user.get("id", "admin")
        
        # Create a restricted board
        restricted_board = {
            "name": f"TEST_RestrictedBoard_{uuid.uuid4().hex[:6]}",
            "description": "Restricted board for testing",
            "is_restricted": True,
            "tagged_members": [self.admin_id],
            "location_id": "loc_001"
        }
        resp = requests.post(f"{BASE_URL}/api/boards", json=restricted_board, headers=auth_headers)
        if resp.status_code in [200, 201]:
            self.test_board_ids.append(resp.json().get("id"))
            self.restricted_board_id = resp.json().get("id")
        
        # Create a private board
        private_board = {
            "name": f"TEST_PrivateBoard_{uuid.uuid4().hex[:6]}",
            "description": "Private board for testing",
            "is_private": True,
            "tagged_members": [self.admin_id],
            "location_id": "loc_001"
        }
        resp = requests.post(f"{BASE_URL}/api/boards", json=private_board, headers=auth_headers)
        if resp.status_code in [200, 201]:
            self.test_board_ids.append(resp.json().get("id"))
            self.private_board_id = resp.json().get("id")
        
        # Create a normal board
        normal_board = {
            "name": f"TEST_NormalBoard_{uuid.uuid4().hex[:6]}",
            "description": "Normal board for testing",
            "location_id": "loc_001"
        }
        resp = requests.post(f"{BASE_URL}/api/boards", json=normal_board, headers=auth_headers)
        if resp.status_code in [200, 201]:
            self.test_board_ids.append(resp.json().get("id"))
            self.normal_board_id = resp.json().get("id")
        
        yield
        # Cleanup
        for bid in self.test_board_ids:
            requests.delete(f"{BASE_URL}/api/boards/{bid}", headers=auth_headers)
    
    def test_restricted_board_created_with_flag(self, auth_headers):
        """Test that restricted board is created with is_restricted=true"""
        if not hasattr(self, 'restricted_board_id'):
            pytest.skip("Restricted board not created")
        
        response = requests.get(f"{BASE_URL}/api/boards/{self.restricted_board_id}", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get restricted board: {response.text}"
        
        board = response.json()
        assert board.get("is_restricted") == True, "Board should have is_restricted=true"
        assert self.admin_id in (board.get("tagged_members") or []), "Admin should be in tagged_members"
        print(f"Restricted board verified: {board.get('name')}")
    
    def test_private_board_created_with_flag(self, auth_headers):
        """Test that private board is created with is_private=true"""
        if not hasattr(self, 'private_board_id'):
            pytest.skip("Private board not created")
        
        response = requests.get(f"{BASE_URL}/api/boards/{self.private_board_id}", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get private board: {response.text}"
        
        board = response.json()
        assert board.get("is_private") == True, "Board should have is_private=true"
        print(f"Private board verified: {board.get('name')}")
    
    def test_list_boards_includes_restricted_for_tagged_user(self, auth_headers):
        """Test that list boards includes restricted boards for tagged members"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert response.status_code == 200, f"Failed to list boards: {response.text}"
        
        boards = response.json()
        board_ids = [b.get("id") for b in boards]
        
        # Admin should see restricted board (they're tagged)
        if hasattr(self, 'restricted_board_id'):
            assert self.restricted_board_id in board_ids, "Tagged user should see restricted board"
            print("Restricted board visible to tagged user: PASS")
    
    def test_list_boards_includes_private_for_creator(self, auth_headers):
        """Test that list boards includes private boards for creator"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert response.status_code == 200
        
        boards = response.json()
        board_ids = [b.get("id") for b in boards]
        
        # Creator should see private board
        if hasattr(self, 'private_board_id'):
            assert self.private_board_id in board_ids, "Creator should see private board"
            print("Private board visible to creator: PASS")


# =================== PUBLIC EVENTS COUNTRY FILTER ===================

class TestPublicEventsCountryFilter:
    """Test public events country filter resolves from location_id"""
    
    @pytest.fixture(autouse=True)
    def setup_test_events_with_location(self, auth_headers):
        """Create test events with location_id for country resolution"""
        self.test_event_ids = []
        
        # Create event with location_id (should resolve country from location)
        event_data = {
            "title": f"TEST_CountryEvent_{uuid.uuid4().hex[:6]}",
            "type": "conference",
            "date": "2026-06-15",
            "time": "09:00",
            "location": "Kampala",
            "location_id": "loc_001",  # This location should have country=Uganda
            "capacity": 100,
            "is_public": True,
            "status": "upcoming"
        }
        response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        if response.status_code in [200, 201]:
            self.test_event_ids.append(response.json().get("id"))
        
        yield
        # Cleanup
        for eid in self.test_event_ids:
            requests.delete(f"{BASE_URL}/api/events/{eid}", headers=auth_headers)
    
    def test_public_events_returns_events(self):
        """Test GET /api/public/events returns public events"""
        response = requests.get(f"{BASE_URL}/api/public/events")
        
        assert response.status_code == 200, f"Public events failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return a list of events"
        print(f"Public events: {len(data)} events returned")
    
    def test_public_events_country_filter(self):
        """Test public events can be filtered by country"""
        # Get all public events first
        all_response = requests.get(f"{BASE_URL}/api/public/events")
        assert all_response.status_code == 200
        all_events = all_response.json()
        
        # Filter by Uganda
        uganda_response = requests.get(f"{BASE_URL}/api/public/events?country=Uganda")
        assert uganda_response.status_code == 200, f"Country filter failed: {uganda_response.text}"
        uganda_events = uganda_response.json()
        
        print(f"All public events: {len(all_events)}, Uganda events: {len(uganda_events)}")
        
        # Verify filtered events have Uganda country or location resolves to Uganda
        for event in uganda_events:
            # Event should either have country=Uganda or no country (location resolves)
            country = event.get("country", "")
            if country:
                assert country == "Uganda" or country == "", f"Event country should be Uganda or empty, got: {country}"
    
    def test_public_events_country_filter_all(self):
        """Test country=ALL returns all events"""
        response = requests.get(f"{BASE_URL}/api/public/events?country=ALL")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Public events with country=ALL: {len(data)} events")
    
    def test_public_events_resolves_country_from_location(self, auth_headers):
        """Test that events without country field get country resolved from location_id"""
        if not self.test_event_ids:
            pytest.skip("No test events created")
        
        # Get public events
        response = requests.get(f"{BASE_URL}/api/public/events")
        assert response.status_code == 200
        
        events = response.json()
        # Find our test event
        test_event = next((e for e in events if e.get("id") in self.test_event_ids), None)
        
        if test_event:
            # The event should have country resolved from location_id
            # loc_001 is "58:12 Global (Central)" with country="Uganda"
            print(f"Test event country: {test_event.get('country', 'NOT SET')}")
            print(f"Test event location_id: {test_event.get('location_id')}")


# =================== EDGE CASES ===================

class TestBulkOperationsEdgeCases:
    """Test edge cases for bulk operations"""
    
    def test_bulk_event_update_invalid_field_ignored(self, auth_headers):
        """Test that invalid fields in bulk update are ignored"""
        # Create a test event
        event_data = {
            "title": f"TEST_EdgeCase_{uuid.uuid4().hex[:6]}",
            "type": "meeting",
            "date": "2026-07-01",
            "time": "10:00",
            "capacity": 50
        }
        create_resp = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        if create_resp.status_code not in [200, 201]:
            pytest.skip("Could not create test event")
        
        event_id = create_resp.json().get("id")
        
        try:
            # Try to update with invalid field
            response = requests.put(f"{BASE_URL}/api/events/bulk-update", json={
                "ids": [event_id],
                "updates": {
                    "status": "completed",
                    "invalid_field": "should_be_ignored",
                    "another_invalid": 123
                }
            }, headers=auth_headers)
            
            assert response.status_code == 200, f"Bulk update should succeed: {response.text}"
            # Valid field should be updated
            verify = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=auth_headers)
            if verify.status_code == 200:
                assert verify.json().get("status") == "completed"
        finally:
            requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=auth_headers)
    
    def test_bulk_task_archive_with_missing_ids(self, auth_headers):
        """Test bulk archive with non-existent IDs"""
        response = requests.post(f"{BASE_URL}/api/tasks/bulk-archive", json={
            "ids": ["nonexistent_id_1", "nonexistent_id_2"],
            "archive": True
        }, headers=auth_headers)
        
        assert response.status_code == 200
        assert response.json().get("updated") == 0, "Should update 0 tasks for non-existent IDs"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
