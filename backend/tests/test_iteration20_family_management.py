"""
Iteration 20: Family Management Features Tests
- GET /api/families/{id} returns family with children, parents (guests), and guardians
- POST /api/families/{id}/guardians adds a guardian to a family
- PUT /api/families/{id}/guardians/{gid} updates a guardian
- DELETE /api/families/{id}/guardians/{gid} removes a guardian
- GET /api/portal/family returns the parent's own family data
- PUT /api/portal/family allows parent to update their family details
- POST /api/portal/family/children allows parent to add a child
- POST /api/portal/family/guardians allows parent to add a guardian
- PUT /api/guests/{id} updates a guest record
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
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("token")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def test_family(auth_headers):
    """Create a test family for testing"""
    unique_id = str(uuid.uuid4())[:8]
    family_data = {
        "family_name": f"TEST_Family_{unique_id}",
        "primary_contact_name": "Test Parent",
        "primary_contact_email": f"testparent_{unique_id}@test.com",
        "primary_contact_phone": "+256700000001",
        "address": "123 Test Street"
    }
    response = requests.post(f"{BASE_URL}/api/families", json=family_data, headers=auth_headers)
    assert response.status_code == 200, f"Failed to create test family: {response.text}"
    family = response.json()
    yield family
    # Cleanup
    requests.delete(f"{BASE_URL}/api/families/{family['id']}", headers=auth_headers)

@pytest.fixture(scope="module")
def test_guest(auth_headers, test_family):
    """Create a test guest (parent) linked to the test family"""
    unique_id = str(uuid.uuid4())[:8]
    guest_data = {
        "name": f"TEST_Parent_{unique_id}",
        "email": f"testparent_{unique_id}@test.com",
        "phone": "+256700000002",
        "visit_date": "2025-01-01",
        "is_parent": True,
        "family_id": test_family["id"]
    }
    response = requests.post(f"{BASE_URL}/api/guests", json=guest_data, headers=auth_headers)
    assert response.status_code == 200, f"Failed to create test guest: {response.text}"
    guest = response.json()
    yield guest
    # Cleanup
    requests.delete(f"{BASE_URL}/api/guests/{guest['id']}", headers=auth_headers)


class TestFamilyDetailEndpoint:
    """Test GET /api/families/{id} returns family with children, parents, guardians"""
    
    def test_get_family_detail_returns_family(self, auth_headers, test_family):
        """GET /api/families/{id} returns the family"""
        response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get family detail: {response.text}"
        data = response.json()
        assert data["id"] == test_family["id"]
        assert data["family_name"] == test_family["family_name"]
        print(f"PASS: GET /api/families/{test_family['id']} returns family data")
    
    def test_get_family_detail_includes_children_array(self, auth_headers, test_family):
        """GET /api/families/{id} includes children array"""
        response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "children" in data, "Response should include 'children' array"
        assert isinstance(data["children"], list), "'children' should be a list"
        print(f"PASS: Family detail includes 'children' array")
    
    def test_get_family_detail_includes_parents_array(self, auth_headers, test_family):
        """GET /api/families/{id} includes parents array (from guests collection)"""
        response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "parents" in data, "Response should include 'parents' array"
        assert isinstance(data["parents"], list), "'parents' should be a list"
        print(f"PASS: Family detail includes 'parents' array")
    
    def test_get_family_detail_404_for_nonexistent(self, auth_headers):
        """GET /api/families/{id} returns 404 for non-existent family"""
        response = requests.get(f"{BASE_URL}/api/families/nonexistent_family_id", headers=auth_headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: GET /api/families/nonexistent returns 404")


class TestGuardianCRUD:
    """Test guardian CRUD operations on families"""
    
    def test_add_guardian_to_family(self, auth_headers, test_family):
        """POST /api/families/{id}/guardians adds a guardian"""
        guardian_data = {
            "name": "Test Guardian",
            "phone": "+256700000003",
            "email": "guardian@test.com",
            "relationship": "Grandparent"
        }
        response = requests.post(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians",
            json=guardian_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to add guardian: {response.text}"
        guardian = response.json()
        assert "id" in guardian, "Guardian should have an id"
        assert guardian["name"] == "Test Guardian"
        assert guardian["relationship"] == "Grandparent"
        print(f"PASS: POST /api/families/{test_family['id']}/guardians adds guardian")
        return guardian
    
    def test_guardian_appears_in_family_detail(self, auth_headers, test_family):
        """After adding guardian, it appears in family detail"""
        # First add a guardian
        guardian_data = {
            "name": "Detail Test Guardian",
            "phone": "+256700000004",
            "email": "detailguardian@test.com",
            "relationship": "Aunt/Uncle"
        }
        add_response = requests.post(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians",
            json=guardian_data,
            headers=auth_headers
        )
        assert add_response.status_code == 200
        added_guardian = add_response.json()
        
        # Now get family detail and check guardians
        response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        guardians = data.get("guardians", [])
        guardian_ids = [g["id"] for g in guardians]
        assert added_guardian["id"] in guardian_ids, "Added guardian should appear in family detail"
        print(f"PASS: Guardian appears in family detail after adding")
    
    def test_update_guardian(self, auth_headers, test_family):
        """PUT /api/families/{id}/guardians/{gid} updates a guardian"""
        # First add a guardian
        guardian_data = {
            "name": "Update Test Guardian",
            "phone": "+256700000005",
            "email": "updateguardian@test.com",
            "relationship": "Guardian"
        }
        add_response = requests.post(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians",
            json=guardian_data,
            headers=auth_headers
        )
        assert add_response.status_code == 200
        guardian = add_response.json()
        
        # Update the guardian
        update_data = {
            "name": "Updated Guardian Name",
            "phone": "+256700000006",
            "email": "updatedguardian@test.com",
            "relationship": "Nanny"
        }
        update_response = requests.put(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians/{guardian['id']}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200, f"Failed to update guardian: {update_response.text}"
        print(f"PASS: PUT /api/families/{test_family['id']}/guardians/{guardian['id']} updates guardian")
        
        # Verify update by getting family detail
        detail_response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert detail_response.status_code == 200
        family = detail_response.json()
        updated_guardian = next((g for g in family.get("guardians", []) if g["id"] == guardian["id"]), None)
        assert updated_guardian is not None, "Guardian should still exist"
        assert updated_guardian["name"] == "Updated Guardian Name", "Guardian name should be updated"
        assert updated_guardian["relationship"] == "Nanny", "Guardian relationship should be updated"
        print(f"PASS: Guardian update verified in family detail")
    
    def test_remove_guardian(self, auth_headers, test_family):
        """DELETE /api/families/{id}/guardians/{gid} removes a guardian"""
        # First add a guardian
        guardian_data = {
            "name": "Remove Test Guardian",
            "phone": "+256700000007",
            "email": "removeguardian@test.com",
            "relationship": "Sibling"
        }
        add_response = requests.post(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians",
            json=guardian_data,
            headers=auth_headers
        )
        assert add_response.status_code == 200
        guardian = add_response.json()
        
        # Remove the guardian
        delete_response = requests.delete(
            f"{BASE_URL}/api/families/{test_family['id']}/guardians/{guardian['id']}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200, f"Failed to remove guardian: {delete_response.text}"
        print(f"PASS: DELETE /api/families/{test_family['id']}/guardians/{guardian['id']} removes guardian")
        
        # Verify removal by getting family detail
        detail_response = requests.get(f"{BASE_URL}/api/families/{test_family['id']}", headers=auth_headers)
        assert detail_response.status_code == 200
        family = detail_response.json()
        guardian_ids = [g["id"] for g in family.get("guardians", [])]
        assert guardian["id"] not in guardian_ids, "Removed guardian should not appear in family detail"
        print(f"PASS: Guardian removal verified in family detail")


class TestPortalFamilyEndpoints:
    """Test portal family endpoints for parent self-service"""
    
    def test_get_portal_family_returns_data(self, auth_headers):
        """GET /api/portal/family returns family data or null message"""
        response = requests.get(f"{BASE_URL}/api/portal/family", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get portal family: {response.text}"
        data = response.json()
        # Admin user may not have a linked family, so we check for either family or message
        assert "family" in data or "message" in data, "Response should have 'family' or 'message'"
        print(f"PASS: GET /api/portal/family returns data (family: {data.get('family') is not None})")
    
    def test_get_portal_family_structure(self, auth_headers):
        """GET /api/portal/family returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/portal/family", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have children and parents arrays even if empty
        assert "children" in data, "Response should have 'children' key"
        assert "parents" in data, "Response should have 'parents' key"
        print(f"PASS: GET /api/portal/family has expected structure")


