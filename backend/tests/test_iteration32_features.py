"""
Iteration 32 Backend Tests
Tests for:
1. AdminPage refactoring - UserCreateDialog, UserImportDialog, UserEditDialog, BadgePrintView
2. server.py modularization - settings.py router (/api/currencies, /api/global-settings, /api/app-settings, /api/gdpr/settings, /api/financial-apis, /api/inventory/alerts)
3. Conference scheduling with email invites
4. Thread support in chat
5. Presence improvements
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_admin(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@5812uganda.org"
        print(f"✓ Admin login successful, role: {data['user'].get('role')}")
        return data["token"]


class TestSettingsRouter:
    """Test settings.py router endpoints (extracted from server.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_get_currencies(self):
        """Test /api/currencies endpoint"""
        response = requests.get(f"{BASE_URL}/api/currencies", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Check for expected currencies
        codes = [c["code"] for c in data]
        assert "UGX" in codes, "UGX currency missing"
        assert "USD" in codes, "USD currency missing"
        print(f"✓ Currencies endpoint returned {len(data)} currencies")
    
    def test_get_global_settings(self):
        """Test /api/global-settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/global-settings", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "app_name" in data or "_key" in data
        print(f"✓ Global settings retrieved")
    
    def test_update_global_settings(self):
        """Test PUT /api/global-settings endpoint"""
        response = requests.put(f"{BASE_URL}/api/global-settings", 
            headers=self.headers,
            json={"app_name": "58:12 Global Connect", "currency": "UGX"})
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Global settings updated")
    
    def test_get_app_settings(self):
        """Test /api/app-settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/app-settings", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "user_id" in data or "dark_mode" in data or "language" in data
        print(f"✓ App settings retrieved")
    
    def test_update_app_settings(self):
        """Test PUT /api/app-settings endpoint"""
        response = requests.put(f"{BASE_URL}/api/app-settings", 
            headers=self.headers,
            json={"dark_mode": False, "language": "en"})
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ App settings updated")
    
    def test_get_gdpr_settings(self):
        """Test /api/gdpr/settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/gdpr/settings", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "retention_months" in data or "consent_required" in data
        print(f"✓ GDPR settings retrieved")
    
    def test_update_gdpr_settings(self):
        """Test PUT /api/gdpr/settings endpoint"""
        response = requests.put(f"{BASE_URL}/api/gdpr/settings", 
            headers=self.headers,
            json={"retention_months": 36, "consent_required": True})
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ GDPR settings updated")
    
    def test_get_financial_apis(self):
        """Test /api/financial-apis endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial-apis", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Financial APIs list retrieved ({len(data)} items)")
    
    def test_create_financial_api(self):
        """Test POST /api/financial-apis endpoint"""
        response = requests.post(f"{BASE_URL}/api/financial-apis", 
            headers=self.headers,
            json={
                "name": "TEST_PaymentAPI",
                "type": "payment",
                "provider": "test_provider",
                "api_url": "https://api.test.com",
                "enabled": True
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        self.test_api_id = data["id"]
        print(f"✓ Financial API created: {data['id']}")
        return data["id"]
    
    def test_get_inventory_alerts(self):
        """Test /api/inventory/alerts endpoint"""
        response = requests.get(f"{BASE_URL}/api/inventory/alerts", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "alerts" in data
        assert "count" in data
        print(f"✓ Inventory alerts retrieved ({data['count']} alerts)")


class TestChatThreadSupport:
    """Test chat thread support"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_create_conversation(self):
        """Test creating a conversation"""
        response = requests.post(f"{BASE_URL}/api/chat/conversations", 
            headers=self.headers,
            json={
                "name": "TEST_ThreadConversation",
                "type": "group",
                "participants": [self.user_id]
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        self.conv_id = data["id"]
        print(f"✓ Conversation created: {data['id']}")
        return data["id"]
    
    def test_send_message_and_thread_reply(self):
        """Test sending a message and replying in a thread"""
        # Create conversation first
        conv_response = requests.post(f"{BASE_URL}/api/chat/conversations", 
            headers=self.headers,
            json={
                "name": "TEST_ThreadTest",
                "type": "group",
                "participants": [self.user_id]
            })
        assert conv_response.status_code == 200
        conv_id = conv_response.json()["id"]
        
        # Send parent message
        msg_response = requests.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", 
            headers=self.headers,
            json={"text": "TEST_ParentMessage"})
        assert msg_response.status_code == 200, f"Failed: {msg_response.text}"
        parent_msg = msg_response.json()
        assert "id" in parent_msg
        parent_id = parent_msg["id"]
        print(f"✓ Parent message sent: {parent_id}")
        
        # Send thread reply
        thread_response = requests.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", 
            headers=self.headers,
            json={"text": "TEST_ThreadReply", "thread_id": parent_id})
        assert thread_response.status_code == 200, f"Failed: {thread_response.text}"
        thread_msg = thread_response.json()
        assert thread_msg.get("thread_id") == parent_id
        print(f"✓ Thread reply sent with thread_id: {thread_msg.get('thread_id')}")
        
        # Get messages with thread_id filter
        thread_msgs_response = requests.get(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/messages",
            headers=self.headers,
            params={"thread_id": parent_id})
        assert thread_msgs_response.status_code == 200
        thread_msgs = thread_msgs_response.json()
        assert len(thread_msgs) >= 1
        print(f"✓ Thread messages retrieved: {len(thread_msgs)} messages")
    
    def test_get_messages_with_thread_count(self):
        """Test that messages include thread_count"""
        # Create conversation
        conv_response = requests.post(f"{BASE_URL}/api/chat/conversations", 
            headers=self.headers,
            json={
                "name": "TEST_ThreadCountTest",
                "type": "group",
                "participants": [self.user_id]
            })
        conv_id = conv_response.json()["id"]
        
        # Send parent message
        msg_response = requests.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", 
            headers=self.headers,
            json={"text": "TEST_ParentForCount"})
        parent_id = msg_response.json()["id"]
        
        # Send 2 thread replies
        for i in range(2):
            requests.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", 
                headers=self.headers,
                json={"text": f"TEST_Reply{i}", "thread_id": parent_id})
        
        # Get top-level messages (should include thread_count)
        msgs_response = requests.get(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/messages",
            headers=self.headers)
        assert msgs_response.status_code == 200
        msgs = msgs_response.json()
        parent_msg = next((m for m in msgs if m["id"] == parent_id), None)
        assert parent_msg is not None
        assert parent_msg.get("thread_count", 0) >= 2
        print(f"✓ Thread count verified: {parent_msg.get('thread_count')} replies")


class TestConferenceScheduling:
    """Test conference scheduling with email invites"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_create_scheduled_conference(self):
        """Test creating a scheduled conference with calendar event"""
        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        response = requests.post(
            f"{BASE_URL}/api/conferences?user_id={self.user_id}",
            headers=self.headers,
            json={
                "title": "TEST_ScheduledConference",
                "description": "Test conference for iteration 32",
                "scheduled_at": scheduled_time,
                "duration_minutes": 60,
                "is_video_enabled": True,
                "user_ids": [],
                "external_emails": ["test@example.com"],
                "create_calendar_event": True,
                "send_email_invites": True
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert "meeting_code" in data
        assert "join_link" in data
        assert data["status"] in ["scheduled", "ready"]
        print(f"✓ Conference created: {data['id']}, code: {data['meeting_code']}")
        return data["id"]
    
    def test_create_instant_meeting(self):
        """Test creating an instant meeting"""
        response = requests.post(
            f"{BASE_URL}/api/conferences/instant?title=TEST_InstantMeeting&user_id={self.user_id}",
            headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["status"] == "ongoing"
        print(f"✓ Instant meeting created: {data['id']}")
        return data["id"]
    
    def test_list_conferences(self):
        """Test listing conferences"""
        response = requests.get(
            f"{BASE_URL}/api/conferences?user_id={self.user_id}",
            headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Conferences listed: {len(data)} conferences")
    
    def test_conference_with_external_emails(self):
        """Test conference creation with external email invites"""
        response = requests.post(
            f"{BASE_URL}/api/conferences?user_id={self.user_id}",
            headers=self.headers,
            json={
                "title": "TEST_ExternalInviteConf",
                "scheduled_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
                "duration_minutes": 30,
                "external_emails": ["external1@test.com", "external2@test.com"],
                "send_email_invites": True,
                "create_calendar_event": False
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert len(data.get("external_invites", [])) == 2
        print(f"✓ Conference with external invites created: {len(data['external_invites'])} external emails")
    
    def test_join_conference(self):
        """Test joining a conference"""
        # Create conference first
        create_response = requests.post(
            f"{BASE_URL}/api/conferences/instant?title=TEST_JoinTest&user_id={self.user_id}",
            headers=self.headers)
        conf_id = create_response.json()["id"]
        
        # Join conference
        join_response = requests.post(
            f"{BASE_URL}/api/conferences/{conf_id}/join?user_id={self.user_id}",
            headers=self.headers,
            json={"display_name": "Test User"})
        assert join_response.status_code == 200, f"Failed: {join_response.text}"
        data = join_response.json()
        assert "conference" in data
        assert "participant" in data
        assert "ice_servers" in data
        print(f"✓ Joined conference successfully")


class TestPresenceAPI:
    """Test presence API improvements"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_heartbeat(self):
        """Test presence heartbeat"""
        response = requests.put(
            f"{BASE_URL}/api/presence/heartbeat?user_id={self.user_id}",
            headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Heartbeat sent successfully")
    
    def test_set_status(self):
        """Test setting presence status"""
        response = requests.put(
            f"{BASE_URL}/api/presence/status?user_id={self.user_id}&status=online",
            headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Status set to online")
    
    def test_get_online_users(self):
        """Test getting online users"""
        # First send heartbeat
        requests.put(
            f"{BASE_URL}/api/presence/heartbeat?user_id={self.user_id}",
            headers=self.headers)
        
        response = requests.get(
            f"{BASE_URL}/api/presence/online-users",
            headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Online users retrieved: {len(data)} users")


class TestAdminUserManagement:
    """Test admin user management (for AdminPage refactoring verification)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_list_users(self):
        """Test listing users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Users listed: {len(data)} users")
    
    def test_create_user(self):
        """Test creating a user (UserCreateDialog)"""
        unique_email = f"test_user_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/admin/users", 
            headers=self.headers,
            json={
                "name": "TEST_NewUser",
                "email": unique_email,
                "phone": "+256700000000",
                "role": "Staff",
                "department": "Testing",
                "also_create_member": True
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["email"] == unique_email
        print(f"✓ User created: {data['id']}")
        return data["id"]
    
    def test_import_users(self):
        """Test importing users (UserImportDialog)"""
        unique_email = f"test_import_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/admin/users/import", 
            headers=self.headers,
            json={
                "users": [
                    {"name": "TEST_ImportUser1", "email": unique_email, "role": "Staff"}
                ]
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "created" in data
        print(f"✓ Users imported: {data['created']} created, {data.get('skipped', 0)} skipped")
    
    def test_get_user_full_profile(self):
        """Test getting user full profile (UserEditDialog)"""
        # First get a user
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        users = users_response.json()
        if not users:
            pytest.skip("No users to test")
        
        user_id = users[0]["id"]
        response = requests.get(f"{BASE_URL}/api/admin/users/{user_id}/profile", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "name" in data
        assert "email" in data
        print(f"✓ User full profile retrieved: {data['name']}")
    
    def test_update_user(self):
        """Test updating a user (UserEditDialog save)"""
        # Create a test user first
        unique_email = f"test_update_{uuid.uuid4().hex[:8]}@test.com"
        create_response = requests.post(f"{BASE_URL}/api/admin/users", 
            headers=self.headers,
            json={"name": "TEST_UpdateUser", "email": unique_email, "role": "Staff"})
        user_id = create_response.json()["id"]
        
        # Update the user
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", 
            headers=self.headers,
            json={"name": "TEST_UpdatedName", "department": "Updated Dept"})
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("name") == "TEST_UpdatedName" or "id" in data
        print(f"✓ User updated successfully")
    
    def test_reset_password(self):
        """Test resetting user password"""
        # Create a test user first
        unique_email = f"test_reset_{uuid.uuid4().hex[:8]}@test.com"
        create_response = requests.post(f"{BASE_URL}/api/admin/users", 
            headers=self.headers,
            json={"name": "TEST_ResetPwUser", "email": unique_email, "role": "Staff"})
        user_id = create_response.json()["id"]
        
        # Reset password
        response = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/reset-password", 
            headers=self.headers,
            json={"new_password": "NewPassword123!"})
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Password reset successfully")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.user_id = response.json()["user"]["id"]
        else:
            pytest.skip("Auth failed")
    
    def test_cleanup_test_users(self):
        """Clean up TEST_ prefixed users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        if response.status_code == 200:
            users = response.json()
            test_users = [u for u in users if u.get("name", "").startswith("TEST_")]
            deleted = 0
            for user in test_users:
                del_response = requests.delete(
                    f"{BASE_URL}/api/admin/users/{user['id']}", 
                    headers=self.headers)
                if del_response.status_code == 200:
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test users")
    
    def test_cleanup_test_financial_apis(self):
        """Clean up TEST_ prefixed financial APIs"""
        response = requests.get(f"{BASE_URL}/api/financial-apis", headers=self.headers)
        if response.status_code == 200:
            apis = response.json()
            test_apis = [a for a in apis if a.get("name", "").startswith("TEST_")]
            deleted = 0
            for api in test_apis:
                del_response = requests.delete(
                    f"{BASE_URL}/api/financial-apis/{api['id']}", 
                    headers=self.headers)
                if del_response.status_code == 200:
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test financial APIs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
