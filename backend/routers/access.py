"""Restricted access management - residents, staff access, guest pre-approval"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
from deps import db, get_current_user, _audit

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
    """Assign a child/person as resident of a restricted sub-location"""
    member_id = data.get("member_id")
    location_id = data.get("location_id")
    tags = data.get("tags", [])  # e.g. ["special_needs", "shelter"]

    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not loc or not loc.get("is_restricted"):
        raise HTTPException(status_code=400, detail="Location must be restricted")
    if not loc.get("allows_residents", True):
        raise HTTPException(status_code=400, detail="This location does not allow residents")

    doc = {
        "id": f"res_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "location_id": location_id,
        "tags": tags,
        "status": "active",
        "assigned_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.residents.insert_one(doc)
    doc.pop("_id", None)
    # Update member record
    await db.members.update_one(
        {"id": member_id},
        {"$set": {"is_resident": True, "resident_location_id": location_id, "resident_tags": tags}}
    )
    await _audit(current_user["id"], "create", "resident_assignment", doc["id"])
    return doc


@router.get("/access/residents")
async def list_residents(location_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"status": "active"}
    if location_id:
        query["location_id"] = location_id
    residents = await db.residents.find(query, {"_id": 0}).to_list(200)
    # Enrich with member data
    for r in residents:
        member = await db.members.find_one({"id": r["member_id"]}, {"_id": 0, "name": 1, "role": 1})
        if member:
            r["member_name"] = member.get("name")
            r["member_role"] = member.get("role")
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
        import sys
        sys.path.insert(0, '/app/backend')
        from server import send_push_to_role
        await send_push_to_role(7, f"Guest Visit: {doc.get('guest_name', '')}", f"At {loc.get('name') if loc else location_id} on {doc.get('visit_date', '')}", "/access")
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
async def list_eligible_residents(location_id: str, current_user: dict = Depends(get_current_user)):
    """Return people eligible to be added as residents to a restricted sub-location.
    Only staff, children, or people in that campus can be selected.
    EDs and Advisers belong to all so are always eligible."""
    loc = await db.locations.find_one({"id": location_id}, {"_id": 0})
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    parent_campus_id = loc.get("parent_id") or location_id
    GLOBAL_ROLES = {"admin", "system_admin", "executive director", "adviser", "director"}

    # Members in the campus or with global roles
    members = await db.members.find({
        "$or": [
            {"location_id": parent_campus_id},
            {"location_ids": parent_campus_id},
            {"location_id": location_id},
            {"location_ids": location_id},
        ]
    }, {"_id": 0, "id": 1, "name": 1, "role": 1, "location_id": 1}).to_list(500)

    # Add global role users
    global_users = await db.users.find(
        {"role": {"$regex": "^(admin|system_admin|Executive Director|Adviser|Director)$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1, "role": 1}
    ).to_list(100)

    # Merge unique
    seen = {m["id"] for m in members}
    for u in global_users:
        if u["id"] not in seen:
            members.append(u)
            seen.add(u["id"])

    # Also include children in the campus
    children = await db.children.find({
        "$or": [{"location_id": parent_campus_id}, {"location_id": location_id}]
    }, {"_id": 0, "id": 1, "name": 1}).to_list(200)

    return {"members": members, "children": children}
