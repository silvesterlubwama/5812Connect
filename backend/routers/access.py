"""Restricted access management - residents, staff access, guest pre-approval"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
from deps import db, get_current_user, require_admin, require_staff, _audit

router = APIRouter(prefix="/api", tags=["access"])
logger = logging.getLogger(__name__)

ROLE_HIERARCHY = {
    "system_admin": 10, "admin": 10, "Executive Director": 10, "Executive": 10,
    "Advisor": 9, "Director": 8, "Manager": 7,
    "Coordinator": 6, "Staff": 5, "Intern": 4, "Volunteer": 4,
    "Parent": 2, "Customer": 1, "Child": 0,
}


def get_role_level(role: str) -> int:
    return ROLE_HIERARCHY.get(role, 0)


def can_edit_role(editor_role: str, target_role: str) -> bool:
    """Directors and Executives can edit all. Managers can edit below them only."""
    editor_level = get_role_level(editor_role)
    target_level = get_role_level(target_role)
    if editor_level >= 8:  # Director+
        return True
    if editor_level >= 7:  # Manager
        return target_level < editor_level
    return False


async def notify_role_level(min_level: int, notification_type: str, data: dict):
    try:
        from routers.notifications import send_notification, NotifyRequest
        users = await db.users.find(
            {"email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1, "name": 1, "role": 1}
        ).to_list(500)
        for user in users:
            if get_role_level(user.get("role", "")) >= min_level:
                await send_notification(NotifyRequest(
                    type=notification_type,
                    recipient_email=user["email"],
                    recipient_name=user.get("name", ""),
                    data=data,
                ))
    except Exception as e:
        logger.warning(f"Access notify failed: {e}")


# ========== RESIDENT TRACKING ==========

@router.post("/access/residents")
async def assign_resident(data: dict, current_user: dict = Depends(get_current_user)):
    """Assign a child/person/guest as resident of a restricted sub-location. Supports multiple IDs."""
    member_ids = data.get("member_ids") or ([data["member_id"]] if data.get("member_id") else [])
    location_id = data.get("location_id")
    tags = data.get("tags", [])

    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not loc or not loc.get("is_restricted"):
        raise HTTPException(status_code=400, detail="Location must be restricted")
    if not loc.get("allows_residents", True):
        raise HTTPException(status_code=400, detail="This location does not allow residents")

    created = []
    for member_id in member_ids:
        # Skip if already a resident
        existing = await db.residents.find_one({"member_id": member_id, "location_id": location_id, "status": "active"})
        if existing:
            continue
        # Resolve name from members, children, or guests
        name = ""
        source = "member"
        person = await db.members.find_one({"id": member_id}, {"_id": 0, "name": 1, "role": 1})
        if person:
            name = person.get("name", "")
        else:
            child = await db.children.find_one({"id": member_id}, {"_id": 0, "name": 1})
            if child:
                name = child.get("name", ""); source = "child"
                await db.children.update_one({"id": member_id}, {"$set": {"is_resident": True, "resident_location_id": location_id}})
            else:
                guest = await db.guests.find_one({"id": member_id}, {"_id": 0, "name": 1})
                if guest:
                    name = guest.get("name", ""); source = "guest"
                    await db.guests.update_one({"id": member_id}, {"$set": {"is_resident": True, "resident_location_id": location_id}})
        doc = {
            "id": f"res_{str(uuid.uuid4())[:8]}",
            "member_id": member_id,
            "member_name": name,
            "source": source,
            "location_id": location_id,
            "tags": tags,
            "status": "active",
            "assigned_by": current_user["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.residents.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)
        # Update member record if it exists
        await db.members.update_one(
            {"id": member_id},
            {"$set": {"is_resident": True, "resident_location_id": location_id, "resident_tags": tags}}
        )
        # Auto-issue access badge for residents (unless staff badge exists)
        existing_badge = await db.wallet_badges.find_one({"member_id": member_id})
        if not existing_badge:
            badge_token = uuid.uuid4().hex[:16]
            await db.wallet_badges.insert_one({
                "id": f"wbadge_{badge_token}", "token": badge_token,
                "member_id": member_id, "name": name, "role": "Resident",
                "qr_data": member_id, "location_name": loc.get("name", ""),
                "country": loc.get("country", ""), "country_code": loc.get("country_code", ""),
                "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"],
            })
    await _audit(current_user["id"], "create", "resident_assignment", location_id, {"count": len(created)})
    return created if len(created) != 1 else created[0] if created else {"message": "Already residents"}


@router.get("/access/residents")
async def list_residents(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    residents = await db.residents.find(query, {"_id": 0}).to_list(200)
    # Also add children tagged as residents for this location
    if location_id:
        resident_children = await db.children.find({"is_resident": True, "resident_location_id": location_id}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        existing_ids = {r["member_id"] for r in residents}
        for child in resident_children:
            if child["id"] not in existing_ids:
                residents.append({"id": f"auto_{child['id']}", "member_id": child["id"], "member_name": child.get("name", ""), "member_role": "child", "source": "child", "location_id": location_id, "status": "active"})
        # Also add guests tagged as residents
        resident_guests = await db.guests.find({"is_resident": True, "resident_location_id": location_id}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        for guest in resident_guests:
            if guest["id"] not in existing_ids:
                residents.append({"id": f"auto_{guest['id']}", "member_id": guest["id"], "member_name": guest.get("name", ""), "member_role": "guest", "source": "guest", "location_id": location_id, "status": "active"})
    # Enrich with member/child/guest data
    for r in residents:
        if not r.get("member_name"):
            person = await db.members.find_one({"id": r["member_id"]}, {"_id": 0, "name": 1, "role": 1})
            if not person:
                person = await db.children.find_one({"id": r["member_id"]}, {"_id": 0, "name": 1})
                if person: person["role"] = "child"
            if not person:
                person = await db.guests.find_one({"id": r["member_id"]}, {"_id": 0, "name": 1})
                if person: person["role"] = "guest"
            if person:
                r["member_name"] = person.get("name")
                r["member_role"] = person.get("role")
    return residents


@router.delete("/access/residents/{resident_id}")
async def remove_resident(resident_id: str, current_user: dict = Depends(get_current_user)):
    res = await db.residents.find_one({"id": resident_id}, {"_id": 0})
    if not res:
        raise HTTPException(status_code=404, detail="Not found")
    await db.residents.update_one({"id": resident_id}, {"$set": {"status": "removed"}})
    await db.members.update_one({"id": res["member_id"]}, {"$set": {"is_resident": False}})
    return {"message": "Resident removed"}


# ========== STAFF ACCESS ==========

@router.post("/access/staff-passes")
async def assign_staff_access(data: dict, current_user: dict = Depends(get_current_user)):
    """Grant a staff member access to a restricted sub-location"""
    staff_id = data.get("staff_id")
    location_id = data.get("location_id")

    doc = {
        "id": f"sap_{str(uuid.uuid4())[:8]}",
        "staff_id": staff_id,
        "location_id": location_id,
        "status": "active",
        "granted_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.staff_access.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/access/staff-passes")
async def list_staff_access(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    passes = await db.staff_access.find(query, {"_id": 0}).to_list(200)
    for p in passes:
        staff = await db.members.find_one({"id": p["staff_id"]}, {"_id": 0, "name": 1, "role": 1})
        if staff:
            p["staff_name"] = staff.get("name")
            p["staff_role"] = staff.get("role")
    return passes


@router.delete("/access/staff-passes/{pass_id}")
async def revoke_staff_access(pass_id: str, current_user: dict = Depends(get_current_user)):
    await db.staff_access.update_one({"id": pass_id}, {"$set": {"status": "revoked"}})
    return {"message": "Access revoked"}


# ========== GUEST PRE-APPROVAL ==========

@router.post("/access/guest-requests")
async def request_guest_visit(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a guest visit request for a restricted sub-location"""
    location_id = data.get("location_id")
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0, "name": 1})
    doc = {
        "id": f"gr_{str(uuid.uuid4())[:8]}",
        "guest_name": data.get("guest_name"),
        "guest_phone": data.get("guest_phone", ""),
        "guest_id_number": data.get("guest_id_number", ""),
        "location_id": location_id,
        "purpose": data.get("purpose", ""),
        "visit_date": data.get("visit_date"),
        "visit_time": data.get("visit_time", ""),
        "status": "pending",  # pending, approved, rejected
        "requested_by": current_user["id"],
        "approved_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guest_requests.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "guest_request", doc["id"])
    await notify_role_level(7, "guest_approval", {
        "guest_name": doc.get("guest_name", ""),
        "location_name": loc.get("name") if loc else location_id,
        "date": doc.get("visit_date", ""),
        "purpose": doc.get("purpose", ""),
        "action_url": "/access",
    })
    # Real-time WS broadcast to online managers
    try:
        from routers.websocket import manager as ws_manager
        await ws_manager.broadcast({
            "type": "notification",
            "title": f"Guest visit request: {doc.get('guest_name', '')}",
            "body": f"At {loc.get('name') if loc else location_id} on {doc.get('visit_date', '')}",
            "link": "/access",
        })
    except Exception:
        pass
    # Send push notification to managers
    try:
        # Push notification for guest requests (non-blocking)
        from deps import db as _db, logger as _log
        _log.info(f"Guest request: {doc.get('guest_name', '')} at {loc.get('name') if loc else location_id}")
    except Exception:
        pass
    return doc


@router.get("/access/guest-requests")
async def list_guest_requests(location_id: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    if status:
        query["status"] = status
    requests = await db.guest_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return requests


@router.put("/access/guest-requests/{request_id}/approve")
async def approve_guest_request(request_id: str, current_user: dict = Depends(get_current_user)):
    """Approve a guest visit - requires Manager role or above"""
    if get_role_level(current_user.get("role", "")) < 7:
        raise HTTPException(status_code=403, detail="Manager or above required to approve guest visits")
    await db.guest_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "approved", "approved_by": current_user["id"], "approved_at": datetime.now(timezone.utc).isoformat()}}
    )
    await _audit(current_user["id"], "update", "guest_request", request_id, "approved")
    # Create limited-time guest pass with QR
    req = await db.guest_requests.find_one({"id": request_id}, {"_id": 0})
    if req:
        pass_id = f"gp_{str(uuid.uuid4())[:8]}"
        # Check if the guest already has a member/staff badge
        existing_badge = await db.members.find_one(
            {"$or": [{"name": req.get("guest_name")}, {"phone": req.get("guest_phone")}]},
            {"_id": 0, "id": 1, "name": 1, "badge_id": 1}
        )
        if not existing_badge:
            # Also check staff/users table
            existing_badge = await db.users.find_one(
                {"$or": [{"name": req.get("guest_name")}, {"phone": req.get("guest_phone")}, {"email": req.get("guest_phone")}]},
                {"_id": 0, "id": 1, "name": 1}
            )
        visit_time = req.get("visit_time", "")
        guest_pass = {
            "id": pass_id,
            "guest_request_id": request_id,
            "guest_name": req.get("guest_name"),
            "guest_phone": req.get("guest_phone", ""),
            "location_id": req.get("location_id"),
            "visit_date": req.get("visit_date"),
            "valid_from": req.get("visit_date"),
            "valid_until": req.get("visit_date"),  # Single day by default
            "valid_from_time": visit_time or "06:00",
            "valid_until_time": "22:00",  # Default end of day
            "qr_value": pass_id,
            "has_existing_badge": bool(existing_badge),
            "existing_member_id": existing_badge.get("id") if existing_badge else None,
            "existing_badge_name": existing_badge.get("name") if existing_badge else None,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guest_passes.insert_one(guest_pass)
    try:
        from routers.notifications import send_notification, NotifyRequest
        req = await db.guest_requests.find_one({"id": request_id}, {"_id": 0})
        if req:
            requester = await db.users.find_one({"id": req.get("requested_by")}, {"_id": 0, "email": 1, "name": 1})
            if requester and requester.get("email"):
                loc = await db.locations.find_one({"id": req.get("location_id")}, {"_id": 0, "name": 1})
                loc_name = loc.get("name") if loc else req.get("location_id")
                await send_notification(NotifyRequest(
                    type="custom",
                    recipient_email=requester["email"],
                    recipient_name=requester.get("name", ""),
                    data={
                        "subject": "Guest Visit Approved",
                        "message": f"Your guest visit request for {req.get('guest_name', '')} at {loc_name} on {req.get('visit_date', '')} has been approved.",
                    },
                ))
    except Exception as e:
        logger.warning(f"Guest approval notify failed: {e}")
    return {"message": "Guest visit approved"}


@router.put("/access/guest-requests/{request_id}/reject")
async def reject_guest_request(request_id: str, current_user: dict = Depends(get_current_user)):
    if get_role_level(current_user.get("role", "")) < 7:
        raise HTTPException(status_code=403, detail="Manager or above required")
    await db.guest_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "rejected_by": current_user["id"], "rejected_at": datetime.now(timezone.utc).isoformat()}}
    )
    try:
        from routers.notifications import send_notification, NotifyRequest
        req = await db.guest_requests.find_one({"id": request_id}, {"_id": 0})
        if req:
            requester = await db.users.find_one({"id": req.get("requested_by")}, {"_id": 0, "email": 1, "name": 1})
            if requester and requester.get("email"):
                loc = await db.locations.find_one({"id": req.get("location_id")}, {"_id": 0, "name": 1})
                loc_name = loc.get("name") if loc else req.get("location_id")
                await send_notification(NotifyRequest(
                    type="custom",
                    recipient_email=requester["email"],
                    recipient_name=requester.get("name", ""),
                    data={
                        "subject": "Guest Visit Rejected",
                        "message": f"Your guest visit request for {req.get('guest_name', '')} at {loc_name} on {req.get('visit_date', '')} was rejected.",
                    },
                ))
    except Exception as e:
        logger.warning(f"Guest rejection notify failed: {e}")
    return {"message": "Guest visit rejected"}


