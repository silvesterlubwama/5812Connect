"""Children inherit their parent's access to restricted locations — until 18.

A child never needs their own paperwork to follow the adult who is already
cleared for a site: if a caregiver (Mother, Father, Guardian, Step-Parent) holds
an active staff pass or is a resident of a restricted location, the child's
badge carries that same access, and it expires automatically on their 18th
birthday.

Rules, in order of precedence:
  1. An explicit staff decision on the child wins — `block` denies everywhere,
     `grant` adds locations by hand.
  2. Inheritance applies only while the child is under 18 and only from
     caregiver-role family members. No date of birth on file → no inheritance
     (we cannot prove they are a minor).
  3. Everything is evaluated live at the gate, so revoking the parent's pass
     revokes the child's in the same instant. The daily re-check exists to
     clean up the stored badge and to flag children who have aged out and now
     need their own member/guest badge.
"""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user, require_staff, require_admin, _audit
from routers.members.family_members import CAREGIVER_ROLES, normalise_role

router = APIRouter(prefix="/api", tags=["access"])

ADULT_AGE = 18


def _dob(child: dict) -> Optional[date]:
    raw = (child.get("date_of_birth") or child.get("dob") or "").strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def eighteenth_birthday(dob: date) -> date:
    try:
        return dob.replace(year=dob.year + ADULT_AGE)
    except ValueError:      # 29 Feb
        return dob.replace(year=dob.year + ADULT_AGE, day=28)


def age_years(dob: date, on: Optional[date] = None) -> int:
    on = on or date.today()
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


async def caregiver_ids(child: dict) -> list:
    """Every profile id that could carry access for this child.

    The child's own `parent_ids`, the caregiver-role rows on the household, and
    for each of those the linked user account (staff passes are held by the
    user record, not the members mirror).
    """
    ids = [p for p in (child.get("parent_ids") or []) if p]
    if child.get("family_id"):
        family = await db.families.find_one({"id": child["family_id"]}, {"_id": 0, "guardians": 1})
        for g in (family or {}).get("guardians") or []:
            if (g.get("approval_status") or "approved") == "pending":
                continue
            if normalise_role(g.get("role") or g.get("relationship")).lower() not in CAREGIVER_ROLES:
                continue
            if g.get("person_id"):
                ids.append(g["person_id"])
    out = list(dict.fromkeys(ids))
    # follow member → user links so a staff pass on the account is found
    for pid in list(out):
        for coll in (db.members, db.guests):
            row = await coll.find_one({"id": pid}, {"_id": 0, "user_id": 1})
            if row and row.get("user_id"):
                out.append(row["user_id"])
        user = await db.users.find_one({"id": pid}, {"_id": 0, "member_id": 1})
        if user and user.get("member_id"):
            out.append(user["member_id"])
    return list(dict.fromkeys(out))


async def _loc_names(ids: list) -> dict:
    if not ids:
        return {}
    return {l["id"]: l.get("name") or "" async for l in
            db.locations.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1})}


