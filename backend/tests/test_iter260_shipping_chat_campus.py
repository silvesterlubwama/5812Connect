"""iter 260 — Shipping auto-pack + packing-unit stacking, chat ghost-user
filters, campus switcher RBAC, tasks directory, and basic regressions."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"
SHIPMENT_ID = "sh_1091d195ee"
PREFIX = "Iter260_"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    if not e or not pw:
        pytest.skip("no creds parsed")
    return {"identifier": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="session")
def admin(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    body = r.json()
    token = body.get("access_token") or body.get("token")
    assert token, f"no token in login response: {list(body.keys())}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    s.me = body.get("user") or {}
    return s


@pytest.fixture(scope="module")
def created(admin):
    """Track created ids for teardown."""
    reg = {"items": [], "units": [], "users": []}
    yield reg
    for iid in reg["items"]:
        admin.delete(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}", timeout=30)
    for uid in reg["units"]:
        admin.delete(f"{API}/shipments/{SHIPMENT_ID}/packing-units/{uid}", timeout=30)
    for uid in reg["users"]:
        admin.delete(f"{API}/admin/users/{uid}", timeout=30)


def _get_shipment(admin):
    r = admin.get(f"{API}/shipments/{SHIPMENT_ID}", timeout=45)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find_item(ship, item_id):
    return next((i for i in (ship.get("items") or []) if i["id"] == item_id), None)


def _find_unit(ship, unit_id):
    return next((u for u in (ship.get("packing_units") or []) if u["id"] == unit_id), None)


@pytest.fixture(scope="module")
def box(admin, created):
    r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/packing-units",
                   json={"type": "box", "name": f"{PREFIX}Box A", "preset_key": "medium_box"}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    u = r.json()
    created["units"].append(u["id"])
    return u


# ---------- SHIPPING: auto-pack on create ----------
class TestAutoPackCreate:
    def test_create_item_with_packing_unit_snaps_to_origin(self, admin, created, box):
        payload = {"name": f"{PREFIX}Snap Item", "category": "household",
                   "qty_needed": 1, "qty_acquired": 1,
                   "packing_unit_id": box["id"], "x_cm": 99, "y_cm": 88, "z_cm": 77}
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/items", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        it = r.json()
        created["items"].append(it["id"])
        assert it["packing_unit_id"] == box["id"]
        assert (it["x_cm"], it["y_cm"], it["z_cm"]) == (0.0, 0.0, 0.0)
        # verify persisted
        got = _find_item(_get_shipment(admin), it["id"])
        assert got is not None
        assert (got["x_cm"], got["y_cm"], got["z_cm"]) == (0.0, 0.0, 0.0)

    def test_create_loose_item_keeps_coords(self, admin, created):
        payload = {"name": f"{PREFIX}Loose Item", "qty_acquired": 1,
                   "x_cm": 12, "y_cm": 13, "z_cm": 14}
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/items", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        it = r.json()
        created["items"].append(it["id"])
        assert (it["x_cm"], it["y_cm"], it["z_cm"]) == (12.0, 13.0, 14.0)


# ---------- SHIPPING: auto-pack on update ----------
class TestAutoPackUpdate:
    def test_link_to_box_resets_coords_and_clears_floor(self, admin, created, box):
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/items",
                       json={"name": f"{PREFIX}Floating Item", "qty_acquired": 1}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        iid = r.json()["id"]
        created["items"].append(iid)
        # place on the container floor
        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}",
                      json={"floor_x_cm": 300, "floor_y_cm": 120, "x_cm": 5, "y_cm": 6, "z_cm": 7}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        got = _find_item(_get_shipment(admin), iid)
        assert got["floor_x_cm"] == 300 and got["floor_y_cm"] == 120
        assert got["x_cm"] == 5
        # now link to the box
        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}",
                      json={"packing_unit_id": box["id"]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        got = _find_item(_get_shipment(admin), iid)
        assert got["packing_unit_id"] == box["id"]
        assert (got["x_cm"], got["y_cm"], got["z_cm"]) == (0.0, 0.0, 0.0), got
        assert got["floor_x_cm"] is None and got["floor_y_cm"] is None, got

    def test_unlink_does_not_wipe_coords(self, admin, created, box):
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/items",
                       json={"name": f"{PREFIX}Unlink Item", "qty_acquired": 1,
                             "packing_unit_id": box["id"]}, timeout=30)
        iid = r.json()["id"]
        created["items"].append(iid)
        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}",
                      json={"packing_unit_id": None, "x_cm": 20}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        got = _find_item(_get_shipment(admin), iid)
        assert got["packing_unit_id"] in (None, "")
        assert got["x_cm"] == 20


# ---------- SHIPPING: stacking ----------
class TestPackingUnitStacking:
    def test_stack_and_unstack(self, admin, created, box):
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/packing-units",
                       json={"type": "box", "name": f"{PREFIX}Box Child", "preset_key": "small_box"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        child = r.json()
        created["units"].append(child["id"])
        assert child.get("parent_id") is None

        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/packing-units/{child['id']}",
                      json={"parent_id": box["id"]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        u = _find_unit(_get_shipment(admin), child["id"])
        assert u["parent_id"] == box["id"], u

        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/packing-units/{child['id']}",
                      json={"parent_id": None}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        u = _find_unit(_get_shipment(admin), child["id"])
        assert u["parent_id"] is None, u

    def test_stack_unknown_unit_404(self, admin):
        r = admin.put(f"{API}/shipments/{SHIPMENT_ID}/packing-units/pku_doesnotexist",
                      json={"parent_id": None}, timeout=30)
        assert r.status_code == 404, r.status_code


# ---------- CHAT ----------
STAFF_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
               "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer",
               "Security Contractor"}


class TestChatUsers:
    def test_chat_users_shape(self, admin):
        r = admin.get(f"{API}/chat/users", timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list) and rows
        me = admin.me.get("id")
        for u in rows:
            assert u.get("id"), u
            assert (u.get("name") or "").strip(), u
            assert u.get("role") in STAFF_ROLES, u
            assert u["id"] != me, "caller must not appear in chat users"

    def test_chat_users_excludes_non_staff_and_inactive(self, admin, created):
        # inactive staff user
        r = admin.post(f"{API}/admin/users", json={
            "name": f"{PREFIX}Inactive Staff", "email": f"{PREFIX.lower()}inactive@test.local",
            "role": "Staff", "status": "inactive"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        inactive_id = (r.json().get("user") or r.json()).get("id") or r.json().get("id")
        created["users"].append(inactive_id)
        # non-staff role user
        r = admin.post(f"{API}/admin/users", json={
            "name": f"{PREFIX}Member Guy", "email": f"{PREFIX.lower()}member@test.local",
            "role": "Member", "status": "active"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        member_id = (r.json().get("user") or r.json()).get("id") or r.json().get("id")
        created["users"].append(member_id)

        ids = {u["id"] for u in admin.get(f"{API}/chat/users", timeout=30).json()}
        assert inactive_id not in ids, "inactive user leaked into /chat/users"
        assert member_id not in ids, "non-staff role leaked into /chat/users"


class TestChatGhostConversations:
    def test_direct_dm_disappears_when_counterparty_deleted(self, admin, created):
        r = admin.post(f"{API}/admin/users", json={
            "name": f"{PREFIX}Ghost Staff", "email": f"{PREFIX.lower()}ghost@test.local",
            "role": "Staff", "status": "active"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        body = r.json()
        ghost_id = (body.get("user") or body).get("id") or body.get("id")
        assert ghost_id

        me = admin.me.get("id")
        r = admin.post(f"{API}/chat/conversations",
                       json={"type": "direct", "participants": [me, ghost_id]}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        conv_id = r.json().get("id")
        assert conv_id

        convs = admin.get(f"{API}/chat/conversations", timeout=30).json()
        assert any(c.get("id") == conv_id for c in convs), "new DM not listed"

        # group conversation with the ghost too — must survive the delete
        r = admin.post(f"{API}/chat/conversations",
                       json={"type": "group", "name": f"{PREFIX}Group",
                             "participants": [me, ghost_id]}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        group_id = r.json().get("id")

        d = admin.delete(f"{API}/admin/users/{ghost_id}", timeout=30)
        assert d.status_code == 200, d.text[:300]

        convs = admin.get(f"{API}/chat/conversations", timeout=30).json()
        ids = {c.get("id") for c in convs}
        assert conv_id not in ids, "ghost direct DM still listed after user deletion"
        if group_id:
            assert group_id in ids, "group conversation wrongly hidden"
            admin.delete(f"{API}/chat/conversations/{group_id}", timeout=30)
        admin.delete(f"{API}/chat/conversations/{conv_id}", timeout=30)


# ---------- CAMPUS SWITCHER ----------
@pytest.fixture(scope="module")
def director(admin, created):
    """Multi-campus Director (2 assigned sibling campuses) + login session."""
    locs = admin.get(f"{API}/locations", timeout=30)
    assert locs.status_code == 200, locs.text[:300]
    rows = locs.json()
    siblings = [l for l in rows if l.get("parent_id") == "loc_001" and not l.get("is_restricted")]
    restricted = next((l for l in rows if l.get("is_restricted")), None)
    if len(siblings) < 3:
        pytest.skip(f"need >=3 non-restricted siblings under loc_001, got {len(siblings)}")
    assigned = [siblings[0]["id"], siblings[1]["id"]]
    other = siblings[2]["id"]
    email = f"{PREFIX.lower()}director@test.local"
    r = admin.post(f"{API}/admin/users", json={
        "name": f"{PREFIX}Director", "email": email, "role": "Director",
        "status": "active", "password": "Test@5812!",
        "location_id": assigned[0], "location_ids": assigned}, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    body = r.json()
    uid = (body.get("user") or body).get("id") or body.get("id")
    created["users"].append(uid)

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    lr = s.post(f"{API}/auth/login", json={"identifier": email, "password": "Test@5812!"}, timeout=30)
    assert lr.status_code == 200, lr.text[:300]
    tok = lr.json().get("access_token") or lr.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return {"session": s, "assigned": assigned, "other": other,
            "restricted": restricted,
            "location_ids": set((lr.json().get("user") or {}).get("location_ids") or [])}


class TestCampusSwitcher:
    def test_assigned_campuses_allowed(self, director):
        s = director["session"]
        for cid in director["assigned"]:
            rr = s.put(f"{API}/user/active-campus", json={"campus_id": cid}, timeout=30)
            assert rr.status_code == 200, f"assigned campus {cid} rejected: {rr.status_code} {rr.text[:200]}"
            assert rr.json().get("active_campus_id") == cid

    def test_unassigned_sibling_campus_forbidden(self, director):
        s, other = director["session"], director["other"]
        assert other not in director["location_ids"], "test setup: 'other' campus was auto-assigned"
        rr = s.put(f"{API}/user/active-campus", json={"campus_id": other}, timeout=30)
        assert rr.status_code == 403, (
            f"UNASSIGNED sibling campus {other} accepted for a Director assigned only to "
            f"{director['assigned']}: {rr.status_code} {rr.text[:200]}")

    def test_restricted_campus_forbidden(self, director):
        r = director["restricted"]
        if not r:
            pytest.skip("no restricted location in db")
        rr = director["session"].put(f"{API}/user/active-campus", json={"campus_id": r["id"]}, timeout=30)
        assert rr.status_code == 403, f"restricted campus accepted: {rr.status_code} {rr.text[:200]}"

    def test_validation_codes(self, director):
        s = director["session"]
        assert s.put(f"{API}/user/active-campus", json={"campus_id": "loc_nope"}, timeout=30).status_code == 404
        assert s.put(f"{API}/user/active-campus", json={}, timeout=30).status_code == 400
        assert s.put(f"{API}/user/active-campus/clear", timeout=30).status_code == 200


# ---------- TASKS DIRECTORY ----------
DIR_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
             "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer"}


class TestUserDirectory:
    def test_directory_staff_only_no_password(self, admin):
        r = admin.get(f"{API}/admin/users/directory", timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert isinstance(rows, list) and rows
        for u in rows:
            assert u.get("role") in DIR_ROLES, u
            assert "password_hash" not in u
            assert "_id" not in u
            assert u.get("id")

    def test_directory_search(self, admin):
        r = admin.get(f"{API}/admin/users/directory", params={"search": "adm"}, timeout=30)
        assert r.status_code == 200
        for u in r.json():
            hay = f"{u.get('name','')} {u.get('email','')}".lower()
            assert "adm" in hay, u


# ---------- REGRESSIONS ----------
class TestRegressions:
    @pytest.mark.parametrize("path", ["/events", "/tasks", "/shipments"])
    def test_list_endpoints_return_arrays(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=60)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list), f"{path} did not return an array"

    def test_read_does_not_mutate_prelinked_item_coords(self, admin, created, box):
        """Legacy items linked to a box with non-zero coords must not be
        rewritten just because the shipment was read."""
        r = admin.post(f"{API}/shipments/{SHIPMENT_ID}/items",
                       json={"name": f"{PREFIX}Legacy Item", "qty_acquired": 1}, timeout=30)
        iid = r.json()["id"]
        created["items"].append(iid)
        # emulate legacy state: linked + non-zero coords, set in one PUT where
        # coords come AFTER the link (server-side snap applies), so set them
        # in a second PUT without packing_unit_id in the payload.
        admin.put(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}",
                  json={"packing_unit_id": box["id"]}, timeout=30)
        admin.put(f"{API}/shipments/{SHIPMENT_ID}/items/{iid}",
                  json={"x_cm": 31, "y_cm": 32, "z_cm": 33}, timeout=30)
        first = _find_item(_get_shipment(admin), iid)
        assert (first["x_cm"], first["y_cm"], first["z_cm"]) == (31.0, 32.0, 33.0)
        second = _find_item(_get_shipment(admin), iid)
        assert (second["x_cm"], second["y_cm"], second["z_cm"]) == (31.0, 32.0, 33.0)

    def test_shipment_returns_packing_units_with_parent_id(self, admin, created, box):
        """Units created via the API must expose parent_id (stack tower reads it)."""
        ship = _get_shipment(admin)
        units = ship.get("packing_units") or []
        assert units, "no packing units returned"
        mine = [u for u in units if u["id"] in created["units"]]
        assert mine, "test-created units missing from GET"
        assert all("parent_id" in u for u in mine), mine
        legacy_missing = [u["id"] for u in units if "parent_id" not in u]
        assert not legacy_missing, f"legacy units without parent_id (data issue): {legacy_missing}"
        assert "_id" not in ship
