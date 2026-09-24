"""Outreach lesson planning — yearly theme → monthly topic → session plan.

A plan hangs off a real event (outreach types only) and holds the running order
(time slots with a leader each), worship set, story/teaching, games, snacks and
drinks, materials, the offering slot, memory verse, take-home and an attendance
target. Songs and games come from libraries that grow as they're used, so the
same item isn't retyped every week.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from html import escape as html_escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from deps import _audit, db, get_campus_filter, get_current_user, logger, require_role
from email_helpers import send_notification_email

router = APIRouter(prefix="/api/lesson-planning", tags=["lesson-planning"])

# Volunteers plan sessions too — they're usually the ones running the games.
require_planner = require_role(4)

# Which event types count as outreach — plans are offered for these only.
OUTREACH_TYPES = {"outreach", "community_outreach", "mission", "kids_club", "youth_outreach"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _nid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def _scope(current_user):
    return await get_campus_filter(current_user) or {}


def _is_director(user):
    return (user.get("role") or "").lower() in ("admin", "director", "superadmin", "owner")


def _allowed_locations(scope):
    """The campus ids a scope filter allows, or None when unrestricted.

    `get_campus_filter` returns an `$or` of location_id / location_ids clauses,
    so reading `scope["location_id"]` directly never matches anything.
    """
    if not scope:
        return None
    ids = set()
    for clause in scope.get("$or") or [scope]:
        for key in ("location_id", "location_ids"):
            val = clause.get(key)
            if isinstance(val, dict):
                ids.update(val.get("$in") or [])
            elif val:
                ids.add(val)
    return ids or None


async def _plan_or_404(plan_id, current_user):
    plan = await db.lesson_plans.find_one({"id": plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Lesson plan not found")
    allowed = _allowed_locations(await _scope(current_user))
    if allowed and plan.get("location_id") and plan["location_id"] not in allowed \
            and not _is_director(current_user):
        raise HTTPException(status_code=403, detail="That plan belongs to another campus")
    return plan


# ─────────────────────────── yearly themes (shared across campuses) ──────────
@router.get("/themes")
async def list_themes(current_user: dict = Depends(require_planner)):
    rows = await db.lesson_themes.find({}, {"_id": 0}).sort("year", -1).to_list(100)
    return {"themes": rows}


@router.post("/themes")
async def create_theme(data: dict, current_user: dict = Depends(require_planner)):
    if not (data.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="Give the year a theme name")
    doc = {
        "id": _nid("theme"),
        "year": int(data.get("year") or datetime.now(timezone.utc).year),
        "name": data["name"].strip(),
        "scripture": (data.get("scripture") or "").strip(),
        "description": (data.get("description") or "").strip(),
        # [{period: "2026-07" or "Week 3", title, focus, memory_verse}]
        "topics": data.get("topics") or [],
        "created_at": _now(), "created_by": current_user["id"],
        "created_by_name": current_user.get("name") or "",
    }
    await db.lesson_themes.insert_one(dict(doc))
    await _audit(current_user["id"], "create", "lesson_theme", doc["id"], {"name": doc["name"]})
    return doc


@router.put("/themes/{theme_id}")
async def update_theme(theme_id: str, data: dict, current_user: dict = Depends(require_planner)):
    patch = {k: v for k, v in data.items() if k in ("name", "year", "scripture", "description", "topics")}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to change")
    patch["updated_at"] = _now()
    r = await db.lesson_themes.update_one({"id": theme_id}, {"$set": patch})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Theme not found")
    return await db.lesson_themes.find_one({"id": theme_id}, {"_id": 0})


@router.delete("/themes/{theme_id}")
async def delete_theme(theme_id: str, current_user: dict = Depends(require_planner)):
    if not _is_director(current_user):
        raise HTTPException(status_code=403, detail="Only a director can delete a theme")
    used = await db.lesson_plans.count_documents({"theme_id": theme_id})
    if used:
        raise HTTPException(status_code=400, detail=f"{used} plan(s) use this theme — unlink them first")
    await db.lesson_themes.delete_one({"id": theme_id})
    return {"deleted": theme_id}


# ─────────────────────────── song & game libraries ──────────────────────────
LIBRARIES = {"songs": "lesson_songs", "games": "lesson_games"}


@router.get("/library/{kind}")
async def list_library(kind: str, q: str = "", current_user: dict = Depends(require_planner)):
    if kind not in LIBRARIES:
        raise HTTPException(status_code=404, detail="Unknown library")
    allowed = _allowed_locations(await _scope(current_user))
    query = {}
    if allowed:
        # Unassigned items are shared across campuses.
        query["$or"] = [{"location_id": {"$in": list(allowed)}}, {"location_id": {"$in": ["", None]}}]
    rows = await db[LIBRARIES[kind]].find(query, {"_id": 0}).sort("name", 1).to_list(500)
    if q:
        low = q.lower()
        rows = [r for r in rows if low in f"{r.get('name','')} {r.get('tags','')}".lower()]
    return {kind: rows, "count": len(rows)}


@router.post("/library/{kind}")
async def add_library_item(kind: str, data: dict, current_user: dict = Depends(require_planner)):
    if kind not in LIBRARIES:
        raise HTTPException(status_code=404, detail="Unknown library")
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A name is required")
    coll = db[LIBRARIES[kind]]
    existing = await coll.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0})
    if existing:
        return existing                 # adding the same song twice is a no-op, not an error
    doc = {
        "id": _nid("song" if kind == "songs" else "game"),
        "name": name,
        "location_id": data.get("location_id") or "",
        "tags": (data.get("tags") or "").strip(),
        "created_at": _now(), "created_by_name": current_user.get("name") or "",
    }
    if kind == "songs":
        doc.update({"key": (data.get("key") or "").strip(), "tempo": (data.get("tempo") or "").strip(),
                    "language": (data.get("language") or "").strip(), "link": (data.get("link") or "").strip()})
    else:
        doc.update({"age_range": (data.get("age_range") or "").strip(),
                    "duration_min": int(data.get("duration_min") or 10),
                    "kit": (data.get("kit") or "").strip(),
                    "how_to": (data.get("how_to") or "").strip()})
    await coll.insert_one(dict(doc))
    return doc


@router.delete("/library/{kind}/{item_id}")
async def delete_library_item(kind: str, item_id: str, current_user: dict = Depends(require_planner)):
    if kind not in LIBRARIES:
        raise HTTPException(status_code=404, detail="Unknown library")
    await db[LIBRARIES[kind]].delete_one({"id": item_id})
    return {"deleted": item_id}


# ─────────────────────────── outreach events + plan status ──────────────────
@router.get("/outreach-events")
async def outreach_events(
    upcoming_only: bool = True,
    current_user: dict = Depends(require_planner),
):
    """Outreach events with whether a plan exists — the planner's home list.

    Past and cancelled events are left out: a planner only ever works on what
    is still ahead. `upcoming_only=False` is kept for reports that genuinely
    want the history.
    """
    allowed = _allowed_locations(await _scope(current_user))
    DEAD_STATUSES = ["cancelled", "canceled", "completed", "closed", "done", "archived"]
    query = {"type": {"$in": list(OUTREACH_TYPES)}, "status": {"$nin": DEAD_STATUSES}}
    if allowed:
        query["$or"] = [{"location_id": {"$in": list(allowed)}}, {"location_id": {"$in": ["", None]}}]
    if upcoming_only:
        query["date"] = {"$gte": datetime.now(timezone.utc).date().isoformat()}
    rows = await db.events.find(query, {
        "_id": 0, "id": 1, "title": 1, "name": 1, "date": 1, "time": 1, "end_time": 1,
        "location": 1, "location_id": 1, "type": 1,
    }).sort("date", 1).to_list(200)
    out = []
    for e in rows:
        plan = await db.lesson_plans.find_one({"event_id": e["id"]}, {"_id": 0, "id": 1, "status": 1, "topic_title": 1})
        out.append({**e, "title": e.get("title") or e.get("name") or "Event",
                    "plan_id": (plan or {}).get("id"),
                    "plan_status": (plan or {}).get("status"),
                    "plan_topic": (plan or {}).get("topic_title")})
    return {"events": out, "count": len(out),
            "unplanned": len([e for e in out if not e["plan_id"]])}


# ─────────────────────────── plans ──────────────────────────────────────────
def _plan_body(data, current_user, base=None):
    base = base or {}
    slots = []
    for s in data.get("slots", base.get("slots") or []):
        slots.append({
            "id": s.get("id") or _nid("slot"),
            "start": (s.get("start") or "").strip(),
            "duration_min": int(s.get("duration_min") or 0),
            "title": (s.get("title") or "").strip(),
            "kind": s.get("kind") or "other",     # welcome|worship|story|games|snacks|offering|other
            "leader_id": s.get("leader_id") or "",
            "leader_name": (s.get("leader_name") or "").strip(),
            "notes": (s.get("notes") or "").strip(),
        })
    keep = lambda k, default: data.get(k, base.get(k, default))  # noqa: E731
    return {
        "event_id": keep("event_id", ""),
        "event_title": keep("event_title", ""),
        "date": keep("date", ""),
        "location_id": keep("location_id", ""),
        "theme_id": keep("theme_id", ""),
        "theme_name": keep("theme_name", ""),
        "topic_title": keep("topic_title", ""),
        "topic_focus": keep("topic_focus", ""),
        "memory_verse": keep("memory_verse", ""),
        "story": keep("story", {}),               # {title, passage, main_point, questions: []}
        "songs": keep("songs", []),               # [{song_id, name, key}]
        "games": keep("games", []),               # [{game_id, name, age_range, duration_min, kit}]
        "snacks": keep("snacks", []),             # [{item, servings, who, cost}]
        "materials": keep("materials", []),       # [{item, done}]
        "offering": keep("offering", {}),         # {planned, purpose, target}
        "take_home": keep("take_home", ""),
        "attendance_target": int(keep("attendance_target", 0) or 0),
        "notes_after": keep("notes_after", ""),
        "status": keep("status", "draft"),
        "slots": slots,
    }


@router.get("/plans")
async def list_plans(
    event_id: str = "",
    include_past: bool = False,
    limit: int = Query(100, le=500),
    current_user: dict = Depends(require_planner),
):
    scope = await _scope(current_user)
    query = dict(scope)
    if event_id:
        query["event_id"] = event_id
    elif not include_past:
        # Plans for events that have already happened stay out of the planner.
        query["date"] = {"$gte": datetime.now(timezone.utc).date().isoformat()}
    rows = await db.lesson_plans.find(query, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    if not event_id:
        cancelled = set()
        event_ids = [r["event_id"] for r in rows if r.get("event_id")]
        if event_ids:
            async for e in db.events.find(
                {"id": {"$in": event_ids},
                 "status": {"$in": ["cancelled", "canceled", "archived"]}}, {"_id": 0, "id": 1}):
                cancelled.add(e["id"])
        rows = [r for r in rows if r.get("event_id") not in cancelled]
    return {"plans": rows, "count": len(rows)}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, current_user: dict = Depends(require_planner)):
    return await _plan_or_404(plan_id, current_user)


@router.post("/plans")
async def create_plan(data: dict, current_user: dict = Depends(require_planner)):
    event_id = (data.get("event_id") or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="A plan belongs to an event — pick one first")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if (event.get("type") or "") not in OUTREACH_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Lesson plans are for outreach events — change the event type first",
        )
    if await db.lesson_plans.find_one({"event_id": event_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="That event already has a plan")
    template_id = (data.get("template_id") or "").strip()
    if template_id:
        tpl = await db.lesson_plan_templates.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        # An empty list/dict from the caller must not wipe the template's content.
        supplied = {k: v for k, v in data.items() if v not in (None, "", [], {})}
        data = {**(tpl.get("plan") or {}), **supplied}
    body = _plan_body(data, current_user)
    body.update({
        "event_title": event.get("title") or event.get("name") or "",
        "date": event.get("date") or "",
        "location_id": event.get("location_id") or data.get("location_id") or "",
    })
    doc = {"id": _nid("plan"), **body, "created_at": _now(),
           "created_by": current_user["id"], "created_by_name": current_user.get("name") or ""}
    if template_id:
        doc["from_template_id"] = template_id
        await db.lesson_plan_templates.update_one({"id": template_id}, {"$inc": {"used_count": 1}})
    await db.lesson_plans.insert_one(dict(doc))
    await _audit(current_user["id"], "create", "lesson_plan", doc["id"], {"event_id": event_id})
    return doc


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: str, data: dict, current_user: dict = Depends(require_planner)):
    plan = await _plan_or_404(plan_id, current_user)
    body = _plan_body(data, current_user, base=plan)
    body.pop("event_id", None)             # a plan never moves event — duplicate instead
    body.update({"updated_at": _now(), "updated_by_name": current_user.get("name") or ""})
    await db.lesson_plans.update_one({"id": plan_id}, {"$set": body})
    # Remember any newly typed song or game so it doesn't have to be retyped.
    for s in body.get("songs") or []:
        if s.get("name") and not s.get("song_id"):
            await add_library_item("songs", {"name": s["name"], "key": s.get("key", ""),
                                             "location_id": plan.get("location_id", "")}, current_user)
    for g in body.get("games") or []:
        if g.get("name") and not g.get("game_id"):
            await add_library_item("games", {"name": g["name"], "age_range": g.get("age_range", ""),
                                             "duration_min": g.get("duration_min") or 10,
                                             "kit": g.get("kit", ""),
                                             "location_id": plan.get("location_id", "")}, current_user)
    return await db.lesson_plans.find_one({"id": plan_id}, {"_id": 0})


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, current_user: dict = Depends(require_planner)):
    plan = await _plan_or_404(plan_id, current_user)
    if plan.get("created_by") != current_user["id"] and not _is_director(current_user):
        raise HTTPException(status_code=403, detail="Only the author or a director can delete this plan")
    await db.lesson_plans.delete_one({"id": plan_id})
    await _audit(current_user["id"], "delete", "lesson_plan", plan_id, {"event_id": plan.get("event_id")})
    return {"deleted": plan_id}


@router.post("/plans/{plan_id}/duplicate")
async def duplicate_plan(plan_id: str, data: dict, current_user: dict = Depends(require_planner)):
    """Copy a plan onto another outreach event — outreach repeats weekly."""
    plan = await _plan_or_404(plan_id, current_user)
    target_id = (data or {}).get("event_id")
    if not target_id:
        raise HTTPException(status_code=400, detail="Pick the event to copy this plan onto")
    event = await db.events.find_one({"id": target_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Target event not found")
    if (event.get("type") or "") not in OUTREACH_TYPES:
        raise HTTPException(status_code=400, detail="Lesson plans are for outreach events only")
    allowed = _allowed_locations(await _scope(current_user))
    if allowed and event.get("location_id") and event["location_id"] not in allowed \
            and not _is_director(current_user):
        raise HTTPException(status_code=403, detail="That event belongs to another campus")
    if await db.lesson_plans.find_one({"event_id": target_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="That event already has a plan")
    copy = {k: v for k, v in plan.items() if k not in
            ("id", "created_at", "created_by", "created_by_name", "updated_at", "notes_after")}
    copy.update({
        "id": _nid("plan"), "event_id": target_id,
        "event_title": event.get("title") or event.get("name") or "",
        "date": event.get("date") or "", "location_id": event.get("location_id") or plan.get("location_id") or "",
        "status": "draft", "notes_after": "", "copied_from": plan_id,
        "created_at": _now(), "created_by": current_user["id"],
        "created_by_name": current_user.get("name") or "",
    })
    await db.lesson_plans.insert_one(dict(copy))
    return copy


@router.post("/plans/{plan_id}/purchase-order")
async def plan_to_purchase_order(plan_id: str, current_user: dict = Depends(require_planner)):
    """Turn the snacks + materials list into a draft purchase order."""
    plan = await _plan_or_404(plan_id, current_user)
    lines = []
    for s in plan.get("snacks") or []:
        if (s.get("item") or "").strip():
            qty = float(s.get("servings") or 1)
            price = float(s.get("cost") or 0)
            lines.append({"description": f"Snacks — {s['item'].strip()}", "qty": qty, "unit": "serving",
                          "unit_price": round(price / qty, 2) if qty and price else price,
                          "line_total": round(price, 2)})
    for m in plan.get("materials") or []:
        if (m.get("item") or "").strip():
            lines.append({"description": f"Materials — {m['item'].strip()}", "qty": 1, "unit": "ea",
                          "unit_price": float(m.get("cost") or 0), "line_total": float(m.get("cost") or 0)})
    if not lines:
        raise HTTPException(status_code=400, detail="Add snacks or materials to the plan first")
    subtotal = round(sum(x["line_total"] for x in lines), 2)
    # count+1 can collide when an older PO was deleted — bump until it's free.
    seq = await db.purchase_orders.count_documents({}) + 1
    year = datetime.now(timezone.utc).year
    while await db.purchase_orders.find_one({"po_number": f"PO-{year}-{seq:06d}"}, {"_id": 0, "id": 1}):
        seq += 1
    po = {
        "id": _nid("po"),
        "po_number": f"PO-{year}-{seq:06d}",
        "vendor_name": "", "vendor_id": "",
        "status": "draft", "currency": "UGX",
        "requested_date": datetime.now(timezone.utc).date().isoformat(),
        "delivery_date": plan.get("date") or "",
        "location_id": plan.get("location_id") or "",
        "lines": lines, "subtotal": subtotal, "tax": 0, "total": subtotal,
        "notes": f"Raised from the lesson plan for {plan.get('event_title')} ({plan.get('date')})",
        "source": "lesson_plan", "lesson_plan_id": plan_id,
        "requested_by": current_user["id"], "requested_by_name": current_user.get("name") or "",
        "created_at": _now(),
    }
    await db.purchase_orders.insert_one(dict(po))
    await db.lesson_plans.update_one({"id": plan_id}, {"$set": {"purchase_order_id": po["id"],
                                                               "purchase_order_number": po["po_number"]}})
    await _audit(current_user["id"], "create", "purchase_order", po["id"], {"from_lesson_plan": plan_id})
    return {"purchase_order": po, "lines": len(lines), "total": subtotal}


@router.get("/my-slots")
async def my_slots(days: int = 7, current_user: dict = Depends(get_current_user)):
    """Every slot this person is leading in the next few days."""
    today = datetime.now(timezone.utc).date()
    until = (today + timedelta(days=days)).isoformat()
    rows = await db.lesson_plans.find(
        {"date": {"$gte": today.isoformat(), "$lte": until}}, {"_id": 0},
    ).sort("date", 1).to_list(200)
    # Drop slots belonging to an event that was cancelled after planning.
    event_ids = [r["event_id"] for r in rows if r.get("event_id")]
    dead = set()
    if event_ids:
        async for e in db.events.find(
            {"id": {"$in": event_ids}, "status": {"$in": ["cancelled", "canceled", "archived"]}},
            {"_id": 0, "id": 1}):
            dead.add(e["id"])
    rows = [r for r in rows if r.get("event_id") not in dead]
    mine = []
    name = (current_user.get("name") or "").strip().lower()
    for p in rows:
        for s in p.get("slots") or []:
            if s.get("leader_id") == current_user["id"] or (name and (s.get("leader_name") or "").strip().lower() == name):
                mine.append({
                    "plan_id": p["id"], "event_title": p.get("event_title"), "date": p.get("date"),
                    "topic": p.get("topic_title"), "start": s.get("start"),
                    "duration_min": s.get("duration_min"), "title": s.get("title"), "kind": s.get("kind"),
                    "notes": s.get("notes"),
                })
    mine.sort(key=lambda x: (x["date"] or "", x["start"] or ""))
    return {"slots": mine, "count": len(mine)}



# ─────────────────────────── reusable plan templates ────────────────────────
# A template is a plan with the event, date and after-notes stripped out, and
# the leaders cleared — the running order and content repeat, the people don't.
TEMPLATE_SKIP = {"id", "event_id", "event_title", "date", "notes_after", "status",
                 "created_at", "created_by", "created_by_name", "updated_at",
                 "updated_by_name", "purchase_order_id", "purchase_order_number",
                 "copied_from", "from_template_id"}


def _template_snapshot(plan):
    snap = {k: v for k, v in plan.items() if k not in TEMPLATE_SKIP}
    snap["slots"] = [{**s, "leader_id": "", "leader_name": ""} for s in (plan.get("slots") or [])]
    return snap


@router.get("/templates")
async def list_templates(current_user: dict = Depends(require_planner)):
    allowed = _allowed_locations(await _scope(current_user))
    query = {}
    if allowed:
        query["$or"] = [{"location_id": {"$in": list(allowed)}}, {"location_id": {"$in": ["", None]}}]
    rows = await db.lesson_plan_templates.find(query, {"_id": 0}).sort("name", 1).to_list(200)
    for t in rows:
        plan = t.get("plan") or {}
        t["slot_count"] = len(plan.get("slots") or [])
        t["song_count"] = len(plan.get("songs") or [])
        t["game_count"] = len(plan.get("games") or [])
    return {"templates": rows, "count": len(rows)}


@router.post("/templates")
async def save_as_template(data: dict, current_user: dict = Depends(require_planner)):
    """Keep the open plan as a favourite to start future sessions from."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the template a name")
    plan = await _plan_or_404((data.get("plan_id") or "").strip(), current_user)
    if await db.lesson_plan_templates.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
                                               {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail="A template already uses that name")
    doc = {
        "id": _nid("tpl"),
        "name": name,
        "description": (data.get("description") or "").strip(),
        "location_id": plan.get("location_id") or "",
        "plan": _template_snapshot(plan),
        "used_count": 0,
        "source_plan_id": plan["id"],
        "created_at": _now(), "created_by": current_user["id"],
        "created_by_name": current_user.get("name") or "",
    }
    await db.lesson_plan_templates.insert_one(dict(doc))
    await _audit(current_user["id"], "create", "lesson_plan_template", doc["id"], {"name": name})
    return doc


