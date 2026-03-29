"""
Iteration 43 - WebRTC Calling Tests
Tests for: CallContext pure WebRTC, CommsPage call buttons, Dialer, PBX Settings
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCallingEndpoints:
    """Test calling API endpoints"""
    
    def test_health_check(self):
        """Test API health"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health check passed")
    
    def test_get_callable_contacts(self):
        """Test getting callable contacts for dialer"""
        # First login to get a user_id
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        user_data = login_response.json()
        user_id = user_data.get("user", {}).get("id")
        assert user_id, "No user_id in login response"
        
        # Get callable contacts
        response = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}")
        assert response.status_code == 200, f"Failed to get contacts: {response.text}"
        contacts = response.json()
        assert isinstance(contacts, list), "Contacts should be a list"
        print(f"✓ Got {len(contacts)} callable contacts")
        
        # Verify contact structure
        if len(contacts) > 0:
            contact = contacts[0]
            assert "user_id" in contact, "Contact should have user_id"
            assert "name" in contact or "display_name" in contact, "Contact should have name"
            print(f"✓ Contact structure verified: {contact.get('name') or contact.get('display_name')}")
    
    def test_get_ice_servers(self):
        """Test getting ICE servers for WebRTC"""
        response = requests.get(f"{BASE_URL}/api/calling/ice-servers")
        assert response.status_code == 200, f"Failed to get ICE servers: {response.text}"
        data = response.json()
        assert "ice_servers" in data, "Response should have ice_servers"
        assert isinstance(data["ice_servers"], list), "ice_servers should be a list"
        assert len(data["ice_servers"]) > 0, "Should have at least one ICE server"
        print(f"✓ Got {len(data['ice_servers'])} ICE servers")
    
    def test_get_sip_credentials(self):
        """Test getting SIP credentials (should return no PBX when not configured)"""
        response = requests.get(f"{BASE_URL}/api/calling/pbx-configs/sip-credentials")
        assert response.status_code == 200, f"Failed to get SIP credentials: {response.text}"
        data = response.json()
        # When no PBX is configured, should return error message
        if "error" in data:
            assert data["error"] == "No default active PBX"
            print("✓ SIP credentials correctly returns 'No default active PBX' when not configured")
        else:
            # If PBX is configured, should have sip_username
            assert "sip_username" in data
            print(f"✓ SIP credentials returned for configured PBX")
    
    def test_list_extensions(self):
        """Test listing extensions"""
        response = requests.get(f"{BASE_URL}/api/calling/extensions")
        assert response.status_code == 200, f"Failed to list extensions: {response.text}"
        extensions = response.json()
        assert isinstance(extensions, list), "Extensions should be a list"
        print(f"✓ Got {len(extensions)} extensions")
        
        # Verify extension structure if any exist
        if len(extensions) > 0:
            ext = extensions[0]
            assert "extension" in ext, "Extension should have extension number"
            assert "user_id" in ext, "Extension should have user_id"
            print(f"✓ Extension structure verified: {ext.get('extension')}")
    
    def test_list_pbx_configs(self):
        """Test listing PBX configurations"""
        response = requests.get(f"{BASE_URL}/api/calling/pbx-configs")
        assert response.status_code == 200, f"Failed to list PBX configs: {response.text}"
        configs = response.json()
        assert isinstance(configs, list), "PBX configs should be a list"
        print(f"✓ Got {len(configs)} PBX configurations")
    
    def test_get_auto_attendant(self):
        """Test getting auto-attendant configuration"""
        response = requests.get(f"{BASE_URL}/api/calling/auto-attendant")
        assert response.status_code == 200, f"Failed to get auto-attendant: {response.text}"
        data = response.json()
        assert "enabled" in data, "Auto-attendant should have enabled field"
        assert "greeting" in data, "Auto-attendant should have greeting"
        assert "menu_options" in data, "Auto-attendant should have menu_options"
        print(f"✓ Auto-attendant config retrieved (enabled: {data['enabled']})")
    
    def test_list_call_queues(self):
        """Test listing call queues"""
        response = requests.get(f"{BASE_URL}/api/calling/queues")
        assert response.status_code == 200, f"Failed to list queues: {response.text}"
        queues = response.json()
        assert isinstance(queues, list), "Queues should be a list"
        print(f"✓ Got {len(queues)} call queues")
    
    def test_list_outgoing_rules(self):
        """Test listing outgoing call rules"""
        response = requests.get(f"{BASE_URL}/api/calling/outgoing-rules")
        assert response.status_code == 200, f"Failed to list outgoing rules: {response.text}"
        rules = response.json()
        assert isinstance(rules, list), "Rules should be a list"
        print(f"✓ Got {len(rules)} outgoing rules")


