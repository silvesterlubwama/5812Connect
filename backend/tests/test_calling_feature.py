"""
Test Calling Feature - Extensions, PBX Configs, Call History, Voicemail, Recordings
Tests for the new audio/video calling feature with PBX integration
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("token"), data.get("user", {}).get("id")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    token, user_id = auth_token
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    return session, user_id


class TestExtensionsAPI:
    """Test extension management endpoints"""
    
    created_extension = None
    
    def test_list_extensions(self, api_client):
        """Test listing all extensions"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/extensions")
        assert response.status_code == 200, f"Failed to list extensions: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of extensions"
        print(f"✓ List extensions: {len(data)} extensions found")
    
    def test_create_extension(self, api_client):
        """Test creating a new extension"""
        session, user_id = api_client
        
        # Generate unique extension number
        ext_number = f"{1000 + (uuid.uuid4().int % 9000)}"
        
        response = session.post(f"{BASE_URL}/api/calling/extensions", json={
            "user_id": user_id,
            "extension": ext_number,
            "display_name": "Test Admin Extension",
            "voicemail_enabled": True,
            "dnd_enabled": False
        })
        
        # May fail if user already has extension
        if response.status_code == 400 and "already has an extension" in response.text:
            print("✓ Create extension: User already has extension (expected)")
            # Get existing extension
            ext_response = session.get(f"{BASE_URL}/api/calling/extensions/user/{user_id}")
            if ext_response.status_code == 200 and ext_response.json():
                TestExtensionsAPI.created_extension = ext_response.json().get("extension")
            return
        
        if response.status_code == 400 and "already assigned" in response.text:
            print("✓ Create extension: Extension number already in use (expected)")
            return
            
        assert response.status_code in [200, 201], f"Failed to create extension: {response.text}"
        data = response.json()
        assert "extension" in data, "Response should contain extension"
        TestExtensionsAPI.created_extension = data.get("extension")
        print(f"✓ Create extension: {data.get('extension')} created")
    
    def test_get_user_extension(self, api_client):
        """Test getting extension for a specific user"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/extensions/user/{user_id}")
        assert response.status_code == 200, f"Failed to get user extension: {response.text}"
        print(f"✓ Get user extension: {response.json()}")
    
    def test_update_extension(self, api_client):
        """Test updating an extension"""
        session, user_id = api_client
        
        if not TestExtensionsAPI.created_extension:
            # Get user's extension first
            ext_response = session.get(f"{BASE_URL}/api/calling/extensions/user/{user_id}")
            if ext_response.status_code == 200 and ext_response.json():
                TestExtensionsAPI.created_extension = ext_response.json().get("extension")
        
        if not TestExtensionsAPI.created_extension:
            pytest.skip("No extension to update")
        
        response = session.put(
            f"{BASE_URL}/api/calling/extensions/{TestExtensionsAPI.created_extension}",
            json={
                "display_name": "Updated Admin Extension",
                "dnd_enabled": True
            }
        )
        assert response.status_code == 200, f"Failed to update extension: {response.text}"
        print(f"✓ Update extension: {TestExtensionsAPI.created_extension} updated")


class TestPbxConfigsAPI:
    """Test PBX configuration endpoints"""
    
    created_config_id = None
    
    def test_list_pbx_configs(self, api_client):
        """Test listing all PBX configurations"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/pbx-configs")
        assert response.status_code == 200, f"Failed to list PBX configs: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of PBX configs"
        print(f"✓ List PBX configs: {len(data)} configs found")
    
    def test_create_pbx_config(self, api_client):
        """Test creating a new PBX configuration"""
        session, user_id = api_client
        
        response = session.post(f"{BASE_URL}/api/calling/pbx-configs", json={
            "name": f"TEST_PBX_{uuid.uuid4().hex[:6]}",
            "provider": "freepbx",
            "host": "test-pbx.example.com",
            "port": 5060,
            "username": "test_user",
            "password": "test_pass",
            "api_url": "https://test-pbx.example.com/api",
            "websocket_url": "wss://test-pbx.example.com:8089/ws",
            "stun_servers": ["stun:stun.l.google.com:19302"],
            "is_active": True,
            "is_default": False
        })
        
        assert response.status_code in [200, 201], f"Failed to create PBX config: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain id"
        TestPbxConfigsAPI.created_config_id = data.get("id")
        print(f"✓ Create PBX config: {data.get('name')} created with id {data.get('id')}")
    
    def test_test_pbx_connection(self, api_client):
        """Test PBX connection test endpoint"""
        session, user_id = api_client
        
        if not TestPbxConfigsAPI.created_config_id:
            pytest.skip("No PBX config to test")
        
        response = session.post(f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigsAPI.created_config_id}/test")
        assert response.status_code == 200, f"Failed to test PBX connection: {response.text}"
        data = response.json()
        # Connection may fail since it's a test host, but endpoint should work
        print(f"✓ Test PBX connection: {data}")
    
    def test_update_pbx_config(self, api_client):
        """Test updating a PBX configuration"""
        session, user_id = api_client
        
        if not TestPbxConfigsAPI.created_config_id:
            pytest.skip("No PBX config to update")
        
        response = session.put(
            f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigsAPI.created_config_id}",
            json={
                "name": "TEST_PBX_Updated",
                "is_active": False
            }
        )
        assert response.status_code == 200, f"Failed to update PBX config: {response.text}"
        print(f"✓ Update PBX config: {TestPbxConfigsAPI.created_config_id} updated")
    
    def test_delete_pbx_config(self, api_client):
        """Test deleting a PBX configuration"""
        session, user_id = api_client
        
        if not TestPbxConfigsAPI.created_config_id:
            pytest.skip("No PBX config to delete")
        
        response = session.delete(f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigsAPI.created_config_id}")
        assert response.status_code == 200, f"Failed to delete PBX config: {response.text}"
        print(f"✓ Delete PBX config: {TestPbxConfigsAPI.created_config_id} deleted")


