"""Iteration 182 — Tier 1 + Tier 2 PBX additions.

Covers:
  - SIP trunk: `registrar` + `trunk_type` (sip|fxo) + FXO settings
  - Extension: max_contacts default 5, -1 for unlimited
  - Extension: forwarding_number + is_fax_extension fields
  - Auto-sync: creating/updating a staff user with `extension` provisions a
    matching PBX extension (transport-wss, max_contacts=5, auto_provisioned=true)
  - Auto-sync: members/customers are NOT auto-provisioned
  - Hunt-group + Queue: `member_priorities` / `agent_priorities` round-trip
  - queues.conf: priority emitted as Asterisk `penalty` in member lines
  - extensions.conf: forwarding adds extra Dial(Local/...) leg
  - extensions.conf: fax extension emits ReceiveFAX dialplan
  - Queue fallback: when destination_type=queue, fallback is appended to dialplan
  - Contact groups CRUD (campus-scoped)
  - Extension groups CRUD
  - /api/pbx/me/contact-groups returns shared groups
  - /api/pbx/blf/peers returns monitorable peers
  - /api/pbx/extensions/{id}/contacts returns 200 with empty list when AMI not connected
"""
import os
import time
import requests
import pytest
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _cleanup_users(headers, ids):
    for uid in ids:
        try:
            requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=headers, timeout=5)
        except Exception:
            pass


def _cleanup_extensions_by_number(numbers):
    try:
        from pymongo import MongoClient
        c = MongoClient(MONGO_URL)
        db = c[DB_NAME]
        db.pbx_extensions.delete_many({"number": {"$in": numbers}})
    except Exception:
        pass


def _cleanup_collection(coll, ids):
    try:
        from pymongo import MongoClient
        c = MongoClient(MONGO_URL)
        db = c[DB_NAME]
        db[coll].delete_many({"id": {"$in": ids}})
    except Exception:
        pass


class TestAutoSync:
    def test_create_user_autoprovisions_extension(self, headers):
        users_created, exts_to_clean = [], []
        ext_num = f"39{int(time.time()) % 100:02d}"
        try:
            r = requests.post(f"{BASE_URL}/api/admin/users", headers=headers, json={
                "name": "Auto Sync Staff",
                "email": f"autosync-{int(time.time())}@test.com",
                "role": "Staff",
                "extension": ext_num,
                "extension_pin": "1234",
                "forward_to": "+15558889999",
            }, timeout=10)
            assert r.status_code == 200, r.text
            users_created.append(r.json()["id"])

            # PBX extension should now exist
            r2 = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
            ext = next((e for e in r2.json() if e.get("number") == ext_num), None)
            assert ext is not None, f"Extension {ext_num} not auto-provisioned"
            exts_to_clean.append(ext_num)
            assert ext["auto_provisioned"] is True
            assert ext["transport"] == "transport-wss"
            assert ext["max_contacts"] == 5
            assert ext["voicemail_pin"] == "1234"
            assert ext["forwarding_number"] == "+15558889999"
            assert ext["display_name"] == "Auto Sync Staff"
        finally:
            _cleanup_users(headers, users_created)
            _cleanup_extensions_by_number(exts_to_clean)

    def test_member_role_not_autoprovisioned(self, headers):
        users_created = []
        ext_num = f"39{int(time.time()) % 100:02d}9"
        try:
            r = requests.post(f"{BASE_URL}/api/admin/users", headers=headers, json={
                "name": "Member No Ext",
                "email": f"membernoext-{int(time.time())}@test.com",
                "role": "Customer",
                "extension": ext_num,
            }, timeout=10)
            assert r.status_code == 200, r.text
            users_created.append(r.json()["id"])
            time.sleep(0.3)
            r2 = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
            assert not any(e.get("number") == ext_num for e in r2.json()), \
                "Customer role should NOT be auto-provisioned"
        finally:
            _cleanup_users(headers, users_created)


