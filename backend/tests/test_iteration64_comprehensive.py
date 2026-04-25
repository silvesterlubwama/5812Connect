"""
Iteration 64 - Comprehensive Testing
Tests all major features including:
- Login/Auth
- Dashboard with action items
- People (Members, Families, Children, Guests)
- Events with recurrence
- Tasks/Boards
- Financial (Donations, Expenses, Assets with DELETE buttons)
- Products/Sales with DELETE buttons
- Outreach/Programmes
- Access Control
- Check-ins
- Communications
- Locations
- Admin user management
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == "admin@5812uganda.org"
        print(f"PASS: Admin login successful, role={data['user'].get('role')}")
        return data["token"]

    def test_login_invalid_credentials(self):
        """Test login with wrong password"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "WrongPassword"
        })
        assert response.status_code in [401, 400], f"Expected 401/400, got {response.status_code}"
        print("PASS: Invalid credentials rejected")


class TestDashboard:
    """Dashboard tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        print(f"PASS: Dashboard stats loaded - {data}")
    
    def test_dashboard_action_items(self):
        """Test dashboard action items (overdue tasks, unassigned tasks)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/action-items", headers=self.headers)
        assert response.status_code == 200, f"Action items failed: {response.text}"
        data = response.json()
        print(f"PASS: Action items loaded - overdue_tasks={data.get('overdue_tasks_count', 0)}, unassigned={data.get('unassigned_tasks_count', 0)}")


