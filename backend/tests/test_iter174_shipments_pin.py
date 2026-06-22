"""Iter-174 backend regression for the new shipment-editor PIN flow + container/pallet/item full-edit endpoints + child documents 14-item checklist."""
import os
import io
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def staff_token():
    """Create a non-admin staff user to validate 403 path on admin endpoints."""
    rnd = uuid.uuid4().hex[:6]
    email = f"TEST_iter174_staff_{rnd}@example.com"
    # Login as admin first to create the staff user
    r = requests.post(f"{API}/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    tok = r.json().get("token") or r.json().get("access_token")
    h = {"Authorization": f"Bearer {tok}"}
    create = requests.post(f"{API}/admin/users", json={
        "name": "TEST iter174 staff",
        "email": email,
        "password": "Staff@1234",
        "role": "staff",
    }, headers=h, timeout=20)
    if create.status_code not in (200, 201):
        pytest.skip(f"could not seed staff user: {create.status_code} {create.text}")
    login = requests.post(f"{API}/auth/login",
                         json={"identifier": email, "password": "Staff@1234"},
                         timeout=20)
    if login.status_code != 200:
        pytest.skip(f"staff login failed: {login.status_code} {login.text}")
    return login.json().get("token") or login.json().get("access_token")


@pytest.fixture(scope="module")
def shipment(admin_headers):
    """Create a shipment for the module, delete on teardown."""
    r = requests.post(f"{API}/shipments", headers=admin_headers, json={
        "name": f"TEST_iter174_ship_{uuid.uuid4().hex[:6]}",
        "dest_country": "Uganda",
        "description": "iter-174 regression shipment",
        "target_ship_date": "2026-06-01",
    }, timeout=20)
    assert r.status_code == 200, f"create shipment failed: {r.status_code} {r.text}"
    s = r.json()
    yield s
    requests.delete(f"{API}/shipments/{s['id']}", headers=admin_headers, timeout=20)


# ---------- shipments: container dims editor ----------
class TestContainerDims:
    def test_update_container_dims_persists(self, admin_headers, shipment):
        sid = shipment["id"]
        new_dims = {"length_cm": 1500, "width_cm": 250, "height_cm": 280, "max_payload_kg": 28000}
        r = requests.put(f"{API}/shipments/{sid}",
                         headers=admin_headers,
                         json={"container_dims_cm": new_dims, "max_payload_kg": 28000},
                         timeout=20)
        assert r.status_code == 200, r.text
        # GET back to verify
        g = requests.get(f"{API}/shipments/{sid}", headers=admin_headers, timeout=20)
        assert g.status_code == 200
        body = g.json()
        cd = body.get("container_dims_cm") or {}
        assert float(cd.get("length_cm")) == 1500
        assert float(cd.get("width_cm")) == 250
        assert float(cd.get("height_cm")) == 280
        assert float(cd.get("max_payload_kg")) == 28000


# ---------- shipments: pallet manager ----------
class TestPallets:
    def test_add_update_delete_pallet(self, admin_headers, shipment):
        sid = shipment["id"]
        # Add
        r = requests.post(f"{API}/shipments/{sid}/pallets", headers=admin_headers, json={
            "label": "TEST_Pallet_A", "length_cm": 120, "width_cm": 80,
            "height_cm": 160, "x_cm": 50, "y_cm": 40, "color": "#10b981",
        }, timeout=20)
        assert r.status_code == 200, r.text
        pallet = r.json()
        pid = pallet["id"]
        assert pallet["label"] == "TEST_Pallet_A"
        assert float(pallet["length_cm"]) == 120
        assert float(pallet["x_cm"]) == 50
        assert pallet["color"] == "#10b981"
        # Update x_cm
        u = requests.put(f"{API}/shipments/{sid}/pallets/{pid}",
                        headers=admin_headers, json={"x_cm": 200}, timeout=20)
        assert u.status_code == 200, u.text
        # Verify
        g = requests.get(f"{API}/shipments/{sid}", headers=admin_headers, timeout=20)
        plt = next((p for p in g.json().get("pallets", []) if p["id"] == pid), None)
        assert plt is not None
        assert float(plt["x_cm"]) == 200
        # Delete
        d = requests.delete(f"{API}/shipments/{sid}/pallets/{pid}",
                            headers=admin_headers, timeout=20)
        assert d.status_code == 200


# ---------- shipments: item full edit + pallet assignment ----------
class TestItems:
    def test_add_full_edit_item(self, admin_headers, shipment):
        sid = shipment["id"]
        # Create pallet to assign to
        rp = requests.post(f"{API}/shipments/{sid}/pallets", headers=admin_headers,
                          json={"label": "TEST_pallet_for_item"}, timeout=20)
        pid = rp.json()["id"]
        # Add item
        r = requests.post(f"{API}/shipments/{sid}/items", headers=admin_headers,
                         json={"name": "TEST_Soccer_Ball", "weight_kg": 0.5,
                               "qty_needed": 5}, timeout=20)
        assert r.status_code == 200, r.text
        item = r.json()
        iid = item["id"]
        assert item["name"] == "TEST_Soccer_Ball"
        # Full edit — weight, dims, pallet, position
        u = requests.put(f"{API}/shipments/{sid}/items/{iid}", headers=admin_headers, json={
            "weight_kg": 0.75, "dims_cm": {"length": 30, "width": 30, "height": 30},
            "pallet_id": pid, "x_cm": 10, "y_cm": 20, "z_cm": 5,
            "qty_acquired": 1, "priority": "high",
        }, timeout=20)
        assert u.status_code == 200, u.text
        # Verify
        g = requests.get(f"{API}/shipments/{sid}", headers=admin_headers, timeout=20)
        item2 = next(i for i in g.json()["items"] if i["id"] == iid)
        assert float(item2["weight_kg"]) == 0.75
        assert float(item2["dims_cm"]["length"]) == 30
        assert item2["pallet_id"] == pid
        assert float(item2["x_cm"]) == 10
        assert int(item2["qty_acquired"]) == 1
        assert item2["priority"] == "high"


# ---------- shipments: PIN flow + security regression ----------
class TestPinFlow:
    def test_set_pin_requires_admin(self, staff_token, shipment):
        """Set-PIN endpoint must require admin (try with non-admin JWT → expect 403)."""
        sid = shipment["id"]
        h = {"Authorization": f"Bearer {staff_token}"}
        r = requests.post(f"{API}/shipments/{sid}/set-pin", headers=h,
                         json={"pin": "1234"}, timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_admin_set_pin_and_public_login(self, admin_headers, shipment):
        sid = shipment["id"]
        token = shipment["token"]
        # Set pin
        r = requests.post(f"{API}/shipments/{sid}/set-pin",
                         headers=admin_headers, json={"pin": "4321pin"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("set") is True
        # public_shipment now reports pin_required=true
        ps = requests.get(f"{API}/public/shipments/{token}", timeout=20)
        assert ps.status_code == 200
        assert ps.json().get("pin_required") is True
        # Wrong PIN → 401
        wrong = requests.post(f"{API}/public/shipments/{token}/login",
                              json={"pin": "wrong"}, timeout=20)
        assert wrong.status_code == 401, wrong.text
        # Correct PIN → edit_token
        ok = requests.post(f"{API}/public/shipments/{token}/login",
                           json={"pin": "4321pin"}, timeout=20)
        assert ok.status_code == 200, ok.text
        edit_token = ok.json()["edit_token"]
        assert isinstance(edit_token, str) and len(edit_token) > 10

    def test_public_item_without_auth_401(self, shipment):
        """POST /api/public/shipments/{token}/items WITHOUT X-Shipment-Edit-Token
        AND without admin JWT must return 401."""
        token = shipment["token"]
        r = requests.post(f"{API}/public/shipments/{token}/items",
                          json={"name": "TEST_unauth"}, timeout=20)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_public_edit_with_pin_token_works(self, shipment):
        token = shipment["token"]
        # Login again (PIN was set in previous test)
        lg = requests.post(f"{API}/public/shipments/{token}/login",
                           json={"pin": "4321pin"}, timeout=20)
        assert lg.status_code == 200, lg.text
        edit_token = lg.json()["edit_token"]
        h = {"X-Shipment-Edit-Token": edit_token}
        # Add item via public editor
        r = requests.post(f"{API}/public/shipments/{token}/items", headers=h,
                         json={"name": "TEST_Public_Item", "weight_kg": 2,
                               "qty_needed": 1}, timeout=20)
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["name"] == "TEST_Public_Item"
        iid = item["id"]
        # Update via public editor
        u = requests.put(f"{API}/public/shipments/{token}/items/{iid}",
                        headers=h, json={"name": "TEST_Public_Item_Updated"}, timeout=20)
        assert u.status_code == 200, u.text
        # Update container via public editor
        c = requests.put(f"{API}/public/shipments/{token}/container", headers=h,
                        json={"length_cm": 1400, "width_cm": 240,
                              "height_cm": 270, "max_payload_kg": 27000}, timeout=20)
        assert c.status_code == 200, c.text
        # Add pallet via public editor
        p = requests.post(f"{API}/public/shipments/{token}/pallets", headers=h,
                         json={"label": "TEST_Public_Pallet"}, timeout=20)
        assert p.status_code == 200, p.text
        # Cleanup
        requests.delete(f"{API}/public/shipments/{token}/items/{iid}", headers=h, timeout=20)
        requests.delete(f"{API}/public/shipments/{token}/pallets/{p.json()['id']}", headers=h, timeout=20)

    def test_public_login_wrong_pin_401(self, shipment):
        """POST /api/public/shipments/{token}/login with wrong PIN must return 401."""
        token = shipment["token"]
        r = requests.post(f"{API}/public/shipments/{token}/login",
                          json={"pin": "totallywrongpin"}, timeout=20)
        assert r.status_code == 401


# ---------- public payload shape: donor_count, leaderboard, container_dims ----------
class TestPublicPayloadShape:
    def test_public_response_includes_new_fields(self, shipment):
        token = shipment["token"]
        r = requests.get(f"{API}/public/shipments/{token}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        # Required new fields
        assert "container_dims_cm" in body
        assert "pin_required" in body
        totals = body.get("totals", {})
        assert "donor_count" in totals
        assert "leaderboard" in totals
        assert "pallet_count" in totals
        assert isinstance(totals["leaderboard"], list)
        # Pallet roster includes dims+positions
        for p in body.get("pallets", []):
            for f in ("length_cm", "width_cm", "height_cm", "x_cm", "y_cm"):
                assert f in p, f"pallet missing {f}"


# ---------- child file doc types: 14-item master list with synthetic flags ----------
class TestChildDocTypes:
    @pytest.fixture(scope="class")
    def child_id(self, admin_headers):
        # Try existing child, else create one
        r = requests.get(f"{API}/children", headers=admin_headers, timeout=20)
        if r.status_code == 200 and r.json():
            return r.json()[0]["id"]
        c = requests.post(f"{API}/children", headers=admin_headers,
                         json={"name": f"TEST_iter174_child_{uuid.uuid4().hex[:6]}",
                               "date_of_birth": "2015-01-01", "gender": "male"},
                         timeout=20)
        if c.status_code not in (200, 201):
            pytest.skip(f"could not seed child: {c.status_code} {c.text}")
        cid = c.json()["id"]
        yield cid
        # Cleanup
        requests.delete(f"{API}/children/{cid}", headers=admin_headers, timeout=20)
        return

    def test_doc_types_returns_14_entries(self, admin_headers, child_id):
        r = requests.get(f"{API}/children/{child_id}/file-doc-types",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        types = r.json()
        assert isinstance(types, list)
        assert len(types) == 14, f"expected 14 doc types, got {len(types)}"
        keys = [t["key"] for t in types]
        expected = {
            "child_photo", "ovcmis_form_008", "sponsorship_assessment", "school_report",
            "guardian_national_id", "lc1_introduction_letter", "medical_assessment",
            "family_consent_letter", "welfare_review", "school_document",
            "sponsor_letter_in", "sponsor_letter_out", "exit_form", "other",
        }
        assert set(keys) == expected

    def test_synthetic_flag_set_on_child_photo_and_welfare(self, admin_headers, child_id):
        r = requests.get(f"{API}/children/{child_id}/file-doc-types",
                         headers=admin_headers, timeout=20)
        types = r.json()
        by_key = {t["key"]: t for t in types}
        assert by_key["child_photo"].get("synthetic") is True
        assert by_key["welfare_review"].get("synthetic") is True
        # All others should NOT be synthetic
        for k, t in by_key.items():
            if k in ("child_photo", "welfare_review"):
                continue
            assert t.get("synthetic") is not True, f"{k} should not be synthetic"
        # Every entry has a count field
        for t in types:
            assert "count" in t
            assert isinstance(t["count"], int)

    def test_doc_upload_increments_count(self, admin_headers, child_id):
        # Count before
        before = requests.get(f"{API}/children/{child_id}/file-doc-types",
                              headers=admin_headers, timeout=20).json()
        before_count = next(t["count"] for t in before if t["key"] == "ovcmis_form_008")
        # Upload a doc
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 TEST"), "application/pdf")}
        data = {"doc_type": "ovcmis_form_008", "notes": "TEST_iter174"}
        up = requests.post(f"{API}/children/{child_id}/file-docs",
                          headers=admin_headers, files=files, data=data, timeout=20)
        assert up.status_code == 200, up.text
        doc_id = up.json()["id"]
        try:
            after = requests.get(f"{API}/children/{child_id}/file-doc-types",
                                 headers=admin_headers, timeout=20).json()
            after_count = next(t["count"] for t in after if t["key"] == "ovcmis_form_008")
            assert after_count == before_count + 1
        finally:
            # Cleanup via child_extras delete endpoint
            requests.delete(f"{API}/children/{child_id}/extras/{doc_id}",
                            headers=admin_headers, timeout=20)
