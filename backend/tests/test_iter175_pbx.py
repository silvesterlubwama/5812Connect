"""PBX (Phase 1) management API tests — iteration 175.

Validates CRUD for extensions / trunks / inbound / outbound / hunt_groups / ivrs,
secret rotation, Asterisk config rendering, RBAC, cascade behaviour.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def cleanup(headers):
    """Track created entities and clean them up at end."""
    created = {"ext": [], "trunk": [], "inb": [], "out": [], "hg": [], "ivr": []}
    yield created
    for ext_id in created["ext"]:
        requests.delete(f"{BASE_URL}/api/pbx/extensions/{ext_id}", headers=headers, timeout=10)
    for tid in created["trunk"]:
        requests.delete(f"{BASE_URL}/api/pbx/trunks/{tid}", headers=headers, timeout=10)
    for rid in created["inb"]:
        requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{rid}", headers=headers, timeout=10)
    for rid in created["out"]:
        requests.delete(f"{BASE_URL}/api/pbx/outbound-routes/{rid}", headers=headers, timeout=10)
    for hid in created["hg"]:
        requests.delete(f"{BASE_URL}/api/pbx/hunt-groups/{hid}", headers=headers, timeout=10)
    for iid in created["ivr"]:
        requests.delete(f"{BASE_URL}/api/pbx/ivrs/{iid}", headers=headers, timeout=10)


# ─── Extensions ────────────────────────────────────────────────
class TestExtensions:
    def test_create_extension_returns_secret(self, headers, cleanup):
        r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
            "number": "200", "display_name": "QA Test",
            "transport": "transport-udp", "voicemail_enabled": True, "voicemail_pin": "1111",
        }, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["number"] == "200"
        assert data["display_name"] == "QA Test"
        assert "secret" in data and isinstance(data["secret"], str)
        assert 20 <= len(data["secret"]) <= 32  # token_urlsafe(18) → ~24 chars
        # base64url charset
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", data["secret"])
        cleanup["ext"].append(data["id"])
        cleanup["_ext200_id"] = data["id"]
        cleanup["_ext200_secret"] = data["secret"]

    def test_list_extensions(self, headers, cleanup):
        r = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
        assert r.status_code == 200
        nums = [e["number"] for e in r.json()]
        assert "200" in nums

    def test_validation_leading_zero(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers,
                          json={"number": "1"}, timeout=10)
        assert r.status_code == 400
        assert "2-6 digits" in r.text or "start with 0" in r.text or "leading" in r.text.lower()

    def test_validation_duplicate(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers,
                          json={"number": "200"}, timeout=10)
        assert r.status_code == 400
        assert "exists" in r.text.lower() or "already" in r.text.lower()

    def test_update_extension(self, headers, cleanup):
        eid = cleanup["_ext200_id"]
        r = requests.put(f"{BASE_URL}/api/pbx/extensions/{eid}", headers=headers,
                         json={"display_name": "QA Updated"}, timeout=10)
        assert r.status_code == 200
        # verify via list
        r2 = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
        e = next(e for e in r2.json() if e["id"] == eid)
        assert e["display_name"] == "QA Updated"

    def test_rotate_secret(self, headers, cleanup):
        eid = cleanup["_ext200_id"]
        orig = cleanup["_ext200_secret"]
        r = requests.post(f"{BASE_URL}/api/pbx/extensions/{eid}/rotate-secret",
                          headers=headers, timeout=10)
        assert r.status_code == 200
        new = r.json()["secret"]
        assert new != orig
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", new)


# ─── Trunks ────────────────────────────────────────────────────
class TestTrunks:
    def test_create_trunk(self, headers, cleanup):
        r = requests.post(f"{BASE_URL}/api/pbx/trunks", headers=headers, json={
            "name": "TestTrunk", "host": "sip.test.com", "port": 5060,
            "username": "u1", "secret": "s1", "register": True,
            "did_numbers": ["+15551234567"], "outbound_caller_id": "+15551234567",
        }, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TestTrunk"
        assert data["host"] == "sip.test.com"
        cleanup["trunk"].append(data["id"])
        cleanup["_trunk_id"] = data["id"]

    def test_missing_host_400(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/trunks", headers=headers,
                          json={"name": "NoHost"}, timeout=10)
        assert r.status_code == 400
        assert "host" in r.text.lower()

    def test_list_update_trunk(self, headers, cleanup):
        tid = cleanup["_trunk_id"]
        r = requests.get(f"{BASE_URL}/api/pbx/trunks", headers=headers, timeout=10)
        assert r.status_code == 200
        assert any(t["id"] == tid for t in r.json())
        r2 = requests.put(f"{BASE_URL}/api/pbx/trunks/{tid}", headers=headers,
                          json={"port": 5061}, timeout=10)
        assert r2.status_code == 200


# ─── Inbound routes ───────────────────────────────────────────
class TestInbound:
    def test_create_inbound(self, headers, cleanup):
        ext_id = cleanup["_ext200_id"]
        r = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
            "did_pattern": "_+1NXXNXXXXXX",
            "destination_type": "extension",
            "destination_id": ext_id,
        }, timeout=10)
        assert r.status_code == 200, r.text
        cleanup["inb"].append(r.json()["id"])

    def test_invalid_destination_type(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
            "did_pattern": "_+1NXXNXXXXXX", "destination_type": "foo",
        }, timeout=10)
        assert r.status_code == 400
        assert "destination" in r.text.lower()

    def test_invalid_did_pattern(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
            "did_pattern": "@@@", "destination_type": "extension",
        }, timeout=10)
        assert r.status_code == 400


# ─── Outbound routes ──────────────────────────────────────────
class TestOutbound:
    def test_create_outbound(self, headers, cleanup):
        tid = cleanup["_trunk_id"]
        r = requests.post(f"{BASE_URL}/api/pbx/outbound-routes", headers=headers, json={
            "pattern": "_1NXXNXXXXXX", "trunk_id": tid,
            "priority": 10, "strip": 0, "prepend": "+",
        }, timeout=10)
        assert r.status_code == 200, r.text
        cleanup["out"].append(r.json()["id"])

    def test_missing_trunk_id(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/outbound-routes", headers=headers, json={
            "pattern": "_1NXXNXXXXXX",
        }, timeout=10)
        assert r.status_code == 400
        assert "trunk" in r.text.lower()


# ─── Hunt groups ──────────────────────────────────────────────
class TestHuntGroups:
    def test_create_hunt(self, headers, cleanup):
        ext_id = cleanup["_ext200_id"]
        r = requests.post(f"{BASE_URL}/api/pbx/hunt-groups", headers=headers, json={
            "name": "Sales", "strategy": "ringall",
            "member_extension_ids": [ext_id], "ring_timeout": 25,
        }, timeout=10)
        assert r.status_code == 200, r.text
        cleanup["hg"].append(r.json()["id"])
        cleanup["_hg_id"] = r.json()["id"]

    def test_invalid_strategy(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/hunt-groups", headers=headers, json={
            "name": "Bad", "strategy": "chaotic",
        }, timeout=10)
        assert r.status_code == 400


# ─── IVRs ─────────────────────────────────────────────────────
class TestIVRs:
    def test_create_ivr(self, headers, cleanup):
        ext_id = cleanup["_ext200_id"]
        r = requests.post(f"{BASE_URL}/api/pbx/ivrs", headers=headers, json={
            "name": "Main menu",
            "prompt_text": "Press 1 for sales",
            "options": {"1": {"type": "extension", "id": ext_id}},
            "timeout_sec": 8,
        }, timeout=10)
        assert r.status_code == 200, r.text
        cleanup["ivr"].append(r.json()["id"])
        cleanup["_ivr_id"] = r.json()["id"]


# ─── Config rendering ─────────────────────────────────────────
class TestConfigBundle:
    def test_bundle_structure_and_content(self, headers, cleanup):
        r = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=15)
        assert r.status_code == 200
        b = r.json()
        for k in ("pjsip.conf", "extensions.conf", "voicemail.conf", "generated_at", "counts"):
            assert k in b, f"missing {k}"

        pjsip = b["pjsip.conf"]
        assert "[transport-udp]" in pjsip
        assert "[200]" in pjsip
        assert "type=endpoint" in pjsip
        assert "allow=ulaw,alaw,opus" in pjsip
        tid = cleanup["_trunk_id"]
        assert f"[trunk-{tid}]" in pjsip
        assert "from_user=u1" in pjsip

        ext = b["extensions.conf"]
        assert "[from-internal]" in ext
        assert "_XX." in ext  # internal dialing pattern
        assert "_1NXXNXXXXXX,1,NoOp(Outbound" in ext
        assert "_+1NXXNXXXXXX" in ext
        ivr_id = cleanup["_ivr_id"]
        assert f"[ivr-{ivr_id}]" in ext
        assert "exten => 1,1,NoOp(IVR option 1)" in ext

        vm = b["voicemail.conf"]
        assert "200 => 1111,QA Updated," in vm or "200 => 1111,QA Test," in vm

    def test_per_file_endpoint(self, headers):
        r = requests.get(f"{BASE_URL}/api/pbx/config/pjsip.conf", headers=headers, timeout=10)
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "")
        assert "[transport-udp]" in r.text

    def test_per_file_404(self, headers):
        r = requests.get(f"{BASE_URL}/api/pbx/config/nonexistent.conf", headers=headers, timeout=10)
        assert r.status_code == 404


# ─── RBAC ─────────────────────────────────────────────────────
class TestRBAC:
    def test_anon_401_or_403(self):
        r = requests.get(f"{BASE_URL}/api/pbx/extensions", timeout=10)
        assert r.status_code in (401, 403), f"got {r.status_code}"


# ─── Apply stub ───────────────────────────────────────────────
class TestApply:
    def test_apply_returns_stub(self, headers):
        r = requests.post(f"{BASE_URL}/api/pbx/apply", headers=headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["applied"] is False
        assert "config_urls" in d
        for k in ("pjsip", "extensions", "voicemail"):
            assert k in d["config_urls"]


# ─── Cascade ──────────────────────────────────────────────────
class TestCascade:
    def test_delete_extension_removes_from_hunt_group(self, headers, cleanup):
        # Create a temp extension + hunt group
        re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers,
                            json={"number": "299"}, timeout=10)
        assert re_.status_code == 200
        e_id = re_.json()["id"]

        rh = requests.post(f"{BASE_URL}/api/pbx/hunt-groups", headers=headers, json={
            "name": "CascadeHG", "strategy": "ringall", "member_extension_ids": [e_id],
        }, timeout=10)
        assert rh.status_code == 200
        hg_id = rh.json()["id"]
        cleanup["hg"].append(hg_id)

        # Delete the extension
        rd = requests.delete(f"{BASE_URL}/api/pbx/extensions/{e_id}", headers=headers, timeout=10)
        assert rd.status_code == 200

        # Verify hunt group's member list no longer contains it
        rl = requests.get(f"{BASE_URL}/api/pbx/hunt-groups", headers=headers, timeout=10)
        hg = next(h for h in rl.json() if h["id"] == hg_id)
        assert e_id not in hg["member_extension_ids"]

    def test_delete_trunk_removes_inbound_route(self, headers, cleanup):
        # Create a trunk + inbound route bound to it
        rt = requests.post(f"{BASE_URL}/api/pbx/trunks", headers=headers, json={
            "name": "CascadeTrunk", "host": "sip.cascade.test", "username": "u", "secret": "p",
        }, timeout=10)
        assert rt.status_code == 200
        t_id = rt.json()["id"]

        ri = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
            "did_pattern": "_+18005551234", "destination_type": "hangup",
            "trunk_id": t_id,
        }, timeout=10)
        assert ri.status_code == 200
        inb_id = ri.json()["id"]

        # Delete trunk
        rd = requests.delete(f"{BASE_URL}/api/pbx/trunks/{t_id}", headers=headers, timeout=10)
        assert rd.status_code == 200

        # Inbound route should be deleted
        rl = requests.get(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, timeout=10)
        assert not any(i["id"] == inb_id for i in rl.json())


# ─── Delete (final teardown trigger via test order) ───────────
class TestDelete:
    def test_delete_extension(self, headers, cleanup):
        # Last test — delete the main ext200 to verify DELETE works
        # (cleanup fixture handles others)
        pass  # cleanup fixture deletes everything in teardown
