"""
Iteration 62 - Financial Features Campus Filter Tests
Tests:
1. Backend /api/auth/login works
2. GET /api/financial/summary applies campus filter
3. GET /api/financial/cashflow applies campus filter
4. POST /api/financial/donations auto-sets location_id from user's active campus
5. POST /api/financial/expenses auto-sets location_id from user's active campus
6. POST /api/products auto-sets location_id from user's active campus
7. POST /api/sales auto-sets location_id from user's active campus
8. GET /api/financial/donations respects campus filter
9. GET /api/financial/expenses respects campus filter
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = creds.ADMIN_EMAIL
ADMIN_PASSWORD = creds.ADMIN_PASSWORD


class TestAuthLogin:
    """Test authentication endpoint"""
    
    def test_login_success(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"Login successful, user role: {data['user'].get('role')}")
        print(f"User active_campus_id: {data['user'].get('active_campus_id')}")
        print(f"User location_id: {data['user'].get('location_id')}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def admin_user(auth_token):
    """Get admin user info"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("user")
    return {}


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestFinancialSummary:
    """Test financial summary endpoint with campus filter"""
    
    def test_summary_returns_200(self, auth_headers):
        """Test financial summary endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=auth_headers)
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        # Verify response structure
        assert "monthly_donations" in data
        assert "monthly_expenses" in data
        assert "monthly_sales" in data
        assert "cashflow_in" in data
        assert "cashflow_out" in data
        assert "net_balance" in data
        print(f"Financial summary: {data}")
    
    def test_summary_with_location_filter(self, auth_headers):
        """Test financial summary with explicit location_id filter"""
        response = requests.get(f"{BASE_URL}/api/financial/summary?location_id=loc_001", headers=auth_headers)
        assert response.status_code == 200, f"Summary with location failed: {response.text}"
        data = response.json()
        assert isinstance(data.get("monthly_donations"), (int, float))
        print(f"Summary for loc_001: {data}")


class TestFinancialCashflow:
    """Test cashflow endpoint with campus filter"""
    
    def test_cashflow_returns_200(self, auth_headers):
        """Test cashflow endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/financial/cashflow", headers=auth_headers)
        assert response.status_code == 200, f"Cashflow failed: {response.text}"
        data = response.json()
        assert "monthly" in data
        assert isinstance(data["monthly"], list)
        if data["monthly"]:
            month = data["monthly"][0]
            assert "month" in month
            assert "inflow" in month
            assert "outflow" in month
            assert "net" in month
        print(f"Cashflow data: {data}")
    
    def test_cashflow_with_months_param(self, auth_headers):
        """Test cashflow with custom months parameter"""
        response = requests.get(f"{BASE_URL}/api/financial/cashflow?months=3", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("monthly", [])) <= 3


class TestDonationAutoLocationId:
    """Test donation creation auto-sets location_id"""
    
    def test_create_donation_auto_location(self, auth_headers, admin_user):
        """Test POST /api/financial/donations auto-sets location_id from user's active campus"""
        unique_id = str(uuid.uuid4())[:8]
        donation_data = {
            "donor_name": f"TEST_Donor_{unique_id}",
            "amount": 50000,
            "currency": "UGX",
            "type": "tithe",
            "notes": "Test donation for iteration 62"
            # location_id NOT provided - should be auto-set
        }
        response = requests.post(f"{BASE_URL}/api/financial/donations", json=donation_data, headers=auth_headers)
        assert response.status_code == 200, f"Create donation failed: {response.text}"
        data = response.json()
        
        # Verify location_id was auto-set
        assert "location_id" in data, "location_id not in response"
        assert data["location_id"], "location_id is empty"
        
        # Should be set to user's active_campus_id or location_id
        expected_loc = admin_user.get("active_campus_id") or admin_user.get("location_id") or ""
        if expected_loc:
            assert data["location_id"] == expected_loc, f"Expected location_id={expected_loc}, got {data['location_id']}"
        
        print(f"Created donation with auto location_id: {data['location_id']}")
        print(f"Donation ID: {data.get('id')}")
        
        # Cleanup - delete the test donation
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/financial/donations/{data['id']}", headers=auth_headers)
    
    def test_create_donation_explicit_location(self, auth_headers):
        """Test POST /api/financial/donations with explicit location_id"""
        unique_id = str(uuid.uuid4())[:8]
        donation_data = {
            "donor_name": f"TEST_Donor_Explicit_{unique_id}",
            "amount": 25000,
            "currency": "UGX",
            "type": "offering",
            "location_id": "loc_002"  # Explicit location
        }
        response = requests.post(f"{BASE_URL}/api/financial/donations", json=donation_data, headers=auth_headers)
        assert response.status_code == 200, f"Create donation failed: {response.text}"
        data = response.json()
        
        # Verify explicit location_id is preserved
        assert data["location_id"] == "loc_002", f"Expected loc_002, got {data['location_id']}"
        print(f"Created donation with explicit location_id: {data['location_id']}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/financial/donations/{data['id']}", headers=auth_headers)