@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: dict, current_user: dict = Depends(require_planner)):
    patch = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Give the template a name")
        clash = await db.lesson_plan_templates.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "id": {"$ne": template_id}},
            {"_id": 0, "id": 1})
        if clash:
            raise HTTPException(status_code=400, detail="A template already uses that name")
        patch["name"] = name
    if "description" in data:
        patch["description"] = (data.get("description") or "").strip()
    if data.get("refresh_from_plan_id"):
        plan = await _plan_or_404(data["refresh_from_plan_id"], current_user)
        patch["plan"] = _template_snapshot(plan)
        patch["source_plan_id"] = plan["id"]
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to change")
    patch["updated_at"] = _now()
    r = await db.lesson_plan_templates.update_one({"id": template_id}, {"$set": patch})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Template not found")
    return await db.lesson_plan_templates.find_one({"id": template_id}, {"_id": 0})


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, current_user: dict = Depends(require_planner)):
    tpl = await db.lesson_plan_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if tpl.get("created_by") != current_user["id"] and not _is_director(current_user):
        raise HTTPException(status_code=403, detail="Only the author or a director can delete this template")
    await db.lesson_plan_templates.delete_one({"id": template_id})
    await _audit(current_user["id"], "delete", "lesson_plan_template", template_id, {"name": tpl.get("name")})
    return {"deleted": template_id}


