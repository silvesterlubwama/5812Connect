"""
Iteration 35 Backend Tests - Massive Update Features
Tests for:
1. Public bookings with payment flow (Cash/Mobile Money/Venmo/Card)
2. Cash cutoff rules (no cash within 3 days)
3. Mark-as-paid endpoint (staff only)
4. Pending payments endpoint
5. Policies endpoint (6 policies)
6. Report generation fix (db.checkins not db.check_ins)
7. New user signup defaults to 'Member' with 'pending' status
8. Public events with country filter and 1-year limit
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_admin(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == creds.ADMIN_EMAIL
        return data["token"]


class TestPublicPolicies:
    """Test GET /api/public/policies - returns 6 policies"""
    
    def test_policies_endpoint_no_auth(self):
        """Policies endpoint should work without authentication"""
        response = requests.get(f"{BASE_URL}/api/public/policies")
        assert response.status_code == 200, f"Policies failed: {response.text}"
        data = response.json()
        
        # Should have 6 policies
        assert len(data) == 6, f"Expected 6 policies, got {len(data)}"
        
        # Check all required policies exist
        expected_policies = [
            "privacy_policy",
            "terms_of_service", 
            "refund_policy",
            "employee_onboarding",
            "data_retention",
            "cookie_policy"
        ]
        for policy_key in expected_policies:
            assert policy_key in data, f"Missing policy: {policy_key}"
            assert "title" in data[policy_key], f"Policy {policy_key} missing title"
            assert "content" in data[policy_key], f"Policy {policy_key} missing content"
    
    def test_policies_content_mentions_countries(self):
        """Policies should mention compliance with US/EU/Uganda/Kenya/Thailand/Haiti/Mexico"""
        response = requests.get(f"{BASE_URL}/api/public/policies")
        data = response.json()
        
        privacy_content = data["privacy_policy"]["content"].lower()
        # Check for country/regulation mentions
        assert "gdpr" in privacy_content or "eu" in privacy_content, "Privacy policy should mention EU/GDPR"
        assert "uganda" in privacy_content, "Privacy policy should mention Uganda"


class TestPublicEvents:
    """Test public events with country filter and 1-year limit"""
    
    def test_public_events_no_auth(self):
        """Public events endpoint should work without authentication"""
        response = requests.get(f"{BASE_URL}/api/public/events")
        assert response.status_code == 200, f"Public events failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
    
    def test_public_events_country_filter(self):
        """Test country filter parameter"""
        response = requests.get(f"{BASE_URL}/api/public/events?country=UG")
        assert response.status_code == 200
        # Should return events (may be empty if no UG events)
        data = response.json()
        assert isinstance(data, list)
    
    def test_public_events_1_year_limit(self):
        """Events should be limited to 1 year ahead"""
        response = requests.get(f"{BASE_URL}/api/public/events")
        data = response.json()
        
        max_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        for event in data:
            if event.get("date"):
                assert event["date"] <= max_date, f"Event {event['id']} date {event['date']} exceeds 1-year limit"


class TestPublicVenues:
    """Test public venues endpoint - only bookable venues"""
    
    def test_public_venues_no_auth(self):
        """Public venues should work without auth"""
        response = requests.get(f"{BASE_URL}/api/public/venues")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned venues should be bookable
        for venue in data:
            # is_bookable should not be False (can be True or not set)
            assert venue.get("is_bookable") != False, f"Venue {venue['id']} should be bookable"


class TestPublicBookings:
    """Test public booking flow with payment methods"""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    @pytest.fixture
    def test_event(self, auth_token):
        """Create a test event for booking tests"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create a free event
        free_event = {
            "title": "TEST_Free_Event_Iter35",
            "type": "community",
            "date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "time": "10:00",
            "capacity": 100,
            "is_public": True,
            "is_free": True
        }
        res = requests.post(f"{BASE_URL}/api/events", json=free_event, headers=headers)
        free_id = res.json().get("id") if res.status_code == 200 else None
        
        # Create a paid event
        paid_event = {
            "title": "TEST_Paid_Event_Iter35",
            "type": "conference",
            "date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "time": "14:00",
            "capacity": 50,
            "is_public": True,
            "is_free": False,
            "price": 50000
        }
        res2 = requests.post(f"{BASE_URL}/api/events", json=paid_event, headers=headers)
        paid_id = res2.json().get("id") if res2.status_code == 200 else None
        
        yield {"free_id": free_id, "paid_id": paid_id}
        
        # Cleanup
        if free_id:
            requests.delete(f"{BASE_URL}/api/events/{free_id}", headers=headers)
        if paid_id:
            requests.delete(f"{BASE_URL}/api/events/{paid_id}", headers=headers)
    
    def test_book_free_event(self, test_event):
        """Book a free event - no payment required"""
        if not test_event.get("free_id"):
            pytest.skip("No test event created")
        
        booking_data = {
            "name": "TEST_John Doe",
            "email": "test_john@example.com",
            "phone": "+256700000001",
            "event_id": test_event["free_id"],
            "num_tickets": 2,
            "agreed_to_terms": True
        }
        response = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking_data)
        assert response.status_code == 200, f"Booking failed: {response.text}"
        
        data = response.json()
        assert data["is_free"] == True
        assert data["payment_status"] == "paid"  # Free events are auto-paid
        assert data["status"] == "confirmed"
        assert len(data["ticket_ids"]) == 2
    
    def test_book_paid_event_with_card(self, test_event):
        """Book a paid event with card payment"""
        if not test_event.get("paid_id"):
            pytest.skip("No paid test event created")
        
        booking_data = {
            "name": "TEST_Jane Smith",
            "email": "test_jane@example.com",
            "phone": "+256700000002",
            "event_id": test_event["paid_id"],
            "num_tickets": 1,
            "payment_method": "card",
            "agreed_to_terms": True
        }
        response = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking_data)
        assert response.status_code == 200, f"Booking failed: {response.text}"
        
        data = response.json()
        assert data["is_free"] == False
        assert data["payment_status"] == "pending"
        assert data["payment_method"] == "card"
        assert data["total"] == 50000  # price * 1 ticket
    
    def test_book_paid_event_with_mobile_money(self, test_event):
        """Book a paid event with MTN Mobile Money"""
        if not test_event.get("paid_id"):
            pytest.skip("No paid test event created")
        
        booking_data = {
            "name": "TEST_Bob MTN",
            "email": "test_bob@example.com",
            "event_id": test_event["paid_id"],
            "num_tickets": 1,
            "payment_method": "mobile_money_mtn",
            "agreed_to_terms": True
        }
        response = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["payment_method"] == "mobile_money_mtn"


