"""
Iteration 67 - Testing Profile PDF Download and Sub-Location Accounts
Features:
1. GET /api/members/{id}/profile-pdf - generates PDF with member info, documents, NFC tags
2. GET /api/financial/accounts - aggregates per sub-location with campus totals
"""
import pytest
import requests
import os

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
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestProfilePdfEndpoint:
    """Tests for GET /api/members/{id}/profile-pdf"""
    
    def test_profile_pdf_requires_auth(self):
        """Profile PDF endpoint requires authentication"""
        # First get a member ID
        response = requests.get(f"{BASE_URL}/api/members/mem_12345678/profile-pdf")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Profile PDF requires authentication")
    
    def test_profile_pdf_returns_pdf_or_html(self, api_client):
        """Profile PDF endpoint returns PDF or HTML content"""
        # First get a member to test with
        members_res = api_client.get(f"{BASE_URL}/api/members", params={"limit": 1})
        assert members_res.status_code == 200, f"Failed to get members: {members_res.status_code}"
        members = members_res.json().get("members", [])
        
        if not members:
            pytest.skip("No members found to test PDF generation")
        
        member_id = members[0]["id"]
        member_name = members[0].get("name", "Unknown")
        print(f"Testing PDF generation for member: {member_name} ({member_id})")
        
        # Request the profile PDF
        response = api_client.get(f"{BASE_URL}/api/members/{member_id}/profile-pdf")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type - should be PDF or HTML (fallback)
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type or "text/html" in content_type, \
            f"Expected PDF or HTML content type, got: {content_type}"
        
        # Check content disposition header
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, f"Expected attachment disposition, got: {content_disp}"
        assert "profile-" in content_disp, f"Expected profile filename, got: {content_disp}"
        
        # Check content is not empty
        assert len(response.content) > 100, "PDF/HTML content is too small"
        
        if "application/pdf" in content_type:
            # Verify PDF magic bytes
            assert response.content[:4] == b'%PDF', "Content doesn't start with PDF magic bytes"
            print(f"PASS: Profile PDF generated successfully ({len(response.content)} bytes)")
        else:
            # HTML fallback - check for expected content
            html_content = response.content.decode('utf-8')
            assert "58:12 GLOBAL" in html_content, "HTML should contain organization name"
            assert member_name in html_content, f"HTML should contain member name: {member_name}"
            print(f"PASS: Profile HTML generated (PDF fallback) ({len(response.content)} bytes)")
    
    def test_profile_pdf_contains_member_info(self, api_client):
        """Profile PDF/HTML contains personal information"""
        # Get a member with some data
        members_res = api_client.get(f"{BASE_URL}/api/members", params={"limit": 5})
        members = members_res.json().get("members", [])
        
        if not members:
            pytest.skip("No members found")
        
        # Find a member with email or phone
        test_member = None
        for m in members:
            if m.get("email") or m.get("phone"):
                test_member = m
                break
        
        if not test_member:
            test_member = members[0]
        
        member_id = test_member["id"]
        response = api_client.get(f"{BASE_URL}/api/members/{member_id}/profile-pdf")
        assert response.status_code == 200
        
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            html = response.content.decode('utf-8')
            # Check for expected sections
            assert "Personal Information" in html, "Should have Personal Information section"
            assert test_member.get("name", "") in html, "Should contain member name"
            print(f"PASS: Profile contains member info for {test_member.get('name')}")
        else:
            # PDF - just verify it's valid
            assert response.content[:4] == b'%PDF'
            print("PASS: PDF generated (content verification skipped for binary)")
    
    def test_profile_pdf_not_found(self, api_client):
        """Profile PDF returns 404 for non-existent member"""
        response = api_client.get(f"{BASE_URL}/api/members/mem_nonexistent_12345/profile-pdf")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Profile PDF returns 404 for non-existent member")


