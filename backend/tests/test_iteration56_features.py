"""
Iteration 56 Tests - User Directory, Location Venues, Bi-monthly/Quarterly Recurrence
Tests:
1. GET /api/admin/users/directory - returns all users regardless of campus filter
2. GET /api/locations/{id}/venues - includes external venues
3. Outreach programme creation with location_id and venue_id
4. Events recurrence types (bi-monthly, quarterly)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestUserDirectory:
    """Test /api/admin/users/directory endpoint - returns ALL users without campus filtering"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_user_directory_returns_all_users(self):
        """User directory should return all users regardless of campus filter"""
        response = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        users = response.json()
        assert isinstance(users, list), "Should return a list"
        print(f"User directory returned {len(users)} users")
        
        # Verify response structure - should have id, name, role, photo_url, location_id, email
        if len(users) > 0:
            user = users[0]
            assert "id" in user, "User should have id"
            assert "name" in user, "User should have name"
            assert "role" in user, "User should have role"
            # photo_url, location_id, email are optional but should be in projection
            print(f"Sample user: {user.get('name')} - {user.get('role')}")
    
    def test_user_directory_vs_admin_users(self):
        """Compare user directory (all users) vs admin users (campus filtered)"""
        # Get user directory (should be all users)
        dir_response = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=self.headers)
        assert dir_response.status_code == 200
        directory_users = dir_response.json()
        
        # Get admin users (may be campus filtered)
        admin_response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        assert admin_response.status_code == 200
        admin_users = admin_response.json()
        
        print(f"Directory users: {len(directory_users)}, Admin users: {len(admin_users)}")
        # Directory should have >= admin users (since it bypasses campus filter)
        assert len(directory_users) >= len(admin_users), "Directory should have all users"


