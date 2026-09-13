"""iter350 Phase 3/4/5 backend tests.

Covers:
  - HR pay-periods derived from anchor + frequency (weekly/biweekly/monthly)
  - Timesheet XLSX template has NO wage/rate cols; upload still imports
  - Timesheet submission uses canonical period from /hr/pay-periods
  - Badge-less checkpoint scan (phone / in-app id / junk)
  - Kiosk lookup (phone / in-app id / junk) + qr-scan by phone
  - Social work compliance: sponsored_threshold_days=365
  - Social work multi-select support_needed/support_given
  - Sponsor story generation via Claude Sonnet 4.6
"""
import io
import os
import re
from datetime import date, timedelta

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASSWORD = "Admin@5812"

# ---------------- shared fixtures ----------------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed {r.status_code}: {r.text[:300]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_user(admin_headers):
    r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text[:200]
    return r.json()


@pytest.fixture(scope="module")
def default_location(admin_user):
    return admin_user.get("active_campus_id") or admin_user.get("location_id") or ""


# ---------------- HR pay periods ----------------

class TestPayPeriods:
    def test_pay_periods_shape(self, admin_headers):
        r = requests.get(f"{API}/hr/pay-periods", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "frequency" in data and "anchor" in data and "current" in data and "periods" in data
        assert data["frequency"] in {"weekly", "biweekly", "monthly"}
        periods = data["periods"]
        assert len(periods) >= 2
        currents = [p for p in periods if p["is_current"]]
        assert len(currents) == 1, f"expected exactly one is_current=true, got {len(currents)}"
        # Contiguous & non-overlapping
        for a, b in zip(periods, periods[1:]):
            end_a = date.fromisoformat(a["end"])
            start_b = date.fromisoformat(b["start"])
            assert start_b == end_a + timedelta(days=1), f"non-contiguous: {a['end']} -> {b['start']}"
        # Correct length for freq
        step = 7 if data["frequency"] == "weekly" else (14 if data["frequency"] == "biweekly" else None)
        if step:
            for p in periods:
                span = (date.fromisoformat(p["end"]) - date.fromisoformat(p["start"])).days + 1
                assert span == step, f"period {p['period']} span={span} expected {step}"

    def test_pay_periods_weekly_from_anchor_and_restore(self, admin_headers, default_location):
        loc = default_location
        assert loc, "admin has no active_campus_id/location_id"
        # snapshot original settings
        cur = requests.get(f"{API}/hr/settings/{loc}", headers=admin_headers, timeout=15).json()
        orig_freq = cur.get("pay_frequency", "biweekly")
        orig_next = cur.get("next_pay_date", "2026-02-25")
        orig_anchor = cur.get("period_anchor_date", "")
        try:
            anchor = "2026-01-05"  # a Monday
            put = requests.put(
                f"{API}/hr/settings/{loc}",
                headers=admin_headers,
                json={"pay_frequency": "weekly", "period_anchor_date": anchor},
                timeout=15,
            )
            assert put.status_code == 200, put.text[:300]
            r = requests.get(f"{API}/hr/pay-periods", headers=admin_headers, timeout=15)
            assert r.status_code == 200
            data = r.json()
            assert data["frequency"] == "weekly"
            for p in data["periods"]:
                start = date.fromisoformat(p["start"])
                end = date.fromisoformat(p["end"])
                assert (end - start).days + 1 == 7
                # start must tile from anchor: (start - anchor).days % 7 == 0
                assert (start - date.fromisoformat(anchor)).days % 7 == 0
        finally:
            # restore
            requests.put(
                f"{API}/hr/settings/{loc}",
                headers=admin_headers,
                json={"pay_frequency": orig_freq, "next_pay_date": orig_next, "period_anchor_date": orig_anchor},
                timeout=15,
            )


# ---------------- Timesheet template & upload ----------------

class TestTimesheetTemplate:
    def test_template_no_wage_or_rate_columns(self, admin_headers):
        # get current period
        pp = requests.get(f"{API}/hr/pay-periods", headers=admin_headers, timeout=15).json()
        period = next((p["period"] for p in pp["periods"] if p["is_current"]), pp["periods"][0]["period"])
        r = requests.get(f"{API}/hr/timesheets/template", params={"period": period}, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        # parse xlsx and check headers
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(r.content))
        # find Timesheet sheet (first sheet is timesheet)
        ws = wb.worksheets[0]
        # scan first 15 rows for header row
        headers = None
        for row in ws.iter_rows(min_row=1, max_row=15, values_only=True):
            if row and any(str(c or "").strip() == "Staff Name" for c in row):
                headers = [str(c or "").strip() for c in row if c is not None and str(c).strip() != ""]
                break
        assert headers is not None, "Staff Name header row not found"
        expected = ["Staff Name", "Badge Number", "Days Worked", "Hours Worked", "PTO Days", "Notes", "Signature"]
        assert headers[:len(expected)] == expected, f"headers={headers}"
        # No wage type / rate anywhere
        for row in ws.iter_rows(values_only=True):
            for c in row:
                s = str(c or "").lower()
                assert "wage type" not in s, f"found 'wage type' cell"
                assert "rate" not in s or "hourly rate" not in s, f"rate leakage: {c}"

    def test_template_upload_still_imports(self, admin_headers):
        pp = requests.get(f"{API}/hr/pay-periods", headers=admin_headers, timeout=15).json()
        period = next((p["period"] for p in pp["periods"] if p["is_current"]), pp["periods"][0]["period"])
        # ensure at least one salary exists
        sal_list = requests.get(f"{API}/hr/salaries", headers=admin_headers, timeout=15).json()
        if not sal_list:
            # create a minimal salary tied to admin user
            me = requests.get(f"{API}/auth/me", headers=admin_headers).json()
            body = {
                "staff_id": me["id"],
                "staff_name": me.get("name") or "Admin",
                "wage_type": "salary",
                "monthly_amount": 1000,
                "location_id": me.get("location_id") or me.get("active_campus_id"),
            }
            cr = requests.post(f"{API}/hr/salaries", headers=admin_headers, json=body, timeout=15)
            assert cr.status_code in (200, 201), cr.text[:300]
            sal_list = requests.get(f"{API}/hr/salaries", headers=admin_headers, timeout=15).json()
        assert sal_list, "need at least one salary to test upload"
        target = sal_list[0]
        # download template & fill in
        tmpl = requests.get(f"{API}/hr/timesheets/template", params={"period": period}, headers=admin_headers, timeout=30)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(tmpl.content))
        ws = wb.worksheets[0]
        header_row_idx = None
        for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
            if row and any(str(c or "").strip() == "Staff Name" for c in row):
                header_row_idx = i
                break
        assert header_row_idx
        # locate the row for our staff (by name) and set Days Worked to 5
        col_name = 1
        col_badge = 2
        col_days = 3
        filled = False
        for r_i in range(header_row_idx + 1, header_row_idx + 200):
            name_cell = ws.cell(row=r_i, column=col_name).value
            badge_cell = ws.cell(row=r_i, column=col_badge).value
            if not name_cell and not badge_cell:
                continue
            if (str(name_cell or "").strip().lower() == (target.get("staff_name") or "").strip().lower()
                    or (badge_cell and str(badge_cell).strip() == str(target.get("badge_number") or ""))):
                ws.cell(row=r_i, column=col_days).value = 5
                filled = True
                break
        if not filled:
            # just fill the first empty-name row with target's name + 5 days
            for r_i in range(header_row_idx + 1, header_row_idx + 200):
                if not ws.cell(row=r_i, column=col_name).value:
                    ws.cell(row=r_i, column=col_name).value = target.get("staff_name") or "Admin"
                    ws.cell(row=r_i, column=col_badge).value = target.get("badge_number") or ""
                    ws.cell(row=r_i, column=col_days).value = 5
                    filled = True
                    break
        assert filled
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        files = {"file": ("filled.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        # do NOT set Content-Type
        h = {"Authorization": admin_headers["Authorization"]}
        up = requests.post(f"{API}/hr/timesheets/upload", params={"period": period}, headers=h, files=files, timeout=30)
        assert up.status_code == 200, f"upload failed: {up.status_code} {up.text[:400]}"
        body = up.json()
        # look for imported/submitted rows
        assert isinstance(body, dict)
        # verify a submitted timesheet now exists for this period
        ts_list = requests.get(f"{API}/hr/timesheets", params={"period": period}, headers=admin_headers, timeout=15).json()
        assert any(t.get("status") in ("submitted", "approved") for t in ts_list), f"no submitted rows in {ts_list[:2]}"


# ---------------- Timesheet submission with canonical period ----------------

class TestTimesheetSubmit:
    def test_submit_and_approve(self, admin_headers, admin_user):
        pp = requests.get(f"{API}/hr/pay-periods", headers=admin_headers, timeout=15).json()
        current = next((p for p in pp["periods"] if p["is_current"]), pp["periods"][0])
        period = current["period"]
        start = date.fromisoformat(current["start"])
        entries = [{"date": (start + timedelta(days=i)).isoformat(), "day_worked": True} for i in (0, 1)]
        body = {"period": period, "days_worked": 2, "entries": entries}
        r = requests.post(f"{API}/hr/timesheets", headers=admin_headers, json=body, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"
        ts = r.json()
        assert ts.get("period") == period
        ts_id = ts["id"]
        # list by period
        lst = requests.get(f"{API}/hr/timesheets", params={"period": period}, headers=admin_headers, timeout=15).json()
        assert any(t.get("id") == ts_id for t in lst)
        # approve
        ap = requests.put(f"{API}/hr/timesheets/{ts_id}/approve", headers=admin_headers, timeout=15)
        assert ap.status_code == 200, ap.text[:300]


# ---------------- Badge-less checkpoint scan ----------------

@pytest.fixture(scope="module")
def cp_session(admin_headers, default_location):
    """Create a checkpoint as admin, read PIN, pair, return X-Checkpoint-Session token."""
    loc = default_location
    assert loc, "no location"
    body = {"name": "TEST_iter350 CP", "location_id": loc, "kind": "check_in_only"}
    cp = requests.post(f"{API}/security/checkpoints", headers=admin_headers, json=body, timeout=15)
    assert cp.status_code == 200, cp.text[:300]
    checkpoint = cp.json()
    pin = checkpoint["pairing_pin"]
    pr = requests.post(f"{API}/security/checkpoint/pair", json={"pin": pin, "mode": "security"}, timeout=15)
    assert pr.status_code == 200, pr.text[:300]
    token = pr.json()["session_token"]
    yield {"token": token, "checkpoint_id": checkpoint["id"]}
    # cleanup
    try:
        requests.delete(f"{API}/security/checkpoints/{checkpoint['id']}", headers=admin_headers, timeout=15)
    except Exception:
        pass


class TestBadgelessScan:
    def _user_with_phone(self, admin_headers):
        for path in ("/admin/users", "/users"):
            resp = requests.get(f"{API}{path}", headers=admin_headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            rows = data if isinstance(data, list) else (data.get("users") or data.get("items") or [])
            for u in rows:
                if u.get("phone") and len(re.sub(r"\D", "", u["phone"])) >= 7:
                    return u
        return None

    def test_scan_by_phone(self, cp_session, admin_headers):
        u = self._user_with_phone(admin_headers)
        if not u:
            pytest.skip("no user with phone found")
        headers = {"X-Checkpoint-Session": cp_session["token"], "Content-Type": "application/json"}
        r = requests.post(f"{API}/security/checkpoint/scan", headers=headers,
                          json={"scan_type": "manual", "payload": u["phone"]}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        ev = r.json()
        assert ev.get("badgeless") is True, f"expected badgeless=true, got {ev.get('badgeless')}"
        assert ev.get("matched_by") == "phone", f"matched_by={ev.get('matched_by')}"
        assert "badge-less entry" in (ev.get("reason") or "").lower()

    def test_scan_by_app_id(self, cp_session, admin_user):
        headers = {"X-Checkpoint-Session": cp_session["token"], "Content-Type": "application/json"}
        r = requests.post(f"{API}/security/checkpoint/scan", headers=headers,
                          json={"scan_type": "manual", "payload": admin_user["id"]}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        ev = r.json()
        # matched_by should be app_id (or id-ish)
        assert ev.get("badgeless") is True
        assert ev.get("matched_by") in ("app_id", "id", "user_id"), f"matched_by={ev.get('matched_by')}"
        assert "badge-less entry" in (ev.get("reason") or "").lower()

    def test_scan_junk(self, cp_session):
        headers = {"X-Checkpoint-Session": cp_session["token"], "Content-Type": "application/json"}
        r = requests.post(f"{API}/security/checkpoint/scan", headers=headers,
                          json={"scan_type": "manual", "payload": "ZZZZ-NOPE-999"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        ev = r.json()
        assert ev.get("decision") == "denied"
        assert (ev.get("subject") or {}).get("kind") == "unknown"
        assert not ev.get("badgeless")


# ---------------- Kiosk lookup ----------------

class TestKioskLookup:
    def _get_phone_user(self, admin_headers):
        # try members first
        rows_resp = requests.get(f"{API}/members", headers=admin_headers, timeout=15).json()
        rows = rows_resp if isinstance(rows_resp, list) else (rows_resp.get("members") or [])
        for m in rows:
            if m.get("phone") and len(re.sub(r"\D", "", m["phone"])) >= 7:
                return ("member", m)
        users_resp = requests.get(f"{API}/users", headers=admin_headers, timeout=15).json()
        users = users_resp if isinstance(users_resp, list) else (users_resp.get("users") or users_resp.get("items") or [])
        for u in users:
            if u.get("phone") and len(re.sub(r"\D", "", u["phone"])) >= 7:
                return ("user", u)
        return (None, None)

    def test_lookup_by_phone_and_id(self, admin_headers):
        kind, u = self._get_phone_user(admin_headers)
        if not u:
            pytest.skip("no member/user with phone")
        r = requests.get(f"{API}/kiosk/lookup", params={"identifier": u["phone"]}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        # by id
        r2 = requests.get(f"{API}/kiosk/lookup", params={"identifier": u["id"]}, timeout=15)
        assert r2.status_code == 200, r2.text[:300]

    def test_lookup_junk(self):
        r = requests.get(f"{API}/kiosk/lookup", params={"identifier": "ZZZZ-NOPE-999"}, timeout=15)
        assert r.status_code == 404
        assert "national" in (r.json().get("detail") or "").lower() or "phone" in (r.json().get("detail") or "").lower()

    def test_qr_scan_by_phone(self, admin_headers):
        kind, u = self._get_phone_user(admin_headers)
        if not u:
            pytest.skip("no phone user")
        r = requests.post(f"{API}/checkins/qr-scan", headers=admin_headers, json={"qr_data": u["phone"]}, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"


# ---------------- Social work — compliance yearly ----------------

class TestSocialCompliance:
    def test_compliance_due_sponsored_365(self, admin_headers):
        r = requests.get(f"{API}/social-work/reviews/compliance/due", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("sponsored_threshold_days") == 365
        assert data.get("threshold_days") == 90
        for row in data.get("list", []):
            assert "threshold_days" in row and "sponsored" in row
            if row["sponsored"]:
                assert row["threshold_days"] == 365


# ---------------- Social work — multi-select support ----------------

EXISTING_CASE_ID = "sc_140b496b"


class TestSupportTypes:
    def test_update_support_arrays(self, admin_headers):
        # verify case exists
        got = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15)
        if got.status_code == 404:
            pytest.skip("preseeded case sc_140b496b not present")
        assert got.status_code == 200
        body = {"support_needed": ["school_fees", "food"], "support_given": ["medical"]}
        r = requests.put(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text[:300]
        chk = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15).json()
        assert sorted(chk.get("support_needed") or []) == sorted(["school_fees", "food"])
        assert chk.get("support_given") == ["medical"]

    def test_reject_unknown_value(self, admin_headers):
        r = requests.put(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers,
                         json={"support_needed": ["nonsense"]}, timeout=15)
        if r.status_code == 404:
            pytest.skip("case not present")
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"

    def test_reject_non_list(self, admin_headers):
        r = requests.put(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers,
                         json={"support_needed": "school_fees"}, timeout=15)
        if r.status_code == 404:
            pytest.skip("case not present")
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


# ---------------- Sponsor story ----------------

class TestSponsorStory:
    def test_generate_and_save(self, admin_headers):
        got = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15)
        if got.status_code == 404:
            pytest.skip("preseeded case not present")
        body = {
            "tone": "warm",
            "length": "short",
            "inputs": {
                "favourite_colour": "bright yellow",
                "dream": "a nurse",
                "living_situation": "lives with her grandmother",
            },
        }
        r = requests.post(f"{API}/social-work/cases/{EXISTING_CASE_ID}/sponsor-story",
                          headers=admin_headers, json=body, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        data = r.json()
        story = data.get("story") or ""
        assert len(story) > 30, f"story too short: {story!r}"
        assert data.get("model") == "claude-sonnet-4-6"
        low = story.lower()
        # story should not leak school name / address / diagnosis
        for banned in ("school name", "diagnosis"):
            assert banned not in low, f"story contains banned '{banned}'"
        # verify persisted
        chk = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15).json()
        assert chk.get("sponsor_story")
        assert chk.get("sponsor_story_generated_at")

    def test_hand_edit_save(self, admin_headers):
        got = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15)
        if got.status_code == 404:
            pytest.skip("preseeded case not present")
        r = requests.put(f"{API}/social-work/cases/{EXISTING_CASE_ID}/sponsor-story",
                         headers=admin_headers, json={"story": "Hand edited story."}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("story") == "Hand edited story."
        chk = requests.get(f"{API}/social-work/cases/{EXISTING_CASE_ID}", headers=admin_headers, timeout=15).json()
        assert chk.get("sponsor_story") == "Hand edited story."
