# iter394 — adversarial RETEST of the iter393 org-isolation hardening fixes
# (privilege escalation, forged google token, seeding, router auth, websocket, presence,
#  duplicate-email login, foreign location 404, is_default, super-admin logout) + bypass probes
import os
import json
import time
import uuid
import asyncio
import pytest
import requests
import websockets
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
LOCAL = "http://localhost:8001/api"  # only for spoofed Host header probes

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LUB_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
CREDS = {
    "owner": ("owner@5812global.org", "Owner@5812!"),
    "g_admin": ("admin@5812uganda.org", "Admin@5812"),
    "l_admin": ("admin@lubwamas.org", "Lubwama@2026"),
}


def mongo(fn):
    async def run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()
    return asyncio.run(run())


def clear_throttle():
    async def f(db):
        await db.login_attempts.delete_many({})
    mongo(f)


def raw_login(email, pw, base=API, headers=None):
    for _ in range(4):
        clear_throttle()
        r = requests.post(f"{base}/auth/login", json={"identifier": email, "password": pw},
                          headers=headers or {}, timeout=30)
        if r.status_code != 429:
            return r
        time.sleep(35)
    return r


_T = {}


def token(key):
    if key not in _T:
        r = raw_login(*CREDS[key])
        assert r.status_code == 200, r.text
        j = r.json()
        if key == "owner" and j.get("requires_org_choice") or (key == "owner" and "user" not in j):
            t = j["token"]
            e = requests.post(f"{API}/organizations/{GLOBAL_ORG}/enter", headers={"Authorization": f"Bearer {t}"}, timeout=30)
            assert e.status_code == 200, e.text
            _T[key] = e.json()["token"]
        else:
            _T[key] = j["token"]
    return _T[key]


def H(key):
    return {"Authorization": f"Bearer {token(key)}"}


def me(key):
    return requests.get(f"{API}/auth/me", headers=H(key), timeout=30).json()


