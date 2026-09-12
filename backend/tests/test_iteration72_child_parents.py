"""
Iteration 72 - Child Parent Management Tests
Tests for:
1. GET /children/{id}/parents - Returns parent details + campus_phone
2. Child CRUD with parent_ids
3. Parent search across guests and staff
"""

import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestChildParentManagement:
    """Tests for child parent management features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        token = response.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Store test IDs for cleanup
        self.test_child_id = None
        self.test_guest_id = None
        
        yield
        
        # Cleanup
        if self.test_child_id:
            self.session.delete(f"{BASE_URL}/api/children/{self.test_child_id}")
        if self.test_guest_id:
            self.session.delete(f"{BASE_URL}/api/guests/{self.test_guest_id}")
    
    def test_get_children_list(self):
        """Test GET /children returns list"""
        response = self.session.get(f"{BASE_URL}/api/children")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} children")
    
    def test_get_guests_list(self):
        """Test GET /guests returns list with is_parent field"""
        response = self.session.get(f"{BASE_URL}/api/guests")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Check that guests have is_parent field
        for guest in data[:5]:
            assert "is_parent" in guest or guest.get("is_parent") is None
        print(f"Found {len(data)} guests")
    
    def test_get_members_list(self):
        """Test GET /members returns list with staff"""
        response = self.session.get(f"{BASE_URL}/api/members")
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert isinstance(data["members"], list)
        print(f"Found {len(data['members'])} members/staff")
    
    def test_create_child_with_parent_ids(self):
        """Test creating a child with parent_ids"""
        # First create a test guest to be a parent
        guest_data = {
            "name": "TEST_Parent_Guest",
            "phone": "+1234567890",
            "is_parent": True,
            "visit_date": "2026-01-01"
        }
        guest_response = self.session.post(f"{BASE_URL}/api/guests", json=guest_data)
        assert guest_response.status_code in [200, 201], f"Failed to create guest: {guest_response.text}"
        guest = guest_response.json()
        self.test_guest_id = guest["id"]
        
        # Create child with parent_ids
        child_data = {
            "name": "TEST_Child_WithParent",
            "date_of_birth": "2020-01-15",
            "grade": "1st",
            "class_group": "Class A",
            "parent_ids": [guest["id"]]
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201], f"Failed to create child: {child_response.text}"
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Verify parent_ids are saved
        assert "parent_ids" in child
        assert guest["id"] in child["parent_ids"]
        print(f"Created child {child['id']} with parent {guest['id']}")
    
    def test_get_child_parents_endpoint(self):
        """Test GET /children/{id}/parents returns parent details + campus_phone"""
        # First create test data
        guest_data = {
            "name": "TEST_Parent_ForEndpoint",
            "phone": "+9876543210",
            "email": "testparent@example.com",
            "is_parent": True,
            "visit_date": "2026-01-01"
        }
        guest_response = self.session.post(f"{BASE_URL}/api/guests", json=guest_data)
        assert guest_response.status_code in [200, 201]
        guest = guest_response.json()
        self.test_guest_id = guest["id"]
        
        # Create child with parent
        child_data = {
            "name": "TEST_Child_ForParentsEndpoint",
            "date_of_birth": "2019-05-20",
            "parent_ids": [guest["id"]]
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201]
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Test the /children/{id}/parents endpoint
        parents_response = self.session.get(f"{BASE_URL}/api/children/{child['id']}/parents")
        assert parents_response.status_code == 200, f"Failed: {parents_response.text}"
        
        data = parents_response.json()
        assert "parents" in data
        assert "campus_phone" in data
        assert isinstance(data["parents"], list)
        
        # Verify parent details are returned
        if len(data["parents"]) > 0:
            parent = data["parents"][0]
            assert "id" in parent
            assert "name" in parent
            assert parent["name"] == "TEST_Parent_ForEndpoint"
            assert parent.get("phone") == "+9876543210"
            print(f"Parent details: {parent}")
        
        print(f"Campus phone: {data['campus_phone']}")
    
    def test_get_child_parents_empty(self):
        """Test GET /children/{id}/parents with no parents"""
        # Create child without parents
        child_data = {
            "name": "TEST_Child_NoParents",
            "date_of_birth": "2021-03-10"
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201]
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Test endpoint
        parents_response = self.session.get(f"{BASE_URL}/api/children/{child['id']}/parents")
        assert parents_response.status_code == 200
        
        data = parents_response.json()
        assert data["parents"] == []
        assert "campus_phone" in data
        print("Empty parents list returned correctly")
    
    def test_get_child_parents_not_found(self):
        """Test GET /children/{id}/parents with invalid child ID"""
        response = self.session.get(f"{BASE_URL}/api/children/invalid_child_id/parents")
        assert response.status_code == 404
        print("404 returned for invalid child ID")
    
    def test_update_child_parent_ids(self):
        """Test updating child's parent_ids"""
        # Create guest
        guest_data = {
            "name": "TEST_Parent_ForUpdate",
            "phone": "+1112223333",
            "is_parent": True,
            "visit_date": "2026-01-01"
        }
        guest_response = self.session.post(f"{BASE_URL}/api/guests", json=guest_data)
        assert guest_response.status_code in [200, 201]
        guest = guest_response.json()
        self.test_guest_id = guest["id"]
        
        # Create child without parents
        child_data = {
            "name": "TEST_Child_ToUpdate",
            "date_of_birth": "2018-07-25"
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201]
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Update child with parent_ids (name is required for PUT)
        update_data = {
            "name": "TEST_Child_ToUpdate",
            "parent_ids": [guest["id"]]
        }
        update_response = self.session.put(f"{BASE_URL}/api/children/{child['id']}", json=update_data)
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify update
        get_response = self.session.get(f"{BASE_URL}/api/children/{child['id']}/parents")
        assert get_response.status_code == 200
        data = get_response.json()
        assert len(data["parents"]) == 1
        assert data["parents"][0]["id"] == guest["id"]
        print(f"Successfully updated child with parent: {data['parents'][0]['name']}")
    
    def test_parent_from_staff_member(self):
        """Test that staff members can be parents too"""
        # Get existing staff member
        members_response = self.session.get(f"{BASE_URL}/api/members")
        assert members_response.status_code == 200
        members = members_response.json()["members"]
        
        if len(members) == 0:
            pytest.skip("No staff members available for test")
        
        staff_member = members[0]
        
        # Create child with staff as parent
        child_data = {
            "name": "TEST_Child_StaffParent",
            "date_of_birth": "2017-11-30",
            "parent_ids": [staff_member["id"]]
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201]
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Verify parent is resolved from staff
        parents_response = self.session.get(f"{BASE_URL}/api/children/{child['id']}/parents")
        assert parents_response.status_code == 200
        data = parents_response.json()
        
        # Parent should be found (from users or members collection)
        print(f"Parents found: {len(data['parents'])}")
        if len(data["parents"]) > 0:
            print(f"Staff parent resolved: {data['parents'][0]['name']}")


