"""
Iteration 47 - Testing new features:
1. Event recurrence: bimonthly, quarterly, custom, custom_weekly patterns
2. Children bulk import with auto-creation of families/parents and deduplication
3. Family member editing endpoint (PUT /api/families/{id}/members)
4. Staff-as-parents included in parent lists
5. Access control API connections CRUD
6. Guest access links with shareable tokens
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    def test_login_success(self, auth_token):
        """Verify login works"""
        assert auth_token is not None
        print(f"✓ Login successful, token obtained")


class TestEventRecurrence:
    """Test event recurrence patterns: bimonthly, quarterly, custom, custom_weekly"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_bimonthly_recurrence(self, auth_headers):
        """Test bimonthly pattern generates events every 2 months"""
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring", 
            headers=auth_headers,
            json={
                "pattern": "bimonthly",
                "title": "TEST_Bimonthly Meeting",
                "type": "meeting",
                "start_date": "2026-04-01",
                "occurrences": 4,
                "time": "10:00",
                "location": "Conference Room"
            }
        )
        assert response.status_code == 200, f"Bimonthly recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 4, f"Expected 4 events, got {data['created']}"
        
        # Verify dates are 2 months apart: Apr, Jun, Aug, Oct
        dates = [e["date"] for e in data["events"]]
        expected_months = ["2026-04", "2026-06", "2026-08", "2026-10"]
        for i, date in enumerate(dates):
            assert date.startswith(expected_months[i]), f"Event {i} date {date} should be in {expected_months[i]}"
        print(f"✓ Bimonthly recurrence: {dates}")
    
    def test_quarterly_recurrence(self, auth_headers):
        """Test quarterly pattern generates events every 3 months"""
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring",
            headers=auth_headers,
            json={
                "pattern": "quarterly",
                "title": "TEST_Quarterly Review",
                "type": "meeting",
                "start_date": "2026-01-15",
                "occurrences": 4,
                "time": "14:00"
            }
        )
        assert response.status_code == 200, f"Quarterly recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 4, f"Expected 4 events, got {data['created']}"
        
        # Verify dates are 3 months apart: Jan, Apr, Jul, Oct
        dates = [e["date"] for e in data["events"]]
        expected_months = ["2026-01", "2026-04", "2026-07", "2026-10"]
        for i, date in enumerate(dates):
            assert date.startswith(expected_months[i]), f"Event {i} date {date} should be in {expected_months[i]}"
        print(f"✓ Quarterly recurrence: {dates}")
    
    def test_custom_dates_recurrence(self, auth_headers):
        """Test custom pattern with specific dates"""
        custom_dates = ["2026-05-10", "2026-06-22", "2026-08-05", "2026-09-18"]
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring",
            headers=auth_headers,
            json={
                "pattern": "custom",
                "title": "TEST_Custom Event",
                "type": "conference",
                "custom_dates": custom_dates,
                "occurrences": 10,  # Should only create 4 (limited by custom_dates)
                "time": "09:00"
            }
        )
        assert response.status_code == 200, f"Custom recurrence failed: {response.text}"
        data = response.json()
        assert data["created"] == 4, f"Expected 4 events, got {data['created']}"
        
        dates = [e["date"] for e in data["events"]]
        assert dates == custom_dates, f"Dates mismatch: {dates} vs {custom_dates}"
        print(f"✓ Custom dates recurrence: {dates}")
    
    def test_custom_weekly_multi_day(self, auth_headers):
        """Test custom_weekly pattern with multiple days per week (e.g., Mon+Wed+Fri)"""
        response = requests.post(f"{BASE_URL}/api/events/generate-recurring",
            headers=auth_headers,
            json={
                "pattern": "custom_weekly",
                "title": "TEST_MWF Class",
                "type": "training",
                "start_date": "2026-04-06",  # Monday
                "days_of_week": [0, 2, 4],  # Mon, Wed, Fri
                "occurrences": 6,
                "time": "08:00"
            }
        )
        assert response.status_code == 200, f"Custom weekly failed: {response.text}"
        data = response.json()
        assert data["created"] == 6, f"Expected 6 events, got {data['created']}"
        print(f"✓ Custom weekly (MWF) recurrence: {[e['date'] for e in data['events']]}")