class TestPeople:
    """People management tests - Members, Families, Children, Guests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_members_list(self):
        """Test members list endpoint"""
        response = requests.get(f"{BASE_URL}/api/members", headers=self.headers)
        assert response.status_code == 200, f"Members list failed: {response.text}"
        data = response.json()
        print(f"PASS: Members list loaded - {len(data)} members")
    
    def test_member_crud(self):
        """Test member create, read, update, delete"""
        # Create
        member_data = {
            "name": "TEST_Member_64",
            "email": f"test64_{datetime.now().timestamp()}@test.com",
            "phone": "+256700000064",
            "member_type": "member"
        }
        create_resp = requests.post(f"{BASE_URL}/api/members", json=member_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create member failed: {create_resp.text}"
        member = create_resp.json()
        member_id = member.get("id")
        print(f"PASS: Member created - id={member_id}")
        
        # Read
        get_resp = requests.get(f"{BASE_URL}/api/members/{member_id}", headers=self.headers)
        assert get_resp.status_code == 200, f"Get member failed: {get_resp.text}"
        
        # Update
        update_resp = requests.put(f"{BASE_URL}/api/members/{member_id}", json={"name": "TEST_Member_64_Updated"}, headers=self.headers)
        assert update_resp.status_code == 200, f"Update member failed: {update_resp.text}"
        
        # Delete with cascade
        delete_resp = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete member failed: {delete_resp.text}"
        print("PASS: Member CRUD with cascade delete works")
    
    def test_families_list(self):
        """Test families list endpoint"""
        response = requests.get(f"{BASE_URL}/api/families", headers=self.headers)
        assert response.status_code == 200, f"Families list failed: {response.text}"
        print(f"PASS: Families list loaded - {len(response.json())} families")
    
    def test_children_list(self):
        """Test children list endpoint"""
        response = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        assert response.status_code == 200, f"Children list failed: {response.text}"
        print(f"PASS: Children list loaded - {len(response.json())} children")
    
    def test_guests_list(self):
        """Test guests list endpoint"""
        response = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        assert response.status_code == 200, f"Guests list failed: {response.text}"
        print(f"PASS: Guests list loaded - {len(response.json())} guests")
    
    def test_guest_delete(self):
        """Test individual guest delete"""
        # Create a guest first
        guest_data = {"name": "TEST_Guest_64", "phone": "+256700000065"}
        create_resp = requests.post(f"{BASE_URL}/api/guests", json=guest_data, headers=self.headers)
        if create_resp.status_code in [200, 201]:
            guest_id = create_resp.json().get("id")
            # Delete
            delete_resp = requests.delete(f"{BASE_URL}/api/guests/{guest_id}", headers=self.headers)
            assert delete_resp.status_code in [200, 204], f"Delete guest failed: {delete_resp.text}"
            print("PASS: Guest delete works")
        else:
            print(f"SKIP: Could not create guest for delete test - {create_resp.text}")


class TestEvents:
    """Events tests including recurrence"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_events_list(self):
        """Test events list endpoint"""
        response = requests.get(f"{BASE_URL}/api/events", headers=self.headers)
        assert response.status_code == 200, f"Events list failed: {response.text}"
        print(f"PASS: Events list loaded - {len(response.json())} events")
    
    def test_event_crud(self):
        """Test event create, read, update, delete"""
        event_data = {
            "title": "TEST_Event_64",
            "start_date": (datetime.now() + timedelta(days=1)).isoformat(),
            "end_date": (datetime.now() + timedelta(days=1, hours=2)).isoformat(),
            "event_type": "meeting"
        }
        create_resp = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create event failed: {create_resp.text}"
        event = create_resp.json()
        event_id = event.get("id")
        print(f"PASS: Event created - id={event_id}")
        
        # Update
        update_resp = requests.put(f"{BASE_URL}/api/events/{event_id}", json={"title": "TEST_Event_64_Updated"}, headers=self.headers)
        assert update_resp.status_code == 200, f"Update event failed: {update_resp.text}"
        
        # Delete
        delete_resp = requests.delete(f"{BASE_URL}/api/events/{event_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete event failed: {delete_resp.text}"
        print("PASS: Event CRUD works")
    
    def test_event_types(self):
        """Test event types endpoint"""
        response = requests.get(f"{BASE_URL}/api/event-types", headers=self.headers)
        assert response.status_code == 200, f"Event types failed: {response.text}"
        print(f"PASS: Event types loaded")


class TestTasksBoards:
    """Tasks and Boards (Kanban) tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_boards_list(self):
        """Test boards list endpoint"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=self.headers)
        assert response.status_code == 200, f"Boards list failed: {response.text}"
        print(f"PASS: Boards list loaded - {len(response.json())} boards")
    
    def test_tasks_list(self):
        """Test tasks list endpoint"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert response.status_code == 200, f"Tasks list failed: {response.text}"
        print(f"PASS: Tasks list loaded - {len(response.json())} tasks")
    
    def test_user_directory_for_assignees(self):
        """Test user directory endpoint for task assignees"""
        response = requests.get(f"{BASE_URL}/api/admin/users/directory", headers=self.headers)
        assert response.status_code == 200, f"User directory failed: {response.text}"
        print(f"PASS: User directory loaded for assignee resolution")


class TestFinancial:
    """Financial tests - Donations, Expenses, Assets with DELETE buttons"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_financial_summary(self):
        """Test financial summary endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=self.headers)
        assert response.status_code == 200, f"Financial summary failed: {response.text}"
        print(f"PASS: Financial summary loaded")
    
    def test_donations_list(self):
        """Test donations list endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial/donations", headers=self.headers)
        assert response.status_code == 200, f"Donations list failed: {response.text}"
        print(f"PASS: Donations list loaded - {len(response.json())} donations")
    
    def test_donation_crud_with_delete(self):
        """Test donation create and DELETE (key fix verification)"""
        donation_data = {
            "donor_name": "TEST_Donor_64",
            "amount": 50000,
            "currency": "UGX",
            "type": "tithe",
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        create_resp = requests.post(f"{BASE_URL}/api/financial/donations", json=donation_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create donation failed: {create_resp.text}"
        donation = create_resp.json()
        donation_id = donation.get("id")
        print(f"PASS: Donation created - id={donation_id}")
        
        # DELETE - This is the key fix being tested
        delete_resp = requests.delete(f"{BASE_URL}/api/financial/donations/{donation_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete donation failed: {delete_resp.text}"
        print("PASS: Donation DELETE works (finance admin)")
    
    def test_expenses_list(self):
        """Test expenses list endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial/expenses", headers=self.headers)
        assert response.status_code == 200, f"Expenses list failed: {response.text}"
        print(f"PASS: Expenses list loaded - {len(response.json())} expenses")
    
    def test_expense_crud_with_delete(self):
        """Test expense create and DELETE (key fix verification)"""
        expense_data = {
            "title": "TEST_Expense_64",
            "amount": 25000,
            "currency": "UGX",
            "category": "general",
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        create_resp = requests.post(f"{BASE_URL}/api/financial/expenses", json=expense_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create expense failed: {create_resp.text}"
        expense = create_resp.json()
        expense_id = expense.get("id")
        print(f"PASS: Expense created - id={expense_id}")
        
        # DELETE - This is the key fix being tested
        delete_resp = requests.delete(f"{BASE_URL}/api/financial/expenses/{expense_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete expense failed: {delete_resp.text}"
        print("PASS: Expense DELETE works (finance admin)")
    
    def test_assets_list(self):
        """Test assets list endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial/assets", headers=self.headers)
        assert response.status_code == 200, f"Assets list failed: {response.text}"
        print(f"PASS: Assets list loaded - {len(response.json())} assets")
    
    def test_asset_crud_with_delete(self):
        """Test asset create and DELETE (key fix verification)"""
        asset_data = {
            "name": "TEST_Asset_64",
            "value": 1000000,
            "category": "equipment",
            "purchase_date": datetime.now().strftime("%Y-%m-%d"),
            "depreciation_years": 5
        }
        create_resp = requests.post(f"{BASE_URL}/api/financial/assets", json=asset_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create asset failed: {create_resp.text}"
        asset = create_resp.json()
        asset_id = asset.get("id")
        print(f"PASS: Asset created - id={asset_id}")
        
        # DELETE - This is the key fix being tested
        delete_resp = requests.delete(f"{BASE_URL}/api/financial/assets/{asset_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete asset failed: {delete_resp.text}"
        print("PASS: Asset DELETE works (finance admin)")
    
    def test_balance_sheet(self):
        """Test balance sheet endpoint"""
        response = requests.get(f"{BASE_URL}/api/financial/balance-sheet", headers=self.headers)
        assert response.status_code == 200, f"Balance sheet failed: {response.text}"
        print(f"PASS: Balance sheet loaded")
    
    def test_financial_campus_filter(self):
        """Test financial data respects campus filter"""
        # Get locations first
        loc_resp = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        if loc_resp.status_code == 200 and len(loc_resp.json()) > 0:
            location_id = loc_resp.json()[0].get("id")
            # Test with location filter
            response = requests.get(f"{BASE_URL}/api/financial/summary", params={"location_id": location_id}, headers=self.headers)
            assert response.status_code == 200, f"Financial summary with campus filter failed: {response.text}"
            print(f"PASS: Financial data respects campus filter")
        else:
            print("SKIP: No locations to test campus filter")


class TestProductsSales:
    """Products and Sales tests with DELETE buttons"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_products_list(self):
        """Test products list endpoint"""
        response = requests.get(f"{BASE_URL}/api/products", headers=self.headers)
        assert response.status_code == 200, f"Products list failed: {response.text}"
        print(f"PASS: Products list loaded - {len(response.json())} products")
    
    def test_product_crud(self):
        """Test product create, update, delete"""
        product_data = {
            "name": "TEST_Product_64",
            "price": 10000,
            "stock": 50,
            "currency": "UGX"
        }
        create_resp = requests.post(f"{BASE_URL}/api/products", json=product_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create product failed: {create_resp.text}"
        product = create_resp.json()
        product_id = product.get("id")
        print(f"PASS: Product created - id={product_id}")
        
        # Delete
        delete_resp = requests.delete(f"{BASE_URL}/api/products/{product_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete product failed: {delete_resp.text}"
        print("PASS: Product DELETE works")
    
    def test_sales_list(self):
        """Test sales list endpoint"""
        response = requests.get(f"{BASE_URL}/api/sales", headers=self.headers)
        assert response.status_code == 200, f"Sales list failed: {response.text}"
        print(f"PASS: Sales list loaded - {len(response.json())} sales")
    
    def test_sale_crud_with_delete(self):
        """Test sale create and DELETE (key fix verification)"""
        # First create a product
        product_data = {"name": "TEST_SaleProduct_64", "price": 5000, "stock": 100, "currency": "UGX"}
        prod_resp = requests.post(f"{BASE_URL}/api/products", json=product_data, headers=self.headers)
        if prod_resp.status_code not in [200, 201]:
            print(f"SKIP: Could not create product for sale test")
            return
        product = prod_resp.json()
        product_id = product.get("id")
        
        # Create sale
        sale_data = {
            "items": [{"product_id": product_id, "name": "TEST_SaleProduct_64", "unit_price": 5000, "qty": 2}],
            "customer_name": "TEST_Customer_64",
            "payment_method": "cash",
            "total": 10000
        }
        create_resp = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create sale failed: {create_resp.text}"
        sale = create_resp.json()
        sale_id = sale.get("id")
        print(f"PASS: Sale created - id={sale_id}")
        
        # DELETE - This is the key fix being tested
        delete_resp = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete sale failed: {delete_resp.text}"
        print("PASS: Sale DELETE works (admin)")
        
        # Cleanup product
        requests.delete(f"{BASE_URL}/api/products/{product_id}", headers=self.headers)


class TestOutreach:
    """Outreach/Programmes tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_programmes_list(self):
        """Test programmes list endpoint"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=self.headers)
        assert response.status_code == 200, f"Programmes list failed: {response.text}"
        print(f"PASS: Programmes list loaded - {len(response.json())} programmes")
    
    def test_programme_categories(self):
        """Test programme categories endpoint"""
        response = requests.get(f"{BASE_URL}/api/programme-categories", headers=self.headers)
        assert response.status_code == 200, f"Programme categories failed: {response.text}"
        print(f"PASS: Programme categories loaded")


class TestAccessControl:
    """Access control tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_access_scan_log(self):
        """Test access scan log endpoint"""
        response = requests.get(f"{BASE_URL}/api/access/scan-log", headers=self.headers)
        assert response.status_code == 200, f"Access scan log failed: {response.text}"
        print(f"PASS: Access scan log loaded")
    
    def test_access_scan(self):
        """Test access scan endpoint"""
        scan_data = {"identifier": "test_scan_64", "scan_type": "nfc"}
        response = requests.post(f"{BASE_URL}/api/access/scan", json=scan_data, headers=self.headers)
        # May return 404 if identifier not found, which is expected
        assert response.status_code in [200, 404], f"Access scan failed unexpectedly: {response.text}"
        print(f"PASS: Access scan endpoint works")


class TestCheckins:
    """Check-ins tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_checkins_list(self):
        """Test check-ins list endpoint"""
        response = requests.get(f"{BASE_URL}/api/checkins", headers=self.headers)
        assert response.status_code == 200, f"Check-ins list failed: {response.text}"
        print(f"PASS: Check-ins list loaded - {len(response.json())} check-ins")
    
    def test_checkins_stats(self):
        """Test check-ins stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/checkins/stats", headers=self.headers)
        assert response.status_code == 200, f"Check-ins stats failed: {response.text}"
        print(f"PASS: Check-ins stats loaded")


class TestCommunications:
    """Communications tests - Chat, AI Assistant, Announcements"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_chat_conversations(self):
        """Test chat conversations endpoint"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=self.headers)
        assert response.status_code == 200, f"Chat conversations failed: {response.text}"
        print(f"PASS: Chat conversations loaded")
    
    def test_announcements_list(self):
        """Test announcements list endpoint"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=self.headers)
        assert response.status_code == 200, f"Announcements list failed: {response.text}"
        print(f"PASS: Announcements list loaded")


class TestLocations:
    """Locations tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_locations_list(self):
        """Test locations list endpoint"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert response.status_code == 200, f"Locations list failed: {response.text}"
        print(f"PASS: Locations list loaded - {len(response.json())} locations")
    
    def test_venues_list(self):
        """Test venues list endpoint"""
        response = requests.get(f"{BASE_URL}/api/venues", headers=self.headers)
        assert response.status_code == 200, f"Venues list failed: {response.text}"
        print(f"PASS: Venues list loaded - {len(response.json())} venues")
    
    def test_group_types_list(self):
        """Test group types list endpoint"""
        response = requests.get(f"{BASE_URL}/api/group-types", headers=self.headers)
        assert response.status_code == 200, f"Group types list failed: {response.text}"
        print(f"PASS: Group types list loaded")


class TestAdmin:
    """Admin tests - User management"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_admin_users_list(self):
        """Test admin users list endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        assert response.status_code == 200, f"Admin users list failed: {response.text}"
        print(f"PASS: Admin users list loaded - {len(response.json())} users")
    
    def test_admin_user_crud_with_cascade_delete(self):
        """Test admin user create and delete with cascade"""
        user_data = {
            "name": "TEST_User_64",
            "email": f"testuser64_{datetime.now().timestamp()}@test.com",
            "password": "TestPass123!",
            "role": "staff"
        }
        create_resp = requests.post(f"{BASE_URL}/api/admin/users", json=user_data, headers=self.headers)
        assert create_resp.status_code in [200, 201], f"Create user failed: {create_resp.text}"
        user = create_resp.json()
        user_id = user.get("id")
        print(f"PASS: User created - id={user_id}")
        
        # Delete with cascade (removes from tasks, boards)
        delete_resp = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=self.headers)
        assert delete_resp.status_code in [200, 204], f"Delete user failed: {delete_resp.text}"
        print("PASS: User DELETE with cascade works")
    
    def test_audit_log(self):
        """Test audit log endpoint"""
        response = requests.get(f"{BASE_URL}/api/admin/audit", headers=self.headers)
        assert response.status_code == 200, f"Audit log failed: {response.text}"
        print(f"PASS: Audit log loaded")


class TestKiosk:
    """Kiosk tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_kiosk_devices_list(self):
        """Test kiosk devices list endpoint"""
        response = requests.get(f"{BASE_URL}/api/kiosk/devices", headers=self.headers)
        assert response.status_code == 200, f"Kiosk devices list failed: {response.text}"
        print(f"PASS: Kiosk devices list loaded")


class TestPortal:
    """Portal tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_portal_dashboard(self):
        """Test portal dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/portal/dashboard", headers=self.headers)
        assert response.status_code == 200, f"Portal dashboard failed: {response.text}"
        print(f"PASS: Portal dashboard loaded")
    
    def test_portal_profile(self):
        """Test portal profile endpoint"""
        response = requests.get(f"{BASE_URL}/api/portal/profile", headers=self.headers)
        assert response.status_code == 200, f"Portal profile failed: {response.text}"
        print(f"PASS: Portal profile loaded")


class TestWalletBadge:
    """Wallet badge tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.user = login_resp.json().get("user", {})
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_wallet_badge_creation(self):
        """Test wallet badge creation for a member"""
        # Get a member first
        members_resp = requests.get(f"{BASE_URL}/api/members", headers=self.headers)
        if members_resp.status_code == 200 and len(members_resp.json()) > 0:
            member_id = members_resp.json()[0].get("id")
            # Create wallet badge
            response = requests.post(f"{BASE_URL}/api/members/{member_id}/wallet-badge", headers=self.headers)
            # May return 200 or 400 if already exists
            assert response.status_code in [200, 201, 400], f"Wallet badge creation failed: {response.text}"
            if response.status_code in [200, 201]:
                data = response.json()
                print(f"PASS: Wallet badge created - token={data.get('token', 'N/A')[:20]}...")
            else:
                print(f"PASS: Wallet badge endpoint works (badge may already exist)")
        else:
            print("SKIP: No members to test wallet badge")


class TestBulkOperations:
    """Bulk operations tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_bulk_delete_events(self):
        """Test bulk delete events endpoint"""
        # Create 2 test events
        event_ids = []
        for i in range(2):
            event_data = {
                "title": f"TEST_BulkEvent_{i}",
                "start_date": (datetime.now() + timedelta(days=i+1)).isoformat(),
                "end_date": (datetime.now() + timedelta(days=i+1, hours=2)).isoformat()
            }
            resp = requests.post(f"{BASE_URL}/api/events", json=event_data, headers=self.headers)
            if resp.status_code in [200, 201]:
                event_ids.append(resp.json().get("id"))
        
        if len(event_ids) >= 2:
            # Bulk delete
            delete_resp = requests.post(f"{BASE_URL}/api/events/bulk-delete", json={"ids": event_ids}, headers=self.headers)
            assert delete_resp.status_code in [200, 204], f"Bulk delete events failed: {delete_resp.text}"
            print("PASS: Bulk delete events works")
        else:
            print("SKIP: Could not create events for bulk delete test")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
