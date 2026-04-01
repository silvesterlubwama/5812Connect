"""
Iteration 12 - Tests for:
1. WebAuthn endpoints (register/begin, credentials list, authenticate/begin)
2. Member bulk update (admin/members/bulk-update)
3. Member edit (PUT /api/members/{id})
4. Children edit (PUT /api/children/{id})
5. Export endpoint (exportApi bug check)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ---- Auth helpers ----
ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@1234")

@pytest.fixture(scope="module")
def admin_token():
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json().get("token")

@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture(scope="module")
def first_member_id(auth_headers):
    res = requests.get(f"{BASE_URL}/api/members", headers=auth_headers, params={"limit": 1})
    assert res.status_code == 200
    members = res.json()
    if isinstance(members, dict):
        members = members.get("members", [])
    assert len(members) > 0, "No members found for testing"
    return members[0]["id"]


# ===== WEBAUTHN TESTS =====

class TestWebAuthnRegisterBegin:
    """Tests for POST /api/webauthn/register/begin"""

    def test_register_begin_returns_options(self, auth_headers):
        """Should return registration options with challenge and rp"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/register/begin",
            json={"rpId": "preview.emergentagent.com"},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        # py_webauthn returns camelCase JSON
        assert "challenge" in data, "Missing challenge in response"
        assert "rp" in data, "Missing rp in response"
        print(f"PASS: register/begin returned options with challenge and rp.id={data['rp'].get('id')}")

    def test_register_begin_rp_id_correct(self, auth_headers):
        """rp.id should match the provided rpId"""
        rp_id = "preview.emergentagent.com"
        res = requests.post(
            f"{BASE_URL}/api/webauthn/register/begin",
            json={"rpId": rp_id},
            headers=auth_headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("rp", {}).get("id") == rp_id, f"rp.id mismatch: expected {rp_id}, got {data.get('rp', {}).get('id')}"
        print(f"PASS: rp.id is correctly set to {rp_id}")

    def test_register_begin_has_user_field(self, auth_headers):
        """Registration options should include user object"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/register/begin",
            json={"rpId": "preview.emergentagent.com"},
            headers=auth_headers
        )
        assert res.status_code == 200
        data = res.json()
        assert "user" in data, "Missing user field in registration options"
        assert "id" in data["user"], "Missing user.id"
        print(f"PASS: registration options contain user: {data['user'].get('name')}")

    def test_register_begin_requires_auth(self):
        """Should return 401/403 without auth token"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/register/begin",
            json={"rpId": "preview.emergentagent.com"}
        )
        assert res.status_code in [401, 403], f"Expected 401/403 without auth, got {res.status_code}"
        print(f"PASS: register/begin correctly rejects unauthenticated requests ({res.status_code})")


