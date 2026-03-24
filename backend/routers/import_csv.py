"""CSV file upload and data import routes"""
from fastapi import APIRouter, Depends, UploadFile, File
from deps import db, get_current_user, require_manager, _audit, logger
from datetime import datetime, timezone
import uuid
import csv
import io

router = APIRouter(prefix="/api", tags=["import"])


# ========== JSON IMPORT ==========

@router.post("/import/children-parents")
async def import_children_parents(data: dict, current_user: dict = Depends(get_current_user)):
    rows = data.get("rows", [])
    imported_children = 0
    imported_parents = 0
    imported_families = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            fname = str(row.get("first_name") or "").strip()
            lname = str(row.get("last_name") or "").strip()
            child_full_name = str(row.get("name") or f"{fname} {lname}").strip()
            if not child_full_name:
                errors.append(f"Row {i+1}: child name required (first_name or name)")
                continue

            family_name = str(row.get("family_name") or lname or child_full_name.split()[-1]).strip()

            # --- Family: lookup by family_name field (correct schema) ---
            family = await db.families.find_one({"family_name": {"$regex": f"^{family_name}$", "$options": "i"}})
            if not family:
                father_name = str(row.get("fathers_names") or row.get("father_name") or "").strip()
                mother_name = str(row.get("mothers_names") or row.get("mother_name") or "").strip()
                primary_contact = father_name or mother_name or child_full_name
                family_id = f"fam_{str(uuid.uuid4())[:8]}"
                family = {
                    "id": family_id,
                    "family_name": family_name,
                    "primary_contact_name": primary_contact,
                    "primary_contact_email": str(row.get("email") or "").strip(),
                    "primary_contact_phone": str(row.get("fathers_phone") or row.get("mothers_phone") or row.get("phone") or "").strip(),
                    "address": str(row.get("address") or "").strip(),
                    "notes": "",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"],
                }
                await db.families.insert_one(family)
                imported_families += 1
            else:
                family_id = family["id"]

            # --- Child: goes to db.children (not db.members) ---
            # Dedup by exact name + family_id
            existing_child = await db.children.find_one({
                "name": {"$regex": f"^{child_full_name}$", "$options": "i"},
                "family_id": family_id
            })
            if not existing_child:
                child_doc = {
                    "id": f"chd_{str(uuid.uuid4())[:8]}",
                    "name": child_full_name,
                    "date_of_birth": str(row.get("date_of_birth") or "").strip(),
                    "gender": str(row.get("gender") or "").strip().lower(),
                    "family_id": family_id,
                    "class_group": str(row.get("grade") or row.get("class_group") or "").strip(),
                    "allergies": str(row.get("allergies") or "").strip(),
                    "medical_notes": str(row.get("medical_notes") or "").strip(),
                    "special_needs": str(row.get("special_needs") or "").strip(),
                    "emergency_contact": str(row.get("emergency_contact") or "").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.children.insert_one(child_doc)
                imported_children += 1

            # --- Father: goes to db.members (parent) ---
            father_name = str(row.get("fathers_names") or row.get("father_name") or "").strip()
            father_phone = str(row.get("fathers_phone") or row.get("father_phone") or "").strip()
            if father_name:
                # Dedup by name + phone combination
                dedup_q = {"name": {"$regex": f"^{father_name}$", "$options": "i"}, "is_parent": True}
                if father_phone:
                    dedup_q["$or"] = [{"phone": father_phone}, {"name": {"$regex": f"^{father_name}$", "$options": "i"}}]
                existing_father = await db.members.find_one(dedup_q)
                if not existing_father:
                    await db.members.insert_one({
                        "id": f"m_{str(uuid.uuid4())[:8]}",
                        "name": father_name,
                        "phone": father_phone,
                        "email": str(row.get("fathers_email") or "").strip().lower(),
                        "role": "Parent",
                        "is_parent": True,
                        "gender": "male",
                        "family_id": family_id,
                        "group": "General",
                        "status": "active",
                        "join_date": datetime.now(timezone.utc).date().isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    imported_parents += 1
                else:
                    # Update family_id if missing
                    if not existing_father.get("family_id"):
                        await db.members.update_one({"id": existing_father["id"]}, {"$set": {"family_id": family_id}})

            # --- Mother ---
            mother_name = str(row.get("mothers_names") or row.get("mother_name") or "").strip()
            mother_phone = str(row.get("mothers_phone") or row.get("mother_phone") or "").strip()
            if mother_name:
                dedup_q = {"name": {"$regex": f"^{mother_name}$", "$options": "i"}, "is_parent": True}
                if mother_phone:
                    dedup_q["$or"] = [{"phone": mother_phone}, {"name": {"$regex": f"^{mother_name}$", "$options": "i"}}]
                existing_mother = await db.members.find_one(dedup_q)
                if not existing_mother:
                    await db.members.insert_one({
                        "id": f"m_{str(uuid.uuid4())[:8]}",
                        "name": mother_name,
                        "phone": mother_phone,
                        "email": str(row.get("mothers_email") or "").strip().lower(),
                        "role": "Parent",
                        "is_parent": True,
                        "gender": "female",
                        "family_id": family_id,
                        "group": "General",
                        "status": "active",
                        "join_date": datetime.now(timezone.utc).date().isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    imported_parents += 1
                else:
                    if not existing_mother.get("family_id"):
                        await db.members.update_one({"id": existing_mother["id"]}, {"$set": {"family_id": family_id}})

        except Exception as e:
            logger.error(f"Import row {i+1}: {e}")
            errors.append(f"Row {i+1}: {str(e)}")

    await _audit(current_user["id"], "create", "csv_import",
                 f"{imported_children}_children_{imported_parents}_parents_{imported_families}_families")
    return {
        "imported_children": imported_children,
        "imported_parents": imported_parents,
        "imported_families": imported_families,
        "errors": errors,
        "total_rows": len(rows),
    }


@router.post("/import/staff")
async def import_staff(data: dict, current_user: dict = Depends(require_manager)):
    rows = data.get("rows", [])
    imported = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            name = str(row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {i+1}: name required")
                continue
            email = str(row.get("email") or "").strip().lower()
            if email:
                existing = await db.members.find_one({"email": email})
                if existing:
                    errors.append(f"Row {i+1}: Email {email} already exists")
                    continue
            doc = {
                "id": f"m_{str(uuid.uuid4())[:8]}", "name": name, "email": email,
                "phone": str(row.get("phone") or "").strip(),
                "national_id": str(row.get("national_id") or "").strip(),
                "role": str(row.get("role") or "Staff").strip(),
                "department": str(row.get("department") or "").strip(),
                "group": "", "gender": "", "status": "active",
                "join_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "staff_import", f"{imported}_staff")
    return {"imported": imported, "errors": errors, "total": len(rows)}


# ========== REAL CSV FILE UPLOAD ==========

@router.post("/import/csv/members")
async def import_csv_members_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    errors = []
    for i, row in enumerate(reader):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {i+1}: name required")
                continue
            email = (row.get("email") or "").strip().lower()
            if email:
                existing = await db.members.find_one({"email": email})
                if existing:
                    errors.append(f"Row {i+1}: Email {email} exists")
                    continue
            doc = {
                "id": f"m_{str(uuid.uuid4())[:8]}",
                "name": name, "email": email,
                "phone": (row.get("phone") or "").strip(),
                "national_id": (row.get("national_id") or "").strip(),
                "role": (row.get("role") or "Member").strip(),
                "group": (row.get("group") or "General").strip(),
                "gender": (row.get("gender") or "").strip().lower(),
                "department": (row.get("department") or "").strip(),
                "status": "active",
                "join_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "csv_file_import", f"{imported}_members")
    return {"imported": imported, "errors": errors}


@router.post("/import/csv/children-parents")
async def import_csv_children_parents_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    result = await import_children_parents({"rows": rows}, current_user)
    return result


@router.post("/import/csv/staff")
async def import_csv_staff_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    result = await import_staff({"rows": rows}, current_user)
    return result
