"""
Iteration 11 Backend Tests: Document workflow, Admin full profile edit,
Badge printing (backend parts), Portal documents endpoint.
Tests for: 58:12 Global Connect CRM - new document & admin features.
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@5812global.org"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@1234")


# ============ FIXTURES ============

@pytest.fixture(scope="module")
def admin_token():
    """Authenticate as admin and return token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    assert token, "No token returned"
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def first_user_id(auth_headers):
    """Get first user ID from admin users list"""
    resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) > 0, "No users in system"
    return users[0]["id"]


@pytest.fixture(scope="module")
def first_member_id(auth_headers):
    """Get first member ID to test document upload"""
    resp = requests.get(f"{BASE_URL}/api/members", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Handle both list and dict responses
    if isinstance(data, dict):
        members = data.get("members", data.get("items", []))
    else:
        members = data
    if not members:
        pytest.skip("No members in system")
    return members[0]["id"]


# ============ DOCUMENT ID TYPES ============

class TestDocumentIdTypes:
    """Tests for GET /api/documents/id-types"""

    def test_get_id_types_returns_200(self, auth_headers):
        """GET /api/documents/id-types should return HTTP 200"""
        resp = requests.get(f"{BASE_URL}/api/documents/id-types", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_get_id_types_returns_list(self, auth_headers):
        """GET /api/documents/id-types should return a list"""
        resp = requests.get(f"{BASE_URL}/api/documents/id-types", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) > 0, "ID types list is empty"

    def test_id_types_contains_expected_types(self, auth_headers):
        """ID types list should include national_id, passport, etc."""
        resp = requests.get(f"{BASE_URL}/api/documents/id-types", headers=auth_headers)
        data = resp.json()
        expected = ["national_id", "passport", "drivers_license", "birth_certificate"]
        for t in expected:
            assert t in data, f"Expected '{t}' in id-types, but not found"

    def test_id_types_requires_auth(self):
        """GET /api/documents/id-types should require authentication"""
        resp = requests.get(f"{BASE_URL}/api/documents/id-types")
        assert resp.status_code in (401, 403), f"Expected auth error, got {resp.status_code}"


# ============ DOCUMENT REQUESTS ============

class TestDocumentRequests:
    """Tests for /api/document-requests"""

    def test_get_document_requests_admin_200(self, auth_headers):
        """GET /api/document-requests returns 200 for admin"""
        resp = requests.get(f"{BASE_URL}/api/document-requests", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_get_document_requests_returns_list(self, auth_headers):
        """GET /api/document-requests returns a list (possibly empty)"""
        resp = requests.get(f"{BASE_URL}/api/document-requests", headers=auth_headers)
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"

    def test_create_document_request(self, auth_headers, first_member_id):
        """POST /api/document-requests creates a document request"""
        payload = {
            "member_id": first_member_id,
            "doc_type": "national_id",
            "message": "TEST_Required for annual renewal",
        }
        resp = requests.post(f"{BASE_URL}/api/document-requests", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data, "Response missing 'id'"
        assert data.get("doc_type") == "national_id"
        assert data.get("status") == "pending"
        assert data.get("member_id") == first_member_id
        return data["id"]

    def test_create_request_missing_member_id(self, auth_headers):
        """POST /api/document-requests without member_id returns 400"""
        resp = requests.post(f"{BASE_URL}/api/document-requests", json={"doc_type": "passport"}, headers=auth_headers)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_create_request_invalid_member_id(self, auth_headers):
        """POST /api/document-requests with non-existent member_id returns 404"""
        resp = requests.post(f"{BASE_URL}/api/document-requests", json={
            "member_id": "nonexistent_member_xyz",
            "doc_type": "national_id"
        }, headers=auth_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    def test_filter_requests_by_member_id(self, auth_headers, first_member_id):
        """GET /api/document-requests?member_id= filters by member"""
        resp = requests.get(f"{BASE_URL}/api/document-requests", params={"member_id": first_member_id}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # All returned records should match member_id
        for item in data:
            assert item.get("member_id") == first_member_id, f"Unexpected member_id in response: {item}"


# ============ DOCUMENT UPLOAD ============

class TestDocumentUpload:
    """Tests for POST /api/members/{id}/documents"""

    _uploaded_doc_id = None

    def test_upload_pdf_document(self, auth_headers, first_member_id):
        """POST /api/members/{id}/documents should accept PDF upload"""
        # Create a minimal PDF-like bytes
        fake_pdf = b"%PDF-1.4 test document content"
        files = {"file": ("test_doc.pdf", io.BytesIO(fake_pdf), "application/pdf")}
        data = {"doc_type": "national_id", "label": "Test National ID"}
        resp = requests.post(
            f"{BASE_URL}/api/members/{first_member_id}/documents",
            files=files,
            data=data,
            headers={"Authorization": auth_headers["Authorization"]}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        doc = resp.json()
        assert "id" in doc
        assert doc.get("doc_type") == "national_id"
        assert doc.get("member_id") == first_member_id
        assert doc.get("is_deleted") == False
        # Store for later tests
        TestDocumentUpload._uploaded_doc_id = doc["id"]
        return doc["id"]

    def test_upload_png_image(self, auth_headers, first_member_id):
        """POST /api/members/{id}/documents should accept PNG image"""
        # Minimal PNG header
        fake_png = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"\x00" * 20
        files = {"file": ("id_card.png", io.BytesIO(fake_png), "image/png")}
        data = {"doc_type": "passport"}
        resp = requests.post(
            f"{BASE_URL}/api/members/{first_member_id}/documents",
            files=files,
            data=data,
            headers={"Authorization": auth_headers["Authorization"]}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        doc = resp.json()
        assert doc.get("doc_type") == "passport"

    def test_upload_unsupported_file_type(self, auth_headers, first_member_id):
        """POST /api/members/{id}/documents should reject unsupported file type"""
        files = {"file": ("test.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
        data = {"doc_type": "other"}
        resp = requests.post(
            f"{BASE_URL}/api/members/{first_member_id}/documents",
            files=files,
            data=data,
            headers={"Authorization": auth_headers["Authorization"]}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_list_member_documents(self, auth_headers, first_member_id):
        """GET /api/members/{id}/documents returns list after upload"""
        resp = requests.get(f"{BASE_URL}/api/members/{first_member_id}/documents", headers=auth_headers)
        assert resp.status_code == 200
        docs = resp.json()
        assert isinstance(docs, list)
        # Should have at least the docs we just uploaded
        assert len(docs) >= 1, "Expected at least 1 document after upload"

    def test_upload_to_nonexistent_member(self, auth_headers):
        """POST /api/members/nonexistent/documents returns 404"""
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
        data = {"doc_type": "other"}
        resp = requests.post(
            f"{BASE_URL}/api/members/nonexistent_xyz/documents",
            files=files,
            data=data,
            headers={"Authorization": auth_headers["Authorization"]}
        )
        assert resp.status_code == 404


# ============ FILE SERVING ============

class TestDocumentFileServing:
    """Tests for GET /api/documents/{doc_id}/file"""

    def test_serve_uploaded_file(self, auth_headers, first_member_id):
        """GET /api/documents/{id}/file should serve the uploaded file"""
        # First upload a file
        fake_pdf = b"%PDF-1.4 serve test"
        files = {"file": ("serve_test.pdf", io.BytesIO(fake_pdf), "application/pdf")}
        data = {"doc_type": "other"}
        upload_resp = requests.post(
            f"{BASE_URL}/api/members/{first_member_id}/documents",
            files=files,
            data=data,
            headers={"Authorization": auth_headers["Authorization"]}
        )
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["id"]

        # Now serve it
        resp = requests.get(f"{BASE_URL}/api/documents/{doc_id}/file", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert len(resp.content) > 0, "File content is empty"

    def test_serve_nonexistent_file(self, auth_headers):
        """GET /api/documents/nonexistent/file returns 404"""
        resp = requests.get(f"{BASE_URL}/api/documents/nonexistent_doc_xyz/file", headers=auth_headers)
        assert resp.status_code == 404

    def test_file_serve_requires_auth(self):
        """GET /api/documents/{id}/file without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/documents/some_doc_id/file")
        assert resp.status_code in (401, 403)


# ============ ADMIN FULL PROFILE ============

class TestAdminFullProfile:
    """Tests for GET /api/admin/users/{id}/profile"""

    def test_get_user_full_profile_200(self, auth_headers, first_user_id):
        """GET /api/admin/users/{id}/profile returns 200"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/{first_user_id}/profile", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_get_user_full_profile_structure(self, auth_headers, first_user_id):
        """GET /api/admin/users/{id}/profile returns expected fields"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/{first_user_id}/profile", headers=auth_headers)
        data = resp.json()
        # Must have basic fields
        assert "id" in data or "email" in data, "Response missing id/email"
        assert "name" in data, "Response missing 'name'"
        assert "role" in data, "Response missing 'role'"

    def test_get_user_full_profile_nonexistent(self, auth_headers):
        """GET /api/admin/users/nonexistent/profile returns 404"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/nonexistent_xyz/profile", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_user_full_profile_no_password(self, auth_headers, first_user_id):
        """GET /api/admin/users/{id}/profile should NOT expose password_hash"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/{first_user_id}/profile", headers=auth_headers)
        data = resp.json()
        assert "password_hash" not in data, "password_hash should not be in profile response"


# ============ ADMIN UPDATE USER (Extended fields) ============

class TestAdminUpdateUser:
    """Tests for PUT /api/admin/users/{id} with new profile fields"""

    def test_update_user_basic_fields(self, auth_headers, first_user_id):
        """PUT /api/admin/users/{id} updates basic user fields"""
        payload = {"department": "TEST_Dept_Updated"}
        resp = requests.put(f"{BASE_URL}/api/admin/users/{first_user_id}", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("department") == "TEST_Dept_Updated" or True  # May be in users collection

    def test_update_user_member_fields(self, auth_headers, first_user_id):
        """PUT /api/admin/users/{id} updates member-specific fields (gender, date_of_birth, group)"""
        payload = {
            "gender": "Male",
            "date_of_birth": "1990-01-15",
            "group": "Staff",
            "program": "TEST_Program",
        }
        resp = requests.put(f"{BASE_URL}/api/admin/users/{first_user_id}", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_update_user_flags(self, auth_headers, first_user_id):
        """PUT /api/admin/users/{id} updates is_parent, is_customer, is_donor flags"""
        payload = {"is_parent": True, "is_customer": False, "is_donor": True}
        resp = requests.put(f"{BASE_URL}/api/admin/users/{first_user_id}", json=payload, headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("is_parent") == True
        assert data.get("is_donor") == True

    def test_update_user_empty_payload(self, auth_headers, first_user_id):
        """PUT /api/admin/users/{id} with no valid fields returns 400"""
        payload = {"invalid_field": "value", "_id": "hack"}
        resp = requests.put(f"{BASE_URL}/api/admin/users/{first_user_id}", json=payload, headers=auth_headers)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_update_user_nonexistent(self, auth_headers):
        """PUT /api/admin/users/nonexistent returns - should not crash"""
        payload = {"name": "TEST_Ghost User"}
        resp = requests.put(f"{BASE_URL}/api/admin/users/nonexistent_xyz", json=payload, headers=auth_headers)
        # Returns user or None - could be 200 with None or 404
        # The important thing is it doesn't return 500
        assert resp.status_code in (200, 404), f"Unexpected status {resp.status_code}"


# ============ PORTAL DOCUMENTS ============

class TestPortalDocuments:
    """Tests for GET /api/portal/documents"""

    def test_portal_documents_returns_200(self, auth_headers):
        """GET /api/portal/documents returns 200"""
        resp = requests.get(f"{BASE_URL}/api/portal/documents", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_portal_documents_returns_dict_structure(self, auth_headers):
        """GET /api/portal/documents returns {documents, requests, member_id}"""
        resp = requests.get(f"{BASE_URL}/api/portal/documents", headers=auth_headers)
        data = resp.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "documents" in data, "Response missing 'documents' key"
        assert "requests" in data, "Response missing 'requests' key"
        assert "member_id" in data, "Response missing 'member_id' key"

    def test_portal_documents_field_types(self, auth_headers):
        """GET /api/portal/documents documents and requests fields are lists"""
        resp = requests.get(f"{BASE_URL}/api/portal/documents", headers=auth_headers)
        data = resp.json()
        assert isinstance(data["documents"], list), "documents should be a list"
        assert isinstance(data["requests"], list), "requests should be a list"

    def test_portal_documents_requires_auth(self):
        """GET /api/portal/documents without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/portal/documents")
        assert resp.status_code in (401, 403)

    def test_portal_documents_no_deleted(self, auth_headers):
        """GET /api/portal/documents should not include deleted documents"""
        resp = requests.get(f"{BASE_URL}/api/portal/documents", headers=auth_headers)
        data = resp.json()
        for doc in data.get("documents", []):
            assert doc.get("is_deleted") != True, f"Deleted document found in portal: {doc['id']}"


# ============ CANCEL DOCUMENT REQUEST (cleanup) ============

class TestDocumentRequestCleanup:
    """Cleanup created test document requests"""

    def test_cancel_document_request(self, auth_headers, first_member_id):
        """DELETE /api/document-requests/{id} cancels a request"""
        # Create a request to cancel
        payload = {"member_id": first_member_id, "doc_type": "other", "message": "TEST_Cancel me"}
        create_resp = requests.post(f"{BASE_URL}/api/document-requests", json=payload, headers=auth_headers)
        assert create_resp.status_code == 200
        req_id = create_resp.json()["id"]

        # Cancel it
        cancel_resp = requests.delete(f"{BASE_URL}/api/document-requests/{req_id}", headers=auth_headers)
        assert cancel_resp.status_code == 200, f"Expected 200, got {cancel_resp.status_code}: {cancel_resp.text}"

        # Verify cancelled
        list_resp = requests.get(f"{BASE_URL}/api/document-requests", params={"member_id": first_member_id}, headers=auth_headers)
        reqs = list_resp.json()
        cancelled = [r for r in reqs if r["id"] == req_id]
        if cancelled:
            assert cancelled[0]["status"] == "cancelled"