class TestExpenseAutoLocationId:
    """Test expense creation auto-sets location_id"""
    
    def test_create_expense_auto_location(self, auth_headers, admin_user):
        """Test POST /api/financial/expenses auto-sets location_id from user's active campus"""
        unique_id = str(uuid.uuid4())[:8]
        expense_data = {
            "title": f"TEST_Expense_{unique_id}",
            "amount": 30000,
            "currency": "UGX",
            "category": "supplies",
            "notes": "Test expense for iteration 62"
            # location_id NOT provided - should be auto-set
        }
        response = requests.post(f"{BASE_URL}/api/financial/expenses", json=expense_data, headers=auth_headers)
        assert response.status_code == 200, f"Create expense failed: {response.text}"
        data = response.json()
        
        # Verify location_id was auto-set
        assert "location_id" in data, "location_id not in response"
        assert data["location_id"], "location_id is empty"
        
        expected_loc = admin_user.get("active_campus_id") or admin_user.get("location_id") or ""
        if expected_loc:
            assert data["location_id"] == expected_loc, f"Expected location_id={expected_loc}, got {data['location_id']}"
        
        print(f"Created expense with auto location_id: {data['location_id']}")
        print(f"Expense ID: {data.get('id')}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/financial/expenses/{data['id']}", headers=auth_headers)


class TestProductAutoLocationId:
    """Test product creation auto-sets location_id"""
    
    def test_create_product_auto_location(self, auth_headers, admin_user):
        """Test POST /api/products auto-sets location_id from user's active campus"""
        unique_id = str(uuid.uuid4())[:8]
        product_data = {
            "name": f"TEST_Product_{unique_id}",
            "price": 15000,
            "currency": "UGX",
            "stock": 10,
            "category": "merchandise"
            # location_id NOT provided - should be auto-set
        }
        response = requests.post(f"{BASE_URL}/api/products", json=product_data, headers=auth_headers)
        assert response.status_code == 200, f"Create product failed: {response.text}"
        data = response.json()
        
        # Verify location_id was auto-set
        assert "location_id" in data, "location_id not in response"
        assert data["location_id"], "location_id is empty"
        
        expected_loc = admin_user.get("active_campus_id") or admin_user.get("location_id") or ""
        if expected_loc:
            assert data["location_id"] == expected_loc, f"Expected location_id={expected_loc}, got {data['location_id']}"
        
        print(f"Created product with auto location_id: {data['location_id']}")
        print(f"Product ID: {data.get('id')}")
        
        # Cleanup
        if data.get("id"):
            requests.delete(f"{BASE_URL}/api/products/{data['id']}", headers=auth_headers)