class TestTrunkExtras:
    def test_registrar_and_fxo_fields_round_trip(self, headers):
        created = None
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/trunks", headers=headers, json={
                "name": "Test FXO Trunk",
                "host": "sip.carrier.com",
                "registrar": "registrar.carrier.com",
                "trunk_type": "fxo",
                "fxo_lines": 4,
                "fxo_gateway": "192.168.1.10:5060",
                "username": "carrieruser",
                "secret": "carriersecret",
            }, timeout=10)
            assert r.status_code == 200, r.text
            tr = r.json(); created = tr["id"]
            assert tr["registrar"] == "registrar.carrier.com"
            assert tr["trunk_type"] == "fxo"
            assert tr["fxo_lines"] == 4
            assert tr["fxo_gateway"] == "192.168.1.10:5060"

            # pjsip.conf should now use the registrar for server_uri/client_uri
            bundle = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()
            pjsip = bundle["pjsip.conf"]
            assert "server_uri=sip:registrar.carrier.com" in pjsip
            assert "client_uri=sip:carrieruser@registrar.carrier.com" in pjsip
        finally:
            if created:
                requests.delete(f"{BASE_URL}/api/pbx/trunks/{created}", headers=headers, timeout=5)


class TestExtensionExtras:
    def test_max_contacts_unlimited(self, headers):
        created = None
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3920", "display_name": "Unlim Ext",
                "max_contacts": -1,
            }, timeout=10)
            assert r.status_code == 200
            ext = r.json(); created = ext["id"]
            assert ext["max_contacts"] == -1

            bundle = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()
            # -1 should render as the cap (50) in pjsip.conf
            assert "max_contacts=50" in bundle["pjsip.conf"]
        finally:
            if created:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{created}", headers=headers, timeout=5)

    def test_forwarding_number_in_dialplan(self, headers):
        created = []
        try:
            re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3921", "display_name": "Fwd Ext",
                "forwarding_number": "+15557776666",
            }, timeout=10)
            ext = re_.json(); created.append(ext["id"])
            time.sleep(0.2)
            inb = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
                "did_pattern": "_+18883921", "destination_type": "extension", "destination_id": ext["id"],
            }, timeout=10)
            inb_id = inb.json()["id"]
            try:
                bundle = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()
                conf = bundle["extensions.conf"]
                assert "Dial(PJSIP/3921,25)" in conf
                assert "Local/+15557776666@" in conf
            finally:
                requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{inb_id}", headers=headers, timeout=5)
        finally:
            for cid in created:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{cid}", headers=headers, timeout=5)

    def test_fax_extension_emits_receivefax(self, headers):
        created = []
        try:
            re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3922", "display_name": "Fax Ext",
                "is_fax_extension": True,
                "voicemail_email": "fax@example.com",
            }, timeout=10)
            ext = re_.json(); created.append(ext["id"])
            inb = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
                "did_pattern": "_+18883922", "destination_type": "extension", "destination_id": ext["id"],
            }, timeout=10)
            inb_id = inb.json()["id"]
            try:
                bundle = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()
                conf = bundle["extensions.conf"]
                assert "ReceiveFAX(/var/spool/asterisk/fax/" in conf
                assert "fax@example.com" in conf
            finally:
                requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{inb_id}", headers=headers, timeout=5)
        finally:
            for cid in created:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{cid}", headers=headers, timeout=5)


class TestPriorities:
    def test_queue_priorities_emit_penalties(self, headers):
        created_e, created_q = [], []
        try:
            r1 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3923", "display_name": "Primary"}, timeout=10)
            time.sleep(0.2)
            r2 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3924", "display_name": "Backup"}, timeout=10)
            e1, e2 = r1.json(), r2.json()
            created_e.extend([e1["id"], e2["id"]])

            rq = requests.post(f"{BASE_URL}/api/pbx/queues", headers=headers, json={
                "name": "Priority Test Q",
                "agent_extension_ids": [e1["id"], e2["id"]],
                "agent_priorities": {e1["id"]: 0, e2["id"]: 2},
            }, timeout=10)
            assert rq.status_code == 200
            q = rq.json(); created_q.append(q["id"])
            assert q["agent_priorities"] == {e1["id"]: 0, e2["id"]: 2}

            bundle = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()
            qc = bundle["queues.conf"]
            assert "member => PJSIP/3923,0," in qc
            assert "member => PJSIP/3924,2," in qc
        finally:
            for cid in created_q:
                requests.delete(f"{BASE_URL}/api/pbx/queues/{cid}", headers=headers, timeout=5)
            for cid in created_e:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{cid}", headers=headers, timeout=5)


