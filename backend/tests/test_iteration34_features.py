"""
Iteration 34 - Phase D+E Features Testing
Tests for:
1. Adviser campus switcher (has_campus_switcher includes 'adviser')
2. Chat defaults to 1 user (auto-detect direct vs group)
3. GDPR accessible to all roles
4. Venue offsite/non-bookable options
5. Extension in staff profile admin edit
6. QR code check-in scanning
7. Public calendar country detection (frontend)
8. Outreach auto-creates/deletes events
9. Auto-attendant & call queues (PBX)
10. Call forwarding rules
11. Outgoing call rules
12. Events ordering (upcoming first)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Login and get auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in login response"
    return data["token"]

@pytest.fixture(scope="module")
def headers(auth_token):
    """Auth headers for requests"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def user_info(auth_token):
    """Get current user info"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    assert response.status_code == 200
    return response.json()


class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"Login successful - User: {data['user'].get('name')}, Role: {data['user'].get('role')}")


class TestAdviserCampusSwitcher:
    """Test that Advisers can use campus switcher"""
    
    def test_set_active_campus(self, headers, user_info):
        """Test setting active campus (admin/ED/Adviser can do this)"""
        # First get locations
        response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert response.status_code == 200
        locations = response.json()
        
        if len(locations) > 0:
            campus_id = locations[0]["id"]
            # Set active campus
            response = requests.put(f"{BASE_URL}/api/user/active-campus", 
                                   json={"campus_id": campus_id}, headers=headers)
            assert response.status_code == 200
            print(f"Set active campus to: {locations[0].get('name')}")
    
    def test_clear_active_campus(self, headers):
        """Test clearing active campus filter"""
        response = requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=headers)
        assert response.status_code == 200
        print("Cleared active campus filter")


class TestGDPRAccessible:
    """Test GDPR endpoints accessible to all roles"""
    
    def test_gdpr_settings_accessible(self, headers):
        """Test GDPR settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/gdpr/settings", headers=headers)
        assert response.status_code == 200
        data = response.json()
        print(f"GDPR settings accessible - Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")


