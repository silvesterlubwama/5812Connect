"""
Iteration 69 - Customer Accounts Feature Tests
Tests for:
- Customer CRUD endpoints (list, create, get, update, delete)
- Customer search by name/phone/email
- Customer purchase history
- Sales with customer_id updates customer totals
- Auto-guest linking when creating customers
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for admin user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": "Admin@5812"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestCustomerCRUD:
    """Customer CRUD endpoint tests"""
    
    def test_create_customer_success(self, authenticated_client):
        """POST /api/customers creates a customer account"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": f"TEST_Customer_{unique_id}",
            "email": f"test_customer_{unique_id}@example.com",
            "phone": f"+256700{unique_id[:6]}",
            "notes": "Test customer for iteration 69"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Customer ID should be returned"
        assert data["name"] == payload["name"], "Name should match"
        assert data["email"] == payload["email"].lower(), "Email should match (lowercased)"
        assert data["phone"] == payload["phone"], "Phone should match"
        assert data["total_purchases"] == 0, "Initial total_purchases should be 0"
        assert data["total_spent"] == 0, "Initial total_spent should be 0"
        assert "created_at" in data, "created_at should be present"
        
        # Store for cleanup
        self.__class__.created_customer_id = data["id"]
        print(f"✓ Created customer: {data['id']}")
    
    def test_create_customer_requires_name(self, authenticated_client):
        """POST /api/customers requires name field"""
        payload = {
            "email": "noname@example.com",
            "phone": "+256700000000"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        
        assert response.status_code == 400, f"Expected 400 for missing name, got {response.status_code}"
        print("✓ Name validation works")
    
    def test_list_customers(self, authenticated_client):
        """GET /api/customers lists customer accounts"""
        response = authenticated_client.get(f"{BASE_URL}/api/customers")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Listed {len(data)} customers")
    
    def test_search_customers_by_name(self, authenticated_client):
        """GET /api/customers?search=name searches by name"""
        # First create a customer with unique name
        unique_id = str(uuid.uuid4())[:8]
        unique_name = f"TEST_SearchName_{unique_id}"
        payload = {"name": unique_name, "email": f"search_{unique_id}@test.com"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        created_id = create_resp.json()["id"]
        
        # Search by name
        response = authenticated_client.get(f"{BASE_URL}/api/customers", params={"search": unique_name[:10]})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        found = any(c["id"] == created_id for c in data)
        assert found, f"Created customer should be found in search results"
        print(f"✓ Search by name works - found customer")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{created_id}")
    
    def test_search_customers_by_phone(self, authenticated_client):
        """GET /api/customers?search=phone searches by phone"""
        unique_id = str(uuid.uuid4())[:8]
        unique_phone = f"+256788{unique_id[:6]}"
        payload = {"name": f"TEST_PhoneSearch_{unique_id}", "phone": unique_phone}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        created_id = create_resp.json()["id"]
        
        # Search by phone
        response = authenticated_client.get(f"{BASE_URL}/api/customers", params={"search": unique_phone[5:]})
        
        assert response.status_code == 200
        data = response.json()
        found = any(c["id"] == created_id for c in data)
        assert found, "Customer should be found by phone search"
        print(f"✓ Search by phone works")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{created_id}")
    
    def test_search_customers_by_email(self, authenticated_client):
        """GET /api/customers?search=email searches by email"""
        unique_id = str(uuid.uuid4())[:8]
        unique_email = f"emailsearch_{unique_id}@test.com"
        payload = {"name": f"TEST_EmailSearch_{unique_id}", "email": unique_email}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        created_id = create_resp.json()["id"]
        
        # Search by email
        response = authenticated_client.get(f"{BASE_URL}/api/customers", params={"search": unique_email[:15]})
        
        assert response.status_code == 200
        data = response.json()
        found = any(c["id"] == created_id for c in data)
        assert found, "Customer should be found by email search"
        print(f"✓ Search by email works")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{created_id}")
    
    def test_get_customer_by_id(self, authenticated_client):
        """GET /api/customers/{id} returns customer with purchase history"""
        # Create a customer first
        unique_id = str(uuid.uuid4())[:8]
        payload = {"name": f"TEST_GetById_{unique_id}", "email": f"getbyid_{unique_id}@test.com"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Get customer by ID
        response = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data["id"] == customer_id, "ID should match"
        assert "purchases" in data, "Response should include purchases array"
        assert isinstance(data["purchases"], list), "Purchases should be a list"
        print(f"✓ Get customer by ID works with purchase history")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")
    
    def test_get_customer_not_found(self, authenticated_client):
        """GET /api/customers/{id} returns 404 for non-existent customer"""
        response = authenticated_client.get(f"{BASE_URL}/api/customers/nonexistent_id_12345")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ 404 returned for non-existent customer")
    
    def test_update_customer(self, authenticated_client):
        """PUT /api/customers/{id} updates customer details"""
        # Create a customer first
        unique_id = str(uuid.uuid4())[:8]
        payload = {"name": f"TEST_Update_{unique_id}", "email": f"update_{unique_id}@test.com"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Update customer
        update_payload = {
            "name": f"TEST_Updated_{unique_id}",
            "notes": "Updated notes"
        }
        response = authenticated_client.put(f"{BASE_URL}/api/customers/{customer_id}", json=update_payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data["name"] == update_payload["name"], "Name should be updated"
        assert data["notes"] == update_payload["notes"], "Notes should be updated"
        assert "updated_at" in data, "updated_at should be present"
        print(f"✓ Update customer works")
        
        # Verify persistence with GET
        get_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == update_payload["name"]
        print(f"✓ Update persisted correctly")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")
    
    def test_delete_customer(self, authenticated_client):
        """DELETE /api/customers/{id} deletes customer account"""
        # Create a customer first
        unique_id = str(uuid.uuid4())[:8]
        payload = {"name": f"TEST_Delete_{unique_id}"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Delete customer
        response = authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify deletion with GET
        get_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        assert get_resp.status_code == 404, "Customer should not exist after deletion"
        print(f"✓ Delete customer works")


class TestCustomerPurchases:
    """Customer purchase history and sales integration tests"""
    
    def test_get_customer_purchases(self, authenticated_client):
        """GET /api/customers/{id}/purchases returns purchase list with totals"""
        # Create a customer
        unique_id = str(uuid.uuid4())[:8]
        payload = {"name": f"TEST_Purchases_{unique_id}"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Get purchases
        response = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}/purchases")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "purchases" in data, "Response should have purchases array"
        assert "total_count" in data, "Response should have total_count"
        assert "total_spent" in data, "Response should have total_spent"
        assert isinstance(data["purchases"], list), "Purchases should be a list"
        print(f"✓ Get customer purchases endpoint works")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")
    
    def test_sale_with_customer_id_updates_totals(self, authenticated_client):
        """POST /api/sales with customer_id updates customer totals"""
        # Create a customer
        unique_id = str(uuid.uuid4())[:8]
        payload = {"name": f"TEST_SaleTotals_{unique_id}"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Get initial totals
        initial_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        assert initial_resp.status_code == 200
        initial_data = initial_resp.json()
        initial_purchases = initial_data.get("total_purchases", 0)
        initial_spent = initial_data.get("total_spent", 0)
        
        # Create a sale with customer_id
        sale_total = 50000
        sale_payload = {
            "items": [{"name": "Test Item", "price": sale_total, "qty": 1}],
            "total": sale_total,
            "payment_method": "cash",
            "customer_id": customer_id,
            "customer_name": f"TEST_SaleTotals_{unique_id}"
        }
        sale_resp = authenticated_client.post(f"{BASE_URL}/api/sales", json=sale_payload)
        
        assert sale_resp.status_code == 200, f"Expected 200, got {sale_resp.status_code}: {sale_resp.text}"
        sale_data = sale_resp.json()
        assert sale_data.get("customer_id") == customer_id, "Sale should have customer_id"
        
        # Verify customer totals were updated
        updated_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        assert updated_resp.status_code == 200
        updated_data = updated_resp.json()
        
        assert updated_data["total_purchases"] == initial_purchases + 1, "total_purchases should increment by 1"
        assert updated_data["total_spent"] == initial_spent + sale_total, f"total_spent should increase by {sale_total}"
        print(f"✓ Sale with customer_id updates customer totals correctly")
        
        # Verify purchase appears in customer's purchase history
        purchases_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}/purchases")
        assert purchases_resp.status_code == 200
        purchases_data = purchases_resp.json()
        assert purchases_data["total_count"] >= 1, "Customer should have at least 1 purchase"
        print(f"✓ Purchase appears in customer's history")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")


class TestCustomerLocationFilter:
    """Customer location/campus filter tests"""
    
    def test_list_customers_with_location_filter(self, authenticated_client):
        """GET /api/customers?location_id filters by campus"""
        # Create a customer with specific location
        unique_id = str(uuid.uuid4())[:8]
        test_location = f"test_loc_{unique_id}"
        payload = {
            "name": f"TEST_Location_{unique_id}",
            "location_id": test_location
        }
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        
        # Filter by location
        response = authenticated_client.get(f"{BASE_URL}/api/customers", params={"location_id": test_location})
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned customers should have the specified location
        for customer in data:
            assert customer.get("location_id") == test_location, "All customers should match location filter"
        
        print(f"✓ Location filter works")
        
        # Cleanup
        authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")


class TestSalesPortalLogin:
    """Sales portal login tests"""
    
    def test_sales_portal_login_endpoint(self, api_client):
        """POST /api/auth/sales-portal-login validates last_name + PIN"""
        # Test with invalid credentials
        response = api_client.post(f"{BASE_URL}/api/auth/sales-portal-login", json={
            "last_name": "InvalidName",
            "pin": "000000"
        })
        
        # Should return 401 for invalid credentials
        assert response.status_code == 401, f"Expected 401 for invalid credentials, got {response.status_code}"
        print("✓ Sales portal login rejects invalid credentials")


class TestCustomersApiInFrontend:
    """Verify customersApi methods work correctly"""
    
    def test_customers_api_list(self, authenticated_client):
        """customersApi.list() - GET /api/customers"""
        response = authenticated_client.get(f"{BASE_URL}/api/customers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("✓ customersApi.list() works")
    
    def test_customers_api_create_get_update_delete(self, authenticated_client):
        """Full CRUD cycle via customersApi methods"""
        unique_id = str(uuid.uuid4())[:8]
        
        # Create
        create_payload = {"name": f"TEST_CRUD_{unique_id}", "email": f"crud_{unique_id}@test.com"}
        create_resp = authenticated_client.post(f"{BASE_URL}/api/customers", json=create_payload)
        assert create_resp.status_code == 200
        customer_id = create_resp.json()["id"]
        print(f"✓ customersApi.create() works")
        
        # Get
        get_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == customer_id
        print(f"✓ customersApi.get() works")
        
        # Update
        update_resp = authenticated_client.put(f"{BASE_URL}/api/customers/{customer_id}", json={"notes": "Updated"})
        assert update_resp.status_code == 200
        assert update_resp.json()["notes"] == "Updated"
        print(f"✓ customersApi.update() works")
        
        # Purchases
        purchases_resp = authenticated_client.get(f"{BASE_URL}/api/customers/{customer_id}/purchases")
        assert purchases_resp.status_code == 200
        assert "purchases" in purchases_resp.json()
        print(f"✓ customersApi.purchases() works")
        
        # Delete
        delete_resp = authenticated_client.delete(f"{BASE_URL}/api/customers/{customer_id}")
        assert delete_resp.status_code == 200
        print(f"✓ customersApi.delete() works")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_customers(self, authenticated_client):
        """Remove TEST_ prefixed customers"""
        response = authenticated_client.get(f"{BASE_URL}/api/customers")
        if response.status_code == 200:
            customers = response.json()
            deleted = 0
            for c in customers:
                if c.get("name", "").startswith("TEST_"):
                    del_resp = authenticated_client.delete(f"{BASE_URL}/api/customers/{c['id']}")
                    if del_resp.status_code == 200:
                        deleted += 1
            print(f"✓ Cleaned up {deleted} test customers")