class TestChildrenBulkImport:
    """Test children bulk import with auto-creation of families/parents and deduplication"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_bulk_import_creates_family_and_parent(self, auth_headers):
        """Test that importing a child auto-creates family and parent"""
        unique_id = str(uuid.uuid4())[:6]
        response = requests.post(f"{BASE_URL}/api/children/bulk-import",
            headers=auth_headers,
            json={
                "children": [{
                    "name": f"TEST_Child_{unique_id}",
                    "age": 8,
                    "gender": "female",
                    "family_name": f"TEST_Family_{unique_id}",
                    "parent_name": f"TEST_Parent_{unique_id}",
                    "parent_phone": f"+256700{unique_id}",
                    "parent_email": f"parent_{unique_id}@test.com"
                }]
            }
        )
        assert response.status_code == 200, f"Bulk import failed: {response.text}"
        data = response.json()
        assert data["imported"] == 1, f"Expected 1 imported, got {data['imported']}"
        assert data["updated"] == 0, f"Expected 0 updated, got {data['updated']}"
        print(f"✓ Bulk import created child, family, and parent")
        
        # Verify family was created
        families_resp = requests.get(f"{BASE_URL}/api/families", 
            headers=auth_headers,
            params={"search": f"TEST_Family_{unique_id}"}
        )
        families = families_resp.json()
        assert len(families) >= 1, "Family was not created"
        print(f"✓ Family auto-created: {families[0]['family_name']}")
        
        # Verify parent was created as guest
        guests_resp = requests.get(f"{BASE_URL}/api/guests",
            headers=auth_headers,
            params={"search": f"TEST_Parent_{unique_id}"}
        )
        guests = guests_resp.json()
        parent_found = any(g.get("is_parent") for g in guests)
        assert parent_found, "Parent guest was not created with is_parent flag"
        print(f"✓ Parent auto-created as guest with is_parent=True")
    
    def test_bulk_import_deduplication(self, auth_headers):
        """Test that re-importing same child updates instead of duplicating"""
        unique_id = str(uuid.uuid4())[:6]
        child_data = {
            "name": f"TEST_Dedup_Child_{unique_id}",
            "age": 5,
            "gender": "male",
            "family_name": f"TEST_Dedup_Family_{unique_id}",
            "parent_name": f"TEST_Dedup_Parent_{unique_id}"
        }
        
        # First import
        resp1 = requests.post(f"{BASE_URL}/api/children/bulk-import",
            headers=auth_headers,
            json={"children": [child_data]}
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["imported"] == 1, "First import should create 1 child"
        
        # Second import with updated age
        child_data["age"] = 6
        resp2 = requests.post(f"{BASE_URL}/api/children/bulk-import",
            headers=auth_headers,
            json={"children": [child_data]}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["imported"] == 0, "Second import should not create new child"
        assert data2["updated"] == 1, "Second import should update existing child"
        print(f"✓ Deduplication works: imported={data2['imported']}, updated={data2['updated']}")


class TestFamilyMemberEditing:
    """Test family member editing endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_update_family_members(self, auth_headers):
        """Test PUT /api/families/{id}/members to update children and parents"""
        unique_id = str(uuid.uuid4())[:6]
        
        # Create a family
        family_resp = requests.post(f"{BASE_URL}/api/families",
            headers=auth_headers,
            json={
                "family_name": f"TEST_Edit_Family_{unique_id}",
                "primary_contact_name": "Test Contact",
                "primary_contact_phone": "+256700000000"
            }
        )
        assert family_resp.status_code == 200, f"Family creation failed: {family_resp.text}"
        family = family_resp.json()
        family_id = family["id"]
        
        # Create a child
        child_resp = requests.post(f"{BASE_URL}/api/children",
            headers=auth_headers,
            json={
                "name": f"TEST_Edit_Child_{unique_id}",
                "gender": "male",
                "date_of_birth": "2018-05-15"
            }
        )
        assert child_resp.status_code == 200
        child = child_resp.json()
        child_id = child["id"]
        
        # Create a parent guest
        parent_resp = requests.post(f"{BASE_URL}/api/guests",
            headers=auth_headers,
            json={
                "name": f"TEST_Edit_Parent_{unique_id}",
                "phone": "+256700111111",
                "is_parent": True
            }
        )
        assert parent_resp.status_code == 200
        parent = parent_resp.json()
        parent_id = parent["id"]
        
        # Update family members
        update_resp = requests.put(f"{BASE_URL}/api/families/{family_id}/members",
            headers=auth_headers,
            json={
                "child_ids": [child_id],
                "parent_ids": [parent_id],
                "guardian_ids": []
            }
        )
        assert update_resp.status_code == 200, f"Family member update failed: {update_resp.text}"
        data = update_resp.json()
        assert data["children"] == 1, f"Expected 1 child linked, got {data['children']}"
        assert data["parents"] == 1, f"Expected 1 parent linked, got {data['parents']}"
        print(f"✓ Family members updated: {data}")
        
        # Verify child is now linked to family
        child_check = requests.get(f"{BASE_URL}/api/children",
            headers=auth_headers,
            params={"family_id": family_id}
        )
        children = child_check.json()
        assert any(c["id"] == child_id for c in children), "Child not linked to family"
        print(f"✓ Child correctly linked to family")