class TestCallHistoryAPI:
    """Test call history endpoints"""
    
    def test_get_call_history(self, api_client):
        """Test getting call history for user"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/history?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get call history: {response.text}"
        data = response.json()
        assert "calls" in data, "Response should contain calls"
        assert "total" in data, "Response should contain total"
        print(f"✓ Get call history: {data.get('total')} calls found")
    
    def test_get_missed_calls(self, api_client):
        """Test getting missed calls"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/missed?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get missed calls: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of missed calls"
        print(f"✓ Get missed calls: {len(data)} missed calls")
    
    def test_get_missed_call_count(self, api_client):
        """Test getting missed call count"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/missed/count?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get missed call count: {response.text}"
        data = response.json()
        assert "count" in data, "Response should contain count"
        print(f"✓ Get missed call count: {data.get('count')}")


class TestVoicemailAPI:
    """Test voicemail endpoints"""
    
    def test_get_voicemails(self, api_client):
        """Test getting voicemails for user"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/voicemail?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get voicemails: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of voicemails"
        print(f"✓ Get voicemails: {len(data)} voicemails found")
    
    def test_get_unread_voicemail_count(self, api_client):
        """Test getting unread voicemail count"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/voicemail/unread-count?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get unread voicemail count: {response.text}"
        data = response.json()
        assert "count" in data, "Response should contain count"
        print(f"✓ Get unread voicemail count: {data.get('count')}")


class TestRecordingsAPI:
    """Test call recordings endpoints"""
    
    def test_get_recordings(self, api_client):
        """Test getting call recordings for user"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/recordings?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get recordings: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of recordings"
        print(f"✓ Get recordings: {len(data)} recordings found")


class TestCallStatusAPI:
    """Test call status endpoints"""
    
    def test_get_user_status(self, api_client):
        """Test getting user's call status"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/status/{user_id}")
        assert response.status_code == 200, f"Failed to get user status: {response.text}"
        data = response.json()
        print(f"✓ Get user status: {data}")
    
    def test_update_user_status(self, api_client):
        """Test updating user's call status"""
        session, user_id = api_client
        response = session.put(f"{BASE_URL}/api/calling/status?user_id={user_id}&status=available")
        assert response.status_code == 200, f"Failed to update user status: {response.text}"
        data = response.json()
        assert data.get("success") == True, "Status update should succeed"
        print(f"✓ Update user status: {data}")
    
    def test_update_invalid_status(self, api_client):
        """Test updating with invalid status"""
        session, user_id = api_client
        response = session.put(f"{BASE_URL}/api/calling/status?user_id={user_id}&status=invalid_status")
        assert response.status_code == 400, "Should reject invalid status"
        print("✓ Invalid status rejected correctly")


class TestContactsAPI:
    """Test callable contacts endpoint"""
    
    def test_get_callable_contacts(self, api_client):
        """Test getting callable contacts"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get contacts: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of contacts"
        print(f"✓ Get callable contacts: {len(data)} contacts found")


class TestIceServersAPI:
    """Test ICE servers endpoint"""
    
    def test_get_ice_servers(self, api_client):
        """Test getting ICE servers for WebRTC"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/ice-servers")
        assert response.status_code == 200, f"Failed to get ICE servers: {response.text}"
        data = response.json()
        assert "ice_servers" in data, "Response should contain ice_servers"
        assert len(data["ice_servers"]) > 0, "Should have at least one ICE server"
        print(f"✓ Get ICE servers: {len(data['ice_servers'])} servers configured")


class TestCallInitiation:
    """Test call initiation (without actual WebRTC)"""
    
    def test_get_active_calls(self, api_client):
        """Test getting active calls"""
        session, user_id = api_client
        response = session.get(f"{BASE_URL}/api/calling/calls/active?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get active calls: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of active calls"
        print(f"✓ Get active calls: {len(data)} active calls")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_extension(self, api_client):
        """Clean up test extension if created"""
        session, user_id = api_client
        
        # Don't delete the admin's extension as it may be needed
        # Just verify we can list extensions
        response = session.get(f"{BASE_URL}/api/calling/extensions")
        assert response.status_code == 200
        print("✓ Cleanup: Extension list verified")
    
    def test_cleanup_test_pbx_configs(self, api_client):
        """Clean up any remaining test PBX configs"""
        session, user_id = api_client
        
        response = session.get(f"{BASE_URL}/api/calling/pbx-configs")
        if response.status_code == 200:
            configs = response.json()
            for config in configs:
                if config.get("name", "").startswith("TEST_"):
                    session.delete(f"{BASE_URL}/api/calling/pbx-configs/{config['id']}")
                    print(f"✓ Cleanup: Deleted test PBX config {config['id']}")
        print("✓ Cleanup: PBX configs cleaned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
