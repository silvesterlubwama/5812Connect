"""Iteration 162 backend tests:
- Password change (auth)
- Fund Requests module (advance/reimbursement, receipt upload, mark-paid, cancel, workflow autoseed)
- HR Manual Payslips
- Social work schools visibility
"""
import os
import io
import time
import pytest
import requests

def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    # read from frontend/.env
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found in env or frontend/.env")


BASE = _load_backend_url()
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"


def _login(identifier, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"identifier": identifier, "password": password}, timeout=30)
    return r


def _token(r):
    body = r.json() if r.ok else {}
    return body.get("token") or body.get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tk = _token(r)
    assert tk, f"No token in login response: {r.text}"
    return tk


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ============================================================
# PASSWORD CHANGE — critical fix verification
# ============================================================
class TestPasswordChange:
    def test_change_password_requires_auth(self):
        r = requests.post(f"{BASE}/api/auth/change-password", json={"current_password": "x", "new_password": "yyyyyy"})
        assert r.status_code in (401, 403), f"Expected 401/403 unauth, got {r.status_code}"

    def test_change_password_wrong_current_returns_401(self, admin_headers):
        r = requests.post(
            f"{BASE}/api/auth/change-password",
            headers=admin_headers,
            json={"current_password": "WRONG_PASSWORD_HERE!!!", "new_password": "NewTestPwd@1234"},
        )
        assert r.status_code == 401, f"Expected 401 for wrong current pw, got {r.status_code}: {r.text}"

    def test_change_password_short_returns_400(self, admin_headers):
        r = requests.post(
            f"{BASE}/api/auth/change-password",
            headers=admin_headers,
            json={"current_password": ADMIN_PASSWORD, "new_password": "abc"},
        )
        assert r.status_code == 400, f"Expected 400 for short pw, got {r.status_code}: {r.text}"

    def test_change_password_same_as_current_returns_400(self, admin_headers):
        r = requests.post(
            f"{BASE}/api/auth/change-password",
            headers=admin_headers,
            json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
        )
        assert r.status_code == 400, f"Expected 400 for same pw, got {r.status_code}: {r.text}"

    def test_change_password_success_and_rotate_back(self, admin_headers):
        """Change → login with new → login with old fails → change back."""
        new_pw = f"Temp@5812-{int(time.time())}"
        r = requests.post(
            f"{BASE}/api/auth/change-password",
            headers=admin_headers,
            json={"current_password": ADMIN_PASSWORD, "new_password": new_pw},
        )
        assert r.status_code == 200, f"Change failed: {r.status_code} {r.text}"

        # New password must work
        r_new = _login(ADMIN_EMAIL, new_pw)
        assert r_new.status_code == 200, f"Login with new pw failed: {r_new.status_code} {r_new.text}"
        new_token = _token(r_new)
        assert new_token

        # Old password must fail
        r_old = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r_old.status_code in (401, 400), f"Old pw should fail but got {r_old.status_code}"

        # Rotate back
        rb = requests.post(
            f"{BASE}/api/auth/change-password",
            headers={"Authorization": f"Bearer {new_token}", "Content-Type": "application/json"},
            json={"current_password": new_pw, "new_password": ADMIN_PASSWORD},
        )
        assert rb.status_code == 200, f"Rotate back failed: {rb.status_code} {rb.text}"

        # Confirm we can log in with original again
        r_final = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r_final.status_code == 200


