"""
Iteration 8 Backend Tests - 58:12 Global Connect CRM
Tests for:
1. Auth router refactoring (routers/auth.py)
2. Members router refactoring (routers/members.py)
3. CSV import router (routers/import_csv.py)
4. Push notification endpoints
5. Biometric/NFC endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASSWORD = "Admin@1234"
ADMIN2_EMAIL = "admin@5812uganda.org"
ADMIN2_PASSWORD = "Admin@5812"


class TestHealthAndBasics:
    """Basic health check tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("PASS: Health endpoint returns healthy status")


class TestAuthRouter:
    """Tests for the refactored auth router (routers/auth.py)"""
    
    def test_login_admin_primary(self):
        """POST /api/auth/login with admin@5812global.org / Admin@1234"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == ADMIN_EMAIL.lower()
        print(f"PASS: Admin login successful - {ADMIN_EMAIL}")
    
    def test_login_admin_secondary(self):
        """POST /api/auth/login with admin@5812uganda.org / Admin@5812"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN2_EMAIL,
            "password": ADMIN2_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"PASS: Admin2 login successful - {ADMIN2_EMAIL}")
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "invalid@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("PASS: Invalid credentials rejected with 401")
    
    def test_auth_me_requires_token(self):
        """GET /api/auth/me requires authentication"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("PASS: /api/auth/me requires authentication")
    
    def test_auth_me_with_token(self):
        """GET /api/auth/me returns user info with valid token"""
        # Login first
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        
        # Get user info
        response = requests.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "name" in data
        print("PASS: /api/auth/me returns user info with valid token")


class TestMembersRouter:
    """Tests for the refactored members router (routers/members.py)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_list_members(self, auth_token):
        """GET /api/members returns members list with total count"""
        response = requests.get(f"{BASE_URL}/api/members", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        assert isinstance(data["members"], list)
        assert isinstance(data["total"], int)
        print(f"PASS: GET /api/members returns {data['total']} members")
    
    def test_list_families(self, auth_token):
        """GET /api/families returns families list"""
        response = requests.get(f"{BASE_URL}/api/families", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/families returns {len(data)} families")
    
    def test_list_children(self, auth_token):
        """GET /api/children returns children list"""
        response = requests.get(f"{BASE_URL}/api/children", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/children returns {len(data)} children")
    
    def test_list_guests(self, auth_token):
        """GET /api/guests returns guests list"""
        response = requests.get(f"{BASE_URL}/api/guests", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/guests returns {len(data)} guests")
    
    def test_list_badges(self, auth_token):
        """GET /api/badges returns badges list"""
        response = requests.get(f"{BASE_URL}/api/badges", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/badges returns {len(data)} badges")
    
    def test_approve_member_endpoint_exists(self, auth_token):
        """PUT /api/members/{id}/approve endpoint exists"""
        # Use a non-existent member ID to test endpoint exists
        response = requests.put(f"{BASE_URL}/api/members/nonexistent_id/approve", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # Should return 404 (member not found) not 405 (method not allowed)
        assert response.status_code in [200, 404]
        print("PASS: PUT /api/members/{id}/approve endpoint exists")


class TestCSVImportRouter:
    """Tests for the CSV import router (routers/import_csv.py)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_csv_members_endpoint_requires_auth(self):
        """POST /api/import/csv/members requires authentication"""
        response = requests.post(f"{BASE_URL}/api/import/csv/members")
        assert response.status_code == 401
        print("PASS: POST /api/import/csv/members requires authentication")
    
    def test_csv_members_endpoint_exists(self, auth_token):
        """POST /api/import/csv/members endpoint exists"""
        # Send empty request to check endpoint exists
        response = requests.post(f"{BASE_URL}/api/import/csv/members", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        # Should return 422 (validation error for missing file) not 404
        assert response.status_code in [422, 400]
        print("PASS: POST /api/import/csv/members endpoint exists")


class TestPushNotificationEndpoints:
    """Tests for push notification endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_vapid_key_endpoint(self):
        """GET /api/push/vapid-key returns publicKey"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-key")
        assert response.status_code == 200
        data = response.json()
        assert "publicKey" in data
        # VAPID key should be a non-empty string
        assert isinstance(data["publicKey"], str)
        print(f"PASS: GET /api/push/vapid-key returns publicKey: {data['publicKey'][:20]}...")
    
    def test_push_subscribe_requires_auth(self):
        """POST /api/push/subscribe requires authentication"""
        response = requests.post(f"{BASE_URL}/api/push/subscribe", json={
            "subscription": {"endpoint": "https://example.com"}
        })
        assert response.status_code == 401
        print("PASS: POST /api/push/subscribe requires authentication")
    
    def test_push_subscribe_validates_subscription(self, auth_token):
        """POST /api/push/subscribe validates subscription object"""
        # Invalid subscription (missing endpoint)
        response = requests.post(f"{BASE_URL}/api/push/subscribe", 
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"subscription": {}}
        )
        assert response.status_code == 400
        print("PASS: POST /api/push/subscribe validates subscription object")


class TestBiometricEndpoints:
    """Tests for biometric verification endpoints"""
    
    def test_biometric_verify_endpoint_exists(self):
        """POST /api/biometric/verify endpoint exists and returns expected response"""
        response = requests.post(f"{BASE_URL}/api/biometric/verify", json={
            "credential_id": "unknown_credential_123"
        })
        # Should return 404 (credential not found) not 405 (method not allowed)
        assert response.status_code in [404, 400]
        print("PASS: POST /api/biometric/verify endpoint exists (returns 404 for unknown credential)")
    
    def test_biometric_verify_requires_credential_id(self):
        """POST /api/biometric/verify requires credential_id"""
        response = requests.post(f"{BASE_URL}/api/biometric/verify", json={})
        assert response.status_code == 400
        print("PASS: POST /api/biometric/verify requires credential_id")


class TestNFCEndpoints:
    """Tests for NFC scan endpoints"""
    
    def test_nfc_scan_endpoint_exists(self):
        """POST /api/nfc/scan endpoint exists and returns expected response"""
        response = requests.post(f"{BASE_URL}/api/nfc/scan", json={
            "serial_number": "04:A2:B3:C4:D5"
        })
        # Should return 404 (tag not registered) not 405 (method not allowed)
        assert response.status_code in [404, 400]
        print("PASS: POST /api/nfc/scan endpoint exists (returns 404 for unknown tag)")
    
    def test_nfc_scan_requires_serial_number(self):
        """POST /api/nfc/scan requires serial_number"""
        response = requests.post(f"{BASE_URL}/api/nfc/scan", json={})
        assert response.status_code == 400
        print("PASS: POST /api/nfc/scan requires serial_number")


class TestRouterIntegration:
    """Tests to verify routers are properly integrated"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_all_member_crud_endpoints(self, auth_token):
        """Verify all member CRUD endpoints work through the new router"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # List members
        list_res = requests.get(f"{BASE_URL}/api/members", headers=headers)
        assert list_res.status_code == 200
        
        # Create member
        create_res = requests.post(f"{BASE_URL}/api/members", headers=headers, json={
            "name": "TEST_Router_Integration_Member",
            "email": "test_router_integration@example.com",
            "role": "Member"
        })
        assert create_res.status_code == 200
        member_id = create_res.json()["id"]
        
        # Get member
        get_res = requests.get(f"{BASE_URL}/api/members/{member_id}", headers=headers)
        assert get_res.status_code == 200
        
        # Update member
        update_res = requests.put(f"{BASE_URL}/api/members/{member_id}", headers=headers, json={
            "name": "TEST_Router_Integration_Member_Updated"
        })
        assert update_res.status_code == 200
        
        # Delete member (cleanup)
        delete_res = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=headers)
        assert delete_res.status_code == 200
        
        print("PASS: All member CRUD endpoints work through the new router")
    
    def test_all_family_crud_endpoints(self, auth_token):
        """Verify all family CRUD endpoints work through the new router"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # List families
        list_res = requests.get(f"{BASE_URL}/api/families", headers=headers)
        assert list_res.status_code == 200
        
        # Create family
        create_res = requests.post(f"{BASE_URL}/api/families", headers=headers, json={
            "family_name": "TEST_Router_Family",
            "primary_contact_name": "Test Contact"
        })
        assert create_res.status_code == 200
        family_id = create_res.json()["id"]
        
        # Update family
        update_res = requests.put(f"{BASE_URL}/api/families/{family_id}", headers=headers, json={
            "family_name": "TEST_Router_Family_Updated",
            "primary_contact_name": "Test Contact Updated"
        })
        assert update_res.status_code == 200
        
        # Delete family (cleanup)
        delete_res = requests.delete(f"{BASE_URL}/api/families/{family_id}", headers=headers)
        assert delete_res.status_code == 200
        
        print("PASS: All family CRUD endpoints work through the new router")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
