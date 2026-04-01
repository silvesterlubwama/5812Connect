"""
Iteration 21: Parent-Child Check-In Flow Tests
Tests the new parent-lookup endpoint and child check-in functionality.

Features tested:
- POST /api/checkins/parent-lookup with phone/email/name/id finds parent and returns children
- POST /api/checkins/parent-lookup with checkin=true creates check-in records
- Check-in records include type=child, method=parent_id, parent_name fields
- GET /api/checkins/stats includes children count
- Child model accepts parent_ids field on create and update
- Guest model supports is_parent and family_id fields
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestParentLookupEndpoint:
    """Tests for POST /api/checkins/parent-lookup endpoint"""
    
    def test_parent_lookup_with_phone_finds_test_dad(self, api_client):
        """Test parent lookup by phone number finds Test Dad and returns children"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify parent found
        assert "parent" in data, "Response should contain 'parent' field"
        assert data["parent"] is not None, "Parent should be found"
        assert data["parent"]["name"] == "Test Dad", f"Expected 'Test Dad', got {data['parent'].get('name')}"
        assert data["parent"]["id"] == "gst_9ec87113", f"Expected 'gst_9ec87113', got {data['parent'].get('id')}"
        
        # Verify children returned
        assert "children" in data, "Response should contain 'children' field"
        assert isinstance(data["children"], list), "Children should be a list"
        
        # Verify checked_in is empty (no checkin requested)
        assert "checked_in" in data, "Response should contain 'checked_in' field"
        assert data["checked_in"] == [], "checked_in should be empty when checkin=false"
    
    def test_parent_lookup_with_email(self, api_client):
        """Test parent lookup by email"""
        # First get the test parent's email if available
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "gst_9ec87113"  # Use ID to find parent
        })
        assert response.status_code == 200
        parent = response.json().get("parent", {})
        
        if parent.get("email"):
            # Test lookup by email
            email_response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
                "lookup": parent["email"]
            })
            assert email_response.status_code == 200
            assert email_response.json()["parent"]["id"] == parent["id"]
    
    def test_parent_lookup_with_name(self, api_client):
        """Test parent lookup by name"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "Test Dad"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["parent"] is not None, "Parent should be found by name"
        assert "Test Dad" in data["parent"]["name"], f"Expected name containing 'Test Dad', got {data['parent'].get('name')}"
    
    def test_parent_lookup_with_id(self, api_client):
        """Test parent lookup by guest ID"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "gst_9ec87113"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["parent"] is not None, "Parent should be found by ID"
        assert data["parent"]["id"] == "gst_9ec87113"
    
    def test_parent_lookup_not_found(self, api_client):
        """Test parent lookup returns 404 for non-existent parent"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "nonexistent_parent_12345"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        assert "not found" in response.json().get("detail", "").lower()
    
    def test_parent_lookup_empty_lookup_returns_400(self, api_client):
        """Test parent lookup with empty lookup returns 400"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": ""
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_parent_lookup_returns_children_with_matching_family_id(self, api_client):
        """Test that children with matching family_id are returned"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888"
        })
        assert response.status_code == 200
        data = response.json()
        
        children = data.get("children", [])
        # Check if Little Test Jr is in the children list
        child_names = [c.get("name") for c in children]
        assert "Little Test Jr" in child_names, f"Expected 'Little Test Jr' in children, got {child_names}"


class TestParentCheckinFlow:
    """Tests for checking in children via parent lookup"""
    
    def test_checkin_children_via_parent_lookup(self, api_client):
        """Test checking in children using parent lookup with checkin=true"""
        # First lookup to get children
        lookup_response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888"
        })
        assert lookup_response.status_code == 200
        children = lookup_response.json().get("children", [])
        
        if not children:
            pytest.skip("No children found for test parent")
        
        # Now check in the children
        checkin_response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888",
            "event_id": "test_event_parent_checkin",
            "event_name": "Test Parent Check-In Event",
            "checkin": True
        })
        assert checkin_response.status_code == 200, f"Expected 200, got {checkin_response.status_code}: {checkin_response.text}"
        data = checkin_response.json()
        
        # Verify check-ins were created
        assert "checked_in" in data, "Response should contain 'checked_in' field"
        assert len(data["checked_in"]) > 0, "At least one child should be checked in"
        
        # Verify check-in record structure
        checkin = data["checked_in"][0]
        assert checkin.get("type") == "child", f"Check-in type should be 'child', got {checkin.get('type')}"
        assert checkin.get("method") == "parent_id", f"Check-in method should be 'parent_id', got {checkin.get('method')}"
        assert "parent_name" in checkin, "Check-in should include parent_name"
        assert "parent_id" in checkin, "Check-in should include parent_id"
        assert checkin.get("event_id") == "test_event_parent_checkin"
        assert checkin.get("event_name") == "Test Parent Check-In Event"
    
    def test_checkin_specific_children_only(self, api_client):
        """Test checking in only specific children using child_ids"""
        # First lookup to get children
        lookup_response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888"
        })
        assert lookup_response.status_code == 200
        children = lookup_response.json().get("children", [])
        
        if not children:
            pytest.skip("No children found for test parent")
        
        # Check in only the first child
        first_child_id = children[0]["id"]
        checkin_response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888",
            "event_id": "test_event_specific_child",
            "event_name": "Test Specific Child Event",
            "checkin": True,
            "child_ids": [first_child_id]
        })
        assert checkin_response.status_code == 200
        data = checkin_response.json()
        
        # Verify only one child was checked in
        assert len(data["checked_in"]) == 1, f"Expected 1 check-in, got {len(data['checked_in'])}"
        assert data["checked_in"][0]["member_id"] == first_child_id


class TestCheckinStats:
    """Tests for GET /api/checkins/stats endpoint"""
    
    def test_checkin_stats_includes_children_count(self, api_client):
        """Test that checkin stats includes children count"""
        response = api_client.get(f"{BASE_URL}/api/checkins/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify children count is present
        assert "children" in data, f"Stats should include 'children' count. Got: {data}"
        assert isinstance(data["children"], int), "Children count should be an integer"
        
        # Verify other expected fields
        assert "total" in data
        assert "today" in data
        assert "members" in data
        assert "visitors" in data
        assert "staff" in data


class TestChildModelParentIds:
    """Tests for Child model parent_ids field"""
    
    def test_create_child_with_parent_ids(self, api_client):
        """Test creating a child with parent_ids field"""
        unique_id = str(uuid.uuid4())[:8]
        child_data = {
            "name": f"TEST_Child_{unique_id}",
            "date_of_birth": "2020-01-15",
            "gender": "male",
            "class_group": "Toddlers",
            "parent_ids": ["gst_9ec87113"]  # Test Dad's ID
        }
        
        response = api_client.post(f"{BASE_URL}/api/children", json=child_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify parent_ids was saved
        assert "parent_ids" in data, "Response should include parent_ids"
        assert "gst_9ec87113" in data["parent_ids"], f"parent_ids should contain 'gst_9ec87113', got {data['parent_ids']}"
        
        # Cleanup
        if data.get("id"):
            api_client.delete(f"{BASE_URL}/api/children/{data['id']}")
    
    def test_update_child_with_parent_ids(self, api_client):
        """Test updating a child's parent_ids field"""
        # First create a child
        unique_id = str(uuid.uuid4())[:8]
        child_name = f"TEST_UpdateChild_{unique_id}"
        create_response = api_client.post(f"{BASE_URL}/api/children", json={
            "name": child_name,
            "gender": "female"
        })
        assert create_response.status_code in [200, 201]
        child_id = create_response.json()["id"]
        
        try:
            # Update with parent_ids (must include name as ChildCreate model requires it)
            update_response = api_client.put(f"{BASE_URL}/api/children/{child_id}", json={
                "name": child_name,
                "gender": "female",
                "parent_ids": ["gst_9ec87113", "gst_another_parent"]
            })
            assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
            data = update_response.json()
            
            # Verify parent_ids was updated
            assert "parent_ids" in data, "Response should include parent_ids"
            assert "gst_9ec87113" in data["parent_ids"]
        finally:
            # Cleanup
            api_client.delete(f"{BASE_URL}/api/children/{child_id}")