class TestPortalFamilyWithLinkedFamily:
    """Test portal family endpoints with a family linked to admin user"""
    
    @pytest.fixture(scope="class")
    def admin_linked_family(self, auth_headers):
        """Create a family linked to admin user's email"""
        unique_id = str(uuid.uuid4())[:8]
        family_data = {
            "family_name": f"TEST_AdminFamily_{unique_id}",
            "primary_contact_name": "Admin User",
            "primary_contact_email": "admin@5812uganda.org",  # Admin's email
            "primary_contact_phone": "+256700000010",
            "address": "Admin Test Address"
        }
        response = requests.post(f"{BASE_URL}/api/families", json=family_data, headers=auth_headers)
        assert response.status_code == 200, f"Failed to create admin-linked family: {response.text}"
        family = response.json()
        yield family
        # Cleanup
        requests.delete(f"{BASE_URL}/api/families/{family['id']}", headers=auth_headers)
    
    def test_portal_family_returns_linked_family(self, auth_headers, admin_linked_family):
        """GET /api/portal/family returns family when linked by email"""
        response = requests.get(f"{BASE_URL}/api/portal/family", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("family") is not None, "Should return linked family"
        assert data["family"]["id"] == admin_linked_family["id"], "Should return the correct family"
        print(f"PASS: GET /api/portal/family returns linked family")
    
    def test_portal_update_family(self, auth_headers, admin_linked_family):
        """PUT /api/portal/family updates family details"""
        update_data = {
            "family_name": f"Updated_{admin_linked_family['family_name']}",
            "address": "Updated Address 123",
            "notes": "Test notes from portal",
            "primary_contact_phone": "+256700000011"
        }
        response = requests.put(f"{BASE_URL}/api/portal/family", json=update_data, headers=auth_headers)
        assert response.status_code == 200, f"Failed to update family via portal: {response.text}"
        updated = response.json()
        assert updated["address"] == "Updated Address 123", "Address should be updated"
        print(f"PASS: PUT /api/portal/family updates family details")
    
    def test_portal_add_child(self, auth_headers, admin_linked_family):
        """POST /api/portal/family/children adds a child"""
        unique_id = str(uuid.uuid4())[:8]
        child_data = {
            "name": f"TEST_PortalChild_{unique_id}",
            "date_of_birth": "2020-01-15",
            "gender": "male",
            "class_group": "Nursery",
            "medical_notes": "None",
            "allergies": ""
        }
        response = requests.post(f"{BASE_URL}/api/portal/family/children", json=child_data, headers=auth_headers)
        assert response.status_code == 200, f"Failed to add child via portal: {response.text}"
        child = response.json()
        assert "id" in child, "Child should have an id"
        assert child["name"] == child_data["name"], "Child name should match"
        assert child["family_id"] == admin_linked_family["id"], "Child should be linked to family"
        print(f"PASS: POST /api/portal/family/children adds child to family")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/children/{child['id']}", headers=auth_headers)
    
    def test_portal_add_guardian(self, auth_headers, admin_linked_family):
        """POST /api/portal/family/guardians adds a guardian"""
        guardian_data = {
            "name": "Portal Test Guardian",
            "phone": "+256700000012",
            "email": "portalguardian@test.com",
            "relationship": "Grandparent"
        }
        response = requests.post(f"{BASE_URL}/api/portal/family/guardians", json=guardian_data, headers=auth_headers)
        assert response.status_code == 200, f"Failed to add guardian via portal: {response.text}"
        guardian = response.json()
        assert "id" in guardian, "Guardian should have an id"
        assert guardian["name"] == "Portal Test Guardian", "Guardian name should match"
        print(f"PASS: POST /api/portal/family/guardians adds guardian to family")


class TestGuestUpdate:
    """Test PUT /api/guests/{id} updates a guest record"""
    
    def test_update_guest(self, auth_headers, test_guest):
        """PUT /api/guests/{id} updates guest fields"""
        update_data = {
            "name": f"Updated_{test_guest['name']}",
            "email": "updated_guest@test.com",
            "phone": "+256700000099",
            "visit_date": "2025-02-01",
            "notes": "Updated via test"
        }
        response = requests.put(f"{BASE_URL}/api/guests/{test_guest['id']}", json=update_data, headers=auth_headers)
        assert response.status_code == 200, f"Failed to update guest: {response.text}"
        updated = response.json()
        assert updated["email"] == "updated_guest@test.com", "Email should be updated"
        assert updated["phone"] == "+256700000099", "Phone should be updated"
        print(f"PASS: PUT /api/guests/{test_guest['id']} updates guest record")
    
    def test_update_guest_verify_persistence(self, auth_headers, test_guest):
        """Verify guest update persists by fetching guest list"""
        # First update
        update_data = {
            "name": test_guest['name'],
            "email": "persistence_test@test.com",
            "phone": "+256700000098"
        }
        requests.put(f"{BASE_URL}/api/guests/{test_guest['id']}", json=update_data, headers=auth_headers)
        
        # Fetch guests and verify
        response = requests.get(f"{BASE_URL}/api/guests", headers=auth_headers)
        assert response.status_code == 200
        guests = response.json()
        updated_guest = next((g for g in guests if g["id"] == test_guest["id"]), None)
        assert updated_guest is not None, "Guest should exist in list"
        assert updated_guest["email"] == "persistence_test@test.com", "Update should persist"
        print(f"PASS: Guest update persists in database")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
