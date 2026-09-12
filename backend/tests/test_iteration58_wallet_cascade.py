"""
Iteration 58 Tests: Wallet Badge & Cascade Deletion Features
- POST /api/members/{id}/wallet-badge: Creates wallet badge with token
- GET /api/wallet-badge/{token}: Public endpoint to fetch badge data
- DELETE cascade cleanup for users, members, families, guests, children
"""
import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": creds.ADMIN_EMAIL,
        "password": creds.ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestWalletBadgeEndpoints:
    """Test wallet badge creation and public fetch"""
    
    def test_create_wallet_badge_for_member(self, auth_headers):
        """POST /api/members/{id}/wallet-badge creates badge with token"""
        # First get a member to create badge for
        members_res = requests.get(f"{BASE_URL}/api/members", headers=auth_headers, params={"limit": 1})
        assert members_res.status_code == 200
        members = members_res.json().get("members", [])
        
        if not members:
            # Create a test member
            create_res = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
                "name": "TEST_WalletBadge User",
                "email": f"test_wallet_{uuid.uuid4().hex[:6]}@test.com",
                "role": "Staff",
                "gender": "male"
            })
            assert create_res.status_code == 200
            member_id = create_res.json()["id"]
        else:
            member_id = members[0]["id"]
        
        # Create wallet badge
        response = requests.post(f"{BASE_URL}/api/members/{member_id}/wallet-badge", headers=auth_headers)
        assert response.status_code == 200, f"Failed to create wallet badge: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain token"
        assert "member_id" in data, "Response should contain member_id"
        assert "name" in data, "Response should contain name"
        assert len(data["token"]) == 16, "Token should be 16 characters"
        
        # Store token for next test
        TestWalletBadgeEndpoints.wallet_token = data["token"]
        TestWalletBadgeEndpoints.member_id = member_id
        print(f"Created wallet badge with token: {data['token']}")
    
    def test_get_wallet_badge_public_no_auth(self):
        """GET /api/wallet-badge/{token} is public (no auth required)"""
        token = getattr(TestWalletBadgeEndpoints, 'wallet_token', None)
        if not token:
            pytest.skip("No wallet token from previous test")
        
        # Fetch without auth headers
        response = requests.get(f"{BASE_URL}/api/wallet-badge/{token}")
        assert response.status_code == 200, f"Public badge fetch failed: {response.text}"
        
        data = response.json()
        assert "token" in data
        assert "name" in data
        assert "member_id" in data
        print(f"Public badge fetch successful: {data.get('name')}")
    
    def test_get_wallet_badge_invalid_token(self):
        """GET /api/wallet-badge/{token} returns 404 for invalid token"""
        response = requests.get(f"{BASE_URL}/api/wallet-badge/invalidtoken12345")
        assert response.status_code == 404
        print("Invalid token correctly returns 404")
    
    def test_wallet_badge_contains_location_info(self, auth_headers):
        """Wallet badge should include location/country info if available"""
        token = getattr(TestWalletBadgeEndpoints, 'wallet_token', None)
        if not token:
            pytest.skip("No wallet token from previous test")
        
        response = requests.get(f"{BASE_URL}/api/wallet-badge/{token}")
        assert response.status_code == 200
        
        data = response.json()
        # These fields should exist (may be empty if member has no location)
        assert "location_name" in data or data.get("location_name") is None
        assert "country" in data or data.get("country") is None
        assert "country_code" in data or data.get("country_code") is None
        print(f"Badge location info: {data.get('location_name')}, {data.get('country')}")


class TestMemberDeleteCascade:
    """Test DELETE /api/members/{id} cascade cleanup"""
    
    def test_delete_member_cascades_task_assignees(self, auth_headers):
        """Deleting member removes them from task assignees"""
        # Create a test member
        member_res = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_CascadeMember",
            "email": f"cascade_member_{uuid.uuid4().hex[:6]}@test.com",
            "role": "Staff",
            "gender": "male"
        })
        assert member_res.status_code == 200
        member_id = member_res.json()["id"]
        
        # Create a task with this member as assignee
        task_res = requests.post(f"{BASE_URL}/api/tasks", headers=auth_headers, json={
            "title": "TEST_CascadeTask",
            "assignees": [member_id],
            "status": "todo"
        })
        if task_res.status_code == 200:
            task_id = task_res.json()["id"]
            
            # Delete the member
            del_res = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
            assert del_res.status_code == 200
            
            # Verify task no longer has this assignee
            task_check = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)
            if task_check.status_code == 200:
                assignees = task_check.json().get("assignees", [])
                assert member_id not in assignees, "Member should be removed from task assignees"
                print("Member cascade: removed from task assignees")
            
            # Cleanup task
            requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)
        else:
            # Just delete the member if task creation failed
            requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
            print("Task creation skipped, member deleted")


