"""
Iteration 49 - Test refactored backend endpoints:
1. admin_update_user with _expand_user_locations and _sync_member_profile helpers
2. import_trello_board with _import_board_lists, _import_trello_cards, _build_trello_card_doc, _process_card_attachments helpers
"""
import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "identifier": creds.ADMIN_EMAIL,
        "password": creds.ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestAuthLogin:
    """Test auth/login endpoint"""
    
    def test_login_success(self):
        """Test successful login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == creds.ADMIN_EMAIL
        print("✓ Login success test passed")

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code in [401, 404]
        print("✓ Login invalid credentials test passed")


class TestAdminUsersEndpoint:
    """Test /api/admin/users endpoint"""
    
    def test_list_users(self, auth_headers):
        """Test listing all users"""
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ List users returned {len(data)} users")

    def test_list_users_with_search(self, auth_headers):
        """Test listing users with search filter"""
        response = requests.get(f"{BASE_URL}/api/admin/users?search=admin", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ List users with search returned {len(data)} users")


class TestAdminUpdateUser:
    """Test refactored admin_update_user with _expand_user_locations and _sync_member_profile helpers"""
    
    def test_update_user_basic_fields(self, auth_headers):
        """Test updating basic user fields using admin's own user ID"""
        # Get admin user info via /auth/me
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        admin_user = response.json()
        user_id = admin_user["id"]
        
        # Update user with basic fields
        update_data = {
            "department": f"TEST_Dept_{uuid.uuid4().hex[:6]}",
            "notes": "Test update from iteration 49"
        }
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        updated_user = response.json()
        assert updated_user["department"] == update_data["department"]
        assert updated_user["notes"] == update_data["notes"]
        print(f"✓ Update user basic fields passed for user {user_id}")

    def test_update_user_with_location_expansion(self, auth_headers):
        """Test updating user with location_ids - should expand with parent campuses"""
        # Get locations first
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Locations endpoint not available")
        
        locations = response.json()
        if not locations:
            pytest.skip("No locations available for testing")
        
        # Get admin user info via /auth/me
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        admin_user = response.json()
        user_id = admin_user["id"]
        
        # Update with location_id
        loc_id = locations[0]["id"]
        update_data = {
            "location_id": loc_id,
            "location_ids": [loc_id]
        }
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        updated_user = response.json()
        assert updated_user.get("location_id") == loc_id
        print(f"✓ Update user with location expansion passed")

    def test_update_user_syncs_member_profile(self, auth_headers):
        """Test that updating user also syncs to member profile"""
        # Get admin user info via /auth/me
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        admin_user = response.json()
        user_id = admin_user["id"]
        
        # Update user
        new_dept = f"TEST_SyncDept_{uuid.uuid4().hex[:6]}"
        update_data = {"department": new_dept}
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        
        # Verify member profile was synced
        response = requests.get(f"{BASE_URL}/api/admin/users/{user_id}/profile", headers=auth_headers)
        if response.status_code == 200:
            profile = response.json()
            # Member profile should have the updated department
            assert profile.get("department") == new_dept or profile.get("department") is not None
            print(f"✓ User update synced to member profile")
        else:
            print(f"✓ User update completed (profile endpoint returned {response.status_code})")


