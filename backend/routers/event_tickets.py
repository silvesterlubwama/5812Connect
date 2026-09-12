"""Admin auto-issue tickets to existing users (children, members) for events.

Admins pick an event, an audience filter (e.g. "all children at this campus"),
specific member IDs), an optional custom label / tier, and we create one
`public_bookings` row per person. Tickets are marked `auto_issued=True`
so front-desk staff can distinguish them from public bookings.

Also exposes door-staff endpoints for scanning `tkt_*` marketplace
tickets (see routers/sales.py — marketplace sales auto-create these):

- GET  /api/tickets/{ticket_id}          → look up a ticket
- POST /api/tickets/{ticket_id}/redeem   → mark as used at entry
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Optional
import uuid

from deps import db, get_current_user, require_manager, require_staff, get_campus_filter

router = APIRouter(prefix="/api/events", tags=["event-tickets"])
tickets_router = APIRouter(prefix="/api/tickets", tags=["tickets"])


# ============================================================
# Canonical ticket rows (iter345)
# ============================================================
# Every ticket-issuing path — public checkout, admin auto-issue, POS sale and
# portal RSVP — now writes a row in `event_tickets`. Before this, auto-issued
# and RSVP tickets only existed inside `public_bookings`, so the door scanner
# 404'd on them and the portal wallet never showed an RSVP. `event_tickets` is
# the single source of truth for "does this person hold a pass".

async def ensure_ticket_row(
    ticket_id: str,
    event: dict,
    *,
    holder_name: str = "",
    holder_person_id: str = "",
    holder_email: str = "",
    holder_phone: str = "",
    booking_id: str = "",
    price: float = 0,
    tier_name: Optional[str] = None,
    source: str = "",
) -> dict:
    """Idempotently create the scannable `event_tickets` row for a ticket id."""
    existing = await db.event_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "id": ticket_id,
        "event_id": event.get("id"),
        "event_title": event.get("title", ""),
        "event_date": event.get("date") or event.get("event_date") or "",
        "booking_id": booking_id or None,
        "holder_name": holder_name or "Guest",
        "holder_person_id": holder_person_id or None,
        "holder_email": (holder_email or "").strip().lower() or None,
        "holder_phone": holder_phone or "",
        "price": float(price or 0),
        "tier_name": tier_name,
        "status": "issued",
        "source": source or "manual",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.event_tickets.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def ticket_flags_for(
    person_ids: Optional[list] = None,
    email: str = "",
    on_date: Optional[str] = None,
) -> list:
    """Live "is this person ticketed?" lookup used by kiosks, checkpoints and
    the badge view. Matches on any identity we hold for the person; when
    `on_date` is given, only events on that date are returned."""
    ids = [i for i in (person_ids or []) if i]
    email = (email or "").strip().lower()
    match: list = []
    if ids:
        match += [{"holder_person_id": {"$in": ids}}, {"holder_id": {"$in": ids}}]
    if email:
        match.append({"holder_email": email})
    if not match:
        return []
    rows = await db.event_tickets.find(
        {"$or": match, "status": {"$ne": "void"}}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    if not rows:
        return []
    # Hydrate event context (older rows only stored event_id).
    ev_ids = list({r.get("event_id") for r in rows if r.get("event_id")})
    events: dict = {}
    if ev_ids:
        async for ev in db.events.find(
            {"id": {"$in": ev_ids}},
            {"_id": 0, "id": 1, "title": 1, "date": 1, "time": 1, "location": 1, "location_id": 1},
        ):
            events[ev["id"]] = ev
    out = []
    for r in rows:
        ev = events.get(r.get("event_id"), {}) or {}
        date = ev.get("date") or r.get("event_date") or ""
        if on_date and date != on_date:
            continue
        out.append({
            "ticket_id": r["id"],
            "event_id": r.get("event_id"),
            "event_title": ev.get("title") or r.get("event_title") or "",
            "event_date": date,
            "event_time": ev.get("time") or "",
            "event_location": ev.get("location") or "",
            "tier_name": r.get("tier_name"),
            "status": r.get("status") or "issued",
            "used_at": r.get("used_at"),
            "holder_name": r.get("holder_name"),
        })
    return out


@tickets_router.get("/flags")
async def get_ticket_flags(
    person_id: Optional[str] = None,
    email: Optional[str] = None,
    date: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Door/kiosk helper — every pass held by one person, optionally for a
    single date. `today=1`-style use: pass `date=YYYY-MM-DD`."""
    flags = await ticket_flags_for([person_id] if person_id else [], email or "", date)
    return {"count": len(flags), "tickets": flags}