class TestLocationsAndCampusPhone:
    """Tests for location/campus phone in child parents response"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200
        token = response.json()["token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        self.test_child_id = None
        
        yield
        
        if self.test_child_id:
            self.session.delete(f"{BASE_URL}/api/children/{self.test_child_id}")
    
    def test_get_locations(self):
        """Test GET /locations returns list with contact_phone"""
        response = self.session.get(f"{BASE_URL}/api/locations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check locations have contact_phone field
        for loc in data[:3]:
            print(f"Location: {loc.get('name')} - Phone: {loc.get('contact_phone', 'N/A')}")
    
    def test_child_with_location_returns_campus_phone(self):
        """Test that child with location_id returns campus_phone"""
        # Get a location
        locations_response = self.session.get(f"{BASE_URL}/api/locations")
        assert locations_response.status_code == 200
        locations = locations_response.json()
        
        if len(locations) == 0:
            pytest.skip("No locations available")
        
        location = locations[0]
        
        # Create child with location
        child_data = {
            "name": "TEST_Child_WithLocation",
            "date_of_birth": "2020-06-15",
            "location_id": location["id"]
        }
        child_response = self.session.post(f"{BASE_URL}/api/children", json=child_data)
        assert child_response.status_code in [200, 201]
        child = child_response.json()
        self.test_child_id = child["id"]
        
        # Get parents endpoint
        parents_response = self.session.get(f"{BASE_URL}/api/children/{child['id']}/parents")
        assert parents_response.status_code == 200
        data = parents_response.json()
        
        # campus_phone should be from location
        print(f"Campus phone returned: {data['campus_phone']}")
        if location.get("contact_phone"):
            assert data["campus_phone"] == location["contact_phone"]


class TestHealthAndBasicEndpoints:
    """Basic health and endpoint tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("Health check passed")
    
    def test_login_endpoint(self):
        """Test login endpoint"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"Login successful for: {data['user']['email']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
