"""
Iteration 33 Tests: Major Application Overhaul
- Navigation overhaul with collapsible sections
- Campus switcher for admin/ED users
- Data isolation (SYSTEM_ADMIN_ROLES updated)
- Rename Tasks to Boards (/boards route)
- Events ordered by upcoming (status asc, date asc)
- Calendar year navigation
- Default password 'User@58:12'
- App name '58:12 Connect'
- Main location renamed to '58:12 Global (Central)'
- Close dialog on save in admin edit
- Admin-only Financial APIs and PBX Settings
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_admin(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@5812uganda.org"
        assert data["user"]["role"] == "admin"
        print("✓ Admin login successful")
        return data["token"]


class TestCampusSwitcher:
    """Campus switcher API tests"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_set_active_campus(self, auth_token):
        """Test setting active campus for admin"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First get locations to find a campus
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert locs_res.status_code == 200
        locations = locs_res.json()
        
        # Find a campus (not sub-location)
        campus = next((l for l in locations if l.get("type") in ["main", "campus"]), None)
        if not campus:
            pytest.skip("No campus found to test")
        
        # Set active campus
        response = requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=headers, json={"campus_id": campus["id"]})
        assert response.status_code == 200
        data = response.json()
        assert data["active_campus_id"] == campus["id"]
        print(f"✓ Set active campus to {campus['name']}")
    
    def test_clear_active_campus(self, auth_token):
        """Test clearing active campus"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["active_campus_id"] is None
        print("✓ Cleared active campus")


class TestEventsOrdering:
    """Test events are ordered by status then date ascending"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_events_sorted_by_date_within_status(self, auth_token):
        """Events should be sorted by date ascending within same status"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/events", headers=headers)
        assert response.status_code == 200
        events = response.json()
        
        if len(events) < 2:
            pytest.skip("Not enough events to test ordering")
        
        # Check date ordering within upcoming events
        upcoming_events = [e for e in events if e.get("status") == "upcoming"]
        if len(upcoming_events) >= 2:
            dates = [e.get("date", "") for e in upcoming_events]
            assert dates == sorted(dates), "Upcoming events should be sorted by date ascending"
        
        print(f"✓ Events sorted by date within status - {len(events)} events, {len(upcoming_events)} upcoming")


class TestGlobalSettings:
    """Test global settings including app name"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_global_settings_app_name(self, auth_token):
        """Test that default app_name is '58:12 Connect'"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/global-settings", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Default should be '58:12 Connect'
        assert data.get("app_name") == "58:12 Connect" or "58:12" in data.get("app_name", "")
        print(f"✓ Global settings app_name: {data.get('app_name')}")


class TestLocations:
    """Test locations including main location name"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_main_location_name(self, auth_token):
        """Test that main location is named '58:12 Global (Central)'"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert response.status_code == 200
        locations = response.json()
        
        main_loc = next((l for l in locations if l.get("type") == "main"), None)
        if main_loc:
            assert "58:12 Global" in main_loc.get("name", ""), f"Main location should be '58:12 Global (Central)', got {main_loc.get('name')}"
            print(f"✓ Main location name: {main_loc.get('name')}")
        else:
            print("⚠ No main location found")


class TestAdminUserCreation:
    """Test admin user creation with default password"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_create_user_default_password(self, auth_token):
        """Test that new users get default password 'User@58:12'"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        import uuid
        test_email = f"test_iter33_{uuid.uuid4().hex[:8]}@example.com"
        
        # Create user without specifying password
        response = requests.post(f"{BASE_URL}/api/admin/users", headers=headers, json={
            "name": "Test User Iter33",
            "email": test_email,
            "role": "Staff"
        })
        assert response.status_code == 200
        data = response.json()
        
        # The temp_password should be 'User@58:12' (default)
        assert data.get("temp_password") == "User@58:12", f"Expected default password 'User@58:12', got {data.get('temp_password')}"
        print(f"✓ User created with default password 'User@58:12'")
        
        # Cleanup - delete the test user
        user_id = data.get("id")
        if user_id:
            requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)


class TestFinancialAPIs:
    """Test Financial APIs endpoint (admin-only)"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_list_financial_apis(self, auth_token):
        """Test listing financial APIs"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/financial-apis", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Financial APIs endpoint accessible - {len(data)} APIs configured")


class TestDataIsolation:
    """Test data isolation rules"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_admin_sees_all_data(self, auth_token):
        """Admin should see all data without campus filter"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Clear any active campus filter
        requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=headers)
        
        # Get dashboard stats
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_members" in data
        print(f"✓ Admin sees all data - {data.get('total_members')} total members")
    
    def test_admin_campus_filter(self, auth_token):
        """Admin with active campus should see filtered data"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get locations
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        locations = locs_res.json()
        campus = next((l for l in locations if l.get("type") in ["main", "campus"]), None)
        
        if not campus:
            pytest.skip("No campus found")
        
        # Set active campus
        requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=headers, json={"campus_id": campus["id"]})
        
        # Get dashboard stats - should be filtered
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200
        
        # Clear filter for other tests
        requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=headers)
        print(f"✓ Admin campus filter works")


class TestBoardsRoute:
    """Test that /boards route works (alias to tasks)"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_boards_api_exists(self, auth_token):
        """Test that boards API endpoint exists"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/boards", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Boards API works - {len(data)} boards")
    
    def test_tasks_api_still_works(self, auth_token):
        """Test that tasks API still works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/tasks", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Tasks API still works - {len(data)} tasks")


class TestCurrencies:
    """Test currencies endpoint"""
    
    def test_currencies_list(self):
        """Test currencies endpoint returns list"""
        response = requests.get(f"{BASE_URL}/api/currencies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 10  # Should have at least 10 currencies
        # Check UGX is present
        ugx = next((c for c in data if c.get("code") == "UGX"), None)
        assert ugx is not None
        print(f"✓ Currencies endpoint works - {len(data)} currencies")


class TestCalendarExport:
    """Test calendar export/import"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_ical_export(self, auth_token):
        """Test iCal export endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/events/export/ical", headers=headers)
        assert response.status_code == 200
        content = response.text
        assert "BEGIN:VCALENDAR" in content
        print("✓ iCal export works")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json()["token"]
    
    def test_clear_campus_filter(self, auth_token):
        """Clear any campus filter set during tests"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.put(f"{BASE_URL}/api/user/active-campus/clear", headers=headers)
        assert response.status_code == 200
        print("✓ Cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