# ---------------- 1. privilege escalation ----------------
class TestPrivilegeEscalation:
    @pytest.mark.parametrize("role", ["super_admin", "Super_Admin", "SUPER_ADMIN"])
    def test_create_super_admin_refused(self, role):
        r = requests.post(f"{API}/admin/users", headers=H("l_admin"), timeout=30, json={
            "name": "TEST_esc", "email": f"test_esc_{uuid.uuid4().hex[:6]}@x.org", "password": "Esc@12345", "role": role})
        print(role, r.status_code, r.text[:120])
        assert r.status_code == 403

    def test_promote_and_bulk_refused(self):
        r = requests.post(f"{API}/admin/users", headers=H("l_admin"), timeout=30, json={
            "name": "TEST_esc2", "email": f"test_esc2_{uuid.uuid4().hex[:6]}@x.org", "password": "Esc@12345", "role": "Staff"})
        assert r.status_code == 200, r.text
        uid = r.json().get("id") or r.json().get("user", {}).get("id")
        try:
            p = requests.put(f"{API}/admin/users/{uid}", headers=H("l_admin"), json={"role": "super_admin"}, timeout=30)
            b = requests.post(f"{API}/admin/users/bulk-update", headers=H("l_admin"),
                              json={"user_ids": [uid], "updates": {"role": "Super_Admin"}}, timeout=30)
            print("put", p.status_code, "bulk", b.status_code)
            assert p.status_code == 403 and b.status_code == 403
        finally:
            requests.delete(f"{API}/admin/users/{uid}", headers=H("l_admin"), timeout=30)

    def test_owner_untouchable_by_org_admin(self):
        owner_id = "489c73cf-60ca-4721-bd5b-16e2e61a5a36"
        for k in ("g_admin", "l_admin"):
            p = requests.put(f"{API}/admin/users/{owner_id}", headers=H(k), json={"name": "PWNED", "status": "inactive"}, timeout=30)
            d = requests.delete(f"{API}/admin/users/{owner_id}", headers=H(k), timeout=30)
            b = requests.post(f"{API}/admin/users/bulk-update", headers=H(k),
                              json={"user_ids": [owner_id], "updates": {"status": "inactive"}}, timeout=30)
            print(k, p.status_code, d.status_code, b.status_code, b.text[:80])
            assert p.status_code in (403, 404) and d.status_code in (403, 404)
            if b.status_code == 200:
                assert b.json().get("updated") == 0

        async def f(db):
            return await db.users.find_one({"id": owner_id}, {"_id": 0, "name": 1, "status": 1, "role": 1})
        o = mongo(f)
        assert o and o.get("role") == "super_admin" and o.get("name") != "PWNED" and o.get("status") != "inactive"

    def test_bypass_user_import_with_super_admin_role(self):
        email = f"test_imp_{uuid.uuid4().hex[:6]}@x.org"
        r = requests.post(f"{API}/admin/users/import", headers=H("l_admin"), timeout=30,
                          json={"users": [{"name": "TEST_imp", "email": email, "password": "Imp@12345", "role": "super_admin"}]})
        print("import", r.status_code, r.text[:200])

        async def f(db):
            u = await db.users.find_one({"email": email}, {"_id": 0, "role": 1, "id": 1})
            await db.users.delete_many({"email": email})
            await db.members.delete_many({"email": email})
            return u
        u = mongo(f)
        print("created user", u)
        assert not (u and (u.get("role") or "").lower() == "super_admin"), "IMPORT BYPASS: org admin minted super_admin"

    def test_bypass_guest_move_to_staff_super_admin(self):
        g = requests.post(f"{API}/guests", headers=H("l_admin"), timeout=30,
                          json={"name": "TEST_guest_esc", "email": f"test_ge_{uuid.uuid4().hex[:6]}@x.org"})
        print("guest create", g.status_code, g.text[:150])
        if g.status_code not in (200, 201):
            pytest.skip("cannot create guest")
        gid = g.json().get("id")
        email = g.json().get("email")
        m = requests.post(f"{API}/guests/{gid}/move-to-staff", headers=H("l_admin"), timeout=30,
                          json={"role": "super_admin", "password": "Esc@12345"})
        print("move-to-staff", m.status_code, m.text[:200])

        async def f(db):
            u = await db.users.find_one({"original_id": gid}, {"_id": 0, "role": 1, "id": 1})
            await db.users.delete_many({"original_id": gid})
            await db.members.delete_many({"$or": [{"email": email}, {"name": "TEST_guest_esc"}]})
            await db.guests.delete_many({"id": gid})
            return u
        u = mongo(f)
        print("created", u)
        assert not (u and (u.get("role") or "").lower() == "super_admin"), "MOVE-TO-STAFF BYPASS: org director/admin minted super_admin"


