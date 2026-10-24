"""iter395 — socket login check, org-bound calendar links, owner activity log,
move-person tool, per-org branding isolation, logo upload, isolation regression.
Run alone (auth routes rate limited ~20/min per IP)."""
import asyncio
import json
import os
import time
import uuid

import pytest
import requests
import websockets
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
# Host-header tests must bypass the preview ingress, which routes on Host itself
# and would answer with its own 404 before the app ever sees the request.
LOCAL = os.environ.get("TEST_LOCAL_BASE", "http://localhost:8001")

def _owner_creds():
    env = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", ".env")) as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v
    except OSError:
        pass
    email = os.environ.get("OWNER_EMAIL") or env.get("OWNER_EMAIL")
    password = os.environ.get("OWNER_PASSWORD") or env.get("OWNER_PASSWORD")
    if not email or not password:
        pytest.skip("OWNER_EMAIL/OWNER_PASSWORD not configured", allow_module_level=True)
    return {"identifier": email, "password": password}


OWNER = _owner_creds()
A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
B_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}
A_MEMBER = {"identifier": "member@5812uganda.org", "password": "Member@5812"}
ORG_A = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"   # 58:12 Global
ORG_B = "ee79732c-1263-46a8-bf46-511c5fe812bf"   # Lubwamas

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(creds):
    for _ in range(3):
        _db().login_attempts.delete_many({})
        r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
        if r.status_code == 429:
            time.sleep(35)
            continue
        assert r.status_code == 200, r.text
        return r.json()
    pytest.fail("login rate limited")


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def S():
    """Shared tokens + user ids."""
    s = {}
    a = _login(A_ADMIN); s["a_tok"], s["a_id"] = a["token"], a["user"]["id"]
    b = _login(B_ADMIN); s["b_tok"], s["b_id"] = b["token"], b["user"]["id"]
    # throwaway Member in org A (member@5812uganda.org password is not reliable)
    memail = f"test_iter395_mem_{uuid.uuid4().hex[:6]}@example.test"
    r = requests.post(f"{API}/admin/users", headers=H(s["a_tok"]), timeout=30, json={
        "name": "TEST_iter395 member", "email": memail, "role": "Member", "password": "Member@2026x!"})
    assert r.status_code in (200, 201), r.text
    m = _login({"identifier": memail, "password": "Member@2026x!"})
    s["m_tok"], s["m_id"] = m["token"], m["user"]["id"]
    o = _login(OWNER)
    r = requests.post(f"{API}/organizations/{ORG_A}/enter", headers=H(o["token"]), timeout=30)
    assert r.status_code == 200, r.text
    s["o_tok"] = r.json()["token"]
    yield s
    _db().users.delete_one({"id": s["m_id"]})


async def _ws(user_id, token=None):
    url = f"{WS_BASE}/api/ws/{user_id}" + (f"?token={token}" if token is not None else "")
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            return "open", json.loads(msg)
    except websockets.exceptions.InvalidStatus as e:
        return "refused", e.response.status_code
    except websockets.exceptions.ConnectionClosed as e:
        return "closed", e.code


# ---------------------------------------------------------------- WebSocket
class TestSocketLogin:
    def test_no_token_refused(self, S):
        st, info = asyncio.run(_ws(S["a_id"]))
        assert st != "open", info

    def test_garbage_token_refused(self, S):
        st, info = asyncio.run(_ws(S["a_id"], "garbage.token.value"))
        assert st != "open", info

    def test_other_users_token_same_org_refused(self, S):
        st, info = asyncio.run(_ws(S["a_id"], S["m_tok"]))
        assert st != "open", info

    def test_other_org_token_refused(self, S):
        st, info = asyncio.run(_ws(S["a_id"], S["b_tok"]))
        assert st != "open", info

    def test_own_token_accepted_and_scoped(self, S):
        st, info = asyncio.run(_ws(S["b_id"], S["b_tok"]))
        assert st == "open", info
        assert info["type"] == "online_users"
        a_users = {u["id"] for u in _db().users.find({"organization_id": ORG_A}, {"id": 1})}
        assert not (set(info.get("users") or []) & a_users), "org A users visible to org B socket"


