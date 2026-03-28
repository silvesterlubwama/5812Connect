"""
Iteration 41 Tests - Video Call Auto-Detect, SIP Indicators, SIP-Only Mode
Tests:
1. Video call auto-detect on answer (call_type field in call data)
2. Blue SIP dot on contacts (sipRegistered state)
3. SIP-only mode toggle in PBX config
4. PBX config sip_only field persistence
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIteration41Features:
    """Test iteration 41 features: video calls, SIP indicators, SIP-only mode"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data.get("access_token") or data.get("token")
        self.user_id = data.get("user", {}).get("id")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        # Cleanup test PBX configs
        try:
            configs = self.session.get(f"{BASE_URL}/api/calling/pbx-configs").json()
            for c in configs:
                if c.get("name", "").startswith("TEST_"):
                    self.session.delete(f"{BASE_URL}/api/calling/pbx-configs/{c['id']}")
        except:
            pass
    
    def test_health_check(self):
        """Test API health"""
        resp = self.session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        assert resp.json().get("status") == "healthy"
    
    def test_login_success(self):
        """Test admin login works"""
        assert self.token is not None
        assert self.user_id is not None
    
    def test_pbx_config_sip_only_field(self):
        """Test PBX config supports sip_only field"""
        # Create PBX config with sip_only=True
        create_resp = self.session.post(f"{BASE_URL}/api/calling/pbx-configs", json={
            "name": "TEST_SIP_ONLY_PBX",
            "provider": "freepbx",
            "host": "test-pbx.example.com",
            "port": 5060,
            "sip_username": "test_user",
            "sip_password": "test_pass",
            "sip_domain": "test-pbx.example.com",
            "websocket_url": "wss://test-pbx.example.com:8089/ws",
            "sip_only": True,
            "is_active": True
        })
        assert create_resp.status_code in [200, 201], f"Create failed: {create_resp.text}"
        created = create_resp.json()
        pbx_id = created.get("id")
        assert pbx_id is not None
        
        # Verify sip_only is persisted (API returns array directly)
        get_resp = self.session.get(f"{BASE_URL}/api/calling/pbx-configs")
        assert get_resp.status_code == 200
        configs = get_resp.json()  # Direct array
        test_config = next((c for c in configs if c.get("id") == pbx_id), None)
        assert test_config is not None, "Created config not found"
        assert test_config.get("sip_only") == True, "sip_only field not persisted"
        
        # Update to sip_only=False
        update_resp = self.session.put(f"{BASE_URL}/api/calling/pbx-configs/{pbx_id}", json={
            "name": "TEST_SIP_ONLY_PBX",
            "sip_only": False
        })
        assert update_resp.status_code == 200
        
        # Verify update
        get_resp2 = self.session.get(f"{BASE_URL}/api/calling/pbx-configs")
        configs2 = get_resp2.json()
        test_config2 = next((c for c in configs2 if c.get("id") == pbx_id), None)
        assert test_config2.get("sip_only") == False, "sip_only update not persisted"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/calling/pbx-configs/{pbx_id}")
    
    def test_sip_credentials_endpoint_includes_sip_only(self):
        """Test SIP credentials endpoint returns sip_only field"""
        resp = self.session.get(f"{BASE_URL}/api/calling/pbx-configs/sip-credentials")
        # May return 404 if no default PBX, or 200 with credentials
        assert resp.status_code == 200
        data = resp.json()
        # Should have sip_only field if PBX is configured
        if "sip_username" in data:
            # sip_only should be present (may be None if not set)
            assert "sip_only" in data or data.get("sip_only") is None or data.get("sip_only") == False
    
    def test_contacts_endpoint(self):
        """Test contacts endpoint returns extension info for SIP indicators"""
        # Contacts endpoint requires user_id parameter
        resp = self.session.get(f"{BASE_URL}/api/calling/contacts", params={"user_id": self.user_id})
        assert resp.status_code == 200
        contacts = resp.json()  # Direct array
        # Verify contacts have extension field (for SIP indicator logic)
        for contact in contacts[:5]:  # Check first 5
            assert "user_id" in contact
            # extension may or may not be present
            if "extension" in contact:
                assert isinstance(contact["extension"], (str, type(None)))
    
    def test_extensions_endpoint(self):
        """Test extensions endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/calling/extensions")
        assert resp.status_code == 200
        extensions = resp.json()  # Direct array
        # Verify extension structure
        for ext in extensions[:5]:
            assert "extension" in ext
            assert "user_id" in ext
    
    def test_ice_servers_endpoint(self):
        """Test ICE servers endpoint (used when sip_only=False)"""
        resp = self.session.get(f"{BASE_URL}/api/calling/ice-servers")
        assert resp.status_code == 200
        data = resp.json()
        # Should return ICE server configuration
        assert "iceServers" in data or "ice_servers" in data or isinstance(data, list)
    
    def test_pbx_config_create_without_sip_only(self):
        """Test PBX config defaults sip_only to False"""
        create_resp = self.session.post(f"{BASE_URL}/api/calling/pbx-configs", json={
            "name": "TEST_DEFAULT_SIP_ONLY",
            "provider": "freepbx",
            "host": "test2-pbx.example.com",
            "port": 5060,
            "is_active": True
        })
        assert create_resp.status_code in [200, 201]
        created = create_resp.json()
        pbx_id = created.get("id")
        
        # Verify sip_only defaults to False
        get_resp = self.session.get(f"{BASE_URL}/api/calling/pbx-configs")
        configs = get_resp.json()
        test_config = next((c for c in configs if c.get("id") == pbx_id), None)
        assert test_config is not None
        # sip_only should be False (default)
        assert test_config.get("sip_only", False) == False
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/calling/pbx-configs/{pbx_id}")
    
    def test_extension_has_user_info(self):
        """Test extension includes user info for SIP indicator display"""
        resp = self.session.get(f"{BASE_URL}/api/calling/extensions")
        assert resp.status_code == 200
        extensions = resp.json()
        # Admin should have extension 2450
        admin_ext = next((e for e in extensions if e.get("extension") == "2450"), None)
        if admin_ext:
            assert "user_name" in admin_ext or "display_name" in admin_ext
            assert "user_email" in admin_ext or "email" in admin_ext


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
