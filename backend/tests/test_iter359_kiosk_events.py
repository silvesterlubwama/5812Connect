"""iter359 — kiosk shows what's on now, and checks in only the people tapped.

Before: the kiosk filed a blank check-in (no event at all) and the adult who did
the lookup was always checked in, even when they were only dropping a child off.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))
from pin_security import pin_digest  # noqa: E402
from tests.creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
TAG = uuid.uuid4().hex[:6]
PIN = "8431"


def local_now(tz_name="Africa/Kampala"):
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(tz_name))


async def main():
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(f"{name} {extra}".strip())
        print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))

    mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    loc_id = mdb.locations.find_one({}, {"_id": 0, "id": 1})["id"]
    now = local_now((mdb.locations.find_one({"id": loc_id}) or {}).get("timezone") or "Africa/Kampala")
    today = now.date().isoformat()

    def hhmm(delta_minutes):
        return (now + timedelta(minutes=delta_minutes)).strftime("%H:%M")

    fixtures = {
        "ongoing": {"time": hhmm(-30), "end_time": hhmm(60)},      # started, still running
        "soon": {"time": hhmm(35), "end_time": hhmm(120)},          # inside the hour
        "later": {"time": hhmm(200), "end_time": hhmm(300)},        # today, but far off
        "finished": {"time": hhmm(-240), "end_time": hhmm(-180)},   # already over
    }
    event_ids = {}
    for key, times in fixtures.items():
        eid = f"evt_iter359_{TAG}_{key}"
        event_ids[key] = eid
        mdb.events.insert_one({
            "id": eid, "title": f"{key.title()} Session {TAG}", "type": "service",
            "date": today, "status": "upcoming", "location_id": loc_id,
            "location": "Main Hall", "capacity": 50, **times,
        })

    parent_id = f"mem_iter359_{TAG}"
    fam_id = f"fam_iter359_{TAG}"
    mdb.members.insert_one({
        "id": parent_id, "name": f"Parent {TAG}", "role": "member", "phone": f"+2567000{TAG[:5]}",
        "family_id": fam_id, "location_id": loc_id, "pin_lookup": pin_digest(PIN),
        "national_id": f"NIN{TAG.upper()}0001",
    })
    kids = []
    for i in (1, 2):
        cid = f"chi_iter359_{TAG}_{i}"
        kids.append(cid)
        mdb.children.insert_one({"id": cid, "name": f"Kid{i} {TAG}", "family_id": fam_id,
                                 "parent_ids": [parent_id], "location_id": loc_id})

    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            # ── the kiosk lookup must say what's on ──────────────────────
            r = await c.post("/api/kiosk/pin-checkin", json={
                "pin": PIN, "action": "lookup", "location_id": loc_id})
            body = r.json()
            check("pin lookup works", r.status_code == 200 and body.get("member_id") == parent_id, r.text[:200])
            names_now = [e["name"] for e in body.get("events_now", [])]
            ids_now = [e["id"] for e in body.get("events_now", [])]
            check("event on now is offered", event_ids["ongoing"] in ids_now, str(names_now))
            check("event starting within the hour is offered", event_ids["soon"] in ids_now, str(names_now))
            check("event later today is NOT in the now list", event_ids["later"] not in ids_now, str(names_now))
            check("finished event is dropped", event_ids["finished"] not in ids_now, str(names_now))
            later_ids = [e["id"] for e in body.get("events_later_today", [])]
            check("later event offered under 'something else today'", event_ids["later"] in later_ids, str(later_ids))
            ongoing = next(e for e in body["events_now"] if e["id"] == event_ids["ongoing"])
            check("says it already started", ongoing.get("started") is True and "ago" in (ongoing.get("when") or ""),
                  str(ongoing.get("when")))
            soon = next(e for e in body["events_now"] if e["id"] == event_ids["soon"])
            check("says how long until it starts", soon.get("started") is False and "Starts in" in (soon.get("when") or ""),
                  str(soon.get("when")))
            check("the family is returned with the events", len(body.get("children") or []) == 2,
                  str(body.get("children")))
            check("window is reported to the kiosk", body.get("event_window_minutes") == 60,
                  str(body.get("event_window_minutes")))

            # the badge-less lookup route must carry the same information
            r = await c.get("/api/kiosk/lookup", params={"identifier": f"NIN{TAG.upper()}0001"})
            check("badge-less lookup also lists events",
                  r.status_code == 200 and event_ids["ongoing"] in [e["id"] for e in r.json().get("events_now", [])],
                  r.text[:200])

            r = await c.get("/api/kiosk/events-now", params={"location_id": loc_id})
            check("standalone events-now endpoint works",
                  r.status_code == 200 and event_ids["ongoing"] in [e["id"] for e in r.json()["events_now"]],
                  r.text[:150])

            # ── only the people tapped get checked in ────────────────────
            r = await c.post("/api/kiosk/pin-checkin", json={
                "pin": PIN, "action": "checkin", "include_self": False,
                "child_ids": [kids[0]], "event_id": event_ids["ongoing"], "location_id": loc_id})
            body = r.json()
            check("check-in accepted", r.status_code == 200, r.text[:200])
            check("guardian NOT checked in when unselected", body.get("checkin") is None, str(body.get("checkin")))
            check("only the tapped child is checked in", len(body.get("child_checkins") or []) == 1,
                  str([x["member_name"] for x in body.get("child_checkins") or []]))
            check("event name resolved from its id", body.get("event_name") == f"Ongoing Session {TAG}",
                  str(body.get("event_name")))
            check("confirmation lists who went in", body.get("checked_in_count") == 1
                  and f"Kid1 {TAG}" in (body.get("checked_in_names") or []), str(body.get("checked_in_names")))
            rows = list(mdb.checkins.find({"member_id": {"$in": [parent_id] + kids}}, {"_id": 0}))
            check("nothing recorded for the guardian", not any(x["member_id"] == parent_id for x in rows),
                  str([x["member_name"] for x in rows]))
            kid_row = next(x for x in rows if x["member_id"] == kids[0])
            check("the child's row carries the event", kid_row.get("event_id") == event_ids["ongoing"]
                  and kid_row.get("event_name") == f"Ongoing Session {TAG}", str(kid_row.get("event_name")))

            # guardian checking themselves in too
            r = await c.post("/api/kiosk/pin-checkin", json={
                "pin": PIN, "action": "checkin", "include_self": True,
                "child_ids": [kids[1]], "event_id": event_ids["soon"], "location_id": loc_id})
            body = r.json()
            check("guardian checked in when they tap their name", (body.get("checkin") or {}).get("member_id") == parent_id,
                  str(body.get("checked_in_names")))
            check("both people counted", body.get("checked_in_count") == 2, str(body.get("checked_in_names")))
            parent_row = mdb.checkins.find_one({"member_id": parent_id}, {"_id": 0})
            check("guardian's row carries the chosen event", parent_row.get("event_id") == event_ids["soon"],
                  str(parent_row.get("event_name")))

            # nobody selected → refused, nothing written
            before = mdb.checkins.count_documents({"member_id": {"$in": [parent_id] + kids}})
            r = await c.post("/api/kiosk/pin-checkin", json={
                "pin": PIN, "action": "checkin", "include_self": False, "child_ids": [],
                "event_id": event_ids["ongoing"], "location_id": loc_id})
            check("empty selection is refused", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
            check("nothing written on refusal",
                  mdb.checkins.count_documents({"member_id": {"$in": [parent_id] + kids}}) == before)

            # general check-in still allowed with no event chosen
            r = await c.post("/api/kiosk/pin-checkin", json={
                "pin": PIN, "action": "checkin", "include_self": True, "location_id": loc_id})
            check("general check-in still works without an event",
                  r.status_code == 200 and (r.json().get("checkin") or {}).get("event_id") in (None, ""),
                  r.text[:160])

            # ── admin can change the window ──────────────────────────────
            r = await c.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            H = {"Authorization": f"Bearer {r.json()['token']}"}
            await c.put("/api/admin/system-settings", headers=H, json={"kiosk": {"event_window_minutes": 10}})
            r = await c.get("/api/kiosk/events-now", params={"location_id": loc_id})
            ids_now = [e["id"] for e in r.json()["events_now"]]
            check("narrower window drops the 35-min-away event", event_ids["soon"] not in ids_now, str(ids_now))
            check("narrower window keeps the running event", event_ids["ongoing"] in ids_now, str(ids_now))
            check("window change is reported", r.json()["event_window_minutes"] == 10)
            await c.put("/api/admin/system-settings", headers=H, json={"kiosk": {"event_window_minutes": 60}})
            r = await c.get("/api/kiosk/events-now", params={"location_id": loc_id})
            check("window restored to 60", r.json()["event_window_minutes"] == 60)
    finally:
        mdb.events.delete_many({"id": {"$regex": f"^evt_iter359_{TAG}"}})
        mdb.members.delete_many({"id": parent_id})
        mdb.children.delete_many({"id": {"$in": kids}})
        mdb.checkins.delete_many({"member_id": {"$in": [parent_id] + kids}})

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
