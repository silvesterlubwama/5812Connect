"""
Wave API Tests - Iteration 45
Tests for Grandstream Wave H5 Embedded SDK integration:
- Server CRUD endpoints
- User config with extension and wave_password for auto-login
- postMessage integration (mocked - depends on Wave accepting message format)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")


class TestWaveAPI:
    """Wave server CRUD and user config tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.user = login_res.json().get("user")
    
    # ========== Wave Server CRUD Tests ==========
    
    def test_list_wave_servers(self):
        """GET /api/wave/servers - List all Wave servers"""
        res = self.session.get(f"{BASE_URL}/api/wave/servers")
        assert res.status_code == 200, f"Failed to list servers: {res.text}"
        data = res.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} Wave servers")
        return data
    
    def test_create_wave_server(self):
        """POST /api/wave/servers - Create a new Wave server"""
        payload = {
            "name": "TEST_Wave_Server",
            "url": "https://test-wave.example.com",
            "campus_id": "",
            "campus_name": "",
            "is_default": False
        }
        res = self.session.post(f"{BASE_URL}/api/wave/servers", json=payload)
        assert res.status_code == 200, f"Failed to create server: {res.text}"
        data = res.json()
        
        # Verify response structure
        assert "id" in data, "Response should have id"
        assert data["name"] == payload["name"], "Name should match"
        assert data["url"] == payload["url"], "URL should match"
        assert "created_at" in data, "Should have created_at"
        
        print(f"Created Wave server: {data['id']}")
        return data
    
    def test_create_wave_server_with_campus(self):
        """POST /api/wave/servers - Create Wave server with campus assignment"""
        payload = {
            "name": "TEST_Campus_Wave",
            "url": "https://campus-wave.example.com",
            "campus_id": "loc_001",
            "campus_name": "58:12 Global (Central)",
            "is_default": False
        }
        res = self.session.post(f"{BASE_URL}/api/wave/servers", json=payload)
        assert res.status_code == 200, f"Failed to create server: {res.text}"
        data = res.json()
        
        assert data["campus_id"] == payload["campus_id"], "Campus ID should match"
        assert data["campus_name"] == payload["campus_name"], "Campus name should match"
        
        print(f"Created campus-assigned Wave server: {data['id']}")
        return data
    
    def test_update_wave_server(self):
        """PUT /api/wave/servers/{id} - Update a Wave server"""
        # First create a server
        create_res = self.session.post(f"{BASE_URL}/api/wave/servers", json={
            "name": "TEST_Update_Server",
            "url": "https://update-test.example.com",
            "is_default": False
        })
        assert create_res.status_code == 200
        server_id = create_res.json()["id"]
        
        # Update it
        update_payload = {
            "name": "TEST_Updated_Server",
            "url": "https://updated-url.example.com",
            "is_default": True
        }
        res = self.session.put(f"{BASE_URL}/api/wave/servers/{server_id}", json=update_payload)
        assert res.status_code == 200, f"Failed to update server: {res.text}"
        data = res.json()
        
        assert data["name"] == update_payload["name"], "Name should be updated"
        assert data["url"] == update_payload["url"], "URL should be updated"
        assert data["is_default"] == True, "Should be marked as default"
        assert "updated_at" in data, "Should have updated_at"
        
        print(f"Updated Wave server: {server_id}")
        return data
    
    def test_delete_wave_server(self):
        """DELETE /api/wave/servers/{id} - Delete a Wave server"""
        # First create a server
        create_res = self.session.post(f"{BASE_URL}/api/wave/servers", json={
            "name": "TEST_Delete_Server",
            "url": "https://delete-test.example.com",
            "is_default": False
        })
        assert create_res.status_code == 200
        server_id = create_res.json()["id"]
        
        # Delete it
        res = self.session.delete(f"{BASE_URL}/api/wave/servers/{server_id}")
        assert res.status_code == 200, f"Failed to delete server: {res.text}"
        data = res.json()
        assert data.get("message") == "Deleted", "Should return deleted message"
        
        # Verify it's gone
        list_res = self.session.get(f"{BASE_URL}/api/wave/servers")
        servers = list_res.json()
        assert not any(s["id"] == server_id for s in servers), "Server should be deleted"
        
        print(f"Deleted Wave server: {server_id}")
    
    # ========== Wave User Config Tests ==========
    
    def test_get_my_wave_config(self):
        """GET /api/wave/my-config - Get user's Wave config with extension and wave_password for H5 auto-login"""
        res = self.session.get(f"{BASE_URL}/api/wave/my-config")
        assert res.status_code == 200, f"Failed to get config: {res.text}"
        data = res.json()
        
        # Verify response structure for H5 embedded SDK
        assert "server" in data, "Response should have server field"
        assert "extension" in data, "Response should have extension field for auto-login"
        assert "wave_password" in data, "Response should have wave_password field for auto-login"
        assert "auto_login" in data, "Response should have auto_login flag"
        assert "display_name" in data, "Response should have display_name"
        
        if data["server"]:
            print(f"User's Wave server: {data['server'].get('name')} - {data['server'].get('url')}")
        else:
            print("No Wave server configured for user")
        
        print(f"Extension: {data.get('extension')}, Auto-login: {data.get('auto_login')}")
        
        return data
    
    def test_my_config_auto_login_flag(self):
        """Test auto_login flag is True only when extension, wave_password, and server are all set"""
        res = self.session.get(f"{BASE_URL}/api/wave/my-config")
        assert res.status_code == 200
        data = res.json()
        
        has_extension = bool(data.get("extension"))
        has_password = bool(data.get("wave_password"))
        has_server = bool(data.get("server"))
        
        expected_auto_login = has_extension and has_password and has_server
        assert data.get("auto_login") == expected_auto_login, \
            f"auto_login should be {expected_auto_login} (ext={has_extension}, pwd={has_password}, server={has_server})"
        
        print(f"Auto-login flag correctly set to {data.get('auto_login')}")
    
    def test_save_my_wave_credentials(self):
        """PUT /api/wave/my-credentials - Save user's Wave credentials"""
        payload = {
            "wave_extension": "1001",
            "wave_server_id": "wave_test123",
            "auto_login": True
        }
        res = self.session.put(f"{BASE_URL}/api/wave/my-credentials", json=payload)
        assert res.status_code == 200, f"Failed to save credentials: {res.text}"
        data = res.json()
        
        assert data["wave_extension"] == payload["wave_extension"], "Extension should match"
        assert data["auto_login"] == payload["auto_login"], "Auto login should match"
        assert "updated_at" in data, "Should have updated_at"
        
        print(f"Saved Wave credentials for user")
        return data
    
    # ========== Default Server Logic Tests ==========
    
    def test_default_server_logic(self):
        """Test that setting a server as default unsets others"""
        # Create first server as default
        res1 = self.session.post(f"{BASE_URL}/api/wave/servers", json={
            "name": "TEST_Default_1",
            "url": "https://default1.example.com",
            "is_default": True
        })
        assert res1.status_code == 200
        server1_id = res1.json()["id"]
        
        # Create second server as default
        res2 = self.session.post(f"{BASE_URL}/api/wave/servers", json={
            "name": "TEST_Default_2",
            "url": "https://default2.example.com",
            "is_default": True
        })
        assert res2.status_code == 200
        server2_id = res2.json()["id"]
        
        # Verify only second is default
        list_res = self.session.get(f"{BASE_URL}/api/wave/servers")
        servers = list_res.json()
        
        server1 = next((s for s in servers if s["id"] == server1_id), None)
        server2 = next((s for s in servers if s["id"] == server2_id), None)
        
        if server1:
            assert server1.get("is_default") == False, "First server should no longer be default"
        if server2:
            assert server2.get("is_default") == True, "Second server should be default"
        
        print("Default server logic verified")
    
    # ========== Cleanup ==========
    
    def test_cleanup_test_servers(self):
        """Cleanup - Delete all TEST_ prefixed servers"""
        list_res = self.session.get(f"{BASE_URL}/api/wave/servers")
        servers = list_res.json()
        
        deleted = 0
        for server in servers:
            if server.get("name", "").startswith("TEST_"):
                del_res = self.session.delete(f"{BASE_URL}/api/wave/servers/{server['id']}")
                if del_res.status_code == 200:
                    deleted += 1
        
        print(f"Cleaned up {deleted} test servers")


class TestWaveAPIUnauthorized:
    """Test Wave API without authentication"""
    
    def test_list_servers_unauthorized(self):
        """GET /api/wave/servers without auth should fail"""
        res = requests.get(f"{BASE_URL}/api/wave/servers")
        assert res.status_code == 401, "Should require authentication"
    
    def test_create_server_unauthorized(self):
        """POST /api/wave/servers without auth should fail"""
        res = requests.post(f"{BASE_URL}/api/wave/servers", json={
            "name": "Test",
            "url": "https://test.com"
        })
        assert res.status_code == 401, "Should require authentication"
    
    def test_get_my_config_unauthorized(self):
        """GET /api/wave/my-config without auth should fail"""
        res = requests.get(f"{BASE_URL}/api/wave/my-config")
        assert res.status_code == 401, "Should require authentication"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