# ─────────────────────────── printable run sheet ────────────────────────────
def _esc(v):
    return html_escape(str(v if v is not None else ""))


def _run_sheet_html(plan):
    rows = ""
    for s in plan.get("slots") or []:
        note = f"<div class='meta'>{_esc(s.get('notes'))}</div>" if s.get("notes") else ""
        rows += (
            "<tr>"
            f"<td class='t'>{_esc(s.get('start'))}</td>"
            f"<td class='t'>{_esc(s.get('duration_min') or '')} min</td>"
            f"<td><strong>{_esc(s.get('title') or s.get('kind'))}</strong>{note}</td>"
            f"<td>{_esc(s.get('leader_name') or '—')}</td>"
            "</tr>"
        )
    if not rows:
        rows = "<tr><td colspan='4' class='empty'>No running order yet</td></tr>"

    def block(title, inner):
        return f"<div class='block'><h3>{_esc(title)}</h3>{inner}</div>" if inner else ""

    def li(text):
        return f"<li>{text}</li>"

    songs = "".join(
        li(_esc(s.get("name")) + (f" — {_esc(s.get('key'))}" if s.get("key") else ""))
        for s in plan.get("songs") or [] if s.get("name"))
    games = "".join(
        li(_esc(g.get("name"))
           + (f" ({_esc(g.get('age_range'))})" if g.get("age_range") else "")
           + (f" · kit: {_esc(g.get('kit'))}" if g.get("kit") else ""))
        for g in plan.get("games") or [] if g.get("name"))
    snacks = "".join(
        li(f"{_esc(s.get('item'))} × {_esc(s.get('servings') or '?')}"
           + (f" — {_esc(s.get('who'))}" if s.get("who") else ""))
        for s in plan.get("snacks") or [] if s.get("item"))
    materials = "".join(li(_esc(m.get("item"))) for m in plan.get("materials") or [] if m.get("item"))

    story = plan.get("story") or {}
    story_html = ""
    if story.get("title") or story.get("passage") or story.get("main_point"):
        qs = "".join(li(_esc(q)) for q in (story.get("questions") or []) if str(q).strip())
        passage = f" · {_esc(story.get('passage'))}" if story.get("passage") else ""
        point = f"<p>{_esc(story.get('main_point'))}</p>" if story.get("main_point") else ""
        story_html = (f"<p class='lead'>{_esc(story.get('title') or '')}{passage}</p>"
                      f"{point}{f'<ul>{qs}</ul>' if qs else ''}")

    offering = plan.get("offering") or {}
    extras = ""
    if offering.get("planned"):
        target = f" · target {_esc(offering.get('target'))}" if offering.get("target") else ""
        extras += f"<p><strong>Offering:</strong> {_esc(offering.get('purpose') or 'collection')}{target}</p>"
    if plan.get("take_home"):
        extras += f"<p><strong>Take home:</strong> {_esc(plan['take_home'])}</p>"
    if plan.get("attendance_target"):
        extras += f"<p><strong>Attendance target:</strong> {_esc(plan['attendance_target'])}</p>"

    theme_bit = f" · Theme: {_esc(plan.get('theme_name'))}" if plan.get("theme_name") else ""
    topic_bit = f" · Topic: {_esc(plan.get('topic_title'))}" if plan.get("topic_title") else ""
    verse_bit = (f'<div class="verse">Memory verse — {_esc(plan.get("memory_verse"))}</div>'
                 if plan.get("memory_verse") else "")
    status_bit = f"· {_esc(plan.get('status') or 'draft').upper()}"

    return f"""<html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 14mm 14mm 12mm; }}
      body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 11px; }}
      .bar {{ background: #1a1a2e; color: #fbbf24; padding: 8px 12px; font-weight: 700;
              letter-spacing: 1px; font-size: 12px; }}
      h1 {{ font-size: 18px; margin: 12px 0 2px; }}
      .sub {{ color: #64748b; font-size: 11px; margin: 0 0 2px; }}
      .verse {{ background: #f1f5f9; border-left: 3px solid #fbbf24; padding: 6px 8px;
                margin: 8px 0; font-style: italic; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
      th {{ background: #f8fafc; text-align: left; font-size: 9px; text-transform: uppercase;
            letter-spacing: .06em; color: #64748b; padding: 5px 6px; border-bottom: 1px solid #cbd5e1; }}
      td {{ padding: 5px 6px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
      td.t {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
      .meta {{ color: #64748b; font-size: 10px; }}
      .empty {{ text-align: center; color: #94a3b8; }}
      .cols {{ margin-top: 10px; }}
      .block {{ margin-bottom: 10px; page-break-inside: avoid; }}
      .block h3 {{ font-size: 9px; text-transform: uppercase; letter-spacing: .08em;
                   color: #64748b; margin: 0 0 3px; }}
      ul {{ margin: 0; padding-left: 16px; }}
      p {{ margin: 2px 0; }}
      .lead {{ font-weight: 600; }}
      .foot {{ margin-top: 14px; border-top: 1px solid #e2e8f0; padding-top: 6px;
               color: #94a3b8; font-size: 9px; }}
    </style></head><body>
      <div class="bar">58:12 GLOBAL CONNECT · OUTREACH RUN SHEET</div>
      <h1>{_esc(plan.get('event_title') or 'Outreach')}</h1>
      <p class="sub">{_esc(plan.get('date') or '')}{theme_bit}{topic_bit}</p>
      {verse_bit}
      <table><thead><tr><th>Time</th><th>Length</th><th>What happens</th><th>Leader</th></tr></thead>
        <tbody>{rows}</tbody></table>
      <div class="cols">
        {block('Worship set', f'<ul>{songs}</ul>' if songs else '')}
        {block('Story / teaching', story_html)}
        {block('Games', f'<ul>{games}</ul>' if games else '')}
        {block('Snacks & drinks', f'<ul>{snacks}</ul>' if snacks else '')}
        {block('Materials & kit', f'<ul>{materials}</ul>' if materials else '')}
        {block('Also on the day', extras)}
      </div>
      <div class="foot">Run sheet generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')} UTC
        {status_bit}</div>
    </body></html>"""


