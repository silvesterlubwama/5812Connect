"""Children CRUD + education + residency + extras + photos + bulk + move-to-guest."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from deps import (
    db, get_current_user, _audit, require_staff, require_manager,
    logger, is_system_admin, get_campus_filter,
)
from models import ChildCreate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/children")
async def list_children(
    family_id: Optional[str] = None,
    search: Optional[str] = None,
    welfare_category: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {**await get_campus_filter(current_user)}
    if family_id:
        query["family_id"] = family_id
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    # Welfare-category filter: restrict to children with an active social_work case
    if welfare_category and welfare_category != "all":
        case_query = {"subject_kind": "child", "status": "active"}
        if welfare_category != "any":
            case_query["category"] = welfare_category
        cases = await db.social_cases.find(case_query, {"_id": 0, "subject_id": 1}).to_list(5000)
        ids = list({c["subject_id"] for c in cases if c.get("subject_id")})
        if not ids:
            return []
        query["id"] = {"$in": ids}
    # Children in restricted sub-locations: only visible to staff assigned to that exact location
    if not is_system_admin(current_user):
        user_loc = current_user.get("location_id")
        # Get restricted sub-location IDs
        restricted_locs = await db.locations.find(
            {"type": "sub-location", "is_restricted": True},
            {"_id": 0, "id": 1}
        ).to_list(100)
        restricted_ids = [r["id"] for r in restricted_locs]
        if restricted_ids:
            # Exclude children in restricted locations that aren't the user's location
            other_restricted = [rid for rid in restricted_ids if rid != user_loc]
            if other_restricted:
                query["location_id"] = {"$nin": other_restricted}
    children = await db.children.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    # Enrich with welfare-case metadata
    if children:
        cids = [c["id"] for c in children]
        wmap = {}
        async for sc in db.social_cases.find(
            {"subject_kind": "child", "subject_id": {"$in": cids}, "status": "active"},
            {"_id": 0, "subject_id": 1, "category": 1, "risk_level": 1},
        ):
            wmap[sc["subject_id"]] = {"category": sc.get("category"), "risk_level": sc.get("risk_level")}
        for c in children:
            if c["id"] in wmap:
                c["welfare_case"] = wmap[c["id"]]
    return children


@router.post("/children")
async def create_child(data: ChildCreate, current_user: dict = Depends(get_current_user)):
    # Duplicate check by name + family_id
    name = data.name.strip()
    dedup_q = {"name": {"$regex": f"^{name}$", "$options": "i"}}
    if data.family_id:
        dedup_q["family_id"] = data.family_id
    existing = await db.children.find_one(dedup_q)
    if existing:
        raise HTTPException(status_code=409, detail=f"A child named '{name}' already exists in this family")
    doc = {
        "id": f"chd_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.children.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ========== BULK OPERATIONS FOR CHILDREN ==========

@router.put("/children/bulk-update")
async def bulk_update_children(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk update children. Body: {ids: [], updates: {family_id, location_id, class_group, gender}}"""
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates:
        return {"updated": 0}
    allowed = {"family_id", "location_id", "class_group", "gender", "grade", "medical_info", "allergies"}
    clean = {k: v for k, v in updates.items() if k in allowed and v}
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.children.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/children/bulk-delete")
async def bulk_delete_children(data: dict, current_user: dict = Depends(get_current_user)):
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    result = await db.children.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.put("/children/{child_id}")
async def update_child(child_id: str, data: ChildCreate, current_user: dict = Depends(get_current_user)):
    update = {**data.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}
    # Get old child to check residency changes
    old_child = await db.children.find_one({"id": child_id}, {"_id": 0})
    await db.children.update_one({"id": child_id}, {"$set": update})
    # Sync residency if changed
    new_resident = update.get("is_resident", False)
    new_loc = update.get("resident_location_id", "")
    old_loc = old_child.get("resident_location_id", "") if old_child else ""
    if new_resident and new_loc:
        await db.locations.update_one({"id": new_loc}, {"$addToSet": {"resident_ids": child_id}})
        if old_loc and old_loc != new_loc:
            await db.locations.update_one({"id": old_loc}, {"$pull": {"resident_ids": child_id}})
    elif not new_resident and old_loc:
        await db.locations.update_one({"id": old_loc}, {"$pull": {"resident_ids": child_id}})
    return await db.children.find_one({"id": child_id}, {"_id": 0})