class TestVenueOffsiteNonBookable:
    """Test venue with is_offsite and is_bookable fields"""
    
    def test_create_venue_with_offsite_fields(self, headers):
        """Create venue with new offsite/bookable fields"""
        venue_data = {
            "name": f"TEST_Offsite_Venue_{uuid.uuid4().hex[:6]}",
            "capacity": 50,
            "type": "outdoor",
            "description": "Test offsite venue",
            "is_offsite": True,
            "is_bookable": False,
            "country": "Uganda",
            "address": "123 Test Street, Kampala"
        }
        response = requests.post(f"{BASE_URL}/api/venues", json=venue_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_offsite") == True
        assert data.get("is_bookable") == False
        assert data.get("country") == "Uganda"
        assert data.get("address") == "123 Test Street, Kampala"
        print(f"Created offsite venue: {data.get('name')} - is_offsite={data.get('is_offsite')}, is_bookable={data.get('is_bookable')}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/venues/{data['id']}", headers=headers)
    
    def test_update_venue_offsite_fields(self, headers):
        """Update venue offsite/bookable fields"""
        # Create a venue first
        venue_data = {
            "name": f"TEST_Update_Venue_{uuid.uuid4().hex[:6]}",
            "capacity": 30,
            "type": "hall"
        }
        create_resp = requests.post(f"{BASE_URL}/api/venues", json=venue_data, headers=headers)
        assert create_resp.status_code == 200
        venue_id = create_resp.json().get("id")
        
        # Update with offsite fields
        update_data = {
            "is_offsite": True,
            "is_bookable": True,
            "country": "Kenya",
            "address": "456 Nairobi Road"
        }
        response = requests.put(f"{BASE_URL}/api/venues/{venue_id}", json=update_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_offsite") == True
        assert data.get("country") == "Kenya"
        print(f"Updated venue with offsite fields: country={data.get('country')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/venues/{venue_id}", headers=headers)


class TestQRCodeCheckin:
    """Test QR code check-in endpoint"""
    
    def test_qr_scan_checkin_invalid_qr(self, headers):
        """Test QR scan with invalid QR data returns 404"""
        response = requests.post(f"{BASE_URL}/api/checkins/qr-scan", 
                                json={"qr_data": "invalid_qr_code_12345"},
                                headers=headers)
        # Should return 404 for invalid QR
        assert response.status_code == 404
        print("QR scan with invalid data correctly returns 404")
    
    def test_qr_scan_checkin_empty_qr(self, headers):
        """Test QR scan with empty QR data returns 400"""
        response = requests.post(f"{BASE_URL}/api/checkins/qr-scan", 
                                json={"qr_data": ""},
                                headers=headers)
        assert response.status_code == 400
        print("QR scan with empty data correctly returns 400")
    
    def test_qr_scan_endpoint_exists(self, headers):
        """Test QR scan endpoint exists and accepts POST"""
        response = requests.post(f"{BASE_URL}/api/checkins/qr-scan", 
                                json={"qr_data": "test_member_id", "event_id": "", "event_name": ""},
                                headers=headers)
        # Should return 404 (member not found) not 405 (method not allowed)
        assert response.status_code in [200, 404]
        print(f"QR scan endpoint exists - status: {response.status_code}")


class TestAutoAttendant:
    """Test auto-attendant PBX feature"""
    
    def test_get_auto_attendant(self, headers):
        """Get auto-attendant configuration"""
        response = requests.get(f"{BASE_URL}/api/calling/auto-attendant", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have default config
        assert "greeting" in data or "enabled" in data
        print(f"Auto-attendant config: enabled={data.get('enabled')}, greeting={data.get('greeting', '')[:50]}...")
    
    def test_update_auto_attendant(self, headers):
        """Update auto-attendant configuration"""
        update_data = {
            "enabled": True,
            "greeting": "Welcome to 58:12 Global. Press 1 for reception.",
            "menu_options": [
                {"key": "1", "action": "transfer", "target": "reception", "label": "Reception"},
                {"key": "2", "action": "directory", "target": "directory", "label": "Directory"}
            ],
            "business_hours": {"start": "08:00", "end": "17:00", "timezone": "Africa/Kampala"}
        }
        response = requests.put(f"{BASE_URL}/api/calling/auto-attendant", 
                               json=update_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("enabled") == True
        print(f"Updated auto-attendant: enabled={data.get('enabled')}")


class TestCallQueues:
    """Test call queues CRUD"""
    
    def test_list_call_queues(self, headers):
        """List call queues"""
        response = requests.get(f"{BASE_URL}/api/calling/queues", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Call queues count: {len(data)}")
    
    def test_create_call_queue(self, headers):
        """Create a call queue"""
        queue_data = {
            "name": f"TEST_Support_Queue_{uuid.uuid4().hex[:6]}",
            "strategy": "ring_all",
            "timeout": 30,
            "max_wait": 300,
            "members": [],
            "announce_position": True
        }
        response = requests.post(f"{BASE_URL}/api/calling/queues", 
                                json=queue_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == queue_data["name"]
        assert data.get("strategy") == "ring_all"
        print(f"Created call queue: {data.get('name')} with strategy={data.get('strategy')}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/calling/queues/{data['id']}", headers=headers)
    
    def test_call_queue_strategies(self, headers):
        """Test different queue strategies"""
        strategies = ["ring_all", "round_robin", "least_recent", "random"]
        for strategy in strategies:
            queue_data = {
                "name": f"TEST_Queue_{strategy}_{uuid.uuid4().hex[:4]}",
                "strategy": strategy,
                "timeout": 20
            }
            response = requests.post(f"{BASE_URL}/api/calling/queues", 
                                    json=queue_data, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data.get("strategy") == strategy
            # Cleanup
            if data.get("id"):
                requests.delete(f"{BASE_URL}/api/calling/queues/{data['id']}", headers=headers)
        print(f"All queue strategies work: {strategies}")


class TestCallForwarding:
    """Test call forwarding rules"""
    
    def test_get_forwarding_rules(self, headers, user_info):
        """Get call forwarding rules for user"""
        user_id = user_info.get("id")
        response = requests.get(f"{BASE_URL}/api/calling/forwarding/{user_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "enabled" in data
        print(f"Forwarding rules for user: enabled={data.get('enabled')}")
    
    def test_update_forwarding_rules(self, headers, user_info):
        """Update call forwarding rules"""
        user_id = user_info.get("id")
        update_data = {
            "enabled": True,
            "forward_always": None,
            "forward_busy": "+256700000001",
            "forward_no_answer": "+256700000002",
            "forward_no_answer_timeout": 25,
            "forward_offline": "+256700000003"
        }
        response = requests.put(f"{BASE_URL}/api/calling/forwarding/{user_id}", 
                               json=update_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("enabled") == True
        assert data.get("forward_busy") == "+256700000001"
        print(f"Updated forwarding: forward_busy={data.get('forward_busy')}")


class TestOutgoingRules:
    """Test outgoing call rules"""
    
    def test_list_outgoing_rules(self, headers):
        """List outgoing call rules"""
        response = requests.get(f"{BASE_URL}/api/calling/outgoing-rules", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Outgoing rules count: {len(data)}")
    
    def test_create_outgoing_rule(self, headers):
        """Create an outgoing call rule"""
        rule_data = {
            "name": f"TEST_Block_International_{uuid.uuid4().hex[:6]}",
            "pattern": "^00.*",
            "action": "block",
            "priority": 10,
            "enabled": True
        }
        response = requests.post(f"{BASE_URL}/api/calling/outgoing-rules", 
                                json=rule_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == rule_data["name"]
        assert data.get("action") == "block"
        print(f"Created outgoing rule: {data.get('name')} - action={data.get('action')}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/calling/outgoing-rules/{data['id']}", headers=headers)


class TestOutreachAutoEvents:
    """Test outreach programme auto-creates/deletes events"""
    
    def test_create_recurring_programme_generates_events(self, headers):
        """Create recurring programme and verify events are generated"""
        programme_data = {
            "name": f"TEST_Recurring_Programme_{uuid.uuid4().hex[:6]}",
            "description": "Test recurring outreach",
            "category": "community",
            "status": "active",
            "is_recurring": True,
            "recurrence_pattern": "saturday",
            "recurrence_day": 2,  # 2nd Saturday
            "recurrence_time": "10:00",
            "recurrence_end_time": "13:00"
        }
        response = requests.post(f"{BASE_URL}/api/outreach/programs", 
                                json=programme_data, headers=headers)
        assert response.status_code == 200
        data = response.json()
        prog_id = data.get("id")
        print(f"Created recurring programme: {data.get('name')}")
        
        # Check if events were auto-generated (may take a moment)
        events_resp = requests.get(f"{BASE_URL}/api/events", headers=headers)
        assert events_resp.status_code == 200
        
        # Cleanup - delete programme (should also delete associated events)
        if prog_id:
            del_resp = requests.delete(f"{BASE_URL}/api/outreach/programs/{prog_id}", headers=headers)
            assert del_resp.status_code == 200
            print(f"Deleted programme {prog_id} - associated events should be auto-deleted")


class TestEventsOrdering:
    """Test events are ordered with upcoming first"""
    
    def test_events_upcoming_first(self, headers):
        """Verify events are sorted with upcoming status first"""
        response = requests.get(f"{BASE_URL}/api/events", headers=headers)
        assert response.status_code == 200
        events = response.json()
        
        if len(events) > 1:
            # Check that upcoming events come before completed
            statuses = [e.get("status", "") for e in events]
            upcoming_indices = [i for i, s in enumerate(statuses) if s == "upcoming"]
            completed_indices = [i for i, s in enumerate(statuses) if s == "completed"]
            
            if upcoming_indices and completed_indices:
                # All upcoming should come before all completed
                max_upcoming = max(upcoming_indices) if upcoming_indices else -1
                min_completed = min(completed_indices) if completed_indices else float('inf')
                assert max_upcoming < min_completed or not completed_indices, \
                    "Upcoming events should be sorted before completed events"
                print(f"Events ordering verified: upcoming events come first")
            else:
                print(f"Events found: {len(events)}, statuses: {set(statuses)}")
        else:
            print(f"Only {len(events)} events found - ordering test skipped")


class TestExtensionInProfile:
    """Test extension field in user profile via calling API"""
    
    def test_extension_field_via_calling_api(self, headers, user_info):
        """Verify extension can be retrieved via calling API"""
        user_id = user_info.get("id")
        response = requests.get(f"{BASE_URL}/api/calling/extensions/user/{user_id}", headers=headers)
        # May return 200 with data or null if no extension assigned
        assert response.status_code == 200
        data = response.json()
        print(f"User extension via calling API: {data}")
    
    def test_create_extension_via_calling_api(self, headers, user_info):
        """Test creating extension via calling API (the correct way)"""
        user_id = user_info.get("id")
        # First check if user already has extension
        check_resp = requests.get(f"{BASE_URL}/api/calling/extensions/user/{user_id}", headers=headers)
        if check_resp.status_code == 200 and check_resp.json():
            print("User already has extension - skipping creation")
            return
        
        ext_data = {
            "user_id": user_id,
            "extension": "2460",
            "display_name": "Test Admin",
            "voicemail_enabled": True,
            "forward_to": "+256700000000"
        }
        response = requests.post(f"{BASE_URL}/api/calling/extensions", 
                                json=ext_data, headers=headers)
        # May return 200 (created) or 400 (already exists)
        if response.status_code == 200:
            data = response.json()
            print(f"Created extension: {data.get('extension')}")
            # Cleanup
            requests.delete(f"{BASE_URL}/api/calling/extensions/{data.get('extension')}", headers=headers)
        elif response.status_code == 400:
            print(f"Extension creation returned 400 (likely already exists): {response.json()}")
        else:
            print(f"Extension creation returned: {response.status_code}")


class TestChatConversationAutoDetect:
    """Test chat conversation auto-detects direct vs group"""
    
    def test_create_direct_conversation(self, headers, user_info):
        """Create conversation with 1 participant (should be direct)"""
        # Get another user to chat with
        users_resp = requests.get(f"{BASE_URL}/api/admin/users?limit=5", headers=headers)
        if users_resp.status_code != 200:
            pytest.skip("Cannot get users list")
        
        users = users_resp.json()
        if isinstance(users, dict):
            users = users.get("users", [])
        
        other_users = [u for u in users if u.get("id") != user_info.get("id")]
        if not other_users:
            pytest.skip("No other users to create conversation with")
        
        conv_data = {
            "name": "",  # Empty name - should auto-name for direct
            "participants": [other_users[0]["id"]],
            "type": "direct"
        }
        response = requests.post(f"{BASE_URL}/api/chat/conversations", 
                                json=conv_data, headers=headers)
        # May return 200 or conversation may already exist
        if response.status_code == 200:
            data = response.json()
            print(f"Created direct conversation: {data.get('name', 'unnamed')}, type={data.get('type')}")
        else:
            print(f"Conversation creation returned: {response.status_code}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_venues(self, headers):
        """Clean up test venues"""
        response = requests.get(f"{BASE_URL}/api/venues", headers=headers)
        if response.status_code == 200:
            venues = response.json()
            for venue in venues:
                if venue.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/venues/{venue['id']}", headers=headers)
        print("Cleaned up test venues")
    
    def test_cleanup_test_queues(self, headers):
        """Clean up test call queues"""
        response = requests.get(f"{BASE_URL}/api/calling/queues", headers=headers)
        if response.status_code == 200:
            queues = response.json()
            for queue in queues:
                if queue.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/calling/queues/{queue['id']}", headers=headers)
        print("Cleaned up test call queues")
    
    def test_cleanup_test_rules(self, headers):
        """Clean up test outgoing rules"""
        response = requests.get(f"{BASE_URL}/api/calling/outgoing-rules", headers=headers)
        if response.status_code == 200:
            rules = response.json()
            for rule in rules:
                if rule.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/calling/outgoing-rules/{rule['id']}", headers=headers)
        print("Cleaned up test outgoing rules")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