# ========== SCAN IN/OUT ==========

@router.post("/access/scan")
async def scan_in_out(data: dict, current_user: dict = Depends(get_current_user)):
    """Scan a resident or staff in/out of a restricted location"""
    member_id = data.get("member_id")
    location_id = data.get("location_id")
    action = data.get("action", "in")  # in or out
    guest_request_id = data.get("guest_request_id")
    guest_name = data.get("guest_name")

    # Verify the person has access
    is_resident = await db.residents.find_one({"member_id": member_id, "location_id": location_id, "status": "active"})
    has_staff_pass = await db.staff_access.find_one({"staff_id": member_id, "location_id": location_id, "status": "active"})
    guest_query = {
        "location_id": location_id,
        "status": "approved",
        "visit_date": datetime.now(timezone.utc).date().isoformat(),
    }
    if guest_request_id:
        guest_query["id"] = guest_request_id
    if guest_name:
        guest_query["guest_name"] = guest_name
    is_approved_guest = await db.guest_requests.find_one(guest_query)

    if not is_resident and not has_staff_pass and not is_approved_guest:
        raise HTTPException(status_code=403, detail="No access authorization for this restricted location")

    scan = {
        "id": f"scan_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "location_id": location_id,
        "action": action,
        "scanned_by": current_user["id"],
        "access_type": "resident" if is_resident else ("staff" if has_staff_pass else "guest"),
        "guest_request_id": guest_request_id,
        "guest_name": guest_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.access_scans.insert_one(scan)
    scan.pop("_id", None)
    return scan


@router.get("/access/scan-log")
async def get_scan_log(location_id: Optional[str] = None, date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    if date:
        query["timestamp"] = {"$regex": f"^{date}"}
    scans = await db.access_scans.find(query, {"_id": 0}).sort("timestamp", -1).to_list(200)
    for s in scans:
        member = await db.members.find_one({"id": s["member_id"]}, {"_id": 0, "name": 1})
        if member:
            s["member_name"] = member.get("name")
    return scans



@router.get("/access/guest-passes")
async def list_guest_passes(location_id: Optional[str] = None, status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if location_id:
        query["location_id"] = location_id
    if status:
        query["status"] = status
    passes = await db.guest_passes.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    # Auto-expire passes past their valid_until date
    today = datetime.now(timezone.utc).isoformat()[:10]
    for p in passes:
        if p.get("status") == "active" and p.get("valid_until") and p["valid_until"] < today:
            p["status"] = "expired"
            await db.guest_passes.update_one({"id": p["id"]}, {"$set": {"status": "expired"}})
    return passes


@router.get("/access/guest-passes/{pass_id}/validate")
async def validate_guest_pass(pass_id: str):
    """Public QR validation endpoint — scan a guest pass QR to check validity."""
    gp = await db.guest_passes.find_one({"$or": [{"id": pass_id}, {"qr_value": pass_id}]}, {"_id": 0})
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    today = datetime.now(timezone.utc).isoformat()[:10]
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    is_valid_date = (gp.get("valid_from", "") <= today <= gp.get("valid_until", ""))
    # Check time bounds if set
    is_valid_time = True
    if gp.get("valid_from_time") and gp.get("valid_until_time"):
        is_valid_time = gp["valid_from_time"] <= now_time <= gp["valid_until_time"]
    is_active = gp.get("status") == "active"
    valid = is_valid_date and is_valid_time and is_active
    if not valid and is_active and not is_valid_date:
        await db.guest_passes.update_one({"id": gp["id"]}, {"$set": {"status": "expired"}})
        gp["status"] = "expired"
    loc = await db.locations.find_one({"id": gp.get("location_id")}, {"_id": 0, "name": 1})
    if valid:
        msg = "Access granted"
    elif not is_active:
        msg = f"Pass is {gp.get('status', 'inactive')}"
    elif not is_valid_date:
        msg = "Pass expired"
    elif not is_valid_time:
        msg = f"Outside valid hours ({gp.get('valid_from_time', '')} - {gp.get('valid_until_time', '')})"
    else:
        msg = "Pass inactive"
    return {
        "valid": valid,
        "pass": gp,
        "location_name": loc.get("name") if loc else "",
        "message": msg,
    }


@router.put("/access/guest-passes/{pass_id}/extend")
async def extend_guest_pass(pass_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Extend a guest pass validity period."""
    ROLE_HIERARCHY_LOCAL = {"system_admin": 10, "admin": 10, "Executive Director": 10, "Advisor": 9, "Director": 8, "Manager": 7}
    if ROLE_HIERARCHY_LOCAL.get(current_user.get("role", ""), 0) < 7:
        raise HTTPException(status_code=403, detail="Manager or above required")
    gp = await db.guest_passes.find_one({"id": pass_id}, {"_id": 0})
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    update = {}
    if data.get("valid_until"):
        update["valid_until"] = data["valid_until"]
    if data.get("valid_until_time"):
        update["valid_until_time"] = data["valid_until_time"]
    if data.get("valid_from_time"):
        update["valid_from_time"] = data["valid_from_time"]
    if data.get("valid_days"):
        from datetime import timedelta
        new_end = (datetime.now(timezone.utc) + timedelta(days=int(data["valid_days"]))).isoformat()[:10]
        update["valid_until"] = new_end
    update["status"] = "active"
    update["extended_by"] = current_user["id"]
    update["extended_at"] = datetime.now(timezone.utc).isoformat()
    await db.guest_passes.update_one({"id": pass_id}, {"$set": update})
    await _audit(current_user["id"], "update", "guest_pass_extend", pass_id)
    return {**gp, **update}


@router.get("/access/eligible-residents/{location_id}")
async def list_eligible_residents(location_id: str, search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Return people eligible as residents: members, children, AND guests in the campus."""
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    parent_campus_id = loc.get("parent_id") or location_id

    member_q = {"$or": [{"location_id": parent_campus_id}, {"location_ids": parent_campus_id}, {"location_id": location_id}]}
    child_q = {"$or": [{"location_id": parent_campus_id}, {"location_id": location_id}]}
    guest_q = {"$or": [{"location_id": parent_campus_id}, {"location_id": location_id}, {"location_id": {"$in": [None, ""]}}]}
    if search:
        name_filter = {"name": {"$regex": search, "$options": "i"}}
        member_q = {"$and": [member_q, name_filter]}
        child_q = {"$and": [child_q, name_filter]}
        guest_q = {"$and": [guest_q, name_filter]}

    members = await db.members.find(member_q, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(200)
    children = await db.children.find(child_q, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    guests = await db.guests.find(guest_q, {"_id": 0, "id": 1, "name": 1, "phone": 1, "is_parent": 1}).to_list(200)

    # Add global role users
    global_q = {"role": {"$regex": "^(admin|system_admin|Executive Director|Adviser|Director)$", "$options": "i"}}
    if search:
        global_q["name"] = {"$regex": search, "$options": "i"}
    global_users = await db.users.find(global_q, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(100)
    seen = {m["id"] for m in members}
    for u in global_users:
        if u["id"] not in seen:
            members.append(u); seen.add(u["id"])

    return {"members": members, "children": children, "guests": guests}


# ========== ACCESS CONTROL API CONNECTIONS ==========

@router.get("/access/api-connections")
async def list_access_api_connections(current_user: dict = Depends(require_admin)):
    """List configured access control system API connections"""
    return await db.access_api_connections.find({}, {"_id": 0}).sort("name", 1).to_list(50)


@router.post("/access/api-connections")
async def create_access_api_connection(data: dict, current_user: dict = Depends(require_admin)):
    """Add an access control API connection for a door/sublocation/venue"""
    doc = {
        "id": f"acc_{str(uuid.uuid4())[:8]}",
        "name": data.get("name", ""),
        "type": data.get("type", "door"),  # door, gate, turnstile, barrier
        "api_url": data.get("api_url", ""),
        "api_key": data.get("api_key", ""),
        "auth_type": data.get("auth_type", "api_key"),  # api_key, oauth, basic
        "location_id": data.get("location_id"),
        "sublocation_id": data.get("sublocation_id"),
        "venue_id": data.get("venue_id"),
        "door_name": data.get("door_name", ""),
        "enabled": data.get("enabled", True),
        "provider": data.get("provider", "generic"),  # generic, kisi, salto, brivo, openpath, unifi
        "config": data.get("config", {}),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.access_api_connections.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/access/api-connections/{conn_id}")
async def update_access_api_connection(conn_id: str, data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None); data.pop("id", None)
    if not data.get("api_key"): data.pop("api_key", None)  # Don't overwrite with blank
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.access_api_connections.update_one({"id": conn_id}, {"$set": data})
    return await db.access_api_connections.find_one({"id": conn_id}, {"_id": 0, "api_key": 0})


@router.delete("/access/api-connections/{conn_id}")
async def delete_access_api_connection(conn_id: str, current_user: dict = Depends(require_admin)):
    await db.access_api_connections.delete_one({"id": conn_id})
    return {"message": "Connection removed"}


# ========== SHAREABLE GUEST ACCESS LINKS ==========

@router.post("/access/guest-links")
async def create_guest_access_link(data: dict, current_user: dict = Depends(require_staff)):
    """Create a shareable link for guests to request access to a restricted space"""
    import secrets as sec
    token = sec.token_urlsafe(24)
    doc = {
        "id": f"glink_{str(uuid.uuid4())[:8]}",
        "token": token,
        "location_id": data.get("location_id"),
        "sublocation_id": data.get("sublocation_id"),
        "venue_id": data.get("venue_id"),
        "space_name": data.get("space_name", ""),
        "max_uses": data.get("max_uses", 0),  # 0 = unlimited
        "uses": 0,
        "expires_at": data.get("expires_at"),  # ISO date string
        "requires_approval": data.get("requires_approval", True),
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guest_access_links.insert_one(doc)
    doc.pop("_id", None)
    doc["link"] = f"/public-access/{token}"
    return doc


@router.get("/access/guest-links")
async def list_guest_access_links(current_user: dict = Depends(require_staff)):
    links = await db.guest_access_links.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for l in links:
        l["link"] = f"/public-access/{l['token']}"
    return links


@router.delete("/access/guest-links/{link_id}")
async def delete_guest_access_link(link_id: str, current_user: dict = Depends(require_staff)):
    await db.guest_access_links.delete_one({"id": link_id})
    return {"message": "Link deleted"}


@router.post("/public/access-request/{token}")
async def submit_guest_access_request(token: str, data: dict):
    """Public endpoint — guest submits access request via shared link"""
    link = await db.guest_access_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    if link.get("max_uses") and link["uses"] >= link["max_uses"]:
        raise HTTPException(status_code=400, detail="This link has reached its maximum uses")
    if link.get("expires_at"):
        from datetime import datetime as dt
        if dt.fromisoformat(link["expires_at"]) < dt.now(timezone.utc):
            raise HTTPException(status_code=400, detail="This link has expired")
    request_doc = {
        "id": f"areq_{str(uuid.uuid4())[:8]}",
        "link_id": link["id"],
        "guest_name": data.get("name", ""),
        "guest_email": data.get("email", ""),
        "guest_phone": data.get("phone", ""),
        "purpose": data.get("purpose", ""),
        "visit_date": data.get("visit_date", ""),
        "location_id": link.get("location_id"),
        "space_name": link.get("space_name"),
        "status": "pending" if link.get("requires_approval") else "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guest_access_requests.insert_one(request_doc)
    request_doc.pop("_id", None)
    await db.guest_access_links.update_one({"id": link["id"]}, {"$inc": {"uses": 1}})
    return request_doc



# ========== GUEST ACCESS REQUEST ENHANCEMENTS ==========

@router.post("/public/access-request/{token}")
async def submit_guest_access_request_v2(token: str, data: dict):
    """Public endpoint — guest submits access request, auto-creates guest profile."""
    # This override handles the full flow: creates guest profile + request
    link = await db.guest_access_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    # Check if guest already exists (by email or phone)
    guest = None
    if email:
        guest = await db.guests.find_one({"email": email}, {"_id": 0})
    if not guest and phone:
        guest = await db.guests.find_one({"phone": phone}, {"_id": 0})
    if not guest:
        guest = {
            "id": f"gst_{uuid.uuid4().hex[:8]}", "name": name, "email": email,
            "phone": phone, "location_id": link.get("location_id", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guests.insert_one(guest)
        guest.pop("_id", None)
    request_doc = {
        "id": f"areq_{uuid.uuid4().hex[:8]}",
        "link_id": link["id"], "guest_id": guest["id"],
        "guest_name": name, "guest_email": email, "guest_phone": phone,
        "purpose": data.get("purpose", ""), "visit_date": data.get("visit_date", ""),
        "location_id": link.get("location_id"), "space_name": link.get("space_name"),
        "status": "pending" if link.get("requires_approval") else "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.guest_access_requests.insert_one(request_doc)
    request_doc.pop("_id", None)
    await db.guest_access_links.update_one({"id": link["id"]}, {"$inc": {"uses": 1}})
    # If auto-approved, issue temporary badge
    if request_doc["status"] == "approved":
        badge_token = uuid.uuid4().hex[:16]
        from datetime import timedelta
        valid_until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()[:10]
        await db.access_guest_passes.insert_one({
            "id": f"gp_{uuid.uuid4().hex[:8]}", "guest_id": guest["id"],
            "guest_name": name, "guest_phone": phone,
            "location_id": link.get("location_id"), "badge_token": badge_token,
            "valid_until": valid_until, "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        request_doc["badge_token"] = badge_token
        request_doc["valid_until"] = valid_until
    return request_doc


@router.put("/access/guest-passes/{pass_id}/convert-to-resident")
async def convert_pass_to_resident(pass_id: str, current_user: dict = Depends(get_current_user)):
    """Convert a temporary guest pass to permanent residency."""
    if get_role_level(current_user.get("role", "")) < 8:
        raise HTTPException(status_code=403, detail="Director+ required")
    gp = await db.access_guest_passes.find_one({"id": pass_id}, {"_id": 0})
    if not gp:
        raise HTTPException(status_code=404, detail="Pass not found")
    guest_id = gp.get("guest_id")
    location_id = gp.get("location_id")
    if not guest_id or not location_id:
        raise HTTPException(status_code=400, detail="Pass missing guest or location")
    # Create resident record
    existing = await db.residents.find_one({"member_id": guest_id, "location_id": location_id, "status": "active"})
    if not existing:
        res_doc = {
            "id": f"res_{uuid.uuid4().hex[:8]}", "member_id": guest_id,
            "member_name": gp.get("guest_name", ""), "source": "guest_pass_conversion",
            "location_id": location_id, "tags": [], "status": "active",
            "assigned_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.residents.insert_one(res_doc)
    await db.guests.update_one({"id": guest_id}, {"$set": {"is_resident": True, "resident_location_id": location_id}})
    await db.access_guest_passes.update_one({"id": pass_id}, {"$set": {"status": "converted_to_resident", "converted_at": datetime.now(timezone.utc).isoformat()}})
    await _audit(current_user["id"], "update", "convert_to_resident", pass_id)
    return {"message": "Pass converted to permanent residency"}


# ========== KIOSK ACCESS VALIDATION ==========

@router.post("/access/validate")
async def validate_access(data: dict, current_user: dict = Depends(get_current_user)):
    """Validate whether a person (by QR, NFC serial, fingerprint, or ID) has access to a restricted location."""
    location_id = data.get("location_id", "")
    qr_data = data.get("qr_data", "")
    nfc_serial = data.get("nfc_serial", "")
    fingerprint_id = data.get("fingerprint_id", "")
    member_id = data.get("member_id", "")

    person_id = member_id
    person_name = ""

    # Resolve person from QR/NFC/fingerprint
    if qr_data and not person_id:
        person_id = qr_data
    if nfc_serial and not person_id:
        tag_owner = await db.members.find_one({"nfc_tags.serial_number": nfc_serial}, {"_id": 0, "id": 1, "name": 1})
        if tag_owner:
            person_id = tag_owner["id"]; person_name = tag_owner.get("name", "")
    if fingerprint_id and not person_id:
        fp = await db.fingerprints.find_one({"credential_id": fingerprint_id}, {"_id": 0, "user_id": 1})
        if fp:
            person_id = fp["user_id"]

    if not person_id:
        return {"allowed": False, "reason": "No identification provided"}

    # Resolve name
    if not person_name:
        for coll in [db.members, db.users, db.children, db.guests]:
            doc = await coll.find_one({"id": person_id}, {"_id": 0, "name": 1})
            if doc:
                person_name = doc.get("name", ""); break

    # Check 1: Is this person a resident of this location?
    resident = await db.residents.find_one({"member_id": person_id, "location_id": location_id, "status": "active"})
    if not resident:
        # Also check children tagged as residents
        child_res = await db.children.find_one({"id": person_id, "is_resident": True, "resident_location_id": location_id})
        if child_res:
            resident = True
    if not resident:
        # Also check guests tagged as residents
        guest_res = await db.guests.find_one({"id": person_id, "is_resident": True, "resident_location_id": location_id})
        if guest_res:
            resident = True
    if resident:
        return {"allowed": True, "person_id": person_id, "person_name": person_name, "access_type": "resident", "valid_until": "permanent"}

    # Check 2: Staff with access pass for this location
    staff_pass = await db.staff_passes.find_one({"staff_id": person_id, "location_id": location_id, "status": "active"})
    if staff_pass:
        return {"allowed": True, "person_id": person_id, "person_name": person_name, "access_type": "staff", "valid_until": staff_pass.get("valid_until", "permanent")}

    # Check 3: Active guest pass for this location
    guest_pass = await db.access_guest_passes.find_one({"$or": [{"guest_id": person_id}, {"guest_request_id": person_id}], "location_id": location_id, "status": "active"})
    if guest_pass:
        valid_until = guest_pass.get("valid_until", "")
        if valid_until and valid_until < datetime.now(timezone.utc).isoformat()[:10]:
            return {"allowed": False, "person_id": person_id, "person_name": person_name, "reason": "Guest pass expired"}
        return {"allowed": True, "person_id": person_id, "person_name": person_name, "access_type": "guest_pass", "valid_until": valid_until}

    return {"allowed": False, "person_id": person_id, "person_name": person_name, "reason": "No access authorization for this location"}


# ========== FINGERPRINT DATABASE ==========

@router.post("/access/fingerprints")
async def register_fingerprint(data: dict, current_user: dict = Depends(require_staff)):
    """Register a fingerprint credential for a user."""
    user_id = data.get("user_id") or current_user["id"]
    credential_id = data.get("credential_id", "")
    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id required")
    doc = {
        "id": f"fp_{uuid.uuid4().hex[:8]}",
        "user_id": user_id,
        "credential_id": credential_id,
        "public_key": data.get("public_key", ""),
        "label": data.get("label", "Fingerprint"),
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "registered_by": current_user["id"],
    }
    await db.fingerprints.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/access/fingerprints/{user_id}")
async def list_user_fingerprints(user_id: str, current_user: dict = Depends(get_current_user)):
    fps = await db.fingerprints.find({"user_id": user_id}, {"_id": 0}).to_list(10)
    return fps


@router.delete("/access/fingerprints/{fp_id}")
async def delete_fingerprint(fp_id: str, current_user: dict = Depends(require_staff)):
    await db.fingerprints.delete_one({"id": fp_id})
    return {"message": "Fingerprint removed"}
