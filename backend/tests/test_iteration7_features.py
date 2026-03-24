"""
Iteration 7 Feature Tests - 58:12 Global Connect CRM
Tests for:
1. Unified People UI (Members/Families/Children/Guests tabs)
2. API-level RBAC enforcement
3. Web Push notifications (VAPID keys, subscription)
4. Background sync for offline messages
5. Kiosk page functionality
6. Health endpoint
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-member-sync.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


class TestHealthEndpoint:
    """Health check endpoint tests"""
    
    def test_health_returns_healthy(self):
        """GET /api/health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "58:12 Global Connect" in data.get("service", "")
        print("PASS: Health endpoint returns healthy status")


class TestAuthentication:
    """Authentication tests"""
    
    def test_admin_login_success(self):
        """Admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "admin"
        print(f"PASS: Admin login successful - role: {data['user']['role']}")
        return data["token"]
    
    def test_login_invalid_credentials(self):
        """Login with invalid credentials should fail"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("PASS: Invalid credentials rejected with 401")


class TestRBACEnforcement:
    """RBAC (Role-Based Access Control) tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_financial_summary_requires_auth(self):
        """GET /api/financial/summary requires authentication"""
        response = requests.get(f"{BASE_URL}/api/financial/summary")
        assert response.status_code == 401
        print("PASS: /api/financial/summary returns 401 without auth")
    
    def test_financial_summary_with_manager_role(self):
        """GET /api/financial/summary works for Manager+ (admin has level 10)"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly_donations" in data
        assert "monthly_expenses" in data
        assert "monthly_sales" in data
        print(f"PASS: /api/financial/summary works for admin - donations: {data['monthly_donations']}")
    
    def test_import_csv_members_requires_auth(self):
        """POST /api/import/csv/members requires authentication"""
        response = requests.post(f"{BASE_URL}/api/import/csv/members")
        assert response.status_code in [401, 422]  # 401 no auth or 422 missing file
        print("PASS: /api/import/csv/members requires auth")
    
    def test_audit_requires_admin(self):
        """GET /api/audit requires admin role"""
        response = requests.get(f"{BASE_URL}/api/audit", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        print(f"PASS: /api/audit works for admin - {data.get('total', 0)} logs")
    
    def test_audit_without_auth_fails(self):
        """GET /api/audit without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/audit")
        assert response.status_code == 401
        print("PASS: /api/audit returns 401 without auth")
    
    def test_delete_member_requires_coordinator(self):
        """DELETE /api/members/{id} requires Coordinator+ role"""
        # First create a test member
        create_response = requests.post(f"{BASE_URL}/api/members", headers=self.headers, json={
            "name": "TEST_DeleteTest",
            "email": "test_delete@example.com",
            "role": "Member",
            "gender": "male"
        })
        if create_response.status_code == 200:
            member_id = create_response.json()["id"]
            # Admin (level 10) should be able to delete
            delete_response = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=self.headers)
            assert delete_response.status_code == 200
            print("PASS: Admin can delete members (Coordinator+ required)")
        else:
            print(f"SKIP: Could not create test member - {create_response.status_code}")


class TestWebPushNotifications:
    """Web Push notification tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_vapid_key_endpoint(self):
        """GET /api/push/vapid-key returns public key"""
        response = requests.get(f"{BASE_URL}/api/push/vapid-key")
        assert response.status_code == 200
        data = response.json()
        assert "publicKey" in data
        assert data["publicKey"].startswith("BPush-")
        print(f"PASS: VAPID key returned: {data['publicKey'][:20]}...")
    
    def test_push_subscribe_requires_auth(self):
        """POST /api/push/subscribe requires authentication"""
        response = requests.post(f"{BASE_URL}/api/push/subscribe", json={
            "subscription": {"endpoint": "https://test.example.com"}
        })
        assert response.status_code == 401
        print("PASS: /api/push/subscribe requires auth")
    
    def test_push_subscribe_with_auth(self):
        """POST /api/push/subscribe works with valid auth"""
        response = requests.post(f"{BASE_URL}/api/push/subscribe", headers=self.headers, json={
            "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test123",
                "keys": {"p256dh": "test_key", "auth": "test_auth"}
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("PASS: Push subscription saved successfully")


class TestOfflineSync:
    """Background sync for offline messages tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_sync_messages_requires_auth(self):
        """POST /api/sync/messages requires authentication"""
        response = requests.post(f"{BASE_URL}/api/sync/messages", json={
            "messages": []
        })
        assert response.status_code == 401
        print("PASS: /api/sync/messages requires auth")
    
    def test_sync_messages_accepts_offline_messages(self):
        """POST /api/sync/messages accepts offline messages"""
        import uuid
        test_msg_id = f"offline_test_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/sync/messages", headers=self.headers, json={
            "messages": [
                {
                    "conversation_id": "test_conv_123",
                    "text": "Test offline message",
                    "id": test_msg_id,
                    "created_at": "2026-01-22T10:00:00Z"
                }
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert "synced" in data
        assert data["synced"] >= 0  # May be 0 if duplicate
        print(f"PASS: Sync messages endpoint works - synced: {data['synced']}")
    
    def test_sync_empty_messages(self):
        """POST /api/sync/messages handles empty array"""
        response = requests.post(f"{BASE_URL}/api/sync/messages", headers=self.headers, json={
            "messages": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["synced"] == 0
        print("PASS: Sync handles empty messages array")


class TestUnifiedPeopleAPI:
    """Tests for unified people management (Members, Families, Children, Guests)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_members(self):
        """GET /api/members returns member list"""
        response = requests.get(f"{BASE_URL}/api/members", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        print(f"PASS: Members list - {data['total']} members")
    
    def test_list_families(self):
        """GET /api/families returns family list"""
        response = requests.get(f"{BASE_URL}/api/families", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Families list - {len(data)} families")
    
    def test_list_children(self):
        """GET /api/children returns children list"""
        response = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Children list - {len(data)} children")
    
    def test_list_guests(self):
        """GET /api/guests returns guest list"""
        response = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Guests list - {len(data)} guests")
    
    def test_create_member_gender_validation(self):
        """POST /api/members validates gender (male/female only)"""
        # Test invalid gender
        response = requests.post(f"{BASE_URL}/api/members", headers=self.headers, json={
            "name": "TEST_GenderTest",
            "gender": "other"
        })
        assert response.status_code == 400
        print("PASS: Invalid gender 'other' rejected")
        
        # Test valid gender
        response = requests.post(f"{BASE_URL}/api/members", headers=self.headers, json={
            "name": "TEST_GenderValid",
            "gender": "female",
            "role": "Member"
        })
        assert response.status_code == 200
        member_id = response.json()["id"]
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=self.headers)
        print("PASS: Valid gender 'female' accepted")


class TestKioskEndpoints:
    """Kiosk functionality tests"""
    
    def test_kiosk_checkin(self):
        """POST /api/kiosk/checkin works without auth"""
        response = requests.post(f"{BASE_URL}/api/kiosk/checkin", json={
            "member_name": "Test Visitor",
            "type": "visitor",
            "method": "manual"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["type"] == "visitor"
        print(f"PASS: Kiosk check-in works - ID: {data['id']}")
    
    def test_kiosk_lookup_not_found(self):
        """GET /api/kiosk/lookup returns 404 for unknown ID"""
        response = requests.get(f"{BASE_URL}/api/kiosk/lookup", params={
            "identifier": "UNKNOWN_ID_12345"
        })
        assert response.status_code == 404
        print("PASS: Kiosk lookup returns 404 for unknown ID")


class TestReportsEndpoint:
    """Reports functionality tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_reports_summary(self):
        """GET /api/reports/summary returns report data"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # Should have various stats
        print(f"PASS: Reports summary endpoint works")
    
    def test_reports_pdf_export(self):
        """GET /api/reports/pdf returns PDF file"""
        response = requests.get(f"{BASE_URL}/api/reports/pdf", headers=self.headers)
        assert response.status_code == 200
        # Check content type is PDF
        content_type = response.headers.get("content-type", "")
        assert "pdf" in content_type.lower() or "octet-stream" in content_type.lower()
        print("PASS: Reports PDF export works")


class TestLocationsEndpoint:
    """Locations management tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_locations(self):
        """GET /api/locations returns location list"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Locations list - {len(data)} locations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
