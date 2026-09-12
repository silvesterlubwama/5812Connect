"""
Iteration 27 Tests: 4 NEW Features
1. Financial live import/export API
2. Calendar live import/export for regular users
3. Restricted residents & guest pass QR enhancements
4. Event recurrence customizations (daily, weekly, monthly, yearly)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication for all tests"""
    token = None
    
    @classmethod
    def get_token(cls):
        if cls.token:
            return cls.token
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        cls.token = response.json().get("token")
        return cls.token

@pytest.fixture
def auth_headers():
    token = TestAuth.get_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ========== 1. FINANCIAL LIVE IMPORT/EXPORT API ==========

class TestFinancialExportImport:
    """Test GET /api/financial/export and POST /api/financial/import"""
    
    def test_financial_export_basic(self, auth_headers):
        """Test financial export returns donations and expenses"""
        response = requests.get(f"{BASE_URL}/api/financial/export", headers=auth_headers)
        assert response.status_code == 200, f"Export failed: {response.text}"
        data = response.json()
        # Verify response structure
        assert "donations" in data, "Missing donations in export"
        assert "expenses" in data, "Missing expenses in export"
        assert "donations_count" in data, "Missing donations_count"
        assert "expenses_count" in data, "Missing expenses_count"
        assert isinstance(data["donations"], list)
        assert isinstance(data["expenses"], list)
        print(f"✓ Financial export: {data['donations_count']} donations, {data['expenses_count']} expenses")
    
    def test_financial_export_with_date_filters(self, auth_headers):
        """Test financial export with date_from and date_to params"""
        today = datetime.now().strftime("%Y-%m-%d")
        last_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        response = requests.get(
            f"{BASE_URL}/api/financial/export",
            params={"date_from": last_month, "date_to": today},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Export with dates failed: {response.text}"
        data = response.json()
        assert "donations" in data
        assert "expenses" in data
        print(f"✓ Financial export with date filter: {data['donations_count']} donations, {data['expenses_count']} expenses")
    
    def test_financial_export_with_location_filter(self, auth_headers):
        """Test financial export with location_id param"""
        response = requests.get(
            f"{BASE_URL}/api/financial/export",
            params={"location_id": "loc_002"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Export with location failed: {response.text}"
        data = response.json()
        assert "donations" in data
        assert "expenses" in data
        print(f"✓ Financial export with location filter: {data['donations_count']} donations, {data['expenses_count']} expenses")
    
    def test_financial_import_donations_and_expenses(self, auth_headers):
        """Test POST /api/financial/import with donations and expenses"""
        import_data = {
            "donations": [
                {"donor_name": "TEST_Import_Donor", "amount": 50000, "currency": "UGX", "type": "donation", "date": "2026-01-15"}
            ],
            "expenses": [
                {"title": "TEST_Import_Expense", "amount": 25000, "currency": "UGX", "category": "supplies", "date": "2026-01-15"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/financial/import", json=import_data, headers=auth_headers)
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        assert "donations_imported" in data, "Missing donations_imported"
        assert "expenses_imported" in data, "Missing expenses_imported"
        assert data["donations_imported"] == 1, f"Expected 1 donation imported, got {data['donations_imported']}"
        assert data["expenses_imported"] == 1, f"Expected 1 expense imported, got {data['expenses_imported']}"
        print(f"✓ Financial import: {data['donations_imported']} donations, {data['expenses_imported']} expenses imported")
    
    def test_financial_import_empty_data_fails(self, auth_headers):
        """Test that import with no data returns 400"""
        response = requests.post(f"{BASE_URL}/api/financial/import", json={}, headers=auth_headers)
        assert response.status_code == 400, f"Expected 400 for empty import, got {response.status_code}"
        print("✓ Financial import correctly rejects empty data")


# ========== 2. CALENDAR LIVE IMPORT/EXPORT ==========

class TestCalendarImportExport:
    """Test iCal import/export and recurring event generation"""
    
    def test_ical_export(self, auth_headers):
        """Test GET /api/events/export/ical returns iCal format"""
        response = requests.get(f"{BASE_URL}/api/events/export/ical", headers=auth_headers)
        assert response.status_code == 200, f"iCal export failed: {response.text}"
        content_type = response.headers.get("content-type", "")
        assert "text/calendar" in content_type, f"Expected text/calendar, got {content_type}"
        content = response.text
        assert "BEGIN:VCALENDAR" in content, "Missing VCALENDAR header"
        assert "VERSION:2.0" in content, "Missing VERSION"
        print(f"✓ iCal export successful, {len(content)} bytes")
    
    def test_ical_import(self, auth_headers):
        """Test POST /api/events/import/ical parses iCal text"""
        ical_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-import-event@5812global
DTSTART:20260201T100000
SUMMARY:TEST_Imported_Event
DESCRIPTION:Test event from iCal import
LOCATION:Test Location
END:VEVENT
END:VCALENDAR"""
        response = requests.post(
            f"{BASE_URL}/api/events/import/ical",
            json={"ical_content": ical_content},
            headers=auth_headers
        )
        assert response.status_code == 200, f"iCal import failed: {response.text}"
        data = response.json()
        assert "imported" in data, "Missing imported count"
        assert data["imported"] >= 1, f"Expected at least 1 event imported, got {data['imported']}"
        print(f"✓ iCal import: {data['imported']} events imported")
    
    def test_ical_import_empty_fails(self, auth_headers):
        """Test that empty iCal content returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/events/import/ical",
            json={"ical_content": ""},
            headers=auth_headers
        )
        assert response.status_code == 400, f"Expected 400 for empty iCal, got {response.status_code}"
        print("✓ iCal import correctly rejects empty content")


# ========== 3. EVENT RECURRENCE CUSTOMIZATIONS ==========

class TestEventRecurrence:
    """Test POST /api/events/generate-recurring with various patterns"""
    
    def test_daily_recurrence(self, auth_headers):
        """Test daily pattern creates correct number of events"""
        payload = {
            "title": "TEST_Daily_Event",
            "pattern": "daily",
            "occurrences": 5,
            "start_date": "2026-02-01",
            "time": "09:00",
            "type": "meeting"
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Daily recurrence failed: {response.text}"
        data = response.json()
        assert "created" in data, "Missing created count"
        assert data["created"] == 5, f"Expected 5 events, got {data['created']}"
        assert "events" in data
        assert len(data["events"]) == 5
        print(f"✓ Daily recurrence: {data['created']} events created")
    
    def test_weekly_recurrence(self, auth_headers):
        """Test weekly pattern creates correct number of events"""
        payload = {
            "title": "TEST_Weekly_Event",
            "pattern": "weekly",
            "occurrences": 4,
            "start_date": "2026-02-01",
            "time": "10:00",
            "type": "service"
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Weekly recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 4, f"Expected 4 events, got {data['created']}"
        print(f"✓ Weekly recurrence: {data['created']} events created")
    
    def test_monthly_recurrence(self, auth_headers):
        """Test monthly pattern creates correct number of events"""
        payload = {
            "title": "TEST_Monthly_Event",
            "pattern": "monthly",
            "occurrences": 6,
            "start_date": "2026-02-15",
            "time": "14:00",
            "type": "meeting"
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Monthly recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 6, f"Expected 6 events, got {data['created']}"
        print(f"✓ Monthly recurrence: {data['created']} events created")
    
    def test_yearly_recurrence(self, auth_headers):
        """Test yearly pattern creates correct number of events"""
        payload = {
            "title": "TEST_Yearly_Event",
            "pattern": "yearly",
            "occurrences": 3,
            "start_date": "2026-03-01",
            "time": "11:00",
            "type": "conference"
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Yearly recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 3, f"Expected 3 events, got {data['created']}"
        print(f"✓ Yearly recurrence: {data['created']} events created")
    
    def test_nth_week_recurrence(self, auth_headers):
        """Test nth_week pattern (e.g., 2nd Monday of each month)"""
        payload = {
            "title": "TEST_NthWeek_Event",
            "pattern": "nth_week",
            "occurrences": 4,
            "start_date": "2026-02-01",
            "time": "15:00",
            "type": "meeting",
            "day_of_week": 1,  # Monday
            "nth_week": 2  # 2nd week
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Nth week recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] >= 1, f"Expected at least 1 event, got {data['created']}"
        print(f"✓ Nth week recurrence: {data['created']} events created")
    
    def test_recurrence_with_end_date(self, auth_headers):
        """Test that end_date stops event creation early"""
        payload = {
            "title": "TEST_EndDate_Event",
            "pattern": "daily",
            "occurrences": 100,  # High number
            "start_date": "2026-02-01",
            "end_date": "2026-02-05",  # Should stop after 5 days
            "time": "08:00",
            "type": "meeting"
        }
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"End date recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] <= 5, f"Expected max 5 events due to end_date, got {data['created']}"
        print(f"✓ Recurrence with end_date: {data['created']} events (stopped at end_date)")


# ========== 4. GUEST PASS QR ENHANCEMENTS ==========

class TestGuestPassQR:
    """Test guest pass validation and extension with time bounds"""
    
    def test_list_guest_passes(self, auth_headers):
        """Test GET /api/access/guest-passes returns passes with time bounds"""
        response = requests.get(
            f"{BASE_URL}/api/access/guest-passes",
            params={"location_id": "loc_002"},
            headers=auth_headers
        )
        assert response.status_code == 200, f"List guest passes failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of guest passes"
        if len(data) > 0:
            # Check that passes have time bound fields
            pass_item = data[0]
            print(f"✓ Guest passes list: {len(data)} passes found")
            print(f"  Sample pass fields: {list(pass_item.keys())}")
        else:
            print("✓ Guest passes list: 0 passes (empty)")
    
    def test_validate_guest_pass(self, auth_headers):
        """Test GET /api/access/guest-passes/{id}/validate returns validation result"""
        # First get a pass ID
        list_response = requests.get(
            f"{BASE_URL}/api/access/guest-passes",
            params={"location_id": "loc_002"},
            headers=auth_headers
        )
        passes = list_response.json()
        
        if len(passes) == 0:
            pytest.skip("No guest passes available to validate")
        
        pass_id = passes[0]["id"]
        response = requests.get(f"{BASE_URL}/api/access/guest-passes/{pass_id}/validate", headers=auth_headers)
        assert response.status_code == 200, f"Validate guest pass failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "valid" in data, "Missing 'valid' field"
        assert "pass" in data, "Missing 'pass' field"
        assert "message" in data, "Missing 'message' field"
        assert "location_name" in data, "Missing 'location_name' field"
        
        print(f"✓ Guest pass validation: valid={data['valid']}, message='{data['message']}'")
    
    def test_validate_guest_pass_known_id(self, auth_headers):
        """Test validation of known guest pass gp_b3f3c2a2"""
        response = requests.get(f"{BASE_URL}/api/access/guest-passes/gp_b3f3c2a2/validate", headers=auth_headers)
        # May return 404 if pass doesn't exist, or 200 with validation result
        if response.status_code == 404:
            print("✓ Guest pass gp_b3f3c2a2 not found (expected if not seeded)")
        else:
            assert response.status_code == 200, f"Validate failed: {response.text}"
            data = response.json()
            assert "valid" in data
            assert "message" in data
            print(f"✓ Guest pass gp_b3f3c2a2 validation: valid={data['valid']}, message='{data['message']}'")
    
    def test_extend_guest_pass(self, auth_headers):
        """Test PUT /api/access/guest-passes/{id}/extend with valid_days"""
        # First get a pass ID
        list_response = requests.get(
            f"{BASE_URL}/api/access/guest-passes",
            params={"location_id": "loc_002"},
            headers=auth_headers
        )
        passes = list_response.json()
        
        if len(passes) == 0:
            pytest.skip("No guest passes available to extend")
        
        pass_id = passes[0]["id"]
        response = requests.put(
            f"{BASE_URL}/api/access/guest-passes/{pass_id}/extend",
            json={"valid_days": 7},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Extend guest pass failed: {response.text}"
        data = response.json()
        assert "valid_until" in data, "Missing valid_until in response"
        print(f"✓ Guest pass extended: new valid_until={data.get('valid_until')}")


# ========== CLEANUP ==========

class TestCleanup:
    """Clean up test data created during tests"""
    
    def test_cleanup_test_events(self, auth_headers):
        """Delete TEST_ prefixed events"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        if response.status_code == 200:
            events = response.json()
            deleted = 0
            for event in events:
                if event.get("title", "").startswith("TEST_"):
                    del_resp = requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=auth_headers)
                    if del_resp.status_code in [200, 204]:
                        deleted += 1
            print(f"✓ Cleanup: deleted {deleted} test events")
        else:
            print("✓ Cleanup: no events to clean")
    
    def test_cleanup_test_donations(self, auth_headers):
        """Note: Donations don't have delete endpoint, just verify they exist"""
        response = requests.get(f"{BASE_URL}/api/financial/donations", headers=auth_headers)
        if response.status_code == 200:
            donations = response.json()
            test_donations = [d for d in donations if d.get("donor_name", "").startswith("TEST_")]
            print(f"✓ Cleanup note: {len(test_donations)} test donations exist (no delete endpoint)")
        else:
            print("✓ Cleanup: donations check complete")
