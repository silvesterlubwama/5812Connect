"""Admin auto-issue tickets to existing users (children, members) for events.

Admins pick an event, an audience filter (e.g. "all children at this campus",
specific member IDs), an optional custom label / tier, and we create one
`public_bookings` row per person. Tickets are marked `auto_issued=True`
so front-desk staff can distinguish them from public bookings.
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Optional
import uuid

from deps import db, get_current_user, require_manager, get_campus_filter

router = APIRouter(prefix="/api/events", tags=["event-tickets"])


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
