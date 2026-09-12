"""
Iteration 65 - Testing fixes for:
1. Default password changed to the default new-user password from tests/creds.py
2. Password reset sends email notification
3. System Admin toggle in UserEditDialog
4. Guest profile editing for admins
"""
import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://multi-tenant-scope.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD
DEFAULT_PASSWORD = creds.NEW_USER_PASSWORD


class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        return data["token"]
    
    def test_admin_login(self, admin_token):
        """Test admin can login with correct credentials"""
        assert admin_token is not None
        print(f"SUCCESS: Admin login successful, token obtained")


class TestUserCreationDefaultPassword:
    """Test user creation with default password the default new-user password from tests/creds.py"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_create_user_with_default_password(self, headers):
        """Test POST /api/admin/users creates user with default password the default new-user password from tests/creds.py"""
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"TEST_defaultpw_{unique_id}@test.com"
        
        # Create user without specifying password
        response = requests.post(f"{BASE_URL}/api/admin/users", json={
            "name": f"Test Default PW {unique_id}",
            "email": test_email,
            "phone": "1234567890",
            "role": "Staff"
        }, headers=headers)
        
        assert response.status_code == 200, f"User creation failed: {response.text}"
        data = response.json()
        
        # Verify temp_password is returned and equals default
        assert "temp_password" in data, "temp_password not returned in response"
        assert data["temp_password"] == DEFAULT_PASSWORD, f"Expected default password '{DEFAULT_PASSWORD}', got '{data['temp_password']}'"
        print(f"SUCCESS: User created with default password '{DEFAULT_PASSWORD}'")
        
        # Store user_id for cleanup
        user_id = data.get("id")
        
        # Verify user can login with default password
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": test_email,
            "password": DEFAULT_PASSWORD
        })
        assert login_response.status_code == 200, f"Login with default password failed: {login_response.text}"
        print(f"SUCCESS: User can login with default password '{DEFAULT_PASSWORD}'")
        
        # Cleanup - delete test user
        if user_id:
            requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)
    
    def test_create_user_with_custom_password(self, headers):
        """Test user creation with custom password still works"""
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"TEST_custompw_{unique_id}@test.com"
        custom_password = creds.CUSTOM_PASSWORD
        
        response = requests.post(f"{BASE_URL}/api/admin/users", json={
            "name": f"Test Custom PW {unique_id}",
            "email": test_email,
            "password": custom_password,
            "role": "Staff"
        }, headers=headers)
        
        assert response.status_code == 200, f"User creation failed: {response.text}"
        data = response.json()
        
        # Verify temp_password matches custom password
        assert data.get("temp_password") == custom_password, f"Expected custom password, got '{data.get('temp_password')}'"
        print(f"SUCCESS: User created with custom password")
        
        # Cleanup
        user_id = data.get("id")
        if user_id:
            requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)


class TestPasswordReset:
    """Test password reset functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_user(self, headers):
        """Create a test user for password reset testing"""
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"TEST_pwreset_{unique_id}@test.com"
        
        response = requests.post(f"{BASE_URL}/api/admin/users", json={
            "name": f"Test PW Reset {unique_id}",
            "email": test_email,
            "role": "Staff"
        }, headers=headers)
        
        assert response.status_code == 200, f"Test user creation failed: {response.text}"
        user_data = response.json()
        yield user_data
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/users/{user_data['id']}", headers=headers)
    
    def test_password_reset_stores_new_hash(self, headers, test_user):
        """Test POST /api/admin/users/{id}/reset-password stores new password hash correctly"""
        user_id = test_user["id"]
        new_password = creds.RESET_PASSWORD
        
        # Reset password
        response = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/reset-password", json={
            "new_password": new_password
        }, headers=headers)
        
        assert response.status_code == 200, f"Password reset failed: {response.text}"
        data = response.json()
        assert "message" in data, "No message in response"
        print(f"SUCCESS: Password reset endpoint returned success")
        
        # Verify user can login with new password
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": test_user["email"],
            "password": new_password
        })
        assert login_response.status_code == 200, f"Login with new password failed: {login_response.text}"
        print(f"SUCCESS: User can login with new password after reset")
    
    def test_password_reset_requires_min_length(self, headers, test_user):
        """Test password reset requires minimum 6 characters"""
        user_id = test_user["id"]
        
        response = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/reset-password", json={
            "new_password": "short"
        }, headers=headers)
        
        assert response.status_code == 400, f"Expected 400 for short password, got {response.status_code}"
        print(f"SUCCESS: Password reset correctly rejects short passwords")


