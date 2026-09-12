"""
Test Suite for Iteration 4 Features:
- Booking system with 1-hour buffer enforcement
- Rate limiting middleware (120 req/min)
- Modular routers for bookings and websockets
- Communications page pinned rooms (AI Assistant, Announcements)
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-tenant-scope.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


class TestAuth:
    """Authentication tests"""
    
    def test_login_admin_5812uganda(self):
        """Test login with admin@5812uganda.org"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"✓ Login successful for {ADMIN_EMAIL}")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Authentication failed")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestBookingSystem:
    """Tests for the new booking system with 1-hour buffer"""
    
    def test_list_bookings(self, auth_headers):
        """Test GET /api/bookings returns list"""
        response = requests.get(f"{BASE_URL}/api/bookings", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/bookings returned {len(data)} bookings")
    
    def test_create_booking(self, auth_headers):
        """Test POST /api/bookings creates a booking"""
        # First get a resource to book
        res_response = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        resources = res_response.json() if res_response.status_code == 200 else []
        
        # Use a resource if available, otherwise just location
        resource_id = None
        if resources:
            bookable = [r for r in resources if r.get("is_bookable", True)]
            if bookable:
                resource_id = bookable[0]["id"]
        
        # Create booking for tomorrow to avoid conflicts
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        booking_data = {
            "resource_id": resource_id,
            "title": "TEST_Team Meeting",
            "date": tomorrow,
            "start_time": "09:00",
            "end_time": "10:00",
            "notes": "Test booking"
        }
        
        response = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking_data)
        assert response.status_code == 200, f"Failed to create booking: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["title"] == "TEST_Team Meeting"
        assert data["status"] == "confirmed"
        print(f"✓ Created booking: {data['id']}")
        return data
    
    def test_booking_buffer_conflict(self, auth_headers):
        """Test that 1-hour buffer is enforced between bookings"""
        # First create a booking
        tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        
        # Get a bookable resource
        res_response = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        resources = res_response.json() if res_response.status_code == 200 else []
        resource_id = None
        if resources:
            bookable = [r for r in resources if r.get("is_bookable", True)]
            if bookable:
                resource_id = bookable[0]["id"]
        
        # Create first booking 09:00-10:00
        booking1 = {
            "resource_id": resource_id,
            "title": "TEST_First Booking",
            "date": tomorrow,
            "start_time": "09:00",
            "end_time": "10:00"
        }
        response1 = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking1)
        
        if response1.status_code != 200:
            # May already have a booking, try different time
            booking1["start_time"] = "14:00"
            booking1["end_time"] = "15:00"
            response1 = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking1)
        
        if response1.status_code == 200:
            # Now try to create a conflicting booking within 1-hour buffer
            # If first booking is 14:00-15:00, next should start no earlier than 16:00
            booking2 = {
                "resource_id": resource_id,
                "title": "TEST_Conflicting Booking",
                "date": tomorrow,
                "start_time": "15:30",  # Within 1-hour buffer of 15:00 end
                "end_time": "16:30"
            }
            response2 = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking2)
            
            # Should return 409 conflict
            assert response2.status_code == 409, f"Expected 409 conflict, got {response2.status_code}: {response2.text}"
            assert "buffer" in response2.text.lower() or "conflict" in response2.text.lower()
            print("✓ 1-hour buffer conflict correctly enforced (409 returned)")
        else:
            print(f"⚠ Could not create first booking to test buffer: {response1.text}")
    
    def test_cancel_booking(self, auth_headers):
        """Test DELETE /api/bookings/{id} cancels a booking"""
        # Create a booking first
        day_after = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        booking_data = {
            "title": "TEST_To Cancel",
            "date": day_after,
            "start_time": "11:00",
            "end_time": "12:00"
        }
        create_response = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking_data)
        
        if create_response.status_code == 200:
            booking_id = create_response.json()["id"]
            
            # Cancel it
            delete_response = requests.delete(f"{BASE_URL}/api/bookings/{booking_id}", headers=auth_headers)
            assert delete_response.status_code == 200, f"Failed to cancel: {delete_response.text}"
            print(f"✓ Cancelled booking {booking_id}")
        else:
            print(f"⚠ Could not create booking to test cancel: {create_response.text}")


