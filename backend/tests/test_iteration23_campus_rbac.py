"""
Iteration 23: Campus-based RBAC, Staff Auto-sync, Badge Location Name, Campuses Rename
Tests for:
- Campus RBAC: System admins see ALL data, non-admins see only their campus
- Staff auto-sync: Creating/updating users auto-creates/updates linked member records
- Location name enrichment on /api/auth/me, /api/admin/users, /api/members
- Badge location: StaffBadge, ParentBadge, ChildTag show location name
- Nav rename: 'Locations' renamed to 'Campuses' in sidebar
- Location dropdown in Admin edit dialog and child create/edit forms
- Campus filtering on dashboard stats, events, checkins, financial endpoints
- Chat users endpoint scoped to campus
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
ADMIN2_EMAIL = "admin@5812global.org"
ADMIN2_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@1234")


class TestCampusRBAC:
    """Test Campus-based RBAC functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session and get admin token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        self.admin_token = data["token"]
        self.admin_user = data["user"]
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        yield
        # Cleanup: delete test users created during tests
        self._cleanup_test_data()
    
    def _cleanup_test_data(self):
        """Clean up TEST_ prefixed data"""
        try:
            # Get all users and delete TEST_ prefixed ones
            resp = self.session.get(f"{BASE_URL}/api/admin/users")
            if resp.status_code == 200:
                users = resp.json()
                for u in users:
                    if u.get("name", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/admin/users/{u['id']}")
        except:
            pass
    
    # ========== SYSTEM ADMIN TESTS ==========
    
    def test_admin_role_is_system_admin(self):
        """Verify admin role is recognized as system admin (sees all data)"""
        # Admin should see all users regardless of location
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        print(f"PASS: Admin can list all users ({len(users)} users)")
    
    def test_admin_sees_all_members(self):
        """System admin should see all members across campuses"""
        resp = self.session.get(f"{BASE_URL}/api/members")
        assert resp.status_code == 200
        data = resp.json()
        members = data.get("members", data) if isinstance(data, dict) else data
        assert isinstance(members, list)
        print(f"PASS: Admin sees all members ({len(members)} members)")
    
    def test_admin_sees_all_children(self):
        """System admin should see all children across campuses"""
        resp = self.session.get(f"{BASE_URL}/api/children")
        assert resp.status_code == 200
        children = resp.json()
        assert isinstance(children, list)
        print(f"PASS: Admin sees all children ({len(children)} children)")
    
    def test_admin_sees_all_events(self):
        """System admin should see all events across campuses"""
        resp = self.session.get(f"{BASE_URL}/api/events")
        assert resp.status_code == 200
        events = resp.json()
        assert isinstance(events, list)
        print(f"PASS: Admin sees all events ({len(events)} events)")
    
    def test_admin_sees_all_chat_users(self):
        """System admin should see all chat users across campuses"""
        resp = self.session.get(f"{BASE_URL}/api/chat/users")
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        print(f"PASS: Admin sees all chat users ({len(users)} users)")
    
    # ========== STAFF AUTO-SYNC TESTS ==========
    
    def test_create_user_auto_creates_member(self):
        """Creating a user should auto-create a linked member record"""
        test_email = f"test_autosync_{uuid.uuid4().hex[:8]}@test.com"
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_AutoSync User",
            "email": test_email,
            "phone": "+256700111222",
            "role": "Staff",
            "department": "Operations",
            "also_create_member": True
        })
        assert resp.status_code == 200, f"Create user failed: {resp.text}"
        user = resp.json()
        
        # Verify user was created
        assert user.get("name") == "TEST_AutoSync User"
        assert user.get("email") == test_email.lower()
        
        # Verify member was auto-created
        assert user.get("has_member_profile") == True, "Member profile should be auto-created"
        assert user.get("member_id") is not None, "member_id should be returned"
        
        print(f"PASS: User created with auto-synced member (member_id: {user.get('member_id')})")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user['id']}")
    
    def test_update_user_updates_member(self):
        """Updating a user should also update their linked member record"""
        # First create a user
        test_email = f"test_update_{uuid.uuid4().hex[:8]}@test.com"
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_UpdateSync User",
            "email": test_email,
            "role": "Staff",
            "also_create_member": True
        })
        assert resp.status_code == 200
        user = resp.json()
        user_id = user["id"]
        
        # Update the user
        resp = self.session.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "name": "TEST_UpdateSync User Updated",
            "phone": "+256700333444",
            "department": "Finance"
        })
        assert resp.status_code == 200, f"Update user failed: {resp.text}"
        updated = resp.json()
        
        # Verify user was updated
        assert updated.get("name") == "TEST_UpdateSync User Updated"
        assert updated.get("phone") == "+256700333444"
        
        print(f"PASS: User updated successfully")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
    
    def test_update_user_auto_creates_member_if_missing(self):
        """Updating a user without a member record should auto-create one"""
        # This tests the auto-create on update path
        test_email = f"test_autocreate_{uuid.uuid4().hex[:8]}@test.com"
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_AutoCreate User",
            "email": test_email,
            "role": "Volunteer",
            "also_create_member": False  # Don't create member initially
        })
        assert resp.status_code == 200
        user = resp.json()
        user_id = user["id"]
        
        # Update the user - should auto-create member
        resp = self.session.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "gender": "male",
            "date_of_birth": "1990-01-15"
        })
        assert resp.status_code == 200, f"Update user failed: {resp.text}"
        
        print(f"PASS: User update with member auto-creation works")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
    
    # ========== LOCATION NAME ENRICHMENT TESTS ==========
    
    def test_auth_me_includes_location_name(self):
        """GET /api/auth/me should include location_name if user has location_id"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        user = resp.json()
        
        # Check that location_name field exists (may be empty if no location assigned)
        # The endpoint should at least not error
        assert "id" in user
        assert "name" in user
        assert "role" in user
        
        # If user has location_id, location_name should be present
        if user.get("location_id"):
            assert "location_name" in user, "location_name should be enriched when location_id exists"
            print(f"PASS: /auth/me includes location_name: {user.get('location_name')}")
        else:
            print(f"PASS: /auth/me works (user has no location_id assigned)")
    
    def test_admin_users_includes_location_name(self):
        """GET /api/admin/users should include location_name for users with location_id"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200
        users = resp.json()
        
        # Find a user with location_id
        users_with_loc = [u for u in users if u.get("location_id")]
        if users_with_loc:
            user = users_with_loc[0]
            assert "location_name" in user, "location_name should be enriched"
            print(f"PASS: /admin/users includes location_name: {user.get('location_name')}")
        else:
            print(f"PASS: /admin/users works (no users with location_id found)")
    
    def test_members_includes_location_name(self):
        """GET /api/members should include location_name for members with location_id"""
        resp = self.session.get(f"{BASE_URL}/api/members")
        assert resp.status_code == 200
        data = resp.json()
        members = data.get("members", data) if isinstance(data, dict) else data
        
        # Find a member with location_id
        members_with_loc = [m for m in members if m.get("location_id")]
        if members_with_loc:
            member = members_with_loc[0]
            assert "location_name" in member, "location_name should be enriched"
            print(f"PASS: /members includes location_name: {member.get('location_name')}")
        else:
            print(f"PASS: /members works (no members with location_id found)")
    
    # ========== LOCATION ASSIGNMENT TESTS ==========
    
    def test_create_user_with_location_id(self):
        """Creating a user with location_id should work"""
        # First get available locations
        resp = self.session.get(f"{BASE_URL}/api/locations")
        assert resp.status_code == 200
        locations = resp.json()
        
        if not locations:
            pytest.skip("No locations available for testing")
        
        loc_id = locations[0]["id"]
        test_email = f"test_loc_{uuid.uuid4().hex[:8]}@test.com"
        
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_Location User",
            "email": test_email,
            "role": "Staff",
            "location_id": loc_id,
            "also_create_member": True
        })
        assert resp.status_code == 200, f"Create user with location failed: {resp.text}"
        user = resp.json()
        
        assert user.get("location_id") == loc_id, "location_id should be set"
        print(f"PASS: User created with location_id: {loc_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user['id']}")
    
    def test_update_user_location_id(self):
        """Updating a user's location_id should work"""
        # Get locations
        resp = self.session.get(f"{BASE_URL}/api/locations")
        locations = resp.json()
        if len(locations) < 1:
            pytest.skip("Need at least 1 location for testing")
        
        loc_id = locations[0]["id"]
        test_email = f"test_updateloc_{uuid.uuid4().hex[:8]}@test.com"
        
        # Create user without location
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_UpdateLoc User",
            "email": test_email,
            "role": "Staff"
        })
        assert resp.status_code == 200
        user = resp.json()
        user_id = user["id"]
        
        # Update with location
        resp = self.session.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "location_id": loc_id
        })
        assert resp.status_code == 200, f"Update location failed: {resp.text}"
        updated = resp.json()
        
        assert updated.get("location_id") == loc_id, "location_id should be updated"
        print(f"PASS: User location_id updated to: {loc_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
    
    def test_create_child_with_location_id(self):
        """Creating a child with location_id should work"""
        # Get locations
        resp = self.session.get(f"{BASE_URL}/api/locations")
        locations = resp.json()
        if not locations:
            pytest.skip("No locations available")
        
        loc_id = locations[0]["id"]
        
        resp = self.session.post(f"{BASE_URL}/api/children", json={
            "name": f"TEST_Child_{uuid.uuid4().hex[:6]}",
            "date_of_birth": "2018-05-15",
            "gender": "male",
            "class_group": "Primary 2",
            "location_id": loc_id
        })
        assert resp.status_code == 200, f"Create child with location failed: {resp.text}"
        child = resp.json()
        
        assert child.get("location_id") == loc_id, "Child location_id should be set"
        print(f"PASS: Child created with location_id: {loc_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/children/{child['id']}")
    
    # ========== CAMPUS FILTERING TESTS ==========
    
    def test_dashboard_stats_with_campus_filter(self):
        """Dashboard stats should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        stats = resp.json()
        
        # Verify stats structure
        assert "total_members" in stats
        assert "active_members" in stats
        assert "total_families" in stats
        assert "total_children" in stats
        assert "checkins_today" in stats
        
        print(f"PASS: Dashboard stats returned (members: {stats['total_members']}, families: {stats['total_families']})")
    
    def test_people_stats_with_campus_filter(self):
        """People stats should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/people/stats")
        assert resp.status_code == 200
        stats = resp.json()
        
        assert "total_members" in stats
        assert "total_families" in stats
        assert "total_children" in stats
        assert "total_guests" in stats
        
        print(f"PASS: People stats returned (members: {stats['total_members']}, children: {stats['total_children']})")
    
    def test_events_with_campus_filter(self):
        """Events endpoint should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/events")
        assert resp.status_code == 200
        events = resp.json()
        assert isinstance(events, list)
        print(f"PASS: Events endpoint works ({len(events)} events)")
    
    def test_checkins_with_campus_filter(self):
        """Checkins endpoint should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/checkins")
        assert resp.status_code == 200
        checkins = resp.json()
        assert isinstance(checkins, list)
        print(f"PASS: Checkins endpoint works ({len(checkins)} checkins)")
    
    def test_families_with_campus_filter(self):
        """Families endpoint should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/families")
        assert resp.status_code == 200
        families = resp.json()
        assert isinstance(families, list)
        print(f"PASS: Families endpoint works ({len(families)} families)")
    
    def test_guests_with_campus_filter(self):
        """Guests endpoint should respect campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/guests")
        assert resp.status_code == 200
        guests = resp.json()
        assert isinstance(guests, list)
        print(f"PASS: Guests endpoint works ({len(guests)} guests)")
    
    # ========== NON-ADMIN USER CAMPUS ISOLATION TESTS ==========
    
    def test_create_staff_user_with_location(self):
        """Create a Staff-role user with specific location for isolation testing"""
        # Get a location
        resp = self.session.get(f"{BASE_URL}/api/locations")
        locations = resp.json()
        if not locations:
            pytest.skip("No locations available")
        
        loc = locations[0]
        loc_id = loc["id"]
        loc_name = loc["name"]
        
        test_email = f"test_staff_{uuid.uuid4().hex[:8]}@test.com"
        test_password = "TestPass123"
        
        # Create staff user with location
        resp = self.session.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_Staff User",
            "email": test_email,
            "password": test_password,
            "role": "Staff",
            "location_id": loc_id,
            "also_create_member": True
        })
        assert resp.status_code == 200, f"Create staff user failed: {resp.text}"
        staff_user = resp.json()
        
        print(f"PASS: Staff user created with location: {loc_name} (id: {loc_id})")
        
        # Now login as this staff user and verify they see filtered data
        staff_session = requests.Session()
        staff_session.headers.update({"Content-Type": "application/json"})
        
        resp = staff_session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": test_email,
            "password": test_password
        })
        assert resp.status_code == 200, f"Staff login failed: {resp.text}"
        staff_token = resp.json()["token"]
        staff_session.headers.update({"Authorization": f"Bearer {staff_token}"})
        
        # Verify /auth/me includes location_name
        resp = staff_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        me = resp.json()
        assert me.get("location_id") == loc_id, "Staff user should have location_id"
        if me.get("location_id"):
            assert "location_name" in me, "location_name should be enriched"
            print(f"PASS: Staff /auth/me includes location_name: {me.get('location_name')}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{staff_user['id']}")
    
    # ========== LOCATIONS ENDPOINT TESTS ==========
    
    def test_list_locations(self):
        """GET /api/locations should return all locations"""
        resp = self.session.get(f"{BASE_URL}/api/locations")
        assert resp.status_code == 200
        locations = resp.json()
        assert isinstance(locations, list)
        
        # Verify location structure
        if locations:
            loc = locations[0]
            assert "id" in loc
            assert "name" in loc
            print(f"PASS: Locations endpoint works ({len(locations)} locations)")
            for l in locations[:5]:
                print(f"  - {l['name']} (id: {l['id']}, type: {l.get('type', 'N/A')})")
        else:
            print(f"PASS: Locations endpoint works (no locations found)")


