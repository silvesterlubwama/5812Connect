"""App settings, global settings, currencies, GDPR/privacy — extracted from server.py"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_admin, require_manager, require_staff
from datetime import datetime, timezone
import os, uuid

router = APIRouter(prefix="/api", tags=["settings"])

CURRENCIES = [
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "UGX"},
    {"code": "USD", "name": "US Dollar", "symbol": "$"},
    {"code": "EUR", "name": "Euro", "symbol": "\u20ac"},
    {"code": "GBP", "name": "British Pound", "symbol": "\u00a3"},
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KES"},
    {"code": "TZS", "name": "Tanzanian Shilling", "symbol": "TZS"},
    {"code": "RWF", "name": "Rwandan Franc", "symbol": "RWF"},
    {"code": "ZAR", "name": "South African Rand", "symbol": "R"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "\u20a6"},
    {"code": "GHS", "name": "Ghanaian Cedi", "symbol": "GH\u20b5"},
    {"code": "CAD", "name": "Canadian Dollar", "symbol": "CA$"},
    {"code": "AUD", "name": "Australian Dollar", "symbol": "A$"},
    {"code": "INR", "name": "Indian Rupee", "symbol": "\u20b9"},
    {"code": "HTG", "name": "Haitian Gourde", "symbol": "G"},
]

@router.get("/currencies")
async def get_currencies():
    return CURRENCIES

@router.get("/global-settings")
async def get_global_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.global_settings.find_one({"_key": "global"}, {"_id": 0})
    return doc or {"_key": "global", "app_name": "58:12 Connect", "org_name": "58:12 Global", "currency": "UGX", "main_currency": "USD", "footer_text": "58:12 Global", "contact_email": "", "contact_phone": "", "contact_address": "", "logo_url": ""}

@router.put("/global-settings")
async def update_global_settings(settings: dict, current_user: dict = Depends(require_admin)):
    settings.pop("_id", None)
    settings["_key"] = "global"
    settings["updated_by"] = current_user["id"]
    settings["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.global_settings.update_one({"_key": "global"}, {"$set": settings}, upsert=True)
    return settings

@router.get("/app-settings")
async def get_app_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.app_settings.find_one({"user_id": current_user["id"]}, {"_id": 0})
    return doc or {"user_id": current_user["id"], "dark_mode": False, "language": "en"}

@router.put("/app-settings")
async def update_app_settings(settings: dict, current_user: dict = Depends(get_current_user)):
    settings.pop("_id", None)
    settings["user_id"] = current_user["id"]
    await db.app_settings.update_one({"user_id": current_user["id"]}, {"$set": settings}, upsert=True)
    return settings

# ========== GDPR / DATA RETENTION ==========

@router.get("/gdpr/settings")
async def get_gdpr_settings(current_user: dict = Depends(get_current_user)):
    doc = await db.gdpr_settings.find_one({}, {"_id": 0})
    return doc or {"retention_months": 36, "auto_archive": False, "anonymize_inactive": False, "consent_required": True, "data_export_enabled": True}

@router.put("/gdpr/settings")
async def update_gdpr_settings(data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None)
    data["updated_by"] = current_user["id"]
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.gdpr_settings.update_one({}, {"$set": data}, upsert=True)
    return data

@router.post("/gdpr/export-my-data")
async def export_my_data(current_user: dict = Depends(get_current_user)):
    uid = current_user["id"]
    user = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0, "totp_secret": 0})
    members = await db.members.find({"created_by": uid}, {"_id": 0}).to_list(100)
    checkins = await db.check_ins.find({"user_id": uid}, {"_id": 0}).to_list(500)
    donations = await db.donations.find({"created_by": uid}, {"_id": 0}).to_list(500)
    return {"user": user, "members_created": members, "check_ins": checkins, "donations": donations, "exported_at": datetime.now(timezone.utc).isoformat()}

@router.post("/gdpr/anonymize/{user_id}")
async def anonymize_user(user_id: str, current_user: dict = Depends(require_admin)):
    anon = {"name": "Anonymized User", "email": f"anon_{user_id[:8]}@removed.local", "phone": "", "avatar": "", "status": "anonymized", "anonymized_at": datetime.now(timezone.utc).isoformat()}
    await db.users.update_one({"id": user_id}, {"$set": anon})
    return {"message": "User anonymized"}

# ========== FINANCIAL API MANAGEMENT ==========

@router.get("/financial-apis")
async def list_financial_apis(current_user: dict = Depends(get_current_user)):
    return await db.financial_apis.find({}, {"_id": 0}).to_list(50)

@router.post("/financial-apis")
async def add_financial_api(data: dict, current_user: dict = Depends(require_admin)):
    import uuid
    api_id = f"fapi_{str(uuid.uuid4())[:8]}"
    doc = {"id": api_id, "name": data.get("name", ""), "type": data.get("type", "payment"), "provider": data.get("provider", ""), "api_url": data.get("api_url", ""), "api_key": data.get("api_key", ""), "webhook_url": data.get("webhook_url", ""), "location_id": data.get("location_id"), "enabled": data.get("enabled", True), "config": data.get("config", {}), "created_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.financial_apis.insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/financial-apis/{api_id}")
async def update_financial_api(api_id: str, data: dict, current_user: dict = Depends(require_admin)):
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.financial_apis.update_one({"id": api_id}, {"$set": data})
    return {"id": api_id, **data}

@router.delete("/financial-apis/{api_id}")
async def delete_financial_api(api_id: str, current_user: dict = Depends(require_admin)):
    await db.financial_apis.delete_one({"id": api_id})
    return {"message": "API removed"}

# ========== INVENTORY ALERTS ==========

@router.get("/inventory/alerts")
async def inventory_alerts(current_user: dict = Depends(get_current_user)):
    products = await db.products.find({"$expr": {"$lte": ["$stock", "$reorder_level"]}}, {"_id": 0}).to_list(100)
    if not products:
        products = await db.products.find({"stock": {"$lte": 5}}, {"_id": 0}).to_list(100)
    return {"alerts": products, "count": len(products)}



# ========== ADMIN-EDITABLE CONFIGURATION ==========

DEFAULT_ROLES = ["Executive Director", "Adviser", "Director", "Manager", "Leader", "Coordinator", "Staff", "HR", "Volunteer", "Member", "Parent", "Customer", "Guest"]
DEFAULT_DOC_TYPES = [
    {"value": "national_id", "label": "National ID / State ID"},
    {"value": "passport", "label": "Passport"},
    {"value": "drivers_license", "label": "Driver's License"},
    {"value": "birth_certificate", "label": "Birth Certificate"},
    {"value": "refugee_id", "label": "Refugee ID"},
    {"value": "voter_card", "label": "Voter Card"},
    {"value": "student_id", "label": "Student ID"},
    {"value": "employee_id", "label": "Employee ID"},
    {"value": "other", "label": "Other"},
]


@router.get("/config/roles")
async def get_roles(current_user: dict = Depends(get_current_user)):
    stored = await db.app_config.find_one({"_key": "roles"}, {"_id": 0})
    return stored.get("roles", DEFAULT_ROLES) if stored else DEFAULT_ROLES


@router.put("/config/roles")
async def update_roles(data: dict, current_user: dict = Depends(require_admin)):
    roles = data.get("roles", [])
    await db.app_config.update_one({"_key": "roles"}, {"$set": {"_key": "roles", "roles": roles}}, upsert=True)
    return roles


@router.get("/config/document-types")
async def get_document_types(current_user: dict = Depends(get_current_user)):
    stored = await db.app_config.find_one({"_key": "doc_types"}, {"_id": 0})
    return stored.get("types", DEFAULT_DOC_TYPES) if stored else DEFAULT_DOC_TYPES


@router.put("/config/document-types")
async def update_document_types(data: dict, current_user: dict = Depends(require_admin)):
    types = data.get("types", [])
    await db.app_config.update_one({"_key": "doc_types"}, {"$set": {"_key": "doc_types", "types": types}}, upsert=True)
    return types


# ========== RESTRICTED SPACE MANAGEMENT ==========

@router.get("/restricted-spaces")
async def list_restricted_spaces(campus_id: str = None, current_user: dict = Depends(get_current_user)):
    """List restricted sub-locations/venues for a campus"""
    query = {"is_restricted": True}
    if campus_id:
        query["$or"] = [{"id": campus_id}, {"parent_id": campus_id}]
    spaces = await db.locations.find(query, {"_id": 0}).to_list(100)
    return spaces


@router.post("/restricted-spaces/{space_id}/staff")
async def add_staff_to_restricted(space_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Add staff access to a restricted space from campus staff list"""
    staff_ids = data.get("staff_ids", [])
    await db.locations.update_one({"id": space_id}, {"$addToSet": {"staff_ids": {"$each": staff_ids}}})
    return {"message": f"Added {len(staff_ids)} staff to restricted space"}