class TestSystemAdminToggle:
    """Test System Admin toggle functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_user(self, headers):
        """Create a test user for admin toggle testing"""
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"TEST_admintoggle_{unique_id}@test.com"
        
        response = requests.post(f"{BASE_URL}/api/admin/users", json={
            "name": f"Test Admin Toggle {unique_id}",
            "email": test_email,
            "role": "Staff"
        }, headers=headers)
        
        assert response.status_code == 200, f"Test user creation failed: {response.text}"
        user_data = response.json()
        yield user_data
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/users/{user_data['id']}", headers=headers)
    
    def test_update_user_to_admin_role(self, headers, test_user):
        """Test updating user role to 'admin' via PUT /api/admin/users/{id}"""
        user_id = test_user["id"]
        
        # Update user to admin role
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "role": "admin"
        }, headers=headers)
        
        assert response.status_code == 200, f"User update failed: {response.text}"
        data = response.json()
        assert data.get("role") == "admin", f"Expected role 'admin', got '{data.get('role')}'"
        print(f"SUCCESS: User role updated to 'admin'")
        
        # Verify by fetching user
        get_response = requests.get(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)
        assert get_response.status_code == 200
        user_data = get_response.json()
        assert user_data.get("role") == "admin", f"User role not persisted as 'admin'"
        print(f"SUCCESS: Admin role persisted correctly")
    
    def test_update_user_back_to_staff(self, headers, test_user):
        """Test updating user role back to Staff"""
        user_id = test_user["id"]
        
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "role": "Staff"
        }, headers=headers)
        
        assert response.status_code == 200, f"User update failed: {response.text}"
        data = response.json()
        assert data.get("role") == "Staff", f"Expected role 'Staff', got '{data.get('role')}'"
        print(f"SUCCESS: User role updated back to 'Staff'")


class TestGuestEditing:
    """Test guest profile editing functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_guest(self, headers):
        """Create a test guest for editing"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Get first location for campus filter compatibility
        locs_resp = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        locs = locs_resp.json()
        location_id = locs[0]["id"] if locs else ""
        
        response = requests.post(f"{BASE_URL}/api/guests", json={
            "name": f"TEST Guest {unique_id}",
            "email": f"TEST_guest_{unique_id}@test.com",
            "phone": "9876543210",
            "is_parent": False,
            "notes": "Test guest for editing",
            "location_id": location_id
        }, headers=headers)
        
        assert response.status_code in [200, 201], f"Guest creation failed: {response.text}"
        guest_data = response.json()
        yield guest_data
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/guests/{guest_data['id']}", headers=headers)
    
    def test_guest_list_endpoint(self, headers):
        """Test GET /api/guests returns guest list"""
        response = requests.get(f"{BASE_URL}/api/guests", headers=headers)
        assert response.status_code == 200, f"Guest list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of guests"
        print(f"SUCCESS: Guest list endpoint works, found {len(data)} guests")
    
    def test_guest_update_endpoint(self, headers, test_guest):
        """Test PUT /api/guests/{id} updates guest record"""
        guest_id = test_guest["id"]
        
        # Update guest
        updated_data = {
            "name": f"{test_guest['name']} Updated",
            "phone": "1111111111",
            "email": test_guest.get("email", ""),
            "is_parent": True,
            "notes": "Updated notes",
            "address": "123 Test Street"
        }
        
        response = requests.put(f"{BASE_URL}/api/guests/{guest_id}", json=updated_data, headers=headers)
        assert response.status_code == 200, f"Guest update failed: {response.text}"
        data = response.json()
        
        # Verify updates
        assert "Updated" in data.get("name", ""), f"Name not updated: {data.get('name')}"
        assert data.get("phone") == "1111111111", f"Phone not updated: {data.get('phone')}"
        assert data.get("is_parent") == True, f"is_parent not updated: {data.get('is_parent')}"
        assert data.get("notes") == "Updated notes", f"Notes not updated: {data.get('notes')}"
        print(f"SUCCESS: Guest update endpoint works correctly")
    
    def test_guest_update_persists(self, headers):
        """Test guest updates are persisted in database"""
        # Create a fresh guest for this test
        unique_id = str(uuid.uuid4())[:8]
        
        # Get first location for campus filter compatibility
        locs_resp = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        locs = locs_resp.json()
        location_id = locs[0]["id"] if locs else ""
        
        create_resp = requests.post(f"{BASE_URL}/api/guests", json={
            "name": f"TEST Persist {unique_id}",
            "email": f"TEST_persist_{unique_id}@test.com",
            "location_id": location_id
        }, headers=headers)
        assert create_resp.status_code in [200, 201], f"Guest creation failed: {create_resp.text}"
        guest = create_resp.json()
        guest_id = guest["id"]
        
        # Update the guest
        update_resp = requests.put(f"{BASE_URL}/api/guests/{guest_id}", json={
            "name": f"TEST Persist {unique_id} VERIFIED",
            "phone": "3333333333",
            "location_id": location_id
        }, headers=headers)
        assert update_resp.status_code == 200, f"Guest update failed: {update_resp.text}"
        
        # Fetch guest list and find our guest
        response = requests.get(f"{BASE_URL}/api/guests", headers=headers)
        assert response.status_code == 200
        guests = response.json()
        
        # Find our test guest
        found_guest = None
        for g in guests:
            if g.get("id") == guest_id:
                found_guest = g
                break
        
        assert found_guest is not None, f"Test guest not found in list"
        assert "VERIFIED" in found_guest.get("name", ""), f"Update not persisted: {found_guest.get('name')}"
        print(f"SUCCESS: Guest update persisted correctly")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=headers)


class TestGuestsApiUpdate:
    """Test guestsApi.update method exists and works"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_guests_update_endpoint_exists(self, headers):
        """Test PUT /api/guests/{id} endpoint exists"""
        # Create a guest first
        unique_id = str(uuid.uuid4())[:8]
        create_response = requests.post(f"{BASE_URL}/api/guests", json={
            "name": f"TEST API Update {unique_id}",
            "email": f"TEST_apiupdate_{unique_id}@test.com"
        }, headers=headers)
        
        assert create_response.status_code in [200, 201], f"Guest creation failed: {create_response.text}"
        guest = create_response.json()
        guest_id = guest["id"]
        
        # Test update endpoint
        update_response = requests.put(f"{BASE_URL}/api/guests/{guest_id}", json={
            "name": f"TEST API Update {unique_id} Modified"
        }, headers=headers)
        
        # Should not be 404 or 405
        assert update_response.status_code not in [404, 405], f"PUT /api/guests/{guest_id} endpoint not found or not allowed"
        assert update_response.status_code == 200, f"Guest update failed: {update_response.text}"
        print(f"SUCCESS: guestsApi.update endpoint (PUT /api/guests/{{id}}) exists and works")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=headers)


