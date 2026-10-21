# iter393 — adversarial multi-tenant isolation probes (cross-tenant by-id, org_id injection,
# registry RBAC, super-admin picker, suspend/delete/export/import lifecycle, 58:12 regression)
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LUB_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
CREDS = {
    "owner": ("owner@5812global.org", "Owner@5812!"),
    "g_admin": ("admin@5812uganda.org", "Admin@5812"),
    "l_admin": ("admin@lubwamas.org", "Lubwama@2026"),
}


def mongo(coro_fn):
    async def run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await coro_fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()
    return asyncio.run(run())


def clear_throttle():
    async def f(db):
        await db.login_attempts.delete_many({})
    mongo(f)


_TOKENS = {}


def login(key, host=None):
    clear_throttle()
    email, pw = CREDS[key]
    h = {"Host": host} if host else {}
    base = "http://localhost:8001/api" if host else API  # Cloudflare rejects spoofed Host on the public URL
    r = requests.post(f"{base}/auth/login", json={"identifier": email, "password": pw}, headers=h, timeout=30)
    return r


def token(key):
    if key not in _TOKENS:
        r = login(key)
        assert r.status_code == 200, r.text
        _TOKENS[key] = r.json()["token"]
    return _TOKENS[key]


def H(key):
    return {"Authorization": f"Bearer {token(key)}"}


# ---- helpers to pick existing 58:12 record ids directly from Mongo ----
def pick_ids():
    async def f(db):
        out = {}
        for coll in ["members", "events", "tasks", "products", "invoices", "hr_payslips", "social_cases", "files",
                     "bookings", "documents", "locations", "expenses", "tickets", "donations"]:
            d = await db[coll].find_one({"organization_id": GLOBAL_ORG, "id": {"$exists": True}}, {"_id": 0, "id": 1})
            if d:
                out[coll] = d["id"]
        return out
    return mongo(f)


def exists(coll, rid):
    async def f(db):
        return await db[coll].count_documents({"id": rid, "organization_id": GLOBAL_ORG})
    return mongo(f)


# Cross-tenant by-id: Lubwamas admin holding valid 58:12 ids
class TestCrossTenantById:
    ROUTES = {
        "members": "/members/{id}", "events": "/events/{id}", "tasks": "/tasks/{id}",
        "products": "/products/{id}", "invoices": "/invoices/{id}", "hr_payslips": "/hr/payslips/{id}/history",
        "social_cases": "/social-work/cases/{id}", "expenses": "/expenses/{id}", "donations": "/donations/{id}", "bookings": "/bookings/{id}", "documents": "/documents/{id}",
        "locations": "/locations/{id}",
    }

    def test_get_put_delete_foreign_ids(self):
        ids = pick_ids()
        print("picked", ids)
        leaks = []
        for coll, path in self.ROUTES.items():
            if coll not in ids:
                continue
            url = API + path.format(id=ids[coll])
            g = requests.get(url, headers=H("l_admin"), timeout=30)
            p = requests.put(url, headers=H("l_admin"), json={"name": "PWNED", "title": "PWNED"}, timeout=30)
            d = requests.delete(url, headers=H("l_admin"), timeout=30)
            survived = exists(coll, ids[coll])
            print(coll, g.status_code, p.status_code, d.status_code, "survived", survived)
            if g.status_code == 200 or d.status_code in (200, 204) and not survived:
                leaks.append((coll, g.status_code, d.status_code, survived))
            if not survived:
                leaks.append((coll, "DELETED"))
        assert not leaks, leaks

    def test_foreign_record_not_modified(self):
        ids = pick_ids()

        async def f(db):
            bad = []
            for coll, rid in ids.items():
                d = await db[coll].find_one({"id": rid}, {"_id": 0, "name": 1, "title": 1})
                if d and ("PWNED" in (d.get("name") or "") or "PWNED" in (d.get("title") or "")):
                    bad.append(coll)
            return bad
        assert mongo(f) == []