# ---------------- 2. forged google token ----------------
class TestGoogleForgery:
    def test_google_route_gone(self):
        r = requests.post(f"{API}/auth/google", json={"credential": "x.eyJlbWFpbCI6ImFkbWluQDU4MTJ1Z2FuZGEub3JnIn0.x"}, timeout=30)
        assert r.status_code in (404, 405)

    def test_google_session_fake_id(self):
        r = requests.post(f"{API}/auth/google-session", json={"session_id": "forged-" + uuid.uuid4().hex}, timeout=30)
        print("google-session", r.status_code, r.text[:150])
        assert r.status_code in (400, 401, 403, 422)
        assert "token" not in r.text.lower() or r.status_code >= 400

    def test_forged_jwts_grant_nothing(self):
        import base64
        def b64(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
        sub = me("g_admin")["id"]
        forged = [
            b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": sub, "exp": 9999999999}) + ".",
            b64({"alg": "HS256", "typ": "JWT"}) + "." + b64({"sub": sub, "exp": 9999999999}) + ".AAAA",
        ]
        from jose import jwt as J
        forged.append(J.encode({"sub": sub, "exp": 9999999999}, "5812global_secret_key_change_in_production", algorithm="HS256"))
        forged.append(J.encode({"sub": sub, "exp": 9999999999}, "secret", algorithm="HS256"))
        for t in forged:
            for path in ("/auth/me", "/members", "/organizations", "/calling/extensions"):
                r = requests.get(f"{API}{path}", headers={"Authorization": f"Bearer {t}"}, timeout=30)
                assert r.status_code in (401, 403), (path, t[:30], r.status_code)


# ---------------- 3. seeding ----------------
class TestSeed:
    PATHS = ["/seed", "/seed-extended", "/seed-locations", "/seed-all"]

    def test_anonymous_refused(self):
        for p in self.PATHS:
            for q in ("", "?org=lubwamas"):
                r = requests.post(f"{API}{p}{q}", timeout=30)
                assert r.status_code == 401, (p, q, r.status_code)
            r = requests.post(f"{LOCAL}{p}", headers={"Host": "new.lubwamas.org"}, timeout=30)
            assert r.status_code == 401, (p, "host", r.status_code)

    def test_org_admin_refused(self):
        for p in self.PATHS:
            for k in ("g_admin", "l_admin"):
                r = requests.post(f"{API}{p}?org=lubwamas", headers=H(k), timeout=30)
                assert r.status_code == 403, (p, k, r.status_code)

    def test_no_injected_admin_in_lubwamas(self):
        async def f(db):
            return await db.users.count_documents({"email": "admin@5812global.org"})
        assert mongo(f) == 0


# ---------------- 4. router-level auth ----------------
ANON_PROBES = [
    ("GET", "/calling/extensions"), ("GET", "/calling/contacts"), ("GET", "/calling/history"),
    ("GET", "/calling/voicemail"), ("GET", "/calling/pbx-configs"), ("GET", "/calling/calls/active"),
    ("GET", "/conferences"), ("POST", "/conferences/instant"), ("GET", "/conferences/schedule/available-slots"),
    ("GET", "/presence/online-users"), ("GET", "/presence/bulk"), ("PUT", "/presence/heartbeat?user_id=x"),
    ("GET", "/presence/status/x"),
    ("GET", "/reactions/quick"), ("GET", "/reactions/message/x"),
]


class TestRouterAuth:
    def test_anonymous_refused(self):
        bad = []
        for m, p in ANON_PROBES:
            r = requests.request(m, f"{API}{p}", timeout=30, json={})
            if r.status_code not in (401, 403):
                bad.append((m, p, r.status_code))
        assert not bad, bad

    def test_signed_in_5812_user_can_use(self):
        h = H("g_admin")
        uid = me("g_admin")["id"]
        res = {}
        q = f"?user_id={uid}"
        for m, p in [("GET", "/calling/extensions"), ("GET", "/calling/contacts" + q), ("GET", "/calling/history" + q),
                     ("GET", "/calling/voicemail" + q), ("GET", "/calling/voicemail/unread-count" + q), ("GET", "/calling/missed" + q),
                     ("GET", "/calling/calls/active" + q), ("GET", "/conferences" + q), ("GET", "/calling/pbx-configs"), ("GET", f"/presence/online-users"),
                     ("PUT", f"/presence/heartbeat?user_id={uid}"), ("GET", f"/presence/status/{uid}"),
                     ("GET", "/reactions/quick")]:
            r = requests.request(m, f"{API}{p}", headers=h, timeout=30)
            res[p] = r.status_code
        print(res)
        assert all(v == 200 for v in res.values()), res

    def test_conference_crud_as_5812(self):
        h = H("g_admin")
        uid = me("g_admin")["id"]
        c = requests.post(f"{API}/conferences?user_id={uid}", headers=h, timeout=30, json={"title": "TEST_conf394", "name": "TEST_conf394"})
        print("create conf", c.status_code, c.text[:200])
        assert c.status_code in (200, 201), c.text
        cid = c.json().get("id") or c.json().get("conference", {}).get("id")
        g = requests.get(f"{API}/conferences/{cid}?user_id={uid}", headers=h, timeout=30)
        lg = requests.get(f"{API}/conferences/{cid}?user_id={uid}", headers=H("l_admin"), timeout=30)
        d = requests.delete(f"{API}/conferences/{cid}?user_id={uid}", headers=h, timeout=30)
        print("get", g.status_code, "lub get", lg.status_code, "del", d.status_code)
        assert g.status_code == 200 and lg.status_code == 404 and d.status_code in (200, 204)

    def test_lubwamas_calling_sees_no_5812_staff(self):
        r = requests.get(f"{API}/calling/contacts?user_id={me('l_admin')['id']}", headers=H("l_admin"), timeout=30)
        e = requests.get(f"{API}/calling/extensions", headers=H("l_admin"), timeout=30)
        txt = r.text + e.text
        print("lub contacts", r.status_code, r.text[:200])
        assert "5812uganda" not in txt and "5812global" not in txt

    def test_presence_cross_tenant_write_by_user_id(self):
        """A signed-in Lubwamas admin sets presence for a 58:12 user id via ?user_id=."""
        gid = me("g_admin")["id"]
        requests.put(f"{API}/presence/heartbeat?user_id={gid}", headers=H("g_admin"), timeout=30)
        w = requests.put(f"{API}/presence/status?user_id={gid}&status=dnd", headers=H("l_admin"), timeout=30)
        s = requests.get(f"{API}/presence/status/{gid}", headers=H("l_admin"), timeout=30)
        print("lub sets 58:12 dnd", w.status_code, "lub reads 58:12 presence", s.status_code, s.text[:150])
        own = requests.get(f"{API}/presence/status/{gid}", headers=H("g_admin"), timeout=30).json()
        requests.put(f"{API}/presence/status?user_id={gid}&status=online", headers=H("g_admin"), timeout=30)
        # the dnd write lands on the caller (l_admin) now — undo it so later presence tests are clean
        requests.put(f"{API}/presence/status?status=online", headers=H("l_admin"), timeout=30)
        assert own.get("status") != "dnd", "Lubwamas admin altered 58:12 admin presence (user_id taken from query, not token)"


# ---------------- 5. websocket isolation ----------------
WS = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws/"


async def _drain(ws, secs):
    out = []
    end = time.time() + secs
    while time.time() < end:
        try:
            out.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))))
        except asyncio.TimeoutError:
            break
        except Exception:
            break
    return out