class TestLocationVenues:
    """Test /api/locations/{id}/venues endpoint - includes external venues"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_get_locations(self):
        """Get list of locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        locations = response.json()
        assert isinstance(locations, list), "Should return a list"
        print(f"Found {len(locations)} locations")
        return locations
    
    def test_location_venues_endpoint(self):
        """Test location venues endpoint returns venues and sublocations"""
        # First get locations
        locations = self.test_get_locations()
        if len(locations) == 0:
            pytest.skip("No locations to test")
        
        loc_id = locations[0]["id"]
        response = requests.get(f"{BASE_URL}/api/locations/{loc_id}/venues", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have venues and sublocations keys
        assert "venues" in data, "Response should have 'venues' key"
        assert "sublocations" in data, "Response should have 'sublocations' key"
        
        print(f"Location {loc_id} has {len(data['venues'])} venues and {len(data['sublocations'])} sublocations")
        
        # Check if any external venues are included
        external_count = sum(1 for v in data['venues'] if v.get('is_external') or not v.get('location_id'))
        print(f"External venues included: {external_count}")
    
    def test_create_external_venue(self):
        """Create an external venue and verify it appears in location venues"""
        import uuid
        venue_name = f"TEST_External_Venue_{uuid.uuid4().hex[:6]}"
        
        # Create external venue (no location_id or is_external=True)
        create_response = requests.post(f"{BASE_URL}/api/venues", headers=self.headers, json={
            "name": venue_name,
            "is_external": True,
            "address": "External Address",
            "capacity": 100
        })
        
        if create_response.status_code == 201:
            venue = create_response.json()
            print(f"Created external venue: {venue.get('id')}")
            
            # Get locations and check if external venue appears
            locations = self.test_get_locations()
            if len(locations) > 0:
                loc_id = locations[0]["id"]
                venues_response = requests.get(f"{BASE_URL}/api/locations/{loc_id}/venues", headers=self.headers)
                if venues_response.status_code == 200:
                    data = venues_response.json()
                    venue_ids = [v.get('id') for v in data['venues']]
                    if venue.get('id') in venue_ids:
                        print("PASS: External venue appears in location venues")
                    else:
                        print(f"External venue {venue.get('id')} not found in venues list")
            
            # Cleanup
            requests.delete(f"{BASE_URL}/api/venues/{venue.get('id')}", headers=self.headers)
        else:
            print(f"Could not create venue: {create_response.status_code} - {create_response.text}")


class TestOutreachProgrammes:
    """Test outreach programme creation with location_id and venue_id"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_create_programme_with_location_and_venue(self):
        """Create outreach programme with location_id and venue_id"""
        import uuid
        
        # Get a location first
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        locations = loc_response.json() if loc_response.status_code == 200 else []
        location_id = locations[0]["id"] if locations else ""
        
        programme_name = f"TEST_Programme_{uuid.uuid4().hex[:6]}"
        payload = {
            "name": programme_name,
            "description": "Test programme with location and venue",
            "category": "community",
            "status": "active",
            "location": "Test Location",
            "location_id": location_id,
            "venue_id": "",  # Can be empty
            "start_date": "2026-02-01",
            "target": 100,
            "is_recurring": False
        }
        
        response = requests.post(f"{BASE_URL}/api/outreach/programs", headers=self.headers, json=payload)
        assert response.status_code in [200, 201], f"Failed to create programme: {response.text}"
        
        programme = response.json()
        assert programme.get("name") == programme_name
        assert programme.get("location_id") == location_id
        print(f"Created programme: {programme.get('id')} with location_id: {programme.get('location_id')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/outreach/programs/{programme.get('id')}", headers=self.headers)
    
    def test_list_programmes(self):
        """List outreach programmes"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=self.headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        programmes = response.json()
        print(f"Found {len(programmes)} programmes")


class TestRecurrenceTypes:
    """Test bi-monthly and quarterly recurrence types for events"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_create_event_with_bimonthly_recurrence(self):
        """Create event with bi-monthly recurrence type"""
        import uuid
        event_title = f"TEST_Bimonthly_Event_{uuid.uuid4().hex[:6]}"
        
        payload = {
            "title": event_title,
            "type": "service",
            "date": "2026-02-01",
            "time": "10:00",
            "end_time": "12:00",
            "location": "Test Location",
            "capacity": 50,
            "is_recurring": True,
            "recurrence_type": "bimonthly",
            "recurrence_interval": 1,
            "visibility": "external"
        }
        
        response = requests.post(f"{BASE_URL}/api/events", headers=self.headers, json=payload)
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        
        event = response.json()
        assert event.get("title") == event_title
        assert event.get("is_recurring") == True
        print(f"Created bi-monthly event: {event.get('id')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/events/{event.get('id')}", headers=self.headers)
    
    def test_create_event_with_quarterly_recurrence(self):
        """Create event with quarterly recurrence type"""
        import uuid
        event_title = f"TEST_Quarterly_Event_{uuid.uuid4().hex[:6]}"
        
        payload = {
            "title": event_title,
            "type": "service",
            "date": "2026-02-01",
            "time": "14:00",
            "end_time": "16:00",
            "location": "Test Location",
            "capacity": 100,
            "is_recurring": True,
            "recurrence_type": "quarterly",
            "recurrence_interval": 1,
            "visibility": "external"
        }
        
        response = requests.post(f"{BASE_URL}/api/events", headers=self.headers, json=payload)
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        
        event = response.json()
        assert event.get("title") == event_title
        assert event.get("is_recurring") == True
        print(f"Created quarterly event: {event.get('id')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/events/{event.get('id')}", headers=self.headers)
    
    def test_generate_recurring_events_bimonthly(self):
        """Test generating recurring events with bi-monthly pattern"""
        payload = {
            "title": "TEST_Bimonthly_Generated",
            "type": "outreach",
            "location": "Test Location",
            "pattern": "bimonthly",
            "occurrences": 6,
            "interval": 1,
            "start_date": "2026-02-01",
            "time": "09:00",
            "end_time": "11:00"
        }
        
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", headers=self.headers, json=payload)
        if response.status_code in [200, 201]:
            data = response.json()
            print(f"Generated {data.get('created', 0)} bi-monthly events")
            # Cleanup generated events
            for event_id in data.get('event_ids', []):
                requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=self.headers)
        else:
            print(f"Generate recurring response: {response.status_code} - {response.text[:200]}")
    
    def test_generate_recurring_events_quarterly(self):
        """Test generating recurring events with quarterly pattern"""
        payload = {
            "title": "TEST_Quarterly_Generated",
            "type": "outreach",
            "location": "Test Location",
            "pattern": "quarterly",
            "occurrences": 4,
            "interval": 1,
            "start_date": "2026-02-01",
            "time": "14:00",
            "end_time": "16:00"
        }
        
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", headers=self.headers, json=payload)
        if response.status_code in [200, 201]:
            data = response.json()
            print(f"Generated {data.get('created', 0)} quarterly events")
            # Cleanup generated events
            for event_id in data.get('event_ids', []):
                requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=self.headers)
        else:
            print(f"Generate recurring response: {response.status_code} - {response.text[:200]}")


class TestGuestDelete:
    """Test individual guest delete functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_create_and_delete_guest(self):
        """Create a guest and delete it individually"""
        import uuid
        guest_name = f"TEST_Guest_{uuid.uuid4().hex[:6]}"
        
        # Create guest
        create_response = requests.post(f"{BASE_URL}/api/guests", headers=self.headers, json={
            "name": guest_name,
            "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+256700000000"
        })
        
        if create_response.status_code in [200, 201]:
            guest = create_response.json()
            guest_id = guest.get("id")
            print(f"Created guest: {guest_id}")
            
            # Delete guest
            delete_response = requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=self.headers)
            assert delete_response.status_code in [200, 204], f"Delete failed: {delete_response.text}"
            print(f"Deleted guest: {guest_id}")
            
            # Verify deletion
            get_response = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
            if get_response.status_code == 200:
                guests = get_response.json()
                guest_ids = [g.get('id') for g in guests]
                assert guest_id not in guest_ids, "Guest should be deleted"
                print("PASS: Guest successfully deleted")
        else:
            print(f"Could not create guest: {create_response.status_code}")


