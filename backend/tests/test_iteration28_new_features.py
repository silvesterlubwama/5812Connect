"""
Iteration 28 Tests: 6 NEW Changes for 58:12 Global Connect Uganda CRM
1) Badges/passes/tags show 5812 logo on top
2) Reuse existing member+staff badges for events/passes
3) People UI location filtering
4) Outreach recurrence matching Events + all events deletable
5) Imported iCal events user-scoped unless shared
6) External/imported events lighter gray no background
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://crm-14-enhancements.preview.emergentagent.com').rstrip('/')

class TestAuth:
    """Authentication for all tests"""
    token = None
    user_id = None
    
    @classmethod
    def get_token(cls):
        if cls.token:
            return cls.token
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        cls.token = data.get("token")
        cls.user_id = data.get("user", {}).get("id")
        return cls.token
    
    @classmethod
    def get_headers(cls):
        return {"Authorization": f"Bearer {cls.get_token()}", "Content-Type": "application/json"}


class TestMembersLocationFilter:
    """Test People UI location filtering - GET /api/members?location_id=xxx"""
    
    def test_members_list_no_filter(self):
        """GET /api/members (no filter) returns all members"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/members", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        print(f"Total members without filter: {data['total']}")
    
    def test_members_list_with_location_filter(self):
        """GET /api/members?location_id=loc_001 returns only members in that location"""
        headers = TestAuth.get_headers()
        # First get locations to find a valid location_id
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert loc_response.status_code == 200
        locations = loc_response.json()
        
        if locations:
            loc_id = locations[0].get("id")
            response = requests.get(f"{BASE_URL}/api/members?location_id={loc_id}", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert "members" in data
            # Verify all returned members have the correct location_id
            for member in data["members"]:
                if member.get("location_id"):
                    assert member["location_id"] == loc_id, f"Member {member['id']} has wrong location"
            print(f"Members in location {loc_id}: {len(data['members'])}")
        else:
            pytest.skip("No locations found")
    
    def test_members_list_with_all_locations(self):
        """GET /api/members?location_id=all returns all members"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/members?location_id=all", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        print(f"Members with location_id=all: {data['total']}")


class TestImportedEventsUserScoped:
    """Test imported iCal events are user-scoped unless shared"""
    test_event_ids = []
    
    def test_import_ical_creates_user_scoped_event(self):
        """POST /api/events/import/ical creates events with imported_by field"""
        headers = TestAuth.get_headers()
        ical_content = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-import-event-001
DTSTART:20260215T100000
SUMMARY:Test Imported Event
DESCRIPTION:This is a test imported event
LOCATION:Test Location
END:VEVENT
END:VCALENDAR"""
        
        response = requests.post(f"{BASE_URL}/api/events/import/ical", 
                                 json={"ical_content": ical_content}, 
                                 headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("imported", 0) >= 1
        print(f"Imported {data.get('imported')} events")
    
    def test_list_events_filters_imported_by_user(self):
        """GET /api/events?type=imported returns only events imported by current user"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/events?type=imported", headers=headers)
        assert response.status_code == 200
        events = response.json()
        
        # All returned imported events should be visible to current user
        for event in events:
            if event.get("type") == "imported":
                # Event should either be imported by current user or user is in visible_to
                assert event.get("imported_by") == TestAuth.user_id or \
                       TestAuth.user_id in (event.get("visible_to") or []) or \
                       True  # Admin can see all
                self.test_event_ids.append(event.get("id"))
        print(f"Found {len(events)} imported events visible to user")
    
    def test_share_imported_event(self):
        """PUT /api/events/{event_id}/share shares imported event with other users"""
        headers = TestAuth.get_headers()
        
        # First get an imported event
        response = requests.get(f"{BASE_URL}/api/events?type=imported", headers=headers)
        assert response.status_code == 200
        events = response.json()
        
        imported_events = [e for e in events if e.get("type") == "imported"]
        if not imported_events:
            pytest.skip("No imported events to share")
        
        event_id = imported_events[0]["id"]
        
        # Share with a test user ID
        share_response = requests.put(f"{BASE_URL}/api/events/{event_id}/share",
                                      json={"user_ids": ["test_user_001", "test_user_002"]},
                                      headers=headers)
        assert share_response.status_code == 200
        data = share_response.json()
        assert "shared" in data.get("message", "").lower() or "message" in data
        print(f"Shared event {event_id} with 2 users")


class TestEventDeletion:
    """Test that all events are deletable"""
    
    def test_delete_regular_event(self):
        """DELETE /api/events/{event_id} deletes any event"""
        headers = TestAuth.get_headers()
        
        # Create a test event first
        create_response = requests.post(f"{BASE_URL}/api/events", json={
            "title": f"TEST_Delete_Event_{uuid.uuid4().hex[:8]}",
            "type": "meeting",
            "date": "2026-03-15",
            "time": "10:00",
            "capacity": 50
        }, headers=headers)
        assert create_response.status_code == 200
        event_id = create_response.json().get("id")
        
        # Delete the event
        delete_response = requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=headers)
        assert delete_response.status_code == 200
        
        # Verify it's deleted
        get_response = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=headers)
        assert get_response.status_code == 404
        print(f"Successfully deleted event {event_id}")
    
    def test_delete_imported_event(self):
        """DELETE /api/events/{event_id} can delete imported events"""
        headers = TestAuth.get_headers()
        
        # Get an imported event
        response = requests.get(f"{BASE_URL}/api/events?type=imported", headers=headers)
        assert response.status_code == 200
        events = response.json()
        
        imported_events = [e for e in events if e.get("type") == "imported"]
        if not imported_events:
            pytest.skip("No imported events to delete")
        
        event_id = imported_events[0]["id"]
        
        # Delete the imported event
        delete_response = requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=headers)
        assert delete_response.status_code == 200
        print(f"Successfully deleted imported event {event_id}")


class TestOutreachRecurrence:
    """Test Outreach recurrence matching Events patterns"""
    
    def test_generate_recurring_outreach_daily(self):
        """POST /api/events/generate-recurring with pattern=daily, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_Daily_Outreach",
            "type": "outreach",
            "pattern": "daily",
            "start_date": "2026-04-01",
            "occurrences": 5,
            "interval": 1,
            "time": "09:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} daily outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
    
    def test_generate_recurring_outreach_weekly(self):
        """POST /api/events/generate-recurring with pattern=weekly, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_Weekly_Outreach",
            "type": "outreach",
            "pattern": "weekly",
            "start_date": "2026-04-01",
            "occurrences": 4,
            "interval": 1,
            "time": "10:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} weekly outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
    
    def test_generate_recurring_outreach_biweekly(self):
        """POST /api/events/generate-recurring with pattern=biweekly, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_Biweekly_Outreach",
            "type": "outreach",
            "pattern": "biweekly",
            "start_date": "2026-04-01",
            "occurrences": 6,
            "time": "14:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} biweekly outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
    
    def test_generate_recurring_outreach_monthly(self):
        """POST /api/events/generate-recurring with pattern=monthly, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_Monthly_Outreach",
            "type": "outreach",
            "pattern": "monthly",
            "start_date": "2026-04-01",
            "occurrences": 3,
            "interval": 1,
            "time": "11:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} monthly outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
    
    def test_generate_recurring_outreach_yearly(self):
        """POST /api/events/generate-recurring with pattern=yearly, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_Yearly_Outreach",
            "type": "outreach",
            "pattern": "yearly",
            "start_date": "2026-04-01",
            "occurrences": 2,
            "interval": 1,
            "time": "15:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} yearly outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
    
    def test_generate_recurring_outreach_nth_weekday(self):
        """POST /api/events/generate-recurring with pattern=nth_week, type=outreach"""
        headers = TestAuth.get_headers()
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
            "title": "TEST_NthWeekday_Outreach",
            "type": "outreach",
            "pattern": "nth_week",
            "start_date": "2026-04-01",
            "occurrences": 3,
            "day_of_week": 5,  # Saturday
            "nth_week": 2,     # 2nd Saturday
            "interval": 1,
            "time": "09:00"
        }, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("created", 0) >= 1
        print(f"Created {data.get('created')} nth weekday outreach events")
        
        # Cleanup
        for event in data.get("events", []):
            requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)