class TestCashCutoffRules:
    """Test cash payment cutoff rules - no cash within 3 days of event"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    @pytest.fixture
    def event_in_2_days(self, auth_token):
        """Create event happening in 2 days"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        event = {
            "title": "TEST_Event_2Days",
            "type": "meeting",
            "date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
            "capacity": 50,
            "is_public": True,
            "is_free": False,
            "price": 25000
        }
        res = requests.post(f"{BASE_URL}/api/events", json=event, headers=headers)
        event_id = res.json().get("id") if res.status_code == 200 else None
        yield event_id
        if event_id:
            requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=headers)
    
    def test_cash_rejected_within_3_days(self, event_in_2_days):
        """Cash payment should be rejected for events within 3 days"""
        if not event_in_2_days:
            pytest.skip("No test event")
        
        booking_data = {
            "name": "TEST_Cash User",
            "email": "test_cash@example.com",
            "event_id": event_in_2_days,
            "num_tickets": 1,
            "payment_method": "cash",
            "agreed_to_terms": True
        }
        response = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking_data)
        
        # Should be rejected
        assert response.status_code == 400, f"Cash should be rejected within 3 days: {response.text}"
        assert "cash" in response.json().get("detail", "").lower()


class TestMarkAsPaid:
    """Test PUT /api/public/bookings/{id}/mark-paid - staff only"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    @pytest.fixture
    def pending_booking(self, auth_token):
        """Create a booking with pending payment"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create paid event
        event = {
            "title": "TEST_MarkPaid_Event",
            "type": "workshop",
            "date": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
            "capacity": 30,
            "is_public": True,
            "is_free": False,
            "price": 75000
        }
        ev_res = requests.post(f"{BASE_URL}/api/events", json=event, headers=headers)
        event_id = ev_res.json().get("id") if ev_res.status_code == 200 else None
        
        if not event_id:
            yield None, None
            return
        
        # Create booking
        booking = {
            "name": "TEST_Pending User",
            "email": "test_pending@example.com",
            "event_id": event_id,
            "num_tickets": 1,
            "payment_method": "cash",
            "agreed_to_terms": True
        }
        book_res = requests.post(f"{BASE_URL}/api/public/bookings/event", json=booking)
        booking_id = book_res.json().get("id") if book_res.status_code == 200 else None
        
        yield booking_id, event_id
        
        # Cleanup
        if event_id:
            requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=headers)
    
    def test_mark_paid_requires_auth(self, pending_booking):
        """Mark-as-paid should require authentication"""
        booking_id, _ = pending_booking
        if not booking_id:
            pytest.skip("No booking created")
        
        response = requests.put(f"{BASE_URL}/api/public/bookings/{booking_id}/mark-paid", json={
            "transaction_ref": "TEST123"
        })
        assert response.status_code in [401, 403], "Should require auth"
    
    def test_mark_paid_with_staff(self, auth_token, pending_booking):
        """Staff can mark booking as paid"""
        booking_id, _ = pending_booking
        if not booking_id:
            pytest.skip("No booking created")
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.put(
            f"{BASE_URL}/api/public/bookings/{booking_id}/mark-paid",
            json={"transaction_ref": "CASH-001", "notes": "Paid in person"},
            headers=headers
        )
        assert response.status_code == 200, f"Mark paid failed: {response.text}"
        assert "paid" in response.json().get("message", "").lower()