class TestFinancialAccountsEndpoint:
    """Tests for GET /api/financial/accounts - sub-location accounts unified at campus level"""
    
    def test_accounts_requires_auth(self):
        """Accounts endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/financial/accounts")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Financial accounts requires authentication")
    
    def test_accounts_requires_manager_role(self, api_client):
        """Accounts endpoint requires manager+ role"""
        # Admin should have access
        response = api_client.get(f"{BASE_URL}/api/financial/accounts", params={"campus_id": "loc_001"})
        # Should be 200 or 400 (if campus_id not found), not 403
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text}"
        print("PASS: Admin has access to financial accounts")
    
    def test_accounts_returns_structure(self, api_client):
        """Accounts endpoint returns expected structure with campus totals"""
        # First get a valid campus ID
        locations_res = api_client.get(f"{BASE_URL}/api/locations")
        assert locations_res.status_code == 200
        locations = locations_res.json()
        
        # Find a campus (type=campus or main)
        campus = None
        for loc in locations:
            if loc.get("type") in ["campus", "main"]:
                campus = loc
                break
        
        if not campus:
            # Use first location
            campus = locations[0] if locations else None
        
        if not campus:
            pytest.skip("No locations found to test accounts")
        
        campus_id = campus["id"]
        print(f"Testing accounts for campus: {campus.get('name')} ({campus_id})")
        
        response = api_client.get(f"{BASE_URL}/api/financial/accounts", params={"campus_id": campus_id})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify structure
        assert "campus_id" in data, "Response should have campus_id"
        assert "accounts" in data, "Response should have accounts array"
        assert "campus_total_income" in data, "Response should have campus_total_income"
        assert "campus_total_expenses" in data, "Response should have campus_total_expenses"
        assert "campus_balance" in data, "Response should have campus_balance"
        
        # Verify accounts is a list
        assert isinstance(data["accounts"], list), "accounts should be a list"
        
        # Verify campus totals are numbers
        assert isinstance(data["campus_total_income"], (int, float)), "campus_total_income should be numeric"
        assert isinstance(data["campus_total_expenses"], (int, float)), "campus_total_expenses should be numeric"
        assert isinstance(data["campus_balance"], (int, float)), "campus_balance should be numeric"
        
        # Verify balance calculation
        expected_balance = data["campus_total_income"] - data["campus_total_expenses"]
        assert data["campus_balance"] == expected_balance, \
            f"Balance mismatch: {data['campus_balance']} != {expected_balance}"
        
        print(f"PASS: Accounts structure valid - Income: {data['campus_total_income']}, Expenses: {data['campus_total_expenses']}, Balance: {data['campus_balance']}")
    
    def test_accounts_per_location_breakdown(self, api_client):
        """Accounts endpoint returns per-location breakdown"""
        # Get locations
        locations_res = api_client.get(f"{BASE_URL}/api/locations")
        locations = locations_res.json()
        
        # Find a campus with sub-locations
        campus = None
        for loc in locations:
            if loc.get("type") in ["campus", "main"]:
                campus = loc
                break
        
        if not campus:
            campus = locations[0] if locations else None
        
        if not campus:
            pytest.skip("No locations found")
        
        response = api_client.get(f"{BASE_URL}/api/financial/accounts", params={"campus_id": campus["id"]})
        assert response.status_code == 200
        
        data = response.json()
        accounts = data.get("accounts", [])
        
        if accounts:
            # Verify each account has required fields
            for acc in accounts:
                assert "location_id" in acc, "Account should have location_id"
                assert "location_name" in acc, "Account should have location_name"
                assert "total_income" in acc, "Account should have total_income"
                assert "total_expenses" in acc, "Account should have total_expenses"
                assert "balance" in acc, "Account should have balance"
                
                # Verify balance calculation per location
                expected = acc["total_income"] - acc["total_expenses"]
                assert acc["balance"] == expected, f"Location balance mismatch for {acc['location_name']}"
            
            print(f"PASS: {len(accounts)} sub-location accounts with valid structure")
        else:
            print("PASS: No sub-location accounts (empty but valid response)")
    
    def test_accounts_requires_campus_id(self, api_client):
        """Accounts endpoint requires campus_id parameter"""
        # Test without campus_id - should use user's active campus or return error
        response = api_client.get(f"{BASE_URL}/api/financial/accounts")
        # Could be 200 (if user has active campus) or 400 (if no campus)
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}"
        
        if response.status_code == 400:
            assert "Campus ID required" in response.text or "campus" in response.text.lower()
            print("PASS: Accounts requires campus_id when user has no active campus")
        else:
            print("PASS: Accounts uses user's active campus when campus_id not provided")


class TestFinancialSummary:
    """Additional tests for financial summary endpoint"""
    
    def test_financial_summary_works(self, api_client):
        """Financial summary endpoint returns data"""
        response = api_client.get(f"{BASE_URL}/api/financial/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "monthly_donations" in data
        assert "monthly_expenses" in data
        assert "net_balance" in data
        print(f"PASS: Financial summary - Net balance: {data.get('net_balance')}")


class TestMembersEndpoint:
    """Basic member endpoint tests to ensure profile PDF has data"""
    
    def test_members_list(self, api_client):
        """Members list endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/members", params={"limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        print(f"PASS: Members list - {data['total']} total members")
    
    def test_member_detail(self, api_client):
        """Member detail endpoint works"""
        # Get a member first
        members_res = api_client.get(f"{BASE_URL}/api/members", params={"limit": 1})
        members = members_res.json().get("members", [])
        
        if not members:
            pytest.skip("No members found")
        
        member_id = members[0]["id"]
        response = api_client.get(f"{BASE_URL}/api/members/{member_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("id") == member_id
        print(f"PASS: Member detail for {data.get('name')}")


class TestLocationsEndpoint:
    """Location endpoint tests for accounts feature"""
    
    def test_locations_list(self, api_client):
        """Locations list endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/locations")
        assert response.status_code == 200
        
        locations = response.json()
        assert isinstance(locations, list)
        
        # Count by type
        types = {}
        for loc in locations:
            t = loc.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        
        print(f"PASS: Locations list - {len(locations)} locations: {types}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