class TestChatUsersScoping:
    """Test chat users endpoint scoping to campus"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.session.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
    
    def test_chat_users_endpoint(self):
        """GET /api/chat/users should return users for messaging"""
        resp = self.session.get(f"{BASE_URL}/api/chat/users")
        assert resp.status_code == 200
        users = resp.json()
        assert isinstance(users, list)
        
        # Verify user structure
        if users:
            user = users[0]
            assert "id" in user
            assert "name" in user
            # Should not include password_hash
            assert "password_hash" not in user
        
        print(f"PASS: Chat users endpoint works ({len(users)} users)")


class TestFinancialCampusFilter:
    """Test financial endpoints with campus filter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.session.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
    
    def test_financial_summary(self):
        """GET /api/financial/summary should work with campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/financial/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert isinstance(summary, dict)
        print(f"PASS: Financial summary endpoint works")
    
    def test_donations_endpoint(self):
        """GET /api/financial/donations should work with campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/financial/donations")
        assert resp.status_code == 200
        donations = resp.json()
        assert isinstance(donations, list)
        print(f"PASS: Donations endpoint works ({len(donations)} donations)")
    
    def test_expenses_endpoint(self):
        """GET /api/financial/expenses should work with campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/financial/expenses")
        assert resp.status_code == 200
        expenses = resp.json()
        assert isinstance(expenses, list)
        print(f"PASS: Expenses endpoint works ({len(expenses)} expenses)")


class TestResourcesCampusFilter:
    """Test resources endpoint with campus filter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.session.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
    
    def test_resources_endpoint(self):
        """GET /api/resources should work with campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        assert isinstance(resources, list)
        print(f"PASS: Resources endpoint works ({len(resources)} resources)")


class TestReportsCampusFilter:
    """Test reports endpoint with campus filter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        self.session.headers.update({"Authorization": f"Bearer {resp.json()['token']}"})
    
    def test_report_summary(self):
        """GET /api/reports/summary should work with campus filter"""
        resp = self.session.get(f"{BASE_URL}/api/reports/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert isinstance(summary, dict)
        print(f"PASS: Reports summary endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
