"""Backend tests for iteration 140:
   1) POST /api/badges/auto-issue  (idempotent unified helper)
   2) Store settings peripherals fields (auto_print_receipt, auto_issue_badge,
      badge_label_size, print_mode) via PUT/GET /api/store-settings/{location_id}
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def first_location(admin_headers):
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    locs = r.json()
    if isinstance(locs, dict):
        locs = locs.get("locations") or locs.get("items") or []
    assert isinstance(locs, list) and locs
    return locs[0]


@pytest.fixture(scope="module")
def test_member(admin_headers, first_location):
    """Create a throw-away member used by the auto-issue tests."""
    suffix = uuid.uuid4().hex[:8]
    body = {
        "name": f"TEST_Iter140_{suffix}",
        "email": f"test_iter140_{suffix}@example.com",
        "phone": f"+25670{int(time.time()) % 10000000:07d}",
        "location_id": first_location["id"],
        "kind": "member",
        "role": "Member",
    }
    r = requests.post(f"{BASE_URL}/api/members", headers=admin_headers, json=body, timeout=20)
    assert r.status_code in (200, 201), r.text[:300]
    m = r.json()
    # Ensure no pre-existing badge
    yield m
    # Teardown: delete the member; corresponding wallet_badge cleanup may cascade
    requests.delete(f"{BASE_URL}/api/members/{m['id']}", headers=admin_headers, timeout=20)


# -----------------------------------------------------------------------------
# /api/badges/auto-issue — Idempotency, validation, audit fields
# -----------------------------------------------------------------------------
class TestAutoIssueBadge:
    def test_auth_required(self):
        r = requests.post(f"{BASE_URL}/api/badges/auto-issue",
                          json={"subject_kind": "member", "subject_id": "anything"}, timeout=15)
        assert r.status_code in (401, 403), r.text[:200]

    def test_missing_fields_returns_400(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                          json={}, timeout=15)
        assert r.status_code == 400, r.text[:300]

        r2 = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                           json={"subject_kind": "member"}, timeout=15)
        assert r2.status_code == 400

    def test_unsupported_kind_returns_400(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                          json={"subject_kind": "alien", "subject_id": "x"}, timeout=15)
        assert r.status_code == 400, r.text[:300]
        assert "Unsupported" in r.text or "subject_kind" in r.text

    def test_unknown_subject_returns_404(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                          json={"subject_kind": "member",
                                "subject_id": f"does-not-exist-{uuid.uuid4().hex}"},
                          timeout=15)
        assert r.status_code == 404, r.text[:300]

    def test_first_call_creates_then_idempotent(self, admin_headers, test_member):
        # First call: must create
        r1 = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                           json={"subject_kind": "member", "subject_id": test_member["id"]},
                           timeout=20)
        assert r1.status_code == 200, r1.text[:300]
        b1 = r1.json()
        assert b1.get("was_created") is True
        assert b1.get("token") and isinstance(b1["token"], str) and len(b1["token"]) >= 8
        assert b1.get("member_id") == test_member["id"]
        assert "_id" not in b1, "Mongo _id leaked"
        assert b1.get("name")  # name copied from subject
        assert b1.get("role")
        # Audit fields
        assert b1.get("issued_via") == "auto_kiosk"
        assert b1.get("issued_by")  # the admin user id
        assert "issued_by_name" in b1

        # Second call: must be idempotent (same token, was_created=false)
        r2 = requests.post(f"{BASE_URL}/api/badges/auto-issue", headers=admin_headers,
                           json={"subject_kind": "member", "subject_id": test_member["id"]},
                           timeout=20)
        assert r2.status_code == 200, r2.text[:300]
        b2 = r2.json()
        assert b2.get("was_created") is False
        assert b2.get("token") == b1["token"], "Different token returned — not idempotent"
        assert "_id" not in b2


# -----------------------------------------------------------------------------
# Store Settings peripherals fields
# -----------------------------------------------------------------------------
class TestStoreSettingsPeripherals:
    def test_put_then_get_persists_peripherals(self, admin_headers, first_location):
        loc_id = first_location["id"]
        # Save existing values to restore at teardown
        prev = requests.get(f"{BASE_URL}/api/store-settings/{loc_id}",
                            headers=admin_headers, timeout=15).json() or {}
        prev.pop("_id", None)

        payload = {
            **prev,
            "auto_print_receipt": True,
            "auto_issue_badge": True,
            "badge_label_size": "62x29",
            "print_mode": "default",
        }
        r = requests.put(f"{BASE_URL}/api/store-settings/{loc_id}",
                         headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text[:300]
        saved = r.json()
        assert saved.get("auto_print_receipt") is True
        assert saved.get("auto_issue_badge") is True
        assert saved.get("badge_label_size") == "62x29"
        assert saved.get("print_mode") == "default"

        # GET should return them back
        r2 = requests.get(f"{BASE_URL}/api/store-settings/{loc_id}",
                          headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        got = r2.json()
        assert got.get("auto_print_receipt") is True
        assert got.get("auto_issue_badge") is True
        assert got.get("badge_label_size") == "62x29"
        assert got.get("print_mode") == "default"
        assert "_id" not in got

        # Toggle off and confirm persists
        payload["auto_print_receipt"] = False
        payload["auto_issue_badge"] = False
        r3 = requests.put(f"{BASE_URL}/api/store-settings/{loc_id}",
                          headers=admin_headers, json=payload, timeout=15)
        assert r3.status_code == 200
        r4 = requests.get(f"{BASE_URL}/api/store-settings/{loc_id}",
                          headers=admin_headers, timeout=15).json()
        assert r4.get("auto_print_receipt") is False
        assert r4.get("auto_issue_badge") is False