async def child_access(child_id: str) -> dict:
    """What this child may enter right now, and why."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    override = child.get("access_override") or {}
    mode = (override.get("mode") or "auto").lower()
    out = {
        "child_id": child_id, "name": child.get("name") or "",
        "mode": mode, "override": override or None,
        "locations": [], "expires_on": None, "age": None, "eligible": False,
        "reason": "", "aged_out": False,
    }
    if mode == "block":
        out["reason"] = f"Access blocked by staff{': ' + override['reason'] if override.get('reason') else ''}"
        return out

    dob = _dob(child)
    if dob:
        out["age"] = age_years(dob)
        out["expires_on"] = eighteenth_birthday(dob).isoformat()
        out["aged_out"] = out["age"] >= ADULT_AGE

    granted: dict = {}
    if mode == "grant":
        for lid in (override.get("location_ids") or []):
            granted[lid] = {"location_id": lid, "via_name": override.get("granted_by_name") or "Staff",
                            "via_kind": "manual"}

    if not dob:
        out["reason"] = "No date of birth on file — add one to inherit a parent's access"
    elif out["aged_out"]:
        out["reason"] = f"Turned {ADULT_AGE} on {out['expires_on']} — needs their own member or guest badge"
    else:
        ids = await caregiver_ids(child)
        if ids:
            async for r in db.residents.find(
                {"member_id": {"$in": ids}, "status": "active"},
                {"_id": 0, "member_id": 1, "member_name": 1, "location_id": 1},
            ):
                granted.setdefault(r["location_id"], {
                    "location_id": r["location_id"], "via_person_id": r["member_id"],
                    "via_name": r.get("member_name") or "", "via_kind": "resident"})
            for coll in ("staff_access", "staff_passes"):
                async for p in db[coll].find(
                    {"staff_id": {"$in": ids}, "status": "active"},
                    {"_id": 0, "staff_id": 1, "location_id": 1},
                ):
                    granted.setdefault(p["location_id"], {
                        "location_id": p["location_id"], "via_person_id": p["staff_id"],
                        "via_name": "", "via_kind": "staff_pass"})
        if not granted:
            out["reason"] = "No caregiver holds access to a restricted location"

    names = await _loc_names(list(granted))
    for lid, row in granted.items():
        row["location_name"] = names.get(lid, "")
        if not row.get("via_name") and row.get("via_person_id"):
            for coll in (db.users, db.members, db.guests):
                p = await coll.find_one({"id": row["via_person_id"]}, {"_id": 0, "name": 1})
                if p:
                    row["via_name"] = p.get("name") or ""
                    break
    out["locations"] = list(granted.values())
    out["eligible"] = bool(out["locations"])
    if out["eligible"] and not out["reason"]:
        out["reason"] = "Inherited from a caregiver's access"
    return out


async def may_child_enter(child_id: str, location_id: str) -> Optional[dict]:
    """Gate check. Returns the grant when the child may enter, else None."""
    info = await child_access(child_id)
    if info["mode"] == "block" or not info["eligible"]:
        return None
    hit = next((l for l in info["locations"] if l["location_id"] == location_id), None)
    if not hit:
        return None
    # The 18th-birthday cut-off only governs inherited access — a grant made by
    # hand is a staff decision and stands on its own.
    if hit.get("via_kind") != "manual" and info.get("expires_on") \
            and info["expires_on"] < date.today().isoformat():
        return None
    return {**hit, "expires_on": info["expires_on"], "mode": info["mode"]}


async def sync_child_badge(child_id: str, actor: Optional[dict] = None) -> dict:
    """Write the current inherited access onto the child's badge (or clear it)."""
    info = await child_access(child_id)
    update = {
        "inherited_locations": info["locations"],
        "inherited_location_ids": [l["location_id"] for l in info["locations"]],
        "access_expires_on": info["expires_on"],
        "access_mode": info["mode"],
        "access_reason": info["reason"],
        "access_synced_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wallet_badges.update_one({"member_id": child_id}, {"$set": update})
    return {**info, "badge_updated": True}


async def sync_all_children(actor: Optional[dict] = None, notify: bool = True) -> dict:
    """Daily re-check: refresh every child badge, and flag the ones that have
    aged out so staff can issue them their own member/guest badge."""
    revoked, aged_out, refreshed = [], [], 0
    async for badge in db.wallet_badges.find(
        {"role": "Child"}, {"_id": 0, "member_id": 1, "name": 1, "inherited_location_ids": 1}
    ):
        cid = badge.get("member_id")
        if not cid:
            continue
        before = set(badge.get("inherited_location_ids") or [])
        try:
            info = await sync_child_badge(cid, actor)
        except HTTPException:
            continue
        refreshed += 1
        after = {l["location_id"] for l in info["locations"]}
        lost = before - after
        if lost:
            revoked.append({"child_id": cid, "name": info["name"], "lost": sorted(lost),
                            "reason": info["reason"]})
        if info.get("aged_out"):
            aged_out.append({"child_id": cid, "name": info["name"], "expired_on": info["expires_on"]})
    if notify and (revoked or aged_out):
        try:
            from routers.notifications import create_notification
            admins = await db.users.find(
                {"role": {"$in": ["admin", "system_admin", "Executive Director", "Director", "Manager"]}},
                {"_id": 0, "id": 1},
            ).to_list(50)
            body = []
            if revoked:
                body.append(f"{len(revoked)} child badge(s) lost inherited access")
            if aged_out:
                body.append(f"{len(aged_out)} child(ren) turned {ADULT_AGE} and need their own badge")
            for a in admins:
                try:
                    await create_notification("Child access review", " · ".join(body),
                                              a["id"], "warning", "/access")
                except Exception:
                    pass
        except Exception:
            pass
    return {"refreshed": refreshed, "revoked": revoked, "aged_out": aged_out}


# ========== ROUTES ==========

@router.get("/access/child-access/{child_id}")
async def get_child_access(child_id: str, current_user: dict = Depends(get_current_user)):
    """What this child inherits, from whom, and when it expires."""
    return await child_access(child_id)


@router.post("/access/child-access/{child_id}/sync")
async def post_sync_child_access(child_id: str, current_user: dict = Depends(require_staff)):
    return await sync_child_badge(child_id, current_user)


@router.put("/access/child-access/{child_id}/override")
async def set_child_access_override(child_id: str, data: dict,
                                    current_user: dict = Depends(require_staff)):
    """Staff decision that beats inheritance.
    Body: { mode: 'auto'|'grant'|'block', location_ids?: [], reason?: str }"""
    mode = (data.get("mode") or "auto").lower()
    if mode not in {"auto", "grant", "block"}:
        raise HTTPException(status_code=400, detail="mode must be auto, grant or block")
    if not await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Child not found")
    if mode == "auto":
        await db.children.update_one({"id": child_id}, {"$unset": {"access_override": ""}})
    else:
        await db.children.update_one({"id": child_id}, {"$set": {"access_override": {
            "mode": mode,
            "location_ids": data.get("location_ids") or [],
            "reason": (data.get("reason") or "")[:300],
            "granted_by": current_user["id"],
            "granted_by_name": current_user.get("name", ""),
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }}})
    await _audit(current_user["id"], "update", "child_access_override", child_id, {"mode": mode})
    return await sync_child_badge(child_id, current_user)


@router.post("/access/child-access/sync-all")
async def post_sync_all_children(current_user: dict = Depends(require_admin)):
    """Re-check every child badge now (also runs nightly)."""
    return await sync_all_children(current_user)


@router.get("/access/child-access-review")
async def review_child_access(current_user: dict = Depends(require_staff)):
    """Children whose badge no longer stands up: aged out, or inherited
    nothing any more. Drives the Access page review list."""
    aged_out, no_access = [], []
    async for badge in db.wallet_badges.find(
        {"role": "Child"},
        {"_id": 0, "member_id": 1, "name": 1, "access_expires_on": 1,
         "inherited_location_ids": 1, "access_reason": 1},
    ):
        expires = badge.get("access_expires_on")
        row = {"child_id": badge.get("member_id"), "name": badge.get("name") or "",
               "expires_on": expires, "reason": badge.get("access_reason") or ""}
        if expires and expires < date.today().isoformat():
            aged_out.append(row)
        elif not (badge.get("inherited_location_ids") or []):
            no_access.append(row)
    return {"aged_out": aged_out, "no_inherited_access": no_access}