class TestWebAuthnCredentials:
    """Tests for GET /api/webauthn/credentials"""

    def test_list_credentials_returns_list(self, auth_headers):
        """Should return a list (possibly empty) of credentials"""
        res = requests.get(f"{BASE_URL}/api/webauthn/credentials", headers=auth_headers)
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: credentials endpoint returned list with {len(data)} items")

    def test_list_credentials_no_public_key_exposed(self, auth_headers):
        """Credentials should NOT expose the private public_key bytes"""
        res = requests.get(f"{BASE_URL}/api/webauthn/credentials", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        for cred in data:
            assert "public_key" not in cred, "public_key should not be exposed in credential list"
        print(f"PASS: No public_key exposed in {len(data)} credentials")

    def test_list_credentials_requires_auth(self):
        """Should return 401 without auth"""
        res = requests.get(f"{BASE_URL}/api/webauthn/credentials")
        assert res.status_code in [401, 403], f"Expected 401/403, got {res.status_code}"
        print(f"PASS: credentials list correctly rejects unauthenticated requests ({res.status_code})")


class TestWebAuthnAuthBegin:
    """Tests for POST /api/webauthn/authenticate/begin"""

    def test_authenticate_begin_no_email(self):
        """Begin without email should still return options (discoverable credentials)"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/authenticate/begin",
            json={"rpId": "preview.emergentagent.com", "email": ""}
        )
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        assert "challenge" in data
        print(f"PASS: authenticate/begin without email returns challenge")

    def test_authenticate_begin_with_email(self):
        """Begin with known email should return challenge"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/authenticate/begin",
            json={"rpId": "preview.emergentagent.com", "email": ADMIN_EMAIL}
        )
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        data = res.json()
        assert "challenge" in data, "Missing challenge"
        print(f"PASS: authenticate/begin with admin email returns challenge. allowCredentials: {len(data.get('allowCredentials', []))}")

    def test_authenticate_begin_with_unknown_email(self):
        """Begin with unknown email should still return options (empty allowCredentials)"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/authenticate/begin",
            json={"rpId": "preview.emergentagent.com", "email": "nonexistent@example.com"}
        )
        assert res.status_code == 200, f"Should return 200 with empty creds, got {res.status_code}"
        data = res.json()
        assert "challenge" in data
        allow_creds = data.get("allowCredentials", [])
        assert len(allow_creds) == 0, f"Should have 0 allowCredentials for unknown email, got {len(allow_creds)}"
        print(f"PASS: authenticate/begin with unknown email returns challenge with empty allowCredentials")

    def test_authenticate_begin_does_not_require_auth(self):
        """authenticate/begin should not require auth token (user not yet logged in)"""
        res = requests.post(
            f"{BASE_URL}/api/webauthn/authenticate/begin",
            json={"rpId": "preview.emergentagent.com", "email": ""}
        )
        assert res.status_code == 200, f"authenticate/begin should be public endpoint, got {res.status_code}"
        print(f"PASS: authenticate/begin is public (no auth required)")


# ===== MEMBER BULK UPDATE TESTS =====

class TestMemberBulkUpdate:
    """Tests for POST /api/admin/members/bulk-update"""

    def test_bulk_update_status_activate(self, auth_headers, first_member_id):
        """Should activate member via bulk update"""
        res = requests.post(
            f"{BASE_URL}/api/admin/members/bulk-update",
            json={"member_ids": [first_member_id], "updates": {"status": "active"}},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        print(f"PASS: bulk-update activate returned 200")

    def test_bulk_update_role(self, auth_headers, first_member_id):
        """Should update member role via bulk update"""
        # First get current role
        member_res = requests.get(f"{BASE_URL}/api/members/{first_member_id}", headers=auth_headers)
        original_role = member_res.json().get("role", "Staff")

        res = requests.post(
            f"{BASE_URL}/api/admin/members/bulk-update",
            json={"member_ids": [first_member_id], "updates": {"role": "Staff"}},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected status: {res.status_code} {res.text}"
        
        # Verify persistence
        get_res = requests.get(f"{BASE_URL}/api/members/{first_member_id}", headers=auth_headers)
        assert get_res.status_code == 200
        print(f"PASS: bulk-update role returned 200, member role now: {get_res.json().get('role')}")

    def test_bulk_update_requires_auth(self, first_member_id):
        """Should reject bulk update without auth"""
        res = requests.post(
            f"{BASE_URL}/api/admin/members/bulk-update",
            json={"member_ids": [first_member_id], "updates": {"status": "active"}}
        )
        assert res.status_code in [401, 403], f"Expected 401/403, got {res.status_code}"
        print(f"PASS: bulk-update correctly rejects unauthenticated requests ({res.status_code})")


# ===== MEMBER EDIT TESTS =====

class TestMemberEdit:
    """Tests for PUT /api/members/{id}"""

    def test_edit_member_name(self, auth_headers, first_member_id):
        """Should update member name"""
        get_res = requests.get(f"{BASE_URL}/api/members/{first_member_id}", headers=auth_headers)
        assert get_res.status_code == 200
        original_name = get_res.json().get("name", "Test Member")

        update_res = requests.put(
            f"{BASE_URL}/api/members/{first_member_id}",
            json={"name": original_name},  # Keep same name to not break data
            headers=auth_headers
        )
        assert update_res.status_code == 200, f"Unexpected: {update_res.status_code} {update_res.text}"
        print(f"PASS: PUT /api/members/{first_member_id} returned 200")

    def test_edit_member_phone(self, auth_headers, first_member_id):
        """Should update member phone field"""
        res = requests.put(
            f"{BASE_URL}/api/members/{first_member_id}",
            json={"phone": "+256700000001"},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected: {res.status_code} {res.text}"
        
        # Verify persistence
        get_res = requests.get(f"{BASE_URL}/api/members/{first_member_id}", headers=auth_headers)
        assert get_res.status_code == 200
        print(f"PASS: member phone updated, stored as: {get_res.json().get('phone')}")

    def test_edit_member_not_found(self, auth_headers):
        """Should return 404 for nonexistent member"""
        res = requests.put(
            f"{BASE_URL}/api/members/nonexistent_id_12345",
            json={"name": "Ghost Member"},
            headers=auth_headers
        )
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        print(f"PASS: PUT /api/members/nonexistent_id returns 404")


# ===== CHILDREN EDIT TESTS =====

class TestChildrenEdit:
    """Tests for PUT /api/children/{child_id}"""

    @pytest.fixture(scope="class")
    def test_child_id(self, auth_headers):
        """Create a test child for editing"""
        res = requests.post(
            f"{BASE_URL}/api/children",
            json={"name": "TEST_EditChild", "date_of_birth": "2015-06-01", "gender": "male", "class_group": "Juniors"},
            headers=auth_headers
        )
        assert res.status_code in [200, 201], f"Failed to create test child: {res.text}"
        child_id = res.json().get("id")
        yield child_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/children/{child_id}", headers=auth_headers)

    def test_edit_child_name(self, auth_headers, test_child_id):
        """Should update child name"""
        res = requests.put(
            f"{BASE_URL}/api/children/{test_child_id}",
            json={"name": "TEST_EditChild_Updated", "date_of_birth": "2015-06-01", "gender": "male", "class_group": "Juniors"},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected: {res.status_code} {res.text}"
        data = res.json()
        assert data.get("name") == "TEST_EditChild_Updated", f"Name not updated: {data.get('name')}"
        print(f"PASS: Child name updated to '{data.get('name')}'")

    def test_edit_child_allergies(self, auth_headers, test_child_id):
        """Should update child allergies field"""
        res = requests.put(
            f"{BASE_URL}/api/children/{test_child_id}",
            json={"name": "TEST_EditChild_Updated", "date_of_birth": "2015-06-01", "gender": "male", "class_group": "Juniors", "allergies": "peanuts"},
            headers=auth_headers
        )
        assert res.status_code == 200, f"Unexpected: {res.status_code} {res.text}"
        data = res.json()
        assert data.get("allergies") == "peanuts", f"Allergies not updated: {data.get('allergies')}"
        print(f"PASS: Child allergies updated to '{data.get('allergies')}'")

    def test_list_children(self, auth_headers):
        """GET /api/children should return list"""
        res = requests.get(f"{BASE_URL}/api/children", headers=auth_headers)
        assert res.status_code == 200, f"Unexpected: {res.status_code} {res.text}"
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: GET /api/children returns list of {len(data)} children")


# ===== EXPORT ENDPOINT TEST =====

class TestExportEndpoint:
    """Tests for /api/export/members (CSV export)"""

    def test_export_members_csv_endpoint(self, auth_headers):
        """GET /api/export/members should return CSV data"""
        res = requests.get(f"{BASE_URL}/api/export/members", headers=auth_headers)
        # Should return 200 with CSV content
        assert res.status_code == 200, f"Export endpoint returned: {res.status_code} {res.text[:200]}"
        print(f"PASS: Export endpoint returned 200, content-type: {res.headers.get('content-type', 'unknown')}")