@router.get("/children/{child_id}/parents")
async def get_child_parents(child_id: str, current_user: dict = Depends(get_current_user)):
    """Get full parent details for a child (for badge/profile display)."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "parent_ids": 1, "location_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    parents = []
    for pid in (child.get("parent_ids") or []):
        # Check guests first, then users/members
        p = await db.guests.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1})
        if not p:
            p = await db.users.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1})
        if not p:
            p = await db.members.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1})
        if p:
            parents.append(p)
    # Get campus contact info
    campus_phone = ""
    if child.get("location_id"):
        loc = await db.locations.find_one({"id": child["location_id"]}, {"_id": 0, "contact_phone": 1, "name": 1})
        if loc:
            campus_phone = loc.get("contact_phone", "")
    return {"parents": parents, "campus_phone": campus_phone}


@router.delete("/children/{child_id}")
async def delete_child(child_id: str, current_user: dict = Depends(get_current_user)):
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    child["_deleted_from"] = "children"
    child["deleted_at"] = datetime.now(timezone.utc).isoformat()
    child["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(child)
    await db.children.delete_one({"id": child_id})
    # Cascade: remove from resident lists
    if child.get("resident_location_id"):
        await db.locations.update_one({"id": child["resident_location_id"]}, {"$pull": {"resident_ids": child_id}})
    await _audit(current_user["id"], "delete", "child", child_id, {"name": child.get("name")})
    return {"message": "Child deleted"}


# ========== CHILD EDUCATION & PROFILE INFO ==========

@router.put("/children/{child_id}/education")
async def update_child_education(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update child's school, grade, report cards — staff or parent can update"""
    allowed = {"school", "grade", "class_group", "report_cards", "achievements", "special_needs", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.children.update_one({"id": child_id}, {"$set": update})
    return await db.children.find_one({"id": child_id}, {"_id": 0})


@router.post("/children/{child_id}/report-card")
async def add_report_card(child_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a report card entry to a child's profile"""
    entry = {
        "id": f"rc_{str(uuid.uuid4())[:8]}",
        "term": data.get("term", ""),
        "year": data.get("year", ""),
        "school": data.get("school", ""),
        "grade": data.get("grade", ""),
        "gpa": data.get("gpa", ""),
        "notes": data.get("notes", ""),
        "document_id": data.get("document_id"),
        "added_by": current_user["id"],
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.children.update_one({"id": child_id}, {"$push": {"report_cards": entry}})
    return entry


@router.put("/children/{child_id}/residency")
async def set_child_residency(child_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Set a child as a resident of a restricted location"""
    resident_loc = data.get("resident_location_id", "")
    is_resident = data.get("is_resident", True)
    update = {"is_resident": is_resident, "resident_location_id": resident_loc if is_resident else None, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.children.update_one({"id": child_id}, {"$set": update})
    # Also add to location's resident_ids
    if is_resident and resident_loc:
        await db.locations.update_one({"id": resident_loc}, {"$addToSet": {"resident_ids": child_id}})
    elif not is_resident and resident_loc:
        await db.locations.update_one({"id": resident_loc}, {"$pull": {"resident_ids": child_id}})
    return {"message": "Residency updated"}


@router.get("/children/{child_id}/full-profile")
async def get_child_full_profile(child_id: str, current_user: dict = Depends(get_current_user)):
    """Get full child profile — restricted info hidden based on access level"""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    user_role = (current_user.get("role") or "").lower()
    is_authorized = user_role in {"admin", "system_admin", "executive director"}

    # Check if user is director/manager/staff of child's location
    if not is_authorized:
        user_locs = current_user.get("location_ids") or []
        user_loc = current_user.get("location_id", "")
        if user_loc and user_loc not in user_locs:
            user_locs.append(user_loc)
        child_loc = child.get("location_id") or child.get("resident_location_id") or ""
        if child_loc:
            # Check if child's location is user's location or sub-location
            loc = await db.locations.find_one({"id": child_loc}, {"_id": 0, "parent_id": 1})
            if child_loc in user_locs or (loc and loc.get("parent_id") in user_locs):
                if user_role in {"director", "manager", "coordinator", "staff"}:
                    is_authorized = True
        # Check if user is a parent of this child
        if current_user["id"] in (child.get("parent_ids") or []):
            is_authorized = True

    # Get documents
    docs = await db.member_documents.find({"member_id": child_id}, {"_id": 0}).to_list(50)

    result = {**child, "documents": docs}

    # Hide restricted info if not authorized
    if not is_authorized and child.get("is_resident"):
        result.pop("resident_location_id", None)
        result.pop("sponsor_first_name", None)
        result.pop("sponsor_id", None)

    return result


# ========== CHILD EXTRAS: gallery photos + welfare updates ==========

@router.get("/children/{child_id}/extras")
async def list_child_extras(child_id: str, kind: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """List extra media + updates for a child. kind in: gallery|report|receipt|update."""
    query = {"child_id": child_id}
    if kind:
        query["kind"] = kind
    return await db.child_extras.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/children/{child_id}/extras")
async def add_child_extra(
    child_id: str,
    file: UploadFile = File(None),
    kind: str = Form("update"),
    caption: str = Form(""),
    is_public_for_sponsor: bool = Form(True),
    current_user: dict = Depends(require_staff),
):
    """Upload an extra photo / document or post a text-only welfare update."""
    if kind not in {"gallery", "report", "receipt", "update", "school", "medical"}:
        raise HTTPException(status_code=400, detail="Invalid kind")
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    file_url = None
    file_size = None
    if file and file.filename:
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File must be under 10MB")
        ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else 'bin'
        file_size = len(data)
        unique_name = f"{child_id}-{uuid.uuid4().hex[:8]}.{ext}"
        # Try object storage first, fall back to local filesystem
        try:
            from storage import put_object
            result = put_object(f"child-extras/{unique_name}", data, file.content_type or 'application/octet-stream')
            file_url = result.get("url", f"/api/storage/child-extras/{unique_name}")
        except Exception as e:
            logger.warning(f"Storage put failed, saving locally: {e}")
            import os
            os.makedirs("/app/backend/uploads/child-extras", exist_ok=True)
            with open(f"/app/backend/uploads/child-extras/{unique_name}", "wb") as fh:
                fh.write(data)
            file_url = f"/api/uploads/child-extras/{unique_name}"
    if not file_url and not caption.strip():
        raise HTTPException(status_code=400, detail="Provide a file or a caption")
    doc = {
        "id": f"cex_{uuid.uuid4().hex[:10]}",
        "child_id": child_id,
        "child_name": child.get("name"),
        "kind": kind,
        "caption": caption.strip()[:1000],
        "file_url": file_url,
        "file_name": file.filename if file and file.filename else None,
        "file_size": file_size,
        "is_public_for_sponsor": bool(is_public_for_sponsor),
        "location_id": child.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.child_extras.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/children/{child_id}/extras/{extra_id}")
async def delete_child_extra(child_id: str, extra_id: str, current_user: dict = Depends(require_staff)):
    extra = await db.child_extras.find_one({"id": extra_id, "child_id": child_id}, {"_id": 0})
    if not extra:
        raise HTTPException(status_code=404, detail="Not found")
    if extra.get("created_by") != current_user["id"] and current_user.get("role") not in {"admin", "system_admin", "Executive Director", "Director", "Manager"}:
        raise HTTPException(status_code=403, detail="Only the author or a manager can delete")
    await db.child_extras.delete_one({"id": extra_id})
    return {"deleted": True}


# ========== PHOTOS ==========

async def _save_photo(file: UploadFile, path_prefix: str, subject_id: str) -> str:
    """Shared helper: save an image upload and return its public URL."""
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    ext = file.filename.rsplit('.', 1)[-1] if '.' in (file.filename or '') else 'jpg'
    path = f"profile-photos/{path_prefix}{subject_id}.{ext}"
    try:
        from storage import put_object
        result = put_object(path, data, file.content_type)
        return result.get("url", f"/api/storage/{path}")
    except Exception as e:
        logger.warning(f"Storage upload failed, saving locally: {e}")
        import os
        os.makedirs("/app/backend/uploads/photos", exist_ok=True)
        local_name = f"{path_prefix}{subject_id}.{ext}"
        local_path = f"/app/backend/uploads/photos/{local_name}"
        with open(local_path, "wb") as f:
            f.write(data)
        return f"/api/uploads/photos/{local_name}"


@router.post("/members/{member_id}/photo")
async def upload_member_photo(member_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_staff)) -> dict:
    """Upload a profile photo for a member. Stores in object storage."""
    photo_url = await _save_photo(file, "", member_id)
    await db.members.update_one({"id": member_id}, {"$set": {"photo_url": photo_url}})
    # Also update user record if linked
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$set": {"photo_url": photo_url}})
    return {"photo_url": photo_url}


@router.post("/children/{child_id}/photo")
async def upload_child_photo(child_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_staff)) -> dict:
    """Upload a profile photo for a child."""
    photo_url = await _save_photo(file, "child-", child_id)
    await db.children.update_one({"id": child_id}, {"$set": {"photo_url": photo_url}})
    return {"photo_url": photo_url}


@router.post("/users/{user_id}/photo")
async def upload_user_photo(user_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_staff)) -> dict:
    """Upload a profile photo for a staff/user record (admin-side equivalent of member photo)."""
    if user_id != current_user["id"] and current_user.get("role") not in {"admin", "system_admin", "Executive Director", "Director", "Manager"}:
        raise HTTPException(status_code=403, detail="Only yourself or a manager can change this user's photo")
    photo_url = await _save_photo(file, "user-", user_id)
    await db.users.update_one({"id": user_id}, {"$set": {"photo_url": photo_url}})
    # Mirror to member record if linked
    await db.members.update_many({"user_id": user_id}, {"$set": {"photo_url": photo_url}})
    return {"photo_url": photo_url}


# ========== MOVE BETWEEN ROLES ==========

@router.post("/children/{child_id}/move-to-guest")
async def move_child_to_guest(child_id: str, current_user: dict = Depends(require_manager)) -> dict:
    """Move a child record to the guests collection."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    guest_id = f"gst_{uuid.uuid4().hex[:8]}"
    guest = {
        "id": guest_id, "name": child.get("name", ""), "phone": child.get("emergency_contact", ""),
        "email": "", "location_id": child.get("location_id", ""),
        "is_parent": False, "notes": f"Moved from children. DOB: {child.get('date_of_birth', '')}",
        "created_at": datetime.now(timezone.utc).isoformat(), "moved_from": "children", "original_id": child_id,
    }
    await db.guests.insert_one(guest)
    await db.children.delete_one({"id": child_id})
    guest.pop("_id", None)
    await _audit(current_user["id"], "move", "child_to_guest", child_id, {"new_id": guest_id})
    return {"message": f"Moved {child.get('name')} to guests", "guest_id": guest_id}



# ========== TYPED FILE-CHECKLIST DOCUMENTS ==========

# Canonical doc_types — matches the "Items in a child's file" master list 1:1.
# Order matches the customer's "LIST OF ITEMS IN A CHILD'S FILE" reference doc.
# Two entries (child_photo, welfare_review) are *synthetic* — their satisfaction
# is derived from the child profile (profile photo) and the social_reviews
# collection respectively, NOT from uploaded scans. Their `synthetic` flag tells
# the FE to hide the Upload button and instead surface a "Go to source" link.
CHILD_FILE_DOC_TYPES = [
    {"key": "child_photo", "label": "Child's Photograph", "synthetic": True, "source": "profile_photo"},
    {"key": "ovcmis_form_008", "label": "OVCMIS Form 008 — Child Enrollment & Monitoring Card"},
    {"key": "sponsorship_assessment", "label": "58:12 Child Sponsorship Assessment"},
    {"key": "school_report", "label": "Previous / Current School Reports"},
    {"key": "guardian_national_id", "label": "Parent / Guardian National ID"},
    {"key": "lc1_introduction_letter", "label": "LC1 Introduction Letter"},
    {"key": "medical_assessment", "label": "Medical Assessment Form (scan)"},
    {"key": "family_consent_letter", "label": "Family Consent Letter (58:12 policies)"},
    {"key": "welfare_review", "label": "58:12 Child Welfare Review & Visit Forms", "synthetic": True, "source": "social_reviews"},
    {"key": "school_document", "label": "Other School Documents (admission, transfer, etc.)"},
    {"key": "sponsor_letter_in", "label": "Letter from Sponsor"},
    {"key": "sponsor_letter_out", "label": "Letter to Sponsor"},
    {"key": "exit_form", "label": "Exit Form"},
    {"key": "other", "label": "Other document"},
]


@router.get("/children/{child_id}/file-doc-types")
async def get_doc_types(child_id: str, current_user: dict = Depends(require_staff)):
    """Doc-type catalogue + per-type count for the Documents tab UI.
    Synthetic items derive their count from the child record / reviews."""
    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    counts = {}
    async for ex in db.child_extras.find({"child_id": child_id, "kind": "file_doc"}, {"_id": 0, "doc_type": 1}):
        counts[ex.get("doc_type") or "other"] = counts.get(ex.get("doc_type") or "other", 0) + 1
    # Derive synthetic counts
    photo_present = 1 if (child.get("photo_url") or child.get("profile_photo_url")) else 0
    review_count = await db.social_review_forms.count_documents({"child_id": child_id})
    derived = {"child_photo": photo_present, "welfare_review": review_count}
    return [{**t, "count": derived.get(t["key"], counts.get(t["key"], 0))} for t in CHILD_FILE_DOC_TYPES]


@router.post("/children/{child_id}/file-docs")
async def upload_file_doc(
    child_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    notes: str = Form(""),
    issued_date: Optional[str] = Form(None),
    current_user: dict = Depends(require_staff),
):
    """Upload a checklist document (LC1 letter, guardian ID scan, etc.) as a
    typed child_extras row so the Documents tab can group by category and the
    profile-bundle ZIP knows what to label them."""
    if doc_type not in {t["key"] for t in CHILD_FILE_DOC_TYPES}:
        doc_type = "other"
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Document must be under 15 MB")
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin"
    unique = f"{child_id}-{doc_type}-{uuid.uuid4().hex[:8]}.{ext}"
    file_url = None
    try:
        from storage import put_object
        result = put_object(f"child-file-docs/{unique}", data, file.content_type or "application/octet-stream")
        file_url = result.get("url", f"/api/storage/child-file-docs/{unique}")
    except Exception as e:
        logger.warning(f"Cloud storage put failed, saving locally: {e}")
        import os as _os
        _os.makedirs("/app/backend/uploads/child-file-docs", exist_ok=True)
        with open(f"/app/backend/uploads/child-file-docs/{unique}", "wb") as fh:
            fh.write(data)
        file_url = f"/api/uploads/child-file-docs/{unique}"

    label = next((t["label"] for t in CHILD_FILE_DOC_TYPES if t["key"] == doc_type), "Other document")
    doc = {
        "id": f"cex_{uuid.uuid4().hex[:10]}",
        "child_id": child_id,
        "child_name": child.get("name"),
        "kind": "file_doc",
        "doc_type": doc_type,
        "doc_label": label,
        "caption": (notes or label)[:300],
        "issued_date": (issued_date or "")[:10],
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": len(data),
        "is_public_for_sponsor": False,
        "location_id": child.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.child_extras.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "child_file_doc", doc["id"], {"doc_type": doc_type})
    return doc


@router.get("/children/{child_id}/file-docs")
async def list_file_docs(child_id: str, current_user: dict = Depends(require_staff)):
    rows = await db.child_extras.find({"child_id": child_id, "kind": "file_doc"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


# ========== WHOLE-PROFILE BUNDLE DOWNLOAD ==========

@router.get("/children/{child_id}/profile-bundle")
async def download_profile_bundle(child_id: str, current_user: dict = Depends(require_staff)):
    """Stream a ZIP containing the entire child file: profile JSON, main photo,
    all review forms + attached scans + visit photos, all checklist documents,
    and the gallery. Includes an INDEX.md manifest listing checklist coverage so
    field staff can see at a glance what's missing."""
    from fastapi.responses import StreamingResponse
    import io
    import zipfile
    import json as _json
    import httpx

    child = await db.children.find_one({"id": child_id}, {"_id": 0})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True)

    async def _add_url(rel_path: str, url: str):
        try:
            if not url:
                return
            # Local-disk URL — read directly (avoids an HTTP roundtrip)
            if url.startswith("/api/uploads/"):
                import os as _os
                local_path = url.replace("/api/uploads/", "/app/backend/uploads/")
                if _os.path.exists(local_path):
                    with open(local_path, "rb") as fh:
                        zf.writestr(rel_path, fh.read())
                    return
            # Otherwise fetch via HTTP
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    zf.writestr(rel_path, r.content)
                else:
                    zf.writestr(rel_path + ".missing.txt", f"Could not fetch {url}: HTTP {r.status_code}")
        except Exception as e:
            zf.writestr(rel_path + ".error.txt", f"Could not fetch {url}: {e}")

    # 1. profile.json
    profile = {k: v for k, v in child.items() if k != "_id"}
    zf.writestr("profile.json", _json.dumps(profile, indent=2, default=str))

    # 2. Main profile photo
    if child.get("photo_url"):
        await _add_url("photo.jpg", child["photo_url"])

    # 3. Reviews + attached scans + visit photos
    reviews = await db.social_review_forms.find({"child_id": child_id}, {"_id": 0}).to_list(500)
    for r in reviews:
        date = (r.get("review_date") or "undated")[:10]
        kind = r.get("kind", "review")
        zf.writestr(f"reviews/{kind}-{date}-{r['id']}.json", _json.dumps(r, indent=2, default=str))
        if r.get("attached_scan_url"):
            ext = r["attached_scan_url"].rsplit(".", 1)[-1] if "." in r["attached_scan_url"] else "bin"
            await _add_url(f"reviews/{kind}-{date}-{r['id']}-scan.{ext}", r["attached_scan_url"])
        for p in (r.get("photos") or []):
            if p.get("url"):
                ext = p["url"].rsplit(".", 1)[-1] if "." in p["url"] else "jpg"
                await _add_url(f"reviews/{kind}-{date}-{r['id']}-photo-{p['id']}.{ext}", p["url"])

    # 4. Checklist documents
    docs = await db.child_extras.find({"child_id": child_id, "kind": "file_doc"}, {"_id": 0}).to_list(200)
    for d in docs:
        if d.get("file_url"):
            ext = d["file_url"].rsplit(".", 1)[-1] if "." in d["file_url"] else "bin"
            safe_type = (d.get("doc_type") or "other").replace("/", "_")
            await _add_url(f"documents/{safe_type}-{d['id']}.{ext}", d["file_url"])

    # 5. Gallery photos
    gallery = await db.child_extras.find({"child_id": child_id, "kind": "gallery"}, {"_id": 0}).to_list(200)
    for g in gallery:
        if g.get("file_url"):
            ext = g["file_url"].rsplit(".", 1)[-1] if "." in g["file_url"] else "jpg"
            await _add_url(f"gallery/{g['id']}.{ext}", g["file_url"])

    # 6. INDEX.md — manifest + checklist coverage
    doc_type_seen = {d.get("doc_type") for d in docs}
    review_kinds = {r.get("kind") for r in reviews}
    lines = [
        f"# 58:12 Connect — Child File Bundle for {child.get('name', '?')}",
        f"_Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} by {current_user.get('name', '')}_",
        "",
        f"- Child ID: {child_id}",
        f"- Reviews: {len(reviews)} (school: {1 if 'school_progress' in review_kinds else 0}, welfare: {1 if 'welfare_visit' in review_kinds else 0}, medical: {1 if 'medical_exam' in review_kinds else 0})",
        f"- Documents (checklist): {len(docs)}",
        f"- Gallery photos: {len(gallery)}",
        "",
        "## Checklist coverage",
        f"- [{'x' if child.get('photo_url') else ' '}] Child's photo",
        f"- [{'x' if 'ovcmis_form_008' in doc_type_seen else ' '}] OVCMIS Form 008 — Child Enrollment & Monitoring Card",
        f"- [{'x' if 'sponsorship_assessment' in doc_type_seen else ' '}] 58:12 Child Sponsorship Assessment",
        f"- [{'x' if 'lc1_introduction_letter' in doc_type_seen else ' '}] LC1 Introduction Letter",
        f"- [{'x' if 'school_report' in doc_type_seen else ' '}] Previous / Current School Report",
        f"- [{'x' if 'guardian_national_id' in doc_type_seen else ' '}] Parent / Guardian National ID",
        f"- [{'x' if 'family_consent_letter' in doc_type_seen else ' '}] Family Consent Letter",
        f"- [{'x' if 'medical_assessment' in doc_type_seen or 'medical_exam' in review_kinds else ' '}] Medical Assessment Form",
        f"- [{'x' if 'welfare_visit' in review_kinds or 'school_progress' in review_kinds else ' '}] 58:12 Welfare Review and Visit Forms",
        f"- [{'x' if 'exit_form' in doc_type_seen else ' '}] Exit Form",
        f"- [{'x' if 'sponsor_letter_in' in doc_type_seen or 'sponsor_letter_out' in doc_type_seen else ' '}] Letters to / from the Sponsor",
    ]
    zf.writestr("INDEX.md", "\n".join(lines))

    zf.close()
    buf.seek(0)
    name_safe = (child.get("name") or "child").replace(" ", "_").replace("/", "_")
    fname = f"{name_safe}-file-bundle-{datetime.now(timezone.utc).strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