async def _resolve_ticket(ticket_id: str) -> Optional[dict]:
    """Find a ticket row, backfilling from `public_bookings` for legacy
    tickets that were only ever recorded inside a booking (iter345)."""
    t = await db.event_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if t:
        return t
    b = await db.public_bookings.find_one({"ticket_ids": ticket_id}, {"_id": 0})
    if not b:
        return None
    ev = await db.events.find_one({"id": b.get("event_id")}, {"_id": 0}) or {"id": b.get("event_id")}
    return await ensure_ticket_row(
        ticket_id, ev,
        holder_name=b.get("name") or "", holder_person_id=b.get("auto_member_id") or "",
        holder_email=b.get("email") or "", holder_phone=b.get("phone") or "",
        booking_id=b.get("id"), price=b.get("price") or 0,
        tier_name=b.get("tier_name"), source="backfill_booking",
    )


@tickets_router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, current_user: dict = Depends(require_staff)):
    """Look up a marketplace-issued ticket. Returns the ticket plus a
    minimal event summary so the scanner can show the door staff the
    event name / date and the current status."""
    t = await _resolve_ticket(ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ev = None
    if t.get("event_id"):
        ev = await db.events.find_one({"id": t["event_id"]}, {"_id": 0, "id": 1, "title": 1, "event_date": 1, "location_id": 1})
    return {"ticket": t, "event": ev}


@tickets_router.post("/{ticket_id}/redeem")
async def redeem_ticket(ticket_id: str, current_user: dict = Depends(require_staff)):
    """Mark a ticket as used at the door. Idempotent-ish: re-scanning a
    used ticket returns 409 with the original redemption timestamp so
    door staff can see when it was first used."""
    t = await _resolve_ticket(ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if t.get("status") == "used":
        raise HTTPException(
            status_code=409,
            detail=f"Ticket already used at {t.get('used_at') or 'earlier'} by {t.get('used_by_name') or 'staff'}",
        )
    if t.get("status") == "void":
        raise HTTPException(status_code=410, detail="Ticket is void (refund or cancellation)")
    now = datetime.now(timezone.utc).isoformat()
    await db.event_tickets.update_one(
        {"id": ticket_id},
        {"$set": {
            "status": "used", "used_at": now,
            "used_by": current_user["id"], "used_by_name": current_user.get("name"),
        }},
    )
    return {"ok": True, "ticket_id": ticket_id, "used_at": now, "used_by_name": current_user.get("name")}


@router.post("/{event_id}/issue-tickets")
async def issue_tickets(
    event_id: str,
    data: dict,
    current_user: dict = Depends(require_manager),
):
    """Body:
    {
      audience: 'children' | 'members' | 'custom',
      member_ids?: [str],       # required when audience='custom'
      location_id?: str,        # filter for 'children' / 'members'
      tier_id?: str,            # optional — pick a specific tier
      custom_label?: str,       # printed on the ticket
      note?: str,
    }
    """
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    audience = (data.get("audience") or "").strip().lower()
    if audience not in ("children", "members", "custom"):
        raise HTTPException(status_code=400, detail="audience must be 'children', 'members', or 'custom'")

    # Resolve recipient list
    if audience == "custom":
        ids = [x for x in (data.get("member_ids") or []) if x]
        if not ids:
            raise HTTPException(status_code=400, detail="member_ids required for audience=custom")
        recipients = await db.members.find({"id": {"$in": ids}}, {"_id": 0}).to_list(1000)
        # fall back to users collection
        if len(recipients) < len(ids):
            uids = set(ids) - {r["id"] for r in recipients}
            users = await db.users.find({"id": {"$in": list(uids)}}, {"_id": 0, "password_hash": 0}).to_list(1000)
            for u in users:
                recipients.append({**u, "first_name": (u.get("name") or "").split(" ")[0], "last_name": " ".join((u.get("name") or "").split(" ")[1:])})
    else:
        campus = await get_campus_filter(current_user)
        q = {**(campus or {})}
        loc = (data.get("location_id") or "").strip()
        if loc:
            q["$or"] = [{"location_id": loc}, {"location_ids": loc}]
        if audience == "children":
            q["$and"] = [{"$or": [{"is_child": True}, {"role": "child"}, {"grade": {"$exists": True, "$nin": [None, ""]}}]}]
        recipients = await db.members.find(q, {"_id": 0}).to_list(2000)

    if not recipients:
        raise HTTPException(status_code=400, detail="No recipients matched the audience filter")

    # Resolve tier (optional)
    tier = None
    tier_id = (data.get("tier_id") or "").strip()
    if tier_id and event.get("ticket_tiers"):
        tier = next((t for t in event["ticket_tiers"] if t.get("id") == tier_id), None)
        if not tier:
            raise HTTPException(status_code=400, detail="Invalid tier_id")

    label = (data.get("custom_label") or "").strip()[:80]
    note = (data.get("note") or "").strip()[:280]
    now_iso = datetime.now(timezone.utc).isoformat()
    created = []
    skipped = []
    for m in recipients:
        # Skip duplicates — same event + member with auto_issued tag
        existing = await db.public_bookings.find_one(
            {"event_id": event_id, "auto_member_id": m["id"], "auto_issued": True},
            {"_id": 0, "id": 1},
        )
        if existing:
            skipped.append({"member_id": m["id"], "reason": "already_issued", "booking_id": existing["id"]})
            continue
        name = m.get("name") or f"{m.get('first_name','')} {m.get('last_name','')}".strip() or "Guest"
        booking_id = f"book_{uuid.uuid4().hex[:12]}"
        ticket_id = f"TKT-{uuid.uuid4().hex[:4].upper()}"
        booking = {
            "id": booking_id,
            "event_id": event_id,
            "event_title": event.get("title", ""),
            "name": name,
            "email": m.get("email") or "",
            "phone": m.get("phone") or "",
            "num_tickets": 1,
            "is_free": True,
            "price": 0,
            "total": 0,
            "payment_status": "paid",
            "status": "confirmed",
            "ticket_ids": [ticket_id],
            "tier_id": tier.get("id") if tier else None,
            "tier_name": tier.get("name") if tier else None,
            "custom_label": label or None,
            "auto_issued": True,
            "auto_issued_by": current_user["id"],
            "auto_member_id": m["id"],
            "auto_audience": audience,
            "note": note,
            "created_at": now_iso,
        }
        await db.public_bookings.insert_one(booking)
        await ensure_ticket_row(
            ticket_id, event,
            holder_name=name, holder_person_id=m["id"],
            holder_email=m.get("email") or "", holder_phone=m.get("phone") or "",
            booking_id=booking_id, price=0,
            tier_name=tier.get("name") if tier else None, source="auto_issue",
        )
        created.append({"booking_id": booking_id, "ticket_id": ticket_id, "member_id": m["id"], "name": name})
    # Bump event registered count
    if created:
        inc = {"registered": len(created)}
        if tier:
            await db.events.update_one(
                {"id": event_id, "ticket_tiers.id": tier["id"]},
                {"$inc": {"registered": len(created), "ticket_tiers.$.sold": len(created)}},
            )
        else:
            await db.events.update_one({"id": event_id}, {"$inc": inc})
    return {
        "event_id": event_id,
        "event_title": event.get("title"),
        "audience": audience,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created[:50],
        "skipped": skipped[:50],
    }


@router.get("/{event_id}/auto-issued")
async def list_auto_issued(
    event_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Show which members already have auto-issued tickets for this event."""
    rows = await db.public_bookings.find(
        {"event_id": event_id, "auto_issued": True},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return rows
