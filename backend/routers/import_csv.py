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

            # --- Father: goes to db.guests (parent) ---
            father_name = str(row.get("fathers_names") or row.get("father_name") or "").strip()
            father_phone = str(row.get("fathers_phone") or row.get("father_phone") or "").strip()
            father_email = str(row.get("fathers_email") or "").strip().lower()
            if father_name:
                # Dedup by name + phone/email in guests
                dedup_or = [{"name": {"$regex": f"^{father_name}$", "$options": "i"}}]
                if father_phone:
                    dedup_or.append({"phone": father_phone})
                if father_email:
                    dedup_or.append({"email": father_email})
                existing_father = await db.guests.find_one({"$or": dedup_or})
                if not existing_father:
                    await db.guests.insert_one({
                        "id": f"gst_{str(uuid.uuid4())[:8]}",
                        "name": father_name,
                        "phone": father_phone,
                        "email": father_email,
                        "is_parent": True,
                        "family_id": family_id,
                        "visit_date": datetime.now(timezone.utc).date().isoformat(),
                        "referred_by": f"Parent of {child_full_name}",
                        "address": str(row.get("address") or "").strip(),
                        "notes": "Imported as parent/guest",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    imported_parents += 1
                else:
                    # Link family_id if missing
                    if not existing_father.get("family_id"):
                        await db.guests.update_one({"id": existing_father["id"]}, {"$set": {"family_id": family_id}})

            # --- Mother: goes to db.guests (parent) ---
            mother_name = str(row.get("mothers_names") or row.get("mother_name") or "").strip()
            mother_phone = str(row.get("mothers_phone") or row.get("mother_phone") or "").strip()
            mother_email = str(row.get("mothers_email") or "").strip().lower()
            if mother_name:
                dedup_or = [{"name": {"$regex": f"^{mother_name}$", "$options": "i"}}]
                if mother_phone:
                    dedup_or.append({"phone": mother_phone})
                if mother_email:
                    dedup_or.append({"email": mother_email})
                existing_mother = await db.guests.find_one({"$or": dedup_or})
                if not existing_mother:
                    await db.guests.insert_one({
                        "id": f"gst_{str(uuid.uuid4())[:8]}",
                        "name": mother_name,
                        "phone": mother_phone,
                        "email": mother_email,
                        "is_parent": True,
                        "family_id": family_id,
                        "visit_date": datetime.now(timezone.utc).date().isoformat(),
                        "referred_by": f"Parent of {child_full_name}",
                        "address": str(row.get("address") or "").strip(),
                        "notes": "Imported as parent/guest",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    imported_parents += 1
                else:
                    if not existing_mother.get("family_id"):
                        await db.guests.update_one({"id": existing_mother["id"]}, {"$set": {"family_id": family_id}})

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


# ========== TEMPLATE DOWNLOADS ==========

from fastapi.responses import StreamingResponse

@router.get("/import/template/children")
async def download_children_template(current_user: dict = Depends(get_current_user)):
    """Download CSV template for children import with all fields including campus"""
    headers = ["name", "date_of_birth", "gender", "grade", "class_group", "family_name",
               "father_name", "father_phone", "father_email", "mother_name", "mother_phone", "mother_email",
               "campus", "location_id", "allergies", "medical_notes", "special_needs", "emergency_contact", "notes"]
    example = ["John Doe", "2018-03-15", "male", "P3", "Blue Group", "Doe",
               "James Doe", "+256700111222", "james@example.com", "Jane Doe", "+256700333444", "jane@example.com",
               "58:12 Uganda", "", "None", "", "", "+256700111222", ""]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerow(example)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=children_import_template.csv"})


@router.get("/import/template/staff")
async def download_staff_template(current_user: dict = Depends(get_current_user)):
    """Download CSV template for staff import"""
    headers = ["name", "email", "phone", "national_id", "role", "department", "campus", "location_id",
               "gender", "date_of_birth", "address", "emergency_contact", "notes"]
    example = ["Jane Smith", "jane@5812.org", "+256700555666", "CM12345", "Staff", "Programs",
               "58:12 Uganda", "", "female", "1990-01-01", "Kampala", "+256700777888", ""]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerow(example)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=staff_import_template.csv"})


@router.get("/import/template/guests")
async def download_guests_template(current_user: dict = Depends(get_current_user)):
    """Download CSV template for guests import"""
    headers = ["name", "phone", "email", "is_parent", "campus", "location_id",
               "purpose", "visit_date", "notes"]
    example = ["Tom Visitor", "+256700999000", "tom@example.com", "false", "58:12 Uganda", "",
               "Church Visit", "2026-02-20", ""]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerow(example)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=guests_import_template.csv"})
