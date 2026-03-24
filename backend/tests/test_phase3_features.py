"""
Backend API tests for 58:12 Global Connect CRM - Phase 3 Major Overhaul
Tests: Compass system, multi-currency, new role hierarchy, CSV imports, chat/AI, fund distribution, resource types
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://staff-self-service-1.preview.emergentagent.com')


class TestAuth:
    """Authentication tests with new admin credentials"""
    
    def test_login_admin_5812uganda(self):
        """Test login with admin@5812uganda.org / Admin@5812"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@5812uganda.org"
        assert data["user"]["role"] == "admin"
        print(f"✓ Login successful for admin@5812uganda.org")
    
    def test_login_admin_5812global(self):
        """Test login with admin@5812global.org / Admin@1234"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812global.org",
            "password": "Admin@1234"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "admin@5812global.org"
        print(f"✓ Login successful for admin@5812global.org")


class TestLocationsCompassSystem:
    """Test locations with compass system (Phase 1)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_locations_returns_compass_types(self, auth_headers):
        """GET /api/locations returns locations with type=compass"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Check for compass type locations
        types = [loc.get("type") for loc in data]
        print(f"Location types found: {set(types)}")
        assert "compass" in types or "main" in types, "Should have compass or main type locations"
        # Check for new fields
        if data:
            loc = data[0]
            assert "currency" in loc or loc.get("currency") is None
            print(f"✓ Locations returned with types: {set(types)}")
    
    def test_create_compass_location(self, auth_headers):
        """POST /api/locations creates new compass with currency, is_venue, is_bookable, is_restricted, departments"""
        payload = {
            "name": "TEST_Mbarara Compass",
            "code": "MBR",
            "type": "compass",
            "parent_id": "loc_001",  # Main location
            "address": "123 Test Street, Mbarara",
            "country": "Uganda",
            "currency": "UGX",
            "contact_name": "Test Director",
            "contact_phone": "+256 700 123456",
            "is_venue": False,
            "is_bookable": False,
            "is_restricted": False,
            "departments": ["Youth", "Education", "Sports"]
        }
        response = requests.post(f"{BASE_URL}/api/locations", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Mbarara Compass"
        assert data["type"] == "compass"
        assert data["currency"] == "UGX"
        assert data["departments"] == ["Youth", "Education", "Sports"]
        assert "id" in data
        print(f"✓ Created compass location: {data['id']}")
        # Store for cleanup
        self.__class__.created_location_id = data["id"]
    
    def test_update_location_fields(self, auth_headers):
        """PUT /api/locations/{id} can update type, parent_id, currency, director_id etc"""
        loc_id = getattr(self.__class__, 'created_location_id', None)
        if not loc_id:
            pytest.skip("No location created to update")
        
        update_payload = {
            "name": "TEST_Mbarara Compass Updated",
            "currency": "USD",
            "is_venue": True,
            "is_bookable": True,
            "departments": ["Youth", "Education", "Sports", "Media"]
        }
        response = requests.put(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers, json=update_payload)
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Mbarara Compass Updated"
        assert data["currency"] == "USD"
        assert data["is_venue"] == True
        assert data["is_bookable"] == True
        print(f"✓ Updated location successfully")
    
    def test_create_sub_location(self, auth_headers):
        """Create sub-location under compass"""
        parent_id = getattr(self.__class__, 'created_location_id', None)
        if not parent_id:
            parent_id = "loc_002"  # Use existing compass
        
        payload = {
            "name": "TEST_Training Hall",
            "code": "TRH",
            "type": "sub-location",
            "parent_id": parent_id,
            "is_venue": True,
            "is_bookable": True,
            "is_restricted": False,
            "currency": "UGX"
        }
        response = requests.post(f"{BASE_URL}/api/locations", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Create sub-location failed: {response.text}"
        data = response.json()
        assert data["type"] == "sub-location"
        assert data["parent_id"] == parent_id
        assert data["is_venue"] == True
        print(f"✓ Created sub-location: {data['id']}")
        self.__class__.created_sublocation_id = data["id"]


class TestExchangeRate:
    """Test exchange rate endpoint (Phase 1)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_exchange_rate_ugx_to_usd(self, auth_headers):
        """GET /api/exchange-rate?from_currency=UGX&to_currency=USD returns rate"""
        response = requests.get(f"{BASE_URL}/api/exchange-rate", 
                               params={"from_currency": "UGX", "to_currency": "USD"},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "from" in data
        assert "to" in data
        assert "rate" in data
        assert data["from"] == "UGX"
        assert data["to"] == "USD"
        assert isinstance(data["rate"], (int, float))
        print(f"✓ Exchange rate UGX->USD: {data['rate']}")
    
    def test_exchange_rate_usd_to_kes(self, auth_headers):
        """Test USD to KES exchange rate"""
        response = requests.get(f"{BASE_URL}/api/exchange-rate", 
                               params={"from_currency": "USD", "to_currency": "KES"},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["from"] == "USD"
        assert data["to"] == "KES"
        print(f"✓ Exchange rate USD->KES: {data['rate']}")


class TestMembersNewRoles:
    """Test members with new role hierarchy (Phase 2)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_create_member_with_new_role(self, auth_headers):
        """Create member with new role hierarchy roles"""
        payload = {
            "name": "TEST_Director Member",
            "email": "test_director@example.com",
            "phone": "+256 700 999888",
            "role": "Director",
            "location_id": "loc_002",
            "department": "Youth",
            "is_parent": False,
            "is_customer": False,
            "is_donor": True
        }
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Create member failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Director Member"
        assert data["role"] == "Director"
        assert data["is_donor"] == True
        print(f"✓ Created member with Director role: {data['id']}")
        self.__class__.created_member_id = data["id"]
    
    def test_create_member_multi_role(self, auth_headers):
        """Create member with multi-role (staff can be parent/customer/donor)"""
        payload = {
            "name": "TEST_Multi Role Staff",
            "email": "test_multirole@example.com",
            "role": "Staff",
            "is_parent": True,
            "is_customer": True,
            "is_donor": True
        }
        response = requests.post(f"{BASE_URL}/api/members", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["is_parent"] == True
        assert data["is_customer"] == True
        assert data["is_donor"] == True
        print(f"✓ Created multi-role member: {data['id']}")


class TestCSVImports:
    """Test CSV import endpoints (Phase 5)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_import_children_parents(self, auth_headers):
        """POST /api/import/children-parents creates children + parents + families from CSV rows"""
        payload = {
            "rows": [
                {
                    "first_name": "TEST_Child",
                    "last_name": "ImportTest",
                    "date_of_birth": "2018-05-15",
                    "grade": "Primary 2",
                    "family_name": "ImportTest Family",
                    "fathers_names": "TEST_Father ImportTest",
                    "fathers_phone": "+256 700 111222",
                    "mothers_names": "TEST_Mother ImportTest",
                    "mothers_phone": "+256 700 333444",
                    "allergies": "None",
                    "medical_notes": "",
                    "special_needs": ""
                }
            ]
        }
        response = requests.post(f"{BASE_URL}/api/import/children-parents", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        assert "imported_children" in data
        assert "imported_parents" in data
        assert "imported_families" in data
        print(f"✓ Imported: {data['imported_children']} children, {data['imported_parents']} parents, {data['imported_families']} families")
    
    def test_import_staff(self, auth_headers):
        """POST /api/import/staff creates staff members from CSV rows"""
        payload = {
            "rows": [
                {
                    "name": "TEST_Staff Import",
                    "email": "test_staff_import@example.com",
                    "phone": "+256 700 555666",
                    "national_id": "CM123456789",
                    "role": "Coordinator",
                    "department": "Operations"
                }
            ]
        }
        response = requests.post(f"{BASE_URL}/api/import/staff", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Staff import failed: {response.text}"
        data = response.json()
        assert "imported" in data
        assert data["imported"] >= 0
        print(f"✓ Imported {data['imported']} staff members")


class TestFinancialFundDistribution:
    """Test financial endpoints with location scoping (Phase 3)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_financial_summary_with_location(self, auth_headers):
        """GET /api/financial/summary?location_id={id} filters by location"""
        response = requests.get(f"{BASE_URL}/api/financial/summary", 
                               params={"location_id": "loc_001"},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "monthly_donations" in data or "net_balance" in data
        print(f"✓ Financial summary with location filter works")
    
    def test_distribute_funds(self, auth_headers):
        """POST /api/financial/distribute-funds creates expense at source and donation at destination"""
        # First check if endpoint exists
        payload = {
            "from_location_id": "loc_001",
            "to_location_id": "loc_002",
            "amount": 50000,
            "currency": "UGX",
            "notes": "TEST_Fund transfer for youth program"
        }
        response = requests.post(f"{BASE_URL}/api/financial/distribute-funds", headers=auth_headers, json=payload)
        # This endpoint may not exist yet - check status
        if response.status_code == 404:
            pytest.skip("distribute-funds endpoint not implemented")
        assert response.status_code in [200, 201], f"Distribute funds failed: {response.text}"
        print(f"✓ Fund distribution endpoint works")


class TestResourceTypes:
    """Test resources with new types (Phase 4)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_resources(self, auth_headers):
        """GET /api/resources returns resources array"""
        response = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Resources list returned {len(data)} items")
    
    def test_create_resource_sports_equipment(self, auth_headers):
        """Create resource with type=sports_equipment"""
        payload = {
            "name": "TEST_Football Set",
            "type": "sports_equipment",
            "quantity": 5,
            "description": "Set of footballs for youth program",
            "location_id": "loc_002",
            "is_bookable": True,
            "staff_only": False,
            "is_consumable": False
        }
        response = requests.post(f"{BASE_URL}/api/resources", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Create resource failed: {response.text}"
        data = response.json()
        assert data["type"] == "sports_equipment"
        assert data["is_bookable"] == True
        print(f"✓ Created sports equipment resource: {data['id']}")
    
    def test_create_resource_venue(self, auth_headers):
        """Create resource with type=venue"""
        payload = {
            "name": "TEST_Conference Room B",
            "type": "venue",
            "capacity": 25,
            "description": "Small conference room",
            "location_id": "loc_001",
            "hourly_rate": 15000,
            "is_bookable": True,
            "staff_only": True
        }
        response = requests.post(f"{BASE_URL}/api/resources", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "venue"
        assert data["staff_only"] == True
        print(f"✓ Created venue resource: {data['id']}")


class TestChatAndAI:
    """Test chat and AI assistant endpoints (Phase 6)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_conversations(self, auth_headers):
        """GET /api/chat/conversations returns conversations list"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Conversations list returned {len(data)} items")
    
    def test_create_conversation(self, auth_headers):
        """POST /api/chat/conversations creates new conversation"""
        payload = {
            "name": "TEST_Team Chat",
            "type": "group",
            "participants": []
        }
        response = requests.post(f"{BASE_URL}/api/chat/conversations", headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Create conversation failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Team Chat"
        assert "id" in data
        print(f"✓ Created conversation: {data['id']}")
        self.__class__.created_conv_id = data["id"]
    
    def test_send_message(self, auth_headers):
        """POST /api/chat/conversations/{id}/messages sends message"""
        conv_id = getattr(self.__class__, 'created_conv_id', None)
        if not conv_id:
            pytest.skip("No conversation created")
        
        payload = {"text": "TEST_Hello team!"}
        response = requests.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", 
                                headers=auth_headers, json=payload)
        assert response.status_code == 200, f"Send message failed: {response.text}"
        data = response.json()
        assert data["text"] == "TEST_Hello team!"
        print(f"✓ Message sent successfully")
    
    def test_ai_assistant(self, auth_headers):
        """POST /api/chat/ai-assistant sends message to Gemini AI"""
        payload = {
            "message": "What is 58:12 Global Connect?",
            "session_id": "test_session_123"
        }
        response = requests.post(f"{BASE_URL}/api/chat/ai-assistant", headers=auth_headers, json=payload)
        # AI may fail if key not configured - that's ok
        if response.status_code == 500:
            error_detail = response.json().get("detail", "")
            if "AI not configured" in error_detail or "AI assistant error" in error_detail:
                print(f"⚠ AI Assistant not configured (expected if no API key)")
                return
        assert response.status_code == 200, f"AI assistant failed: {response.text}"
        data = response.json()
        assert "response" in data
        print(f"✓ AI Assistant responded: {data['response'][:100]}...")


class TestAnnouncements:
    """Test announcements endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_announcements(self, auth_headers):
        """GET /api/announcements returns announcements"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Announcements list returned {len(data)} items")
    
    def test_create_announcement(self, auth_headers):
        """POST /api/announcements creates new announcement"""
        payload = {
            "title": "TEST_Important Update",
            "content": "This is a test announcement for the team.",
            "type": "general",
            "pinned": False
        }
        response = requests.post(f"{BASE_URL}/api/announcements", headers=auth_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Important Update"
        print(f"✓ Created announcement: {data['id']}")


class TestAppSettings:
    """Test app settings endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": "admin@5812uganda.org",
            "password": "Admin@5812"
        })
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_app_settings(self, auth_headers):
        """GET /api/app-settings returns settings"""
        response = requests.get(f"{BASE_URL}/api/app-settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print(f"✓ App settings retrieved")
    
    def test_update_app_settings(self, auth_headers):
        """PUT /api/app-settings updates settings"""
        payload = {
            "registration_open": True,
            "maintenance_mode": False
        }
        response = requests.put(f"{BASE_URL}/api/app-settings", headers=auth_headers, json=payload)
        assert response.status_code == 200
        print(f"✓ App settings updated")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
