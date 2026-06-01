"""Bulk import for members + children (with auto-parent/family creation)."""
from fastapi import APIRouter, Depends
from deps import db, get_current_user, _audit
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["members"])


@router.post("/members/bulk-import")
async def bulk_import_members(file: str = None, members_data: list = None, current_user: dict = Depends(get_current_user)):
    if not members_data:
        return {"imported": 0, "errors": []}
    imported = 0
    errors = []
    for i, row in enumerate(members_data):
        try:
            if not row.get("name"):
                errors.append(f"Row {i+1}: Name is required")
                continue
            existing = await db.members.find_one({"email": row.get("email", "")})
            if existing and row.get("email"):
                errors.append(f"Row {i+1}: Email {row['email']} already exists")
                continue
            doc = {"id": f"m_{str(uuid.uuid4())[:8]}", "name": row.get("name", ""), "email": row.get("email", ""), "phone": row.get("phone", ""), "national_id": row.get("national_id", ""), "role": row.get("role", "Member"), "group": row.get("group", "General"), "gender": row.get("gender", ""), "status": "active", "join_date": datetime.now(timezone.utc).date().isoformat(), "location_id": row.get("location_id"), "created_at": datetime.now(timezone.utc).isoformat()}
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "bulk_import", f"{imported}_members")
    return {"imported": imported, "errors": errors, "total": len(members_data)}


