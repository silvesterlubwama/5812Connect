"""Restricted access management - residents, staff access, guest pre-approval"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from datetime import datetime, timezone
import uuid
from deps import db, get_current_user, _audit

router = APIRouter(prefix="/api", tags=["access"])

ROLE_HIERARCHY = {
    "Executive Director": 10, "Advisor": 9, "Director": 8, "Manager": 7,
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
    doc = {
        "id": f"gr_{str(uuid.uuid4())[:8]}",
        "guest_name": data.get("guest_name"),
        "guest_phone": data.get("guest_phone", ""),
        "guest_id_number": data.get("guest_id_number", ""),
        "location_id": data.get("location_id"),
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
    return {"message": "Guest visit approved"}


@router.put("/access/guest-requests/{request_id}/reject")
async def reject_guest_request(request_id: str, current_user: dict = Depends(get_current_user)):
    if get_role_level(current_user.get("role", "")) < 7:
        raise HTTPException(status_code=403, detail="Manager or above required")
    await db.guest_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "rejected_by": current_user["id"], "rejected_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Guest visit rejected"}


# ========== SCAN IN/OUT ==========

@router.post("/access/scan")
async def scan_in_out(data: dict, current_user: dict = Depends(get_current_user)):
    """Scan a resident or staff in/out of a restricted location"""
    member_id = data.get("member_id")
    location_id = data.get("location_id")
    action = data.get("action", "in")  # in or out

    # Verify the person has access
    is_resident = await db.residents.find_one({"member_id": member_id, "location_id": location_id, "status": "active"})
    has_staff_pass = await db.staff_access.find_one({"staff_id": member_id, "location_id": location_id, "status": "active"})
    is_approved_guest = await db.guest_requests.find_one({
        "guest_name": {"$exists": True}, "location_id": location_id,
        "status": "approved", "visit_date": datetime.now(timezone.utc).date().isoformat()
    })

    if not is_resident and not has_staff_pass and not is_approved_guest:
        raise HTTPException(status_code=403, detail="No access authorization for this restricted location")

    scan = {
        "id": f"scan_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "location_id": location_id,
        "action": action,
        "scanned_by": current_user["id"],
        "access_type": "resident" if is_resident else ("staff" if has_staff_pass else "guest"),
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