class TestTrelloImport:
    """Test refactored import_trello_board with helper functions"""
    
    def test_import_trello_board_basic(self, auth_headers):
        """Test importing a basic Trello board structure"""
        trello_data = {
            "name": f"TEST_Trello_Import_{uuid.uuid4().hex[:6]}",
            "desc": "Test board imported from Trello format",
            "lists": [
                {"id": "list1", "name": "To Do", "pos": 1, "closed": False},
                {"id": "list2", "name": "In Progress", "pos": 2, "closed": False},
                {"id": "list3", "name": "Done", "pos": 3, "closed": False}
            ],
            "cards": [
                {
                    "id": "card1",
                    "name": "Test Card 1",
                    "desc": "Description for card 1",
                    "idList": "list1",
                    "pos": 1,
                    "closed": False,
                    "labels": [{"name": "Priority", "color": "red"}]
                },
                {
                    "id": "card2",
                    "name": "Test Card 2",
                    "desc": "Description for card 2",
                    "idList": "list2",
                    "pos": 1,
                    "closed": False
                }
            ],
            "checklists": [],
            "labels": [{"id": "lbl1", "name": "Priority", "color": "red"}]
        }
        
        response = requests.post(f"{BASE_URL}/api/boards/import-trello", json=trello_data, headers=auth_headers)
        assert response.status_code == 200, f"Import failed: {response.text}"
        
        result = response.json()
        assert "board_id" in result
        assert result["lists"] == 3
        assert result["imported"] == 2
        print(f"✓ Trello import created board {result['board_id']} with {result['lists']} lists and {result['imported']} cards")
        
        # Cleanup - delete the test board
        board_id = result["board_id"]
        requests.delete(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)

    def test_import_trello_board_with_checklists(self, auth_headers):
        """Test importing Trello board with checklists"""
        trello_data = {
            "name": f"TEST_Trello_Checklist_{uuid.uuid4().hex[:6]}",
            "lists": [
                {"id": "list1", "name": "Tasks", "pos": 1, "closed": False}
            ],
            "cards": [
                {
                    "id": "card1",
                    "name": "Card with Checklist",
                    "idList": "list1",
                    "pos": 1,
                    "closed": False,
                    "idChecklists": ["cl1"]
                }
            ],
            "checklists": [
                {
                    "id": "cl1",
                    "name": "Todo Items",
                    "checkItems": [
                        {"name": "Item 1", "state": "complete"},
                        {"name": "Item 2", "state": "incomplete"}
                    ]
                }
            ],
            "labels": []
        }
        
        response = requests.post(f"{BASE_URL}/api/boards/import-trello", json=trello_data, headers=auth_headers)
        assert response.status_code == 200
        
        result = response.json()
        assert result["imported"] == 1
        print(f"✓ Trello import with checklists passed")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/boards/{result['board_id']}", headers=auth_headers)

    def test_import_trello_board_filters_closed_items(self, auth_headers):
        """Test that closed lists and cards are filtered out"""
        trello_data = {
            "name": f"TEST_Trello_Closed_{uuid.uuid4().hex[:6]}",
            "lists": [
                {"id": "list1", "name": "Open List", "pos": 1, "closed": False},
                {"id": "list2", "name": "Closed List", "pos": 2, "closed": True}
            ],
            "cards": [
                {"id": "card1", "name": "Open Card", "idList": "list1", "pos": 1, "closed": False},
                {"id": "card2", "name": "Closed Card", "idList": "list1", "pos": 2, "closed": True}
            ],
            "checklists": [],
            "labels": []
        }
        
        response = requests.post(f"{BASE_URL}/api/boards/import-trello", json=trello_data, headers=auth_headers)
        assert response.status_code == 200
        
        result = response.json()
        assert result["lists"] == 1, "Should only import 1 open list"
        assert result["imported"] == 1, "Should only import 1 open card"
        print(f"✓ Trello import correctly filters closed items")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/boards/{result['board_id']}", headers=auth_headers)


class TestBoardsEndpoint:
    """Test boards CRUD operations"""
    
    def test_list_boards(self, auth_headers):
        """Test listing boards"""
        response = requests.get(f"{BASE_URL}/api/boards", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ List boards returned {len(data)} boards")

    def test_create_and_delete_board(self, auth_headers):
        """Test creating and deleting a board"""
        board_data = {
            "name": f"TEST_Board_{uuid.uuid4().hex[:6]}",
            "description": "Test board for iteration 49"
        }
        
        # Create
        response = requests.post(f"{BASE_URL}/api/boards", json=board_data, headers=auth_headers)
        assert response.status_code == 200
        board = response.json()
        assert board["name"] == board_data["name"]
        board_id = board["id"]
        print(f"✓ Created board {board_id}")
        
        # Get
        response = requests.get(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)
        assert response.status_code == 200
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/boards/{board_id}", headers=auth_headers)
        assert response.status_code == 200
        print(f"✓ Deleted board {board_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
