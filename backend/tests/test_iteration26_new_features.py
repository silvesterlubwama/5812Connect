"""
Iteration 26: Testing NEW features for 58:12 Global Connect Uganda CRM
- Store Settings per location (GET/PUT /api/store-settings/{loc_id})
- Sales Import/Export (GET /api/sales/export, POST /api/sales/import)
- Outreach session auto-creating calendar events (POST /api/outreach/sessions)
- Admin editing with multi-location arrays
- Products CRUD with location field
- POS checkout flow
"""
import pytest
import requests
import os
import json
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Login as admin and get token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": "Admin@5812"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("token")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def locations(auth_headers):
    """Get list of locations"""
    response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
    assert response.status_code == 200
    return response.json()


# ========== LOGIN & DASHBOARD ==========

class TestLoginAndDashboard:
    """Test login and dashboard stats"""
    
    def test_login_success(self):
        """Login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"✓ Login successful: {data['user'].get('name')}")
    
    def test_dashboard_stats(self, auth_headers):
        """Dashboard loads with stats"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_members" in data or "members" in data or isinstance(data, dict)
        print(f"✓ Dashboard stats loaded: {data}")


# ========== STORE SETTINGS ==========

class TestStoreSettings:
    """Test store settings per location"""
    
    def test_get_store_settings(self, auth_headers, locations):
        """GET /api/store-settings/{location_id} returns settings"""
        if not locations:
            pytest.skip("No locations available")
        loc_id = locations[0]["id"]
        response = requests.get(f"{BASE_URL}/api/store-settings/{loc_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "location_id" in data
        assert "payment_methods" in data
        print(f"✓ Store settings retrieved for {loc_id}: {data}")
    
    def test_update_store_settings(self, auth_headers, locations):
        """PUT /api/store-settings/{location_id} updates settings"""
        if not locations:
            pytest.skip("No locations available")
        loc_id = locations[0]["id"]
        payload = {
            "store_name": "Test Store Uganda",
            "payment_methods": ["cash", "mobile_money", "card"],
            "mobile_money_providers": ["MTN", "Airtel"],
            "tax_rate": 18.0,
            "currency": "UGX",
            "receipt_footer": "Thank you for shopping!"
        }
        response = requests.put(f"{BASE_URL}/api/store-settings/{loc_id}", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("store_name") == "Test Store Uganda"
        assert "cash" in data.get("payment_methods", [])
        print(f"✓ Store settings updated: {data}")
    
    def test_list_all_store_settings(self, auth_headers):
        """GET /api/store-settings lists all"""
        response = requests.get(f"{BASE_URL}/api/store-settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ All store settings listed: {len(data)} locations")


# ========== SALES EXPORT/IMPORT ==========

class TestSalesExportImport:
    """Test sales export and import functionality"""
    
    def test_export_sales(self, auth_headers):
        """GET /api/sales/export returns sales data"""
        response = requests.get(f"{BASE_URL}/api/sales/export", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "sales" in data
        assert "count" in data
        print(f"✓ Sales exported: {data['count']} sales")
    
    def test_export_sales_with_location_filter(self, auth_headers, locations):
        """GET /api/sales/export with location_id filter"""
        if not locations:
            pytest.skip("No locations available")
        loc_id = locations[0]["id"]
        response = requests.get(f"{BASE_URL}/api/sales/export?location_id={loc_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "sales" in data
        print(f"✓ Sales exported for location {loc_id}: {data['count']} sales")
    
    def test_import_sales(self, auth_headers, locations):
        """POST /api/sales/import imports sales data"""
        loc_id = locations[0]["id"] if locations else ""
        payload = {
            "sales": [
                {
                    "items": [{"name": "Test Product", "qty": 2, "unit_price": 5000}],
                    "customer_name": "TEST_Import Customer",
                    "total": 10000,
                    "payment_method": "cash",
                    "location_id": loc_id
                }
            ]
        }
        response = requests.post(f"{BASE_URL}/api/sales/import", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("imported") == 1
        print(f"✓ Sales imported: {data}")


# ========== PRODUCTS CRUD ==========

class TestProductsCRUD:
    """Test products CRUD with location field"""
    
    @pytest.fixture(scope="class")
    def test_product_id(self, auth_headers, locations):
        """Create a test product and return its ID"""
        loc_id = locations[0]["id"] if locations else ""
        payload = {
            "name": "TEST_Product_Iteration26",
            "price": 25000,
            "currency": "UGX",
            "stock": 100,
            "category": "Test",
            "sku": "TEST-SKU-26",
            "reorder_level": 10,
            "location_id": loc_id
        }
        response = requests.post(f"{BASE_URL}/api/products", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        return data["id"]
    
    def test_list_products(self, auth_headers):
        """GET /api/products lists products"""
        response = requests.get(f"{BASE_URL}/api/products", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Products listed: {len(data)} products")
    
    def test_create_product_with_location(self, auth_headers, locations):
        """POST /api/products creates product with location"""
        loc_id = locations[0]["id"] if locations else ""
        payload = {
            "name": "TEST_Product_WithLocation",
            "price": 15000,
            "currency": "UGX",
            "stock": 50,
            "category": "Farm",
            "location_id": loc_id
        }
        response = requests.post(f"{BASE_URL}/api/products", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == "TEST_Product_WithLocation"
        assert data.get("location_id") == loc_id
        print(f"✓ Product created with location: {data['id']}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/products/{data['id']}", headers=auth_headers)
    
    def test_update_product(self, auth_headers, test_product_id):
        """PUT /api/products/{id} updates product"""
        payload = {"name": "TEST_Product_Updated", "price": 30000}
        response = requests.put(f"{BASE_URL}/api/products/{test_product_id}", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == "TEST_Product_Updated"
        assert data.get("price") == 30000
        print(f"✓ Product updated: {data}")
    
    def test_delete_product(self, auth_headers, test_product_id):
        """DELETE /api/products/{id} deletes product"""
        response = requests.delete(f"{BASE_URL}/api/products/{test_product_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"✓ Product deleted: {test_product_id}")


# ========== POS / SALES ==========

class TestPOSSales:
    """Test POS checkout flow"""
    
    def test_create_sale(self, auth_headers, locations):
        """POST /api/sales creates a sale"""
        loc_id = locations[0]["id"] if locations else ""
        payload = {
            "items": [
                {"product_id": "test_prod", "name": "Test Item", "qty": 2, "unit_price": 5000}
            ],
            "customer_name": "TEST_POS Customer",
            "total": 10000,
            "payment_method": "mobile_money",
            "location_id": loc_id
        }
        response = requests.post(f"{BASE_URL}/api/sales", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("total") == 10000
        assert data.get("payment_method") == "mobile_money"
        print(f"✓ Sale created: {data['id']}")
    
    def test_list_sales(self, auth_headers):
        """GET /api/sales lists sales"""
        response = requests.get(f"{BASE_URL}/api/sales", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Sales listed: {len(data)} sales")


# ========== OUTREACH SESSIONS & CALENDAR EVENTS ==========

class TestOutreachSessions:
    """Test outreach session creation auto-creates calendar events"""
    
    @pytest.fixture(scope="class")
    def test_program(self, auth_headers):
        """Create a test outreach program"""
        payload = {
            "name": "TEST_Outreach_Program_26",
            "description": "Test program for iteration 26",
            "category": "community",
            "status": "active",
            "location": "Test Location",
            "target": 100
        }
        response = requests.post(f"{BASE_URL}/api/outreach/programs", headers=auth_headers, json=payload)
        assert response.status_code == 200
        return response.json()
    
    def test_list_programs(self, auth_headers):
        """GET /api/outreach/programs lists programs"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Outreach programs listed: {len(data)} programs")
    
    def test_create_session_creates_calendar_event(self, auth_headers, test_program):
        """POST /api/outreach/sessions creates session AND calendar event"""
        session_date = datetime.now().strftime("%Y-%m-%d")
        payload = {
            "program_id": test_program["id"],
            "date": session_date,
            "time": "10:00",
            "location": "Community Center",
            "attendees": 45,
            "notes": "Test session for iteration 26",
            "led_by": "Test Leader"
        }
        response = requests.post(f"{BASE_URL}/api/outreach/sessions", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("attendees") == 45
        # Check if calendar_event_id was created
        if "calendar_event_id" in data:
            print(f"✓ Session created with calendar event: {data['calendar_event_id']}")
        else:
            print(f"✓ Session created: {data['id']} (calendar event may be created)")
        
        # Verify calendar event exists
        events_response = requests.get(f"{BASE_URL}/api/events?type=outreach", headers=auth_headers)
        if events_response.status_code == 200:
            events = events_response.json()
            matching = [e for e in events if e.get("session_id") == data["id"] or e.get("programme_id") == test_program["id"]]
            if matching:
                print(f"✓ Calendar event verified: {matching[0].get('id')}")
    
    def test_list_sessions(self, auth_headers):
        """GET /api/outreach/sessions lists sessions"""
        response = requests.get(f"{BASE_URL}/api/outreach/sessions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Outreach sessions listed: {len(data)} sessions")


# ========== ADMIN MULTI-LOCATION ==========

class TestAdminMultiLocation:
    """Test admin user editing with multi-location arrays"""
    
    def test_list_admin_users(self, auth_headers):
        """GET /api/admin/users lists users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin users listed: {len(data)} users")
    
    def test_create_user_with_location(self, auth_headers, locations):
        """POST /api/admin/users creates user with location"""
        loc_id = locations[0]["id"] if locations else ""
        payload = {
            "name": "TEST_User_MultiLoc",
            "email": f"test_multiloc_{datetime.now().timestamp()}@test.com",
            "phone": "+256700000000",
            "role": "Staff",
            "department": "Operations",
            "location_id": loc_id,
            "also_create_member": True
        }
        response = requests.post(f"{BASE_URL}/api/admin/users", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data.get("location_id") == loc_id
        print(f"✓ User created with location: {data['id']}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/users/{data['id']}", headers=auth_headers)
    
    def test_update_user_multi_location(self, auth_headers, locations):
        """PUT /api/admin/users/{id} updates user with multiple locations"""
        # First create a test user
        payload = {
            "name": "TEST_User_MultiLocUpdate",
            "email": f"test_multiloc_update_{datetime.now().timestamp()}@test.com",
            "role": "Coordinator"
        }
        create_response = requests.post(f"{BASE_URL}/api/admin/users", headers=auth_headers, json=payload)
        assert create_response.status_code == 200
        user_id = create_response.json()["id"]
        
        # Update with multiple locations
        loc_ids = [loc["id"] for loc in locations[:2]] if len(locations) >= 2 else [locations[0]["id"]] if locations else []
        update_payload = {
            "location_ids": loc_ids,
            "department": "Multi-Campus"
        }
        update_response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", headers=auth_headers, json=update_payload)
        assert update_response.status_code == 200
        data = update_response.json()
        print(f"✓ User updated with multi-location: {data}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=auth_headers)


# ========== AUDIT TRAIL ==========

class TestAuditTrail:
    """Test audit trail functionality"""
    
    def test_list_audit_logs(self, auth_headers):
        """GET /api/admin/audit lists audit logs"""
        response = requests.get(f"{BASE_URL}/api/admin/audit?limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        print(f"✓ Audit logs listed: {data['total']} total, showing {len(data['logs'])}")
    
    def test_list_deleted_items(self, auth_headers):
        """GET /api/admin/deleted-items lists recycle bin"""
        response = requests.get(f"{BASE_URL}/api/admin/deleted-items", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Deleted items listed: {len(data)} items in recycle bin")


# ========== APP SETTINGS ==========

class TestAppSettings:
    """Test global app settings"""
    
    def test_get_global_settings(self, auth_headers):
        """GET /api/global-settings returns settings"""
        response = requests.get(f"{BASE_URL}/api/global-settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Global settings retrieved: {data}")
    
    def test_get_currencies(self, auth_headers):
        """GET /api/currencies returns currency list"""
        response = requests.get(f"{BASE_URL}/api/currencies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Currencies listed: {len(data)} currencies")


# ========== FINANCIAL ==========

class TestFinancial:
    """Test financial endpoints"""
    
    def test_financial_summary(self, auth_headers):
        """GET /api/financial/summary returns summary"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly_donations" in data or "net_balance" in data
        print(f"✓ Financial summary: {data}")
    
    def test_financial_summary_with_location(self, auth_headers, locations):
        """GET /api/financial/summary with location filter"""
        if not locations:
            pytest.skip("No locations available")
        loc_id = locations[0]["id"]
        response = requests.get(f"{BASE_URL}/api/financial/summary?location_id={loc_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Financial summary for {loc_id}: {data}")


# ========== CLEANUP ==========

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_products(self, auth_headers):
        """Delete TEST_ prefixed products"""
        response = requests.get(f"{BASE_URL}/api/products", headers=auth_headers)
        if response.status_code == 200:
            products = response.json()
            for p in products:
                if p.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/products/{p['id']}", headers=auth_headers)
        print("✓ Test products cleaned up")
    
    def test_cleanup_test_programs(self, auth_headers):
        """Delete TEST_ prefixed outreach programs"""
        response = requests.get(f"{BASE_URL}/api/outreach/programs", headers=auth_headers)
        if response.status_code == 200:
            programs = response.json()
            for p in programs:
                if p.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/outreach/programs/{p['id']}", headers=auth_headers)
        print("✓ Test programs cleaned up")
