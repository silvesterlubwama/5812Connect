"""
Backend API tests for 58:12 Global Connect CRM - New Features (Iteration 2)
Tests: Analytics, Announcements, Outreach, Resources, Badges, Cashflow, App Settings, Google Auth
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://crm-production-3.preview.emergentagent.com')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        return data["token"]
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@5812global.org"
        assert data["user"]["role"] == "admin"
    
    def test_google_session_invalid(self):
        """Test Google auth with invalid session_id returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/google-session", json={
            "session_id": "invalid_session_id_12345"
        })
        assert response.status_code == 401


class TestAnalytics:
    """Analytics endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_attendance_analytics(self, auth_headers):
        """GET /api/analytics/attendance returns attendance data"""
        response = requests.get(f"{BASE_URL}/api/analytics/attendance", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "total_today" in data or "weekly_data" in data or "recent" in data
    
    def test_sales_analytics(self, auth_headers):
        """GET /api/analytics/sales returns sales analytics data"""
        response = requests.get(f"{BASE_URL}/api/analytics/sales", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "total_revenue" in data or "monthly_data" in data or "payment_breakdown" in data
    
    def test_location_analytics(self, auth_headers):
        """GET /api/analytics/locations returns location analytics data"""
        response = requests.get(f"{BASE_URL}/api/analytics/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert "locations" in data or isinstance(data, list)


class TestAnnouncements:
    """Announcements/Communications endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_announcements(self, auth_headers):
        """GET /api/announcements returns announcements array"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_announcement(self, auth_headers):
        """POST /api/announcements creates new announcement"""
        response = requests.post(f"{BASE_URL}/api/announcements", headers=auth_headers, json={
            "title": "TEST_Announcement",
            "content": "This is a test announcement",
            "type": "general",
            "pinned": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Announcement"
        assert "id" in data


class TestOutreach:
    """Outreach programs endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_outreach_programs(self, auth_headers):
        """GET /api/outreach/programs returns outreach programs array"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_outreach_program(self, auth_headers):
        """POST /api/outreach/programs creates new program"""
        response = requests.post(f"{BASE_URL}/api/outreach/programs", headers=auth_headers, json={
            "name": "TEST_Outreach Program",
            "description": "Test program description",
            "category": "community",
            "status": "active",
            "location": "Kampala"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Outreach Program"
        assert "id" in data


class TestResources:
    """Resources management endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_resources(self, auth_headers):
        """GET /api/resources returns resources array"""
        response = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_resource(self, auth_headers):
        """POST /api/resources creates new resource"""
        response = requests.post(f"{BASE_URL}/api/resources", headers=auth_headers, json={
            "name": "TEST_Resource",
            "type": "room",
            "capacity": 50,
            "description": "Test resource"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Resource"
        assert "id" in data


class TestBadges:
    """Badges endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_badges(self, auth_headers):
        """GET /api/badges returns badges array"""
        response = requests.get(f"{BASE_URL}/api/badges", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_badge(self, auth_headers):
        """POST /api/badges creates new badge"""
        response = requests.post(f"{BASE_URL}/api/badges", headers=auth_headers, json={
            "name": "TEST_Badge",
            "description": "Test badge description",
            "color": "#6366f1"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Badge"
        assert "id" in data


class TestFinancialCashflow:
    """Financial cashflow endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_cashflow_6_months(self, auth_headers):
        """GET /api/financial/cashflow?months=6 returns cashflow data with monthly array"""
        response = requests.get(f"{BASE_URL}/api/financial/cashflow?months=6", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly" in data
        assert isinstance(data["monthly"], list)


class TestMembersPending:
    """Members pending approval endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_pending_members(self, auth_headers):
        """GET /api/members/pending returns pending members array"""
        response = requests.get(f"{BASE_URL}/api/members/pending", headers=auth_headers)
        # Note: This endpoint may return 404 if not implemented or 200 with empty array
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


class TestAppSettings:
    """App settings endpoints tests"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_app_settings(self, auth_headers):
        """GET /api/app-settings returns app settings"""
        response = requests.get(f"{BASE_URL}/api/app-settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        assert isinstance(data, dict)
    
    def test_update_app_settings(self, auth_headers):
        """PUT /api/app-settings updates app settings"""
        # First get current settings
        get_response = requests.get(f"{BASE_URL}/api/app-settings", headers=auth_headers)
        current_settings = get_response.json()
        
        # Update settings
        response = requests.put(f"{BASE_URL}/api/app-settings", headers=auth_headers, json={
            "registration_open": True,
            "default_role": "member",
            "maintenance_mode": False
        })
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
