"""iter393 — adversarial tenant-isolation probes (beyond test_iter392).

Runs against the PUBLIC URL. Canary rows for org A (58:12 Global) are inserted
directly into Mongo with TEST393 ids and removed afterwards, so no real data is
ever put at risk. Every test org created here is suspended + deleted on teardown.
"""
import io
import json
import sys
import tarfile
import uuid

import bcrypt
import pytest
import requests

sys.path.insert(0, "/app/backend/tests")
from tenant_probe_common import (  # noqa: E402
    API, A_ORG, A_ADMIN, SUPER, LUB_ADMIN, clear_throttle, destroy_org, h, login, make_org, mdb,
)

INTERNAL = "http://localhost:8001/api"  # only used where a custom Host header is required
LUB_HOST = "new.lubwamas.org"


def _rows(resp):
    j = resp.json()
    if isinstance(j, list):
        return j
    for k in ("items", "members", "products", "events", "data", "results", "locations", "tasks", "payslips"):
        if isinstance(j.get(k), list):
            return j[k]
    for v in j.values():
        if isinstance(v, list):
            return v
    return []


@pytest.fixture(scope="module")
def org_b():
    org, hb, body = make_org("ProbeB")
    yield org, hb, body
    destroy_org(org)


@pytest.fixture(scope="module")
def a_headers():
    t = login(A_ADMIN)
    assert t.get("token"), t
    return h(t["token"])


# ---- 1. fresh tenant starts empty ----
def test_new_org_is_empty(org_b):
    _, hb, _ = org_b
    for path in ("/members", "/products", "/events"):
        r = requests.get(f"{API}{path}", headers=hb, timeout=30)
        assert r.status_code == 200, (path, r.text[:200])
        assert len(_rows(r)) == 0, (path, _rows(r)[:2])
    r = requests.get(f"{API}/locations", headers=hb, timeout=30)
    assert r.status_code == 200 and len(_rows(r)) == 1, r.text[:300]


# ---- 2. cross-tenant IDOR by id on many endpoints (canaries in org A) ----
IDOR = [
    ("members", "/members/{id}", ("get", "put", "delete")),
    ("events", "/events/{id}", ("get", "put", "delete")),
    ("tasks", "/tasks/{id}", ("put", "delete")),
    ("products", "/products/{id}", ("put", "delete")),
    ("invoices", "/invoices/{id}", ("get", "put", "delete")),
    ("hr_payslips", "/hr/payslips/{id}", ("put", "delete")),
    ("hr_payslips", "/hr/payslips/{id}/pdf", ("get",)),
    ("social_cases", "/social-work/cases/{id}", ("get", "put", "delete")),
    ("bookings", "/bookings/{id}", ("put", "delete")),
    ("files", "/documents/{id}", ("delete",)),
    ("files", "/documents/{id}/file", ("get",)),
    ("boards", "/boards/{id}", ("get", "put", "delete")),
    ("families", "/families/{id}", ("get", "put", "delete")),
    ("venues", "/venues/{id}", ("put", "delete")),
    ("hr_employee_expenses", "/hr/expenses/{id}", ("put", "delete")),
    ("locations", "/locations/{id}", ("put", "delete")),
    ("conversations", "/chat/conversations/{id}", ("delete",)),
]


@pytest.mark.parametrize("coll,path,methods", IDOR, ids=[f"{c}:{p}" for c, p, _ in IDOR])
def test_idor_cannot_touch_other_tenant(org_b, coll, path, methods):
    _, hb, _ = org_b
    d = mdb()
    cid = f"TEST393-{uuid.uuid4()}"
    canary = {"id": cid, "organization_id": A_ORG, "name": "TEST_canary", "title": "TEST_canary",
              "status": "active", "member_id": cid, "participants": [], "deleted": False}
    d[coll].insert_one(dict(canary))
    try:
        bad = []
        for m in methods:
            kw = {"json": {"name": "HACKED", "title": "HACKED", "status": "cancelled"}} if m == "put" else {}
            r = getattr(requests, m)(f"{API}{path.format(id=cid)}", headers=hb, timeout=30, **kw)
            if "TEST_canary" in r.text or (m == "get" and r.status_code < 400):
                bad.append((m, r.status_code, r.text[:150]))
            elif r.status_code < 400:
                # canary integrity is asserted below; a 2xx here is a misleading "success" (should be 404)
                print(f"SOFT: {m.upper()} {path} on foreign id -> {r.status_code} {r.text[:80]}")
        after = d[coll].find_one({"id": cid})
        assert after is not None, "canary in org A was DELETED by org B"
        assert after.get("name") == "TEST_canary" and after.get("title") == "TEST_canary", f"canary modified: {after}"
        assert after.get("organization_id") == A_ORG
        assert not bad, bad
    finally:
        d[coll].delete_many({"id": cid})


