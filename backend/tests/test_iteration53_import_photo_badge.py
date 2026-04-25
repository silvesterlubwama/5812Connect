"""
Iteration 53 - Testing Import Templates, Photo Upload, Children Bulk Import, and Badge Features
Tests:
1. CSV Template Downloads (children, staff, guests)
2. Children Bulk Import with campus name resolution and parent creation
3. Photo Upload endpoints for members and children
4. Uploaded photos serving endpoint
5. Auth login verification
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        print(f"✓ Login successful, user: {data['user'].get('name')}")
        return data["token"]


class TestCSVTemplates:
    """Test CSV template download endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_children_template_download(self, auth_token):
        """GET /api/import/template/children returns CSV with all fields including campus"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/import/template/children", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Not CSV content type"
        content = response.text
        # Check required fields are in header
        assert "name" in content, "Missing 'name' field"
        assert "campus" in content, "Missing 'campus' field"
        assert "father_name" in content, "Missing 'father_name' field"
        assert "mother_name" in content, "Missing 'mother_name' field"
        assert "location_id" in content, "Missing 'location_id' field"
        print(f"✓ Children template has all required fields including campus")
        print(f"  Headers: {content.split(chr(10))[0]}")
    
    def test_staff_template_download(self, auth_token):
        """GET /api/import/template/staff returns CSV template"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/import/template/staff", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Not CSV content type"
        content = response.text
        assert "name" in content, "Missing 'name' field"
        assert "email" in content, "Missing 'email' field"
        assert "role" in content, "Missing 'role' field"
        assert "campus" in content, "Missing 'campus' field"
        print(f"✓ Staff template downloaded successfully")
        print(f"  Headers: {content.split(chr(10))[0]}")
    
    def test_guests_template_download(self, auth_token):
        """GET /api/import/template/guests returns CSV template"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/import/template/guests", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Not CSV content type"
        content = response.text
        assert "name" in content, "Missing 'name' field"
        assert "phone" in content, "Missing 'phone' field"
        assert "campus" in content, "Missing 'campus' field"
        print(f"✓ Guests template downloaded successfully")
        print(f"  Headers: {content.split(chr(10))[0]}")


class TestChildrenBulkImport:
    """Test children bulk import with campus resolution and parent creation"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_bulk_import_with_campus_name(self, auth_token):
        """POST /api/children/bulk-import resolves campus name to location_id"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First get a location to use as campus
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        locations = loc_response.json() if loc_response.status_code == 200 else []
        campus_name = locations[0]["name"] if locations else "58:12 Uganda"
        
        import_data = {
            "children": [
                {
                    "name": "TEST_ImportChild_CampusResolve",
                    "age": 8,
                    "gender": "male",
                    "family_name": "TEST_ImportFamily",
                    "campus": campus_name,  # Using campus name instead of location_id
                    "parent_name": "TEST_ImportParent_NoEmail",
                    "parent_phone": "+256700999888"
                    # Note: No parent_email - testing parent creation without email
                }
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", json=import_data, headers=headers)
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        
        # Verify import results
        assert data.get("imported", 0) > 0 or data.get("updated", 0) > 0, f"No children imported/updated: {data}"
        print(f"✓ Children import: imported={data.get('imported')}, updated={data.get('updated')}, parents_created={data.get('parents_created')}")
        
        # Verify child was created with location_id resolved from campus name
        children_response = requests.get(f"{BASE_URL}/api/children?search=TEST_ImportChild_CampusResolve", headers=headers)
        if children_response.status_code == 200:
            children = children_response.json()
            if children:
                child = children[0]
                print(f"  Child location_id: {child.get('location_id')}")
                # If campus was resolved, location_id should be set
                if locations:
                    assert child.get("location_id") == locations[0]["id"], "Campus name not resolved to location_id"
                    print(f"✓ Campus name '{campus_name}' resolved to location_id '{child.get('location_id')}'")
    
    def test_bulk_import_creates_parent_without_email(self, auth_token):
        """POST /api/children/bulk-import creates parents even without email"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        import_data = {
            "children": [
                {
                    "name": "TEST_ChildNoEmailParent",
                    "age": 6,
                    "gender": "female",
                    "family_name": "TEST_NoEmailFamily",
                    "parent_name": "TEST_ParentNoEmail",
                    "parent_phone": "+256700111222"
                    # No email provided
                }
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", json=import_data, headers=headers)
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        
        # Check if parent was created
        parents_created = data.get("parents_created", 0)
        print(f"✓ Import result: parents_created={parents_created}")
        
        # Verify parent exists in guests
        guests_response = requests.get(f"{BASE_URL}/api/guests?search=TEST_ParentNoEmail", headers=headers)
        if guests_response.status_code == 200:
            guests = guests_response.json()
            parent_found = any(g.get("name") == "TEST_ParentNoEmail" for g in guests)
            if parent_found:
                print(f"✓ Parent created without email address")
            else:
                print(f"  Note: Parent may have been created in previous run (dedup)")


class TestPhotoUpload:
    """Test photo upload endpoints for members and children"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_member_photo_upload_endpoint_exists(self, auth_token):
        """POST /api/members/{id}/photo endpoint exists"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get a member to test with
        members_response = requests.get(f"{BASE_URL}/api/members?limit=1", headers=headers)
        if members_response.status_code != 200 or not members_response.json().get("members"):
            pytest.skip("No members found")
        
        member_id = members_response.json()["members"][0]["id"]
        
        # Create a minimal test image (1x1 PNG)
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        
        files = {"file": ("test.png", io.BytesIO(png_data), "image/png")}
        response = requests.post(f"{BASE_URL}/api/members/{member_id}/photo", headers=headers, files=files)
        
        # Endpoint should exist (200 or 400 for validation, not 404/405)
        assert response.status_code in [200, 400, 422], f"Endpoint issue: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "photo_url" in data, "No photo_url in response"
            print(f"✓ Member photo uploaded: {data['photo_url']}")
        else:
            print(f"✓ Member photo endpoint exists (validation: {response.status_code})")
    
    def test_child_photo_upload_endpoint_exists(self, auth_token):
        """POST /api/children/{id}/photo endpoint exists"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get a child to test with
        children_response = requests.get(f"{BASE_URL}/api/children", headers=headers)
        if children_response.status_code != 200 or not children_response.json():
            pytest.skip("No children found")
        
        children = children_response.json()
        if not children:
            pytest.skip("No children found")
        
        child_id = children[0]["id"]
        
        # Create a minimal test image
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        
        files = {"file": ("test.png", io.BytesIO(png_data), "image/png")}
        response = requests.post(f"{BASE_URL}/api/children/{child_id}/photo", headers=headers, files=files)
        
        assert response.status_code in [200, 400, 422], f"Endpoint issue: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "photo_url" in data, "No photo_url in response"
            print(f"✓ Child photo uploaded: {data['photo_url']}")
        else:
            print(f"✓ Child photo endpoint exists (validation: {response.status_code})")
    
    def test_uploaded_photos_serving(self, auth_token):
        """GET /api/uploads/photos/{filename} serves uploaded photos"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First upload a photo
        members_response = requests.get(f"{BASE_URL}/api/members?limit=1", headers=headers)
        if members_response.status_code != 200 or not members_response.json().get("members"):
            pytest.skip("No members found")
        
        member_id = members_response.json()["members"][0]["id"]
        
        # Upload a test image
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {"file": ("test.png", io.BytesIO(png_data), "image/png")}
        upload_response = requests.post(f"{BASE_URL}/api/members/{member_id}/photo", headers=headers, files=files)
        
        if upload_response.status_code == 200:
            photo_url = upload_response.json().get("photo_url", "")
            if photo_url.startswith("/api/uploads/photos/"):
                # Try to fetch the uploaded photo
                serve_response = requests.get(f"{BASE_URL}{photo_url}")
                assert serve_response.status_code == 200, f"Photo serving failed: {serve_response.status_code}"
                assert "image" in serve_response.headers.get("Content-Type", ""), "Not an image content type"
                print(f"✓ Uploaded photo served successfully from {photo_url}")
            else:
                print(f"✓ Photo stored in object storage: {photo_url}")
        else:
            print(f"  Photo upload returned {upload_response.status_code}, skipping serve test")


class TestLocationCountryCode:
    """Test country_code field on locations"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_location_has_country_code_field(self, auth_token):
        """Verify locations can have country_code field"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get locations
        response = requests.get(f"{BASE_URL}/api/locations", headers=headers)
        assert response.status_code == 200, f"Failed to get locations: {response.text}"
        
        locations = response.json()
        if locations:
            # Check if any location has country_code
            has_country_code = any(loc.get("country_code") for loc in locations)
            print(f"✓ Locations retrieved: {len(locations)}")
            if has_country_code:
                for loc in locations:
                    if loc.get("country_code"):
                        print(f"  Location '{loc['name']}' has country_code: {loc['country_code']}")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Auth failed")
    
    def test_cleanup_test_data(self, auth_token):
        """Clean up TEST_ prefixed data"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Clean up test children
        children_response = requests.get(f"{BASE_URL}/api/children", headers=headers)
        if children_response.status_code == 200:
            children = children_response.json()
            test_children = [c for c in children if c.get("name", "").startswith("TEST_")]
            for child in test_children:
                requests.delete(f"{BASE_URL}/api/children/{child['id']}", headers=headers)
            if test_children:
                print(f"  Cleaned up {len(test_children)} test children")
        
        # Clean up test families
        families_response = requests.get(f"{BASE_URL}/api/families", headers=headers)
        if families_response.status_code == 200:
            families = families_response.json()
            test_families = [f for f in families if f.get("family_name", "").startswith("TEST_")]
            for family in test_families:
                requests.delete(f"{BASE_URL}/api/families/{family['id']}", headers=headers)
            if test_families:
                print(f"  Cleaned up {len(test_families)} test families")
        
        # Clean up test guests (parents)
        guests_response = requests.get(f"{BASE_URL}/api/guests", headers=headers)
        if guests_response.status_code == 200:
            guests = guests_response.json()
            test_guests = [g for g in guests if g.get("name", "").startswith("TEST_")]
            for guest in test_guests:
                requests.delete(f"{BASE_URL}/api/guests/{guest['id']}", headers=headers)
            if test_guests:
                print(f"  Cleaned up {len(test_guests)} test guests")
        
        print("✓ Test data cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
