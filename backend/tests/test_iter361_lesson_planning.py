"""iter361 — outreach lesson planning end to end.

Creates a sample outreach event, plans it, checks the libraries grow, duplicates
the plan onto a second event and raises a purchase order from the snacks list.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
LP = f"{API}/lesson-planning"


@pytest.fixture(scope="module")
def hdr():
    r = requests.post(f"{API}/auth/login", json={"identifier": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _mk_event(hdr, title, days_ahead, etype="outreach"):
    date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).date().isoformat()
    r = requests.post(f"{API}/events", headers=hdr, timeout=30, json={
        "title": title, "type": etype, "date": date, "time": "09:00", "end_time": "12:00",
        "location": "Kampala field", "description": "iter361 sample outreach",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(scope="module")
def events(hdr):
    tag = uuid.uuid4().hex[:5]
    a = _mk_event(hdr, f"Kids Club outreach {tag}", 3)
    b = _mk_event(hdr, f"Kids Club outreach {tag} (next week)", 10)
    meeting = _mk_event(hdr, f"Staff meeting {tag}", 4, etype="meeting")
    return {"a": a, "b": b, "meeting": meeting}


def test_theme_crud(hdr):
    r = requests.post(f"{LP}/themes", headers=hdr, timeout=30, json={
        "year": 2026, "name": f"Rooted {uuid.uuid4().hex[:4]}", "scripture": "Col 2:7",
        "topics": [{"period": "2026-07", "title": "Who is Jesus", "memory_verse": "John 14:6"}],
    })
    assert r.status_code == 200, r.text
    theme = r.json()
    assert theme["topics"][0]["title"] == "Who is Jesus"

    r = requests.get(f"{LP}/themes", headers=hdr, timeout=30)
    assert r.status_code == 200
    assert any(t["id"] == theme["id"] for t in r.json()["themes"])

    r = requests.put(f"{LP}/themes/{theme['id']}", headers=hdr, timeout=30, json={"scripture": "Colossians 2:7"})
    assert r.status_code == 200 and r.json()["scripture"] == "Colossians 2:7"

    assert requests.post(f"{LP}/themes", headers=hdr, timeout=30, json={"name": "  "}).status_code == 400
    pytest.theme_id = theme["id"]


def test_outreach_events_listing(hdr, events):
    r = requests.get(f"{LP}/outreach-events", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in r.json()["events"]]
    assert events["a"]["id"] in ids
    assert events["meeting"]["id"] not in ids, "non-outreach events must not be offered"


def test_plan_lifecycle(hdr, events):
    # a plan needs an event, and the event must be outreach
    assert requests.post(f"{LP}/plans", headers=hdr, timeout=30, json={}).status_code == 400
    assert requests.post(f"{LP}/plans", headers=hdr, timeout=30,
                         json={"event_id": events["meeting"]["id"]}).status_code == 400

    r = requests.post(f"{LP}/plans", headers=hdr, timeout=30, json={"event_id": events["a"]["id"]})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["event_title"] == events["a"]["title"]
    assert plan["date"] == events["a"]["date"]
    assert plan["status"] == "draft"

    # one plan per event
    assert requests.post(f"{LP}/plans", headers=hdr, timeout=30,
                         json={"event_id": events["a"]["id"]}).status_code == 400

    body = {
        **plan,
        "theme_id": getattr(pytest, "theme_id", ""),
        "theme_name": "Rooted",
        "topic_title": "Jesus feeds the 5000",
        "memory_verse": "John 6:35",
        "attendance_target": 80,
        "slots": [
            {"start": "09:00", "duration_min": 15, "title": "Welcome & register", "kind": "welcome",
             "leader_name": "Grace N"},
            {"start": "09:15", "duration_min": 20, "title": "Worship", "kind": "worship"},
            {"start": "09:35", "duration_min": 25, "title": "Story", "kind": "story"},
            {"start": "10:00", "duration_min": 10, "title": "Offering", "kind": "offering"},
        ],
        "songs": [{"name": "Tukutendereza Yesu", "key": "G"}, {"name": "Yesu Ali Nange", "key": "C"}],
        "games": [{"name": "Sack race", "age_range": "6-12", "duration_min": 15, "kit": "4 sacks"}],
        "story": {"title": "Feeding the 5000", "passage": "John 6:1-14",
                  "main_point": "Jesus provides", "questions": ["What did the boy give?"]},
        "snacks": [{"item": "Bananas", "servings": 80, "who": "Sarah", "cost": 40000}],
        "materials": [{"item": "Crayons", "cost": 15000}],
        "offering": {"planned": True, "purpose": "School fees fund", "target": 50000},
        "take_home": "Memory verse card",
    }
    r = requests.put(f"{LP}/plans/{plan['id']}", headers=hdr, timeout=30, json=body)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert len(saved["slots"]) == 4
    assert all(s["id"] for s in saved["slots"]), "every slot gets an id"
    assert saved["attendance_target"] == 80
    assert saved["offering"]["planned"] is True

    # typed songs/games are remembered in the libraries
    songs = requests.get(f"{LP}/library/songs", headers=hdr, timeout=30).json()["songs"]
    assert any(s["name"] == "Tukutendereza Yesu" for s in songs)
    games = requests.get(f"{LP}/library/games", headers=hdr, timeout=30).json()["games"]
    assert any(g["name"] == "Sack race" for g in games)

    # library search + idempotent add
    r = requests.get(f"{LP}/library/songs?q=tukuten", headers=hdr, timeout=30)
    assert r.status_code == 200 and len(r.json()["songs"]) >= 1
    again = requests.post(f"{LP}/library/songs", headers=hdr, timeout=30,
                          json={"name": "tukutendereza yesu"})
    assert again.status_code == 200
    assert again.json()["name"] == "Tukutendereza Yesu", "same song twice is a no-op"
    assert requests.post(f"{LP}/library/songs", headers=hdr, timeout=30, json={"name": ""}).status_code == 400
    assert requests.get(f"{LP}/library/nope", headers=hdr, timeout=30).status_code == 404

    # the event list now shows the plan
    listing = requests.get(f"{LP}/outreach-events", headers=hdr, timeout=30).json()["events"]
    row = next(e for e in listing if e["id"] == events["a"]["id"])
    assert row["plan_id"] == plan["id"]
    assert row["plan_topic"] == "Jesus feeds the 5000"

    pytest.plan_id = plan["id"]


def test_purchase_order_from_plan(hdr):
    r = requests.post(f"{LP}/plans/{pytest.plan_id}/purchase-order", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["lines"] == 2
    assert out["total"] == 55000
    assert out["purchase_order"]["po_number"].startswith("PO-")
    po_id = out["purchase_order"]["id"]
    detail = requests.get(f"{API}/purchase-orders/{po_id}", headers=hdr, timeout=30)
    assert detail.status_code == 200, detail.text


def test_duplicate_plan(hdr, events):
    assert requests.post(f"{LP}/plans/{pytest.plan_id}/duplicate", headers=hdr,
                         timeout=30, json={}).status_code == 400
    assert requests.post(f"{LP}/plans/{pytest.plan_id}/duplicate", headers=hdr, timeout=30,
                         json={"event_id": events["meeting"]["id"]}).status_code == 400

    r = requests.post(f"{LP}/plans/{pytest.plan_id}/duplicate", headers=hdr, timeout=30,
                      json={"event_id": events["b"]["id"]})
    assert r.status_code == 200, r.text
    copy = r.json()
    assert copy["id"] != pytest.plan_id
    assert copy["event_id"] == events["b"]["id"]
    assert copy["date"] == events["b"]["date"]
    assert copy["status"] == "draft"
    assert copy["copied_from"] == pytest.plan_id
    assert len(copy["slots"]) == 4
    assert copy["topic_title"] == "Jesus feeds the 5000"

    # can't copy onto an event that already has one
    assert requests.post(f"{LP}/plans/{pytest.plan_id}/duplicate", headers=hdr, timeout=30,
                         json={"event_id": events["b"]["id"]}).status_code == 400
    pytest.copy_id = copy["id"]


def test_my_slots_and_delete(hdr):
    r = requests.get(f"{LP}/my-slots?days=30", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["slots"], list)

    r = requests.get(f"{LP}/plans?event_id=", headers=hdr, timeout=30)
    assert r.status_code == 200 and r.json()["count"] >= 2

    assert requests.get(f"{LP}/plans/nope", headers=hdr, timeout=30).status_code == 404

    r = requests.delete(f"{LP}/plans/{pytest.copy_id}", headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    assert requests.get(f"{LP}/plans/{pytest.copy_id}", headers=hdr, timeout=30).status_code == 404


def test_requires_auth():
    assert requests.get(f"{LP}/themes", timeout=30).status_code == 401
    assert requests.get(f"{LP}/outreach-events", timeout=30).status_code == 401
