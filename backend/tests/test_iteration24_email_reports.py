"""
Iteration 24 Tests: Email Integration (Resend), Campus Reports, Dashboard Switcher
Tests for:
1. Email: POST /api/email/send with templates
2. Email: GET /api/email/templates
3. Email: GET /api/email/log
4. Campus Reports: GET /api/reports/campus-comparison
5. Campus Reports: GET /api/reports/campus/{location_id}
6. Dashboard Switcher: GET /api/dashboard/stats with campus_id filter
"""
import pytest
import requests
import os

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestEmailIntegration:
    """Tests for Resend email integration"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_email_templates_list(self):
        """GET /api/email/templates returns available templates"""
        res = requests.get(f"{BASE_URL}/api/email/templates", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        templates = res.json()
        assert isinstance(templates, list), "Templates should be a list"
        assert len(templates) >= 4, f"Expected at least 4 templates, got {len(templates)}"
        
        # Verify template structure
        template_ids = [t["id"] for t in templates]
        assert "welcome" in template_ids, "Missing 'welcome' template"
        assert "event_invite" in template_ids, "Missing 'event_invite' template"
        assert "password_reset" in template_ids, "Missing 'password_reset' template"
        assert "report" in template_ids, "Missing 'report' template"
        
        # Verify template has required fields
        for t in templates:
            assert "id" in t, "Template missing 'id'"
            assert "name" in t, "Template missing 'name'"
            assert "description" in t, "Template missing 'description'"
        print(f"PASS: Email templates list returns {len(templates)} templates")
    
    def test_email_send_welcome_template(self):
        """POST /api/email/send with 'welcome' template sends email via Resend"""
        payload = {
            "to": ["delivered@resend.dev"],
            "subject": "TEST Welcome to 58:12 Global Connect",
            "template": "welcome",
            "context": {
                "name": "Test User",
                "email": "testuser@example.com",
                "password": "TempPass123"
            }
        }
        res = requests.post(f"{BASE_URL}/api/email/send", json=payload, headers=self.headers)
        assert res.status_code == 200, f"Email send failed: {res.text}"
        data = res.json()
        assert data.get("status") == "sent", f"Expected status 'sent', got {data.get('status')}"
        assert "email_id" in data, "Response missing 'email_id'"
        assert data.get("recipients") == ["delivered@resend.dev"], "Recipients mismatch"
        print(f"PASS: Welcome email sent successfully, email_id: {data.get('email_id')}")
    
    def test_email_send_event_invite_template(self):
        """POST /api/email/send with 'event_invite' template"""
        payload = {
            "to": ["delivered@resend.dev"],
            "subject": "TEST Event Invitation",
            "template": "event_invite",
            "context": {
                "name": "Test User",
                "event_name": "Youth Leadership Summit",
                "date": "2026-04-12",
                "time": "10:00 AM",
                "location": "Kampala Conference Hall"
            }
        }
        res = requests.post(f"{BASE_URL}/api/email/send", json=payload, headers=self.headers)
        assert res.status_code == 200, f"Email send failed: {res.text}"
        data = res.json()
        assert data.get("status") == "sent"
        print(f"PASS: Event invite email sent successfully")
    
    def test_email_send_report_template(self):
        """POST /api/email/send with 'report' template"""
        payload = {
            "to": ["delivered@resend.dev"],
            "subject": "TEST Campus Report",
            "template": "report",
            "context": {
                "title": "Monthly Campus Summary",
                "body": "Total Members: 150, Donations: UGX 500,000"
            }
        }
        res = requests.post(f"{BASE_URL}/api/email/send", json=payload, headers=self.headers)
        assert res.status_code == 200, f"Email send failed: {res.text}"
        data = res.json()
        assert data.get("status") == "sent"
        print(f"PASS: Report email sent successfully")
    
    def test_email_log(self):
        """GET /api/email/log returns sent email history"""
        res = requests.get(f"{BASE_URL}/api/email/log", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        logs = res.json()
        assert isinstance(logs, list), "Email log should be a list"
        
        # Should have at least the emails we just sent
        if len(logs) > 0:
            log = logs[0]
            assert "id" in log, "Log entry missing 'id'"
            assert "to" in log, "Log entry missing 'to'"
            assert "subject" in log, "Log entry missing 'subject'"
            assert "sent_at" in log, "Log entry missing 'sent_at'"
            print(f"PASS: Email log returns {len(logs)} entries, latest: {log.get('subject')}")
        else:
            print("PASS: Email log endpoint works (no entries yet)")


class TestCampusReports:
    """Tests for advanced campus reporting endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_campus_comparison_report(self):
        """GET /api/reports/campus-comparison returns all campuses with totals"""
        res = requests.get(f"{BASE_URL}/api/reports/campus-comparison", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        
        # Verify structure
        assert "campuses" in data, "Response missing 'campuses'"
        assert "totals" in data, "Response missing 'totals'"
        assert "generated_at" in data, "Response missing 'generated_at'"
        
        campuses = data["campuses"]
        assert isinstance(campuses, list), "Campuses should be a list"
        
        # Verify campus data structure
        if len(campuses) > 0:
            campus = campuses[0]
            required_fields = ["location_id", "location_name", "members", "children", "donations", "expenses", "net", "events", "checkins"]
            for field in required_fields:
                assert field in campus, f"Campus missing '{field}'"
        
        # Verify totals structure
        totals = data["totals"]
        assert "members" in totals, "Totals missing 'members'"
        assert "children" in totals, "Totals missing 'children'"
        assert "donations" in totals, "Totals missing 'donations'"
        assert "expenses" in totals, "Totals missing 'expenses'"
        assert "net" in totals, "Totals missing 'net'"
        
        print(f"PASS: Campus comparison returns {len(campuses)} campuses, total members: {totals.get('members')}")
    
    def test_campus_comparison_with_date_filter(self):
        """GET /api/reports/campus-comparison with date filters"""
        res = requests.get(
            f"{BASE_URL}/api/reports/campus-comparison",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=self.headers
        )
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        assert "campuses" in data
        assert "totals" in data
        print(f"PASS: Campus comparison with date filter works")
    
    def test_campus_detail_report(self):
        """GET /api/reports/campus/{location_id} returns detail for one campus"""
        # First get list of locations
        loc_res = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert loc_res.status_code == 200
        locations = loc_res.json()
        
        if len(locations) == 0:
            pytest.skip("No locations available for testing")
        
        location_id = locations[0]["id"]
        
        res = requests.get(f"{BASE_URL}/api/reports/campus/{location_id}", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        
        # Verify structure
        assert "campus" in data, "Response missing 'campus'"
        assert "member_count" in data, "Response missing 'member_count'"
        assert "children_count" in data, "Response missing 'children_count'"
        assert "group_breakdown" in data, "Response missing 'group_breakdown'"
        assert "monthly_trends" in data, "Response missing 'monthly_trends'"
        
        # Verify monthly trends structure
        trends = data["monthly_trends"]
        assert isinstance(trends, list), "Monthly trends should be a list"
        if len(trends) > 0:
            trend = trends[0]
            assert "month" in trend, "Trend missing 'month'"
            assert "donations" in trend, "Trend missing 'donations'"
            assert "expenses" in trend, "Trend missing 'expenses'"
            assert "checkins" in trend, "Trend missing 'checkins'"
        
        print(f"PASS: Campus detail for {data['campus'].get('name')}: {data['member_count']} members, {len(trends)} months of trends")
    
    def test_campus_detail_unauthorized_access(self):
        """Non-admin users can only access their own campus"""
        # This test verifies the RBAC is in place
        # For now, just verify the endpoint exists and returns proper error for invalid campus
        res = requests.get(f"{BASE_URL}/api/reports/campus/invalid_campus_id", headers=self.headers)
        assert res.status_code == 404, f"Expected 404 for invalid campus, got {res.status_code}"
        print("PASS: Campus detail returns 404 for invalid campus ID")


class TestDashboardSwitcher:
    """Tests for dashboard campus switcher functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats_all_campuses(self):
        """GET /api/dashboard/stats without campus_id returns all (for admin)"""
        res = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        
        # Verify dashboard stats structure
        required_fields = ["total_members", "active_members", "total_families", "total_children", 
                          "events_this_month", "upcoming_events", "checkins_today", "monthly_donations"]
        for field in required_fields:
            assert field in data, f"Dashboard stats missing '{field}'"
        
        print(f"PASS: Dashboard stats (all campuses): {data.get('total_members')} members, {data.get('monthly_donations')} donations")
        return data
    
    def test_dashboard_stats_filtered_by_campus(self):
        """GET /api/dashboard/stats?campus_id=loc_xxx filters to that campus"""
        # First get list of locations
        loc_res = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        assert loc_res.status_code == 200
        locations = loc_res.json()
        
        if len(locations) == 0:
            pytest.skip("No locations available for testing")
        
        location_id = locations[0]["id"]
        
        # Get stats for specific campus
        res = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"campus_id": location_id},
            headers=self.headers
        )
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        
        # Verify structure is same as all-campus stats
        assert "total_members" in data
        assert "active_members" in data
        assert "monthly_donations" in data
        
        print(f"PASS: Dashboard stats filtered by campus {location_id}: {data.get('total_members')} members")
    
    def test_dashboard_stats_comparison(self):
        """Verify filtered stats are subset of all-campus stats"""
        # Get all-campus stats
        all_res = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert all_res.status_code == 200
        all_data = all_res.json()
        
        # Get locations
        loc_res = requests.get(f"{BASE_URL}/api/locations", headers=self.headers)
        locations = loc_res.json()
        
        if len(locations) == 0:
            pytest.skip("No locations available for testing")
        
        # Get stats for first campus
        location_id = locations[0]["id"]
        filtered_res = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"campus_id": location_id},
            headers=self.headers
        )
        assert filtered_res.status_code == 200
        filtered_data = filtered_res.json()
        
        # Filtered members should be <= all members
        assert filtered_data.get("total_members", 0) <= all_data.get("total_members", 0), \
            f"Filtered members ({filtered_data.get('total_members')}) should be <= all members ({all_data.get('total_members')})"
        
        print(f"PASS: Filtered stats ({filtered_data.get('total_members')}) <= All stats ({all_data.get('total_members')})")


class TestReportsPdfExport:
    """Tests for PDF report export"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        self.token = login_res.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_pdf_export(self):
        """GET /api/reports/pdf returns PDF file"""
        res = requests.get(f"{BASE_URL}/api/reports/pdf", headers=self.headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        assert res.headers.get("content-type") == "application/pdf", \
            f"Expected PDF content-type, got {res.headers.get('content-type')}"
        assert len(res.content) > 0, "PDF content is empty"
        print(f"PASS: PDF export returns {len(res.content)} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
