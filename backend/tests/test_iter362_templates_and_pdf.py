"""iter362 — plan templates + run-sheet PDF / email to leaders."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
LP = f"{API}/lesson-planning"
EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
TAG = "iter362 template test"


@pytest.fixture(scope="module")
def hdr():
    r = requests.post(f"{API}/auth/login", json={"identifier": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _event(hdr, days_ahead, etype="outreach"):
    date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).date().isoformat()
    r = requests.post(f"{API}/events", headers=hdr, timeout=30, json={
        "title": f"Outreach {uuid.uuid4().hex[:5]}", "type": etype, "date": date,
        "time": "09:00", "end_time": "12:00", "description": TAG,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(scope="module")
def planned(hdr):
    """A fully filled plan on its own event, plus a spare empty event."""
    ev = _event(hdr, 5)
    spare = _event(hdr, 12)
    plan = requests.post(f"{LP}/plans", headers=hdr, timeout=30, json={"event_id": ev["id"]}).json()
    me = requests.get(f"{API}/auth/me", headers=hdr, timeout=30).json()
    body = {
        **plan,
        "topic_title": "Jesus calms the storm",
        "memory_verse": "Mark 4:39",
        "theme_name": "Rooted in Christ",
        "attendance_target": 60,
        "slots": [
            {"start": "09:00", "duration_min": 15, "title": "Welcome", "kind": "welcome",
             "leader_id": me["id"], "leader_name": me.get("name") or "Admin", "notes": "Register everyone"},
            {"start": "09:15", "duration_min": 20, "title": "Worship", "kind": "worship"},
        ],
        "songs": [{"name": "Tukutendereza Yesu", "key": "G"}],
        "games": [{"name": "Sack race", "age_range": "6-12", "kit": "4 sacks"}],
        "story": {"title": "The storm", "passage": "Mark 4:35-41", "main_point": "Jesus is Lord over fear",
                  "questions": ["When are you afraid?"]},
        "snacks": [{"item": "Bananas", "servings": 60, "who": "Sarah", "cost": 30000}],
        "materials": [{"item": "Crayons", "cost": 10000}],
        "offering": {"planned": True, "purpose": "School fees", "target": 40000},
        "take_home": "Verse card",
        "notes_after": "Ran 10 minutes long",
    }
    plan = requests.put(f"{LP}/plans/{plan['id']}", headers=hdr, timeout=30, json=body).json()
    return {"plan": plan, "event": ev, "spare": spare, "me": me}


def test_run_sheet_pdf(hdr, planned):
    r = requests.get(f"{LP}/plans/{planned['plan']['id']}/run-sheet.pdf", headers=hdr, timeout=60)
    assert r.status_code == 200, r.text[:400]
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF", "must be a real PDF, not an HTML fallback"
    assert len(r.content) > 3000, "a one-page run sheet should not be near-empty"

    assert requests.get(f"{LP}/plans/nope/run-sheet.pdf", headers=hdr, timeout=30).status_code == 404
    assert requests.get(f"{LP}/plans/{planned['plan']['id']}/run-sheet.pdf", timeout=30).status_code == 401


def test_run_sheet_pdf_survives_an_empty_plan(hdr):
    ev = _event(hdr, 6)
    plan = requests.post(f"{LP}/plans", headers=hdr, timeout=30, json={"event_id": ev["id"]}).json()
    r = requests.get(f"{LP}/plans/{plan['id']}/run-sheet.pdf", headers=hdr, timeout=60)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_email_run_sheet(hdr, planned):
    r = requests.post(f"{LP}/plans/{planned['plan']['id']}/email-run-sheet", headers=hdr, timeout=90, json={})
    # Admin has an email address, so there IS a recipient; whether Resend accepts
    # it depends on the configured key, so both sent and failed are valid.
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["filename"].endswith(".pdf")
    assert len(out["sent"]) + len(out["failed"]) >= 1
    assert isinstance(out["no_email"], list)

    # a plan with no leaders at all is refused with a useful message
    ev = _event(hdr, 7)
    bare = requests.post(f"{LP}/plans", headers=hdr, timeout=30, json={"event_id": ev["id"]}).json()
    r = requests.post(f"{LP}/plans/{bare['id']}/email-run-sheet", headers=hdr, timeout=30, json={})
    assert r.status_code == 400
    assert "leader" in r.json()["detail"].lower()

    # extra addresses are accepted even with no leaders assigned
    r = requests.post(f"{LP}/plans/{bare['id']}/email-run-sheet", headers=hdr, timeout=90,
                      json={"extra_emails": ["volunteer@example.test"]})
    assert r.status_code == 200, r.text
    assert len(r.json()["sent"]) + len(r.json()["failed"]) == 1


def test_save_as_template(hdr, planned):
    name = f"Saturday club {uuid.uuid4().hex[:5]}"
    r = requests.post(f"{LP}/templates", headers=hdr, timeout=30,
                      json={"plan_id": planned["plan"]["id"], "name": name, "description": "Our usual shape"})
    assert r.status_code == 200, r.text
    tpl = r.json()
    snap = tpl["plan"]
    # content is kept
    assert snap["topic_title"] == "Jesus calms the storm"
    assert len(snap["slots"]) == 2
    assert snap["songs"][0]["name"] == "Tukutendereza Yesu"
    assert snap["games"][0]["name"] == "Sack race"
    assert snap["snacks"][0]["item"] == "Bananas"
    assert snap["story"]["passage"] == "Mark 4:35-41"
    assert snap["offering"]["planned"] is True
    # event, date, after-notes and leaders are NOT
    for gone in ("event_id", "event_title", "date", "notes_after", "id", "created_at"):
        assert gone not in snap, f"{gone} must not be stored on a template"
    assert all(not s["leader_id"] and not s["leader_name"] for s in snap["slots"]), \
        "leaders change every week — they must be cleared"

    assert requests.post(f"{LP}/templates", headers=hdr, timeout=30,
                         json={"plan_id": planned["plan"]["id"], "name": "  "}).status_code == 400
    assert requests.post(f"{LP}/templates", headers=hdr, timeout=30,
                         json={"plan_id": planned["plan"]["id"], "name": name}).status_code == 400, \
        "duplicate template names are rejected"
    assert requests.post(f"{LP}/templates", headers=hdr, timeout=30,
                         json={"plan_id": "nope", "name": "x"}).status_code == 404

    listing = requests.get(f"{LP}/templates", headers=hdr, timeout=30).json()
    row = next(t for t in listing["templates"] if t["id"] == tpl["id"])
    assert row["slot_count"] == 2 and row["song_count"] == 1 and row["game_count"] == 1
    pytest.tpl_id = tpl["id"]
    pytest.tpl_name = name


def test_start_a_plan_from_a_template(hdr, planned):
    r = requests.post(f"{LP}/plans", headers=hdr, timeout=30,
                      json={"event_id": planned["spare"]["id"], "template_id": pytest.tpl_id})
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["event_id"] == planned["spare"]["id"]
    assert fresh["event_title"] == planned["spare"]["title"]
    assert fresh["date"] == planned["spare"]["date"], "the new plan takes the new event's date"
    assert fresh["topic_title"] == "Jesus calms the storm"
    assert len(fresh["slots"]) == 2
    assert all(not s["leader_name"] for s in fresh["slots"])
    assert fresh["notes_after"] == ""
    assert fresh["status"] == "draft"
    assert fresh["from_template_id"] == pytest.tpl_id

    used = next(t for t in requests.get(f"{LP}/templates", headers=hdr, timeout=30).json()["templates"]
                if t["id"] == pytest.tpl_id)
    assert used["used_count"] == 1

    ev = _event(hdr, 9)
    assert requests.post(f"{LP}/plans", headers=hdr, timeout=30,
                         json={"event_id": ev["id"], "template_id": "nope"}).status_code == 404


def test_start_from_template_with_an_empty_slots_array(hdr):
    """The UI used to post `slots: []` alongside template_id, which wiped the
    template's running order. An empty list must never clobber the template."""
    ev = _event(hdr, 14)
    r = requests.post(f"{LP}/plans", headers=hdr, timeout=30,
                      json={"event_id": ev["id"], "template_id": pytest.tpl_id,
                            "slots": [], "songs": [], "games": [], "snacks": []})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert len(plan["slots"]) == 2, "slots must come from the template"
    assert plan["songs"] and plan["games"] and plan["snacks"]


def test_rename_and_delete_template(hdr):
    new_name = f"{pytest.tpl_name} v2"
    r = requests.put(f"{LP}/templates/{pytest.tpl_id}", headers=hdr, timeout=30, json={"name": new_name})
    assert r.status_code == 200 and r.json()["name"] == new_name
    assert requests.put(f"{LP}/templates/{pytest.tpl_id}", headers=hdr, timeout=30, json={}).status_code == 400
    assert requests.put(f"{LP}/templates/nope", headers=hdr, timeout=30,
                        json={"name": "x"}).status_code == 404

    r = requests.delete(f"{LP}/templates/{pytest.tpl_id}", headers=hdr, timeout=30)
    assert r.status_code == 200
    assert requests.delete(f"{LP}/templates/{pytest.tpl_id}", headers=hdr, timeout=30).status_code == 404


def test_templates_require_auth():
    assert requests.get(f"{LP}/templates", timeout=30).status_code == 401