class TestWebsocket:
    def test_presence_events_stay_in_org(self):
        gid, lid = me("g_admin")["id"], me("l_admin")["id"]

        async def run():
            async with websockets.connect(WS + gid + "?token=" + token("g_admin"), open_timeout=20) as wg:
                g0 = await _drain(wg, 2)
                async with websockets.connect(WS + lid + "?token=" + token("l_admin"), open_timeout=20) as wl:
                    l0 = await _drain(wl, 2)
                    g1 = await _drain(wg, 2)
                g2 = await _drain(wg, 3)
            return g0 + g1 + g2, l0
        gmsgs, lmsgs = asyncio.run(run())
        print("g msgs", gmsgs[:6]); print("l msgs", lmsgs[:6])
        assert gid not in json.dumps(lmsgs), "Lubwamas socket saw 58:12 user id"
        assert lid not in json.dumps(gmsgs), "58:12 socket saw Lubwamas user id"
        assert any(m.get("type") == "online_users" for m in lmsgs)

    def test_ws_cross_tenant_call_offer(self):
        gid, lid = me("g_admin")["id"], me("l_admin")["id"]

        async def run():
            async with websockets.connect(WS + gid + "?token=" + token("g_admin"), open_timeout=20) as wg:
                await _drain(wg, 1)
                async with websockets.connect(WS + lid + "?token=" + token("l_admin"), open_timeout=20) as wl:
                    await _drain(wl, 1)
                    await wl.send(json.dumps({"type": "call_offer", "call_id": "TEST_" + uuid.uuid4().hex[:6],
                                              "target_user_id": gid, "sdp": "v=0", "caller_name": "TEST_x"}))
                    await asyncio.sleep(1)
                return await _drain(wg, 2)
        got = asyncio.run(run())
        print("58:12 got", got)
        assert not any(m.get("type") == "incoming_call" for m in got), "Cross-tenant call_offer delivered over WS"