class TestPendingPayments:
    """Test GET /api/public/bookings/pending-payments"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_pending_payments_requires_auth(self):
        """Pending payments endpoint requires staff auth"""
        response = requests.get(f"{BASE_URL}/api/public/bookings/pending-payments")
        assert response.status_code in [401, 403]
    
    def test_pending_payments_with_staff(self, auth_token):
        """Staff can list pending payments"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/public/bookings/pending-payments", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestNewUserSignup:
    """Test new user signup defaults to 'Member' with 'pending' status"""
    
    def test_register_defaults_to_member(self):
        """New registration should default to Member role with pending status"""
        import uuid
        unique_email = f"test_member_{uuid.uuid4().hex[:8]}@example.com"
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST_New Member",
            "email": unique_email,
            "password": creds.CUSTOM_PASSWORD
        })
        assert response.status_code == 200, f"Registration failed: {response.text}"
        
        data = response.json()
        user = data.get("user", {})
        
        # Should default to Member role
        assert user.get("role") == "Member", f"Expected 'Member' role, got '{user.get('role')}'"
        
        # Should have pending status
        assert user.get("status") == "pending", f"Expected 'pending' status, got '{user.get('status')}'"


class TestReportGeneration:
    """Test report generation uses correct collection name (db.checkins not db.check_ins)"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_create_and_generate_attendance_report(self, auth_token):
        """Create and generate an attendance report - should not error on collection name"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create report
        report_data = {
            "title": "TEST_Attendance_Report",
            "type": "attendance",
            "filters": {},
            "columns": ["member_name", "check_in_time", "type"]
        }
        create_res = requests.post(f"{BASE_URL}/api/reports", json=report_data, headers=headers)
        assert create_res.status_code == 200, f"Create report failed: {create_res.text}"
        
        report_id = create_res.json().get("id")
        
        # Generate report data - this should use db.checkins (not db.check_ins)
        gen_res = requests.post(f"{BASE_URL}/api/reports/{report_id}/generate", headers=headers)
        assert gen_res.status_code == 200, f"Generate report failed: {gen_res.text}"
        
        data = gen_res.json()
        assert "data" in data
        assert "checkins" in data["data"] or "checkins_count" in data["data"]
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/reports/{report_id}", headers=headers)


class TestKioskCheckout:
    """Test kiosk checkout functionality"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_checkout_endpoint_exists(self, auth_token):
        """Test that checkout endpoint exists"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First create a check-in
        checkin_data = {
            "member_name": "TEST_Checkout_User",
            "type": "visitor",
            "method": "manual"
        }
        ci_res = requests.post(f"{BASE_URL}/api/checkins", json=checkin_data, headers=headers)
        
        if ci_res.status_code == 200:
            checkin_id = ci_res.json().get("id")
            
            # Try to checkout
            co_res = requests.post(f"{BASE_URL}/api/checkins/{checkin_id}/checkout", headers=headers)
            assert co_res.status_code == 200, f"Checkout failed: {co_res.text}"


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["token"]
        pytest.skip("Auth failed")
    
    def test_cleanup_test_events(self, auth_token):
        """Clean up any remaining test events"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get all events
        res = requests.get(f"{BASE_URL}/api/events", headers=headers)
        if res.status_code == 200:
            events = res.json()
            for event in events:
                if event.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
        
        assert True  # Cleanup always passes