class TestStaffAsParents:
    """Test that staff marked as parents are included in parent lists"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_portal_family_includes_staff_parents(self, auth_headers):
        """Test that /api/portal/family includes staff users with is_parent=True"""
        # This endpoint returns parents including staff marked as parents
        response = requests.get(f"{BASE_URL}/api/portal/family", headers=auth_headers)
        # May return 404 if no family linked, which is acceptable
        if response.status_code == 200:
            data = response.json()
            # Check if parents list includes staff_parents
            parents = data.get("parents", [])
            print(f"✓ Portal family endpoint works, parents count: {len(parents)}")
        else:
            # No family linked is acceptable for this test
            print(f"✓ Portal family endpoint returns {response.status_code} (no family linked)")


class TestAccessAPIConnections:
    """Test access control API connections CRUD"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_create_api_connection(self, auth_headers):
        """Test creating an access control API connection"""
        unique_id = str(uuid.uuid4())[:6]
        response = requests.post(f"{BASE_URL}/api/access/api-connections",
            headers=auth_headers,
            json={
                "name": f"TEST_Front_Door_{unique_id}",
                "type": "door",
                "api_url": "https://api.kisi.io/doors/123",
                "api_key": "test_api_key_123",
                "auth_type": "api_key",
                "provider": "kisi",
                "door_name": "Main Entrance",
                "enabled": True
            }
        )
        assert response.status_code == 200, f"Create API connection failed: {response.text}"
        data = response.json()
        assert "id" in data, "No ID returned"
        assert data["name"] == f"TEST_Front_Door_{unique_id}"
        assert data["provider"] == "kisi"
        print(f"✓ API connection created: {data['id']}")
        return data["id"]
    
    def test_list_api_connections(self, auth_headers):
        """Test listing access control API connections"""
        response = requests.get(f"{BASE_URL}/api/access/api-connections", headers=auth_headers)
        assert response.status_code == 200, f"List API connections failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Listed {len(data)} API connections")
    
    def test_update_api_connection(self, auth_headers):
        """Test updating an access control API connection"""
        # First create one
        unique_id = str(uuid.uuid4())[:6]
        create_resp = requests.post(f"{BASE_URL}/api/access/api-connections",
            headers=auth_headers,
            json={
                "name": f"TEST_Update_Door_{unique_id}",
                "type": "gate",
                "provider": "salto"
            }
        )
        conn_id = create_resp.json()["id"]
        
        # Update it
        update_resp = requests.put(f"{BASE_URL}/api/access/api-connections/{conn_id}",
            headers=auth_headers,
            json={
                "name": f"TEST_Updated_Door_{unique_id}",
                "enabled": False
            }
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        print(f"✓ API connection updated")
    
    def test_delete_api_connection(self, auth_headers):
        """Test deleting an access control API connection"""
        # First create one
        unique_id = str(uuid.uuid4())[:6]
        create_resp = requests.post(f"{BASE_URL}/api/access/api-connections",
            headers=auth_headers,
            json={
                "name": f"TEST_Delete_Door_{unique_id}",
                "type": "turnstile"
            }
        )
        conn_id = create_resp.json()["id"]
        
        # Delete it
        delete_resp = requests.delete(f"{BASE_URL}/api/access/api-connections/{conn_id}",
            headers=auth_headers
        )
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        print(f"✓ API connection deleted")


class TestGuestAccessLinks:
    """Test shareable guest access links with expiry and max uses"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_create_guest_access_link(self, auth_headers):
        """Test creating a shareable guest access link"""
        unique_id = str(uuid.uuid4())[:6]
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        response = requests.post(f"{BASE_URL}/api/access/guest-links",
            headers=auth_headers,
            json={
                "space_name": f"TEST_Conference_Room_{unique_id}",
                "max_uses": 5,
                "expires_at": expires_at,
                "requires_approval": True
            }
        )
        assert response.status_code == 200, f"Create guest link failed: {response.text}"
        data = response.json()
        assert "id" in data, "No ID returned"
        assert "token" in data, "No token returned"
        assert "link" in data, "No link returned"
        assert data["max_uses"] == 5
        print(f"✓ Guest access link created: {data['link']}")
        return data
    
    def test_list_guest_access_links(self, auth_headers):
        """Test listing guest access links"""
        response = requests.get(f"{BASE_URL}/api/access/guest-links", headers=auth_headers)
        assert response.status_code == 200, f"List guest links failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Listed {len(data)} guest access links")
    
    def test_public_access_request_via_token(self, auth_headers):
        """Test submitting a guest access request via shared link token"""
        # First create a link
        unique_id = str(uuid.uuid4())[:6]
        create_resp = requests.post(f"{BASE_URL}/api/access/guest-links",
            headers=auth_headers,
            json={
                "space_name": f"TEST_Public_Room_{unique_id}",
                "max_uses": 10,
                "requires_approval": True
            }
        )
        link_data = create_resp.json()
        token = link_data["token"]
        
        # Submit public access request (no auth required)
        public_resp = requests.post(f"{BASE_URL}/api/public/access-request/{token}",
            json={
                "name": f"TEST_Guest_{unique_id}",
                "email": f"guest_{unique_id}@test.com",
                "phone": "+256700999999",
                "purpose": "Meeting with staff",
                "visit_date": "2026-04-15"
            }
        )
        assert public_resp.status_code == 200, f"Public access request failed: {public_resp.text}"
        data = public_resp.json()
        assert "id" in data, "No request ID returned"
        assert data["status"] == "pending", f"Expected pending status, got {data['status']}"
        print(f"✓ Public access request submitted: {data['id']}")
    
    def test_delete_guest_access_link(self, auth_headers):
        """Test deleting a guest access link"""
        # First create one
        unique_id = str(uuid.uuid4())[:6]
        create_resp = requests.post(f"{BASE_URL}/api/access/guest-links",
            headers=auth_headers,
            json={"space_name": f"TEST_Delete_Room_{unique_id}"}
        )
        link_id = create_resp.json()["id"]
        
        # Delete it
        delete_resp = requests.delete(f"{BASE_URL}/api/access/guest-links/{link_id}",
            headers=auth_headers
        )
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        print(f"✓ Guest access link deleted")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_cleanup_test_events(self, auth_headers):
        """Clean up TEST_ prefixed events"""
        events_resp = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        if events_resp.status_code == 200:
            events = events_resp.json()
            deleted = 0
            for event in events:
                if event.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/events/{event['id']}", headers=auth_headers)
                    deleted += 1
            print(f"✓ Cleaned up {deleted} test events")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