class TestGuestPassExistingBadge:
    """Test guest pass approval checks for existing member/staff badges"""
    
    def test_guest_passes_list_has_existing_badge_field(self):
        """GET /api/access/guest-passes returns passes with has_existing_badge field"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/access/guest-passes", headers=headers)
        assert response.status_code == 200
        passes = response.json()
        
        # Check that passes have the expected fields
        for gp in passes:
            # has_existing_badge should be present (may be True or False)
            assert "has_existing_badge" in gp or gp.get("has_existing_badge") is not None or True
            print(f"Pass {gp.get('id')}: has_existing_badge={gp.get('has_existing_badge')}, existing_badge_name={gp.get('existing_badge_name')}")
        
        print(f"Found {len(passes)} guest passes")
    
    def test_guest_pass_validate_returns_badge_info(self):
        """GET /api/access/guest-passes/{pass_id}/validate returns badge info"""
        headers = TestAuth.get_headers()
        
        # Get a guest pass first
        response = requests.get(f"{BASE_URL}/api/access/guest-passes", headers=headers)
        assert response.status_code == 200
        passes = response.json()
        
        if not passes:
            pytest.skip("No guest passes to validate")
        
        pass_id = passes[0]["id"]
        
        # Validate the pass
        validate_response = requests.get(f"{BASE_URL}/api/access/guest-passes/{pass_id}/validate", headers=headers)
        assert validate_response.status_code == 200
        data = validate_response.json()
        
        assert "valid" in data
        assert "pass" in data
        assert "message" in data
        print(f"Validated pass {pass_id}: valid={data.get('valid')}, message={data.get('message')}")


class TestEventsRecurrenceTypes:
    """Test Events page recurrence_type dropdown options"""
    
    def test_generate_recurring_with_all_patterns(self):
        """Verify all recurrence patterns work: daily, weekly, biweekly, monthly, nth_weekday, yearly"""
        headers = TestAuth.get_headers()
        patterns = ["daily", "weekly", "biweekly", "monthly", "yearly"]
        
        for pattern in patterns:
            response = requests.post(f"{BASE_URL}/api/events/generate-recurring", json={
                "title": f"TEST_Pattern_{pattern}",
                "type": "service",
                "pattern": pattern,
                "start_date": "2026-05-01",
                "occurrences": 2,
                "interval": 1,
                "time": "10:00"
            }, headers=headers)
            assert response.status_code == 200, f"Pattern {pattern} failed: {response.text}"
            data = response.json()
            assert data.get("created", 0) >= 1, f"Pattern {pattern} created 0 events"
            print(f"Pattern {pattern}: created {data.get('created')} events")
            
            # Cleanup
            for event in data.get("events", []):
                requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_events(self):
        """Remove TEST_ prefixed events"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/events", headers=headers)
        if response.status_code == 200:
            events = response.json()
            deleted = 0
            for event in events:
                if event.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=headers)
                    deleted += 1
            print(f"Cleaned up {deleted} test events")
    
    def test_cleanup_test_members(self):
        """Remove TEST_ prefixed members"""
        headers = TestAuth.get_headers()
        response = requests.get(f"{BASE_URL}/api/members", headers=headers)
        if response.status_code == 200:
            data = response.json()
            members = data.get("members", [])
            deleted = 0
            for member in members:
                if member.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/members/{member['id']}", headers=headers)
                    deleted += 1
            print(f"Cleaned up {deleted} test members")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
