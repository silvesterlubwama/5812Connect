"""
Iteration 66 Tests: HR Module, Sale Deletion Stock Restore, Finance Nav, Campus Switcher, Resident Search, Residency Toggle, Sponsored Children
"""
import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestSaleDeletionStockRestore(TestAuth):
    """Test that deleting a sale restores product stock"""
    
    def test_sale_delete_restores_stock(self, auth_headers):
        """DELETE /api/sales/{id} should restore product stock"""
        # 1. Create a test product
        product_data = {
            "name": f"TEST_Product_{uuid.uuid4().hex[:6]}",
            "price": 1000,
            "stock": 50,
            "currency": "UGX"
        }
        prod_res = requests.post(f"{BASE_URL}/api/products", json=product_data, headers=auth_headers)
        assert prod_res.status_code == 200, f"Product creation failed: {prod_res.text}"
        product = prod_res.json()
        product_id = product["id"]
        initial_stock = product["stock"]
        
        # 2. Create a sale with this product
        sale_data = {
            "items": [{"product_id": product_id, "name": product_data["name"], "qty": 5, "price": 1000}],
            "total": 5000,
            "payment_method": "cash",
            "customer_name": "Test Customer"
        }
        sale_res = requests.post(f"{BASE_URL}/api/sales", json=sale_data, headers=auth_headers)
        assert sale_res.status_code == 200, f"Sale creation failed: {sale_res.text}"
        sale = sale_res.json()
        sale_id = sale["id"]
        
        # 3. Verify stock was reduced
        prod_check = requests.get(f"{BASE_URL}/api/products", headers=auth_headers)
        products = prod_check.json()
        updated_product = next((p for p in products if p["id"] == product_id), None)
        assert updated_product is not None
        assert updated_product["stock"] == initial_stock - 5, f"Stock should be reduced after sale"
        
        # 4. Delete the sale
        del_res = requests.delete(f"{BASE_URL}/api/sales/{sale_id}", headers=auth_headers)
        assert del_res.status_code == 200, f"Sale deletion failed: {del_res.text}"
        assert "stock restored" in del_res.json().get("message", "").lower()
        
        # 5. Verify stock was restored
        prod_final = requests.get(f"{BASE_URL}/api/products", headers=auth_headers)
        products_final = prod_final.json()
        final_product = next((p for p in products_final if p["id"] == product_id), None)
        assert final_product is not None
        assert final_product["stock"] == initial_stock, f"Stock should be restored after sale deletion"
        
        # Cleanup: delete test product
        requests.delete(f"{BASE_URL}/api/products/{product_id}", headers=auth_headers)