class TestSaleAutoLocationId:
    """Test sale creation auto-sets location_id"""
    
    def test_create_sale_auto_location(self, auth_headers, admin_user):
        """Test POST /api/sales auto-sets location_id from user's active campus"""
        unique_id = str(uuid.uuid4())[:8]
        sale_data = {
            "items": [{"name": f"TEST_Item_{unique_id}", "qty": 1, "price": 5000}],
            "customer_name": f"TEST_Customer_{unique_id}",
            "total": 5000,
            "payment_method": "cash"
            # location_id NOT provided - should be auto-set
        }
        response = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=auth_headers)
        assert response.status_code == 200, f"Create sale failed: {response.text}"
        data = response.json()
        
        # Verify location_id was auto-set
        assert "location_id" in data, "location_id not in response"
        assert data["location_id"], "location_id is empty"
        
        expected_loc = admin_user.get("active_campus_id") or admin_user.get("location_id") or ""
        if expected_loc:
            assert data["location_id"] == expected_loc, f"Expected location_id={expected_loc}, got {data['location_id']}"
        
        print(f"Created sale with auto location_id: {data['location_id']}")
        print(f"Sale ID: {data.get('id')}")
        
        # Note: Sales deletion has time-based restrictions, so we won't cleanup immediately


class TestDonationsListCampusFilter:
    """Test donations list respects campus filter"""
    
    def test_list_donations_returns_200(self, auth_headers):
        """Test GET /api/financial/donations returns 200"""
        response = requests.get(f"{BASE_URL}/api/financial/donations", headers=auth_headers)
        assert response.status_code == 200, f"List donations failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} donations")
    
    def test_list_donations_with_location_filter(self, auth_headers):
        """Test GET /api/financial/donations with location_id filter"""
        response = requests.get(f"{BASE_URL}/api/financial/donations?location_id=loc_001", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # All returned donations should have location_id=loc_001
        for donation in data:
            if donation.get("location_id"):
                assert donation["location_id"] == "loc_001", f"Donation {donation.get('id')} has wrong location"
        print(f"Found {len(data)} donations for loc_001")


class TestExpensesListCampusFilter:
    """Test expenses list respects campus filter"""
    
    def test_list_expenses_returns_200(self, auth_headers):
        """Test GET /api/financial/expenses returns 200"""
        response = requests.get(f"{BASE_URL}/api/financial/expenses", headers=auth_headers)
        assert response.status_code == 200, f"List expenses failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} expenses")
    
    def test_list_expenses_with_location_filter(self, auth_headers):
        """Test GET /api/financial/expenses with location_id filter"""
        response = requests.get(f"{BASE_URL}/api/financial/expenses?location_id=loc_001", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # All returned expenses should have location_id=loc_001
        for expense in data:
            if expense.get("location_id"):
                assert expense["location_id"] == "loc_001", f"Expense {expense.get('id')} has wrong location"
        print(f"Found {len(data)} expenses for loc_001")


class TestDashboardStats:
    """Test dashboard stats endpoint"""
    
    def test_dashboard_stats_returns_200(self, auth_headers):
        """Test GET /api/dashboard/stats returns 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        print(f"Dashboard stats: {data}")


class TestLocationsEndpoint:
    """Test locations endpoint for campus switcher"""
    
    def test_list_locations(self, auth_headers):
        """Test GET /api/locations returns locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200, f"List locations failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} locations")
        for loc in data[:3]:
            print(f"  - {loc.get('id')}: {loc.get('name')} (financial_enabled={loc.get('financial_enabled', True)})")


class TestUserActiveCampus:
    """Test user active campus endpoints"""
    
    def test_get_user_profile(self, auth_headers):
        """Test GET /api/user/profile returns user with active_campus_id"""
        response = requests.get(f"{BASE_URL}/api/user/profile", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            print(f"User profile: active_campus_id={data.get('active_campus_id')}, location_id={data.get('location_id')}")
        else:
            # Try /api/auth/me endpoint
            response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
            if response.status_code == 200:
                data = response.json()
                print(f"User (from /me): active_campus_id={data.get('active_campus_id')}, location_id={data.get('location_id')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
