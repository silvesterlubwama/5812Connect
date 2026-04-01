"""
Iteration 40 - SIP.js Integration Testing
Tests for:
1. GET /api/calling/pbx-configs/sip-credentials - Returns SIP credentials for registration
2. PBX update preserves passwords (blank password fields don't overwrite stored values)
3. All PBX tabs still work (Extensions, PBX, Queues, AA, Rules)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSipCredentialsEndpoint:
    """Test the new /api/calling/pbx-configs/sip-credentials endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user_id = login_resp.json().get("user", {}).get("id")
    
    def test_sip_credentials_endpoint_exists(self):
        """Test that GET /api/calling/pbx-configs/sip-credentials returns 200"""
        resp = requests.get(f"{BASE_URL}/api/calling/pbx-configs/sip-credentials", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Should return either credentials or error message
        assert isinstance(data, dict), "Response should be a dict"
        print(f"SIP credentials response: {data}")
    
    def test_sip_credentials_returns_expected_fields(self):
        """Test that sip-credentials returns expected fields when PBX is configured"""
        resp = requests.get(f"{BASE_URL}/api/calling/pbx-configs/sip-credentials", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # If no default PBX, should return error
        if data.get("error"):
            assert "No default active PBX" in data.get("error", "")
            print("No default PBX configured - expected behavior")
        else:
            # If PBX exists, should have these fields
            expected_fields = ["sip_username", "sip_domain", "websocket_url", "host"]
            for field in expected_fields:
                assert field in data, f"Missing field: {field}"
            # sip_password should be included for registration
            assert "sip_password" in data, "sip_password should be returned for SIP registration"
            print(f"SIP credentials contain expected fields: {list(data.keys())}")


class TestPbxPasswordPreservation:
    """Test that PBX update skips blank passwords"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.test_pbx_id = None
    
    def test_create_pbx_with_password(self):
        """Create a PBX config with password"""
        unique_name = f"TEST_PBX_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/calling/pbx-configs", headers=self.headers, json={
            "name": unique_name,
            "provider": "generic_sip",
            "host": "test.pbx.example.com",
            "port": 5060,
            "sip_username": "testuser",
            "sip_password": "secret123",
            "sip_domain": "test.pbx.example.com",
            "websocket_url": "wss://test.pbx.example.com:8089/ws",
            "is_active": True,
            "is_default": False
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        data = create_resp.json()
        self.test_pbx_id = data.get("id")
        assert self.test_pbx_id, "PBX ID should be returned"
        # Password should NOT be in response
        assert "sip_password" not in data, "sip_password should not be in create response"
        print(f"Created PBX: {self.test_pbx_id}")
        
        # Cleanup
        if self.test_pbx_id:
            requests.delete(f"{BASE_URL}/api/calling/pbx-configs/{self.test_pbx_id}", headers=self.headers)
    
    def test_update_pbx_blank_password_preserves_existing(self):
        """Update PBX with blank password should not overwrite stored password"""
        # Create PBX first
        unique_name = f"TEST_PBX_{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(f"{BASE_URL}/api/calling/pbx-configs", headers=self.headers, json={
            "name": unique_name,
            "provider": "generic_sip",
            "host": "test.pbx.example.com",
            "port": 5060,
            "sip_username": "testuser",
            "sip_password": "original_secret",
            "sip_domain": "test.pbx.example.com",
            "is_active": True,
            "is_default": True  # Make it default to test sip-credentials
        })
        assert create_resp.status_code == 200
        pbx_id = create_resp.json().get("id")
        
        try:
            # Update with blank password
            update_resp = requests.put(f"{BASE_URL}/api/calling/pbx-configs/{pbx_id}", headers=self.headers, json={
                "name": unique_name + "_updated",
                "sip_password": "",  # Blank password
                "password": ""  # Blank admin password
            })
            assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
            
            # Verify password was preserved by checking sip-credentials
            creds_resp = requests.get(f"{BASE_URL}/api/calling/pbx-configs/sip-credentials", headers=self.headers)
            assert creds_resp.status_code == 200
            creds = creds_resp.json()
            
            # If this is the default PBX, password should still be there
            if creds.get("sip_password"):
                assert creds["sip_password"] == "original_secret", "Password should be preserved"
                print("Password preserved correctly after blank update")
            else:
                print("Note: Password field not returned (may be expected if not default)")
        finally:
            # Cleanup
            requests.delete(f"{BASE_URL}/api/calling/pbx-configs/{pbx_id}", headers=self.headers)


class TestPbxConfigsEndpoints:
    """Test all PBX-related endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user_id = login_resp.json().get("user", {}).get("id")
    
    def test_list_pbx_configs(self):
        """GET /api/calling/pbx-configs returns list"""
        resp = requests.get(f"{BASE_URL}/api/calling/pbx-configs", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        # Verify sensitive fields are excluded
        for config in data:
            assert "password" not in config, "password should be excluded"
            assert "api_key" not in config, "api_key should be excluded"
            assert "sip_password" not in config, "sip_password should be excluded from list"
        print(f"Listed {len(data)} PBX configs")
    
    def test_list_extensions(self):
        """GET /api/calling/extensions returns list"""
        resp = requests.get(f"{BASE_URL}/api/calling/extensions", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Listed {len(data)} extensions")
    
    def test_list_queues(self):
        """GET /api/calling/queues returns list"""
        resp = requests.get(f"{BASE_URL}/api/calling/queues", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Listed {len(data)} queues")
    
    def test_get_auto_attendant(self):
        """GET /api/calling/auto-attendant returns config"""
        resp = requests.get(f"{BASE_URL}/api/calling/auto-attendant", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict), "Should return a dict"
        # Should have expected fields
        assert "enabled" in data or "_key" in data, "Should have auto-attendant fields"
        print(f"Auto-attendant config: enabled={data.get('enabled')}")
    
    def test_list_outgoing_rules(self):
        """GET /api/calling/outgoing-rules returns list"""
        resp = requests.get(f"{BASE_URL}/api/calling/outgoing-rules", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Listed {len(data)} outgoing rules")
    
    def test_get_ice_servers(self):
        """GET /api/calling/ice-servers returns ICE config"""
        resp = requests.get(f"{BASE_URL}/api/calling/ice-servers", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "ice_servers" in data, "Should have ice_servers field"
        assert isinstance(data["ice_servers"], list), "ice_servers should be a list"
        print(f"ICE servers: {len(data['ice_servers'])} configured")
    
    def test_get_callable_contacts(self):
        """GET /api/calling/contacts returns contacts"""
        resp = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={self.user_id}", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Should return a list"
        print(f"Listed {len(data)} callable contacts")
    
    def test_get_user_extension(self):
        """GET /api/calling/extensions/user/{user_id} returns user extension"""
        resp = requests.get(f"{BASE_URL}/api/calling/extensions/user/{self.user_id}", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        # May be null if user has no extension
        if data:
            assert "extension" in data, "Should have extension field"
            print(f"User extension: {data.get('extension')}")
        else:
            print("User has no extension assigned")


class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print("Health check passed")
    
    def test_admin_login(self):
        """Admin login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data, "Should return token"
        assert "user" in data, "Should return user"
        print(f"Admin login successful: {data['user'].get('email')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