# ---------------------------------------------------------------- Calendar
class TestCalendarLinks:
    ev_id = None

    def test_token_shape_and_feed(self, S):
        r = requests.get(f"{API}/calendar/share-links", headers=H(S["a_tok"]), timeout=30)
        assert r.status_code == 200, r.text
        tok = r.json()["global"]["token"]
        assert tok.startswith(ORG_A + "."), tok
        ics = requests.get(f"{API}/public/calendar/global.ics", params={"token": tok}, timeout=30)
        assert ics.status_code == 200 and "BEGIN:VCALENDAR" in ics.text
        assert "BEGIN:VEVENT" in ics.text  # 58:12 has public events
        TestCalendarLinks.a_tok = tok

    def test_other_org_token_does_not_show_first_org(self, S):
        TestCalendarLinks.ev_id = str(uuid.uuid4())
        _db().events.insert_one({"id": TestCalendarLinks.ev_id, "organization_id": ORG_B,
                                 "title": "TEST_iter395 Lubwamas public", "date": "2026-03-01",
                                 "is_public": True, "status": "upcoming"})
        try:
            r = requests.get(f"{API}/calendar/share-links", headers=H(S["b_tok"]), timeout=30)
            tok = r.json()["global"]["token"]
            assert tok.startswith(ORG_B + ".")
            assert tok != TestCalendarLinks.a_tok
            j = requests.get(f"{API}/public/calendar/global", params={"token": tok}, timeout=30).json()
            ids = {e["id"] for e in j["events"]}
            assert TestCalendarLinks.ev_id in ids
            assert all(e.get("organization_id") in (ORG_B, None) for e in j["events"]), "org A leak"
            assert len(ids) == 1
        finally:
            _db().events.delete_one({"id": TestCalendarLinks.ev_id})

    def test_tampered_tokens_404(self, S):
        tok = TestCalendarLinks.a_tok
        oid, sig = tok.split(".")
        for bad in [oid + "." + ("0" * 16), ORG_B + "." + sig, sig, "", "x.y"]:
            r = requests.get(f"{API}/public/calendar/global.ics", params={"token": bad}, timeout=30)
            assert r.status_code in (404, 422), (bad, r.status_code)


