"""iter385 — private events redact to 'Busy' for uninvited staff, and
passcode-gated whole-calendar share links."""
import os
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
MEMBER = {"identifier": "member@5812uganda.org", "password": "Member@5812"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_private_event_is_redacted_for_uninvited_staff():
    admin = _login(ADMIN)
    ev = requests.post(f"{API}/events", json={
        "title": "Confidential leadership review",
        "type": "meeting", "date": "2027-03-11", "time": "10:00", "end_time": "11:00",
        "visibility": "private", "invitee_ids": [],
    }, headers=_h(admin), timeout=30)
    assert ev.status_code == 200, ev.text
    eid = ev.json()["id"]
    try:
        # The creator still sees everything.
        mine = requests.get(f"{API}/events", headers=_h(admin), timeout=30).json()
        row = next((e for e in mine if e["id"] == eid), None)
        assert row and row["title"] == "Confidential leadership review"

        # Another staff account only gets an opaque slot-blocking stub.
        other = _login(MEMBER)
        theirs = requests.get(f"{API}/events", headers=_h(other), timeout=30).json()
        stub = next((e for e in theirs if e["id"] == eid), None)
        if stub is not None:          # campus scope may hide it entirely
            assert stub["title"] == "Busy"
            assert stub["private_blocked"] is True
            assert "description" not in stub
            assert stub["time"] == "10:00"      # still blocks availability

        # Direct fetch is refused rather than leaking the detail.
        detail = requests.get(f"{API}/events/{eid}", headers=_h(other), timeout=30)
        assert detail.status_code == 403, detail.text
    finally:
        requests.delete(f"{API}/events/{eid}", headers=_h(admin), timeout=30)


def test_private_event_visible_to_invited_guest():
    admin = _login(ADMIN)
    member_tok = _login(MEMBER)
    me = requests.get(f"{API}/auth/me", headers=_h(member_tok), timeout=30).json()
    ev = requests.post(f"{API}/events", json={
        "title": "Invited-only sync", "type": "meeting", "date": "2027-03-12",
        "visibility": "private", "invitee_ids": [me["id"]],
    }, headers=_h(admin), timeout=30)
    eid = ev.json()["id"]
    try:
        detail = requests.get(f"{API}/events/{eid}", headers=_h(member_tok), timeout=30)
        assert detail.status_code == 200, detail.text
        assert detail.json()["title"] == "Invited-only sync"
    finally:
        requests.delete(f"{API}/events/{eid}", headers=_h(admin), timeout=30)


def test_whole_calendar_share_link_requires_passcode_and_hides_private():
    admin = _login(ADMIN)
    # A whole-calendar link without a passcode is refused outright.
    bad = requests.post(f"{API}/calendar/share-configs", json={
        "name": "No code", "include_all_events": True,
    }, headers=_h(admin), timeout=30)
    assert bad.status_code == 400, bad.text

    priv = requests.post(f"{API}/events", json={
        "title": "Hidden from outsiders", "type": "meeting", "date": "2027-03-13",
        "visibility": "private",
    }, headers=_h(admin), timeout=30).json()
    pub = requests.post(f"{API}/events", json={
        "title": "Open to outsiders", "type": "meeting", "date": "2027-03-14",
    }, headers=_h(admin), timeout=30).json()

    cfg = requests.post(f"{API}/calendar/share-configs", json={
        "name": "Outside viewer", "include_all_events": True, "passcode": "letmein42",
    }, headers=_h(admin), timeout=30)
    assert cfg.status_code == 200, cfg.text
    cfg = cfg.json()
    assert cfg["requires_passcode"] is True
    assert "passcode_hash" not in cfg          # never leaves the server
    token = cfg["token"]
    try:
        # No code → 401 with a machine-readable reason.
        r = requests.get(f"{API}/public/calendar/user/{token}", timeout=30)
        assert r.status_code == 401 and r.json()["detail"] == "passcode_required"

        # Wrong code → 401.
        r = requests.get(f"{API}/public/calendar/user/{token}?passcode=nope", timeout=30)
        assert r.status_code == 401 and r.json()["detail"] == "passcode_invalid"

        # Right code → the whole calendar, minus anything marked private.
        r = requests.get(f"{API}/public/calendar/user/{token}?passcode=letmein42", timeout=30)
        assert r.status_code == 200, r.text
        titles = [e["title"] for e in r.json()["events"]]
        assert "Open to outsiders" in titles
        assert "Hidden from outsiders" not in titles

        # The .ics feed honours the same gate.
        ics = requests.get(f"{API}/public/calendar/user/{token}.ics?passcode=letmein42", timeout=30)
        assert ics.status_code == 200 and "BEGIN:VCALENDAR" in ics.text
        assert "Hidden from outsiders" not in ics.text
        assert requests.get(f"{API}/public/calendar/user/{token}.ics", timeout=30).status_code == 401

        # The owner's list view never exposes the hash either.
        listed = requests.get(f"{API}/calendar/share-configs", headers=_h(admin), timeout=30).json()
        row = next(c for c in listed if c["id"] == cfg["id"])
        assert "passcode_hash" not in row
    finally:
        requests.delete(f"{API}/calendar/share-configs/{cfg['id']}", headers=_h(admin), timeout=30)
        for e in (priv, pub):
            requests.delete(f"{API}/events/{e['id']}", headers=_h(admin), timeout=30)


def test_expired_share_link_is_dead():
    admin = _login(ADMIN)
    cfg = requests.post(f"{API}/calendar/share-configs", json={
        "name": "Stale", "expires_at": "2020-01-01",
    }, headers=_h(admin), timeout=30).json()
    try:
        r = requests.get(f"{API}/public/calendar/user/{cfg['token']}", timeout=30)
        assert r.status_code == 404, r.text
    finally:
        requests.delete(f"{API}/calendar/share-configs/{cfg['id']}", headers=_h(admin), timeout=30)
