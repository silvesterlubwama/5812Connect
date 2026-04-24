"""
Iteration 51 - Badge Improvements & NFC Tag CRUD Tests
Tests:
- NFC tag CRUD endpoints (GET/POST/DELETE /api/members/{id}/nfc-tags)
- NFC tag duplicate check (409 conflict)
- Auth login verification
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == "admin@5812uganda.org"
        print(f"✓ Login successful for admin user")


class TestNfcTagCrud:
    """NFC Tag CRUD endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find a test member"""
        # Login
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a member to test with
        members_res = requests.get(f"{BASE_URL}/api/members", headers=self.headers, params={"limit": 5})
        assert members_res.status_code == 200, f"Failed to get members: {members_res.text}"
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) > 0, "No members found for testing"
        self.test_member_id = members[0]["id"]
        self.test_member_name = members[0].get("name", "Unknown")
        print(f"Using test member: {self.test_member_name} ({self.test_member_id})")
    
    def test_get_nfc_tags_empty(self):
        """Test GET /api/members/{id}/nfc-tags returns list (possibly empty)"""
        response = requests.get(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers
        )
        assert response.status_code == 200, f"GET NFC tags failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ GET NFC tags returned {len(data)} tags")
    
    def test_add_nfc_tag(self):
        """Test POST /api/members/{id}/nfc-tags adds a tag"""
        unique_serial = f"04:A2:B3:C4:D5:E6:{uuid.uuid4().hex[:2].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers,
            json={
                "serial_number": unique_serial,
                "label": "Test Badge Card"
            }
        )
        assert response.status_code == 200, f"POST NFC tag failed: {response.text}"
        data = response.json()
        assert "id" in data, "No id in response"
        assert data["serial_number"] == unique_serial
        assert data["label"] == "Test Badge Card"
        assert "added_at" in data
        print(f"✓ Added NFC tag: {data['id']} with serial {unique_serial}")
        
        # Verify it appears in GET
        get_res = requests.get(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers
        )
        assert get_res.status_code == 200
        tags = get_res.json()
        tag_ids = [t["id"] for t in tags]
        assert data["id"] in tag_ids, "Added tag not found in GET response"
        print(f"✓ Verified tag appears in GET response")
        
        # Store for cleanup
        self.added_tag_id = data["id"]
        return data
    
    def test_add_and_delete_nfc_tag(self):
        """Test full add/delete cycle"""
        unique_serial = f"04:B3:C4:D5:E6:F7:{uuid.uuid4().hex[:2].upper()}"
        
        # Add
        add_res = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Delete Test"}
        )
        assert add_res.status_code == 200, f"Add failed: {add_res.text}"
        tag_id = add_res.json()["id"]
        print(f"✓ Added tag {tag_id}")
        
        # Delete
        del_res = requests.delete(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags/{tag_id}",
            headers=self.headers
        )
        assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
        assert "message" in del_res.json()
        print(f"✓ Deleted tag {tag_id}")
        
        # Verify removed
        get_res = requests.get(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers
        )
        tags = get_res.json()
        tag_ids = [t["id"] for t in tags]
        assert tag_id not in tag_ids, "Deleted tag still appears in GET"
        print(f"✓ Verified tag removed from GET response")
    
    def test_add_nfc_tag_missing_serial(self):
        """Test POST without serial_number returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers,
            json={"label": "No Serial"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Missing serial returns 400")
    
    def test_delete_nonexistent_tag(self):
        """Test DELETE non-existent tag returns 404"""
        response = requests.delete(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags/nfc_nonexistent123",
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print(f"✓ Delete non-existent tag returns 404")


class TestNfcTagDuplicateCheck:
    """Test NFC tag duplicate serial check (409 conflict)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find two different members"""
        # Login
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200
        self.token = login_res.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get at least 2 members
        members_res = requests.get(f"{BASE_URL}/api/members", headers=self.headers, params={"limit": 10})
        assert members_res.status_code == 200
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) >= 2, "Need at least 2 members for duplicate test"
        self.member1_id = members[0]["id"]
        self.member2_id = members[1]["id"]
        print(f"Using members: {self.member1_id} and {self.member2_id}")
    
    def test_duplicate_serial_returns_409(self):
        """Test adding same serial to different member returns 409"""
        unique_serial = f"04:DUP:TEST:{uuid.uuid4().hex[:4].upper()}"
        
        # Add to first member
        res1 = requests.post(
            f"{BASE_URL}/api/members/{self.member1_id}/nfc-tags",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Dup Test 1"}
        )
        assert res1.status_code == 200, f"First add failed: {res1.text}"
        tag1_id = res1.json()["id"]
        print(f"✓ Added tag to member1: {tag1_id}")
        
        # Try to add same serial to second member - should fail with 409
        res2 = requests.post(
            f"{BASE_URL}/api/members/{self.member2_id}/nfc-tags",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Dup Test 2"}
        )
        assert res2.status_code == 409, f"Expected 409 conflict, got {res2.status_code}: {res2.text}"
        assert "already assigned" in res2.json().get("detail", "").lower()
        print(f"✓ Duplicate serial correctly returns 409 conflict")
        
        # Cleanup - delete from first member
        requests.delete(
            f"{BASE_URL}/api/members/{self.member1_id}/nfc-tags/{tag1_id}",
            headers=self.headers
        )
        print(f"✓ Cleaned up test tag")


class TestLocationsHaveCountry:
    """Verify locations have country field for badge watermarks"""
    
    def test_locations_have_country(self):
        """Test that locations have country field"""
        # Login
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get locations
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert locs_res.status_code == 200, f"Failed to get locations: {locs_res.text}"
        locations = locs_res.json()
        assert len(locations) > 0, "No locations found"
        
        # Check at least one has country
        countries_found = [loc.get("country") for loc in locations if loc.get("country")]
        print(f"Found {len(countries_found)} locations with country field: {countries_found}")
        
        # List all locations for debugging
        for loc in locations:
            print(f"  - {loc.get('name')}: country={loc.get('country', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