# ---------------- 6. presence eviction ----------------
class TestPresenceEviction:
    def test_other_org_presence_not_evicted(self):
        lid = me("l_admin")["id"]
        requests.put(f"{API}/presence/connect?user_id={lid}", headers=H("l_admin"), timeout=30)
        g = requests.get(f"{API}/presence/online-users", headers=H("g_admin"), timeout=30)
        assert g.status_code == 200 and lid not in g.text
        l = requests.get(f"{API}/presence/online-users", headers=H("l_admin"), timeout=30)
        print("lub online", l.text[:200])
        assert lid in l.text, "Lubwamas presence was evicted by a 58:12 call"
        requests.put(f"{API}/presence/disconnect?user_id={lid}", headers=H("l_admin"), timeout=30)


# ---------------- 7. same email in two orgs ----------------
class TestDuplicateEmail:
    def test_both_people_sign_in_to_own_org(self):
        email = f"test_dup394_{uuid.uuid4().hex[:6]}@x.org"
        a = requests.post(f"{API}/admin/users", headers=H("g_admin"), timeout=30,
                          json={"name": "TEST_DupA", "email": email, "password": "DupA@12345", "role": "Staff"})
        b = requests.post(f"{API}/admin/users", headers=H("l_admin"), timeout=30,
                          json={"name": "TEST_DupB", "email": email, "password": "DupB@12345", "role": "Staff"})
        print("create", a.status_code, b.status_code, b.text[:120])
        try:
            assert a.status_code == 200 and b.status_code == 200
            ra = raw_login(email, "DupA@12345")
            rb = raw_login(email, "DupB@12345")
            rw = raw_login(email, "Wrong@12345")
            print("A", ra.status_code, "B", rb.status_code, "wrong", rw.status_code)
            assert ra.status_code == 200 and ra.json()["user"]["organization_id"] == GLOBAL_ORG
            assert rb.status_code == 200 and rb.json()["user"]["organization_id"] == LUB_ORG
            assert rw.status_code == 401
            # each token sees only its own org's members
            ta = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {ra.json()['token']}"}, timeout=30).json()
            tb = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {rb.json()['token']}"}, timeout=30).json()
            assert ta["name"] == "TEST_DupA" and tb["name"] == "TEST_DupB"
        finally:
            async def f(db):
                await db.users.delete_many({"email": email})
                await db.members.delete_many({"email": email})
            mongo(f)


# ---------------- 8/9/10 ----------------
class TestMisc:
    def test_foreign_location_put_delete_404(self):
        async def f(db):
            return await db.locations.find_one({"organization_id": GLOBAL_ORG}, {"_id": 0, "id": 1, "name": 1})
        loc = mongo(f)
        p = requests.put(f"{API}/locations/{loc['id']}", headers=H("l_admin"), json={"name": "PWNED"}, timeout=30)
        d = requests.delete(f"{API}/locations/{loc['id']}", headers=H("l_admin"), timeout=30)
        after = mongo(f)
        print(p.status_code, d.status_code, after)
        assert p.status_code == 404 and d.status_code == 404 and after["name"] == loc["name"]

    def test_single_default_org(self):
        async def f(db):
            return await db.organizations.count_documents({"is_default": True})
        assert mongo(f) == 1

    def test_owner_logout_clears_active_org(self):
        r = raw_login(*CREDS["owner"])
        t = r.json()["token"]
        if "user" not in r.json():
            t = requests.post(f"{API}/organizations/{GLOBAL_ORG}/enter", headers={"Authorization": f"Bearer {t}"}, timeout=30).json()["token"]
        lo = requests.post(f"{API}/auth/logout", headers={"Authorization": f"Bearer {t}"}, timeout=30)
        assert lo.status_code == 200
        r2 = raw_login(*CREDS["owner"])
        j = r2.json()
        print("after logout login keys", list(j.keys()))
        assert "user" not in j or not j.get("user", {}).get("organization_id"), "picker did not return"
        # leave owner inside 58:12 Global
        e = requests.post(f"{API}/organizations/{GLOBAL_ORG}/enter", headers={"Authorization": f"Bearer {j['token']}"}, timeout=30)
        assert e.status_code == 200


