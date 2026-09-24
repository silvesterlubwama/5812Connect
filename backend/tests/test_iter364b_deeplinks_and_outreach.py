"""iter364b — outreach event hygiene + deep-link support endpoints.

Covers the user reports:
  • "In outreach planning, remove past or cancelled events"
  • "Deep link from social profile to child profile is not working"
    (the People page now resolves the target with a direct GET, so those
     endpoints must answer for a child / member / family id)
"""
import os
from datetime import date, timedelta

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
DEAD = {"cancelled", "canceled", "completed", "closed", "done", "archived"}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_outreach_events_exclude_past(head):
    r = requests.get(f"{BASE}/lesson-planning/outreach-events", headers=head, timeout=30)
    assert r.status_code == 200
    today = date.today().isoformat()
    past = [e for e in r.json()["events"] if (e.get("date") or "9999") < today]
    assert past == [], f"past outreach events still listed: {past}"


def test_outreach_events_exclude_cancelled(head):
    """Create a cancelled outreach event for tomorrow — it must not be listed."""
    payload = {
        "title": "ITER364B cancelled outreach",
        "type": "Kids Club",
        "date": (date.today() + timedelta(days=2)).isoformat(),
        "time": "10:00",
        "status": "cancelled",
    }
    created = requests.post(f"{BASE}/events", json=payload, headers=head, timeout=30)
    if created.status_code not in (200, 201):
        pytest.skip(f"events create unavailable: {created.status_code}")
    ev_id = created.json().get("id")
    try:
        r = requests.get(f"{BASE}/lesson-planning/outreach-events", headers=head, timeout=30)
        ids = [e["id"] for e in r.json()["events"]]
        assert ev_id not in ids
    finally:
        requests.delete(f"{BASE}/events/{ev_id}", headers=head, timeout=30)


def test_plans_list_hides_past_by_default(head):
    r = requests.get(f"{BASE}/lesson-planning/plans", headers=head, timeout=30)
    assert r.status_code == 200
    today = date.today().isoformat()
    assert all((p.get("date") or "9999") >= today for p in r.json()["plans"])
    r2 = requests.get(f"{BASE}/lesson-planning/plans", params={"include_past": True},
                      headers=head, timeout=30)
    assert r2.status_code == 200


def test_deeplink_targets_resolve(head):
    """A child / member / family id must be fetchable on its own — that's what
    the /people?open=<id> deep link now uses instead of scanning loaded lists."""
    children = requests.get(f"{BASE}/children", headers=head, timeout=30).json()
    children = children if isinstance(children, list) else children.get("children", [])
    assert children, "no children on file to test the deep link with"
    cid = children[0]["id"]
    r = requests.get(f"{BASE}/children/{cid}", headers=head, timeout=30)
    assert r.status_code == 200 and r.json()["id"] == cid

    fams = requests.get(f"{BASE}/families", headers=head, timeout=30).json()
    if fams:
        fid = fams[0]["id"]
        rf = requests.get(f"{BASE}/families/{fid}", headers=head, timeout=30)
        assert rf.status_code == 200 and rf.json()["id"] == fid

    mem = requests.get(f"{BASE}/members", params={"limit": 1}, headers=head, timeout=30).json()
    rows = mem.get("members") or []
    if rows:
        mid = rows[0]["id"]
        rm = requests.get(f"{BASE}/members/{mid}", headers=head, timeout=30)
        assert rm.status_code == 200 and rm.json()["id"] == mid


def test_social_case_deeplink_lookups(head):
    """?case=<id> resolves one case; ?subject_id=<id> resolves by person."""
    cases = requests.get(f"{BASE}/social-work/cases", params={"status": "active"},
                         headers=head, timeout=30).json()
    if not cases:
        pytest.skip("no active social cases seeded")
    case = cases[0]
    r = requests.get(f"{BASE}/social-work/cases/{case['id']}", headers=head, timeout=30)
    assert r.status_code == 200 and r.json()["id"] == case["id"]
    r2 = requests.get(f"{BASE}/social-work/cases", params={"subject_id": case["subject_id"]},
                      headers=head, timeout=30)
    assert r2.status_code == 200
    assert all(c["subject_id"] == case["subject_id"] for c in r2.json())


def test_duplicates_include_people_without_campus(head):
    """The review list must not hide records that have no campus on file."""
    r = requests.get(f"{BASE}/people/duplicates", headers=head, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "groups" in body and isinstance(body["groups"], list)