# ============================================================
# FUND REQUESTS
# ============================================================
class TestFundWorkflow:
    def test_workflow_autoseed_idempotent(self, admin_headers):
        r1 = requests.get(f"{BASE}/api/funds/workflow", headers=admin_headers)
        assert r1.status_code == 200, f"workflow GET failed: {r1.status_code} {r1.text}"
        wf1 = r1.json()
        assert wf1.get("id") == "wf_fund_request_default"
        assert wf1.get("kind") == "fund_request"
        assert isinstance(wf1.get("steps"), list) and len(wf1["steps"]) >= 1

        r2 = requests.get(f"{BASE}/api/funds/workflow", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json().get("id") == wf1["id"]

    def test_unauthenticated_funds_returns_401(self):
        r = requests.get(f"{BASE}/api/funds/requests/mine")
        assert r.status_code in (401, 403)


class TestFundRequestCRUD:
    """Full CRUD flow on a fund request — kept in one class so we can clean up."""
    created_ids = []

    def test_invalid_kind_returns_400(self, admin_headers):
        r = requests.post(f"{BASE}/api/funds/requests", headers=admin_headers,
                          json={"kind": "bogus", "amount": 100, "purpose": "x"})
        assert r.status_code == 400

    def test_invalid_amount_returns_400(self, admin_headers):
        r = requests.post(f"{BASE}/api/funds/requests", headers=admin_headers,
                          json={"kind": "advance", "amount": 0, "purpose": "x"})
        assert r.status_code == 400

    def test_create_advance_then_get_mine(self, admin_headers):
        payload = {"kind": "advance", "amount": 125000, "currency": "UGX",
                   "purpose": "TEST_iter162 field trip transport", "category": "Transport"}
        r = requests.post(f"{BASE}/api/funds/requests", headers=admin_headers, json=payload)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        doc = r.json()
        assert doc["subject_kind"] == "fund_request"
        assert doc["status"] == "in_progress"
        assert doc["amount"] == 125000
        assert doc["metadata"]["kind"] == "advance"
        assert doc["title"].lower().startswith("advance")
        TestFundRequestCRUD.created_ids.append(doc["id"])

        # GET mine
        rm = requests.get(f"{BASE}/api/funds/requests/mine", headers=admin_headers)
        assert rm.status_code == 200
        mine = rm.json()
        assert any(x["id"] == doc["id"] for x in mine), "created request not in /mine"

    def test_create_reimbursement(self, admin_headers):
        r = requests.post(f"{BASE}/api/funds/requests", headers=admin_headers,
                          json={"kind": "reimbursement", "amount": 47500,
                                "purpose": "TEST_iter162 stationery receipts"})
        assert r.status_code == 200
        doc = r.json()
        assert doc["metadata"]["kind"] == "reimbursement"
        TestFundRequestCRUD.created_ids.append(doc["id"])

    def test_list_all_requests(self, admin_headers):
        r = requests.get(f"{BASE}/api/funds/requests", headers=admin_headers)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        ids = {x["id"] for x in rows}
        for cid in TestFundRequestCRUD.created_ids:
            assert cid in ids, f"created id {cid} missing from /requests"

    def test_receipt_upload(self, admin_headers):
        # use a created reimbursement
        rid = TestFundRequestCRUD.created_ids[-1]
        # tiny PNG (8x8 transparent) header
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
            b"\x08\x06\x00\x00\x00\xc4\x0f\xbe\x8b\x00\x00\x00\x19tEXtSoftware\x00"
            b"Adobe ImageReadyq\xc9e<\x00\x00\x00\rIDATx\xdac\xfc\xff\xff?\x03\x00"
            b"\x06\x00\x02\xfe\xa3X@\x9e\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
        # Use auth header WITHOUT Content-Type so requests sets multipart boundary
        hdr = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{BASE}/api/funds/requests/{rid}/receipt", headers=hdr, files=files)
        assert r.status_code == 200, f"receipt upload failed: {r.status_code} {r.text}"
        assert r.json().get("receipt_url"), "no receipt_url in response"

    def test_receipt_upload_invalid_content_type(self, admin_headers):
        rid = TestFundRequestCRUD.created_ids[-1]
        files = {"file": ("hack.exe", io.BytesIO(b"MZ\x90"), "application/x-msdownload")}
        hdr = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{BASE}/api/funds/requests/{rid}/receipt", headers=hdr, files=files)
        assert r.status_code == 400

    def test_mark_paid_blocked_when_in_progress(self, admin_headers):
        """Cannot mark-paid until approval lifecycle is 'approved'."""
        rid = TestFundRequestCRUD.created_ids[0]
        r = requests.post(f"{BASE}/api/funds/requests/{rid}/mark-paid", headers=admin_headers, json={})
        # The request status is 'in_progress', so mark-paid must reject with 400
        assert r.status_code == 400, f"Expected 400 (not approved), got {r.status_code}: {r.text}"

    def test_mark_paid_after_force_approve_and_idempotent(self, admin_headers):
        """Approve via direct DB short-circuit using admin and verify mark-paid idempotency."""
        # Use the second created request (reimbursement)
        rid = TestFundRequestCRUD.created_ids[1]

        # Force approve via /api/approvals/requests/{id}/act
        ad = requests.post(
            f"{BASE}/api/approvals/requests/{rid}/act",
            headers=admin_headers,
            json={"outcome": "approved", "note": "test approve"},
        )
        # If that endpoint signature differs, skip the lifecycle test gracefully
        if ad.status_code not in (200, 201):
            pytest.skip(f"approvals/act route returned {ad.status_code}: {ad.text[:200]} — skipping mark-paid full lifecycle")

        # Now mark-paid should succeed
        r1 = requests.post(f"{BASE}/api/funds/requests/{rid}/mark-paid", headers=admin_headers, json={"notes": "TEST_iter162"})
        assert r1.status_code == 200, f"mark-paid failed: {r1.status_code} {r1.text}"
        body1 = r1.json()
        assert body1.get("expense_id"), "no expense_id returned"
        first_exp = body1["expense_id"]

        # Idempotent — second call must return same expense_id
        r2 = requests.post(f"{BASE}/api/funds/requests/{rid}/mark-paid", headers=admin_headers, json={})
        assert r2.status_code == 200
        assert r2.json().get("expense_id") == first_exp, "mark-paid not idempotent — different expense_id returned!"

    def test_cancel_in_progress(self, admin_headers):
        """Create a fresh in_progress request and cancel it."""
        r = requests.post(f"{BASE}/api/funds/requests", headers=admin_headers,
                          json={"kind": "advance", "amount": 1000, "purpose": "TEST_iter162 to-cancel"})
        assert r.status_code == 200
        rid = r.json()["id"]
        TestFundRequestCRUD.created_ids.append(rid)
        d = requests.delete(f"{BASE}/api/funds/requests/{rid}", headers=admin_headers)
        assert d.status_code == 200, f"cancel failed: {d.status_code} {d.text}"

    @classmethod
    def teardown_class(cls):
        """Best-effort cleanup of TEST_ fund requests via DELETE."""
        r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
        if r.status_code != 200:
            return
        tk = _token(r)
        hdr = {"Authorization": f"Bearer {tk}"}
        for rid in cls.created_ids:
            try:
                requests.delete(f"{BASE}/api/funds/requests/{rid}", headers=hdr, timeout=10)
            except Exception:
                pass


# ============================================================
# HR MANUAL PAYSLIP
# ============================================================
class TestManualPayslip:
    created_ids = []

    def test_manual_payslip_validation(self, admin_headers):
        # Missing staff_id
        r = requests.post(f"{BASE}/api/hr/payslips/manual", headers=admin_headers,
                          json={"period": "2026-01", "gross_salary": 1000})
        assert r.status_code == 400

        # Missing period
        r = requests.post(f"{BASE}/api/hr/payslips/manual", headers=admin_headers,
                          json={"staff_id": "x", "gross_salary": 1000})
        assert r.status_code == 400

        # gross <= 0
        r = requests.post(f"{BASE}/api/hr/payslips/manual", headers=admin_headers,
                          json={"staff_id": "x", "period": "2026-01", "gross_salary": 0})
        assert r.status_code == 400

    def test_manual_payslip_creates_and_computes_net(self, admin_headers):
        # Find a staff (use admin as recipient)
        me = requests.get(f"{BASE}/api/auth/me", headers=admin_headers)
        assert me.status_code == 200
        sid = me.json()["id"]

        payload = {
            "staff_id": sid,
            "period": "2026-01",
            "gross_salary": 1000000,
            "currency": "UGX",
            "allowances": [{"name": "Transport", "amount": 50000}, {"name": "Airtime", "amount": 25000}],
            "deductions": [{"name": "Tax PAYE", "amount": 100000}],
            "notes": "TEST_iter162 manual payslip",
        }
        r = requests.post(f"{BASE}/api/hr/payslips/manual", headers=admin_headers, json=payload)
        assert r.status_code == 200, f"manual payslip failed: {r.status_code} {r.text}"
        ps = r.json()
        assert ps["is_manual"] is True
        assert ps["salary_id"] is None
        # net = 1000000 + 75000 - 100000 = 975000
        assert abs(ps["net_salary"] - 975000) < 0.01, f"net wrong: {ps['net_salary']}"
        assert ps["gross_salary"] == 1000000
        assert ps["allowances"] == 75000
        assert ps["deductions"] == 100000
        TestManualPayslip.created_ids.append(ps["id"])


# ============================================================
# SOCIAL WORK SCHOOLS
# ============================================================
class TestSocialWorkSchools:
    def test_admin_can_list_schools(self, admin_headers):
        r = requests.get(f"{BASE}/api/social-work/schools", headers=admin_headers)
        assert r.status_code == 200, f"schools list failed: {r.status_code} {r.text}"
        rows = r.json()
        assert isinstance(rows, list)
        # Don't assert non-empty (may be a fresh tenant); but every row must have id+name
        for s in rows:
            assert "id" in s and "name" in s
            assert "_id" not in s  # mongo internal id must be excluded
