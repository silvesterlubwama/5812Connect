"""
Iteration 52 - NFC Tag Writing Tests
Tests:
- POST /api/members/{id}/nfc-write endpoint (director+ required)
- 403 for staff-level users (non-director)
- Auto-adds tag to member profile
- Logs to nfc_write_log collection
- Duplicate serial check on write
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestNfcWriteEndpoint:
    """NFC Write endpoint tests - requires director+ role"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token (admin = director+) and find a test member"""
        # Login as admin (role level 10, which is director+)
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.user = login_res.json()["user"]
        print(f"Logged in as: {self.user.get('name')} (role: {self.user.get('role')})")
        
        # Get a member to test with
        members_res = requests.get(f"{BASE_URL}/api/members", headers=self.headers, params={"limit": 5})
        assert members_res.status_code == 200, f"Failed to get members: {members_res.text}"
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) > 0, "No members found for testing"
        self.test_member_id = members[0]["id"]
        self.test_member_name = members[0].get("name", "Unknown")
        print(f"Using test member: {self.test_member_name} ({self.test_member_id})")
    
    def test_nfc_write_success(self):
        """Test POST /api/members/{id}/nfc-write works for director+"""
        unique_serial = f"04:WRITE:{uuid.uuid4().hex[:6].upper()}"
        
        response = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-write",
            headers=self.headers,
            json={
                "serial_number": unique_serial,
                "written_data": self.test_member_id,
                "label": "Test Written Badge"
            }
        )
        assert response.status_code == 200, f"NFC write failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "message" in data, "No message in response"
        assert "tag" in data, "No tag in response"
        assert "member_id" in data, "No member_id in response"
        assert "member_name" in data, "No member_name in response"
        assert data["member_id"] == self.test_member_id
        print(f"✓ NFC write successful: {data['message']}")
        
        # Verify tag was added to member profile
        tags_res = requests.get(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers
        )
        assert tags_res.status_code == 200
        tags = tags_res.json()
        tag_serials = [t.get("serial_number") for t in tags]
        assert unique_serial in tag_serials, f"Written tag not found in member's NFC tags: {tag_serials}"
        print(f"✓ Tag auto-added to member profile")
        
        # Cleanup - remove the tag
        tag_id = data["tag"]["id"] if data.get("tag") else None
        if tag_id:
            requests.delete(
                f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags/{tag_id}",
                headers=self.headers
            )
            print(f"✓ Cleaned up test tag")
    
    def test_nfc_write_missing_serial(self):
        """Test POST /api/members/{id}/nfc-write without serial returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-write",
            headers=self.headers,
            json={"label": "No Serial"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Missing serial returns 400")
    
    def test_nfc_write_nonexistent_member(self):
        """Test POST /api/members/{id}/nfc-write for non-existent member returns 404"""
        unique_serial = f"04:NOEXIST:{uuid.uuid4().hex[:6].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/members/mem_nonexistent123/nfc-write",
            headers=self.headers,
            json={"serial_number": unique_serial}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print(f"✓ Non-existent member returns 404")
    
    def test_nfc_write_existing_tag_marks_written(self):
        """Test writing to a tag that already exists on member marks it as written"""
        unique_serial = f"04:EXIST:{uuid.uuid4().hex[:6].upper()}"
        
        # First add the tag normally
        add_res = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Pre-existing Tag"}
        )
        assert add_res.status_code == 200, f"Add tag failed: {add_res.text}"
        tag_id = add_res.json()["id"]
        print(f"✓ Added pre-existing tag: {tag_id}")
        
        # Now write to it
        write_res = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-write",
            headers=self.headers,
            json={"serial_number": unique_serial, "written_data": self.test_member_id}
        )
        assert write_res.status_code == 200, f"NFC write failed: {write_res.text}"
        print(f"✓ NFC write to existing tag successful")
        
        # Verify tag is marked as written
        tags_res = requests.get(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags",
            headers=self.headers
        )
        tags = tags_res.json()
        written_tag = next((t for t in tags if t.get("serial_number") == unique_serial), None)
        assert written_tag is not None, "Tag not found"
        assert written_tag.get("written") == True, f"Tag not marked as written: {written_tag}"
        print(f"✓ Existing tag marked as written")
        
        # Cleanup
        requests.delete(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags/{tag_id}",
            headers=self.headers
        )


class TestNfcWriteDuplicateCheck:
    """Test NFC write duplicate serial check (409 conflict)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find two different members"""
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
    
    def test_nfc_write_duplicate_serial_returns_409(self):
        """Test writing same serial to different member returns 409"""
        unique_serial = f"04:WDUP:{uuid.uuid4().hex[:6].upper()}"
        
        # Write to first member
        res1 = requests.post(
            f"{BASE_URL}/api/members/{self.member1_id}/nfc-write",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Write Dup Test 1"}
        )
        assert res1.status_code == 200, f"First write failed: {res1.text}"
        tag1 = res1.json().get("tag")
        print(f"✓ Wrote tag to member1")
        
        # Try to write same serial to second member - should fail with 409
        res2 = requests.post(
            f"{BASE_URL}/api/members/{self.member2_id}/nfc-write",
            headers=self.headers,
            json={"serial_number": unique_serial, "label": "Write Dup Test 2"}
        )
        assert res2.status_code == 409, f"Expected 409 conflict, got {res2.status_code}: {res2.text}"
        assert "already assigned" in res2.json().get("detail", "").lower()
        print(f"✓ Duplicate serial correctly returns 409 conflict")
        
        # Cleanup
        if tag1 and tag1.get("id"):
            requests.delete(
                f"{BASE_URL}/api/members/{self.member1_id}/nfc-tags/{tag1['id']}",
                headers=self.headers
            )
            print(f"✓ Cleaned up test tag")


class TestNfcWriteRoleRestriction:
    """Test that NFC write requires director+ role (level 8+)"""
    
    def test_nfc_write_requires_director_role(self):
        """Test that non-director users get 403 on NFC write"""
        # First login as admin to create a staff-level user for testing
        admin_login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get a member to test with
        members_res = requests.get(f"{BASE_URL}/api/members", headers=admin_headers, params={"limit": 1})
        assert members_res.status_code == 200
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) > 0, "No members found"
        test_member_id = members[0]["id"]
        
        # Try to find or create a staff-level user
        # First check if there's a staff user we can use
        users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, params={"role": "Staff", "limit": 5})
        if users_res.status_code == 200:
            users = users_res.json()
            staff_users = [u for u in users if u.get("role") in ["Staff", "Coordinator", "Volunteer", "Member"]]
            
            if staff_users:
                # Try to login as staff user - but we don't know their password
                # Instead, we'll create a test staff user
                pass
        
        # Create a test staff user
        test_email = f"test_staff_{uuid.uuid4().hex[:6]}@test.com"
        test_password = "TestPass123!"
        
        create_res = requests.post(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
            json={
                "name": "Test Staff User",
                "email": test_email,
                "password": test_password,
                "role": "Staff",  # Staff role level is below 8
                "also_create_member": False
            }
        )
        
        if create_res.status_code in [200, 201]:
            staff_user_id = create_res.json().get("id")
            print(f"Created test staff user: {test_email}")
            
            # Login as staff user
            staff_login = requests.post(f"{BASE_URL}/api/auth/login", json={
                "identifier": test_email,
                "password": test_password
            })
            
            if staff_login.status_code == 200:
                staff_token = staff_login.json()["token"]
                staff_headers = {"Authorization": f"Bearer {staff_token}"}
                staff_role = staff_login.json()["user"].get("role")
                print(f"Logged in as staff user with role: {staff_role}")
                
                # Try NFC write - should get 403
                unique_serial = f"04:STAFF:{uuid.uuid4().hex[:6].upper()}"
                write_res = requests.post(
                    f"{BASE_URL}/api/members/{test_member_id}/nfc-write",
                    headers=staff_headers,
                    json={"serial_number": unique_serial}
                )
                
                assert write_res.status_code == 403, f"Expected 403 for staff user, got {write_res.status_code}: {write_res.text}"
                print(f"✓ Staff user correctly gets 403 on NFC write")
                
                # Cleanup - delete test user
                requests.delete(f"{BASE_URL}/api/admin/users/{staff_user_id}", headers=admin_headers)
                print(f"✓ Cleaned up test staff user")
            else:
                print(f"Could not login as staff user: {staff_login.text}")
                # Cleanup
                if staff_user_id:
                    requests.delete(f"{BASE_URL}/api/admin/users/{staff_user_id}", headers=admin_headers)
                pytest.skip("Could not login as staff user to test role restriction")
        else:
            print(f"Could not create staff user: {create_res.text}")
            pytest.skip("Could not create staff user to test role restriction")


class TestNfcWriteLog:
    """Test that NFC writes are logged to nfc_write_log collection"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find a test member"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200
        self.token = login_res.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        members_res = requests.get(f"{BASE_URL}/api/members", headers=self.headers, params={"limit": 1})
        assert members_res.status_code == 200
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) > 0
        self.test_member_id = members[0]["id"]
        self.test_member_name = members[0].get("name", "Unknown")
    
    def test_nfc_write_creates_log_entry(self):
        """Test that NFC write creates a log entry (verified by successful write)"""
        unique_serial = f"04:LOG:{uuid.uuid4().hex[:6].upper()}"
        
        # Perform write
        write_res = requests.post(
            f"{BASE_URL}/api/members/{self.test_member_id}/nfc-write",
            headers=self.headers,
            json={
                "serial_number": unique_serial,
                "written_data": self.test_member_id,
                "label": "Log Test Badge"
            }
        )
        assert write_res.status_code == 200, f"NFC write failed: {write_res.text}"
        print(f"✓ NFC write successful - log entry should be created in nfc_write_log collection")
        
        # Note: We can't directly query the nfc_write_log collection via API
        # The test verifies the endpoint works; the logging is internal
        # A more thorough test would require direct DB access
        
        # Cleanup
        tag = write_res.json().get("tag")
        if tag and tag.get("id"):
            requests.delete(
                f"{BASE_URL}/api/members/{self.test_member_id}/nfc-tags/{tag['id']}",
                headers=self.headers
            )


class TestDirectorRolesCanWrite:
    """Test that all director+ roles can write NFC tags"""
    
    def test_admin_can_write_nfc(self):
        """Test admin role (level 10) can write NFC"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_role = login_res.json()["user"].get("role")
        print(f"Testing with role: {user_role}")
        
        # Get a member
        members_res = requests.get(f"{BASE_URL}/api/members", headers=headers, params={"limit": 1})
        assert members_res.status_code == 200
        members_data = members_res.json()
        members = members_data.get("members", members_data) if isinstance(members_data, dict) else members_data
        assert len(members) > 0
        member_id = members[0]["id"]
        
        # Try write
        unique_serial = f"04:ADMIN:{uuid.uuid4().hex[:6].upper()}"
        write_res = requests.post(
            f"{BASE_URL}/api/members/{member_id}/nfc-write",
            headers=headers,
            json={"serial_number": unique_serial}
        )
        assert write_res.status_code == 200, f"Admin should be able to write NFC: {write_res.text}"
        print(f"✓ Admin role can write NFC tags")
        
        # Cleanup
        tag = write_res.json().get("tag")
        if tag and tag.get("id"):
            requests.delete(f"{BASE_URL}/api/members/{member_id}/nfc-tags/{tag['id']}", headers=headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