# ---------------------------------------------------------------- Activity log
class TestActivityLog:
    def test_owner_sees_merged_rows(self, S):
        r = requests.get(f"{API}/organizations/activity", headers=H(S["o_tok"]), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        rows = d["activity"]
        assert rows and {o["id"] for o in d["organizations"]} >= {ORG_A, ORG_B}
        scopes = {x["scope"] for x in rows}
        assert "platform" in scopes, scopes
        ts = [x["timestamp"] or "" for x in rows]
        assert ts == sorted(ts, reverse=True)
        enter = [x for x in rows if x["action"] == "enter"]
        assert enter and enter[0]["organization_name"]

    def test_filter_by_org(self, S):
        r = requests.get(f"{API}/organizations/activity", params={"org_id": ORG_B},
                         headers=H(S["o_tok"]), timeout=30)
        assert r.status_code == 200
        rows = r.json()["activity"]
        bad = [x for x in rows if x["organization_id"] not in (ORG_B,)]
        assert not bad, f"{len(bad)} rows not tagged with Lubwamas: {bad[:2]}"

    def test_admin_forbidden(self, S):
        r = requests.get(f"{API}/organizations/activity", headers=H(S["a_tok"]), timeout=30)
        assert r.status_code == 403

    def test_paging(self, S):
        big = requests.get(f"{API}/organizations/activity", params={"limit": 10},
                           headers=H(S["o_tok"]), timeout=30).json()["activity"]
        pg = requests.get(f"{API}/organizations/activity", params={"limit": 5, "skip": 5},
                          headers=H(S["o_tok"]), timeout=30).json()["activity"]
        assert [x["id"] for x in pg] == [x["id"] for x in big[5:10]]


# ---------------------------------------------------------------- Move person
class TestTransferPerson:
    def test_people_list_and_search(self, S):
        r = requests.get(f"{API}/organizations/{ORG_B}/people", headers=H(S["o_tok"]), timeout=30)
        assert r.status_code == 200
        people = r.json()["people"]
        assert any(p["email"] == "admin@lubwamas.org" for p in people)
        r = requests.get(f"{API}/organizations/{ORG_B}/people", params={"q": "lubwamas"},
                         headers=H(S["o_tok"]), timeout=30)
        assert all("lubwamas" in (p["email"] + p["name"]).lower() for p in r.json()["people"])
        assert requests.get(f"{API}/organizations/{ORG_B}/people", headers=H(S["a_tok"]),
                            timeout=30).status_code == 403

    def test_transfer_errors(self, S):
        h = H(S["o_tok"])
        r = requests.post(f"{API}/organizations/transfer-person", headers=h, timeout=30,
                          json={"user_id": "nope", "from_org_id": ORG_A, "to_org_id": ORG_B})
        assert r.status_code == 404
        r = requests.post(f"{API}/organizations/transfer-person", headers=h, timeout=30,
                          json={"user_id": S["m_id"], "from_org_id": ORG_A, "to_org_id": ORG_A})
        assert r.status_code == 400
        r = requests.post(f"{API}/organizations/transfer-person", headers=H(S["a_tok"]), timeout=30,
                          json={"user_id": S["m_id"], "from_org_id": ORG_A, "to_org_id": ORG_B})
        assert r.status_code == 403

    def test_transfer_409_and_success(self, S):
        email = f"test_iter395_{uuid.uuid4().hex[:6]}@example.test"
        pw = "Move@2026x!"
        created = []
        try:
            r = requests.post(f"{API}/admin/users", headers=H(S["a_tok"]), timeout=30, json={
                "name": "TEST_iter395 mover", "email": email, "role": "admin", "password": pw})
            assert r.status_code in (200, 201), r.text
            uid = r.json().get("id") or r.json().get("user", {}).get("id")
            created.append(uid)
            # clash in destination
            r = requests.post(f"{API}/admin/users", headers=H(S["b_tok"]), timeout=30, json={
                "name": "TEST_iter395 clash", "email": email, "role": "Member", "password": pw})
            assert r.status_code in (200, 201), r.text
            clash_id = r.json().get("id") or r.json().get("user", {}).get("id")
            created.append(clash_id)
            r = requests.post(f"{API}/organizations/transfer-person", headers=H(S["o_tok"]), timeout=30,
                              json={"user_id": uid, "from_org_id": ORG_A, "to_org_id": ORG_B})
            assert r.status_code == 409, r.text
            _db().users.delete_one({"id": clash_id})
            # old token, then success move
            old = _login({"identifier": email, "password": pw})["token"]
            assert requests.get(f"{API}/auth/me", headers=H(old), timeout=30).status_code == 200
            r = requests.post(f"{API}/organizations/transfer-person", headers=H(S["o_tok"]), timeout=30,
                              json={"user_id": uid, "from_org_id": ORG_A, "to_org_id": ORG_B})
            assert r.status_code == 200, r.text
            assert _db().users.find_one({"id": uid})["organization_id"] == ORG_B
            assert requests.get(f"{API}/auth/me", headers=H(old), timeout=30).status_code == 401
            st, _ = asyncio.run(_ws(uid, old))
            assert st != "open", "revoked token still opens a socket"
            new = _login({"identifier": email, "password": pw})["token"]
            for path in ("members", "events", "admin/users"):
                rr = requests.get(f"{API}/{path}", headers=H(new), timeout=30)
                assert rr.status_code == 200, (path, rr.text[:200])
                body = rr.json()
                items = body if isinstance(body, list) else next(
                    (v for v in body.values() if isinstance(v, list)), [])
                ids = [x.get("id") for x in items if isinstance(x, dict)]
                coll = {"members": "members", "events": "events", "admin/users": "users"}[path]
                leak = _db()[coll].count_documents({"id": {"$in": ids}, "organization_id": ORG_A})
                assert leak == 0, f"{path}: {leak} org A rows visible after move"
        finally:
            _db().users.delete_many({"id": {"$in": [c for c in created if c]}})


# ---------------------------------------------------------------- Branding
class TestBranding:
    def test_branding_isolated(self, S):
        marker = f"TESTX{uuid.uuid4().hex[:6]}"
        orig_a = _db().system_settings.find_one({"organization_id": ORG_A}, {"_id": 0, "branding": 1})
        try:
            r = requests.put(f"{API}/admin/system-settings", headers=H(S["b_tok"]), timeout=30, json={
                "branding": {"app_name": f"Lub {marker}", "logo_url": f"/x/{marker}.png",
                             "primary_color": "#123456", "accent_color": "#654321",
                             "login_headline": f"H {marker}", "login_subtitle": f"S {marker}",
                             "login_background": "#111111",
                             "terms": {"Member": "Resident", f"K{marker}": marker},
                             f"newkey_{marker}": marker}})
            assert r.status_code == 200, r.text
            pb = requests.get(f"{API}/admin/system-settings/public", headers=H(S["b_tok"]), timeout=30).json()
            assert pb["branding"]["login_headline"] == f"H {marker}"
            assert pb["branding"]["terms"]["Member"] == "Resident"
            for label, hdr in (("orgA", H(S["a_tok"])), ("anon", {}), ("garbage", H("bad"))):
                txt = requests.get(f"{API}/admin/system-settings/public", headers=hdr, timeout=30).text
                assert marker not in txt and "Resident" not in txt, f"{label} sees Lubwamas branding"
            full_a = requests.get(f"{API}/admin/system-settings", headers=H(S["a_tok"]), timeout=30).text
            assert marker not in full_a
            # org A saves a block it never had -> must not get B's keys
            requests.put(f"{API}/admin/system-settings", headers=H(S["a_tok"]), timeout=30,
                         json={"branding": {"tagline": ""}})
            assert marker not in json.dumps(_db().system_settings.find_one(
                {"organization_id": ORG_A}, {"_id": 0}), default=str)
        finally:
            if orig_a:
                _db().system_settings.update_one({"organization_id": ORG_A}, {"$set": {"branding": orig_a["branding"]}})

    def test_logo_upload(self, S):
        r = requests.post(f"{API}/admin/system-settings/branding/logo", headers=H(S["b_tok"]), timeout=60,
                          files={"file": ("l.png", PNG, "image/png")})
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert f"/api/storage/branding/{ORG_B}/" in url, url
        full = url if url.startswith("http") else BASE_URL + url
        g = requests.get(full, timeout=30)
        assert g.status_code == 200 and g.content[:4] == b"\x89PNG"
        r = requests.post(f"{API}/admin/system-settings/branding/logo", headers=H(S["b_tok"]), timeout=30,
                          files={"file": ("l.txt", b"hello", "text/plain")})
        assert r.status_code == 400
        r = requests.post(f"{API}/admin/system-settings/branding/logo", headers=H(S["m_tok"]), timeout=30,
                          files={"file": ("l.png", PNG, "image/png")})
        assert r.status_code == 403


# ---------------------------------------------------------------- Regression
class TestIsolationRegression:
    def test_cross_org_by_id_404(self, S):
        d = _db()
        for coll, path in (("members", "members"), ("events", "events"), ("products", "products")):
            doc = d[coll].find_one({"organization_id": ORG_A}, {"id": 1})
            if not doc:
                continue
            r = requests.get(f"{API}/{path}/{doc['id']}", headers=H(S["b_tok"]), timeout=30)
            assert r.status_code == 404, (path, r.status_code)

    def test_org_console_403_for_admin(self, S):
        assert requests.get(f"{API}/organizations", headers=H(S["a_tok"]), timeout=30).status_code == 403

    def test_admin_update_foreign_user_404(self, S):
        r = requests.put(f"{API}/admin/users/{S['a_id']}", headers=H(S["b_tok"]), timeout=30,
                         json={"name": "hijack"})
        assert r.status_code == 404


# ── iter396: one web address, one organisation ──────────────────────────────

def test_hostname_is_normalised_and_www_twin_added():
    """Whatever the owner types, the stored address is what a browser sends —
    and the www form lands in the same organisation."""
    h = H(_login(OWNER)["token"])
    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    lub = next(o for o in orgs if o["name"] == "Lubwamas")
    original = lub.get("hostnames") or []
    try:
        r = requests.put(f"{API}/organizations/{lub['id']}", headers=h, timeout=30,
                         json={"hostnames": ["https://Probe396.Lubwamas.org/"]})
        assert r.status_code == 200, r.text
        saved = r.json()["updates"]["hostnames"]
        assert "probe396.lubwamas.org" in saved
        assert "www.probe396.lubwamas.org" in saved
        for host in ("probe396.lubwamas.org", "www.probe396.lubwamas.org"):
            b = requests.get(f"{LOCAL}/api/admin/system-settings/public",
                             headers={"Host": host}, timeout=30)
            assert b.status_code == 200
    finally:
        requests.put(f"{API}/organizations/{lub['id']}", headers=h, timeout=30,
                     json={"hostnames": original})


def test_two_organisations_cannot_share_one_address():
    h = H(_login(OWNER)["token"])
    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    lub = next(o for o in orgs if o["name"] == "Lubwamas")
    other = next(o for o in orgs if o["id"] != lub["id"])
    taken = (lub.get("hostnames") or ["new.lubwamas.org"])[0]
    original = other.get("hostnames") or []
    r = requests.put(f"{API}/organizations/{other['id']}", headers=h, timeout=30,
                     json={"hostnames": [taken]})
    assert r.status_code == 409, r.text
    assert "already belongs" in r.json()["detail"]
    # and the loser's own addresses are untouched
    after = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    assert (next(o for o in after if o["id"] == other["id"]).get("hostnames") or []) == original


def test_clearing_addresses_twice_does_not_collide():
    """Two organisations with no address at all must both be allowed — the
    unique index treats an empty array as a value, so they are stored as absent."""
    h = H(_login(OWNER)["token"])
    orgs = requests.get(f"{API}/organizations", headers=h, timeout=30).json()["organizations"]
    lub = next(o for o in orgs if o["name"] == "Lubwamas")
    original = lub.get("hostnames") or []
    try:
        for _ in range(2):
            r = requests.put(f"{API}/organizations/{lub['id']}", headers=h, timeout=30,
                             json={"hostnames": []})
            assert r.status_code == 200, r.text
    finally:
        requests.put(f"{API}/organizations/{lub['id']}", headers=h, timeout=30,
                     json={"hostnames": original})


def test_signing_in_on_another_organisations_address_is_refused():
    lub_host = "new.lubwamas.org"
    wrong = requests.post(f"{LOCAL}/api/auth/login", headers={"Host": lub_host}, timeout=30,
                          json={"identifier": A_ADMIN["identifier"],
                                "password": A_ADMIN["password"]})
    assert wrong.status_code == 401, wrong.text
    right = requests.post(f"{LOCAL}/api/auth/login", headers={"Host": lub_host}, timeout=30,
                          json={"identifier": B_ADMIN["identifier"],
                                "password": B_ADMIN["password"]})
    assert right.status_code == 200, right.text
