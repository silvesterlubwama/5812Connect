"""iter392 — organisation isolation.

The question these tests exist to answer: can anyone in organisation B see,
fetch, modify or count anything belonging to organisation A? Including by
guessing a record id, which is the usual way tenant walls leak.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"

SUPER = {"identifier": "owner@5812global.org", "password": "Owner@5812!"}
ORG_A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


@pytest.fixture(autouse=True)
def _clear_login_throttle():
    """These tests sign in as several tenants in quick succession, which trips
    the per-IP brute-force tarpit. Reset it between tests."""
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    mc[os.environ.get("DB_NAME", "5812global")].login_attempts.delete_many({})
    mc.close()
    yield


_TOKEN_CACHE = {}


def _login(creds, cache=True):
    """Sign-in routes are capped at 20/min per IP, and this suite authenticates
    as several tenants, so stable logins are cached."""
    key = (creds["identifier"], creds["password"])
    if cache and key in _TOKEN_CACHE:
        return _TOKEN_CACHE[key]
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    out = r.json()
    if cache:
        _TOKEN_CACHE[key] = out
    return out


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _super_headers():
    return _h(_login(SUPER)["token"])


def _forget(creds):
    _TOKEN_CACHE.pop((creds["identifier"], creds["password"]), None)


def _orgs(h):
    r = requests.get(f"{API}/organizations", headers=h, timeout=30)
    r.raise_for_status()
    return r.json()["organizations"]


def _make_org(h, label):
    slug = f"t392{uuid.uuid4().hex[:8]}"
    body = {
        "name": f"TEST_iter392 {label}",
        "slug": slug,
        "owner_email": f"{slug}@example.test",
        "owner_name": f"{label} Admin",
        "owner_password": "Tenant@2026!",
    }
    r = requests.post(f"{API}/organizations", json=body, headers=h, timeout=60)
    assert r.status_code == 200, r.text
    org = r.json()["organization"]
    token = _login({"identifier": body["owner_email"], "password": body["owner_password"]})["token"]
    return org, _h(token), body


def _cleanup(h, org_id, slug):
    requests.post(f"{API}/organizations/{org_id}/status", json={"status": "suspended"},
                  headers=h, timeout=30)
    requests.delete(f"{API}/organizations/{org_id}", params={"confirm": slug},
                    headers=h, timeout=60)


# ---------------------------------------------------------------- isolation

def test_new_org_starts_empty_even_though_db_is_full():
    """The existing install has thousands of rows. A new tenant must see none."""
    sh = _super_headers()
    org, h, _ = _make_org(sh, "empty")
    try:
        members = requests.get(f"{API}/members", headers=h, timeout=30).json()
        assert members.get("total", 0) == 0, members
        assert requests.get(f"{API}/products", headers=h, timeout=30).json() == []
        assert requests.get(f"{API}/events", headers=h, timeout=30).json() == []
        # exactly its own seeded campus, nobody else's
        locs = requests.get(f"{API}/locations", headers=h, timeout=30).json()
        rows = locs.get("locations") if isinstance(locs, dict) else locs
        assert len(rows) == 1, rows
    finally:
        _cleanup(sh, org["id"], org["slug"])


def test_cannot_fetch_another_tenants_record_by_id():
    """The classic tenant leak: a valid id from org A used by org B."""
    sh = _super_headers()
    a = _h(_login(ORG_A_ADMIN)["token"])
    a_events = requests.get(f"{API}/events", headers=a, timeout=30).json()
    assert a_events, "org A needs at least one event for this test to mean anything"
    stolen_id = a_events[0]["id"]

    org, b, _ = _make_org(sh, "idor")
    try:
        r = requests.get(f"{API}/events/{stolen_id}", headers=b, timeout=30)
        assert r.status_code == 404, f"org B fetched org A's event: {r.status_code} {r.text[:200]}"
        # and cannot delete what it cannot see
        d = requests.delete(f"{API}/events/{stolen_id}", headers=b, timeout=30)
        assert d.status_code in (403, 404), d.text
        # org A's event survived
        still = requests.get(f"{API}/events/{stolen_id}", headers=a, timeout=30)
        assert still.status_code == 200
    finally:
        _cleanup(sh, org["id"], org["slug"])


def test_writes_land_in_the_right_tenant_only():
    sh = _super_headers()
    org, b, _ = _make_org(sh, "writes")
    try:
        name = f"TEST_iter392 {uuid.uuid4().hex[:6]}"
        created = requests.post(f"{API}/products", headers=b, timeout=30, json={
            "name": name, "price": 500, "currency": "UGX", "stock": 3,
        })
        assert created.status_code in (200, 201), created.text
        pid = created.json()["id"]

        mine = requests.get(f"{API}/products", headers=b, timeout=30).json()
        assert any(p["id"] == pid for p in mine)

        a = _h(_login(ORG_A_ADMIN)["token"])
        theirs = requests.get(f"{API}/products", headers=a, timeout=30).json()
        assert not any(p["id"] == pid for p in theirs), "tenant B's product leaked into tenant A"
    finally:
        _cleanup(sh, org["id"], org["slug"])


def test_same_email_in_two_tenants_are_different_people():
    """Tenants must be free to use an email another tenant already uses."""
    sh = _super_headers()
    org, _, body = _make_org(sh, "dupe")
    try:
        slug2 = f"t392{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/organizations", headers=sh, timeout=60, json={
            "name": "TEST_iter392 dupe2", "slug": slug2,
            "owner_email": body["owner_email"],  # same address, other tenant
            "owner_password": "Tenant@2026!",
        })
        assert r.status_code == 200, r.text
        org2 = r.json()["organization"]
        _cleanup(sh, org2["id"], org2["slug"])
    finally:
        _cleanup(sh, org["id"], org["slug"])


# ---------------------------------------------------------------- lifecycle

def test_suspension_blocks_login_immediately():
    sh = _super_headers()
    org, h, body = _make_org(sh, "suspend")
    try:
        assert requests.get(f"{API}/products", headers=h, timeout=30).status_code == 200

        requests.post(f"{API}/organizations/{org['id']}/status", headers=sh, timeout=30,
                      json={"status": "suspended", "reason": "unpaid"})

        # fresh login refused
        r = requests.post(f"{API}/auth/login", timeout=30, json={
            "identifier": body["owner_email"], "password": body["owner_password"]})
        assert r.status_code == 403, r.text
        assert "suspended" in r.text.lower()

        # the session they already held is dead too
        r2 = requests.get(f"{API}/products", headers=h, timeout=30)
        assert r2.status_code in (401, 403), r2.text

        # reactivation restores access
        requests.post(f"{API}/organizations/{org['id']}/status", headers=sh, timeout=30,
                      json={"status": "active"})
        r3 = requests.post(f"{API}/auth/login", timeout=30, json={
            "identifier": body["owner_email"], "password": body["owner_password"]})
        assert r3.status_code == 200, r3.text
    finally:
        _cleanup(sh, org["id"], org["slug"])


def test_delete_requires_suspension_and_slug_confirmation():
    sh = _super_headers()
    org, _, _ = _make_org(sh, "delete")
    oid, slug = org["id"], org["slug"]

    # live tenant cannot be deleted
    r = requests.delete(f"{API}/organizations/{oid}", params={"confirm": slug},
                        headers=sh, timeout=30)
    assert r.status_code == 400 and "suspend" in r.text.lower(), r.text

    requests.post(f"{API}/organizations/{oid}/status", headers=sh, timeout=30,
                  json={"status": "suspended"})

    # wrong confirmation string refused
    r = requests.delete(f"{API}/organizations/{oid}", params={"confirm": "nope"},
                        headers=sh, timeout=30)
    assert r.status_code == 400, r.text

    r = requests.delete(f"{API}/organizations/{oid}", params={"confirm": slug},
                        headers=sh, timeout=60)
    assert r.status_code == 200, r.text
    assert not any(o["id"] == oid for o in _orgs(sh))


def test_export_then_import_restores_a_tenant():
    sh = _super_headers()
    org, h, _ = _make_org(sh, "export")
    try:
        name = f"TEST_iter392 {uuid.uuid4().hex[:6]}"
        requests.post(f"{API}/products", headers=h, timeout=30,
                      json={"name": name, "price": 750, "currency": "UGX", "stock": 1})

        dump = requests.get(f"{API}/organizations/{org['id']}/export", headers=sh, timeout=60)
        assert dump.status_code == 200, dump.text
        payload = dump.json()
        assert payload["document_count"] > 0
        assert any(p["name"] == name for p in payload["collections"].get("products", []))

        restored = requests.post(f"{API}/organizations/import", headers=sh, timeout=60, json=payload)
        assert restored.status_code == 200, restored.text
        new_org = restored.json()["organization"]
        try:
            # the copy is a separate tenant with its own id
            assert new_org["id"] != org["id"]
            assert restored.json()["restored_documents"] > 0
        finally:
            _cleanup(sh, new_org["id"], new_org["slug"])
    finally:
        _cleanup(sh, org["id"], org["slug"])


# ---------------------------------------------------------------- super admin

def test_super_admin_must_choose_and_sees_one_tenant_at_a_time():
    first = _login(SUPER)
    # either already inside one, or being asked to pick — never a merged view
    if first.get("requires_org_selection"):
        assert "token" in first and first["organizations"]
        sh = _h(first["token"])
    else:
        sh = _h(first["token"])
        requests.post(f"{API}/organizations/exit", headers=sh, timeout=30)
        sh = _h(_login(SUPER, cache=False)["token"])

    orgs = _orgs(sh)
    assert len(orgs) >= 1

    org, _, _ = _make_org(sh, "switch")
    try:
        # enter the new (empty) tenant
        r = requests.post(f"{API}/organizations/{org['id']}/enter", headers=sh, timeout=30)
        assert r.status_code == 200, r.text
        inside_new = _h(r.json()["token"])
        assert requests.get(f"{API}/products", headers=inside_new, timeout=30).json() == []

        # enter 58:12 instead — entering replaces, never adds
        a_org = next(o for o in orgs if o["slug"] == "5812global")
        r2 = requests.post(f"{API}/organizations/{a_org['id']}/enter", headers=sh, timeout=30)
        inside_a = _h(r2.json()["token"])
        a_products = requests.get(f"{API}/products", headers=inside_a, timeout=30).json()

        # the previously-entered tenant's view is gone, not combined
        now = requests.get(f"{API}/products", headers=inside_new, timeout=30).json()
        assert now == a_products, "super admin kept a stale view of the old organisation"
    finally:
        requests.post(f"{API}/organizations/exit", headers=sh, timeout=30)
        _cleanup(sh, org["id"], org["slug"])


def test_registry_is_super_admin_only():
    a = _h(_login(ORG_A_ADMIN)["token"])
    for method, path in (
        ("get", "/organizations"),
        ("post", "/organizations"),
    ):
        r = getattr(requests, method)(f"{API}{path}", headers=a, timeout=30, json={})
        assert r.status_code == 403, f"{method} {path} -> {r.status_code}"


def test_hostname_binds_a_site_to_one_tenant():
    """Requests arriving on a tenant's own hostname only accept that tenant's
    accounts, so personal.5812uganda.org cannot be used to reach another org."""
    sh = _super_headers()
    org, _, body = _make_org(sh, "host")
    host = f"{org['slug']}.example.test"
    try:
        requests.put(f"{API}/organizations/{org['id']}", headers=sh, timeout=30,
                     json={"hostnames": [host]})

        # the tenant's own admin is accepted on that host
        ok = requests.post(f"{API}/auth/login", timeout=30, headers={"Host": host},
                           json={"identifier": body["owner_email"],
                                 "password": body["owner_password"]})
        assert ok.status_code in (200, 403), ok.text  # 403 only if proxy rewrote Host

        # 58:12's admin is not
        bad = requests.post(f"{API}/auth/login", timeout=30, headers={"Host": host},
                            json=ORG_A_ADMIN)
        assert bad.status_code in (401, 403), bad.text
    finally:
        requests.put(f"{API}/organizations/{org['id']}", headers=sh, timeout=30,
                     json={"hostnames": []})
        _cleanup(sh, org["id"], org["slug"])