# org_id injection in body / query
class TestOrgIdInjection:
    def test_body_organization_id_is_stripped(self):
        email = f"test_inj_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/members", headers=H("l_admin"), json={
            "name": "TEST_Inj Probe", "first_name": "TEST_Inj", "last_name": "Probe", "email": email,
            "organization_id": GLOBAL_ORG}, timeout=30)
        print("create member", r.status_code, r.text[:200])
        assert r.status_code in (200, 201)

        async def f(db):
            return await db.members.find_one({"email": email}, {"_id": 0, "organization_id": 1, "id": 1})
        doc = mongo(f)
        assert doc and doc["organization_id"] == LUB_ORG, doc
        # cleanup
        async def c(db):
            await db.members.delete_many({"email": email})
        mongo(c)

    def test_query_organization_id_does_not_widen(self):
        r = requests.get(f"{API}/members", headers=H("l_admin"),
                         params={"organization_id": GLOBAL_ORG, "org": "5812global", "limit": 500}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        rows = body if isinstance(body, list) else (body.get("members") or body.get("items") or body.get("data") or [])
        async def f(db):
            return await db.members.count_documents({"organization_id": LUB_ORG})
        assert len(rows) <= mongo(f) + 0, len(rows)

    def test_update_cannot_move_record(self):
        # create in lub, then try to $set organization_id to global
        r = requests.post(f"{API}/tasks", headers=H("l_admin"), json={"title": "TEST_inj_task"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        tid = r.json().get("id") or (r.json().get("task") or {}).get("id")
        requests.put(f"{API}/tasks/{tid}", headers=H("l_admin"),
                     json={"title": "TEST_inj_task2", "organization_id": GLOBAL_ORG}, timeout=30)
        async def f(db):
            return await db.tasks.find_one({"id": tid}, {"_id": 0, "organization_id": 1})
        assert mongo(f)["organization_id"] == LUB_ORG
        requests.delete(f"{API}/tasks/{tid}", headers=H("l_admin"), timeout=30)


# routes without get_current_user run under the default org
class TestUnauthRoutesCrossTenant:
    def test_calling_contacts_not_leaking_default_org(self):
        r = requests.get(f"{API}/calling/extensions", headers=H("l_admin"), timeout=30)
        r2 = requests.get(f"{API}/calling/extensions", timeout=30)
        print("calling ext as lub", r.status_code, r.text[:300])
        print("calling ext anon", r2.status_code, r2.text[:300])
        assert r2.status_code in (401, 403), "calling routes unauthenticated"


# registry RBAC
class TestRegistryRBAC:
    @pytest.mark.parametrize("method,path", [
        ("get", "/organizations"), ("post", "/organizations"),
        ("post", f"/organizations/{LUB_ORG}/status"), ("get", f"/organizations/{LUB_ORG}/export"),
        ("post", "/organizations/import"), ("delete", f"/organizations/{LUB_ORG}"),
        ("post", f"/organizations/{GLOBAL_ORG}/enter"), ("put", f"/organizations/{LUB_ORG}"),
    ])
    def test_org_admin_forbidden(self, method, path):
        r = getattr(requests, method)(API + path, headers=H("g_admin"), json={}, timeout=30)
        assert r.status_code == 403, (path, r.status_code)


# per-org email uniqueness + shared-host login ambiguity
class TestSameEmailTwoOrgs:
    def test_same_email_two_people_both_can_login(self):
        email = f"test_dup_{uuid.uuid4().hex[:6]}@example.com"
        ids = []
        for key, pw in (("g_admin", "DupA@12345"), ("l_admin", "DupB@12345")):
            r = requests.post(f"{API}/admin/users", headers=H(key), json={
                "name": "TEST Dup", "email": email, "password": pw, "role": "Member"}, timeout=30)
            print(key, r.status_code, r.text[:200])
            assert r.status_code in (200, 201), r.text
        async def f(db):
            return await db.users.find({"email": email}, {"_id": 0, "organization_id": 1, "id": 1}).to_list(5)
        rows = mongo(f)
        assert len(rows) == 2 and {r["organization_id"] for r in rows} == {GLOBAL_ORG, LUB_ORG}
        results = {}
        for pw in ("DupA@12345", "DupB@12345"):
            clear_throttle()
            r = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
            results[pw] = r.status_code
        async def c(db):
            await db.users.delete_many({"email": email})
            await db.members.delete_many({"email": email})
        mongo(c)
        print("login results on shared host", results)
        assert all(v == 200 for v in results.values()), results


# hostname-gated login
class TestHostnameLogin:
    def test_foreign_account_refused_on_lub_host(self):
        r = login("g_admin", host="new.lubwamas.org")
        print("g_admin on lub host", r.status_code, r.text[:200])
        assert r.status_code in (401, 403)

    def test_own_account_allowed_on_lub_host(self):
        r = login("l_admin", host="new.lubwamas.org")
        print("l_admin on lub host", r.status_code)
        assert r.status_code == 200


# 58:12 regression
class TestGlobalRegression:
    @pytest.mark.parametrize("path", ["/members", "/locations", "/events", "/products", "/tasks",
                                      "/finance/reports/trial-balance", "/finance/reports/pnl", "/hr/payslips", "/dashboard/stats"])
    def test_global_endpoints(self, path):
        r = requests.get(API + path, headers=H("g_admin"), timeout=60)
        print(path, r.status_code, len(r.content))
        assert r.status_code == 200, (path, r.status_code, r.text[:200])

    def test_lub_locations_only_own(self):
        g = requests.get(f"{API}/locations", headers=H("g_admin"), timeout=60).json()
        l = requests.get(f"{API}/locations", headers=H("l_admin"), timeout=60).json()
        print("locations global", [x.get("name") for x in g], "lub", [x.get("name") for x in l])
        assert not ({x["id"] for x in g} & {x["id"] for x in l})


# full lifecycle on a throwaway org: empty start, suspend/reactivate, export/import, delete
class TestOrgLifecycle:
    def test_lifecycle(self):
        slug = f"test-iso-{uuid.uuid4().hex[:6]}"
        email = f"{slug}@example.com"
        pw = "TestIso@2026"
        r = requests.post(f"{API}/organizations", headers=H("owner"), json={
            "name": f"TEST {slug}", "slug": slug, "owner_email": email, "owner_password": pw,
            "owner_name": "TEST Iso Admin"}, timeout=30)
        assert r.status_code == 200, r.text
        oid = r.json()["organization"]["id"]
        imported_id = None
        try:
            clear_throttle()
            lr = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
            assert lr.status_code == 200, lr.text
            t = {"Authorization": f"Bearer {lr.json()['token']}"}
            counts = {}
            for path in ["/members", "/events", "/products", "/locations", "/tasks", "/hr/payslips"]:
                b = requests.get(API + path, headers=t, timeout=60)
                j = b.json()
                counts[path] = (b.status_code, len(j) if isinstance(j, list) else
                                {k: (len(v) if isinstance(v, list) else v) for k, v in j.items()} if isinstance(j, dict) else j)
            print("new org counts", counts)
            assert counts["/members"][1] in (0,) or counts["/members"][1].get("total", 0) == 0 if isinstance(counts["/members"][1], dict) else counts["/members"][1] == 0
            assert counts["/locations"][1] == 1
            # dashboard stats should be zero-ish
            ds = requests.get(f"{API}/dashboard/stats", headers=t, timeout=60)
            print("new org dashboard", ds.status_code, ds.text[:400])
            # create an event in new org, verify absent from global
            ev = requests.post(f"{API}/events", headers=t, json={"title": "TEST_iso_event", "name": "TEST_iso_event",
                               "start_date": "2026-12-01", "date": "2026-12-01"}, timeout=30)
            print("create event", ev.status_code, ev.text[:200])
            gev = requests.get(f"{API}/events", headers=H("g_admin"), timeout=60).text
            assert "TEST_iso_event" not in gev
            # suspend
            s = requests.post(f"{API}/organizations/{oid}/status", headers=H("owner"), json={"status": "suspended"}, timeout=30)
            assert s.status_code == 200
            assert requests.get(f"{API}/members", headers=t, timeout=30).status_code in (401, 403)
            clear_throttle()
            lr2 = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
            print("login while suspended", lr2.status_code, lr2.text[:150])
            assert lr2.status_code == 403 and "suspend" in lr2.text.lower()
            # delete refuses without slug
            d0 = requests.delete(f"{API}/organizations/{oid}", headers=H("owner"), params={"confirm": "wrong"}, timeout=30)
            assert d0.status_code == 400
            # reactivate
            requests.post(f"{API}/organizations/{oid}/status", headers=H("owner"), json={"status": "active"}, timeout=30)
            d1 = requests.delete(f"{API}/organizations/{oid}", headers=H("owner"), params={"confirm": slug}, timeout=30)
            assert d1.status_code == 400, "active org deletable"
            clear_throttle()
            lr3 = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
            assert lr3.status_code == 200
            # export / import
            ex = requests.get(f"{API}/organizations/{oid}/export", headers=H("owner"), timeout=120)
            assert ex.status_code == 200
            dump = ex.json()
            print("export colls", {k: len(v) for k, v in dump["collections"].items()})
            assert "users" in dump["collections"] and "locations" in dump["collections"]
            im = requests.post(f"{API}/organizations/import", headers=H("owner"), json=dump, timeout=120)
            assert im.status_code == 200, im.text
            imported_id = im.json()["organization"]["id"]
            assert imported_id != oid
            print("imported", im.json()["organization"]["slug"], im.json()["restored_documents"])
            # duplicate email now in two orgs with same password - which one does login land in?
            clear_throttle()
            lr4 = requests.post(f"{API}/auth/login", json={"identifier": email, "password": pw}, timeout=30)
            print("login after import lands in", lr4.json().get("user", {}).get("organization_id"), "orig", oid, "imp", imported_id)
            # original untouched
            async def f(db):
                return (await db.locations.count_documents({"organization_id": oid}),
                        await db.locations.count_documents({"organization_id": imported_id}))
            print("loc counts orig/imp", mongo(f))
            assert mongo(f) == (1, 1)
        finally:
            for o in [x for x in (oid, imported_id) if x]:
                requests.post(f"{API}/organizations/{o}/status", headers=H("owner"), json={"status": "suspended"}, timeout=30)
                org = requests.get(f"{API}/organizations", headers=H("owner"), timeout=30).json()
                lst = org.get("organizations", org) if isinstance(org, dict) else org
                sl = next((x["slug"] for x in lst if x["id"] == o), None)
                dd = requests.delete(f"{API}/organizations/{o}", headers=H("owner"), params={"confirm": sl}, timeout=60)
                print("cleanup", o, dd.status_code, dd.text[:120])
            async def g(db):
                return await db.users.count_documents({"email": email})
            assert mongo(g) == 0


# super admin picker / token scope
class TestSuperAdminPicker:
    def test_picker_token_unlocks_nothing(self):
        async def f(db):
            await db.users.update_one({"email": "owner@5812global.org"}, {"$set": {"active_organization_id": None}})
        mongo(f)
        r = login("owner")
        j = r.json()
        print("owner login", r.status_code, {k: j.get(k) for k in ("requires_org_selection",)}, [o["slug"] for o in j.get("organizations", [])])
        assert j.get("requires_org_selection") is True and j.get("token")
        t = {"Authorization": f"Bearer {j['token']}"}
        for p in ["/members", "/events", "/locations", "/dashboard/stats", "/auth/me"]:
            sc = requests.get(API + p, headers=t, timeout=30).status_code
            print("picker token", p, sc)
            if p != "/auth/me":
                assert sc == 403, (p, sc)
        assert requests.get(f"{API}/organizations", headers=t, timeout=30).status_code == 200
        # enter lub, then switch to global -> same token sees global only
        assert requests.post(f"{API}/organizations/{LUB_ORG}/enter", headers=t, timeout=30).status_code == 200
        lub_locs = {x["id"] for x in requests.get(f"{API}/locations", headers=t, timeout=30).json()}
        assert requests.post(f"{API}/organizations/{GLOBAL_ORG}/enter", headers=t, timeout=30).status_code == 200
        g_locs = {x["id"] for x in requests.get(f"{API}/locations", headers=t, timeout=30).json()}
        print("lub", len(lub_locs), "global", len(g_locs))
        assert lub_locs and g_locs and not (lub_locs & g_locs)
        _TOKENS["owner"] = j["token"]


# privilege escalation: an org admin must not be able to mint a super_admin
class TestSuperAdminEscalation:
    def test_org_admin_cannot_create_super_admin(self):
        email = f"test_esc_{uuid.uuid4().hex[:5]}@example.com"
        r = requests.post(f"{API}/admin/users", headers=H("l_admin"), json={
            "name": "TEST esc", "email": email, "password": "Esc@12345", "role": "super_admin"}, timeout=30)
        async def f(db):
            u = await db.users.find_one({"email": email}, {"_id": 0, "role": 1})
            await db.users.delete_many({"email": email})
            await db.members.delete_many({"email": email})
            return u
        u = mongo(f)
        print("create super_admin by org admin:", r.status_code, u)
        assert r.status_code in (400, 403) and not (u and u.get("role") == "super_admin")


# /auth/google must not accept an unsigned JWT
class TestGoogleAuthForgery:
    def test_unsigned_google_token_rejected(self):
        import base64, json as _j
        email = f"test_forge_{uuid.uuid4().hex[:5]}@example.com"
        p = base64.urlsafe_b64encode(_j.dumps({"email": email}).encode()).decode().rstrip("=")
        r = requests.post(f"{API}/auth/google", json={"token": f"x.{p}.x"}, timeout=30)
        async def f(db):
            await db.users.delete_many({"email": email})
        mongo(f)
        print("forged google token:", r.status_code, r.text[:120])
        assert r.status_code in (400, 401)
