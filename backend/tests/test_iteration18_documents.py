"""
Iteration 18 Tests: Document upload with user_id fallback, Campus rename, Calendar enhancements
Tests:
1. Document upload with user_id (not just member_id)
2. Document listing with user_id
3. Document request with user_id
4. Outreach sessions API for calendar
5. Events API for calendar
6. Locations API - Campus type handling
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    def test_login_success(self, auth_token):
        """Test admin login works"""
        assert auth_token is not None
        assert len(auth_token) > 10
        print(f"PASS: Admin login successful, token length: {len(auth_token)}")


class TestDocumentUploadWithUserId:
    """Test document upload with user_id fallback (bug fix verification)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_admin_users(self, headers):
        """Get admin users to find a user_id for testing"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert response.status_code == 200, f"Failed to get users: {response.text}"
        users = response.json()
        assert len(users) > 0, "No users found"
        print(f"PASS: Found {len(users)} users")
        return users
    
    def test_document_upload_with_user_id(self, headers):
        """Test document upload using user_id instead of member_id"""
        # First get a user_id
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        
        # Find a user that has a member profile
        user_with_profile = None
        for user in users:
            if user.get("has_member_profile"):
                user_with_profile = user
                break
        
        if not user_with_profile:
            # Use any user
            user_with_profile = users[0]
        
        user_id = user_with_profile["id"]
        print(f"Testing document upload with user_id: {user_id}")
        
        # Create a test file
        files = {
            'file': ('test_doc.txt', b'Test document content', 'text/plain')
        }
        data = {
            'doc_type': 'other',
            'label': 'Test Document'
        }
        
        response = requests.post(
            f"{BASE_URL}/api/members/{user_id}/documents",
            headers=headers,
            files=files,
            data=data
        )
        
        # Should succeed (200 or 201) or fail with validation error (400), not 404 "Member not found"
        if response.status_code == 400:
            # Check if it's a file type validation error (expected for .txt)
            error_detail = response.json().get("detail", "")
            assert "Member not found" not in error_detail, f"Bug not fixed: {error_detail}"
            print(f"PASS: Document upload with user_id - validation error (expected for .txt): {error_detail}")
        else:
            assert response.status_code in [200, 201], f"Unexpected status: {response.status_code}, {response.text}"
            print(f"PASS: Document upload with user_id succeeded")
    
    def test_document_list_with_user_id(self, headers):
        """Test document listing using user_id"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        user_id = users[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/members/{user_id}/documents",
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to list documents: {response.text}"
        docs = response.json()
        assert isinstance(docs, list), "Response should be a list"
        print(f"PASS: Document listing with user_id returned {len(docs)} documents")
    
    def test_document_request_with_user_id(self, headers):
        """Test document request using user_id"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        user_id = users[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/document-requests",
            headers=headers,
            json={
                "member_id": user_id,  # Using user_id instead of member_id
                "doc_type": "national_id",
                "message": "Please upload your ID"
            }
        )
        
        # Should succeed or fail with something other than "Member not found"
        if response.status_code == 404:
            error_detail = response.json().get("detail", "")
            assert "Member not found" not in error_detail, f"Bug not fixed: {error_detail}"
        else:
            assert response.status_code in [200, 201], f"Unexpected status: {response.status_code}, {response.text}"
            data = response.json()
            assert "id" in data, "Response should have id"
            print(f"PASS: Document request with user_id created: {data.get('id')}")


class TestCalendarFeatures:
    """Test calendar-related APIs for outreach and events"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_events_list(self, headers):
        """Test events API returns events for calendar"""
        response = requests.get(f"{BASE_URL}/api/events", headers=headers)
        assert response.status_code == 200, f"Failed to get events: {response.text}"
        events = response.json()
        assert isinstance(events, list), "Events should be a list"
        print(f"PASS: Events API returned {len(events)} events")
        
        # Check event structure
        if events:
            event = events[0]
            assert "id" in event, "Event should have id"
            assert "title" in event, "Event should have title"
            assert "date" in event, "Event should have date"
            print(f"PASS: Event structure verified - {event.get('title')}")
    
    def test_outreach_sessions_list(self, headers):
        """Test outreach sessions API for calendar integration"""
        response = requests.get(f"{BASE_URL}/api/outreach/sessions", headers=headers)
        assert response.status_code == 200, f"Failed to get outreach sessions: {response.text}"
        sessions = response.json()
        assert isinstance(sessions, list), "Sessions should be a list"
        print(f"PASS: Outreach sessions API returned {len(sessions)} sessions")
        
        # Check session structure if any exist
        if sessions:
            session = sessions[0]
            assert "id" in session, "Session should have id"
            print(f"PASS: Session structure verified")
    
    def test_outreach_programs_list(self, headers):
        """Test outreach programs API"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=headers)
        assert response.status_code == 200, f"Failed to get outreach programs: {response.text}"
        programs = response.json()
        assert isinstance(programs, list), "Programs should be a list"
        print(f"PASS: Outreach programs API returned {len(programs)} programs")
    
    def test_create_event_with_recurrence(self, headers):
        """Test creating event with recurrence pattern (for recurring events feature)"""
        event_data = {
            "title": "TEST_Recurring_Event",
            "type": "service",
            "date": "2026-04-15",
            "time": "10:00",
            "location": "Test Location",
            "capacity": 100,
            "status": "upcoming",
            "is_recurring": True,
            "recurrence_pattern": "nth_week_2_day_0_interval_1"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/events",
            headers=headers,
            json=event_data
        )
        
        assert response.status_code in [200, 201], f"Failed to create event: {response.text}"
        event = response.json()
        assert event.get("title") == "TEST_Recurring_Event"
        assert event.get("is_recurring") == True
        print(f"PASS: Created recurring event with pattern: {event.get('recurrence_pattern')}")
        
        # Cleanup
        event_id = event.get("id")
        if event_id:
            requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=headers)


class TestLocationsAndCampus:
    """Test locations API and Campus type handling"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_locations_list(self, headers):
        """Test locations API returns locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert response.status_code == 200, f"Failed to get locations: {response.text}"
        locations = response.json()
        assert isinstance(locations, list), "Locations should be a list"
        print(f"PASS: Locations API returned {len(locations)} locations")
        
        # Check for campus type locations
        campus_locations = [l for l in locations if l.get("type") in ["campus", "compass"]]
        print(f"PASS: Found {len(campus_locations)} campus/compass type locations")
        
        return locations
    
    def test_create_campus_location(self, headers):
        """Test creating a campus type location"""
        location_data = {
            "name": "TEST_Campus_Location",
            "code": "TCL",
            "type": "campus",  # Should be 'campus' not 'compass'
            "country": "Uganda",
            "currency": "UGX",
            "timezone": "Africa/Kampala"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/locations",
            headers=headers,
            json=location_data
        )
        
        assert response.status_code in [200, 201], f"Failed to create location: {response.text}"
        location = response.json()
        assert location.get("name") == "TEST_Campus_Location"
        assert location.get("type") == "campus"
        print(f"PASS: Created campus location: {location.get('id')}")
        
        # Cleanup
        loc_id = location.get("id")
        if loc_id:
            requests.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=headers)


class TestAdminProfileLookup:
    """Test admin profile lookup with user_id fallback"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_admin_user_profile_lookup(self, headers):
        """Test admin can get user profile with user_id"""
        # Get users first
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        user_id = users[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/admin/users/{user_id}/profile",
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed to get profile: {response.text}"
        profile = response.json()
        assert "id" in profile or "email" in profile, "Profile should have id or email"
        print(f"PASS: Admin profile lookup with user_id succeeded")


class TestIDTypes:
    """Test document ID types endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
        })
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_id_types_list(self, headers):
        """Test ID types endpoint returns valid types"""
        response = requests.get(f"{BASE_URL}/api/documents/id-types", headers=headers)
        assert response.status_code == 200, f"Failed to get ID types: {response.text}"
        id_types = response.json()
        assert isinstance(id_types, list), "ID types should be a list"
        assert "national_id" in id_types, "Should include national_id"
        assert "passport" in id_types, "Should include passport"
        print(f"PASS: ID types API returned {len(id_types)} types: {id_types}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
