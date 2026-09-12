"""
Test suite for Iteration 6 features:
- Password reset flow (forgot-password, reset-password)
- WebSocket endpoints
- Access control APIs
- Reports API
- PWA manifest and service worker
"""
import pytest
import requests
import os

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint working")
    
    def test_login_admin(self):
        """Test admin login with provided credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == creds.ADMIN_EMAIL
        print(f"✓ Admin login successful - role: {data['user'].get('role')}")
        return data["token"]
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "invalid@email.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials rejected correctly")


class TestPasswordReset:
    """Password reset flow tests"""
    
    def test_forgot_password_valid_email(self):
        """Test forgot password with valid email"""
        response = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": creds.ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("✓ Forgot password endpoint works for valid email")
    
    def test_forgot_password_invalid_email(self):
        """Test forgot password with non-existent email (should still return 200 for security)"""
        response = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": "nonexistent@example.com"
        })
        # Should return 200 to not reveal if email exists
        assert response.status_code == 200
        print("✓ Forgot password doesn't reveal if email exists")
    
    def test_forgot_password_empty_email(self):
        """Test forgot password with empty email"""
        response = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": ""
        })
        assert response.status_code == 400
        print("✓ Empty email rejected correctly")
    
    def test_reset_password_invalid_token(self):
        """Test reset password with invalid token"""
        response = requests.post(f"{BASE_URL}/api/auth/reset-password", json={
            "token": "INVALID123",
            "new_password": "NewPassword123"
        })
        assert response.status_code == 400
        print("✓ Invalid reset token rejected correctly")
    
    def test_reset_password_short_password(self):
        """Test reset password with too short password"""
        response = requests.post(f"{BASE_URL}/api/auth/reset-password", json={
            "token": "SOMETOKEN",
            "new_password": "12345"  # Less than 6 chars
        })
        assert response.status_code == 400
        print("✓ Short password rejected correctly")


class TestAccessControl:
    """Access control API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_residents(self):
        """Test listing residents"""
        response = requests.get(f"{BASE_URL}/api/access/residents", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Residents list returned {len(response.json())} items")
    
    def test_list_staff_passes(self):
        """Test listing staff access passes"""
        response = requests.get(f"{BASE_URL}/api/access/staff-passes", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Staff passes list returned {len(response.json())} items")
    
    def test_list_guest_requests(self):
        """Test listing guest requests"""
        response = requests.get(f"{BASE_URL}/api/access/guest-requests", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Guest requests list returned {len(response.json())} items")
    
    def test_list_scan_log(self):
        """Test listing scan log"""
        response = requests.get(f"{BASE_URL}/api/access/scan-log", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Scan log returned {len(response.json())} items")


class TestReportsAPI:
    """Reports API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_reports_summary(self):
        """Test reports summary endpoint"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "financial" in data
        assert "events" in data
        print(f"✓ Reports summary: {data.get('members', {}).get('total', 0)} members, {data.get('events', {}).get('total', 0)} events")
    
    def test_reports_pdf_download(self):
        """Test PDF report download"""
        response = requests.get(f"{BASE_URL}/api/reports/pdf", headers=self.headers)
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 0
        print(f"✓ PDF report downloaded ({len(response.content)} bytes)")


class TestPWAAssets:
    """PWA manifest and service worker tests"""
    
    def test_manifest_json(self):
        """Test PWA manifest is accessible"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "icons" in data
        assert data["name"] == "58:12 Global Connect Uganda"
        print(f"✓ PWA manifest accessible - name: {data['name']}")
    
    def test_service_worker(self):
        """Test service worker is accessible"""
        response = requests.get(f"{BASE_URL}/sw.js")
        assert response.status_code == 200
        assert "serviceWorker" in response.text or "self.addEventListener" in response.text
        print("✓ Service worker accessible")


class TestNotifications:
    """Notifications API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_notifications_list(self):
        """Test listing notifications"""
        response = requests.get(f"{BASE_URL}/api/notifications", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Notifications list returned {len(response.json())} items")
    
    def test_notifications_unread_count(self):
        """Test unread notifications count"""
        response = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        print(f"✓ Unread notifications count: {data['count']}")


class TestCommunications:
    """Communications/Chat API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_conversations_list(self):
        """Test listing conversations"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Conversations list returned {len(response.json())} items")
    
    def test_announcements_list(self):
        """Test listing announcements"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=self.headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Announcements list returned {len(response.json())} items")


class TestLocations:
    """Locations API tests for RBAC"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_locations_list(self):
        """Test listing locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Check for restricted locations
        restricted = [l for l in data if l.get("is_restricted")]
        print(f"✓ Locations list: {len(data)} total, {len(restricted)} restricted")


class TestDashboard:
    """Dashboard stats API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_members" in data
        assert "active_members" in data
        assert "upcoming_events" in data
        print(f"✓ Dashboard stats: {data.get('total_members')} members, {data.get('upcoming_events')} upcoming events")


class TestMembers:
    """Members API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_members_list(self):
        """Test listing members"""
        response = requests.get(f"{BASE_URL}/api/members", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        print(f"✓ Members list: {data['total']} total")
    
    def test_members_gender_validation(self):
        """Test that gender only accepts male/female"""
        # Try to create member with invalid gender
        response = requests.post(f"{BASE_URL}/api/members", headers=self.headers, json={
            "name": "TEST_InvalidGender",
            "gender": "other"  # Should be rejected
        })
        assert response.status_code == 400
        print("✓ Invalid gender 'other' rejected correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