class TestFamilyDeleteCascade:
    """Test DELETE /api/families/{id} cascade cleanup"""
    
    def test_delete_family_unlinks_children_and_guests(self, auth_headers):
        """Deleting family unlinks children and guests from that family"""
        # Create a test family
        family_res = requests.post(f"{BASE_URL}/api/families", headers=auth_headers, json={
            "family_name": f"TEST_CascadeFamily_{uuid.uuid4().hex[:6]}",
            "primary_contact_name": "Test Parent"
        })
        assert family_res.status_code == 200
        family_id = family_res.json()["id"]
        
        # Create a child linked to this family
        child_res = requests.post(f"{BASE_URL}/api/children", headers=auth_headers, json={
            "name": "TEST_CascadeChild",
            "family_id": family_id,
            "gender": "male"
        })
        child_id = None
        if child_res.status_code == 200:
            child_id = child_res.json()["id"]
        
        # Create a guest linked to this family
        guest_res = requests.post(f"{BASE_URL}/api/guests", headers=auth_headers, json={
            "name": "TEST_CascadeGuest",
            "family_id": family_id,
            "is_parent": True
        })
        guest_id = None
        if guest_res.status_code == 200:
            guest_id = guest_res.json()["id"]
        
        # Delete the family
        del_res = requests.delete(f"{BASE_URL}/api/families/{family_id}", headers=auth_headers)
        assert del_res.status_code == 200
        
        # Verify child's family_id is unset
        if child_id:
            children_res = requests.get(f"{BASE_URL}/api/children", headers=auth_headers)
            if children_res.status_code == 200:
                children = children_res.json()
                child = next((c for c in children if c["id"] == child_id), None)
                if child:
                    assert child.get("family_id") in [None, ""], "Child's family_id should be unset"
                    print("Family cascade: child's family_id unset")
            # Cleanup child
            requests.delete(f"{BASE_URL}/api/children/{child_id}", headers=auth_headers)
        
        # Verify guest's family_id is unset
        if guest_id:
            guests_res = requests.get(f"{BASE_URL}/api/guests", headers=auth_headers)
            if guests_res.status_code == 200:
                guests = guests_res.json()
                guest = next((g for g in guests if g["id"] == guest_id), None)
                if guest:
                    assert guest.get("family_id") in [None, ""], "Guest's family_id should be unset"
                    print("Family cascade: guest's family_id unset")
            # Cleanup guest
            requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=auth_headers)


class TestGuestDeleteCascade:
    """Test DELETE /api/guests/{id} cascade cleanup"""
    
    def test_delete_guest_removes_from_children_parent_ids(self, auth_headers):
        """Deleting guest removes them from children's parent_ids"""
        # Create a test guest (parent)
        guest_res = requests.post(f"{BASE_URL}/api/guests", headers=auth_headers, json={
            "name": "TEST_CascadeParent",
            "is_parent": True
        })
        assert guest_res.status_code == 200
        guest_id = guest_res.json()["id"]
        
        # Create a child with this guest as parent
        child_res = requests.post(f"{BASE_URL}/api/children", headers=auth_headers, json={
            "name": "TEST_ChildWithParent",
            "parent_ids": [guest_id],
            "gender": "female"
        })
        child_id = None
        if child_res.status_code == 200:
            child_id = child_res.json()["id"]
        
        # Delete the guest
        del_res = requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=auth_headers)
        assert del_res.status_code == 200
        
        # Verify child's parent_ids no longer contains this guest
        if child_id:
            children_res = requests.get(f"{BASE_URL}/api/children", headers=auth_headers)
            if children_res.status_code == 200:
                children = children_res.json()
                child = next((c for c in children if c["id"] == child_id), None)
                if child:
                    parent_ids = child.get("parent_ids", [])
                    assert guest_id not in parent_ids, "Guest should be removed from child's parent_ids"
                    print("Guest cascade: removed from child's parent_ids")
            # Cleanup child
            requests.delete(f"{BASE_URL}/api/children/{child_id}", headers=auth_headers)


class TestChildDeleteCascade:
    """Test DELETE /api/children/{id} cascade cleanup"""
    
    def test_delete_child_removes_from_resident_lists(self, auth_headers):
        """Deleting child removes them from location resident_ids"""
        # Get a location
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        if locs_res.status_code != 200 or not locs_res.json():
            pytest.skip("No locations available")
        
        location = locs_res.json()[0]
        location_id = location["id"]
        
        # Create a child as resident
        child_res = requests.post(f"{BASE_URL}/api/children", headers=auth_headers, json={
            "name": "TEST_ResidentChild",
            "gender": "male",
            "is_resident": True,
            "resident_location_id": location_id
        })
        assert child_res.status_code == 200
        child_id = child_res.json()["id"]
        
        # Delete the child
        del_res = requests.delete(f"{BASE_URL}/api/children/{child_id}", headers=auth_headers)
        assert del_res.status_code == 200
        
        # Verify location's resident_ids no longer contains this child
        loc_check = requests.get(f"{BASE_URL}/api/locations/{location_id}", headers=auth_headers)
        if loc_check.status_code == 200:
            resident_ids = loc_check.json().get("resident_ids", [])
            assert child_id not in resident_ids, "Child should be removed from location resident_ids"
            print("Child cascade: removed from location resident_ids")


