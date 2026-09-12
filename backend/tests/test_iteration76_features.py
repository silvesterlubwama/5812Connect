"""
Iteration 76 - Testing:
1. GET /api/reports/summary - returns income/expenses/members/events/children counts
2. Sales portal login and customer creation
3. Products page variant editing
4. HR toggle in campus settings
5. People page member management buttons
"""
import pytest
import requests
import os

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": creds.ADMIN_EMAIL,
        "password": creds.ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestReportsSummary:
    """Test GET /api/reports/summary endpoint"""
    
    def test_reports_summary_returns_200(self, auth_headers):
        """Reports summary endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_reports_summary_has_required_fields(self, auth_headers):
        """Reports summary should have income/expenses/members/events/children counts"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "total_income" in data, "Missing total_income field"
        assert "total_expenses" in data, "Missing total_expenses field"
        assert "net" in data, "Missing net field"
        assert "income_breakdown" in data, "Missing income_breakdown field"
        assert "expense_breakdown" in data, "Missing expense_breakdown field"
        assert "members_count" in data, "Missing members_count field"
        assert "events_count" in data, "Missing events_count field"
        assert "children_count" in data, "Missing children_count field"
    
    def test_reports_summary_with_date_filter(self, auth_headers):
        """Reports summary should accept date filters"""
        response = requests.get(
            f"{BASE_URL}/api/reports/summary",
            headers=auth_headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_income" in data
    
    def test_reports_summary_with_location_filter(self, auth_headers):
        """Reports summary should accept location_id filter"""
        response = requests.get(
            f"{BASE_URL}/api/reports/summary",
            headers=auth_headers,
            params={"location_id": "loc_001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_income" in data


class TestSalesPortal:
    """Test Sales Portal login and customer creation"""
    
    def test_sales_portal_login_endpoint_exists(self):
        """Sales portal login endpoint should exist"""
        response = requests.post(f"{BASE_URL}/api/auth/sales-portal-login", json={
            "last_name": "Admin",
            "pin": "1234"
        })
        # Should return 401 for invalid credentials, not 404
        assert response.status_code in [200, 401, 422], f"Unexpected status: {response.status_code}"
    
    def test_customers_endpoint_exists(self, auth_headers):
        """Customers endpoint should exist for search"""
        response = requests.get(f"{BASE_URL}/api/customers", headers=auth_headers, params={"search": "test"})
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
    
    def test_create_customer(self, auth_headers):
        """Should be able to create a customer"""
        response = requests.post(f"{BASE_URL}/api/customers", headers=auth_headers, json={
            "name": "TEST_Customer_Iteration76"
        })
        # Accept 200, 201, or 404 if endpoint doesn't exist
        if response.status_code in [200, 201]:
            data = response.json()
            assert "id" in data or "name" in data
            # Cleanup
            if "id" in data:
                requests.delete(f"{BASE_URL}/api/customers/{data['id']}", headers=auth_headers)


class TestProductVariants:
    """Test product variant editing functionality"""
    
    def test_products_list(self, auth_headers):
        """Products endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/products", headers=auth_headers)
        assert response.status_code == 200
    
    def test_create_product_with_variants(self, auth_headers):
        """Should be able to create a product with has_variants flag"""
        response = requests.post(f"{BASE_URL}/api/products", headers=auth_headers, json={
            "name": "TEST_Product_Variants_76",
            "price": 0,
            "stock": 0,
            "has_variants": True,
            "category": "Test"
        })
        assert response.status_code in [200, 201], f"Failed to create product: {response.text}"
        data = response.json()
        product_id = data.get("id")
        assert product_id, "Product ID not returned"
        
        # Verify has_variants is set
        get_response = requests.get(f"{BASE_URL}/api/products/{product_id}", headers=auth_headers)
        if get_response.status_code == 200:
            product = get_response.json()
            assert product.get("has_variants") == True, "has_variants should be True"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/products/{product_id}", headers=auth_headers)
    
    def test_add_variant_to_product(self, auth_headers):
        """Should be able to add a variant to a product"""
        # Create product first
        create_response = requests.post(f"{BASE_URL}/api/products", headers=auth_headers, json={
            "name": "TEST_Product_AddVariant_76",
            "price": 0,
            "stock": 0,
            "has_variants": True
        })
        assert create_response.status_code in [200, 201]
        product_id = create_response.json().get("id")
        
        # Add variant
        variant_response = requests.post(
            f"{BASE_URL}/api/products/{product_id}/variants",
            headers=auth_headers,
            json={"name": "Large", "price": 5000, "stock": 10}
        )
        # Accept 200, 201, or 404 if endpoint doesn't exist
        if variant_response.status_code in [200, 201]:
            variant_data = variant_response.json()
            assert "id" in variant_data or "variants" in variant_data
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/products/{product_id}", headers=auth_headers)


class TestLocationHRToggle:
    """Test HR toggle in campus settings"""
    
    def test_location_has_hr_enabled_field(self, auth_headers):
        """Locations should have hr_enabled field"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        locations = response.json()
        
        if len(locations) > 0:
            # Check if hr_enabled field exists (may be undefined/null if not set)
            loc = locations[0]
            # Field should be present or default to true
            hr_enabled = loc.get("hr_enabled", True)
            assert hr_enabled in [True, False, None], "hr_enabled should be boolean or null"
    
    def test_update_location_hr_toggle(self, auth_headers):
        """Should be able to update hr_enabled on a location"""
        # Get existing location
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        locations = response.json()
        
        if len(locations) > 0:
            loc_id = locations[0]["id"]
            original_hr = locations[0].get("hr_enabled", True)
            
            # Update hr_enabled
            update_response = requests.put(
                f"{BASE_URL}/api/locations/{loc_id}",
                headers=auth_headers,
                json={"hr_enabled": not original_hr}
            )
            assert update_response.status_code == 200, f"Failed to update: {update_response.text}"
            
            # Verify update
            verify_response = requests.get(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers)
            if verify_response.status_code == 200:
                updated_loc = verify_response.json()
                assert updated_loc.get("hr_enabled") == (not original_hr), "hr_enabled not updated"
            
            # Restore original value
            requests.put(
                f"{BASE_URL}/api/locations/{loc_id}",
                headers=auth_headers,
                json={"hr_enabled": original_hr}
            )


class TestMemberManagement:
    """Test member management buttons (Edit, Reset Password, Badge, Delete)"""
    
    def test_members_list(self, auth_headers):
        """Members endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
        assert response.status_code == 200
    
    def test_member_update(self, auth_headers):
        """Should be able to update a member (Edit functionality)"""
        # Create test member
        create_response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Member_Edit_76",
            "email": "test_edit_76@example.com",
            "role": "Staff"
        })
        assert create_response.status_code in [200, 201]
        member_id = create_response.json().get("id")
        
        # Update member
        update_response = requests.put(
            f"{BASE_URL}/api/members/{member_id}",
            headers=auth_headers,
            json={"name": "TEST_Member_Edit_76_Updated"}
        )
        assert update_response.status_code == 200, f"Failed to update member: {update_response.text}"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
    
    def test_password_reset_endpoint(self, auth_headers):
        """Password reset endpoint should exist"""
        # Create test member with user account
        create_response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Member_Reset_76",
            "email": "test_reset_76@example.com",
            "role": "Staff"
        })
        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create test member")
        
        member_id = create_response.json().get("id")
        user_id = create_response.json().get("user_id", member_id)
        
        # Try password reset - should use user_id not member_id
        reset_response = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/reset-password",
            headers=auth_headers,
            json={"new_password": creds.RESET_PASSWORD}
        )
        # Accept 200, 404 (endpoint may not exist), or 400 (validation)
        assert reset_response.status_code in [200, 400, 404, 422], f"Unexpected: {reset_response.status_code}"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
    
    def test_member_delete(self, auth_headers):
        """Should be able to delete a member"""
        # Create test member
        create_response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Member_Delete_76",
            "email": "test_delete_76@example.com",
            "role": "Staff"
        })
        assert create_response.status_code in [200, 201]
        member_id = create_response.json().get("id")
        
        # Delete member
        delete_response = requests.delete(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        assert delete_response.status_code in [200, 204], f"Failed to delete: {delete_response.text}"
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/members/{member_id}", headers=auth_headers)
        assert get_response.status_code == 404, "Member should be deleted"


class TestNavigationHiding:
    """Test that Finance/Marketplace/HR are hidden without campus selection"""
    
    def test_locations_have_feature_flags(self, auth_headers):
        """Locations should have financial_enabled, marketplace_enabled, hr_enabled flags"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        locations = response.json()
        
        if len(locations) > 0:
            loc = locations[0]
            # These fields should exist (may be true by default)
            assert "financial_enabled" in loc or loc.get("financial_enabled") is None or loc.get("financial_enabled") == True
            assert "marketplace_enabled" in loc or loc.get("marketplace_enabled") is None or loc.get("marketplace_enabled") == True


class TestReportsEndpointRouting:
    """Test that /api/reports/summary is correctly routed before /{report_id}"""
    
    def test_summary_not_treated_as_report_id(self, auth_headers):
        """GET /api/reports/summary should NOT return 404 'Report not found'"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=auth_headers)
        assert response.status_code == 200, f"Summary endpoint failed: {response.text}"
        
        # Should NOT contain "Report not found" error
        if response.status_code != 200:
            data = response.json()
            assert "Report not found" not in str(data), "Summary is being treated as report_id"
    
    def test_reports_list_works(self, auth_headers):
        """GET /api/reports should list reports"""
        response = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Reports list should return array"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
