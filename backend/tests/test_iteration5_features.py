"""
Test suite for 58:12 Global Connect CRM - Iteration 5
Features tested:
- Login with the seeded admin account (tests/creds.py)
- Members API with gender Male/Female restriction
- Department based on location
- Access Control (residents, staff passes, guest requests, scan in/out)
- Reports & PDF export
- CSV file upload for members
- Document upload for members
"""
import pytest
import requests
import os
import io

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-tenant-scope.preview.emergentagent.com')


class TestAuth:
    """Authentication tests"""
    
    def test_login_admin_5812uganda(self):
        """Test login with the seeded admin account (tests/creds.py)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == creds.ADMIN_EMAIL
        assert data["user"]["role"] == "admin"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": creds.ADMIN_EMAIL,
        "password": creds.ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Authentication failed")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestMembers:
    """Members API tests"""
    
    def test_list_members(self, auth_headers):
        """Test listing members"""
        response = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "total" in data
        assert isinstance(data["members"], list)
    
    def test_create_member_with_male_gender(self, auth_headers):
        """Test creating member with male gender"""
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Male Member",
            "email": "test_male@example.com",
            "gender": "male",
            "role": "Staff"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["gender"] == "male"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{data['id']}", headers=auth_headers)
    
    def test_create_member_with_female_gender(self, auth_headers):
        """Test creating member with female gender"""
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Female Member",
            "email": "test_female@example.com",
            "gender": "female",
            "role": "Staff"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["gender"] == "female"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/members/{data['id']}", headers=auth_headers)
    
    def test_create_member_invalid_gender_rejected(self, auth_headers):
        """Test that invalid gender values are rejected"""
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json={
            "name": "TEST_Invalid Gender",
            "email": "test_invalid@example.com",
            "gender": "other",  # Should be rejected
            "role": "Staff"
        })
        assert response.status_code == 400
        assert "male or female" in response.json().get("detail", "").lower()


class TestLocations:
    """Locations API tests"""
    
    def test_list_locations(self, auth_headers):
        """Test listing locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_restricted_locations_exist(self, auth_headers):
        """Test that restricted locations are configured"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        restricted = [loc for loc in data if loc.get("is_restricted")]
        assert len(restricted) >= 5, f"Expected at least 5 restricted locations, found {len(restricted)}"


class TestAccessControl:
    """Access Control API tests - residents, staff passes, guest requests, scan"""
    
    @pytest.fixture
    def restricted_location_id(self, auth_headers):
        """Get a restricted location ID for testing"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        data = response.json()
        restricted = [loc for loc in data if loc.get("is_restricted")]
        if not restricted:
            pytest.skip("No restricted locations found")
        return restricted[0]["id"]
    
    @pytest.fixture
    def test_member_id(self, auth_headers):
        """Get a member ID for testing"""
        response = requests.get(f"{BASE_URL}/api/members?limit=1", headers=auth_headers)
        data = response.json()
        if not data.get("members"):
            pytest.skip("No members found")
        return data["members"][0]["id"]
    
    def test_list_residents(self, auth_headers, restricted_location_id):
        """Test listing residents for a restricted location"""
        response = requests.get(
            f"{BASE_URL}/api/access/residents",
            headers=auth_headers,
            params={"location_id": restricted_location_id}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_staff_passes(self, auth_headers, restricted_location_id):
        """Test listing staff passes for a restricted location"""
        response = requests.get(
            f"{BASE_URL}/api/access/staff-passes",
            headers=auth_headers,
            params={"location_id": restricted_location_id}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_guest_requests(self, auth_headers, restricted_location_id):
        """Test listing guest requests for a restricted location"""
        response = requests.get(
            f"{BASE_URL}/api/access/guest-requests",
            headers=auth_headers,
            params={"location_id": restricted_location_id}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_scan_log(self, auth_headers, restricted_location_id):
        """Test listing scan log for a restricted location"""
        response = requests.get(
            f"{BASE_URL}/api/access/scan-log",
            headers=auth_headers,
            params={"location_id": restricted_location_id}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_assign_resident(self, auth_headers, restricted_location_id, test_member_id):
        """Test assigning a resident to a restricted location"""
        response = requests.post(
            f"{BASE_URL}/api/access/residents",
            headers=auth_headers,
            json={
                "member_id": test_member_id,
                "location_id": restricted_location_id,
                "tags": ["test"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["member_id"] == test_member_id
        assert data["location_id"] == restricted_location_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/access/residents/{data['id']}", headers=auth_headers)
    
    def test_assign_staff_pass(self, auth_headers, restricted_location_id):
        """Test assigning staff access to a restricted location"""
        # First get a staff member
        response = requests.get(f"{BASE_URL}/api/members?role=Staff&limit=1", headers=auth_headers)
        members = response.json().get("members", [])
        if not members:
            pytest.skip("No staff members found")
        staff_id = members[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/access/staff-passes",
            headers=auth_headers,
            json={
                "staff_id": staff_id,
                "location_id": restricted_location_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["staff_id"] == staff_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/access/staff-passes/{data['id']}", headers=auth_headers)
    
    def test_request_guest_visit(self, auth_headers, restricted_location_id):
        """Test requesting a guest visit to a restricted location"""
        response = requests.post(
            f"{BASE_URL}/api/access/guest-requests",
            headers=auth_headers,
            json={
                "guest_name": "TEST_Guest Visitor",
                "guest_phone": "+256700111222",
                "location_id": restricted_location_id,
                "purpose": "Testing",
                "visit_date": "2026-04-15"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["guest_name"] == "TEST_Guest Visitor"
        assert data["status"] == "pending"
    
    def test_scan_requires_authorization(self, auth_headers, restricted_location_id, test_member_id):
        """Test that scan requires proper authorization"""
        # Try to scan without being assigned as resident or staff
        response = requests.post(
            f"{BASE_URL}/api/access/scan",
            headers=auth_headers,
            json={
                "member_id": "nonexistent_member",
                "location_id": restricted_location_id,
                "action": "in"
            }
        )
        assert response.status_code == 403
        assert "No access authorization" in response.json().get("detail", "")


class TestReports:
    """Reports API tests"""
    
    def test_report_summary(self, auth_headers):
        """Test getting report summary"""
        response = requests.get(f"{BASE_URL}/api/reports/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "members" in data
        assert "financial" in data
        assert "events" in data
        assert "locations" in data
        assert data["members"]["total"] >= 0
        assert data["members"]["active"] >= 0
    
    def test_report_summary_with_location_filter(self, auth_headers):
        """Test report summary with location filter"""
        # Get a location ID first
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = loc_response.json()
        if not locations:
            pytest.skip("No locations found")
        
        response = requests.get(
            f"{BASE_URL}/api/reports/summary",
            headers=auth_headers,
            params={"location_id": locations[0]["id"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["location_id"] == locations[0]["id"]
    
    def test_report_pdf_export(self, auth_headers):
        """Test PDF report export"""
        response = requests.get(
            f"{BASE_URL}/api/reports/pdf",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        assert "attachment" in response.headers.get("content-disposition", "")
        # Verify it's a valid PDF (starts with %PDF)
        assert response.content[:4] == b'%PDF'


class TestCSVImport:
    """CSV file upload tests"""
    
    def test_csv_members_import_endpoint_exists(self, auth_headers):
        """Test that CSV members import endpoint exists"""
        # Create a minimal CSV file
        csv_content = "name,email,phone,group\nTEST_CSV User,testcsv@example.com,+256700000000,Youth"
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        
        response = requests.post(
            f"{BASE_URL}/api/import/csv/members",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert "imported" in data
    
    def test_csv_children_parents_import_endpoint_exists(self, auth_headers):
        """Test that CSV children-parents import endpoint exists"""
        csv_content = "first_name,last_name,date_of_birth,grade,family_name\nTEST_Child,User,2015-01-01,3,TEST Family"
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        
        response = requests.post(
            f"{BASE_URL}/api/import/csv/children-parents",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert "imported_children" in data or "imported" in data
    
    def test_csv_staff_import_endpoint_exists(self, auth_headers):
        """Test that CSV staff import endpoint exists"""
        csv_content = "name,email,phone,national_id,role,department\nTEST_Staff User,teststaff@example.com,+256700111222,CM123456,Staff,Admin"
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        
        response = requests.post(
            f"{BASE_URL}/api/import/csv/staff",
            headers=auth_headers,
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert "imported" in data


class TestDocuments:
    """Document upload tests"""
    
    @pytest.fixture
    def test_member_id(self, auth_headers):
        """Get a member ID for testing"""
        response = requests.get(f"{BASE_URL}/api/members?limit=1", headers=auth_headers)
        data = response.json()
        if not data.get("members"):
            pytest.skip("No members found")
        return data["members"][0]["id"]
    
    def test_list_member_documents(self, auth_headers, test_member_id):
        """Test listing documents for a member"""
        response = requests.get(
            f"{BASE_URL}/api/members/{test_member_id}/documents",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_document_upload_requires_valid_file_type(self, auth_headers, test_member_id):
        """Test that document upload requires JPG/PNG"""
        # Try uploading a text file (should fail)
        files = {"file": ("test.txt", io.BytesIO(b"test content"), "text/plain")}
        data = {"doc_type": "id_scan"}
        
        response = requests.post(
            f"{BASE_URL}/api/members/{test_member_id}/documents",
            headers=auth_headers,
            files=files,
            data=data
        )
        assert response.status_code == 400
        assert "JPG/PNG" in response.json().get("detail", "")


class TestDepartmentByLocation:
    """Test department based on location"""
    
    def test_location_has_departments(self, auth_headers):
        """Test that locations have departments configured"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Find a location with departments
        locations_with_depts = [loc for loc in data if loc.get("departments")]
        assert len(locations_with_depts) > 0, "No locations with departments found"
        
        # Verify departments is a list
        for loc in locations_with_depts:
            assert isinstance(loc["departments"], list)


class TestFamiliesAndPeople:
    """Test families, children, and guests APIs"""
    
    def test_list_families(self, auth_headers):
        """Test listing families"""
        response = requests.get(f"{BASE_URL}/api/families", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_children(self, auth_headers):
        """Test listing children"""
        response = requests.get(f"{BASE_URL}/api/children", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_list_guests(self, auth_headers):
        """Test listing guests"""
        response = requests.get(f"{BASE_URL}/api/guests", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_create_family(self, auth_headers):
        """Test creating a family"""
        response = requests.post(
            f"{BASE_URL}/api/families",
            headers=auth_headers,
            json={
                "family_name": "TEST_Family",
                "primary_contact_name": "TEST Contact",
                "primary_contact_email": "testfamily@example.com"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["family_name"] == "TEST_Family"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/families/{data['id']}", headers=auth_headers)
    
    def test_create_child(self, auth_headers):
        """Test creating a child"""
        response = requests.post(
            f"{BASE_URL}/api/children",
            headers=auth_headers,
            json={
                "name": "TEST_Child",
                "date_of_birth": "2018-05-15",
                "gender": "male"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Child"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/children/{data['id']}", headers=auth_headers)
    
    def test_create_guest(self, auth_headers):
        """Test creating a guest"""
        response = requests.post(
            f"{BASE_URL}/api/guests",
            headers=auth_headers,
            json={
                "name": "TEST_Guest",
                "phone": "+256700999888",
                "visit_date": "2026-04-01"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TEST_Guest"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/guests/{data['id']}", headers=auth_headers)
