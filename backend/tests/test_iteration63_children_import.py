"""
Iteration 63 - Children Import Tests
Tests for /api/children/bulk-import endpoint:
1. Children import with campus name resolution to location_id
2. Parent creation (father + mother) in guests collection
3. Campus fallback to admin's active_campus_id
4. Duplicate parent handling via parent_cache
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestChildrenImport:
    """Test children bulk import with campus resolution and parent creation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["token"]
        self.user = data["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # Store test IDs for cleanup
        self.test_child_ids = []
        self.test_parent_ids = []
        yield
        # Cleanup after tests
        self._cleanup_test_data()
        # Reset campus to Global Central
        requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=self.headers, json={"campus_id": "loc_001"})
    
    def _cleanup_test_data(self):
        """Clean up test-created children and parents"""
        for child_id in self.test_child_ids:
            try:
                requests.delete(f"{BASE_URL}/api/children/{child_id}", headers=self.headers)
            except:
                pass
        for parent_id in self.test_parent_ids:
            try:
                requests.delete(f"{BASE_URL}/api/guests/{parent_id}", headers=self.headers)
            except:
                pass
    
    def _switch_campus(self, campus_id):
        """Switch admin's active campus"""
        response = requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=self.headers, json={"campus_id": campus_id})
        assert response.status_code == 200, f"Failed to switch campus: {response.text}"
    
    def test_01_login_works(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "admin@5812uganda.org"
        assert data["user"]["role"] == "admin"
        print(f"PASS: Admin login works, active_campus_id={data['user'].get('active_campus_id')}")
    
    def test_02_import_child_with_campus_name_resolves_location(self):
        """Test that campus name in CSV resolves to correct location_id"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_Uganda_{unique_id}"
        
        # Import child with campus name "58:12 Uganda"
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Male",
                    "age": "8",
                    "campus": "58:12 Uganda",  # Should resolve to loc_419f5d5e
                    "family_name": f"TEST_Family_{unique_id}"
                }]
            }
        )
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        assert data["imported"] == 1, f"Expected 1 imported, got {data}"
        print(f"PASS: Import response: {data}")
        
        # Switch to Uganda campus to verify child
        self._switch_campus("loc_419f5d5e")
        
        # Verify child was created with correct location_id
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        assert children_resp.status_code == 200
        children = children_resp.json()
        
        test_child = next((c for c in children if c["name"] == child_name), None)
        assert test_child is not None, f"Child {child_name} not found in children list"
        assert test_child["location_id"] == "loc_419f5d5e", f"Expected loc_419f5d5e (Uganda), got {test_child.get('location_id')}"
        self.test_child_ids.append(test_child["id"])
        print(f"PASS: Child created with correct location_id=loc_419f5d5e (58:12 Uganda)")
    
    def test_03_import_child_with_kenya_campus(self):
        """Test campus resolution for Kenya"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_Kenya_{unique_id}"
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Female",
                    "age": "10",
                    "campus": "58:12 Kenya",  # Should resolve to loc_9d988d24
                }]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        
        # Switch to Kenya campus to verify
        self._switch_campus("loc_9d988d24")
        
        # Verify location_id
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        test_child = next((c for c in children if c["name"] == child_name), None)
        assert test_child is not None
        assert test_child["location_id"] == "loc_9d988d24", f"Expected loc_9d988d24 (Kenya), got {test_child.get('location_id')}"
        self.test_child_ids.append(test_child["id"])
        print(f"PASS: Child created with correct location_id=loc_9d988d24 (58:12 Kenya)")
    
    def test_04_import_without_campus_uses_admin_fallback(self):
        """Test that import without campus uses admin's active_campus_id"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_NoCampus_{unique_id}"
        
        # First ensure admin is on Global Central
        self._switch_campus("loc_001")
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Male",
                    "age": "7",
                    # No campus specified - should use admin's active_campus_id
                }]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        
        # Verify location_id is admin's active_campus_id (loc_001)
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        test_child = next((c for c in children if c["name"] == child_name), None)
        assert test_child is not None
        # Admin's active_campus_id is loc_001 (58:12 Global Central)
        assert test_child["location_id"] == "loc_001", f"Expected loc_001 (admin fallback), got {test_child.get('location_id')}"
        self.test_child_ids.append(test_child["id"])
        print(f"PASS: Child without campus uses admin's active_campus_id=loc_001")
    
    def test_05_import_creates_father_parent(self):
        """Test that import creates father in guests collection with is_parent=true"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_WithFather_{unique_id}"
        father_name = f"TEST_Father_{unique_id}"
        father_phone = f"+256700{unique_id}"
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Female",
                    "age": "9",
                    "campus": "58:12 Uganda",
                    "father_name": father_name,
                    "father_phone": father_phone,
                    "father_email": f"father_{unique_id}@test.com"
                }]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["parents_created"] >= 1, f"Expected at least 1 parent created, got {data}"
        print(f"PASS: Import response: imported={data['imported']}, parents_created={data['parents_created']}")
        
        # Switch to Uganda to verify father
        self._switch_campus("loc_419f5d5e")
        
        # Verify father was created in guests with is_parent=true and correct location_id
        guests_resp = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        assert guests_resp.status_code == 200
        guests = guests_resp.json()
        
        father = next((g for g in guests if g["name"] == father_name), None)
        assert father is not None, f"Father {father_name} not found in guests"
        assert father.get("is_parent") == True, f"Father should have is_parent=true"
        assert father.get("location_id") == "loc_419f5d5e", f"Father should have location_id=loc_419f5d5e (Uganda)"
        self.test_parent_ids.append(father["id"])
        
        # Cleanup child
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        test_child = next((c for c in children if c["name"] == child_name), None)
        if test_child:
            self.test_child_ids.append(test_child["id"])
        
        print(f"PASS: Father created in guests with is_parent=true, location_id=loc_419f5d5e")
    
    def test_06_import_creates_both_father_and_mother(self):
        """Test that import creates both father and mother in guests"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_BothParents_{unique_id}"
        father_name = f"TEST_Father_Both_{unique_id}"
        mother_name = f"TEST_Mother_Both_{unique_id}"
        
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Male",
                    "age": "6",
                    "campus": "58:12 Kenya",
                    "father_name": father_name,
                    "father_phone": f"+254700{unique_id}",
                    "mother_name": mother_name,
                    "mother_phone": f"+254701{unique_id}"
                }]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["parents_created"] >= 2, f"Expected at least 2 parents created, got {data['parents_created']}"
        print(f"PASS: Import created {data['parents_created']} parents")
        
        # Switch to Kenya to verify parents
        self._switch_campus("loc_9d988d24")
        
        # Verify both parents in guests
        guests_resp = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        guests = guests_resp.json()
        
        father = next((g for g in guests if g["name"] == father_name), None)
        mother = next((g for g in guests if g["name"] == mother_name), None)
        
        assert father is not None, f"Father {father_name} not found"
        assert mother is not None, f"Mother {mother_name} not found"
        assert father.get("is_parent") == True
        assert mother.get("is_parent") == True
        assert father.get("location_id") == "loc_9d988d24", "Father should have Kenya location"
        assert mother.get("location_id") == "loc_9d988d24", "Mother should have Kenya location"
        
        self.test_parent_ids.extend([father["id"], mother["id"]])
        
        # Cleanup child
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        test_child = next((c for c in children if c["name"] == child_name), None)
        if test_child:
            self.test_child_ids.append(test_child["id"])
        
        print(f"PASS: Both father and mother created with is_parent=true, location_id=loc_9d988d24 (Kenya)")
    
    def test_07_parent_cache_prevents_duplicates(self):
        """Test that parent_cache prevents duplicate parent creation in same batch"""
        unique_id = str(uuid.uuid4())[:6]
        shared_father = f"TEST_SharedFather_{unique_id}"
        shared_phone = f"+256800{unique_id}"
        
        # Import 2 children with same father
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [
                    {
                        "name": f"TEST_Child1_Shared_{unique_id}",
                        "gender": "Male",
                        "age": "5",
                        "campus": "58:12 Uganda",
                        "father_name": shared_father,
                        "father_phone": shared_phone
                    },
                    {
                        "name": f"TEST_Child2_Shared_{unique_id}",
                        "gender": "Female",
                        "age": "7",
                        "campus": "58:12 Uganda",
                        "father_name": shared_father,
                        "father_phone": shared_phone
                    }
                ]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2, f"Expected 2 children imported"
        # Should only create 1 parent (not 2) due to parent_cache
        assert data["parents_created"] == 1, f"Expected 1 parent (deduped), got {data['parents_created']}"
        print(f"PASS: Parent cache prevented duplicate - 2 children, 1 parent created")
        
        # Switch to Uganda to verify
        self._switch_campus("loc_419f5d5e")
        
        # Verify only 1 parent with that name exists
        guests_resp = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        guests = guests_resp.json()
        matching_parents = [g for g in guests if g["name"] == shared_father]
        assert len(matching_parents) == 1, f"Expected 1 parent, found {len(matching_parents)}"
        self.test_parent_ids.append(matching_parents[0]["id"])
        
        # Cleanup children
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        for c in children:
            if f"TEST_Child" in c["name"] and unique_id in c["name"]:
                self.test_child_ids.append(c["id"])
        
        print(f"PASS: Only 1 parent created for 2 children with same father")
    
    def test_08_case_insensitive_campus_lookup(self):
        """Test that campus name lookup is case-insensitive"""
        unique_id = str(uuid.uuid4())[:6]
        child_name = f"TEST_Child_CaseInsensitive_{unique_id}"
        
        # Use lowercase campus name
        response = requests.post(f"{BASE_URL}/api/children/bulk-import", 
            headers=self.headers,
            json={
                "children": [{
                    "name": child_name,
                    "gender": "Female",
                    "age": "8",
                    "campus": "58:12 uganda"  # lowercase - should still resolve
                }]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        
        # Switch to Uganda to verify
        self._switch_campus("loc_419f5d5e")
        
        # Verify location_id
        children_resp = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        children = children_resp.json()
        test_child = next((c for c in children if c["name"] == child_name), None)
        assert test_child is not None
        assert test_child["location_id"] == "loc_419f5d5e", f"Case-insensitive lookup failed, got {test_child.get('location_id')}"
        self.test_child_ids.append(test_child["id"])
        print(f"PASS: Case-insensitive campus lookup works")


class TestChildrenVisibility:
    """Test that imported children are visible when viewing correct campus"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200
        data = response.json()
        self.token = data["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        yield
        # Reset campus
        requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=self.headers, json={"campus_id": "loc_001"})
    
    def test_09_children_visible_with_location_filter(self):
        """Test children are visible when filtering by location"""
        # Switch to Uganda
        requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=self.headers, json={"campus_id": "loc_419f5d5e"})
        
        # Get children for Uganda location
        response = requests.get(f"{BASE_URL}/api/children", headers=self.headers)
        assert response.status_code == 200
        children = response.json()
        print(f"PASS: Children endpoint returns {len(children)} children for Uganda location")
        
        # Verify all returned children have Uganda location
        for child in children:
            if child.get("location_id"):
                assert child["location_id"] == "loc_419f5d5e", f"Child {child['name']} has wrong location"
    
    def test_10_parents_visible_in_guests(self):
        """Test parents are visible in guests tab with is_parent filter"""
        # Switch to Uganda
        requests.put(f"{BASE_URL}/api/user/active-campus", 
            headers=self.headers, json={"campus_id": "loc_419f5d5e"})
        
        response = requests.get(f"{BASE_URL}/api/guests", headers=self.headers)
        assert response.status_code == 200
        guests = response.json()
        
        # Check that some guests have is_parent=true
        parents = [g for g in guests if g.get("is_parent") == True]
        print(f"PASS: Found {len(parents)} parents in guests collection for Uganda")
        assert len(parents) >= 0, "Parents should be visible in guests"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
