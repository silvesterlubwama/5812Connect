"""
Iteration 10 Backend Tests - 58:12 Global Connect CRM
Tests for: Events, Event Types, Tasks (Trello import), Admin User Management,
Financial Expense Approval, Check-ins (PIN/Checkout), Programmes, Resource Types, Location Venues
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-self-service-1.preview.emergentagent.com')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Login with admin@5812uganda.org / Admin@5812"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def admin2_token(self):
        """Login with admin@5812global.org / Admin@1234"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    def test_login_admin_uganda(self, admin_token):
        """Test login with admin@5812uganda.org / Admin@5812"""
        assert admin_token is not None
        print("✓ Login with admin@5812uganda.org works")
    
    def test_login_admin_global(self, admin2_token):
        """Test login with admin@5812global.org / Admin@1234"""
        assert admin2_token is not None
        print("✓ Login with admin@5812global.org works")


class TestEvents:
    """Events CRUD and features"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_events(self, auth_headers):
        """GET /api/events should return events"""
        response = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/events returns {len(data)} events")
    
    def test_create_event_with_visibility(self, auth_headers):
        """POST /api/events with visibility field"""
        event_data = {
            "title": f"TEST_Event_{uuid.uuid4().hex[:6]}",
            "type": "meeting",
            "date": "2026-05-01",
            "time": "10:00",
            "location": "Test Location",
            "capacity": 50,
            "visibility": "internal",
            "is_public": False
        }
        response = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["visibility"] == "internal"
        assert data["title"] == event_data["title"]
        print(f"✓ POST /api/events creates event with visibility={data['visibility']}")
        return data["id"]
    
    def test_duplicate_event(self, auth_headers):
        """POST /api/events/{id}/duplicate"""
        # First get an existing event
        events_resp = requests.get(f"{BASE_URL}/api/events", headers=auth_headers)
        events = events_resp.json()
        if not events:
            pytest.skip("No events to duplicate")
        
        event_id = events[0]["id"]
        response = requests.post(f"{BASE_URL}/api/events/{event_id}/duplicate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "(Copy)" in data["title"]
        print(f"✓ POST /api/events/{event_id}/duplicate creates '{data['title']}'")


class TestEventTypes:
    """Event Types management"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_event_types(self, auth_headers):
        """GET /api/event-types"""
        response = requests.get(f"{BASE_URL}/api/event-types", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Should have default event types"
        print(f"✓ GET /api/event-types returns {len(data)} types")
    
    def test_create_event_type(self, auth_headers):
        """POST /api/event-types"""
        type_data = {
            "name": f"test_type_{uuid.uuid4().hex[:4]}",
            "label": "Test Type",
            "color": "#ff5733"
        }
        response = requests.post(f"{BASE_URL}/api/event-types", json=type_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "Test Type"
        print(f"✓ POST /api/event-types creates type '{data['name']}'")
        return data["id"]
    
    def test_delete_event_type(self, auth_headers):
        """DELETE /api/event-types/{id}"""
        # Create one to delete
        type_data = {"name": f"delete_me_{uuid.uuid4().hex[:4]}", "label": "Delete Me", "color": "#000000"}
        create_resp = requests.post(f"{BASE_URL}/api/event-types", json=type_data, headers=auth_headers)
        type_id = create_resp.json()["id"]
        
        response = requests.delete(f"{BASE_URL}/api/event-types/{type_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"✓ DELETE /api/event-types/{type_id} works")


class TestTasks:
    """Tasks CRUD and Trello import"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_tasks(self, auth_headers):
        """GET /api/tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/tasks returns {len(data)} tasks")
    
    def test_import_trello(self, auth_headers):
        """POST /api/tasks/import-trello"""
        trello_data = {
            "lists": [
                {"id": "list1", "name": "To Do"},
                {"id": "list2", "name": "In Progress"}
            ],
            "cards": [
                {"name": "TEST_Trello Card 1", "desc": "Imported from Trello", "idList": "list1", "labels": [{"name": "urgent"}]},
                {"name": "TEST_Trello Card 2", "desc": "Another card", "idList": "list2", "labels": []}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/tasks/import-trello", json=trello_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2
        print(f"✓ POST /api/tasks/import-trello imported {data['imported']} cards")


class TestAdminUserManagement:
    """Admin user management: list, edit, password reset, bulk ops"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_list_all_users(self, auth_headers):
        """GET /api/admin/users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2, "Should have at least 2 admin users"
        print(f"✓ GET /api/admin/users returns {len(data)} users")
        return data
    
    def test_edit_user_profile(self, auth_headers):
        """PUT /api/admin/users/{id}"""
        # Get users first
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_resp.json()
        if not users:
            pytest.skip("No users to edit")
        
        user_id = users[0]["id"]
        update_data = {"notes": f"Updated by test at {uuid.uuid4().hex[:6]}"}
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == update_data["notes"]
        print(f"✓ PUT /api/admin/users/{user_id} updates user profile")
    
    def test_reset_password(self, auth_headers):
        """POST /api/admin/users/{id}/reset-password"""
        # Get users first
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_resp.json()
        
        # Find a non-admin user or use the second admin
        target_user = None
        for u in users:
            if u["email"] == "admin@5812global.org":
                target_user = u
                break
        
        if not target_user:
            pytest.skip("No suitable user for password reset test")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users/{target_user['id']}/reset-password",
            json={"new_password": "Admin@1234"},  # Reset to original
            headers=auth_headers
        )
        assert response.status_code == 200
        print(f"✓ POST /api/admin/users/{target_user['id']}/reset-password works")
    
    def test_bulk_update_roles(self, auth_headers):
        """POST /api/admin/users/bulk-update"""
        # Get users
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_resp.json()
        
        if len(users) < 1:
            pytest.skip("Not enough users for bulk update")
        
        # Just update notes for one user (safe operation)
        user_ids = [users[0]["id"]]
        response = requests.post(
            f"{BASE_URL}/api/admin/users/bulk-update",
            json={"user_ids": user_ids, "updates": {"notes": "Bulk updated"}},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "updated" in data
        print(f"✓ POST /api/admin/users/bulk-update updated {data['updated']} users")
    
    def test_bulk_delete_validation(self, auth_headers):
        """POST /api/admin/users/bulk-delete - test validation"""
        # Test with empty list
        response = requests.post(
            f"{BASE_URL}/api/admin/users/bulk-delete",
            json={"user_ids": []},
            headers=auth_headers
        )
        assert response.status_code == 400
        print("✓ POST /api/admin/users/bulk-delete validates empty list")


class TestFinancialExpenseApproval:
    """Financial expense approval workflow"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_pending_expenses(self, auth_headers):
        """GET /api/financial/expenses/pending"""
        response = requests.get(f"{BASE_URL}/api/financial/expenses/pending", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/financial/expenses/pending returns {len(data)} pending expenses")
    
    def test_create_and_approve_expense(self, auth_headers):
        """Create expense, then approve it"""
        # Create a pending expense
        expense_data = {
            "title": f"TEST_Expense_{uuid.uuid4().hex[:6]}",
            "amount": 50000,
            "currency": "UGX",
            "category": "supplies",
            "date": "2026-01-15"
        }
        create_resp = requests.post(f"{BASE_URL}/api/financial/expenses", json=expense_data, headers=auth_headers)
        assert create_resp.status_code == 200
        expense = create_resp.json()
        expense_id = expense["id"]
        
        # Approve it
        approve_resp = requests.put(
            f"{BASE_URL}/api/financial/expenses/{expense_id}/approve",
            json={"comment": "Approved by test"},
            headers=auth_headers
        )
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data["status"] == "approved"
        print(f"✓ PUT /api/financial/expenses/{expense_id}/approve works")
    
    def test_create_and_reject_expense(self, auth_headers):
        """Create expense, then reject it"""
        expense_data = {
            "title": f"TEST_Reject_{uuid.uuid4().hex[:6]}",
            "amount": 100000,
            "currency": "UGX",
            "category": "general"
        }
        create_resp = requests.post(f"{BASE_URL}/api/financial/expenses", json=expense_data, headers=auth_headers)
        expense_id = create_resp.json()["id"]
        
        reject_resp = requests.put(
            f"{BASE_URL}/api/financial/expenses/{expense_id}/reject",
            json={"comment": "Rejected by test"},
            headers=auth_headers
        )
        assert reject_resp.status_code == 200
        data = reject_resp.json()
        assert data["status"] == "rejected"
        print(f"✓ PUT /api/financial/expenses/{expense_id}/reject works")


class TestCheckIns:
    """Check-ins: PIN check-in and admin checkout"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_pin_checkin(self, auth_headers):
        """POST /api/checkins/pin - PIN-based check-in"""
        # Use mem_002 with pin 1234
        response = requests.post(
            f"{BASE_URL}/api/checkins/pin",
            json={"pin": "1234", "action": "checkin"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "member" in data or "message" in data
        print(f"✓ POST /api/checkins/pin works - {data.get('message', 'checked in')}")
    
    def test_pin_checkin_invalid(self, auth_headers):
        """POST /api/checkins/pin - Invalid PIN"""
        response = requests.post(
            f"{BASE_URL}/api/checkins/pin",
            json={"pin": "9999", "action": "checkin"},
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ POST /api/checkins/pin returns 404 for invalid PIN")
    
    def test_admin_checkout(self, auth_headers):
        """POST /api/checkins/{id}/checkout - Admin checkout"""
        # First create a check-in
        checkin_data = {
            "member_name": "Test Checkout Person",
            "type": "visitor",
            "method": "manual"
        }
        create_resp = requests.post(f"{BASE_URL}/api/checkins", json=checkin_data, headers=auth_headers)
        assert create_resp.status_code == 200
        checkin_id = create_resp.json()["id"]
        
        # Now checkout
        checkout_resp = requests.post(f"{BASE_URL}/api/checkins/{checkin_id}/checkout", headers=auth_headers)
        assert checkout_resp.status_code == 200
        print(f"✓ POST /api/checkins/{checkin_id}/checkout works")
    
    def test_checkout_already_out(self, auth_headers):
        """POST /api/checkins/{id}/checkout - Already checked out"""
        # Create and checkout
        checkin_data = {"member_name": "Already Out", "type": "visitor", "method": "manual"}
        create_resp = requests.post(f"{BASE_URL}/api/checkins", json=checkin_data, headers=auth_headers)
        checkin_id = create_resp.json()["id"]
        
        # First checkout
        requests.post(f"{BASE_URL}/api/checkins/{checkin_id}/checkout", headers=auth_headers)
        
        # Second checkout should fail
        response = requests.post(f"{BASE_URL}/api/checkins/{checkin_id}/checkout", headers=auth_headers)
        assert response.status_code == 400
        print("✓ POST /api/checkins/{id}/checkout returns 400 if already out")


class TestProgrammes:
    """Programmes: categories, duplicate, recurring events"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_programme_categories(self, auth_headers):
        """GET /api/programme-categories"""
        response = requests.get(f"{BASE_URL}/api/programme-categories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✓ GET /api/programme-categories returns {len(data)} categories")
    
    def test_create_programme_category(self, auth_headers):
        """POST /api/programme-categories"""
        cat_data = {
            "name": f"test_cat_{uuid.uuid4().hex[:4]}",
            "label": "Test Category",
            "color": "#123456"
        }
        response = requests.post(f"{BASE_URL}/api/programme-categories", json=cat_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "Test Category"
        print(f"✓ POST /api/programme-categories creates '{data['name']}'")
    
    def test_duplicate_programme(self, auth_headers):
        """POST /api/outreach/programs/{id}/duplicate"""
        # Get or create a programme
        progs_resp = requests.get(f"{BASE_URL}/api/outreach/programs", headers=auth_headers)
        progs = progs_resp.json()
        
        if not progs:
            # Create one
            prog_data = {
                "name": f"TEST_Programme_{uuid.uuid4().hex[:6]}",
                "category": "community",
                "status": "active"
            }
            create_resp = requests.post(f"{BASE_URL}/api/outreach/programs", json=prog_data, headers=auth_headers)
            prog_id = create_resp.json()["id"]
        else:
            prog_id = progs[0]["id"]
        
        response = requests.post(f"{BASE_URL}/api/outreach/programs/{prog_id}/duplicate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "(Copy)" in data["name"]
        print(f"✓ POST /api/outreach/programs/{prog_id}/duplicate creates '{data['name']}'")
    
    def test_generate_recurring_events(self, auth_headers):
        """POST /api/outreach/programs/{id}/generate-events"""
        # Create a recurring programme
        prog_data = {
            "name": f"TEST_Recurring_{uuid.uuid4().hex[:6]}",
            "category": "community",
            "status": "active",
            "is_recurring": True,
            "recurrence_pattern": "saturday",
            "recurrence_day": 2,
            "recurrence_time": "09:00",
            "recurrence_end_time": "12:00"
        }
        create_resp = requests.post(f"{BASE_URL}/api/outreach/programs", json=prog_data, headers=auth_headers)
        prog_id = create_resp.json()["id"]
        
        # Generate events
        gen_data = {
            "months_ahead": 2,
            "nth_day": 2,
            "day_of_week": "saturday",
            "time": "09:00",
            "end_time": "12:00"
        }
        response = requests.post(f"{BASE_URL}/api/outreach/programs/{prog_id}/generate-events", json=gen_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "created" in data
        print(f"✓ POST /api/outreach/programs/{prog_id}/generate-events created {data['created']} events")


class TestResourceTypes:
    """Resource types management"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_resource_types(self, auth_headers):
        """GET /api/resource-types"""
        response = requests.get(f"{BASE_URL}/api/resource-types", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✓ GET /api/resource-types returns {len(data)} types")
    
    def test_create_resource_type(self, auth_headers):
        """POST /api/resource-types"""
        type_data = {
            "name": f"test_rtype_{uuid.uuid4().hex[:4]}",
            "label": "Test Resource Type",
            "icon": "box"
        }
        response = requests.post(f"{BASE_URL}/api/resource-types", json=type_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "Test Resource Type"
        print(f"✓ POST /api/resource-types creates '{data['name']}'")


class TestLocationVenues:
    """Location venue picker"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_location_venues(self, auth_headers):
        """GET /api/locations/{id}/venues"""
        # Get locations first
        locs_resp = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locs = locs_resp.json()
        
        if not locs:
            pytest.skip("No locations available")
        
        loc_id = locs[0]["id"]
        response = requests.get(f"{BASE_URL}/api/locations/{loc_id}/venues", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "venues" in data
        assert "sublocations" in data
        print(f"✓ GET /api/locations/{loc_id}/venues returns venues and sublocations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
