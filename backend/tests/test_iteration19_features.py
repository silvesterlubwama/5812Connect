"""
Iteration 19 Tests: Family/Child Editing, Duplicate Prevention, Soft-Delete, Recycle Bin, Parent Import as Guests, Silvester Admin
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": "admin@5812uganda.org",
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


# ========== SILVESTER ADMIN AUTO-PROMOTION ==========

class TestSilvesterAdmin:
    """Test silvester@lubwamas.org is auto-promoted to admin"""
    
    def test_silvester_exists_as_admin(self, api_client):
        """Verify silvester@lubwamas.org exists and has admin role"""
        response = api_client.get(f"{BASE_URL}/api/admin/users", params={"search": "silvester@lubwamas.org"})
        assert response.status_code == 200, f"Failed to list users: {response.text}"
        users = response.json()
        silvester = next((u for u in users if u.get("email") == "silvester@lubwamas.org"), None)
        assert silvester is not None, "silvester@lubwamas.org not found in users"
        assert silvester.get("role") == "admin", f"Expected admin role, got {silvester.get('role')}"
        print(f"PASS: silvester@lubwamas.org exists with role={silvester.get('role')}")


# ========== FAMILY EDITING ==========

class TestFamilyEditing:
    """Test family CRUD operations including edit"""
    
    def test_create_family(self, api_client):
        """Create a test family"""
        unique_name = f"TEST_Family_{uuid.uuid4().hex[:6]}"
        response = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": unique_name,
            "primary_contact_name": "Test Parent",
            "primary_contact_email": "testparent@example.com",
            "primary_contact_phone": "+256700111222",
            "address": "Test Address"
        })
        assert response.status_code == 200, f"Failed to create family: {response.text}"
        family = response.json()
        assert family.get("family_name") == unique_name
        assert "id" in family
        print(f"PASS: Created family {family['id']} with name {unique_name}")
        return family
    
    def test_update_family(self, api_client):
        """Create and update a family via PUT /api/families/{id}"""
        # Create first
        unique_name = f"TEST_EditFamily_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": unique_name,
            "primary_contact_name": "Original Contact",
            "primary_contact_email": "original@example.com",
            "primary_contact_phone": "+256700111333"
        })
        assert create_resp.status_code == 200, f"Failed to create family: {create_resp.text}"
        family = create_resp.json()
        family_id = family["id"]
        
        # Update
        updated_name = f"TEST_UpdatedFamily_{uuid.uuid4().hex[:6]}"
        update_resp = api_client.put(f"{BASE_URL}/api/families/{family_id}", json={
            "family_name": updated_name,
            "primary_contact_name": "Updated Contact",
            "primary_contact_email": "updated@example.com",
            "primary_contact_phone": "+256700111444",
            "address": "Updated Address"
        })
        assert update_resp.status_code == 200, f"Failed to update family: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("family_name") == updated_name, f"Expected {updated_name}, got {updated.get('family_name')}"
        assert updated.get("primary_contact_name") == "Updated Contact"
        print(f"PASS: Updated family {family_id} to name {updated_name}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/families/{family_id}")


# ========== CHILD EDITING ==========

class TestChildEditing:
    """Test child CRUD operations including edit"""
    
    def test_create_and_update_child(self, api_client):
        """Create and update a child via PUT /api/children/{id}"""
        # First create a family for the child
        family_name = f"TEST_ChildFamily_{uuid.uuid4().hex[:6]}"
        fam_resp = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": family_name,
            "primary_contact_name": "Parent"
        })
        assert fam_resp.status_code == 200
        family_id = fam_resp.json()["id"]
        
        # Create child
        child_name = f"TEST_Child_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/children", json={
            "name": child_name,
            "date_of_birth": "2018-05-15",
            "gender": "male",
            "family_id": family_id,
            "class_group": "Primary 2"
        })
        assert create_resp.status_code == 200, f"Failed to create child: {create_resp.text}"
        child = create_resp.json()
        child_id = child["id"]
        
        # Update child
        updated_name = f"TEST_UpdatedChild_{uuid.uuid4().hex[:6]}"
        update_resp = api_client.put(f"{BASE_URL}/api/children/{child_id}", json={
            "name": updated_name,
            "date_of_birth": "2018-06-20",
            "gender": "male",
            "family_id": family_id,
            "class_group": "Primary 3",
            "medical_notes": "Updated medical notes",
            "allergies": "Peanuts"
        })
        assert update_resp.status_code == 200, f"Failed to update child: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("name") == updated_name
        assert updated.get("class_group") == "Primary 3"
        assert updated.get("allergies") == "Peanuts"
        print(f"PASS: Updated child {child_id} to name {updated_name}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/children/{child_id}")
        api_client.delete(f"{BASE_URL}/api/families/{family_id}")


# ========== DUPLICATE PREVENTION ==========

class TestDuplicatePrevention:
    """Test duplicate prevention returns 409 for members, families, children, guests"""
    
    def test_member_duplicate_email(self, api_client):
        """POST /api/members should return 409 for duplicate email"""
        unique_email = f"test_dup_{uuid.uuid4().hex[:6]}@example.com"
        
        # Create first member
        resp1 = api_client.post(f"{BASE_URL}/api/members", json={
            "name": "First Member",
            "email": unique_email,
            "phone": "+256700999001",
            "gender": "male",
            "role": "Member",
            "group": "Youth"
        })
        assert resp1.status_code == 200, f"Failed to create first member: {resp1.text}"
        member1_id = resp1.json()["id"]
        
        # Try to create duplicate
        resp2 = api_client.post(f"{BASE_URL}/api/members", json={
            "name": "Duplicate Member",
            "email": unique_email,
            "phone": "+256700999002",
            "gender": "female",
            "role": "Member",
            "group": "Youth"
        })
        assert resp2.status_code == 409, f"Expected 409 for duplicate email, got {resp2.status_code}: {resp2.text}"
        print(f"PASS: Duplicate email returns 409")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/members/{member1_id}")
    
    def test_family_duplicate_name(self, api_client):
        """POST /api/families should return 409 for duplicate family_name"""
        unique_name = f"TEST_DupFamily_{uuid.uuid4().hex[:6]}"
        
        # Create first family
        resp1 = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": unique_name,
            "primary_contact_name": "Contact 1"
        })
        assert resp1.status_code == 200, f"Failed to create first family: {resp1.text}"
        family1_id = resp1.json()["id"]
        
        # Try to create duplicate
        resp2 = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": unique_name,
            "primary_contact_name": "Contact 2"
        })
        assert resp2.status_code == 409, f"Expected 409 for duplicate family name, got {resp2.status_code}: {resp2.text}"
        print(f"PASS: Duplicate family name returns 409")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/families/{family1_id}")
    
    def test_child_duplicate_name_family(self, api_client):
        """POST /api/children should return 409 for duplicate name+family_id"""
        # Create family
        family_name = f"TEST_DupChildFamily_{uuid.uuid4().hex[:6]}"
        fam_resp = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": family_name,
            "primary_contact_name": "Parent"
        })
        assert fam_resp.status_code == 200
        family_id = fam_resp.json()["id"]
        
        child_name = f"TEST_DupChild_{uuid.uuid4().hex[:6]}"
        
        # Create first child
        resp1 = api_client.post(f"{BASE_URL}/api/children", json={
            "name": child_name,
            "family_id": family_id,
            "gender": "male"
        })
        assert resp1.status_code == 200, f"Failed to create first child: {resp1.text}"
        child1_id = resp1.json()["id"]
        
        # Try to create duplicate
        resp2 = api_client.post(f"{BASE_URL}/api/children", json={
            "name": child_name,
            "family_id": family_id,
            "gender": "female"
        })
        assert resp2.status_code == 409, f"Expected 409 for duplicate child name+family, got {resp2.status_code}: {resp2.text}"
        print(f"PASS: Duplicate child name+family returns 409")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/children/{child1_id}")
        api_client.delete(f"{BASE_URL}/api/families/{family_id}")
    
    def test_guest_duplicate_name_email(self, api_client):
        """POST /api/guests should return 409 for duplicate name+email"""
        unique_name = f"TEST_DupGuest_{uuid.uuid4().hex[:6]}"
        unique_email = f"dupguest_{uuid.uuid4().hex[:6]}@example.com"
        
        # Create first guest
        resp1 = api_client.post(f"{BASE_URL}/api/guests", json={
            "name": unique_name,
            "email": unique_email,
            "phone": "+256700888001"
        })
        assert resp1.status_code == 200, f"Failed to create first guest: {resp1.text}"
        guest1_id = resp1.json()["id"]
        
        # Try to create duplicate
        resp2 = api_client.post(f"{BASE_URL}/api/guests", json={
            "name": unique_name,
            "email": unique_email,
            "phone": "+256700888002"
        })
        assert resp2.status_code == 409, f"Expected 409 for duplicate guest name+email, got {resp2.status_code}: {resp2.text}"
        print(f"PASS: Duplicate guest name+email returns 409")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/guests/{guest1_id}")


# ========== SOFT-DELETE & RECYCLE BIN ==========

class TestSoftDeleteRecycleBin:
    """Test soft-delete moves items to deleted_items and recycle bin operations"""
    
    def test_member_soft_delete_and_restore(self, api_client):
        """DELETE /api/members/{id} soft-deletes, then restore from recycle bin"""
        # Create member
        unique_email = f"test_softdel_{uuid.uuid4().hex[:6]}@example.com"
        create_resp = api_client.post(f"{BASE_URL}/api/members", json={
            "name": "TEST_SoftDeleteMember",
            "email": unique_email,
            "phone": "+256700777001",
            "gender": "male",
            "role": "Member",
            "group": "Youth"
        })
        assert create_resp.status_code == 200, f"Failed to create member: {create_resp.text}"
        member_id = create_resp.json()["id"]
        
        # Delete (soft-delete)
        del_resp = api_client.delete(f"{BASE_URL}/api/members/{member_id}")
        assert del_resp.status_code == 200, f"Failed to delete member: {del_resp.text}"
        
        # Verify member is gone from members collection
        get_resp = api_client.get(f"{BASE_URL}/api/members/{member_id}")
        assert get_resp.status_code == 404, f"Member should be 404 after delete, got {get_resp.status_code}"
        
        # Verify member appears in deleted_items
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items", params={"collection": "members"})
        assert deleted_resp.status_code == 200, f"Failed to get deleted items: {deleted_resp.text}"
        deleted_items = deleted_resp.json()
        deleted_member = next((i for i in deleted_items if i.get("id") == member_id), None)
        assert deleted_member is not None, f"Member {member_id} not found in deleted_items"
        assert deleted_member.get("_deleted_from") == "members"
        print(f"PASS: Member {member_id} soft-deleted and appears in recycle bin")
        
        # Restore
        restore_resp = api_client.post(f"{BASE_URL}/api/admin/deleted-items/{member_id}/restore")
        assert restore_resp.status_code == 200, f"Failed to restore member: {restore_resp.text}"
        
        # Verify member is back
        get_resp2 = api_client.get(f"{BASE_URL}/api/members/{member_id}")
        assert get_resp2.status_code == 200, f"Member should be restored, got {get_resp2.status_code}"
        print(f"PASS: Member {member_id} restored from recycle bin")
        
        # Final cleanup
        api_client.delete(f"{BASE_URL}/api/members/{member_id}")
        # Permanently delete from recycle bin
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{member_id}")
    
    def test_family_soft_delete(self, api_client):
        """DELETE /api/families/{id} soft-deletes"""
        # Create family
        family_name = f"TEST_SoftDelFamily_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": family_name,
            "primary_contact_name": "Test Contact"
        })
        assert create_resp.status_code == 200
        family_id = create_resp.json()["id"]
        
        # Delete
        del_resp = api_client.delete(f"{BASE_URL}/api/families/{family_id}")
        assert del_resp.status_code == 200
        
        # Verify in deleted_items
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items", params={"collection": "families"})
        assert deleted_resp.status_code == 200
        deleted_items = deleted_resp.json()
        deleted_family = next((i for i in deleted_items if i.get("id") == family_id), None)
        assert deleted_family is not None, f"Family {family_id} not found in deleted_items"
        print(f"PASS: Family {family_id} soft-deleted")
        
        # Cleanup - permanent delete
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{family_id}")
    
    def test_child_soft_delete(self, api_client):
        """DELETE /api/children/{id} soft-deletes"""
        # Create family first
        family_name = f"TEST_ChildSoftDelFamily_{uuid.uuid4().hex[:6]}"
        fam_resp = api_client.post(f"{BASE_URL}/api/families", json={
            "family_name": family_name,
            "primary_contact_name": "Parent"
        })
        assert fam_resp.status_code == 200
        family_id = fam_resp.json()["id"]
        
        # Create child
        child_name = f"TEST_SoftDelChild_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/children", json={
            "name": child_name,
            "family_id": family_id,
            "gender": "male"
        })
        assert create_resp.status_code == 200
        child_id = create_resp.json()["id"]
        
        # Delete
        del_resp = api_client.delete(f"{BASE_URL}/api/children/{child_id}")
        assert del_resp.status_code == 200
        
        # Verify in deleted_items
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items", params={"collection": "children"})
        assert deleted_resp.status_code == 200
        deleted_items = deleted_resp.json()
        deleted_child = next((i for i in deleted_items if i.get("id") == child_id), None)
        assert deleted_child is not None, f"Child {child_id} not found in deleted_items"
        print(f"PASS: Child {child_id} soft-deleted")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{child_id}")
        api_client.delete(f"{BASE_URL}/api/families/{family_id}")
    
    def test_guest_soft_delete(self, api_client):
        """DELETE /api/guests/{id} soft-deletes"""
        # Create guest
        guest_name = f"TEST_SoftDelGuest_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/guests", json={
            "name": guest_name,
            "email": f"softdelguest_{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+256700666001"
        })
        assert create_resp.status_code == 200
        guest_id = create_resp.json()["id"]
        
        # Delete
        del_resp = api_client.delete(f"{BASE_URL}/api/guests/{guest_id}")
        assert del_resp.status_code == 200
        
        # Verify in deleted_items
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items", params={"collection": "guests"})
        assert deleted_resp.status_code == 200
        deleted_items = deleted_resp.json()
        deleted_guest = next((i for i in deleted_items if i.get("id") == guest_id), None)
        assert deleted_guest is not None, f"Guest {guest_id} not found in deleted_items"
        print(f"PASS: Guest {guest_id} soft-deleted")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{guest_id}")
    
    def test_permanent_delete(self, api_client):
        """DELETE /api/admin/deleted-items/{id} permanently removes item"""
        # Create and soft-delete a member
        unique_email = f"test_permdel_{uuid.uuid4().hex[:6]}@example.com"
        create_resp = api_client.post(f"{BASE_URL}/api/members", json={
            "name": "TEST_PermDeleteMember",
            "email": unique_email,
            "phone": "+256700555001",
            "gender": "male",
            "role": "Member",
            "group": "Youth"
        })
        assert create_resp.status_code == 200
        member_id = create_resp.json()["id"]
        
        # Soft delete
        api_client.delete(f"{BASE_URL}/api/members/{member_id}")
        
        # Permanent delete
        perm_del_resp = api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{member_id}")
        assert perm_del_resp.status_code == 200, f"Failed to permanently delete: {perm_del_resp.text}"
        
        # Verify not in deleted_items anymore
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items")
        deleted_items = deleted_resp.json()
        deleted_member = next((i for i in deleted_items if i.get("id") == member_id), None)
        assert deleted_member is None, f"Member {member_id} should be permanently deleted"
        print(f"PASS: Member {member_id} permanently deleted")


# ========== RECYCLE BIN ENDPOINTS ==========

class TestRecycleBinEndpoints:
    """Test recycle bin list and filter endpoints"""
    
    def test_list_deleted_items(self, api_client):
        """GET /api/admin/deleted-items lists recently deleted items"""
        response = api_client.get(f"{BASE_URL}/api/admin/deleted-items")
        assert response.status_code == 200, f"Failed to list deleted items: {response.text}"
        items = response.json()
        assert isinstance(items, list), "Expected list of deleted items"
        print(f"PASS: GET /api/admin/deleted-items returns {len(items)} items")
    
    def test_filter_deleted_items_by_collection(self, api_client):
        """GET /api/admin/deleted-items?collection=members filters by collection"""
        response = api_client.get(f"{BASE_URL}/api/admin/deleted-items", params={"collection": "members"})
        assert response.status_code == 200, f"Failed to filter deleted items: {response.text}"
        items = response.json()
        # All items should be from members collection
        for item in items:
            assert item.get("_deleted_from") == "members", f"Expected members, got {item.get('_deleted_from')}"
        print(f"PASS: Filter by collection=members returns {len(items)} items")


# ========== USER SOFT-DELETE ==========

class TestUserSoftDelete:
    """Test admin user soft-delete"""
    
    def test_user_soft_delete(self, api_client):
        """DELETE /api/admin/users/{id} soft-deletes users"""
        # Create a test user
        unique_email = f"test_userdel_{uuid.uuid4().hex[:6]}@example.com"
        create_resp = api_client.post(f"{BASE_URL}/api/admin/users", json={
            "name": "TEST_DeleteUser",
            "email": unique_email,
            "role": "Staff",
            "password": "TestPass123"
        })
        assert create_resp.status_code == 200, f"Failed to create user: {create_resp.text}"
        user_id = create_resp.json()["id"]
        
        # Delete user
        del_resp = api_client.delete(f"{BASE_URL}/api/admin/users/{user_id}")
        assert del_resp.status_code == 200, f"Failed to delete user: {del_resp.text}"
        
        # Verify user is gone
        get_resp = api_client.get(f"{BASE_URL}/api/admin/users/{user_id}")
        assert get_resp.status_code == 404, f"User should be 404 after delete"
        
        # Verify in deleted_items (users collection)
        # Note: users might not have collection filter, check all
        deleted_resp = api_client.get(f"{BASE_URL}/api/admin/deleted-items")
        assert deleted_resp.status_code == 200
        deleted_items = deleted_resp.json()
        deleted_user = next((i for i in deleted_items if i.get("id") == user_id), None)
        assert deleted_user is not None, f"User {user_id} not found in deleted_items"
        assert deleted_user.get("_deleted_from") == "users"
        print(f"PASS: User {user_id} soft-deleted")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{user_id}")


# ========== PARENT IMPORT AS GUESTS ==========

class TestParentImportAsGuests:
    """Test POST /api/import/children-parents creates parents in guests collection"""
    
    def test_import_children_parents_creates_guests(self, api_client):
        """Parents should be imported as guests, not members"""
        unique_suffix = uuid.uuid4().hex[:6]
        
        import_data = {
            "rows": [
                {
                    "first_name": "TestChild",
                    "last_name": f"ImportFamily_{unique_suffix}",
                    "name": f"TestChild ImportFamily_{unique_suffix}",
                    "family_name": f"ImportFamily_{unique_suffix}",
                    "fathers_names": f"TestFather_{unique_suffix}",
                    "fathers_phone": "+256700444001",
                    "mothers_names": f"TestMother_{unique_suffix}",
                    "mothers_phone": "+256700444002",
                    "gender": "male",
                    "date_of_birth": "2015-03-10"
                }
            ]
        }
        
        response = api_client.post(f"{BASE_URL}/api/import/children-parents", json=import_data)
        assert response.status_code == 200, f"Failed to import: {response.text}"
        result = response.json()
        print(f"Import result: {result}")
        
        # Verify parents are in guests collection
        guests_resp = api_client.get(f"{BASE_URL}/api/guests")
        assert guests_resp.status_code == 200
        guests = guests_resp.json()
        
        father_guest = next((g for g in guests if f"TestFather_{unique_suffix}" in g.get("name", "")), None)
        mother_guest = next((g for g in guests if f"TestMother_{unique_suffix}" in g.get("name", "")), None)
        
        assert father_guest is not None, f"Father not found in guests"
        assert mother_guest is not None, f"Mother not found in guests"
        assert father_guest.get("is_parent") == True, "Father should have is_parent=True"
        assert mother_guest.get("is_parent") == True, "Mother should have is_parent=True"
        print(f"PASS: Parents imported as guests with is_parent=True")
        
        # Verify parents are NOT in members collection
        members_resp = api_client.get(f"{BASE_URL}/api/members", params={"search": f"TestFather_{unique_suffix}"})
        assert members_resp.status_code == 200
        members = members_resp.json()
        member_list = members.get("members", members) if isinstance(members, dict) else members
        father_member = next((m for m in member_list if f"TestFather_{unique_suffix}" in m.get("name", "")), None)
        assert father_member is None, "Father should NOT be in members collection"
        print(f"PASS: Parents are NOT in members collection")
        
        # Cleanup
        if father_guest:
            api_client.delete(f"{BASE_URL}/api/guests/{father_guest['id']}")
            api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{father_guest['id']}")
        if mother_guest:
            api_client.delete(f"{BASE_URL}/api/guests/{mother_guest['id']}")
            api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{mother_guest['id']}")
        
        # Cleanup family and child
        families_resp = api_client.get(f"{BASE_URL}/api/families", params={"search": f"ImportFamily_{unique_suffix}"})
        if families_resp.status_code == 200:
            families = families_resp.json()
            for fam in families:
                if f"ImportFamily_{unique_suffix}" in fam.get("family_name", ""):
                    api_client.delete(f"{BASE_URL}/api/families/{fam['id']}")
                    api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{fam['id']}")
        
        children_resp = api_client.get(f"{BASE_URL}/api/children", params={"search": f"TestChild"})
        if children_resp.status_code == 200:
            children = children_resp.json()
            for child in children:
                if f"ImportFamily_{unique_suffix}" in child.get("name", ""):
                    api_client.delete(f"{BASE_URL}/api/children/{child['id']}")
                    api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{child['id']}")


# ========== GUEST UPDATE ENDPOINT ==========

class TestGuestUpdate:
    """Test PUT /api/guests/{id} works"""
    
    def test_update_guest(self, api_client):
        """PUT /api/guests/{id} should update guest"""
        # Create guest
        unique_name = f"TEST_UpdateGuest_{uuid.uuid4().hex[:6]}"
        create_resp = api_client.post(f"{BASE_URL}/api/guests", json={
            "name": unique_name,
            "email": f"updateguest_{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+256700333001"
        })
        assert create_resp.status_code == 200, f"Failed to create guest: {create_resp.text}"
        guest_id = create_resp.json()["id"]
        
        # Update guest
        updated_name = f"TEST_UpdatedGuest_{uuid.uuid4().hex[:6]}"
        update_resp = api_client.put(f"{BASE_URL}/api/guests/{guest_id}", json={
            "name": updated_name,
            "email": f"updatedguest_{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+256700333002",
            "notes": "Updated notes"
        })
        assert update_resp.status_code == 200, f"Failed to update guest: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("name") == updated_name
        assert updated.get("notes") == "Updated notes"
        print(f"PASS: Guest {guest_id} updated successfully")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/guests/{guest_id}")
        api_client.delete(f"{BASE_URL}/api/admin/deleted-items/{guest_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