@router.post("/children/bulk-import")
async def bulk_import_children(request_data: dict, current_user: dict = Depends(get_current_user)):
    """Import children with auto-creation of parents and families.
    Prevents duplicates; updates existing records with new info.
    Parents are created even without email addresses.
    Campus/location_id is auto-resolved from campus name if provided.
    Body: {"children": [{name, age, gender, family_name, parent_name, parent_phone, parent_email, campus, location_id}]}"""
    data = request_data.get("children", request_data.get("data", []))
    if not data:
        return {"imported": 0, "updated": 0, "parents_created": 0, "errors": ["No children data provided"], "total": 0}
    imported = 0
    updated = 0
    parents_created = 0
    errors = []
    family_cache = {}
    campus_cache = {}
    parent_cache = {}  # Track created parents by name+phone to skip repeated info

    for i, row in enumerate(data):
        try:
            child_name = (row.get("name") or "").strip()
            if not child_name:
                errors.append(f"Row {i+1}: Name required")
                continue

            family_name = (row.get("family_name") or "").strip()
            parent_name = (row.get("parent_name") or row.get("father_name") or row.get("mother_name") or "").strip()
            parent_phone = (row.get("parent_phone") or row.get("father_phone") or row.get("mother_phone") or "").strip()
            parent_email = (row.get("parent_email") or row.get("father_email") or row.get("mother_email") or "").strip().lower()
            campus_name = (row.get("campus") or "").strip()
            location_id = row.get("location_id", "")

            # Auto-resolve campus name to location_id; fall back to admin's active campus
            if campus_name and not location_id:
                if campus_name in campus_cache:
                    location_id = campus_cache[campus_name]
                else:
                    loc = await db.locations.find_one({"name": {"$regex": f"^{campus_name}$", "$options": "i"}}, {"_id": 0, "id": 1})
                    location_id = loc["id"] if loc else ""
                    campus_cache[campus_name] = location_id
            if not location_id:
                location_id = current_user.get("active_campus_id") or current_user.get("location_id") or ""

            # 1. Find or create family
            family_id = None
            if family_name:
                if family_name in family_cache:
                    family_id = family_cache[family_name]
                else:
                    existing_fam = await db.families.find_one({"family_name": {"$regex": f"^{family_name}$", "$options": "i"}})
                    if existing_fam:
                        family_id = existing_fam["id"]
                        merge_fields = {}
                        if location_id and not existing_fam.get("location_id"):
                            merge_fields["location_id"] = location_id
                        if parent_phone and not existing_fam.get("primary_contact_phone"):
                            merge_fields["primary_contact_phone"] = parent_phone
                        if parent_name and not existing_fam.get("primary_contact_name"):
                            merge_fields["primary_contact_name"] = parent_name
                        if merge_fields:
                            await db.families.update_one({"id": family_id}, {"$set": merge_fields})
                    else:
                        family_id = f"fam_{str(uuid.uuid4())[:8]}"
                        await db.families.insert_one({
                            "id": family_id, "family_name": family_name,
                            "primary_contact_name": parent_name, "primary_contact_phone": parent_phone,
                            "primary_contact_email": parent_email, "location_id": location_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                    family_cache[family_name] = family_id

            # 2. Find or create parent (even without email) — skip if already handled in this batch
            if parent_name:
                parent_key = f"{parent_name.lower()}|{parent_phone}"
                if parent_key not in parent_cache:
                    parent_q_conditions = [{"name": {"$regex": f"^{parent_name}$", "$options": "i"}, "is_parent": True}]
                    if parent_phone:
                        parent_q_conditions.append({"phone": parent_phone, "is_parent": True})
                    existing_parent = await db.guests.find_one({"$or": parent_q_conditions})
                    if not existing_parent:
                        staff_parent = await db.users.find_one({"name": {"$regex": f"^{parent_name}$", "$options": "i"}, "is_parent": True})
                        if not staff_parent:
                            await db.guests.insert_one({
                                "id": f"gst_{str(uuid.uuid4())[:8]}", "name": parent_name,
                                "email": parent_email, "phone": parent_phone,
                                "is_parent": True, "family_id": family_id, "location_id": location_id,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            })
                            parents_created += 1
                    else:
                        merge = {}
                        if family_id and not existing_parent.get("family_id"):
                            merge["family_id"] = family_id
                        if parent_phone and not existing_parent.get("phone"):
                            merge["phone"] = parent_phone
                        if location_id and not existing_parent.get("location_id"):
                            merge["location_id"] = location_id
                        if merge:
                            await db.guests.update_one({"id": existing_parent["id"]}, {"$set": merge})
                    parent_cache[parent_key] = True

            # Also handle second parent (father/mother) if both provided — skip if already in cache
            father_name = (row.get("father_name") or "").strip()
            mother_name = (row.get("mother_name") or "").strip()
            for pname, pphone, pemail in [
                (father_name, (row.get("father_phone") or "").strip(), (row.get("father_email") or "").strip().lower()),
                (mother_name, (row.get("mother_phone") or "").strip(), (row.get("mother_email") or "").strip().lower()),
            ]:
                if pname and pname != parent_name:
                    p_key = f"{pname.lower()}|{pphone}"
                    if p_key in parent_cache:
                        continue
                    p_conditions = [{"name": {"$regex": f"^{pname}$", "$options": "i"}, "is_parent": True}]
                    if pphone:
                        p_conditions.append({"phone": pphone, "is_parent": True})
                    existing_p = await db.guests.find_one({"$or": p_conditions})
                    if not existing_p:
                        await db.guests.insert_one({
                            "id": f"gst_{str(uuid.uuid4())[:8]}", "name": pname,
                            "email": pemail, "phone": pphone,
                            "is_parent": True, "family_id": family_id, "location_id": location_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        parents_created += 1
                    parent_cache[p_key] = True

            # 3. Find or create/update child
            child_q = {"name": {"$regex": f"^{child_name}$", "$options": "i"}}
            if family_id:
                child_q["family_id"] = family_id
            existing_child = await db.children.find_one(child_q)
            if existing_child:
                update_fields = {}
                for k in ("age", "gender", "date_of_birth", "medical_info", "allergies", "grade", "class_group"):
                    if row.get(k) and row[k] != existing_child.get(k):
                        update_fields[k] = row[k]
                if location_id and location_id != existing_child.get("location_id"):
                    update_fields["location_id"] = location_id
                if family_id and not existing_child.get("family_id"):
                    update_fields["family_id"] = family_id
                if update_fields:
                    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await db.children.update_one({"id": existing_child["id"]}, {"$set": update_fields})
                    updated += 1
            else:
                await db.children.insert_one({
                    "id": f"chd_{str(uuid.uuid4())[:8]}", "name": child_name,
                    "age": row.get("age"), "gender": row.get("gender", ""),
                    "date_of_birth": row.get("date_of_birth", ""),
                    "family_id": family_id, "location_id": location_id,
                    "medical_info": row.get("medical_info", ""), "allergies": row.get("allergies", ""),
                    "grade": row.get("grade", ""), "class_group": row.get("class_group", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    return {"imported": imported, "updated": updated, "parents_created": parents_created, "errors": errors, "total": len(data)}