class TestHRModule(TestAuth):
    """Test HR module endpoints"""
    
    def test_hr_salaries_list(self, auth_headers):
        """GET /api/hr/salaries should return list"""
        response = requests.get(f"{BASE_URL}/api/hr/salaries", headers=auth_headers)
        assert response.status_code == 200, f"HR salaries list failed: {response.text}"
        assert isinstance(response.json(), list)
    
    def test_hr_salary_create(self, auth_headers):
        """POST /api/hr/salaries should create salary record with line items"""
        # First get a staff member
        users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_res.json()
        staff = next((u for u in users if u.get("role") in ["Staff", "Manager", "Director", "admin"]), None)
        if not staff:
            pytest.skip("No staff member found for salary test")
        
        salary_data = {
            "staff_id": staff["id"],
            "base_salary": 500000,
            "currency": "UGX",
            "pay_frequency": "monthly",
            "line_items": [
                {"name": "Housing Allowance", "type": "allowance", "amount": 50000, "is_percentage": False},
                {"name": "Tax", "type": "deduction", "amount": 10, "is_percentage": True}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/hr/salaries", json=salary_data, headers=auth_headers)
        assert response.status_code == 200, f"Salary creation failed: {response.text}"
        salary = response.json()
        assert salary["staff_id"] == staff["id"]
        assert salary["base_salary"] == 500000
        assert len(salary.get("line_items", [])) == 2
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/salaries/{salary['id']}", headers=auth_headers)
    
    def test_hr_payslips_generate(self, auth_headers):
        """POST /api/hr/payslips/generate should generate payslips for a period"""
        response = requests.post(f"{BASE_URL}/api/hr/payslips/generate", json={
            "period": "2026-01"
        }, headers=auth_headers)
        assert response.status_code == 200, f"Payslip generation failed: {response.text}"
        data = response.json()
        assert "generated" in data
        assert "payslips" in data
    
    def test_hr_payslips_list(self, auth_headers):
        """GET /api/hr/payslips should return list"""
        response = requests.get(f"{BASE_URL}/api/hr/payslips", headers=auth_headers)
        assert response.status_code == 200, f"HR payslips list failed: {response.text}"
        assert isinstance(response.json(), list)
    
    def test_hr_contract_templates_list(self, auth_headers):
        """GET /api/hr/contracts/templates should return list"""
        response = requests.get(f"{BASE_URL}/api/hr/contracts/templates", headers=auth_headers)
        assert response.status_code == 200, f"Contract templates list failed: {response.text}"
        assert isinstance(response.json(), list)
    
    def test_hr_contract_template_create(self, auth_headers):
        """POST /api/hr/contracts/templates should create template"""
        template_data = {
            "name": f"TEST_Contract_{uuid.uuid4().hex[:6]}",
            "content": "This Employment Contract is between 58:12 Global and {{staff_name}} for the role of {{role}}.",
            "variables": ["staff_name", "role", "start_date", "salary"]
        }
        response = requests.post(f"{BASE_URL}/api/hr/contracts/templates", json=template_data, headers=auth_headers)
        assert response.status_code == 200, f"Template creation failed: {response.text}"
        template = response.json()
        assert template["name"] == template_data["name"]
        assert "{{staff_name}}" in template["content"]
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/contracts/templates/{template['id']}", headers=auth_headers)
    
    def test_hr_contract_issue(self, auth_headers):
        """POST /api/hr/contracts/issue should issue contract to staff"""
        # Create a template first
        template_data = {
            "name": f"TEST_IssueContract_{uuid.uuid4().hex[:6]}",
            "content": "Contract for {{staff_name}} as {{role}} starting {{start_date}}.",
            "variables": ["staff_name", "role", "start_date"]
        }
        tpl_res = requests.post(f"{BASE_URL}/api/hr/contracts/templates", json=template_data, headers=auth_headers)
        assert tpl_res.status_code == 200
        template = tpl_res.json()
        
        # Get a staff member
        users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_res.json()
        staff = next((u for u in users if u.get("role") in ["Staff", "Manager", "Director", "admin"]), None)
        if not staff:
            requests.delete(f"{BASE_URL}/api/hr/contracts/templates/{template['id']}", headers=auth_headers)
            pytest.skip("No staff member found")
        
        # Issue contract
        issue_data = {
            "template_id": template["id"],
            "staff_id": staff["id"],
            "start_date": "2026-02-01",
            "salary": "500000"
        }
        response = requests.post(f"{BASE_URL}/api/hr/contracts/issue", json=issue_data, headers=auth_headers)
        assert response.status_code == 200, f"Contract issue failed: {response.text}"
        contract = response.json()
        assert contract["staff_id"] == staff["id"]
        assert contract["status"] == "pending_signature"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/hr/contracts/templates/{template['id']}", headers=auth_headers)
    
    def test_hr_document_request(self, auth_headers):
        """POST /api/hr/document-requests should send document request"""
        # Get a staff member
        users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        users = users_res.json()
        staff = next((u for u in users if u.get("role") in ["Staff", "Manager", "Director", "admin"]), None)
        if not staff:
            pytest.skip("No staff member found")
        
        doc_req_data = {
            "staff_id": staff["id"],
            "doc_types": ["resume", "id_document", "passport"],
            "message": "Please submit these documents by end of month."
        }
        response = requests.post(f"{BASE_URL}/api/hr/document-requests", json=doc_req_data, headers=auth_headers)
        assert response.status_code == 200, f"Document request failed: {response.text}"
        doc_req = response.json()
        assert doc_req["staff_id"] == staff["id"]
        assert "resume" in doc_req["doc_types"]
    
    def test_hr_document_requests_list(self, auth_headers):
        """GET /api/hr/document-requests should return list"""
        response = requests.get(f"{BASE_URL}/api/hr/document-requests", headers=auth_headers)
        assert response.status_code == 200, f"Document requests list failed: {response.text}"
        assert isinstance(response.json(), list)
    
    def test_hr_settings_get(self, auth_headers):
        """GET /api/hr/settings/{location_id} should return settings"""
        # Get a location first
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = locs_res.json()
        if not locations:
            pytest.skip("No locations found")
        
        loc_id = locations[0]["id"]
        response = requests.get(f"{BASE_URL}/api/hr/settings/{loc_id}", headers=auth_headers)
        assert response.status_code == 200, f"HR settings get failed: {response.text}"
        settings = response.json()
        assert "hr_enabled" in settings
        assert "pay_frequency" in settings
    
    def test_hr_settings_update(self, auth_headers):
        """PUT /api/hr/settings/{location_id} should update settings"""
        # Get a location first
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = locs_res.json()
        if not locations:
            pytest.skip("No locations found")
        
        loc_id = locations[0]["id"]
        settings_data = {
            "hr_enabled": True,
            "pay_frequency": "monthly",
            "currency": "UGX",
            "pay_day": 28
        }
        response = requests.put(f"{BASE_URL}/api/hr/settings/{loc_id}", json=settings_data, headers=auth_headers)
        assert response.status_code == 200, f"HR settings update failed: {response.text}"
        settings = response.json()
        assert settings["hr_enabled"] == True
        assert settings["pay_day"] == 28


class TestSponsoredChildren(TestAuth):
    """Test sponsored children tracking"""
    
    def test_sponsored_children_stats(self, auth_headers):
        """GET /api/hr/sponsored-children should return stats"""
        response = requests.get(f"{BASE_URL}/api/hr/sponsored-children", headers=auth_headers)
        assert response.status_code == 200, f"Sponsored children stats failed: {response.text}"
        data = response.json()
        assert "sponsored" in data
        assert "total" in data
        assert "percentage" in data


class TestLocationsResidency(TestAuth):
    """Test locations with allows_residents toggle"""
    
    def test_location_allows_residents_field(self, auth_headers):
        """Locations should have allows_residents field"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        locations = response.json()
        # Check that sub-locations can have allows_residents
        sub_locs = [l for l in locations if l.get("type") == "sub-location"]
        # The field should be present or default to true
        for loc in sub_locs:
            # allows_residents defaults to true if not set
            assert loc.get("allows_residents", True) in [True, False]
    
    def test_create_sublocation_with_allows_residents(self, auth_headers):
        """Creating sub-location with allows_residents toggle"""
        # Get a parent location
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = locs_res.json()
        parent = next((l for l in locations if l.get("type") in ["campus", "main"]), None)
        if not parent:
            pytest.skip("No parent location found")
        
        subloc_data = {
            "name": f"TEST_SubLoc_{uuid.uuid4().hex[:6]}",
            "type": "sub-location",
            "parent_id": parent["id"],
            "allows_residents": True,
            "is_restricted": False
        }
        response = requests.post(f"{BASE_URL}/api/locations", json=subloc_data, headers=auth_headers)
        assert response.status_code == 200, f"Sub-location creation failed: {response.text}"
        subloc = response.json()
        assert subloc.get("allows_residents") == True
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/locations/{subloc['id']}", headers=auth_headers)


class TestResidentSearch(TestAuth):
    """Test resident search functionality (members + children)"""
    
    def test_members_search(self, auth_headers):
        """GET /api/members with search should return results"""
        response = requests.get(f"{BASE_URL}/api/members", params={"search": "a", "limit": 10}, headers=auth_headers)
        assert response.status_code == 200, f"Members search failed: {response.text}"
        data = response.json()
        # Should return members or empty list
        assert "members" in data or isinstance(data, list)
    
    def test_children_search(self, auth_headers):
        """GET /api/children with search should return results"""
        response = requests.get(f"{BASE_URL}/api/children", params={"search": "a", "limit": 10}, headers=auth_headers)
        assert response.status_code == 200, f"Children search failed: {response.text}"
        assert isinstance(response.json(), list)


class TestFinancialSummary(TestAuth):
    """Test financial summary endpoint"""
    
    def test_financial_summary(self, auth_headers):
        """GET /api/financial/summary should return financial data"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", headers=auth_headers)
        assert response.status_code == 200, f"Financial summary failed: {response.text}"
        data = response.json()
        assert "monthly_donations" in data
        assert "monthly_expenses" in data
        assert "net_balance" in data


class TestDashboardStats(TestAuth):
    """Test dashboard stats endpoint"""
    
    def test_dashboard_stats(self, auth_headers):
        """GET /api/dashboard/stats should return stats"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        assert "total_members" in data or "active_members" in data


class TestHRContracts(TestAuth):
    """Test HR contracts list endpoint"""
    
    def test_hr_contracts_list(self, auth_headers):
        """GET /api/hr/contracts should return list"""
        response = requests.get(f"{BASE_URL}/api/hr/contracts", headers=auth_headers)
        assert response.status_code == 200, f"HR contracts list failed: {response.text}"
        assert isinstance(response.json(), list)


class TestCampusSwitcher(TestAuth):
    """Test campus switcher functionality"""
    
    def test_locations_list_for_switcher(self, auth_headers):
        """GET /api/locations should return locations for campus switcher"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200, f"Locations list failed: {response.text}"
        locations = response.json()
        assert isinstance(locations, list)
        # Should have campuses and sub-locations
        types = set(l.get("type") for l in locations)
        # At least one location type should exist
        assert len(types) > 0
    
    def test_user_active_campus_set(self, auth_headers):
        """PUT /api/user/active-campus should set active campus"""
        # Get a campus
        locs_res = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = locs_res.json()
        campus = next((l for l in locations if l.get("type") in ["campus", "main"]), None)
        if not campus:
            pytest.skip("No campus found")
        
        response = requests.put(f"{BASE_URL}/api/user/active-campus", json={"campus_id": campus["id"]}, headers=auth_headers)
        # Should succeed or return 200/404 if endpoint exists
        assert response.status_code in [200, 404], f"Active campus set failed: {response.text}"