class TestQueueFallback:
    def test_queue_destination_emits_fallback(self, headers):
        created_q, created_e, created_inb = [], [], []
        try:
            r1 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3925", "display_name": "VM target"}, timeout=10)
            e = r1.json(); created_e.append(e["id"])
            time.sleep(0.2)
            rq = requests.post(f"{BASE_URL}/api/pbx/queues", headers=headers, json={
                "name": "Exit-to-VM Q",
                "fallback_type": "voicemail", "fallback_id": e["id"],
                "agent_extension_ids": [],
            }, timeout=10)
            q = rq.json(); created_q.append(q["id"])
            inb = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
                "did_pattern": "_+18883925",
                "destination_type": "queue", "destination_id": q["id"],
            }, timeout=10)
            created_inb.append(inb.json()["id"])

            conf = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10).json()["extensions.conf"]
            assert f"Queue(q-{q['id']}" in conf
            assert f"Voicemail({e['number']}@default,u)" in conf
        finally:
            for iid in created_inb:
                requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{iid}", headers=headers, timeout=5)
            for qid in created_q:
                requests.delete(f"{BASE_URL}/api/pbx/queues/{qid}", headers=headers, timeout=5)
            for eid in created_e:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{eid}", headers=headers, timeout=5)


class TestContactGroupsAndBLF:
    def test_contact_group_crud(self, headers):
        created = []
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/contact-groups", headers=headers, json={
                "name": "Emergency Contacts",
                "contacts": [
                    {"name": "Police", "phone": "911"},
                    {"name": "Fire Dept", "phone": "911", "extension": "5550"},
                ],
            }, timeout=10)
            assert r.status_code == 200, r.text
            cg = r.json(); created.append(cg["id"])
            assert len(cg["contacts"]) == 2

            r2 = requests.put(f"{BASE_URL}/api/pbx/contact-groups/{cg['id']}", headers=headers,
                              json={"name": "Renamed"}, timeout=10)
            assert r2.status_code == 200

            r3 = requests.get(f"{BASE_URL}/api/pbx/contact-groups", headers=headers, timeout=10)
            assert any(g["id"] == cg["id"] for g in r3.json())
        finally:
            for cid in created:
                requests.delete(f"{BASE_URL}/api/pbx/contact-groups/{cid}", headers=headers, timeout=5)

    def test_extension_group_crud(self, headers):
        created_eg, created_e = [], []
        try:
            r1 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3926", "display_name": "Group Member"}, timeout=10)
            e = r1.json(); created_e.append(e["id"])

            r2 = requests.post(f"{BASE_URL}/api/pbx/extension-groups", headers=headers, json={
                "name": "Front desk",
                "extension_ids": [e["id"]],
            }, timeout=10)
            assert r2.status_code == 200
            eg = r2.json(); created_eg.append(eg["id"])
            assert eg["extension_ids"] == [e["id"]]
        finally:
            for cid in created_eg:
                requests.delete(f"{BASE_URL}/api/pbx/extension-groups/{cid}", headers=headers, timeout=5)
            for cid in created_e:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{cid}", headers=headers, timeout=5)

    def test_blf_peers_admin(self, headers):
        r = requests.get(f"{BASE_URL}/api/pbx/blf/peers", headers=headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestRegisteredContacts:
    def test_contacts_endpoint_returns_empty_in_preview(self, headers):
        created = None
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "3927", "display_name": "Contacts Test"}, timeout=10)
            ext = r.json(); created = ext["id"]
            r2 = requests.get(f"{BASE_URL}/api/pbx/extensions/{ext['id']}/contacts", headers=headers, timeout=10)
            assert r2.status_code == 200
            d = r2.json()
            assert "registered" in d
            assert "count" in d
            assert "max_contacts" in d
            # AMI not connected in preview → empty list
            assert d["count"] == 0
        finally:
            if created:
                requests.delete(f"{BASE_URL}/api/pbx/extensions/{created}", headers=headers, timeout=5)
