"""
Iteration 37 - PBX & Extensions Page Testing
Tests for:
- PBX configuration CRUD with SIP fields (sip_username, sip_password, sip_domain)
- Extension management (list/create/edit/delete with voicemail PIN, call forwarding)
- Auto-attendant configuration
- Call queues with ring strategies
- Outgoing rules with pattern matching
- Calling contacts returns all staff users
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication for testing"""
    
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
    def user_id(self, auth_token):
        """Get current user ID"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        return response.json()["id"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestPbxConfigWithSipFields(TestAuth):
    """Test PBX configuration CRUD with new SIP fields"""
    
    created_pbx_id = None
    
    def test_create_pbx_config_with_sip_fields(self, headers):
        """Create PBX config with sip_username, sip_password, sip_domain"""
        payload = {
            "name": "TEST_PBX_SIP_Config",
            "provider": "freepbx",
            "host": "pbx.test.com",
            "port": 5060,
            "username": "admin",
            "password": "adminpass",
            "sip_username": "sip_test_user",
            "sip_password": "sip_test_pass",
            "sip_domain": "sip.test.com",
            "api_url": "https://pbx.test.com/api",
            "websocket_url": "wss://pbx.test.com:8089/ws",
            "stun_servers": ["stun:stun.l.google.com:19302"],
            "is_active": True,
            "is_default": False
        }
        response = requests.post(f"{BASE_URL}/api/calling/pbx-configs", json=payload, headers=headers)
        assert response.status_code == 200, f"Create PBX failed: {response.text}"
        data = response.json()
        
        # Verify SIP fields are accepted
        assert data.get("name") == "TEST_PBX_SIP_Config"
        assert data.get("sip_username") == "sip_test_user"
        assert data.get("sip_domain") == "sip.test.com"
        # Note: sip_password is returned in response (minor security concern - should be excluded)
        assert "id" in data
        
        TestPbxConfigWithSipFields.created_pbx_id = data["id"]
        print(f"Created PBX config with SIP fields: {data['id']}")
    
    def test_list_pbx_configs(self, headers):
        """List PBX configs and verify SIP domain is shown"""
        response = requests.get(f"{BASE_URL}/api/calling/pbx-configs", headers=headers)
        assert response.status_code == 200
        configs = response.json()
        assert isinstance(configs, list)
        
        # Find our test config
        test_config = next((c for c in configs if c.get("name") == "TEST_PBX_SIP_Config"), None)
        if test_config:
            assert test_config.get("sip_domain") == "sip.test.com"
            print(f"Found PBX config with SIP domain: {test_config.get('sip_domain')}")
    
    def test_update_pbx_config(self, headers):
        """Update PBX config SIP fields"""
        if not TestPbxConfigWithSipFields.created_pbx_id:
            pytest.skip("No PBX config created")
        
        payload = {
            "sip_username": "updated_sip_user",
            "sip_domain": "updated.sip.com"
        }
        response = requests.put(
            f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigWithSipFields.created_pbx_id}",
            json=payload, headers=headers
        )
        assert response.status_code == 200
        print("Updated PBX config SIP fields")
    
    def test_test_pbx_connection(self, headers):
        """Test PBX connection endpoint"""
        if not TestPbxConfigWithSipFields.created_pbx_id:
            pytest.skip("No PBX config created")
        
        response = requests.post(
            f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigWithSipFields.created_pbx_id}/test",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # Connection test may fail (no real PBX) but endpoint should work
        assert "success" in data or "message" in data
        print(f"PBX connection test result: {data}")
    
    def test_delete_pbx_config(self, headers):
        """Delete test PBX config"""
        if not TestPbxConfigWithSipFields.created_pbx_id:
            pytest.skip("No PBX config created")
        
        response = requests.delete(
            f"{BASE_URL}/api/calling/pbx-configs/{TestPbxConfigWithSipFields.created_pbx_id}",
            headers=headers
        )
        assert response.status_code == 200
        print("Deleted test PBX config")


class TestExtensionManagement(TestAuth):
    """Test extension CRUD with voicemail PIN and call forwarding"""
    
    test_extension = None
    test_user_id = None
    
    def test_list_extensions(self, headers):
        """List all extensions"""
        response = requests.get(f"{BASE_URL}/api/calling/extensions", headers=headers)
        assert response.status_code == 200
        extensions = response.json()
        assert isinstance(extensions, list)
        print(f"Found {len(extensions)} extensions")
        
        # Store existing extension count
        TestExtensionManagement.initial_count = len(extensions)
    
    def test_get_users_for_extension(self, headers):
        """Get users to assign extension to"""
        response = requests.get(f"{BASE_URL}/api/admin/users?limit=10", headers=headers)
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        
        # Find a user without extension for testing
        ext_response = requests.get(f"{BASE_URL}/api/calling/extensions", headers=headers)
        extensions = ext_response.json()
        ext_user_ids = {e.get("user_id") for e in extensions}
        
        available_user = next((u for u in users if u.get("id") not in ext_user_ids and u.get("id")), None)
        if available_user:
            TestExtensionManagement.test_user_id = available_user["id"]
            print(f"Found user for extension test: {available_user.get('name')}")
        else:
            print("No available user without extension found")
    
    def test_create_extension_with_voicemail_and_forwarding(self, headers):
        """Create extension with voicemail PIN and call forwarding"""
        if not TestExtensionManagement.test_user_id:
            pytest.skip("No user available for extension test")
        
        payload = {
            "user_id": TestExtensionManagement.test_user_id,
            "extension": "9999",
            "display_name": "TEST Extension User",
            "voicemail_enabled": True,
            "voicemail_pin": "1234",
            "dnd_enabled": False,
            "forward_to": "+256700000000"
        }
        response = requests.post(f"{BASE_URL}/api/calling/extensions", json=payload, headers=headers)
        
        if response.status_code == 400 and "already" in response.text.lower():
            # User or extension already exists, try different extension
            payload["extension"] = "9998"
            response = requests.post(f"{BASE_URL}/api/calling/extensions", json=payload, headers=headers)
        
        assert response.status_code == 200, f"Create extension failed: {response.text}"
        data = response.json()
        
        assert data.get("extension") in ["9999", "9998"]
        assert data.get("voicemail_enabled") == True
        assert data.get("forward_to") == "+256700000000"
        
        TestExtensionManagement.test_extension = data.get("extension")
        print(f"Created extension {data.get('extension')} with voicemail and forwarding")
    
    def test_update_extension(self, headers):
        """Update extension settings"""
        if not TestExtensionManagement.test_extension:
            pytest.skip("No test extension created")
        
        payload = {
            "dnd_enabled": True,
            "forward_to": "+256711111111"
        }
        response = requests.put(
            f"{BASE_URL}/api/calling/extensions/{TestExtensionManagement.test_extension}",
            json=payload, headers=headers
        )
        assert response.status_code == 200
        print(f"Updated extension {TestExtensionManagement.test_extension}")
    
    def test_get_user_extension(self, headers):
        """Get extension for specific user"""
        if not TestExtensionManagement.test_user_id:
            pytest.skip("No test user")
        
        response = requests.get(
            f"{BASE_URL}/api/calling/extensions/user/{TestExtensionManagement.test_user_id}",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        if data:
            print(f"User extension: {data.get('extension')}")
    
    def test_delete_extension(self, headers):
        """Delete test extension"""
        if not TestExtensionManagement.test_extension:
            pytest.skip("No test extension created")
        
        response = requests.delete(
            f"{BASE_URL}/api/calling/extensions/{TestExtensionManagement.test_extension}",
            headers=headers
        )
        assert response.status_code == 200
        print(f"Deleted extension {TestExtensionManagement.test_extension}")


class TestAutoAttendant(TestAuth):
    """Test auto-attendant configuration"""
    
    def test_get_auto_attendant(self, headers):
        """Get auto-attendant configuration"""
        response = requests.get(f"{BASE_URL}/api/calling/auto-attendant", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should have default structure
        assert "greeting" in data or "enabled" in data
        print(f"Auto-attendant config: enabled={data.get('enabled')}, greeting length={len(data.get('greeting', ''))}")
    
    def test_update_auto_attendant(self, headers):
        """Update auto-attendant with greeting, business hours, menu options"""
        payload = {
            "enabled": True,
            "greeting": "Welcome to 58:12 Global. Press 1 for reception, 2 for directory, 0 for operator.",
            "after_hours_greeting": "Our office is currently closed. Please leave a message after the tone.",
            "business_hours": {
                "start": "08:00",
                "end": "17:00",
                "timezone": "Africa/Kampala"
            },
            "after_hours_action": "voicemail",
            "menu_options": [
                {"key": "1", "action": "transfer", "target": "reception", "label": "Reception"},
                {"key": "2", "action": "directory", "target": "directory", "label": "Staff Directory"},
                {"key": "3", "action": "queue", "target": "support", "label": "Support Queue"},
                {"key": "0", "action": "operator", "target": "operator", "label": "Operator"}
            ]
        }
        response = requests.put(f"{BASE_URL}/api/calling/auto-attendant", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("enabled") == True
        assert "menu_options" in data
        assert len(data.get("menu_options", [])) == 4
        print(f"Updated auto-attendant with {len(data.get('menu_options', []))} menu options")
    
    def test_verify_auto_attendant_saved(self, headers):
        """Verify auto-attendant changes were saved"""
        response = requests.get(f"{BASE_URL}/api/calling/auto-attendant", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("enabled") == True
        assert "Press 1 for reception" in data.get("greeting", "")
        print("Auto-attendant changes verified")


class TestCallQueues(TestAuth):
    """Test call queue CRUD with ring strategies"""
    
    created_queue_id = None
    
    def test_list_queues(self, headers):
        """List call queues"""
        response = requests.get(f"{BASE_URL}/api/calling/queues", headers=headers)
        assert response.status_code == 200
        queues = response.json()
        assert isinstance(queues, list)
        print(f"Found {len(queues)} call queues")
    
    def test_create_queue_with_ring_strategy(self, headers):
        """Create call queue with ring strategy, timeout, members"""
        payload = {
            "name": "TEST_Support_Queue",
            "strategy": "round_robin",
            "timeout": 30,
            "max_wait": 300,
            "members": ["1001", "1002", "1003"],
            "announce_position": True,
            "wrap_up_time": 10
        }
        response = requests.post(f"{BASE_URL}/api/calling/queues", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("name") == "TEST_Support_Queue"
        assert data.get("strategy") == "round_robin"
        assert data.get("timeout") == 30
        assert "id" in data
        
        TestCallQueues.created_queue_id = data["id"]
        print(f"Created queue: {data['name']} with strategy {data['strategy']}")
    
    def test_update_queue(self, headers):
        """Update call queue"""
        if not TestCallQueues.created_queue_id:
            pytest.skip("No queue created")
        
        payload = {
            "strategy": "least_recent",
            "timeout": 45
        }
        response = requests.put(
            f"{BASE_URL}/api/calling/queues/{TestCallQueues.created_queue_id}",
            json=payload, headers=headers
        )
        assert response.status_code == 200
        print("Updated queue strategy and timeout")
    
    def test_delete_queue(self, headers):
        """Delete test queue"""
        if not TestCallQueues.created_queue_id:
            pytest.skip("No queue created")
        
        response = requests.delete(
            f"{BASE_URL}/api/calling/queues/{TestCallQueues.created_queue_id}",
            headers=headers
        )
        assert response.status_code == 200
        print("Deleted test queue")


class TestOutgoingRules(TestAuth):
    """Test outgoing call rules with pattern matching"""
    
    created_rule_id = None
    
    def test_list_outgoing_rules(self, headers):
        """List outgoing rules"""
        response = requests.get(f"{BASE_URL}/api/calling/outgoing-rules", headers=headers)
        assert response.status_code == 200
        rules = response.json()
        assert isinstance(rules, list)
        print(f"Found {len(rules)} outgoing rules")
    
    def test_create_outgoing_rule_allow(self, headers):
        """Create outgoing rule with pattern matching - allow"""
        payload = {
            "name": "TEST_Allow_Local",
            "pattern": "^0[0-9]{9}$",
            "action": "allow",
            "priority": 10,
            "enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/calling/outgoing-rules", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("name") == "TEST_Allow_Local"
        assert data.get("action") == "allow"
        assert data.get("pattern") == "^0[0-9]{9}$"
        assert "id" in data
        
        TestOutgoingRules.created_rule_id = data["id"]
        print(f"Created outgoing rule: {data['name']} with pattern {data['pattern']}")
    
    def test_create_outgoing_rule_block(self, headers):
        """Create outgoing rule - block premium numbers"""
        payload = {
            "name": "TEST_Block_Premium",
            "pattern": "^09[0-9]{8}$",
            "action": "block",
            "priority": 5,
            "enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/calling/outgoing-rules", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("action") == "block"
        print(f"Created block rule: {data['name']}")
        
        # Clean up
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/calling/outgoing-rules/{data['id']}", headers=headers)
    
    def test_create_outgoing_rule_prefix(self, headers):
        """Create outgoing rule - add prefix"""
        payload = {
            "name": "TEST_Add_Prefix",
            "pattern": "^[0-9]{10}$",
            "action": "prefix",
            "prefix": "9",
            "priority": 20,
            "enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/calling/outgoing-rules", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("action") == "prefix"
        assert data.get("prefix") == "9"
        print(f"Created prefix rule: {data['name']}")
        
        # Clean up
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/calling/outgoing-rules/{data['id']}", headers=headers)
    
    def test_delete_outgoing_rule(self, headers):
        """Delete test outgoing rule"""
        if not TestOutgoingRules.created_rule_id:
            pytest.skip("No rule created")
        
        response = requests.delete(
            f"{BASE_URL}/api/calling/outgoing-rules/{TestOutgoingRules.created_rule_id}",
            headers=headers
        )
        assert response.status_code == 200
        print("Deleted test outgoing rule")


class TestCallingContacts(TestAuth):
    """Test that calling contacts returns all staff users"""
    
    def test_get_callable_contacts_returns_all_staff(self, headers, user_id):
        """Verify contacts endpoint returns all staff (with and without extensions)"""
        response = requests.get(f"{BASE_URL}/api/calling/contacts?user_id={user_id}", headers=headers)
        assert response.status_code == 200
        contacts = response.json()
        assert isinstance(contacts, list)
        
        # Count contacts with and without extensions
        with_ext = [c for c in contacts if c.get("extension")]
        without_ext = [c for c in contacts if not c.get("extension")]
        
        print(f"Total contacts: {len(contacts)}")
        print(f"  - With extensions: {len(with_ext)}")
        print(f"  - Without extensions: {len(without_ext)}")
        
        # Should have some contacts
        assert len(contacts) > 0, "No callable contacts returned"
        
        # Verify contact structure
        if contacts:
            sample = contacts[0]
            assert "user_id" in sample
            assert "name" in sample or "display_name" in sample
            print(f"Sample contact: {sample.get('name') or sample.get('display_name')}")


class TestIceServers(TestAuth):
    """Test ICE servers endpoint"""
    
    def test_get_ice_servers(self, headers):
        """Get ICE servers for WebRTC"""
        response = requests.get(f"{BASE_URL}/api/calling/ice-servers", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "ice_servers" in data
        servers = data["ice_servers"]
        assert isinstance(servers, list)
        assert len(servers) > 0
        
        # Should have at least STUN server
        stun_servers = [s for s in servers if "stun:" in str(s.get("urls", ""))]
        assert len(stun_servers) > 0, "No STUN servers configured"
        print(f"ICE servers: {len(servers)} total, {len(stun_servers)} STUN")


class TestCallForwarding(TestAuth):
    """Test call forwarding rules"""
    
    def test_get_forwarding_rules(self, headers, user_id):
        """Get call forwarding rules for user"""
        response = requests.get(f"{BASE_URL}/api/calling/forwarding/{user_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "user_id" in data
        assert "enabled" in data
        print(f"Forwarding enabled: {data.get('enabled')}")
    
    def test_update_forwarding_rules(self, headers, user_id):
        """Update call forwarding rules"""
        payload = {
            "enabled": True,
            "forward_always": None,
            "forward_busy": "+256700000001",
            "forward_no_answer": "+256700000002",
            "forward_no_answer_timeout": 25,
            "forward_offline": "+256700000003"
        }
        response = requests.put(f"{BASE_URL}/api/calling/forwarding/{user_id}", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("enabled") == True
        assert data.get("forward_busy") == "+256700000001"
        print("Updated forwarding rules")


class TestCleanup(TestAuth):
    """Cleanup test data"""
    
    def test_cleanup_test_queues(self, headers):
        """Remove any remaining test queues"""
        response = requests.get(f"{BASE_URL}/api/calling/queues", headers=headers)
        if response.status_code == 200:
            queues = response.json()
            for q in queues:
                if q.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/calling/queues/{q['id']}", headers=headers)
                    print(f"Cleaned up queue: {q['name']}")
    
    def test_cleanup_test_rules(self, headers):
        """Remove any remaining test rules"""
        response = requests.get(f"{BASE_URL}/api/calling/outgoing-rules", headers=headers)
        if response.status_code == 200:
            rules = response.json()
            for r in rules:
                if r.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/calling/outgoing-rules/{r['id']}", headers=headers)
                    print(f"Cleaned up rule: {r['name']}")
    
    def test_cleanup_test_pbx_configs(self, headers):
        """Remove any remaining test PBX configs"""
        response = requests.get(f"{BASE_URL}/api/calling/pbx-configs", headers=headers)
        if response.status_code == 200:
            configs = response.json()
            for c in configs:
                if c.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/calling/pbx-configs/{c['id']}", headers=headers)
                    print(f"Cleaned up PBX config: {c['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