@router.delete("/restricted-spaces/{space_id}/staff/{staff_id}")
async def remove_staff_from_restricted(space_id: str, staff_id: str, current_user: dict = Depends(require_manager)):
    await db.locations.update_one({"id": space_id}, {"$pull": {"staff_ids": staff_id}})
    return {"message": "Staff removed from restricted space"}


@router.post("/restricted-spaces/{space_id}/residents")
async def add_residents(space_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Add residents (children, guests, or staff) to a restricted location. Auto-updates their profiles."""
    resident_ids = data.get("resident_ids", [])
    if not resident_ids:
        return {"message": "No IDs provided", "added": 0}
    
    # Add to location's resident_ids
    await db.locations.update_one({"id": space_id}, {"$addToSet": {"resident_ids": {"$each": resident_ids}}})
    
    # Auto-tag each person's profile as resident of this location
    for rid in resident_ids:
        # Try children
        child = await db.children.find_one({"id": rid})
        if child:
            await db.children.update_one({"id": rid}, {"$set": {"is_resident": True, "resident_location_id": space_id}})
            continue
        # Try guests
        guest = await db.guests.find_one({"id": rid})
        if guest:
            await db.guests.update_one({"id": rid}, {"$set": {"is_resident": True, "resident_location_id": space_id}})
            continue
        # Try staff/users
        user = await db.users.find_one({"id": rid})
        if user:
            await db.users.update_one({"id": rid}, {"$set": {"is_resident": True, "resident_location_id": space_id}})
            continue
        # Try members
        await db.members.update_one({"id": rid}, {"$set": {"is_resident": True, "resident_location_id": space_id}})
    
    return {"message": f"Added {len(resident_ids)} residents", "added": len(resident_ids)}


@router.delete("/restricted-spaces/{space_id}/residents/{resident_id}")
async def remove_resident(space_id: str, resident_id: str, current_user: dict = Depends(require_manager)):
    """Remove a resident from a restricted location and untag their profile"""
    await db.locations.update_one({"id": space_id}, {"$pull": {"resident_ids": resident_id}})
    # Untag from all collections
    for coll_name in ["children", "guests", "users", "members"]:
        coll = getattr(db, coll_name)
        await coll.update_one({"id": resident_id, "resident_location_id": space_id}, {"$set": {"is_resident": False}, "$unset": {"resident_location_id": ""}})
    return {"message": "Resident removed"}


@router.get("/restricted-spaces/{space_id}/residents")
async def get_residents(space_id: str, current_user: dict = Depends(get_current_user)):
    """Get all residents of a restricted space — children, guests, and staff"""
    loc = await db.locations.find_one({"id": space_id}, {"_id": 0})
    if not loc: return {"children": [], "guests": [], "staff": [], "members": []}
    ids = loc.get("resident_ids", [])
    if not ids: return {"children": [], "guests": [], "staff": [], "members": []}
    children = await db.children.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)
    guests = await db.guests.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)
    staff = await db.users.find({"id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(200)
    members = await db.members.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)
    return {"children": children, "guests": guests, "staff": staff, "members": members}


# ========== VOLUNTEER EVENT ATTENDEES ==========

@router.get("/volunteer/event-attendees/{event_id}")
async def volunteer_event_attendees(event_id: str, current_user: dict = Depends(get_current_user)):
    """Get attendees of an event that a volunteer is assigned to"""
    # Verify volunteer is assigned to this event
    shift = await db.volunteer_shifts.find_one({"event_id": event_id, "assigned_volunteers": {"$elemMatch": {"member_id": current_user["id"]}}})
    is_staff = current_user.get("role", "").lower() in {"admin", "system_admin", "executive director", "director", "manager", "coordinator", "staff"}
    if not shift and not is_staff:
        raise HTTPException(status_code=403, detail="Not assigned to this event")
    checkins = await db.checkins.find({"event_id": event_id}, {"_id": 0}).sort("check_in_time", -1).to_list(500)
    return checkins



# ========== ENROLLMENT LINKS ==========

@router.post("/enrollment-links")
async def create_enrollment_link(data: dict, current_user: dict = Depends(require_manager)):
    """Create enrollment link unique to a sublocation for families to enroll"""
    import secrets as sec
    token = sec.token_urlsafe(24)
    doc = {
        "id": f"enroll_{str(uuid.uuid4())[:8]}",
        "token": token,
        "location_id": data.get("location_id"),
        "location_name": data.get("location_name", ""),
        "form_fields": data.get("form_fields", ["name", "phone", "email", "children"]),
        "welcome_message": data.get("welcome_message", ""),
        "requires_approval": data.get("requires_approval", True),
        "max_enrollments": data.get("max_enrollments", 0),
        "enrollments": 0,
        "active": True,
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.enrollment_links.insert_one(doc)
    doc.pop("_id", None)
    doc["link"] = f"/enroll/{token}"
    return doc


@router.get("/enrollment-links")
async def list_enrollment_links(current_user: dict = Depends(require_manager)):
    links = await db.enrollment_links.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for l in links:
        l["link"] = f"/enroll/{l['token']}"
    return links


@router.post("/public/enroll/{token}")
async def public_enrollment(token: str, data: dict):
    """Public enrollment endpoint — no auth required"""
    link = await db.enrollment_links.find_one({"token": token, "active": True}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired enrollment link")
    if link.get("max_enrollments") and link["enrollments"] >= link["max_enrollments"]:
        raise HTTPException(status_code=400, detail="Enrollment limit reached")
    
    enrollment = {
        "id": f"enr_{str(uuid.uuid4())[:8]}",
        "link_id": link["id"],
        "location_id": link.get("location_id"),
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "children": data.get("children", []),
        "status": "pending" if link.get("requires_approval") else "approved",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.enrollments.insert_one(enrollment)
    enrollment.pop("_id", None)
    await db.enrollment_links.update_one({"id": link["id"]}, {"$inc": {"enrollments": 1}})
    
    # Auto-create guest and child profiles if approved
    if enrollment["status"] == "approved":
        guest_id = f"gst_{str(uuid.uuid4())[:8]}"
        await db.guests.insert_one({
            "id": guest_id, "name": enrollment["name"], "phone": enrollment["phone"],
            "email": enrollment["email"], "location_id": link.get("location_id"),
            "is_parent": len(enrollment.get("children", [])) > 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        for child in enrollment.get("children", []):
            await db.children.insert_one({
                "id": f"chd_{str(uuid.uuid4())[:8]}", "name": child.get("name", ""),
                "age": child.get("age"), "parent_ids": [guest_id],
                "location_id": link.get("location_id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    
    return enrollment


@router.get("/enrollments")
async def list_enrollments(location_id: str = None, current_user: dict = Depends(require_manager)):
    query = {}
    if location_id: query["location_id"] = location_id
    return await db.enrollments.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.put("/enrollments/{enrollment_id}/approve")
async def approve_enrollment(enrollment_id: str, current_user: dict = Depends(require_manager)):
    """Approve enrollment — creates guest and child profiles"""
    enrollment = await db.enrollments.find_one({"id": enrollment_id}, {"_id": 0})
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await db.enrollments.update_one({"id": enrollment_id}, {"$set": {"status": "approved", "approved_by": current_user["id"], "approved_at": datetime.now(timezone.utc).isoformat()}})
    # Create profiles
    guest_id = f"gst_{str(uuid.uuid4())[:8]}"
    await db.guests.insert_one({
        "id": guest_id, "name": enrollment["name"], "phone": enrollment.get("phone", ""),
        "email": enrollment.get("email", ""), "location_id": enrollment.get("location_id"),
        "is_parent": len(enrollment.get("children", [])) > 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    for child in enrollment.get("children", []):
        await db.children.insert_one({
            "id": f"chd_{str(uuid.uuid4())[:8]}", "name": child.get("name", ""),
            "age": child.get("age"), "parent_ids": [guest_id],
            "location_id": enrollment.get("location_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return {"message": "Enrollment approved, profiles created"}
