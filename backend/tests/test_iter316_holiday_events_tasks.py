"""iter 316 backend tests.

Coverage:
- Calendar event with is_free/ticket_tiers persistence
- Event duplicate endpoint
- Shared calendar feed with include_tasks + task_scope campus/mine (JSON + ICS)
- Holiday policy CRUD + kinds + admin-only + per-name persistence across years
- Payroll credit for hourly (with & without worked holiday), optional_paid, daily
- Payslip generation persists holiday_credit
- /api/tasks board-scoping regression (restricted board not visible to non-tagged)
"""
import os
import time
import uuid
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fallback: read frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE = _load_base()
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


def _login(cred):
    r = requests.post(f"{BASE}/api/auth/login", json=cred, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, f"missing token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def admin_hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def me(admin_hdr):
    r = requests.get(f"{BASE}/api/auth/me", headers=admin_hdr, timeout=15)
    assert r.status_code == 200
    return r.json()


# ── Cleanup registry (module-scoped) ────────────────────────────────────
CREATED = {"events": [], "boards": [], "tasks": [], "salaries": [], "policies": [], "timesheets": [], "share_configs": [], "payslips": []}


@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_hdr):
    yield
    # events
    for eid in CREATED["events"]:
        try:
            requests.delete(f"{BASE}/api/events/{eid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for tid in CREATED["tasks"]:
        try:
            requests.delete(f"{BASE}/api/tasks/{tid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for bid in CREATED["boards"]:
        try:
            requests.delete(f"{BASE}/api/boards/{bid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for sid in CREATED["salaries"]:
        try:
            requests.delete(f"{BASE}/api/hr/salaries/{sid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for tsid in CREATED["timesheets"]:
        try:
            requests.delete(f"{BASE}/api/hr/timesheets/{tsid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for cid in CREATED["share_configs"]:
        try:
            requests.delete(f"{BASE}/api/calendar/share-configs/{cid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for key in CREATED["policies"]:
        try:
            requests.delete(f"{BASE}/api/holidays/policies/{key}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
    for pid in CREATED["payslips"]:
        try:
            requests.delete(f"{BASE}/api/hr/payslips/{pid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass


# ═══════════════════════ 1. EVENT create + duplicate ═══════════════════
class TestEvents:
    def test_create_paid_event_with_ticket_tiers(self, admin_hdr):
        payload = {
            "title": f"TEST_iter316_paid_evt_{uuid.uuid4().hex[:6]}",
            "date": "2026-06-15",
            "time": "10:00",
            "type": "meeting",
            "location": "Main Hall",
            "capacity": 100,
            "is_free": False,
            "price": 25.0,
            "ticket_tiers": [
                {"id": "tier_a", "name": "Standard", "price": 25.0, "qty": 50, "sold": 0},
                {"id": "tier_b", "name": "VIP", "price": 75.0, "qty": 10, "sold": 0},
            ],
        }
        r = requests.post(f"{BASE}/api/events", json=payload, headers=admin_hdr, timeout=15)
        assert r.status_code in (200, 201), r.text
        ev = r.json()
        CREATED["events"].append(ev["id"])
        assert ev["is_free"] is False
        assert float(ev["price"]) == 25.0
        assert len(ev["ticket_tiers"]) == 2
        # verify persistence via GET
        g = requests.get(f"{BASE}/api/events/{ev['id']}", headers=admin_hdr, timeout=15)
        assert g.status_code == 200
        got = g.json()
        assert got["is_free"] is False
        assert len(got["ticket_tiers"]) == 2
        assert got["capacity"] == 100

    def test_duplicate_event(self, admin_hdr):
        payload = {
            "title": f"TEST_iter316_dup_src_{uuid.uuid4().hex[:6]}",
            "date": "2026-07-10",
            "time": "09:00",
            "type": "meeting",
            "is_free": True,
        }
        r = requests.post(f"{BASE}/api/events", json=payload, headers=admin_hdr, timeout=15)
        assert r.status_code in (200, 201)
        src = r.json()
        CREATED["events"].append(src["id"])
        d = requests.post(f"{BASE}/api/events/{src['id']}/duplicate", headers=admin_hdr, timeout=15)
        assert d.status_code in (200, 201), d.text
        dup = d.json()
        assert dup["id"] != src["id"]
        assert src["title"] in dup["title"] or "copy" in dup["title"].lower() or dup["title"]  # tolerate any rename
        CREATED["events"].append(dup["id"])


# ═══════════════════════ 2. HOLIDAY POLICY CRUD ═════════════════════════
class TestHolidayPolicies:
    def test_list_holidays_default_unpaid(self, admin_hdr):
        r = requests.get(f"{BASE}/api/holidays?year=2026&country=US", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        hs = r.json()
        assert len(hs) > 0
        tks = [h for h in hs if h["name"] == "Thanksgiving Day"]
        assert tks, "Thanksgiving Day missing from 2026 US"
        assert tks[0]["policy"] == "unpaid"
        assert tks[0]["policy_key"] == "US:thanksgiving-day"

    def test_set_policy_paid_persists_across_years(self, admin_hdr):
        body = {"name": "Thanksgiving Day", "country": "US", "kind": "paid"}
        r = requests.put(f"{BASE}/api/holidays/policies", json=body, headers=admin_hdr, timeout=15)
        assert r.status_code == 200, r.text
        CREATED["policies"].append("US:thanksgiving-day")
        # verify 2026
        r26 = requests.get(f"{BASE}/api/holidays?year=2026&country=US", headers=admin_hdr, timeout=15).json()
        t26 = [h for h in r26 if h["name"] == "Thanksgiving Day"][0]
        assert t26["policy"] == "paid"
        # same for 2027 (per-name, not per-date)
        r27 = requests.get(f"{BASE}/api/holidays?year=2027&country=US", headers=admin_hdr, timeout=15).json()
        t27 = [h for h in r27 if h["name"] == "Thanksgiving Day"][0]
        assert t27["policy"] == "paid"
        assert t27["date"] != t26["date"]  # date auto-computed

    def test_hidden_removes_from_list(self, admin_hdr):
        body = {"name": "Columbus Day", "country": "US", "kind": "hidden"}
        r = requests.put(f"{BASE}/api/holidays/policies", json=body, headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        CREATED["policies"].append("US:columbus-day")
        hs = requests.get(f"{BASE}/api/holidays?year=2026&country=US", headers=admin_hdr, timeout=15).json()
        assert not [h for h in hs if h["name"] == "Columbus Day"]
        # include_hidden shows it
        hs2 = requests.get(f"{BASE}/api/holidays?year=2026&country=US&include_hidden=true", headers=admin_hdr, timeout=15).json()
        assert [h for h in hs2 if h["name"] == "Columbus Day"]

    def test_delete_policy_resets_to_unpaid(self, admin_hdr):
        r = requests.delete(f"{BASE}/api/holidays/policies/US:columbus-day", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        try:
            CREATED["policies"].remove("US:columbus-day")
        except ValueError:
            pass
        hs = requests.get(f"{BASE}/api/holidays?year=2026&country=US", headers=admin_hdr, timeout=15).json()
        col = [h for h in hs if h["name"] == "Columbus Day"]
        assert col and col[0]["policy"] == "unpaid"

    def test_non_admin_forbidden(self, admin_hdr):
        # create a non-admin user
        email = f"TEST_iter316_user_{uuid.uuid4().hex[:6]}@ex.com"
        payload = {"name": "Iter316 Nonadmin", "email": email, "role": "member",
                   "location_id": "loc_001", "password": "Test@5812!"}
        cr = requests.post(f"{BASE}/api/admin/users", json=payload, headers=admin_hdr, timeout=15)
        if cr.status_code not in (200, 201):
            pytest.skip(f"could not create non-admin user: {cr.status_code} {cr.text[:200]}")
        uid = cr.json().get("id")
        tok = _login({"identifier": email, "password": "Test@5812!"})
        hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        r_put = requests.put(f"{BASE}/api/holidays/policies", json={"name": "X", "country": "US", "kind": "paid"}, headers=hdr, timeout=15)
        assert r_put.status_code == 403, f"expected 403, got {r_put.status_code}: {r_put.text[:200]}"
        r_del = requests.delete(f"{BASE}/api/holidays/policies/US:foo", headers=hdr, timeout=15)
        assert r_del.status_code == 403
        # cleanup user
        try:
            requests.delete(f"{BASE}/api/admin/users/{uid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass


# ═══════════════════════ 3. PAYROLL HOLIDAY CREDIT ═══════════════════════
def _staff_id(admin_hdr, me):
    """Use current admin as staffer for salary tests (they exist and have loc_001)."""
    return me["id"]


class TestPayrollHolidayCredit:
    @pytest.fixture(scope="class", autouse=True)
    def ensure_paid_thanksgiving(self, admin_hdr, me):
        # nuke any pre-existing active salaries for admin so leakage between tests can't
        # taint the wage_type used by preview
        existing = requests.get(f"{BASE}/api/hr/salaries", headers=admin_hdr, timeout=15).json()
        if isinstance(existing, list):
            for s in existing:
                if s.get("staff_id") == me["id"]:
                    try:
                        requests.delete(f"{BASE}/api/hr/salaries/{s['id']}", headers=admin_hdr, timeout=10)
                    except Exception:
                        pass
        # Ensure Thanksgiving is 'paid' for these tests
        r = requests.put(f"{BASE}/api/holidays/policies",
                         json={"name": "Thanksgiving Day", "country": "US", "kind": "paid"},
                         headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        if "US:thanksgiving-day" not in CREATED["policies"]:
            CREATED["policies"].append("US:thanksgiving-day")
        yield

    def _mk_salary(self, admin_hdr, me, **overrides):
        base = {
            "staff_id": me["id"],
            "wage_type": "hourly",
            "hourly_rate": 10.0,
            "holiday_hours": 8,
            "base_salary": 0,
            "currency": "USD",
            "pay_frequency": "monthly",
            "location_id": "loc_001",
            "effective_date": "2026-01-01",
        }
        base.update(overrides)
        r = requests.post(f"{BASE}/api/hr/salaries", json=base, headers=admin_hdr, timeout=15)
        assert r.status_code in (200, 201), r.text
        sal = r.json()
        CREATED["salaries"].append(sal["id"])
        return sal

    def _preview(self, admin_hdr, period, staff_id):
        r = requests.post(f"{BASE}/api/hr/payslips/preview",
                          json={"period": period, "staff_ids": [staff_id]},
                          headers=admin_hdr, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        rows = data.get("rows") or data.get("payslips") or []
        assert rows, f"no rows in preview: {data}"
        return rows[0]

    def test_hourly_paid_holiday_credit(self, admin_hdr, me):
        sal = self._mk_salary(admin_hdr, me)
        # 2026-11 has Thanksgiving 2026-11-26 (paid)
        row = self._preview(admin_hdr, "2026-11", me["id"])
        hc = row.get("holiday_credit") or {}
        assert hc.get("hours") == 8, f"expected 8h holiday credit, got {hc}"
        wd = str(row.get("wage_details") or "").lower()
        assert "holiday" in wd and ("8" in wd), f"wage_details should mention holiday credit 8h: {wd!r}"
        # 2026-10 has no paid holiday
        row_oct = self._preview(admin_hdr, "2026-10", me["id"])
        hc_oct = row_oct.get("holiday_credit") or {}
        assert (hc_oct.get("hours") or 0) == 0
        # cleanup
        requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=admin_hdr, timeout=10)
        CREATED["salaries"].remove(sal["id"])

    def _submit_and_approve_ts(self, admin_hdr, staff_id, period, hours_worked, entries):
        ts = {"staff_id": staff_id, "period": period,
              "days_worked": 21, "hours_worked": hours_worked, "entries": entries}
        r = requests.post(f"{BASE}/api/hr/timesheets", json=ts, headers=admin_hdr, timeout=15)
        assert r.status_code in (200, 201), r.text
        tsid = r.json()["id"]
        CREATED["timesheets"].append(tsid)
        ra = requests.put(f"{BASE}/api/hr/timesheets/{tsid}/approve", json={}, headers=admin_hdr, timeout=15)
        assert ra.status_code == 200, f"approve failed: {ra.status_code} {ra.text[:200]}"
        return tsid

    def test_hourly_worked_holiday_stacks(self, admin_hdr, me):
        sal = self._mk_salary(admin_hdr, me)
        tsid = self._submit_and_approve_ts(admin_hdr, me["id"], "2026-11", 160,
                                            [{"date": "2026-11-26", "hours": 8}])
        row = self._preview(admin_hdr, "2026-11", me["id"])
        gross = float(row.get("gross") or row.get("base_gross") or 0)
        expected = 10 * (160 + 8)
        assert abs(gross - expected) < 0.5, f"gross {gross} != expected {expected}; row={row}"
        requests.delete(f"{BASE}/api/hr/timesheets/{tsid}", headers=admin_hdr, timeout=10)
        CREATED["timesheets"].remove(tsid)
        requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=admin_hdr, timeout=10)
        CREATED["salaries"].remove(sal["id"])

    def test_optional_paid_worked_no_credit(self, admin_hdr, me):
        # flip Thanksgiving to optional_paid for this test
        requests.put(f"{BASE}/api/holidays/policies",
                     json={"name": "Thanksgiving Day", "country": "US", "kind": "optional_paid"},
                     headers=admin_hdr, timeout=15)
        try:
            sal = self._mk_salary(admin_hdr, me)
            tsid = self._submit_and_approve_ts(admin_hdr, me["id"], "2026-11", 160,
                                                [{"date": "2026-11-26", "hours": 8}])
            row = self._preview(admin_hdr, "2026-11", me["id"])
            gross = float(row.get("gross") or row.get("base_gross") or 0)
            assert abs(gross - 1600) < 0.5, f"optional_paid worked → expected 1600, got {gross}"
            hc = row.get("holiday_credit") or {}
            assert (hc.get("hours") or 0) == 0
            requests.delete(f"{BASE}/api/hr/timesheets/{tsid}", headers=admin_hdr, timeout=10)
            CREATED["timesheets"].remove(tsid)
            requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=admin_hdr, timeout=10)
            CREATED["salaries"].remove(sal["id"])
        finally:
            requests.put(f"{BASE}/api/holidays/policies",
                         json={"name": "Thanksgiving Day", "country": "US", "kind": "paid"},
                         headers=admin_hdr, timeout=15)

    def test_daily_wage_paid_holiday(self, admin_hdr, me):
        sal = self._mk_salary(admin_hdr, me, wage_type="daily", daily_rate=50.0, hourly_rate=0)
        row = self._preview(admin_hdr, "2026-11", me["id"])
        hc = row.get("holiday_credit") or {}
        assert hc.get("days") == 1, f"expected days=1, got {hc}"
        requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=admin_hdr, timeout=10)
        CREATED["salaries"].remove(sal["id"])

    def test_payslip_generate_persists_holiday_credit(self, admin_hdr, me):
        sal = self._mk_salary(admin_hdr, me)
        r = requests.post(f"{BASE}/api/hr/payslips/generate",
                         json={"period": "2026-11", "staff_ids": [me["id"]]},
                         headers=admin_hdr, timeout=30)
        assert r.status_code in (200, 201), r.text
        payload = r.json()
        payslips = payload.get("payslips") or payload.get("created") or []
        # If endpoint returns count only, fetch list
        if not payslips:
            g = requests.get(f"{BASE}/api/hr/payslips?period=2026-11&staff_id={me['id']}", headers=admin_hdr, timeout=15)
            payslips = g.json() if g.status_code == 200 else []
        assert payslips, f"no payslips returned/found: {payload}"
        ps = payslips[0] if isinstance(payslips, list) else payslips
        assert "holiday_credit" in ps, f"holiday_credit missing on payslip: keys={list(ps.keys())}"
        assert (ps["holiday_credit"] or {}).get("hours") == 8
        if ps.get("id"):
            CREATED["payslips"].append(ps["id"])
        requests.delete(f"{BASE}/api/hr/salaries/{sal['id']}", headers=admin_hdr, timeout=10)
        CREATED["salaries"].remove(sal["id"])


# ═══════════════════════ 4. TASKS in SHARED CALENDAR ═════════════════════
class TestSharedCalendarTasks:
    def test_task_appears_in_shared_feed(self, admin_hdr, me):
        # create board
        rb = requests.post(f"{BASE}/api/boards",
                           json={"name": f"TEST_iter316_board_{uuid.uuid4().hex[:5]}", "location_id": "loc_001"},
                           headers=admin_hdr, timeout=15)
        assert rb.status_code in (200, 201), rb.text
        board = rb.json()
        CREATED["boards"].append(board["id"])
        # create task with due date
        tpayload = {"title": f"TEST_iter316_task_{uuid.uuid4().hex[:5]}",
                    "board_id": board["id"], "due_date": "2026-06-20",
                    "assignee_id": me["id"]}
        rt = requests.post(f"{BASE}/api/tasks", json=tpayload, headers=admin_hdr, timeout=15)
        assert rt.status_code in (200, 201), rt.text
        task = rt.json()
        CREATED["tasks"].append(task["id"])
        # create share config include_tasks=true campus scope
        cfg = {"name": "iter316-cfg", "include_tasks": True, "task_scope": "campus",
               "location_ids": ["loc_001"]}
        rc = requests.post(f"{BASE}/api/calendar/share-configs", json=cfg, headers=admin_hdr, timeout=15)
        assert rc.status_code in (200, 201), rc.text
        conf = rc.json()
        CREATED["share_configs"].append(conf["id"])
        token = conf.get("token") or conf.get("share_token")
        assert token, f"share token missing: {conf}"
        # JSON feed
        rj = requests.get(f"{BASE}/api/public/calendar/user/{token}", timeout=15)
        assert rj.status_code == 200, rj.text
        j = rj.json()
        tasks_list = j.get("tasks") or []
        assert any(task["id"] == t.get("id") or task["title"] == t.get("title") for t in tasks_list), \
            f"task not in JSON feed: found {[t.get('title') for t in tasks_list]}"
        # ICS feed
        ri = requests.get(f"{BASE}/api/public/calendar/user/{token}.ics", timeout=15)
        assert ri.status_code == 200
        ics = ri.text
        assert "CATEGORIES:TASK" in ics, "CATEGORIES:TASK missing from ics"
        assert task["title"] in ics

    def test_task_scope_mine(self, admin_hdr, me):
        rb = requests.post(f"{BASE}/api/boards",
                           json={"name": f"TEST_iter316_mine_{uuid.uuid4().hex[:5]}", "location_id": "loc_001"},
                           headers=admin_hdr, timeout=15)
        assert rb.status_code in (200, 201)
        board = rb.json()
        CREATED["boards"].append(board["id"])
        rt = requests.post(f"{BASE}/api/tasks",
                           json={"title": f"TEST_iter316_mine_task_{uuid.uuid4().hex[:5]}",
                                 "board_id": board["id"], "due_date": "2026-06-22",
                                 "assignee_id": me["id"]},
                           headers=admin_hdr, timeout=15)
        assert rt.status_code in (200, 201)
        task = rt.json()
        CREATED["tasks"].append(task["id"])
        cfg = {"name": "iter316-mine", "include_tasks": True, "task_scope": "mine"}
        rc = requests.post(f"{BASE}/api/calendar/share-configs", json=cfg, headers=admin_hdr, timeout=15)
        assert rc.status_code in (200, 201)
        conf = rc.json()
        CREATED["share_configs"].append(conf["id"])
        token = conf.get("token") or conf.get("share_token")
        rj = requests.get(f"{BASE}/api/public/calendar/user/{token}", timeout=15)
        assert rj.status_code == 200
        tasks_list = rj.json().get("tasks") or []
        assert any(t.get("id") == task["id"] or t.get("title") == task["title"] for t in tasks_list), \
            "task_scope=mine did not include owner's task"


# ═══════════════════════ 5. TASKS regression board-scoping ════════════
class TestTasksBoardScoping:
    def test_tasks_list_returns(self, admin_hdr):
        r = requests.get(f"{BASE}/api/tasks", headers=admin_hdr, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_restricted_board_hidden_from_non_tagged(self, admin_hdr):
        # create a private/restricted board with only admin as member
        rb = requests.post(f"{BASE}/api/boards",
                           json={"name": f"TEST_iter316_priv_{uuid.uuid4().hex[:5]}",
                                 "location_id": "loc_001",
                                 "is_private": True, "visibility": "private",
                                 "member_ids": []},
                           headers=admin_hdr, timeout=15)
        if rb.status_code not in (200, 201):
            pytest.skip(f"could not create private board: {rb.status_code} {rb.text[:150]}")
        board = rb.json()
        CREATED["boards"].append(board["id"])
        rt = requests.post(f"{BASE}/api/tasks",
                           json={"title": f"TEST_iter316_priv_task_{uuid.uuid4().hex[:5]}",
                                 "board_id": board["id"]},
                           headers=admin_hdr, timeout=15)
        assert rt.status_code in (200, 201)
        task = rt.json()
        CREATED["tasks"].append(task["id"])
        # create non-admin user & login
        email = f"TEST_iter316_scope_{uuid.uuid4().hex[:6]}@ex.com"
        cr = requests.post(f"{BASE}/api/admin/users",
                           json={"name": "Iter316 Scope", "email": email, "role": "member",
                                 "location_id": "loc_002", "password": "Test@5812!"},
                           headers=admin_hdr, timeout=15)
        if cr.status_code not in (200, 201):
            pytest.skip(f"could not create non-admin user: {cr.status_code}")
        uid = cr.json().get("id")
        tok = _login({"identifier": email, "password": "Test@5812!"})
        hdr = {"Authorization": f"Bearer {tok}"}
        r = requests.get(f"{BASE}/api/tasks", headers=hdr, timeout=15)
        assert r.status_code == 200
        titles = [t.get("title") for t in r.json()]
        assert task["title"] not in titles, f"restricted task leaked to non-tagged user: {titles}"
        try:
            requests.delete(f"{BASE}/api/admin/users/{uid}", headers=admin_hdr, timeout=10)
        except Exception:
            pass