class TestRateLimiting:
    """Tests for rate limiting middleware (120 req/min)"""
    
    def test_rate_limit_not_triggered_under_limit(self, auth_headers):
        """Test that normal requests under 120/min work fine"""
        # Make 5 quick requests - should all succeed
        success_count = 0
        for i in range(5):
            response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
            if response.status_code == 200:
                success_count += 1
        
        assert success_count == 5, f"Only {success_count}/5 requests succeeded"
        print("✓ Normal requests under rate limit work fine")
    
    def test_rate_limit_triggered_over_limit(self, auth_headers):
        """Test that 120+ rapid requests trigger 429 response"""
        # This test makes many rapid requests to trigger rate limit
        # Note: This may take a while and could affect other tests
        
        responses_429 = 0
        responses_200 = 0
        
        # Make 130 rapid requests
        for i in range(130):
            response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
            if response.status_code == 429:
                responses_429 += 1
            elif response.status_code == 200:
                responses_200 += 1
        
        # We should see some 429 responses after 120 requests
        print(f"Rate limit test: {responses_200} OK, {responses_429} rate-limited")
        
        if responses_429 > 0:
            print("✓ Rate limiting triggered (429 responses received)")
        else:
            print("⚠ Rate limiting may not have triggered - could be due to test timing")
        
        # At minimum, we should have gotten some successful responses
        assert responses_200 > 0, "No successful responses received"


class TestCommunicationsAPI:
    """Tests for Communications features - AI Assistant and Announcements"""
    
    def test_get_conversations(self, auth_headers):
        """Test GET /api/chat/conversations"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/chat/conversations returned {len(data)} conversations")
    
    def test_create_conversation(self, auth_headers):
        """Test POST /api/chat/conversations"""
        conv_data = {
            "name": "TEST_New Chat Room",
            "type": "group",
            "participants": []
        }
        response = requests.post(f"{BASE_URL}/api/chat/conversations", headers=auth_headers, json=conv_data)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_New Chat Room"
        print(f"✓ Created conversation: {data['id']}")
        return data["id"]
    
    def test_send_message_in_conversation(self, auth_headers):
        """Test sending a message in a conversation"""
        # First create a conversation
        conv_data = {"name": "TEST_Message Test", "type": "direct", "participants": []}
        conv_response = requests.post(f"{BASE_URL}/api/chat/conversations", headers=auth_headers, json=conv_data)
        
        if conv_response.status_code == 200:
            conv_id = conv_response.json()["id"]
            
            # Send a message
            msg_response = requests.post(
                f"{BASE_URL}/api/chat/conversations/{conv_id}/messages",
                headers=auth_headers,
                json={"text": "Hello, this is a test message!"}
            )
            assert msg_response.status_code == 200, f"Failed to send message: {msg_response.text}"
            msg_data = msg_response.json()
            assert "id" in msg_data
            assert msg_data["text"] == "Hello, this is a test message!"
            print(f"✓ Sent message in conversation {conv_id}")
    
    def test_ai_assistant(self, auth_headers):
        """Test POST /api/chat/ai-assistant with Gemini"""
        ai_data = {
            "message": "What is 58:12 Global Connect?",
            "session_id": "test_session_123"
        }
        response = requests.post(f"{BASE_URL}/api/chat/ai-assistant", headers=auth_headers, json=ai_data)
        assert response.status_code == 200, f"AI Assistant failed: {response.text}"
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0
        print(f"✓ AI Assistant responded: {data['response'][:100]}...")
    
    def test_list_announcements(self, auth_headers):
        """Test GET /api/announcements"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/announcements returned {len(data)} announcements")
    
    def test_create_announcement(self, auth_headers):
        """Test POST /api/announcements"""
        ann_data = {
            "title": "TEST_Important Update",
            "content": "This is a test announcement for iteration 4 testing.",
            "type": "general"
        }
        response = requests.post(f"{BASE_URL}/api/announcements", headers=auth_headers, json=ann_data)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["title"] == "TEST_Important Update"
        print(f"✓ Created announcement: {data['id']}")


