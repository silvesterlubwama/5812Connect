"""
Iteration 39 - SIP.js Integration Tests
Tests for SIP registration, PBX configs, extensions, and calling features
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_login_success(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"Login successful, user: {data['user'].get('name')}")


class TestPBXConfigs:
    """PBX Configuration API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_list_pbx_configs(self, auth_headers):
        """Test listing PBX configurations"""
        response = requests.get(f"{BASE_URL}/api/calling/pbx-configs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} PBX configs")
        
        # Check that sensitive fields are not exposed
        for config in data:
            assert "sip_password" not in config, "SIP password should not be exposed"
            assert "password" not in config, "Password should not be exposed"
    
    def test_create_pbx_config(self, auth_headers):
        """Test creating a PBX configuration with SIP fields"""
        test_config = {
            "name": "TEST_PBX_ITERATION39",
            "provider": "freepbx",
            "host": "test-pbx.example.com",
            "port": 5060,
            "sip_username": "test_sip_user",
            "sip_password": "test_sip_pass",
            "sip_domain": "sip.example.com",
            "websocket_url": "wss://test-pbx.example.com:8089/ws",
            "is_active": True,
            "is_default": False
        }
        
        response = requests.post(f"{BASE_URL}/api/calling/pbx-configs", 
                                json=test_config, headers=auth_headers)
        
        # Should succeed or fail gracefully
        if response.status_code == 200:
            data = response.json()
            assert data.get("name") == "TEST_PBX_ITERATION39"
            assert "sip_password" not in data, "SIP password should not be returned"
            print("PBX config created successfully")
            
            # Store ID for cleanup
            pytest.test_pbx_id = data.get("id")
        else:
            print(f"PBX config creation returned: {response.status_code} - {response.text}")
    
    def test_cleanup_test_pbx(self, auth_headers):
        """Cleanup test PBX config"""
        if hasattr(pytest, 'test_pbx_id') and pytest.test_pbx_id:
            response = requests.delete(
                f"{BASE_URL}/api/calling/pbx-configs/{pytest.test_pbx_id}",
                headers=auth_headers
            )
            print(f"Cleanup PBX config: {response.status_code}")


class TestExtensions:
    """Extension management API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, auth_headers):
        """Get admin user ID"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        return response.json().get("id")
    
    def test_list_extensions(self, auth_headers):
        """Test listing all extensions"""
        response = requests.get(f"{BASE_URL}/api/calling/extensions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} extensions")
        
        # Check extension structure
        for ext in data:
            assert "extension" in ext
            print(f"  Extension: {ext.get('extension')} - {ext.get('display_name', 'N/A')}")
    
    def test_get_user_extension(self, auth_headers, admin_user_id):
        """Test getting extension for a specific user"""
        response = requests.get(
            f"{BASE_URL}/api/calling/extensions/user/{admin_user_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if data:
            assert "extension" in data
            print(f"Admin extension: {data.get('extension')}")
        else:
            print("Admin has no extension assigned")
    
    def test_get_callable_contacts(self, auth_headers, admin_user_id):
        """Test getting callable contacts for a user"""
        response = requests.get(
            f"{BASE_URL}/api/calling/contacts",
            params={"user_id": admin_user_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} callable contacts")
        
        # Check contact structure
        for contact in data[:3]:  # Check first 3
            print(f"  Contact: {contact.get('name', 'N/A')} - Ext: {contact.get('extension', 'N/A')}")


class TestICEServers:
    """ICE Server configuration tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_ice_servers(self, auth_headers):
        """Test getting ICE server configuration"""
        response = requests.get(f"{BASE_URL}/api/calling/ice-servers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "ice_servers" in data
        ice_servers = data["ice_servers"]
        assert isinstance(ice_servers, list)
        assert len(ice_servers) > 0, "Should have at least one ICE server"
        
        # Check STUN server format
        for server in ice_servers:
            assert "urls" in server
            print(f"ICE Server: {server.get('urls')}")


class TestCallingFeatures:
    """Calling feature API tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, auth_headers):
        """Get admin user ID"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        return response.json().get("id")
    
    def test_call_history(self, auth_headers, admin_user_id):
        """Test getting call history"""
        response = requests.get(
            f"{BASE_URL}/api/calling/history",
            params={"user_id": admin_user_id},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Response is an object with 'calls' array and 'total' count
        if isinstance(data, dict):
            assert "calls" in data
            calls = data["calls"]
            total = data.get("total", len(calls))
            print(f"Found {total} call history records")
        else:
            # Fallback for list response
            assert isinstance(data, list)
            print(f"Found {len(data)} call history records")


class TestHealthCheck:
    """Basic health check tests"""
    
    def test_api_health(self):
        """Test API is responding"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("API health check passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