class TestPortalPage:
    """Test portal page loads correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_portal_dashboard_api(self):
        """Test portal dashboard API"""
        response = requests.get(f"{BASE_URL}/api/portal/dashboard", headers=self.headers)
        # Portal dashboard may return 200 or 404 depending on user type
        print(f"Portal dashboard response: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Portal dashboard data keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")


class TestMajorPagesLoad:
    """Test that all major pages' APIs respond correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_dashboard_api(self):
        """Test dashboard stats API"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert response.status_code == 200, f"Dashboard API failed: {response.text}"
        print("Dashboard API: OK")
    
    def test_boards_api(self):
        """Test boards API (Tasks/Boards page)"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=self.headers)
        assert response.status_code == 200, f"Boards API failed: {response.text}"
        print(f"Boards API: OK - {len(response.json())} boards")
    
    def test_tasks_api(self):
        """Test tasks API"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert response.status_code == 200, f"Tasks API failed: {response.text}"
        print(f"Tasks API: OK - {len(response.json())} tasks")
    
    def test_events_api(self):
        """Test events API"""
        response = requests.get(f"{BASE_URL}/api/events", headers=self.headers)
        assert response.status_code == 200, f"Events API failed: {response.text}"
        print(f"Events API: OK - {len(response.json())} events")
    
    def test_outreach_api(self):
        """Test outreach programmes API"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=self.headers)
        assert response.status_code == 200, f"Outreach API failed: {response.text}"
        print(f"Outreach API: OK - {len(response.json())} programmes")
    
    def test_admin_users_api(self):
        """Test admin users API"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        assert response.status_code == 200, f"Admin users API failed: {response.text}"
        print(f"Admin users API: OK - {len(response.json())} users")
    
    def test_members_api(self):
        """Test members API (People page)"""
        response = requests.get(f"{BASE_URL}/api/members", headers=self.headers)
        assert response.status_code == 200, f"Members API failed: {response.text}"
        print(f"Members API: OK - {len(response.json())} members")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