# ---- 3. a non-super-admin cannot escalate by sending organization_id ----
def test_organization_id_in_body_and_query_is_ignored(org_b):
    org, hb, _ = org_b
    d = mdb()
    r = requests.post(f"{API}/members", json={"name": "TEST_iter393 esc", "organization_id": A_ORG}, headers=hb, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    mid = (r.json().get("member") or r.json()).get("id")
    doc = d.members.find_one({"id": mid})
    assert doc["organization_id"] == org["id"], "body organization_id was honoured on create"
    r = requests.put(f"{API}/members/{mid}", json={"name": "TEST_iter393 esc2", "organization_id": A_ORG}, headers=hb, timeout=30)
    assert r.status_code == 200, r.text[:300]
    doc = d.members.find_one({"id": mid})
    assert doc["organization_id"] == org["id"] and doc["name"] == "TEST_iter393 esc2"
    for params in ({"organization_id": A_ORG}, {"org": "5812global"}, {"location_id": "all"}):
        r = requests.get(f"{API}/members", params=params, headers={**hb, "X-Organization-Id": A_ORG}, timeout=30)
        assert r.status_code == 200
        ids = {x.get("id") for x in _rows(r)}
        assert ids <= {mid}, f"widened scope with {params}: {len(ids)} rows"


def test_b_records_never_appear_in_a(org_b, a_headers):
    _, hb, _ = org_b
    name = f"TEST_iter393 prodB {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/products", json={"name": name, "price": 1000}, headers=hb, timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    ra = requests.get(f"{API}/products", headers=a_headers, timeout=60)
    assert ra.status_code == 200
    assert name not in ra.text
    rb = requests.get(f"{API}/products", headers=hb, timeout=30)
    assert name in rb.text and len(_rows(rb)) == 1


# ---- 4. per-tenant on-disk backups and backup import ----
def test_backup_snapshots_not_visible_to_other_tenant(org_b):
    _, hb, _ = org_b
    r = requests.get(f"{API}/admin/backup/snapshots", headers=hb, timeout=30)
    files = r.json() if r.status_code == 200 else []
    assert r.status_code == 403 or files == [], f"org B admin sees {len(files)} on-disk snapshots of other tenants, e.g. {files[:2]}"


def test_backup_import_replace_does_not_drop_other_tenants(org_b):
    org, hb, body = org_b
    d = mdb()
    coll = "test_iter393_canary"
    d[coll].insert_many([{"id": f"TEST393-a-{i}", "organization_id": A_ORG} for i in range(3)])
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("manifest.json", json.dumps({"version": 1}).encode()),
                           (f"collections/{coll}.jsonl", json.dumps({"id": "TEST393-b-1"}).encode() + b"\n")):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
    try:
        r = requests.post(f"{API}/admin/backup/import", headers=hb, timeout=120,
                          files={"file": ("b.tar.gz", buf.getvalue(), "application/gzip")},
                          data={"mode": "replace", "admin_password": body["owner_password"], "dry_run": "false"})
        print("import status", r.status_code, r.text[:200])
        left = d[coll].count_documents({"organization_id": A_ORG})
        assert left == 3, f"org B backup import (replace) dropped org A rows: {left}/3 remain"
    finally:
        d[coll].drop()


# ---- 5. routers with no auth run in the DEFAULT tenant regardless of caller ----
def test_calling_router_requires_auth_and_is_scoped(org_b):
    _, hb, _ = org_b
    anon = requests.get(f"{API}/calling/pbx-configs", timeout=30)
    rb = requests.get(f"{API}/calling/pbx-configs", headers=hb, timeout=30)
    leaked = A_ORG in rb.text
    assert anon.status_code == 401 and not leaked, f"anon={anon.status_code}; org B sees org A PBX configs={leaked}"