def _run_sheet_filename(plan):
    base = re.sub(r"[^A-Za-z0-9]+", "-", f"{plan.get('event_title') or 'outreach'}-{plan.get('date') or ''}")
    return f"run-sheet-{base.strip('-').lower()}.pdf"


async def _run_sheet_pdf(plan) -> bytes:
    from weasyprint import HTML
    try:
        return HTML(string=_run_sheet_html(plan)).write_pdf()
    except Exception as e:
        logger.error(f"Run sheet PDF failed for {plan.get('id')}: {e}")
        raise HTTPException(status_code=500, detail="Could not build the run sheet PDF")


@router.get("/plans/{plan_id}/run-sheet.pdf")
async def run_sheet_pdf(plan_id: str, current_user: dict = Depends(require_planner)):
    plan = await _plan_or_404(plan_id, current_user)
    pdf = await _run_sheet_pdf(plan)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{_run_sheet_filename(plan)}"',
    })


async def _leader_recipients(plan):
    """Email + name for everyone with a slot on this plan, de-duplicated."""
    ids = [s["leader_id"] for s in plan.get("slots") or [] if s.get("leader_id")]
    named = {(s.get("leader_name") or "").strip().lower()
             for s in plan.get("slots") or [] if s.get("leader_name") and not s.get("leader_id")}
    found, missing = {}, []
    if ids:
        async for u in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
            if u.get("email"):
                found[u["email"].lower()] = u.get("name") or u["email"]
            else:
                missing.append(u.get("name") or u["id"])
    for name in named:
        person = await db.users.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
                                         {"_id": 0, "name": 1, "email": 1})
        if person and person.get("email"):
            found[person["email"].lower()] = person.get("name") or person["email"]
        else:
            missing.append(name.title())
    return found, sorted(set(missing))


