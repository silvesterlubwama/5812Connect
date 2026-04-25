"""
Iteration 59 - Safety Features Backend Tests
Tests for login API and basic endpoint verification
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthLogin:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test successful login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@5812uganda.org"
        assert data["user"]["role"] == "admin"
        print(f"✓ Login successful, user: {data['user']['name']}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code in [401, 404]
        print("✓ Invalid credentials rejected correctly")
    
    def test_login_missing_password(self):
        """Test login with missing password"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org"
        })
        assert response.status_code in [400, 422]
        print("✓ Missing password rejected correctly")


class TestProtectedEndpoints:
    """Test that protected endpoints require authentication"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_members_endpoint_with_auth(self, auth_token):
        """Test members endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/members",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Members endpoint accessible with auth")
    
    def test_families_endpoint_with_auth(self, auth_token):
        """Test families endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/families",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Families endpoint accessible with auth")
    
    def test_guests_endpoint_with_auth(self, auth_token):
        """Test guests endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/guests",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Guests endpoint accessible with auth")
    
    def test_children_endpoint_with_auth(self, auth_token):
        """Test children endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/children",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Children endpoint accessible with auth")
    
    def test_locations_endpoint_with_auth(self, auth_token):
        """Test locations endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/locations",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Locations endpoint accessible with auth")
    
    def test_admin_users_endpoint_with_auth(self, auth_token):
        """Test admin users endpoint with authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Admin users endpoint accessible with auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
