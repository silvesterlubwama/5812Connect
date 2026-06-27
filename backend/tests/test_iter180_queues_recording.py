"""Iteration 180 — Call recording + queues + skill-based routing.

Covers:
  - GET/PUT /api/pbx/recording-settings (retention, format, stereo, announce)
  - Per-extension `recording_enabled` + `skills` fields (create/update/round-trip)
  - Queues CRUD: /api/pbx/queues
  - Inbound routes accepting destination_type=queue
  - Dialplan rendering: MixMonitor on recording-enabled extensions
  - queues.conf rendering with skill-based agent filtering
  - POST /api/pbx/cdr/{call_id}/recording attaches a URL
  - POST /api/pbx/recording-retention/purge unlinks old recordings
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


def _cleanup_extensions(headers, ext_ids):
    for eid in ext_ids:
        try:
            requests.delete(f"{BASE_URL}/api/pbx/extensions/{eid}", headers=headers, timeout=5)
        except Exception:
            pass


def _cleanup_queues(headers, q_ids):
    for qid in q_ids:
        try:
            requests.delete(f"{BASE_URL}/api/pbx/queues/{qid}", headers=headers, timeout=5)
        except Exception:
            pass


def _cleanup_cdr(call_ids):
    try:
        from pymongo import MongoClient
        c = MongoClient(MONGO_URL)
        db = c[DB_NAME]
        db.pbx_cdr.delete_many({"id": {"$in": call_ids}})
    except Exception:
        pass


class TestRecordingSettings:
    def test_get_defaults(self, headers):
        r = requests.get(f"{BASE_URL}/api/pbx/recording-settings", headers=headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert {"retention_days", "storage_path", "format", "stereo", "announce_recording"}.issubset(d.keys())

    def test_put_and_round_trip(self, headers):
        body = {"retention_days": 45, "format": "wav49", "stereo": False, "announce_recording": True,
                "storage_path": "/tmp/rec-test"}
        r = requests.put(f"{BASE_URL}/api/pbx/recording-settings", headers=headers, json=body, timeout=10)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/pbx/recording-settings", headers=headers, timeout=10)
        d = r2.json()
        assert d["retention_days"] == 45
        assert d["format"] == "wav49"
        assert d["stereo"] is False
        assert d["announce_recording"] is True
        assert d["storage_path"] == "/tmp/rec-test"
        # Restore defaults so other tests aren't impacted
        requests.put(f"{BASE_URL}/api/pbx/recording-settings", headers=headers, json={
            "retention_days": 30, "format": "wav", "stereo": True, "announce_recording": False,
        }, timeout=10)

    def test_put_bad_format_rejected(self, headers):
        r = requests.put(f"{BASE_URL}/api/pbx/recording-settings", headers=headers,
                         json={"retention_days": 30, "format": "mp3"}, timeout=10)
        assert r.status_code == 400


class TestExtensionRecordingAndSkills:
    def test_create_with_recording_and_skills(self, headers):
        created = []
        try:
            r = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1981", "display_name": "Test rec ext",
                "recording_enabled": True, "skills": ["spanish", "tier-2"],
            }, timeout=10)
            assert r.status_code == 200, r.text
            ext = r.json()
            created.append(ext["id"])
            assert ext["recording_enabled"] is True
            assert ext["skills"] == ["spanish", "tier-2"]

            # PUT updates skills + recording flag
            r2 = requests.put(f"{BASE_URL}/api/pbx/extensions/{ext['id']}", headers=headers,
                              json={"recording_enabled": False, "skills": ["spanish"]}, timeout=10)
            assert r2.status_code == 200
            # Re-fetch
            r3 = requests.get(f"{BASE_URL}/api/pbx/extensions", headers=headers, timeout=10)
            target = next((e for e in r3.json() if e["id"] == ext["id"]), None)
            assert target is not None
            assert target["recording_enabled"] is False
            assert target["skills"] == ["spanish"]
        finally:
            _cleanup_extensions(headers, created)


class TestQueuesCRUD:
    def test_full_lifecycle(self, headers):
        created_q, created_e = [], []
        try:
            # Seed an extension with a skill
            re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1982", "display_name": "Sales Spanish",
                "skills": ["spanish", "sales"],
            }, timeout=10)
            assert re_.status_code == 200
            ext = re_.json(); created_e.append(ext["id"])

            # Create queue
            rq = requests.post(f"{BASE_URL}/api/pbx/queues", headers=headers, json={
                "name": "Spanish Sales", "strategy": "ringall",
                "required_skills": ["spanish"], "agent_extension_ids": [ext["id"]],
                "ring_timeout": 25, "max_wait": 90,
            }, timeout=10)
            assert rq.status_code == 200, rq.text
            q = rq.json(); created_q.append(q["id"])
            assert q["strategy"] == "ringall"
            assert q["required_skills"] == ["spanish"]
            assert q["agent_extension_ids"] == [ext["id"]]

            # List
            r_list = requests.get(f"{BASE_URL}/api/pbx/queues", headers=headers, timeout=10)
            assert any(x["id"] == q["id"] for x in r_list.json())

            # Update strategy + skills
            ru = requests.put(f"{BASE_URL}/api/pbx/queues/{q['id']}", headers=headers, json={
                "strategy": "leastrecent", "required_skills": ["spanish", "sales"],
            }, timeout=10)
            assert ru.status_code == 200

            # Bad strategy 400
            r_bad = requests.put(f"{BASE_URL}/api/pbx/queues/{q['id']}", headers=headers,
                                  json={"strategy": "bogus"}, timeout=10)
            assert r_bad.status_code == 400
        finally:
            _cleanup_queues(headers, created_q)
            _cleanup_extensions(headers, created_e)

    def test_inbound_route_accepts_queue_destination(self, headers):
        created_q, created_inb, created_e = [], [], []
        try:
            re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1983", "display_name": "Q dest test"}, timeout=10)
            assert re_.status_code == 200
            created_e.append(re_.json()["id"])

            rq = requests.post(f"{BASE_URL}/api/pbx/queues", headers=headers, json={
                "name": "Main support",
                "agent_extension_ids": [re_.json()["id"]],
            }, timeout=10)
            assert rq.status_code == 200
            q = rq.json(); created_q.append(q["id"])

            r_inb = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
                "did_pattern": "_+18005551983",
                "destination_type": "queue", "destination_id": q["id"],
            }, timeout=10)
            assert r_inb.status_code == 200, r_inb.text
            created_inb.append(r_inb.json()["id"])
        finally:
            for inb_id in created_inb:
                requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{inb_id}", headers=headers, timeout=5)
            _cleanup_queues(headers, created_q)
            _cleanup_extensions(headers, created_e)


class TestDialplanRendering:
    def test_mixmonitor_emitted_for_recording_extension(self, headers):
        created = []
        try:
            re_ = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1984", "display_name": "Rec ext",
                "recording_enabled": True,
            }, timeout=10)
            assert re_.status_code == 200
            ext = re_.json(); created.append(ext["id"])

            # Create an inbound route that points to this extension so dest_dial is rendered
            r_inb = requests.post(f"{BASE_URL}/api/pbx/inbound-routes", headers=headers, json={
                "did_pattern": "_+18885551984",
                "destination_type": "extension", "destination_id": ext["id"],
            }, timeout=10)
            inb_id = r_inb.json()["id"]
            try:
                r = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10)
                conf = r.json()["extensions.conf"]
                assert "MixMonitor(" in conf, "MixMonitor not emitted for recording-enabled extension"
                assert f"Dial(PJSIP/{ext['number']},25)" in conf
            finally:
                requests.delete(f"{BASE_URL}/api/pbx/inbound-routes/{inb_id}", headers=headers, timeout=5)
        finally:
            _cleanup_extensions(headers, created)

    def test_queues_conf_skill_filtering(self, headers):
        created_q, created_e = [], []
        try:
            # Two extensions: one with the skill, one without
            r1 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1985", "display_name": "Has skill",
                "skills": ["spanish"],
            }, timeout=10)
            assert r1.status_code == 200, f"r1 status={r1.status_code} body={r1.text}"
            time.sleep(0.2)
            r2 = requests.post(f"{BASE_URL}/api/pbx/extensions", headers=headers, json={
                "number": "1986", "display_name": "No skill",
                "skills": [],
            }, timeout=10)
            assert r2.status_code == 200, f"r2 status={r2.status_code} body={r2.text}"
            ext1, ext2 = r1.json(), r2.json()
            created_e.extend([ext1["id"], ext2["id"]])

            rq = requests.post(f"{BASE_URL}/api/pbx/queues", headers=headers, json={
                "name": "Skill filtered q",
                "required_skills": ["spanish"],
                "agent_extension_ids": [ext1["id"], ext2["id"]],
            }, timeout=10)
            q = rq.json(); created_q.append(q["id"])

            r = requests.get(f"{BASE_URL}/api/pbx/config-bundle", headers=headers, timeout=10)
            queues_conf = r.json().get("queues.conf", "")
            # Only ext1 should appear as a member because ext2 lacks the skill
            assert f"member => PJSIP/{ext1['number']}" in queues_conf
            assert f"member => PJSIP/{ext2['number']}" not in queues_conf
        finally:
            _cleanup_queues(headers, created_q)
            _cleanup_extensions(headers, created_e)


class TestRecordingAttach:
    def test_attach_url_and_purge(self, headers):
        call_id = f"rec-{int(time.time()*1000)}"
        try:
            # Seed a CDR row that's "old" (we'll backdate via Mongo)
            requests.post(f"{BASE_URL}/api/pbx/cdr/log", headers=headers, json={
                "call_id": call_id, "direction": "outgoing", "peer": "+15551001984",
                "duration_sec": 30, "status": "completed",
            }, timeout=10).raise_for_status()

            # Attach a recording URL
            r = requests.post(f"{BASE_URL}/api/pbx/cdr/{call_id}/recording", headers=headers,
                              json={"recording_url": "https://example.com/rec1.wav"}, timeout=10)
            assert r.status_code == 200
            # Confirm it's set
            cdr_rows = requests.get(f"{BASE_URL}/api/pbx/cdr/me?limit=50", headers=headers, timeout=10).json()
            row = next((x for x in cdr_rows if x["id"] == call_id), None)
            assert row and row.get("recording_url") == "https://example.com/rec1.wav"

            # Now backdate the row & purge
            from pymongo import MongoClient
            c = MongoClient(MONGO_URL)
            db = c[DB_NAME]
            db.pbx_cdr.update_one({"id": call_id}, {"$set": {"started_at": "2000-01-01T00:00:00+00:00"}})

            r2 = requests.post(f"{BASE_URL}/api/pbx/recording-retention/purge", headers=headers, timeout=10)
            assert r2.status_code == 200
            assert r2.json()["purged"] >= 1

            cdr_rows2 = requests.get(f"{BASE_URL}/api/pbx/cdr/me?limit=50", headers=headers, timeout=10).json()
            row2 = next((x for x in cdr_rows2 if x["id"] == call_id), None)
            assert row2 is not None
            assert not row2.get("recording_url")
        finally:
            _cleanup_cdr([call_id])

    def test_attach_400_when_url_missing(self, headers):
        # Even on a non-existent CDR, missing body should 400 (we validate before the find)
        r = requests.post(f"{BASE_URL}/api/pbx/cdr/non-existent/recording", headers=headers,
                          json={}, timeout=10)
        assert r.status_code == 400
