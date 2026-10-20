"""iter390 — the lesson planner run sheet was dropping entered fields and could
be served stale from cache."""
import os
import requests
from routers.lesson_planning import _run_sheet_html

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}

FULL_PLAN = {
    "id": "plan_iter390",
    "event_title": "Kampala Kids Outreach",
    "date": "2026-07-18",
    "theme_name": "Rooted",
    "topic_title": "The Good Shepherd",
    "topic_focus": "Knowing the shepherd's voice",
    "memory_verse": "John 10:11",
    "status": "final",
    "purchase_order_number": "PO-2026-0041",
    "attendance_target": 120,
    "take_home": "Sticker sheet",
    "notes_after": "Start the games ten minutes earlier next time.",
    "slots": [
        {"start": "09:00", "duration_min": 15, "title": "Welcome", "kind": "welcome",
         "leader_name": "Zipporah", "notes": "Door greeters in place by 08:45"},
        {"start": "09:15", "duration_min": 20, "title": "", "kind": "worship", "leader_name": "Henry"},
    ],
    "songs": [{"name": "Shepherd of my soul", "key": "G"}],
    "games": [{"name": "Sheep and wolf", "age_range": "6-9", "duration_min": 25, "kit": "cones"}],
    "snacks": [{"item": "Mandazi", "servings": 120, "who": "Grace", "cost": 90000},
               {"item": "Juice", "servings": 120, "who": "Henry", "cost": 60000}],
    "materials": [{"item": "Craft paper", "cost": 25000}, {"item": "Glue sticks", "cost": 7500}],
    "offering": {"planned": True, "purpose": "Bibles", "target": 200000},
    "story": {"title": "The lost sheep", "passage": "Luke 15:1-7",
              "main_point": "He goes after the one", "questions": ["Who left the ninety-nine?"]},
}


def test_entered_costs_reach_the_run_sheet():
    html = _run_sheet_html(FULL_PLAN)
    assert "90,000" in html and "60,000" in html, "snack costs dropped"
    assert "25,000" in html and "7,500" in html, "material costs dropped"


def test_run_sheet_totals_the_shopping():
    html = _run_sheet_html(FULL_PLAN)
    assert "Budget 182,500" in html          # 90k + 60k + 25k + 7.5k
    assert "snacks 150,000" in html
    assert "kit 32,500" in html


def test_previously_dropped_fields_are_printed():
    html = _run_sheet_html(FULL_PLAN)
    assert "Knowing the shepherd&#x27;s voice" in html or "Knowing the shepherd's voice" in html
    assert "ten minutes earlier" in html, "notes_after dropped"
    assert "After the event" in html
    assert "PO-2026-0041" in html, "purchase order dropped"
    assert "25 min" in html, "game duration dropped"


def test_a_slot_shows_both_its_title_and_its_kind():
    html = _run_sheet_html(FULL_PLAN)
    assert "Welcome" in html and "· welcome" in html
    # A slot with no title still falls back to the kind alone.
    assert "worship" in html


def test_typed_line_breaks_survive_into_the_pdf():
    """Textarea text used to collapse, so paragraphs ran into one another."""
    plan = {**FULL_PLAN, "story": {
        "title": "The lost sheep", "passage": "Luke 15:1-7",
        "main_point": "He leaves the ninety-nine.\nHe searches until he finds the one.",
        "questions": ["Why carry it home\ninstead of driving it?"]}}
    plan["slots"] = [{**FULL_PLAN["slots"][0], "notes": "Greeters by 08:45.\nCheck the sound desk."}]
    html = _run_sheet_html(plan)
    # Every block of leader-typed prose has to carry the pre-wrap class.
    assert html.count("wrap") >= 4
    assert "class='wrap'" in html or 'class="wrap"' in html
    assert "white-space: pre-wrap" in html
    assert "class='meta wrap'" in html, "slot notes lost their line breaks"
    assert "\n" in plan["story"]["main_point"]      # and the newline itself is preserved
    assert "He searches until he finds the one." in html


def test_nothing_empty_is_printed():
    bare = {"id": "p", "event_title": "Bare", "date": "2026-01-01", "slots": []}
    html = _run_sheet_html(bare)
    assert "No running order yet" in html
    for heading in ("Budget", "After the event", "Snacks & drinks", "Materials & kit", "Games"):
        assert heading not in html, heading


def test_costs_that_are_blank_or_text_do_not_break_the_sheet():
    plan = {**FULL_PLAN,
            "snacks": [{"item": "Water", "servings": 10, "cost": ""},
                       {"item": "Buns", "servings": 10, "cost": "n/a"},
                       {"item": "Tea", "servings": 10, "cost": 5000}],
            "materials": [{"item": "Rope"}]}
    html = _run_sheet_html(plan)
    assert "Water" in html and "Buns" in html
    assert "Budget 5,000" in html


def test_pdf_is_never_served_from_cache():
    headers = _admin_headers()
    pid = _any_plan_id(headers)
    if not pid:
        return                                   # nothing planned yet in this environment
    res = requests.get(f"{API}/lesson-planning/plans/{pid}/run-sheet.pdf", headers=headers, timeout=60)
    assert res.status_code == 200, res.text[:300]
    assert res.content[:4] == b"%PDF"
    assert "no-store" in res.headers.get("Cache-Control", "")


def _admin_headers():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _any_plan_id(headers):
    r = requests.get(f"{API}/lesson-planning/plans", params={"include_past": "true"},
                     headers=headers, timeout=30).json()
    rows = r.get("plans") if isinstance(r, dict) else r
    return rows[0]["id"] if rows else None


def test_a_finished_outreach_can_be_reopened():
    """A run outreach is marked completed — you still need its run sheet and its
    after-the-event notes, so looking back must surface it."""
    headers = _admin_headers()
    ahead = requests.get(f"{API}/lesson-planning/outreach-events",
                         params={"upcoming_only": "true"}, headers=headers, timeout=30).json()["events"]
    back = requests.get(f"{API}/lesson-planning/outreach-events",
                        params={"upcoming_only": "false"}, headers=headers, timeout=30).json()["events"]
    assert len(back) > len(ahead), "looking back showed nothing extra"
    today = __import__("datetime").date.today().isoformat()
    assert all(e["date"] >= today for e in ahead), "a past event leaked into the default list"
    assert any(e["date"] < today for e in back), "no past event came back"


def test_a_plan_with_no_campus_is_still_listed():
    """Mirrors the calendar fix: a plan whose event has no campus set used to
    fall outside every campus filter and disappear."""
    headers = _admin_headers()
    rows = requests.get(f"{API}/lesson-planning/plans", params={"include_past": "true"},
                        headers=headers, timeout=30).json()["plans"]
    blank = [p for p in rows if not (p.get("location_id") or "")]
    if not blank:
        return
    pid = blank[0]["id"]
    assert requests.get(f"{API}/lesson-planning/plans/{pid}", headers=headers, timeout=30).status_code == 200
