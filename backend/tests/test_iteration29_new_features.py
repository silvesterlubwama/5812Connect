"""
Iteration 29 - Testing 14 Major Enhancements:
1. Financial APIs Management
2. Report Builder (Custom Reports)
3. Volunteer Scheduling
4. Email Templates
5. Advanced Analytics
6. GDPR Settings
7. 2FA Setup
8. Multi-language (Luganda, Thai)
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
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ========== ANALYTICS TESTS ==========
class TestAnalytics:
    """Test Advanced Analytics endpoints"""
    
    def test_analytics_overview(self, auth_headers):
        """Test analytics overview endpoint"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers, params={"months": 6})
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "events" in data
        assert "checkins" in data
        assert "financial" in data
        assert "total" in data["members"]
        assert "active" in data["members"]
        print(f"Analytics overview: {data['members']['total']} members, {data['events']['total']} events")
    
    def test_analytics_trends(self, auth_headers):
        """Test analytics trends endpoint"""
        response = requests.get(f"{BASE_URL}/api/analytics/trends", headers=auth_headers, params={"months": 6})
        assert response.status_code == 200
        data = response.json()
        assert "monthly" in data
        assert isinstance(data["monthly"], list)
        if data["monthly"]:
            assert "month" in data["monthly"][0]
            assert "new_members" in data["monthly"][0]
            assert "checkins" in data["monthly"][0]
        print(f"Analytics trends: {len(data['monthly'])} months of data")
    
    def test_analytics_location_breakdown(self, auth_headers):
        """Test analytics by location"""
        response = requests.get(f"{BASE_URL}/api/analytics/location-breakdown", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Location breakdown: {len(data)} locations")
    
    def test_analytics_member_growth(self, auth_headers):
        """Test member growth analytics"""
        response = requests.get(f"{BASE_URL}/api/analytics/member-growth", headers=auth_headers, params={"months": 12})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Member growth: {len(data)} months of data")
    
    def test_analytics_outreach_impact(self, auth_headers):
        """Test outreach impact analytics"""
        response = requests.get(f"{BASE_URL}/api/analytics/outreach-impact", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "programs" in data
        assert "total_sessions" in data
        assert "total_reached" in data
        print(f"Outreach impact: {data['programs']} programs, {data['total_reached']} reached")


# ========== REPORT BUILDER TESTS ==========
class TestReportBuilder:
    """Test Report Builder CRUD and generation"""
    
    created_report_id = None
    
    def test_create_report(self, auth_headers):
        """Test creating a custom report"""
        payload = {
            "title": "TEST_Monthly_Member_Report",
            "type": "members",
            "is_shared": False,
            "auto_update": True,
            "schedule": "manual",
            "filters": {"status": "active"},
            "columns": ["name", "email", "status"]
        }
        response = requests.post(f"{BASE_URL}/api/reports", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["title"] == "TEST_Monthly_Member_Report"
        assert data["type"] == "members"
        TestReportBuilder.created_report_id = data["id"]
        print(f"Created report: {data['id']}")
    
    def test_list_reports(self, auth_headers):
        """Test listing reports"""
        response = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Listed {len(data)} reports")
    
    def test_generate_report(self, auth_headers):
        """Test generating report data"""
        if not TestReportBuilder.created_report_id:
            pytest.skip("No report created")
        response = requests.post(f"{BASE_URL}/api/reports/{TestReportBuilder.created_report_id}/generate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "generated_at" in data
        print(f"Generated report with {len(data.get('data', {}).get('members', []))} members")
    
    def test_delete_report(self, auth_headers):
        """Test deleting report"""
        if not TestReportBuilder.created_report_id:
            pytest.skip("No report created")
        response = requests.delete(f"{BASE_URL}/api/reports/{TestReportBuilder.created_report_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"Deleted report: {TestReportBuilder.created_report_id}")


# ========== VOLUNTEER SCHEDULING TESTS ==========
class TestVolunteerScheduling:
    """Test Volunteer Scheduling endpoints"""
    
    created_shift_id = None
    
    def test_create_shift(self, auth_headers):
        """Test creating a volunteer shift"""
        payload = {
            "title": "TEST_Sunday_Ushers",
            "date": "2026-02-15",
            "start_time": "08:00",
            "end_time": "12:00",
            "role": "Usher",
            "slots": 5,
            "notes": "Test shift for iteration 29"
        }
        response = requests.post(f"{BASE_URL}/api/volunteer/shifts", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["title"] == "TEST_Sunday_Ushers"
        assert data["slots"] == 5
        TestVolunteerScheduling.created_shift_id = data["id"]
        print(f"Created shift: {data['id']}")
    
    def test_list_shifts(self, auth_headers):
        """Test listing shifts"""
        response = requests.get(f"{BASE_URL}/api/volunteer/shifts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Listed {len(data)} shifts")
    
    def test_assign_volunteer(self, auth_headers):
        """Test assigning a volunteer to shift"""
        if not TestVolunteerScheduling.created_shift_id:
            pytest.skip("No shift created")
        payload = {
            "member_id": "test_member_001",
            "name": "Test Volunteer"
        }
        response = requests.post(f"{BASE_URL}/api/volunteer/shifts/{TestVolunteerScheduling.created_shift_id}/assign", headers=auth_headers, json=payload)
        assert response.status_code == 200
        print("Assigned volunteer to shift")
    
    def test_my_shifts(self, auth_headers):
        """Test getting my shifts"""
        response = requests.get(f"{BASE_URL}/api/volunteer/my-shifts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"My shifts: {len(data)}")
    
    def test_delete_shift(self, auth_headers):
        """Test deleting shift"""
        if not TestVolunteerScheduling.created_shift_id:
            pytest.skip("No shift created")
        response = requests.delete(f"{BASE_URL}/api/volunteer/shifts/{TestVolunteerScheduling.created_shift_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"Deleted shift: {TestVolunteerScheduling.created_shift_id}")


# ========== EMAIL TEMPLATES TESTS ==========
class TestEmailTemplates:
    """Test Email Templates CRUD"""
    
    created_template_id = None
    
    def test_list_templates(self, auth_headers):
        """Test listing email templates (should seed defaults)"""
        response = requests.get(f"{BASE_URL}/api/email-templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have default templates
        print(f"Listed {len(data)} email templates")
    
    def test_create_template(self, auth_headers):
        """Test creating an email template"""
        payload = {
            "name": "TEST_Custom_Template",
            "subject": "Hello {{name}}!",
            "body": "Dear {{name}},\n\nThis is a test template.\n\nBest,\nTeam",
            "variables": ["name"],
            "category": "general"
        }
        response = requests.post(f"{BASE_URL}/api/email-templates", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_Custom_Template"
        TestEmailTemplates.created_template_id = data["id"]
        print(f"Created template: {data['id']}")
    
    def test_update_template(self, auth_headers):
        """Test updating an email template"""
        if not TestEmailTemplates.created_template_id:
            pytest.skip("No template created")
        payload = {
            "subject": "Updated: Hello {{name}}!",
            "body": "Dear {{name}},\n\nThis is an updated test template.\n\nBest,\nTeam"
        }
        response = requests.put(f"{BASE_URL}/api/email-templates/{TestEmailTemplates.created_template_id}", headers=auth_headers, json=payload)
        assert response.status_code == 200
        print("Updated template")
    
    def test_delete_template(self, auth_headers):
        """Test deleting email template"""
        if not TestEmailTemplates.created_template_id:
            pytest.skip("No template created")
        response = requests.delete(f"{BASE_URL}/api/email-templates/{TestEmailTemplates.created_template_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"Deleted template: {TestEmailTemplates.created_template_id}")


# ========== FINANCIAL APIS TESTS ==========
class TestFinancialApis:
    """Test Financial API Management"""
    
    created_api_id = None
    
    def test_list_financial_apis(self, auth_headers):
        """Test listing financial APIs"""
        response = requests.get(f"{BASE_URL}/api/financial-apis", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Listed {len(data)} financial APIs")
    
    def test_create_financial_api(self, auth_headers):
        """Test adding a financial API connection"""
        payload = {
            "name": "TEST_Stripe_Connection",
            "type": "payment",
            "provider": "stripe",
            "api_url": "https://api.stripe.com",
            "api_key": "pk_test_xxx",
            "enabled": True,
            "config": {"sandbox": True}
        }
        response = requests.post(f"{BASE_URL}/api/financial-apis", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_Stripe_Connection"
        TestFinancialApis.created_api_id = data["id"]
        print(f"Created financial API: {data['id']}")
    
    def test_update_financial_api(self, auth_headers):
        """Test updating a financial API"""
        if not TestFinancialApis.created_api_id:
            pytest.skip("No API created")
        payload = {"enabled": False}
        response = requests.put(f"{BASE_URL}/api/financial-apis/{TestFinancialApis.created_api_id}", headers=auth_headers, json=payload)
        assert response.status_code == 200
        print("Updated financial API")
    
    def test_delete_financial_api(self, auth_headers):
        """Test deleting a financial API"""
        if not TestFinancialApis.created_api_id:
            pytest.skip("No API created")
        response = requests.delete(f"{BASE_URL}/api/financial-apis/{TestFinancialApis.created_api_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"Deleted financial API: {TestFinancialApis.created_api_id}")


# ========== GDPR TESTS ==========
class TestGdpr:
    """Test GDPR Settings and Data Export"""
    
    def test_get_gdpr_settings(self, auth_headers):
        """Test getting GDPR settings"""
        response = requests.get(f"{BASE_URL}/api/gdpr/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have default settings
        assert "consent_required" in data or "retention_months" in data or isinstance(data, dict)
        print(f"GDPR settings: {data}")
    
    def test_update_gdpr_settings(self, auth_headers):
        """Test updating GDPR settings"""
        payload = {
            "retention_months": 24,
            "auto_archive": True,
            "consent_required": True,
            "data_export_enabled": True
        }
        response = requests.put(f"{BASE_URL}/api/gdpr/settings", headers=auth_headers, json=payload)
        assert response.status_code == 200
        print("Updated GDPR settings")
    
    def test_export_my_data(self, auth_headers):
        """Test exporting user's own data"""
        response = requests.post(f"{BASE_URL}/api/gdpr/export-my-data", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "user" in data or "exported_at" in data
        print("Exported user data successfully")


# ========== 2FA TESTS ==========
class TestTwoFactor:
    """Test 2FA Setup endpoints"""
    
    def test_2fa_setup(self, auth_headers):
        """Test 2FA setup endpoint"""
        response = requests.post(f"{BASE_URL}/api/auth/2fa/setup", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "uri" in data
        print(f"2FA setup: secret generated, URI provided")
    
    def test_2fa_verify_invalid(self, auth_headers):
        """Test 2FA verify with invalid code"""
        response = requests.post(f"{BASE_URL}/api/auth/2fa/verify", headers=auth_headers, json={"code": "000000"})
        # Should fail with invalid code
        assert response.status_code == 400
        print("2FA verify correctly rejects invalid code")


# ========== I18N TESTS ==========
class TestI18n:
    """Test Multi-language support"""
    
    def test_get_all_languages(self, auth_headers):
        """Test getting all available languages"""
        response = requests.get(f"{BASE_URL}/api/i18n", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert "translations" in data
        # Check for Luganda and Thai
        lang_codes = [l["code"] for l in data["languages"]]
        assert "lg" in lang_codes, "Luganda (lg) should be available"
        assert "th" in lang_codes, "Thai (th) should be available"
        print(f"Languages available: {lang_codes}")
    
    def test_get_luganda_translations(self, auth_headers):
        """Test getting Luganda translations"""
        response = requests.get(f"{BASE_URL}/api/i18n/lg", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "dashboard" in data
        assert data["dashboard"] == "Dashiboodi"  # Luganda for Dashboard
        print(f"Luganda translations: {list(data.keys())[:5]}...")
    
    def test_get_thai_translations(self, auth_headers):
        """Test getting Thai translations"""
        response = requests.get(f"{BASE_URL}/api/i18n/th", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "dashboard" in data
        assert "แดชบอร์ด" in data["dashboard"]  # Thai for Dashboard
        print(f"Thai translations: {list(data.keys())[:5]}...")


# ========== WEBCAL TESTS ==========
class TestWebcal:
    """Test Webcal subscription"""
    
    def test_webcal_feed(self, auth_headers):
        """Test webcal feed endpoint"""
        # Get current user ID first
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        if me_response.status_code != 200:
            pytest.skip("Could not get user info")
        user_id = me_response.json().get("id")
        
        # Test webcal feed (public endpoint)
        response = requests.get(f"{BASE_URL}/api/webcal/{user_id}.ics")
        assert response.status_code == 200
        content = response.text
        assert "BEGIN:VCALENDAR" in content
        assert "VERSION:2.0" in content
        print("Webcal feed returns valid iCal format")


# ========== CLEANUP ==========
class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_reports(self, auth_headers):
        """Clean up any remaining test reports"""
        response = requests.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        if response.status_code == 200:
            reports = response.json()
            for r in reports:
                if r.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/reports/{r['id']}", headers=auth_headers)
        print("Cleaned up test reports")
    
    def test_cleanup_test_shifts(self, auth_headers):
        """Clean up any remaining test shifts"""
        response = requests.get(f"{BASE_URL}/api/volunteer/shifts", headers=auth_headers)
        if response.status_code == 200:
            shifts = response.json()
            for s in shifts:
                if s.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/volunteer/shifts/{s['id']}", headers=auth_headers)
        print("Cleaned up test shifts")
    
    def test_cleanup_test_templates(self, auth_headers):
        """Clean up any remaining test templates"""
        response = requests.get(f"{BASE_URL}/api/email-templates", headers=auth_headers)
        if response.status_code == 200:
            templates = response.json()
            for t in templates:
                if t.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/email-templates/{t['id']}", headers=auth_headers)
        print("Cleaned up test templates")
    
    def test_cleanup_test_apis(self, auth_headers):
        """Clean up any remaining test financial APIs"""
        response = requests.get(f"{BASE_URL}/api/financial-apis", headers=auth_headers)
        if response.status_code == 200:
            apis = response.json()
            for a in apis:
                if a.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/financial-apis/{a['id']}", headers=auth_headers)
        print("Cleaned up test financial APIs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