# ---------------- 58:12 regression ----------------
class TestGlobalRegression:
    def test_core_lists(self):
        res = {}
        for p in ["/members", "/locations", "/events", "/products", "/tasks", "/reports/summary", "/hr/payslips"]:
            r = requests.get(f"{API}{p}", headers=H("g_admin"), timeout=60)
            res[p] = r.status_code
        print(res)
        assert all(v == 200 for v in res.values()), res


# ---------------- WS: other cross-tenant push paths (chat participants, guest-request broadcast) ----------------
class TestWebsocketPushPaths:
    def test_chat_to_foreign_participant_not_delivered(self):
        gid = me("g_admin")["id"]
        c = requests.post(f"{API}/chat/conversations", headers=H("l_admin"), timeout=30,
                          json={"type": "direct", "participants": [gid], "name": "TEST_x394"})
        print("conv create", c.status_code, c.text[:150])
        cid = c.json().get("id")
        lid = me("l_admin")["id"]

        async def run():
            async with websockets.connect(WS + gid + "?token=" + token("g_admin"), open_timeout=20) as wg:
                await _drain(wg, 1)
                async with websockets.connect(WS + lid + "?token=" + token("l_admin"), open_timeout=20) as wl:
                    await _drain(wl, 1)
                    await wl.send(json.dumps({"type": "chat_message", "conversation_id": cid, "text": "TEST_cross_tenant_394"}))
                    await asyncio.sleep(1.5)
                return await _drain(wg, 2)
        got = asyncio.run(run())

        async def f(db):
            await db.chat_messages.delete_many({"conversation_id": cid})
            await db.conversations.delete_many({"id": cid})
        mongo(f)
        print("58:12 got", got)
        assert "TEST_cross_tenant_394" not in json.dumps(got), "Lubwamas chat pushed to 58:12 socket"

    def test_guest_request_broadcast_scoped(self):
        gid = me("g_admin")["id"]

        async def f(db):
            return await db.locations.find_one({"organization_id": LUB_ORG}, {"_id": 0, "id": 1})
        loc = mongo(f)

        async def run():
            async with websockets.connect(WS + gid + "?token=" + token("g_admin"), open_timeout=20) as wg:
                await _drain(wg, 1)
                r = await asyncio.to_thread(requests.post, f"{API}/access/guest-requests",
                                            headers=H("l_admin"), json={"location_id": loc["id"], "guest_name": "TEST_GuestLeak394"}, timeout=30)
                print("guest req", r.status_code, r.text[:120])
                rid = r.json().get("id") if r.status_code == 200 else None
                return await _drain(wg, 2), rid
        got, rid = asyncio.run(run())

        async def g(db):
            await db.guest_requests.delete_many({"guest_name": "TEST_GuestLeak394"})
            await db.notifications.delete_many({"data.guest_name": "TEST_GuestLeak394"})
        mongo(g)
        print("58:12 got", got)
        assert "TEST_GuestLeak394" not in json.dumps(got), "Lubwamas guest-visit notification broadcast to 58:12 socket"