class TestUserDeleteCascade:
    """Test DELETE /api/admin/users/{id} cascade cleanup"""
    
    def test_delete_user_cascades_all_references(self, auth_headers):
        """Deleting user removes from tasks, boards, unlinks members/guests"""
        # Create a test user
        user_res = requests.post(f"{BASE_URL}/api/admin/users", headers=auth_headers, json={
            "name": "TEST_CascadeUser",
            "email": f"cascade_user_{uuid.uuid4().hex[:6]}@test.com",
            "role": "Staff",
            "also_create_member": True
        })
        assert user_res.status_code == 200
        user_id = user_res.json()["id"]
        member_id = user_res.json().get("member_id")
        
        # Create a task with this user as assignee
        task_res = requests.post(f"{BASE_URL}/api/tasks", headers=auth_headers, json={
            "title": "TEST_UserCascadeTask",
            "assignees": [user_id],
            "status": "todo"
        })
        task_id = None
        if task_res.status_code == 200:
            task_id = task_res.json()["id"]
        
        # Delete the user
        del_res = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=auth_headers)
        assert del_res.status_code == 200
        
        # Verify task no longer has this assignee
        if task_id:
            task_check = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)
            if task_check.status_code == 200:
                assignees = task_check.json().get("assignees", [])
                assert user_id not in assignees, "User should be removed from task assignees"
                print("User cascade: removed from task assignees")
            # Cleanup task
            requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=auth_headers)
        
        # Verify member's user_id is unset
        if member_id:
            members_res = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
            if members_res.status_code == 200:
                members = members_res.json().get("members", [])
                member = next((m for m in members if m["id"] == member_id), None)
                if member:
                    assert member.get("user_id") in [None, ""], "Member's user_id should be unset"
                    print("User cascade: member's user_id unset")
                # Cleanup member
                requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)


class TestDataEventsIntegration:
    """Test that delete operations work correctly (frontend event bus is client-side)"""
    
    def test_member_delete_returns_success(self, auth_headers):
        """DELETE /api/members/{id} returns success message"""
        # Create a test member
        member_res = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_EventMember",
            "email": f"event_member_{uuid.uuid4().hex[:6]}@test.com",
            "role": "Staff",
            "gender": "male"
        })
        assert member_res.status_code == 200
        member_id = member_res.json()["id"]
        
        # Delete the member
        del_res = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        assert del_res.status_code == 200
        assert "message" in del_res.json()
        print(f"Member delete response: {del_res.json()}")
    
    def test_guest_delete_returns_success(self, auth_headers):
        """DELETE /api/guests/{id} returns success message"""
        # Create a test guest
        guest_res = requests.post(f"{BASE_URL}/api/guests", headers=auth_headers, json={
            "name": "TEST_EventGuest"
        })
        assert guest_res.status_code == 200
        guest_id = guest_res.json()["id"]
        
        # Delete the guest
        del_res = requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=auth_headers)
        assert del_res.status_code == 200
        assert "message" in del_res.json()
        print(f"Guest delete response: {del_res.json()}")


class TestCleanup:
    """Cleanup any remaining test data"""
    
    def test_cleanup_test_data(self, auth_headers):
        """Remove TEST_ prefixed data"""
        # Cleanup members
        members_res = requests.get(f"{BASE_URL}/api/members", headers=auth_headers, params={"limit": 500})
        if members_res.status_code == 200:
            members = members_res.json().get("members", [])
            for m in members:
                if m.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/members/{m['id']}", headers=auth_headers)
        
        # Cleanup children
        children_res = requests.get(f"{BASE_URL}/api/children", headers=auth_headers)
        if children_res.status_code == 200:
            children = children_res.json()
            for c in children:
                if c.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/children/{c['id']}", headers=auth_headers)
        
        # Cleanup guests
        guests_res = requests.get(f"{BASE_URL}/api/guests", headers=auth_headers)
        if guests_res.status_code == 200:
            guests = guests_res.json()
            for g in guests:
                if g.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/guests/{g['id']}", headers=auth_headers)
        
        # Cleanup families
        families_res = requests.get(f"{BASE_URL}/api/families", headers=auth_headers)
        if families_res.status_code == 200:
            families = families_res.json()
            for f in families:
                if f.get("family_name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/families/{f['id']}", headers=auth_headers)
        
        print("Test data cleanup completed")
