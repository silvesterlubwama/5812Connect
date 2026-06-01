"""Logbook + Household Lookup endpoints — extracted from the package's __init__.py
for readability. Same router instance is imported here so paths stay unchanged.
"""
from fastapi import Depends, HTTPException, Header
from deps import db, require_director, logger
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid

from ._common import (
    SCAN_RESET_SECONDS,
    _resolve_session, _hydrate_subject, _decide, _build_visitor_log,
    _broadcast_to_checkpoint,
)


def register(router):
    """Attach the logbook + lookup + batch-check-in endpoints to the shared router."""

    @router.get("/checkpoint/visitor-log")
    async def checkpoint_visitor_log_device(
        date: Optional[str] = None,
        include_residents: bool = False,
        session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
    ):
        """Device-session-authed visitor log."""
        sess = await _resolve_session(session_token)
        return await _build_visitor_log(sess["checkpoint_id"], date or "", include_residents=include_residents)

    @router.get("/checkpoints/{checkpoint_id}/visitor-log")
    async def checkpoint_visitor_log_admin(
        checkpoint_id: str,
        date: Optional[str] = None,
        include_residents: bool = False,
        current_user: dict = Depends(require_director),
    ):
        """Admin-authed visitor log — same shape as the device endpoint."""
        return await _build_visitor_log(checkpoint_id, date or "", include_residents=include_residents)

    @router.get("/checkpoint/residents-log")
    async def checkpoint_residents_log_device(
        date: Optional[str] = None,
        session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
    ):
        """Device-session view: every resident scan (in/out) on the given date."""
        sess = await _resolve_session(session_token)
        return await _build_visitor_log(sess["checkpoint_id"], date or "", residents_only=True)

    @router.get("/checkpoints/{checkpoint_id}/residents-log")
    async def checkpoint_residents_log_admin(
        checkpoint_id: str,
        date: Optional[str] = None,
        current_user: dict = Depends(require_director),
    ):
        """Admin-auth view: same as the device endpoint."""
        return await _build_visitor_log(checkpoint_id, date or "", residents_only=True)

    @router.post("/checkpoint/lookup")
    async def checkpoint_household_lookup(
        data: dict,
        session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
    ):
        """Search members + children, return each match with its household siblings."""
        await _resolve_session(session_token)
        q = (data.get("q") or "").strip()
        if len(q) < 2:
            raise HTTPException(status_code=400, detail="Search needs at least 2 characters")
        rx = {"$regex": q, "$options": "i"}
        member_matches = await db.members.find(
            {"$or": [{"name": rx}, {"phone": rx}, {"email": rx}, {"national_id": rx}]},
            {"_id": 0, "password_hash": 0, "pin_hash": 0},
        ).limit(20).to_list(20)
        child_matches = await db.children.find(
            {"$or": [{"name": rx}, {"phone": rx}]},
            {"_id": 0},
        ).limit(20).to_list(20)
        family_ids = list({m.get("family_id") for m in member_matches if m.get("family_id")})
        family_ids += list({c.get("family_id") for c in child_matches if c.get("family_id")})
        families = {}
        if family_ids:
            async for fam in db.families.find({"id": {"$in": list(set(family_ids))}}, {"_id": 0}):
                families[fam["id"]] = fam
        out = []
        seen = set()
        member_ids = {m.get("id") for m in member_matches}
        for who in member_matches + child_matches:
            wid = who.get("id")
            if not wid or wid in seen:
                continue
            seen.add(wid)
            fam_id = who.get("family_id")
            family_members = []
            if fam_id:
                siblings_m = await db.members.find(
                    {"family_id": fam_id, "id": {"$ne": wid}},
                    {"_id": 0, "id": 1, "name": 1, "phone": 1, "role": 1, "photo_url": 1},
                ).to_list(20)
                siblings_c = await db.children.find(
                    {"family_id": fam_id, "id": {"$ne": wid}},
                    {"_id": 0, "id": 1, "name": 1, "date_of_birth": 1, "photo_url": 1, "grade": 1},
                ).to_list(20)
                for s in siblings_m:
                    family_members.append({**s, "kind": "member"})
                for s in siblings_c:
                    family_members.append({**s, "kind": "child"})
            kind = "member" if wid in member_ids else "child"
            out.append({
                "kind": kind,
                "id": wid,
                "name": who.get("name"),
                "phone": who.get("phone"),
                "email": who.get("email"),
                "role": who.get("role"),
                "photo_url": who.get("photo_url"),
                "family_id": fam_id,
                "family_name": (families.get(fam_id) or {}).get("name") if fam_id else None,
                "household": family_members,
            })
        return {"q": q, "results": out, "count": len(out)}

    @router.post("/checkpoint/check-in-batch")
    async def checkpoint_check_in_batch(
        data: dict,
        session_token: Optional[str] = Header(None, alias="X-Checkpoint-Session"),
    ):
        """Manually check in a batch of selected household members."""
        sess = await _resolve_session(session_token)
        cp = await db.security_checkpoints.find_one({"id": sess["checkpoint_id"]}, {"_id": 0})
        if not cp:
            raise HTTPException(status_code=404, detail="Checkpoint missing")
        members = data.get("members") or []
        if not isinstance(members, list) or not members:
            raise HTTPException(status_code=400, detail="members[] required")
        now = datetime.now(timezone.utc)
        clear_at = (now + timedelta(seconds=SCAN_RESET_SECONDS)).isoformat()
        created = []
        for m in members:
            subject = await _hydrate_subject(m.get("kind") or "member", m.get("id") or "")
            if subject.get("kind") == "unknown":
                continue
            decision, reason = _decide(cp, subject)
            event = {
                "id": f"cev_{uuid.uuid4().hex[:10]}",
                "checkpoint_id": cp["id"],
                "location_id": cp.get("location_id"),
                "kind": "entry_scan",
                "direction": "entry",
                "scan_type": "manual_household",
                "payload": subject.get("id"),
                "subject": subject,
                "decision": decision,
                "reason": reason + " (household batch check-in)",
                "from_session_id": sess["id"],
                "from_mode": sess.get("mode"),
                "created_at": now.isoformat(),
                "clear_at": clear_at,
            }
            await db.security_checkpoint_events.insert_one(event)
            event.pop("_id", None)
            if decision == "approved":
                try:
                    await db.checkins.insert_one({
                        "id": f"chk_{uuid.uuid4().hex[:10]}",
                        "member_id": subject.get("id"),
                        "member_name": subject.get("name"),
                        "type": subject.get("kind"),
                        "method": "checkpoint_household",
                        "location_id": cp.get("location_id"),
                        "checkpoint_id": cp["id"],
                        "checked_in_at": now.isoformat(),
                    })
                except Exception as e:
                    logger.warning(f"household checkin mirror failed: {e}")
            created.append(event)
        if created:
            await _broadcast_to_checkpoint(cp["id"], {"type": "event", "event": created[-1]})
        return {"checked_in": len(created), "events": created}