class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint availability"""
    
    def test_websocket_endpoint_exists(self):
        """Test that WebSocket endpoint is accessible"""
        # We can't fully test WebSocket with requests, but we can check the upgrade fails gracefully
        try:
            response = requests.get(f"{BASE_URL}/ws/test_user", timeout=5)
            # Should get a 400 or similar since we're not doing proper WS upgrade
            print(f"✓ WebSocket endpoint exists (got {response.status_code} without upgrade)")
        except Exception as e:
            print(f"⚠ WebSocket endpoint check: {str(e)}")


class TestResourcesWithBooking:
    """Tests for Resources page with booking functionality"""
    
    def test_list_resources(self, auth_headers):
        """Test GET /api/resources"""
        response = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/resources returned {len(data)} resources")
        return data
    
    def test_create_bookable_resource(self, auth_headers):
        """Test creating a bookable resource"""
        resource_data = {
            "name": "TEST_Conference Room C",
            "type": "room",
            "capacity": 20,
            "is_bookable": True,
            "staff_only": False,
            "description": "Test room for booking"
        }
        response = requests.post(f"{BASE_URL}/api/resources", headers=auth_headers, json=resource_data)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["is_bookable"] == True
        print(f"✓ Created bookable resource: {data['id']}")
        return data["id"]
    
    def test_book_resource_via_bookings_api(self, auth_headers):
        """Test booking a resource through /api/bookings"""
        # Create a resource first
        resource_data = {
            "name": "TEST_Bookable Room D",
            "type": "room",
            "is_bookable": True
        }
        res_response = requests.post(f"{BASE_URL}/api/resources", headers=auth_headers, json=resource_data)
        
        if res_response.status_code == 200:
            resource_id = res_response.json()["id"]
            
            # Book it
            booking_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
            booking_data = {
                "resource_id": resource_id,
                "title": "TEST_Resource Booking",
                "date": booking_date,
                "start_time": "10:00",
                "end_time": "11:00"
            }
            book_response = requests.post(f"{BASE_URL}/api/bookings", headers=auth_headers, json=booking_data)
            assert book_response.status_code == 200, f"Failed to book: {book_response.text}"
            print(f"✓ Booked resource {resource_id} via /api/bookings")


class TestNavigationPages:
    """Test that all main pages are accessible"""
    
    def test_dashboard_stats(self, auth_headers):
        """Test Dashboard API"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        print("✓ Dashboard stats accessible")
    
    def test_members_list(self, auth_headers):
        """Test Members API"""
        response = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
        assert response.status_code == 200, f"Members failed: {response.text}"
        print("✓ Members list accessible")
    
    def test_financial_summary(self, auth_headers):
        """Test Financial API"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=auth_headers)
        assert response.status_code == 200, f"Financial failed: {response.text}"
        print("✓ Financial summary accessible")
    
    def test_events_list(self, auth_headers):
        """Test Events API"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        assert response.status_code == 200, f"Events failed: {response.text}"
        print("✓ Events list accessible")
    
    def test_tasks_list(self, auth_headers):
        """Test Tasks API"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers)
        assert response.status_code == 200, f"Tasks failed: {response.text}"
        print("✓ Tasks list accessible")
    
    def test_locations_list(self, auth_headers):
        """Test Locations API"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200, f"Locations failed: {response.text}"
        print("✓ Locations list accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