def test_security_contractor_restriction_holds_in_non_default_org(org_b):
    org, _, _ = org_b
    d = mdb()
    email = f"t393sc{uuid.uuid4().hex[:6]}@example.test"
    uid = str(uuid.uuid4())
    d.users.insert_one({"id": uid, "email": email, "name": "TEST393 Contractor", "role": "Security Contractor",
                        "status": "active", "organization_id": org["id"],
                        "password_hash": bcrypt.hashpw(b"Contract@2026", bcrypt.gensalt()).decode()})
    try:
        t = login({"identifier": email, "password": "Contract@2026"}, cache=False)
        assert t.get("token"), t
        r = requests.get(f"{API}/members", headers=h(t["token"]), timeout=30)
        assert r.status_code == 403, f"contractor in non-default org reached /members: {r.status_code}"
    finally:
        d.users.delete_one({"id": uid})


# ---- 6. same email in two tenants on the shared URL ----
def test_same_email_two_tenants_both_can_sign_in(org_b):
    _, _, body = org_b
    s = login(SUPER)
    slug = f"t393{uuid.uuid4().hex[:8]}"
    rc = requests.post(f"{API}/organizations", headers=h(s["token"]), timeout=60, json={
        "name": "TEST_iter393 Twin", "slug": slug, "owner_email": body["owner_email"],
        "owner_name": "Twin", "owner_password": "Twin@2026!x"})
    assert rc.status_code == 200, rc.text
    org_c = rc.json()["organization"]
    try:
        b = login({"identifier": body["owner_email"], "password": body["owner_password"]}, cache=False)
        c = login({"identifier": body["owner_email"], "password": "Twin@2026!x"}, cache=False)
        assert b.get("token"), b
        assert c.get("token"), f"second tenant's same-email user cannot sign in on shared URL: {c}"
    finally:
        destroy_org(org_c)


# ---- 7. hostname binding (needs custom Host header -> internal port) ----
def test_hostname_login_rules():
    clear_throttle()
    d = mdb()
    before = d.users.find_one({"email": SUPER["identifier"]}, {"active_organization_id": 1})["active_organization_id"]
    try:
        ra = requests.post(f"{INTERNAL}/auth/login", json=A_ADMIN, headers={"Host": LUB_HOST}, timeout=30)
        assert ra.status_code in (401, 403), f"58:12 admin signed in on Lubwamas host: {ra.status_code}"
        rl = requests.post(f"{INTERNAL}/auth/login", json=LUB_ADMIN, headers={"Host": LUB_HOST}, timeout=30)
        assert rl.status_code == 200, rl.text[:200]
        rs = requests.post(f"{INTERNAL}/auth/login", json=SUPER, headers={"Host": LUB_HOST}, timeout=30)
        assert rs.status_code == 200, f"super admin cannot sign in via an organisation hostname: {rs.status_code} {rs.text[:150]}"
    finally:
        d.users.update_one({"email": SUPER["identifier"]}, {"$set": {"active_organization_id": before}})


# ---- 8. super admin picker / switching ----
def test_super_admin_picker_and_switch_replaces(org_b, a_headers):
    org, _, _ = org_b
    d = mdb()
    before = d.users.find_one({"email": SUPER["identifier"]})["active_organization_id"]
    d.users.update_one({"email": SUPER["identifier"]}, {"$set": {"active_organization_id": None}})
    try:
        s = login(SUPER, cache=False)
        assert s.get("requires_org_selection") is True and s.get("token"), s
        hs = h(s["token"])
        r = requests.get(f"{API}/members", headers=hs, timeout=30)
        assert r.status_code == 403 and "not attached" in r.text.lower(), r.text[:200]
        assert requests.get(f"{API}/organizations", headers=hs, timeout=30).status_code == 200
        eb = requests.post(f"{API}/organizations/{org['id']}/enter", headers=hs, timeout=30).json()
        hb_tok = h(eb["token"])
        nb = len(_rows(requests.get(f"{API}/members", headers=hb_tok, timeout=30)))
        ea = requests.post(f"{API}/organizations/{A_ORG}/enter", headers=hs, timeout=30)
        assert ea.status_code == 200
        r_old = requests.get(f"{API}/members", headers=hb_tok, timeout=60)
        assert r_old.status_code == 200
        txt = r_old.text
        assert "TEST_iter393 esc" not in txt and len(_rows(r_old)) > nb, "old token still sees org B / merged view"
    finally:
        d.users.update_one({"email": SUPER["identifier"]}, {"$set": {"active_organization_id": before}})


def test_registry_forbidden_for_org_admin(a_headers, org_b):
    org, _, _ = org_b
    for m, p in (("get", "/organizations"), ("post", "/organizations"), ("get", f"/organizations/{org['id']}/export"),
                 ("post", "/organizations/import"), ("post", f"/organizations/{org['id']}/status"),
                 ("post", f"/organizations/{org['id']}/enter"), ("delete", f"/organizations/{org['id']}")):
        r = getattr(requests, m)(f"{API}{p}", headers=a_headers, json={}, timeout=30)
        assert r.status_code == 403, (m, p, r.status_code)


