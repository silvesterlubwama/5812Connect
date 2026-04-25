"""
Iteration 60 - Template Download Endpoints Tests
Tests for GET /api/import/template/{children|staff|guests} endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTemplateDownloads:
    """Test CSV template download endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for authenticated requests"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_children_template_download(self):
        """GET /api/import/template/children returns CSV with correct headers"""
        response = requests.get(f"{BASE_URL}/api/import/template/children", headers=self.headers)
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Content-Type assertion
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected text/csv content type"
        
        # Content-Disposition assertion
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, "Expected attachment disposition"
        assert "children" in content_disp.lower(), "Expected children in filename"
        
        # CSV content assertions
        content = response.text
        assert "name" in content.lower(), "Expected 'name' column in CSV"
        assert "date_of_birth" in content.lower(), "Expected 'date_of_birth' column in CSV"
        assert "gender" in content.lower(), "Expected 'gender' column in CSV"
        assert "campus" in content.lower() or "location" in content.lower(), "Expected campus/location column in CSV"
        assert "father" in content.lower(), "Expected father fields in CSV"
        assert "mother" in content.lower(), "Expected mother fields in CSV"
        
        print(f"Children template CSV headers: {content.split(chr(10))[0]}")
    
    def test_staff_template_download(self):
        """GET /api/import/template/staff returns CSV with correct headers"""
        response = requests.get(f"{BASE_URL}/api/import/template/staff", headers=self.headers)
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Content-Type assertion
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected text/csv content type"
        
        # Content-Disposition assertion
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, "Expected attachment disposition"
        assert "staff" in content_disp.lower(), "Expected staff in filename"
        
        # CSV content assertions
        content = response.text
        assert "name" in content.lower(), "Expected 'name' column in CSV"
        assert "email" in content.lower(), "Expected 'email' column in CSV"
        assert "phone" in content.lower(), "Expected 'phone' column in CSV"
        assert "role" in content.lower(), "Expected 'role' column in CSV"
        assert "department" in content.lower(), "Expected 'department' column in CSV"
        
        print(f"Staff template CSV headers: {content.split(chr(10))[0]}")
    
    def test_guests_template_download(self):
        """GET /api/import/template/guests returns CSV with correct headers"""
        response = requests.get(f"{BASE_URL}/api/import/template/guests", headers=self.headers)
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Content-Type assertion
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected text/csv content type"
        
        # Content-Disposition assertion
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, "Expected attachment disposition"
        assert "guests" in content_disp.lower(), "Expected guests in filename"
        
        # CSV content assertions
        content = response.text
        assert "name" in content.lower(), "Expected 'name' column in CSV"
        assert "phone" in content.lower(), "Expected 'phone' column in CSV"
        assert "email" in content.lower(), "Expected 'email' column in CSV"
        assert "is_parent" in content.lower(), "Expected 'is_parent' column in CSV"
        
        print(f"Guests template CSV headers: {content.split(chr(10))[0]}")
    
    def test_template_requires_auth(self):
        """Template endpoints should require authentication"""
        # Test without auth header
        response = requests.get(f"{BASE_URL}/api/import/template/children")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        response = requests.get(f"{BASE_URL}/api/import/template/staff")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        response = requests.get(f"{BASE_URL}/api/import/template/guests")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"


class TestHealthAndBasicEndpoints:
    """Basic health and endpoint tests"""
    
    def test_api_health(self):
        """API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
    
    def test_login_success(self):
        """Login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Expected token in response"
        assert "user" in data, "Expected user in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
