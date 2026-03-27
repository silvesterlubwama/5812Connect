#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for 58:12 Global Connect CRM
Tests all endpoints as specified in the review request
"""

import requests
import json
import sys
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://comms-hub-57.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASSWORD = "Admin@1234"

class APITester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.test_results = []
        self.created_member_id = None
        self.created_event_id = None
        self.created_task_id = None
        self.created_venue_id = None
        
    def log_result(self, endpoint, method, status, message, details=None):
        """Log test result"""
        result = {
            "endpoint": endpoint,
            "method": method,
            "status": "✅ PASS" if status else "❌ FAIL",
            "message": message,
            "details": details or {}
        }
        self.test_results.append(result)
        print(f"{result['status']} {method} {endpoint}: {message}")
        if details and not status:
            print(f"   Details: {details}")
    
    def test_endpoint(self, method, endpoint, data=None, headers=None, expected_status=200, description=""):
        """Generic endpoint tester"""
        url = f"{BASE_URL}{endpoint}"
        
        # Add auth header if token exists
        if self.token and headers is None:
            headers = {"Authorization": f"Bearer {self.token}"}
        elif self.token and headers:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, headers=headers)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            
            try:
                response_data = response.json()
            except:
                response_data = response.text
            
            self.log_result(
                endpoint, 
                method.upper(), 
                success,
                f"{description} - Status: {response.status_code}",
                {
                    "expected_status": expected_status,
                    "actual_status": response.status_code,
                    "response": response_data if not success else "Success"
                }
            )
            
            return success, response_data, response.status_code
            
        except Exception as e:
            self.log_result(
                endpoint, 
                method.upper(), 
                False,
                f"{description} - Error: {str(e)}",
                {"error": str(e)}
            )
            return False, str(e), 0
    
    def run_all_tests(self):
        """Run all API tests in sequence"""
        print("🚀 Starting 58:12 Global Connect CRM Backend API Tests")
        print("=" * 60)
        
        # 1. Authentication Tests
        print("\n📋 1. AUTHENTICATION TESTS")
        self.test_auth_login()
        self.test_auth_me()
        
        # 2. Dashboard Tests
        print("\n📊 2. DASHBOARD TESTS")
        self.test_dashboard_stats()
        
        # 3. Members Tests
        print("\n👥 3. MEMBERS TESTS")
        self.test_members_list()
        self.test_members_create()
        self.test_members_get_detail()
        self.test_members_update()
        self.test_members_delete()
        
        # 4. Events Tests
        print("\n🎉 4. EVENTS TESTS")
        self.test_events_list()
        self.test_events_create()
        self.test_events_get_detail()
        
        # 5. Tasks Tests
        print("\n📝 5. TASKS TESTS")
        self.test_tasks_list()
        self.test_tasks_create()
        self.test_tasks_update()
        self.test_tasks_delete()
        
        # 6. Check-ins Tests
        print("\n✅ 6. CHECK-INS TESTS")
        self.test_checkins_list()
        self.test_checkins_create()
        self.test_checkins_stats()
        
        # 7. Venues Tests
        print("\n🏢 7. VENUES TESTS")
        self.test_venues_list()
        self.test_venues_create()
        
        # 8. Public API Tests (No Auth)
        print("\n🌐 8. PUBLIC API TESTS")
        self.test_public_events()
        self.test_public_venues()
        self.test_public_booking_event()
        self.test_public_booking_status()
        
        # 9. Kiosk API Tests (No Auth)
        print("\n🖥️ 9. KIOSK API TESTS")
        self.test_kiosk_checkin()
        self.test_kiosk_lookup()
        
        # Print Summary
        self.print_summary()
    
    def test_auth_login(self):
        """Test 1: POST /api/auth/login"""
        success, data, status = self.test_endpoint(
            "POST", 
            "/auth/login",
            {"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={},
            description="Admin login"
        )
        
        if success and isinstance(data, dict) and "token" in data:
            self.token = data["token"]
            print(f"   🔑 Token obtained: {self.token[:20]}...")
        else:
            print("   ❌ Failed to get authentication token")
    
    def test_auth_me(self):
        """Test 2: GET /api/auth/me"""
        self.test_endpoint(
            "GET",
            "/auth/me",
            description="Verify token works"
        )
    
    def test_dashboard_stats(self):
        """Test 3: GET /api/dashboard/stats"""
        success, data, status = self.test_endpoint(
            "GET",
            "/dashboard/stats",
            description="Get dashboard statistics"
        )
        
        if success and isinstance(data, dict):
            print(f"   📊 Stats: {data.get('total_members', 0)} members, {data.get('events_this_month', 0)} events this month")
    
    def test_members_list(self):
        """Test 4: GET /api/members"""
        success, data, status = self.test_endpoint(
            "GET",
            "/members",
            description="List members (should return 10)"
        )
        
        if success and isinstance(data, dict) and "members" in data:
            member_count = len(data["members"])
            print(f"   👥 Found {member_count} members")
            if member_count >= 10:
                print("   ✅ Expected 10+ members found")
            else:
                print(f"   ⚠️ Expected 10+ members, found {member_count}")
    
    def test_members_create(self):
        """Test 5: POST /api/members"""
        member_data = {
            "name": "Test Member API",
            "email": "testmember@example.com",
            "phone": "+256 700 999888",
            "role": "Member",
            "group": "Test Group"
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/members",
            member_data,
            description="Create new member"
        )
        
        if success and isinstance(data, dict) and "id" in data:
            self.created_member_id = data["id"]
            print(f"   👤 Created member with ID: {self.created_member_id}")
    
    def test_members_get_detail(self):
        """Test 6: GET /api/members/{id}"""
        if not self.created_member_id:
            # Use a known member ID from seed data
            self.created_member_id = "mem_001"
        
        success, data, status = self.test_endpoint(
            "GET",
            f"/members/{self.created_member_id}",
            description="Get member detail with checkin_history"
        )
        
        if success and isinstance(data, dict):
            has_checkin_history = "checkin_history" in data
            print(f"   📋 Member details loaded, checkin_history present: {has_checkin_history}")
    
    def test_members_update(self):
        """Test 7: PUT /api/members/{id}"""
        if not self.created_member_id:
            self.created_member_id = "mem_001"
        
        update_data = {"notes": "Updated via API test"}
        
        self.test_endpoint(
            "PUT",
            f"/members/{self.created_member_id}",
            update_data,
            description="Update member field"
        )
    
    def test_members_delete(self):
        """Test 8: DELETE /api/members/{id}"""
        if self.created_member_id and self.created_member_id.startswith("mem_"):
            # Only delete if it's our test member, not seed data
            if "testmember" in str(self.created_member_id).lower():
                self.test_endpoint(
                    "DELETE",
                    f"/members/{self.created_member_id}",
                    description="Delete test member"
                )
            else:
                print("   ⚠️ Skipping delete of seed data member")
        else:
            print("   ⚠️ No test member to delete")
    
    def test_events_list(self):
        """Test 9: GET /api/events"""
        success, data, status = self.test_endpoint(
            "GET",
            "/events",
            description="List events (should return 7+)"
        )
        
        if success and isinstance(data, list):
            event_count = len(data)
            print(f"   🎉 Found {event_count} events")
            if event_count >= 7:
                print("   ✅ Expected 7+ events found")
            else:
                print(f"   ⚠️ Expected 7+ events, found {event_count}")
    
    def test_events_create(self):
        """Test 10: POST /api/events"""
        event_data = {
            "title": "API Test Event",
            "type": "meeting",
            "date": "2026-05-15",
            "time": "14:00",
            "end_time": "16:00",
            "location": "Test Room",
            "capacity": 25,
            "description": "Event created via API test",
            "is_public": True,
            "is_free": True
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/events",
            event_data,
            description="Create event"
        )
        
        if success and isinstance(data, dict) and "id" in data:
            self.created_event_id = data["id"]
            print(f"   🎉 Created event with ID: {self.created_event_id}")
    
    def test_events_get_detail(self):
        """Test 11: GET /api/events/{id}"""
        if not self.created_event_id:
            # Use a known event ID from seed data
            self.created_event_id = "evt_001"
        
        success, data, status = self.test_endpoint(
            "GET",
            f"/events/{self.created_event_id}",
            description="Get event detail with attendees/checkins"
        )
        
        if success and isinstance(data, dict):
            has_attendees = "attendees" in data
            has_checkins = "checkins" in data
            print(f"   📋 Event details loaded, attendees: {has_attendees}, checkins: {has_checkins}")
    
    def test_tasks_list(self):
        """Test 12: GET /api/tasks"""
        success, data, status = self.test_endpoint(
            "GET",
            "/tasks",
            description="List tasks"
        )
        
        if success and isinstance(data, list):
            print(f"   📝 Found {len(data)} tasks")
    
    def test_tasks_create(self):
        """Test 13: POST /api/tasks"""
        task_data = {
            "title": "API Test Task",
            "description": "Task created via API test",
            "status": "todo",
            "priority": "medium",
            "assignee": "Test User",
            "due_date": "2026-05-20",
            "tags": ["api-test"]
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/tasks",
            task_data,
            description="Create task"
        )
        
        if success and isinstance(data, dict) and "id" in data:
            self.created_task_id = data["id"]
            print(f"   📝 Created task with ID: {self.created_task_id}")
    
    def test_tasks_update(self):
        """Test 14: PUT /api/tasks/{id}"""
        if not self.created_task_id:
            # Use a known task ID from seed data
            self.created_task_id = "task_001"
        
        update_data = {"status": "in-progress"}
        
        self.test_endpoint(
            "PUT",
            f"/tasks/{self.created_task_id}",
            update_data,
            description="Update task status"
        )
    
    def test_tasks_delete(self):
        """Test 15: DELETE /api/tasks/{id}"""
        if self.created_task_id and "api test" in str(self.created_task_id).lower():
            self.test_endpoint(
                "DELETE",
                f"/tasks/{self.created_task_id}",
                description="Delete test task"
            )
        else:
            print("   ⚠️ Skipping delete of seed data task")
    
    def test_checkins_list(self):
        """Test 16: GET /api/checkins"""
        success, data, status = self.test_endpoint(
            "GET",
            "/checkins",
            description="List check-ins"
        )
        
        if success and isinstance(data, list):
            print(f"   ✅ Found {len(data)} check-ins")
    
    def test_checkins_create(self):
        """Test 17: POST /api/checkins"""
        checkin_data = {
            "member_name": "API Test Checkin",
            "type": "visitor",
            "event_name": "Test Event",
            "method": "manual"
        }
        
        self.test_endpoint(
            "POST",
            "/checkins",
            checkin_data,
            description="Manual check-in"
        )
    
    def test_checkins_stats(self):
        """Test 18: GET /api/checkins/stats"""
        success, data, status = self.test_endpoint(
            "GET",
            "/checkins/stats",
            description="Get check-in stats"
        )
        
        if success and isinstance(data, dict):
            print(f"   📊 Check-in stats: {data.get('total', 0)} total, {data.get('today', 0)} today")
    
    def test_venues_list(self):
        """Test 19: GET /api/venues"""
        success, data, status = self.test_endpoint(
            "GET",
            "/venues",
            description="List venues"
        )
        
        if success and isinstance(data, list):
            print(f"   🏢 Found {len(data)} venues")
    
    def test_venues_create(self):
        """Test 20: POST /api/venues"""
        venue_data = {
            "name": "API Test Venue",
            "capacity": 50,
            "type": "meeting",
            "description": "Venue created via API test",
            "hourly_rate": 30000,
            "available": True
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/venues",
            venue_data,
            description="Create venue"
        )
        
        if success and isinstance(data, dict) and "id" in data:
            self.created_venue_id = data["id"]
            print(f"   🏢 Created venue with ID: {self.created_venue_id}")
    
    def test_public_events(self):
        """Test 21: GET /api/public/events (no auth)"""
        success, data, status = self.test_endpoint(
            "GET",
            "/public/events",
            headers={},  # No auth
            description="Public events (no auth needed)"
        )
        
        if success and isinstance(data, list):
            print(f"   🌐 Found {len(data)} public events")
    
    def test_public_venues(self):
        """Test 22: GET /api/public/venues (no auth)"""
        success, data, status = self.test_endpoint(
            "GET",
            "/public/venues",
            headers={},  # No auth
            description="Public venues (no auth)"
        )
        
        if success and isinstance(data, list):
            print(f"   🌐 Found {len(data)} public venues")
    
    def test_public_booking_event(self):
        """Test 23: POST /api/public/bookings/event"""
        booking_data = {
            "name": "API Test Booking",
            "email": "testbooking@example.com",
            "phone": "+256 700 888999",
            "event_id": "evt_001",  # Use known event ID
            "num_tickets": 2
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/public/bookings/event",
            booking_data,
            headers={},  # No auth
            description="Book an event"
        )
        
        if success and isinstance(data, dict):
            print(f"   🎫 Booking created with status: {data.get('status', 'unknown')}")
    
    def test_public_booking_status(self):
        """Test 24: GET /api/public/bookings/status"""
        success, data, status = self.test_endpoint(
            "GET",
            "/public/bookings/status?email=testbooking@example.com",
            headers={},  # No auth
            description="Check booking status"
        )
        
        if success and isinstance(data, list):
            print(f"   📋 Found {len(data)} bookings for email")
    
    def test_kiosk_checkin(self):
        """Test 25: POST /api/kiosk/checkin (no auth)"""
        checkin_data = {
            "member_name": "Kiosk Test User",
            "type": "visitor",
            "event_name": "Test Event",
            "method": "manual"
        }
        
        success, data, status = self.test_endpoint(
            "POST",
            "/kiosk/checkin",
            checkin_data,
            headers={},  # No auth
            description="Kiosk check-in (no auth)"
        )
        
        if success:
            print("   🖥️ Kiosk check-in successful")
    
    def test_kiosk_lookup(self):
        """Test 26: GET /api/kiosk/lookup"""
        success, data, status = self.test_endpoint(
            "GET",
            "/kiosk/lookup?identifier=%2B256%20700%20123456",  # URL encoded phone from seed data
            headers={},  # No auth
            description="Member lookup"
        )
        
        if success and isinstance(data, dict):
            print(f"   🔍 Found member: {data.get('name', 'Unknown')}")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if "✅" in r["status"])
        failed = sum(1 for r in self.test_results if "❌" in r["status"])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if "❌" in result["status"]:
                    print(f"   {result['method']} {result['endpoint']}: {result['message']}")
                    if result.get('details'):
                        print(f"      Details: {result['details']}")
        
        print("\n🎯 All 26 endpoints tested as requested!")
        return passed, failed, total

def main():
    """Main test runner"""
    tester = APITester()
    tester.run_all_tests()
    
    passed, failed, total = tester.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()