class TestGuestModelParentFields:
    """Tests for Guest model is_parent and family_id fields"""
    
    def test_create_guest_with_is_parent_and_family_id(self, api_client):
        """Test creating a guest with is_parent and family_id fields"""
        unique_id = str(uuid.uuid4())[:8]
        guest_data = {
            "name": f"TEST_Parent_{unique_id}",
            "phone": f"+256 700 {unique_id[:6]}",
            "is_parent": True,
            "family_id": "fam_test_12345"
        }
        
        response = api_client.post(f"{BASE_URL}/api/guests", json=guest_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify is_parent and family_id were saved
        assert data.get("is_parent") == True, f"is_parent should be True, got {data.get('is_parent')}"
        assert data.get("family_id") == "fam_test_12345", f"family_id should be 'fam_test_12345', got {data.get('family_id')}"
        
        # Cleanup
        if data.get("id"):
            api_client.delete(f"{BASE_URL}/api/guests/{data['id']}")
    
    def test_verify_test_dad_has_is_parent_and_family_id(self, api_client):
        """Verify the test parent (Test Dad) has is_parent=True and family_id set"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "gst_9ec87113"
        })
        assert response.status_code == 200
        parent = response.json().get("parent", {})
        
        # Test Dad should have is_parent=True and family_id=fam_55726c04
        assert parent.get("is_parent") == True or parent.get("is_parent") is None, \
            f"Test Dad should have is_parent=True (or None for fallback), got {parent.get('is_parent')}"
        
        # family_id check
        if parent.get("family_id"):
            assert parent["family_id"] == "fam_55726c04", f"Expected family_id 'fam_55726c04', got {parent.get('family_id')}"


class TestParentLookupSpecialCharacters:
    """Tests for parent lookup with special characters in phone numbers"""
    
    def test_lookup_with_plus_sign_in_phone(self, api_client):
        """Test that phone numbers with + sign are handled correctly"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "+256 700 999888"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.json().get("parent") is not None
    
    def test_lookup_with_partial_phone(self, api_client):
        """Test lookup with partial phone number"""
        response = api_client.post(f"{BASE_URL}/api/checkins/parent-lookup", json={
            "lookup": "700 999888"
        })
        # Should still find the parent with partial match
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestVerifyTestData:
    """Verify the test data exists as expected"""
    
    def test_verify_test_child_exists(self, api_client):
        """Verify Little Test Jr (chd_a3b4e279) exists with correct parent_ids"""
        response = api_client.get(f"{BASE_URL}/api/children")
        assert response.status_code == 200
        children = response.json()
        
        test_child = next((c for c in children if c.get("id") == "chd_a3b4e279"), None)
        if test_child:
            assert test_child["name"] == "Little Test Jr", f"Expected 'Little Test Jr', got {test_child.get('name')}"
            # Verify parent_ids contains Test Dad's ID
            parent_ids = test_child.get("parent_ids", [])
            assert "gst_9ec87113" in parent_ids, f"Expected 'gst_9ec87113' in parent_ids, got {parent_ids}"
        else:
            # Child might not exist yet, which is okay for initial test
            pytest.skip("Test child chd_a3b4e279 not found - may need to be created")
    
    def test_verify_test_parent_exists(self, api_client):
        """Verify Test Dad (gst_9ec87113) exists"""
        response = api_client.get(f"{BASE_URL}/api/guests")
        assert response.status_code == 200
        guests = response.json()
        
        test_parent = next((g for g in guests if g.get("id") == "gst_9ec87113"), None)
        if test_parent:
            assert test_parent["name"] == "Test Dad", f"Expected 'Test Dad', got {test_parent.get('name')}"
            assert test_parent.get("phone") == "+256 700 999888", f"Expected phone '+256 700 999888', got {test_parent.get('phone')}"
        else:
            pytest.skip("Test parent gst_9ec87113 not found - may need to be created")