# ---- 9. lifecycle: suspend / reactivate / delete / export / import ----
def test_lifecycle_suspend_export_import_delete():
    org, hc, body = make_org("Life")
    s = h(login(SUPER)["token"])
    d = mdb()
    try:
        requests.post(f"{API}/members", json={"name": "TEST_iter393 life"}, headers=hc, timeout=30)
        # delete while active refused
        r = requests.delete(f"{API}/organizations/{org['id']}", params={"confirm": org["slug"]}, headers=s, timeout=30)
        assert r.status_code == 400
        # export / import
        ex = requests.get(f"{API}/organizations/{org['id']}/export", headers=s, timeout=60).json()
        assert "TEST_iter393 life" in json.dumps(ex["collections"].get("members", []))
        im = requests.post(f"{API}/organizations/import", json=ex, headers=s, timeout=120)
        assert im.status_code == 200, im.text[:200]
        new = im.json()["organization"]
        assert new["id"] != org["id"]
        assert d.members.count_documents({"organization_id": new["id"], "name": "TEST_iter393 life"}) == 1
        assert d.members.count_documents({"organization_id": org["id"], "name": "TEST_iter393 life"}) == 1
        destroy_org(new)
        # suspend kills live session and blocks login
        requests.post(f"{API}/organizations/{org['id']}/status", json={"status": "suspended"}, headers=s, timeout=30)
        assert requests.get(f"{API}/members", headers=hc, timeout=30).status_code in (401, 403)
        rl = login({"identifier": body["owner_email"], "password": body["owner_password"]}, cache=False)
        assert rl["status"] == 403 and "suspend" in json.dumps(rl).lower(), rl
        requests.post(f"{API}/organizations/{org['id']}/status", json={"status": "active"}, headers=s, timeout=30)
        rl = login({"identifier": body["owner_email"], "password": body["owner_password"]}, cache=False)
        assert rl.get("token"), rl
        # delete after suspend with wrong then right slug
        requests.post(f"{API}/organizations/{org['id']}/status", json={"status": "suspended"}, headers=s, timeout=30)
        assert requests.delete(f"{API}/organizations/{org['id']}", params={"confirm": "nope"}, headers=s, timeout=30).status_code == 400
        assert requests.delete(f"{API}/organizations/{org['id']}", params={"confirm": org["slug"]}, headers=s, timeout=120).status_code == 200
        left = sum(d[c].count_documents({"organization_id": org["id"]}) for c in d.list_collection_names())
        assert left == 0
    finally:
        destroy_org(org)


# ---- 10. regression for 58:12 Global + public pages ----
@pytest.mark.parametrize("path", ["/members", "/locations", "/events", "/products", "/tasks", "/reports/summary",
                                  "/hr/payslips", "/dashboard/stats", "/auth/me"])
def test_regression_default_org(a_headers, path):
    r = requests.get(f"{API}{path}", headers=a_headers, timeout=60)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    if path in ("/members", "/locations", "/events"):  # products collection is empty platform-wide (pre-existing)
        assert len(_rows(r)) > 0, path
    if path == "/locations":
        names = {x.get("name") for x in _rows(r)}
        assert {"58:12 Uganda", "58:12 Shelter", "Zimba Farm"} <= names, names


@pytest.mark.parametrize("path", ["/public/events", "/public/products"])
def test_public_pages(path):
    r = requests.get(f"{API}{path}", timeout=30)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])


# ---- 11. an org admin must not be able to mint a platform super_admin ----
@pytest.mark.parametrize("role", ["super_admin", "Super_Admin", "SUPER_ADMIN"])
def test_org_admin_cannot_grant_super_admin(role):
    org, hb, body = make_org("Esc")
    d = mdb()
    try:
        uid = requests.get(f"{API}/auth/me", headers=hb, timeout=30).json().get("id")
        r = requests.put(f"{API}/admin/users/{uid}", json={"role": role}, headers=hb, timeout=30)
        got = (d.users.find_one({"id": uid}) or {}).get("role")
        assert (got or "").lower() != "super_admin", f"org admin self-promoted to {got} (HTTP {r.status_code})"
    finally:
        d.users.update_many({"organization_id": org["id"]}, {"$set": {"role": "admin"}})
        destroy_org(org)