class TestMajorPagesLoad:
    """Test major pages load correctly"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_dashboard_stats(self, headers):
        """Test dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        print(f"SUCCESS: Dashboard stats endpoint works")
    
    def test_members_list(self, headers):
        """Test members list endpoint"""
        response = requests.get(f"{BASE_URL}/api/members", headers=headers)
        assert response.status_code == 200, f"Members list failed: {response.text}"
        print(f"SUCCESS: Members list endpoint works")
    
    def test_admin_users_list(self, headers):
        """Test admin users list endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert response.status_code == 200, f"Admin users list failed: {response.text}"
        print(f"SUCCESS: Admin users list endpoint works")
    
    def test_guests_list(self, headers):
        """Test guests list endpoint"""
        response = requests.get(f"{BASE_URL}/api/guests", headers=headers)
        assert response.status_code == 200, f"Guests list failed: {response.text}"
        print(f"SUCCESS: Guests list endpoint works")
    
    def test_families_list(self, headers):
        """Test families list endpoint"""
        response = requests.get(f"{BASE_URL}/api/families", headers=headers)
        assert response.status_code == 200, f"Families list failed: {response.text}"
        print(f"SUCCESS: Families list endpoint works")
    
    def test_children_list(self, headers):
        """Test children list endpoint"""
        response = requests.get(f"{BASE_URL}/api/children", headers=headers)
        assert response.status_code == 200, f"Children list failed: {response.text}"
        print(f"SUCCESS: Children list endpoint works")
    
    def test_events_list(self, headers):
        """Test events list endpoint"""
        response = requests.get(f"{BASE_URL}/api/events", headers=headers)
        assert response.status_code == 200, f"Events list failed: {response.text}"
        print(f"SUCCESS: Events list endpoint works")
    
    def test_locations_list(self, headers):
        """Test locations list endpoint"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert response.status_code == 200, f"Locations list failed: {response.text}"
        print(f"SUCCESS: Locations list endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