class TestCallInitiation:
    """Test call initiation flow"""
    
    @pytest.fixture
    def auth_user(self):
        """Login and get user info"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        return response.json()
    
    def test_initiate_webrtc_call(self, auth_user):
        """Test initiating a WebRTC call"""
        user_id = auth_user.get("user", {}).get("id")
        
        # Get a target user to call
        contacts_response = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}")
        contacts = contacts_response.json()
        
        if len(contacts) == 0:
            pytest.skip("No contacts available to call")
        
        target_user_id = contacts[0]["user_id"]
        
        # Initiate call
        response = requests.post(f"{BASE_URL}/api/calling/calls/initiate?user_id={user_id}", json={
            "to_user_id": target_user_id,
            "call_type": "audio",
            "use_pbx": False
        })
        assert response.status_code == 200, f"Failed to initiate call: {response.text}"
        data = response.json()
        
        assert "call_id" in data, "Response should have call_id"
        assert "ice_servers" in data, "Response should have ice_servers"
        assert "call" in data, "Response should have call object"
        
        call = data["call"]
        assert call["caller_id"] == user_id, "Caller ID should match"
        assert call["target_user_id"] == target_user_id, "Target user ID should match"
        assert call["call_type"] == "audio", "Call type should be audio"
        assert call["use_pbx"] == False, "use_pbx should be False for WebRTC"
        
        print(f"✓ WebRTC call initiated: {data['call_id']}")
        
        # End the call
        end_response = requests.post(f"{BASE_URL}/api/calling/calls/{data['call_id']}/action?user_id={user_id}", json={
            "action": "hangup"
        })
        assert end_response.status_code == 200
        print("✓ Call ended successfully")
    
    def test_initiate_video_call(self, auth_user):
        """Test initiating a video call"""
        user_id = auth_user.get("user", {}).get("id")
        
        # Get a target user
        contacts_response = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}")
        contacts = contacts_response.json()
        
        if len(contacts) == 0:
            pytest.skip("No contacts available to call")
        
        target_user_id = contacts[0]["user_id"]
        
        # Initiate video call
        response = requests.post(f"{BASE_URL}/api/calling/calls/initiate?user_id={user_id}", json={
            "to_user_id": target_user_id,
            "call_type": "video",
            "use_pbx": False
        })
        assert response.status_code == 200, f"Failed to initiate video call: {response.text}"
        data = response.json()
        
        assert data["call"]["call_type"] == "video", "Call type should be video"
        print(f"✓ Video call initiated: {data['call_id']}")
        
        # End the call
        requests.post(f"{BASE_URL}/api/calling/calls/{data['call_id']}/action?user_id={user_id}", json={
            "action": "hangup"
        })


class TestCallActions:
    """Test call actions (hold, mute, etc.)"""
    
    @pytest.fixture
    def active_call(self):
        """Create an active call for testing"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        user_id = login_response.json().get("user", {}).get("id")
        
        # Get contacts
        contacts_response = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}")
        contacts = contacts_response.json()
        
        if len(contacts) == 0:
            pytest.skip("No contacts available")
        
        # Initiate call
        call_response = requests.post(f"{BASE_URL}/api/calling/calls/initiate?user_id={user_id}", json={
            "to_user_id": contacts[0]["user_id"],
            "call_type": "audio",
            "use_pbx": False
        })
        
        call_data = call_response.json()
        yield {"call_id": call_data["call_id"], "user_id": user_id}
        
        # Cleanup - end call
        requests.post(f"{BASE_URL}/api/calling/calls/{call_data['call_id']}/action?user_id={user_id}", json={
            "action": "hangup"
        })
    
    def test_hold_action(self, active_call):
        """Test putting call on hold"""
        response = requests.post(
            f"{BASE_URL}/api/calling/calls/{active_call['call_id']}/action?user_id={active_call['user_id']}", 
            json={"action": "hold"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["call"]["is_on_hold"] == True
        print("✓ Call put on hold")
        
        # Unhold
        response = requests.post(
            f"{BASE_URL}/api/calling/calls/{active_call['call_id']}/action?user_id={active_call['user_id']}", 
            json={"action": "unhold"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["call"]["is_on_hold"] == False
        print("✓ Call taken off hold")
    
    def test_mute_action(self, active_call):
        """Test muting call"""
        response = requests.post(
            f"{BASE_URL}/api/calling/calls/{active_call['call_id']}/action?user_id={active_call['user_id']}", 
            json={"action": "mute"}
        )
        assert response.status_code == 200
        print("✓ Call muted")
        
        # Unmute
        response = requests.post(
            f"{BASE_URL}/api/calling/calls/{active_call['call_id']}/action?user_id={active_call['user_id']}", 
            json={"action": "unmute"}
        )
        assert response.status_code == 200
        print("✓ Call unmuted")


class TestCallHistory:
    """Test call history endpoints"""
    
    def test_get_call_history(self):
        """Test getting call history"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        user_id = login_response.json().get("user", {}).get("id")
        
        response = requests.get(f"{BASE_URL}/api/calling/history?user_id={user_id}")
        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert "total" in data
        print(f"✓ Got {data['total']} calls in history")
    
    def test_get_missed_calls(self):
        """Test getting missed calls"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        user_id = login_response.json().get("user", {}).get("id")
        
        response = requests.get(f"{BASE_URL}/api/calling/missed?user_id={user_id}")
        assert response.status_code == 200
        missed = response.json()
        assert isinstance(missed, list)
        print(f"✓ Got {len(missed)} missed calls")


class TestVoicemail:
    """Test voicemail endpoints"""
    
    def test_get_voicemails(self):
        """Test getting voicemails"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        user_id = login_response.json().get("user", {}).get("id")
        
        response = requests.get(f"{BASE_URL}/api/calling/voicemail?user_id={user_id}")
        assert response.status_code == 200
        voicemails = response.json()
        assert isinstance(voicemails, list)
        print(f"✓ Got {len(voicemails)} voicemails")
    
    def test_get_unread_voicemail_count(self):
        """Test getting unread voicemail count"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        user_id = login_response.json().get("user", {}).get("id")
        
        response = requests.get(f"{BASE_URL}/api/calling/voicemail/unread-count?user_id={user_id}")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        print(f"✓ Unread voicemail count: {data['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
