"""Iter-173 backend regression tests
Tests:
- POST /api/products/{id}/generate-barcodes (no force) → only fills missing
- POST /api/products/{id}/generate-barcodes?force=true → regenerates ALL
- Response shape includes {message, format, force}
- 403 when called without admin/director/manager role
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_location_id(admin_headers):
    """Get a location to use for the product."""
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Could not list locations: {r.status_code}")
    locs = r.json()
    if not locs:
        pytest.skip("No locations available")
    return locs[0]["id"]


@pytest.fixture(scope="module")
def seed_product(admin_headers, admin_location_id):
    """Create a TEST_ product with 2 variants."""
    payload = {
        "name": f"TEST_iter173_{uuid.uuid4().hex[:6]}",
        "sku": f"TEST173-{uuid.uuid4().hex[:6]}",
        "price": 5000,
        "currency": "UGX",
        "stock": 0,
        "location_id": admin_location_id,
        "category": "general",
    }
    r = requests.post(f"{BASE_URL}/api/products", headers=admin_headers, json=payload, timeout=20)
    assert r.status_code in (200, 201), f"Product create failed: {r.status_code} {r.text}"
    product = r.json()
    pid = product["id"]
    # Add 2 variants
    for vname in ("Small", "Large"):
        rv = requests.post(
            f"{BASE_URL}/api/products/{pid}/variants",
            headers=admin_headers,
            json={"name": vname, "price": 5000, "stock": 5},
            timeout=20,
        )
        assert rv.status_code in (200, 201), f"Variant {vname} failed: {rv.status_code} {rv.text}"
    yield pid
    # cleanup
    requests.delete(f"{BASE_URL}/api/products/{pid}", headers=admin_headers, timeout=20)


def _get_variants(admin_headers, pid):
    # No GET /products/{id} — use the list endpoint and filter
    r = requests.get(f"{BASE_URL}/api/products", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    products = r.json()
    prod = next((p for p in products if p.get("id") == pid), None)
    assert prod, f"Product {pid} not found in list"
    return prod.get("variants") or []


# ===== generate-barcodes endpoint =====
class TestGenerateBarcodes:
    def test_default_fills_missing_only(self, admin_headers, seed_product):
        pid = seed_product
        # First call: variants should have no 5812- barcode → all get filled
        r = requests.post(
            f"{BASE_URL}/api/products/{pid}/generate-barcodes",
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "message" in data
        assert "format" in data
        assert data.get("force") is False
        # All variants now have 5812- barcodes
        variants = _get_variants(admin_headers, pid)
        assert len(variants) >= 2
        for v in variants:
            assert str(v.get("barcode", "")).startswith("5812-"), f"variant {v.get('name')} barcode={v.get('barcode')}"
        # capture current barcodes
        before = {v["id"]: v["barcode"] for v in variants}

        # Second call without force: should NOT change existing 5812- barcodes
        r2 = requests.post(
            f"{BASE_URL}/api/products/{pid}/generate-barcodes",
            headers=admin_headers,
            timeout=20,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("force") is False
        # The message should indicate 0 regenerated
        assert "Generated 0" in d2.get("message", "") or "0" in d2.get("message", "")
        variants_after = _get_variants(admin_headers, pid)
        after = {v["id"]: v["barcode"] for v in variants_after}
        assert after == before, "Existing 5812 barcodes must NOT change without force=true"

    def test_force_regenerates_all(self, admin_headers, seed_product):
        pid = seed_product
        # ensure all have barcodes first
        requests.post(f"{BASE_URL}/api/products/{pid}/generate-barcodes", headers=admin_headers, timeout=20)
        before = {v["id"]: v["barcode"] for v in _get_variants(admin_headers, pid)}

        r = requests.post(
            f"{BASE_URL}/api/products/{pid}/generate-barcodes?force=true",
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "message" in data
        assert "format" in data
        assert data.get("force") is True
        # message should say Generated N (N = number of variants)
        assert "Generated" in data.get("message", "")

        variants_after = _get_variants(admin_headers, pid)
        after = {v["id"]: v["barcode"] for v in variants_after}
        # All barcodes should now be different AND still start with 5812-
        for vid, bc in after.items():
            assert str(bc).startswith("5812-")
            assert bc != before.get(vid), f"variant {vid} barcode did not change after force=true"


# ===== RBAC: 403 for non-privileged user =====
class TestBarcodeRBAC:
    def test_unauthenticated_blocked(self, seed_product):
        pid = seed_product
        r = requests.post(f"{BASE_URL}/api/products/{pid}/generate-barcodes", timeout=20)
        # FastAPI returns 401 or 403 for missing auth
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_non_privileged_role_blocked(self, admin_headers, seed_product):
        """Create a TEST volunteer user, login, attempt generate-barcodes → 403."""
        pid = seed_product
        # Create a TEST user with role 'volunteer' (no barcode permission)
        suffix = uuid.uuid4().hex[:6]
        user_payload = {
            "email": f"TEST_iter173_{suffix}@example.com",
            "name": f"TEST iter173 {suffix}",
            "password": "Test@5812!",
            "role": "Staff",
        }
        cr = requests.post(f"{BASE_URL}/api/admin/users", headers=admin_headers, json=user_payload, timeout=20)
        if cr.status_code not in (200, 201):
            pytest.skip(f"Could not create test user: {cr.status_code} {cr.text[:200]}")
        created = cr.json()
        uid = created.get("id")
        try:
            # Login as volunteer
            lr = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"identifier": user_payload["email"], "password": user_payload["password"]},
                timeout=20,
            )
            if lr.status_code != 200:
                pytest.skip(f"Volunteer login failed: {lr.status_code} {lr.text[:200]}")
            vtoken = lr.json().get("token") or lr.json().get("access_token")
            vh = {"Authorization": f"Bearer {vtoken}", "Content-Type": "application/json"}
            r = requests.post(
                f"{BASE_URL}/api/products/{pid}/generate-barcodes",
                headers=vh,
                timeout=20,
            )
            assert r.status_code == 403, f"Expected 403 for volunteer, got {r.status_code}: {r.text[:200]}"
            # also test force=true
            r2 = requests.post(
                f"{BASE_URL}/api/products/{pid}/generate-barcodes?force=true",
                headers=vh,
                timeout=20,
            )
            assert r2.status_code == 403
        finally:
            if uid:
                requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers, timeout=20)