@router.post("/plans/{plan_id}/email-run-sheet")
async def email_run_sheet(plan_id: str, data: dict = None, current_user: dict = Depends(require_planner)):
    """Send the run-sheet PDF to every leader on the plan (plus any extra addresses)."""
    plan = await _plan_or_404(plan_id, current_user)
    recipients, missing = await _leader_recipients(plan)
    for extra in (data or {}).get("extra_emails") or []:
        extra = (extra or "").strip()
        if "@" in extra:
            recipients.setdefault(extra.lower(), extra)
    if not recipients:
        raise HTTPException(
            status_code=400,
            detail="Nobody to send to — assign leaders with an email address to the slots first",
        )
    pdf = await _run_sheet_pdf(plan)
    attachment = [{"filename": _run_sheet_filename(plan), "content": pdf,
                   "content_type": "application/pdf"}]
    subject = f"Run sheet — {plan.get('event_title') or 'Outreach'} ({plan.get('date') or ''})"
    sent, failed = [], []
    for email, name in recipients.items():
        slots = [s for s in plan.get("slots") or []
                 if (s.get("leader_name") or "").strip().lower() == (name or "").strip().lower()]
        mine = "".join(f"<li><strong>{_esc(s.get('start'))}</strong> — {_esc(s.get('title') or s.get('kind'))}"
                       f" ({_esc(s.get('duration_min') or '')} min)</li>" for s in slots)
        topic = f", topic “{_esc(plan.get('topic_title'))}”" if plan.get("topic_title") else ""
        body = (
            f"<p>Hi {_esc(name.split(' ')[0] if name else 'there')},</p>"
            f"<p>Here is the run sheet for <strong>{_esc(plan.get('event_title'))}</strong> on "
            f"<strong>{_esc(plan.get('date'))}</strong>{topic}. The PDF is attached.</p>"
            f"{f'<p>Your slots:</p><ul>{mine}</ul>' if mine else ''}"
            f"<p>Sent by {_esc(current_user.get('name') or 'the outreach team')}.</p>"
        )
        ok = await send_notification_email(email, subject, body, attachments=attachment)
        (sent if ok else failed).append(email)
    await db.lesson_plans.update_one({"id": plan_id}, {"$set": {
        "run_sheet_sent_at": _now(), "run_sheet_sent_to": sent,
        "run_sheet_sent_by_name": current_user.get("name") or "",
    }})
    await _audit(current_user["id"], "email", "lesson_plan", plan_id, {"sent": len(sent), "failed": len(failed)})
    return {"sent": sent, "sent_count": len(sent), "failed": failed,
            "no_email": missing, "filename": _run_sheet_filename(plan)}
